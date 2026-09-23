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
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors.grounding import (
    GroundingReport,
    build_corpus,
    check_text,
    corpus_from_texts,
)
from app.services.hp import rulebook as rb
from app.services.hp.guardrails import (
    approve_facts,
    approve_rulebook_facts,
    prose_guardrail_faults,
    summarise,
)
from app.services.hp.product_rules import RULES_BY_ID, match_rules

logger = logging.getLogger(__name__)

# 2 - confidence no longer matches "hp" as a substring, which had promoted
#     "Contextual - no direct HP line" categories to Confirmed.
# 3 - recommendations carry category_key/category_name so they render inside
#     the technographic category they concern.
# 4 - Part A of the HP 220 Account Rulebook replaces the hand-typed rules and
#     the deck-extracted facts (C 02).
# 5 - the stored payload now reports the rulebook's version and counts the
#     rules the rulebook evaluated, which read as 0 on a card that existed.
# 6 - rules refused under C 06 are now reported in `rules_blocked` instead of
#     being discarded, so a single card can be explained rather than doubted.
# 7 - rules refused before selection are reported too, not only those C 06
#     withheld. A card missing because its only term was "microsoft azure"
#     should say so rather than simply not appear.
# 8 - a refused rule now carries the category it would have appeared in, so
#     the reason sits beside the empty category rather than at the page foot.
# 9 - Part B rules now produce a card in the category they speak to. Part A is
#     HP's client-hardware chapter, so four of the six categories could never
#     carry one while 144 service rules sat unused behind them.
# 10 - Part A now matches the account's whole research corpus, not four
#      widgets. HP's own signal for rule 1 names "AI hiring" and the hiring
#      data was unreachable. A card says which dataset earned it, and drops the
#      confidence band where no estate evidence fired it.
# 11 - the per-family cap no longer spends a slot on a modifier, which had
#      been cutting rule 1 before selection saw it; and a withheld rule is
#      reported once rather than twice.
# 12 - provenance drops the widget-derived restatement of a dataset it already
#      names, so a card does not cite "Autodesk" twice from two places.
RECOMMENDATION_PROMPT_VERSION = 12

# Whether hardware facts come from the rulebook (C 02) or from the decks.
#
# The rulebook is the client's authority and says plainly that the engine must
# not reopen the original HP files. Set False to fall back to the deck corpus,
# which is richer but is exactly what C 02 forbids at runtime.
RULEBOOK_PART_A = True
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

    # The account's whole research corpus, not just the four widgets this
    # feature used to read.
    #
    # Part A rules are evaluated HERE and nowhere else - the Opportunity Map
    # deliberately excludes them - so a signal this corpus cannot hold is a
    # signal the product can never match. Four of the twelve placeable Part A
    # rules name evidence the widgets do not carry: rule 1 is "Enterprise AI /
    # local AI ... AI HIRING ... AI-PC refresh", and the account's Data
    # Engineer job ad fires it. On the old 377-cell corpus it fired nothing,
    # so HP wrote a signal that had no way of being matched.
    research = rb.account_evidence(account_id)

    intent = [str(t.get("topic_name") or "")
              for t in (widget("intent_topics_table").get("topics") or [])]
    triggers = [str(t.get("headline") or t.get("text") or "")
                for t in (widget("opportunity_trigger_signals").get("triggers") or [])]
    stack = [str(s) for s in (matrix.get("full_tech_stack") or [])]

    # Widget-derived cells stay in the corpus beside the raw research. They are
    # the same facts in a tidier form, and keeping both means nothing that
    # matched before this widened can stop matching now.
    seen: set = set()
    texts = []
    for text in ([exec_card.get("business_description") or "", *intent,
                  *triggers, *stack] + [r["text"] for r in research]):
        text = str(text or "").strip()
        if text and text not in seen:
            seen.add(text)
            texts.append(text)

    return {
        "company_name": exec_card.get("company_name") or "",
        "hq_location": exec_card.get("hq_location") or "",
        "business_description": exec_card.get("business_description") or "",
        "intent_topics": intent,
        "triggers": triggers,
        "tech_stack": stack,
        "categories": techno.get("categories") or [],
        "texts": texts,
        # The same cells with their dataset and field, so a card can say which
        # of the account's files fired the rule instead of implying it came
        # from the technology export.
        "research": research,
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


# One Part B card per category, for the same reason `select` allows one play
# per opportunity type: a category carrying four Care Pack rules is a catalogue,
# not a recommendation.
MAX_PART_B_PER_CATEGORY = 1

# The datasets that describe the technology estate itself. A confidence band is
# a statement about the estate, so it is only published where the estate is
# what fired the rule.
ESTATE_DATASETS = frozenset((
    "technographics", "technology_detections", "webstack", "technographic_map",
))


def _category_families(category: dict) -> frozenset:
    """The rulebook families whose rules speak to this category.

    Derived from the category's own cards rather than a seventh hand-typed
    table: each vendor card already names the HP line it maps to, and
    `rulebook.HP_LINE_TO_RULEBOOK_FAMILIES` already says which families speak
    for a line. A whitespace category names its line too - Print Fleet's
    placeholder card says "HP Enterprise Print / MPS" - so an empty category
    can still reach the rules that would fill it.
    """
    families: set = set()
    for vendor in category.get("vendors") or []:
        if not isinstance(vendor, dict):
            continue
        line = str(((vendor.get("hp_play") or {}).get("product")) or "").strip().lower()
        families.update(rb.HP_LINE_TO_RULEBOOK_FAMILIES.get(line, ()))
    return frozenset(families)


def _part_b_cards(book, matches: list, categories: list, country: str,
                  now) -> list:
    """Part B recommendations, placed in the category they speak to.

    Part A is HP's client-hardware chapter: 12 of its 18 rules are notebooks and
    desktops, so only two of the six categories could ever carry a card and the
    other four - security, collaboration, print, client OS - had none, while 144
    Part B rules sat unused behind them.

    Nothing here is generated. A Part B card carries the rule's approved facts
    as HP wrote them, the way the Opportunity Map's service plays do: C 03 is
    "use exact facts", and passing an approved sentence through a model to be
    reworded is the one step that could turn it into an unapproved one.
    """
    cards, used = [], set()
    for category in categories or []:
        if not isinstance(category, dict):
            continue
        families = _category_families(category)
        if not families:
            continue
        for match in matches:
            if match["family"] not in families or match["rule_label"] in used:
                continue
            approved, rejected = approve_rulebook_facts(
                match["rule"], country, now)
            if not approved:
                continue
            used.add(match["rule_label"])
            cards.append({
                "rule_id": match["rule_label"],
                "part": "B",
                "hp_line": rb.RULEBOOK_FAMILY_TO_HP_LINE.get(match["family"]),
                "offering": match.get("offering"),
                "hp_family": match["family"],
                "device_type": None,
                "category_key": category.get("category_key"),
                "category_name": category.get("category_name"),
                "rule_condition": match["rule"].get("signal_text"),
                "matched_tokens": (match.get("qualifying_terms")
                                   or match.get("matched_terms")),
                "indicative_tokens": match.get("indicative_terms") or [],
                "approved_facts": [d.as_dict()
                                   for d in approved[:MAX_FACTS_PER_RECOMMENDATION]],
                "withheld_summary": summarise(rejected),
                "prohibitions": list(match["rule"].get("prohibitions") or []),
                # No confidence band: the Part A bands are computed from the
                # category status of a DEVICE, and a service rule has no device
                # to check the estate for. An invented band would look like the
                # same measurement.
                "confidence": None,
                "deck": match["rule"].get("evidence_source"),
                "quoted_verbatim": True,
            })
            if len([c for c in cards
                    if c["category_key"] == category.get("category_key")
                    ]) >= MAX_PART_B_PER_CATEGORY:
                break
    return cards


def _blocked_placement(rule_label: str) -> dict:
    """Which category a refused rule would have appeared in, had it been used.

    A refusal listed at the foot of the page answers a question nobody asked
    there. The question is asked in the category that LOOKS empty - "no HP
    client hardware detected" with no recommendation under it - so the answer
    belongs beside it. Rule 2 is a notebook rule, and PC/Laptop Brands is the
    category a seller is staring at when they wonder why nothing was suggested.

    A rule with no device type in the bridge has no category to sit in and
    stays with the general list.
    """
    bridge = RULES_BY_ID.get(int(rule_label)) if rule_label.isdigit() else None
    key, name = DEVICE_TYPE_TO_CATEGORY.get(
        (bridge or {}).get("device_type") or "", (None, None))
    return {"category_key": key, "category_name": name,
            "deck": (bridge or {}).get("deck")}


def _rulebook_candidates(db, evidence: dict, now):
    """Part A rules this account's evidence earns, as recommendation candidates.

    The same shape the deck path produces, so everything downstream - the
    prompt, the two-corpus grounding, Strategy Chat, the evaluator, the
    dashboard and `audit_grounding.py` - is unchanged.

    Metadata the rulebook does not carry (the deck this rule maps to, the
    device type, the HP family, the exact-competitor requirement) is read from
    `product_rules.RULES_BY_ID`, which was transcribed from an earlier HP
    document and has been in production since. The rulebook decides WHICH rule
    and WHAT may be said; the bridge supplies what the document is silent on.
    """
    book = rb.load(db)
    if not book.get("rules"):
        return [], [], ""

    # Provenanced, so a matched rule knows which file fired it. Widget-derived
    # cells carry no dataset of their own and are labelled as such rather than
    # borrowed from one.
    items = list(evidence.get("research") or [])
    known = {i["text"] for i in items}
    items += [{"text": t, "dataset": "technographic_map", "field": "derived"}
              for t in evidence["texts"] if t not in known]
    refused: list = []
    every = rb.candidates(book, items, None, evidence["hq_location"],
                          drops=refused)
    # Part B cards for the four categories Part A can never reach. Built from
    # the same match pass, so both halves answer from one reading of the
    # evidence rather than two.
    part_b = _part_b_cards(book, [m for m in every if m["rule"].get("part") != "A"],
                           evidence.get("categories") or [],
                           evidence["hq_location"], now)
    matches = [m for m in every if m["rule"].get("part") == "A"]
    chosen = rb.select(matches)
    if not chosen["primary"]:
        # Part A found nothing, which says nothing about Part B.
        return part_b, [], rb.knowledge_version(db)

    candidates, blocked = [], []

    # C 06 refusals, reported rather than dropped. `select` already records why
    # it refused each one; this used to discard that, so a page showing one card
    # gave no way to tell whether one rule fired or five - and the honest answer
    # (four more fired, on the same sentence as the first) is the useful one.
    # C 07 asks for exactly this: "leave out the recommendation or label the
    # missing condition clearly."
    # Rules that never became candidates: a condition failed, or every term
    # they matched on was one that points at a rule without earning it.
    for dropped in refused:
        label = str(dropped.get("rule_label", ""))
        if not label.isdigit():
            continue                      # Part B belongs to the Opportunity Map
        blocked.append({"rule_id": dropped["rule_label"],
                        "blocked": "; ".join(dropped.get("unmet") or [])
                                   or "no qualifying evidence",
                        **_blocked_placement(label)})

    for match in chosen.get("withheld") or []:
        blocked.append({
            "rule_id": match["rule_label"],
            "offering": match.get("offering"),
            "blocked": match.get("withheld_because")
                       or "C 06: no separate verified evidence supports it",
            "matched_tokens": match.get("qualifying_terms")
                              or match.get("matched_terms"),
            **_blocked_placement(str(match["rule_label"])),
        })

    for match in [chosen["primary"], *chosen["secondary"]]:
        rule = match["rule"]
        label = rule["rule_label"]
        bridge = RULES_BY_ID.get(int(label)) if str(label).isdigit() else None

        approved, rejected = approve_rulebook_facts(
            {**rule,
             "requires_exact_competitor": bool((bridge or {}).get(
                 "requires_exact_competitor"))},
            evidence["hq_location"], now)
        if not approved:
            blocked.append({"rule_id": label,
                            "blocked": "every fact was withheld by a guardrail"})
            continue

        shim = {"device_type": (bridge or {}).get("device_type")}
        fired_rows = [items[i] for i in sorted(match["evidence_indices"])
                      if i < len(items)]
        # A widget-derived cell is a restatement of a dataset this list already
        # names - "Autodesk" beside the technographics row it was lifted from -
        # so it is dropped from the provenance rather than shown as a second
        # source. It stays in the match corpus; it is just not evidence of
        # anything the raw row does not already show.
        real = [r for r in fired_rows
                if r.get("dataset") and r["dataset"] != "technographic_map"]
        fired_rows = real or fired_rows
        fired_in = sorted({str(r.get("dataset") or "") for r in fired_rows})
        status = _category_status_for_rule(evidence["categories"], shim)
        band, basis = _confidence_for(status, bool(evidence["triggers"]),
                                      summarise(rejected))
        basis["fired_by_datasets"] = fired_in

        # The band measures whether this DEVICE's category is confirmed in the
        # estate. Where nothing in the estate fired the rule - the account is
        # hiring data engineers, say - the band would be reporting a
        # measurement of something other than the reason the card exists. C 07
        # would rather label the gap than dress it up, so the band is dropped
        # and the reason recorded in its place.
        if not (set(fired_in) & ESTATE_DATASETS):
            band = None
            basis["no_band_because"] = (
                "no technology-estate evidence fired this rule; it was earned "
                "by %s" % (", ".join(d for d in fired_in if d) or "other research"))

        category_key, category_name = DEVICE_TYPE_TO_CATEGORY.get(
            shim["device_type"] or "", (None, None))
        candidates.append({
            "rule_id": label,
            "rule_condition": rule.get("signal_text"),
            "matched_tokens": match["matched_terms"],
            "hp_family": (bridge or {}).get("family"),
            "device_type": shim["device_type"],
            "category_key": category_key,
            "category_name": category_name,
            # Provenance only. C 02: "Source names are provenance only; the
            # engine must not reopen the original HP files."
            "deck": rule.get("material") or (bridge or {}).get("deck"),
            "approved_facts": [d.as_dict()
                               for d in approved[:MAX_FACTS_PER_RECOMMENDATION]],
            "withheld_summary": summarise(rejected),
            "confidence": band,
            "confidence_basis": basis,
            # Named, not implied. A card in PC/Laptop Brands earned by a job ad
            # must not carry a "technographics ->" line it did not come from.
            "fired_by_datasets": fired_in,
            "account_evidence": [
                {"text": str(r.get("text") or "")[:300],
                 "dataset": r.get("dataset"),
                 "field": r.get("field")}
                for r in fired_rows[:4]],
            "unverified_conditions": match["unverified_conditions"],
            "fact_source": "rulebook",
        })

    return candidates + part_b, blocked, rb.knowledge_version(db)


def _fingerprint(evidence: dict, rule_ids: list, kversion: str) -> str:
    payload = {
        "prompt_version": RECOMMENDATION_PROMPT_VERSION,
        "knowledge_version": kversion,
        # Rule ids are strings under the rulebook and were ints under the
        # hand-typed table. `sorted` raises TypeError on a mixed list, so they
        # are normalised before sorting rather than after a crash.
        "rules": sorted(str(r) for r in rule_ids),
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
    now = datetime.now(UTC)
    kversion = knowledge_version(db)

    evidence = _account_evidence(db, account_id)
    if not evidence["texts"]:
        return None

    rulebook_candidates, rulebook_blocked, rversion = [], [], ""
    if RULEBOOK_PART_A:
        rulebook_candidates, rulebook_blocked, rversion = _rulebook_candidates(
            db, evidence, now)

    matched, live, blocked = [], [], []
    if not RULEBOOK_PART_A:
        matched = match_rules(evidence["texts"],
                              competitor_models=evidence["tech_stack"])
        live = [m for m in matched if not m["blocked"]]
        blocked = [m for m in matched if m["blocked"]]

    existing = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "technographic_hp_recommendations"})
    rule_ids = ([c["rule_id"] for c in rulebook_candidates] if RULEBOOK_PART_A
                else [m["rule_id"] for m in live])
    # The rulebook's own version joins the fingerprint, so reloading it
    # rebuilds these the way reloading the decks already did.
    fingerprint = _fingerprint(evidence, rule_ids, kversion + "|" + rversion)
    if (existing and existing.get("status") == "available"
            and (existing.get("data") or {}).get("fingerprint") == fingerprint):
        return existing

    # ---- assemble candidates: Python decides everything here ----------------
    if RULEBOOK_PART_A:
        candidates = rulebook_candidates
        blocked = rulebook_blocked
    else:
        candidates = []

    # `live` is empty under the rulebook, so this loop is the deck path only.
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

    # Part B never reaches the model. Its text is HP's approved wording carried
    # verbatim, the way the Opportunity Map's service plays are: C 03 is "use
    # exact facts", and passing an approved sentence through a model to be
    # reworded is the one step that could make it unapproved. So the two halves
    # separate here - Part A goes on to the prompt, Part B goes straight out.
    part_b_cards = [c for c in candidates if c.get("part") == "B"]
    candidates = [c for c in candidates if c.get("part") != "B"]

    candidates.sort(key=lambda c: (c["confidence"] != CONFIDENCE_CONFIRMED,
                                   -len(c["approved_facts"])))
    # C 06 - "Give one main recommendation. Add another product or service only
    # when separate verified evidence supports it" - is enforced by
    # `rulebook.select` before we get here, so the rulebook path arrives
    # already limited and the cap below only applies to the deck path.
    if not RULEBOOK_PART_A:
        candidates = candidates[:MAX_RECOMMENDATIONS]

    if not candidates and not part_b_cards:
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

    # Only Part A needs the model, and an account can now have Part B cards and
    # no Part A rule at all - a security-only or print-only match. Calling with
    # an empty list would spend a request to be told nothing.
    result = (generate_gpt4o_json_completion(SYSTEM_PROMPT, user_prompt)
              if candidates else None)
    prose = {}
    if result and isinstance(result.get("recommendations"), list):
        for entry in result["recommendations"]:
            if isinstance(entry, dict) and entry.get("rule_id") is not None:
                # Keyed as a string: Part B ids read "WXP 01" and int() on one
                # raises. Part A's are numeric but arrive as strings too.
                prose[str(entry["rule_id"])] = entry

    # ---- verify what it wrote, against two separate corpora -----------------
    account_corpus = build_corpus({"account": [{"t": t} for t in evidence["texts"]]})
    report = GroundingReport(account_corpus,
                             ["rationale", "why_this_product", "discovery_question"])
    report.hp_facts_checked = 0
    report.hp_facts_rejected = []

    out = []
    for candidate in candidates:
        entry = prose.get(str(candidate["rule_id"])) or {}
        rationale = str(entry.get("rationale") or "").strip()
        why = str(entry.get("why_this_product") or "").strip()
        question = str(entry.get("discovery_question") or "").strip()
        # %s, not %d: a rulebook rule id is a string.
        label = "rule-%s" % candidate["rule_id"]

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

        # Product guardrails 15 and 16. A figure can be correctly sourced and
        # still be used to make a claim the document forbids - "13 TOPS" is a
        # real fact, and calling that product a Next Gen AI PC is false by the
        # rulebook's own definition.
        if why:
            faults = prose_guardrail_faults(why, candidate["approved_facts"])
            if faults:
                report.hp_facts_rejected.append("%s: %s" % (label, "; ".join(faults)))
                logger.warning("hp recommendations: %s dropped product prose - %s",
                               label, faults)
                why = ""

        candidate.update({"rationale": rationale or None,
                          "why_this_product": why or None,
                          "discovery_question": question or None})
        out.append(candidate)

    # Part B after Part A, so a category that has both reads hardware first.
    out.extend(part_b_cards)

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
            # Both paths. Under RULEBOOK_PART_A the deck matcher evaluates
            # nothing, so counting only `matched` reported "0 rules evaluated"
            # on a widget showing a recommendation - which reads as a bug to
            # anyone checking why a card appeared.
            "rules_evaluated": len(matched) + len(rulebook_candidates),
            "rules_blocked": blocked,
            # The deck corpus version is kept above as `knowledge_version`
            # because the older path keys on it. The rulebook has its own, and
            # it is the one that decides these cards today.
            "rulebook_version": rversion,
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
