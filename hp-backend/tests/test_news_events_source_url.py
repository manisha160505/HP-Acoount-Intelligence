"""A news_events signal links to the article the client verified (14 Oct sheet).

Run: python -m pytest tests/test_news_events_source_url.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import recent_news_signals as rns


def _url(source_url):
    row = {"summary": "Accenture launches Trusted Wealth Ops", "found_at": "2026-09-14",
           "category": "launches", "source_url": source_url}
    return rns._normalize_signals([], [row])[0]["source_url"]


def test_a_filled_source_url_becomes_the_signal_link():
    link = "https://newsroom.accenture.com/blogs/2026/accenture-launches-trusted-wealth-ops"
    assert _url(link) == link


def test_a_blank_source_url_stays_unlinked():
    assert _url("") == ""
    assert _url(None) == ""


def test_a_non_http_value_is_not_a_link():
    assert _url("N/A") == ""
    assert _url("newsroom.accenture.com/blogs") == ""


# Live Signals shows only signals with a source link (client, 15 Oct).

def _group(source_url, *supporting):
    return {"signal_id": "abc", "headline": "Accenture launches Trusted Wealth Ops",
            "source_url": source_url, "_canon": "x",
            "supporting_sources": [{"url": u} for u in (source_url, *supporting)]}


def test_an_unlinked_signal_is_dropped_with_a_reason():
    linked, rejected = rns._split_unlinked([_group("")])
    assert linked == []
    assert rejected[0]["gate_reject_reason"] == "no source link"
    assert "_canon" not in rejected[0]


def test_a_linked_signal_is_kept():
    g = _group("https://newsroom.accenture.com/a")
    assert rns._split_unlinked([g]) == ([g], [])


def test_a_signal_is_kept_when_a_merged_article_links():
    g = _group("", "https://www.reuters.com/a")
    assert rns._split_unlinked([g]) == ([g], [])


def test_a_non_http_link_does_not_count():
    linked, rejected = rns._split_unlinked([_group("N/A", "www.reuters.com/a")])
    assert linked == [] and len(rejected) == 1
