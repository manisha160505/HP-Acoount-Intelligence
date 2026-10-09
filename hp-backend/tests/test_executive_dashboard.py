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

from app.config import account_overrides
from app.services.extractors.executive_dashboard import (
    MAPPING_SOURCE,
    MERGED_SOURCE,
    _parents,
    _resolve_parent,
    _subsidiaries,
)

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


# --- client data, 7 Oct: the parent-company mapping and the merged hierarchy ---

def test_the_clients_mapping_replaces_explorium():
    row = {"Business Id": "s", "Ultimate Parent Id": "x",
           "Ultimate Parent Name": "sembcorp industries"}
    assert _parents(row, "SEATRIUM LIMITED - SG") == (["Temasek Holdings"], [MAPPING_SOURCE])
    row = {"Business Id": "h", "Ultimate Parent Id": "x",
           "Ultimate Parent Name": "brookfield dtla fund office trust investor"}
    assert _parents(row, "HEALTHSCOPE - AU")[0] == [
        "Brookfield Asset Management (via Brookfield Business Partners)"]


def test_the_nine_hidden_accounts_show_no_parent_despite_the_mapping():
    """Client, 8 Oct: no parent for the nine accounts Explorium held differently
    (config/account_overrides.yaml), even where the 7 Oct mapping names one."""
    row = {"Business Id": "b", "Parent Company Name": "andeavor",
           "Ultimate Parent Id": "m", "Ultimate Parent Name": "marathon petroleum"}
    assert _parents(row, "BHP BILLITON - AU") == ([], [])
    assert _parents({}, "VIETTEL CORPORATION - VN") == ([], [])
    assert _parents({}, "THE BANK OF TOKYO-MITSUBISHI LIMITED (BANGKOK BRANCH) - TH") == ([], [])


def test_no_parent_in_the_mapping_shows_nothing_whatever_explorium_says():
    row = {"Business Id": "m", "Parent Company Name": "us bancorp",
           "Ultimate Parent Id": "u", "Ultimate Parent Name": "us bancorp"}
    assert _parents(row, "MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP") == ([], [])
    assert _parents({"Business Id": "s", "Ultimate Parent Id": "c",
                     "Ultimate Parent Name": "citibank"},
                    "SUMITOMO MITSUI FINANCIAL GROUP, INC. - JP") == ([], [])
    # The client named Shiseido itself as its parent: independent, so none.
    assert _parents({"Ultimate Parent Name": "henkel", "Business Id": "s",
                     "Ultimate Parent Id": "h"}, "SHISEIDO COMPANY, LIMITED - JP") == ([], [])


def test_a_parent_from_the_merged_sheet_is_added_to_explorium():
    row = {"Business Id": "b", "Ultimate Parent Id": "w", "Ultimate Parent Name": "wesfarmers"}
    # Both sources name Wesfarmers: shown once, credited to Explorium.
    assert _parents(row, "BUNNINGS GROUP LIMITED") == (["wesfarmers"], ["Company Hierarchy - Ultimate Parent Name"])
    # Explorium has nothing: the merged sheet's parent shows.
    assert _parents({}, "ANZ HOLDINGS (NEW ZEALAND) LIMITED - NZ") == (
        ["Australia and New Zealand Banking Group"], [MERGED_SOURCE])


def test_two_parents_are_both_shown():
    row = {"Business Id": "k", "Ultimate Parent Id": "p", "Ultimate Parent Name": "Kerry Group"}
    parents, sources = _parents(row, "KUOK (SINGAPORE) LIMITED - SG")
    assert parents == ["Kerry Group", "Kuok Group"]
    assert sources == ["Company Hierarchy - Ultimate Parent Name", MERGED_SOURCE]


def test_a_reviewed_parent_sharing_the_accounts_first_word_is_kept():
    # 'Kuok Group' starts like 'KUOK (SINGAPORE)' and is its real parent; the
    # Explorium own-name rule would drop it, so the merged rows use exact names.
    assert _parents({}, "KUOK (SINGAPORE) LIMITED - SG")[0] == ["Kuok Group"]
    assert _parents({}, "SEIKO EPSON CORPORATION - JP")[0] == ["Seiko Group"]


def test_an_account_outside_the_clients_data_is_unchanged():
    row = {"Business Id": "b", "Ultimate Parent Id": "s", "Ultimate Parent Name": "sm investments"}
    assert _parents(row, "BANCO DE ORO UNIBANK, INC. (BDO) - PH") == (
        ["sm investments"], ["Company Hierarchy - Ultimate Parent Name"])
    assert _parents({}, "CANON INC. - JP") == ([], [])


def test_the_merged_sheets_subsidiaries_fill_an_account_with_none():
    subs = _subsidiaries([], "ACCENTURE INC - PH", [])
    # 62 in the sheet; 'Accenture' and 'Accenture PLC.' are the account's own
    # name and are not its subsidiaries.
    assert len(subs) == 60
    assert "Accenture" not in subs and "Accenture PLC." not in subs
    assert len({s.lower() for s in subs}) == len(subs)


def test_subsidiaries_leave_out_every_parent():
    rows = [{"Subsidiary Name": "Kerry Group"}, {"Subsidiary Name": "Pacific Carriers"}]
    assert _subsidiaries(rows, "ACME - SG", ["Kerry Group", "Kuok Group"]) == ["Pacific Carriers"]


def test_a_hidden_account_shows_no_parent_whatever_any_source_says(monkeypatch):
    """Client, 8 Oct mechanism: an account flagged `hide_parent_company` in
    config/account_overrides.yaml shows no parent at all - over Explorium and
    over the 7 Oct mapping. Set here, so the test does not depend on which
    accounts the shipped file lists."""
    monkeypatch.setattr(account_overrides, "OVERRIDES", account_overrides._parse(
        {"accounts": {"ACME - SG": {"hide_parent_company": True},
                      "BHP BILLITON - AU": {"hide_parent_company": True}}}))
    row = {"Business Id": "m", "Ultimate Parent Id": "u", "Ultimate Parent Name": "Real Parent"}
    assert _resolve_parent(row, "ACME - SG") == ("", None)
    assert _resolve_parent(row, "acme  - sg") == ("", None)
    assert _parents(row, "ACME - SG") == ([], [])
    assert _parents({}, "BHP BILLITON - AU") == ([], [])


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


def test_a_government_is_never_a_subsidiary():
    """Explorium lists the Government of Japan - a shareholder - as a subsidiary
    of eight Japanese accounts, and the Queensland Government under Coles."""
    rows = [{"Subsidiary Name": n} for n in
            ("verigy us", "japan the government of japan", "crea srl")]
    assert _subsidiaries(rows, "ADVANTEST CORPORATION - JP", "") == ["verigy us", "crea srl"]
    rows = [{"Subsidiary Name": n} for n in ("queensland government", "liquorland")]
    assert _subsidiaries(rows, "COLES GROUP - AU", "") == ["liquorland"]
    # Only the word "government": these are real subsidiaries.
    rows = [{"Subsidiary Name": n} for n in
            ("commonwealth superannuation", "daikin czech republic in pilsen")]
    assert len(_subsidiaries(rows, "ACME - AU", "")) == 2


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
