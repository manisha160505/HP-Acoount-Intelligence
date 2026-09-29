"""The HTTP surface of regeneration: nothing generates inside a request, and
nothing is queued unless a regeneration run was asked for (29 Sep).

Upload and page views queue nothing; preview writes nothing; a run queues
exactly its plan. Every extractor raises if it is called, so a test that
generated anything inline would fail.

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
    # The data rows these tests insert name files that are never opened -
    # nothing runs here - so they count as present (one test says otherwise).
    present = {"yes": True}
    engine = engine_mod.Engine(db=db, graph=DEFAULT, versions=manifest.StaticVersions(),
                               file_exists=lambda _row: present["yes"])
    db.files_present = present
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




def _data(db, acct, *keys):
    """Active dataset rows, so the planner sees data to generate from. The
    files themselves are never read: nothing runs in these tests."""
    for key in keys:
        db["account_data_files"].insert_one({
            "account_id": acct, "dataset_key": key, "status": "active",
            "file_path": "data/accounts/%s/%s/x.csv" % (acct, key),
            "original_filename": "%s.csv" % key,
            "content_sha256": hashlib.sha256(key.encode()).hexdigest()})


def _live(db):
    return list(db[jobs.COLLECTION].find({"status": {"$in": list(jobs.LIVE)}}))


def test_regenerate_feature_is_an_explicit_run_and_repeats_share_the_job(env):
    client, db, acct = env
    _data(db, acct, "prospect_contacts", "firmographics", "technographics")
    first = client.post("/api/v1/accounts/%s/features/stakeholder_map/regenerate" % acct)
    assert first.status_code == 202
    body = first.json()
    assert body["run_id"]
    nodes = {n["node_id"]: n for n in body["nodes"]}
    assert nodes["stakeholder_roster"]["action"] == "run"
    queued = {j["node_id"] for j in _live(db)}
    assert "stakeholder_roster" in queued
    second = client.post("/api/v1/accounts/%s/features/stakeholder_map/regenerate" % acct)
    assert all(n["job"]["coalesced"] for n in second.json()["nodes"] if n["job"])
    assert {j["node_id"] for j in _live(db)} == queued
    run = db["regen_runs"].find_one({"_id": ObjectId(body["run_id"])})
    assert run["request"]["force"] is False


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
    client, db, acct = env
    _data(db, acct, "intent_score", "intent_topics", "job_openings", "firmographics")
    client.post("/api/v1/accounts/%s/features/intent_demand_signals/regenerate" % acct)
    rows = client.get("/api/v1/accounts/%s/regeneration/jobs" % acct).json()["jobs"]
    assert rows and "fence" not in rows[0] and "lease_owner" not in rows[0]
    assert rows[0]["triggers"][0]["actor"] == "user:u1"
    assert rows[0]["run_ids"]


def test_upload_stores_the_file_and_queues_nothing(env):
    client, db, acct = env
    content = b"Company Name,Business Description\nAcme,Makes things\n"
    resp = client.post("/api/v1/accounts/%s/data" % acct,
                       data={"dataset_key": "firmographics"},
                       files={"file": ("firmographics.csv", io.BytesIO(content), "text/csv")})
    assert resp.status_code == 201, resp.text
    regen = resp.json()["regeneration"]
    assert regen["queued"] == []
    assert set(DEFAULT.readers_of_dataset("firmographics")) <= set(regen["stale"])
    assert _live(db) == []
    row = db["account_data_files"].find_one({"account_id": acct})
    assert row["content_sha256"] == hashlib.sha256(content).hexdigest()
    # Content-addressed, so the stored bytes can never be overwritten.
    assert row["stored_filename"].startswith(row["content_sha256"][:12])


def test_a_page_view_neither_generates_nor_queues(env):
    client, db, acct = env
    _data(db, acct, "intent_score", "intent_topics")
    resp = client.get("/api/v1/accounts/%s/widgets/intent_demand_signals" % acct)
    assert resp.status_code == 200
    assert {w["status"] for w in resp.json()} == {"empty"}
    assert _live(db) == []


def test_the_old_regenerate_endpoint_runs_without_force(env):
    client, db, acct = env
    _data(db, acct, "technographics", "technology_detections", "webstack",
          "tech_breakdown", "firmographics")
    resp = client.post("/api/v1/accounts/%s/widgets/tech_landscape/regenerate" % acct)
    assert resp.status_code == 200
    assert len(resp.json()) == 5
    queued = {j["node_id"]: j for j in _live(db)}
    assert "tech_core" in queued and not queued["tech_core"].get("force")


def test_preview_writes_nothing_and_run_queues_exactly_the_plan(env):
    client, db, acct = env
    _data(db, acct, "firmographics", "intent_score", "intent_topics")
    body = {"accounts": [acct], "features": ["intent_demand_signals"]}
    preview = client.post("/api/v1/regeneration/preview", json=body)
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert _live(db) == [] and db["regen_runs"].count_documents({}) == 0
    planned = {i["node_id"] for i in plan["accounts"][0]["items"] if i["action"] == "run"}
    assert "intent" in planned and plan["totals"]["run"] == len(planned)

    run = client.post("/api/v1/regeneration", json=body)
    assert run.status_code == 202, run.text
    run_id = run.json()["_id"]
    assert {j["node_id"] for j in _live(db)} == planned
    got = client.get("/api/v1/regeneration/%s" % run_id).json()
    assert got["status"] == "RUNNING" and got["progress"]["total"] == len(planned)
    listed = client.get("/api/v1/regeneration/runs?account_id=%s" % acct).json()["runs"]
    assert listed[0]["_id"] == run_id

    cancelled = client.post("/api/v1/regeneration/%s/cancel" % run_id).json()
    assert cancelled["cancelled"] == len(planned) and _live(db) == []


def test_a_run_by_account_name_and_the_bad_requests(env):
    client, db, acct = env
    _data(db, acct, "firmographics")
    ok = client.post("/api/v1/regeneration/preview", json={"accounts": ["Acme"]})
    assert ok.status_code == 200 and ok.json()["accounts"][0]["account_id"] == acct
    assert client.post("/api/v1/regeneration/preview", json={}).status_code == 400
    assert client.post("/api/v1/regeneration/preview",
                       json={"accounts": ["Nobody Inc"]}).status_code == 400
    assert client.post("/api/v1/regeneration/preview",
                       json={"accounts": "all", "features": ["nope"]}).status_code == 400


def test_queue_pause_and_resume(env):
    client, _db, _acct = env
    assert client.get("/api/v1/regeneration/queue").json()["paused"] is False
    paused = client.post("/api/v1/regeneration/queue/pause",
                         json={"reason": "testing"}).json()
    assert paused["paused"] is True and paused["reason"] == "testing"
    assert client.post("/api/v1/regeneration/queue/resume").json()["paused"] is False


def test_account_pipeline_groups_every_section_with_reasons(env):
    client, db, acct = env
    _data(db, acct, "firmographics")
    body = client.get("/api/v1/accounts/%s/pipeline" % acct).json()
    assert sum(body["counts"].values()) == len(DEFAULT.order)
    never = body["groups"]["NEVER_RUN"]
    assert never and never[0]["reasons"][0]["category"] == "never_run"
    assert body["queue"]["paused"] is False and body["runs"] == []

    summary = client.get("/api/v1/regeneration/accounts-summary").json()
    row = next(a for a in summary["accounts"] if a["account_id"] == acct)
    assert row["counts"]["NEVER_RUN"] == len(DEFAULT.order) and row["needs_run"] > 0


def test_index_rebuild_preview_names_only_index_sections(env):
    client, db, acct = env
    _data(db, acct, "firmographics", "compliance_filings")
    plan = client.post("/api/v1/indexes/rebuild/preview",
                       json={"accounts": [acct], "indexes": ["executive_dashboard"]}).json()
    requested = plan["requested_nodes"]
    assert requested == ["idx_executive_dashboard"]


def test_preview_reports_sections_whose_files_are_missing_on_the_server(env):
    client, db, acct = env
    _data(db, acct, "firmographics", "intent_score", "intent_topics")
    db.files_present["yes"] = False
    plan = client.post("/api/v1/regeneration/preview",
                       json={"accounts": [acct], "features": ["intent_demand_signals"]}).json()
    intent = next(i for i in plan["accounts"][0]["items"] if i["node_id"] == "intent")
    assert intent["action"] == "cannot_run" and intent["missing_files"]
    body = client.get("/api/v1/accounts/%s/pipeline" % acct).json()
    assert any(n["node_id"] == "intent" for n in body["groups"]["FILES_MISSING"])
