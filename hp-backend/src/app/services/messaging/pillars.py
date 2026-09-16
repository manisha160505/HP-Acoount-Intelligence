"""Content Messaging - the message house, built on retrieval.

ABX Feature 15 in six steps, five of them deterministic:

    [D/D] 1  select the highest-priority account challenges from verified evidence
    [D/D] 2  store the challenge and its source BEFORE writing any HP benefit
    [D/D] 3  match official HP benefits and solutions that answer that challenge
    [D/D] 4  attach each proof to the individual claim, not to the pillar
    [VLLM] 5 write the umbrella message over the pillars, adding no new fact
    [D/D] 6  dedupe products and proof, then publish

The division is kept exactly. The model proposes candidate challenges and
writes prose; Python decides which survive, in what order, and what may be
said about HP.

**Candidates are retrieved first, then filtered.** The retrieval layer answers
with candidate challenges and the evidence ids behind them; this module then
drops anything whose evidence does not resolve, anything not HP-addressable,
and anything that duplicates another pillar. Nothing is ranked by an invented
number - ABX asks to "rank account evidence by strategic relevance" but defines
no formula for this feature, and explicitly forbids inventing one elsewhere, so
ordering is by evidence weight and nothing masquerades as a score.

**The evidence registry is the authority, not the model.** An `evidence_id` the
model returns that does not resolve - or resolves to another account - drops the
claim it supported and increments `invalid_evidence_count`. Same discipline as
the Message Evaluator's phrase spans.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors.grounding import (
    HP_PRODUCT_LINES,
    filter_enum_list,
    normalize_hp_product,
)
from app.services.hp.guardrails import (
    COMPETITOR_BLOCK_COUNTRIES,
    SUPERLATIVE_BLOCK_COUNTRIES,
    normalize_country,
)
from app.services.retrieval import evidence as ev, index_state, query

logger = logging.getLogger(__name__)

INDEX = "content_messaging"
WIDGET_KEY = "messaging_pillars_output"
PROMPT_VERSION = 2

MIN_PILLARS = 3
MAX_PILLARS = 5
MIN_EVIDENCE_PER_PILLAR = 1

# The question put to the graph. Deliberately about the ACCOUNT's problems, not
# about HP - asking "what should HP sell" invites the model to answer from
# product knowledge rather than from account evidence.
CHALLENGE_QUESTION = (
    "What are this account's most significant operational and technology "
    "challenges, based only on its own evidence - its technology stack, "
    "research intent, recent events and identified opportunities? For each "
    "challenge, quote the evidence identifiers in square brackets that support "
    "it."
)


def _text(value) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return ""
    return " ".join(str(value if value is not None else "").split())


class PillarError(Exception):
    """Content Messaging cannot be generated from what is available."""


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

# Readable provenance for a source chip. The dataset is what the evidence
# registry records, so this is the one place that turns it into something a
# seller reads - no chip ever shows a bare identifier as its only label.
DATASET_LABELS = {
    "hp_products": "HP product deck",
    "content_messaging": "Account evidence",
    "firmographics": "Firmographics",
    "technographics": "Technographics",
    "intent_score": "Bombora intent",
    "google_news": "Google News",
    "news_events": "News events",
    "job_openings": "Job postings",
    "prospect_contacts": "Contact records",
}

# Where a document's evidence came from, when the dataset alone is too coarse.
# The corpus keeps account material under one dataset, so the document is what
# distinguishes a news item from a technology row.
DOC_LABELS = (
    ("news_signals", "Account news"),
    ("news_triggers", "Account news"),
    ("opportunity_plays", "Opportunity analysis"),
    ("technology_stack", "Technology stack"),
    ("technology_categories", "Technology stack"),
    ("intent_topics", "Bombora intent"),
    ("account_profile", "Company profile"),
    ("hp_products", "HP product deck"),
)


def source_label(row: dict) -> str:
    """What a source chip reads, in order of how specific it is.

    The row's own dataset comes before the document heuristic. An opportunity
    play restates a technographics cell; labelling that "Opportunity analysis"
    named the step that assembled the sentence rather than the evidence behind
    the claim, which is the thing a seller needs to judge.
    """
    row = row or {}
    publisher = _text(row.get("publisher"))
    if publisher:
        return publisher

    dataset = row.get("dataset")
    # The corpus keeps its own assembled material under the feature's name, so
    # that value is not a real provenance and defers to the document heuristic.
    if dataset and dataset not in (INDEX, "content_messaging"):
        return DATASET_LABELS.get(dataset, dataset.replace("_", " ").title())

    doc_id = row.get("doc_id") or ""
    for marker, label in DOC_LABELS:
        if marker in doc_id:
            return label
    return DATASET_LABELS.get(dataset, "Account evidence")


def _source(row: dict) -> dict:
    """One citation, as the UI shows it.

    `label` is what the chip reads and `source_url` is the link when the
    evidence genuinely has one; `evidence_id` stays so a claim remains traceable
    to the exact registry row behind it.
    """
    out = {
        "evidence_id": row["evidence_id"],
        "dataset": row["dataset"],
        "field": row.get("field"),
        "source_text": row["source_text"],
        "label": source_label(row),
    }
    if row.get("source_url"):
        out["source_url"] = row["source_url"]
    if row.get("publisher"):
        out["publisher"] = row["publisher"]
    # The raw value the sentence was written about, so a tooltip can show the
    # cell itself rather than only the prose derived from it.
    if row.get("quote"):
        out["quote"] = row["quote"]
    return out


def _hp_resource(pillar: dict, plays: list) -> dict | None:
    """The public HP page for what this pillar sells, or None.

    Taken from the opportunity play whose products the pillar actually names -
    the URL comes from the plays data, so there is no hardcoded link table and
    nothing to keep in step with HP's site. A pillar that matches no play gets
    no chip, rather than a default one that would point somewhere it did not
    earn.

    This is deliberately NOT attached to a proof point. HP deck facts cite a
    slide in a confidential deck; pointing that citation at a marketing page
    would tell a seller the claim came from somewhere it did not.
    """
    ordered = [_text(s).lower() for s in (pillar.get("hp_solutions") or []) if _text(s)]
    named = set(ordered)
    if not named:
        return None

    # A play may cover several lines - the PC play lists workstations too - so
    # overlap alone ties and the first play declared wins, which sent every
    # pillar to the same laptops page. Ranked instead by: how much it covers,
    # then whether it covers the pillar's OWN primary line, then how specific
    # the play is. A workstation pillar then reaches the workstation page.
    scored = []
    for play in (plays or []):
        if not _text(play.get("hp_resource_url")):
            continue
        products = {_text(p).lower() for p in (play.get("hp_products") or [])}
        overlap = named & products
        if not overlap:
            continue
        primary_rank = next((i for i, s in enumerate(ordered) if s in products),
                            len(ordered))
        scored.append(((len(overlap), -primary_rank, -len(products)), play))

    if not scored:
        return None
    best = max(scored, key=lambda pair: pair[0])[1]
    return {
        "label": _text(best.get("category_label")) or _text(best.get("title")) or "HP",
        "url": _text(best.get("hp_resource_url")),
        "play_key": _text(best.get("play_key")),
    }


def _sourced_count(pillar: dict) -> dict:
    """How many of this pillar's proof points actually carry a source.

    Counted, never generated - the badge in the UI is arithmetic over the
    resolved registry rows, so it cannot flatter the pillar.
    """
    proofs = pillar.get("proof_points") or []
    with_source = sum(1 for p in proofs if p.get("sources"))
    return {"sourced": with_source, "total": len(proofs)}


# ---------------------------------------------------------------------------
# Step 1-2: candidates from retrieval, then filtered in Python
# ---------------------------------------------------------------------------

CANDIDATE_SYSTEM = """You identify an account's own challenges from retrieved evidence.

You are given retrieved context about ONE account. Every line of it carries an
evidence identifier in square brackets, like [a1b2c3d4_technology_stack#c7].

Return the account's most significant challenges. For each one:
  - state the challenge as a fact about THIS account, not as generic industry pain
  - list the evidence identifiers that support it, copied EXACTLY from the context

Rules that are checked in code after you answer:
1. An evidence identifier you did not copy from the context will not resolve,
   and the challenge that depends on it is discarded. Never invent one.
2. A challenge with no evidence identifier is discarded.
3. Do not name HP or any HP product here. This step is about the account only.
4. Do not introduce a number, percentage or date that is not in the context.

Return JSON:
{"challenges": [{"challenge": "<one sentence about this account>",
                 "evidence_ids": ["<copied exactly>"],
                 "theme": "<two or three words>"}]}"""


async def _candidate_challenges(account_id: str, mode: str | None = None) -> tuple:
    """(candidates, retrieval_result). Retrieval first - no filtering yet."""
    result = await query.retrieve(account_id, INDEX, CHALLENGE_QUESTION,
                                  mode=mode, top_k=60)
    user = "\n".join([
        "RETRIEVED CONTEXT (every line carries its evidence identifier):",
        result.context[:60000],
        "",
        "Identify the account's challenges from the context above.",
        "Return JSON only.",
    ])
    raw = generate_gpt4o_json_completion(CANDIDATE_SYSTEM, user) or {}
    return (raw.get("challenges") or []), result


def _resolve_challenges(account_id: str, candidates: list) -> tuple:
    """Keep only challenges whose evidence actually resolves.

    Returns (kept, dropped, invalid_total). `dropped` carries the reason, so the
    widget can report what was discarded rather than silently showing fewer
    pillars.
    """
    kept, dropped, invalid_total = [], [], 0

    for candidate in (candidates or []):
        if not isinstance(candidate, dict):
            continue
        text = _text(candidate.get("challenge"))
        if not text:
            continue

        resolved, invalid = ev.resolve(account_id, INDEX,
                                       candidate.get("evidence_ids") or [])
        invalid_total += len(invalid)
        if len(resolved) < MIN_EVIDENCE_PER_PILLAR:
            dropped.append({"challenge": text[:160],
                            "reason": "no resolvable account evidence",
                            "invalid_ids": invalid[:4]})
            continue

        kept.append({
            "challenge": text,
            "theme": _text(candidate.get("theme")) or "Account challenge",
            "evidence": [_source(r) for r in resolved],
            "invalid_evidence_ids": invalid,
        })

    # Ordering: how much verified evidence stands behind it, then how many
    # distinct datasets agree. Both are counts of real rows - not a score.
    kept.sort(key=lambda c: (-len(c["evidence"]),
                             -len({e["dataset"] for e in c["evidence"]})))
    return kept, dropped, invalid_total


# ---------------------------------------------------------------------------
# Step 3-4: HP benefit and solutions, per challenge
# ---------------------------------------------------------------------------

PILLAR_SYSTEM = """You write one messaging pillar for an HP seller.

You are given ONE verified account challenge, the account's own evidence, and
the HP capability facts approved for this account. Write the pillar.

Rules that are checked in code after you answer:
1. Name HP solutions only as a CLASS, never a specific model or SKU. "HP Elite
   / Pro PCs", not "HP EliteBook 840 G11". A product name that is not a
   recognised HP line is removed.
2. Every proof point must cite an evidence identifier copied EXACTLY from the
   evidence supplied. A proof whose identifier does not resolve is removed.
3. The benefit must answer THIS challenge. Do not restate the challenge.
4. Do not introduce a number, percentage, date or entity that is not in what you
   were given. Everything specific must come from the evidence.
5. Where you are interpreting rather than citing, say so plainly - that text is
   labelled "HP account analysis" and must not read like a sourced claim.

WRITE PROPERLY, NOT IN SUMMARY:
- "challenge_detail" is 3-6 sentences telling the account's situation in its own
  specifics - the systems it runs, what it is hiring for or researching, what it
  has announced, and what that implies about its hardware. Use the dates, names
  and figures the ACCOUNT EVIDENCE gives you. A single generic sentence is a
  failed answer.
- "hp_benefit" is 3-5 sentences: what HP changes for THIS situation, which teams
  or workloads it touches, and why that follows from the challenge above.
- "proof_points" are 3-5 statements of FACT with their citation. Prefer the
  account's own evidence - what it announced, runs, or is researching - over HP
  product specifications. A pillar proved only by datasheet lines proves nothing
  about this account.

Return JSON:
{"pillar_title": "<short theme, 2-5 words>",
 "challenge_detail": "<3-6 sentences, specific to this account>",
 "hp_benefit": "<3-5 sentences>",
 "hp_solutions": ["<HP product line>"],
 "proof_points": [{"proof": "<one factual sentence>", "evidence_ids": ["<copied exactly>"]}],
 "target_role": "<the role this speaks to, or empty>",
 "next_step": "<one concrete next step, or empty>"}"""


def _account_evidence_block(db, account_id: str, limit: int = 90) -> str:
    """The account's own evidence, citable by the pillar.

    An earlier version offered only the approved HP facts as proof, so every
    proof point cited a datasheet line and the pillars read like a product
    brochure. The registry holds far more - news, intent, the technology stack,
    the opportunity plays - and those are what prove something about THIS
    account. Ordered so dated, externally-sourced material comes first, because
    that is what a seller can actually stand behind.
    """
    rows = list(db[ev.COLLECTION].find(
        {"account_id": account_id, "index": INDEX,
         "dataset": {"$ne": "hp_products"}},
        {"_id": 0}))

    def rank(row):
        doc = row.get("doc_id") or ""
        if "news" in doc:
            return 0
        if "opportunity_plays" in doc:
            return 1
        if "technology" in doc or "account_profile" in doc:
            return 2
        return 3

    rows.sort(key=rank)
    return "\n".join(
        "%s [%s] (%s)" % (row["source_text"][:300], row["evidence_id"],
                          source_label(row))
        for row in rows[:limit])


def _hp_fact_block(db, account_id: str) -> tuple:
    """Approved HP facts with their evidence ids, for the prompt."""
    rows = list(db[ev.COLLECTION].find(
        {"account_id": account_id, "index": INDEX, "dataset": "hp_products"},
        {"_id": 0}))
    lines = ["%s [%s]" % (r["source_text"], r["evidence_id"]) for r in rows]
    return "\n".join(lines[:120]), {r["evidence_id"] for r in rows}


def _restrictions(db, account_id: str) -> dict:
    exec_card = (db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
    ).get("data") or {}
    country = normalize_country(_text(exec_card.get("hq_location")))
    return {
        "country": country,
        "superlatives_blocked": bool(country) and country in SUPERLATIVE_BLOCK_COUNTRIES,
        "competitor_claims_blocked": bool(country) and country in COMPETITOR_BLOCK_COUNTRIES,
    }


def _build_pillar(account_id: str, challenge: dict, hp_facts: str,
                  account_facts: str, restrictions: dict) -> dict | None:
    """One pillar. Returns None when nothing survives validation."""
    guard = []
    if restrictions["superlatives_blocked"]:
        guard.append("Superlative claims are not permitted in %s - do not write "
                     "'world's most', 'industry-leading', 'best in class' or "
                     "similar." % restrictions["country"].title())
    if restrictions["competitor_claims_blocked"]:
        guard.append("Competitor comparison claims are not permitted in %s - do "
                     "not name or compare against another vendor."
                     % restrictions["country"].title())

    user = "\n".join([
        "THE ACCOUNT CHALLENGE (verified):",
        challenge["challenge"],
        "",
        "THE EVIDENCE BEHIND IT:",
        "\n".join("  %s [%s]" % (e["source_text"][:300], e["evidence_id"])
                  for e in challenge["evidence"]),
        "",
        "THE ACCOUNT'S OWN EVIDENCE (cite these by identifier - prefer these "
        "for proof points):",
        account_facts or "  (none available)",
        "",
        "APPROVED HP CAPABILITY FACTS (cite these by identifier):",
        hp_facts or "  (none approved for this account)",
        "",
        "HP lines you may name: %s" % ", ".join(HP_PRODUCT_LINES),
        "",
        "\n".join(guard),
        "",
        "Return JSON only.",
    ])

    raw = generate_gpt4o_json_completion(PILLAR_SYSTEM, user) or {}
    if not isinstance(raw, dict):
        return None

    benefit = _text(raw.get("hp_benefit"))
    if not benefit:
        return None

    products, rejected_products = filter_enum_list(
        raw.get("hp_solutions") or [], HP_PRODUCT_LINES)

    proofs, dropped_proofs = [], []
    for item in (raw.get("proof_points") or []):
        if not isinstance(item, dict):
            continue
        text = _text(item.get("proof"))
        if not text:
            continue
        resolved, invalid = ev.resolve(account_id, INDEX,
                                       item.get("evidence_ids") or [])
        if not resolved:
            dropped_proofs.append({"proof": text[:160], "invalid_ids": invalid[:3]})
            continue
        proofs.append({"proof": text, "sources": [_source(r) for r in resolved]})

    # The retrieved one-liner stays as the summary headline; the detailed
    # telling becomes the body, but only when the model actually wrote one.
    detail = _text(raw.get("challenge_detail"))

    return {
        "pillar_title": _text(raw.get("pillar_title")) or challenge["theme"],
        "challenge": detail or challenge["challenge"],
        "challenge_headline": challenge["challenge"],
        "challenge_evidence": challenge["evidence"],
        "hp_benefit": benefit,
        "hp_benefit_label": "HP account analysis",
        "hp_solutions": products,
        "proof_points": proofs,
        "target_role": _text(raw.get("target_role")),
        "next_step": _text(raw.get("next_step")),
        "rejected_products": rejected_products,
        "dropped_proofs": dropped_proofs,
    }


# Words that say nothing about which challenge this is. Without these removed,
# two unrelated pillars look similar simply because both are about this account.
_STOPWORDS = {
    "astra", "account", "company", "business", "technology", "technologies",
    "solutions", "solution", "needs", "need", "focus", "across", "within",
    "their", "these", "those", "which", "where", "there", "indicates",
    "indicating", "suggests", "suggesting", "highlights", "requires", "using",
    "through", "including", "various", "diverse", "multiple", "several",
}


def _content_words(text) -> set:
    """The words that distinguish one challenge from another."""
    return {w for w in re.findall(r"[a-z]{4,}", str(text or "").lower())
            if w not in _STOPWORDS}


def _distinct(pillars: list) -> tuple:
    """Merge pillars repeating the same challenge and solution.

    ABX: "if two pillars repeat the same challenge and solution, merge them
    into one pillar and keep the strongest supporting evidence."
    """
    kept, merged = [], []
    for pillar in pillars:
        # Compared on the one-line challenge, not the full paragraph. Once the
        # body grew to several hundred words, any two pillars shared far more
        # than three long words - "astra", "security", "technology" - and almost
        # every pillar names the same two HP lines, so the old rule merged
        # genuinely distinct pillars and quietly cut five down to three.
        signature = (
            frozenset(pillar["hp_solutions"]),
            frozenset(_content_words(pillar.get("challenge_headline")
                                     or pillar["challenge"])),
        )
        match = None
        for existing in kept:
            same_products = signature[0] and signature[0] == existing["_signature"][0]
            if not same_products:
                continue
            a, b = signature[1], existing["_signature"][1]
            union = a | b
            # Jaccard over the headline's content words: the two challenges have
            # to be substantially the SAME statement, not merely both about this
            # account's technology.
            if union and len(a & b) / len(union) >= 0.5:
                match = existing
                break
        if match:
            # Keep whichever has more verified evidence behind it.
            if len(pillar["challenge_evidence"]) > len(match["challenge_evidence"]):
                match.update({k: v for k, v in pillar.items() if k != "_signature"})
            for proof in pillar["proof_points"]:
                if proof["proof"] not in {p["proof"] for p in match["proof_points"]}:
                    match["proof_points"].append(proof)
            merged.append(pillar["pillar_title"])
            continue
        pillar["_signature"] = signature
        kept.append(pillar)

    for pillar in kept:
        pillar.pop("_signature", None)
    return kept, merged


def _dedupe_proof(pillars: list) -> list:
    """Step 6 - a proof point may appear in only one pillar.

    ABX: "remove duplicate proof points appearing across multiple pillars unless
    each use is clearly different", and "detect repeated HP products/proof
    across pillars and consolidate". Without this the same HP fact lands in
    three pillars and the message house reads as one claim restated, which is
    exactly what a message house is supposed to prevent.

    The proof stays with the pillar that has the fewest alternatives, so a
    pillar is never stripped of its only support to spare a richer one.
    """
    seen = {}
    order = sorted(range(len(pillars)), key=lambda i: len(pillars[i]["proof_points"]))

    for i in order:
        pillar = pillars[i]
        surviving, shared = [], []
        for proof in pillar["proof_points"]:
            key = frozenset(s["evidence_id"] for s in proof["sources"]) or \
                frozenset([proof["proof"].lower()[:120]])
            if key in seen:
                pillar.setdefault("proof_shared_with", []).append(seen[key])
                shared.append(proof)
                continue
            seen[key] = pillar["pillar_title"]
            surviving.append(proof)

        # Dedupe must not strip a pillar bare. ABX requires proof points per
        # pillar and separately forbids gratuitous repetition; when those pull
        # against each other, the pillar keeps one proof, flagged as shared,
        # rather than being published with nothing behind its HP claim.
        if not surviving and shared:
            reused = dict(shared[0])
            reused["shared"] = True
            surviving = [reused]

        pillar["proof_points"] = surviving

    return pillars


# ---------------------------------------------------------------------------
# Step 5: the umbrella message - the one [VLLM] step
# ---------------------------------------------------------------------------

UMBRELLA_SYSTEM = """You write one umbrella message for an account's message house.

You are given the finished messaging pillars. Write the single sentence that
sits above them.

Rules that are checked in code after you answer:
1. Introduce NO fact that is not already in the pillars below. The umbrella
   summarises them; it does not add to them.
2. No numbers, percentages or dates unless they already appear in a pillar.
3. Name only HP lines that a pillar already names. Fewer is better.
4. One or two sentences. No superlatives.

Return JSON: {"umbrella_message": "<one or two sentences>"}"""


def _validate_derived(text: str, pillars: list, restrictions: dict,
                      label: str = "text") -> tuple:
    """(text, faults). Nothing derived from the pillars may add to them.

    Applies to every generated string in the message house - the umbrella, the
    vector bullets, the Why-HP descriptions, the one-line summaries - not just
    the umbrella it started as. All of them are summaries of the same finished
    pillars, so all of them are checkable the same way: an HP line the pillars
    never named, a figure they never carried, or a superlative in a market that
    forbids one.
    """
    faults = []
    if not text:
        return "", ["the model returned no %s" % label]

    named = {p for pillar in pillars for p in pillar["hp_solutions"]}
    line = normalize_hp_product(text)
    if line and line not in named:
        faults.append("names %s, which no pillar names" % line)

    pillar_blob = " ".join(
        [p["challenge"] for p in pillars]
        + [p.get("challenge_headline", "") for p in pillars]
        + [p["hp_benefit"] for p in pillars]
        + [pr["proof"] for p in pillars for pr in p["proof_points"]])
    pillar_numbers = set(re.findall(r"\d[\d,\.]*", pillar_blob))
    for number in set(re.findall(r"\d[\d,\.]*", text)):
        if len(number.replace(",", "").replace(".", "")) >= 2 \
                and number not in pillar_numbers:
            faults.append("introduces the figure %s, which no pillar carries" % number)

    if restrictions.get("superlatives_blocked") and re.search(
            r"world'?s most|industry[- ]leading|best[- ]in[- ]class|most secure|"
            r"unmatched|number one|#1", text, re.I):
        faults.append("carries a superlative, which is not permitted in %s"
                      % restrictions["country"].title())

    return text, faults


def _umbrella(pillars: list, company: str, restrictions: dict) -> tuple:
    user = "\n".join([
        "ACCOUNT: %s" % company,
        "",
        "THE PILLARS:",
        "\n".join("  %d. %s - challenge: %s | HP: %s"
                  % (i, p["pillar_title"], p["challenge"][:200],
                     "; ".join(p["hp_solutions"]) or "no product named")
                  for i, p in enumerate(pillars, 1)),
        "",
        ("Superlative claims are not permitted in %s."
         % restrictions["country"].title()) if restrictions["superlatives_blocked"] else "",
        "",
        "Return JSON only.",
    ])
    raw = generate_gpt4o_json_completion(UMBRELLA_SYSTEM, user) or {}
    text, faults = _validate_derived(_text(raw.get("umbrella_message")),
                                     pillars, restrictions, "umbrella message")
    if faults:
        logger.warning("content_messaging: umbrella rejected (%s) - retrying once",
                       "; ".join(faults))
        correction = user + "\n\nYour previous answer was rejected:\n" + \
            "\n".join("  - %s" % f for f in faults)
        retry = generate_gpt4o_json_completion(UMBRELLA_SYSTEM, correction) or {}
        text, faults = _validate_derived(_text(retry.get("umbrella_message")),
                                         pillars, restrictions, "umbrella message")

    if faults:
        # The pillars are verified and publishable on their own; an umbrella
        # that keeps adding unsupported material is withheld rather than shown.
        logger.warning("content_messaging: publishing without an umbrella - %s",
                       "; ".join(faults))
        return "", faults
    return text, []


# ---------------------------------------------------------------------------
# The framing - everything the message house shows above and below the pillars
# ---------------------------------------------------------------------------
#
# One call, not four. The headline, the vector bullets, the Why-HP items and the
# one-line summaries are all derived from the same finished pillars; splitting
# them would pay four times to send the same context.
#
# It runs AFTER the pillars are final, so it can only summarise what already
# survived validation. Every string it returns goes through `_validate_derived`
# individually, and failure is per field: a bad vector is dropped, a bad summary
# falls back to the paragraph's first sentence, and the pillars are never at
# risk from any of it.

FRAMING_SYSTEM = """You write the framing around an account's message house.

You are given the finished messaging pillars. Everything you write must be a
summary of them - you are not adding to them.

Rules that are checked in code after you answer:
1. Introduce NO fact, number, percentage or date that is not already in a
   pillar. Anything you add is dropped.
2. Name only HP lines that a pillar already names.
3. No superlatives.
4. Keep every line short. A vector label is 4-8 words. A summary is ONE line.
5. "why_hp" gives 2-3 REASONS HP suits this account across the pillars as a
   whole - what is true of HP that no single pillar says on its own, such as
   covering the whole estate with one partner, or security that is part of the
   hardware. It is NOT a list of products: "Z by HP Workstations" is a product,
   "One partner across the full estate" is a reason. Each reason must still be
   supported by what the pillars say.

Return JSON:
{
  "umbrella_headline": "<one sentence: what this account is doing, in its own terms>",
  "umbrella_lead": "<one short line introducing the list, ending with a colon>",
  "vectors": [{"label": "<4-8 words: the hardware trigger>", "pillar_title": "<the pillar it comes from>"}],
  "why_hp": [{"title": "<3-6 words: a REASON, not a product name>", "description": "<one sentence>"}],
  "pillar_summaries": [{"pillar_title": "<exact title>",
                        "challenge_summary": "<one line>",
                        "benefit_summary": "<one line>"}]
}"""


def _first_sentence(text: str, limit: int = 160) -> str:
    """Fallback summary - the paragraph's own opening, never invented."""
    body = _text(text)
    if not body:
        return ""
    cut = re.split(r"(?<=[.!?])\s+", body)[0]
    return cut if len(cut) <= limit else cut[:limit].rsplit(" ", 1)[0] + "…"


def _framing(pillars: list, company: str, restrictions: dict) -> dict:
    """Headline, vectors, Why-HP items and per-pillar summaries.

    Returns what survived validation. Nothing here can fail the message house;
    the worst case is that the layout falls back to the pillars' own text.
    """
    titles = [p["pillar_title"] for p in pillars]
    user = "\n".join([
        "ACCOUNT: %s" % company,
        "",
        "THE FINISHED PILLARS:",
        "\n".join(
            "  %d. %s\n     challenge: %s\n     benefit: %s\n     HP: %s"
            % (i, p["pillar_title"], p["challenge"][:300], p["hp_benefit"][:300],
               "; ".join(p["hp_solutions"]) or "none named")
            for i, p in enumerate(pillars, 1)),
        "",
        "Write one vector per pillar, and one summary per pillar.",
        ("Superlative claims are not permitted in %s."
         % restrictions["country"].title()) if restrictions["superlatives_blocked"] else "",
        "",
        "Return JSON only.",
    ])

    raw = generate_gpt4o_json_completion(FRAMING_SYSTEM, user) or {}
    dropped = []

    def keep(value, label):
        text, faults = _validate_derived(_text(value), pillars, restrictions, label)
        if faults:
            dropped.append({"field": label, "text": _text(value)[:120],
                            "reasons": faults})
            return ""
        return text

    headline = keep(raw.get("umbrella_headline"), "umbrella headline")
    lead = keep(raw.get("umbrella_lead"), "umbrella lead")

    vectors = []
    for item in (raw.get("vectors") or []):
        if not isinstance(item, dict):
            continue
        label = keep(item.get("label"), "vector")
        if not label:
            continue
        # The pillar it points at must be one that actually exists, so a vector
        # can never advertise a pillar the seller cannot find below it.
        pillar_title = _text(item.get("pillar_title"))
        vectors.append({"label": label,
                        "pillar_title": pillar_title if pillar_title in titles else None})

    why_hp_items = []
    for item in (raw.get("why_hp") or []):
        if not isinstance(item, dict):
            continue
        title = keep(item.get("title"), "why-hp title")
        description = keep(item.get("description"), "why-hp description")
        if title and description:
            why_hp_items.append({"title": title, "description": description})

    summaries = {}
    for item in (raw.get("pillar_summaries") or []):
        if not isinstance(item, dict):
            continue
        title = _text(item.get("pillar_title"))
        if title not in titles:
            continue
        summaries[title] = {
            "challenge_summary": keep(item.get("challenge_summary"), "challenge summary"),
            "benefit_summary": keep(item.get("benefit_summary"), "benefit summary"),
        }

    # Attach summaries, falling back to the challenge's own retrieved headline
    # or each paragraph's first sentence, so a table cell is never empty and
    # never invented.
    for pillar in pillars:
        got = summaries.get(pillar["pillar_title"]) or {}
        pillar["challenge_summary"] = got.get("challenge_summary") \
            or pillar.get("challenge_headline") \
            or _first_sentence(pillar["challenge"])
        pillar["benefit_summary"] = got.get("benefit_summary") \
            or _first_sentence(pillar["hp_benefit"])

    return {
        "umbrella_headline": headline,
        "umbrella_lead": lead,
        "vectors": vectors,
        "why_hp_items": why_hp_items,
        "framing_dropped": dropped,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_messaging_pillars(account_id: str, mode: str | None = None) -> dict:
    """Build the message house. Returns the stored widget document."""
    db = get_db()
    now = datetime.now(UTC)

    state = index_state.get(account_id, INDEX)
    if state.get("status") not in (index_state.READY, index_state.STALE):
        raise PillarError(
            "the Content Messaging index is %s - %s"
            % (state.get("status"), state.get("last_error") or "build it first"))

    company = _text((db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "messaging_context_card"}) or {}
    ).get("data", {}).get("company_name"))

    candidates, retrieval = asyncio.run(_candidate_challenges(account_id, mode))
    challenges, dropped, invalid_count = _resolve_challenges(account_id, candidates)
    if not challenges:
        raise PillarError(
            "no account challenge survived evidence validation (%d candidate(s), "
            "%d unresolvable evidence id(s))" % (len(candidates), invalid_count))

    hp_facts, _hp_ids = _hp_fact_block(db, account_id)
    account_facts = _account_evidence_block(db, account_id)
    restrictions = _restrictions(db, account_id)

    pillars = []
    for challenge in challenges[:MAX_PILLARS + 2]:
        pillar = _build_pillar(account_id, challenge, hp_facts,
                               account_facts, restrictions)
        if pillar:
            pillars.append(pillar)
        if len(pillars) >= MAX_PILLARS + 2:
            break

    pillars, merged = _distinct(pillars)
    pillars = pillars[:MAX_PILLARS]
    pillars = _dedupe_proof(pillars)

    # ABX: drop a weak pillar rather than pad the message house with generic
    # copy. Checked AFTER proof dedupe, so a pillar left with nothing but a
    # repeated proof is dropped rather than published on borrowed support.
    pillars = [p for p in pillars if p["hp_solutions"] and
               (p["proof_points"] or p["challenge_evidence"])]

    if not pillars:
        raise PillarError("no pillar survived validation - nothing is published "
                          "rather than publishing generic copy")

    plays = ((db["account_widgets"].find_one(
        {"account_id": account_id,
         "widget_key": "opportunity_narrative_plays"}) or {}).get("data")
        or {}).get("opportunity_plays") or []

    for pillar in pillars:
        pillar["sourced"] = _sourced_count(pillar)
        resource = _hp_resource(pillar, plays)
        if resource:
            pillar["hp_resource"] = resource

    umbrella, umbrella_faults = _umbrella(pillars, company, restrictions)
    framing = _framing(pillars, company, restrictions)

    payload = {
        "account_id": account_id,
        "feature_key": "content_messaging",
        "widget_key": WIDGET_KEY,
        "data_classification": "inferred",
        "status": "available",
        "data": {
            "umbrella_message": umbrella,
            "umbrella_withheld": umbrella_faults,
            "umbrella_headline": framing["umbrella_headline"],
            "umbrella_lead": framing["umbrella_lead"],
            "vectors": framing["vectors"],
            "why_hp_items": framing["why_hp_items"],
            "pillars": pillars,
            "pillar_count": len(pillars),
            "why_hp": [p["hp_benefit"] for p in pillars],
            "generation": {
                "prompt_version": PROMPT_VERSION,
                "retrieval_mode": retrieval.mode,
                "index_workspace": retrieval.workspace,
                "index_stale": retrieval.stale,
                "candidates_returned": len(candidates),
                "challenges_kept": len(challenges),
                "dropped_challenges": dropped,
                "merged_pillars": merged,
                "invalid_evidence_count": invalid_count
                + sum(len(p.get("dropped_proofs") or []) for p in pillars),
                "restrictions": restrictions,
                "framing_dropped": framing["framing_dropped"],
            },
        },
        "source_datasets": ["firmographics", "technographics", "intent_score",
                            "google_news", "news_events"],
        "extracted_at": now,
        "updated_at": now,
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": WIDGET_KEY},
        {"$set": payload}, upsert=True)
    logger.info("content_messaging: published %d pillar(s) for account %s",
                len(pillars), account_id)
    return payload
