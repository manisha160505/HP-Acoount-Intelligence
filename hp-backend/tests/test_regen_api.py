"""The HTTP surface of regeneration: nothing generates inside a request.

Upload, the page-view bootstrap and every regenerate endpoint queue work and
return; the tests prove it by making every extractor raise if it is called.

Run: python -m pytest tests/test_regen_api.py -v
"""

import hashlib
import io

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import deps
from app.database import mongodb
from app.services.regen import engine as engine_mod, jobs, manifest
from app.services.regen.graph import DEFAULT
from regen_fakes import FakeDb

USER = {"id": "u1", "email": "admin@example.com", "full_name": "Admin", "role": "admin"}


@pytest.fixture
def env(monkeypatch, tmp_path):
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    engine = engine_mod.Engine(db=db, graph=DEFAULT, versions=manifest.StaticVersions())
    engine.ensure_indexes()
    monkeypatch.setattr(engine_mod, "_default_engine", engine)

    from app.config.settings import settings
    monkeypatch.setattr(settings, "DATA_STORAGE_DIR", str(tmp_path))

    # Any inline generation fails the test.
    def boom(*_a, **_kw):
        raise AssertionError("an extractor ran inside a request")
    from app.services.regen import producers
    for name in dir(producers):
        if not name.startswith("_") and callable(getattr(producers, name)):
            monkeypatch.setattr(producers, name, boom)
    from app.api.v1 import widgets
    for key in list(widgets.FEATURE_EXTRACTORS):
        monkeypatch.setitem(widgets.FEATURE_EXTRACTORS, key, boom)

    from app.api.v1.account_data import router as data_router
    from app.api.v1.regeneration import router as regen_router
    from app.api.v1.widgets import router as widgets_router
    app = FastAPI()
    for router in (data_router, regen_router, widgets_router):
        app.include_router(router, prefix="/api/v1")
    for dep in (deps.require_user_role, deps.require_admin_role,
                deps.get_current_user_flexible):
        app.dependency_overrides[dep] = lambda: USER

    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})
    return TestClient(app), db, account_id


def test_regenerate_returns_202_with_the_jobs_and_repeats_coalesce(env):
    client, db, acct = env
    first = client.post("/api/v1/accounts/%s/features/stakeholder_map/regenerate" % acct)
    assert first.status_code == 202
    nodes = {n["node_id"]: n for n in first.json()["nodes"]}
    assert set(nodes) == {"stakeholder_roster", "stakeholder_talking_points"}
    assert all(n["job"]["status"] == jobs.PENDING for n in nodes.values())
    second = client.post("/api/v1/accounts/%s/features/stakeholder_map/regenerate" % acct)
    assert all(n["job"]["coalesced"] for n in second.json()["nodes"])
    assert db[jobs.COLLECTION].count_documents({"status": jobs.PENDING}) == 2


def test_regenerate_validates_account_and_feature(env):
    client, _db, acct = env
    assert client.post("/api/v1/accounts/nope/features/intent_demand_signals/regenerate"
                       ).status_code == 400
    assert client.post("/api/v1/accounts/%s/features/nope/regenerate" % str(ObjectId())
                       ).status_code == 404
    assert client.post("/api/v1/accounts/%s/features/nope/regenerate" % acct
                       ).status_code == 404


def test_status_lists_every_feature_with_a_lifecycle(env):
    client, _db, acct = env
    body = client.get("/api/v1/accounts/%s/features/status" % acct).json()
    from app.api.v1.widgets import WIDGET_REGISTRY
    assert set(body["features"]) == set(WIDGET_REGISTRY)
    assert {f["lifecycle"] for f in body["features"].values()} == {"NEVER_GENERATED"}


def test_job_history_hides_lease_internals(env):
    client, _db, acct = env
    client.post("/api/v1/accounts/%s/features/intent_demand_signals/regenerate" % acct)
    rows = client.get("/api/v1/accounts/%s/regeneration/jobs" % acct).json()["jobs"]
    assert rows and "fence" not in rows[0] and "lease_owner" not in rows[0]
    assert rows[0]["triggers"][0]["actor"] == "user:u1"


def test_upload_queues_the_readers_of_the_dataset_and_returns_at_once(env):
    client, db, acct = env
    content = b"Company Name,Business Description\nAcme,Makes things\n"
    resp = client.post("/api/v1/accounts/%s/data" % acct,
                       data={"dataset_key": "firmographics"},
                       files={"file": ("firmographics.csv", io.BytesIO(content), "text/csv")})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    readers = set(DEFAULT.readers_of_dataset("firmographics"))
    assert set(body["regeneration"]["queued"]) == readers
    row = db["account_data_files"].find_one({"account_id": acct})
    assert row["content_sha256"] == hashlib.sha256(content).hexdigest()
    # Content-addressed, so the stored bytes can never be overwritten.
    assert row["stored_filename"].startswith(row["content_sha256"][:12])
    # Nothing reads firmographics in these nodes, so they were not queued.
    assert "stakeholder_roster" not in body["regeneration"]["queued"]


def test_a_page_view_queues_a_never_generated_feature_instead_of_generating_it(env):
    client, db, acct = env
    resp = client.get("/api/v1/accounts/%s/widgets/intent_demand_signals" % acct)
    assert resp.status_code == 200
    assert {w["status"] for w in resp.json()} == {"empty"}
    assert db[jobs.COLLECTION].count_documents({"node_id": "intent",
                                                "status": jobs.PENDING}) == 1


def test_the_old_regenerate_endpoint_queues_and_returns_the_widgets(env):
    client, db, acct = env
    resp = client.post("/api/v1/accounts/%s/widgets/tech_landscape/regenerate" % acct)
    assert resp.status_code == 200
    assert len(resp.json()) == 5
    queued = {j["node_id"] for j in db[jobs.COLLECTION].find({"status": jobs.PENDING})}
    assert queued == {"tech_core", "tech_recs"}
