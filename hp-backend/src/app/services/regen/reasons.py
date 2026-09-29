"""Why a node is stale, in categories an admin can act on.

`manifest.diff` names the inputs that changed ("datasets.prospect_contacts",
"logic"). That is enough for a log line and not enough for a person deciding
whether to spend quota: "logic" does not say whether a developer bumped the
producer's version or a prompt changed, and "datasets.x" does not say which
upload. This module turns the difference between the committed manifest and the
one the inputs produce now into a list of reasons, each with a category and,
where there is one, the old and new value.

Pure: everything it needs is passed in, so the admin page, the preview and the
tests all read the same answer.
"""

DATA = "data_file"
UPSTREAM = "upstream"
CODE = "code"
PROMPT = "prompt"
RULES = "rules"
MODEL = "model"
INSTRUCTIONS = "instructions"
ACCOUNT = "account_details"
LEGACY = "legacy"
NEVER = "never_run"
FAILED = "failed"
FORCED = "forced"

CATEGORY_LABELS = {
    DATA: "Data file changed",
    UPSTREAM: "Upstream section changed",
    CODE: "Code change",
    PROMPT: "Prompt change",
    RULES: "Rules / knowledge change",
    MODEL: "Model change",
    INSTRUCTIONS: "Account instructions changed",
    ACCOUNT: "Account details changed",
    LEGACY: "Built before change tracking",
    NEVER: "Never run",
    FAILED: "Last run failed",
    FORCED: "Forced re-run",
}

# What the admin page calls each node. Features are what sellers see; a node is
# one producer inside one, so several read "<feature> - <part>".
NODE_LABELS = {
    "stakeholder_roster": "Stakeholder Map - contacts",
    "stakeholder_talking_points": "Stakeholder Map - talking points",
    "tech_core": "Tech Landscape",
    "tech_recs": "Tech Landscape - recommendations",
    "objection": "Objection Playbook",
    "intent": "Intent & Demand Signals",
    "opp_core": "Opportunity Map",
    "opp_triggers": "Opportunity Map - triggers",
    "content_persona": "Content Studio",
    "news": "Live Signals",
    "exec_core": "Executive Dashboard",
    "exec_priorities": "Executive Dashboard - strategic priorities",
    "idx_executive_dashboard": "Executive Dashboard - knowledge index",
    "evaluator_personas": "Message Evaluator",
    "strategy_snapshot": "Strategy Chat - snapshot",
    "idx_strategy": "Strategy Chat - knowledge index",
}

FEATURE_LABELS = {
    "executive_dashboard": "Executive Dashboard",
    "recent_news_signals": "Live Signals",
    "stakeholder_map": "Stakeholder Map",
    "solution_narrative_opportunity_map": "Opportunity Map",
    "tech_landscape": "Tech Landscape",
    "objection_playbook": "Objection Playbook",
    "content_studio": "Content Studio",
    "strategy_chat": "Strategy Chat",
    "message_evaluator": "Message Evaluator",
    "intent_demand_signals": "Intent & Demand Signals",
}

RULE_LABELS = {
    "rulebook": "HP rulebook", "case_studies": "case studies",
    "product_knowledge": "product knowledge", "lifecycle": "product lifecycle",
    "urgency": "urgency scoring", "evidence_strength": "evidence scoring",
    "live_signal": "live-signal scoring", "tech_confidence": "tech confidence scoring",
}


def node_label(node_id: str) -> str:
    return NODE_LABELS.get(node_id, node_id)


def feature_label(feature_id: str) -> str:
    return FEATURE_LABELS.get(feature_id, feature_id)


def _short(value, n=12):
    if value is None:
        return None
    text = str(value)
    return text[:n] if len(text) > n else text


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _reason(category, label, detail="", old=None, new=None, key=None) -> dict:
    return {"category": category, "category_label": CATEGORY_LABELS[category],
            "label": label, "detail": detail, "old": old, "new": new, "key": key}


def _dataset_detail(key: str, rows: list) -> str:
    if not rows:
        return "no active file any more (deleted)"
    latest = max(rows, key=lambda r: str(r.get("uploaded_at") or ""))
    name = latest.get("original_filename") or latest.get("stored_filename") or ""
    at = _iso(latest.get("uploaded_at"))
    count = len(rows)
    files = "%d files" % count if count > 1 else "file"
    return ("%s %s uploaded %s" % (files, name, at or "")).strip()


def _logic_reasons(old: dict, new: dict) -> list:
    out = []
    if int(old.get("own") or 0) != int(new.get("own") or 0):
        out.append(_reason(CODE, "Section logic updated in a deploy",
                           "logic version %s -> %s" % (old.get("own"), new.get("own")),
                           old.get("own"), new.get("own"), "logic.own"))
    old_refs, new_refs = old.get("refs") or {}, new.get("refs") or {}
    for ref in sorted(set(old_refs) | set(new_refs)):
        if old_refs.get(ref) != new_refs.get(ref):
            name = ref.rpartition(":")[2] or ref
            out.append(_reason(PROMPT, "%s changed" % name,
                               "%s %s -> %s" % (name, old_refs.get(ref), new_refs.get(ref)),
                               old_refs.get(ref), new_refs.get(ref), "logic.refs.%s" % name))
    return out


def classify(old_manifest, new_manifest: dict, *, rows=None, states=None) -> list:
    """Every reason `new_manifest` differs from `old_manifest`, categorised.

    `rows` is dataset_key -> active file rows (for which upload), `states` is
    node_id -> node_state doc (for when an upstream last committed).
    """
    rows, states = rows or {}, states or {}
    if not old_manifest:
        return [_reason(LEGACY, "Built before change tracking",
                        "output was adopted from the previous release and has not "
                        "been verified against its inputs")]
    out = []
    if old_manifest.get("logic") != new_manifest.get("logic"):
        out.extend(_logic_reasons(old_manifest.get("logic") or {},
                                  new_manifest.get("logic") or {}))

    old_ds, new_ds = old_manifest.get("datasets") or {}, new_manifest.get("datasets") or {}
    for key in sorted(set(old_ds) | set(new_ds)):
        if old_ds.get(key) != new_ds.get(key):
            out.append(_reason(DATA, key, _dataset_detail(key, rows.get(key) or []),
                               _short(old_ds.get(key)), _short(new_ds.get(key)),
                               "datasets.%s" % key))

    old_up, new_up = old_manifest.get("upstream") or {}, new_manifest.get("upstream") or {}
    for up in sorted(set(old_up) | set(new_up)):
        if old_up.get(up) != new_up.get(up):
            when = ((states.get(up) or {}).get("current") or {}).get("generated_at")
            out.append(_reason(UPSTREAM, node_label(up),
                               "regenerated %s" % _iso(when) if when else "new output",
                               _short(old_up.get(up)), _short(new_up.get(up)),
                               "upstream.%s" % up))

    for section in ("config", "knowledge"):
        old_v, new_v = old_manifest.get(section) or {}, new_manifest.get(section) or {}
        for name in sorted(set(old_v) | set(new_v)):
            if old_v.get(name) != new_v.get(name):
                out.append(_reason(RULES, RULE_LABELS.get(name, name),
                                   "%s updated" % RULE_LABELS.get(name, name),
                                   _short(old_v.get(name), 20), _short(new_v.get(name), 20),
                                   "%s.%s" % (section, name)))

    old_m, new_m = old_manifest.get("model") or {}, new_manifest.get("model") or {}
    names = {"provider": "Model provider", "chat": "Chat model",
             "retrieval": "Extraction model", "embedding": "Embedding model"}
    for name in sorted(set(old_m) | set(new_m)):
        if name in new_m and old_m.get(name) != new_m.get(name):
            before = old_m.get(name) or "not recorded"
            out.append(_reason(MODEL, names.get(name, "%s model" % name),
                               "%s -> %s" % (before, new_m.get(name)),
                               old_m.get(name), new_m.get(name), "model.%s" % name))

    if old_manifest.get("account_config") != new_manifest.get("account_config"):
        out.append(_reason(INSTRUCTIONS, "Account instructions or guardrails edited",
                           key="account_config"))
    if old_manifest.get("account_record") != new_manifest.get("account_record"):
        out.append(_reason(ACCOUNT, "Account name or domain changed",
                           key="account_record"))
    return out


def waiting_on(upstream_ids: list, derived: dict) -> list:
    """A node whose own inputs are unchanged but an ancestor is not current."""
    return [{**_reason(UPSTREAM, node_label(up),
                    "waiting on %s (%s)" % (node_label(up),
                                            derived[up]["lifecycle"].lower().replace("_", " ")),
                    key="waiting.%s" % up),
             "category_label": "Waiting on upstream"}
            for up in upstream_ids]


def categories(reasons: list) -> list:
    """The distinct categories, in first-seen order."""
    seen = []
    for r in reasons:
        if r["category"] not in seen:
            seen.append(r["category"])
    return seen
