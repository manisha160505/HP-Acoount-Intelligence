"""Admin-managed users, the login changes, and the usage-event endpoint.

Run: python -m pytest tests/test_user_management.py -v
     REGEN_TEST_MONGO_URI=mongodb://localhost:27017 python -m pytest tests/test_user_management.py
"""

from app.services.usage import USAGE_EVENTS
from auth_harness import PASSWORD, add_user, auth, body, token

# The `db` and `client` fixtures.
pytest_plugins = ["auth_harness"]

NEW_USER = {"email": "New.Seller@Example.com", "full_name": "New Seller",
            "password": "TempPass123!"}


def _admin_and_user(db):
    return add_user(db, "admin@example.com", role="admin"), add_user(db, "user@example.com")


def _login(client, email, password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


# --------------------------------------------------------------- create / list

def test_admin_can_create_user_defaults_active_and_role_user(db, client):
    admin, _ = _admin_and_user(db)
    r = client.post("/api/v1/admin/users", json={**NEW_USER, "role": "admin"},
                    headers=auth(admin))
    assert r.status_code == 201, r.text
    created = body(r)
    assert created["email"] == "new.seller@example.com"
    # A role in the body is ignored: this endpoint cannot create an admin.
    assert created["role"] == "user"
    assert created["is_active"] is True
    assert created["last_login_at"] is None
    assert created["created_at"]
    assert "password" not in r.text and "password_hash" not in r.text
    stored = db["users"].find_one({"email": "new.seller@example.com"})
    assert stored["role"] == "user"
    assert stored["password_hash"] != NEW_USER["password"]


def test_normal_user_cannot_create_list_or_patch_users(db, client):
    admin, user = _admin_and_user(db)
    h = auth(user)
    assert client.post("/api/v1/admin/users", json=NEW_USER, headers=h).status_code == 403
    assert client.get("/api/v1/admin/users", headers=h).status_code == 403
    r = client.patch("/api/v1/admin/users/%s" % admin["_id"], json={"is_active": False},
                     headers=h)
    assert r.status_code == 403
    assert db["users"].find_one({"_id": admin["_id"]}).get("is_active", True) is True


def test_unauthenticated_rejected_from_admin_endpoints(db, client):
    assert client.get("/api/v1/admin/users").status_code in (401, 403)
    assert client.get("/api/v1/admin/analytics").status_code in (401, 403)


def test_duplicate_email_rejected_case_insensitively(db, client):
    admin, _ = _admin_and_user(db)
    assert client.post("/api/v1/admin/users", json=NEW_USER,
                       headers=auth(admin)).status_code == 201
    r = client.post("/api/v1/admin/users",
                    json={**NEW_USER, "email": "NEW.SELLER@example.com"}, headers=auth(admin))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "ALREADY_EXISTS"
    assert db["users"].count_documents({"email": "new.seller@example.com"}) == 1


def test_invalid_input_rejected(db, client):
    admin, _ = _admin_and_user(db)
    for bad in ({**NEW_USER, "email": "not-an-email"}, {**NEW_USER, "password": "short"},
                {**NEW_USER, "full_name": ""}):
        assert client.post("/api/v1/admin/users", json=bad,
                           headers=auth(admin)).status_code == 422


def test_list_never_returns_password_hash(db, client):
    admin, _ = _admin_and_user(db)
    r = client.get("/api/v1/admin/users", headers=auth(admin))
    assert r.status_code == 200
    rows = body(r)
    assert {u["email"] for u in rows} == {"admin@example.com", "user@example.com"}
    assert "password" not in r.text
    for u in rows:
        assert set(u) == {"id", "email", "full_name", "role", "is_active",
                          "created_at", "last_login_at"}
        # Seeded before activation existed: no field, reported active.
        assert u["is_active"] is True


# ------------------------------------------------------ activate / deactivate

def test_deactivate_blocks_login_and_existing_token_then_reactivate(db, client):
    admin, user = _admin_and_user(db)
    old_token = auth(user)
    url = "/api/v1/admin/users/%s" % user["_id"]

    r = client.patch(url, json={"is_active": False}, headers=auth(admin))
    assert r.status_code == 200 and body(r)["is_active"] is False
    # Never deleted.
    assert db["users"].find_one({"_id": user["_id"]}) is not None

    assert _login(client, "user@example.com").status_code == 403
    # A token issued before the deactivation stops working too.
    assert client.post("/api/v1/events", json={"events": []},
                       headers=old_token).status_code == 401

    r = client.patch(url, json={"is_active": True}, headers=auth(admin))
    assert r.status_code == 200 and body(r)["is_active"] is True
    assert _login(client, "user@example.com").status_code == 200


def test_patch_only_changes_active_state(db, client):
    admin, user = _admin_and_user(db)
    r = client.patch("/api/v1/admin/users/%s" % user["_id"],
                     json={"is_active": False, "role": "admin", "email": "x@example.com"},
                     headers=auth(admin))
    assert r.status_code == 200
    stored = db["users"].find_one({"_id": user["_id"]})
    assert stored["role"] == "user" and stored["email"] == "user@example.com"


def test_patch_unknown_or_malformed_user(db, client):
    admin, _ = _admin_and_user(db)
    r = client.patch("/api/v1/admin/users/%s" % ("0" * 24), json={"is_active": False},
                     headers=auth(admin))
    assert r.status_code == 404 and r.json()["error"]["code"] == "USER_NOT_FOUND"
    r = client.patch("/api/v1/admin/users/nope", json={"is_active": False},
                     headers=auth(admin))
    assert r.status_code == 400


def test_admin_cannot_deactivate_self(db, client):
    admin, _ = _admin_and_user(db)
    r = client.patch("/api/v1/admin/users/%s" % admin["_id"], json={"is_active": False},
                     headers=auth(admin))
    assert r.status_code == 403


def test_history_survives_deactivation(db, client):
    admin, user = _admin_and_user(db)
    assert _login(client, "user@example.com").status_code == 200
    client.patch("/api/v1/admin/users/%s" % user["_id"], json={"is_active": False},
                 headers=auth(admin))
    assert db[USAGE_EVENTS].count_documents({"user_id": str(user["_id"])}) == 1


# ------------------------------------------------------------------- login

def test_login_sets_last_login_and_records_event_for_user(db, client):
    _, user = _admin_and_user(db)
    r = _login(client, "user@example.com")
    assert r.status_code == 200
    assert body(r)["access_token"] and body(r)["user"]["role"] == "user"
    assert db["users"].find_one({"_id": user["_id"]}).get("last_login_at") is not None
    events = list(db[USAGE_EVENTS].find({"user_id": str(user["_id"])}))
    assert [e["event"] for e in events] == ["login"]


def test_admin_login_records_no_event(db, client):
    admin, _ = _admin_and_user(db)
    assert _login(client, "admin@example.com").status_code == 200
    assert db["users"].find_one({"_id": admin["_id"]}).get("last_login_at") is not None
    assert db[USAGE_EVENTS].count_documents({}) == 0


def test_wrong_password_still_401(db, client):
    _admin_and_user(db)
    assert _login(client, "user@example.com", "wrong-password").status_code == 401
    assert db[USAGE_EVENTS].count_documents({}) == 0


# ------------------------------------------------------------------ events

def _view(feature="executive_dashboard", **extra):
    return {"event": "feature_view", "feature_key": feature, "account_id": "a1",
            "session_id": "s1", **extra}


def test_user_can_submit_events(db, client):
    _, user = _admin_and_user(db)
    r = client.post("/api/v1/events", json={"events": [_view(), _view("strategy_chat")]},
                    headers=auth(user))
    assert r.status_code == 200 and body(r) == {"accepted": 2}
    rows = list(db[USAGE_EVENTS].find({}))
    assert {e["feature_key"] for e in rows} == {"executive_dashboard", "strategy_chat"}
    assert all(e["user_id"] == str(user["_id"]) and e["ts"] for e in rows)


def test_client_user_id_and_ts_are_ignored(db, client):
    admin, user = _admin_and_user(db)
    spoof = _view(user_id=str(admin["_id"]), ts="2000-01-01T00:00:00Z")
    assert client.post("/api/v1/events", json={"events": [spoof]},
                       headers=auth(user)).status_code == 200
    (row,) = list(db[USAGE_EVENTS].find({}))
    assert row["user_id"] == str(user["_id"])
    assert row["ts"].year != 2000


def test_invalid_event_type_rejected(db, client):
    _, user = _admin_and_user(db)
    for bad in (_view(event="login"), _view(event="purchase"), {"feature_key": "x"}):
        r = client.post("/api/v1/events", json={"events": [bad]}, headers=auth(user))
        assert r.status_code == 422, bad
    assert client.post("/api/v1/events", content=b"not json", headers=auth(user)
                       ).status_code == 422
    assert db[USAGE_EVENTS].count_documents({}) == 0


def test_unknown_feature_dropped_not_fatal(db, client):
    _, user = _admin_and_user(db)
    r = client.post("/api/v1/events", json={"events": [_view("retired_feature"), _view()]},
                    headers=auth(user))
    assert r.status_code == 200 and body(r) == {"accepted": 1}


def test_unauthenticated_events_rejected(db, client):
    assert client.post("/api/v1/events", json={"events": [_view()]}).status_code == 401
    assert client.post("/api/v1/events?token=garbage",
                       json={"events": [_view()]}).status_code == 401


def test_beacon_style_submission(db, client):
    """sendBeacon: token in the query string, JSON body sent as text/plain."""
    _, user = _admin_and_user(db)
    import json
    r = client.post("/api/v1/events?token=%s" % token(user),
                    content=json.dumps({"events": [_view()]}),
                    headers={"Content-Type": "text/plain;charset=UTF-8"})
    assert r.status_code == 200 and body(r) == {"accepted": 1}


def test_admin_events_are_not_recorded(db, client):
    admin, _ = _admin_and_user(db)
    r = client.post("/api/v1/events", json={"events": [_view()]}, headers=auth(admin))
    assert r.status_code == 200 and body(r) == {"accepted": 0}
    assert db[USAGE_EVENTS].count_documents({}) == 0


def test_batch_size_is_bounded(db, client):
    _, user = _admin_and_user(db)
    r = client.post("/api/v1/events", json={"events": [_view()] * 101}, headers=auth(user))
    assert r.status_code == 422
