"""The client's 7 Oct parent/subsidiary data, and the version that guards it.

`config/company_relationships.csv` is part of the Executive Dashboard's logic:
its node references RELATIONSHIPS_VERSION, so every account's dashboard goes
stale when the version moves. These tests make it impossible to change the
data without moving it.

Run: python -m pytest tests/test_company_relationships.py -v
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import company_relationships as cr
from app.services.regen.graph import DEFAULT as GRAPH


def test_the_file_matches_its_pinned_hash():
    """Changed the CSV? Bump RELATIONSHIPS_VERSION and set FILE_SHA256 to the
    new hash (shasum -a 256 config/company_relationships.csv)."""
    assert cr.file_sha256() == cr.FILE_SHA256


def test_the_executive_dashboard_depends_on_it():
    refs = GRAPH["exec_core"].logic_refs
    assert "app.services.hp.company_relationships:RELATIONSHIPS_VERSION" in refs


def test_every_row_is_well_formed():
    with open(cr.PATH, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows
    for row in rows:
        assert row["relationship"] in {"parent", "subsidiary", "no_parent"}, row
        assert bool(row["company"]) == (row["relationship"] != "no_parent"), row


def test_the_clients_eleven_mapped_accounts_are_all_overridden():
    mapped = ["BANK FOR AGRICULTURE AND AGRICULTURAL COOPERATIVE - TH", "BHP BILLITON - AU",
              "CHAROEN POKPHAND GROUP CO LTD - TH", "MILITARY BANK - VN",
              "MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP",
              "THE BANK OF TOKYO-MITSUBISHI LIMITED (BANGKOK BRANCH) - TH",
              "SHISEIDO COMPANY, LIMITED - JP", "SUMITOMO MITSUI FINANCIAL GROUP, INC. - JP",
              "VIETTEL CORPORATION - VN", "SEATRIUM LIMITED - SG", "HEALTHSCOPE - AU"]
    for account in mapped:
        assert cr.for_account(account)["override"] is not None, account


def test_no_self_parent_survived_the_build():
    for account, wrong in (("BUNNINGS GROUP LIMITED", "Bunnings"),
                           ("UNITED OVERSEAS BANK LIMITED (UOB) - SG", "UOB"),
                           ("HKMC GROUP(HYUNDAI AUTOEVER) - KR", "Autoever"),
                           ("FONTERRA CO-OPERATIVE GROUP LIMITED - NZ", "Fonterra")):
        assert wrong not in cr.for_account(account)["parents"]


def test_an_account_is_found_with_or_without_its_country_suffix():
    assert cr.for_account("BHP BILLITON - AU") == cr.for_account("bhp billiton")
    assert cr.for_account("NOT AN ACCOUNT - SG") == {"override": None, "parents": [],
                                                     "subsidiaries": []}
