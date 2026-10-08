"""Opportunity Map with no tech stack and no intent draws on Live Signals' news.

Client, 8 Oct: MINISTRY OF NATIONAL DEFENSE - KR had an empty Opportunity Map
because it has no Technographics and no Bombora intent - "use relevant data from
Live Signals to populate the Opportunity Map". The same raw news goes through
Live Signals' own gate and dedupe, and every surviving item reaches the model
with its evidence sentence; an account that has a tech stack keeps the ten raw
headlines it always had.

These tests stop at the model call and read the prompt it would have been sent.

Run: python -m pytest tests/test_opportunity_news_only.py -v
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import solution_narrative_opportunity_map as opp
from regen_fakes import FakeDb


class _Asked(Exception):
    """Raised by the fake model so the test ends where the prompt is built."""


def _days_ago(n):
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


NEWS = [
    {"event_headline": "Ministry opens a new cyber command centre", "event_date": _days_ago(30),
     "news_announcements": "The centre will train 2,000 staff on secure systems.",
     "event_url": "https://example.org/a"},
    {"event_headline": "Ministry signs defence logistics digitisation deal",
     "event_date": _days_ago(90), "event_url": "https://example.org/b"},
    # Older than twelve months: Live Signals' gate drops it.
    {"event_headline": "Ancient procurement story", "event_date": _days_ago(500)},
]


@pytest.fixture
def run(monkeypatch):
    def go(datasets):
        db = FakeDb()
        account_id = str(ObjectId())
        db["accounts"].insert_one({"_id": ObjectId(account_id),
                                   "name": "MINISTRY OF NATIONAL DEFENSE - KR"})
        monkeypatch.setattr(opp, "get_db", lambda: db)
        monkeypatch.setattr(opp, "_read_dataset_records",
                            lambda _a, key: list(datasets.get(key, [])))
        monkeypatch.setattr(opp, "read_dataset_rows", lambda *_a, **_k: [])
        monkeypatch.setattr(opp, "account_domain", lambda _a: "mnd.go.kr")
        monkeypatch.setattr(opp.widget_store, "get", lambda *_a, **_k: None)
        asked = {}

        def model(system_prompt, user_prompt):
            asked["prompt"] = system_prompt + "\n" + user_prompt
            raise _Asked

        monkeypatch.setattr(opp, "generate_gpt4o_json_completion", model)
        with pytest.raises(_Asked):
            opp.generate_opportunity_map_plays_with_gpt4o(account_id)
        return asked["prompt"]
    return go


def test_no_stack_and_no_intent_uses_gated_news_with_evidence(run):
    prompt = run({"firmographics": [{"Business Description": "Defence ministry."}],
                  "google_news": NEWS})
    assert "Ministry opens a new cyber command centre" in prompt
    assert "The centre will train 2,000 staff on secure systems." in prompt
    assert "Ministry signs defence logistics digitisation deal" in prompt
    assert "Ancient procurement story" not in prompt


def test_an_account_with_a_stack_keeps_raw_headlines_only(run):
    prompt = run({"firmographics": [{"Business Description": "Defence ministry."}],
                  "technographics": [{"Full Tech Stack": "Microsoft 365, Zoom"}],
                  "google_news": NEWS[:2]})
    assert "Ministry opens a new cyber command centre" in prompt
    assert "The centre will train 2,000 staff on secure systems." not in prompt
