"""Forgot password: a user sets a new password with their recovery code.

The code is issued whenever a user sets a password, shown once, stored only as
a hash, and works once. No email and no admin are needed; an admin reset
cancels the code (the user may have lost it).

Run: python -m pytest tests/test_password_recovery.py -v
"""

import re

import pytest

from app.config.settings import settings
from auth_harness import PASSWORD, add_user, auth, body

pytest_plugins = ["auth_harness"]

CODE = re.compile(r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")


@pytest.fixture(autouse=True)
def _plain_http_cookies(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", False)


def _login(client, email, password):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _change(client, user, new="Sunrise2026"):
    r = client.post("/api/v1/auth/change-password", headers=auth(user),
                    json={"current_password": PASSWORD, "new_password": new})
    assert r.status_code == 200, r.text
    return body(r)["recovery_code"]


def _forgot(client, email, code, new="Moonrise2027"):
    return client.post("/api/v1/auth/forgot-password",
                       json={"email": email, "recovery_code": code, "new_password": new})


def test_setting_a_password_gives_a_recovery_code_stored_only_as_a_hash(db, client):
    seller = add_user(db, "seller@example.com", must_change_password=True)
    code = _change(client, seller)
    assert CODE.match(code), code
    stored = db["users"].find_one({"_id": seller["_id"]})
    assert stored["recovery_code_hash"] and code.replace("-", "") not in str(stored)


def test_forgot_password_with_the_code_sets_a_new_password_and_a_new_code(db, client):
    seller = add_user(db, "seller@example.com")
    code = _change(client, seller)
    old_session = auth(seller)
    r = _forgot(client, "Seller@Example.com", code.lower().replace("-", " "))
    assert r.status_code == 200, r.text
    new_code = body(r)["recovery_code"]
    assert CODE.match(new_code) and new_code != code
    assert client.get("/api/v1/auth/me", headers=old_session).status_code == 401
    assert _login(client, "seller@example.com", "Sunrise2026").status_code == 401
    ok = _login(client, "seller@example.com", "Moonrise2027")
    assert ok.status_code == 200 and body(ok)["user"]["must_change_password"] is False
    row = db["user_audit"].find_one({"action": "user.password_recovered"})
    assert row["target_email"] == "seller@example.com"


def test_a_code_works_once(db, client):
    seller = add_user(db, "seller@example.com")
    code = _change(client, seller)
    assert _forgot(client, "seller@example.com", code).status_code == 200
    assert _forgot(client, "seller@example.com", code, new="Another2028").status_code == 400


def test_a_wrong_code_and_an_unknown_email_get_the_same_answer(db, client):
    seller = add_user(db, "seller@example.com")
    _change(client, seller)
    wrong = _forgot(client, "seller@example.com", "AAAA-BBBB-CCCC-DDDD")
    unknown = _forgot(client, "nobody@example.com", "AAAA-BBBB-CCCC-DDDD")
    assert wrong.status_code == unknown.status_code == 400
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]
    assert _login(client, "seller@example.com", "Sunrise2026").status_code == 200


def test_a_user_who_never_set_a_password_has_no_code(db, client):
    add_user(db, "new@example.com", must_change_password=True)
    assert _forgot(client, "new@example.com", "AAAA-BBBB-CCCC-DDDD").status_code == 400


def test_an_admin_reset_cancels_the_code(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    seller = add_user(db, "seller@example.com")
    code = _change(client, seller)
    r = client.post("/api/v1/admin/users/%s/reset-password" % seller["_id"], json={},
                    headers=auth(admin))
    assert r.status_code == 200
    assert _forgot(client, "seller@example.com", code).status_code == 400


def test_a_deactivated_user_cannot_use_their_code(db, client):
    seller = add_user(db, "seller@example.com")
    code = _change(client, seller)
    db["users"].update_one({"_id": seller["_id"]}, {"$set": {"is_active": False}})
    assert _forgot(client, "seller@example.com", code).status_code == 400


def test_the_new_password_follows_the_usual_rules(db, client):
    seller = add_user(db, "seller@example.com")
    code = _change(client, seller)
    assert _forgot(client, "seller@example.com", code, new="short").status_code == 422
    assert _forgot(client, "seller@example.com", code, new="Sunrise2026").status_code == 422
    # A refused password does not use up the code.
    assert _forgot(client, "seller@example.com", code).status_code == 200
