"""Tests for the Executive Dashboard summary card's ultimate-parent resolution.

What these pin is a refusal rather than a computation: when the hierarchy file
cannot establish a parent, the field is suppressed and flagged, never guessed.
Astra is the case that motivated it and is pinned first with its real values -
a self-referential hierarchy row whose Ultimate Parent Name is the company
itself, sitting against a Business Description that ends "operates as a
subsidiary of Jardine Cycle & Carriage Limited".

The rule that matters most here is the one asserting Jardine is NOT written into
the field. Parsing a parent out of prose and promoting it to ground truth is the
silent swap this codebase exists to avoid; the contradicting name belongs on a
review flag where a human confirms it, and test_does_not_promote_stated_parent
is what stops a later change from "helpfully" filling the field in.

Run: python -m pytest tests/test_executive_dashboard.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.executive_dashboard import _resolve_ultimate_parent

ASTRA_ID = "8fe936f404e732f41c273a98045b8526"

ASTRA_DESCRIPTION = (
    "PT Astra International Tbk is a diverse Indonesian conglomerate operating "
    "through its subsidiaries across a multitude of sectors. Established in "
    "Jakarta, Indonesia, in 1957, PT Astra International Tbk operates as a "
    "subsidiary of Jardine Cycle & Carriage Limited."
)

ASTRA_HIERARCHY = {
    "Business Id": ASTRA_ID,
    "Parent Company Id": "",
    "Parent Company Name": "",
    "Ultimate Parent Id": ASTRA_ID,
    "Ultimate Parent Name": "pt astra international tbk",
}


# ---------------------------------------------------------------------------
# Astra - the account that motivated the rule
# ---------------------------------------------------------------------------

def test_astra_parent_is_suppressed():
    """The self-referential row must not put Astra's own name in the field."""
    parent, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, ASTRA_DESCRIPTION)
    assert parent == ""
    assert flag is not None


def test_astra_flag_reports_both_reasons():
    _, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, ASTRA_DESCRIPTION)
    assert flag["field"] == "ultimate_parent"
    assert flag["status"] == "needs_review"
    assert "self-referential" in flag["reason"]
    assert "contradicts" in flag["reason"]


def test_astra_flag_preserves_the_suppressed_value():
    """Suppressed, not discarded - review needs to see what was rejected."""
    _, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, ASTRA_DESCRIPTION)
    assert flag["suppressed_value"] == "pt astra international tbk"


def test_does_not_promote_stated_parent():
    """Jardine is reported for review and never written into the field.

    The description is unstructured vendor prose; "subsidiary of" there may
    describe a minority stake rather than an ultimate parent. It is evidence
    that the hierarchy file is wrong, which is not the same as being ground
    truth itself.
    """
    parent, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, ASTRA_DESCRIPTION)
    assert "jardine" not in parent.lower()
    assert flag["stated_parent"] == "Jardine Cycle & Carriage Limited"


# ---------------------------------------------------------------------------
# Parent Company Name - the client's ruling, which outranks the checks below
# ---------------------------------------------------------------------------

def test_populated_parent_name_is_used_as_supplied():
    """A populated Parent Company Name settles it, per the client (Sep 2026)."""
    row = {
        "Business Id": "child-id",
        "Parent Company Id": "parent-id",
        "Parent Company Name": "Jardine Cycle & Carriage Limited",
        "Ultimate Parent Id": "ultimate-id",
        "Ultimate Parent Name": "Some Other Holdings Ltd",
    }
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == "Jardine Cycle & Carriage Limited"
    assert flag is None


def test_parent_name_wins_over_a_self_referential_row():
    """The self-reference check guards an unestablished parent.

    A populated Parent Company Name establishes one, so the check does not
    apply even though Ultimate Parent Id still equals Business Id.
    """
    row = dict(ASTRA_HIERARCHY, **{"Parent Company Name": "Jardine Cycle & Carriage Limited"})
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == "Jardine Cycle & Carriage Limited"
    assert flag is None


def test_parent_name_is_not_second_guessed_against_the_description():
    """Taken as supplied - a description disagreeing with it does not flag it."""
    row = {
        "Business Id": "child-id",
        "Parent Company Name": "Completely Unrelated Holdings Ltd",
        "Ultimate Parent Id": "ultimate-id",
        "Ultimate Parent Name": "Some Other Holdings Ltd",
    }
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == "Completely Unrelated Holdings Ltd"
    assert flag is None


def test_blank_parent_name_falls_through_to_the_existing_rules():
    """Blank is "ignore the parent relationship", not "look harder".

    Astra ships a blank Parent Company Name, so it still lands on the
    self-referential suppression path rather than displaying its own name.
    """
    parent, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, ASTRA_DESCRIPTION)
    assert parent == ""
    assert flag is not None
    assert "self-referential" in flag["reason"]


# ---------------------------------------------------------------------------
# The two independent triggers
# ---------------------------------------------------------------------------

def test_self_reference_alone_suppresses():
    """No description to contradict it, but the row still establishes nothing."""
    parent, flag = _resolve_ultimate_parent(ASTRA_HIERARCHY, "")
    assert parent == ""
    assert "self-referential" in flag["reason"]
    assert flag["stated_parent"] is None


def test_contradiction_alone_suppresses():
    """A genuine parent id, but a name the description disagrees with."""
    row = {
        "Business Id": "child-id",
        "Ultimate Parent Id": "parent-id",
        "Ultimate Parent Name": "Some Other Holdings Ltd",
    }
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == ""
    assert "contradicts" in flag["reason"]
    assert "self-referential" not in flag["reason"]


# ---------------------------------------------------------------------------
# Rows that must still pass through untouched
# ---------------------------------------------------------------------------

def test_valid_hierarchy_passes_through():
    """A real parent, agreeing with the description, is displayed unflagged."""
    row = {
        "Business Id": "child-id",
        "Ultimate Parent Id": "parent-id",
        "Ultimate Parent Name": "Jardine Cycle & Carriage Limited",
    }
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == "Jardine Cycle & Carriage Limited"
    assert flag is None


def test_legal_suffix_differences_are_not_a_contradiction():
    """"Jardine Cycle & Carriage Ltd" vs "... Limited" is the same company.

    Without this, the comparison would flag well-formed rows over punctuation
    and turn the review queue into noise.
    """
    row = {
        "Business Id": "child-id",
        "Ultimate Parent Id": "parent-id",
        "Ultimate Parent Name": "Jardine Cycle & Carriage Ltd.",
    }
    parent, flag = _resolve_ultimate_parent(row, ASTRA_DESCRIPTION)
    assert parent == "Jardine Cycle & Carriage Ltd."
    assert flag is None


def test_no_hierarchy_row_is_not_a_flag():
    """Absent data is missing, not contradictory - nothing to review."""
    assert _resolve_ultimate_parent(None, ASTRA_DESCRIPTION) == ("", None)


def test_blank_parent_name_is_not_a_flag():
    row = {"Business Id": ASTRA_ID, "Ultimate Parent Id": ASTRA_ID,
           "Ultimate Parent Name": ""}
    assert _resolve_ultimate_parent(row, ASTRA_DESCRIPTION) == ("", None)


def test_lowercase_column_names_are_accepted():
    """Matches the fallback the surrounding extractor already does."""
    row = {"business_id": ASTRA_ID, "ultimate_parent_id": ASTRA_ID,
           "ultimate_parent_name": "pt astra international tbk"}
    parent, flag = _resolve_ultimate_parent(row, "")
    assert parent == ""
    assert flag is not None


def test_missing_business_id_does_not_trigger_self_reference():
    """Without both ids there is nothing to compare; don't invent a reason."""
    row = {"Ultimate Parent Id": ASTRA_ID,
           "Ultimate Parent Name": "Some Holdings Ltd"}
    parent, flag = _resolve_ultimate_parent(row, "")
    assert parent == "Some Holdings Ltd"
    assert flag is None
