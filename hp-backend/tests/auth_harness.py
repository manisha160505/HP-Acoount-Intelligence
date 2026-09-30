"""Shared setup for the user-management, usage-event and analytics tests.

The app under test is built from the real routers with the real auth
dependencies - no `dependency_overrides` - so a test that says "a user cannot
call this" exercises the same `require_admin_role` production does.

`db` runs every test on the in-memory fake and again on a real mongod when
`REGEN_TEST_MONGO_URI` is set (a throwaway database, dropped afterwards), the
same convention the regeneration tests use.
"""

import os
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import create_access_token, get_password_hash
from app.database import mongodb
from app.errors import register_error_handlers
from app.services import usage, users_admin
from regen_fakes import FakeDb

PASSWORD = "Password123!"
# bcrypt is deliberately slow; hash once per test session, not per user.
_HASH = get_password_hash(PASSWORD)


def mongo_db():
    uri = os.getenv("REGEN_TEST_MONGO_URI")
    if not uri:
        pytest.skip("set REGEN_TEST_MONGO_URI to also run against a real mongod")
    from pymongo import MongoClient
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    name = "usage_test_%s" % uuid.uuid4().hex[:10]
    return client, client[name], name


def install(monkeypatch, db):
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    users_admin.ensure_indexes(db)
    usage.ensure_indexes(db)
    return db


@pytest.fixture(params=["fake", "mongo"])
def db(request, monkeypatch):
    if request.param == "fake":
        yield install(monkeypatch, FakeDb())
        return
    client, real, name = mongo_db()
    try:
        yield install(monkeypatch, real)
    finally:
        client.drop_database(name)
        client.close()


@pytest.fixture
def client():
    from app.api.v1.admin_users import router as admin_users_router
    from app.api.v1.analytics import router as analytics_router
    from app.api.v1.auth import router as auth_router
    from app.api.v1.events import router as events_router
    app = FastAPI()
    register_error_handlers(app)
    for router in (auth_router, admin_users_router, events_router, analytics_router):
        app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def add_user(db, email, role="user", **extra):
    doc = {"email": email, "full_name": email.split("@")[0], "role": role,
           "password_hash": _HASH, **extra}
    doc["_id"] = db["users"].insert_one(doc).inserted_id
    return doc


def auth(user) -> dict:
    token = create_access_token({"sub": str(user["_id"]), "role": user["role"]})
    return {"Authorization": "Bearer %s" % token}


def token(user) -> str:
    return create_access_token({"sub": str(user["_id"]), "role": user["role"]})


def body(response):
    """The payload, whether or not an envelope middleware wrapped it."""
    data = response.json()
    if isinstance(data, dict) and {"success", "data", "meta"} <= set(data):
        return data["data"]
    return data
