"""A rewrite built from the evaluator's own suggestions must pass its own checks.

Reported on AEON CO., LTD. - JP, 12 Oct, after ticking the tool's suggestions:

  LinkedIn Message  "rewrite is 360 characters; LinkedIn Message allows 300"
  One-Pager         "figures not found in Account data: 128, 13"

Both were the evaluation and the rewrite working from different facts and
limits. The evaluation recommended additions without knowing the cap, and
recommended citing HP case studies the rewrite's check had never been given.

Run: python -m pytest tests/test_evaluator_rewrite.py -v
"""

import json
import os
import sys
import typing

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database import mongodb
from app.services.evaluator import evaluate as E, formats as F, sources as SRC
from app.services.extractors.grounding import build_corpus, corpus_from_texts
from app.services.hp import buyer_personas as bp
from regen_fakes import FakeDb

PROOF = [{"line": "Managed Print Services",
          "text": "Seven & i cut device downtime 13% across 128 stores with HP Managed Print",
          "customer": "Seven & i", "industry": "retail"}]
PERSONA = {"name": "Taro Yamada", "is_named_person": True, "title": "CIO"}


def _sources(draft="We help retailers modernise their device estate.", country="japan",
             account_fact="AEON operates supermarkets in Japan"):
    return SRC.EvaluatorSources(
        "acct", "AEON CO., LTD.", country,
        build_corpus({"firmographics": [{"text": account_fact}]}),
        corpus_from_texts([]), PERSONA, draft, 0, False)


# --- sources: what the evaluation offered is a source, narrowly -----------------

class TestOfferedProofIsASource:

    def test_a_figure_from_an_offered_case_study_is_supported(self):
        s = _sources().offer(PROOF, [])
        check = s.verify_claim("Seven & i cut device downtime 13% across 128 stores.")
        assert check["verdict"] == SRC.VERDICT_SUPPORTED
        assert check["via_offered_proof"] is True

    def test_it_counts_without_the_customers_name_when_the_wording_matches(self):
        s = _sources().offer(PROOF, [])
        check = s.verify_claim("A retailer cut device downtime 13% across 128 stores.")
        assert check["verdict"] == SRC.VERDICT_SUPPORTED

    def test_the_same_figure_with_nothing_offered_is_not(self):
        check = _sources().verify_claim("Seven & i cut device downtime 13% across 128 stores.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED

    def test_a_claim_about_the_account_cannot_borrow_a_case_studys_number(self):
        """Guardrail 13 holds: nothing offered is about this account."""
        s = _sources().offer(PROOF, [])
        check = s.verify_claim("AEON runs 128 stores.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED
        assert "128" in check["reasons"][0]

    def test_a_figure_in_no_source_still_fails_and_is_named(self):
        s = _sources().offer(PROOF, [])
        check = s.verify_claim("Seven & i cut device downtime 40% across 128 stores.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED
        assert "40%" in check["reasons"][0] and "128" not in check["reasons"][0]

    def test_rulebook_positioning_answers_hp_claims_only(self):
        positioning = [{"line": "HP Wolf Security", "offering": "",
                        "allowed": ["HP Wolf Security stops 99% of known threats"],
                        "prohibited": []}]
        s = _sources().offer([], positioning)
        assert s.verify_claim(
            "HP Wolf Security stops 99% of known threats.")["verdict"] == SRC.VERDICT_SUPPORTED
        assert s.verify_claim(
            "AEON blocks 99% of known threats.")["verdict"] == SRC.VERDICT_UNSUPPORTED

    def test_a_market_restriction_still_applies_to_offered_text(self):
        s = _sources(country="indonesia").offer(
            [{"text": "the world's most secure PCs cut incidents 13%", "customer": "Acme"}], [])
        check = s.verify_claim("Acme chose the world's most secure PCs and cut incidents 13%.")
        assert check["verdict"] == SRC.VERDICT_RESTRICTED


class TestAMeetingLengthIsAnAskNotAClaim:
    """A call to action asking for "a 15-minute call" was refused for the
    number 15 - there is nothing a source could hold about a meeting request."""

    @pytest.mark.parametrize("ask", [
        "Open to a 15-minute call next week?",
        "Could we take 30 minutes on Thursday?",
        "A 20 min intro call would cover it.",
    ])
    def test_a_requested_duration_is_not_checked_as_a_figure(self, ask):
        assert _sources().verify_claim(ask)["verdict"] != SRC.VERDICT_UNSUPPORTED
        assert _sources().untraceable_figures(ask) == []

    def test_a_duration_that_is_a_claim_is_still_checked(self):
        check = _sources().verify_claim("We cut downtime by 30 minutes per device.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED

    def test_another_figure_in_the_same_ask_is_still_checked(self):
        check = _sources().verify_claim("Our 45-minute demo shows a 40% saving.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED
        assert "40%" in check["reasons"][0] and "45" not in check["reasons"][0]


# --- suggestions the rewrite could not apply are not offered --------------------

class TestUntraceableSuggestionsAreWithheld:

    def _phrases(self):
        return [
            {"chunk": "We help retailers", "verdict": "Improve", "comment": "Generic.",
             "suggestion": "Cite Seven & i cutting downtime 13% across 128 stores."},
            {"chunk": "modernise", "verdict": "Change", "comment": "Vague.",
             "suggestion": "Say it saves 40% on print costs."},
            {"chunk": "device estate", "verdict": "Improve",
             "comment": "Quantify it: 9,000 devices.", "suggestion": ""},
        ]

    def test_a_suggestion_with_a_figure_no_source_holds_is_withheld(self):
        s = _sources().offer(PROOF, [])
        phrases = self._phrases()
        withheld = E._withhold_unusable(phrases, s)

        assert phrases[0]["suggestion"].startswith("Cite Seven & i"), "offered proof: kept"
        assert "actionable" not in phrases[0]
        assert phrases[1]["suggestion"] == "" and phrases[1]["actionable"] is False
        assert phrases[1]["suggestion_withheld"] == "Say it saves 40% on print costs."
        assert phrases[1]["comment"] == "Vague.", "the phrase and its reason stay"
        # No suggestion, so the dashboard would tick the comment - also not tickable.
        assert phrases[2]["actionable"] is False
        assert [w["reason"] for w in withheld] == [
            "a figure no source holds (40%)", "a figure no source holds (9,000)"]
        assert phrases[1]["withheld_reason"] == "a figure no source holds (40%)"

    def test_a_figure_already_in_the_draft_is_traceable(self):
        s = _sources(draft="Your 128 stores deserve better devices.")
        phrases = [{"chunk": "Your 128 stores", "verdict": "Improve", "comment": "",
                    "suggestion": "Lead with the 128 stores."}]
        assert E._withhold_unusable(phrases, s) == []


# --- the evaluation is told the cap ---------------------------------------------

def _words(n, word="word"):
    return " ".join([word] * n)


class TestTheEvaluationKnowsTheCap:

    def test_a_capped_format_states_the_limit_and_the_current_length(self):
        block = E._cap_block(F.FORMATS["linkedin_message"], _words(40))
        assert "at most 110 words" in block and "this message is 40" in block
        assert "REPLACING or CUTTING" not in block

    def test_near_the_cap_it_asks_for_swaps_not_additions(self):
        block = E._cap_block(F.FORMATS["linkedin_message"], _words(100))
        assert "REPLACING or" in block and "what" in block

    def test_an_email_is_held_to_its_180_word_guide(self):
        """AEON, 12 Nov: an uncapped email rewrite came out at 184 words and
        its own evaluation marked it over the 180-word guide."""
        block = E._cap_block(F.FORMATS["email"], _words(150))
        assert "at most 180 words" in block and "this message is 150" in block

    def test_an_uncapped_format_says_nothing(self):
        assert E._cap_block({"label": "Note", "rewrite": {}}, _words(500)) == ""


# --- the budget the model is given is the real one ------------------------------

class TestTheBudgetCountsEverythingPythonAdds:
    """LinkedIn Message is capped in words (110), as Content Studio writes it:
    the greeting's words count; blank lines are not words."""

    def test_the_greeting_is_subtracted(self):
        spec = F.body_budget("linkedin_message", PERSONA, "")
        greeting = F.compose_greeting(PERSONA, F.rewrite_contract("linkedin_message"), "")
        words = len(greeting.split())
        assert spec == {"max": 110, "unit": "words", "composed": words, "separators": 0,
                        "budget": 110 - words}

    def test_a_draft_that_meets_the_budget_exactly_is_accepted(self):
        spec = F.body_budget("linkedin_message", PERSONA, "")
        third = spec["budget"] // 3
        raw = {"opening": _words(third, "a"), "body_sections": [{"text": _words(third, "b")}],
               "cta": _words(spec["budget"] - 2 * third, "c")}
        rewrite, faults = F.validate_rewrite(raw, "linkedin_message", (), PERSONA, "")
        assert faults == [] and len(rewrite["plain_text"].split()) == 110

    def test_a_content_studio_length_message_is_not_refused(self):
        """AEON, 12 Nov: a 76-word Content Studio message was refused for 318
        characters against a 300-character cap."""
        raw = {"opening": _words(25, "a"), "body_sections": [{"text": _words(40, "b")}],
               "cta": _words(15, "c")}
        _rewrite, faults = F.validate_rewrite(raw, "linkedin_message", (), PERSONA, "")
        assert faults == []
        checks = F.structure_checks("Hi Taro,\n\n" + _words(80), "linkedin_message")
        assert not any(c["check"] == "character_limit" for c in checks["checks"])

    def test_the_retry_note_gives_the_numbers(self):
        raw = {"opening": _words(50, "a"), "body_sections": [{"text": _words(50, "b")}],
               "cta": _words(20, "c")}
        _clean, faults, draft = F.validate_rewrite(raw, "linkedin_message", (), PERSONA, "",
                                                   keep_draft=True)
        assert F.length_only(faults)
        note = F.length_retry_note("linkedin_message", draft, PERSONA, "")
        budget = F.body_budget("linkedin_message", PERSONA, "")["budget"]
        assert "totalled 120 words" in note
        assert "at most %d" % budget in note
        assert "Cut at least %d words" % (120 - budget) in note
        assert "opening: 50 words" in note


# --- rewrite_message, end to end with a scripted model ---------------------------

def _answer(opening, body, cta):
    return {"opening": opening, "body_sections": [{"text": body}], "cta": cta}


LONG = _answer(_words(50, "open"), _words(50, "body"), _words(20, "ask"))  # 123 words
FITS = _answer("Saw AEON's store refresh plans.",
               "We help retailers modernise their device estate with less downtime.",
               "Open to a 15-minute call next week?")


@pytest.fixture
def rewrite(monkeypatch):
    """Runs `rewrite_message` against a scripted model. Returns (run, asked)."""
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    asked = []

    def run(answers, fmt="linkedin_message", original="We help retailers modernise.",
            proof=(), selected=("Make it specific",), persona=None, country="japan",
            account_fact="AEON operates supermarkets in Japan"):
        evaluation = {"format": fmt, "format_label": F.FORMATS[fmt]["label"],
                      "objective_label": "Awareness", "message_text": original,
                      "persona_contact_id": "p1", "mode": E.MODE_LITE,
                      "proof_available": list(proof), "rulebook_positioning": []}
        stored = {}
        monkeypatch.setattr(E.storage, "find_existing", lambda *_a: {**evaluation, **stored})
        monkeypatch.setattr(E.storage, "resolve_persona", lambda *_a: persona or PERSONA)
        monkeypatch.setattr(E.SRC, "build", lambda *_a, **_k: _sources(
            original, country, account_fact))
        monkeypatch.setattr(E.content_audit, "record", lambda *_a, **_k: None)
        script = list(answers)

        def ask(_system, user):
            asked.append(user)
            return script.pop(0) if script else None

        monkeypatch.setattr(E, "_ask", ask)
        return E.rewrite_message("acct", "f" * 32, list(selected))

    return run, asked


class TestATooLongRewriteIsShortenedNotRefused:

    def test_over_twice_then_the_shorten_pass_fits(self, rewrite):
        run, asked = rewrite
        run([LONG, LONG, FITS])
        assert len(asked) == 3, "attempt, retry, one shorten pass"
        assert "Cut at least" in asked[1], "the retry is told how much to cut"
        assert asked[2].startswith("SHORTEN THIS REWRITE")
        assert json.dumps(_words(50, "open")) in asked[2], "it is shown its own draft"

    def test_it_stops_after_two_shorten_passes_with_a_message_to_act_on(self, rewrite):
        run, asked = rewrite
        shorter = _answer(_words(45, "open"), _words(45, "body"), _words(20, "ask"))
        with pytest.raises(E.EvaluationError) as err:
            run([LONG, LONG, shorter, shorter, FITS])
        assert len(asked) == 2 + E.SHORTEN_PASSES, "never a third shorten pass"
        message = str(err.value)
        assert "don't fit in a LinkedIn Message (110 words)" in message
        assert "Select fewer changes" in message
        assert "format contract" not in message
        assert err.value.code == "REWRITE_TOO_LONG"
        shortest = len(F.validate_rewrite(shorter, "linkedin_message", (), PERSONA, "",
                                          keep_draft=True)[2]["plain_text"].split())
        assert "came out at %d" % shortest in message

    def test_a_fault_that_is_not_length_is_never_sent_to_shorten(self, rewrite):
        """A shape fault goes to the repair pass, never the shorten pass."""
        run, asked = rewrite
        broken = {"opening": "", "body_sections": [], "cta": ""}
        run([broken, broken, FITS])
        assert len(asked) == 3
        assert asked[2].startswith("FIX THIS REWRITE")
        assert not any(a.startswith("SHORTEN THIS REWRITE") for a in asked)

    def test_a_shortened_draft_that_invents_a_figure_is_still_refused(self, rewrite):
        run, _asked = rewrite
        invented = _answer("Saw AEON's plans.", "We cut costs 40% for retailers.", "Call?")
        with pytest.raises(E.EvaluationError) as err:
            run([LONG, LONG, invented])
        assert "40%" in str(err.value) and "Untick the change" in str(err.value)
        assert err.value.code == "REWRITE_UNSUPPORTED_FIGURE"


class TestARewriteMayCiteWhatTheEvaluationOffered:

    ONE_PAGER: typing.ClassVar[dict] = {"headline": "Less downtime across every store",
                 "opening": "AEON's stores depend on devices that stay up.",
                 "body_sections": [
                     {"heading": "The challenge", "text": "Devices that fail close tills."},
                     {"heading": "Proof", "text": "Seven & i cut device downtime 13% "
                                                  "across 128 stores with HP Managed Print."},
                     {"heading": "Fit", "text": "The same service fits a retail estate."},
                     {"heading": "Next step", "text": "A review of the current estate."}],
                 "cta": "Let's review your estate together."}

    def test_the_reported_one_pager_case_now_passes(self, rewrite):
        run, asked = rewrite
        run([self.ONE_PAGER], fmt="one_pager", proof=PROOF,
            original="AEON's stores depend on devices that stay up. We can help.",
            selected=("Cite the Seven & i case study",))
        assert "HP PROOF AND POSITIONING YOU MAY CITE" in asked[0]
        assert "13% across 128 stores" in asked[0], "exact wording reaches the rewrite"

    def test_without_the_offered_proof_it_is_refused_with_the_figures_named(self, rewrite):
        run, _asked = rewrite
        with pytest.raises(E.EvaluationError) as err:
            run([self.ONE_PAGER], fmt="one_pager", proof=(),
                original="AEON's stores depend on devices that stay up. We can help.")
        message = str(err.value)
        assert "128" in message and "13%" in message
        assert "Untick the change that adds it" in message


# =============================================================================
# Part 2 - the remaining ways the tool could suggest a change and then refuse it
# =============================================================================

CFO = {"persona_id": "cfo", "is_named_person": False, "name": None}
CFO_CARD = bp.evaluator_card("cfo")
DENIED = bp.denied_lines("cfo")[0]            # a line a CFO is never offered
BLOCKED_MARKET = "indonesia"                  # blocks superlatives and competitors


def _phrase(suggestion, chunk="We help retailers", comment="Generic."):
    return {"chunk": chunk, "verdict": "Improve", "comment": comment,
            "suggestion": suggestion}


class TestASuggestionTheRewriteWouldRefuseHasNoCheckbox:

    def test_a_line_this_persona_is_not_offered(self):
        phrases = [_phrase("Mention %s for their meeting rooms." % DENIED)]
        withheld = E._withhold_unusable(phrases, _sources(), CFO_CARD)
        assert phrases[0]["actionable"] is False and phrases[0]["suggestion"] == ""
        assert DENIED in withheld[0]["reason"]

    def test_a_superlative_where_the_market_blocks_them(self):
        phrases = [_phrase("Say it is the world's most secure PC.")]
        withheld = E._withhold_unusable(phrases, _sources(country=BLOCKED_MARKET))
        assert phrases[0]["actionable"] is False
        assert "superlative" in withheld[0]["reason"]

    def test_a_competitor_where_the_market_blocks_them(self):
        phrases = [_phrase("Compare it with Lenovo's fleet pricing.")]
        withheld = E._withhold_unusable(phrases, _sources(country=BLOCKED_MARKET))
        assert phrases[0]["actionable"] is False
        assert "competitor" in withheld[0]["reason"]

    def test_a_link_no_source_holds(self):
        phrases = [_phrase("Link to https://example.com/roi-calculator for the numbers.")]
        withheld = E._withhold_unusable(phrases, _sources())
        assert phrases[0]["actionable"] is False
        assert "link" in withheld[0]["reason"]

    @pytest.mark.parametrize("draft, suggestion, country", [
        ("We also offer %s for your rooms." % DENIED, "Remove the %s mention." % DENIED, "japan"),
        ("It is the world's most secure PC.", "Drop 'the world's most secure'.", BLOCKED_MARKET),
        ("Unlike Lenovo, we include support.", "Cut the Lenovo comparison.", BLOCKED_MARKET),
    ])
    def test_telling_the_seller_to_remove_one_stays_tickable(self, draft, suggestion, country):
        """The term is already in the draft; the suggestion takes it out."""
        phrases = [_phrase(suggestion, chunk=draft[:20])]
        assert E._withhold_unusable(phrases, _sources(draft, country), CFO_CARD) == []
        assert phrases[0]["suggestion"] == suggestion and "actionable" not in phrases[0]

    def test_a_superlative_is_fine_where_the_market_allows_it(self):
        phrases = [_phrase("Say it is the world's most secure PC.")]
        assert E._withhold_unusable(phrases, _sources(country="japan")) == []


class TestGuardrail13IsUnchanged:

    def test_a_mixed_sentence_is_still_unsupported_and_says_how_to_fix_it(self):
        s = _sources(account_fact="AEON employs 20,000 staff")
        check = s.verify_claim("AEON's 20,000 staff would benefit from HP EliteBook.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED, "the verdict is not softened"
        assert check["routed_to"] == SRC.HP_FACT_CORPUS
        assert check["hints"] == [{"kind": "mixed_sentence", "figures": ["20,000"],
                                   "held_by": "Account data"}]


MIXED = _answer("Saw your store refresh plans.",
                "AEON's 20,000 staff would benefit from HP EliteBook.",
                "Worth a short call?")
SPLIT = _answer("Saw your store refresh plans.",
                "AEON employs 20,000 staff. HP EliteBook suits a fleet that size.",
                "Worth a short call?")
INVENTED = _answer("Saw your plans.", "We cut costs 40% for retailers.", "Worth a call?")
CLEAN = _answer("Saw your plans.", "We cut costs for retailers.", "Worth a call?")


class TestAClaimFaultGetsOneRepairPass:

    def test_a_mixed_sentence_is_split_and_published(self, rewrite):
        run, asked = rewrite
        run([MIXED, SPLIT], original="We help AEON.",
            account_fact="AEON employs 20,000 staff")
        assert len(asked) == 2
        assert asked[1].startswith("FIX THIS REWRITE")
        assert "two separate sentences" in asked[1]
        assert "20,000 staff would benefit" in asked[1], "it is shown its own draft"

    def test_an_invented_figure_removed_on_repair_is_published(self, rewrite):
        run, asked = rewrite
        run([INVENTED, CLEAN])
        assert len(asked) == 2 and "Remove it" in asked[1]

    def test_still_wrong_after_the_one_repair_is_refused_with_a_clear_message(self, rewrite):
        run, asked = rewrite
        with pytest.raises(E.EvaluationError) as err:
            run([INVENTED, INVENTED, CLEAN, CLEAN])
        assert len(asked) == 2, "exactly one repair pass"
        assert "40%" in str(err.value) and "Untick the change" in str(err.value)
        assert err.value.code == "REWRITE_UNSUPPORTED_FIGURE"

    def test_a_superlative_added_in_a_blocked_market_is_named_plainly(self, rewrite):
        run, _asked = rewrite
        boast = _answer("Saw your plans.", "It is the world's most secure PC.", "Call?")
        with pytest.raises(E.EvaluationError) as err:
            run([boast, boast], country=BLOCKED_MARKET)
        assert "superlative claims are not permitted in Indonesia" in str(err.value)


def _one_pager(sections):
    return {"headline": "Less downtime across every store",
            "opening": "AEON's stores depend on devices that stay up.",
            "body_sections": [{"heading": "Part %d" % i, "text": "Point %d stands." % i}
                              for i in range(1, sections + 1)],
            "cta": "Let's review your estate together."}


class TestAShapeFaultIsRepairedAndExplained:

    def test_a_one_pager_with_too_few_sections_is_repaired(self, rewrite):
        run, asked = rewrite
        run([_one_pager(2), _one_pager(2), _one_pager(4)], fmt="one_pager",
            original="AEON's stores depend on devices that stay up. We can help.")
        assert len(asked) == 3
        assert "needs exactly 4 body sections; you returned 2" in asked[1]
        assert asked[2].startswith("FIX THIS REWRITE")

    def test_a_shape_that_cannot_be_fixed_reads_neutrally(self, rewrite):
        """Client rule, 21 Oct: a malformed rewrite is the model's failure, and
        the seller sees one neutral line - no fault list, raw or plain."""
        run, asked = rewrite
        with pytest.raises(E.EvaluationError) as err:
            run([_one_pager(2)] * 6, fmt="one_pager",
                original="AEON's stores depend on devices that stay up. We can help.")
        message = str(err.value)
        assert message == "Something went wrong. Please try again."
        assert len(asked) == 3, "attempt, retry, one repair - and no more"

    def test_a_line_the_persona_cannot_be_sent_is_not_repaired_and_is_named(self, rewrite):
        run, asked = rewrite
        pitch = _answer("Saw your plans.", "We also offer %s for your rooms." % DENIED,
                        "Worth a call?")
        with pytest.raises(E.EvaluationError) as err:
            run([pitch, pitch, CLEAN], persona=CFO)
        assert len(asked) == 2, "a gate rejection gets its retry and no repair pass"
        assert DENIED in asked[1] and "Remove it completely" in asked[1]
        assert DENIED in str(err.value) and "Untick the change" in str(err.value)

    def test_no_answer_from_the_model_says_try_again(self, rewrite):
        run, _asked = rewrite
        with pytest.raises(E.EvaluationError, match=r"^Something went wrong\. Please try again\.$"):
            run([])


class TestOneRequestNeverMakesMoreThanItsBudgetOfCalls:

    @pytest.mark.parametrize("script", [
        [LONG] * 12,                                   # never fits
        [LONG, LONG, {"opening": "", "body_sections": [], "cta": ""}] + [LONG] * 9,
        [INVENTED] * 12,                               # never supported
        [LONG, LONG, INVENTED, INVENTED] + [LONG] * 8, # fits, then unsupported
    ])
    def test_the_cap_holds_on_every_path(self, rewrite, script):
        run, asked = rewrite
        with pytest.raises(E.EvaluationError):
            run(script)
        assert len(asked) <= E.MAX_REWRITE_CALLS == 5


class TestATickedGreetingReplacesTheSellersOwn:
    """AEON, 12 Nov: the draft "hi" with "Dear [CFO's Name]," ticked came back
    opening "hi," while Changes Applied listed the Dear line as done."""

    EMAIL = F.rewrite_contract("email")
    CFO: typing.ClassVar[dict] = {"title": "Chief Financial Officer"}

    def test_the_ticked_salutation_is_used(self):
        addressed = F.with_selected_greeting("hi", ["Dear [CFO's Name],"])
        assert F.compose_greeting(self.CFO, self.EMAIL, addressed) == "Dear [CFO's Name],"

    def test_only_the_greeting_line_changes(self):
        draft = "Hi Taro,\n\nWe help retailers.\n\nBest regards,\nAnna"
        addressed = F.with_selected_greeting(draft, ["Dear [CIO Name],"])
        assert addressed == "Dear [CIO Name],\n\nWe help retailers.\n\nBest regards,\nAnna"
        assert F.compose_signoff(self.EMAIL, addressed) == "Best regards,\n\nAnna"

    def test_a_draft_without_a_greeting_gets_the_ticked_one(self):
        addressed = F.with_selected_greeting("We help retailers.", ["Dear [CFO Name],"])
        assert F.compose_greeting(self.CFO, self.EMAIL, addressed) == "Dear [CFO Name],"

    @pytest.mark.parametrize("rec", [
        "Hi, I wanted to share how HP can help.",      # a sentence, not a salutation
        "Fix greeting: no salutation found",
        "Address the CFO by role in the greeting.",
    ])
    def test_other_changes_keep_the_sellers_greeting(self, rec):
        assert F.with_selected_greeting("hi", [rec]) == "hi"
        assert F.compose_greeting(self.CFO, self.EMAIL, "hi") == "hi,"

    def test_the_published_rewrite_opens_with_it(self, rewrite, monkeypatch):
        run, _asked = rewrite
        rendered = []
        render = F.render_rewrite
        monkeypatch.setattr(F, "render_rewrite",
                            lambda r: rendered.append(render(r)) or rendered[-1])
        run([FITS], original="Hi there,\n\nWe help retailers modernise.",
            selected=("Dear [CIO Name],", "Make it specific"))
        assert rendered and rendered[-1].startswith("Dear [CIO Name],"), rendered


class TestTheGreetingIsReadUnderTheSubjectLine:
    """AEON, 12 Nov: every email with a Subject line - every rewrite among them -
    was reported as having no greeting, so "Fix greeting" came back each time."""

    EMAIL = F.rewrite_contract("email")
    DRAFT = ("Subject: Lower TCO for AEON\n\nHi Taro,\n\nWe help retailers.\n\n"
             "Would you be open to a call?\n\nSincerely,\nAnna")

    def test_the_check_finds_it(self):
        checks = {c["check"]: c for c in F.structure_checks(self.DRAFT, "email")["checks"]}
        assert checks["greeting"]["passed"], checks["greeting"]
        assert checks["greeting"]["detail"] == "opens with 'Hi Taro,'"

    def test_the_rewrite_keeps_the_sellers_own(self):
        assert F.compose_greeting({"title": "CIO"}, self.EMAIL, self.DRAFT) == "Hi Taro,"

    def test_a_ticked_salutation_replaces_it_and_the_subject_stays(self):
        addressed = F.with_selected_greeting(self.DRAFT, ["Dear [CIO Name],"])
        assert addressed.startswith("Subject: Lower TCO for AEON\n\nDear [CIO Name],\n\n")

    def test_a_ticked_salutation_goes_under_the_subject_when_there_is_none(self):
        addressed = F.with_selected_greeting("Subject: Hello\nWe help.", ["Dear [CIO Name],"])
        assert addressed == "Subject: Hello\nDear [CIO Name],\n\nWe help."

    def test_a_rewrite_passes_its_own_greeting_check(self):
        raw = {"subject_line": "Lower TCO for AEON", "opening": "Saw your store plans.",
               "body_sections": [{"text": "We help retailers."}],
               "cta": "Would you be open to a call?"}
        rewrite, faults = F.validate_rewrite(raw, "email", (), {"title": "CIO"}, "")
        assert faults == []
        checks = F.structure_checks(rewrite["plain_text"], "email")["checks"]
        assert all(c["passed"] for c in checks), [c for c in checks if not c["passed"]]


class TestAnEmailRewriteFitsTheGuideItIsScoredAgainst:

    def test_the_budget_counts_greeting_signoff_and_subject_label(self):
        spec = F.body_budget("email", {"title": "CIO"}, "")
        # "Dear [CIO Name]," 3 + "Best regards, [Your Name]" 4 + "Subject:" 1
        assert spec == {"max": 180, "unit": "words", "composed": 8, "separators": 0,
                        "budget": 172}

    def test_a_rewrite_over_180_words_is_shortened_not_published(self):
        raw = {"subject_line": "Lower TCO", "opening": _words(60, "a"),
               "body_sections": [{"text": _words(100, "b")}], "cta": _words(20, "c")}
        _clean, faults, draft = F.validate_rewrite(raw, "email", (), {"title": "CIO"}, "",
                                                   keep_draft=True)
        assert F.length_only(faults) and faults[0].startswith("rewrite is 190 words")
        note = F.length_retry_note("email", draft, {"title": "CIO"}, "")
        assert "subject_line: 2 words" in note
        assert '"subject_line": "Lower TCO"' in F.shorten_prompt("email", draft, {"title": "CIO"}, "")


class TestScoringIsSteady:
    """AEON, 12 Nov: the same draft scored 71, then 69, then 71."""

    def test_scoring_asks_at_temperature_0_and_a_rewrite_does_not(self, monkeypatch):
        seen = []
        monkeypatch.setattr(E, "generate_gpt4o_json_completion",
                            lambda s, _u, temperature=None: seen.append((s, temperature)) or {"a": 1})
        E._ask(E.SYSTEM_PROMPT, "score this")
        E._ask(E.REWRITE_SYSTEM, "rewrite this")
        assert seen == [(E.SYSTEM_PROMPT, 0.0), (E.REWRITE_SYSTEM, 0.2)]
