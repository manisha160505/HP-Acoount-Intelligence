"""Per-account overrides: what the client asked not to show, account by account.

Client, 8 Oct (open data gaps): remove Intent where there is no Bombora and every
HP category is 0, remove Tech Landscape for three government accounts, and show
no parent where Explorium holds it differently. These live in
config/account_overrides.yaml so the next decision is a YAML edit, not code.

Run: python -m pytest tests/test_account_overrides.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.feature_mapping import FEATURE_MAPPINGS
from app.config import account_overrides as ao

# --- the shipped file --------------------------------------------------------

def test_the_shipped_file_only_names_real_features():
    ao.validate_feature_keys(FEATURE_MAPPINGS)


def test_the_client_decisions_are_in_the_shipped_file():
    assert ao.is_hidden("MINISTRY OF DEFENCE - MY", "intent_demand_signals")
    assert ao.is_hidden("MINISTRY OF DEFENCE - MY", "tech_landscape")
    assert ao.is_hidden("YAMATO HOLDINGS CO.,LTD. - JP", "intent_demand_signals")
    assert not ao.is_hidden("YAMATO HOLDINGS CO.,LTD. - JP", "tech_landscape")
    assert ao.hides_parent("BHP BILLITON - AU")
    # 16 Intent, 3 Tech Landscape, 9 parents.
    entries = ao.OVERRIDES.values()
    assert sum("intent_demand_signals" in e["hidden_features"] for e in entries) == 16
    assert sum("tech_landscape" in e["hidden_features"] for e in entries) == 3
    assert sum(e["hide_parent_company"] for e in entries) == 9


def test_an_account_not_listed_hides_nothing():
    assert ao.hidden_features("ACCENTURE INC - PH") == frozenset()
    assert not ao.hides_parent("ACCENTURE INC - PH")
    assert ao.hidden_features(None) == frozenset()


def test_names_match_ignoring_case_and_spacing():
    assert ao.is_hidden("  ministry of   defence - my ", "TECH_LANDSCAPE")


# --- validation ---------------------------------------------------------------

@pytest.mark.parametrize("config, message", [
    ({"accounts": {"A": {"hide_parent": True}}}, "unknown field"),
    ({"accounts": {"A": {"hidden_features": "intent_demand_signals"}}}, "list of feature keys"),
    ({"accounts": {"A": {"hide_parent_company": "yes"}}}, "true or false"),
    ({"accounts": {"A": {}, " a ": {}}}, "listed twice"),
    ({"accounts": ["A"]}, "not a mapping"),
])
def test_a_malformed_file_is_refused(config, message):
    with pytest.raises(ao.AccountOverridesError, match=message):
        ao._parse(config)


def test_a_misspelt_feature_key_is_refused(monkeypatch):
    """The failure this exists to stop: a typo silently shows what the client
    asked us to hide."""
    monkeypatch.setattr(ao, "OVERRIDES",
                        ao._parse({"accounts": {"A": {"hidden_features": ["intnet"]}}}))
    with pytest.raises(ao.AccountOverridesError, match="intnet"):
        ao.validate_feature_keys(FEATURE_MAPPINGS)


# --- the parent, masked on read ----------------------------------------------

def test_the_parent_is_removed_for_a_listed_account():
    data = {"company_name": "BHP BILLITON - AU", "parent_company": "andeavor",
            "parent_company_source": "Company Hierarchy - Parent Company Name"}
    out = ao.masked("BHP BILLITON - AU", "exec_summary_card", data)
    assert out["parent_company"] == "" and out["parent_company_source"] is None
    assert out["company_name"] == "BHP BILLITON - AU"
    assert data["parent_company"] == "andeavor", "the stored copy is never mutated"


def test_other_accounts_and_widgets_are_untouched():
    data = {"parent_company": "wesfarmers"}
    assert ao.masked("ACCENTURE INC - PH", "exec_summary_card", data) is data
    assert ao.masked("BHP BILLITON - AU", "exec_key_metrics", data) is data


# --- the API ------------------------------------------------------------------

def test_the_account_response_carries_its_hidden_features():
    from datetime import UTC, datetime

    from app.api.v1.accounts import serialize_account
    doc = {"_id": "0" * 24, "name": "MINISTRY OF DEFENCE - VN",
           "created_at": datetime(2026, 1, 1, tzinfo=UTC),
           "updated_at": datetime(2026, 1, 1, tzinfo=UTC)}
    assert serialize_account(doc)["hidden_features"] == [
        "intent_demand_signals", "tech_landscape"]
    assert serialize_account({**doc, "name": "ACCENTURE INC - PH"})["hidden_features"] == []
