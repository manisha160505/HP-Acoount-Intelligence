"""Section F: the structured record behind every seller-facing output.

    "Generate a structured internal object first; then render the approved
    seller-facing fields in the UI. Each important claim must be traceable to
    its evidence IDs."

The property that matters is stability. An id derived from the claim survives a
regeneration that did not change the sentence, so "this is the claim that was on
the card yesterday" is answerable without storing anything.

Run: python -m pytest tests/test_output_record.py -v
"""

import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import output_record as orec

FEATURE = "tech_landscape"
ACCOUNT = "6a997c3b"


class TestIdsAreDerivedNotAllocated:
    def test_the_same_claim_keeps_its_id(self):
        first = orec.claim_id(FEATURE, ACCOUNT, "rule-10", "rationale", "Astra runs Autodesk.")
        second = orec.claim_id(FEATURE, ACCOUNT, "rule-10", "rationale", "Astra  runs Autodesk. ")
        assert first == second, "whitespace must not change a claim id"

    def test_a_changed_claim_gets_a_new_id(self):
        first = orec.claim_id(FEATURE, ACCOUNT, "rule-10", "rationale", "Astra runs Autodesk.")
        second = orec.claim_id(FEATURE, ACCOUNT, "rule-10", "rationale", "Astra runs Solidworks.")
        assert first != second

    def test_the_same_sentence_on_a_different_rule_is_a_different_claim(self):
        assert (orec.claim_id(FEATURE, ACCOUNT, "rule-10", "rationale", "x")
                != orec.claim_id(FEATURE, ACCOUNT, "rule-2", "rationale", "x"))

    def test_evidence_ids_are_stable_and_deduplicated(self):
        row = {"dataset": "technographics", "field": "Full Tech Stack", "text": "Autodesk"}
        out = orec.record(FEATURE, ACCOUNT, "2026-09-14", "text",
                          evidence_rows=[row, dict(row)])
        assert len(out["evidence_ids"]) == 1

    def test_a_registry_id_is_used_as_supplied(self):
        """The retrieval features already mint ids. Re-deriving one would give
        the same row two identities depending on which path found it."""
        out = orec.record(FEATURE, ACCOUNT, None, "t", evidence_rows=[
            {"evidence_id": "a6a997c3b_filings#c4", "text": "revenue rose"}])
        assert out["evidence_ids"] == ["a6a997c3b_filings#c4"]

    def test_an_empty_row_contributes_nothing(self):
        assert orec.record(FEATURE, ACCOUNT, None, "t",
                           evidence_rows=[{}, {"dataset": "x"}])["evidence_ids"] == []


class TestTheNineFields:
    def test_every_field_section_f_names_is_present(self):
        out = orec.record(FEATURE, ACCOUNT, "2026-09-14", "Buy the tower.",
                          claims={"rationale": "Astra runs Autodesk."},
                          evidence_rows=[{"dataset": "technographics", "text": "Autodesk"}],
                          hp_offering_ids=["10"], proof_ids=["cs_77"],
                          confidence_tier="Opportunity", scope="rule-10")
        for field in ("feature", "account_id", "as_of_date", "recommendation_text",
                      "claim_ids", "evidence_ids", "hp_offering_ids", "proof_ids",
                      "confidence_tier"):
            assert field in out, field
        assert out["confidence_tier"] == "Opportunity"
        assert out["hp_offering_ids"] == ["10"]

    def test_nothing_cited_is_an_empty_list_not_a_missing_key(self):
        """Section F marks these "When used". An empty list says the question
        was asked and the answer was none; a missing key cannot."""
        out = orec.record(FEATURE, ACCOUNT, None, "t")
        assert out["hp_offering_ids"] == []
        assert out["proof_ids"] == []

    def test_a_blank_claim_earns_no_id(self):
        out = orec.record(FEATURE, ACCOUNT, None, "t",
                          claims={"rationale": "", "why": "   ", "kept": "real"})
        assert len(out["claim_ids"]) == 1

    def test_claims_map_an_id_back_to_its_field(self):
        out = orec.record(FEATURE, ACCOUNT, None, "t",
                          claims={"rationale": "a", "why_this_product": "b"},
                          scope="rule-10")
        assert sorted(out["claims"].values()) == ["rationale", "why_this_product"]
        assert set(out["claims"]) == set(out["claim_ids"])

    def test_pre_derived_ids_join_the_ones_derived_from_rows(self):
        """A caller that kept only truncated rows for display derives its ids
        from the full text earlier and hands them in."""
        out = orec.record(FEATURE, ACCOUNT, None, "t",
                          evidence_rows=[{"dataset": "job_openings", "text": "CAD"}],
                          evidence_ids=["ev_abc123", "ev_abc123", ""])
        assert "ev_abc123" in out["evidence_ids"]
        assert len(out["evidence_ids"]) == 2


class TestRecommendationCardsCarryTheRecord:
    """Section F on the cards themselves, both parts."""

    def test_part_b_card_carries_all_nine_fields(self, monkeypatch):
        from app.services.hp import lifecycle, recommendations as rec

        monkeypatch.setattr(lifecycle, "load", lambda *_a, **_k: [])
        rule = {"rule_label": "WOLF 09", "signal_text": "endpoint protection",
                "offering": "HP Wolf Pro Security", "family": "WOLF",
                "evidence_source": "rulebook",
                "allowed_facts": [
                    "Recommend Wolf Pro Security when HP software must operate "
                    "as the primary endpoint protection.",
                    "Wolf Pro Security is positioned for small and medium "
                    "business endpoints."]}
        match = {"rule": rule, "rule_label": "WOLF 09", "family": "WOLF",
                 "offering": "HP Wolf Pro Security", "evidence_indices": [0],
                 "matched_terms": ["kaspersky"], "qualifying_terms": ["kaspersky"]}
        book = {}
        # The families a category can carry are derived from its own vendor
        # cards, not from a hand-typed list on the category.
        categories = [{"category_key": "security", "category_name": "IT Security",
                       "vendors": [{"name": "Kaspersky",
                                    "hp_play": {"product": "HP Wolf Security"}}]}]
        items = [{"dataset": "technographics", "field": "vendor", "text": "Kaspersky"}]

        cards = rec._part_b_cards(book, [match], categories, "India",
                                 datetime.now(UTC), items, {},
                                 ACCOUNT, "2026-09-14")
        assert cards, "the rule's own allowed facts should survive the guardrails"
        out = cards[0]["output_record"]
        assert out["feature"] == "tech_landscape"
        assert out["account_id"] == ACCOUNT
        assert out["as_of_date"] == "2026-09-14"
        assert out["hp_offering_ids"] == ["WOLF 09"]
        assert out["confidence_tier"] == cards[0]["confidence_tier"]
        assert out["evidence_ids"]

    def test_a_claim_id_survives_a_regeneration_that_did_not_change_the_text(self):
        """The point of deriving rather than allocating: yesterday's card and
        today's rebuild name the same claim by the same id."""
        first = orec.record("tech_landscape", ACCOUNT, "2026-09-14", "text",
                            claims={"rationale": "Astra runs Autodesk."},
                            scope="10")
        again = orec.record("tech_landscape", ACCOUNT, "2026-09-21", "text",
                            claims={"rationale": "Astra runs Autodesk."},
                            scope="10")
        assert first["claim_ids"] == again["claim_ids"]

        changed = orec.record("tech_landscape", ACCOUNT, "2026-09-14", "text",
                              claims={"rationale": "Astra runs Ansys."},
                              scope="10")
        assert changed["claim_ids"] != first["claim_ids"]
