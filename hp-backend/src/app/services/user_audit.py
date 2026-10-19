"""Who changed which user, and when.

One row per change an admin (or a user, for their own password) makes to a
user or their access. Written after the change succeeds; a failed write is
logged and never undoes or blocks the change it describes.
"""

import logging
from datetime import UTC, datetime

from pymongo import DESCENDING
from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

USER_AUDIT = "user_audit"

USER_CREATED = "user.created"
USER_ACTIVATED = "user.activated"
USER_DEACTIVATED = "user.deactivated"
USER_RENAMED = "user.renamed"
ROLE_CHANGED = "user.role_changed"
ACCOUNTS_CHANGED = "user.accounts_changed"
PASSWORD_RESET = "user.password_reset"
PASSWORD_CHANGED = "user.password_changed"
PASSWORD_RECOVERED = "user.password_recovered"
SESSIONS_REVOKED_ALL = "sessions.revoked_all"


def ensure_indexes(db) -> None:
    try:
        db[USER_AUDIT].create_index([("ts", DESCENDING)], name="by_ts")
        db[USER_AUDIT].create_index([("target_id", 1), ("ts", DESCENDING)], name="by_target")
    except PyMongoError:
        logger.exception("user_audit: could not build indexes")


def record(db, actor: dict, action: str, target: dict | None = None,
           details: dict | None = None) -> None:
    """`actor` is the signed-in principal (id, email); `target` a user document
    or response (needs id/_id and email)."""
    try:
        db[USER_AUDIT].insert_one({
            "ts": datetime.now(UTC),
            "actor_id": actor.get("id"),
            "actor_email": actor.get("email"),
            "action": action,
            "target_id": str(target.get("_id") or target.get("id")) if target else None,
            "target_email": target.get("email") if target else None,
            "details": details or {},
        })
    except PyMongoError:
        logger.exception("user_audit: could not record %s", action)


def recent(db, target_id: str | None = None, limit: int = 200) -> list[dict]:
    query = {"target_id": target_id} if target_id else {}
    # _id breaks ties: two changes in the same millisecond keep their order.
    return list(db[USER_AUDIT].find(query)
                .sort([("ts", DESCENDING), ("_id", DESCENDING)]).limit(limit))
