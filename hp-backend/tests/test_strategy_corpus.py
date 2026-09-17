"""What feeds Strategy Chat, and what happens when one widget changes.

Two guarantees are pinned here, both of which were broken in ways nothing
caught:

**Every contributing feature reaches the chat.** Eleven widgets never entered
the corpus at all, so the chat could not answer from the urgency score, the
size bands or the web stack, and nothing failed - the questions simply came
back unanswerable. A widget added to a feature in future must not be able to
go missing the same quiet way, so the registry list is checked against the
widget registry rather than against a hand-written list.

**One widget changing updates only its own documents.** This is the property
that makes a republish cheap. It already held, but nothing asserted it, and a
builder change that folded a whole widget into every document's fingerprint
would silently turn every republish into a full re-embed of all 65 documents.

Run: python -m pytest tests/test_strategy_corpus.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.widgets import WIDGET_REGISTRY
from app.services.retrieval import registry

# Excluded by instruction: these publish a user's own draft message and the
# assets the platform generated, not intelligence about the account.
NOT_IN_CHAT = {"message_evaluator", "content_studio"}

# Excluded for a structural reason rather than an editorial one: Strategy Chat's
# own widgets describe the chat itself - what it is grounded in, and whether it
# can answer yet. Feeding them back in would make the corpus change on every
# build and trigger the next one, the same loop `test_the_index_does_not_feed_
# itself` guards for generated widgets.
SELF = {"strategy_chat"}


def strategy_widgets():
    return set(registry.spec(registry.STRATEGY).get("widgets") or [])


# --- every feature reaches the chat ---------------------------------------


def test_every_contributing_feature_has_at_least_one_widget_in_the_chat():
    wanted = strategy_widgets()
    missing = sorted(feature for feature, contracts in WIDGET_REGISTRY.items()
                     if feature not in NOT_IN_CHAT | SELF
                     and not any(c["widget_key"] in wanted for c in contracts))
    assert not missing, "features feeding nothing into Strategy Chat: %s" % missing


def test_every_widget_of_every_contributing_feature_is_listed():
    """Not just one widget per feature - all of them.

    This is the check that would have caught the eleven. A feature can be
    represented by its headline widget while its other outputs never reach the
    chat, which is exactly the state this test was written to end.
    """
    wanted = strategy_widgets()
    missing = sorted(c["widget_key"] for feature, contracts in WIDGET_REGISTRY.items()
                     if feature not in NOT_IN_CHAT | SELF
                     for c in contracts if c["widget_key"] not in wanted)
    assert not missing, "widgets not feeding Strategy Chat: %s" % missing


def test_excluded_features_stay_excluded():
    wanted = strategy_widgets()
    leaked = sorted(c["widget_key"] for feature in NOT_IN_CHAT | SELF
                    for c in WIDGET_REGISTRY.get(feature, [])
                    if c["widget_key"] in wanted)
    assert not leaked, "excluded features reached the chat: %s" % leaked


def test_the_index_does_not_feed_itself():
    """A generated widget in its own corpus changes it on every build."""
    for index in registry.INDEX_KEYS:
        own = (registry.generates(index) or {}).get("widget_key")
        if own:
            assert own not in set(registry.spec(index).get("widgets") or []), (
                "%s reads the widget it generates (%s) - every build would "
                "change the corpus and trigger the next one" % (index, own))


# --- the widget -> index mapping -------------------------------------------


def test_dependents_maps_a_widget_to_the_indexes_that_read_it():
    assert registry.dependents("exec_urgency_score") == [registry.STRATEGY]
    assert registry.STRATEGY in registry.dependents("exec_strategic_priorities")


def test_dependents_of_an_unread_widget_is_empty():
    """Content Studio's output must not queue anything."""
    assert registry.dependents("content_generated_assets") == []
    assert registry.dependents("") == []
    assert registry.dependents(None) == []


def test_dependents_skips_disabled_indexes():
    entry = registry.INDEX_REGISTRY[registry.STRATEGY]
    was = entry["enabled"]
    entry["enabled"] = False
    try:
        assert registry.dependents("exec_urgency_score") == []
        assert registry.dependents("exec_urgency_score", enabled_only=False) == [
            registry.STRATEGY]
    finally:
        entry["enabled"] = was


def test_dependents_of_dedupes_and_keeps_registry_order():
    several = registry.dependents_of(
        ["exec_key_metrics", "exec_urgency_score", "not_a_widget"])
    assert several == sorted(set(several), key=several.index)
    assert registry.STRATEGY in several
    assert registry.dependents_of([]) == []


# --- one widget changing updates only its own documents --------------------


class _FakeDocument:
    """Just enough of `corpus.Document` for `fingerprints()` and `diff()`."""

    def __init__(self, doc_id, unit_key, fingerprint):
        self.doc_id = doc_id
        self.unit_key = unit_key
        self.fingerprint = fingerprint


def test_diff_reports_only_the_documents_whose_fingerprint_moved(monkeypatch):
    """The property the whole design rests on.

    `update_index` sets `targets = added + changed`, so a document that keeps
    its fingerprint is never re-embedded and never re-extracted. If a builder
    ever folded a whole widget into every document's fingerprint, every
    republish would re-embed everything and only the cost would show it.
    """
    from app.services.retrieval import index_state

    before = {"doc_a": {"fingerprint": "aaa", "unit_key": "a"},
              "doc_b": {"fingerprint": "bbb", "unit_key": "b"},
              "doc_c": {"fingerprint": "ccc", "unit_key": "c"}}
    monkeypatch.setattr(index_state, "get",
                        lambda _account_id, _index: {"documents": before})

    # doc_b changed, doc_d is new, doc_c is gone. doc_a must not move.
    now = {"doc_a": {"fingerprint": "aaa", "unit_key": "a"},
           "doc_b": {"fingerprint": "CHANGED", "unit_key": "b"},
           "doc_d": {"fingerprint": "ddd", "unit_key": "d"}}

    delta = index_state.diff("acct", "strategy", now)
    assert delta["changed"] == ["doc_b"]
    assert delta["added"] == ["doc_d"]
    assert delta["removed"] == ["doc_c"]
    assert delta["unchanged"] == ["doc_a"]


def test_fingerprint_covers_the_rendered_text_not_only_the_source():
    """A builder change must count as a change.

    Narrative documents were once switched from paragraph-level to
    sentence-level evidence - the indexed text changed completely - and because
    the underlying data had not changed, every document compared equal and the
    improvement never reached the index.
    """
    from app.services.retrieval import corpus

    same_source = {"unchanged": True}
    one = corpus.Document("d1", "u1", "strategy", "Title", ["line one"], [], same_source)
    two = corpus.Document("d1", "u1", "strategy", "Title", ["line TWO"], [], same_source)
    assert one.fingerprint != two.fingerprint


def test_fingerprints_are_stable_for_identical_input():
    from app.services.retrieval import corpus

    args = ("d1", "u1", "strategy", "Title", ["a", "b"], [], {"k": "v"})
    assert corpus.Document(*args).fingerprint == corpus.Document(*args).fingerprint


def test_fingerprints_keyed_by_doc_id():
    from app.services.retrieval import corpus

    docs = [_FakeDocument("d1", "u1", "f1"), _FakeDocument("d2", "u2", "f2")]
    out = corpus.fingerprints(docs)
    assert set(out) == {"d1", "d2"}
    assert out["d1"]["fingerprint"] == "f1"
    assert out["d1"]["unit_key"] == "u1"


# --- the trigger ------------------------------------------------------------


def test_requeue_dependents_queues_each_index_once(monkeypatch):
    from app.services.retrieval import ingest

    calls = []
    # `reason`/`full` land in **_kw: `requeue_dependents` passes account_id and
    # index positionally, so only their order matters here, not their names.
    monkeypatch.setattr(ingest, "request_update",
                        lambda _account_id, index, **_kw:
                        calls.append(index) or {"index": index})

    queued = ingest.requeue_dependents(
        "acct", ["exec_urgency_score", "exec_key_metrics"])
    assert calls == queued
    assert len(calls) == len(set(calls)), "an index was queued twice"
    assert registry.STRATEGY in queued


def test_requeue_dependents_skips_the_index_that_republished(monkeypatch):
    """A generated widget must not queue the index that generated it."""
    from app.services.retrieval import ingest

    monkeypatch.setattr(ingest, "request_update",
                        lambda _account_id, index, **_kw: {"i": index})
    queued = ingest.requeue_dependents(
        "acct", "exec_strategic_priorities", skip=registry.STRATEGY)
    assert registry.STRATEGY not in queued


def test_requeue_dependents_never_raises(monkeypatch):
    """A queueing failure must not fail the regeneration that triggered it."""
    from app.services.retrieval import ingest

    def boom(*a, **k):
        raise RuntimeError("queue is down")

    monkeypatch.setattr(ingest, "request_update", boom)
    assert ingest.requeue_dependents("acct", "exec_urgency_score") == []


def test_requeue_dependents_ignores_empty_input():
    from app.services.retrieval import ingest

    assert ingest.requeue_dependents("acct", []) == []
    assert ingest.requeue_dependents("acct", None) == []
    assert ingest.requeue_dependents("acct", "") == []


@pytest.mark.parametrize("widget_key", sorted(strategy_widgets()))
def test_every_listed_widget_resolves_to_the_strategy_index(widget_key):
    """The list and the mapping cannot drift apart."""
    assert registry.STRATEGY in registry.dependents(widget_key)


# ---------------------------------------------------------------------------
# Abbreviated citations
#
# The model writes a second citation from the same document in shorthand -
# "[doc#c2, c3]" - and every step read ids with a pattern matching a complete
# `doc#cN`, so the abbreviated half was invisible. It was never resolved, never
# validated, and never reached the seller's source list, while the answer
# quoted the sentence it stood for. The bracket also failed the UI's pattern and
# rendered raw.
# ---------------------------------------------------------------------------

def test_shorthand_second_citation_is_expanded():
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("Counter with X [a6_objection_x#c2, c3].")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_objection_x#c2", "a6_objection_x#c3"]


def test_shorthand_with_a_hash_is_expanded():
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[a6_x#c1, #c4]")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_x#c1", "a6_x#c4"]


def test_several_shorthands_all_inherit_the_last_document():
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[a6_x#c1, c2, c3]")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_x#c1", "a6_x#c2", "a6_x#c3"]


def test_full_ids_are_left_alone():
    from app.services.strategy.chat import _expand_citations

    for text in ("[a6_x#c1, a6_y#c2]", "[a6_x#c9]", "no citations here"):
        assert _expand_citations(text) == text


def test_a_shorthand_with_no_preceding_document_is_not_invented():
    """Nothing to inherit from, so it must not be guessed at."""
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[c3]")
    assert _EVIDENCE_REF_RE.findall(out) == []


def test_unrecognised_reference_survives_to_fail_loudly():
    """Dropping it would hide a bad citation from `resolve`."""
    from app.services.strategy.chat import _expand_citations

    assert "nonsense" in _expand_citations("[a6_x#c1, nonsense]")


# ---------------------------------------------------------------------------
# Markdown in a plain-text answer
#
# The prompt asks for "FACTS:" and the model mostly writes it, but about one
# run in three it reaches for "### FACTS". The UI renders the answer as plain
# text, so the seller reads the hashes - and the verification suite, which looks
# for an uppercase label ending in a colon, fails intermittently on a perfectly
# good answer. `**bold**` was already stripped for the same reason; headings
# were not.
# ---------------------------------------------------------------------------

def markdown_cleaned(text):
    """The heading rewrite exactly as `_validate` applies it."""
    import re
    return re.sub(r"^\s{0,3}#{1,6}\s*(.+?)\s*:?\s*$",
                  lambda m: "%s:" % m.group(1).rstrip(":"), text, flags=re.M)


def test_a_markdown_heading_becomes_a_labelled_section():
    """Rewritten, not stripped - a heading should stay a heading."""
    assert markdown_cleaned("### FACTS") == "FACTS:"
    assert markdown_cleaned("## RECOMMENDATION:") == "RECOMMENDATION:"


def test_the_rewritten_heading_satisfies_the_published_contract():
    """The same pattern the verification suite checks for."""
    import re
    body = markdown_cleaned("### FACTS ABOUT REVENUE\n1. Something [a6_x#c1].")
    assert re.findall(r"^[A-Z][A-Z ,'/&-]{5,}:", body, re.M) == ["FACTS ABOUT REVENUE:"]


def test_ordinary_lines_are_untouched():
    for line in ("no heading here", "1. A numbered line",
                 "C# is a language", "a sentence with # inside"):
        assert markdown_cleaned(line) == line


def test_semicolon_separated_citations_are_expanded():
    """The model varies the separator between runs; both must work.

    A comma-only split left "[x#c2; c3]" with its shorthand intact, so the
    second citation stayed invisible to resolution and to the source list - and
    the bracket rendered raw in the UI, which is how it was noticed.
    """
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[a6_x#c2; c3]")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_x#c2", "a6_x#c3"]


def test_mixed_separators_in_one_bracket():
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[a6_x#c1, c2; c3]")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_x#c1", "a6_x#c2", "a6_x#c3"]


def test_semicolon_between_two_full_ids_is_left_resolvable():
    from app.services.strategy.chat import _EVIDENCE_REF_RE, _expand_citations

    out = _expand_citations("[a6_x#c2; a6_y#c3]")
    assert _EVIDENCE_REF_RE.findall(out) == ["a6_x#c2", "a6_y#c3"]


# ---------------------------------------------------------------------------
# The uncited-facts gate
#
# `_validate` rejects an answer that asserts things about the account and cites
# nothing. Whether an answer "asserts things" used to be decided by looking for
# the literal word "fact" in its opening 400 characters - which trusted the
# model to have written a "FACTS:" header before the requirement applied to it.
#
# Demonstrated against the live account before this was changed: the sentence
# "The Chief Financial Officer is Someone Invented." - a fabricated name and a
# fabricated title, no citation - passed validation in 8ms. The figure check
# still bit, because an invented NUMBER is caught wherever it appears. An
# invented NAME, TITLE or VENDOR had nothing standing in its way, and those are
# exactly what ABX says "cannot come from model memory".
#
# A gate a model can disable by omitting a header is not a gate.
# ---------------------------------------------------------------------------

def test_an_answer_that_asserts_anything_is_treated_as_asserting_facts():
    from app.services.strategy.chat import _asserts_facts

    assert _asserts_facts("The Chief Financial Officer is Someone Invented.")
    assert _asserts_facts("Irvan Nr is Chief Operating Officer.")
    assert _asserts_facts("FACTS:\n1. Revenue fell.")
    # Advice with no account facts in it still has to say what it rests on.
    assert _asserts_facts("You should lead with security.")


def test_a_refusal_asserts_nothing_and_needs_no_citation():
    """The one answer that legitimately grounds nothing: it claims nothing."""
    from app.services.strategy.chat import _asserts_facts

    for refusal in (
        "The platform does not hold a personal mobile number for the CEO.",
        "That is not available in this account's evidence.",
        "The platform has no information about that.",
        "The account data does not include their budget.",
    ):
        assert not _asserts_facts(refusal), refusal


def test_the_gate_does_not_depend_on_the_model_writing_a_header():
    """The regression this replaced.

    Both of these assert a name and a title. The first happens to contain the
    word "fact" and the second does not, and under the old rule that alone
    decided whether the citation requirement applied.
    """
    from app.services.strategy.chat import _asserts_facts

    with_header = "FACTS:\n1. The CFO is Someone Invented."
    without_header = "The CFO is Someone Invented."
    assert _asserts_facts(with_header) == _asserts_facts(without_header) is True
