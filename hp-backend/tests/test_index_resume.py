"""An interrupted index build resumes; it is never thrown away by accident.

29 Sep: Westpac's Strategy Chat index stopped (quota) after all 166 of its
documents had been indexed but before `finish_build`. Two gaps showed:

  * the embedding model was only recorded at the finish, so the resume read
    "no embedding" as the old OpenAI one and would have dropped all 166
    documents for a full rebuild;
  * a resume with nothing left to extract returned "unchanged" without
    finishing, so the index would have stayed BUILDING - not queryable.

Run: python -m pytest tests/test_index_resume.py -v
"""

import asyncio
from types import SimpleNamespace

import pytest

from app.config.settings import settings
from app.services.retrieval import client, index_state, ingest, registry
from regen_fakes import FakeDb


@pytest.fixture
def env(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(index_state, "get_db", lambda: db)
    monkeypatch.setattr(ingest, "get_db", lambda: db)
    monkeypatch.setattr(registry, "preconditions", lambda *_a: (True, None))
    docs = [SimpleNamespace(doc_id="d%d" % i, fingerprint="f%d" % i, unit_key="u%d" % i,
                            text="t", file_path="p", evidence_rows=[]) for i in range(3)]
    monkeypatch.setattr(registry, "build_documents", lambda *_a: docs)
    dropped = []
    monkeypatch.setattr(client, "drop_workspace",
                        lambda ws, **_kw: dropped.append(ws) or {})
    return db, docs, dropped


def test_a_build_records_its_embedding_when_it_starts(env):
    state = index_state.begin_build("a1", "strategy", index_state.FULL)
    assert state["status"] == index_state.BUILDING
    assert state["embedding"] == settings.embedding_identity


def test_a_resume_with_every_document_done_finishes_without_rebuilding(env):
    _db, docs, dropped = env
    index_state.begin_build("a1", "strategy", index_state.FULL)
    for d in docs:
        index_state.record_document("a1", "strategy", d.doc_id,
                                    {"fingerprint": d.fingerprint, "unit_key": d.unit_key})
    stats = asyncio.run(ingest._update_index("a1", "strategy"))
    assert stats["skipped"] and stats["unchanged"] == 3
    assert dropped == []                                  # nothing thrown away
    state = index_state.get("a1", "strategy")
    assert state["status"] == index_state.READY
    assert len(state["documents"]) == 3


def test_the_strategy_index_no_longer_reads_the_removed_message_house():
    import inspect

    from app.services.retrieval import corpus
    source = inspect.getsource(corpus.strategy_documents)
    assert "_strategy_messaging_documents(" not in source
