"""Sign-in sessions: what keeps a seller signed in, and what signs them out.

A session is one sign-in on one browser. The browser holds its refresh token in
an httpOnly cookie; the database holds only a hash of it. Each refresh swaps the
token for a new one and pushes the idle expiry out, so a session lives
SESSION_IDLE_DAYS past its last use and never longer than SESSION_MAX_DAYS.

Access tokens name their session (`sid`) and every request checks it is still
live, so revoking a session - logout, a password change, a deactivation, or the
super admin's "sign out everyone" - takes effect on the next request.

Refresh-token reuse: a token that was already swapped is honoured for
ROTATION_GRACE_SECONDS (two tabs refreshing at once both send the old cookie)
without being swapped again. Presented after that, it can only be a copy - so
the whole session is revoked.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta

from pymongo import ReturnDocument
from pymongo.errors import PyMongoError

from app.config.settings import settings

logger = logging.getLogger(__name__)

SESSIONS = "auth_sessions"
ROTATION_GRACE_SECONDS = 30


class InvalidSession(Exception):
    pass


def ensure_indexes(db) -> None:
    try:
        db[SESSIONS].create_index([("user_id", 1)], name="by_user")
        # Mongo drops a session once its hard limit has passed.
        db[SESSIONS].create_index([("max_expires_at", 1)], name="ttl_max_expires",
                                  expireAfterSeconds=0)
    except PyMongoError:
        logger.exception("sessions: could not build indexes")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(ts):
    # pymongo returns naive datetimes; every one here was written as UTC.
    return ts.replace(tzinfo=UTC) if isinstance(ts, datetime) and ts.tzinfo is None else ts


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _split(refresh_token: str) -> tuple[str, str]:
    sid, _, secret = (refresh_token or "").partition(".")
    if not sid or not secret:
        raise InvalidSession("malformed refresh token")
    return sid, secret


def _live(doc: dict | None, now: datetime) -> bool:
    return bool(doc) and doc.get("revoked_at") is None \
        and _aware(doc["idle_expires_at"]) > now and _aware(doc["max_expires_at"]) > now


def create(db, user_id: str, user_agent: str = "") -> tuple[str, str]:
    """A new session for `user_id`. Returns (session id, refresh token)."""
    now = _now()
    sid = secrets.token_urlsafe(16)
    secret = secrets.token_urlsafe(32)
    db[SESSIONS].insert_one({
        "_id": sid,
        "user_id": user_id,
        "secret_hash": _hash(secret),
        "prev_secret_hash": None,
        "rotated_at": None,
        "created_at": now,
        "last_used_at": now,
        "idle_expires_at": now + timedelta(days=settings.SESSION_IDLE_DAYS),
        "max_expires_at": now + timedelta(days=settings.SESSION_MAX_DAYS),
        "revoked_at": None,
        "revoked_reason": None,
        "user_agent": (user_agent or "")[:300],
    })
    return sid, "%s.%s" % (sid, secret)


def is_live(db, sid: str, user_id: str) -> bool:
    doc = db[SESSIONS].find_one({"_id": sid})
    return _live(doc, _now()) and doc.get("user_id") == user_id


def refresh(db, refresh_token: str) -> tuple[dict, str | None]:
    """Swap a refresh token. Returns (session, new refresh token).

    The new token is None inside the rotation grace window: the caller issues an
    access token but leaves the cookie alone, since the browser already holds
    the newer one. Raises InvalidSession for anything that should sign out.
    """
    sid, secret = _split(refresh_token)
    now = _now()
    doc = db[SESSIONS].find_one({"_id": sid})
    if not _live(doc, now):
        raise InvalidSession("session ended")
    presented = _hash(secret)

    if hmac.compare_digest(presented, doc["secret_hash"]):
        new_secret = secrets.token_urlsafe(32)
        # Conditional on the hash just checked: of two concurrent swaps only one
        # lands; the other falls through to the grace check on its retry.
        updated = db[SESSIONS].find_one_and_update(
            {"_id": sid, "secret_hash": presented, "revoked_at": None},
            {"$set": {
                "secret_hash": _hash(new_secret),
                "prev_secret_hash": presented,
                "rotated_at": now,
                "last_used_at": now,
                "idle_expires_at": min(now + timedelta(days=settings.SESSION_IDLE_DAYS),
                                       _aware(doc["max_expires_at"])),
            }},
            return_document=ReturnDocument.AFTER)
        if updated:
            return updated, "%s.%s" % (sid, new_secret)
        doc = db[SESSIONS].find_one({"_id": sid})
        if not _live(doc, now):
            raise InvalidSession("session ended")

    rotated_at = _aware(doc.get("rotated_at"))
    if doc.get("prev_secret_hash") and hmac.compare_digest(presented, doc["prev_secret_hash"]) \
            and rotated_at and (now - rotated_at).total_seconds() <= ROTATION_GRACE_SECONDS:
        return doc, None

    revoke(db, sid, "refresh token reused")
    logger.warning("sessions: refresh token reuse on session %s; session revoked", sid)
    raise InvalidSession("refresh token reused")


def revoke(db, sid: str, reason: str) -> None:
    db[SESSIONS].update_one({"_id": sid, "revoked_at": None},
                            {"$set": {"revoked_at": _now(), "revoked_reason": reason}})


def revoke_user(db, user_id: str, reason: str, keep_sid: str | None = None) -> int:
    query = {"user_id": user_id, "revoked_at": None}
    if keep_sid:
        query["_id"] = {"$ne": keep_sid}
    return db[SESSIONS].update_many(
        query, {"$set": {"revoked_at": _now(), "revoked_reason": reason}}).modified_count


def revoke_everyone(db, reason: str, keep_sid: str | None = None) -> int:
    query = {"revoked_at": None}
    if keep_sid:
        query["_id"] = {"$ne": keep_sid}
    return db[SESSIONS].update_many(
        query, {"$set": {"revoked_at": _now(), "revoked_reason": reason}}).modified_count
