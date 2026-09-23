"""Tests for the Executive Dashboard summary card's parent resolution.

Client ruling (Sep 2026): the Company Hierarchy sheet's Parent Company Name is
the parent when it is populated, used as supplied. When it is blank the parent
relationship is ignored for now - nothing is shown and nothing is flagged.

Astra is pinned with its real values: a blank Parent Company Name, a
self-referential Ultimate Parent row naming the company itself, and a Business
Description ending "operates as a subsidiary of Jardine Cycle & Carriage
Limited". None of those last two may reach the field.

Run: python -m pytest tests/test_executive_dashboard.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.executive_dashboard import _resolve_parent

ASTRA_ID = "8fe936f404e732f41c273a98045b8526"

ASTRA_HIERARCHY = {
    "Business Id": ASTRA_ID,
    "Parent Company Id": "",
    "Parent Company Name": "",
    "Ultimate Parent Id": ASTRA_ID,
    "Ultimate Parent Name": "pt astra international tbk",
}


def test_astra_blank_parent_name_shows_nothing():
    """Blank Parent Company Name: no parent, whatever Ultimate Parent says."""
    assert _resolve_parent(ASTRA_HIERARCHY) == ""


def test_blank_parent_name_ignores_a_valid_looking_ultimate_parent():
    """Ignored means ignored - Ultimate Parent Name is not a fallback."""
    row = {
        "Business Id": "child-id",
        "Parent Company Name": "",
        "Ultimate Parent Id": "parent-id",
        "Ultimate Parent Name": "Jardine Cycle & Carriage Limited",
    }
    assert _resolve_parent(row) == ""


def test_populated_parent_name_is_used_as_supplied():
    row = {
        "Business Id": "child-id",
        "Parent Company Id": "parent-id",
        "Parent Company Name": "Jardine Cycle & Carriage Limited",
        "Ultimate Parent Id": "ultimate-id",
        "Ultimate Parent Name": "Some Other Holdings Ltd",
    }
    assert _resolve_parent(row) == "Jardine Cycle & Carriage Limited"


def test_parent_name_wins_over_a_self_referential_row():
    row = dict(ASTRA_HIERARCHY, **{"Parent Company Name": "Jardine Cycle & Carriage Limited"})
    assert _resolve_parent(row) == "Jardine Cycle & Carriage Limited"


def test_parent_name_is_trimmed():
    assert _resolve_parent({"Parent Company Name": "  Jardine Ltd  "}) == "Jardine Ltd"


def test_whitespace_only_parent_name_counts_as_blank():
    assert _resolve_parent({"Parent Company Name": "   "}) == ""


def test_no_hierarchy_row_shows_nothing():
    assert _resolve_parent(None) == ""
    assert _resolve_parent({}) == ""


def test_lowercase_column_name_is_accepted():
    assert _resolve_parent({"parent_company_name": "Jardine Ltd"}) == "Jardine Ltd"
