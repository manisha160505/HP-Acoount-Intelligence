"""The build specification's Message Evaluator acceptance suite, T11-T22.

HP220_Content_Studio_Message_Evaluator_Build_Spec_BridgeAI_30Sept2026, Section
7. Named by number for the same reason as the Content Studio suite: the client
will ask for them that way.

Where a test needs a model, the model is a stub that returns whatever the test
is about. Nothing here calls an LLM - every one of these is a property of the
code around the model, which is where the specification puts the guarantees.
"""

import os
import sys
import typing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.evaluator import evaluate as E, formats as F, scoring as S, verify
from app.services.hp import buyer_personas as bp

# --- T11 --------------------------------------------------------------------

class TestT11SevenDimensionsAlways:
    """T11 | Any persona + Email + any objective | Exactly 7 dimensions
    returned. Never 10.

    "Never 10" is the reference application, which added three GEO/AEO
    dimensions on two formats. This build never had them - `formats.py` records
    the decision not to reproduce them - so the failure to guard against was the
    other direction: `required_dimensions` returned the WEIGHTED dimensions, so
    Awareness asked for five and the seller saw five bars.
    """

    @pytest.mark.parametrize("objective", S.OBJECTIVES)
    def test_seven_are_asked_for(self, objective):
        block = E._dimension_block(objective)
        # Named as the specification names them - "Brand_Recall", "CTA" - so an
        # HP reader holding both documents sees the same seven words.
        for dimension in S.ALL_DIMENSIONS:
            assert '"%s"' % S.SPEC_DIMENSION_NAMES[dimension] in block
        assert block.count("<0-100>") == 7

    @pytest.mark.parametrize("objective", S.OBJECTIVES)
    def test_seven_are_validated(self, objective):
        raw = dict.fromkeys(S.ALL_DIMENSIONS, 70)
        valid, problems = S.validate_dimensions(raw, objective)
        assert problems == []
        assert len(valid) == 7

    @pytest.mark.parametrize("objective", S.OBJECTIVES)
    def test_a_missing_unweighted_dimension_is_still_a_problem(self, objective):
        """Scored and displayed means scored and displayed. A dimension that
        carries no weight for this objective is still one the seller is owed."""
        raw = dict.fromkeys(S.ALL_DIMENSIONS, 70)
        unweighted = [d for d in S.ALL_DIMENSIONS
                      if S.weight_of(objective, d) == 0.0]
        if not unweighted:
            pytest.skip("%s weights every dimension" % objective)
        del raw[unweighted[0]]
        _valid, problems = S.validate_dimensions(raw, objective)
        assert any(unweighted[0] in p for p in problems)

    def test_there_is_no_eighth_dimension(self):
        assert len(S.ALL_DIMENSIONS) == 7
        assert len(set(S.ALL_DIMENSIONS)) == 7


# --- T12 and T13 ------------------------------------------------------------

class TestT12ObjectiveChangesTheCompositeNotTheScores:
    """T12 | Same stimulus, objective Awareness vs Conversion | Dimension
    scores stable; composite differs per the weight table."""

    DIMS: typing.ClassVar[dict] = {S.RELEVANCE: 80.0, S.IMPACT: 60.0, S.BRAND_RECALL: 40.0,
            S.CLARITY: 70.0, S.CREATIVITY: 50.0, S.EMOTIONAL: 30.0,
            S.NEXT_STEP: 90.0}

    def test_the_same_dimensions_give_different_composites(self):
        awareness = S.composite(self.DIMS, "awareness")
        conversion = S.composite(self.DIMS, "conversion")
        assert awareness != conversion

    def test_only_the_objective_selects_the_formula(self):
        """Not the mode, not the format, not the persona - `formula_for` takes
        one argument and that is the design."""
        for objective in S.OBJECTIVES:
            assert S.formula_for(objective) == S.OBJECTIVE_FORMULAS[objective]

    def test_every_row_sums_to_one(self):
        for objective in S.OBJECTIVES:
            assert abs(sum(S.formula_for(objective).values()) - 1.0) < 1e-9


class TestT13CompositeIsRecomputedInCode:
    """T13 | Composite recomputed in code from dimensions and weights | Matches
    the displayed value to within rounding."""

    def test_the_composite_is_the_weighted_sum(self):
        dims = TestT12ObjectiveChangesTheCompositeNotTheScores.DIMS
        for objective in S.OBJECTIVES:
            weights = S.formula_for(objective)
            expected = sum(dims[d] * w for d, w in weights.items())
            assert abs(S.composite(dims, objective) - expected) < 0.05

    def test_the_displayed_formula_names_the_same_weights(self):
        for objective in S.OBJECTIVES:
            expression = S.formula_expression(objective)
            for dimension, weight in S.formula_for(objective).items():
                assert S.DIMENSION_LABELS[dimension] in expression
                assert ("%g" % weight) in expression

    def test_an_unweighted_dimension_cannot_move_the_composite(self):
        dims = dict(TestT12ObjectiveChangesTheCompositeNotTheScores.DIMS)
        before = S.composite(dims, "awareness")
        dims[S.NEXT_STEP] = 0.0            # weight 0 under Awareness
        assert S.composite(dims, "awareness") == before

    def test_the_model_is_told_it_will_not_see_the_result(self):
        assert "do NOT compute the composite" in E.SYSTEM_PROMPT


# --- T14 and T15 ------------------------------------------------------------

class TestT14LiteMode:
    """T14 | LITE mode | 5 chunks. No behavioralState key on the card."""

    def test_the_chunk_instruction_asks_for_exactly_five(self):
        assert "exactly 5 chunks" in E._chunk_instruction(E.MODE_LITE)

    def test_the_limit_is_enforced_not_requested(self):
        assert E.LITE_MAX_CHUNKS == 5

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_card_has_no_behavioural_state(self, persona_id):
        """Omitted entirely, not emitted empty: "an empty slot invites the model
        to fill it", and in the UI it is a blank row."""
        card = bp.evaluator_card(persona_id)
        assert "behavioural_state" not in card


class TestT15DeepMode:
    """T15 | DEEP mode | 10-15 chunks. behavioralState present and matching the
    Section 4.9 table for that persona."""

    def test_the_chunk_instruction_asks_for_the_range(self):
        assert "between 10 and 15 chunks" in E._chunk_instruction(E.MODE_DEEP)
        assert (E.DEEP_MIN_CHUNKS, E.DEEP_MAX_CHUNKS) == (10, 15)

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_state_matches_the_entry_table(self, persona_id):
        card = bp.evaluator_card(persona_id, deep=True)
        state = card["behavioural_state"]
        assert state["name"] == bp.card(persona_id)["behavioural_state"]
        assert state["name"] in bp.BEHAVIOURAL_STATES
        assert 0.0 < state["trust_level"] <= 1.0
        assert state["response_bias"] and state["messaging_approach"]
        assert state["fast_track_trigger"] and state["key_blocker"]

    def test_the_four_states_are_the_reference_implementation_s(self):
        assert set(bp.BEHAVIOURAL_STATES) == {
            "INITIAL_SKEPTICISM", "INFORMATION_SEEKING",
            "EVALUATION_MODE", "DECISION_READY"}

    def test_the_prompt_says_the_state_is_an_assumption(self):
        """Section 4.9: "Entry states are hypotheses, not observed behaviour."
        The value of the state machine is that it makes the assumption explicit
        and adjustable rather than buried in tone, so the prompt says so."""
        block = E._card_block(bp.evaluator_card("cfo", deep=True))
        assert "ASSUMED ENTRY STATE" in block
        assert "not something observed" in block


# --- T16 --------------------------------------------------------------------

class TestT16ChunksReconstructTheStimulus:
    """T16 | Concatenate returned chunks | Reconstructs the stimulus exactly.
    G14 does not fire.

    The point is not that each chunk is verbatim - `verify_phrases` located
    every one of them in the draft, so that much is true by construction. It is
    that the SET is complete. An uncovered sentence reads in the highlighted
    view as text nobody objected to, and Step R rewrites from the chunks, so it
    is also a sentence the rewrite cannot touch.
    """

    MSG = "Your team reported a refresh. HP can set the lifecycle cost. Worth a look?"

    def _spans(self, *pairs):
        return [{"start": a, "end": b, "chunk": self.MSG[a:b]} for a, b in pairs]

    def test_a_complete_cover_passes(self):
        full = self._spans((0, 30), (30, 61), (61, len(self.MSG)))
        assert verify.chunk_fidelity(full, self.MSG) == []

    def test_a_missing_middle_is_caught(self):
        gapped = self._spans((0, 30), (61, len(self.MSG)))
        faults = verify.chunk_fidelity(gapped, self.MSG)
        assert faults and "lifecycle cost" in faults[0]

    def test_stopping_early_is_caught(self):
        faults = verify.chunk_fidelity(self._spans((0, 30)), self.MSG)
        assert faults and "stop before the end" in faults[0]

    def test_overlapping_chunks_are_caught(self):
        overlapping = self._spans((0, 40), (30, 61), (61, len(self.MSG)))
        assert verify.chunk_fidelity(overlapping, self.MSG)

    def test_no_chunks_at_all_is_caught(self):
        assert verify.chunk_fidelity([], self.MSG)

    def test_whitespace_between_chunks_is_not_a_gap(self):
        """A chunker splitting on sentence boundaries leaves a space behind
        every time. The specification's "contiguous" is about substance."""
        assert verify.chunk_fidelity(
            self._spans((0, 29), (30, 60), (61, len(self.MSG))), self.MSG) == []

    def test_the_model_is_told_to_tile_the_message(self):
        for mode in (E.MODE_LITE, E.MODE_DEEP):
            instruction = E._chunk_instruction(mode)
            assert "no gaps and no overlap" in instruction
            assert "checked in code" in instruction


# --- T17 and T18 ------------------------------------------------------------

class TestT17ADeniedLineFloorsRelevance:
    """T17 | Stimulus pitching a Poly video bar, persona cfo | Relevance scores
    below 40 and the summary names the line mismatch explicitly."""

    STIMULUS = ("Your meeting rooms are due an upgrade. At HP, we would put Poly "
                "Studio video bars in the main rooms. Worth a conversation?")

    def test_the_failure_is_found_in_python(self):
        found = E._severe_failures(self.STIMULUS, "cfo")
        assert len(found) == 1
        assert found[0]["dimension"] == S.RELEVANCE
        assert found[0]["gate"] == "G4"
        assert "Poly Studio" in found[0]["detail"]

    def test_the_floor_is_below_forty(self):
        assert E.SEVERE_FLOOR < 40

    def test_the_model_is_told_the_finding_is_decided(self):
        block = E._severe_block(E._severe_failures(self.STIMULUS, "cfo"))
        assert "do not dispute" in block.lower()
        assert "Relevance" in block
        assert "39" in block

    def test_an_allowed_line_is_not_a_severe_failure(self):
        clean = ("Your device estate is due a refresh. At HP, we would set the "
                 "lifecycle economics against a fixed multi-year cost. Worth a look?")
        assert E._severe_failures(clean, "cfo") == []


class TestT18AnOutOfAngleAskFloorsCta:
    """T18 | Stimulus asking a Gatekeeper to choose HP, persona
    head-procurement | CTA scores below 40 and the summary names the angle
    mismatch."""

    STIMULUS = ("A refresh is due across the estate. Would you choose HP for the "
                "fleet standard?")

    def test_the_failure_is_found_in_python(self):
        found = E._severe_failures(self.STIMULUS, "head-procurement")
        assert found
        assert found[0]["dimension"] == S.NEXT_STEP
        assert found[0]["gate"] == "G6"
        assert "Gatekeeper" in found[0]["detail"]

    def test_a_process_ask_to_the_gatekeeper_is_fine(self):
        clean = ("A refresh is due across the estate. How is a new hardware vendor "
                 "evaluated here, and what documentation do you need?")
        assert E._severe_failures(clean, "head-procurement") == []

    def test_the_ask_is_the_closing_question_not_the_whole_message(self):
        """The committee-angle rule is about the ask. A message that MENTIONS a
        price in its body and asks a process question is not an out-of-angle
        ask, and treating the whole message as the ask would say it was."""
        assert E._ask_sentence("We saw the refresh. Would you choose HP? Thanks.") \
            == "Would you choose HP?"
        assert E._ask_sentence("One sentence only.") == "One sentence only."
        assert E._ask_sentence("") == ""

    def test_a_price_to_finance_is_caught_too(self):
        found = E._severe_failures(
            "The estate is ageing. Shall I send pricing for the fleet?", "cfo")
        assert found and found[0]["dimension"] == S.NEXT_STEP


# --- T19 --------------------------------------------------------------------

class TestT19TheCardIsIdenticalEverywhere:
    """T19 | Same persona_id on three different accounts | The persona card is
    byte-identical across all three."""

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_card_is_a_constant(self, persona_id):
        import json
        renders = [json.dumps(bp.evaluator_card(persona_id, deep=True),
                              sort_keys=True) for _ in range(3)]
        assert len(set(renders)) == 1

    def test_the_card_takes_no_account_argument(self):
        """It cannot vary by account because it is not given one. That is the
        guarantee, rather than a test that happens to pass."""
        import inspect
        params = list(inspect.signature(bp.evaluator_card).parameters)
        assert params == ["persona_id", "deep"]

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_footer_says_hardcoded_on_every_row(self, persona_id):
        card = bp.evaluator_card(persona_id)
        assert card["card_source"] == bp.PERSONA_CARD_SOURCE
        assert set(card["data_sources"].values()) == {bp.PERSONA_CARD_SOURCE_LABEL}
        assert "hardcoded" in bp.PERSONA_CARD_SOURCE_LABEL.lower()

    def test_mutating_a_returned_card_cannot_corrupt_the_pack(self):
        card = bp.evaluator_card("cfo")
        card["goals"].append("something the seller invented")
        assert "something the seller invented" not in bp.evaluator_card("cfo")["goals"]


# --- T20 --------------------------------------------------------------------

class TestT20TheRewriteIsGated:
    """T20 | Rewrite with 2 of 5 recommendations selected | Only those two areas
    change. changesApplied has 2 entries. Section 6 gates run on the rewritten
    text.

    The first two clauses are the model's job and are checked by
    `verify.diff_rewrite`, which compares against the original. The third is
    this build's and it did not exist: nothing stopped a rewrite that "makes the
    value clearer" from naming Poly to a CFO.
    """

    CARD = bp.evaluator_card("cfo")
    PERSONA: typing.ClassVar[dict] = {
        "persona_id": "cfo", "is_named_person": False, "name": None}

    class _Corpus:
        def __init__(self, cells):
            self.cells = list(cells)

    class _Sources:
        def __init__(self):
            self.account = TestT20TheRewriteIsGated._Corpus(
                ["The estate is due a refresh."])
            self.hp = TestT20TheRewriteIsGated._Corpus(
                ["HP Care Pack Services covers multi-year support."])

    def _faults(self, rewrite):
        return E._rewrite_gate_faults(rewrite, self.CARD, self.PERSONA, [],
                                      self._Sources(), "The estate is due a refresh.",
                                      "email")

    def test_a_denied_line_in_the_rewrite_is_a_fault(self):
        faults = self._faults({
            "opening": "The estate is due a refresh.",
            "body_sections": [{"text": "Poly Studio would cover the rooms."}],
            "cta": "Worth a look?", "hp_products": []})
        assert any("G4" in f for f in faults)

    def test_a_clean_rewrite_passes(self):
        assert self._faults({
            "opening": "The estate is due a refresh.",
            "body_sections": [{"text": "HP Care Pack Services covers multi-year support."}],
            "cta": "Worth a look at the lifecycle cost?",
            "hp_products": ["HP Care Pack Services"]}) == []

    def test_a_persona_outside_the_eight_checks_nothing_rather_than_guessing(self):
        """There is no eligibility row for a persona the matrix does not carry,
        and inventing one would be worse than checking nothing."""
        assert E._rewrite_gate_faults(
            {"opening": "Poly Studio."}, None, self.PERSONA, [],
            self._Sources(), "", "email") == []

    def test_no_rewrite_means_no_faults(self):
        assert E._rewrite_gate_faults(None, self.CARD, self.PERSONA, [],
                                      self._Sources(), "", "email") == []

    def test_at_least_one_recommendation_is_required(self):
        """The gate the specification puts on Step R itself."""
        import inspect
        source = inspect.getsource(E.rewrite_message)
        assert "select at least one recommendation" in source


# --- T21 --------------------------------------------------------------------

class TestT21AMissingDimensionIsPadded:
    """T21 | Model returns 6 dimensions | Missing dimension padded to 50,
    warning logged naming the dimension, request succeeds.

    This is in direct tension with `scoring.py`'s own rule - no partial
    composite, no renormalising - so the pad is recorded rather than hidden. The
    formula is untouched; what changes is that the evaluation says which number
    was not the model's.
    """

    def test_the_missing_dimension_is_padded_and_named(self):
        raw = dict.fromkeys(S.ALL_DIMENSIONS, 70)
        del raw[S.CLARITY]
        valid, problems = S.validate_dimensions(raw, "awareness")
        dimensions, padded, remaining = S.pad_missing(valid, problems)
        assert padded == [S.CLARITY]
        assert dimensions[S.CLARITY] == S.PAD_SCORE == 50.0
        assert remaining == []

    def test_the_composite_then_computes(self):
        raw = dict.fromkeys(S.ALL_DIMENSIONS, 70)
        del raw[S.CLARITY]
        valid, problems = S.validate_dimensions(raw, "awareness")
        dimensions, _padded, remaining = S.pad_missing(valid, problems)
        assert remaining == []
        assert S.composite(dimensions, "awareness") == pytest.approx(67.0, abs=0.05)

    def test_a_bad_value_is_not_padded(self):
        """Padding is for a dimension the model never gave us. A dimension it
        returned as "excellent", or as 400, is a different failure and stays a
        problem - silently replacing a wrong answer with 50 would hide it."""
        for bad in ("excellent", 400, -5):
            raw = dict.fromkeys(S.ALL_DIMENSIONS, 70)
            raw[S.CLARITY] = bad
            valid, problems = S.validate_dimensions(raw, "awareness")
            _dimensions, padded, remaining = S.pad_missing(valid, problems)
            assert padded == []
            assert remaining == problems

    def test_the_pad_is_a_warning_the_flow_records(self):
        import inspect
        source = inspect.getsource(E.evaluate_message)
        assert "dimensions_padded" in source
        assert "logger.warning" in source


# --- T22 --------------------------------------------------------------------

class TestT22NonJsonFromTheModel:
    """T22 | Model returns non-JSON | Clear error to the UI. No partial score
    shown."""

    def test_a_failed_call_returns_an_empty_dict_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(E, "generate_gpt4o_json_completion",
                            lambda _s, _u: (_ for _ in ()).throw(ValueError("not json")))
        assert E._ask("system", "user") == {}

    def test_nothing_is_padded_when_the_model_returned_nothing(self):
        """The pad exists so a 6-of-7 answer still publishes. A model that
        answered with nothing has not scored anything, and seven 50s would be a
        fabricated evaluation rather than a degraded one."""
        import inspect
        source = inspect.getsource(E.evaluate_message)
        assert "if problems and raw:" in source

    def test_the_coded_checks_still_publish_without_a_score(self):
        checks = F.structure_checks("Hi. Worth a chat?", "email")
        assert checks["checks"]
        assert all("passed" in c for c in checks["checks"])

    def test_an_unavailable_composite_has_no_band(self):
        assert S.score_band(None) == "Unavailable"


# --- the rubric -------------------------------------------------------------

class TestTheRubricIsTheSpecification:
    """Section 4.5's six bands. The previous table had five and started
    "Strong" at 80, so a 76 read as Good where the specification calls it
    Strong."""

    @pytest.mark.parametrize("value,band", [
        (100, "Exceptional"), (90, "Exceptional"),
        (89, "Strong"), (75, "Strong"),
        (74, "Good"), (60, "Good"),
        (59, "Average"), (40, "Average"),
        (39, "Weak"), (20, "Weak"),
        (19, "Poor"), (0, "Poor"),
    ])
    def test_the_bands(self, value, band):
        assert S.score_band(value) == band

    def test_a_severely_floored_dimension_lands_in_weak(self):
        assert S.score_band(E.SEVERE_FLOOR) == "Weak"


# --- spec 4.10, the scoring prompt ------------------------------------------

class TestTheScoringPromptCarriesWhatSection410Asks:
    """The behaviour was right before these; the prompt was not.

    Python floors Relevance when a denied line appears, which is stronger than
    asking the model to. But the model wrote the summary and the persona
    reaction without knowing which lines are wrong for this buyer, so its prose
    could praise the very sentence the score was about to be capped for.
    """

    def test_the_eligibility_matrix_is_in_the_prompt(self):
        block = E._lines_block(bp.evaluator_card("cfo"))
        assert "MAY BE OFFERED" in block
        assert "WRONG FOR THIS PERSONA" in block
        for line in bp.denied_lines("cfo"):
            assert line in block
        for line in bp.allowed_lines("cfo"):
            assert line in block
        assert "Relevance must score below 40" in block

    def test_a_persona_outside_the_eight_gets_no_matrix_rather_than_a_guess(self):
        assert E._lines_block(None) == ""

    def test_the_rubric_is_the_specification_s(self):
        rubric = E._rubric_block()
        for band in ("90-100 Exceptional", "75-89 Strong", "60-74 Good",
                     "40-59 Average", "20-39 Weak", "0-19 Poor"):
            assert band in rubric

    def test_every_dimension_is_asked_for_with_a_rationale(self):
        block = E._dimension_block("awareness")
        assert block.count('"rationale"') == 7
        for dimension in S.ALL_DIMENSIONS:
            assert S.SPEC_DIMENSION_NAMES[dimension] in block

    def test_the_rationale_survives_into_the_stored_evaluation(self):
        import inspect
        source = inspect.getsource(E.evaluate_message)
        assert "dimension_rationales" in source
        assert "split_dimension_payload" in source


class TestBothDimensionShapesAreRead:
    """Section 4.10 returns an array; this build asked for an object. A stored
    evaluation written under the older contract still has to load."""

    def test_the_specification_s_array_form(self):
        scores, rationales = S.split_dimension_payload([
            {"dimension": "Brand_Recall", "score": 61, "rationale": "HP named once"},
            {"dimension": "CTA", "score": 40, "rationale": "vague ask"},
        ])
        assert scores == {S.BRAND_RECALL: 61, S.NEXT_STEP: 40}
        assert rationales[S.NEXT_STEP] == "vague ask"

    def test_the_build_s_object_form(self):
        scores, rationales = S.split_dimension_payload({"clarity": 70, "CTA": 55})
        assert scores == {S.CLARITY: 70, S.NEXT_STEP: 55}
        assert rationales == {}

    def test_a_nested_object_form(self):
        scores, rationales = S.split_dimension_payload(
            {"clarity": {"score": 70, "rationale": "short paragraphs"}})
        assert scores == {S.CLARITY: 70}
        assert rationales == {S.CLARITY: "short paragraphs"}

    def test_an_unrecognised_dimension_is_dropped(self):
        """Section 4.10: "Extra/unrecognised dimension: drop it." The three
        GEO dimensions this build never had are exactly what this catches."""
        scores, _ = S.split_dimension_payload([
            {"dimension": "Geo_Visibility", "score": 99},
            {"dimension": "Clarity", "score": 70},
        ])
        assert scores == {S.CLARITY: 70}

    def test_nothing_at_all_is_empty_rather_than_an_error(self):
        assert S.split_dimension_payload(None) == ({}, {})
        assert S.split_dimension_payload([]) == ({}, {})

    def test_the_card_block_carries_every_section_4_10_names(self):
        """4.10 lists the persona blocks the scoring prompt must contain.

        Our headings differ from the specification's ("They decide by asking"
        for DECISION CRITERIA, "What lands with them" for WHAT RESONATES) -
        the content is what is checked, not the capitalisation, because an HP
        reader comparing the two is reading for the buyer's goals, not for a
        heading style.
        """
        card = bp.evaluator_card("cfo", deep=True)
        block = E._card_block(card)
        for field in ("goals", "pain_points", "value_drivers",
                      "decision_criteria", "typical_objections",
                      "resonates", "does_not_resonate"):
            assert card[field][0] in block, field
        prefs = card["content_preferences"]
        assert prefs["tone"] in block
        assert prefs["format"] in block
        assert prefs["key_metrics"][0] in block
        assert card["behavioural_state"]["name"] in block

    def test_the_prompt_names_the_account(self):
        """The card is the same on all 220, so this line and the evidence are
        the only things saying which account is being written to."""
        class _Corpus:
            cells: typing.ClassVar[list] = ["a fact"]

        class _Sources:
            account = _Corpus()
            hp = _Corpus()
            country = "japan"
            company_name = "Advantest Corporation"
            superlatives_blocked = False
            competitor_claims_blocked = False

        prompt = E._user_prompt(
            "msg", {"title": "CFO"}, "conversion", "email", E.MODE_DEEP,
            _Sources(), F.structure_checks("x", "email"),
            card=bp.evaluator_card("cfo"), severe=[])
        assert "ACCOUNT: Advantest Corporation" in prompt

    def test_format_notes_are_asked_for_and_stored(self):
        """4.10's `formatNotes`: what the draft does well or badly AS an email,
        which the seven dimensions do not ask about directly."""
        import inspect
        assert "format_notes" in inspect.getsource(E._user_prompt)
        assert "format_notes" in inspect.getsource(E.evaluate_message)

    def test_the_composite_formula_is_deliberately_withheld(self):
        """4.10 puts it in the prompt and this build does not.

        The model is told it will never see the composite. Handing it the
        weights would tell it which three dimensions to optimise and which four
        do not count. The number is computed in code either way, so the
        seller's score is identical; what changes is whether the model has a
        reason to inflate Relevance under Engagement.
        """
        assert "do NOT compute the composite" in E.SYSTEM_PROMPT
        for objective in S.OBJECTIVES:
            assert S.formula_expression(objective) not in E._dimension_block(objective)


# --- tuning row 9, Column 6 -------------------------------------------------

class TestTheRulebookAndCaseStudiesReachTheScorer:
    """Tuning ROW 9, Column 6.

        "The Rulebook is used in scoring rather than in generation:
         Brand_Recall is assessed against whether HP is positioned as the
         Rulebook describes the named line, and Impact is assessed against
         whether a claim that could have been proved by an available HP case
         study was left unproved."

    Neither reached the Evaluator. Brand_Recall was "HP positioning
    reinforcement" with nothing to measure against, so it scored on how
    enthusiastic the copy sounded.
    """

    RULE: typing.ClassVar[dict] = {
        "kind": "rule", "family": "WOLF", "rule_label": "B1", "order": 1,
        "part": "B", "routing_only": False,
        "offering": "HP Wolf Security - firmware protection below the OS",
        "allowed_facts": ["Protection sits below the operating system."],
        "prohibitions": ["Do not claim it replaces an endpoint detection product."],
    }

    def _with_knowledge(self, monkeypatch, *, rules=True, studies=True):
        from app.services.hp import case_studies as cstudies, rulebook
        monkeypatch.setattr(rulebook, "load", lambda _db: {
            "rules": [self.RULE] if rules else [], "routing": [],
            "matrices": {}, "guardrails": [], "country_lists": {}})
        monkeypatch.setattr(cstudies, "match",
                            lambda _db, _l, **_k: [{"headline": "x"}] if studies else [])
        monkeypatch.setattr(cstudies, "as_proof_point", lambda _s: {
            "text": "HP secured 40,000 endpoints at a global manufacturer.",
            "customer": "A global manufacturer", "industry": "manufacturing"})

    def test_the_lines_the_seller_named_are_found(self):
        found = E._hp_lines_named(
            "We would put HP Wolf Security on the fleet and add HP Care Pack Services.")
        assert found == ["HP Wolf Security", "HP Care Pack Services"]

    def test_a_message_naming_nothing_pulls_nothing(self):
        assert E._hp_lines_named("Your estate is due a refresh. Worth a chat?") == []
        assert E._rulebook_block([], [], []) == ""

    def test_brand_recall_is_given_the_positioning(self, monkeypatch):
        self._with_knowledge(monkeypatch)
        lines = ["HP Wolf Security"]
        block = E._rulebook_block(E._rulebook_positioning(None, lines),
                                  E._proof_available(None, lines, "", "draft"), lines)
        assert "HOW HP POSITIONS THESE LINES" in block
        assert "firmware protection below the OS" in block
        assert "may state: Protection sits below the operating system." in block
        assert "must NOT say: Do not claim it replaces" in block
        assert "not against enthusiasm" in block

    def test_impact_is_given_the_proof_that_exists(self, monkeypatch):
        self._with_knowledge(monkeypatch)
        lines = ["HP Wolf Security"]
        block = E._rulebook_block(E._rulebook_positioning(None, lines),
                                  E._proof_available(None, lines, "", "draft"), lines)
        assert "HP PROOF THAT EXISTS" in block
        assert "40,000 endpoints" in block
        assert "left unproved" in block

    def test_with_no_case_study_the_instruction_is_to_cut_not_soften(self, monkeypatch):
        """The row is explicit: "Where no case study fits, the recommendation
        is to cut the claim rather than to soften it." Softening an unprovable
        claim leaves it in the message."""
        self._with_knowledge(monkeypatch, studies=False)
        lines = ["HP Wolf Security"]
        block = E._rulebook_block(E._rulebook_positioning(None, lines),
                                  E._proof_available(None, lines, "", "draft"), lines)
        assert "CUT the claim, not to soften it" in block

    def test_with_no_rulebook_entry_brand_recall_says_so(self, monkeypatch):
        self._with_knowledge(monkeypatch, rules=False)
        lines = ["HP Wolf Security"]
        block = E._rulebook_block(E._rulebook_positioning(None, lines), [], lines)
        assert "carries no positioning" in block

    def test_the_system_prompt_says_what_those_two_are_measured_against(self):
        assert "measured against the Rulebook positioning" in E.SYSTEM_PROMPT
        assert "left unproved" in E.SYSTEM_PROMPT

    def test_what_was_judged_against_is_stored(self):
        """The score is inspectable rather than asserted."""
        import inspect
        source = inspect.getsource(E.evaluate_message)
        for key in ("hp_lines_named", "rulebook_positioning", "proof_available"):
            assert '"%s"' % key in source

    def test_the_generator_is_still_never_shown_a_case_study(self):
        """The asymmetry is the point. Rule 4 makes the HP line something the
        GENERATOR has to earn, so handing it a study would hand it the product
        to work backwards from. The evaluator is judging a line the seller
        already named, so nothing is being chosen."""
        import inspect

        from app.services.extractors import content_studio
        prompt_source = inspect.getsource(content_studio._build_system_prompt)
        assert "case study" not in prompt_source.lower()
        assert "proof point" not in prompt_source.lower()
