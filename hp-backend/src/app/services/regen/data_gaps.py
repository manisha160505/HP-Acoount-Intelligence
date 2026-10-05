"""Why a widget field shows a neutral placeholder.

The client sees only "No signal observed" or "Not disclosed" where a value is
absent (client instruction, 1 Oct): nothing on screen may suggest a file was
not uploaded, a pipeline did not run or a model failed. The real reason is kept
here instead. Every committed generation carries `data_gaps`, one row per
field, so "why does this account show No signal observed?" is answered from the
database, not guessed:

    node_state.current.data_gaps = [
        {"widget": "exec_urgency_score",
         "field": "drivers[2].terms[0]",
         "code": "INPUT_NOT_ON_FILE",
         "reason": "comparable associated-members history unavailable - ..."},
        ...]

Nothing here decides what a widget contains. It reads the markers the
extractors already publish (`missing_input`, `zero_reason`, `notice`,
`"not_available"`, ...) and turns each into a coded row, so a new extractor
only needs to keep publishing those markers. Outside the fingerprint and the
output hash: recording a reason never makes a generation stale.
"""

import logging

logger = logging.getLogger(__name__)

# Codes, so gaps can be counted and filtered across accounts.
INPUT_NOT_ON_FILE = "INPUT_NOT_ON_FILE"          # source file or rows absent
NOT_IN_SOURCE = "NOT_IN_SOURCE"                  # file present, field empty
NOT_SCORED_NO_EVIDENCE = "NOT_SCORED_NO_EVIDENCE"
UNAVAILABLE = "UNAVAILABLE"
FALLBACK_SOURCE = "FALLBACK_SOURCE"              # value taken from a secondary source
OTHER_ENTITY_FIGURE = "OTHER_ENTITY_FIGURE"
MODEL_NOT_ASSESSED = "MODEL_NOT_ASSESSED"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
MODEL_INCOMPLETE = "MODEL_INCOMPLETE"
MODEL_FALLBACK = "MODEL_FALLBACK"                # template / plain text used instead
WITHHELD = "WITHHELD"
UNVERIFIED_CONDITION = "UNVERIFIED_CONDITION"
NOISY_KEYWORD = "NOISY_KEYWORD"
DOMAIN_UNVERIFIED = "DOMAIN_UNVERIFIED"
SOURCE_INCONSISTENT = "SOURCE_INCONSISTENT"
NOTICE = "NOTICE"
WIDGET_NOT_AVAILABLE = "WIDGET_NOT_AVAILABLE"

MAX_REASON = 500


def _text(value) -> str:
    if isinstance(value, (list, tuple)):
        parts = []
        for item in value:
            if isinstance(item, dict):
                item = (item.get("reason") or item.get("message") or item.get("label")
                        or item.get("term") or item.get("name") or item)
            parts.append(str(item))
        value = "; ".join(parts)
    return " ".join(str(value if value is not None else "").split())[:MAX_REASON]


def _sibling_reason(node: dict, *keys) -> str:
    for key in (*keys, "basis", "reason", "note", "notice", "label", "name"):
        if node.get(key):
            return _text(node[key])
    return ""


def _rules(node: dict):
    """(marker key, code, reason) for every gap marker set on this dict."""
    get = node.get
    if get("missing_input") is True:
        yield "missing_input", INPUT_NOT_ON_FILE, _sibling_reason(node)
    if get("zero_reason"):
        yield "zero_reason", NOT_SCORED_NO_EVIDENCE, _text(get("zero_reason"))
    if get("unavailable_reason"):
        yield "unavailable_reason", UNAVAILABLE, _text(get("unavailable_reason"))
    if get("fallback_note"):
        yield "fallback_note", FALLBACK_SOURCE, _text(get("fallback_note"))
    elif get("from_news_fallback") is True:
        yield "from_news_fallback", FALLBACK_SOURCE, "drawn from recent events"
    if get("entity_note"):
        yield "entity_note", OTHER_ENTITY_FIGURE, _text(get("entity_note"))
    if isinstance(get("not_assessed_count"), int) and get("not_assessed_count") > 0:
        yield ("not_assessed_count", MODEL_NOT_ASSESSED,
               "%d signal(s) have no relevance judgement" % get("not_assessed_count"))
    if get("not_in_technographics") is True:
        # The Objection Playbook falls back to tech_breakdown when
        # technographics is empty; the flag keeps its name, the source differs.
        yield ("not_in_technographics", NOT_IN_SOURCE,
               "no vendor for this area in the website technology (tech_breakdown)"
               if get("evidence_source") == "tech_breakdown"
               else "no vendor for this area in the technographics export")
    if get("unverified_conditions"):
        yield "unverified_conditions", UNVERIFIED_CONDITION, _text(get("unverified_conditions"))
    if get("is_fallback") is True:
        yield "is_fallback", MODEL_FALLBACK, "safe template used, not model output"
    if get("ai_available") is False:
        yield "ai_available", MODEL_UNAVAILABLE, _sibling_reason(node, "ai_error", "error")
    for key in ("dimensions_padded", "dimension_problems", "chunk_fidelity_faults",
                "phrases_dropped"):
        if get(key):
            yield key, MODEL_INCOMPLETE, _text(get(key))
    for key in ("reaction_withheld", "withheld_summary"):
        if get(key):
            yield key, WITHHELD, _text(get(key))
    if get("quality_flags"):
        yield "quality_flags", NOISY_KEYWORD, _text(get("quality_flags"))
    if get("written_by") == "python":
        yield ("written_by", MODEL_FALLBACK,
               "generated description rejected; plain summary shown")
    if get("available") is False:
        yield "available", UNAVAILABLE, _sibling_reason(node, "unavailable_reason")
    if isinstance(get("notice"), str) and get("notice").strip():
        yield "notice", NOTICE, _text(get("notice"))

    match = get("account_match")
    if isinstance(match, dict) and match.get("status") not in (None, "matched"):
        yield ("account_match", DOMAIN_UNVERIFIED,
               "%s: %s" % (match.get("status"), _text(match.get("note"))))
    category = get("category_file")
    if isinstance(category, dict) and category.get("status") not in (None, "matched"):
        yield ("category_file", INPUT_NOT_ON_FILE,
               "%s: %s" % (category.get("status"), _text(category.get("note"))))
    check = get("top_check")
    if isinstance(check, dict) and check.get("consistent") is False:
        yield "top_check", SOURCE_INCONSISTENT, _text(check.get("note") or check)


def _walk(value, path: str, out: list, widget_key: str) -> None:
    if isinstance(value, dict):
        for key, code, reason in _rules(value):
            out.append({"widget": widget_key, "field": "%s.%s" % (path, key) if path else key,
                        "code": code, "reason": reason})
        for key, child in value.items():
            if child == "not_available":
                out.append({"widget": widget_key,
                            "field": "%s.%s" % (path, key) if path else key,
                            "code": NOT_IN_SOURCE,
                            "reason": "field not available in the source data"})
            elif isinstance(child, (dict, list)):
                _walk(child, "%s.%s" % (path, key) if path else key, out, widget_key)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            if isinstance(child, (dict, list)):
                _walk(child, "%s[%d]" % (path, i), out, widget_key)


def collect(widget_key: str, widget: dict) -> list[dict]:
    """Every gap in one widget, as coded rows."""
    out: list[dict] = []
    widget = widget or {}
    status = widget.get("status")
    if status and status != "available":
        data = widget.get("data") or {}
        reason = _text(data.get("notice") or data.get("unavailable_reason")
                       or "widget status %r" % status) if isinstance(data, dict) else ""
        out.append({"widget": widget_key, "field": "", "code": WIDGET_NOT_AVAILABLE,
                    "reason": reason or "widget status %r" % status})
    _walk(widget.get("data"), "", out, widget_key)
    return out


def collect_all(widgets: dict) -> list[dict]:
    """Gaps across a generation's widgets. Never raises: a reason that cannot
    be recorded must not cost the account its generation."""
    out: list[dict] = []
    for key, widget in (widgets or {}).items():
        try:
            out.extend(collect(key, widget))
        except Exception:
            logger.exception("data_gaps: could not collect for widget %s", key)
    return out
