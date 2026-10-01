"""Usage analytics over `usage_events`: the admin view across all sellers, and
each seller's own view of themselves (`build_my_activity`). Both run the same
aggregation, so a seller sees exactly the numbers an admin sees for them.

Dates
-----
`from` and `to` are calendar dates (YYYY-MM-DD), both INCLUSIVE, in UTC - the
timezone every timestamp in this database is written in. The query window is
[from 00:00 UTC, to + 1 day 00:00 UTC). Days are bucketed in UTC too, so a
daily count and the window agree on where a day starts.

Omitted: `to` defaults to today (UTC) and `from` to 29 days before `to`, i.e.
the last 30 days. A malformed date, `from` after `to`, or a window over 366
days is an INVALID_PARAMETER error rather than a silent default.

Who counts
----------
Only users whose role is not `admin`. Admin events are not written in the first
place (see services/usage.py); filtering by the current non-admin user ids here
as well covers anything written before someone was made an admin.

Time spent
----------
From `feature_heartbeat` events, sent every HEARTBEAT_SECONDS while a feature
is open in a visible tab and the seller is active. Time is the number of
distinct (user, feature, HEARTBEAT_SECONDS window) buckets times
HEARTBEAT_SECONDS - so a duplicated or replayed heartbeat cannot add time.
Periods before heartbeats shipped have views but no time.

"Top feature" is the one with the most time; with no time recorded, the one
with the most views; ties go to the feature listed first in the registry.

Everything is computed in one `$facet` aggregation on the server; the event
collection is never loaded into the application.
"""

from datetime import UTC, date, datetime, timedelta

from bson import ObjectId
from bson.errors import InvalidId

from app.errors import APIError, ErrorCode
from app.schemas.usage import (
    AccountViews,
    AnalyticsResponse,
    AnalyticsTotals,
    DailyActiveUsers,
    FeatureUsage,
    MyActivityResponse,
    MyActivityTotals,
    RecentActivity,
    UserUsage,
)
from app.services.usage import (
    EVENT_FEATURE_HEARTBEAT,
    EVENT_FEATURE_VIEW,
    EVENT_LOGIN,
    HEARTBEAT_SECONDS,
    USAGE_EVENTS,
    feature_keys,
)
from app.services.users_admin import is_user_active

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 366
TOP_ACCOUNTS = 10
RECENT_LIMIT = 15


def _parse_day(value: str | None, name: str) -> date | None:
    if value is None or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise APIError(ErrorCode.INVALID_PARAMETER, "`%s` must be a date as YYYY-MM-DD." % name,
                       fields={name: "Use YYYY-MM-DD."}) from exc


def resolve_window(date_from: str | None, date_to: str | None,
                   today: date | None = None) -> tuple[date, date]:
    today = today or datetime.now(UTC).date()
    end = _parse_day(date_to, "to") or today
    start = _parse_day(date_from, "from") or end - timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    if start > end:
        raise APIError(ErrorCode.INVALID_PARAMETER, "`from` must be on or before `to`.",
                       fields={"from": "Must be on or before `to`."})
    if (end - start).days + 1 > MAX_WINDOW_DAYS:
        raise APIError(ErrorCode.INVALID_PARAMETER,
                       "The date range can be at most %d days." % MAX_WINDOW_DAYS)
    return start, end


def _midnight(d: date) -> datetime:
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def _facet_pipeline(user_ids: list[str], start: datetime, end: datetime) -> list[dict]:
    views = {"$match": {"event": EVENT_FEATURE_VIEW}}
    day = {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts", "timezone": "UTC"}}
    # One row per (user, feature, heartbeat window) that saw any heartbeat.
    beats = [
        {"$match": {"event": EVENT_FEATURE_HEARTBEAT}},
        {"$group": {"_id": {"u": "$user_id", "f": "$feature_key",
                            "b": {"$dateTrunc": {"date": "$ts", "unit": "second",
                                                 "binSize": HEARTBEAT_SECONDS}}}}},
    ]
    return [
        {"$match": {"ts": {"$gte": start, "$lt": end}, "user_id": {"$in": user_ids}}},
        {"$facet": {
            "by_feature": [
                views,
                {"$group": {"_id": "$feature_key", "views": {"$sum": 1},
                            "users": {"$addToSet": "$user_id"}, "last": {"$max": "$ts"}}},
                {"$project": {"views": 1, "last": 1, "unique_users": {"$size": "$users"}}},
            ],
            "by_user_feature": [
                views,
                {"$group": {"_id": {"u": "$user_id", "f": "$feature_key"},
                            "views": {"$sum": 1}}},
            ],
            "time_by_user_feature": [
                *beats,
                {"$group": {"_id": {"u": "$_id.u", "f": "$_id.f"}, "beats": {"$sum": 1}}},
            ],
            "logins_by_user": [
                {"$match": {"event": EVENT_LOGIN}},
                {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            ],
            "daily": [
                {"$group": {"_id": {"day": day, "u": "$user_id"},
                            "views": {"$sum": {"$cond": [
                                {"$eq": ["$event", EVENT_FEATURE_VIEW]}, 1, 0]}}}},
                {"$group": {"_id": "$_id.day", "users": {"$sum": 1},
                            "user_ids": {"$push": "$_id.u"},
                            "views": {"$sum": "$views"}}},
            ],
            "daily_time": [
                *beats,
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$_id.b",
                                                      "timezone": "UTC"}},
                            "beats": {"$sum": 1}}},
            ],
            "accounts": [
                views,
                {"$match": {"account_id": {"$nin": [None, ""]}}},
                {"$group": {"_id": "$account_id", "views": {"$sum": 1},
                            "users": {"$addToSet": "$user_id"}}},
                {"$project": {"views": 1, "users": 1, "unique_users": {"$size": "$users"}}},
                {"$sort": {"views": -1, "_id": 1}},
                {"$limit": TOP_ACCOUNTS},
            ],
        }},
    ]


def _aware(ts: datetime | None) -> datetime | None:
    # pymongo hands back naive datetimes unless the client is tz_aware; every
    # timestamp here was written as UTC.
    if ts is not None and ts.tzinfo is None:
        return ts.replace(tzinfo=UTC)
    return ts


def _account_names(db, account_ids: list[str]) -> dict[str, str]:
    oids = []
    for aid in account_ids:
        try:
            oids.append(ObjectId(aid))
        except (InvalidId, TypeError):
            continue
    if not oids:
        return {}
    return {str(a["_id"]): a.get("name") for a in db["accounts"].find({"_id": {"$in": oids}})}


def _window(date_from, date_to, now):
    start_day, end_day = resolve_window(date_from, date_to, today=now.date())
    return start_day, end_day, _midnight(start_day), _midnight(end_day + timedelta(days=1))


def _top_feature(seconds: dict[str, int], views: dict[str, int],
                 order: dict[str, int]) -> str | None:
    used = set(seconds) | set(views)
    if not used:
        return None
    return min(used, key=lambda f: (-seconds.get(f, 0), -views.get(f, 0),
                                    order.get(f, len(order))))


class _Usage:
    """The aggregation's result for a set of users, shaped for both views."""

    def __init__(self, db, user_ids: list[str], start_day: date, end_day: date,
                 start: datetime, end: datetime):
        self.features = feature_keys()
        self.order = {f: i for i, f in enumerate(self.features)}
        known = set(self.features)
        facet = next(iter(db[USAGE_EVENTS].aggregate(
            _facet_pipeline(user_ids, start, end))), {}) if user_ids else {}

        by_feature = {r["_id"]: r for r in facet.get("by_feature", [])}
        self.views: dict[str, dict[str, int]] = {}
        for r in facet.get("by_user_feature", []):
            if r["_id"]["f"] in known:
                self.views.setdefault(r["_id"]["u"], {})[r["_id"]["f"]] = r["views"]
        self.seconds: dict[str, dict[str, int]] = {}
        for r in facet.get("time_by_user_feature", []):
            if r["_id"]["f"] in known:
                self.seconds.setdefault(r["_id"]["u"], {})[r["_id"]["f"]] = \
                    r["beats"] * HEARTBEAT_SECONDS
        self.logins = {r["_id"]: r["n"] for r in facet.get("logins_by_user", [])}

        feature_time = {f: sum(s.get(f, 0) for s in self.seconds.values())
                        for f in self.features}
        self.per_feature = [FeatureUsage(
            feature_key=f,
            unique_users=by_feature.get(f, {}).get("unique_users", 0),
            total_views=by_feature.get(f, {}).get("views", 0),
            time_seconds=feature_time[f],
            last_used_at=_aware(by_feature.get(f, {}).get("last")),
        ) for f in self.features]

        daily = {r["_id"]: r for r in facet.get("daily", [])}
        daily_time = {r["_id"]: r["beats"] * HEARTBEAT_SECONDS
                      for r in facet.get("daily_time", [])}
        self.daily = []
        day = start_day
        while day <= end_day:
            key = day.isoformat()
            self.daily.append(DailyActiveUsers(
                date=key, active_users=daily.get(key, {}).get("users", 0),
                views=daily.get(key, {}).get("views", 0),
                time_seconds=daily_time.get(key, 0),
                user_ids=sorted(daily.get(key, {}).get("user_ids", []))))
            day += timedelta(days=1)

        acct_rows = facet.get("accounts", [])
        names = _account_names(db, [r["_id"] for r in acct_rows])
        self.top_accounts = [AccountViews(account_id=r["_id"], account_name=names.get(r["_id"]),
                                          views=r["views"], unique_users=r["unique_users"],
                                          user_ids=sorted(r.get("users", [])))
                             for r in acct_rows]

    def for_user(self, uid: str) -> tuple[dict[str, int], dict[str, int]]:
        return self.views.get(uid, {}), self.seconds.get(uid, {})


def build_analytics(db, date_from: str | None = None, date_to: str | None = None,
                    now: datetime | None = None) -> AnalyticsResponse:
    now = now or datetime.now(UTC)
    start_day, end_day, start, end = _window(date_from, date_to, now)

    users = list(db["users"].find({"role": {"$ne": "admin"}}).sort("created_at", 1))
    user_ids = [str(u["_id"]) for u in users]
    usage = _Usage(db, user_ids, start_day, end_day, start, end)
    features = usage.features

    per_user = []
    for u in users:
        uid = str(u["_id"])
        views, seconds = usage.for_user(uid)
        per_user.append(UserUsage(
            user_id=uid,
            email=u.get("email", ""),
            full_name=u.get("full_name") or "",
            is_active=is_user_active(u),
            last_login_at=_aware(u.get("last_login_at")),
            logins=usage.logins.get(uid, 0),
            features_used=sum(1 for f in features if views.get(f) or seconds.get(f)),
            time_seconds=sum(seconds.values()),
            top_feature=_top_feature(seconds, views, usage.order),
            feature_views={f: views.get(f, 0) for f in features},
            feature_seconds={f: seconds.get(f, 0) for f in features},
        ))

    # 7-day actives are relative to now, not to the window.
    active_7d = sorted(db[USAGE_EVENTS].distinct("user_id", {
        "ts": {"$gte": now - timedelta(days=7), "$lte": now},
        "user_id": {"$in": user_ids}})) if user_ids else []

    return AnalyticsResponse(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        features=features,
        totals=AnalyticsTotals(
            total_users=len(users),
            active_users_7d=len(active_7d),
            active_user_ids_7d=active_7d,
            logins=sum(usage.logins.values()),
            feature_views=sum(r.total_views for r in usage.per_feature),
            time_seconds=sum(r.time_seconds for r in usage.per_feature),
        ),
        per_feature=usage.per_feature,
        per_user=per_user,
        daily_active_users=usage.daily,
        top_accounts=usage.top_accounts,
    )


def build_my_activity(db, user: dict, date_from: str | None = None,
                      date_to: str | None = None,
                      now: datetime | None = None) -> MyActivityResponse:
    """The signed-in user's own usage. `user` is the authenticated user from
    the token - never an id from the request - so nobody can read anyone
    else's activity through this. An admin gets an empty result, because
    admin activity is not recorded."""
    now = now or datetime.now(UTC)
    start_day, end_day, start, end = _window(date_from, date_to, now)
    uid = user["id"]
    usage = _Usage(db, [uid], start_day, end_day, start, end)
    views, seconds = usage.for_user(uid)

    rows = list(db[USAGE_EVENTS].find({
        "user_id": uid, "event": EVENT_FEATURE_VIEW,
        "ts": {"$gte": start, "$lt": end}}).sort("ts", -1).limit(RECENT_LIMIT))
    names = _account_names(db, list({r["account_id"] for r in rows if r.get("account_id")}))
    recent = [RecentActivity(ts=_aware(r["ts"]), feature_key=r["feature_key"],
                             account_id=r.get("account_id"),
                             account_name=names.get(r.get("account_id") or ""))
              for r in rows if r.get("feature_key") in usage.order]

    doc = db["users"].find_one({"_id": ObjectId(uid)}) or {}
    return MyActivityResponse(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        heartbeat_seconds=HEARTBEAT_SECONDS,
        features=usage.features,
        totals=MyActivityTotals(
            logins=usage.logins.get(uid, 0),
            feature_views=sum(views.values()),
            time_seconds=sum(seconds.values()),
            features_used=sum(1 for f in usage.features if views.get(f) or seconds.get(f)),
            top_feature=_top_feature(seconds, views, usage.order),
            last_login_at=_aware(doc.get("last_login_at")),
        ),
        per_feature=usage.per_feature,
        daily=usage.daily,
        top_accounts=usage.top_accounts,
        recent=recent,
    )
