"""Which Bombora exports are attached to an account.

The export's Company Website must be the account's domain, a parent or
subdomain of it (health.nsw.gov.au / nsw.gov.au), or a confirmed alias of the
same organisation (client, 5 Oct: IAG NZ's export is under iag.com.au). An
export for another company stays a mismatch and its topics are dropped.

Run: python -m pytest tests/test_intent_domain_match.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.intent_demand_signals import _match_provider_account


def _match(website, account_domain, name="x"):
    return _match_provider_account(
        [{"Company Website": website, "Company Name": name, "Date Stamp": "20260913"}],
        account_domain)[0]


def test_exact_domain_matches():
    m = _match("www.astra.co.id", "astra.co.id")
    assert (m["status"], m["matched_by"]) == ("matched", "domain")


def test_parent_domain_of_a_subdomain_account_matches():
    """NSW Health: the export is filed under nsw.gov.au."""
    m = _match("nsw.gov.au", "health.nsw.gov.au", "nsw health")
    assert (m["status"], m["matched_by"], m["provider_domain"]) == (
        "matched", "subdomain", "nsw.gov.au")
    assert "nsw.gov.au" in m["note"]


def test_confirmed_alias_matches():
    m = _match("iag.com.au", "iag.co.nz", "insurance australia group")
    assert (m["status"], m["matched_by"]) == ("matched", "confirmed_alias")


def test_the_six_exports_the_client_confirmed_on_8_oct_are_attached():
    """Point 9 of the open data gaps: 'not actual mismatch cases'."""
    for website, domain in (("nga.mil", "nis.go.kr"), ("ubldigital.com", "uob.com.my"),
                            ("smrc.co.jp", "smfg.co.jp"), ("uweei.org.sg", "ntuc.org.sg"),
                            ("mufg.com", "mufg.jp")):
        m = _match(website, domain)
        assert (m["status"], m["matched_by"]) == ("matched", "confirmed_alias"), website
        assert m["provider_domain"] == website


def test_a_confirmed_alias_is_for_its_own_account_only():
    # nga.mil is accepted for NIS Korea, not for any other account.
    assert _match("nga.mil", "ntuc.org.sg")["status"] == "mismatch"


def test_a_different_company_stays_a_mismatch():
    for website, domain in (("acme-holdings.com", "astra.co.id"), ("nga.mil", "mod.gov.my")):
        m = _match(website, domain)
        assert (m["status"], m["matched_by"]) == ("mismatch", None), website


def test_lookalike_registered_domains_do_not_match():
    assert _match("posco-inc.com", "posco.com")["status"] == "mismatch"
