"""Admin screens: roles, account assignment, password resets and the audit log.

Who may do what:
  admin       - manages sellers: create, assign accounts, reset, (de)activate
  super admin - also creates admins and changes roles
  nobody      - changes the super admin, or demotes/deactivates/resets themselves

Run: python -m pytest tests/test_admin_user_screens.py -v
"""

import pytest

from app.services import sessions
from auth_harness import add_user, auth, body

pytest_plugins = ["auth_harness"]

U = "/api/v1/admin/users"


@pytest.fixture
def client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.router import api_v1_router
    from app.errors import register_error_handlers
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api_v1_router)
    return TestClient(app)


def _people(db):
    return (add_user(db, "bridge@example.com", role="super_admin"),
            add_user(db, "admin@example.com", role="admin"),
            add_user(db, "seller@example.com"))


def _account(db, name):
    return str(db["accounts"].insert_one({"name": name, "status": "active"}).inserted_id)


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _code(r):
    return r.json()["error"]["code"]


# ------------------------------------------------------------------ create

def test_super_admin_creates_an_admin_but_an_admin_cannot(db, client):
    boss, admin, _ = _people(db)
    r = client.post(U, json={"email": "new.admin@example.com", "role": "admin"}, headers=auth(boss))
    assert r.status_code == 201 and body(r)["role"] == "admin"
    r = client.post(U, json={"email": "sneaky@example.com", "role": "admin"}, headers=auth(admin))
    assert r.status_code == 403
    assert db["users"].find_one({"email": "sneaky@example.com"}) is None


def test_no_request_can_create_a_super_admin(db, client):
    boss, _, _ = _people(db)
    r = client.post(U, json={"email": "x@example.com", "role": "super_admin"}, headers=auth(boss))
    assert r.status_code == 422


def test_a_generated_password_is_returned_once_and_works(db, client):
    _, admin, _ = _people(db)
    a = _account(db, "Astra")
    r = client.post(U, json={"email": "Seller.One@Example.com", "account_ids": [a, a]},
                    headers=auth(admin))
    assert r.status_code == 201, r.text
    created = body(r)
    pw = created["temporary_password"]
    assert pw and len(pw) == 12
    assert created["full_name"] == "seller.one@example.com"
    assert created["account_ids"] == [a] and created["must_change_password"] is True
    assert pw not in str(db["users"].find_one({"email": "seller.one@example.com"}))
    login = _login(client, "seller.one@example.com", pw)
    assert login.status_code == 200 and body(login)["user"]["must_change_password"] is True
    assert client.get(U, headers=auth(admin)).text.count(pw) == 0


def test_unknown_accounts_are_refused_and_nothing_is_created(db, client):
    _, admin, _ = _people(db)
    r = client.post(U, json={"email": "x@example.com", "account_ids": ["0" * 24, "bad"]},
                    headers=auth(admin))
    assert r.status_code == 422 and "account_ids" in r.json()["error"].get("fields", {})
    assert db["users"].find_one({"email": "x@example.com"}) is None


# ---------------------------------------------------------------- accounts

def test_admin_assigns_and_removes_accounts_and_it_is_audited(db, client):
    _, admin, seller = _people(db)
    a, b = _account(db, "Astra"), _account(db, "Jabil")
    url = "%s/%s/accounts" % (U, seller["_id"])
    assert body(client.put(url, json={"account_ids": [a, b]}, headers=auth(admin)))["account_ids"] == [a, b]
    assert body(client.put(url, json={"account_ids": [b]}, headers=auth(admin)))["account_ids"] == [b]
    log = body(client.get("/api/v1/admin/audit?user_id=%s" % seller["_id"], headers=auth(admin)))
    assert log[0]["action"] == "user.accounts_changed"
    assert log[0]["details"] == {"added": [], "removed": ["Astra"]}
    assert log[1]["details"] == {"added": ["Astra", "Jabil"], "removed": []}
    assert log[0]["actor_email"] == "admin@example.com"


def test_admins_are_not_given_accounts(db, client):
    boss, admin, _ = _people(db)
    a = _account(db, "Astra")
    r = client.put("%s/%s/accounts" % (U, admin["_id"]), json={"account_ids": [a]}, headers=auth(boss))
    assert r.status_code == 422


def test_who_has_access_to_an_account(db, client):
    _, admin, seller = _people(db)
    a = _account(db, "Astra")
    other = add_user(db, "other@example.com")
    db["users"].update_one({"_id": seller["_id"]}, {"$set": {"account_ids": [a]}})
    rows = body(client.get("/api/v1/admin/accounts/%s/users" % a, headers=auth(admin)))
    assert [r["email"] for r in rows] == ["seller@example.com"]
    assert other["email"] not in str(rows)


# ------------------------------------------------------------------- roles

def test_only_the_super_admin_changes_roles(db, client):
    boss, admin, seller = _people(db)
    url = "%s/%s/role" % (U, seller["_id"])
    assert client.put(url, json={"role": "admin"}, headers=auth(admin)).status_code == 403
    r = client.put(url, json={"role": "admin"}, headers=auth(boss))
    assert r.status_code == 200 and body(r)["role"] == "admin"
    # Promoted: sees every account at once, with no assignments.
    _account(db, "Astra")
    names = [x["name"] for x in body(client.get("/api/v1/accounts/user-list", headers=auth(seller)))]
    assert names == ["Astra"]
    r = client.put(url, json={"role": "user"}, headers=auth(boss))
    assert body(r)["role"] == "user"


@pytest.mark.parametrize("action", ["role", "deactivate", "reset", "accounts"])
def test_nobody_changes_the_super_admin(db, client, action):
    boss, admin, _ = _people(db)
    other_boss = add_user(db, "other.boss@example.com", role="super_admin")
    url = "%s/%s" % (U, boss["_id"])
    method, path, payload = {
        "role": ("PUT", "/role", {"role": "user"}),
        "deactivate": ("PATCH", "", {"is_active": False}),
        "reset": ("POST", "/reset-password", {}),
        "accounts": ("PUT", "/accounts", {"account_ids": []}),
    }[action]
    for actor in (admin, other_boss):
        r = client.request(method, url + path, json=payload, headers=auth(actor))
        assert r.status_code == 403, (actor["email"], action, r.text)
    assert db["users"].find_one({"_id": boss["_id"]})["role"] == "super_admin"


def test_the_super_admin_cannot_demote_or_deactivate_themselves(db, client):
    boss, _, _ = _people(db)
    assert client.put("%s/%s/role" % (U, boss["_id"]), json={"role": "user"},
                      headers=auth(boss)).status_code == 403
    assert client.patch("%s/%s" % (U, boss["_id"]), json={"is_active": False},
                        headers=auth(boss)).status_code == 403


def test_an_admin_cannot_manage_another_admin_but_the_super_admin_can(db, client):
    boss, admin, _ = _people(db)
    other = add_user(db, "admin2@example.com", role="admin")
    url = "%s/%s" % (U, other["_id"])
    assert client.patch(url, json={"is_active": False}, headers=auth(admin)).status_code == 403
    assert client.post(url + "/reset-password", json={}, headers=auth(admin)).status_code == 403
    assert client.patch(url, json={"is_active": False}, headers=auth(boss)).status_code == 200


# ---------------------------------------------------------------- password

def test_reset_ends_sessions_and_forces_a_change(db, client):
    _, admin, seller = _people(db)
    old = auth(seller)
    r = client.post("%s/%s/reset-password" % (U, seller["_id"]), json={}, headers=auth(admin))
    assert r.status_code == 200, r.text
    pw = body(r)["temporary_password"]
    assert body(r)["user"]["must_change_password"] is True
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    assert db[sessions.SESSIONS].count_documents(
        {"user_id": str(seller["_id"]), "revoked_at": None}) == 0
    login = _login(client, "seller@example.com", pw)
    assert login.status_code == 200 and body(login)["user"]["must_change_password"] is True


def test_reset_with_a_chosen_password_returns_none(db, client):
    _, admin, seller = _people(db)
    r = client.post("%s/%s/reset-password" % (U, seller["_id"]), json={"password": "Chosen-123"},
                    headers=auth(admin))
    assert body(r)["temporary_password"] is None
    assert _login(client, "seller@example.com", "Chosen-123").status_code == 200


def test_an_admin_cannot_reset_their_own_password_here(db, client):
    _, admin, _ = _people(db)
    r = client.post("%s/%s/reset-password" % (U, admin["_id"]), json={}, headers=auth(admin))
    assert r.status_code == 403


# ------------------------------------------------------------------- audit

def test_the_audit_log_records_each_change_newest_first(db, client):
    boss, admin, seller = _people(db)
    client.post(U, json={"email": "new@example.com"}, headers=auth(admin))
    client.patch("%s/%s" % (U, seller["_id"]), json={"is_active": False}, headers=auth(admin))
    client.put("%s/%s/role" % (U, admin["_id"]), json={"role": "user"}, headers=auth(boss))
    client.post("/api/v1/auth/sessions/revoke-all", headers=auth(boss))
    log = body(client.get("/api/v1/admin/audit", headers=auth(boss)))
    assert [e["action"] for e in log] == ["sessions.revoked_all", "user.role_changed",
                                          "user.deactivated", "user.created"]
    assert log[1]["details"] == {"from": "admin", "to": "user"}
    assert log[3]["target_email"] == "new@example.com"


def test_a_seller_cannot_read_the_audit_log(db, client):
    _, _, seller = _people(db)
    assert client.get("/api/v1/admin/audit", headers=auth(seller)).status_code == 403


def test_a_password_change_is_audited(db, client):
    seller = add_user(db, "seller@example.com", must_change_password=True)
    r = client.post("/api/v1/auth/change-password", headers=auth(seller),
                    json={"current_password": "Password123!", "new_password": "Sunrise2026"})
    assert r.status_code == 200, r.text
    row = db["user_audit"].find_one({"action": "user.password_changed"})
    assert row["target_email"] == "seller@example.com" and row["details"] == {"first_sign_in": True}
