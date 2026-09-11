"""HP product recommendations for the Technographic Map.

The chain is deterministic end to end except for the prose:

    verified account evidence
        -> product_rules.match_rules        (Python picks the rule)
        -> hp_product_knowledge             (the deck that rule maps to)
        -> guardrails.approve_facts         (Python filters the claims)
        -> confidence                       (Python assigns the band)
        -> GPT-4o                           (writes the rationale only)
        -> grounding, two corpora           (Python verifies what it wrote)

The model never chooses a product, never supplies a fact, and never sets a
confidence. It is handed the rule, the evidence and the approved facts, and
asked to explain the connection.

Two corpora are checked separately, because guardrail 13 forbids a deck from
establishing an account fact: prose about the account is verified against the
account's uploads, prose about the product against the approved HP facts.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors.grounding import (
    build_corpus, corpus_from_texts, check_text, GroundingReport,
)
from app.services.hp.guardrails import approve_facts, summarise
from app.services.hp.product_rules import RULES_BY_ID, match_rules

logger = logging.getLogger(__name__)

# 2 - confidence no longer matches "hp" as a substring, which had promoted
#     "Contextual - no direct HP line" categories to Confirmed.
# 3 - recommendations carry category_key/category_name so they render inside
#     the technographic category they concern.
RECOMMENDATION_PROMPT_VERSION = 3
MAX_RECOMMENDATIONS = 5
MAX_FACTS_PER_RECOMMENDATION = 8

KNOWLEDGE_COLLECTION = "hp_product_knowledge"
VERSION_DOC_ID = "__knowledge_version__"

# Which technographic category a recommendation belongs under, so it renders
# inside that category block rather than as a panel of its own. Derived from
# the rule's device type, which the rules table already fixes - no new
# inference, and nothing for the model to decide. A device type with no
# category stays None and renders after the list rather than being forced into
# a category it does not belong to.
DEVICE_TYPE_TO_CATEGORY = {
    "notebook": ("pc_laptop_brands", "PC/Laptop Brands"),
    "tower": ("workstations_compute", "Workstations & High-Performance Compute"),
    "sff": ("workstations_compute", "Workstations & High-Performance Compute"),
    "mini": ("workstations_compute", "Workstations & High-Performance Compute"),
    "aio": ("workstations_compute", "Workstations & High-Performance Compute"),
}

# Confidence is the ABX Feature 5 technology status carried forward, not a new
# invented number. The spec defines no numeric score for this feature.
CONFIDENCE_CONFIRMED = "Confirmed"
CONFIDENCE_LIKELY = "Likely"
CONFIDENCE_DISCOVERY = "Discovery"


def knowledge_version(db) -> str:
    doc = db[KNOWLEDGE_COLLECTION].find_one({"_id": VERSION_DOC_ID}) or {}
    return str(doc.get("knowledge_version") or "")


def _account_evidence(db, account_id: str) -> dict:
    """Only the account's own extracted data. No HP content enters here."""
    def widget(key):
        return (db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": key}) or {}).get("data") or {}

    exec_card = widget("exec_summary_card")
    matrix = widget("tech_stack_matrix")
    techno = widget("technographic_map")

    intent = [str(t.get("topic_name") or "")
              for t in (widget("intent_topics_table").get("topics") or [])]
    triggers = [str(t.get("headline") or t.get("text") or "")
                for t in (widget("opportunity_trigger_signals").get("triggers") or [])]
    stack = [str(s) for s in (matrix.get("full_tech_stack") or [])]

    return {
        "company_name": exec_card.get("company_name") or "",
        "hq_location": exec_card.get("hq_location") or "",
        "business_description": exec_card.get("business_description") or "",
        "intent_topics": intent,
        "triggers": triggers,
        "tech_stack": stack,
        "categories": techno.get("categories") or [],
        "texts": [exec_card.get("business_description") or ""] + intent + triggers + stack,
    }


def _confidence_for(category_status: str, has_trigger: bool, dropped: dict) -> tuple:
    """Deterministic. The model is never asked for this and never sees a score.

    Returns (band, basis).
    """
    status = (category_status or "").lower()
    basis = {
        "technology_status": category_status or "unknown",
        "timing_trigger_present": bool(has_trigger),
        "facts_dropped_by_guardrail": dropped or {},
    }

    # Order matters, and the checks are explicit rather than substring-loose.
    # A first version tested `"hp" in status`, which matched "Contextual - no
    # direct HP line" and promoted a category HP does not even address to
    # Confirmed.
    if "whitespace" in status or "open opportunity" in status:
        return CONFIDENCE_DISCOVERY, basis
    if "contextual" in status:
        # The deterministic layer says this category has no direct HP line, so
        # any product recommendation against it is exploratory by definition.
        return CONFIDENCE_DISCOVERY, basis
    if not has_trigger:
        return CONFIDENCE_LIKELY, basis
    if "displacement" in status or "complementary" in status or "existing hp" in status:
        return CONFIDENCE_CONFIRMED, basis
    return CONFIDENCE_LIKELY, basis


def _category_status_for_rule(categories: list, rule: dict) -> str:
    """The technographic status most relevant to this rule's device type."""
    wanted = {
        "notebook": ("client", "endpoint", "platform", "device"),
        "tower": ("platform", "storage", "compute"),
        "sff": ("platform", "storage", "compute"),
        "mini": ("platform", "device"),
        "aio": ("collaboration", "device"),
    }.get(rule.get("device_type") or "", ())

    for category in categories:
        label = " ".join(str(v) for v in (
            category.get("category"), category.get("category_name")) if v).lower()
        if any(w in label for w in wanted):
            return str(category.get("status_badge") or "")
    return str((categories[0] or {}).get("status_badge") or "") if categories else ""


def _fingerprint(evidence: dict, rule_ids: list, kversion: str) -> str:
    payload = {
        "prompt_version": RECOMMENDATION_PROMPT_VERSION,
        "knowledge_version": kversion,
        "rules": sorted(rule_ids),
        "evidence": sorted(t for t in evidence["texts"] if t),
        "hq": evidence["hq_location"],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


SYSTEM_PROMPT = """You write the rationale for HP product recommendations that have ALREADY been decided.

You are given, per recommendation:
  - the HP deck-usage rule that fired, and the account evidence that fired it
  - the HP product family and the approved product facts, already filtered for
    this account's market, configuration and embargo rules
  - a confidence band that has already been assigned

RULES, all mandatory:
1. Do NOT choose, change or suggest a different product. The product is fixed.
2. Do NOT state any HP product fact that is not in approved_facts for that
   recommendation. Copy the wording of a fact if you use it; never round,
   generalise or merge two facts.
3. Do NOT state anything about the account that is not in account_evidence.
   HP material can never be evidence about the account.
4. Do NOT output a confidence, score, rank or probability of any kind.
5. Keep every qualifier attached to the fact it belongs to: "up to", "optional",
   "where supported", "requires ...". Never present an optional feature as
   standard.
6. If a fact carries a condition, keep the condition with it.
7. Write plainly. No "perfect time", "ideal", "guarantees", "ensures".

Return JSON only:
{"recommendations": [{"rule_id": <int>, "rationale": "2-3 sentences connecting the
account evidence to this HP family", "why_this_product": "1-2 sentences using only
approved_facts", "discovery_question": "one neutral question a seller could ask"}]}"""


def generate_hp_recommendations(account_id: str) -> dict | None:
    """Build the technographic_hp_recommendations widget payload."""
    db = get_db()
    now = datetime.now(timezone.utc)
    kversion = knowledge_version(db)

    evidence = _account_evidence(db, account_id)
    if not evidence["texts"]:
        return None

    matched = match_rules(evidence["texts"], competitor_models=evidence["tech_stack"])
    live = [m for m in matched if not m["blocked"]]
    blocked = [m for m in matched if m["blocked"]]

    existing = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "technographic_hp_recommendations"})
    fingerprint = _fingerprint(evidence, [m["rule_id"] for m in live], kversion)
    if (existing and existing.get("status") == "available"
            and (existing.get("data") or {}).get("fingerprint") == fingerprint):
        return existing

    # ---- assemble candidates: Python decides everything here ----------------
    candidates = []
    for match in live:
        rule = RULES_BY_ID[match["rule_id"]]
        if rule.get("modifier_only") or rule.get("routing_only"):
            continue          # these qualify a product, they do not select one
        if not rule.get("deck_match"):
            continue

        slides = list(db[KNOWLEDGE_COLLECTION].find(
            {"deck": {"$regex": rule["deck_match"]}}))
        approved, rejected = approve_facts(slides, rule, evidence["hq_location"], now)
        if not approved:
            blocked.append({"rule_id": rule["rule_id"],
                            "blocked": "every fact was withheld by a guardrail"})
            continue

        status = _category_status_for_rule(evidence["categories"], rule)
        has_trigger = bool(evidence["triggers"])
        band, basis = _confidence_for(status, has_trigger, summarise(rejected))

        facts = [d.as_dict() for d in approved[:MAX_FACTS_PER_RECOMMENDATION]]
        category_key, category_name = DEVICE_TYPE_TO_CATEGORY.get(
            rule.get("device_type") or "", (None, None))
        candidates.append({
            "rule_id": rule["rule_id"],
            "rule_condition": rule["condition"],
            "matched_tokens": match["matched_tokens"],
            "hp_family": rule.get("family"),
            "device_type": rule.get("device_type"),
            "category_key": category_key,
            "category_name": category_name,
            "deck": rule["deck"],
            "approved_facts": facts,
            "withheld_summary": summarise(rejected),
            "confidence": band,
            "confidence_basis": basis,
            "account_evidence": [t for t in evidence["texts"]
                                 if any(tok in t.lower() for tok in match["matched_tokens"])][:4],
        })

    candidates.sort(key=lambda c: (c["confidence"] != CONFIDENCE_CONFIRMED,
                                   -len(c["approved_facts"])))
    candidates = candidates[:MAX_RECOMMENDATIONS]

    if not candidates:
        if existing and existing.get("status") == "available":
            return existing
        return _pending(account_id, now, kversion,
                        "No HP deck-usage rule matched this account's verified evidence, "
                        "or every candidate fact was withheld by a guardrail. "
                        "No deck is forced when no rule matches.", blocked)

    # ---- prose, and only prose ---------------------------------------------
    user_prompt = json.dumps({
        "company": evidence["company_name"],
        "recommendations": [{
            "rule_id": c["rule_id"],
            "rule_condition": c["rule_condition"],
            "hp_family": c["hp_family"],
            "device_type": c["device_type"],
            "account_evidence": c["account_evidence"],
            "approved_facts": [{"text": f["text"], "qualifiers": f["qualifiers"],
                                "conditions": f["conditions"]} for f in c["approved_facts"]],
        } for c in candidates],
    }, ensure_ascii=False)

    result = generate_gpt4o_json_completion(SYSTEM_PROMPT, user_prompt)
    prose = {}
    if result and isinstance(result.get("recommendations"), list):
        for entry in result["recommendations"]:
            if isinstance(entry, dict) and entry.get("rule_id") is not None:
                prose[int(entry["rule_id"])] = entry

    # ---- verify what it wrote, against two separate corpora -----------------
    account_corpus = build_corpus({"account": [{"t": t} for t in evidence["texts"]]})
    report = GroundingReport(account_corpus,
                             ["rationale", "why_this_product", "discovery_question"])
    report.hp_facts_checked = 0
    report.hp_facts_rejected = []

    out = []
    for candidate in candidates:
        entry = prose.get(candidate["rule_id"]) or {}
        rationale = str(entry.get("rationale") or "").strip()
        why = str(entry.get("why_this_product") or "").strip()
        question = str(entry.get("discovery_question") or "").strip()
        label = "rule-%d" % candidate["rule_id"]

        # Account-facing prose is checked against the account's own uploads.
        bad_numbers, bad_urls = check_text(account_corpus, report, label, rationale, question)
        if bad_numbers or bad_urls:
            rationale, question = "", ""
            logger.warning("hp recommendations: %s dropped account prose carrying "
                           "unsourced values", label)

        # Product prose is checked against the approved facts for THIS
        # recommendation only - never the account corpus, never another
        # product's facts.
        hp_corpus = corpus_from_texts(
            [f["text"] for f in candidate["approved_facts"]]
            + [c for f in candidate["approved_facts"] for c in f["conditions"]])
        report.hp_facts_checked += 1
        hp_bad_numbers = hp_corpus.unsourced_numbers(why)
        if hp_bad_numbers:
            report.hp_facts_rejected.append("%s: %s" % (label, hp_bad_numbers))
            logger.warning("hp recommendations: %s dropped product prose carrying "
                           "figures absent from its approved facts", label)
            why = ""

        candidate.update({"rationale": rationale or None,
                          "why_this_product": why or None,
                          "discovery_question": question or None})
        out.append(candidate)

    grounding = report.as_dict()
    grounding["hp_facts_checked"] = report.hp_facts_checked
    grounding["hp_facts_rejected"] = report.hp_facts_rejected

    return {
        "account_id": account_id,
        "feature_key": "tech_landscape",
        "widget_key": "technographic_hp_recommendations",
        "data_classification": "inferred",
        "status": "available",
        "data": {
            "fingerprint": fingerprint,
            "knowledge_version": kversion,
            "prompt_version": RECOMMENDATION_PROMPT_VERSION,
            "account_country": evidence["hq_location"],
            "recommendations": out,
            "recommendations_count": len(out),
            "rules_evaluated": len(matched),
            "rules_blocked": blocked,
            "grounding_report": grounding,
        },
        "source_datasets": ["technographics", "technology_detections", "webstack",
                            "intent_score", "firmographics"],
        "extracted_at": now,
        "updated_at": now,
    }


def _pending(account_id, now, kversion, notice, blocked):
    return {
        "account_id": account_id,
        "feature_key": "tech_landscape",
        "widget_key": "technographic_hp_recommendations",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "fingerprint": None,
            "knowledge_version": kversion,
            "recommendations": [],
            "recommendations_count": 0,
            "rules_blocked": blocked,
            "notice": notice,
        },
        "source_datasets": ["technographics", "technology_detections", "webstack",
                            "intent_score", "firmographics"],
        "extracted_at": now,
        "updated_at": now,
    }
