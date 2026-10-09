"""Executive Dashboard filing figures from filings_financials.csv.

One row per filing PDF (scripts/filings_to_csv.py); the resolver picks what
the dashboard shows. These tests hold it to the client's Feature 1 rules:
latest filing first, the last verified period when the latest lacks a metric,
full years never mixed with quarters, segment / parent-only figures never
shown, another entity's figures only under its name.

Run: python -m pytest tests/test_filings_financials.py -v
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import filings_financials as ff

# The fixtures span 2023 to 2026, more than the 24-month filings window
# (client, 6 Oct) can hold at once. The tests of how a filing is chosen run
# with the window off; the window's own tests (marked) run it against a
# pinned "today" so they hold still as real time moves on.
AS_OF = date(2025, 12, 31)
_recent_filings = ff.recent_filings


@pytest.fixture(autouse=True)
def _window(request, monkeypatch):
    monkeypatch.setattr(ff.time_windows, "today", lambda: AS_OF)
    if request.node.get_closest_marker("window") is None:
        monkeypatch.setattr(ff, "recent_filings", lambda rows, _as_of=None: list(rows or []))


def _metric(name, value, **kw):
    out = {name: value, name + "_currency": "AUD", name + "_scale": "million",
           name + "_label": "Revenue", name + "_text": str(value), name + "_unit": "$m",
           name + "_page": "12", name + "_scope": "consolidated", name + "_check": "verified",
           name + "_prior": "", name + "_prior_period_end": "", name + "_history": "",
           name + "_flags": ""}
    out.update({name + k: v for k, v in kw.items()})
    return out


def _row(period_end="2025-06-30", period_type="FY", file="ar2025.pdf", **metrics):
    row = {"account": "AUSTRALIA_POST", "company": "AUSTRALIA POST", "file": file,
           "document_title": "Annual Report", "period_type": period_type,
           "period_end": period_end, "entity_match": "same",
           "filing_entity_english": "Australian Postal Corporation",
           "publication_date": period_end, "ceo_check": "not found"}
    for name in ("revenue", "net_income", "employees"):
        row.update(_metric(name, "", _check="not found"))
    for name, spec in metrics.items():
        row.update(_metric(name, **spec) if isinstance(spec, dict) else _metric(name, spec))
    return row


def test_latest_full_year_with_growth_from_its_own_comparative():
    rows = [_row(revenue={"value": 9454.4, "_prior": 9129.1,
                          "_prior_period_end": "2024-06-30",
                          "_history": "2023-06-30=8965.2"})]
    [card] = ff.reported_metrics(rows)
    assert card["metric"] == "Revenue" and card["period"] == "FY2025"
    assert card["value_text"] == "AUD 9,454.40 million"
    assert card["change_text"] == "+3.6%" and card["previous_period"] == "FY2024"
    assert "ar2025.pdf" in card["change_basis"]
    assert [s["period"] for s in card["series"]] == ["FY2023", "FY2024", "FY2025"]


def test_missing_in_latest_falls_back_to_last_verified_with_a_note():
    rows = [_row("2025-06-30", file="ar2025.pdf", revenue=100.0),
            _row("2024-06-30", file="ar2024.pdf", revenue=90.0, net_income=5.0)]
    cards = {c["metric"]: c for c in ff.reported_metrics(rows)}
    assert cards["Revenue"]["period"] == "FY2025" and not cards["Revenue"]["fallback_note"]
    assert cards["Net income"]["period"] == "FY2024"
    assert "ar2025.pdf" in cards["Net income"]["fallback_note"]


def test_growth_across_two_filings_when_no_comparative():
    rows = [_row("2025-06-30", file="ar2025.pdf", revenue=110.0),
            _row("2024-06-30", file="ar2024.pdf", revenue=100.0)]
    [card] = ff.reported_metrics(rows)
    assert card["change_text"] == "+10.0%"
    assert "ar2025.pdf vs ar2024.pdf" in card["change_basis"]


def test_scales_are_reconciled_before_comparing():
    rows = [_row("2025-12-31", revenue={"value": 11471675.0, "_scale": "thousand"}),
            _row("2024-12-31", file="ar2024.pdf", revenue=9231.0)]
    [card] = ff.reported_metrics(rows)
    assert card["change_text"] == "+24.3%"


def test_newer_quarter_is_its_own_card_compared_with_same_quarter():
    rows = [_row("2025-12-31", revenue=195669.0),
            _row("2026-06-30", "Q2", file="q2_26.pdf",
                 revenue={"value": 45901.0, "_prior": 49596.0, "_prior_period_end": "2025-06-30"}),
            _row("2026-03-31", "Q1", file="q1_26.pdf", revenue=46393.0)]
    cards = ff.reported_metrics(rows)
    assert [c["metric"] for c in cards] == ["Revenue", "Revenue (Q2)"]
    q2 = cards[1]
    assert q2["period"] == "2026-Q2" and q2["previous_period"] == "2025-Q2"
    assert "series" not in q2


def test_older_quarter_is_not_shown_beside_a_newer_full_year():
    rows = [_row("2025-12-31", revenue=100.0),
            _row("2025-06-30", "1H", file="h1.pdf", revenue=48.0)]
    assert [c["metric"] for c in ff.reported_metrics(rows)] == ["Revenue"]


def test_segment_and_parent_only_figures_are_never_used():
    rows = [_row(revenue={"value": 100.0, "_scope": "segment"}),
            _row("2024-06-30", file="b.pdf", revenue={"value": 90.0, "_scope": "separate"})]
    assert ff.reported_metrics(rows) == []


def test_unverified_figure_is_never_used():
    rows = [_row(revenue={"value": 100.0, "_check": "value not on cited page"})]
    assert ff.reported_metrics(rows) == []


def test_another_entitys_filing_is_labelled_with_its_name():
    row = _row(revenue=44189.0)
    row.update({"entity_match": "different", "filing_entity_english": "Wesfarmers Limited",
                "company": "BUNNINGS GROUP LIMITED"})
    [card] = ff.reported_metrics([row])
    assert card["metric"] == "Revenue - Wesfarmers Limited"
    assert "Wesfarmers Limited" in card["entity_note"]


def test_own_entity_beats_another_entitys_newer_filing():
    own = _row("2024-06-30", file="own.pdf", revenue=10.0)
    parent = _row("2025-06-30", file="parent.pdf", revenue=500.0)
    parent["entity_match"] = "different"
    [card] = ff.reported_metrics([own, parent])
    assert card["value"] == 10.0


def test_employees_are_a_headcount():
    rows = [_row(employees={"value": 33951.0, "_currency": "", "_scale": "",
                            "_prior": 34683.0, "_prior_period_end": "2024-06-30"})]
    [card] = ff.reported_metrics(rows)
    assert card["value_text"] == "33,951 employees"
    assert card["change_text"] == "-2.1%"


def test_ceo_from_newest_filing_of_the_account_itself():
    old = _row("2024-06-30", file="a.pdf")
    old.update({"ceo_check": "verified", "ceo_name": "Old CEO", "ceo_title": "CEO"})
    new = _row("2025-06-30", file="b.pdf")
    new.update({"ceo_check": "verified", "ceo_name": "Paul Graham", "ceo_title": "Group CEO & MD",
                "ceo_page": "4"})
    assert ff.ceo([old, new])["name"] == "Paul Graham"
    new["entity_match"] = "different"
    assert ff.ceo([old, new])["name"] == "Old CEO"


def test_a_fallback_older_than_two_years_is_not_shown():
    rows = [_row("2025-06-30", file="ar2025.pdf", revenue=100.0),
            _row("2015-06-30", file="ar2015.pdf", employees={"value": 500.0, "_currency": "",
                                                            "_scale": ""})]
    assert [c["metric"] for c in ff.reported_metrics(rows)] == ["Revenue"]


def test_large_thousands_are_shown_in_millions_with_the_original_kept():
    rows = [_row(revenue={"value": 11471675.0, "_scale": "thousand", "_currency": "SGD",
                          "_text": "11,471,675"})]
    [card] = ff.reported_metrics(rows)
    assert card["value_text"] == "SGD 11,471.70 million"
    assert card["original_value_text"] == "11,471,675"


def test_unnamed_entity_is_used_but_flagged():
    row = _row(revenue=100.0)
    row["entity_match"] = "unknown"
    [card] = ff.reported_metrics([row])
    assert "entity_unconfirmed" in card["flags"] and not card["entity_note"]


def test_group_account_never_compares_two_companies():
    motor = _row("2025-06-30", "1H", file="motor_1h25.pdf", revenue=92694438.0)
    mobis = _row("2026-06-30", "1H", file="mobis_1h26.pdf", revenue=31885209.0)
    motor["filing_entity_english"] = "Hyundai Motor Company"
    mobis["filing_entity_english"] = "Hyundai Mobis"
    [card] = ff.reported_metrics([motor, mobis])
    assert card["metric"] == "Revenue (1H) - Hyundai Mobis"
    assert "change_text" not in card
    assert "several" in card["entity_note"]


def test_same_company_spelled_differently_is_still_compared():
    a = _row("2025-12-31", file="a.pdf", revenue=110.0)
    b = _row("2024-12-31", file="b.pdf", revenue=100.0)
    a["filing_entity_english"], b["filing_entity_english"] = "Hanjin KAL Co., Ltd.", "Hanjin Kal Co Ltd"
    [card] = ff.reported_metrics([a, b])
    assert card["metric"] == "Revenue" and card["change_text"] == "+10.0%"


def test_one_company_spelled_two_ways_is_not_several():
    a = _row("2025-06-30", file="a.pdf", revenue=110.0)
    b = _row("2024-06-30", file="b.pdf", revenue=100.0)
    a["filing_entity_english"], b["filing_entity_english"] = "Australian Postal Corporation", "Australia Post"
    [card] = ff.reported_metrics([a, b])
    assert card["metric"] == "Revenue" and not card["entity_note"]
    assert card["change_text"] == "+10.0%"


# -- 24-month filings window (client, 6 Oct) ---------------------------------

@pytest.mark.window
def test_a_filing_published_more_than_24_months_ago_is_not_shown():
    old = _row(period_end="2023-06-30", file="ar2023.pdf", **_metric("revenue", 100.0))
    assert ff.reported_metrics([old]) == []


@pytest.mark.window
def test_the_window_is_measured_on_the_publication_date():
    row = _row(period_end="2023-06-30", file="ar2023.pdf", **_metric("revenue", 100.0))
    row["publication_date"] = "2024-02-15"        # filed within 24 months of AS_OF
    [card] = ff.reported_metrics([row])
    assert card["metric"] == "Revenue"


@pytest.mark.window
def test_ceo_only_from_a_filing_in_the_window():
    old = {**_row(period_end="2023-06-30", file="ar2023.pdf"),
           "ceo_check": "verified", "ceo_name": "Old CEO", "ceo_title": "CEO", "ceo_page": "3"}
    assert ff.ceo([old]) is None


@pytest.mark.window
def test_a_placeholder_publication_date_after_today_falls_back_to_the_period_end():
    """The filings crawl wrote the year's end where it found no date (2026-12-31
    on Accenture's Q3 FY26 release, published 18 Jun 2026). A date after today
    is not a publication date: the period end stands in, so the filing stays."""
    row = _row(period_end="2025-06-30", file="ar2025.pdf", **_metric("revenue", 100.0))
    row["publication_date"] = "2026-12-31T00:00:00Z"
    [card] = ff.reported_metrics([row])
    assert card["metric"] == "Revenue"
    assert ff._filed_on(row, AS_OF) == date(2025, 6, 30)


@pytest.mark.window
def test_a_filing_whose_period_has_not_ended_is_still_left_out():
    row = _row(period_end="2026-03-31", file="future.pdf", **_metric("revenue", 100.0))
    row["publication_date"] = "2026-12-31T00:00:00Z"
    assert ff.reported_metrics([row]) == []


def test_publication_dates_in_every_form_the_crawl_wrote():
    assert ff._published("2025/06/22") == date(2025, 6, 22)        # Japanese EDINET
    assert ff._published("20250312") == date(2025, 3, 12)          # Korean DART
    assert ff._published("05/11/2025") == date(2025, 11, 5)        # ASX, day first
    assert ff._published("2025-06-18T00:00:00Z") == date(2025, 6, 18)
    assert ff._published("") is None
