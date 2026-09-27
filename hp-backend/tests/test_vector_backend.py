"""Tests for the switchable vector backend and the bounded query-handle cache.

What is pinned:
  * VECTOR_STORAGE picks the store, and "nano" converts the threshold so the
    same results pass as on Atlas (Atlas scores cosine as (1 + cos) / 2).
  * drop_workspace removes a workspace's NanoVectorDB files - and only its own.
  * The query-handle cache is bounded, evicts least recently used first, and
    never finalises a handle that a question is still using.

No Mongo, no LightRAG handles: storage is a fake and handles are stubs.

Run: python -m pytest tests/test_vector_backend.py -v
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import client

# ---------------------------------------------------------------------------
# Backend choice and threshold
# ---------------------------------------------------------------------------

def test_atlas_keeps_the_shared_vector_storage(monkeypatch):
    monkeypatch.setattr(client.settings, "VECTOR_STORAGE", "atlas")
    assert client._vector_storage_config() == {"vector_storage": "HpSharedVectorStorage"}


def test_nano_converts_the_atlas_threshold_to_raw_cosine(monkeypatch):
    """0.2 on Atlas's (1 + cos) / 2 scale is cos >= -0.6."""
    monkeypatch.setattr(client.settings, "VECTOR_STORAGE", "nano")
    monkeypatch.delenv("COSINE_THRESHOLD", raising=False)
    config = client._vector_storage_config()
    assert config["vector_storage"] == "NanoVectorDBStorage"
    assert config["cosine_better_than_threshold"] == pytest.approx(-0.6)


def test_nano_threshold_follows_an_overridden_atlas_threshold(monkeypatch):
    monkeypatch.setattr(client.settings, "VECTOR_STORAGE", "nano")
    monkeypatch.setenv("COSINE_THRESHOLD", "0.5")
    assert client._vector_storage_config()["cosine_better_than_threshold"] == pytest.approx(0.0)


@pytest.mark.parametrize("value", ["", "qdrant", "mongo"])
def test_an_unknown_backend_is_refused(monkeypatch, value):
    monkeypatch.setattr(client.settings, "VECTOR_STORAGE", value)
    with pytest.raises(client.RetrievalConfigError):
        client.vector_backend()


def test_backend_name_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(client.settings, "VECTOR_STORAGE", " Nano ")
    assert client.vector_backend() == "nano"


def test_relative_storage_dir_is_anchored_at_the_backend_not_the_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(client.settings, "RAG_STORAGE_DIR", "rag_storage")
    monkeypatch.chdir(tmp_path)
    path = client.rag_storage_dir()
    assert Path(path).is_absolute()
    assert not path.startswith(str(tmp_path))
    assert path.endswith(os.path.join("hp-backend", "rag_storage"))


# ---------------------------------------------------------------------------
# drop_workspace
# ---------------------------------------------------------------------------

class _Result:
    deleted_count = 0


class _Collection:
    def list_search_indexes(self):
        raise RuntimeError("plain MongoDB has no search indexes")

    def drop(self):
        pass

    def delete_many(self, query):
        return _Result()


class _Db:
    def list_collection_names(self):
        return []

    def __getitem__(self, name):
        return _Collection()


def test_drop_workspace_removes_only_its_own_vector_files(monkeypatch, tmp_path):
    monkeypatch.setattr(client.settings, "RAG_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr("app.database.mongodb.get_db", _Db)
    monkeypatch.setattr(client, "forget_query_handle", lambda _: None)

    for workspace in ("acct_a1_strategy", "acct_a1_strategy_extra", "acct_b2_strategy"):
        os.makedirs(tmp_path / workspace)
        for namespace in ("entities", "relationships", "chunks"):
            (tmp_path / workspace / ("vdb_%s.json" % namespace)).write_text("{}")

    dropped = client.drop_workspace("acct_a1_strategy")

    assert dropped["vector_files"] == 3
    assert not (tmp_path / "acct_a1_strategy").exists()
    assert (tmp_path / "acct_a1_strategy_extra").exists()
    assert (tmp_path / "acct_b2_strategy").exists()


def test_drop_workspace_without_vector_files_is_fine(monkeypatch, tmp_path):
    monkeypatch.setattr(client.settings, "RAG_STORAGE_DIR", str(tmp_path))
    monkeypatch.setattr("app.database.mongodb.get_db", _Db)
    monkeypatch.setattr(client, "forget_query_handle", lambda _: None)
    assert client.drop_workspace("acct_a1_strategy")["vector_files"] == 0


# ---------------------------------------------------------------------------
# The bounded query-handle cache
# ---------------------------------------------------------------------------

class StubHandle:
    def __init__(self, workspace):
        self.workspace = workspace
        self.finalised = 0

    async def finalize_storages(self):
        self.finalised += 1


@pytest.fixture
def cache(monkeypatch):
    built = {}

    async def build_rag(account_id, index, for_query=False):
        handle = StubHandle(client.workspace_name(account_id, index))
        built.setdefault(handle.workspace, []).append(handle)
        return handle

    monkeypatch.setattr(client, "build_rag", build_rag)
    monkeypatch.setattr(client.settings, "QUERY_HANDLE_CACHE_SIZE", 2)
    monkeypatch.setattr(client, "_query_handles", client.collections.OrderedDict())
    monkeypatch.setattr(client, "_handle_users", {})
    monkeypatch.setattr(client, "_retiring", {})
    return built


def _ask(account):
    """Open and release, as one answered question does."""
    async def go():
        handle = await client.query_handle(account, "strategy")
        await client.release_query_handle(handle)
        return handle
    return asyncio.run(go())


def test_a_handle_is_reused_while_cached(cache):
    assert _ask("a1") is _ask("a1")
    assert len(cache["acct_a1_strategy"]) == 1


def test_the_least_recently_used_idle_handle_is_evicted_and_finalised(cache):
    a = _ask("a1")
    _ask("b2")
    _ask("a1")            # a1 is now the most recent
    _ask("c3")            # over the limit of 2: b2 goes, a1 stays

    assert list(client._query_handles) == ["acct_a1_strategy", "acct_c3_strategy"]
    assert cache["acct_b2_strategy"][0].finalised == 1
    assert a.finalised == 0


def test_a_handle_in_use_is_not_finalised_until_released(cache):
    async def go():
        busy = await client.query_handle("a1", "strategy")      # question in flight
        for account in ("b2", "c3"):                             # evicts a1
            await client.release_query_handle(
                await client.query_handle(account, "strategy"))
        assert "acct_a1_strategy" not in client._query_handles
        assert busy.finalised == 0, "finalised under a running question"
        await client.release_query_handle(busy)
        assert busy.finalised == 1
    asyncio.run(go())


def test_releasing_an_unknown_handle_is_harmless(cache):
    asyncio.run(client.release_query_handle(StubHandle("nobody")))
