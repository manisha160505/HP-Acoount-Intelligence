"""Heartbeats, time spent, and GET /me/activity (a seller's view of themselves).

Time and per-user numbers come from the same `$dateTrunc`/`$facet` aggregation
as the admin view, which the in-memory fake does not implement, so those run
on a real mongod only (set REGEN_TEST_MONGO_URI). Event intake and auth run on
both.

Run: REGEN_TEST_MONGO_URI=mongodb://localhost:27017 python -m pytest tests/test_my_activity.py -v
"""

from datetime import UTC, datetime

import pytest

from app.services.analytics import build_analytics, build_my_activity
from app.services.usage import HEARTBEAT_SECONDS, USAGE_EVENTS, feature_keys
from auth_harness import add_user, auth, body, install, mongo_db

# The `db` and `client` fixtures.
pytest_plugins = ["auth_harness"]

NOW = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


@pytest.fixture
def mdb(monkeypatch):
    client_, real, name = mongo_db()
    try:
        yield install(monkeypatch, real)
    finally:
        client_.drop_database(name)
        client_.close()


def _ev(db, user, event, ts, feature=None, account=None):
    db[USAGE_EVENTS].insert_one({"user_id": str(user["_id"]), "event": event,
                                 "feature_key": feature, "account_id": account,
                                 "session_id": "s", "ts": ts})


def _t(day, h, m=0, s=0):
    return datetime(2026, 9, day, h, m, s, tzinfo=UTC)


def _me(user):
    return {"id": str(user["_id"]), "role": user["role"]}


# ------------------------------------------------------------ event intake

def test_heartbeat_is_accepted_and_stamped_by_server(db, client):
    user = add_user(db, "seller@example.com")
    r = client.post("/api/v1/events", headers=auth(user), json={"events": [
        {"event": "feature_heartbeat", "feature_key": "strategy_chat", "account_id": "a1",
         "session_id": "s1", "seconds": 99999, "user_id": "someone-else"}]})
    assert r.status_code == 200 and body(r) == {"accepted": 1}
    (row,) = list(db[USAGE_EVENTS].find({}))
    assert row["event"] == "feature_heartbeat"
    assert row["user_id"] == str(user["_id"])
    assert "seconds" not in row          # the client cannot say how long


def test_admin_heartbeats_are_dropped(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    r = client.post("/api/v1/events", headers=auth(admin), json={"events": [
        {"event": "feature_heartbeat", "feature_key": "strategy_chat"}]})
    assert body(r) == {"accepted": 0}


def test_my_activity_requires_sign_in(db, client):
    assert client.get("/api/v1/me/activity").status_code in (401, 403)


# ------------------------------------------------------------- time spent

def test_time_counts_distinct_windows_not_raw_events(mdb):
    db = mdb
    u = add_user(db, "seller@example.com")
    # Three heartbeats inside one 30s window (two tabs, a replayed batch...)
    # are worth one window.
    for s in (1, 5, 20):
        _ev(db, u, "feature_heartbeat", _t(20, 10, 0, s), "strategy_chat")
    # Three more, each in its own window.
    for m in (1, 2, 3):
        _ev(db, u, "feature_heartbeat", _t(20, 10, m, 0), "strategy_chat")
    _ev(db, u, "feature_heartbeat", _t(20, 11), "tech_landscape")
    res = build_my_activity(db, _me(u), "2026-09-20", "2026-09-20", now=NOW)
    by = {f.feature_key: f for f in res.per_feature}
    assert by["strategy_chat"].time_seconds == 4 * HEARTBEAT_SECONDS
    assert by["tech_landscape"].time_seconds == HEARTBEAT_SECONDS
    assert res.totals.time_seconds == 5 * HEARTBEAT_SECONDS
    assert res.daily[0].time_seconds == 5 * HEARTBEAT_SECONDS


def test_admin_view_reports_time_per_feature_and_user(mdb):
    db = mdb
    u = add_user(db, "seller@example.com")
    for m in range(4):
        _ev(db, u, "feature_heartbeat", _t(20, 10, m), "stakeholder_map")
    res = build_analytics(db, "2026-09-20", "2026-09-20", now=NOW)
    assert res.totals.time_seconds == 4 * HEARTBEAT_SECONDS
    (row,) = res.per_user
    assert row.time_seconds == 4 * HEARTBEAT_SECONDS
    assert row.feature_seconds["stakeholder_map"] == 4 * HEARTBEAT_SECONDS
    assert list(row.feature_seconds) == feature_keys()
    # Time alone (no view in range) still counts the feature as used.
    assert row.features_used == 1 and row.top_feature == "stakeholder_map"


def test_top_feature_prefers_time_over_views(mdb):
    db = mdb
    u = add_user(db, "seller@example.com")
    for _ in range(5):
        _ev(db, u, "feature_view", _t(20, 9), "executive_dashboard")
    _ev(db, u, "feature_view", _t(20, 9), "strategy_chat")
    for m in range(10):
        _ev(db, u, "feature_heartbeat", _t(20, 10, m), "strategy_chat")
    res = build_my_activity(db, _me(u), "2026-09-20", "2026-09-20", now=NOW)
    assert res.totals.top_feature == "strategy_chat"


# ------------------------------------------------------------ my activity

@pytest.fixture
def two_sellers(mdb):
    db = mdb
    me = add_user(db, "me@example.com", last_login_at=_t(20, 8))
    other = add_user(db, "other@example.com")
    acct = str(db["accounts"].insert_one({"name": "Acme"}).inserted_id)
    _ev(db, me, "login", _t(20, 8))
    _ev(db, me, "feature_view", _t(19, 9), "executive_dashboard", acct)
    _ev(db, me, "feature_view", _t(20, 9), "strategy_chat", acct)
    _ev(db, me, "feature_heartbeat", _t(20, 9, 1), "strategy_chat", acct)
    # Someone else's activity, which must never show up in mine.
    for _ in range(7):
        _ev(db, other, "feature_view", _t(20, 9), "tech_landscape", "other-acct")
    _ev(db, other, "login", _t(20, 8))
    for m in range(9):
        _ev(db, other, "feature_heartbeat", _t(20, 10, m), "tech_landscape")
    return db, me, other, acct


def test_my_activity_shows_only_my_data(two_sellers):
    db, me, _, acct = two_sellers
    res = build_my_activity(db, _me(me), "2026-09-15", "2026-09-21", now=NOW)
    t = res.totals
    assert (t.logins, t.feature_views, t.features_used) == (1, 2, 2)
    assert t.time_seconds == HEARTBEAT_SECONDS
    assert t.top_feature == "strategy_chat"
    assert t.last_login_at == _t(20, 8)
    by = {f.feature_key: f for f in res.per_feature}
    assert by["tech_landscape"].total_views == 0 and by["tech_landscape"].time_seconds == 0
    assert [f.feature_key for f in res.per_feature] == feature_keys()   # zeros included
    assert [a.account_id for a in res.top_accounts] == [acct]
    assert res.top_accounts[0].account_name == "Acme"


def test_recent_is_newest_first_with_account_names(two_sellers):
    db, me, _, _ = two_sellers
    res = build_my_activity(db, _me(me), "2026-09-15", "2026-09-21", now=NOW)
    assert [(r.feature_key, r.account_name) for r in res.recent] == [
        ("strategy_chat", "Acme"), ("executive_dashboard", "Acme")]


def test_recent_logins_are_mine_newest_first_and_in_range(two_sellers):
    db, me, _, _ = two_sellers
    _ev(db, me, "login", _t(21, 7))
    _ev(db, me, "login", _t(10, 7))          # before the range
    res = build_my_activity(db, _me(me), "2026-09-15", "2026-09-21", now=NOW)
    # The other seller's login on the 20th is not in my list.
    assert res.recent_logins == [_t(21, 7), _t(20, 8)]
    assert res.totals.logins == len(res.recent_logins)


def test_daily_series_covers_every_day(two_sellers):
    db, me, _, _ = two_sellers
    res = build_my_activity(db, _me(me), "2026-09-15", "2026-09-21", now=NOW)
    daily = {d.date: d for d in res.daily}
    assert list(daily) == ["2026-09-%02d" % d for d in range(15, 22)]
    assert daily["2026-09-19"].views == 1 and daily["2026-09-20"].views == 1
    assert daily["2026-09-20"].time_seconds == HEARTBEAT_SECONDS
    assert daily["2026-09-16"].views == 0


def test_endpoint_uses_token_identity_only(two_sellers, client):
    _, me, other, _ = two_sellers
    # A user_id in the query string is not a parameter and changes nothing.
    r = client.get("/api/v1/me/activity?from=2026-09-15&to=2026-09-21&user_id=%s"
                   % other["_id"], headers=auth(me))
    assert r.status_code == 200, r.text
    data = body(r)
    assert data["totals"]["feature_views"] == 2
    assert data["heartbeat_seconds"] == HEARTBEAT_SECONDS
    assert client.get("/api/v1/me/activity?from=bad", headers=auth(me)).status_code == 400


def test_admin_gets_an_empty_result_not_an_error(two_sellers, client):
    db, *_ = two_sellers
    admin = add_user(db, "admin@example.com", role="admin")
    r = client.get("/api/v1/me/activity", headers=auth(admin))
    assert r.status_code == 200
    assert body(r)["totals"]["feature_views"] == 0
