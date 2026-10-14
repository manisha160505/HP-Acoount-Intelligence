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
