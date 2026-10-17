"""Per-account access: a seller reaches only the accounts assigned to them.

Two layers. The wiring test walks every route in the API and fails when one
with an `{account_id}` in its path is open to sellers without the access guard,
so a route added later cannot skip it. The behaviour tests call every such route
as a seller who does not hold the account and expect the same 404 a missing
account gets.

Run: python -m pytest tests/test_account_access.py -v
"""

import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_error_handlers
from auth_harness import add_user, auth, body, token

pytest_plugins = ["auth_harness"]

GUARDS = {"require_account_access", "require_account_access_flexible"}
SELLER_DEPS = {"require_user_role", "require_user_role_flexible", "get_current_user",
               "get_current_user_flexible"}


def _api_router():
    from app.api.v1.router import api_v1_router
    return api_v1_router


class _Route:
    """A route with the full path it is served at."""

    def __init__(self, path, route):
        self.path, self.methods, self.dependant = path, route.methods, route.dependant


def _flatten(router, prefix=""):
    # FastAPI 0.141 keeps an included router nested (`_IncludedRouter`) instead
    # of copying its routes up, so `router.routes` alone misses all of them.
    for r in router.routes:
        if hasattr(r, "include_context"):
            yield from _flatten(r.original_router, prefix + r.include_context.prefix)
        elif hasattr(r, "dependant"):
            yield _Route(prefix + r.path, r)


def _routes():
    routes = list(_flatten(_api_router()))
    assert len(routes) > 50, "route discovery found only %d routes" % len(routes)
    return routes


def _top_deps(route) -> set[str]:
    return {getattr(d.call, "__name__", "") for d in route.dependant.dependencies}


def _account_routes():
    return [r for r in _routes() if "{account_id}" in r.path]


def _guarded():
    return [r for r in _account_routes() if _top_deps(r) & GUARDS]


@pytest.fixture
def api(db):
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(_api_router())
    return TestClient(app)


def _account(db, name):
    return str(db["accounts"].insert_one({"name": name, "status": "active"}).inserted_id)


def _url(route, account_id) -> str:
    path = route.path.replace("{account_id}", account_id)
    return re.sub(r"\{[^}]+\}", "x", path)


# ------------------------------------------------------------------- wiring

def test_every_seller_reachable_account_route_is_guarded():
    unguarded = []
    for r in _account_routes():
        deps = _top_deps(r)
        if deps & GUARDS:
            continue
        if "require_admin_role" in deps and not deps & SELLER_DEPS:
            continue
        unguarded.append("%s %s" % (sorted(r.methods), r.path))
    assert not unguarded, "seller-reachable account routes without the access guard: %s" % unguarded


def test_the_guard_covers_the_routes_sellers_use():
    paths = {r.path for r in _guarded()}
    for expected in ("/api/v1/accounts/{account_id}/widgets/{feature_key}",
                     "/api/v1/accounts/{account_id}/widgets/strategy_chat/ask/stream",
                     "/api/v1/accounts/{account_id}/data/filing",
                     "/api/v1/accounts/{account_id}/data/download/{dataset_key}",
                     "/api/v1/accounts/{account_id}/features/status"):
        assert expected in paths


# ---------------------------------------------------------------- behaviour

@pytest.mark.parametrize("route", _guarded(), ids=lambda r: "%s %s" % (sorted(r.methods)[0], r.path))
def test_a_seller_cannot_reach_an_account_that_is_not_theirs(db, api, route):
    mine, theirs = _account(db, "Mine"), _account(db, "Theirs")
    seller = add_user(db, "seller@example.com", account_ids=[mine])
    method = sorted(route.methods)[0]
    r = api.request(method, _url(route, theirs), headers=auth(seller), json={})
    assert r.status_code == 404, (route.path, r.status_code, r.text[:200])
    assert r.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_a_seller_reaches_their_own_account(db, api):
    mine = _account(db, "Mine")
    seller = add_user(db, "seller@example.com", account_ids=[mine])
    r = api.get("/api/v1/accounts/%s/data/filings" % mine, headers=auth(seller))
    assert r.status_code == 200, r.text


def test_an_admin_reaches_every_account_without_assignments(db, api):
    acct = _account(db, "Any")
    for role in ("admin", "super_admin"):
        admin = add_user(db, "%s@example.com" % role, role=role)
        r = api.get("/api/v1/accounts/%s/data/filings" % acct, headers=auth(admin))
        assert r.status_code == 200, (role, r.text)


def test_the_cookie_route_is_guarded_too(db, api):
    mine, theirs = _account(db, "Mine"), _account(db, "Theirs")
    seller = add_user(db, "seller@example.com", account_ids=[mine])
    api.cookies.set("hp_access", token(seller))
    r = api.get("/api/v1/accounts/%s/data/filing?name=x.pdf" % theirs)
    assert r.status_code == 404 and r.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_removing_an_account_takes_effect_on_the_next_request(db, api):
    mine = _account(db, "Mine")
    seller = add_user(db, "seller@example.com", account_ids=[mine])
    h = auth(seller)
    assert api.get("/api/v1/accounts/%s/data/filings" % mine, headers=h).status_code == 200
    db["users"].update_one({"_id": seller["_id"]}, {"$set": {"account_ids": []}})
    assert api.get("/api/v1/accounts/%s/data/filings" % mine, headers=h).status_code == 404


# -------------------------------------------------------------- the picker

def _names(api, user):
    r = api.get("/api/v1/accounts/user-list", headers=auth(user))
    assert r.status_code == 200, r.text
    return [a["name"] for a in body(r)]


def test_the_picker_lists_only_assigned_accounts(db, api):
    a, b = _account(db, "Astra"), _account(db, "Jabil")
    _account(db, "Canon")
    seller = add_user(db, "seller@example.com", account_ids=[b, a])
    assert _names(api, seller) == ["Astra", "Jabil"]


def test_a_seller_with_no_accounts_gets_an_empty_list(db, api):
    _account(db, "Astra")
    assert _names(api, add_user(db, "new@example.com")) == []
    assert _names(api, add_user(db, "empty@example.com", account_ids=[])) == []


def test_a_bad_or_hidden_assignment_is_simply_not_listed(db, api):
    a = _account(db, "Astra")
    hidden = str(db["accounts"].insert_one({"name": "Hidden", "status": "hidden"}).inserted_id)
    seller = add_user(db, "seller@example.com", account_ids=[a, hidden, "not-an-id"])
    assert _names(api, seller) == ["Astra"]


def test_admins_see_every_active_account(db, api):
    _account(db, "Astra")
    _account(db, "Jabil")
    for role in ("admin", "super_admin"):
        assert _names(api, add_user(db, "%s@example.com" % role, role=role)) == ["Astra", "Jabil"]
