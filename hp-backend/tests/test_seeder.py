"""Startup seeding of the Astra pilot files (core/seeder.py).

The pilot CSVs are seeded once, into a database that has never held that
dataset for Astra. Startup must never touch a file record someone has managed
since: on 21 Oct the #106 deploy pointed Astra's active contacts record back
at the 23 pilot contacts, over the client's 17, and marked 13 sections stale.

Run: python -m pytest tests/test_seeder.py -v
"""

import os
import sys

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from app.core import seeder
from regen_fakes import FakeDb


@pytest.fixture
def env(monkeypatch, tmp_path):
    """A backend root with two pilot files, an empty database, cwd at the root."""
    seed = tmp_path / "seed_data" / "astra"
    seed.mkdir(parents=True)
    (seed / "prospect_contacts.csv").write_text("name\npilot one\npilot two\n", encoding="utf-8")
    (seed / "firmographics.csv").write_text("company\nAstra\n", encoding="utf-8")
    db = FakeDb()
    monkeypatch.setattr(seeder, "get_db", lambda: db)
    monkeypatch.setattr(seeder, "_find_backend_root", lambda: str(tmp_path))
    monkeypatch.chdir(tmp_path)
    return db, tmp_path


def _files(db, key):
    return list(db["account_data_files"].find({"dataset_key": key}))


def test_a_fresh_database_gets_the_pilot_files(env):
    db, root = env
    seeder.seed_database_if_empty()
    astra = db["accounts"].find_one({"name": "PT Astra International Tbk"})
    assert astra
    rows = _files(db, "prospect_contacts")
    assert len(rows) == 1 and rows[0]["status"] == "active"
    assert rows[0]["row_count"] == 2
    assert rows[0]["file_path"] == "data/accounts/%s/prospect_contacts/prospect_contacts.csv" % astra["_id"]
    assert (root / rows[0]["file_path"]).exists()
    assert len(_files(db, "firmographics")) == 1
    # Datasets with no pilot file are not invented.
    assert not _files(db, "job_openings")


def test_a_restart_changes_nothing(env):
    db, _root = env
    seeder.seed_database_if_empty()
    before = {d["_id"]: dict(d) for d in db["account_data_files"].find({})}
    seeder.seed_database_if_empty()
    after = {d["_id"]: dict(d) for d in db["account_data_files"].find({})}
    assert after == before


def _astra_with_upload(db, root, status="active"):
    """Astra as on the VM: the client's file uploaded under its own name."""
    aid = ObjectId()
    db["accounts"].insert_one({"_id": aid, "name": "Astra", "status": "active"})
    folder = root / "data" / "accounts" / str(aid) / "prospect_contacts"
    folder.mkdir(parents=True)
    (folder / "20a8399f5680_prospect_contacts.csv").write_text("name\nclient\n", encoding="utf-8")
    upload = {"_id": ObjectId(), "account_id": str(aid), "dataset_key": "prospect_contacts",
              "status": status, "stored_filename": "20a8399f5680_prospect_contacts.csv",
              "file_path": "data/accounts/%s/prospect_contacts/20a8399f5680_prospect_contacts.csv" % aid,
              "file_size": 12, "row_count": 1, "content_sha256": "20a8399f5680" + "0" * 52}
    db["account_data_files"].insert_one(dict(upload))
    return aid, upload


def test_an_uploaded_file_is_never_pointed_back_at_the_pilot_copy(env):
    db, root = env
    aid, upload = _astra_with_upload(db, root)
    seeder.seed_database_if_empty()
    rows = _files(db, "prospect_contacts")
    assert len(rows) == 1, "no pilot record added beside it"
    assert rows[0] == upload, "the record is left exactly as uploaded"
    # The pilot copy is not even written next to it.
    assert not (root / "data" / "accounts" / str(aid) / "prospect_contacts"
                / "prospect_contacts.csv").exists()
    # A dataset Astra has never held is still seeded.
    assert len(_files(db, "firmographics")) == 1


@pytest.mark.parametrize("status", ["deleted", "replaced"])
def test_a_dataset_someone_removed_does_not_come_back(env, status):
    db, root = env
    _aid, upload = _astra_with_upload(db, root, status=status)
    seeder.seed_database_if_empty()
    assert _files(db, "prospect_contacts") == [upload]
