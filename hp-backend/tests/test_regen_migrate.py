"""Adopting an existing database: nothing lost, nothing regenerated, nothing twice.

Runs on the in-memory fake, and on a real mongod when REGEN_TEST_MONGO_URI is set.

Run: python -m pytest tests/test_regen_migrate.py -v
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.services.regen import manifest, migrate, state, store as widget_store
from app.services.regen.engine import Engine
from app.services.regen.graph import DEFAULT
from regen_fakes import FakeDb


@pytest.fixture(params=["fake", "mongo"])
def db(request):
    if request.param == "fake":
        yield FakeDb()
        return
    uri = os.getenv("REGEN_TEST_MONGO_URI")
    if not uri:
        pytest.skip("set REGEN_TEST_MONGO_URI to also run against a real mongod")
    from pymongo import MongoClient
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    name = "regen_test_%s" % uuid.uuid4().hex[:10]
    try:
        yield client[name]
    finally:
        client.drop_database(name)
        client.close()


def _account(db):
    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})
    return account_id


def _widget(db, account_id, key, data, when=None, **extra):
    db["account_widgets"].insert_one({
        "account_id": account_id, "widget_key": key, "status": "available",
        "data": data, "source_datasets": ["firmographics"],
        "updated_at": when or datetime.now(UTC) - timedelta(days=1), **extra})


def _status(db, account_id, nid):
    engine = Engine(db=db, versions=manifest.StaticVersions())
    return engine.status(account_id)["nodes"][nid]


def test_existing_widgets_are_adopted_unchanged_and_read_as_unverified(db):
    acct = _account(db)
    _widget(db, acct, "stakeholder_contacts_grid", {"contacts": [1, 2]})
    _widget(db, acct, "stakeholder_influence_map", {"groups": ["IT"]})
    report = migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    assert report["adopted"] == 1
    served = widget_store.committed(db, acct, "stakeholder_contacts_grid")
    assert served["data"] == {"contacts": [1, 2]}
    status = _status(db, acct, "stakeholder_roster")
    assert status["lifecycle"] == state.STALE
    assert "legacy" in status["reasons"][0]
    # A node with nothing stored stays never-generated.
    assert _status(db, acct, "intent")["lifecycle"] == state.NEVER_GENERATED


def test_dry_run_writes_nothing_and_a_second_run_adopts_nothing(db):
    acct = _account(db)
    _widget(db, acct, "intent_topics_table", {"topics": []})
    assert migrate.run(db, dry_run=True, file_path_for=lambda _p: None)["adopted"] == 1
    assert db[state.COLLECTION].count_documents({}) == 0
    assert migrate.run(db, dry_run=False, file_path_for=lambda _p: None)["adopted"] == 1
    assert migrate.run(db, dry_run=False, file_path_for=lambda _p: None)["adopted"] == 0


def test_duplicate_widget_rows_stop_the_migration(db):
    acct = _account(db)
    _widget(db, acct, "intent_topics_table", {"v": 1})
    _widget(db, acct, "intent_topics_table", {"v": 2})
    report = migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    assert report["duplicates"] and db[state.COLLECTION].count_documents({}) == 0


def test_content_hashes_are_backfilled_only_where_the_file_is_here(db, tmp_path):
    acct = _account(db)
    here = tmp_path / "f.csv"
    here.write_text("a\n1\n")
    db["account_data_files"].insert_one({"account_id": acct, "dataset_key": "firmographics",
                                         "status": "active", "file_path": str(here)})
    db["account_data_files"].insert_one({"account_id": acct, "dataset_key": "webstack",
                                         "status": "active", "file_path": "elsewhere.csv"})
    report = migrate.run(db, dry_run=False,
                         file_path_for=lambda p: p if os.path.exists(p) else None)
    assert report["hashed"] == 1 and report["unhashed_missing"] == 1
    row = db["account_data_files"].find_one({"dataset_key": "firmographics"})
    assert len(row["content_sha256"]) == 64


def test_roll_forward_adopts_rows_the_old_release_wrote_after_a_rollback(db):
    acct = _account(db)
    _widget(db, acct, "intent_topics_table", {"v": "before"})
    migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    # Rolled back: the old release rewrites the row directly (no `rev`).
    db["account_widgets"].update_one(
        {"account_id": acct, "widget_key": "intent_topics_table"},
        {"$set": {"data": {"v": "during rollback"},
                  "updated_at": datetime.now(UTC) + timedelta(minutes=5)}})
    report = migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    assert report["rolled_forward"] == 1
    assert widget_store.committed(db, acct, "intent_topics_table")["data"] == {
        "v": "during rollback"}


def test_mirror_rows_are_not_mistaken_for_rollback_writes(db):
    acct = _account(db)
    _widget(db, acct, "intent_topics_table", {"v": 1}, rev=3,
            when=datetime.now(UTC) + timedelta(minutes=5))
    migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    assert migrate.run(db, dry_run=False, file_path_for=lambda _p: None)["rolled_forward"] == 0


def test_a_built_index_is_adopted_and_a_failed_one_is_not(db):
    acct = _account(db)
    db["retrieval_index_state"].insert_one({
        "account_id": acct, "index": "strategy", "status": "READY", "version": 4,
        "documents": {"d1": {"fingerprint": "f1"}},
        "last_built_at": datetime.now(UTC)})
    db["retrieval_index_state"].insert_one({
        "account_id": acct, "index": "content_messaging", "status": "FAILED"})
    report = migrate.run(db, dry_run=False, file_path_for=lambda _p: None)
    assert report["indexes_adopted"] == 1
    states = state.load_account(db, acct)
    assert states["idx_strategy"]["current"]["index"]["index_version"] == 4
    assert "idx_content_messaging" not in states


def test_graph_is_the_default_one():
    assert migrate.INDEX_OF_NODE.keys() == {n for n in DEFAULT.nodes
                                            if DEFAULT[n].kind == "index"}
