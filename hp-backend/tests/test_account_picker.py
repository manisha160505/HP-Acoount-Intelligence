"""GET /accounts/user-list carries each account's urgency score.

The account picker filters on it, so it has to be the number the Executive
Dashboard shows: read from the committed `exec_urgency_score` widget through
the widget store, never recomputed.

Run: python -m pytest tests/test_account_picker.py -v
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_error_handlers
from app.services.regen import store as widget_store
from app.services.regen.graph import DEFAULT
from app.services.regen.state import COLLECTION as STATE_COLLECTION, state_id
from auth_harness import add_user, auth, body

# The `db` fixture.
pytest_plugins = ["auth_harness"]

KEY = "exec_urgency_score"
NOW = datetime(2026, 10, 1, tzinfo=UTC)


@pytest.fixture
def client():
    from app.api.v1.accounts import router
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def _account(db, name, status="active"):
    return str(db["accounts"].insert_one(
        {"name": name, "status": status, "created_at": NOW, "updated_at": NOW}).inserted_id)


def _legacy(db, acct, score, status="available"):
    """An account the regeneration engine has not adopted: `account_widgets`."""
    db["account_widgets"].insert_one({
        "account_id": acct, "widget_key": KEY, "status": status,
        "data": {"score": score, "max_score": 100}, "updated_at": NOW})


def _committed(db, acct, score, status="available"):
    """An account with node state: the committed generation wins."""
    db[STATE_COLLECTION].insert_one({
        "_id": state_id(acct, DEFAULT.owner[KEY]),
        "current": {"generation_id": "g1", "generated_at": NOW, "widgets": {
            KEY: {"status": status, "data": {"score": score, "max_score": 100}}}}})


def _scores(client, user):
    r = client.get("/api/v1/accounts/user-list", headers=auth(user))
    assert r.status_code == 200
    return {a["name"]: a["urgency_score"] for a in body(r)}


def test_user_list_returns_every_active_account_sorted_with_its_score(db, client):
    user = add_user(db, "seller@example.com")
    a = _account(db, "Jabil")
    b = _account(db, "Astra")
    _account(db, "Hidden Co", status="hidden")
    _legacy(db, a, 72)
    _committed(db, b, 85)

    r = client.get("/api/v1/accounts/user-list", headers=auth(user))
    rows = body(r)
    assert [x["name"] for x in rows] == ["Astra", "Jabil"]
    assert rows[0]["urgency_score"] == 85 and rows[0]["urgency_max_score"] == 100
    assert rows[1]["urgency_score"] == 72
    # The fields the dropdown already used are unchanged.
    assert {"id", "name", "status", "created_at", "updated_at"} <= set(rows[0])


def test_node_state_wins_over_a_stale_legacy_row(db, client):
    user = add_user(db, "seller@example.com")
    a = _account(db, "Jabil")
    _legacy(db, a, 10)
    _committed(db, a, 64)
    assert _scores(client, user) == {"Jabil": 64}


def test_missing_withheld_and_unavailable_scores_are_null(db, client):
    user = add_user(db, "seller@example.com")
    never = _account(db, "Never Generated")
    withheld = _account(db, "Withheld")
    empty = _account(db, "Empty")
    no_widget = _account(db, "Node Without Widget")
    _legacy(db, withheld, None, status="partial")
    _legacy(db, empty, 50, status="empty")
    db[STATE_COLLECTION].insert_one({
        "_id": state_id(no_widget, DEFAULT.owner[KEY]), "current": {"widgets": {}}})

    assert _scores(client, user) == {
        "Empty": None, "Never Generated": None,
        "Node Without Widget": None, "Withheld": None}
    assert never  # created, and listed above with no score


def test_committed_many_matches_committed_per_account(db):
    """The batched read must resolve every account exactly as the dashboard's
    per-account read does."""
    accts = [_account(db, n) for n in ("A", "B", "C", "D")]
    _legacy(db, accts[0], 30)
    _committed(db, accts[1], 40)
    _legacy(db, accts[2], 99)
    _committed(db, accts[2], 55)
    many = widget_store.committed_many(db, accts, KEY)
    for acct in accts:
        one = widget_store.committed(db, acct, KEY)
        assert (many[acct] or {}).get("data") == (one or {}).get("data")
        assert (many[acct] or {}).get("status") == (one or {}).get("status")


def test_user_list_requires_sign_in(db, client):
    assert client.get("/api/v1/accounts/user-list").status_code in (401, 403)
