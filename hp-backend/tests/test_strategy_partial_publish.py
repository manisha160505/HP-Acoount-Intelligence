"""An answer that fails on a few segments is published without a retry.

Each retry resends the whole account (~300k tokens on the largest) and costs a
full generation, while the failed segments are dropped either way. So when most
of the answer held, the turn publishes what held at once; only a bigger loss
spends another attempt.

Run: python -m pytest tests/test_strategy_partial_publish.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.observability import steps
from app.services.strategy import chat


def _segments(count):
    return [{"id": "c%d" % i, "type": "FACT", "block": "paragraph",
             "depends_on": []} for i in range(1, count + 1)]


@pytest.fixture
def turn():
    return {"question": "q", "company": "Acme", "payload": "", "widget_keys": [],
            "topic": "", "mode": "advisor", "persona": None, "sections": {},
            "account_id": "a1"}


@pytest.fixture
def no_side_effects(monkeypatch):
    monkeypatch.setattr(chat, "_revalidate", lambda _t, kept: (True, [], [], kept))
    monkeypatch.setattr(chat.claim_model, "render", lambda kept: "x" * len(kept))
    monkeypatch.setattr(chat, "_published",
                        lambda _t, text, *_a, dropped=0, **_k:
                        {"answer": text, "dropped": dropped})


def _surviving(segments, failures):
    failed = {f["id"] for f in failures}
    return [s for s in segments if s["id"] not in failed]


def test_one_bad_segment_in_ten_is_dropped_and_published(turn, no_side_effects,
                                                         monkeypatch):
    monkeypatch.setattr(chat.claim_model, "surviving", _surviving)
    out = chat._publish_partial(turn, _segments(10), [{"id": "c3", "reason": "r"}],
                                [], steps.StepTimer())
    assert out == {"answer": "x" * 9, "dropped": 1}


def test_losing_more_than_a_quarter_spends_a_retry(turn, no_side_effects,
                                                   monkeypatch):
    monkeypatch.setattr(chat.claim_model, "surviving", _surviving)
    failures = [{"id": "c%d" % i, "reason": "r"} for i in (1, 2, 3)]
    assert chat._publish_partial(turn, _segments(10), failures, [],
                                 steps.StepTimer()) is None


def test_nothing_substantive_left_spends_a_retry(turn, no_side_effects,
                                                 monkeypatch):
    monkeypatch.setattr(chat.claim_model, "surviving", lambda *_: [])
    assert chat._publish_partial(turn, _segments(10), [{"id": "c1", "reason": "r"}],
                                 [], steps.StepTimer()) is None


def test_what_is_left_must_still_pass_the_gate(turn, no_side_effects, monkeypatch):
    monkeypatch.setattr(chat.claim_model, "surviving", _surviving)
    monkeypatch.setattr(chat, "_revalidate",
                        lambda _t, kept: (False, [{"id": "c2"}], [], kept))
    assert chat._publish_partial(turn, _segments(10), [{"id": "c3", "reason": "r"}],
                                 [], steps.StepTimer()) is None
