"""Scoring, caching and the simulated reaction - the 12 Oct audit.

Three faults were reproduced with a scripted model before any of this was
written, and each has a test here:

  * an evaluation made while the model was down was stored and served for ever;
  * a retry that came back worse REPLACED a better first answer, and an answer
    with no scores was padded seven times and published as 50, "Average";
  * the reaction was withheld for quoting the seller's own draft, or for
    repeating a figure from it, with no retry.

Run: python -m pytest tests/test_evaluator_scoring_audit.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database import mongodb
from app.services.evaluator import evaluate as E, scoring as S, sources as SRC, verify
from app.services.extractors.grounding import build_corpus, corpus_from_texts
from regen_fakes import FakeDb

PERSONA = {"persona_id": "p1", "name": "Taro Yamada", "is_named_person": True,
           "title": "CIO"}
MESSAGE = "We help retailers cut device downtime by 40%. Open to a call?"
SIX = dict.fromkeys([S.RELEVANCE, S.IMPACT, S.BRAND_RECALL, S.CLARITY, S.CREATIVITY,
                     S.EMOTIONAL], 70)                       # Next-step missing
SEVEN = {**SIX, S.NEXT_STEP: 70}
PHRASES = [{"chunk": MESSAGE, "verdict": "Improve", "comment": "c", "suggestion": ""}]


def _sources(draft=MESSAGE):
    return SRC.EvaluatorSources(
        "acct", "AEON", "japan",
        build_corpus({"f": [{"t": "AEON operates supermarkets"}]}),
        corpus_from_texts([]), PERSONA, draft, 0, False)


def _answer(dimensions, **extra):
    return {"dimensions": dimensions, "phrases": PHRASES, "summary": "s", **extra}


@pytest.fixture
def evaluate(monkeypatch):
    """Runs `evaluate_message` against a scripted model. Returns (run, asked)."""
    db = FakeDb()
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    monkeypatch.setattr(E.storage, "resolve_persona", lambda *_a: PERSONA)
    monkeypatch.setattr(E.SRC, "build", lambda _db, _a, _p, text, *_r: _sources(text))
    asked, script = [], []

    def ask(_system, user):
        asked.append(user)
        return script.pop(0) if script else {}

    monkeypatch.setattr(E, "_ask", ask)

    def run(answers, message=MESSAGE, mode="LITE"):
        script[:] = list(answers)
        return E.evaluate_message("acct", "p1", "awareness", "email", message, mode=mode)

    return run, asked


# --- the cache holds good answers only ----------------------------------------

class TestAFailedEvaluationIsNotServedForEver:

    def test_after_an_outage_the_same_message_is_scored_again(self, evaluate):
        run, _asked = evaluate
        first = run([])                                    # the model is down
        assert first["ai_available"] is False and first["composite"] is None
        assert "Evaluate again" in first["summary"]

        second = run([_answer(SEVEN)])                     # the model is back
        assert second["ai_available"] is True and second["composite"] == 70.0
        assert second["version"] == first["version"], "the same request, answered"
        assert second["fingerprint"] == first["fingerprint"]

    def test_a_good_evaluation_is_still_served_without_the_model(self, evaluate):
        run, asked = evaluate
        run([_answer(SEVEN)])
        calls = len(asked)
        again = run([_answer(dict.fromkeys(S.ALL_DIMENSIONS, 10))])
        assert again["composite"] == 70.0 and len(asked) == calls

    def test_an_evaluation_with_no_total_is_scored_again(self, evaluate):
        run, _asked = evaluate
        bad = {**SEVEN, S.CLARITY: 400}
        first = run([_answer(bad), _answer(bad)])
        assert first["composite"] is None
        assert run([_answer(SEVEN)])["composite"] == 70.0

    def test_changed_line_breaks_are_scored_again(self, evaluate):
        """The fingerprint ignores whitespace; the stored offsets do not."""
        run, asked = evaluate
        run([_answer(SEVEN)], message="Line one. Line two?")
        calls = len(asked)
        relaid = "Line one.\n\nLine two?"
        out = run([{"dimensions": SEVEN, "summary": "s",
                    "phrases": [{"chunk": relaid, "verdict": "Keep"}]}], message=relaid)
        assert len(asked) > calls and out["message_text"] == relaid


# --- the retry may only add; pads are limited ----------------------------------

class TestAWorseRetryCannotReplaceABetterAnswer:

    def test_the_first_answers_scores_survive_a_retry_with_none(self, evaluate):
        """Reproduced: six real scores became seven pads and a total of 50."""
        run, _asked = evaluate
        out = run([_answer(SIX), {"summary": "the retry had no dimensions"}])
        assert out["dimensions_padded"] == [S.NEXT_STEP]
        assert {d: v for d, v in out["dimensions"].items() if d != S.NEXT_STEP} == dict.fromkeys(SIX, 70.0)
        assert out["composite"] == 70.0, "awareness does not weight the padded one"

    def test_the_retry_fills_the_gap_and_nothing_else_moves(self, evaluate):
        run, _asked = evaluate
        retry = {**dict.fromkeys(SIX, 10), S.NEXT_STEP: 55}
        del retry[S.CLARITY]                                # still incomplete
        out = run([_answer(SIX), _answer(retry)])
        assert out["dimensions"][S.NEXT_STEP] == 55.0
        assert out["dimensions"][S.RELEVANCE] == 70.0, "the first answer's score is kept"
        assert out["dimensions_padded"] == []

    def test_merge_attempts_reports_only_what_neither_answer_gave(self):
        valid, problems = S.merge_attempts(
            {"relevance": 70.0}, ["impact: missing", "clarity: 400 outside 0-100"],
            {"impact": 60.0}, ["relevance: missing", "clarity: missing"])
        assert valid == {"relevance": 70.0, "impact": 60.0}
        assert problems == ["clarity: missing"]


class TestATotalIsNotMadeOfPads:

    def test_an_answer_with_no_scores_publishes_no_total(self, evaluate):
        run, _asked = evaluate
        out = run([{"summary": "no dimensions"}, {"summary": "again none"}])
        assert out["composite"] is None and out["score_band"] == "Unavailable"
        assert out["dimensions_padded"] == [] and out["dimensions"] == {}
        assert "AI scoring was incomplete" in out["summary"]

    def test_three_missing_scores_are_not_padded(self):
        valid = dict.fromkeys(S.ALL_DIMENSIONS[:4], 70.0)
        problems = ["%s: missing" % d for d in S.ALL_DIMENSIONS[4:]]
        dimensions, padded, remaining = S.pad_missing(valid, problems, "awareness")
        assert padded == [] and dimensions == valid and remaining == problems

    def test_two_pads_carrying_half_the_total_are_not_enough(self):
        """Relevance (.30) + Impact (.20) = half of an Awareness total."""
        valid = {d: 70.0 for d in S.ALL_DIMENSIONS if d not in (S.RELEVANCE, S.IMPACT)}
        problems = ["relevance: missing", "impact: missing"]
        _d, padded, remaining = S.pad_missing(valid, problems, "awareness")
        assert padded == [] and remaining == problems

    def test_one_missing_score_is_still_padded_as_the_spec_says(self):
        valid = {d: 70.0 for d in S.ALL_DIMENSIONS if d != S.CLARITY}
        dimensions, padded, remaining = S.pad_missing(valid, ["clarity: missing"], "awareness")
        assert padded == [S.CLARITY] and dimensions[S.CLARITY] == 50.0 and remaining == []


class TestValidScoresAreShownEvenWithoutATotal:

    def test_one_unusable_score_does_not_blank_the_other_six(self, evaluate):
        run, _asked = evaluate
        bad = {**SEVEN, S.CLARITY: "excellent"}
        out = run([_answer(bad), _answer(bad)])
        assert out["composite"] is None
        assert len(out["dimensions"]) == 6 and S.CLARITY not in out["dimensions"]
        assert "Clarity" in out["summary"] and "no overall score" in out["summary"]

    def test_nan_is_not_a_score(self):
        valid, problems = S.validate_dimensions({**SEVEN, S.CLARITY: "nan"}, "awareness")
        assert S.CLARITY not in valid and problems == ["clarity: not numeric (nan)"]


# --- the simulated reaction ----------------------------------------------------

class TestTheReactionMayCommentOnTheDraft:

    def test_it_may_quote_the_sellers_own_words(self):
        out, faults = verify.guard_reaction(
            'Someone in this role would find "cut device downtime" too generic to act on.',
            _sources())
        assert faults == [] and out["is_simulation"] is True

    def test_it_may_repeat_a_figure_that_is_in_the_draft(self):
        out, faults = verify.guard_reaction(
            "Someone in this role would want proof behind the 40% claim before replying.",
            _sources())
        assert faults == [] and out is not None

    def test_a_quotation_that_is_not_the_drafts_is_still_refused(self):
        out, faults = verify.guard_reaction(
            'Someone in this role would say "we already have a supplier".', _sources())
        assert out is None and faults == [
            "contains a quotation; the contact has not said anything"]

    def test_an_unbalanced_quote_is_refused(self):
        out, _faults = verify.guard_reaction(
            'Someone in this role would find "cut device downtime too generic.', _sources())
        assert out is None

    def test_a_figure_from_nowhere_is_still_refused(self):
        out, faults = verify.guard_reaction(
            "Someone in this role would expect a 65% saving at least.", _sources())
        assert out is None and "65%" in faults[0]

    def test_naming_the_contact_is_still_refused(self):
        out, faults = verify.guard_reaction("Taro would find this too generic.", _sources())
        assert out is None and "names the contact" in faults[0]

    def test_the_drafts_own_phrases_are_not_given_the_same_latitude(self):
        """`draft_ok` is for commentary. The draft's claim is still unsupported."""
        check = _sources().verify_claim("We help retailers cut device downtime by 40%.")
        assert check["verdict"] == SRC.VERDICT_UNSUPPORTED


class TestAWithheldReactionGetsOneRetry:

    BAD = "Taro would find this too generic."
    GOOD = "Someone in this role would want a clearer next step."

    def test_a_second_reaction_that_passes_is_shown(self, evaluate):
        run, asked = evaluate
        out = run([_answer(SEVEN, reaction=self.BAD), {"reaction": self.GOOD}], mode="DEEP")
        assert out["reaction"]["text"] == self.GOOD and out["reaction_withheld"] == []
        assert "Your simulated reaction was rejected" in asked[-1]
        assert "names the contact" in asked[-1]

    def test_it_is_withheld_after_one_retry_and_no_more(self, evaluate):
        run, asked = evaluate
        out = run([_answer(SEVEN, reaction=self.BAD), {"reaction": self.BAD},
                   {"reaction": self.GOOD}], mode="DEEP")
        assert out["reaction"] is None and out["reaction_withheld"]
        assert sum("simulated reaction was rejected" in a for a in asked) == 1

    def test_a_good_reaction_costs_no_extra_call(self, evaluate):
        run, asked = evaluate
        run([_answer(SEVEN, reaction=self.GOOD)], mode="DEEP")
        assert len(asked) == 1


# --- wording a seller reads -----------------------------------------------------

class TestMessagesSayWhatToDo:

    def test_an_empty_message(self, evaluate):
        run, _asked = evaluate
        with pytest.raises(E.EvaluationError, match="Enter a message to evaluate"):
            run([], message="   ")

    def test_an_unknown_persona_names_no_internal_id(self, evaluate, monkeypatch):
        run, _asked = evaluate
        monkeypatch.setattr(E.storage, "resolve_persona", lambda *_a: None)
        with pytest.raises(E.EvaluationError) as err:
            run([])
        assert "Pick one from the list" in str(err.value) and "p1" not in str(err.value)

    def test_reasons_carry_no_internal_rule_numbers(self):
        s = SRC.EvaluatorSources(
            "a", "Astra", "indonesia", corpus_from_texts(["x"]), corpus_from_texts([]),
            PERSONA, "d", 0, False)
        reasons = " ".join(
            s.verify_claim("It is the world's most secure PC, unlike Lenovo.")["reasons"]
            + s.verify_claim("HP EliteBook lasts 20 hours.")["reasons"])
        assert "guardrail" not in reasons and "corpus" not in reasons
