"""Admin-managed users: create, list, activate, roles, account access, passwords.

Who may do what:
  - an admin manages sellers (role "user"): creates them, assigns accounts,
    resets passwords, deactivates and reactivates them;
  - only the super admin creates admins, changes roles, and manages admins;
  - nobody changes the super admin through the API, and nobody demotes,
    deactivates or resets themselves here (their own password changes through
    /auth/change-password).

Users are never deleted here. Deactivating keeps the document, so every usage
event that points at it stays attributable in analytics.

A user document written before this module existed has no `is_active`; it is
treated as active everywhere (`is_user_active`), so turning this on locks no
one out.
"""

import logging
from datetime import UTC, datetime

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError, PyMongoError

from app.core.security import generate_temporary_password, get_password_hash
from app.errors import APIError, ErrorCode
from app.schemas.admin_users import (
    AccountUser,
    AdminUserCreate,
    AdminUserCreated,
    AdminUserResponse,
    AuditEntry,
    PasswordResetResponse,
)
from app.services import sessions, user_audit

logger = logging.getLogger(__name__)

USERS = "users"
SUPER_ADMIN = "super_admin"
ADMIN_ROLES = ("admin", SUPER_ADMIN)


def ensure_indexes(db) -> None:
    """Unique email, enforced by the database rather than a find-then-insert
    check two concurrent requests could both pass.

    If existing rows already collide the build fails; that is logged and the
    app keeps running - the duplicate insert check in `create_user` still
    catches the common case, and the log names what has to be cleaned up."""
    try:
        db[USERS].create_index([("email", 1)], name="uniq_email", unique=True)
        db[USERS].create_index([("account_ids", 1)], name="by_account")
    except PyMongoError:
        logger.exception("users: could not build the unique email index - "
                         "duplicate emails may already exist.")
    user_audit.ensure_indexes(db)


def is_user_active(user: dict) -> bool:
    return user.get("is_active", True) is not False


def _aware(ts):
    # pymongo returns naive datetimes; every one here was written as UTC.
    return ts.replace(tzinfo=UTC) if isinstance(ts, datetime) and ts.tzinfo is None else ts


def to_response(user: dict) -> AdminUserResponse:
    """The public shape. Built field by field, so nothing else on the
    document - the password hash above all - can leak into a response."""
    return AdminUserResponse(
        id=str(user["_id"]),
        email=user["email"],
        full_name=user.get("full_name") or user["email"],
        role=user.get("role") or "user",
        is_active=is_user_active(user),
        must_change_password=bool(user.get("must_change_password")),
        account_ids=[str(a) for a in user.get("account_ids") or []],
        created_at=_aware(user.get("created_at")),
        last_login_at=_aware(user.get("last_login_at")),
    )


def _object_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except (InvalidId, TypeError) as exc:
        raise APIError(ErrorCode.INVALID_ID_FORMAT) from exc


def _load(db, user_id: str) -> dict:
    user = db[USERS].find_one({"_id": _object_id(user_id)})
    if not user:
        raise APIError(ErrorCode.USER_NOT_FOUND)
    return user


def _may_manage(actor: dict, target: dict, *, allow_self: bool = False) -> None:
    """Raise unless `actor` may change `target`."""
    if not allow_self and str(target["_id"]) == actor["id"]:
        raise APIError(ErrorCode.FORBIDDEN, "You cannot change your own account here.")
    if target.get("role") == SUPER_ADMIN:
        raise APIError(ErrorCode.FORBIDDEN, "The super admin cannot be changed here.")
    if target.get("role") in ADMIN_ROLES and actor["role"] != SUPER_ADMIN:
        raise APIError(ErrorCode.FORBIDDEN, "Only the super admin can manage admins.")


def _valid_account_ids(db, account_ids: list[str]) -> list[str]:
    """`account_ids`, de-duplicated in order, each an existing account; raises
    naming the ones that are not."""
    wanted = list(dict.fromkeys(a.strip() for a in account_ids if a and a.strip()))
    bad = [a for a in wanted if not ObjectId.is_valid(a)]
    found = {str(d["_id"]) for d in db["accounts"].find(
        {"_id": {"$in": [ObjectId(a) for a in wanted if ObjectId.is_valid(a)]}}, {"_id": 1})}
    bad += [a for a in wanted if ObjectId.is_valid(a) and a not in found]
    if bad:
        raise APIError(ErrorCode.VALIDATION_ERROR, "Some accounts do not exist: %s" % ", ".join(bad),
                       fields={"account_ids": "Unknown account(s): %s" % ", ".join(bad)})
    return wanted


def _account_names(db, account_ids: list[str]) -> dict[str, str]:
    ids = [ObjectId(a) for a in account_ids if ObjectId.is_valid(a)]
    return {str(d["_id"]): d.get("name") or str(d["_id"])
            for d in db["accounts"].find({"_id": {"$in": ids}}, {"name": 1})}


# ------------------------------------------------------------------ create

def create_user(db, data: AdminUserCreate, actor: dict) -> AdminUserCreated:
    if data.role in ADMIN_ROLES and actor["role"] != SUPER_ADMIN:
        raise APIError(ErrorCode.FORBIDDEN, "Only the super admin can create admins.")
    email = data.email.lower().strip()
    if db[USERS].find_one({"email": email}):
        raise APIError(ErrorCode.ALREADY_EXISTS, "A user with that email already exists.",
                       fields={"email": "A user with that email already exists."})
    account_ids = _valid_account_ids(db, data.account_ids)
    generated = None if data.password else generate_temporary_password()
    now = datetime.now(UTC)
    doc = {
        "email": email,
        "full_name": (data.full_name or "").strip() or email,
        "password_hash": get_password_hash(data.password or generated),
        "role": data.role,
        "account_ids": account_ids,
        "is_active": True,
        # The password was chosen by an admin and shared with them; the user
        # replaces it at first sign-in before reaching anything else.
        "must_change_password": True,
        "created_at": now,
        "created_by": actor["id"],
        "last_login_at": None,
    }
    try:
        result = db[USERS].insert_one(doc)
    except DuplicateKeyError as exc:
        # The race the pre-check cannot close: the unique index settles it.
        raise APIError(ErrorCode.ALREADY_EXISTS, "A user with that email already exists.",
                       fields={"email": "A user with that email already exists."}) from exc
    doc["_id"] = result.inserted_id
    user_audit.record(db, actor, user_audit.USER_CREATED, doc,
                      {"role": data.role, "accounts": list(_account_names(db, account_ids).values())})
    logger.info("users: %s created user %s (%s)", actor["id"], doc["_id"], data.role)
    return AdminUserCreated(**to_response(doc).model_dump(), temporary_password=generated)


def list_users(db) -> list[AdminUserResponse]:
    rows = db[USERS].find({}).sort("created_at", 1)
    return [to_response(u) for u in rows]


# ------------------------------------------------------------------ change

def set_active(db, user_id: str, is_active: bool, actor: dict) -> AdminUserResponse:
    user = _load(db, user_id)
    if str(user["_id"]) == actor["id"] and not is_active:
        # The only admin locking themselves out has no way back in short of
        # editing the database.
        raise APIError(ErrorCode.FORBIDDEN, "You cannot deactivate your own account.")
    _may_manage(actor, user, allow_self=True)
    if is_user_active(user) == is_active:
        return to_response(user)
    db[USERS].update_one({"_id": user["_id"]}, {"$set": {"is_active": is_active,
                                                         "updated_at": datetime.now(UTC)}})
    if not is_active:
        # Signed out now, not when their access token runs out.
        sessions.revoke_user(db, str(user["_id"]), "deactivated by %s" % actor["id"])
    user["is_active"] = is_active
    user_audit.record(db, actor, user_audit.USER_ACTIVATED if is_active
                      else user_audit.USER_DEACTIVATED, user)
    logger.info("users: user %s is_active=%s", user["_id"], is_active)
    return to_response(user)


def set_role(db, user_id: str, role: str, actor: dict) -> AdminUserResponse:
    """Super admin only (the router checks): make a seller an admin or back."""
    user = _load(db, user_id)
    _may_manage(actor, user)
    old = user.get("role") or "user"
    if old == role:
        return to_response(user)
    db[USERS].update_one({"_id": user["_id"]}, {"$set": {"role": role,
                                                         "updated_at": datetime.now(UTC)}})
    user["role"] = role
    user_audit.record(db, actor, user_audit.ROLE_CHANGED, user, {"from": old, "to": role})
    return to_response(user)


def set_accounts(db, user_id: str, account_ids: list[str], actor: dict) -> AdminUserResponse:
    """Replace a seller's accounts. Takes effect on their next request."""
    user = _load(db, user_id)
    _may_manage(actor, user)
    if user.get("role") in ADMIN_ROLES:
        raise APIError(ErrorCode.VALIDATION_ERROR, "Admins already see every account.")
    new = _valid_account_ids(db, account_ids)
    old = [str(a) for a in user.get("account_ids") or []]
    db[USERS].update_one({"_id": user["_id"]}, {"$set": {"account_ids": new,
                                                         "updated_at": datetime.now(UTC)}})
    user["account_ids"] = new
    added = [a for a in new if a not in old]
    removed = [a for a in old if a not in new]
    if added or removed:
        names = _account_names(db, added + removed)
        user_audit.record(db, actor, user_audit.ACCOUNTS_CHANGED, user, {
            "added": [names.get(a, a) for a in added],
            "removed": [names.get(a, a) for a in removed],
        })
    return to_response(user)


def reset_password(db, user_id: str, password: str | None, actor: dict) -> PasswordResetResponse:
    """A new temporary password: every session ends and the user must replace
    it at their next sign-in. Generated when `password` is None."""
    user = _load(db, user_id)
    _may_manage(actor, user)
    generated = None if password else generate_temporary_password()
    now = datetime.now(UTC)
    db[USERS].update_one({"_id": user["_id"]}, {"$set": {
        "password_hash": get_password_hash(password or generated),
        "must_change_password": True,
        "updated_at": now,
    }})
    sessions.revoke_user(db, str(user["_id"]), "password reset by %s" % actor["id"])
    user["must_change_password"] = True
    user_audit.record(db, actor, user_audit.PASSWORD_RESET, user)
    return PasswordResetResponse(user=to_response(user), temporary_password=generated)


# ------------------------------------------------------------------- reads

def users_for_account(db, account_id: str) -> list[AccountUser]:
    """The sellers assigned to `account_id`. Admins see every account and are
    not listed."""
    rows = db[USERS].find({"account_ids": account_id, "role": "user"}).sort("email", 1)
    return [AccountUser(id=str(u["_id"]), email=u["email"],
                        full_name=u.get("full_name") or u["email"], role=u.get("role") or "user",
                        is_active=is_user_active(u)) for u in rows]


def audit_log(db, target_id: str | None = None, limit: int = 200) -> list[AuditEntry]:
    if target_id:
        _object_id(target_id)
    return [AuditEntry(id=str(r["_id"]), ts=_aware(r["ts"]), actor_email=r.get("actor_email"),
                       action=r["action"], target_email=r.get("target_email"),
                       details=r.get("details") or {})
            for r in user_audit.recent(db, target_id, limit)]
