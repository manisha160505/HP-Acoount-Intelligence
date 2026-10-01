"""The eight buying personas, and the table that says who may be sold what.

Transcribed from HP 220 - Content Studio & Message Evaluator - Build
Specification v1.0 (30 Sep 2026). Both Content Studio and the Message
Evaluator read this pack, so an error here is an error in two features at
once.

The specification is blunt about why the eligibility matrix exists, and it is
worth repeating where the tests live:

    The most likely failure of this product is not a hallucinated number -
    Rule 2 already catches those mechanically. It is a perfectly fluent,
    perfectly grounded email that pitches a Poly video bar to a CFO. That
    output passes every check currently in place, and it is the one output
    that makes a seller stop trusting the tool. The CFO row is the row that
    pays for this table.

So `test_a_cfo_is_never_offered_poly` is the test that pays for this file.

Run: python -m pytest tests/test_buyer_personas.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.grounding import HP_PRODUCT_LINES
from app.services.hp import buyer_personas as bp

SPEC_PERSONA_IDS = ("vp-it", "cfo", "it-asset-manager", "head-procurement",
                    "it-security-manager", "device-lifecycle-manager",
                    "pc-fleet-standards-owner", "av-collaboration-manager")


# ---------------------------------------------------------------------------
# The eight
# ---------------------------------------------------------------------------

def test_the_pack_holds_exactly_the_eight_the_client_named():
    assert bp.PERSONA_IDS == SPEC_PERSONA_IDS


def test_the_id_is_the_key_not_the_title():
    """The specification: "Never key off the display title - HP may reword a
    title, and a reworded title must not silently change behaviour"."""
    for persona_id in bp.PERSONA_IDS:
        assert bp.card(persona_id)["persona_id"] == persona_id


def test_an_unknown_persona_raises_rather_than_defaulting():
    """A silent default would write content to the wrong buyer."""
    with pytest.raises(bp.UnknownPersona):
        bp.card("cto")


def test_every_card_carries_the_fields_both_features_read():
    needed = ("title", "department", "committee_angle", "evidence_grade", "remit",
              "goals", "pain_points", "value_drivers", "decision_criteria",
              "typical_objections", "resonates", "does_not_resonate",
              "content_preferences", "hp_opportunity", "behavioural_state",
              "fast_track_trigger", "key_blocker", "confidence_explanation")
    for persona_id in bp.PERSONA_IDS:
        card = bp.card(persona_id)
        for field in needed:
            assert card.get(field), "%s is missing %s" % (persona_id, field)
        prefs = card["content_preferences"]
        assert prefs["tone"] and prefs["format"] and prefs["key_metrics"]


# ---------------------------------------------------------------------------
# Section 2.3 - the eligibility matrix
# ---------------------------------------------------------------------------

def test_a_cfo_is_never_offered_poly():
    """The row the specification says pays for the whole table.

    A fluent, grounded email pitching a video bar to a CFO passes every other
    check we have. This is the one that stops it.
    """
    for line in ("Poly Collaboration", "Poly Studio"):
        assert not bp.is_line_allowed("cfo", line)
        assert line in bp.denied_lines("cfo")


def test_poly_is_allowed_to_exactly_one_persona():
    """Spec 5.8: "the only persona of the eight where Poly is the lead"."""
    allowed = [p for p in bp.PERSONA_IDS
               if bp.is_line_allowed(p, "Poly Studio")]
    assert allowed == ["av-collaboration-manager"]


def test_the_standards_owner_is_never_offered_print():
    """Acceptance test T10's precondition."""
    assert not bp.is_line_allowed("pc-fleet-standards-owner",
                                  "HP Enterprise Print / MPS")


def test_3d_printing_is_denied_to_every_persona():
    """It appears in no ALLOWED set in the specification - eight rows, eight
    denials. A line nobody may be offered is worth stating as a property."""
    for persona_id in bp.PERSONA_IDS:
        assert not bp.is_line_allowed(persona_id, "HP Multi Jet Fusion (3D)")


def test_the_matrix_speaks_the_product_enum_s_own_names():
    """Otherwise the eligibility gate and the existing hp_products filter
    disagree, and a line denied here sails through there under another
    spelling."""
    canonical = set(HP_PRODUCT_LINES)
    for persona_id in bp.PERSONA_IDS:
        for line in bp.ALLOWED_LINES[persona_id] + bp.DENIED_LINES[persona_id]:
            assert line in canonical, "%s: %r is not an HP_PRODUCT_LINES name" % (
                persona_id, line)


def test_no_line_is_both_allowed_and_denied():
    for persona_id in bp.PERSONA_IDS:
        clash = set(bp.ALLOWED_LINES[persona_id]) & set(bp.DENIED_LINES[persona_id])
        assert not clash, "%s: %s" % (persona_id, clash)


def test_every_persona_has_both_halves_of_the_matrix():
    assert set(bp.ALLOWED_LINES) == set(bp.PERSONA_IDS)
    assert set(bp.DENIED_LINES) == set(bp.PERSONA_IDS)
    for persona_id in bp.PERSONA_IDS:
        assert bp.ALLOWED_LINES[persona_id], "%s allows nothing" % persona_id


def test_a_qualified_line_carries_its_qualification():
    """The matrix allows some lines only in one framing. Losing the framing
    between the table and the code is how a CFO gets sold a device."""
    assert "financing" in bp.qualifier("cfo", "HP Anyware / DaaS")
    assert "fleet-level" in bp.qualifier("cfo", "HP Elite / Pro PCs")
    assert "engineering" in bp.qualifier("vp-it", "Z by HP Workstations")
    # The Gatekeeper's wildcard covers every line it is offered.
    assert "commercial wrapper" in bp.qualifier("head-procurement",
                                                "HP Care Pack Services")


# ---------------------------------------------------------------------------
# Section 2.2 - the committee angle
# ---------------------------------------------------------------------------

def test_every_persona_carries_one_of_the_four_angles():
    for persona_id in bp.PERSONA_IDS:
        assert bp.angle(persona_id) in bp.ANGLES


def test_the_angles_are_the_ones_the_client_assigned():
    assert bp.angle("vp-it") == bp.ANGLE_ECONOMIC
    assert bp.angle("cfo") == bp.ANGLE_FINANCE
    assert bp.angle("head-procurement") == bp.ANGLE_GATEKEEPER
    # Both flagged SIGN-OFF REQUIRED; conservative defaults until HP rules.
    assert bp.angle("pc-fleet-standards-owner") == bp.ANGLE_TECHNICAL
    assert bp.angle("av-collaboration-manager") == bp.ANGLE_TECHNICAL


def test_each_angle_bounds_the_ask():
    """A Gatekeeper is never pitched, a Finance owner never quoted a price."""
    gate = bp.ask_bound("head-procurement")
    assert "process" in gate["may_ask"]
    assert any("product pitch" in n for n in gate["never"])

    finance = bp.ask_bound("cfo")
    assert any("price" in n for n in finance["never"])
    assert any("budget" in n for n in finance["never"])

    technical = bp.ask_bound("it-security-manager")
    assert "pilot" in technical["may_ask"]
    assert any("decision" in n for n in technical["never"])

    # The Economic Buyer is the only one with no prohibition.
    assert bp.ask_bound("vp-it")["never"] == ()


# ---------------------------------------------------------------------------
# Section 4.9 - the behavioural state machine
# ---------------------------------------------------------------------------

def test_every_entry_state_is_a_defined_state():
    for persona_id in bp.PERSONA_IDS:
        assert bp.card(persona_id)["behavioural_state"] in bp.BEHAVIOURAL_STATES


def test_the_deep_state_carries_what_the_prompt_needs():
    state = bp.behavioural_state("cfo")
    assert state["name"] == "INITIAL_SKEPTICISM"
    assert state["trust_level"] == 0.3
    assert state["response_bias"] == "Critical"
    assert state["messaging_approach"] and state["fast_track_trigger"]
    assert state["key_blocker"]


def test_every_transition_names_states_that_exist():
    for source, _trigger, target in bp.STATE_TRANSITIONS:
        assert source in bp.BEHAVIOURAL_STATES
        assert target in bp.BEHAVIOURAL_STATES


# ---------------------------------------------------------------------------
# Section 3.3 - what generation is allowed to see
# ---------------------------------------------------------------------------

def test_generation_gets_the_remit_and_not_the_pain_points():
    """The specification's own warning, and the reason this function is narrow:

        Do not put the persona's goals, pain points, value drivers or decision
        criteria into this slot. They belong to the Message Evaluator card...
        Injecting them here causes the model to write the persona's pain
        points back to the persona as if they were account evidence, which
        reads as presumption.
    """
    labels = dict(bp.generation_evidence("it-security-manager"))
    assert set(labels) == {"P1", "P2", "P3", "P4", "P5"}
    blob = " ".join(labels.values()).lower()
    assert "role:" in blob and "buying-committee angle" in blob

    card = bp.card("it-security-manager")
    for pain in card["pain_points"]:
        assert pain.lower() not in blob
    for goal in card["goals"]:
        assert goal.lower() not in blob


def test_generation_evidence_leaves_room_for_the_contact():
    """[P6] and [P7] are the contact's name and actual title, added by the
    caller only when the role is filled - never emitted empty."""
    labels = [label for label, _text in bp.generation_evidence("cfo")]
    assert "P6" not in labels and "P7" not in labels


# ---------------------------------------------------------------------------
# Section 8 - what HP has not confirmed
# ---------------------------------------------------------------------------

def test_the_unconfirmed_rows_are_visible_in_code():
    """Spec Section 8 lists five blocking sign-off items. They are recorded
    here so an unconfirmed position is visible to whoever reads the data,
    rather than living only in a document."""
    assert bp.MATRIX_CONFIRMED_BY_HP is False
    assert "pc-fleet-standards-owner" in bp.SIGN_OFF_REQUIRED
    assert "av-collaboration-manager" in bp.SIGN_OFF_REQUIRED
    assert bp.OPEN_WITH_CLIENT


def test_the_thinnest_card_says_so():
    """Persona 7 is the least evidenced of the eight and the specification asks
    for a human to read it before it ships."""
    card = bp.card("pc-fleet-standards-owner")
    assert "SIGN-OFF REQUIRED" in card["evidence_grade"]
    assert "hypothesis" in card["confidence_explanation"]


def test_the_card_is_hardcoded_and_says_so():
    """Spec 4.3: the footer must not claim account-level sourcing for content
    that is the same on all 220 accounts."""
    assert bp.PERSONA_CARD_SOURCE == "HARDCODED"
    footer = bp.data_sources_footer()
    assert set(footer.values()) == {"Persona library v1.0 (hardcoded)"}


def test_the_same_persona_is_identical_whoever_asks():
    """Acceptance test T19: the card is a persona reference, not account
    intelligence, so it cannot vary between accounts or sessions."""
    assert bp.card("cfo") is bp.card("cfo")
    assert bp.generation_evidence("cfo") == bp.generation_evidence("cfo")


class TestTheFourPolyLines:
    """HP confirmed on 1 Oct that Poly Lens and HP Poly Room Compute are
    sellable lines, not features inside Poly Studio.

    Spec 2.3 offers the AV & Collaboration Systems Manager five lines. The pack
    could only offer three, because the other two had no entry in the shared
    product enum - carried in OPEN_WITH_CLIENT until HP answered.
    """

    POLY = ("Poly Collaboration", "Poly Studio", "Poly Lens",
            "HP Poly Room Compute")

    def test_all_four_are_nameable(self):
        from app.services.extractors.grounding import HP_PRODUCT_LINES
        for line in self.POLY:
            assert line in HP_PRODUCT_LINES

    def test_each_one_resolves_to_itself(self):
        """The catch-all that would have swallowed them.

        `HP_LINE_TOKENS` carries a bare ("poly",) rule, so before the specific
        rules existed a model returning "Poly Lens" was stored as "Poly
        Collaboration" - the names would have been in the list and unreachable
        through the resolver, and the distinction spec 2.3 draws would have
        been lost on the way in. "Poly Studio" was already in that position.
        """
        from app.services.extractors.grounding import normalize_hp_product
        for line in self.POLY:
            assert normalize_hp_product(line) == line, line

    def test_an_unqualified_poly_still_falls_to_collaboration(self):
        """The catch-all is still a catch-all; it is just last now."""
        from app.services.extractors.grounding import normalize_hp_product
        for text in ("poly headsets", "a Poly speakerphone", "Poly"):
            assert normalize_hp_product(text) == "Poly Collaboration"

    def test_the_av_manager_is_offered_the_five_the_matrix_gives(self):
        assert bp.allowed_lines("av-collaboration-manager") == (
            "Poly Collaboration", "Poly Studio", "Poly Lens",
            "HP Poly Room Compute", "HP Care Pack Services")

    def test_poly_all_means_all_four(self):
        """Spec 2.3 writes "Poly (all)" in five DENIED rows. A Poly line that
        is nameable but missing from those rows is a line a CFO could be sent:
        allowed nowhere, denied nowhere, and so never rejected."""
        assert set(bp.ALL_POLY) == set(self.POLY)
        for persona_id in bp.PERSONA_IDS:
            denied = set(bp.denied_lines(persona_id))
            overlap = denied & set(self.POLY)
            if overlap:
                assert overlap == set(self.POLY), (
                    "%s denies only part of Poly: %s" % (persona_id, sorted(overlap)))

    def test_no_hp_line_is_nameable_everywhere_and_deniable_nowhere(self):
        """The general form of the bug the two missing lines created."""
        from app.services.extractors.grounding import HP_PRODUCT_LINES
        placed = set()
        for persona_id in bp.PERSONA_IDS:
            placed |= set(bp.allowed_lines(persona_id))
            placed |= set(bp.denied_lines(persona_id))
        # Aliases of a canonical line are not separate rows in the matrix.
        aliases = {"HP Enterprise Printing & MPS", "HP Anyware", "HP DaaS",
                   "HP EliteBook", "HP ProBook", "Original HP Ink"}
        unplaced = set(HP_PRODUCT_LINES) - placed - aliases
        assert not unplaced, (
            "nameable but in no persona's allowed or denied set: %s"
            % sorted(unplaced))
