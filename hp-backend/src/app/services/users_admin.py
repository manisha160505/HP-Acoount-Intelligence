"""Admin-managed users: create, list, activate and deactivate.

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

from app.core.security import get_password_hash
from app.errors import APIError, ErrorCode
from app.schemas.admin_users import AdminUserCreate, AdminUserResponse

logger = logging.getLogger(__name__)

USERS = "users"


def ensure_indexes(db) -> None:
    """Unique email, enforced by the database rather than a find-then-insert
    check two concurrent requests could both pass.

    If existing rows already collide the build fails; that is logged and the
    app keeps running - the duplicate insert check in `create_user` still
    catches the common case, and the log names what has to be cleaned up."""
    try:
        db[USERS].create_index([("email", 1)], name="uniq_email", unique=True)
    except PyMongoError:
        logger.exception("users: could not build the unique email index - "
                         "duplicate emails may already exist.")


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
        full_name=user.get("full_name") or "",
        role=user.get("role") or "user",
        is_active=is_user_active(user),
        created_at=_aware(user.get("created_at")),
        last_login_at=_aware(user.get("last_login_at")),
    )


def create_user(db, data: AdminUserCreate) -> AdminUserResponse:
    email = data.email.lower().strip()
    if db[USERS].find_one({"email": email}):
        raise APIError(ErrorCode.ALREADY_EXISTS, "A user with that email already exists.",
                       fields={"email": "A user with that email already exists."})
    doc = {
        "email": email,
        "full_name": data.full_name.strip(),
        "password_hash": get_password_hash(data.password),
        # Never taken from the request: this path cannot create an admin.
        "role": "user",
        "is_active": True,
        "created_at": datetime.now(UTC),
        "last_login_at": None,
    }
    try:
        result = db[USERS].insert_one(doc)
    except DuplicateKeyError as exc:
        # The race the pre-check cannot close: the unique index settles it.
        raise APIError(ErrorCode.ALREADY_EXISTS, "A user with that email already exists.",
                       fields={"email": "A user with that email already exists."}) from exc
    doc["_id"] = result.inserted_id
    logger.info("users: created user %s", doc["_id"])
    return to_response(doc)


def list_users(db) -> list[AdminUserResponse]:
    rows = db[USERS].find({}).sort("created_at", 1)
    return [to_response(u) for u in rows]


def _object_id(user_id: str) -> ObjectId:
    try:
        return ObjectId(user_id)
    except (InvalidId, TypeError) as exc:
        raise APIError(ErrorCode.INVALID_ID_FORMAT) from exc


def set_active(db, user_id: str, is_active: bool, acting_admin_id: str) -> AdminUserResponse:
    oid = _object_id(user_id)
    user = db[USERS].find_one({"_id": oid})
    if not user:
        raise APIError(ErrorCode.USER_NOT_FOUND)
    if str(oid) == acting_admin_id and not is_active:
        # The only admin locking themselves out has no way back in short of
        # editing the database.
        raise APIError(ErrorCode.FORBIDDEN, "You cannot deactivate your own account.")
    db[USERS].update_one({"_id": oid}, {"$set": {"is_active": is_active,
                                                 "updated_at": datetime.now(UTC)}})
    user["is_active"] = is_active
    logger.info("users: user %s is_active=%s", oid, is_active)
    return to_response(user)
