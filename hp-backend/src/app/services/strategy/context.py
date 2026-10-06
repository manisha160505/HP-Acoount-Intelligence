"""The whole account, assembled for one prompt.

Strategy Chat used to retrieve fragments of this through a graph index. It no
longer does. Measured, the finished output of the eight contributing features is
about 452,000 characters of compact JSON - roughly 113,000 tokens - which fits a
1M context window with room to spare. Retrieval existed to make the corpus fit;
it does not need to fit.

What that buys is not only simplicity. Retrieval answers a question with the
fragments that resemble it, so a multi-hop question - "who should I approach
about AI workstations" - depends on one chunk happening to join a person to a
topic to a technology. Here the model has every feature's output at once and can
make the join itself.

Two features are deliberately absent. Content Studio holds assets the platform
generated and Message Evaluator holds a seller's own draft message; neither is
intelligence about the account, and both would dilute the payload with the
platform's own output.

Isolation is the same rule the corpus builder used: every read is scoped by
`account_id`, so a payload built for one account can contain nothing belonging
to another.

Widgets are read through `regen.store` - the committed generation of each
section, exactly what the dashboard shows - never from `account_widgets`
directly, which the engine keeps only as a rollback copy.
"""

import json
import logging

from app.database.mongodb import get_db
from app.services.regen import store as widget_store
from app.services.regen.graph import DEFAULT

logger = logging.getLogger(__name__)

# The platform's own output rather than the account's.
EXCLUDED_FEATURES = frozenset({"content_studio", "message_evaluator",
                               "strategy_chat"})

# Order matters, and only at the margin - but the margin is where it counts.
# Everything listed here fits comfortably today; if a payload ever has to be
# cut, what should fall off the end is the bulk reference material, not the
# account's identity. `tech_detections_reference` is 18 KB of opaque detection
# ids with no vendor names, so it goes last by design.
#
# A widget NOT in this list is still included - appended after these - so a new
# widget reaches the chat without anyone remembering to add it here. The list
# sets priority, not membership.
PRIORITY_ORDER = (
    "exec_summary_card",
    "exec_key_metrics",
    "exec_strategic_priorities",
    "exec_urgency_score",
    "hiring_postings_summary",
    "stakeholder_contacts_grid",
    "stakeholder_influence_map",
    "stakeholder_talking_points",
    "news_signals_feed",
    "news_relevance_summary",
    "opportunity_narrative_plays",
    "opportunity_trigger_signals",
    "opportunity_context_card",
    "objection_reframe_cards",
    "objection_incumbent_context",
    "technographic_map",
    "technographic_hp_recommendations",
    "tech_stack_matrix",
    "webstack_breakdown",
    "intent_topics_table",
    "intent_category_summary",
    "hiring_family_breakdown",
    "hiring_theme_cards",
    "hiring_tech_tags",
    "tech_detections_reference",
)

# A guard, not a budget. The payload is ~452 KB today; this catches a widget
# that balloons - a runaway list, a field that starts carrying raw rows - before
# it silently eats the context window and starts truncating answers.
MAX_PAYLOAD_CHARS = 900_000

SECTION = "===== %s (feature: %s) ====="


# What the model is sent is the dashboard's data without its bookkeeping (6 Oct:
# Australia Post's payload was 1.56M chars, the answer overran its output limit
# and took 7m46s). Nothing removed here carries a fact or a figure, so the claim
# checker - which looks every figure up in this payload - is unaffected:
#   * empty values (None, "", [], {}) anywhere;
#   * per Bombora topic row, the fields that are the same on every row or only
#     record how the row was mapped;
#   * the intent summary's long tail, which lists topics the topics table
#     already carries with the same scores.
_TOPIC_ROW_DROP = frozenset({"source", "mapping_status", "matched_terms"})


def _strip_empty(value):
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            v = _strip_empty(v)
            if v is None or v in ("", [], {}):
                continue
            out[k] = v
        return out
    if isinstance(value, list):
        return [_strip_empty(v) for v in value]
    return value


def _topic_row(row: dict) -> dict:
    out = {k: v for k, v in row.items() if k not in _TOPIC_ROW_DROP}
    if out.get("included") is True:
        out.pop("included")            # every row is, unless it says otherwise
    if out.get("hiring_linked") is False:
        out.pop("hiring_linked")
    return out


def _signal_row(row: dict) -> dict:
    """A news signal without its repeats: `raw_headline` when it is the
    headline, and a single supporting source that is the row's own URL."""
    out = dict(row)
    if out.get("raw_headline") == out.get("headline"):
        out.pop("raw_headline", None)
    sources = out.get("supporting_sources")
    if (isinstance(sources, list) and len(sources) == 1 and isinstance(sources[0], dict)
            and sources[0].get("url") == out.get("source_url")):
        out.pop("supporting_sources")
    return out


# Lists of news signals, by widget: the same rows, published under two keys.
_SIGNAL_LISTS = {"news_signals_feed": "signals", "opportunity_trigger_signals": "triggers"}


def compact(widget_key: str, data: dict) -> dict:
    """The widget as the model needs it: same facts and figures, less noise."""
    field = _SIGNAL_LISTS.get(widget_key)
    if field and isinstance(data.get(field), list):
        data = {**data, field: [_signal_row(r) if isinstance(r, dict) else r
                                for r in data[field]]}
    if widget_key == "intent_topics_table" and isinstance(data.get("topics"), list):
        rows = [_strip_empty(_topic_row(r)) for r in data["topics"] if isinstance(r, dict)]
        if len(rows) == len(data["topics"]):
            # One header, then values: the same table without its key names
            # repeated on each of up to ~2,800 rows.
            columns = list(dict.fromkeys(k for r in rows for k in r))
            data = {**{k: v for k, v in data.items() if k != "topics"},
                    "topics_columns": columns,
                    "topics_rows": [[r.get(c) for c in columns] for r in rows]}
    if widget_key == "intent_category_summary":
        themes = data.get("themes")
        if isinstance(themes, list):
            # Each theme's topic names are the topics table's rows with that
            # theme; its counts and scores stay.
            data = {**data, "themes": [
                {**{k: v for k, v in t.items() if k != "topics"},
                 "topics_note": "listed in intent_topics_table under this theme"}
                if isinstance(t, dict) and t.get("topics") else t for t in themes]}
        bu = data.get("bu_summary")
        if isinstance(bu, dict) and bu.get("long_tail"):
            data = {**data, "bu_summary": {
                **{k: v for k, v in bu.items() if k != "long_tail"},
                "long_tail_count": len(bu["long_tail"]),
                "long_tail_note": "the other topics, with their scores, are in "
                                  "intent_topics_table"}}
    return _strip_empty(data)


def _sort_key(widget_key: str):
    try:
        return (0, PRIORITY_ORDER.index(widget_key))
    except ValueError:
        return (1, widget_key)


def account_widgets(account_id: str, graph=None) -> list:
    """Every published widget of the contributing features, in prompt order.

    The widgets are the ones the regeneration graph owns, so a new widget
    reaches the chat as soon as a section publishes it; user-request outputs
    (generated assets, a seller's draft) belong to no section and never do.
    """
    graph = graph or DEFAULT
    db = get_db()
    found = []
    for widget_key, node_id in graph.owner.items():
        feature = graph[node_id].feature
        if feature in EXCLUDED_FEATURES:
            continue
        widget = widget_store.committed(db, account_id, widget_key, graph) or {}
        # A widget that never generated carries no data worth sending, and its
        # "pending" notice would read to the model as a fact about the account.
        if widget.get("status") != "available":
            continue
        data = compact(widget_key, widget.get("data") or {})
        if not data:
            continue
        found.append((widget_key, feature, data))
    found.sort(key=lambda row: _sort_key(row[0]))
    return _dedupe_triggers(found)


def _dedupe_triggers(found: list) -> list:
    """Opportunity triggers are published from the same news signals as the
    feed; when the two lists are identical the second is not sent again. The
    section stays, so a citation to it still resolves."""
    by_key = {k: d for k, _, d in found}
    feed = (by_key.get("news_signals_feed") or {}).get("signals")
    out = []
    for widget_key, feature, data in found:
        if (widget_key == "opportunity_trigger_signals" and feed
                and data.get("triggers") == feed):
            data = {**{k: v for k, v in data.items() if k != "triggers"},
                    "triggers_note": "the same %d signals as news_signals_feed.signals; "
                                     "not repeated here" % len(feed)}
        out.append((widget_key, feature, data))
    return out


def build(account_id: str, graph=None) -> tuple:
    """(payload, sections). The account as one string, and what is in it.

    Each section is `{"widget_key", "feature_key"}`. The widget keys are what a
    citation may name: the model is told to tag each fact with the section it
    came from, and a tag naming a section absent from the payload is rejected
    the same way an unresolvable evidence id was. The feature key rides along so
    a citation can tell the seller which screen to click through to without a
    second read of `account_widgets`.

    Compact JSON rather than indented - 18% smaller for exactly the same
    content, which is 18% more room for the conversation.
    """
    widgets = account_widgets(account_id, graph)
    if not widgets:
        return "", []

    parts, sections = [], []
    for widget_key, feature, data in widgets:
        sections.append({"widget_key": widget_key, "feature_key": feature})
        parts.append("%s\n%s" % (
            SECTION % (widget_key, feature),
            json.dumps(data, separators=(",", ":"), default=str,
                       ensure_ascii=False)))

    payload = "\n\n".join(parts)
    if len(payload) > MAX_PAYLOAD_CHARS:
        # Loud, and not silently trimmed: a payload this size means a widget is
        # carrying something it should not, and cutting the tail would hide that
        # while quietly dropping whatever sorted last.
        logger.error(
            "strategy context: payload is %d chars, over the %d guard - a "
            "widget has grown unexpectedly. Largest: %s",
            len(payload), MAX_PAYLOAD_CHARS,
            ", ".join("%s=%d" % (k, len(json.dumps(d, default=str)))
                      for k, _, d in sorted(
                          widgets, key=lambda r: -len(json.dumps(r[2], default=str))
                      )[:3]))
    return payload, sections


def describe(account_id: str) -> dict:
    """What the payload holds, for logging and for the verification script."""
    widgets = account_widgets(account_id)
    payload, sections = build(account_id)
    return {
        "widgets": len(sections),
        "features": sorted({feature for _, feature, _ in widgets}),
        "chars": len(payload),
        # Deliberately a range. Tokenisation varies with content, and a single
        # number here would be quoted back as though it were measured.
        "approx_tokens": (len(payload) // 4, int(len(payload) / 3.5)),
        "widget_keys": [x["widget_key"] for x in sections],
    }
