"""The Tech Landscape confidence, pinned to the client's specification.

`HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx` defines two drivers and
one formula. This file pins both drivers, the formula, and - most importantly -
the guardrail that decides whether a card exists at all.

The document carries two worked examples, and both are reproduced here as
acceptance tests rather than described:

    Driver 1: Windows detected -> WXP 04 accepts a Windows estate -> 10/10
    Driver 2: Astra 3D Printers intent = 34 -> 25-49 band          ->  5/10
    Formula:  [(10 x 0.70) + (5 x 0.30)] x 10                      ->  85%

The suppression tests matter more than the arithmetic ones. A wrong percentage
is visible and arguable; a card that should never have been created looks
exactly like a real finding, and the seller has no way to tell.

Run: python -m pytest tests/test_tech_confidence.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from typing import ClassVar

from app.services.hp import intent_topic_map as tm, tech_confidence as tc


class TestTheDocumentsWorkedExamples:
    """Both examples, end to end, deriving each driver rather than asserting it."""

    def test_windows_scores_a_direct_fit_through_wxp_04(self):
        """"Astra has Microsoft Windows explicitly detected in its technographic
        data. Therefore, Astra satisfies the Windows estate condition in WXP 04."
        """
        points, basis, matched = tc.driver_1_technology(
            ["Microsoft Windows OS"], route=tc.ROUTE_WXP)
        assert points == 10
        assert matched["rule"] == "WXP 04"
        assert "WXP 04" in basis

    def test_astras_3d_intent_of_34_scores_five(self):
        """"34 falls in the 25-49 band -> Driver 2 = 5/10.\""""
        points, basis = tc.driver_2_intent(34, tm.CAT_3D)
        assert points == 5
        assert "34" in basis

    def test_the_two_together_give_eighty_five_percent(self):
        """"Driver 1 = 10 and Driver 2 = 5 -> [(10 x 0.70) + (5 x 0.30)] x 10
        = 85%.\""""
        d1, _basis, _m = tc.driver_1_technology(["Microsoft Windows OS"],
                                                route=tc.ROUTE_WXP)
        d2, _basis2 = tc.driver_2_intent(34, tm.CAT_3D)
        assert tc.confidence(d1, d2) == 85

    def test_azure_is_related_evidence_not_a_direct_fit(self):
        """The document's own reasoning for the 5 band:

        "Azure indicates a Microsoft/cloud technology environment, but the WXP
        rule specifically names technologies such as Microsoft Intune, Microsoft
        Entra ID, Power BI and Power Automate - not Microsoft Azure itself."
        """
        points, basis, matched = tc.driver_1_technology(
            ["Microsoft Azure"], route=tc.ROUTE_WXP)
        assert points == 5
        assert matched["fit"] == "related"
        assert "related" in basis

    def test_vmware_against_a_3d_card_scores_nothing(self):
        """"VMware does not establish a 3D Printing technology opportunity and
        the HP Rulebook provides no supported connection -> 0/10." There is no
        3D route in the rulebook table, so no rule can reach it."""
        points, _basis, _m = tc.driver_1_technology(["VMware"], route="HP 3D Printing")
        assert points == 0


class TestTheSuppressionGuardrail:
    """"If Driver 1 = 0, do not create the Tech Landscape card. Intent may
    strengthen an evidence-backed opportunity, but intent alone cannot prove
    that a technology is present."
    """

    def test_a_zero_technology_driver_means_no_card(self):
        assert tc.is_publishable(0) is False

    def test_a_related_fit_is_enough_to_publish(self):
        assert tc.is_publishable(5) is True
        assert tc.is_publishable(10) is True

    def test_maximum_intent_cannot_rescue_a_card_with_no_technology_fit(self):
        """The failure the guardrail exists to stop. A perfect intent score
        still leaves 30% of a card built on nothing, and it must not render."""
        d1, _basis, _m = tc.driver_1_technology(["Some Unrelated CRM"],
                                                route=tc.ROUTE_WXP)
        d2, _b2 = tc.driver_2_intent(100, tm.CAT_PC)
        assert d1 == 0
        assert d2 == 10
        assert tc.is_publishable(d1) is False, "intent alone must never publish a card"

    def test_the_gate_is_not_the_percentage(self):
        """A caller reading only the score would publish this at 30%."""
        assert tc.confidence(0, 10) == 30
        assert tc.is_publishable(0) is False


class TestDriver2Bands:
    """"Score 10/10 for 50-100, 5/10 for 25-49, and 0/10 for 0-24 or missing.\""""

    @pytest.mark.parametrize("score,expected", [
        (100, 10), (75, 10), (50, 10),      # 50-100
        (49, 5), (34, 5), (25, 5),          # 25-49
        (24, 0), (12, 0), (1, 0), (0, 0),   # 0-24
    ])
    def test_each_band_at_its_boundaries(self, score, expected):
        points, _basis = tc.driver_2_intent(score, tm.CAT_PC)
        assert points == expected, "%s should score %d" % (score, expected)

    def test_a_missing_score_is_in_the_bottom_band_not_unknown(self):
        """"0-24 or missing" - the document puts absence in the band itself."""
        points, basis = tc.driver_2_intent(None, tm.CAT_PC)
        assert points == 0
        assert "no intent score" in basis

    def test_a_missing_score_never_suppresses_a_card(self):
        """Driver 2 is a supporting signal. Only Driver 1 decides existence."""
        assert tc.is_publishable(10) is True      # regardless of driver 2

    def test_the_basis_names_the_category_it_read(self):
        _points, basis = tc.driver_2_intent(34, tm.CAT_3D)
        assert tm.CAT_3D in basis


class TestTheCategoryGuardrail:
    """"If the Tech Landscape card is Workstation, use Astra's Workstation
    Intent Score. Do not use the 3D Printers score of 34 for a Workstation card."

    This is the document's own named failure, so it is tested with Astra's real
    numbers: 3D scores 34, Workstation scores 2.
    """

    ASTRA: ClassVar[dict] = {tm.CAT_3D: 34, tm.CAT_WORKSTATION: 2,
                             tm.CAT_PRINT: 12, tm.CAT_POLY: 2, tm.CAT_PC: 0}

    def test_a_workstation_card_uses_the_workstation_score(self):
        category = tc.hp_category_for("workstations_compute")
        assert category == tm.CAT_WORKSTATION
        points, _basis = tc.driver_2_intent(self.ASTRA[category], category)
        assert points == 0, "Workstation scores 2, which is the bottom band"

    def test_it_does_not_borrow_the_3d_score(self):
        """Had the card taken 34, it would have scored 5 and read 15 points
        higher than the evidence supports."""
        category = tc.hp_category_for("workstations_compute")
        wrong, _b = tc.driver_2_intent(self.ASTRA[tm.CAT_3D], category)
        right, _b2 = tc.driver_2_intent(self.ASTRA[category], category)
        assert wrong == 5 and right == 0
        assert tc.confidence(10, right) == 70
        assert tc.confidence(10, wrong) == 85

    @pytest.mark.parametrize("category_key,expected", [
        ("pc_laptop_brands", tm.CAT_PC),
        ("workstations_compute", tm.CAT_WORKSTATION),
        ("collaboration_hybrid", tm.CAT_POLY),
        ("print_fleet", tm.CAT_PRINT),
    ])
    def test_each_card_category_maps_to_its_own_hp_category(self, category_key, expected):
        assert tc.hp_category_for(category_key) == expected

    @pytest.mark.parametrize("category_key", [
        "client_os", "uem_mdm", "it_security_parity"])
    def test_a_card_with_no_hp_category_scores_driver_2_zero(self, category_key):
        """"If none of the five available intent categories is relevant to the
        HP opportunity, Driver 2 = 0/10; do not force an unrelated intent
        category into the calculation."

        Wolf Security is the clearest case: it sells against it_security_parity
        and is not one of the five categories at all.
        """
        assert tc.hp_category_for(category_key) is None
        points, _basis = tc.driver_2_intent(None, tc.hp_category_for(category_key))
        assert points == 0

    def test_an_unknown_category_key_claims_no_hp_category(self):
        assert tc.hp_category_for("something_else") is None
        assert tc.hp_category_for("") is None


class TestTheFormula:

    def test_only_six_values_are_reachable_on_a_published_card(self):
        """Both drivers are 0/5/10 and Driver 1 = 0 is suppressed, so a card can
        only ever read one of six numbers. Anything else is a bug."""
        reachable = sorted({tc.confidence(d1, d2)
                            for d1 in (tc.RELATED_FIT, tc.DIRECT_FIT)
                            for d2 in tc.BAND_VALUES})
        assert reachable == [35, 50, 65, 70, 85, 100]

    def test_the_weights_are_seventy_thirty(self):
        assert tc.DRIVER_1_WEIGHT == 0.70
        assert tc.DRIVER_2_WEIGHT == 0.30

    def test_technology_evidence_outweighs_intent(self):
        """70/30 means a directly-supported card with no intent still outranks a
        merely-related card with perfect intent."""
        assert tc.confidence(10, 0) > tc.confidence(5, 10)

    def test_the_extremes(self):
        assert tc.confidence(10, 10) == 100
        assert tc.confidence(0, 0) == 0

    def test_the_result_is_a_whole_number(self):
        for d1 in tc.BAND_VALUES:
            for d2 in tc.BAND_VALUES:
                assert isinstance(tc.confidence(d1, d2), int)


class TestDriver1Matching:

    def test_a_named_technology_beats_a_related_one(self):
        """Both are present; the direct fit must win."""
        points, _basis, matched = tc.driver_1_technology(
            ["Microsoft Azure", "Microsoft Intune"], route=tc.ROUTE_WXP)
        assert points == 10
        assert matched["technology"] == "microsoft intune"

    def test_a_substring_does_not_establish_a_fit(self):
        """"teams" inside "Teamsystem" is not Microsoft Teams. Matching is on a
        word boundary, or an accidental substring would publish a card."""
        points, _basis, _m = tc.driver_1_technology(["Teamsystem ERP"],
                                                    route=tc.ROUTE_POLY)
        assert points == 0

    def test_the_route_narrows_the_question(self):
        """Poly is a direct fit for a Poly card and nothing for a WXP card."""
        assert tc.driver_1_technology(["Poly Studio"], route=tc.ROUTE_POLY)[0] == 10
        assert tc.driver_1_technology(["Poly Studio"], route=tc.ROUTE_WXP)[0] == 0

    def test_the_competitor_rule_needs_the_exact_model(self):
        """Part A rule 8 is explicit that a looser match must not reuse its
        claims."""
        assert tc.driver_1_technology(["Lenovo ThinkPad X1 Carbon Gen 13"],
                                      route=tc.ROUTE_COMPETE)[0] == 10
        assert tc.driver_1_technology(["Lenovo ThinkPad"],
                                      route=tc.ROUTE_COMPETE)[0] == 0

    def test_no_detection_at_all_scores_zero(self):
        points, basis, matched = tc.driver_1_technology([], route=tc.ROUTE_WXP)
        assert points == 0
        assert matched is None
        assert "no technology detected" in basis

    def test_the_basis_names_the_rule_that_decided_it(self):
        """A score a reader cannot trace to a rule is not auditable."""
        _points, basis, matched = tc.driver_1_technology(
            ["Intel vPro"], route=tc.ROUTE_SUPPORT)
        assert "CARE 10" in basis
        assert matched["rule"] == "CARE 10"

    def test_every_rulebook_row_carries_its_rule_and_route(self):
        for entry in tc.RULEBOOK_TECHNOLOGIES:
            assert entry["rule"], entry
            assert entry["route"], entry
            assert entry["names"], entry


class TestTheRelatedBandIsBroad:
    """The 5 band is wide, and 0 is rare. Getting this backwards emptied the map.

    A first implementation scored 5 only for members of a hand-written family
    list, so every technology the rulebook does not name fell to 0 and its card
    was suppressed. On Astra that removed 8 of 10 real cards - CAD software off
    the Workstations card, endpoint security off the IT Security card, Google
    Workspace off the Collaboration card.

    The document does not intend that. Its 5 band is "clearly related to the
    same technology environment/use case", and its only 0 example is a
    deliberate mismatch: VMware detected against a proposed 3D-printing card,
    where "the Rulebook provides no supported connection".

    The card's own category is the use case. A vendor is on the IT Security card
    because it is security software, and the HP opportunity there is Wolf
    Security - same environment, indirect relationship, which is a 5.
    """

    def test_cad_software_on_a_workstation_card_is_related(self):
        points, basis, _m = tc.driver_1_for_card(
            ["AutoCAD", "CATIA", "Solidworks"], None, "Z by HP Workstations")
        assert points == 5
        assert "same technology environment" in basis

    def test_ml_frameworks_on_a_workstation_card_are_related(self):
        assert tc.driver_1_for_card(
            ["PyTorch", "Keras"], None, "Z by HP Workstations")[0] == 5

    def test_rival_endpoint_security_on_a_wolf_card_is_related(self):
        """Kaspersky against Wolf Security is the same environment - that is
        what makes it a displacement opportunity worth showing."""
        assert tc.driver_1_for_card(
            ["Kaspersky", "Symantec Endpoint Protection"], None,
            "HP Wolf Security")[0] == 5

    def test_collaboration_software_on_a_poly_card_is_related(self):
        assert tc.driver_1_for_card(
            ["Google Workspace"], None, "Poly Collaboration")[0] == 5

    def test_a_named_technology_still_outranks_a_related_one(self):
        """The 10 band is unaffected - an explicit rulebook match still wins."""
        points, _basis, matched = tc.driver_1_for_card(
            ["Microsoft Windows OS"], tc.ROUTE_WXP, "HP Elite / Pro PCs")
        assert points == 10
        assert matched["rule"] == "WXP 04"

    def test_a_card_with_no_hp_opportunity_scores_zero(self):
        """The document's 0: nothing for the technology to be related to. A
        category the platform itself badges "no direct HP line" offers no
        opportunity, so the card is suppressed."""
        points, _basis, matched = tc.driver_1_for_card(
            ["Apple iOS"], None, None)
        assert points == 0
        assert matched is None
        assert tc.is_publishable(points) is False

    def test_no_detection_still_scores_zero(self):
        assert tc.driver_1_for_card([], None, "Z by HP Workstations")[0] == 0

    def test_most_cards_now_survive(self):
        """The shape of the outcome, not a single case. Given a category with an
        HP opportunity, every detected technology publishes - at 10 if the
        rulebook names it, at 5 otherwise."""
        estate = ["AutoCAD", "Kaspersky", "Google Workspace", "Atlassian",
                  "Cloudflare", "PyTorch", "Microsoft Intune"]
        published = [t for t in estate
                     if tc.is_publishable(
                         tc.driver_1_for_card([t], None, "HP Wolf Security")[0])]
        assert published == estate
