"""Live Signals keeps the batches it finished when a run stops part-way.

A section that fails is never re-queued (29 Sep); it is fixed and submitted
again by hand. For Live Signals that re-run used to score every batch again,
because the result was only saved once all of them were done. Each batch is now
saved as it comes back, and a re-run scores only the batches still missing.

Run: python -m pytest tests/test_live_signals_progress.py -v
"""

from datetime import UTC, datetime

import pytest

from app.services.extractors import recent_news_signals as rns
from app.services.regen import context as run_context
from regen_fakes import FakeDb


@pytest.fixture(autouse=True)
def in_a_run():
    """Progress is saved only inside a regeneration run."""
    with run_context.active(run_context.RunContext(account_id="a1", node_id="news")):
        yield


def test_a_rerun_scores_only_the_batches_that_did_not_finish(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(rns, "get_db", lambda: db)
    signals = [{"signal_id": "s%d" % i, "title": "t%d" % i} for i in range(6)]
    calls, fail_last = [], {"on": True}

    def score_one(chunk, *_a):
        calls.append([s["signal_id"] for s in chunk])
        if fail_last["on"] and chunk[0]["signal_id"] == "s4":
            return []                              # e.g. the quota ran out here
        return [{"signal_id": s["signal_id"]} for s in chunk]

    monkeypatch.setattr(rns, "_score_one_batch", score_one)
    now = datetime(2026, 9, 29, tzinfo=UTC)

    first = rns._score_batches(signals, "Acme", "ctx", now, batch_size=2)
    assert len(calls) == 4                         # 3 batches + 1 retry of s4,s5

    calls.clear()
    fail_last["on"] = False
    second = rns._score_batches(signals, "Acme", "ctx", now, batch_size=2)
    assert calls == [["s4", "s5"]]                 # only what was missing
    assert len(second) == 6 and len(first) == 4


def test_a_changed_batch_is_scored_again(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(rns, "get_db", lambda: db)
    calls = []
    monkeypatch.setattr(rns, "_score_one_batch", lambda chunk, *_a: calls.append(1) or [
        {"signal_id": s["signal_id"]} for s in chunk])
    now = datetime(2026, 9, 29, tzinfo=UTC)
    rns._score_batches([{"signal_id": "a", "title": "x"}], "Acme", "ctx", now)
    rns._score_batches([{"signal_id": "a", "title": "changed"}], "Acme", "ctx", now)
    rns._score_batches([{"signal_id": "a", "title": "changed"}], "Acme", "new ctx", now)
    assert len(calls) == 3


def test_outside_a_run_nothing_is_saved(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(rns, "get_db", lambda: db)
    monkeypatch.setattr(rns, "_score_one_batch", lambda chunk, *_a: [
        {"signal_id": s["signal_id"]} for s in chunk])
    token = run_context._current.set(None)
    try:
        rns._score_batches([{"signal_id": "a"}], "Acme", "ctx",
                           datetime(2026, 9, 29, tzinfo=UTC))
    finally:
        run_context._current.reset(token)
    assert db[rns.BATCH_PROGRESS].count_documents({}) == 0
