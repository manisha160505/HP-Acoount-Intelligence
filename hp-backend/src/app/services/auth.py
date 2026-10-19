"""Sign in, refresh, sign out and change password.

Returns plain values; setting and clearing cookies is the router's job.
"""

import logging
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import PyMongoError

from app.config.settings import settings
from app.core.security import (
    create_access_token,
    generate_recovery_code,
    get_password_hash,
    normalize_recovery_code,
    password_problem,
    verify_password,
)
from app.database.mongodb import get_db
from app.errors import APIError, ErrorCode
from app.schemas.user import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    TokenResponse,
    UserLogin,
    UserResponse,
)
from app.services import sessions, user_audit
from app.services.usage import record_login
from app.services.users_admin import is_user_active

logger = logging.getLogger(__name__)


def _user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name") or user["email"],
        role=user["role"],
        must_change_password=bool(user.get("must_change_password")),
        tour_completed_at=user.get("tour_completed_at"),
        admin_tour_completed_at=user.get("admin_tour_completed_at"),
    )


def _token_response(user: dict, sid: str) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user["_id"]), user["role"], sid),
        expires_in=settings.ACCESS_TOKEN_MINUTES * 60,
        user=_user_response(user),
    )


def authenticate_user(login_data: UserLogin, user_agent: str = "") -> tuple[TokenResponse, str]:
    """Returns the response body and the refresh token for the cookie."""
    db = get_db()
    users_collection = db["users"]
    user = users_collection.find_one({"email": login_data.email.lower().strip()})

    if not user or not user.get("password_hash") \
            or not verify_password(login_data.password, user["password_hash"]):
        raise APIError(ErrorCode.INVALID_CREDENTIALS, "Incorrect email or password")

    # Checked after the password, so the message cannot be used to learn
    # which emails have accounts.
    if not is_user_active(user):
        raise APIError(ErrorCode.FORBIDDEN,
                       "This account has been deactivated. Contact your administrator.")

    sid, refresh_token = sessions.create(db, str(user["_id"]), user_agent)

    # Bookkeeping only: neither write may fail the sign-in.
    try:
        users_collection.update_one({"_id": user["_id"]},
                                    {"$set": {"last_login_at": datetime.now(UTC)}})
    except PyMongoError:
        logger.exception("auth: could not record last_login_at")
    record_login(db, user)

    return _token_response(user, sid), refresh_token


def refresh_session(refresh_token: str | None) -> tuple[TokenResponse, str | None]:
    """A new access token for a live session, and the refresh token to set
    (None: leave the cookie as it is)."""
    if not refresh_token:
        raise APIError(ErrorCode.UNAUTHENTICATED)
    db = get_db()
    try:
        session, new_refresh = sessions.refresh(db, refresh_token)
    except sessions.InvalidSession as exc:
        raise APIError(ErrorCode.TOKEN_EXPIRED) from exc
    try:
        user = db["users"].find_one({"_id": ObjectId(session["user_id"])})
    except (InvalidId, TypeError):
        user = None
    if not user or not is_user_active(user):
        sessions.revoke(db, session["_id"], "user missing or deactivated")
        raise APIError(ErrorCode.UNAUTHENTICATED)
    return _token_response(user, session["_id"]), new_refresh


def logout(session_id: str | None, refresh_token: str | None) -> None:
    db = get_db()
    if session_id:
        sessions.revoke(db, session_id, "logout")
    if refresh_token:
        sid, _, _secret = refresh_token.partition(".")
        if sid:
            sessions.revoke(db, sid, "logout")


def _issue_recovery_code(db, user_id) -> str:
    """A new recovery code for the user, replacing any earlier one. Returned
    once to show the user; only its hash is kept."""
    code = generate_recovery_code()
    db["users"].update_one({"_id": user_id}, {"$set": {
        "recovery_code_hash": get_password_hash(normalize_recovery_code(code)),
        "recovery_code_created_at": datetime.now(UTC),
    }})
    return code


def change_password(current_user: dict, body: ChangePasswordRequest) -> str:
    """Replace the caller's password and end every one of their sessions, this
    one included: they sign in again with the new password. Returns a new
    recovery code, to be shown to the user once."""
    db = get_db()
    oid = ObjectId(current_user["id"])
    user = db["users"].find_one({"_id": oid})
    if not user or not verify_password(body.current_password, user.get("password_hash") or ""):
        raise APIError(ErrorCode.INVALID_CREDENTIALS, "Your old password is not correct.",
                       status_code=400,
                       fields={"current_password": "Your old password is not correct."})
    problem = password_problem(body.new_password, user["password_hash"])
    if problem:
        raise APIError(ErrorCode.VALIDATION_ERROR, problem, fields={"new_password": problem})
    now = datetime.now(UTC)
    db["users"].update_one({"_id": oid}, {"$set": {
        "password_hash": get_password_hash(body.new_password),
        "must_change_password": False,
        "password_changed_at": now,
        "updated_at": now,
    }})
    sessions.revoke_user(db, current_user["id"], "password changed")
    user_audit.record(db, current_user, user_audit.PASSWORD_CHANGED, user,
                      {"first_sign_in": bool(user.get("must_change_password"))})
    logger.info("auth: user %s changed their password", current_user["id"])
    return _issue_recovery_code(db, oid)


# Compared against when the email is unknown, so an unknown email and a wrong
# code take the same time and give the same answer.
_DUMMY_HASH = get_password_hash("no-such-recovery-code")
_RECOVERY_REFUSED = "That email and recovery code do not match."


def recover_password(body: ForgotPasswordRequest) -> str:
    """Set a new password with the recovery code saved when the last one was
    set. No sign-in and no admin needed. The code works once: every session
    ends and a new code is returned, to be shown to the user once."""
    db = get_db()
    user = db["users"].find_one({"email": body.email.lower().strip()})
    stored = (user or {}).get("recovery_code_hash")
    matches = verify_password(normalize_recovery_code(body.recovery_code), stored or _DUMMY_HASH)
    if not user or not stored or not matches or not is_user_active(user):
        raise APIError(ErrorCode.INVALID_CREDENTIALS, _RECOVERY_REFUSED, status_code=400)
    problem = password_problem(body.new_password, user.get("password_hash"))
    if problem:
        raise APIError(ErrorCode.VALIDATION_ERROR, problem, fields={"new_password": problem})
    now = datetime.now(UTC)
    db["users"].update_one({"_id": user["_id"]}, {"$set": {
        "password_hash": get_password_hash(body.new_password),
        "must_change_password": False,
        "password_changed_at": now,
        "updated_at": now,
    }})
    sessions.revoke_user(db, str(user["_id"]), "password set with recovery code")
    actor = {"id": str(user["_id"]), "email": user["email"]}
    user_audit.record(db, actor, user_audit.PASSWORD_RECOVERED, user)
    logger.info("auth: user %s set a new password with their recovery code", user["_id"])
    return _issue_recovery_code(db, user["_id"])


# Which user field records each tour: the dashboard's, and the admin pages'.
TOUR_FIELDS = {"dashboard": "tour_completed_at", "admin": "admin_tour_completed_at"}


def mark_tour_completed(current_user: dict, tour: str = "dashboard") -> datetime:
    """Record that the user has been through a product tour, finished or
    closed. The first time is kept: replaying a feature's help later does not
    move it."""
    field = TOUR_FIELDS[tour]
    db = get_db()
    oid = ObjectId(current_user["id"])
    user = db["users"].find_one({"_id": oid}) or {}
    if user.get(field):
        return user[field]
    now = datetime.now(UTC)
    db["users"].update_one({"_id": oid}, {"$set": {field: now}})
    return now
