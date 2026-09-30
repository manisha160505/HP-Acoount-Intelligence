"""GET /admin/analytics against a controlled set of events.

The aggregation uses `$facet`, `$addToSet` and `$dateToString`, which the
in-memory fake does not implement, so the numbers are checked on a real mongod
only (set REGEN_TEST_MONGO_URI). Date parsing and authorisation run everywhere.

Run: REGEN_TEST_MONGO_URI=mongodb://localhost:27017 python -m pytest tests/test_usage_analytics.py -v
"""

from datetime import UTC, date, datetime

import pytest

from app.errors import APIError
from app.services.analytics import build_analytics, resolve_window
from app.services.usage import USAGE_EVENTS, feature_keys
from auth_harness import add_user, auth, body, install, mongo_db

# The `client` fixture.
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


def _day(d, h=10):
    return datetime(2026, 9, d, h, 0, tzinfo=UTC)


@pytest.fixture
def seeded(mdb):
    """alice: exec x3 (19th, 20th), chat x1 (20th), 2 logins.
    bob:   exec x1 (20th), 1 login, one view outside the window (1st).
    carol: nothing at all.
    admin: loads of activity that must count for nothing."""
    db = mdb
    alice = add_user(db, "alice@example.com", created_at=_day(1),
                     last_login_at=_day(20))
    bob = add_user(db, "bob@example.com", created_at=_day(2), is_active=False)
    add_user(db, "carol@example.com", created_at=_day(3))
    admin = add_user(db, "admin@example.com", role="admin", created_at=_day(1))
    acct = db["accounts"].insert_one({"name": "Acme"}).inserted_id

    _ev(db, alice, "login", _day(19, 9))
    _ev(db, alice, "feature_view", _day(19), "executive_dashboard", str(acct))
    _ev(db, alice, "feature_view", _day(20), "executive_dashboard", str(acct))
    _ev(db, alice, "feature_view", _day(20, 11), "executive_dashboard", str(acct))
    _ev(db, alice, "login", _day(20, 9))
    _ev(db, alice, "feature_view", _day(20, 23), "strategy_chat", "other-acct")
    _ev(db, bob, "login", _day(20, 8))
    _ev(db, bob, "feature_view", _day(20, 15), "executive_dashboard", str(acct))
    _ev(db, bob, "feature_view", _day(1), "tech_landscape")
    for _ in range(5):
        _ev(db, admin, "feature_view", _day(20), "objection_playbook", str(acct))
        _ev(db, admin, "login", _day(20))
    return db, {"alice": alice, "bob": bob, "acct": str(acct)}


def _run(db, f="2026-09-15", t="2026-09-21"):
    return build_analytics(db, f, t, now=NOW)


def test_every_feature_present_including_zero_usage(seeded):
    db, _ = seeded
    res = _run(db)
    assert [f.feature_key for f in res.per_feature] == feature_keys()
    assert len(res.per_feature) == 10
    by = {f.feature_key: f for f in res.per_feature}
    assert by["objection_playbook"].total_views == 0      # admin-only views
    assert by["tech_landscape"].total_views == 0          # outside the window
    assert by["content_studio"].unique_users == 0 and by["content_studio"].last_used_at is None


def test_unique_users_total_views_last_used(seeded):
    db, _ = seeded
    by = {f.feature_key: f for f in _run(db).per_feature}
    assert by["executive_dashboard"].unique_users == 2
    assert by["executive_dashboard"].total_views == 4
    assert by["executive_dashboard"].last_used_at == _day(20, 15)
    assert by["strategy_chat"].unique_users == 1 and by["strategy_chat"].total_views == 1


def test_per_user(seeded):
    db, _ = seeded
    per = {p.email: p for p in _run(db).per_user}
    assert set(per) == {"alice@example.com", "bob@example.com", "carol@example.com"}
    alice, bob, carol = per["alice@example.com"], per["bob@example.com"], per["carol@example.com"]
    assert alice.features_used == 2 and alice.top_feature == "executive_dashboard"
    assert alice.logins == 2 and alice.last_login_at == _day(20)
    assert alice.feature_views["executive_dashboard"] == 3
    assert alice.feature_views["strategy_chat"] == 1
    assert bob.features_used == 1 and bob.logins == 1 and bob.is_active is False
    assert carol.features_used == 0 and carol.top_feature is None and carol.logins == 0
    # Every cell present, zero included.
    for p in per.values():
        assert list(p.feature_views) == feature_keys()


def test_daily_active_users_cover_every_day(seeded):
    db, _ = seeded
    dau = {d.date: d.active_users for d in _run(db).daily_active_users}
    assert list(dau) == ["2026-09-%02d" % d for d in range(15, 22)]
    assert dau["2026-09-19"] == 1
    assert dau["2026-09-20"] == 2          # alice + bob; admin excluded
    assert dau["2026-09-15"] == 0


def test_day_boundary_is_utc(mdb):
    db = mdb
    u = add_user(db, "late@example.com")
    _ev(db, u, "feature_view", datetime(2026, 9, 20, 23, 59, 59, tzinfo=UTC), "strategy_chat")
    _ev(db, u, "feature_view", datetime(2026, 9, 21, 0, 0, 0, tzinfo=UTC), "strategy_chat")
    res = build_analytics(db, "2026-09-20", "2026-09-20", now=NOW)
    assert res.per_feature[feature_keys().index("strategy_chat")].total_views == 1
    assert [d.active_users for d in res.daily_active_users] == [1]


def test_date_filtering(seeded):
    db, _ = seeded
    only_19 = build_analytics(db, "2026-09-19", "2026-09-19", now=NOW)
    by = {f.feature_key: f for f in only_19.per_feature}
    assert by["executive_dashboard"].total_views == 1
    assert by["strategy_chat"].total_views == 0
    assert only_19.totals.logins == 1
    wide = build_analytics(db, "2026-09-01", "2026-09-30", now=NOW)
    assert {f.feature_key: f for f in wide.per_feature}["tech_landscape"].total_views == 1


def test_totals_and_admin_exclusion(seeded):
    db, _ = seeded
    res = _run(db)
    assert res.totals.total_users == 3             # admin not counted
    assert res.totals.logins == 3                  # 2 alice + 1 bob; 5 admin ignored
    assert res.totals.feature_views == 5
    # 7 days back from NOW (30 Sep): nothing after the 20th, so nobody.
    assert res.totals.active_users_7d == 0
    later = build_analytics(db, "2026-09-15", "2026-09-21",
                            now=datetime(2026, 9, 22, tzinfo=UTC))
    assert later.totals.active_users_7d == 2


def test_top_accounts(seeded):
    db, u = seeded
    top = _run(db).top_accounts
    assert top[0].account_id == u["acct"] and top[0].account_name == "Acme"
    assert top[0].views == 4 and top[0].unique_users == 2   # admin's 5 excluded
    assert top[1].account_id == "other-acct" and top[1].account_name is None


def test_events_from_user_later_made_admin_excluded(seeded):
    db, u = seeded
    db["users"].update_one({"_id": u["alice"]["_id"]}, {"$set": {"role": "admin"}})
    by = {f.feature_key: f for f in _run(db).per_feature}
    assert by["executive_dashboard"].unique_users == 1
    assert by["strategy_chat"].total_views == 0


def test_endpoint_admin_only_and_serialises(seeded, client):
    db, u = seeded
    admin = db["users"].find_one({"role": "admin"})
    r = client.get("/api/v1/admin/analytics?from=2026-09-15&to=2026-09-21",
                   headers=auth(admin))
    assert r.status_code == 200, r.text
    data = body(r)
    assert data["date_from"] == "2026-09-15" and data["date_to"] == "2026-09-21"
    assert len(data["per_feature"]) == 10
    assert client.get("/api/v1/admin/analytics", headers=auth(u["alice"])).status_code == 403
    assert client.get("/api/v1/admin/analytics?from=bad",
                      headers=auth(admin)).status_code == 400


# ------------------------------------------------------ window parsing (pure)

def test_window_defaults_to_last_30_days():
    assert resolve_window(None, None, today=date(2026, 9, 30)) == (date(2026, 9, 1),
                                                                  date(2026, 9, 30))
    assert resolve_window("", "2026-09-10", today=date(2026, 9, 30)) == (
        date(2026, 8, 12), date(2026, 9, 10))


@pytest.mark.parametrize("f,t", [("2026-13-01", None), ("yesterday", None),
                                 ("2026-09-10", "2026-09-01"), ("2024-01-01", "2026-01-01")])
def test_window_rejects_bad_input(f, t):
    with pytest.raises(APIError) as exc:
        resolve_window(f, t, today=date(2026, 9, 30))
    assert exc.value.status_code == 400
