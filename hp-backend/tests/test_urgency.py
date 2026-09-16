"""Tests for the Urgency Score.

Unlike Evidence Strength, no worked example came with this formula - there was
nothing to pin it against, because the per-driver formulas were authored here
rather than supplied. So what these tests pin is different: the rules that came
from the specification and must not drift, and the decisions this implementation
took against the data that must stay visible when someone changes them.

The first group is ABX's and is not ours to change: the weights, and the
missing-input rule that forbids scoring an absent driver as zero. The second
group is the two instructed compromises - band proxies and blank-status-as-open
- each of which is defensible only while it is disclosed, so the tests assert
the disclosure as much as the arithmetic.

Run: python -m pytest tests/test_urgency.py -v
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import urgency as u

SCORED_ON = date(2026, 9, 16)


def _complete_drivers():
    """Five available drivers, so the composite computes."""
    return [
        u.fleet_refresh(["Microsoft Windows", "Linux"], "10001+"),
        u.ai_workstation([("AI/ML", 60)], ["Data Scientist"], []),
        u.hiring([{"status": "open", "normalized_title": "Senior Engineer",
                   "categories": '["engineering"]', "posted_at": "2026-09-01"}],
                 SCORED_ON),
        u.expansion("10001+", "10B-100B", [], SCORED_ON),
        u.intent([("PCs", 40, "pc refresh")], [("AI/ML", 60)], ["ai/ml"]),
    ]


# ---------------------------------------------------------------------------
# ABX's rules. These came from the specification and are not ours to change.
# ---------------------------------------------------------------------------

def test_weights_are_the_specified_ones():
    """ABX Feature 1 Step 5, quoted verbatim. Changing these changes the score
    for all 220 accounts, so they are pinned against a silent edit."""
    assert u.WEIGHTS == {
        "fleet_refresh": 0.20,
        "ai_workstation": 0.25,
        "hiring": 0.15,
        "expansion": 0.15,
        "intent": 0.25,
    }
    assert sum(u.WEIGHTS.values()) == pytest.approx(1.0)


def test_one_unavailable_driver_blocks_the_composite():
    """*"If any of the five urgency inputs is unavailable, keep that input
    unavailable and do not calculate the overall urgency score."*"""
    drivers = _complete_drivers()
    drivers[4] = u._unavailable("intent", "no category scores on file")

    result = u.score(drivers, SCORED_ON)

    assert result["score"] is None
    assert result["available"] is False
    assert result["unavailable_drivers"] == ["intent"]


def test_a_missing_driver_is_never_scored_as_zero():
    """*"Do not change a missing value to 0%."* The distinction this protects:
    a driver that computed to zero and a driver that could not be computed are
    different facts and must not render the same."""
    absent = u._unavailable("intent", "no data")
    real_zero = u.intent([("PCs", 0, "procurement")], [], [])

    assert absent["value"] is None and absent["available"] is False
    assert real_zero["value"] == 0 and real_zero["available"] is True


def test_the_composite_is_the_weighted_sum():
    drivers = _complete_drivers()
    result = u.score(drivers, SCORED_ON)

    expected = round(sum(d["value"] * u.WEIGHTS[d["key"]] for d in drivers))
    assert result["score"] == expected
    assert 0 <= result["score"] <= 100


def test_shared_evidence_is_linked_not_deduplicated():
    """*"If one evidence item genuinely supports two different drivers, link the
    same evidence ID to both drivers so the reuse is visible."*"""
    shared_id = "news:AI factory opens"
    a = u._driver("ai_workstation", 40, [], [shared_id])
    b = u._driver("expansion", 40, [], [shared_id])
    drivers = [u._unavailable("fleet_refresh", "x"), a,
               u._unavailable("hiring", "x"), b,
               u._unavailable("intent", "x")]

    result = u.score(drivers, SCORED_ON)

    assert result["shared_evidence"][shared_id] == ["ai_workstation", "expansion"]
    # Still present on both drivers, not moved to one.
    assert shared_id in a["evidence_ids"]
    assert shared_id in b["evidence_ids"]


# ---------------------------------------------------------------------------
# Authorship. These formulas are not the client's and the payload has to say so
# until that changes.
# ---------------------------------------------------------------------------

def test_payload_declares_the_formulas_are_not_client_agreed():
    result = u.score(_complete_drivers(), SCORED_ON)

    assert result["client_agreed"] is False
    assert "delivery-authored" in result["formula_authority"]
    for driver in result["drivers"]:
        assert driver["authored_by"] == "delivery"


# ---------------------------------------------------------------------------
# Band proxies. Instructed, and defensible only while disclosed.
# ---------------------------------------------------------------------------

def test_bands_are_never_parsed_numerically():
    """The input contract says employee and revenue bands are "passed through
    verbatim; NEVER parsed numerically". Scoring reads the band's position on a
    fixed ladder, so no digit is ever extracted from the string."""
    assert u._band_points("10001+", u.EMPLOYEE_BANDS) == (25, "10001+")
    # Spelling varies across vendor exports; the ladder still matches.
    assert u._band_points("10,001 +", u.EMPLOYEE_BANDS)[1] == "10001+"
    # An unrecognised band scores nothing rather than being rounded to a
    # neighbour, which would be inventing the account's size.
    assert u._band_points("banana", u.EMPLOYEE_BANDS) == (0, None)


def test_proxy_drivers_say_what_they_actually_measure():
    """Fleet Refresh and Expansion do not measure what their names promise -
    there is no OS version data and no prior period for growth. Both must carry
    the caveat, or the dashboard is overstating what it knows."""
    fleet = u.fleet_refresh(["Microsoft Windows"], "10001+")
    expand = u.expansion("10001+", "10B-100B", [], SCORED_ON)

    assert fleet["proxy"] is True
    assert "NOT refresh due-ness" in fleet["proxy_note"]
    assert expand["proxy"] is True
    assert "NOT scored" in expand["proxy_note"]

    result = u.score(_complete_drivers(), SCORED_ON)
    assert set(result["proxy_drivers"]) == {"fleet_refresh", "expansion"}


# ---------------------------------------------------------------------------
# Hiring: open question 5.1, answered here by instruction and not by the client.
# ---------------------------------------------------------------------------

def test_blank_status_counts_as_open_and_says_so():
    """Astra's postings are 60 closed, 40 blank, 0 open. Counting blanks as open
    is the instructed reading of unanswered open question 5.1; the note is what
    makes it reversible when the client answers."""
    postings = [{"status": "", "normalized_title": "Analyst",
                 "categories": '["finance"]'} for _ in range(40)]

    driver = u.hiring(postings, SCORED_ON)

    assert driver["terms"][0]["basis"] == "40 open postings"
    assert any("5.1" in note for note in driver["notes"])


def test_blank_status_can_be_read_as_unknown():
    """The other reading of 5.1, behind one flag. If the client answers "blank
    means unknown", this is the single line that changes."""
    postings = [{"status": "", "normalized_title": "Analyst",
                 "categories": '["finance"]'} for _ in range(40)]

    driver = u.hiring(postings, SCORED_ON, blank_status_is_open=False)

    assert driver["terms"][0]["basis"] == "0 open postings"


def test_velocity_ignores_undated_postings_rather_than_using_crawl_dates():
    """`first_seen_at` is populated on every row but records when the crawler
    saw a posting, not when the account published it. Scoring it would measure
    our collection schedule and label the result hiring velocity."""
    postings = [{"status": "open", "normalized_title": "Analyst",
                 "categories": "[]", "posted_at": "",
                 "first_seen_at": "2026-09-15T00:00:00Z"}]

    driver = u.hiring(postings, SCORED_ON)
    velocity = next(t for t in driver["terms"] if t["label"] == "Velocity")

    assert velocity["points"] == 0
    assert "crawl dates" in velocity["basis"]


# ---------------------------------------------------------------------------
# Intent: the noisy-keyword gate, shared with Intent & Demand Signals.
# ---------------------------------------------------------------------------

def test_noisy_keyword_bars_a_category_from_being_primary():
    """Astra's top category is 3D Printers at 34, carried by "SLA" - which in a
    job posting is a service-level agreement, not stereolithography. It keeps
    its score elsewhere on the dashboard but cannot be the primary signal, so
    the weaker but trustworthy Printers takes it."""
    driver = u.intent(
        [("3D Printers", 34, "jig | SLA | manufacturing engineer"),
         ("Printers", 12, "procurement")], [], [])

    assert driver["terms"][0]["basis"] == "Printers scores 12/100"
    assert any("3D Printers" in note for note in driver["notes"])


def test_intent_is_unavailable_when_every_category_is_flagged():
    """Not zero. There is intent data; none of it can serve as a primary
    signal, which is a different statement from "no intent"."""
    driver = u.intent([("3D Printers", 34, "SLA")], [], [])

    assert driver["available"] is False
    assert driver["value"] is None


def test_noisy_terms_come_from_the_shared_dictionary():
    """Read from Intent & Demand Signals' own dictionary rather than copied, so
    a term added there cannot leave this dashboard barring a different set of
    categories than that feature does."""
    from app.services.hp import intent_topic_map

    assert set(u.NOISY_KEYWORDS) == set(intent_topic_map.NOISY_CATEGORY_TERMS)


# ---------------------------------------------------------------------------
# Driver bounds.
# ---------------------------------------------------------------------------

def test_every_driver_is_capped_at_100():
    """Term maxima sum above 100 in some drivers by design - a strong account
    should be able to reach the cap without every term being perfect - so the
    cap is what keeps the weighted total inside 0-100."""
    maxed = u.fleet_refresh(
        ["Microsoft Windows", "macOS", "Linux", "Dell", "Lenovo", "Intel"],
        "10001+")

    assert maxed["value"] <= 100


def test_unavailable_driver_when_nothing_is_on_file():
    assert u.fleet_refresh([], "")["available"] is False
    assert u.ai_workstation([], [], [])["available"] is False
    assert u.hiring([], SCORED_ON)["available"] is False
    assert u.expansion("", "", [], SCORED_ON)["available"] is False
    assert u.intent([], [], [])["available"] is False
