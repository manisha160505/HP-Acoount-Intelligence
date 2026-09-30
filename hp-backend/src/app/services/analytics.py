"""Admin analytics over `usage_events`.

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
    UserUsage,
)
from app.services.usage import EVENT_FEATURE_VIEW, EVENT_LOGIN, USAGE_EVENTS, feature_keys
from app.services.users_admin import is_user_active

DEFAULT_WINDOW_DAYS = 30
MAX_WINDOW_DAYS = 366
TOP_ACCOUNTS = 10


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
            "logins_by_user": [
                {"$match": {"event": EVENT_LOGIN}},
                {"$group": {"_id": "$user_id", "n": {"$sum": 1}}},
            ],
            "daily": [
                {"$group": {"_id": {
                    "day": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts",
                                              "timezone": "UTC"}},
                    "u": "$user_id"}}},
                {"$group": {"_id": "$_id.day", "users": {"$sum": 1}}},
            ],
            "accounts": [
                views,
                {"$match": {"account_id": {"$nin": [None, ""]}}},
                {"$group": {"_id": "$account_id", "views": {"$sum": 1},
                            "users": {"$addToSet": "$user_id"}}},
                {"$project": {"views": 1, "unique_users": {"$size": "$users"}}},
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


def build_analytics(db, date_from: str | None = None, date_to: str | None = None,
                    now: datetime | None = None) -> AnalyticsResponse:
    now = now or datetime.now(UTC)
    start_day, end_day = resolve_window(date_from, date_to, today=now.date())
    start, end = _midnight(start_day), _midnight(end_day + timedelta(days=1))
    features = feature_keys()

    users = list(db["users"].find({"role": {"$ne": "admin"}}).sort("created_at", 1))
    user_ids = [str(u["_id"]) for u in users]

    facet = next(iter(db[USAGE_EVENTS].aggregate(
        _facet_pipeline(user_ids, start, end))), {}) if user_ids else {}

    # -- per feature: every registry feature, zero or not -------------------
    by_feature = {r["_id"]: r for r in facet.get("by_feature", [])}
    per_feature = [FeatureUsage(
        feature_key=f,
        unique_users=by_feature.get(f, {}).get("unique_users", 0),
        total_views=by_feature.get(f, {}).get("views", 0),
        last_used_at=_aware(by_feature.get(f, {}).get("last")),
    ) for f in features]

    # -- per user ---------------------------------------------------------
    known = set(features)
    views_by_user: dict[str, dict[str, int]] = {}
    for r in facet.get("by_user_feature", []):
        if r["_id"]["f"] in known:
            views_by_user.setdefault(r["_id"]["u"], {})[r["_id"]["f"]] = r["views"]
    logins = {r["_id"]: r["n"] for r in facet.get("logins_by_user", [])}
    order = {f: i for i, f in enumerate(features)}

    per_user = []
    for u in users:
        uid = str(u["_id"])
        counts = views_by_user.get(uid, {})
        # Most views wins; a tie goes to the feature listed first in the
        # registry, so the answer is stable between refreshes.
        top = min(counts, key=lambda f: (-counts[f], order.get(f, len(order)))) if counts else None
        per_user.append(UserUsage(
            user_id=uid,
            email=u.get("email", ""),
            full_name=u.get("full_name") or "",
            is_active=is_user_active(u),
            last_login_at=_aware(u.get("last_login_at")),
            logins=logins.get(uid, 0),
            features_used=sum(1 for f in features if counts.get(f)),
            top_feature=top,
            feature_views={f: counts.get(f, 0) for f in features},
        ))

    # -- daily active users, every day in the window -------------------------
    daily = {r["_id"]: r["users"] for r in facet.get("daily", [])}
    dau = []
    day = start_day
    while day <= end_day:
        key = day.isoformat()
        dau.append(DailyActiveUsers(date=key, active_users=daily.get(key, 0)))
        day += timedelta(days=1)

    # -- top accounts ------------------------------------------------------
    acct_rows = facet.get("accounts", [])
    names = _account_names(db, [r["_id"] for r in acct_rows])
    top_accounts = [AccountViews(account_id=r["_id"], account_name=names.get(r["_id"]),
                                 views=r["views"], unique_users=r["unique_users"])
                    for r in acct_rows]

    # -- totals: 7-day actives are relative to now, not to the window --------
    active_7d = len(db[USAGE_EVENTS].distinct("user_id", {
        "ts": {"$gte": now - timedelta(days=7), "$lte": now},
        "user_id": {"$in": user_ids}})) if user_ids else 0

    return AnalyticsResponse(
        date_from=start_day.isoformat(),
        date_to=end_day.isoformat(),
        features=features,
        totals=AnalyticsTotals(
            total_users=len(users),
            active_users_7d=active_7d,
            logins=sum(logins.values()),
            feature_views=sum(r.total_views for r in per_feature),
        ),
        per_feature=per_feature,
        per_user=per_user,
        daily_active_users=dau,
        top_accounts=top_accounts,
    )
