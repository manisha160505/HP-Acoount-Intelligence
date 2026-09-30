"""The build specification's Content Studio acceptance suite, T1-T10.

HP220_Content_Studio_Message_Evaluator_Build_Spec_BridgeAI_30Sept2026, Section
7: "Each test names a persona, a format, an input and the expected outcome. A
build is not done until all pass and the result is recorded with the command
that produced it."

Named T1..T10 in the test names on purpose - the client will ask for them by
number, and a suite whose names do not match the document is a suite nobody can
check against it.

None of these call a model. Each one supplies the asset a model would return
and asserts what Python does with it, because what Python does with it is the
whole point of the gates: "The prompt rules are instructions the model may
follow. These are checks the code enforces."
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import content_studio as cstudio
from app.services.extractors.grounding import GroundingReport, corpus_from_texts
from app.services.hp import buyer_personas as bp, content_gates

# --- fixtures ---------------------------------------------------------------

def _persona(persona_id: str, *, filled: bool = False, name: str | None = None) -> dict:
    """A picker persona for one of the eight, as `_derive_client_personas` builds it."""
    card = bp.card(persona_id)
    return {
        "id": persona_id,
        "kind": "client_role",
        "source": "company_personas",
        "title": card["title"],
        "subtitle": card["department"],
        "department": card["department"],
        "buying_committee_persona": card["committee_angle"],
        "full_name": name if filled else None,
        "actual_job_title": card["title"] if filled else None,
        "contact_status": "Work email found" if filled else "No candidate found",
        "is_filled": filled,
    }


def _judge(asset: dict, persona: dict, content_type: str, *,
           evidence=("The IT team reported a client estate due for refresh.",),
           names=(), industry="semiconductor testing"):
    """Run the real validator and return (published?, rejects, regenerates)."""
    ground = corpus_from_texts(list(evidence))
    labels = {"A%d" % (i + 1): text for i, text in enumerate(evidence)}
    contract = cstudio.CONTENT_TYPE_CONTRACTS[content_type]
    clean, faults, soft = cstudio._validate_asset(
        {"asset": asset}, contract, persona, labels, ground,
        GroundingReport(ground, []), list(names), industry=industry)
    return clean, faults, soft


def _gates(asset: dict, persona_id: str, content_type: str, **kw) -> list:
    """The gate suite alone, for the tests that assert a named gate's silence."""
    return content_gates.run(
        asset, persona_id=persona_id, content_type=content_type,
        filled=kw.get("filled", False), corpus=kw.get("corpus"),
        supplied_labels=kw.get("supplied_labels", ()),
        label_texts=kw.get("label_texts", {}),
        known_names=kw.get("known_names", ()),
        competitors=kw.get("competitors", ()),
        industry=kw.get("industry", ""),
        required_keys=kw.get("required_keys", ()))


def _fired(findings, gate: str) -> bool:
    return any(f["gate"] == gate for f in findings)


EMAIL = {
    "subject_line": "Re: the client refresh calendar",
    "opening": "Your IT team reported a client estate due for refresh.",
    "body_sections": [{"text": "At HP, we can set the lifecycle economics of that estate against "
                               "a fixed multi-year per-seat cost, so the refresh lands as a "
                               "planned line rather than a capital surprise."}],
    "cta": "Would a short look at the extend-versus-replace comparison be useful?",
    "hp_products": ["HP Care Pack Services"],
    "evidence_used": ["A1"],
}


# --- T1 ---------------------------------------------------------------------

class TestT1PolyIsNotOfferedToTheCFO:
    """T1 | cfo + Email + topic "Poly Studio video bars" | hp_products is empty
    or contains only an allowed CFO line. No Poly reference anywhere. G4 does
    not fire.

    The specification calls the eligibility matrix "the single most important
    table in this document", and this is the failure it exists to stop: a
    seller types a topic, the evidence looks supportive, and the CFO is sent a
    video-bar pitch.
    """

    def test_poly_in_hp_products_is_rejected(self):
        asset = {**EMAIL, "hp_products": ["Poly Studio"]}
        clean, faults, _soft = _judge(asset, _persona("cfo"), "email")
        assert clean is None
        assert any(f.startswith("G4") for f in faults)

    def test_poly_in_the_prose_alone_is_rejected(self):
        """"including in prose rather than in hp_products" - naming the line in
        a sentence and leaving hp_products empty is the same output."""
        asset = {**EMAIL, "hp_products": [],
                 "body_sections": [{"text": "At HP, we would look at Poly Studio video bars for "
                                            "the meeting rooms attached to that estate."}]}
        clean, faults, _soft = _judge(asset, _persona("cfo"), "email")
        assert clean is None
        assert any(f.startswith("G4") for f in faults)

    def test_an_allowed_cfo_line_passes_and_g4_is_silent(self):
        clean, faults, _soft = _judge(EMAIL, _persona("cfo"), "email")
        assert clean is not None, faults
        assert clean["hp_products"] == ["HP Care Pack Services"]
        assert not _fired(_gates(clean, "cfo", "email"), "G4")

    def test_no_products_at_all_also_passes(self):
        """The specification's expectation is "empty OR an allowed line". Naming
        nothing is the correct answer when only a denied line is earned."""
        asset = {**EMAIL, "hp_products": [],
                 "body_sections": [{"text": "At HP, we would want to understand how that estate is "
                                            "funded today before proposing anything."}]}
        clean, _faults, _soft = _judge(asset, _persona("cfo"), "email")
        assert clean is not None
        assert clean["hp_products"] == []


# --- T2 ---------------------------------------------------------------------

class TestT2ProcurementGetsProcessNotAProduct:
    """T2 | head-procurement + Email + topic "HP Wolf Security" | No product
    pitch. The ask concerns evaluation process or documentation. G6 does not
    fire."""

    def test_a_product_ask_to_procurement_is_caught(self):
        asset = {**EMAIL, "hp_products": [],
                 "cta": "Shall we put HP Wolf Security in front of your security team?"}
        clean, faults, soft = _judge(asset, _persona("head-procurement"), "email")
        assert clean is None or _fired(_gates(clean, "head-procurement", "email"), "G6")
        assert any("G6" in m for m in faults + soft)

    def test_a_process_ask_passes_and_g6_is_silent(self):
        asset = {**EMAIL, "hp_products": [],
                 "body_sections": [{"text": "At HP, we are usually asked for the documentation "
                                            "set before anything technical is discussed."}],
                 "cta": "Could you tell me how a new hardware vendor is evaluated here, and what "
                        "documentation you need at that stage?"}
        clean, faults, _soft = _judge(asset, _persona("head-procurement"), "email")
        assert clean is not None, faults
        assert not _fired(_gates(clean, "head-procurement", "email"), "G6")

    def test_the_angle_is_the_gatekeeper_angle(self):
        assert bp.angle("head-procurement") == "Gatekeeper - Procurement & Legal"


# --- T3 and T4 --------------------------------------------------------------

LINKEDIN = {
    "opening": "Your team reported a client estate due for refresh.",
    "body_sections": [{"text": "At HP, the room-side and desk-side refresh usually get planned "
                               "separately, which is where the AV standard slips - one "
                               "configuration baseline keeps them on the same calendar."}],
    "cta": "Open to a short technical review of how the two are sequenced?",
    "hp_products": [],
    "evidence_used": ["A1"],
}


class TestT3UnfilledLinkedInMessageNamesNobody:
    """T3 | av-collaboration-manager + LinkedIn Message, persona UNFILLED | No
    name, no greeting-by-name. G7 does not fire.

    The specification expects UNFILLED to be the normal path: fill rates across
    the delivered files run from 8% for this very persona to 61% for the CFO.
    """

    def test_an_unfilled_message_carrying_no_name_passes(self):
        persona = _persona("av-collaboration-manager")
        clean, faults, _soft = _judge(LINKEDIN, persona, "linkedin_message",
                                      names=["Robert Leindl"])
        assert clean is not None, faults
        assert not _fired(_gates(clean, "av-collaboration-manager", "linkedin_message",
                                 filled=False, known_names=["Robert Leindl"]), "G7")

    def test_a_greeting_by_name_is_rejected(self):
        asset = {**LINKEDIN, "opening": "Hi Robert, your team reported a client estate due for refresh."}
        clean, faults, _soft = _judge(asset, _persona("av-collaboration-manager"),
                                      "linkedin_message", names=["Robert Leindl"])
        assert clean is None
        assert any(f.startswith("G7") or "names a contact" in f for f in faults)

    def test_the_persona_rule_tells_the_model_to_name_nobody(self):
        rule = cstudio._persona_rule(
            "client_role", "ACME Corp",
            cstudio.CONTENT_TYPE_CONTRACTS["linkedin_message"], False)
        assert "NO PERSON HAS BEEN IDENTIFIED" in rule.upper()
        assert "may NOT name anyone, greet anyone" in rule


class TestT4FilledLinkedInMessageMayUseTheName:
    """T4 | av-collaboration-manager + LinkedIn Message, persona FILLED | The
    contact's name appears; content is personalised. The public-post override
    does not fire.

    Section 1.3 warns this failure would be invisible in testing, because a
    message written under the public-post rule still reads perfectly well - it
    is simply addressed to nobody, on a format whose whole value is that it is
    addressed to someone.
    """

    def test_the_name_survives_on_a_filled_persona(self):
        asset = {**LINKEDIN,
                 "opening": "Robert, your team reported a client estate due for refresh."}
        persona = _persona("av-collaboration-manager", filled=True, name="Robert Leindl")
        clean, faults, _soft = _judge(asset, persona, "linkedin_message",
                                      names=["Robert Leindl"])
        assert clean is not None, faults
        assert "Robert" in clean["opening"]

    def test_the_linkedin_message_contract_is_not_public(self):
        """The override branches on `public`, and this format must not carry it."""
        assert not cstudio.CONTENT_TYPE_CONTRACTS["linkedin_message"].get("public")
        assert cstudio.CONTENT_TYPE_CONTRACTS["linkedin"].get("public")

    def test_the_filled_rule_is_not_the_public_post_rule(self):
        rule = cstudio._persona_rule(
            "client_role", "ACME Corp",
            cstudio.CONTENT_TYPE_CONTRACTS["linkedin_message"], True)
        assert "PUBLIC POST" not in rule.upper()
        assert "NAMED THE" in rule.upper()


# --- T5 ---------------------------------------------------------------------

class TestT5AnAccountWithNoEvidence:
    """T5 | Any persona + account with no evidence | Output is discovery-led,
    hp_products empty, no claim about the account. Not an error."""

    def test_no_labels_means_no_asset_rather_than_a_fabricated_one(self):
        """The deterministic template needs one grounded account fact to stand
        on. With none it declines - the honest outcome, and the one thing it
        must never do is compose a sentence about an account it knows nothing
        about."""
        out = cstudio._safe_fallback_asset(
            cstudio.CONTENT_TYPE_CONTRACTS["email"], _persona("vp-it"),
            "ACME Corp", "device refresh", {})
        assert out is None

    def test_a_discovery_led_asset_with_no_products_is_published(self):
        asset = {
            "subject_line": "Re: how the client estate is planned",
            "opening": "I have not seen anything published about how the estate here is planned.",
            "body_sections": [{"text": "At HP, the first question is usually who owns the refresh "
                                       "calendar and what it is measured against. Without that, "
                                       "anything else is a guess."}],
            "cta": "Would a short conversation about how that is decided here be useful?",
            "hp_products": [],
            "evidence_used": [],
        }
        clean, faults, _soft = _judge(asset, _persona("vp-it"), "email", evidence=())
        assert clean is not None, faults
        assert clean["hp_products"] == []

    def test_g4_cannot_fire_when_no_line_is_named(self):
        assert not _fired(_gates({"opening": "No product here.", "hp_products": []},
                                 "cfo", "email"), "G4")


# --- T6 ---------------------------------------------------------------------

ONE_PAGER = {
    "headline": "ACME Corp: the client estate and the refresh calendar",
    "subtitle": "For the leader responsible for endpoint security - what the estate implies",
    "why_now": "The IT team reported a client estate due for refresh [A1].",
    "pillars": [
        {"heading": "An estate past its refresh date",
         "challenge": "The IT team reported a client estate due for refresh [A1].",
         "hp_response": "HP Wolf Security puts the firmware baseline below the OS, so an "
                        "ageing estate is not also an unmonitored one.",
         "evidence_used": ["A1"]},
        {"heading": "Standards drift during a refresh",
         "challenge": "A refresh reported without a stated standard is where configuration "
                      "drift starts [A1].",
         "hp_response": "One configuration baseline applied at the factory rather than at "
                        "the desk.",
         "evidence_used": ["A1"]},
    ],
    "hp_play": "HP Wolf Security, scoped to the estate being refreshed rather than to the fleet.",
    "cta": "Would a short technical review of the endpoint baseline be useful?",
    "hp_products": ["HP Wolf Security"],
    "evidence_used": ["A1"],
}


class TestT6TheOnePagerIsStructured:
    """T6 | it-security-manager + 1-Pager | Exactly 2-3 pillars, each with its
    own evidence_used. Renders on one page."""

    def test_two_pillars_each_citing_evidence_passes_g13(self):
        clean, faults, _soft = _judge(ONE_PAGER, _persona("it-security-manager"), "one_pager")
        assert clean is not None, faults
        assert len(clean["pillars"]) == 2
        assert all(p["evidence_used"] for p in clean["pillars"])
        assert not _fired(_gates(clean, "it-security-manager", "one_pager"), "G13")

    def test_one_pillar_is_flagged_rather_than_padded(self):
        """"If the evidence supports only one pillar, the correct output is an
        Email, and the UI should say so rather than pad." So one pillar is a
        finding, not a silent second pillar invented to meet the count."""
        asset = {**ONE_PAGER, "pillars": ONE_PAGER["pillars"][:1]}
        _clean, _faults, soft = _judge(asset, _persona("it-security-manager"), "one_pager")
        assert any("G13" in m for m in soft)

    def test_four_pillars_is_flagged(self):
        extra = dict(ONE_PAGER["pillars"][0], heading="A fourth")
        asset = {**ONE_PAGER, "pillars": [*ONE_PAGER["pillars"], extra, extra]}
        _clean, _faults, soft = _judge(asset, _persona("it-security-manager"), "one_pager")
        assert any("G13" in m and "4 pillars" in m for m in soft)

    def test_a_pillar_citing_nothing_is_flagged(self):
        bare = dict(ONE_PAGER["pillars"][1], evidence_used=[])
        asset = {**ONE_PAGER, "pillars": [ONE_PAGER["pillars"][0], bare]}
        _clean, _faults, soft = _judge(asset, _persona("it-security-manager"), "one_pager")
        assert any("cites no evidence" in m for m in soft)

    def test_the_structure_is_projected_onto_the_render_envelope(self):
        """Every renderer, the asset history and the Evaluator read
        headline / opening / body_sections / cta. The structure is additive."""
        clean, faults, _soft = _judge(ONE_PAGER, _persona("it-security-manager"), "one_pager")
        assert clean is not None, faults
        assert clean["opening"] == ONE_PAGER["why_now"]
        headings = [s["heading"] for s in clean["body_sections"]]
        assert headings == ["An estate past its refresh date",
                            "Standards drift during a refresh",
                            cstudio.HP_PLAY_HEADING]
        assert clean["subtitle"] and clean["why_now"] and clean["hp_play"]

    def test_the_proof_point_is_appended_by_python_not_written_by_the_model(self):
        clean, _faults, _soft = _judge(ONE_PAGER, _persona("it-security-manager"), "one_pager")
        assert "proof_point" not in clean
        cstudio._attach_proof_point(
            clean, {"text": "HP secured 40,000 endpoints for a global manufacturer."},
            cstudio.CONTENT_TYPE_CONTRACTS["one_pager"])
        assert clean["proof_point"]
        assert clean["body_sections"][-1]["heading"] == cstudio.PROOF_POINTS_HEADING

    def test_one_page_is_the_word_budget_counted_once(self):
        """The asset carries the structure and the projection of it at the same
        time. Counted twice, a 200-word brief reads as 400 and every 1-Pager is
        over budget."""
        clean, _faults, _soft = _judge(ONE_PAGER, _persona("it-security-manager"), "one_pager")
        rendered = len(" ".join(
            [clean["headline"], clean["subtitle"], clean["opening"], clean["cta"]]
            + [s["heading"] + " " + s["text"] for s in clean["body_sections"]]).split())
        assert content_gates.asset_word_count(clean) == rendered
        assert content_gates.WORD_BUDGETS["one_pager"] == (350, 500)


# --- T7 ---------------------------------------------------------------------

class TestT7AnAccountWhoseEvidenceCarriesNoNumber:
    """T7 | Any persona + an account whose evidence contains no number | Output
    contains no number. G1 does not fire."""

    NO_NUMBERS = ("The IT team reported that part of the client estate is due for refresh.",)

    def test_copy_without_a_figure_passes(self):
        asset = {**EMAIL,
                 "opening": "Your IT team reported part of the client estate is due for refresh."}
        clean, faults, _soft = _judge(asset, _persona("vp-it"), "email", evidence=self.NO_NUMBERS)
        assert clean is not None, faults
        assert not _fired(_gates(clean, "vp-it", "email",
                                 corpus=corpus_from_texts(list(self.NO_NUMBERS))), "G1")

    def test_a_figure_the_evidence_never_carried_is_rejected(self):
        asset = {**EMAIL,
                 "opening": "Your IT team reported 4,000 devices are due for refresh."}
        clean, faults, _soft = _judge(asset, _persona("vp-it"), "email", evidence=self.NO_NUMBERS)
        assert clean is None
        assert any("4" in f for f in faults)


# --- T8 ---------------------------------------------------------------------

class TestT8NoUrgencyOnADeadlineThatHasPassed:
    """T8 | device-lifecycle-manager + Email | No urgency built on the Windows
    10 deadline as if it were upcoming.

    Support ended in October 2025. This persona lived through that date, and
    the pack records "Urgency built on the Windows 10 deadline, which has
    already passed" under what does not resonate for them.
    """

    # The evidence has to mention Windows 10, or the "10" is an unsourced
    # figure and the grounding gate rejects the asset before the suite runs -
    # a hard fault short-circuits the gates by design. Which is also the
    # realistic case: you only write about the estate's OS if the data says so.
    EVIDENCE = ("The technology estate shows Windows 10 on most client devices.",)

    def test_the_forward_looking_deadline_is_caught(self):
        asset = {**EMAIL,
                 "opening": "The estate shows Windows 10 on most client devices.",
                 "cta": "Worth moving before the Windows 10 end of support deadline?"}
        _clean, _faults, soft = _judge(asset, _persona("device-lifecycle-manager"), "email",
                                       evidence=self.EVIDENCE)
        assert any("deadline that has passed" in m for m in soft)

    def test_naming_an_estate_still_on_windows_10_is_not_caught(self):
        """The estate is a present fact. Only the tense is the failure."""
        asset = {**EMAIL,
                 "opening": "Part of the estate still runs Windows 10, which left support in "
                            "October 2025."}
        evidence = ("Part of the estate still runs Windows 10, which left support in October 2025.",)
        _clean, _faults, soft = _judge(asset, _persona("device-lifecycle-manager"), "email",
                                       evidence=evidence)
        assert not any("deadline that has passed" in m for m in soft)

    def test_the_constraint_is_recorded_on_the_persona(self):
        does_not = " ".join(bp.card("device-lifecycle-manager")["does_not_resonate"]).lower()
        assert "already passed" in does_not


# --- T9 ---------------------------------------------------------------------

class TestT9NoBannedPhrasesAndNoExclamationMarks:
    """T9 | Any persona, 20 consecutive generations | Zero banned phrases. Zero
    exclamation marks.

    Twenty model calls are not something a unit test can assert about, and
    asserting it that way would test the model rather than the build. What is
    testable is the property the specification is reaching for: every phrase on
    the seed list is caught wherever it appears in an asset, on every
    generation, because the gate runs inside the validator.
    """

    def test_every_seed_phrase_is_caught(self):
        for phrase in content_gates.BANNED_PHRASES:
            asset = {**EMAIL, "opening": "Your estate is %s and due for refresh." % phrase}
            findings = _gates(asset, "vp-it", "email")
            assert _fired(findings, "G9"), phrase

    def test_an_exclamation_mark_is_caught_in_any_field(self):
        for field in ("subject_line", "opening", "cta"):
            asset = {**EMAIL, field: EMAIL[field] + "!"}
            assert _fired(_gates(asset, "vp-it", "email"), "G9"), field

    def test_a_phrase_inside_a_pillar_is_caught_too(self):
        """The 1-Pager's prose lives in the structure, so a gate that only read
        body_sections would miss half the document."""
        pillar = dict(ONE_PAGER["pillars"][0],
                      hp_response="An industry-leading baseline.")
        asset = {**ONE_PAGER, "pillars": [pillar, ONE_PAGER["pillars"][1]]}
        assert _fired(_gates(asset, "it-security-manager", "one_pager"), "G9")

    def test_the_gate_runs_inside_the_validator_on_every_generation(self):
        asset = {**EMAIL, "cta": "A world-class next step?"}
        _clean, _faults, soft = _judge(asset, _persona("vp-it"), "email")
        assert any("G9" in m for m in soft)


# --- T10 --------------------------------------------------------------------

class TestT10PrintIsNotOfferedToTheFleetStandardsOwner:
    """T10 | pc-fleet-standards-owner + Email + topic "HP Enterprise Print" |
    Denied line. hp_products empty, no print reference. G4 does not fire."""

    def test_print_in_hp_products_is_rejected(self):
        asset = {**EMAIL, "hp_products": ["HP Enterprise Print / MPS"]}
        clean, faults, _soft = _judge(asset, _persona("pc-fleet-standards-owner"), "email")
        assert clean is None
        assert any(f.startswith("G4") for f in faults)

    def test_the_line_is_denied_in_the_matrix(self):
        assert "HP Enterprise Print / MPS" in bp.denied_lines("pc-fleet-standards-owner")
        assert "HP Enterprise Print / MPS" not in bp.allowed_lines("pc-fleet-standards-owner")

    def test_the_discovery_led_answer_is_the_correct_one(self):
        """"If the only line the account evidence earns is a forbidden one, name
        no product and write the discovery-led piece per Rule 4.\""""
        asset = {**EMAIL, "hp_products": [],
                 "body_sections": [{"text": "At HP, we would want to know which parts of the "
                                            "estate are standardised today before proposing a "
                                            "configuration baseline."}]}
        clean, faults, _soft = _judge(asset, _persona("pc-fleet-standards-owner"), "email")
        assert clean is not None, faults
        assert not _fired(_gates(clean, "pc-fleet-standards-owner", "email"), "G4")

    def test_the_prompt_tells_the_model_the_denied_lines(self):
        persona = _persona("pc-fleet-standards-owner")
        assert "HP Enterprise Print / MPS" in cstudio._denied_lines_for(persona)
        assert "HP Enterprise Print / MPS" not in cstudio._allowed_lines_for(persona)


# --- the eight, on every account -------------------------------------------

class TestEveryPersonaHasAMatrixRow:
    """Section 8, S4 marks the eligibility matrix itself as awaiting HP's
    sign-off. Until it comes, the one thing that must hold is that no persona
    the picker offers is missing a row: a persona with no row would pass G4 by
    default, which is the silent pass the specification forbids.
    """

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_allowed_and_denied_are_both_populated(self, persona_id):
        assert bp.allowed_lines(persona_id)
        assert bp.denied_lines(persona_id)
        assert not set(bp.allowed_lines(persona_id)) & set(bp.denied_lines(persona_id))

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_every_persona_has_an_ask_bound(self, persona_id):
        """Every persona says what may be asked. Only three of the four angles
        say what may not: Section 2.2 gives the Economic Buyer no prohibition,
        because "a decision-oriented ask is acceptable" leaves nothing to
        forbid. An empty `never` is the matrix, not a gap in it."""
        bound = bp.ask_bound(persona_id)
        assert bound["may_ask"]
        assert isinstance(bound["never"], tuple)
        if bp.angle(persona_id) != "Economic Buyer":
            assert bound["never"]
