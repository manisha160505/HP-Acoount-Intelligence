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

# The three membership guarantees that used to live here - every contributing
# feature reaches the chat, every one of its widgets does, and the excluded
# features stay out - moved with the thing they guard. Strategy Chat has no
# index and no corpus list any more; what it sends is assembled live in
# services/strategy/context.py, so the checks now run against that module in
# tests/test_strategy_context.py. They were not dropped.


def test_an_index_does_not_feed_itself():
    """A generated widget in its own corpus changes it on every build."""
    for index in registry.INDEX_KEYS:
        own = (registry.generates(index) or {}).get("widget_key")
        if own:
            assert own not in set(registry.spec(index).get("widgets") or []), (
                "%s reads the widget it generates (%s) - every build would "
                "change the corpus and trigger the next one" % (index, own))


# --- the widget -> index mapping -------------------------------------------
#
# This mapping is what turns a republished widget into a queued rebuild. It
# still matters for the two indexes that remain; it stopped mattering for
# Strategy Chat, which reads every widget live on each question and therefore
# has nothing to keep warm.


def _an_index_reading(widget_key: str) -> str:
    """Whichever remaining index reads this widget - the registry decides."""
    found = registry.dependents(widget_key)
    assert found, "no enabled index reads %s" % widget_key
    return found[0]


def test_dependents_maps_a_widget_to_the_indexes_that_read_it():
    index = _an_index_reading("messaging_context_card")
    assert index in registry.INDEX_KEYS
    assert registry.dependents("messaging_context_card") == [index]


def test_a_widget_no_enabled_index_reads_queues_nothing():
    """Content Studio's output, and - since the rewrite - Strategy Chat's."""
    assert registry.dependents("content_generated_assets") == []
    assert registry.dependents("") == []
    assert registry.dependents(None) == []


def test_the_retired_strategy_index_queues_nothing(monkeypatch):
    """Removing the index must not leave a widget queueing a build that is gone.

    `exec_urgency_score` was read only by Strategy Chat. Now that the chat reads
    it live, republishing it should queue nothing at all - not a rebuild of an
    index that no longer exists.
    """
    assert not hasattr(registry, "STRATEGY")
    assert "strategy" not in registry.INDEX_KEYS
    assert registry.dependents("exec_urgency_score") == []


def test_dependents_skips_disabled_indexes():
    widget = "messaging_context_card"
    index = _an_index_reading(widget)
    entry = registry.INDEX_REGISTRY[index]
    was = entry["enabled"]
    entry["enabled"] = False
    try:
        assert registry.dependents(widget) == []
        assert registry.dependents(widget, enabled_only=False) == [index]
    finally:
        entry["enabled"] = was


def test_dependents_of_dedupes_and_keeps_registry_order():
    several = registry.dependents_of(
        ["messaging_context_card", "technographic_map", "not_a_widget"])
    assert several == sorted(set(several), key=several.index)
    assert several, "no index reads any of these widgets"
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

    # Two widgets that at least one remaining index reads, so there is
    # something to dedupe. Picked from the registry rather than named, so this
    # test does not need editing the next time an index is added or retired.
    widgets = [k for index in registry.INDEX_KEYS
               for k in (registry.spec(index).get("widgets") or [])][:2]
    queued = ingest.requeue_dependents("acct", widgets)
    assert calls == queued
    assert len(calls) == len(set(calls)), "an index was queued twice"
    assert queued, "no index was queued for %s" % widgets


def test_requeue_dependents_skips_the_index_that_republished(monkeypatch):
    """A generated widget must not queue the index that generated it."""
    from app.services.retrieval import ingest

    monkeypatch.setattr(ingest, "request_update",
                        lambda _account_id, index, **_kw: {"i": index})
    widget = next(k for index in registry.INDEX_KEYS
                  for k in (registry.spec(index).get("widgets") or [])
                  if registry.dependents(k))
    reader = registry.dependents(widget)[0]
    assert reader in ingest.requeue_dependents("acct", widget)
    assert reader not in ingest.requeue_dependents("acct", widget, skip=reader)


def test_requeue_dependents_never_raises(monkeypatch):
    """A queueing failure must not fail the regeneration that triggered it."""
    from app.services.retrieval import ingest

    def boom(*a, **k):
        raise RuntimeError("queue is down")

    monkeypatch.setattr(ingest, "request_update", boom)
    assert ingest.requeue_dependents("acct", "messaging_context_card") == []


def test_requeue_dependents_ignores_empty_input():
    from app.services.retrieval import ingest

    assert ingest.requeue_dependents("acct", []) == []
    assert ingest.requeue_dependents("acct", None) == []
    assert ingest.requeue_dependents("acct", "") == []


@pytest.mark.parametrize("index", registry.INDEX_KEYS)
def test_every_listed_widget_resolves_back_to_its_index(index):
    """A corpus list and the widget -> index mapping cannot drift apart."""
    for widget_key in (registry.spec(index).get("widgets") or []):
        assert index in registry.dependents(widget_key), (
            "%s lists %s but dependents() does not map it back"
            % (index, widget_key))



# ---------------------------------------------------------------------------
# Citations, now that they name a payload section
#
# The evidence-id scheme (`doc#cN`) went with the retrieval layer. What has not
# changed is what a citation is FOR: a factual sentence must point at the thing
# it came from, and a pointer at something absent must be caught rather than
# quietly dropped.
#
# These pin the properties that took a day to get right under the old scheme
# and would be as easy to lose under this one. The model varies its separator
# between runs - ", " one time, "; " the next, sometimes " and " - and every
# pattern that anticipated a particular separator rendered the others raw in
# the seller's face.
# ---------------------------------------------------------------------------

def test_a_single_section_is_cited():
    from app.services.strategy.chat import _section_refs

    assert _section_refs("Revenue fell [exec_key_metrics].") == ["exec_key_metrics"]


def test_several_sections_in_one_bracket_whatever_the_separator():
    from app.services.strategy.chat import _section_refs

    for text in ("[exec_key_metrics, news_signals_feed]",
                 "[exec_key_metrics; news_signals_feed]",
                 "[ exec_key_metrics ; news_signals_feed ]",
                 "[exec_key_metrics and news_signals_feed]"):
        assert _section_refs(text) == ["exec_key_metrics", "news_signals_feed"], text


def test_adjacent_brackets_are_both_read():
    from app.services.strategy.chat import _section_refs

    assert _section_refs("A [exec_key_metrics][news_signals_feed].") == [
        "exec_key_metrics", "news_signals_feed"]


def test_a_section_cited_twice_is_listed_once():
    from app.services.strategy.chat import _section_refs

    assert _section_refs("[a_section] and again [a_section]") == ["a_section"]


def test_ordinary_bracketed_prose_is_not_a_citation():
    """Otherwise an aside becomes a citation that cannot resolve."""
    from app.services.strategy.chat import _section_refs

    for text in ("[see below]", "[1]", "[TBD]", "a sentence with no brackets"):
        assert _section_refs(text) == [], text


def test_an_unknown_section_is_rejected_not_dropped():
    """The whole point of the check.

    Silently dropping an unresolvable citation would publish a factual sentence
    whose source does not exist - the failure this feature exists to prevent.
    """
    from app.services.strategy.chat import _validate

    ok, reason, _, _ = _validate(
        "FACTS:\n1. Something true [made_up_section].",
        "===== exec_key_metrics (feature: executive_dashboard) =====\n{}",
        ["exec_key_metrics"])
    assert ok is False
    assert "made_up_section" in reason


def test_a_figure_absent_from_the_payload_is_rejected():
    """Grounding survives the move off retrieval, unchanged in spirit."""
    from app.services.strategy.chat import _validate

    payload = ('===== exec_key_metrics (feature: executive_dashboard) =====\n'
               '{"revenue":"323392"}')
    ok, reason, _, _ = _validate(
        "FACTS:\n1. Revenue grew 4271 percent [exec_key_metrics].",
        payload, ["exec_key_metrics"])
    assert ok is False
    assert "4271" in reason


def test_a_figure_present_in_the_payload_passes_despite_formatting():
    """"IDR 323,392 billion" must match a payload holding 323392."""
    from app.services.strategy.chat import _validate

    payload = ('===== exec_key_metrics (feature: executive_dashboard) =====\n'
               '{"value_text":"IDR 323,392 billion","period":"FY2025"}')
    ok, reason, cited, _ = _validate(
        "FACTS:\n1. Net revenue for FY2025 was IDR 323,392 billion "
        "[exec_key_metrics].", payload, ["exec_key_metrics"])
    assert ok is True, reason
    assert cited == ["exec_key_metrics"]


def test_facts_without_any_citation_are_rejected():
    from app.services.strategy.chat import _validate

    ok, reason, _, _ = _validate(
        "FACTS:\n1. The COO is Irvan Nr.",
        "===== stakeholder_contacts_grid (feature: stakeholder_map) =====\n{}",
        ["stakeholder_contacts_grid"])
    assert ok is False
    assert "without citing" in reason


def test_an_uncited_claim_is_rejected_even_without_a_facts_header():
    """The hole the live verification found.

    The gate used to apply only when the model had written the word "fact" in
    its opening lines - so an answer that began straight into prose asserted the
    account's people and figures with the citation requirement switched off. A
    model must not be able to disable a gate by omitting a header.
    """
    from app.services.strategy.chat import _validate

    ok, reason, _, _ = _validate(
        "PT Example's Chief Operating Officer is Someone Invented, and they "
        "own the endpoint refresh.",
        "===== stakeholder_contacts_grid (feature: stakeholder_map) =====\n{}",
        ["stakeholder_contacts_grid"])
    assert ok is False
    assert "without citing" in reason


def test_a_refusal_needs_no_citation():
    """The one answer that legitimately grounds nothing: it claims nothing."""
    from app.services.strategy.chat import _validate

    ok, reason, cited, _ = _validate(
        "The platform does not hold a personal mobile number for the CEO.",
        "===== stakeholder_contacts_grid (feature: stakeholder_map) =====\n{}",
        ["stakeholder_contacts_grid"])
    assert ok is True, reason
    assert cited == []


def test_a_cited_claim_without_a_facts_header_still_passes():
    """Widening the gate must not reject a correctly grounded answer."""
    from app.services.strategy.chat import _validate

    ok, reason, cited, _ = _validate(
        "Irvan Nr is Chief Operating Officer [stakeholder_contacts_grid].",
        '===== stakeholder_contacts_grid (feature: stakeholder_map) =====\n'
        '{"name":"Irvan Nr","title":"Chief Operating Officer"}',
        ["stakeholder_contacts_grid"])
    assert ok is True, reason
    assert cited == ["stakeholder_contacts_grid"]
