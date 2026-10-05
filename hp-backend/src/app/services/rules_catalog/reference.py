"""The fixed rule sets themselves, for the Rules page's "Rule books" section.

A feature's catalog explains how it USES a rule set ("rules from HP's rulebook
are matched against the account's evidence"). This module lists the rule set's
entries, so a reader can see every rule the feature can apply.

Each set is read through the same loader the engine uses - `rulebook.load`,
`lifecycle.load`, the dictionary and technology constants - so the page lists
exactly what the features apply and follows a reload of the rulebook or the
lifecycle file without an edit here. Entries are shown as the client wrote them:
the rulebook's own text is verbatim by design (its guardrail C 03, "Use exact
facts"). Matching aids derived for the engine (signal tokens, observable terms)
and file provenance are not shown.

Every builder is an ordinary function registered by hand in REFERENCE_SETS;
nothing here is chosen or invoked from data.
"""

from __future__ import annotations

import ast
from datetime import UTC, date, datetime

from app.services.dashboard import urgency
from app.services.hp import intent_topic_map, lifecycle, rulebook

# The rulebook's families, as a reader would name them.
FAMILY_NAMES = {
    "HARDWARE": "HP hardware",
    "PRINT": "Print services",
    "CARE": "Care Packs and support",
    "WOLF": "Wolf Security",
    "DEPLOY": "Deployment and configuration",
    "WXP": "Workforce Experience Platform",
    "IQ": "HP IQ",
    "SCAN": "Scanning and capture",
    "INK": "Ink and supplies",
    "POLY": "Poly collaboration",
    "LIFE": "Device lifecycle services",
}

SCOPE_NAMES = {"common": "All recommendations"}


def _list(value) -> list:
    """Rulebook list fields, whether stored as a list or as a list's text."""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("["):
            try:
                value = ast.literal_eval(text)  # a literal only; never evaluated as code
            except (ValueError, SyntaxError):
                return [text]
        else:
            return [text] if text else []
    out = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("text") or ""
        item = str(item).strip()
        if item and item.lower() not in ("none", "nan"):
            out.append(item)
    return out


def _text(value) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in ("none", "nan") else text


def _family(code: str) -> str:
    return FAMILY_NAMES.get(code or "", (code or "Other").title())


# -------------------------------------------------------------------- rulebook

def _rule_entry(rule: dict) -> dict:
    label = _text(rule.get("rule_label"))
    if rule.get("part") == "A" and label.isdigit():
        label = "Hardware %s" % label
    badges = []
    if rule.get("is_new"):
        badges.append("New in the latest revision")
    if rule.get("confidential"):
        badges.append("Contains figures that need their condition")
    if rule.get("requires_exact_competitor"):
        badges.append("Needs the exact competitor named")
    fields = [
        {"label": "Use when the account shows", "value": _text(rule.get("signal_text"))},
        {"label": "What to recommend", "value": _text(rule.get("system_action"))},
        {"label": "What may be said", "value": _list(rule.get("allowed_facts"))},
        {"label": "Conditions", "value": _list(rule.get("conditions"))},
        {"label": "Do not", "value": [p for p in _list(rule.get("prohibitions"))
                                      if p not in _list(rule.get("conditions"))]},
    ]
    return {
        "id": str(rule.get("_id")),
        "label": label,
        "title": _text(rule.get("offering")),
        "group": _family(rule.get("family")),
        "badges": badges,
        "fields": [f for f in fields if f["value"]],
    }


def _hp_rulebook(db) -> dict:
    book = rulebook.load(db)
    rules = [_rule_entry(r) for r in book["rules"]]
    present = {r["group"] for r in rules}
    groups = [g for g in FAMILY_NAMES.values() if g in present] + sorted(present - set(FAMILY_NAMES.values()))

    routing_rows = [[_text(r.get("opportunity_type")), _text(r.get("evidence_examples")),
                     ", ".join(_family(f) for f in _list(r.get("families"))) or _text(r.get("go_to_text"))]
                    for r in book["routing"]]

    guardrails = sorted(book["guardrails"], key=lambda g: (str(g.get("scope") or ""), int(g.get("order") or 0)))
    guardrail_rows = [[_text(g.get("guardrail_id")), _text(g.get("area")), _text(g.get("rule_text")),
                       SCOPE_NAMES.get(g.get("scope") or "", _family(str(g.get("scope") or "").upper()))]
                      for g in guardrails]

    matrix_sections = []
    for name, rows in sorted(book["matrices"].items()):
        rows = sorted(rows, key=lambda r: int(r.get("order") or 0))
        columns = []
        for r in rows:
            for key in (r.get("columns") or {}):
                if key not in columns:
                    columns.append(key)
        matrix_sections.append({
            "id": "matrix-%s" % name,
            "title": "Selection matrix: %s" % _family(str(rows[0].get("family") or name).upper()),
            "description": "Which option fits which case, as the rulebook's matrix sets out.",
            "kind": "table",
            "columns": [c[:1].upper() + c[1:] for c in columns],
            "rows": [[_text((r.get("columns") or {}).get(c)) for c in columns] for r in rows],
        })

    country_rows = [[_text(c.get("restriction_label")) or _text(c.get("restriction")).title(),
                     ", ".join(_list(c.get("countries")))]
                    for c in book["country_lists"].values()]

    return {
        "count": len(rules),
        "sections": [
            {"id": "rules", "title": "Product and service rules",
             "description": "Each rule says which account evidence makes an HP offering relevant, what to "
                            "recommend, exactly what may be said about it, and its conditions. A rule is used "
                            "only when the account's own evidence fires it.",
             "kind": "entries", "groups": groups, "entries": rules},
            {"id": "routing", "title": "Opportunity routing",
             "description": "Which kind of opportunity the account's evidence points to, and which rule "
                            "families answer it.",
             "kind": "table", "columns": ["Opportunity type", "Typical evidence", "Rule families"],
             "rows": routing_rows},
            {"id": "guardrails", "title": "Guardrails",
             "description": "Rules that apply to every recommendation drawn from the rulebook.",
             "kind": "table", "columns": ["Code", "Area", "Rule", "Applies to"], "rows": guardrail_rows},
            *matrix_sections,
            {"id": "countries", "title": "Country restrictions",
             "description": "Claims that may not be made in these countries.",
             "kind": "table", "columns": ["Restriction", "Countries"], "rows": country_rows},
        ],
    }


# ------------------------------------------------------------------- lifecycle

_LIFECYCLE_STATUS = {
    lifecycle.PAST_END: "Past end of life - not recommended",
    lifecycle.APPROACHING: "Approaching end of life - recommended with a flag",
    lifecycle.LISTED_FUTURE: "Listed, end of life ahead - recommended",
}


def lifecycle_row_status(row: dict, today) -> str:
    """The status `lifecycle.status_for` gives an offering once it has matched
    this row, read from the row's own dates. The row is not looked up by name:
    the matcher is built for rulebook offering names and does not always find a
    row from the row's own product name."""
    first, last, stamp = row.get("first_end"), row.get("last_end"), today.isoformat()
    if last and last < stamp:
        return lifecycle.PAST_END
    if first and first < stamp:
        return lifecycle.APPROACHING
    try:
        if last and (date.fromisoformat(last) - today).days <= lifecycle.APPROACHING_WITHIN_DAYS:
            return lifecycle.APPROACHING
    except ValueError:
        pass
    return lifecycle.LISTED_FUTURE


def _hp_lifecycle(db) -> dict:
    rows = lifecycle.load(db)
    today = datetime.now(UTC).date()
    table = []
    for row in sorted(rows, key=lambda r: (r.get("family") or "", r.get("product") or "")):
        table.append([_text(row.get("product")), _text(row.get("family")),
                      _text(row.get("first_end")), _text(row.get("last_end")),
                      _LIFECYCLE_STATUS[lifecycle_row_status(row, today)]])
    return {
        "count": len(table),
        "sections": [{
            "id": "products", "title": "Product end-of-life dates",
            "description": "Before an HP product is recommended it is looked up here. A product whose last "
                           "end date has passed is not recommended; one whose first end date has passed, or "
                           "whose last is within %d days, is recommended with a flag. A product not listed "
                           "here is not blocked. Status is as of today."
                           % lifecycle.APPROACHING_WITHIN_DAYS,
            "kind": "table", "columns": ["Product", "Family", "First end date", "Last end date", "Status today"],
            "rows": table,
        }],
    }


# ------------------------------------------------------------ intent dictionary

def _intent_dictionary(db) -> dict:
    rows = [[term, theme, category or "—"]
            for term, (theme, category) in sorted(intent_topic_map.TERMS.items(),
                                                  key=lambda kv: (kv[1][0], kv[0]))]
    return {
        "count": len(rows),
        "sections": [{
            "id": "topics", "title": "Research topics and their HP meaning",
            "description": "Each research topic the company shows interest in is placed in a theme, and in "
                           "an HP product category where one applies. A topic not listed here is left "
                           "unmapped rather than guessed.",
            "kind": "table", "columns": ["Topic", "Theme", "HP category"], "rows": rows,
        }],
    }


# ----------------------------------------------------- workplace technologies

def _workplace_technologies(db) -> dict:
    rows = [[name, group] for name, group in sorted(urgency.WORKPLACE_TECHNOLOGIES.items(),
                                                    key=lambda kv: (kv[1], kv[0]))]
    return {
        "count": len(rows),
        "sections": [{
            "id": "technologies", "title": "Workplace technologies that count",
            "description": "Technologies that count towards the workplace technology footprint in the "
                           "urgency score, grouped by what they do.",
            "kind": "table", "columns": ["Technology", "Group"], "rows": rows,
        }],
    }


# --------------------------------------------------------------------- registry

REFERENCE_SETS = {
    "hp_rulebook": {
        "title": "HP sales rulebook",
        "summary": "HP's approved rules for which product, service or solution fits which account "
                   "evidence, and exactly what may be said about it.",
        "used_by": ["objection_playbook", "solution_narrative_opportunity_map", "tech_landscape",
                    "message_evaluator"],
        "build": _hp_rulebook,
    },
    "hp_lifecycle": {
        "title": "Product lifecycle",
        "summary": "End-of-life dates that stop a retired HP product from being recommended.",
        "used_by": ["tech_landscape"],
        "build": _hp_lifecycle,
    },
    "intent_dictionary": {
        "title": "Research topic dictionary",
        "summary": "How each online research topic maps to a theme and an HP product category.",
        "used_by": ["intent_demand_signals", "solution_narrative_opportunity_map"],
        "build": _intent_dictionary,
    },
    "workplace_technologies": {
        "title": "Workplace technologies",
        "summary": "The technologies counted in the urgency score's workplace footprint.",
        "used_by": ["executive_dashboard"],
        "build": _workplace_technologies,
    },
}


def reference_index(db) -> list:
    out = []
    for key, spec in REFERENCE_SETS.items():
        out.append({"key": key, "title": spec["title"], "summary": spec["summary"],
                    "used_by": spec["used_by"], "count": spec["build"](db)["count"]})
    return out


def reference_set(db, key: str) -> dict:
    spec = REFERENCE_SETS[key]
    body = spec["build"](db)
    return {"key": key, "title": spec["title"], "summary": spec["summary"],
            "used_by": spec["used_by"], **body}
