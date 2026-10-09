"""The 9 Oct English release applied without rebuilding News (regen/english_release.py).

Run: python -m pytest tests/test_english_release.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.regen import english_release as er

FEED = {"signals": [
    {"headline": "ソフトバンク、AI投資を拡大", "evidence_sentence": "同社は2026年に300億円を投資する。",
     "source_publisher": "日本経済新聞", "score": 82,
     "supporting_sources": [{"publisher": "日経", "url": "https://x"}],
     "merged_headlines": ["ソフトバンク、AI投資を拡大", "SoftBank expands AI"]},
    {"headline": "SoftBank opens a lab", "source_publisher": "Reuters", "score": 60},
]}
ENGLISH = {
    "headline": {"ソフトバンク、AI投資を拡大": "SoftBank expands AI investment"},
    "sentence": {"同社は2026年に300億円を投資する。": "The company will invest 30 billion yen (300 oku) in 2026."},
    "publisher": {"日本経済新聞": "Nikkei", "日経": "Nikkei"},
}


def test_only_non_english_news_text_is_collected():
    texts = er.news_texts(FEED)
    assert texts["headline"] == ["ソフトバンク、AI投資を拡大", "ソフトバンク、AI投資を拡大"]
    assert texts["publisher"] == ["日本経済新聞", "日経"]
    assert "SoftBank opens a lab" not in str(texts) and "Reuters" not in str(texts)


def test_news_is_translated_in_place_with_the_original_kept():
    import copy
    data = copy.deepcopy(FEED)
    changed = er.translate_news(data, ENGLISH)
    first = data["signals"][0]
    assert first["headline"] == "SoftBank expands AI investment"
    assert first["headline_original"] == "ソフトバンク、AI投資を拡大"
    assert first["source_publisher"] == "Nikkei" and first["publisher_original"] == "日本経済新聞"
    assert first["supporting_sources"][0]["publisher"] == "Nikkei"
    assert first["merged_headlines"] == ["SoftBank expands AI investment", "SoftBank expands AI"]
    assert first["merged_headlines_original"][0] == "ソフトバンク、AI投資を拡大"
    # Scores and English stories are untouched.
    assert first["score"] == 82 and data["signals"][1] == FEED["signals"][1]
    assert changed == 5   # headline, evidence, publisher, a source, a merged headline


def test_translating_twice_changes_nothing_more():
    import copy
    data = copy.deepcopy(FEED)
    er.translate_news(data, ENGLISH)
    once = copy.deepcopy(data)
    assert er.translate_news(data, ENGLISH) == 0 and data == once


def test_text_with_no_acceptable_translation_stays_as_received():
    import copy
    data = copy.deepcopy(FEED)
    er.translate_news(data, {"headline": {}})
    assert data["signals"][0]["headline"] == "ソフトバンク、AI投資を拡大"
    assert "headline_original" not in data["signals"][0]


def test_foreign_text_and_government_subsidiaries_are_detected():
    assert er.has_foreign_text([{"ceo": {"name": "孫 正義"}}])
    assert not er.has_foreign_text([{"ceo": {"name": "Masayoshi Son"}}, {}])
    assert er.has_government_subsidiary([{"subsidiaries": ["japan the government of japan"]}])
    assert er.has_government_subsidiary([{"summary": {"subsidiaries": ["Queensland Government"]}}])
    assert not er.has_government_subsidiary([{"subsidiaries": ["commonwealth superannuation"]}])
    # The word elsewhere on the card is not a subsidiary.
    assert not er.has_government_subsidiary([{"description": "works with the government"}])
