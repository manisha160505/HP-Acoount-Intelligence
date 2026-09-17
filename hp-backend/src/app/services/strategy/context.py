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
"""

import json
import logging

from app.database.mongodb import get_db

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
    "exec_hiring_velocity",
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
    "intent_hiring_demand",
    "messaging_pillars_output",
    "messaging_context_card",
    "tech_detections_reference",
)

# A guard, not a budget. The payload is ~452 KB today; this catches a widget
# that balloons - a runaway list, a field that starts carrying raw rows - before
# it silently eats the context window and starts truncating answers.
MAX_PAYLOAD_CHARS = 900_000

SECTION = "===== %s (feature: %s) ====="


def _sort_key(widget_key: str):
    try:
        return (0, PRIORITY_ORDER.index(widget_key))
    except ValueError:
        return (1, widget_key)


def account_widgets(account_id: str) -> list:
    """Every published widget of the contributing features, in prompt order."""
    db = get_db()
    found = []
    for widget in db["account_widgets"].find({"account_id": account_id}):
        feature = widget.get("feature_key") or ""
        if feature in EXCLUDED_FEATURES:
            continue
        # A widget that never generated carries no data worth sending, and its
        # "pending" notice would read to the model as a fact about the account.
        if widget.get("status") != "available":
            continue
        data = widget.get("data") or {}
        if not data:
            continue
        found.append((widget.get("widget_key") or "", feature, data))
    found.sort(key=lambda row: _sort_key(row[0]))
    return found


def build(account_id: str) -> tuple:
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
    widgets = account_widgets(account_id)
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
