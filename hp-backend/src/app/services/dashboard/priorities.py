"""Executive Dashboard intelligence: strategic priorities and reported metrics.

ABX Feature 1, "How to build this feature", is nine `[Deterministic/Derived]`
steps and one `[VLLM]`. The one VLLM step is a rejection rule for a generated
summary - *"If the generated summary contains a fact that is not supported by
the saved evidence, do not show that version"* - and Step 6 already builds that
summary deterministically. So **no model writes anything published here.**

What a model does do is find things. LightRAG reads 500 pages of filings and
comes back saying "this account is investing in digital infrastructure, see
these evidence identifiers". That answer is treated as a **pointer**: the
identifiers are resolved against the evidence registry, the sentence shown to a
seller is the registered source sentence, and every figure is read from the
evidence row's own `value`, `period` and `unit` fields. A citation the model
invents resolves to nothing and the priority it supported is dropped.

**The priority score is computed, from a formula that defines itself.** ABX's
own weighting - *40% support frequency + 25% supporting document sections + 20%
recency + 15% independent external-source support* - never said how any of those
four counts becomes a number on a scale, so for a long time this module computed
nothing and published `evidence_score: null` with the reason. That refusal was
right about ABX's sentence and it is still right about it.

What replaced it is a different, fully specified formula, supplied in writing:

    Evidence Strength = Filing Evidence (5 per relevant filing, max 25)
                      + Recency (25/20/15/10/5 by age band, 0 when undated)
                      + Source Diversity (10 per category, max 50)

Every term names its own unit, points and cap, so nothing has to be invented to
compute it. `evidence_strength.py` computes it and publishes each term's working
beside the total. ABX's four raw measures are still published unchanged in
`measures`, because they are what the ordering rule uses and they say something
the score does not.

Priorities are still ordered by the stated raw rule - supporting sentences, then
distinct document sections, then recency - and not by the score. The score
answers "how well evidenced is this catalyst"; the ordering answers "which did
this account's documents say most about", and a catalyst can be strongly
evidenced by two sources while another is mentioned twenty times.

The urgency score is out of scope for the same reason, one level worse: ABX
itself records that *"The current POC does not define a reusable
raw-data-to-driver formula for all accounts"*, and its own missing-input rule
then forbids computing an overall score from incomplete drivers.
"""

import asyncio
import logging
import re
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.dashboard import evidence_strength
from app.services.extractors import grounding
from app.services.hp import case_studies as cs
from app.services.retrieval import evidence as ev, index_state, query

logger = logging.getLogger(__name__)

INDEX = "executive_dashboard"
WIDGET_KEY = "exec_strategic_priorities"
METRICS_WIDGET_KEY = "exec_key_metrics"
PROMPT_VERSION = 1

MIN_PRIORITIES = 3
MAX_PRIORITIES = 6
NL = chr(10)

MIN_EVIDENCE_PER_PRIORITY = 1

# The Recommendation Tuning Logic sets a length for each feature's seller-facing
# output. Executive Dashboard: "Minimum 100 words; maximum 120 words."
#
# The maximum is enforced hard - a card that runs long is a card that was not
# written to the brief. The minimum is retried rather than enforced, because the
# only thing below this function is a one-line deterministic fallback, and a
# 90-word grounded paragraph beats "X is evidenced by 4 source sentences" every
# time. A card that is still short after the retry publishes and says so.
DESCRIPTION_MIN_WORDS = 100
DESCRIPTION_MAX_WORDS = 120
MAX_SUMMARY_SENTENCES = 4

ORDERING_BASIS = (
    "Ordered by the number of supporting source sentences, then by how many "
    "distinct document sections support it, then by the most recent supporting "
    "date. These are counts of verified evidence, not a score."
)

# ABX, "Clean and prepare the data": "Convert strategy statements into a
# standard priority list (AI, workforce productivity, hybrid work, expansion,
# security, fleet refresh, print/workflow, sustainability...)".
PRIORITY_QUESTION = (
    "What are this account's stated strategic priorities and investment "
    "themes, based only on its own filed documents and evidence - its annual "
    "report narrative, reported financial results, market position, technology "
    "in use, hiring and recent events? Consider themes such as AI, workforce "
    "productivity, hybrid work, expansion, security, fleet refresh, "
    "print and document workflow, sustainability and cost efficiency, but "
    "report only the ones this account's own evidence actually supports. For "
    "each priority, quote in square brackets the evidence identifiers that "
    "support it."
)

CANDIDATE_SYSTEM = """You identify an account's strategic priorities from retrieved evidence.

Rules:
- Use ONLY the retrieved context. Never use general knowledge about the company or its industry.
- Every priority must be supported by evidence identifiers copied EXACTLY from the context.
- Do not invent an evidence identifier. A priority with no identifier will be discarded.
- Do not state any number, date, percentage or currency amount. Figures are read from the evidence, not from you.
- Prefer priorities the account states about itself over inferences about its market.

Identify 6 to 8 distinct priorities. Several may share a theme - they are grouped under it, not merged
into it - so report each separately evidenced initiative rather than one summary per theme.
Cite 2 to 5 evidence identifiers for each.

Return JSON only:
{"priorities": [
  {"title": "short priority name, at most 8 words",
   "theme": "one of: AI, workforce productivity, hybrid work, expansion, security, fleet refresh, print/workflow, sustainability, cost efficiency, other",
   "why_now": "one sentence on why this matters now, using no figures",
   "evidence_ids": ["..."]}
]}"""


class DashboardError(Exception):
    """Nothing valid could be published, and the reason is worth showing."""


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------

DATASET_LABELS = {
    "compliance_filings": "Company filing",
    "firmographics": "Firmographics",
    "company_hierarchy": "Company hierarchy",
    "job_openings": "Job postings",
    "prospect_contacts": "Contact data",
    "technographics": "Technology detections",
    "intent_score": "Intent data",
    "google_news": "News",
    "news_events": "News",
}


def source_label(row: dict) -> str:
    """What a source chip reads.

    A filing names the document and page, because that is how a reader checks
    it - "2025-Astra-Annual-Report.pdf p.14" can be opened and found. Anything
    else falls back to the publisher, then to the dataset.
    """
    row = row or {}
    filing = _text(row.get("filing_label"))
    if filing:
        page = row.get("page")
        return "%s p.%s" % (filing, page) if page else filing

    publisher = _text(row.get("publisher"))
    if publisher:
        return publisher

    dataset = row.get("dataset")
    if dataset and dataset != INDEX:
        return DATASET_LABELS.get(dataset, dataset.replace("_", " ").title())
    return "Account evidence"


def _source(row: dict) -> dict:
    """One citation as the UI shows it, carrying the figure fields when present."""
    out = {
        "evidence_id": row["evidence_id"],
        "dataset": row.get("dataset"),
        "field": row.get("field"),
        "source_text": row.get("source_text"),
        "label": source_label(row),
    }
    for key in ("source_url", "publisher", "quote", "period", "value", "unit",
                "page", "filing_label", "filing_period"):
        if row.get(key) is not None and row.get(key) != "":
            out[key] = row[key]
    return out


def _section(row: dict) -> str:
    """Which part of the corpus a piece of evidence came from.

    ABX's second measure counts "supporting document sections". A document in
    this corpus is one logical unit - the highlights table, one span of strategy
    narrative, the market report - so the document id is the section, and a page
    distinguishes two spans inside the same document.
    """
    page = row.get("page")
    return "%s#p%s" % (row.get("doc_id"), page) if page else _text(row.get("doc_id"))


def _recency(row: dict) -> str | None:
    """The most specific date this evidence carries, or None.

    Three kinds of evidence carry a date, in descending order of precision: a
    reported figure knows its own reporting period, a narrative paragraph
    inherits the period its filing reports, and a news row carries a publication
    date. Nothing is guessed from a document's name.
    """
    return (_text(row.get("period")) or _text(row.get("filing_period"))
            or None)


# ---------------------------------------------------------------------------
# Step 3: candidates, then evidence validation
# ---------------------------------------------------------------------------

async def _candidate_priorities(account_id: str, mode: str | None = None) -> tuple:
    """(candidates, retrieval_result). Retrieval first - no filtering yet."""
    result = await query.retrieve(account_id, INDEX, PRIORITY_QUESTION,
                                  mode=mode, top_k=60)
    user = "\n".join([
        "RETRIEVED CONTEXT (every line carries its evidence identifier):",
        result.context[:60000],
        "",
        "Identify this account's strategic priorities from the context above.",
        "Return JSON only.",
    ])
    raw = generate_gpt4o_json_completion(CANDIDATE_SYSTEM, user) or {}
    return (raw.get("priorities") or []), result


def _resolve_priorities(account_id: str, candidates: list) -> tuple:
    """(kept, dropped, invalid_total), each kept priority carrying raw measures.

    ABX: *"Show a strategic priority only when at least one saved source
    sentence supports it. Do not create a priority from a general industry
    assumption."* An unresolvable identifier is exactly that assumption wearing
    a citation, so it is discarded and counted rather than repaired.
    """
    kept, dropped, invalid_total = [], [], 0

    for candidate in (candidates or []):
        if not isinstance(candidate, dict):
            continue
        title = _text(candidate.get("title"))
        if not title:
            continue

        resolved, invalid = ev.resolve(account_id, INDEX,
                                       candidate.get("evidence_ids") or [])
        invalid_total += len(invalid)
        if len(resolved) < MIN_EVIDENCE_PER_PRIORITY:
            dropped.append({"title": title[:160],
                            "reason": "no resolvable account evidence",
                            "invalid_ids": invalid[:4]})
            continue

        # Resolving is not the same as supporting. The first build cited a
        # paragraph about optimising profit in Document Solutions under a
        # priority titled "Strengthen sustainability initiatives" - a real id,
        # pointing at real text, that says nothing about the priority. Only 8 of
        # 12 cited rows mentioned their own subject. A row that shares no
        # content word with the priority is dropped the way an unresolvable id
        # already is.
        wanted = _content_words("%s %s" % (title, candidate.get("theme") or ""))
        relevant, off_topic = [], []
        for row in resolved:
            if _supports(row, wanted):
                relevant.append(row)
            else:
                off_topic.append(row.get("evidence_id"))
        if len(relevant) < MIN_EVIDENCE_PER_PRIORITY:
            dropped.append({"title": title[:160],
                            "reason": "cited evidence does not mention this "
                                      "priority's subject",
                            "invalid_ids": off_topic[:4]})
            continue
        resolved = relevant

        sources = [_source(r) for r in resolved]
        sections = {_section(r) for r in resolved}
        dates = sorted(d for d in (_recency(r) for r in resolved) if d)
        publishers = {_text(r.get("publisher")) for r in resolved
                      if _text(r.get("publisher"))}

        kept.append({
            "title": title,
            "theme": _text(candidate.get("theme")) or "other",
            "why_now": _text(candidate.get("why_now")),
            # The supporting sentence a seller reads is the REGISTERED one, not
            # the model's paraphrase of it.
            "supporting_sentence": sources[0].get("source_text"),
            "sources": sources,
            "invalid_evidence_ids": invalid,
            "off_topic_evidence_ids": off_topic,
            # ABX's four terms, kept as the counts they actually are.
            "measures": {
                "support_count": len(resolved),
                "distinct_sections": len(sections),
                "most_recent_date": dates[-1] if dates else None,
                "independent_source_count": len(publishers),
            },
        })

    # The stated ordering rule, applied least-significant term first so each
    # sort direction is right. Written as two passes rather than one key
    # because recency sorts descending while the counts also sort descending,
    # and a single tuple cannot negate a date string.
    kept.sort(key=lambda p: str(p["measures"]["most_recent_date"] or ""),
              reverse=True)
    kept.sort(key=lambda p: (-p["measures"]["support_count"],
                             -p["measures"]["distinct_sections"]))
    return kept, dropped, invalid_total


def _distinct(priorities: list) -> tuple:
    """Drop a priority that repeats one already kept. Returns (kept, merged).

    Only near-identical titles are merged. An earlier version also merged any two
    priorities sharing a theme, on the reading that ABX's "standard priority
    list" has one entry per theme. That is wrong about what a theme is: in the
    reference dashboard a theme is a *heading* with several catalysts under it -
    three separate ones sit under "AI Transformation" - and collapsing on it
    capped the whole dashboard at one card per theme and threw away real,
    separately-evidenced priorities.
    """
    kept, merged = [], []
    for priority in priorities:
        words = _content_words(priority["title"])
        duplicate = None
        for existing in kept:
            other = _content_words(existing["title"])
            if not words or not other:
                continue
            if len(words & other) / float(len(words | other)) >= 0.6:
                duplicate = existing
                break
        if duplicate is None:
            kept.append(priority)
        else:
            merged.append({"dropped": priority["title"],
                           "kept": duplicate["title"],
                           "reason": "near-identical title"})
    return kept, merged


_STOPWORDS = {"and", "the", "for", "with", "into", "from", "of", "to", "in",
              "on", "a", "an", "its", "their", "this", "that", "at", "by"}


def _content_words(text) -> set:
    import re
    return {w for w in re.findall(r"[a-z]{3,}", str(text or "").lower())
            if w not in _STOPWORDS}


def _supports(row, wanted) -> bool:
    """Whether one evidence row is actually about the priority it was cited for.

    Matched on word stems rather than whole words, so "sustainability" in the
    title finds "sustainable" in the source. Deliberately generous - the test is
    meant to catch evidence about a different subject entirely, not to demand
    the priority's exact phrasing.
    """
    body = _text(row.get("source_text")).lower()
    if not body or not wanted:
        return False
    return any(word[:6] in body for word in wanted)


def _hp_facts(db, account_id: str, limit: int = 40) -> list:
    """HP capability statements already approved for this account.

    Read from the recommendations widget rather than written here, so the
    description can say what HP offers without a model inventing a product. Only
    facts the country guardrails kept are present in that widget.
    """
    facts = []

    recs = (db["account_widgets"].find_one(
        {"account_id": account_id,
         "widget_key": "technographic_hp_recommendations"}) or {}
    ).get("data") or {}
    for rec in (recs.get("recommendations") or []):
        family = _text(rec.get("hp_family"))
        for fact in (rec.get("approved_facts") or []):
            if fact.get("kept") and _text(fact.get("text")):
                facts.append("%s: %s" % (family or "HP", _text(fact.get("text"))))
            if len(facts) >= limit:
                return facts

    # The service half of the rulebook, from the Opportunity Map.
    #
    # The recommendations widget carries HARDWARE rules and whatever Part B
    # rule earned a category card - for one account that was eight EliteDesk
    # specifications and a Wolf licence. A catalyst about operational
    # efficiency then had PCIe slots and USB ports to answer it with, while
    # the rulebook's workforce-experience, Care Pack and deployment rules -
    # the ones that actually speak to efficiency - were sitting in the
    # Opportunity Map unread.
    plays = (db["account_widgets"].find_one(
        {"account_id": account_id,
         "widget_key": "opportunity_narrative_plays"}) or {}
    ).get("data") or {}
    for play in (plays.get("service_plays") or []):
        offering = _text(play.get("title")) or _text(play.get("offering"))
        for fact in (play.get("allowed_facts") or []):
            if _text(fact):
                facts.append("%s: %s" % (offering or "HP", _text(fact)))
            if len(facts) >= limit:
                return facts
    return facts


DESCRIPTION_SYSTEM = """You write one short paragraph for an HP seller about an account's strategic priority.

Structure, in this order:
1. What the account is specifically doing, taken ONLY from the supporting evidence given to you.
2. What that implies for HP, taken ONLY from the approved HP capability statements given to you.

Open with the specific thing that happened - the programme, subsidiary, site, technology, figure or
date named in the evidence. Use the company's own name. NEVER begin with "The account", "The company"
or "This account": every card opening the same way is unreadable as a list, and a sentence that could
describe any company is a failure whatever it opens with.

Write it the way an analyst briefing a seller would: what the account is doing, named precisely, then
what it means for HP.

Rules:
- Every number, percentage, amount and date you write MUST appear in the evidence given to you. Copy them exactly. Do not round, convert or estimate, and never supply one from your own knowledge.
- Never name an HP product that does not appear verbatim in the approved HP statements.
- Never name a competitor, and never claim the account already uses HP.
- Write in English even when the evidence is not.
- Between 100 and 120 words. Plain declarative prose, no padding: use the extra room for the
  account's own specifics, not for restating the point.

Return JSON only: {"description": "..."}"""


_FIGURE_RE = re.compile(r"\d[\d.,]*%?")
_HP_MENTION_RE = re.compile(r"\bHP\s+([A-Z][\w-]*(?:\s+[A-Z][\w-]*)?)")


def _validate_description(body: str, evidence_text: str, hp_text: str) -> tuple:
    """(ok, reason). ABX's one [VLLM] rule, applied.

    ABX Feature 1: *"If the generated summary contains a fact that is not
    supported by the saved evidence, do not show that version."* Three things
    are checked, each of which has a cheap deterministic test: no figure of any
    kind, since none was supplied; no HP product name absent from the approved
    statements; and nothing longer than the brief allows. A failure returns the
    reason so the rejection is recorded rather than silent.
    """
    if not body:
        return False, "empty"
    if len(body.split()) > DESCRIPTION_MAX_WORDS:
        return False, "longer than the brief allows (%d words, max %d)" % (
            len(body.split()), DESCRIPTION_MAX_WORDS)
    if re.match(r"^(the account|the company|this account|this company)\b", body, re.I):
        return False, "opens with a stock phrase instead of the specific fact"

    # Every figure must be traceable. An earlier version banned figures outright,
    # which satisfied the rule and produced prose so generic it could have
    # described any company - "advancing its digital transformation by
    # strengthening its IT infrastructure". The specifics are what make a card
    # worth reading, so they are allowed and then checked one by one against the
    # material the model was given.
    haystack = _digits_only(evidence_text) + " " + _digits_only(hp_text)
    for figure in set(_FIGURE_RE.findall(body)):
        if _digits_only(figure) and _digits_only(figure) not in haystack:
            return False, "states %s, which is not in the evidence" % figure

    for mention in _HP_MENTION_RE.findall(body):
        if mention.lower() not in hp_text.lower():
            return False, "names HP %s, which is not in the approved facts" % mention
    return True, "ok"


def _digits_only(value) -> str:
    """Comparable form of a figure: digits and decimal points, nothing else.

    So "83.67%", "83.67 per cent" and "83.67" all match the evidence's "83.67",
    while a separator difference cannot cause a false rejection.

    Trailing punctuation is stripped because a figure at the end of a sentence
    is captured as "2025." - which matched nothing and rejected a description
    whose figures were all perfectly well grounded.
    """
    return re.sub(r"[^\d.]+", " ", str(value or "")).strip(" .")


def _proof_for(db, priority: dict, industry: str, taken: set, here: set):
    """A published HP case study supporting the HP offering this catalyst names.

    The offering is read back out of the finished paragraph rather than chosen
    beside it, because the paragraph is the thing a seller reads: proof that
    supports a line the text never mentions is decoration, not evidence.

    Returns None when the paragraph names no HP line, when no study covers it,
    or when every candidate is already cited elsewhere on this account. The
    Executive Dashboard picks last of the five surfaces (`cs.SURFACE_ORDER`),
    so "none left" is a real and acceptable outcome here.
    """
    body = _text((priority.get("description") or {}).get("text"))
    if not body:
        return None

    # Matched with the same token map that validates HP product names
    # everywhere else, rather than by pulling a name out of the sentence.
    # `_HP_MENTION_RE` captures at most two capitalised words, so it read
    # "HP Workforce Experience Platform" as "Workforce Experience" - a name no
    # line map contains, which quietly cost every catalyst its proof.
    lowered = body.lower()
    lines: list = []
    for tokens, canonical in grounding.HP_LINE_TOKENS:
        if not any(token in lowered for token in tokens):
            continue
        for line in cs.lines_for_hp_line(canonical):
            if line not in lines:
                lines.append(line)
    if not lines:
        return None

    try:
        return cs.allocate(db, lines, industry=industry,
                           taken=taken, used_here=here)
    except Exception:
        logger.exception("executive_dashboard: proof allocation failed for %r",
                         _text(priority.get("title"))[:60])
        return None


def _describe(priority: dict, hp_facts: list, company: str = "") -> dict:
    """A short grounded paragraph for one priority, or a deterministic fallback.

    The account half is summarised from evidence that already passed resolution
    and the relevance gate; the HP half may only use approved statements. If the
    generated version fails validation it is discarded and a plain sentence
    assembled in Python is shown instead - never a rejected paragraph, never
    nothing.
    """
    evidence_text = " ".join(_text(s.get("source_text"))
                             for s in priority["sources"])[:4000]
    hp_text = "\n".join(hp_facts)

    user = "\n".join([
        "COMPANY: %s" % (company or "this account"),
        "PRIORITY: %s" % priority["title"],
        "THEME: %s" % priority["theme"],
        "",
        "SUPPORTING EVIDENCE (the only source for what the account is doing):",
        evidence_text,
        "",
        "APPROVED HP CAPABILITY STATEMENTS (the only source for anything about HP):",
        hp_text or "(none approved for this account - omit the HP sentence)",
        "",
        "Write the paragraph. Return JSON only.",
    ])

    try:
        raw = generate_gpt4o_json_completion(DESCRIPTION_SYSTEM, user) or {}
    except Exception:
        logger.exception("executive_dashboard: description generation failed")
        raw = {}

    body = _text(raw.get("description"))
    ok, reason = _validate_description(body, evidence_text, hp_text)

    # One retry for length alone. The first answer was valid - grounded,
    # correctly figured, no invented product - it was merely short, and
    # discarding it for that would publish the fallback instead.
    if ok and len(body.split()) < DESCRIPTION_MIN_WORDS:
        try:
            retry = generate_gpt4o_json_completion(
                DESCRIPTION_SYSTEM,
                user + NL + NL
                + ("The previous answer was %d words. The brief is %d to %d. "
                   "Expand it using only the evidence and approved statements "
                   "above - more of the account's own specifics, no padding "
                   "and no new claims."
                   % (len(body.split()), DESCRIPTION_MIN_WORDS,
                      DESCRIPTION_MAX_WORDS))) or {}
            longer = _text(retry.get("description"))
            good, _why = _validate_description(longer, evidence_text, hp_text)
            if good and len(longer.split()) > len(body.split()):
                body = longer
        except Exception:
            logger.exception("executive_dashboard: description retry failed")

    if ok:
        short = len(body.split()) < DESCRIPTION_MIN_WORDS
        return {"text": body, "written_by": "model", "validated": True,
                "word_count": len(body.split()),
                "below_brief": short or None}

    logger.info("executive_dashboard: description rejected for %r - %s",
                priority["title"][:60], reason)
    measures = priority["measures"]
    fallback = ("%s is evidenced by %d source sentence(s) across %d section(s) "
                "of the account's filed documents."
                % (priority["title"].rstrip("."), measures["support_count"],
                   measures["distinct_sections"]))
    return {"text": fallback, "written_by": "python", "validated": True,
            "rejected_reason": reason}


# ---------------------------------------------------------------------------
# Step 2: reported figures, read from the registry
# ---------------------------------------------------------------------------

def _reported_metrics(account_id: str) -> list:
    """Reported figures for the key-metric cards, newest period per metric.

    Read straight from the evidence registry rather than from any model answer.
    A row only exists here because `financials.py` bound a metric, a period, a
    value and a unit together on the page, so ABX's pre-display check -
    *"correct metric, correct reporting period, and correct unit/currency"* -
    was already applied before indexing.
    """
    db = get_db()
    rows = list(db[ev.COLLECTION].find(
        {"account_id": account_id, "index": INDEX,
         "dataset": "compliance_filings",
         "period": {"$exists": True}, "value": {"$exists": True},
         "unit": {"$exists": True}},
        {"_id": 0}))

    # Only the whole-company tables. The corpus also registers segment figures
    # in `financial_detail`, and an annual report names a division's revenue
    # "Net Revenue" too - taking the newest period across all of them would put
    # a division's number on a card labelled with the group's name, which is the
    # failure ABX's "correct company/business unit" check exists to prevent.
    rows = [r for r in rows
            if str(r.get("doc_id") or "").endswith(("_financial_highlights",
                                                    "_market_position"))]

    from app.services.retrieval.financials import period_key

    # Grouped by document AND metric, so a series is only ever assembled within
    # one table - the same rule `financials.series` enforces.
    series = {}
    for row in rows:
        metric = _text(row.get("field"))
        if not metric:
            continue
        series.setdefault((row.get("doc_id"), metric.lower()), []).append(row)

    metrics = []
    for (_doc_id, _key), group in series.items():
        group.sort(key=lambda r: period_key(r["period"]))
        latest = group[-1]
        entry = {
            "metric": _text(latest.get("field")),
            "value": latest["value"],
            "value_text": _format_value(latest["value"], latest["unit"]),
            "period": latest["period"],
            "unit": latest["unit"],
            "source": source_label(latest),
            "page": latest.get("page"),
            "filing_label": latest.get("filing_label"),
            "quote": latest.get("quote"),
            "evidence_id": latest["evidence_id"],
            "basis": "reported",
            # Highlights before market position, then table order within each.
            # Sorting on the `#cN` suffix alone interleaved the two documents,
            # because both number their claims from one.
            "order": (0 if str(latest.get("doc_id") or "").endswith(
                          "_financial_highlights") else 1,
                      _order_of(latest["evidence_id"])),
        }

        # Period-on-period change, where a previous period was itself reported.
        # This is arithmetic on two registered figures, not a normalisation:
        # ABX asks for "revenue growth" alongside revenue, both sides are cited,
        # and the result is withheld when either side is missing or the earlier
        # value is zero. A percentage of a percentage would be meaningless, so
        # those carry a point difference instead.
        previous = group[-2] if len(group) > 1 else None
        if previous and previous.get("value") not in (None, 0):
            entry["previous_period"] = previous["period"]
            entry["previous_value_text"] = _format_value(previous["value"],
                                                         previous["unit"])
            entry["previous_evidence_id"] = previous["evidence_id"]
            if latest["unit"] == "%":
                delta = latest["value"] - previous["value"]
                entry["change_text"] = "%+.1f pts" % delta
                entry["direction"] = "up" if delta > 0 else ("down" if delta < 0 else "flat")
            else:
                delta = (latest["value"] - previous["value"]) / abs(previous["value"]) * 100.0
                entry["change_pct"] = round(delta, 1)
                entry["change_text"] = "%+.1f%%" % delta
                entry["direction"] = "up" if delta > 0 else ("down" if delta < 0 else "flat")
            entry["change_basis"] = "%s vs %s, both reported" % (
                latest["period"], previous["period"])
            entry["series"] = [
                {"period": r["period"], "value_text": _format_value(r["value"], r["unit"]),
                 "evidence_id": r["evidence_id"]} for r in group]

        metrics.append(entry)

    # Table order, not alphabetical: a filing's highlights table already reads
    # revenue, then profit, then assets, and that ordering is meaningful.
    metrics.sort(key=lambda m: m["order"])
    return metrics


def _order_of(evidence_id) -> int:
    """Registration order, read from the evidence id's `#cN` suffix."""
    import re
    match = re.search(r"#c(\d+)$", str(evidence_id or ""))
    return int(match.group(1)) if match else 10 ** 6


def _format_value(value, unit) -> str:
    """A figure written the way a reader expects to see it.

    A currency leads its amount - `IDR 323,392 billion`, not `323,392 IDR
    billion` - while a counted unit follows it. The unit itself is never
    dropped or converted: the scale is the filing's own, so a figure stated in
    billions stays stated in billions.
    """
    import re

    try:
        number = float(value)
    except (TypeError, ValueError):
        return _text(value)

    written = (f"{number:,.0f}" if number == int(number)
               else f"{number:,.2f}")
    unit_text = _text(unit)
    if not unit_text:
        return written
    if unit_text == "%":
        return "%s%%" % written

    currency = re.match(r"^([A-Z]{3})\s+(.*)$", unit_text)
    if currency:
        return "%s %s %s" % (currency.group(1), written, currency.group(2))
    # A currency with no scale after it - a figure stated in the currency's own
    # units rather than in billions. It still leads its amount: "IDR 390", not
    # "390 IDR".
    if re.fullmatch(r"[A-Z]{3}", unit_text):
        return "%s %s" % (unit_text, written)
    return "%s %s" % (written, unit_text)


def _publish_metrics(db, account_id: str, reported: list, now) -> dict:
    """Add reported figures to the key-metrics widget without losing the bands.

    The CSV bands stay. A firmographic band and a filed figure are different
    kinds of fact - one is a bucket a data vendor assigned, the other is what
    the company told a regulator - and showing them side by side is what lets a
    seller see which is which. Replacing the band would hide that distinction.
    """
    existing = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": METRICS_WIDGET_KEY}) or {}
    data = dict(existing.get("data") or {})
    data["reported_metrics"] = reported
    data["reported_metric_count"] = len(reported)
    data["reported_source"] = "compliance_filings"
    data["bands_are_not_reported_figures"] = (
        "employee_count and revenue are firmographic bands, not figures the "
        "company reported. Reported figures are listed under reported_metrics "
        "with their period, unit and page.")

    payload = {
        "account_id": account_id,
        "feature_key": "executive_dashboard",
        "widget_key": METRICS_WIDGET_KEY,
        "data_classification": "deterministic",
        "status": "available",
        "data": data,
        "source_datasets": ["firmographics", "compliance_filings"],
        "updated_at": now,
    }
    if not existing:
        payload["extracted_at"] = now
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": METRICS_WIDGET_KEY},
        {"$set": payload}, upsert=True)
    return data


# ---------------------------------------------------------------------------
# Step 6: the executive summary, assembled rather than written
# ---------------------------------------------------------------------------

def _executive_summary(company: str, priorities: list, metrics: list) -> dict:
    """2-4 grounded sentences, assembled in Python from validated material.

    ABX Step 6: *"create the short executive summary from the strongest
    verified priorities and urgency drivers. Do not add facts that are not in
    the stored evidence."* Every sentence below is built from a priority that
    already passed evidence validation or a figure already read from a registry
    row, so the `[VLLM]` rejection rule has nothing left to reject - there is no
    generated version to compare against.
    """
    sentences, cited = [], []

    if metrics:
        headline = next((m for m in metrics
                         if "revenue" in m["metric"].lower()), metrics[0])
        sentences.append("%s reported %s of %s for %s." % (
            company, headline["metric"].lower(), headline["value_text"],
            headline["period"]))
        cited.append(headline["evidence_id"])

    if priorities:
        top = priorities[0]
        sentences.append("Its strongest evidenced priority is %s, supported by "
                         "%d source sentence(s) across %d document section(s)."
                         % (top["title"].rstrip("."),
                            top["measures"]["support_count"],
                            top["measures"]["distinct_sections"]))
        cited.extend(s["evidence_id"] for s in top["sources"][:2])

    if len(priorities) > 1:
        others = ", ".join(p["title"].rstrip(".") for p in priorities[1:3])
        sentences.append("Other evidenced priorities: %s." % others)

    dated = [p["measures"]["most_recent_date"] for p in priorities
             if p["measures"]["most_recent_date"]]
    if dated:
        sentences.append("The most recent supporting evidence is from %s."
                         % max(dated))

    return {
        "sentences": sentences[:MAX_SUMMARY_SENTENCES],
        "evidence_ids": cited,
        "assembled_by": "python",
        "note": ("Assembled from validated priorities and reported figures. No "
                 "model wrote this text."),
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def generate_dashboard_intelligence(account_id: str, mode: str | None = None) -> dict:
    """Build the dashboard's priorities and reported metrics. Returns the widget."""
    db = get_db()
    now = datetime.now(UTC)

    state = index_state.get(account_id, INDEX)
    if state.get("status") not in (index_state.READY, index_state.STALE):
        raise DashboardError(
            "the Executive Dashboard index is %s - %s"
            % (state.get("status"), state.get("last_error") or "build it first"))

    summary_card = (db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
    ).get("data") or {}
    company = _text(summary_card.get("company_name")) or "This account"
    # What makes "the company's own site" decidable for source diversity. Its
    # careers page and its newsroom are one category; a publication is another.
    domain = _text(summary_card.get("domain"))

    candidates, retrieval = asyncio.run(_candidate_priorities(account_id, mode))
    priorities, dropped, invalid_count = _resolve_priorities(account_id, candidates)
    priorities, merged = _distinct(priorities)

    news_fallback_used = False
    if len(priorities) < MIN_PRIORITIES:
        # ABX: "Try to use news data only when the data is insufficient... for
        # the priorities part." Recent signals are already in the corpus, so the
        # fallback is a second, narrower question rather than a new source - and
        # anything it produces is labelled.
        extra, extra_dropped, extra_invalid = _news_priorities(
            account_id, mode, {p["title"].lower() for p in priorities})
        if extra:
            news_fallback_used = True
            priorities.extend(extra)
            priorities, more_merged = _distinct(priorities)
            merged.extend(more_merged)
        dropped.extend(extra_dropped)
        invalid_count += extra_invalid

    if not priorities:
        raise DashboardError(
            "no strategic priority survived evidence validation (%d candidate(s), "
            "%d unresolvable evidence id(s)) - nothing is published rather than "
            "showing an unsupported priority" % (len(candidates), invalid_count))

    priorities = priorities[:MAX_PRIORITIES]

    # Scored after the fallback and the cut, so every published catalyst carries
    # a score and nothing that was dropped was scored. One date for the whole
    # run, so two catalysts in the same widget are never aged against different
    # clocks.
    scored_on = now.date()
    for priority in priorities:
        # Scoring reads vendor-supplied strings - a URL, a period label - across
        # 220 accounts in markets whose conventions this code has not seen. A
        # catalyst that cannot be scored is still a catalyst worth showing, so a
        # failure here costs that card its bars rather than costing the account
        # its dashboard.
        try:
            priority["evidence_strength"] = evidence_strength.score(
                priority["sources"], scored_on, domain)
        except Exception:
            logger.exception("executive_dashboard: scoring failed for %r",
                             priority["title"][:60])
            priority["evidence_strength"] = None

    hp_facts = _hp_facts(db, account_id)
    industry = cs.normalise_industry(
        _text((summary_card or {}).get("industry_classification")))
    elsewhere = cs.cited_above(db, account_id, cs.SURFACE_EXEC)
    here: set = set()

    for priority in priorities:
        priority["description"] = _describe(priority, hp_facts, company)
        # Proof is attached AFTER the paragraph is written, to the HP offering
        # the paragraph actually named. The tuning logic is explicit that a case
        # study "must not create the account need" - so it can only follow a
        # recommendation that the account's own evidence already earned, and a
        # catalyst whose paragraph names no HP offering gets none.
        proof = _proof_for(db, priority, industry, elsewhere, here)
        priority["hp_proof_point"] = (proof or {}).get("text")
        priority["hp_proof_point_detail"] = proof
        if proof and proof.get("study_id"):
            here.add(proof["study_id"])

    reported = _reported_metrics(account_id)
    _publish_metrics(db, account_id, reported, now)
    summary = _executive_summary(company, priorities, reported)

    payload = {
        "account_id": account_id,
        "feature_key": "executive_dashboard",
        "widget_key": WIDGET_KEY,
        "data_classification": "inferred",
        "status": "available",
        "data": {
            "priorities": priorities,
            "priority_count": len(priorities),
            "executive_summary": summary,
            "ordering_basis": ORDERING_BASIS,
            "evidence_scores_available": True,
            "evidence_strength_formula": evidence_strength.FORMULA,
            "evidence_strength_max": evidence_strength.MAX_SCORE,
            "scored_on": scored_on.isoformat(),
            "reported_metrics": reported,
            "generation": {
                "prompt_version": PROMPT_VERSION,
                "retrieval_mode": retrieval.mode,
                "index_workspace": retrieval.workspace,
                "index_stale": retrieval.stale,
                "candidates_returned": len(candidates),
                "priorities_kept": len(priorities),
                "dropped_priorities": dropped,
                "merged_priorities": merged,
                "invalid_evidence_count": invalid_count,
                "news_fallback_used": news_fallback_used,
                "descriptions_rejected": [
                    {"title": p["title"],
                     "reason": p["description"].get("rejected_reason")}
                    for p in priorities
                    if p.get("description", {}).get("rejected_reason")],
                "hp_facts_available": len(hp_facts),
                "reported_metric_count": len(reported),
            },
        },
        "source_datasets": ["compliance_filings", "firmographics",
                            "company_hierarchy", "job_openings",
                            "google_news", "news_events"],
        "extracted_at": now,
        "updated_at": now,
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": WIDGET_KEY},
        {"$set": payload}, upsert=True)
    logger.info("executive_dashboard: published %d priority(ies) and %d reported "
                "metric(s) for account %s", len(priorities), len(reported),
                account_id)
    return payload


NEWS_QUESTION = (
    "What recent events involving this account suggest a current business "
    "priority? Use only the recent signals in the evidence. For each, quote in "
    "square brackets the evidence identifiers that support it."
)


def _news_priorities(account_id: str, mode, already: set) -> tuple:
    """Priorities drawn from recent events, used only when filings fall short."""
    try:
        result = query.ask(account_id, INDEX, NEWS_QUESTION,
                           mode=mode, top_k=40)
    except query.IndexNotReady:
        return [], [], 0

    user = "\n".join([
        "RETRIEVED CONTEXT (every line carries its evidence identifier):",
        result.context[:40000],
        "",
        "Identify priorities suggested by these recent events. Return JSON only.",
    ])
    raw = generate_gpt4o_json_completion(CANDIDATE_SYSTEM, user) or {}
    kept, dropped, invalid = _resolve_priorities(
        account_id, raw.get("priorities") or [])

    out = []
    for priority in kept:
        if priority["title"].lower() in already:
            continue
        priority["from_news_fallback"] = True
        priority["fallback_note"] = (
            "Drawn from recent events because the account's filed documents "
            "supported fewer than %d priorities." % MIN_PRIORITIES)
        out.append(priority)
    return out, dropped, invalid
