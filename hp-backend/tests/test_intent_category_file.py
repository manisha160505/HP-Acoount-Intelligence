"""Attaching the HP category intent file to an account.

The HP category export is the primary source of intent: when Bombora has
nothing for an account, the category file is what Intent & Demand falls back
to. It is attached by matching the account's domain against the file's, and
measured against the live 220 that match failed for three accounts whose
data was present and uploaded the whole time:

    PILIPINAS SHELL   pilipinas.shell.com.ph  vs  shell.com.ph
    POSCO GROUP       posco-inc.com           vs  posco.com
    PUBLIC BANK BHD   publicbankgroup.com     vs  pbebank.com

Only the first is one organisation filed two ways. The other two are
different registered domains, and deciding they are the same account is a
claim about the account - it belongs in a confirmed alias, never in a looser
string rule. These tests pin both halves of that: the subdomain is attached,
and the lookalikes are still refused.

Run: python -m pytest tests/test_intent_category_file.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import intent_demand_signals as ids

# What the Bombora half reports when it has nothing - the wording that was
# being shown even when the HP file had covered for it.
SOURCE_A = {"availability": "no_intent_data",
            "message": "Intent unavailable: no Bombora intent topics are on file."}

# The export's wide layout: row 1 names each category above the columns it
# spans, row 2 names the fields, each later row is one company. Columns whose
# row-1 cell is not "<name> (Score /100)" are account-level.
ROWS = [
    ["Company", "Domain", "Run Date", "PCs (Score /100)", "", ""],
    ["company", "domain", "run date", "Intent Score (/100)", "Buying Stage",
     "Topics Researched"],
    ["Shell Philippines", "shell.com.ph", "2026-09-01", "72", "Consideration",
     "laptops; endpoint security"],
]


class TestTheDomainMatch:

    def test_an_exact_domain_attaches(self):
        out = ids._parse_category_file(ROWS, "shell.com.ph")
        assert out["status"] == "matched"
        assert out["source"]["matched_by"] == "domain"

    def test_a_subdomain_attaches_and_says_so(self):
        """The account is filed under its country subdomain and the file
        covers the group domain. One organisation, one intent row."""
        out = ids._parse_category_file(ROWS, "pilipinas.shell.com.ph")
        assert out["status"] == "matched"
        assert out["source"]["matched_by"] == "subdomain"
        assert out["source"]["file_domain"] == "shell.com.ph"

    @pytest.mark.parametrize("account_domain", [
        "posco-inc.com",          # the file covers posco.com
        "publicbankgroup.com",    # the file covers pbebank.com
        "notshell.com.ph",        # ends similarly, is not under it
    ])
    def test_a_lookalike_domain_is_still_refused(self, account_domain):
        """The guard on the guard. A different registered domain is a
        different account until somebody says otherwise in writing."""
        rows = [r[:] for r in ROWS]
        rows[2][1] = "posco.com"
        out = ids._parse_category_file(rows, account_domain)
        assert out["status"] == "mismatch"
        assert out["source"] is None

    def test_no_domain_on_file_is_unverified_not_mismatch(self):
        out = ids._parse_category_file(ROWS, "")
        assert out["status"] == "unverified"

    def test_an_empty_file_is_no_file(self):
        assert ids._parse_category_file([], "shell.com.ph")["status"] == "no_file"


class TestWhatTheSellerIsTold:
    """The message that sent this audit looking in the wrong place: with
    Bombora absent, every account was told "no Bombora intent topics are on
    file", including the three whose HP file was uploaded and unmatched."""

    def test_an_unmatched_hp_file_is_named(self):
        out = ids._summary_unavailable(
            SOURCE_A,
            {"status": "mismatch", "note": "The category file has no row for posco-inc.com."})
        assert "HP category file could not be attached" in out["message"]
        assert "posco-inc.com" in out["message"]

    def test_both_absent_says_both(self):
        out = ids._summary_unavailable(SOURCE_A, {"status": "no_file"})
        assert "neither" in out["message"].lower()

    def test_a_matched_file_keeps_the_bombora_wording(self):
        """When the HP file did attach, the summary is not unavailable at all
        - but if this is ever called with one, it must not invent a fault."""
        out = ids._summary_unavailable(SOURCE_A, {"status": "matched"})
        assert out == SOURCE_A


class TestTheHelper:

    @pytest.mark.parametrize("a,b,same", [
        ("pilipinas.shell.com.ph", "shell.com.ph", True),
        ("shell.com.ph", "pilipinas.shell.com.ph", True),
        ("astra.co.id", "astra.co.id", True),
        ("posco-inc.com", "posco.com", False),
        ("publicbankgroup.com", "pbebank.com", False),
        ("notshell.com.ph", "shell.com.ph", False),
        ("", "shell.com.ph", False),
        ("shell.com.ph", "", False),
    ])
    def test_same_site(self, a, b, same):
        assert ids._same_site(a, b) is same
