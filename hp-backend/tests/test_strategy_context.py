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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.widgets import WIDGET_REGISTRY
from app.services.strategy import chat, context

ACCOUNT = "acct_under_test"
OTHER = "a_different_account"


class _Widgets:
    """The one collection `context` reads, filtered the way pymongo filters."""

    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query):
        self.queries.append(query)
        return [r for r in self.rows
                if all(r.get(k) == v for k, v in query.items())]


class _Db:
    def __init__(self, rows):
        self.widgets = _Widgets(rows)

    def __getitem__(self, name):
        assert name == "account_widgets", "unexpected collection read: %s" % name
        return self.widgets


def _row(widget_key, feature_key, data, *, account_id=ACCOUNT,
         status="available"):
    return {"account_id": account_id, "widget_key": widget_key,
            "feature_key": feature_key, "status": status, "data": data}


@pytest.fixture
def db(monkeypatch):
    """Installs a database whose rows each test sets."""
    holder = {}

    def install(rows):
        holder["db"] = _Db(rows)
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
    excluded = context.EXCLUDED_FEATURES
    return {f for f in WIDGET_REGISTRY if f not in excluded}


def test_every_contributing_feature_reaches_the_chat(db):
    """Nothing filters by feature except the explicit exclusion list."""
    rows, expected = [], []
    for feature in sorted(_contributing_features()):
        for widget_key in _widget_keys(feature):
            rows.append(_row(widget_key, feature, {"marker": widget_key}))
            expected.append(widget_key)
    db(rows)

    payload, sections = context.build(ACCOUNT)

    reached = {s["widget_key"] for s in sections}
    missing = sorted(set(expected) - reached)
    assert not missing, "widgets not reaching Strategy Chat: %s" % missing
    assert {s["feature_key"] for s in sections} == _contributing_features()
    for widget_key in expected:
        assert context.SECTION % (widget_key, _feature_of(widget_key)) in payload


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
