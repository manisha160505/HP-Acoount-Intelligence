"""How far back data is used (client, 6 Oct): signals 12 months, filings 24.

Run: python -m pytest tests/test_time_windows.py -v
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import time_windows as tw

AS_OF = date(2026, 10, 6)


def test_the_windows_are_12_and_24_months():
    assert tw.SIGNAL_WINDOW_DAYS == 365 and tw.FILINGS_WINDOW_DAYS == 730


def test_dates_are_read_in_the_vendor_forms():
    assert tw.parse_date("2026-09-01") == date(2026, 9, 1)
    assert tw.parse_date("2026-09-01T10:00:00Z") == date(2026, 9, 1)
    assert tw.parse_date("15/08/2026") == date(2026, 8, 15)
    assert tw.parse_date("") is None and tw.parse_date("soon") is None


def test_news_keeps_the_last_12_months_only():
    rows = [{"event_date": "2026-09-30", "h": "new"},
            {"event_date": "2025-10-06", "h": "edge"},            # exactly 365 days
            {"event_date": "2025-10-05", "h": "too old"},
            {"event_date": "", "h": "undated"},
            {"event_date": "2026-12-01", "h": "future"}]
    assert [r["h"] for r in tw.recent_news(rows, AS_OF)] == ["new", "edge"]


def test_news_date_falls_back_like_the_live_signals_gate():
    assert tw.news_date({"event_date": "", "effective_date": "2026-05-01"}) == date(2026, 5, 1)
    assert tw.news_date({"found_at": "2026-04-01T08:00:00"}) == date(2026, 4, 1)


def test_detections_use_last_seen_then_first_seen():
    rows = [{"last_seen_at": "2026-09-01", "first_seen_at": "2020-01-01", "id": "a"},
            {"last_seen_at": "", "first_seen_at": "2026-02-01", "id": "b"},
            {"last_seen_at": "2024-01-01", "id": "c"}]
    assert [r["id"] for r in tw.recent_detections(rows, AS_OF)] == ["a", "b"]


def test_catalyst_evidence_older_than_24_months_is_out(monkeypatch):
    from app.services.dashboard import priorities
    monkeypatch.setattr(tw, "today", lambda: AS_OF)
    assert priorities._within_filings_window({"period": "2025-03-31"})
    assert not priorities._within_filings_window({"period": "2023-03-31"})
    assert priorities._within_filings_window({"period": ""})       # no period: kept
