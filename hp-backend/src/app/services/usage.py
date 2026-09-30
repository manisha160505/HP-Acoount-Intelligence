"""Usage events: which user opened which feature, and when they signed in.

One collection, `usage_events`:

    {user_id, event, feature_key, account_id, session_id, ts}

`user_id` and `ts` are always set here, from the authenticated user and the
server clock - never from the request. Admin activity is not recorded at all,
so it cannot leak into any count; analytics also filters on role, which covers
events written before a user became an admin.

Recording never raises into its caller. Analytics is a side channel: a failed
write must not fail a login or a page view.
"""

import logging
from datetime import UTC, datetime

from pymongo.errors import PyMongoError

logger = logging.getLogger(__name__)

USAGE_EVENTS = "usage_events"
EVENT_LOGIN = "login"
EVENT_FEATURE_VIEW = "feature_view"
EVENT_TYPES = (EVENT_LOGIN, EVENT_FEATURE_VIEW)

# One year. Enough for any "who used what this quarter" question; old events
# expire on their own instead of growing the collection forever.
RETENTION_SECONDS = 365 * 24 * 3600


def feature_keys() -> list[str]:
    """The authoritative feature list: the widget registry's features, in the
    order the registry declares them."""
    from app.api.v1.widgets import WIDGET_REGISTRY
    return list(WIDGET_REGISTRY)


def ensure_indexes(db) -> None:
    col = db[USAGE_EVENTS]
    try:
        col.create_index([("feature_key", 1), ("ts", 1)], name="feature_ts")
        col.create_index([("user_id", 1), ("ts", 1)], name="user_ts")
        col.create_index([("ts", 1)], name="ttl_ts", expireAfterSeconds=RETENTION_SECONDS)
    except PyMongoError:
        logger.exception("usage_events: index build failed - analytics queries "
                         "will be slower until it succeeds.")


def is_tracked(user: dict) -> bool:
    return user.get("role") != "admin"


def record_login(db, user: dict) -> None:
    if not is_tracked(user):
        return
    try:
        db[USAGE_EVENTS].insert_one({
            "user_id": str(user["_id"]),
            "event": EVENT_LOGIN,
            "feature_key": None,
            "account_id": None,
            "session_id": None,
            "ts": datetime.now(UTC),
        })
    except PyMongoError:
        logger.exception("usage_events: could not record a login")


def record_feature_views(db, user: dict, events) -> int:
    """Store a batch from the browser. Returns how many were stored.

    Admin batches are accepted and dropped (the call succeeds, nothing is
    written). Feature keys outside the registry are dropped rather than
    rejecting the whole batch: a stale browser tab naming a retired feature
    should not lose the valid events sent alongside it.
    """
    if not is_tracked(user):
        return 0
    known = set(feature_keys())
    now = datetime.now(UTC)
    docs = [{
        "user_id": user["id"],
        "event": e.event,
        "feature_key": e.feature_key,
        "account_id": e.account_id,
        "session_id": e.session_id,
        "ts": now,
    } for e in events if e.feature_key in known]
    if not docs:
        return 0
    try:
        db[USAGE_EVENTS].insert_many(docs, ordered=False)
    except PyMongoError:
        logger.exception("usage_events: could not record %d feature view(s)", len(docs))
        return 0
    return len(docs)
