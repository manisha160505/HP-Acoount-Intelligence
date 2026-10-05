"""Tests for the Executive Dashboard summary card's parent and subsidiaries.

Client, 5 Oct (issue list v3): the parent is the Company Hierarchy sheet's
column E, Ultimate Parent Name, as supplied, unless it is the account itself;
column C, Parent Company Name, is used when column E names no other company.
Parents Explorium gets wrong are held for client review. Subsidiaries are
column A of the Subsidiaries sheet.

Astra is pinned with its real values: a blank Parent Company Name, a
self-referential Ultimate Parent row naming the company itself, and a Business
Description ending "operates as a subsidiary of Jardine Cycle & Carriage
Limited". None of those may reach the field.

Run: python -m pytest tests/test_executive_dashboard.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.executive_dashboard import _resolve_parent, _subsidiaries

ASTRA_ID = "8fe936f404e732f41c273a98045b8526"
ASTRA = "PT ASTRA INTERNATIONAL TBK - ID"

ASTRA_HIERARCHY = {
    "Business Id": ASTRA_ID,
    "Parent Company Id": "",
    "Parent Company Name": "",
    "Ultimate Parent Id": ASTRA_ID,
    "Ultimate Parent Name": "pt astra international tbk",
}


def test_astra_self_referential_row_shows_nothing():
    assert _resolve_parent(ASTRA_HIERARCHY, ASTRA) == ("", None)


def test_ultimate_parent_name_is_the_parent():
    """Column E, as supplied (BDO -> SM Investments)."""
    row = {"Business Id": "bdo", "Parent Company Name": "sm investments",
           "Ultimate Parent Id": "sm", "Ultimate Parent Name": "sm investments"}
    assert _resolve_parent(row, "BANCO DE ORO UNIBANK, INC. (BDO) - PH") == (
        "sm investments", "Ultimate Parent Name")


def test_column_e_wins_over_column_c():
    row = {"Business Id": "child", "Parent Company Name": "Jardine Cycle & Carriage",
           "Ultimate Parent Id": "top", "Ultimate Parent Name": "Jardine Matheson"}
    assert _resolve_parent(row, "ACME - SG") == ("Jardine Matheson", "Ultimate Parent Name")


def test_own_name_in_column_e_is_not_a_parent():
    """Canon's column E is 'canon' under a different id: still Canon."""
    row = {"Business Id": "a", "Ultimate Parent Id": "b", "Ultimate Parent Name": "canon",
           "Parent Company Name": "canon"}
    assert _resolve_parent(row, "CANON INC. - JP") == ("", None)
    row = {"Business Id": "a", "Ultimate Parent Id": "b", "Ultimate Parent Name": "mitsubishi"}
    assert _resolve_parent(row, "MITSUBISHI MOTORS CORPORATION - JP") == ("", None)


def test_column_c_is_used_when_column_e_is_the_account_itself():
    """San Miguel: column E is San Miguel; column C names Top Frontier."""
    row = {"Business Id": "sm", "Parent Company Name": "top frontier investment holdings",
           "Ultimate Parent Id": "sm", "Ultimate Parent Name": "san miguel"}
    assert _resolve_parent(row, "SAN MIGUEL CORPORATION - PH") == (
        "top frontier investment holdings", "Parent Company Name")


def test_column_c_naming_the_account_itself_shows_nothing():
    row = {"Business Id": "t", "Parent Company Name": "true corporation",
           "Ultimate Parent Id": "t", "Ultimate Parent Name": "true public"}
    assert _resolve_parent(row, "TRUE CORPORATION PUBLIC COMPANY LIMITED - TH") == ("", None)


def test_held_parents_are_not_shown():
    row = {"Business Id": "m", "Parent Company Name": "us bancorp",
           "Ultimate Parent Id": "u", "Ultimate Parent Name": "us bancorp"}
    assert _resolve_parent(row, "MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP") == ("", None)
    row = {"Business Id": "b", "Parent Company Name": "andeavor",
           "Ultimate Parent Id": "m", "Ultimate Parent Name": "marathon petroleum"}
    assert _resolve_parent(row, "BHP BILLITON - AU") == ("", None)


def test_a_corrected_value_for_a_held_account_shows():
    row = {"Business Id": "m", "Ultimate Parent Id": "u", "Ultimate Parent Name": "Real Parent"}
    assert _resolve_parent(row, "MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP")[0] == "Real Parent"


def test_names_are_trimmed_and_blanks_ignored():
    assert _resolve_parent({"Parent Company Name": "  Jardine Ltd  "}, "ACME - SG")[0] == "Jardine Ltd"
    assert _resolve_parent({"Parent Company Name": "   "}, "ACME - SG") == ("", None)


def test_no_hierarchy_row_shows_nothing():
    assert _resolve_parent(None, ASTRA) == ("", None)
    assert _resolve_parent({}, ASTRA) == ("", None)


def test_lowercase_column_name_is_accepted():
    assert _resolve_parent({"parent_company_name": "Jardine Ltd"}, "ACME - SG")[0] == "Jardine Ltd"


def test_subsidiaries_are_column_a_as_supplied_in_order():
    rows = [{"Subsidiary Name": "verigy us", "Subsidiary ID": "1"},
            {"Subsidiary Name": "w2bi a member of the advantest group", "Subsidiary ID": "2"}]
    assert _subsidiaries(rows, "ADVANTEST CORPORATION - JP", "") == [
        "verigy us", "w2bi a member of the advantest group"]


def test_subsidiaries_drop_blanks_repeats_self_and_parent():
    rows = [{"Subsidiary Name": n} for n in
            ("woolworths", "Big W", "big w", "", "endeavour group", "wesfarmers")]
    assert _subsidiaries(rows, "WOOLWORTHS GROUP LIMITED - AU", "wesfarmers") == [
        "Big W", "endeavour group"]


def test_a_subsidiary_starting_with_the_account_name_is_kept():
    """'toyota motor' is Toyota Group's subsidiary, not Toyota itself."""
    rows = [{"Subsidiary Name": "toyota motor"}, {"Subsidiary Name": "aisin"}]
    assert _subsidiaries(rows, "TOYOTA GROUP - JP", "") == ["toyota motor", "aisin"]


def test_subsidiaries_read_column_a_without_its_header():
    assert _subsidiaries([{"Name": "verigy us", "Id": "1"}], "ADVANTEST - JP", "") == ["verigy us"]
