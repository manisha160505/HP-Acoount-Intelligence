"""Sign-in sessions: ES256 access tokens, refresh cookies, revocation, and the
forced password change.

Run: python -m pytest tests/test_auth_sessions.py -v
     REGEN_TEST_MONGO_URI=mongodb://localhost:27017 python -m pytest tests/test_auth_sessions.py
"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config.settings import settings
from app.core import security
from app.services import sessions
from auth_harness import PASSWORD, add_user, auth, body

pytest_plugins = ["auth_harness"]


@pytest.fixture(autouse=True)
def _plain_http_cookies(monkeypatch):
    # TestClient talks http://testserver; a Secure cookie would never be sent back.
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", False)


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def _bearer(r) -> dict:
    return {"Authorization": "Bearer %s" % body(r)["access_token"]}


def _code(r) -> str | None:
    return (r.json().get("error") or {}).get("code")


# ------------------------------------------------------------------ sign in

def test_login_returns_es256_token_and_httponly_strict_cookies(db, client):
    add_user(db, "user@example.com")
    r = _login(client, "user@example.com")
    assert r.status_code == 200, r.text
    data = body(r)
    assert data["expires_in"] == settings.ACCESS_TOKEN_MINUTES * 60
    assert data["user"]["must_change_password"] is False
    header = jwt.get_unverified_header(data["access_token"])
    assert header["alg"] == "ES256"
    claims = jwt.decode(data["access_token"], options={"verify_signature": False})
    assert claims["typ"] == "access" and claims["sid"] and claims["sub"]
    set_cookie = "\n".join(r.headers.get_list("set-cookie")).lower()
    for name in ("hp_refresh=", "hp_access="):
        assert name in set_cookie
    assert set_cookie.count("httponly") == 2 and set_cookie.count("samesite=strict") == 2
    assert "path=/api/v1/auth" in set_cookie
    assert db[sessions.SESSIONS].count_documents({}) == 1


def test_wrong_password_is_401_and_creates_no_session(db, client):
    add_user(db, "user@example.com")
    assert _login(client, "user@example.com", "nope").status_code == 401
    assert db[sessions.SESSIONS].count_documents({}) == 0


@pytest.mark.parametrize("forge", ["hs256", "none", "other_key"])
def test_forged_tokens_are_refused(db, client, forge):
    admin = add_user(db, "admin@example.com", role="admin")
    sid, _ = sessions.create(db, str(admin["_id"]))
    claims = {"sub": str(admin["_id"]), "role": "admin", "sid": sid, "typ": "access",
              "exp": datetime.now(UTC) + timedelta(minutes=5)}
    if forge == "hs256":
        # The old default secret, which anyone with the repository had.
        tok = jwt.encode(claims, "hp-account-intelligence-platform-secret-key-2026-enterprise",
                         algorithm="HS256")
    elif forge == "none":
        tok = jwt.encode(claims, None, algorithm="none")
    else:
        from cryptography.hazmat.primitives import serialization
        other = serialization.load_pem_private_key(
            security.generate_private_key_pem().encode(), password=None)
        tok = jwt.encode(claims, other, algorithm="ES256")
    r = client.get("/api/v1/admin/users", headers={"Authorization": "Bearer %s" % tok})
    assert r.status_code == 401


def test_query_string_token_is_no_longer_accepted(db, client):
    user = add_user(db, "user@example.com")
    tok = auth(user)["Authorization"].split()[1]
    r = client.post("/api/v1/events?token=%s" % tok, json={"events": []})
    assert r.status_code == 401


def test_missing_signing_key_fails_loudly(monkeypatch):
    monkeypatch.setattr(settings, "JWT_PRIVATE_KEY", "")
    with pytest.raises(security.SigningKeyMissing):
        security.ensure_signing_key()


# ------------------------------------------------------------------ refresh

def test_refresh_rotates_and_returns_the_user(db, client):
    add_user(db, "user@example.com")
    _login(client, "user@example.com")
    first = client.cookies.get("hp_refresh")
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 200, r.text
    assert body(r)["user"]["email"] == "user@example.com"
    second = client.cookies.get("hp_refresh")
    assert second and second != first
    assert client.get("/api/v1/auth/me", headers=_bearer(r)).status_code == 200


def test_refresh_without_cookie_is_401(db, client):
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_two_tabs_refreshing_at_once_both_succeed(db, client):
    add_user(db, "user@example.com")
    _login(client, "user@example.com")
    old = client.cookies.get("hp_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    # The second tab's request went out carrying the old cookie.
    r = client.post("/api/v1/auth/refresh", cookies={"hp_refresh": old})
    assert r.status_code == 200
    assert "hp_refresh=" not in "\n".join(r.headers.get_list("set-cookie"))


def test_reused_refresh_token_after_grace_revokes_the_session(db, client):
    add_user(db, "user@example.com")
    login = _login(client, "user@example.com")
    old = client.cookies.get("hp_refresh")
    assert client.post("/api/v1/auth/refresh").status_code == 200
    sid = old.split(".")[0]
    db[sessions.SESSIONS].update_one({"_id": sid}, {"$set": {
        "rotated_at": datetime.now(UTC) - timedelta(seconds=sessions.ROTATION_GRACE_SECONDS + 5)}})
    client.cookies.clear()
    assert client.post("/api/v1/auth/refresh", cookies={"hp_refresh": old}).status_code == 401
    assert db[sessions.SESSIONS].find_one({"_id": sid})["revoked_at"] is not None
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401


def test_idle_session_ends(db, client):
    add_user(db, "user@example.com")
    login = _login(client, "user@example.com")
    db[sessions.SESSIONS].update_many({}, {"$set": {
        "idle_expires_at": datetime.now(UTC) - timedelta(seconds=1)}})
    assert client.post("/api/v1/auth/refresh").status_code == 401
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401


def test_refresh_never_extends_past_the_hard_limit(db, client):
    add_user(db, "user@example.com")
    _login(client, "user@example.com")
    cap = datetime.now(UTC) + timedelta(hours=1)
    db[sessions.SESSIONS].update_many({}, {"$set": {"max_expires_at": cap}})
    assert client.post("/api/v1/auth/refresh").status_code == 200
    doc = db[sessions.SESSIONS].find_one({})
    assert sessions._aware(doc["idle_expires_at"]) <= cap


# ------------------------------------------------------------------ sign out

def test_logout_revokes_the_access_token_at_once(db, client):
    add_user(db, "user@example.com")
    login = _login(client, "user@example.com")
    assert client.post("/api/v1/auth/logout", headers=_bearer(login)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401
    assert client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_with_only_the_cookie_still_ends_the_session(db, client):
    add_user(db, "user@example.com")
    login = _login(client, "user@example.com")
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401


def test_deactivation_signs_the_user_out_at_once(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    user = add_user(db, "user@example.com")
    login = _login(client, "user@example.com")
    r = client.patch("/api/v1/admin/users/%s" % user["_id"], json={"is_active": False},
                     headers=auth(admin))
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401
    assert db[sessions.SESSIONS].count_documents(
        {"user_id": str(user["_id"]), "revoked_at": None}) == 0


# ---------------------------------------------------------- password change

def test_new_user_must_change_password_before_anything_else(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    r = client.post("/api/v1/admin/users", headers=auth(admin), json={
        "email": "seller@example.com", "full_name": "seller@example.com",
        "password": "TempPass123"})
    assert r.status_code == 201
    login = _login(client, "seller@example.com", "TempPass123")
    assert login.status_code == 200
    assert body(login)["user"]["must_change_password"] is True
    me = client.get("/api/v1/auth/me", headers=_bearer(login))
    assert me.status_code == 200 and body(me)["must_change_password"] is True
    blocked = client.post("/api/v1/events", json={"events": []}, headers=_bearer(login))
    assert blocked.status_code == 403 and _code(blocked) == "PASSWORD_CHANGE_REQUIRED"


def test_forced_admin_cannot_use_admin_routes_until_changed(db, client):
    add_user(db, "admin@example.com", role="admin", must_change_password=True)
    login = _login(client, "admin@example.com")
    r = client.get("/api/v1/admin/users", headers=_bearer(login))
    assert r.status_code == 403 and _code(r) == "PASSWORD_CHANGE_REQUIRED"


@pytest.mark.parametrize("new,status,code", [
    ("short7!", 422, "VALIDATION_ERROR"),
    (PASSWORD, 422, "VALIDATION_ERROR"),
])
def test_password_rules(db, client, new, status, code):
    add_user(db, "user@example.com", must_change_password=True)
    login = _login(client, "user@example.com")
    r = client.post("/api/v1/auth/change-password", headers=_bearer(login),
                    json={"current_password": PASSWORD, "new_password": new})
    assert r.status_code == status and _code(r) == code


def test_wrong_current_password_is_400_not_a_sign_out(db, client):
    add_user(db, "user@example.com", must_change_password=True)
    login = _login(client, "user@example.com")
    r = client.post("/api/v1/auth/change-password", headers=_bearer(login),
                    json={"current_password": "wrong", "new_password": "Sunrise2026"})
    assert r.status_code == 400
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 200


def test_change_password_ends_every_session_and_the_new_one_works(db, client):
    user = add_user(db, "user@example.com", must_change_password=True)
    other_browser = auth(user)
    login = _login(client, "user@example.com")
    r = client.post("/api/v1/auth/change-password", headers=_bearer(login),
                    json={"current_password": PASSWORD, "new_password": "Sunrise2026"})
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/auth/me", headers=_bearer(login)).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other_browser).status_code == 401
    assert _login(client, "user@example.com").status_code == 401
    again = _login(client, "user@example.com", "Sunrise2026")
    assert again.status_code == 200
    assert body(again)["user"]["must_change_password"] is False
    ok = client.post("/api/v1/events", json={"events": []}, headers=_bearer(again))
    assert ok.status_code == 200


# -------------------------------------------------------------- super admin

def test_super_admin_passes_admin_checks(db, client):
    boss = add_user(db, "bridge@example.com", role="super_admin")
    assert client.get("/api/v1/admin/users", headers=auth(boss)).status_code == 200


def test_sign_out_everyone_keeps_only_the_callers_session(db, client):
    boss = add_user(db, "bridge@example.com", role="super_admin")
    user = add_user(db, "user@example.com")
    admin = add_user(db, "admin@example.com", role="admin")
    mine, theirs, admins = auth(boss), auth(user), auth(admin)
    r = client.post("/api/v1/auth/sessions/revoke-all", headers=mine)
    assert r.status_code == 200
    assert client.get("/api/v1/auth/me", headers=mine).status_code == 200
    assert client.get("/api/v1/auth/me", headers=theirs).status_code == 401
    assert client.get("/api/v1/auth/me", headers=admins).status_code == 401


def test_only_the_super_admin_can_sign_out_everyone(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    user = add_user(db, "user@example.com")
    assert client.post("/api/v1/auth/sessions/revoke-all", headers=auth(admin)).status_code == 403
    assert client.post("/api/v1/auth/sessions/revoke-all", headers=auth(user)).status_code == 403


def test_role_comes_from_the_database_not_the_token(db, client):
    admin = add_user(db, "admin@example.com", role="admin")
    h = auth(admin)
    db["users"].update_one({"_id": admin["_id"]}, {"$set": {"role": "user"}})
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403
