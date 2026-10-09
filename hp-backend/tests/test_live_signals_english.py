"""Live Signals in English (client, 9 Oct), and Japanese stories kept apart.

Run: python -m pytest tests/test_live_signals_english.py -v
"""

import json
import os
import re
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import recent_news_signals as rns
from app.services.hp import translate
from regen_fakes import FakeDb

JP_A = "アドバンテスト、千歳事業所を開設"
JP_B = "トヨタ、新型EVの生産を開始"


def _signal(headline, evidence="", publisher="", day="2026-09-01"):
    return {"headline": headline, "raw_headline": headline, "evidence_sentence": evidence,
            "event_date": day, "publication_date": "",
            "_event_dt": datetime.fromisoformat(day).replace(tzinfo=UTC),
            "source_url": "", "source_publisher": publisher, "dataset": "google_news"}


@pytest.fixture
def model(monkeypatch):
    answers = {JP_A: "Advantest opens Chitose office",
               JP_B: "Toyota starts production of new EV",
               "日本経済新聞": "Nikkei"}

    def fake(_system, user):
        items = json.loads(user)["items"]
        return {"items": [{"i": i["i"], "english": answers.get(i["text"], "")} for i in items]}

    monkeypatch.setattr(translate, "generate_gpt4o_json_completion", fake)


def test_the_dedup_key_is_unchanged_for_ascii_headlines():
    """Signal ids are hashes of this key, so English accounts must not move."""
    old = lambda t: re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())  # noqa: E731
    for headline in ("Advantest Opens Chitose Office | 2026", "M&A: Toyota buys X-Corp.", ""):
        assert rns._canonical(headline) == old(headline)


def test_two_different_japanese_stories_are_not_merged():
    """They used to reduce to blanks and digits and collapse into one card."""
    groups = rns._dedupe([_signal(JP_A), _signal(JP_B, day="2026-09-02")])
    assert len(groups) == 2
    assert groups[0]["signal_id"] != groups[1]["signal_id"]


def test_signals_are_shown_in_english_with_the_original_kept(model):
    signals = [_signal(JP_A, publisher="日本経済新聞"), _signal("Advantest wins award")]
    assert rns._translate_signals(signals, FakeDb()) == 1
    assert signals[0]["headline"] == "Advantest opens Chitose office"
    assert signals[0]["headline_original"] == JP_A
    assert signals[0]["source_publisher"] == "Nikkei"
    assert signals[0]["publisher_original"] == "日本経済新聞"
    assert "headline_original" not in signals[1], "English signals are untouched"


def test_an_untranslatable_signal_keeps_its_text(monkeypatch):
    monkeypatch.setattr(translate, "generate_gpt4o_json_completion", lambda *_a: None)
    signals = [_signal(JP_A)]
    assert rns._translate_signals(signals, FakeDb()) == 0
    assert signals[0]["headline"] == JP_A and "headline_original" not in signals[0]
