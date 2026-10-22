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
        if deps & {"require_admin_role", "require_super_admin"} and not deps & SELLER_DEPS:
            continue
        unguarded.append("%s %s" % (sorted(r.methods), r.path))
    assert not unguarded, "seller-reachable account routes without the access guard: %s" % unguarded


def test_the_guard_covers_the_routes_sellers_use():
    paths = {r.path for r in _guarded()}
    for expected in ("/api/v1/accounts/{account_id}/widgets/{feature_key}",
                     "/api/v1/accounts/{account_id}/widgets/strategy_chat/ask/stream",
                     "/api/v1/accounts/{account_id}/data/filing",
                     "/api/v1/accounts/{account_id}/data/download/{dataset_key}",
                     "/api/v1/accounts/{account_id}/widgets/strategy_chat/ask"):
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


# ------------------------------------------------------------ pipeline is ours

PIPELINE_PATHS = (
    "/api/v1/regeneration/preview", "/api/v1/regeneration", "/api/v1/regeneration/runs",
    "/api/v1/regeneration/queue", "/api/v1/regeneration/accounts-summary",
    "/api/v1/regeneration/live", "/api/v1/accounts/{account_id}/pipeline",
    "/api/v1/indexes/rebuild", "/api/v1/accounts/{account_id}/features/status",
    "/api/v1/accounts/{account_id}/features/{feature_id}/regenerate",
    "/api/v1/accounts/{account_id}/widgets/{feature_key}/regenerate",
    "/api/v1/accounts/{account_id}/retrieval/{index}/rebuild",
)


def test_every_pipeline_route_is_super_admin_only():
    by_path = {}
    for r in _routes():
        by_path.setdefault(r.path, set()).update(_top_deps(r))
    for path in PIPELINE_PATHS:
        assert by_path.get(path) == {"require_super_admin"}, (path, by_path.get(path))


@pytest.mark.parametrize("role", ["admin", "user"])
def test_hp_admins_and_sellers_cannot_reach_the_pipeline(db, api, role):
    acct = _account(db, "Astra")
    who = add_user(db, "%s@example.com" % role, role=role, account_ids=[acct])
    for method, path in (("GET", "/api/v1/regeneration/accounts-summary"),
                         ("GET", "/api/v1/accounts/%s/pipeline" % acct),
                         ("POST", "/api/v1/regeneration/preview")):
        r = api.request(method, path, headers=auth(who), json={})
        assert r.status_code == 403, (role, path, r.status_code)


def test_the_super_admin_reaches_the_pipeline(db, api):
    acct = _account(db, "Astra")
    boss = add_user(db, "bridge@example.com", role="super_admin")
    r = api.get("/api/v1/accounts/%s/pipeline" % acct, headers=auth(boss))
    assert r.status_code != 403, r.text


# ------------------------------------------- backend controls are BridgeAI's
#
# Client, 22 Oct: HP admins do not upload or change data files, AI
# instructions, guardrails or account details, create accounts, hide or show
# them, or read the internal feature mapping. The screens hide these; the
# server refuses them too, so a saved link or a script cannot reach them.

BRIDGEAI_ONLY = (
    ("GET", "/api/v1/accounts/{account_id}/data"),
    ("POST", "/api/v1/accounts/{account_id}/data"),
    ("DELETE", "/api/v1/accounts/{account_id}/data/{file_id}"),
    ("GET", "/api/v1/accounts/{account_id}/instructions"),
    ("PUT", "/api/v1/accounts/{account_id}/instructions"),
    ("GET", "/api/v1/accounts/{account_id}/guardrails"),
    ("PUT", "/api/v1/accounts/{account_id}/guardrails"),
    ("POST", "/api/v1/accounts"),
    ("PATCH", "/api/v1/accounts/{account_id}"),
    ("PATCH", "/api/v1/accounts/{account_id}/status"),
    ("GET", "/api/v1/features"),
    ("GET", "/api/v1/features/dependencies/reverse"),
    ("GET", "/api/v1/features/{feature_key}"),
)


def _deps_by_route():
    out = {}
    for r in _routes():
        for m in r.methods:
            out.setdefault((m, r.path), set()).update(_top_deps(r))
    return out


def test_every_backend_control_is_super_admin_only():
    by_route = _deps_by_route()
    for key in BRIDGEAI_ONLY:
        assert key in by_route, "route not found (renamed?): %s %s" % key
        assert "require_super_admin" in by_route[key], (key, by_route[key])
        assert not by_route[key] & {"require_admin_role", "require_user_role"}, (key, by_route[key])


@pytest.mark.parametrize("role", ["admin", "user"])
def test_hp_admins_and_sellers_are_refused_every_backend_control(db, api, role):
    acct = _account(db, "Astra")
    who = add_user(db, "%s@example.com" % role, role=role, account_ids=[acct])
    for method, path in BRIDGEAI_ONLY:
        url = path.replace("{account_id}", acct).replace("{file_id}", "0" * 24) \
                  .replace("{feature_key}", "executive_dashboard")
        r = api.request(method, url, headers=auth(who), json={})
        assert r.status_code == 403, (role, method, path, r.status_code)


def test_the_super_admin_reaches_the_backend_controls(db, api):
    acct = _account(db, "Astra")
    boss = add_user(db, "bridge@example.com", role="super_admin")
    for method, path in (("GET", "/api/v1/accounts/%s/data" % acct),
                         ("GET", "/api/v1/accounts/%s/instructions" % acct),
                         ("GET", "/api/v1/features")):
        r = api.request(method, path, headers=auth(boss))
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
    r = api.patch("/api/v1/accounts/%s/status" % acct, json={"status": "hidden"}, headers=auth(boss))
    assert r.status_code == 200 and body(r)["status"] == "hidden"


def test_hp_admins_still_list_accounts_and_manage_users(db, api):
    _account(db, "Astra")
    admin = add_user(db, "admin@example.com", role="admin")
    for path in ("/api/v1/accounts", "/api/v1/admin/users", "/api/v1/admin/audit"):
        assert api.get(path, headers=auth(admin)).status_code == 200, path


# ------------------------------------------------------- hidden means hidden

def _hidden(db, name="Hidden"):
    return str(db["accounts"].insert_one({"name": name, "status": "hidden"}).inserted_id)


def test_a_hidden_account_cannot_be_opened_from_an_old_link(db, api):
    """Client, 22 Oct (Q3): hiding an account takes it out of use for HP's
    sellers and admins; a bookmark to its dashboard no longer opens it."""
    acct = _hidden(db)
    seller = add_user(db, "seller@example.com", account_ids=[acct])
    admin = add_user(db, "admin@example.com", role="admin")
    for who in (seller, admin):
        r = api.get("/api/v1/accounts/%s/data/filings" % acct, headers=auth(who))
        assert r.status_code == 404 and r.json()["error"]["code"] == "ACCOUNT_NOT_FOUND", who["email"]


def test_the_super_admin_still_opens_a_hidden_account(db, api):
    acct = _hidden(db)
    boss = add_user(db, "bridge@example.com", role="super_admin")
    assert api.get("/api/v1/accounts/%s/data/filings" % acct, headers=auth(boss)).status_code == 200


def test_showing_it_again_restores_access_at_once(db, api):
    acct = _hidden(db)
    seller = add_user(db, "seller@example.com", account_ids=[acct])
    h = auth(seller)
    assert api.get("/api/v1/accounts/%s/data/filings" % acct, headers=h).status_code == 404
    db["accounts"].update_one({}, {"$set": {"status": "active"}})
    assert api.get("/api/v1/accounts/%s/data/filings" % acct, headers=h).status_code == 200


def test_only_the_super_admin_lists_hidden_accounts_on_the_platform_page(db, api):
    _account(db, "Astra")
    _hidden(db)
    admin = add_user(db, "admin@example.com", role="admin")
    boss = add_user(db, "bridge@example.com", role="super_admin")
    assert sorted(a["name"] for a in body(api.get("/api/v1/accounts", headers=auth(admin)))) == ["Astra"]
    assert sorted(a["name"] for a in body(api.get("/api/v1/accounts", headers=auth(boss)))) == ["Astra", "Hidden"]
