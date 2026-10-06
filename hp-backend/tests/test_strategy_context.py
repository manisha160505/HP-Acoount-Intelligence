"""The payload Strategy Chat answers from - what is in it, and what is not.

This replaced retrieval. There is no index, no graph and no vector search behind
the chat any more: every published widget of the eight contributing features is
assembled into one string and sent whole. That moves three guarantees out of the
retrieval layer and into this module, so they are pinned here.

**Isolation.** With retrieval it was a `workspace` pre-filter on the vector
search. Here it is the `account_id` scope on a single Mongo read - simpler, and
easier to get wrong silently, because a payload that leaked another account's
widgets would still read as a fluent, confident answer.

**Completeness.** Eleven widgets once never entered the corpus at all, so the
chat could not answer from the urgency score, the size bands or the web stack,
and nothing failed - the questions simply came back unanswerable. The check is
against the widget registry rather than a hand-written list, so a widget added
to a feature in future cannot go missing the same quiet way.

**Nothing that is not evidence.** A widget still pending publishes a status, not
data; sending it would read to the model as a fact about the account. Content
Studio and Message Evaluator hold the platform's own output and a seller's own
draft, and are excluded by instruction.

Run: python -m pytest tests/test_strategy_context.py -v
"""

import os
import sys
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.widgets import WIDGET_REGISTRY
from app.services.strategy import chat, context

ACCOUNT = "acct_under_test"
OTHER = "a_different_account"


class _Widgets:
    """`account_widgets`, filtered the way pymongo filters."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find_one(self, query):
        self.queries.append(query)
        return next((r for r in self.rows
                     if all(r.get(k) == v for k, v in query.items())), None)


class _NoEngineState:
    """`node_state` with nothing in it: an account the engine has not
    migrated, so `widget_store` reads the published rows."""

    def find_one(self, *_args, **_kw):
        return None


class _Db:
    def __init__(self, rows):
        self.widgets = _Widgets(rows)

    def __getitem__(self, name):
        if name == "node_state":
            return _NoEngineState()
        assert name == "account_widgets", "unexpected collection read: %s" % name
        return self.widgets


class _Graph:
    """The regeneration graph, cut down to what `context` asks of it: which
    widgets exist, and which feature owns each. Built from the test's rows so
    each test names its own widgets."""

    def __init__(self, rows):
        self.owner = {r["widget_key"]: r["feature_key"] for r in rows}

    def __getitem__(self, node_id):
        return NS(feature=node_id)


def _row(widget_key, feature_key, data, *, account_id=ACCOUNT,
         status="available"):
    return {"account_id": account_id, "widget_key": widget_key,
            "feature_key": feature_key, "status": status, "data": data}


@pytest.fixture
def db(monkeypatch):
    """Installs a database whose rows each test sets, and a graph owning
    exactly those widgets (or the real graph, when asked for)."""
    holder = {}

    def install(rows, graph=None):
        holder["db"] = _Db(rows)
        monkeypatch.setattr(context, "DEFAULT", graph or _Graph(rows))
        return holder["db"]

    monkeypatch.setattr(context, "get_db", lambda: holder["db"])
    return install


# --- isolation -----------------------------------------------------------

def test_another_accounts_widgets_cannot_reach_the_payload(db):
    db([
        _row("exec_summary_card", "executive_dashboard",
             {"company_name": "The account under test"}),
        _row("exec_summary_card", "executive_dashboard",
             {"company_name": "SOMEONE ELSE ENTIRELY"}, account_id=OTHER),
        _row("news_signals_feed", "recent_signals",
             {"signals": [{"headline": "ANOTHER ACCOUNTS NEWS"}]},
             account_id=OTHER),
    ])

    payload, sections = context.build(ACCOUNT)

    assert "The account under test" in payload
    assert "SOMEONE ELSE ENTIRELY" not in payload
    assert "ANOTHER ACCOUNTS NEWS" not in payload
    assert [s["widget_key"] for s in sections] == ["exec_summary_card"]


def test_every_read_is_scoped_by_account_id(db):
    installed = db([_row("exec_summary_card", "executive_dashboard", {"a": 1})])
    context.build(ACCOUNT)
    assert installed.widgets.queries, "no read was made"
    for query in installed.widgets.queries:
        assert query.get("account_id") == ACCOUNT, (
            "an unscoped read would return every account's widgets: %s" % query)


# --- completeness --------------------------------------------------------

def _contributing_features():
    """Every feature the regeneration graph publishes widgets for, less the
    explicit exclusions - the graph is what decides which widgets exist."""
    from app.services.regen.graph import DEFAULT
    return {DEFAULT[n].feature for n in DEFAULT.owner.values()} - set(
        context.EXCLUDED_FEATURES)


def test_every_contributing_feature_reaches_the_chat(db):
    """Nothing filters by feature except the explicit exclusion list.

    Against the real graph: a widget the graph owns for a contributing
    feature must reach the chat without anyone adding it to a list.
    """
    from app.services.regen.graph import DEFAULT

    rows, expected = [], []
    for widget_key, node_id in DEFAULT.owner.items():
        feature = DEFAULT[node_id].feature
        if feature in context.EXCLUDED_FEATURES:
            continue
        rows.append(_row(widget_key, feature, {"marker": widget_key}))
        expected.append(widget_key)
    db(rows, graph=DEFAULT)

    payload, sections = context.build(ACCOUNT)

    reached = {s["widget_key"] for s in sections}
    missing = sorted(set(expected) - reached)
    assert not missing, "widgets not reaching Strategy Chat: %s" % missing
    assert {s["feature_key"] for s in sections} == _contributing_features()
    for row in rows:
        assert context.SECTION % (row["widget_key"], row["feature_key"]) in payload


def _widget_keys(feature: str) -> list:
    """The widget keys a feature publishes, per the widget registry."""
    return [spec["widget_key"] for spec in WIDGET_REGISTRY.get(feature, [])
            if spec.get("widget_key")]


def _feature_of(widget_key):
    for feature in WIDGET_REGISTRY:
        if widget_key in _widget_keys(feature):
            return feature
    return ""


def test_priority_order_names_only_real_widgets():
    """A typo here would silently sort that key to the back of the payload."""
    known = {k for f in WIDGET_REGISTRY for k in _widget_keys(f)}
    unknown = [k for k in context.PRIORITY_ORDER if k not in known]
    assert not unknown, "PRIORITY_ORDER names widgets that do not exist: %s" % unknown


def test_every_section_has_a_readable_label():
    """A citation must name something a seller recognises, not a database key."""
    missing = [k for k in context.PRIORITY_ORDER if k not in chat.SECTION_LABELS]
    assert not missing, "sections with no human label: %s" % missing


# --- what is excluded ----------------------------------------------------

@pytest.mark.parametrize("feature", sorted(context.EXCLUDED_FEATURES))
def test_excluded_features_stay_out(db, feature):
    db([
        _row("exec_summary_card", "executive_dashboard", {"company_name": "kept"}),
        _row("some_widget", feature, {"secret": "THIS SHOULD NOT BE SENT"}),
    ])

    payload, sections = context.build(ACCOUNT)

    assert "THIS SHOULD NOT BE SENT" not in payload
    assert [s["widget_key"] for s in sections] == ["exec_summary_card"]


@pytest.mark.parametrize("status", ["pending", "empty", "error", "", None])
def test_a_widget_that_has_not_published_is_not_evidence(db, status):
    db([
        _row("exec_summary_card", "executive_dashboard", {"company_name": "kept"}),
        _row("exec_key_metrics", "executive_dashboard",
             {"note": "GENERATION PENDING"}, status=status),
    ])

    payload, sections = context.build(ACCOUNT)

    assert "GENERATION PENDING" not in payload
    assert [s["widget_key"] for s in sections] == ["exec_summary_card"]


def test_an_available_widget_with_no_data_is_skipped(db):
    db([
        _row("exec_summary_card", "executive_dashboard", {"company_name": "kept"}),
        _row("exec_key_metrics", "executive_dashboard", {}),
        _row("exec_urgency_score", "executive_dashboard", None),
    ])
    _, sections = context.build(ACCOUNT)
    assert [s["widget_key"] for s in sections] == ["exec_summary_card"]


def test_an_account_with_nothing_published_yields_nothing(db):
    db([])
    assert context.build(ACCOUNT) == ("", [])


# --- shape ---------------------------------------------------------------

def test_sections_are_ordered_identity_first_bulk_reference_last(db):
    db([
        _row("tech_detections_reference", "tech_landscape", {"d": [1]}),
        _row("intent_topics_table", "intent_demand", {"t": [1]}),
        _row("exec_summary_card", "executive_dashboard", {"company_name": "x"}),
        _row("stakeholder_contacts_grid", "stakeholder_map", {"c": [1]}),
    ])

    _, sections = context.build(ACCOUNT)

    assert [s["widget_key"] for s in sections] == [
        "exec_summary_card", "stakeholder_contacts_grid",
        "intent_topics_table", "tech_detections_reference"]


def test_an_unlisted_widget_still_reaches_the_chat_but_after_the_listed_ones(db):
    """Priority, not membership - a new widget must not need a code change."""
    db([
        _row("a_brand_new_widget", "executive_dashboard", {"new": True}),
        _row("exec_summary_card", "executive_dashboard", {"company_name": "x"}),
    ])

    payload, sections = context.build(ACCOUNT)

    assert [s["widget_key"] for s in sections] == [
        "exec_summary_card", "a_brand_new_widget"]
    assert "a_brand_new_widget" in payload


def test_each_section_is_introduced_by_the_header_a_citation_names(db):
    db([_row("exec_urgency_score", "executive_dashboard", {"score": 72})])

    payload, sections = context.build(ACCOUNT)

    header = context.SECTION % ("exec_urgency_score", "executive_dashboard")
    assert payload.startswith(header + "\n")
    assert sections == [{"widget_key": "exec_urgency_score",
                         "feature_key": "executive_dashboard"}]


def test_json_is_compact_because_whitespace_is_context(db):
    db([_row("exec_key_metrics", "executive_dashboard",
             {"revenue": "1.2B", "employees": 4200})])
    payload, _ = context.build(ACCOUNT)
    assert '"revenue":"1.2B"' in payload
    assert '"revenue": "1.2B"' not in payload


def test_values_json_cannot_serialise_do_not_break_the_payload(db):
    """Widgets carry datetimes; `default=str` is what keeps them sendable."""
    from datetime import UTC, datetime
    db([_row("exec_summary_card", "executive_dashboard",
             {"updated_at": datetime(2026, 1, 2, tzinfo=UTC)})])
    payload, _ = context.build(ACCOUNT)
    assert "2026-01-02" in payload


def test_an_oversized_payload_is_reported_not_silently_truncated(db, caplog):
    """Trimming the tail would hide a runaway widget and drop real evidence."""
    big = "x" * (context.MAX_PAYLOAD_CHARS + 1000)
    db([
        _row("exec_summary_card", "executive_dashboard", {"company_name": "kept"}),
        _row("tech_detections_reference", "tech_landscape", {"blob": big}),
    ])

    with caplog.at_level("ERROR"):
        payload, sections = context.build(ACCOUNT)

    assert len(payload) > context.MAX_PAYLOAD_CHARS, "the payload was truncated"
    assert "kept" in payload
    assert len(sections) == 2
    assert any("over the" in r.message for r in caplog.records), (
        "a runaway widget was not reported")


# --- what `describe` reports --------------------------------------------

def test_describe_reports_what_was_actually_assembled(db):
    db([
        _row("exec_summary_card", "executive_dashboard", {"company_name": "x"}),
        _row("intent_topics_table", "intent_demand", {"t": [1]}),
        _row("ignored", "content_studio", {"assets": [1]}),
    ])

    described = context.describe(ACCOUNT)

    assert described["widgets"] == 2
    assert described["features"] == ["executive_dashboard", "intent_demand"]
    assert described["widget_keys"] == ["exec_summary_card", "intent_topics_table"]
    assert described["chars"] == len(context.build(ACCOUNT)[0])
    low, high = described["approx_tokens"]
    assert low < high, "the token estimate must stay a range, not a figure"


# --- the citations the UI renders ---------------------------------------

def test_a_citation_carries_the_section_key_the_frontend_matches_on():
    sections = [{"widget_key": "exec_urgency_score",
                 "feature_key": "executive_dashboard"}]
    cited = chat._citation("exec_urgency_score", sections)
    assert cited["evidence_id"] == "exec_urgency_score"
    assert cited["source_text"] == "Urgency score and its drivers"
    # What the UI prints in bold: the screen, not the database key.
    assert cited["dataset"] == "Executive Dashboard"
    assert cited["feature_key"] == "executive_dashboard"


def test_a_section_with_no_label_still_reads_as_words():
    cited = chat._citation("a_brand_new_widget",
                           [{"widget_key": "a_brand_new_widget",
                             "feature_key": "executive_dashboard"}])
    assert cited["source_text"] == "a brand new widget"
    assert cited["dataset"] == "Executive Dashboard"


def test_a_citation_for_an_unknown_section_does_not_raise():
    """Validation rejects these first; this is the belt to that's braces."""
    cited = chat._citation("not_in_the_payload", [])
    assert cited["evidence_id"] == "not_in_the_payload"
    assert cited["dataset"] == "Account intelligence"


def test_every_contributing_feature_has_a_display_name():
    """A citation whose label fell back to a key would read as a database row."""
    from app.api.v1.feature_mapping import FEATURE_MAPPINGS
    missing = sorted(f for f in _contributing_features()
                     if not (FEATURE_MAPPINGS.get(f) or {}).get("display_name"))
    assert not missing, "features with no display name: %s" % missing


# --------------------------------------------------------------------------
# Compaction: less noise, the same facts and figures (6 Oct)
# --------------------------------------------------------------------------

import json
import re as _re

from app.services.strategy.context import _dedupe_triggers, compact


def _figures(obj) -> set:
    return set(_re.findall(r"\d+(?:\.\d+)?", json.dumps(obj, default=str)))


TOPICS = {"provider": "Bombora", "topics": [
    {"topic_name": "printing: print quality", "composite_score": 100, "source": "Source A",
     "intensity": "High", "included": True, "exclusion_reason": None, "hiring_linked": False,
     "theme": "Print", "hp_category": "Print", "matched_terms": ["printing"],
     "mapping_status": "mapped", "flag_reason": None},
    {"topic_name": "hr: icims", "composite_score": 61, "source": "Source A",
     "intensity": "Medium", "included": False, "exclusion_reason": "duplicate",
     "hiring_linked": True, "theme": "Other / Low Relevance", "hp_category": None,
     "matched_terms": [], "mapping_status": "unmapped", "flag_reason": None},
]}


def test_topics_table_keeps_every_topic_score_and_exception():
    out = compact("intent_topics_table", TOPICS)
    rows = [dict(zip(out["topics_columns"], r)) for r in out["topics_rows"]]
    assert [r["topic_name"] for r in rows] == ["printing: print quality", "hr: icims"]
    assert [r["composite_score"] for r in rows] == [100, 61]
    # Only the unusual values are spelled out.
    assert rows[1]["included"] is False and rows[1]["exclusion_reason"] == "duplicate"
    assert rows[1]["hiring_linked"] is True
    assert "source" not in out["topics_columns"] and "mapping_status" not in out["topics_columns"]
    assert _figures(TOPICS) <= _figures(out)


def test_intent_summary_drops_only_what_the_topics_table_repeats():
    summary = {"themes": [{"theme": "Print", "topic_count": 1, "average": 100,
                           "topics": ["printing: print quality"]}],
               "bu_summary": {"lead_source": "Bombora", "units": [{"category": "Print", "score": 100}],
                              "long_tail": [{"topic": "hr: icims", "score": 61}]}}
    out = compact("intent_category_summary", summary)
    assert "topics" not in out["themes"][0] and out["themes"][0]["average"] == 100
    assert "long_tail" not in out["bu_summary"] and out["bu_summary"]["long_tail_count"] == 1
    assert out["bu_summary"]["units"] == [{"category": "Print", "score": 100}]


def test_empty_values_go_but_false_and_zero_stay():
    out = compact("x", {"a": None, "b": "", "c": [], "d": {}, "e": False, "f": 0, "g": {"h": None}})
    assert out == {"e": False, "f": 0}


def test_signal_rows_drop_only_exact_repeats():
    row = {"headline": "H", "raw_headline": "H", "source_url": "u",
           "supporting_sources": [{"url": "u", "dataset": "google_news"}], "sales_angle": "S"}
    out = compact("news_signals_feed", {"signals": [row, {**row, "raw_headline": "h2"}]})
    assert out["signals"][0] == {"headline": "H", "source_url": "u", "sales_angle": "S"}
    assert out["signals"][1]["raw_headline"] == "h2"


def test_identical_triggers_are_not_sent_twice():
    feed = [{"headline": "H", "event_date": "2026-09-01"}]
    found = [("news_signals_feed", "recent_news_signals", {"signals": feed}),
             ("opportunity_trigger_signals", "solution_narrative_opportunity_map",
              {"total_trigger_count": 1, "triggers": list(feed)})]
    out = {k: d for k, _, d in _dedupe_triggers(found)}
    assert "triggers" not in out["opportunity_trigger_signals"]
    assert out["opportunity_trigger_signals"]["total_trigger_count"] == 1


def test_different_triggers_are_kept():
    found = [("news_signals_feed", "f", {"signals": [{"headline": "A"}]}),
             ("opportunity_trigger_signals", "o", {"triggers": [{"headline": "B"}]})]
    out = {k: d for k, _, d in _dedupe_triggers(found)}
    assert out["opportunity_trigger_signals"]["triggers"] == [{"headline": "B"}]
