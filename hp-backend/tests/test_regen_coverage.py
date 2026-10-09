"""Which unprovided datasets another source fills (regen/coverage.py).

The admin pages listed every dataset with no file as "Not provided", covered or
not; 126 of 220 accounts read as short of data on 9 Oct when about half the
entries were filled by another source. A dataset is covered only when the same
card still shows data from elsewhere.

Run: python -m pytest tests/test_regen_coverage.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config import account_overrides
from app.services.regen import coverage


def test_bombora_is_covered_by_the_hp_category_file():
    for key in ("intent_score", "intent_topics"):
        assert coverage.covered_by(key, "ACME - SG", {"hp_category_intent"}) == coverage.HP_CATEGORY_FILE
        assert coverage.covered_by(key, "ACME - SG", {"technographics"}) is None


def test_the_category_file_is_covered_by_bombora():
    assert coverage.covered_by("hp_category_intent", "ACME - SG", {"intent_score"}) == coverage.BOMBORA
    assert coverage.covered_by("hp_category_intent", "ACME - SG", set()) is None


def test_hierarchy_and_subsidiaries_from_the_clients_data():
    # Accenture is in the client's merged hierarchy with its subsidiaries.
    assert coverage.covered_by("subsidiaries", "ACCENTURE INC - PH", set()) == coverage.CLIENT_HIERARCHY
    # Seatrium's parent is in the client's 7 Oct mapping.
    assert coverage.covered_by("company_hierarchy", "SEATRIUM LIMITED - SG", set()) == coverage.CLIENT_HIERARCHY
    # Neither source knows this account.
    assert coverage.covered_by("company_hierarchy", "ACME - SG", set()) is None
    assert coverage.covered_by("subsidiaries", "ACME - SG", set()) is None


def test_the_clients_no_parent_decision_covers_the_hierarchy(monkeypatch):
    monkeypatch.setattr(account_overrides, "OVERRIDES", account_overrides._parse(
        {"accounts": {"ACME - SG": {"hide_parent_company": True}}}))
    assert coverage.covered_by("company_hierarchy", "ACME - SG", set()) == coverage.CLIENT_NO_PARENT


def test_tech_breakdown_is_covered_by_webstack_only():
    assert coverage.covered_by("tech_breakdown", "ACME - SG", {"webstack"}) == coverage.WEBSTACK
    # Technographics is a different card: not cover.
    assert coverage.covered_by("tech_breakdown", "ACME - SG", {"technographics"}) is None


def test_technographics_is_covered_by_the_website_sheets():
    """Client, 27 Sep: with no Technographics row the tech map reads the
    website technology (Webstack, Tech Breakdown) and says so on the card."""
    assert coverage.covered_by("technographics", "ACME - SG", {"webstack"}) == coverage.WEBSITE_TECHNOLOGY
    assert coverage.covered_by("technographics", "ACME - SG", {"tech_breakdown"}) == coverage.WEBSITE_TECHNOLOGY
    assert coverage.covered_by("technographics", "ACME - SG", {"technology_detections"}) is None


def test_the_two_news_sources_cover_each_other():
    assert coverage.covered_by("news_events", "ACME - SG", {"google_news"}) == coverage.GOOGLE_NEWS
    assert coverage.covered_by("google_news", "ACME - SG", {"news_events"}) == coverage.NEWS_EVENTS


def test_a_weaker_stand_in_is_never_cover():
    # Revenue ranges are not filed figures; nothing replaces job openings,
    # contacts, filings or technographics.
    everything = {"firmographics", "technographics", "webstack", "intent_score",
                  "hp_category_intent", "news_events", "google_news"}
    for key in ("filings_financials", "job_openings", "prospect_contacts",
                "compliance_filings", "webstack",
                "technology_detections", "extended_company"):
        assert coverage.covered_by(key, "ACCENTURE INC - PH", everything) is None
