"""The index-node runner: what an index build is reported to the engine as.

The build itself (LightRAG) is stubbed; what is pinned here is the mapping the
engine relies on - blocked stays blocked, damaged documents make the build
degraded, and an unchanged corpus reports an unchanged output.

Run: python -m pytest tests/test_regen_index_runner.py -v
"""

import pytest

from app.services.regen import manifest, producers
from app.services.retrieval import index_state, ingest


@pytest.fixture
def stub(monkeypatch):
    calls = {"state": {"version": 3, "documents": {"d1": {"fingerprint": "f1"}}},
             "stats": {"damaged": [], "skipped": False}, "raise": None}

    async def update_index(account_id, index, full=False, progress=None):
        calls["args"] = (account_id, index, full)
        if calls["raise"]:
            raise calls["raise"]
        return calls["stats"]

    monkeypatch.setattr(ingest, "update_index", update_index)
    monkeypatch.setattr(index_state, "get", lambda _a, _i: calls["state"])
    return calls


def _hash(result):
    return manifest.output_hash({}, {"corpus": result["corpus"],
                                     "index_version": result["index_version"]})


def test_a_complete_build_reports_its_corpus_and_version(stub):
    result = producers.index_executive_dashboard("acct", full=True)
    assert stub["args"] == ("acct", "executive_dashboard", True)
    assert result["quality"] == "complete"
    assert result["corpus"] == {"d1": "f1"} and result["index_version"] == 3


def test_damaged_documents_make_the_build_degraded(stub):
    stub["stats"] = {"damaged": ["d1"]}
    assert producers.index_content_messaging("acct")["quality"] == "degraded"


def test_unmet_preconditions_are_blocked_not_failed(stub):
    stub["raise"] = ingest.BuildBlocked("waiting on exec_summary_card")
    result = producers.index_executive_dashboard("acct")
    assert result["quality"] == "blocked" and result["corpus"] == {}


def test_a_concurrent_build_is_a_retryable_failure(stub):
    stub["raise"] = ingest.BuildBusy("already building")
    with pytest.raises(ingest.BuildBusy):
        producers.index_executive_dashboard("acct")


def test_an_unchanged_corpus_reports_an_unchanged_output(stub):
    first = _hash(producers.index_executive_dashboard("acct"))
    stub["stats"] = {"damaged": [], "skipped": True}
    assert _hash(producers.index_executive_dashboard("acct")) == first
    stub["state"] = {"version": 4, "documents": {"d1": {"fingerprint": "f1"}}}
    assert _hash(producers.index_executive_dashboard("acct")) != first   # a rebuild moves it
