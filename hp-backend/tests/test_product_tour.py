"""The first-sign-in product tour is remembered on the user, not the browser.

Client, 17 Oct: new users are walked through every feature on their first
sign-in. Finishing or closing the tour records `tour_completed_at`, so it does
not start again on another laptop or browser; sign-in, refresh and /auth/me
all carry the field so the dashboard can decide.

Run: python -m pytest tests/test_product_tour.py -v
"""

from datetime import UTC, datetime

import pytest

from app.config.settings import settings
from auth_harness import PASSWORD, add_user, auth, body

pytest_plugins = ["auth_harness"]

URL = "/api/v1/auth/me/tour-completed"


@pytest.fixture(autouse=True)
def _plain_http_cookies(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_COOKIE_SECURE", False)


def _login(client, email):
    return client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})


def test_a_new_user_has_not_seen_the_tour(db, client):
    user = add_user(db, "new@example.com")
    assert body(_login(client, "new@example.com"))["user"]["tour_completed_at"] is None
    assert body(client.get("/api/v1/auth/me", headers=auth(user)))["tour_completed_at"] is None


def test_finishing_the_tour_is_recorded_and_returned_everywhere(db, client):
    user = add_user(db, "seller@example.com")
    r = client.post(URL, headers=auth(user))
    assert r.status_code == 200, r.text
    assert body(r)["tour_completed_at"]
    assert db["users"].find_one({"_id": user["_id"]})["tour_completed_at"]

    assert body(client.get("/api/v1/auth/me", headers=auth(user)))["tour_completed_at"]
    assert body(_login(client, "seller@example.com"))["user"]["tour_completed_at"]
    assert body(client.post("/api/v1/auth/refresh"))["user"]["tour_completed_at"]


def test_the_first_time_is_kept(db, client):
    first = datetime(2026, 10, 1, tzinfo=UTC)
    user = add_user(db, "seen@example.com", tour_completed_at=first)
    r = client.post(URL, headers=auth(user))
    assert r.status_code == 200
    stored = db["users"].find_one({"_id": user["_id"]})["tour_completed_at"]
    assert stored.replace(tzinfo=UTC) == first


def test_it_needs_a_signed_in_user(db, client):
    assert client.post(URL).status_code == 401


def test_a_user_who_must_change_password_cannot_record_it(db, client):
    user = add_user(db, "forced@example.com", must_change_password=True)
    assert client.post(URL, headers=auth(user)).status_code == 403
    assert "tour_completed_at" not in db["users"].find_one({"_id": user["_id"]})


# --- the admin pages' tour, remembered apart --------------------------------

def test_the_admin_tour_is_remembered_apart_from_the_dashboard_tour(db, client):
    admin = add_user(db, "boss@example.com", role="admin")
    r = client.post(URL + "?tour=admin", headers=auth(admin))
    assert r.status_code == 200, r.text
    assert body(r)["tour"] == "admin"
    me = body(client.get("/api/v1/auth/me", headers=auth(admin)))
    assert me["admin_tour_completed_at"] and me["tour_completed_at"] is None
    login = body(_login(client, "boss@example.com"))["user"]
    assert login["admin_tour_completed_at"] and login["tour_completed_at"] is None

    client.post(URL, headers=auth(admin))
    stored = db["users"].find_one({"_id": admin["_id"]})
    assert stored["tour_completed_at"] and stored["admin_tour_completed_at"]


def test_an_unknown_tour_is_refused(db, client):
    user = add_user(db, "odd@example.com")
    assert client.post(URL + "?tour=other", headers=auth(user)).status_code == 422
    assert "tour_completed_at" not in db["users"].find_one({"_id": user["_id"]})
