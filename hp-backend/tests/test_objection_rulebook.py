"""The Objection Playbook's HP claims, and refusing to make them.

The reframe is the sentence a seller says to a customer, and until the rulebook
was wired in it was the one place in this feature where HP was described from
the model's own knowledge: the prompt named six HP lines and asked for "the
concrete angle", and whatever came back about HP was unverified. The account
side had always been grounded. These tests are about the HP side.

Run: python -m pytest tests/test_objection_rulebook.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import objection_playbook as op


def facts(*texts):
    return [{"text": t, "qualifiers": [], "conditions": []} for t in texts]


def rules(*fact_texts):
    return [{"rule_label": "WXP 07", "offering": "WXP",
             "hp_line": "HP Workforce Experience Platform",
             "approved_facts": facts(*fact_texts), "withheld": "",
             "prohibitions": [], "matched_terms": ["power bi"]}]


class TestAnAreaReachesTheRulesThatCanAnswerIt:
    """Derived from the maps that already exist, so a family added to the
    rulebook reaches the right areas without a seventh hand-typed taxonomy."""

    def test_every_area_reaches_at_least_one_family(self):
        for area in op.AREA_CATEGORY_COLUMNS:
            assert op._area_families(area), area

    def test_each_area_reaches_the_families_that_speak_for_its_line(self):
        assert "WOLF" in op._area_families("Endpoint Security")
        assert "POLY" in op._area_families("Collaboration")
        assert {"PRINT", "SCAN"} <= op._area_families("Print / MPS")
        # Client-device objections are answered by the services that attach to
        # a client estate, not by a laptop model - Part A is the Technographic
        # Map's job.
        assert {"CARE", "DEPLOY"} <= op._area_families("Client Devices")

    def test_an_unknown_area_reaches_nothing(self):
        assert op._area_families("Quantum Computing") == frozenset()


class TestAnInventedHPClaimIsRefused:
    def test_an_integration_the_facts_never_name_is_a_fault(self):
        """WXP 07's approved facts list the integrations HP's material names
        and then say "Mention only the integration that matches the account
        evidence". The model read that as permission to substitute the
        account's own vendor and wrote that WXP "integrates with ManageEngine"
        - true about the account, invented about HP."""
        faults = op._claim_faults(
            "HP WXP integrates with ManageEngine to add insight.",
            rules("The supplied HP material names ServiceNow, Microsoft Intune, "
                  "Power BI, Power Automate and Tableau."),
            "indonesia")
        assert faults and "ManageEngine" in faults[0]

    def test_an_integration_the_facts_do_name_is_allowed(self):
        assert op._claim_faults(
            "HP WXP integrates with Microsoft Intune.",
            rules("The supplied HP material names ServiceNow, Microsoft Intune, "
                  "Power BI, Power Automate and Tableau."),
            "indonesia") == []

    def test_positioning_alongside_a_competitor_is_not_an_integration_claim(self):
        """A reframe's whole job is to place HP beside an incumbent. Words that
        claim no connection - complement, alongside, beside - must stay usable,
        or the feature cannot answer an objection at all."""
        assert op._claim_faults(
            "Wolf Pro Security can complement Kaspersky and Symantec Endpoint "
            "Protection on supported PCs.",
            rules("Recommend Wolf Pro Security for supported HP and non-HP "
                  "Windows 10 or Windows 11 PCs."),
            "indonesia") == []

    def test_an_area_with_no_rule_still_refuses_an_invented_integration(self):
        assert op._claim_faults(
            "HP connects to ManageEngine natively.", [], "indonesia")

    def test_an_adverb_does_not_hide_the_claim(self):
        """"Poly integrate SEAMLESSLY with Microsoft Teams" was written with no
        approved fact behind it and passed a check that required the verb and
        "with" to be adjacent."""
        assert op._claim_faults(
            "HP offers collaboration hardware like Poly that integrate "
            "seamlessly with platforms such as Microsoft Teams.",
            [], "indonesia", "Astra")

    def test_a_pronoun_does_not_hide_the_claim(self):
        """Nor did routing the claim through "it": "complement your existing
        ManageEngine setup by integrating with it, as noted in the supplied HP
        material" - which also attributed the invented claim to HP."""
        assert op._claim_faults(
            "WXP can complement your existing ManageEngine setup by "
            "integrating with it, as noted in the supplied HP material.",
            rules("The supplied HP material names ServiceNow, Microsoft "
                  "Intune, Power BI and Tableau."),
            "indonesia", "Astra")

    def test_hp_naming_its_own_product_is_not_an_integration_target(self):
        """The check asks what HP claims to connect TO. Reading "WXP" in "HP
        WXP integrates with Microsoft Intune" as an unapproved target would
        refuse the approved sentence along with the invented one."""
        assert op._claim_faults(
            "HP WXP integrates with Microsoft Intune.",
            rules("The supplied HP material names ServiceNow, Microsoft "
                  "Intune, Power BI and Tableau."),
            "indonesia", "Astra") == []

    def test_the_account_name_is_not_an_integration_target_either(self):
        assert op._claim_faults(
            "HP WXP integrates with Microsoft Intune across Astra.",
            rules("The supplied HP material names ServiceNow, Microsoft "
                  "Intune, Power BI and Tableau."),
            "indonesia", "Astra") == []


class TestOurOwnVocabularyStaysOutOfTheSellersMouth:
    def test_naming_the_dataset_is_a_fault(self):
        """"We cannot see a print vendor in your technographics" tells a buyer
        what our research does not contain. That is our gap to close, not
        theirs to hear about."""
        faults = op._claim_faults(
            "HP print services could help, even if no vendor is visible in "
            "your technographics data.", [], "indonesia")
        assert faults and "technographic" in faults[0]

    def test_ordinary_prose_is_untouched(self):
        assert op._claim_faults(
            "HP print services could surface costs you are not seeing today.",
            [], "indonesia") == []


class TestACardSaysWhereItsClaimCameFrom:
    def test_a_matched_rule_is_named_on_the_card(self):
        out = op._claim_provenance(rules("Some approved fact."))
        assert out["hp_claim_source"] == "rulebook"
        assert out["hp_claim_rules"][0]["rule_label"] == "WXP 07"
        assert out["hp_claim_note"] is None

    def test_no_match_says_so_rather_than_leaving_it_blank(self):
        """C 07: label the missing condition clearly. A card with no HP claim
        should read as a deliberate silence, not an oversight."""
        out = op._claim_provenance([])
        assert out["hp_claim_source"] is None
        assert out["hp_claim_rules"] == []
        assert "No HP rulebook offering" in out["hp_claim_note"]
