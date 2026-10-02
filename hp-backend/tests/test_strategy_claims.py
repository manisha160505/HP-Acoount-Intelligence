"""The advisor answer as typed claims, validated whole.

Strategy Chat used to demand a literal `[section]` tag on every sentence that
asserted anything, reconstructing claim boundaries from prose. Asked which HP
line had the strongest case at an account carrying 359,000 characters of
evidence, it generated three good answers, rejected all three for the one
sentence that cannot carry a tag - the conclusion - and told the seller
"nothing in it supports an answer here".

The model now declares what each piece of its answer IS, and this is the gate
that proves it. The rule the client set, in their words:

    A synthesis/conclusion sentence is allowed without its own [section] tag
    when it only summarizes, compares, or draws a conclusion directly from
    facts already supported by tagged evidence. It must not introduce a new
    account fact, number, technology, relationship, event, or unsupported
    claim.

Run: python -m pytest tests/test_strategy_claims.py -v
"""

import os
import sys
import typing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.grounding import corpus_from_texts
from app.services.strategy import claims

PAYLOAD = """===== tech_stack_matrix (feature: tech_landscape) =====
{"full_tech_stack": ["AutoCAD", "CATIA", "Microsoft Defender"], "total_tech_count": 220}
===== opportunity_narrative_plays (feature: solution_narrative_opportunity_map) =====
{"opportunity_plays": [{"title": "High-Performance Workstations", "priority": "Critical"}]}
===== news_signals_feed (feature: recent_news_signals) =====
{"signals": [{"headline": "Capex set at IDR 36 trillion for 2026"}]}
"""
COMPANY = "PT Astra International Tbk"


def _sections(payload=PAYLOAD):
    found, key = {}, None
    for line in payload.split("\n"):
        if line.startswith("=====") and "(feature:" in line:
            key = line.split("=====")[1].split("(feature:")[0].strip()
            found[key] = ""
        elif key:
            found[key] += line + "\n"
    return found


@pytest.fixture
def ground():
    sections = _sections()
    return {"widget_keys": list(sections), "section_texts": sections,
            "corpus": corpus_from_texts([PAYLOAD]), "company": COMPANY,
            "payload": PAYLOAD}


def _fact(id_, text, section, quote, block="paragraph"):
    return {"id": id_, "type": "FACT", "block": block, "text": text,
            "sections": [section], "quote": quote}


FACTS = [
    _fact("c1", "Their estate runs AutoCAD and CATIA.",
          "tech_stack_matrix", "AutoCAD"),
    _fact("c2", "The Opportunity Map rates workstations a Critical play.",
          "opportunity_narrative_plays", "Critical"),
]


def _check(segments, ground):
    return claims.validate(claims.parse({"segments": segments}), **ground)


def _synthesis(text, depends_on=("c1", "c2")):
    return {"id": "c3", "type": "SYNTHESIS", "block": "paragraph",
            "text": text, "depends_on": list(depends_on)}


# ---------------------------------------------------------------------------
# The rule this module exists for
# ---------------------------------------------------------------------------

class TestAConclusionNeedsNoTagOfItsOwn:
    """The failure that prompted the change. Every one of these was rejected
    by the old per-sentence rule and every one of them is a legitimate
    answer."""

    @pytest.mark.parametrize("conclusion", [
        "So the workstation line has the strongest case of the three.",
        "Taken together, that makes a clear argument for prioritising it now.",
        "Comparing the two, the design workload is the more compelling.",
        "So this is where I would start, specifically because of the plans above.",
    ])
    def test_reasoning_prose_passes(self, ground, conclusion):
        ok, failures, _ = _check([*FACTS, _synthesis(conclusion)], ground)
        assert ok, failures

    def test_it_shows_the_sources_of_what_it_rests_on(self, ground):
        """The client asked for this explicitly: the conclusion carries the
        citations of the facts beneath it, so the seller can see what it is
        built from."""
        segments = claims.parse({"segments": [*FACTS, _synthesis("So that is the case.")]})
        rendered = claims.render(segments)
        assert "[tech_stack_matrix, opportunity_narrative_plays]" in rendered

    def test_a_conclusion_resting_on_nothing_is_still_rejected(self, ground):
        bare = {"id": "c3", "type": "SYNTHESIS", "block": "paragraph",
                "text": "So workstations win.", "depends_on": []}
        # An explicit empty list on a conclusion with no facts above it stays
        # empty - there is nothing to infer from.
        ok, failures, _ = _check([bare], ground)
        assert not ok
        assert "names no claim it rests on" in failures[0]["reason"]

    def test_dependencies_are_inferred_when_the_model_omits_them(self, ground):
        """It omits `depends_on` often enough to cost a generation, and the
        answer is ordered: a conclusion after two facts concludes from them."""
        loose = {"id": "c3", "type": "SYNTHESIS", "block": "paragraph",
                 "text": "So that is the stronger case."}
        segments = claims.parse({"segments": [*FACTS, loose]})
        assert segments[2]["depends_on"] == ["c1", "c2"]
        assert segments[2]["inferred_depends_on"] is True

    def test_inferring_them_does_not_loosen_the_check(self, ground):
        """An inferred dependency list goes through the same rule, so a
        conclusion reaching past the facts above it still fails."""
        loose = {"id": "c3", "type": "SYNTHESIS", "block": "paragraph",
                 "text": "So their Trellix rollout is the blocker."}
        ok, failures, _ = _check([*FACTS, loose], ground)
        assert not ok
        assert "trellix" in failures[0]["reason"]


class TestAConclusionMayNotIntroduceAnything:
    """The other half of the client's rule, and the reason this is not just
    a relaxation of the old gate."""

    def test_a_new_vendor_is_rejected(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So workstations beat their Dell Precision estate.")],
            ground)
        assert not ok
        assert "dell" in failures[0]["reason"]

    def test_a_new_figure_is_rejected(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So this covers all 450 seats.")], ground)
        assert not ok
        assert "450" in failures[0]["reason"]

    def test_a_new_hp_line_is_rejected(self, ground):
        """An HP product in a conclusion is the recommendation writing itself
        a premise. It has to be a FACT with its own evidence first."""
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So HP Wolf Security is the right lead.")], ground)
        assert not ok
        assert "wolf" in failures[0]["reason"]

    def test_the_account_s_own_name_is_not_a_new_entity(self, ground):
        """A conclusion says "Astra's security leadership" as a matter of
        course. The account is not a new fact about the account - this
        rejected real answers until it was fixed."""
        for text in ("So Astra's leadership should see this first.",
                     "PT Astra International Tbk is therefore the right target."):
            ok, failures, _ = _check([*FACTS, _synthesis(text)], ground)
            assert ok, failures


# ---------------------------------------------------------------------------
# Evidence: a tag asserts, a quote proves
# ---------------------------------------------------------------------------

class TestAFactMustEarnItsCitation:

    def test_a_fact_with_no_section_is_rejected(self, ground):
        ok, failures, _ = _check(
            [{"id": "c1", "type": "FACT", "block": "paragraph",
              "text": "They run AutoCAD.", "sections": [], "quote": "AutoCAD"}],
            ground)
        assert not ok
        assert "cites no section" in failures[0]["reason"]

    def test_a_fact_with_no_quote_is_rejected(self, ground):
        ok, failures, _ = _check(
            [{"id": "c1", "type": "FACT", "block": "paragraph",
              "text": "They run AutoCAD.", "sections": ["tech_stack_matrix"],
              "quote": ""}], ground)
        assert not ok
        assert "quotes nothing" in failures[0]["reason"]

    def test_a_quote_that_is_nowhere_in_the_data_is_rejected(self, ground):
        ok, failures, _ = _check(
            [_fact("c1", "They run Splunk.", "tech_stack_matrix", "Splunk")],
            ground)
        assert not ok
        assert "does not appear" in failures[0]["reason"]

    def test_a_quote_from_the_wrong_section_is_rejected(self, ground):
        """A tag proves the model ASSERTED an attribution. The quote proves it
        - and nothing checked that before, in either mode."""
        ok, failures, _ = _check(
            [_fact("c1", "They run AutoCAD.", "news_signals_feed", "AutoCAD")],
            ground)
        assert not ok
        assert "not in the section it cites" in failures[0]["reason"]

    def test_another_account_s_section_does_not_resolve(self, ground):
        """Cross-account isolation, enforced by membership as it always was."""
        ok, failures, _ = _check(
            [_fact("c1", "They run AutoCAD.", "someone_elses_widget", "AutoCAD")],
            ground)
        assert not ok
        assert "not a section of this account" in failures[0]["reason"]


class TestGeneralMayNotPoseAsAnAccountFact:

    def test_naming_the_company_makes_it_a_claim(self, ground):
        ok, failures, _ = _check(
            [{"id": "c1", "type": "GENERAL", "block": "paragraph",
              "text": "PT Astra International Tbk should standardise."}], ground)
        assert not ok
        assert "needs evidence" in failures[0]["reason"]

    def test_carrying_a_figure_makes_it_a_claim(self, ground):
        ok, failures, _ = _check(
            [{"id": "c1", "type": "GENERAL", "block": "paragraph",
              "text": "Most estates run 40 percent CAD workloads."}], ground)
        assert not ok
        assert "carries a figure" in failures[0]["reason"]

    def test_genuine_domain_reasoning_passes(self, ground):
        ok, failures, _ = _check(
            [{"id": "c1", "type": "GENERAL", "block": "paragraph",
              "text": "CAD workloads are the usual trigger for "
                      "workstation-class hardware."}], ground)
        assert ok, failures


class TestTheWholeAnswerChecks:

    def test_an_invented_figure_anywhere_is_rejected(self, ground):
        """The grounding check that predates this module, over the published
        text rather than per sentence."""
        ok, failures, _ = _check(
            [_fact("c1", "They run 4271 devices.", "tech_stack_matrix", "AutoCAD")],
            ground)
        assert not ok
        assert "4271" in failures[0]["reason"]

    def test_a_figure_the_data_holds_passes_despite_formatting(self, ground):
        ok, failures, _ = _check(
            [_fact("c1", "The estate carries 220 technologies.",
                   "tech_stack_matrix", "220")], ground)
        assert ok, failures

    def test_an_hp_line_the_evidence_never_mentions_is_rejected(self, ground):
        """The prompt has always said "name an HP product only if it appears
        in the evidence", and nothing checked it."""
        ok, failures, _ = _check(
            [_fact("c1", "HP Wolf Security would suit them.",
                   "tech_stack_matrix", "AutoCAD")], ground)
        assert not ok
        assert "does not appear" in failures[0]["reason"].lower()


# ---------------------------------------------------------------------------
# Three outputs, never conflated
# ---------------------------------------------------------------------------

class TestRenderingAndCleanOutput:

    def test_the_rendered_answer_carries_the_tags_the_ui_parses(self):
        """`AnswerWithCitations` matches the tokens inside each bracket
        against `citations[].evidence_id` to place its footnote markers.
        Emitting them is what keeps that UI untouched."""
        rendered = claims.render(claims.parse({"segments": FACTS}))
        assert "[tech_stack_matrix]" in rendered
        assert "[opportunity_narrative_plays]" in rendered

    def test_the_clean_answer_carries_none(self):
        """What the copy button, the email draft and the history take."""
        clean = claims.clean(claims.parse({"segments": FACTS}))
        assert "[" not in clean and "]" not in clean
        assert "AutoCAD" in clean

    def test_both_say_the_same_thing(self):
        segments = claims.parse({"segments": [*FACTS, _synthesis("So that follows.")]})
        rendered, clean = claims.render(segments), claims.clean(segments)
        for segment in segments:
            assert segment["text"] in rendered
            assert segment["text"] in clean

    def test_a_general_segment_is_rendered_without_a_citation(self):
        segments = claims.parse({"segments": [
            {"id": "c1", "type": "GENERAL", "block": "paragraph",
             "text": "This is how it usually works."}]})
        assert claims.render(segments) == "This is how it usually works."

    def test_blocks_survive_into_the_layout(self):
        segments = claims.parse({"segments": [
            {"id": "c1", "type": "GENERAL", "block": "heading", "text": "FACTS:"},
            _fact("c2", "They run AutoCAD.", "tech_stack_matrix", "AutoCAD",
                  block="bullet")]})
        rendered = claims.render(segments)
        assert rendered.startswith("FACTS:")
        assert "- They run AutoCAD. [tech_stack_matrix]" in rendered


class TestParsing:

    def test_a_fenced_json_block_is_read(self):
        raw = '```json\n{"segments": [{"id": "c1", "type": "GENERAL", "text": "Hi."}]}\n```'
        assert claims.parse(raw)[0]["text"] == "Hi."

    def test_prose_instead_of_json_is_an_error(self):
        with pytest.raises(claims.ClaimError):
            claims.parse("ANSWER: they run AutoCAD [tech_stack_matrix]")

    def test_an_empty_answer_is_an_error(self):
        with pytest.raises(claims.ClaimError):
            claims.parse("")

    def test_a_heading_used_as_a_type_is_understood(self):
        """The model reaches for HEADING as a type as readily as a block. It
        cost a whole generation the first time it did."""
        segments = claims.parse({"segments": [
            {"id": "c1", "type": "HEADING", "block": "heading", "text": "ANSWER:"}]})
        assert segments[0]["type"] == claims.GENERAL


class TestWhatSurvivesWhenRepairFails:
    """The last resort. Publishing the part of an answer that held beats
    telling a seller the platform holds nothing about an account it holds
    350,000 characters on."""

    def test_a_failing_segment_and_its_dependents_are_dropped(self):
        segments = claims.parse({"segments": [
            *FACTS, _synthesis("So that follows.", depends_on=["c1", "c9"])]})
        kept = claims.surviving(segments, [{"id": "c3", "reason": "x"}])
        assert [s["id"] for s in kept] == ["c1", "c2"]

    def test_a_heading_left_over_nothing_goes_with_it(self):
        """"RECOMMENDED NEXT STEPS:" above an empty space reads as a section
        the platform failed to write."""
        segments = claims.parse({"segments": [
            _fact("c1", "They run AutoCAD.", "tech_stack_matrix", "AutoCAD"),
            {"id": "c2", "type": "GENERAL", "block": "heading",
             "text": "RECOMMENDED NEXT STEPS:"},
            _synthesis("Do the thing.", depends_on=["c1"])]})
        kept = claims.surviving(segments, [{"id": "c3", "reason": "x"}])
        assert [s["id"] for s in kept] == ["c1"]

    def test_nothing_substantive_left_means_nothing_published(self):
        segments = claims.parse({"segments": [
            {"id": "c1", "type": "GENERAL", "block": "heading", "text": "ANSWER:"},
            _fact("c2", "They run AutoCAD.", "tech_stack_matrix", "AutoCAD")]})
        assert claims.surviving(segments, [{"id": "c2", "reason": "x"}]) == []


class TestTheRepairNamesWhatFailed:

    def test_it_names_the_segment(self):
        notes = claims.repair_notes([{"id": "c4", "reason": "its quote is wrong"}])
        assert "c4" in notes
        assert "its quote is wrong" in notes

    def test_nothing_failed_means_no_notes(self):
        assert claims.repair_notes([]) == ""


# ---------------------------------------------------------------------------
# What the API publishes
# ---------------------------------------------------------------------------

class TestTheRefusalSaysWhichThingWentWrong:
    """Three unrelated failures printed one message - including the case where
    the model answered and the gate rejected it. A seller reading "nothing in
    it supports an answer here" on a 350,000-character payload concludes the
    platform holds nothing about the account."""

    def _body(self, cause):
        from app.services.strategy import chat
        return chat._unavailable("Astra", "q", "topic", "reason", cause=cause)

    def test_no_data_says_nothing_is_published(self):
        from app.services.strategy import chat
        body = self._body(chat.CAUSE_NO_DATA)["answer"]
        assert "No feature has published anything" in body

    def test_a_model_failure_says_it_is_ours(self):
        from app.services.strategy import chat
        body = self._body(chat.CAUSE_MODEL)["answer"]
        assert "fault on our side, not a gap in the data" in body

    def test_an_unevidenced_answer_says_it_was_drafted(self):
        from app.services.strategy import chat
        body = self._body(chat.CAUSE_UNEVIDENCED)["answer"]
        assert "drafted an answer" in body
        assert "could not evidence" in body

    def test_the_three_differ(self):
        from app.services.strategy import chat
        bodies = {self._body(c)["answer"] for c in
                  (chat.CAUSE_NO_DATA, chat.CAUSE_MODEL, chat.CAUSE_UNEVIDENCED)}
        assert len(bodies) == 3

    def test_every_refusal_still_carries_the_contract(self):
        from app.services.strategy import chat
        payload = self._body(chat.CAUSE_MODEL)
        for key in ("answer", "answer_clean", "claims", "citations",
                    "available", "unavailable_cause"):
            assert key in payload
        assert payload["available"] is False
        assert payload["citations"] == []

    def test_the_persona_refusal_is_unchanged(self):
        """Roleplay breaks character on purpose here, and that wording was
        reasoned about - dressing a platform failure as the character
        stonewalling teaches the seller something that never happened."""
        from app.services.strategy import chat
        body = chat._unavailable("Astra", "q", "t", "r",
                                 persona={"title": "CFO"})["answer"]
        assert "The rehearsal stopped here" in body


class TestThePublishedPayloadKeepsThemApart:

    def test_the_three_outputs_are_separate_keys(self):
        from app.services.strategy import chat
        segments = claims.parse({"segments": FACTS})
        turn = {"question": "q", "topic": "t", "mode": "advisor",
                "persona": None, "sections": [], "widget_keys": ["a"],
                "payload": "x", "company": "Astra"}

        class _Timer:
            counters: typing.ClassVar[dict] = {}

            def as_dict(self):
                return {}

        published = chat._published(turn, claims.render(segments), [], [],
                                    _Timer(), segments=segments)
        assert "[tech_stack_matrix]" in published["answer"]
        assert "[" not in published["answer_clean"]
        assert len(published["claims"]) == len(FACTS)
        assert published["available"] is True

    def test_a_partial_answer_says_how_much_was_dropped(self):
        from app.services.strategy import chat
        segments = claims.parse({"segments": FACTS})
        turn = {"question": "q", "topic": "t", "mode": "advisor",
                "persona": None, "sections": [], "widget_keys": ["a"],
                "payload": "x", "company": "Astra"}

        class _Timer:
            counters: typing.ClassVar[dict] = {}

            def as_dict(self):
                return {}

        published = chat._published(turn, "x", [], [], _Timer(),
                                    segments=segments, dropped=3)
        assert published["generation"]["segments_dropped"] == 3


class TestRoleplayIsUntouched:
    """Its answer is spoken prose with literal tags, decidable on a prefix,
    and its validator carries rules the advisor does not have - banned names,
    section overlap. Only the advisor path changed."""

    def test_the_prose_validator_is_still_there(self):
        from app.services.strategy import chat
        for name in ("_validate", "_validate_roleplay", "_claim_sentences",
                     "_asserts_facts", "_validated_prefix", "_last_citation_end"):
            assert hasattr(chat, name), name

    def test_the_four_tuple_contract_holds(self):
        from app.services.strategy import chat
        turn = {"persona": None, "payload": "===== a_section (feature: f) =====\nx\n",
                "widget_keys": ["a_section"], "banned": []}
        result = chat._check(turn, "ANSWER: nothing to report.")
        assert len(result) == 4


# ---------------------------------------------------------------------------
# Advice, held to its own standard
# ---------------------------------------------------------------------------

def _recommendation(text, depends_on=("c1", "c2"), id_="c4"):
    return {"id": id_, "type": "RECOMMENDATION", "block": "bullet",
            "text": text, "depends_on": list(depends_on)}


class TestARecommendationMayPlan:
    """The failure this type was added for.

    Asked for a 90-day campaign plan, the platform answered with the account's
    revenue, its headcount and fourteen stakeholder names under a RECOMMENDED
    NEXT STEPS heading - and not one step. Every planning sentence had been
    rejected and `surviving()` published the wreckage.

    The cause was one line: a SYNTHESIS may carry no figure its dependencies
    do not carry, and "week 1" is a figure. A plan is made of figures, so a
    plan could not be published at all.
    """

    @pytest.mark.parametrize("step", [
        "Open with the design estate in week 1, then follow up a week later.",
        "Plan three touches over 30 days before asking for a meeting.",
        "Run a 90-day sequence: weeks 1-4 on the workstation case.",
        "Send the first note on day 1 and a second within 10 days.",
        "Follow up on LinkedIn if the first two emails go unanswered.",
    ])
    def test_the_plans_own_schedule_needs_no_evidence(self, ground, step):
        ok, failures, _ = _check([*FACTS, _recommendation(step)], ground)
        assert ok, failures

    def test_it_still_may_not_name_a_person_nobody_cited(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _recommendation("Approach Mike Higgins in week 1.")], ground)
        assert not ok
        assert "Higgins" in failures[0]["reason"] or "higgins" in failures[0]["reason"]

    def test_it_still_may_not_invent_an_hp_line(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _recommendation("Lead with Poly Studio on the first call.")],
            ground)
        assert not ok

    def test_it_still_may_not_state_an_account_figure(self, ground):
        """A number that is not the plan's own schedule is an account claim,
        and needs a FACT like any other."""
        ok, failures, _ = _check(
            [*FACTS, _recommendation("Open on their 4200 seats of CAD.")], ground)
        assert not ok
        assert "4200" in failures[0]["reason"]

    def test_it_rests_on_something_like_any_conclusion(self, ground):
        bare = _recommendation("Just call them.", depends_on=())
        ok, failures, _ = _check([bare], ground)
        assert not ok
        assert "names no claim it rests on" in failures[0]["reason"]

    def test_it_carries_the_citations_of_what_it_rests_on(self, ground):
        segments = claims.parse({"segments": [
            *FACTS, _recommendation("Open on the design estate in week 1.")]})
        rendered = claims.render(segments)
        assert "[tech_stack_matrix, opportunity_narrative_plays]" in rendered

    def test_the_whole_answer_figure_sweep_spares_the_plan(self, ground):
        """`unsourced_numbers` runs over the published answer and would reject
        "week 2" for not appearing in the account's data. Recommendations are
        excluded from that sweep; facts are not."""
        ok, failures, _ = _check(
            [*FACTS, _recommendation("Three touches in weeks 2, 5 and 9.")], ground)
        assert ok, failures

    def test_a_plan_survives_the_retry_budget(self, ground):
        """What the seller actually lost: when OTHER segments fail, the steps
        must be among what `surviving` keeps.

        A step resting on a fact that failed is still dropped - that part is
        right, and is why this fails an unrelated segment rather than one the
        recommendation depends on."""
        unrelated = _fact("c9", "They run Microsoft Defender.",
                          "tech_stack_matrix", "Microsoft Defender")
        segments = claims.parse({"segments": [
            *FACTS, unrelated,
            _recommendation("Open in week 1 on the design estate.")]})
        kept = claims.surviving(segments, [{"id": "c9", "reason": "x"}])
        assert any(s["type"] == claims.RECOMMENDATION for s in kept)
        assert not any(s["id"] == "c9" for s in kept)

    @pytest.mark.parametrize("alias", ["ADVICE", "NEXT_STEP", "PLAN", "ACTION"])
    def test_the_words_the_model_reaches_for_land_on_the_type(self, alias):
        parsed = claims.parse({"segments": [
            {"id": "c1", "type": alias, "block": "bullet", "text": "Do the thing.",
             "depends_on": ["c0"]}]})
        assert parsed[0]["type"] == claims.RECOMMENDATION


class TestWhatAConclusionMayDrawOn:
    """The client's rule, and where it is looked up.

    The rule is unchanged: a conclusion may introduce no account fact, number,
    technology, relationship or event that the evidence does not support. What
    changed is WHERE "supported" is looked up. It used to mean "appears in the
    two or three facts this sentence listed as dependencies", which rejected
    conclusions naming things that are plainly in the account's data - and
    taught the model that writing facts was safe and answering was not.

    It now means "appears anywhere in the payload": `context.build()`, the
    committed output of every contributing feature. Not the raw uploads, and
    not the model's own knowledge of the company.
    """

    def test_it_may_name_something_the_evidence_holds_elsewhere(self, ground):
        """Capex and 36 are in news_signals_feed, which neither dependency
        cites. This is the sentence the old lookup threw away."""
        ok, failures, _ = _check(
            [*FACTS, _synthesis("Their Capex plans make the timing right.")],
            ground)
        assert ok, failures

    def test_a_figure_elsewhere_in_the_evidence_is_supported(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("The 36 trillion capex is the backdrop.")],
            ground)
        assert ok, failures

    def test_a_conclusion_still_may_not_carry_a_new_figure(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So they should start in week 1.")], ground)
        assert not ok
        assert "figure" in failures[0]["reason"]

    def test_a_conclusion_still_may_not_name_a_new_thing(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So their Citrix estate is the way in.")], ground)
        assert not ok
        assert "citrix" in failures[0]["reason"].lower()

    def test_a_conclusion_drawn_from_its_facts_still_passes(self, ground):
        ok, failures, _ = _check(
            [*FACTS, _synthesis("So the workstation case is the strongest.")], ground)
        assert ok, failures
