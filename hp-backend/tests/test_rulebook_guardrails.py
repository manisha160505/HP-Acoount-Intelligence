"""The rulebook's country restrictions, against what the code enforces.

Part C blocks two kinds of claim by market: restricted superlatives, and the
Lenovo comparison from the competitive playbook. Both lists live in
`services/hp/guardrails.py` as module constants and must stay there - two
features import them at module scope, and a database read would make an import
depend on Mongo. So the document is loaded as the *authority* and the constants
are checked against it rather than replaced by it.

These are not hypothetical. Both live accounts are in Indonesia, which is on
**both** lists.

Run: python -m pytest tests/test_rulebook_guardrails.py -v
"""

import os
import sys
from typing import ClassVar

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import rulebook as rb
from app.services.hp.guardrails import (
    COMPETITOR_BLOCK_COUNTRIES,
    SUPERLATIVE_BLOCK_COUNTRIES,
    approve_rulebook_facts,
    normalize_country,
    prose_guardrail_faults,
)


def book_with(superlative=(), competitor=(), aliases=None):
    def row(restriction, countries):
        return {"_id": "country_list::%s" % restriction, "kind": "country_list",
                "restriction": restriction,
                "countries": list(countries),
                "countries_folded": sorted({c.lower() for c in countries}),
                "aliases": dict(aliases or {}), "notes": []}
    return {"rules": [], "routing": [], "matrices": {}, "guardrails": [],
            "country_lists": {"superlative": row("superlative", superlative),
                              "competitor": row("competitor", competitor)}}


class TestTheLiveAccountsMarket:
    """Astra is Indonesian. What may and may not be said about it."""

    def test_indonesia_blocks_restricted_superlatives(self):
        assert "indonesia" in {c.lower() for c in SUPERLATIVE_BLOCK_COUNTRIES}

    def test_indonesia_also_blocks_the_lenovo_comparison(self):
        """Worth pinning because it was got wrong once. The competitor list is
        88 countries in the document and reads as a short Middle East and CIS
        list if you only see the first line of the cell - Indonesia is further
        down it."""
        assert "indonesia" in {c.lower() for c in COMPETITOR_BLOCK_COUNTRIES}

    def test_a_country_on_neither_list_is_unrestricted(self):
        blocked = ({c.lower() for c in SUPERLATIVE_BLOCK_COUNTRIES}
                   | {c.lower() for c in COMPETITOR_BLOCK_COUNTRIES})
        assert "singapore" not in blocked
        assert "japan" not in blocked


class TestReadingAnAccountsCountry:

    @pytest.mark.parametrize("raw,expected", [
        ("indonesia", "indonesia"),
        ("Jakarta, Indonesia", "indonesia"),
        ("  INDONESIA  ", "indonesia"),
    ])
    def test_an_hq_string_resolves_to_its_country(self, raw, expected):
        assert normalize_country(raw) == expected

    def test_an_empty_location_resolves_to_nothing(self):
        assert normalize_country("") == ""
        assert normalize_country(None) == ""


class TestTheDocumentIsTheAuthority:
    """`blocked_countries` exposes the document's own list so a test - and
    `scripts/verify_rulebook.py` - can compare it with what ships."""

    def test_the_document_list_is_readable(self):
        book = book_with(superlative=["Romania", "Indonesia"])
        assert rb.blocked_countries(book, "superlative") == {"romania", "indonesia"}

    def test_an_unloaded_rulebook_reports_nothing_rather_than_raising(self):
        empty = {"rules": [], "routing": [], "matrices": {}, "guardrails": [],
                 "country_lists": {}}
        assert rb.blocked_countries(empty, "superlative") == set()

    def test_every_country_the_document_names_is_enforced_in_code(self):
        """The direction that matters. A country in the document but not in the
        constant is a claim we would make where HP has forbidden it; the
        reverse is only over-blocking, which is safe."""
        book = book_with(
            superlative=["Romania", "Indonesia", "Turkey"],
            competitor=["Romania", "Indonesia", "Saudi Arabia"])
        for restriction, constant in (("superlative", SUPERLATIVE_BLOCK_COUNTRIES),
                                      ("competitor", COMPETITOR_BLOCK_COUNTRIES)):
            document = rb.blocked_countries(book, restriction)
            enforced = {c.lower() for c in constant}
            assert document <= enforced, sorted(document - enforced)

    def test_uzbekistan_is_blocked_for_superlatives_by_the_code_not_the_document(self):
        """A real, deliberate discrepancy. The document's superlative list does
        not name Uzbekistan - its CIS sweep attaches to the competitor list
        only - and the shipped constant does. Over-blocking, so safe, and
        pinned here so the next reader knows it is a decision rather than a
        drift."""
        assert "uzbekistan" in {c.lower() for c in SUPERLATIVE_BLOCK_COUNTRIES}

    def test_the_cis_sweep_is_prose_not_a_list(self):
        """The document ends its competitor cell with "Also block in any CIS
        country covered by the playbook restriction", which is why the shipped
        constant names Armenia, Belarus and Kazakhstan and the literal list
        does not. The loader keeps that sentence as a note."""
        for country in ("armenia", "belarus", "kazakhstan"):
            assert country in {c.lower() for c in COMPETITOR_BLOCK_COUNTRIES}


def a_rule(facts, conditions=(), label="8", competitor=False):
    return {"rule_label": label, "part": "A",
            "allowed_facts": list(facts),
            "conditions": [{"text": c, "condition_type": "unclassified"}
                           for c in conditions],
            "requires_exact_competitor": competitor}


class TestGuardrailsOnARulebookFact:
    """The same filter the deck path uses, applied to a rule's own facts, and
    returning the same `FactDecision` objects - so `recommendations.py`,
    Strategy Chat, the evaluator, the dashboard and `audit_grounding.py` all
    keep working without knowing which corpus a fact came from."""

    def test_a_plain_fact_survives(self):
        approved, rejected = approve_rulebook_facts(
            a_rule(["Intel Core Ultra 5/7 Series 2 processors."]), "Indonesia")
        assert len(approved) == 1
        assert rejected == []

    def test_a_superlative_is_withheld_in_a_blocked_market(self):
        rule = a_rule(["The world's most secure business PC."])
        assert approve_rulebook_facts(rule, "Indonesia")[0] == []
        assert approve_rulebook_facts(rule, "Singapore")[0] != []

    def test_a_competitor_comparison_is_withheld_in_a_blocked_market(self):
        """Part A rule 8 is the Lenovo playbook and Indonesia is on the
        competitor list, so every one of its claims is withheld there while
        the same rule is usable in Singapore."""
        rule = a_rule(
            ["Up to 85% higher CPU performance than the ThinkPad X1 Carbon "
             "on the cited Cinebench 2024 comparison."],
            competitor=True)
        assert approve_rulebook_facts(rule, "Indonesia")[0] == []
        assert approve_rulebook_facts(rule, "Singapore")[0] != []

    def test_a_comparison_without_its_benchmark_is_withheld_anywhere(self):
        rule = a_rule(["Up to 85% higher CPU performance than the competitor."],
                      competitor=True)
        approved, rejected = approve_rulebook_facts(rule, "Singapore")
        assert approved == []
        assert rejected[0].guardrail == "G5 benchmark context"

    def test_a_configuration_feature_needs_its_qualifier(self):
        """G6/G7. "Optional means optional" is C 05 in the rulebook's own
        words, and a 5G claim with no mention of the module or the carrier
        presents an optional feature as standard."""
        bare = a_rule(["5G connectivity for the mobile workforce."])
        assert approve_rulebook_facts(bare, "Singapore")[0] == []

        qualified = a_rule(
            ["5G connectivity for the mobile workforce."],
            conditions=["Only where an optional 5G module is configured at the "
                        "factory and carrier service is available."])
        assert approve_rulebook_facts(qualified, "Singapore")[0] != []

    def test_the_rules_conditions_travel_with_every_fact_it_keeps(self):
        """C 04: keep every condition written in the applicable rule."""
        rule = a_rule(["Up to 64GB memory."],
                      conditions=["Where supported by the configuration."])
        approved, _r = approve_rulebook_facts(rule, "Singapore")
        assert approved[0].as_dict()["conditions"] == [
            "Where supported by the configuration."]

    def test_the_output_shape_matches_the_deck_path(self):
        """Five features read these dicts and none should need to know the
        fact came from the rulebook rather than a deck."""
        approved, _r = approve_rulebook_facts(
            a_rule(["Intel Core Ultra processors."]), "Singapore")
        entry = approved[0].as_dict()
        assert set(entry) >= {"slide_id", "kept", "text", "qualifiers", "conditions"}
        assert entry["kept"] is True


class TestProseGuardrails15And16:
    """Both were defined and never called. A figure can be correctly sourced
    and still be used to make a claim the document forbids."""

    FACTS: ClassVar[list] = [
        {"text": "13 TOPS NPU", "conditions": []},
        {"text": "Up to Intel Core Ultra 9", "conditions": []},
    ]

    def test_g15_blocks_a_below_40_tops_next_gen_claim(self):
        """Rule 10's own fact is "13 TOPS NPU", and the rulebook fixes the
        classes: Next Gen AI PC is 40-60 TOPS, and a below-40-TOPS product may
        not be labelled one.
        """
        faults = prose_guardrail_faults(
            "The Elite tower is a Next Gen AI PC with 13 TOPS NPU.", self.FACTS)
        assert faults and "G15" in faults[0]

    def test_g15_allows_the_claim_inside_the_band(self):
        assert prose_guardrail_faults(
            "A Next Gen AI PC with up to 50 TOPS.",
            [{"text": "up to 50 TOPS", "conditions": []}]) == []

    def test_g15_says_nothing_without_a_figure(self):
        """The class alone is not a violation - only a class contradicted by a
        figure beside it."""
        assert prose_guardrail_faults(
            "Positioned as a Next Gen AI PC.", self.FACTS) == []

    def test_g16_blocks_a_generation_the_facts_never_state(self):
        """The document's own example: a fact for EliteBook 8 G1i is not
        automatically valid for EliteBook 8 G2.
        """
        faults = prose_guardrail_faults(
            "The EliteBook 8 G1i delivers this.", self.FACTS)
        assert faults and "G16" in faults[0]

    def test_g16_allows_a_generation_the_facts_do_state(self):
        assert prose_guardrail_faults(
            "The EliteBook 6 G2 delivers this.",
            [{"text": "EliteBook 6 G2 variants", "conditions": []}]) == []

    def test_a_form_factor_word_is_not_a_mixed_record(self):
        """An earlier version matched "desktop" and flagged calling a tower a
        desktop, which is ordinary English rather than a mixed record."""
        assert prose_guardrail_faults(
            "A desktop for engineering workloads.", self.FACTS) == []

    def test_empty_prose_is_not_a_fault(self):
        assert prose_guardrail_faults("", self.FACTS) == []
        assert prose_guardrail_faults(None, self.FACTS) == []


class TestARefusedRuleSaysWhereItWouldHaveAppeared:
    """A category reading "no HP client hardware detected" with nothing under it
    is where a seller asks why nothing was recommended. The answer used to sit
    at the foot of the page under a heading about something else, so the
    refusal carries the category it would have filled."""

    def test_a_notebook_rule_points_at_the_pc_category(self):
        from app.services.hp.recommendations import _blocked_placement
        out = _blocked_placement("2")
        assert out["category_key"] == "pc_laptop_brands"
        assert out["category_name"] == "PC/Laptop Brands"

    def test_a_rule_with_no_device_type_has_no_category(self):
        """It then stays in the general list rather than being filed under a
        category the bridge never connected it to."""
        from app.services.hp.recommendations import _blocked_placement
        out = _blocked_placement("7")
        assert out["category_key"] is None

    def test_a_part_b_label_is_not_forced_into_a_hardware_category(self):
        from app.services.hp.recommendations import _blocked_placement
        assert _blocked_placement("WOLF 09")["category_key"] is None
