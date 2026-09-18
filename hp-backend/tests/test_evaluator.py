"""Tests for the Message Evaluator's guardrails.

These pin the five rules that decide whether a seller can trust what the
evaluator shows them. Each one exists because the failure it prevents is silent:
a composite computed from four dimensions instead of five still looks like a
score, a phrase the model invented still reads like feedback on the draft, and a
simulated reaction that names the contact still reads like intelligence about
them.

The model is never called here. Everything under test is the Python that runs
after it answers - `validate_dimensions`, `composite`, `verify_phrases`,
`guard_reaction`, `diff_rewrite` - so these tests pin the guarantees that hold
even when the model misbehaves, which is exactly when they matter.

Sources are built as real `EvaluatorSources` over real `Corpus` objects rather
than mocks: the routing rule (guardrail 13 - an HP claim is answerable only by
the HP corpus, an account claim only by the account corpus) is part of what is
being tested, and a mocked corpus would assert nothing about it.

Run: python -m pytest tests/test_evaluator.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.evaluator import scoring as S, verify
from app.services.evaluator.sources import (
    ACCOUNT_CORPUS,
    HP_FACT_CORPUS,
    VERDICT_RESTRICTED,
    VERDICT_SUPPORTED,
    VERDICT_UNSUPPORTED,
    EvaluatorSources,
)
from app.services.extractors.grounding import corpus_from_texts

ACCOUNT_FACTS = [
    "Astra International operates 240 dealerships across Indonesia.",
    "Headcount 10001+ employees.",
    "See https://www.astra.co.id/about for the company profile.",
]

HP_FACTS = [
    "HP Elite series supports Sure Start firmware protection.",
    "HP Wolf Security is available on 42 supported device models.",
]


def _sources(draft, *, country="indonesia", persona=None, hp=True):
    """Real sources over a small, known corpus.

    `country` matters: Indonesia blocks both superlatives and competitor
    comparisons, which is what makes the `restricted` verdict reachable.
    """
    return EvaluatorSources(
        account_id="acct-1",
        company_name="Astra International",
        country=country,
        account=corpus_from_texts(ACCOUNT_FACTS),
        hp=corpus_from_texts(HP_FACTS if hp else []),
        persona=persona if persona is not None else {
            "persona_id": "contact::1",
            "name": "Stephen Dharma",
            "title": "Head of IT Operations",
            "is_named_person": True,
        },
        draft=draft,
        hp_fact_count=len(HP_FACTS) if hp else 0,
        hp_available=hp,
    )


# ---------------------------------------------------------------------------
# 1. Scores must be 0-100
#
# The formulas are the specification's and the composite is computed in Python
# precisely so a model cannot hand back a number outside the scale. What these
# pin is the refusal: an invalid dimension must invalidate the whole composite
# rather than being clamped, dropped or renormalised over what survived.
# ---------------------------------------------------------------------------

def test_weights_are_the_specified_ones():
    """HP_ABX_v3_final Feature 9 Step 4. Changing a weight changes every score
    the seller has already seen, so these are pinned against a silent edit."""
    assert S.OBJECTIVE_FORMULAS["awareness"] == {
        S.RELEVANCE: 0.30, S.IMPACT: 0.20, S.BRAND_RECALL: 0.20,
        S.CLARITY: 0.15, S.CREATIVITY: 0.15,
    }
    assert S.OBJECTIVE_FORMULAS["conversion"] == {
        S.RELEVANCE: 0.15, S.IMPACT: 0.15, S.BRAND_RECALL: 0.25,
        S.CLARITY: 0.10, S.EMOTIONAL: 0.05, S.NEXT_STEP: 0.30,
    }
    for objective, weights in S.OBJECTIVE_FORMULAS.items():
        assert sum(weights.values()) == pytest.approx(1.0), objective


@pytest.mark.parametrize("value", [-1, 101, 100.5, 1000])
def test_out_of_range_dimension_is_rejected(value):
    raw = dict.fromkeys(S.required_dimensions("awareness"), 50)
    raw[S.RELEVANCE] = value
    valid, problems = S.validate_dimensions(raw, "awareness")
    assert problems, "%r was accepted as a 0-100 score" % value
    assert S.RELEVANCE not in valid


@pytest.mark.parametrize("value", [0, 100, 50])
def test_boundary_scores_are_accepted(value):
    """0 and 100 are valid scores, not out of range."""
    raw = dict.fromkeys(S.required_dimensions("awareness"), value)
    valid, problems = S.validate_dimensions(raw, "awareness")
    assert problems == []
    assert valid[S.RELEVANCE] == float(value)


def test_non_numeric_dimension_is_rejected():
    """Including bool, which is an int in Python and would otherwise score 1."""
    raw = dict.fromkeys(S.required_dimensions("awareness"), 50)
    raw[S.CLARITY] = True
    _, problems = S.validate_dimensions(raw, "awareness")
    assert any("clarity" in p for p in problems)


def test_numeric_string_is_accepted():
    """A model returning "80" rather than 80 is a formatting slip, not a bad
    score, and costs a retry if it is treated as one."""
    raw = dict.fromkeys(S.required_dimensions("awareness"), 50)
    raw[S.IMPACT] = "80"
    valid, problems = S.validate_dimensions(raw, "awareness")
    assert problems == []
    assert valid[S.IMPACT] == 80.0


def test_all_problems_are_reported_not_just_the_first():
    """One correction round trip has to be able to fix everything at once."""
    raw = dict.fromkeys(S.required_dimensions("awareness"), 50)
    raw[S.RELEVANCE] = 150
    raw[S.CLARITY] = "n/a"
    del raw[S.IMPACT]
    _, problems = S.validate_dimensions(raw, "awareness")
    assert len(problems) == 3


def test_missing_dimension_blocks_the_composite():
    """No partial-weight fallback and no renormalising: a composite over four of
    five dimensions would look like every other score and mean something else."""
    dims = dict.fromkeys(S.required_dimensions("awareness"), 80.0)
    del dims[S.CREATIVITY]
    with pytest.raises(S.ScoringError):
        S.composite(dims, "awareness")


def test_composite_is_within_range_and_correct():
    dims = dict.fromkeys(S.required_dimensions("awareness"), 80.0)
    assert S.composite(dims, "awareness") == 80.0

    dims = {S.RELEVANCE: 100.0, S.IMPACT: 0.0, S.BRAND_RECALL: 0.0,
            S.CLARITY: 0.0, S.CREATIVITY: 0.0}
    assert S.composite(dims, "awareness") == 30.0  # 100 * 0.30

    for objective in S.OBJECTIVES:
        top = dict.fromkeys(S.required_dimensions(objective), 100.0)
        bottom = dict.fromkeys(S.required_dimensions(objective), 0.0)
        assert S.composite(top, objective) == 100.0
        assert S.composite(bottom, objective) == 0.0


# ---------------------------------------------------------------------------
# 2. The objective alone selects the formula
#
# Not the mode, not the format, not the persona. The UI prints the formula next
# to the score, so a mismatch is visible and wrong.
# ---------------------------------------------------------------------------

def test_each_objective_uses_its_own_formula():
    dims = {d: 100.0 if d == S.NEXT_STEP else 0.0 for d in S.ALL_DIMENSIONS}
    # Next-step carries 0.30 under conversion and is absent from awareness.
    assert S.composite(dims, "conversion") == 30.0
    assert S.composite(dims, "awareness") == 0.0


def test_conversion_requires_six_dimensions_others_five():
    for objective in ("awareness", "engagement", "consideration"):
        assert len(S.required_dimensions(objective)) == 5
    assert len(S.required_dimensions("conversion")) == 6


def test_unknown_objective_is_refused():
    with pytest.raises(S.ScoringError):
        S.normalize_objective("retention")


def test_advocacy_weights_are_attributed_to_the_reference_app():
    """Advocacy is not in HP_ABX_v3_final. It ships so the seller sees all five
    funnel stages, and the evaluation records where its weights came from -
    which is the whole basis on which carrying it is defensible."""
    assert "not in HP_ABX_v3_final" in S.formula_source("advocacy")
    for objective in ("awareness", "engagement", "consideration", "conversion"):
        assert S.formula_source(objective).startswith("HP_ABX_v3_final")


# ---------------------------------------------------------------------------
# 3. Unsupported claims are rejected
#
# The seller's draft is not evidence. A claim is not true because they wrote it,
# and a polished unsupported claim must still be flagged as factual.
# ---------------------------------------------------------------------------

def test_figure_absent_from_the_account_data_is_unsupported():
    src = _sources("We work with 987 dealerships in your network.")
    check = src.verify_claim("We work with 987 dealerships in your network.")
    assert check["verdict"] == VERDICT_UNSUPPORTED
    assert "987" in " ".join(check["reasons"])


def test_figure_present_in_the_account_data_is_supported():
    src = _sources("Your 240 dealerships span Indonesia.")
    assert src.verify_claim("Your 240 dealerships span Indonesia.")["verdict"] \
        == VERDICT_SUPPORTED


def test_hp_claim_routes_to_the_hp_corpus_and_never_the_account_one():
    """Guardrail 13. The account corpus holds 240; if routing leaked, an HP
    claim about 240 device models would verify against dealership data."""
    src = _sources("EliteBook supports 240 device models.")
    check = src.verify_claim("EliteBook supports 240 device models.")
    assert check["routed_to"] == HP_FACT_CORPUS
    assert check["verdict"] == VERDICT_UNSUPPORTED

    supported = src.verify_claim("HP Wolf Security covers 42 supported device models.")
    assert supported["routed_to"] == HP_FACT_CORPUS
    assert supported["verdict"] == VERDICT_SUPPORTED


@pytest.mark.parametrize("claim", [
    "HP Elite protects 240 device models.",
    # The two spellings this codebase's own prompts instruct the model to use.
    "HP Elite/Pro PCs protect 240 device models.",
    "HP Elite & Pro PCs protect 240 device models.",
    "HP Pro devices protect 240 device models.",
])
def test_hp_elite_wording_routes_to_the_hp_corpus(claim):
    """A seller writing "HP Elite" - the way the line is actually written - is
    making an HP capability claim.

    Routing it to the account corpus would let account data answer it: 240 is a
    dealership count in ACCOUNT_FACTS, and a leak here would verify an HP device
    claim against it. That is the exact failure guardrail 13 prevents."""
    src = _sources(claim)
    check = src.verify_claim(claim)
    assert check["routed_to"] == HP_FACT_CORPUS
    assert check["verdict"] == VERDICT_UNSUPPORTED


@pytest.mark.parametrize("text", [
    "Your team has elite performance standards.",
    "We ran a pro bono workshop for 240 staff.",
])
def test_ordinary_prose_still_routes_to_the_account_corpus(text):
    """The tokens are prefixed with "hp " so they do not capture ordinary
    prose. A bare "elite" or "pro" routing to the HP corpus would be the same
    leak in the opposite direction - an account claim answered by HP facts."""
    src = _sources(text)
    assert src.verify_claim(text)["routed_to"] == ACCOUNT_CORPUS


def test_account_claim_is_not_verified_by_hp_facts():
    src = _sources("Your estate runs 42 sites.")
    check = src.verify_claim("Your estate runs 42 sites.")
    assert check["routed_to"] == ACCOUNT_CORPUS
    assert check["verdict"] == VERDICT_UNSUPPORTED


def test_superlative_is_restricted_in_a_blocked_market():
    src = _sources("The world's most secure PC.")
    check = src.verify_claim("The world's most secure PC.")
    assert check["verdict"] == VERDICT_RESTRICTED


def test_competitor_naming_is_restricted_in_a_blocked_market():
    src = _sources("Unlike Lenovo, we deliver.")
    assert src.verify_claim("Unlike Lenovo, we deliver.")["verdict"] == VERDICT_RESTRICTED


def test_a_restriction_does_not_hide_an_unsourced_figure():
    """Both problems are reported. A seller who fixes only what they were shown
    would resubmit and fail again."""
    src = _sources("The world's most secure PC protects 987 sites.")
    check = src.verify_claim("The world's most secure PC protects 987 sites.")
    assert check["verdict"] == VERDICT_RESTRICTED
    assert "superlative" in check["checked"]
    assert "numbers" in check["checked"]


def test_unsupported_phrase_cannot_be_labelled_keep():
    """The model may return Keep on a claim it likes the sound of. A Keep on an
    unsupported claim tells the seller to ship it."""
    draft = "We support 987 dealerships across your network."
    src = _sources(draft)
    phrases, dropped = verify.verify_phrases(
        [{"chunk": "We support 987 dealerships", "verdict": "Keep",
          "comment": "strong and specific"}], src, max_chunks=5)
    assert dropped == []
    assert phrases[0]["verdict"] == verify.CHANGE
    assert phrases[0]["problem_type"] == verify.FACTUAL


def test_style_feedback_on_a_sound_phrase_keeps_its_verdict():
    draft = "I wanted to reach out about your refresh cycle."
    src = _sources(draft)
    phrases, _ = verify.verify_phrases(
        [{"chunk": "I wanted to reach out", "verdict": "Improve",
          "comment": "opens with the seller, not the reader"}], src, max_chunks=5)
    assert phrases[0]["verdict"] == verify.IMPROVE
    assert phrases[0]["problem_type"] == verify.STYLE


# ---------------------------------------------------------------------------
# 4. Phrase feedback must point at text the seller actually wrote
#
# A Keep/Improve/Change label on the wrong span is worse than no label: the
# seller edits the wrong sentence.
# ---------------------------------------------------------------------------

def test_phrase_not_in_the_draft_is_dropped_never_reanchored():
    draft = "Your fleet is due a refresh."
    src = _sources(draft)
    phrases, dropped = verify.verify_phrases(
        [{"chunk": "your fleet is overdue for replacement", "verdict": "Change",
          "comment": "invented"}], src, max_chunks=5)
    assert phrases == []
    assert len(dropped) == 1
    assert "not found" in dropped[0]["reason"]


def test_located_phrase_carries_the_drafts_exact_wording_and_span():
    """The span indexes the original text, and the chunk is sliced from the
    draft rather than taken from the model's quotation of it."""
    draft = "Your fleet is due a refresh this year."
    src = _sources(draft)
    phrases, _ = verify.verify_phrases(
        [{"chunk": "Your  fleet   is due", "verdict": "Improve", "comment": "x"}],
        src, max_chunks=5)
    assert len(phrases) == 1
    start, end = phrases[0]["start"], phrases[0]["end"]
    assert draft[start:end] == phrases[0]["chunk"]
    assert phrases[0]["chunk"].lower().startswith("your fleet is due")


def test_duplicate_spans_are_dropped_once():
    draft = "Your fleet is due a refresh."
    src = _sources(draft)
    phrases, dropped = verify.verify_phrases(
        [{"chunk": "Your fleet", "verdict": "Keep", "comment": "a"},
         {"chunk": "Your fleet", "verdict": "Change", "comment": "b"}],
        src, max_chunks=5)
    assert len(phrases) == 1
    assert any("duplicate" in d["reason"] for d in dropped)


def test_lite_chunk_limit_is_enforced_and_phrases_are_ordered():
    draft = "Alpha one. Bravo two. Charlie three. Delta four. Echo five. Foxtrot six."
    src = _sources(draft)
    raw = [{"chunk": c, "verdict": "Improve", "comment": "x"}
           for c in ["Foxtrot six", "Echo five", "Delta four",
                     "Charlie three", "Bravo two", "Alpha one"]]
    phrases, dropped = verify.verify_phrases(raw, src, max_chunks=5)
    assert len(phrases) == 5
    assert [p["start"] for p in phrases] == sorted(p["start"] for p in phrases)
    assert any("LITE chunk limit" in d["reason"] for d in dropped)


# ---------------------------------------------------------------------------
# 5. The simulated reaction is never a fact about the real person
#
# This is the one output a seller could mistake for intelligence about the
# contact, so a reaction that breaks the rules is withheld outright rather than
# shown with a warning attached.
# ---------------------------------------------------------------------------

def test_reaction_naming_the_contact_is_withheld():
    src = _sources("Hello.")
    reaction, faults = verify.guard_reaction(
        "Stephen would see this as relevant to his refresh planning.", src)
    assert reaction is None
    assert any("names the contact" in f for f in faults)


def test_reaction_attributing_an_inner_state_is_withheld():
    src = _sources("Hello.")
    reaction, faults = verify.guard_reaction(
        "He thinks the current fleet is adequate and wants no change.", src)
    assert reaction is None
    assert any("attributes" in f for f in faults)


def test_reaction_containing_a_quotation_is_withheld():
    src = _sources("Hello.")
    reaction, faults = verify.guard_reaction(
        'Someone in this role would ask "what is the cost?" before replying.', src)
    assert reaction is None
    assert any("quotation" in f for f in faults)


def test_reaction_with_an_unsupported_figure_is_withheld():
    src = _sources("Hello.")
    reaction, faults = verify.guard_reaction(
        "Someone in this role would weigh this against 987 open tickets.", src)
    assert reaction is None
    assert any("unsupported" in f for f in faults)


def test_clean_role_framed_reaction_is_published_as_a_simulation():
    """It publishes, and it carries the simulation label - so the UI cannot
    render it as a statement about the real contact."""
    src = _sources("Hello.")
    reaction, faults = verify.guard_reaction(
        "Someone in this role would likely scan the opening for a reason to "
        "keep reading, then look for a concrete next step.", src)
    assert faults == []
    assert reaction["is_simulation"] is True
    assert reaction["framing"] == "role"
    assert "Not a statement about the real contact" in reaction["label"]


def test_missing_reaction_is_a_fault_not_a_silent_none():
    reaction, faults = verify.guard_reaction("", _sources("Hello."))
    assert reaction is None
    assert faults


# ---------------------------------------------------------------------------
# 6. A rewrite may not smuggle in new claims
#
# Two failure modes pull in opposite directions: a rewrite that quietly drops a
# fact the seller needed, and one that invents a fact they will be held to.
# ---------------------------------------------------------------------------

def test_rewrite_introducing_an_unsourced_figure_is_a_fault():
    original = "Your dealership network is large."
    rewritten = "Your 987 dealerships are a large network."
    _, faults = verify.diff_rewrite(original, rewritten, _sources(original), [])
    assert any("unsupported" in f for f in faults)


def test_rewrite_reusing_a_sourced_figure_is_allowed():
    original = "Your dealership network is large."
    rewritten = "Your 240 dealerships are a large network."
    report, faults = verify.diff_rewrite(original, rewritten, _sources(original), [])
    assert faults == []
    assert "240" in report["facts_added"]


def test_rewrite_introducing_a_superlative_is_blocked_in_a_blocked_market():
    original = "HP devices protect your fleet."
    rewritten = "The world's most secure PC protects your fleet."
    _, faults = verify.diff_rewrite(original, rewritten, _sources(original), [])
    assert any("superlative" in f for f in faults)


def test_rewrite_naming_a_competitor_is_blocked_in_a_blocked_market():
    original = "HP devices protect your fleet."
    rewritten = "Unlike Lenovo, HP devices protect your fleet."
    _, faults = verify.diff_rewrite(original, rewritten, _sources(original), [])
    assert any("competitor" in f for f in faults)


def test_dropped_facts_are_reported_but_do_not_block():
    """A rewrite that removes an unsupported number is doing the right thing.
    The seller sees which figures went rather than losing them silently."""
    original = "We support 987 dealerships and 240 sites."
    rewritten = "We support your dealership network and 240 sites."
    report, faults = verify.diff_rewrite(original, rewritten, _sources(original), [])
    assert faults == []
    assert "987" in report["facts_dropped"]
    assert "240" not in report["facts_dropped"]


def test_rewrite_report_records_what_was_applied():
    original = "Your fleet is due a refresh."
    rewritten = "Your fleet is due a refresh this quarter."
    selected = ["Add a concrete timeframe"]
    report, faults = verify.diff_rewrite(original, rewritten, _sources(original), selected)
    assert faults == []
    assert report["applied_recommendations"] == selected
    assert report["length_after"] > report["length_before"]


def test_unrestricted_market_allows_a_superlative():
    """The restriction is Indonesia's, not a global style rule - so it has to
    lift where it does not apply, or it is just a preference in disguise."""
    original = "HP devices protect your fleet."
    rewritten = "The world's most secure PC protects your fleet."
    src = _sources(original, country="united states")
    assert src.superlatives_blocked is False
    _, faults = verify.diff_rewrite(original, rewritten, src, [])
    assert not any("superlative" in f for f in faults)
