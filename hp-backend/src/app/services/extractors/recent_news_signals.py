import os
import io
import re
import csv
import json
import logging
import hashlib
import difflib
from collections import Counter
import pandas as pd
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.grounding import (
    build_corpus, check_text, GroundingReport,
)
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

logger = logging.getLogger(__name__)


def _find_file_path(rel_path: str) -> str | None:
    """Shared implementation - see datasets.py."""
    return find_file_path(rel_path)

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

def _s(row: dict, *keys: str) -> str:
    """First non-blank value among `keys`, as a clean string."""
    for k in keys:
        v = row.get(k)
        if v is None:
            continue
        s = str(v).strip()
        if s and s.lower() not in ("none", "null", "nan", "[]"):
            return s
    return ""


# ==============================================================================
# CATEGORY MAPPING
# Two source vocabularies -> the six display categories. Mapping tables only;
# nothing here is specific to any one account.
# ==============================================================================

DISPLAY_CATEGORIES = ["Financial", "Technology", "Security", "Hiring", "Strategic", "Competitive"]

GOOGLE_NEWS_TYPE_MAP = {
    "funding": "Financial",
    "earnings": "Financial",
    "m&a": "Strategic",
    "acquisition": "Strategic",
    "leadership": "Strategic",
    "launch": "Technology",
    "product": "Technology",
    "partnership": "Strategic",
    "hiring": "Hiring",
    "security": "Security",
    "other": "Strategic",
}

NEWS_EVENTS_CATEGORY_MAP = {
    "has_earnings": "Financial",
    "invests_into": "Financial",
    "invests_into_assets": "Financial",
    "receives_financing": "Financial",
    "launches": "Technology",
    "is_developing": "Technology",
    "partners_with": "Strategic",
    "acquires": "Strategic",
    "sells_assets_to": "Strategic",
    "expands_to": "Strategic",
    "identified_as_competitor_of": "Competitive",
    "hires": "Hiring",
    "increases_headcount_by": "Hiring",
    "is_vulnerable_to": "Security",
}

DEFAULT_CATEGORY = "Strategic"

# ==============================================================================
# SCORING - the /api/news D1-D5 methodology is the sole scoring authority.
# The model returns the five dimension scores; Python computes the composite
# and the tier. No alternate scale is mixed in.
# ==============================================================================

SCORE_WEIGHTS = {
    "recency": 0.25,
    "hp_relevance": 0.30,
    "strategic_impact": 0.20,
    "actionability": 0.15,
    "source_reliability": 0.10,
}
TIER_THRESHOLDS = [(8.0, "S"), (6.0, "A"), (4.0, "B"), (2.0, "C")]
MIN_CONFIDENCE_TO_PUBLISH = 2.0
MAX_SIGNALS = 20
GATE_MAX_AGE_DAYS = 365
DEDUP_SIMILARITY = 0.85

# Bump when the scoring prompt changes so cached output is regenerated.
SIGNAL_SCORING_PROMPT_VERSION = 8

# The only product lines a signal may be attributed to. The model picks one of
# these or returns null; it never names a product of its own invention. Account
# agnostic - these are HP's lines, not anything derived from an account's data.
HP_PLAYS = [
    "Z by HP Workstations",
    "HP Elite / Pro PCs",
    "HP Wolf Security",
    "Poly Collaboration",
    "HP Enterprise Print / MPS",
    "HP Anyware / DaaS",
]


def _parse_date(raw: str) -> datetime | None:
    if not raw:
        return None
    s = raw.strip().replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)
        except (ValueError, TypeError):
            continue
    return None


def _canonical(text: str) -> str:
    """Lowercased, punctuation-stripped headline used as the dedup key."""
    return re.sub(r"[^a-z0-9 ]", " ", (text or "").lower())


def _split_headline_publisher(headline: str) -> tuple[str, str]:
    """Google News headlines carry the outlet as a trailing ' - Publisher'.
    Recover it structurally - there is no publisher allowlist here, so this
    works for any account. When the suffix does not look like an outlet the
    headline is returned untouched and no publisher is claimed."""
    text = (headline or "").strip()
    if " - " not in text:
        return text, ""
    title, suffix = text.rsplit(" - ", 1)
    title, suffix = title.strip(), suffix.strip()
    if (not title or not suffix
            or len(suffix) > 40
            or len(suffix.split()) > 6
            or suffix.endswith((".", "!", "?", ","))):
        return text, ""
    return title, suffix


def _same_text(a: str, b: str) -> bool:
    """Whitespace- and case-insensitive equality, for spotting a duplicate."""
    return " ".join((a or "").split()).casefold() == " ".join((b or "").split()).casefold()


def _normalize_signals(gnews: list[dict], events: list[dict]) -> list[dict]:
    """Both files into one shape. Evidence and every source field are carried
    through verbatim - nothing here rewrites source text."""
    out = []

    for row in gnews:
        raw_headline = _s(row, "event_headline", "news_announcements", "title")
        if not raw_headline:
            continue
        headline, derived_publisher = _split_headline_publisher(raw_headline)
        event_dt = _parse_date(_s(row, "event_date"))
        raw_type = _s(row, "event_type").lower()

        # This export repeats the headline in news_announcements. Storing it
        # twice would print the same line twice on the card - keep it only when
        # it actually says something the headline does not.
        evidence = _s(row, "news_announcements")
        if _same_text(evidence, raw_headline) or _same_text(evidence, headline):
            evidence = ""

        # The column often holds a feed name rather than an outlet; the suffix
        # recovered from the headline is the better name when we have one.
        column_publisher = _s(row, "source_publisher")
        publisher = derived_publisher or column_publisher

        out.append({
            "headline": headline,
            "raw_headline": raw_headline,
            "evidence_sentence": evidence,
            "event_date": _s(row, "event_date"),
            "publication_date": "",
            "_event_dt": event_dt,
            "category": GOOGLE_NEWS_TYPE_MAP.get(raw_type, DEFAULT_CATEGORY),
            "raw_category": raw_type,
            "source_url": _s(row, "event_url"),
            "source_publisher": publisher,
            "source_publisher_derived": bool(derived_publisher),
            "source_confidence": _s(row, "relevance_confidence"),
            "coverage_depth": _s(row, "coverage_depth_events_per_account_last_12mo"),
            "dataset": "google_news",
        })

    for row in events:
        headline = _s(row, "summary", "article_sentence", "event")
        if not headline:
            continue
        effective = _s(row, "effective_date")
        found = _s(row, "found_at")
        event_dt = _parse_date(effective) or _parse_date(found)
        raw_cat = _s(row, "category").lower()
        evidence = _s(row, "article_sentence")
        if _same_text(evidence, headline):
            evidence = ""

        out.append({
            "headline": headline,
            "raw_headline": headline,
            "evidence_sentence": evidence,
            "source_publisher_derived": False,
            "event_date": effective or found,
            "publication_date": found,
            "_event_dt": event_dt,
            "category": NEWS_EVENTS_CATEGORY_MAP.get(raw_cat, DEFAULT_CATEGORY),
            "raw_category": raw_cat,
            # news_events carries no URL column - never fabricate one.
            "source_url": "",
            "source_publisher": "",
            "source_confidence": _s(row, "confidence"),
            "coverage_depth": "",
            "location": _s(row, "location"),
            "product": _s(row, "product"),
            "amount": _s(row, "amount"),
            "dataset": "news_events",
        })

    return out


def _apply_gate(signals: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """Gate 0, entirely deterministic and run before the model sees anything.
    Returns (passed, rejected-with-reason)."""
    passed, rejected = [], []
    cutoff = now - timedelta(days=GATE_MAX_AGE_DAYS)

    for s in signals:
        reason = None
        if not s["headline"] and not s["evidence_sentence"]:
            reason = "no headline or evidence sentence"
        elif s["_event_dt"] is None:
            reason = "unparseable date"
        elif s["_event_dt"] > now:
            reason = "date is in the future"
        elif s["_event_dt"] < cutoff:
            reason = f"older than {GATE_MAX_AGE_DAYS} days"

        if reason:
            rejected.append({**{k: v for k, v in s.items() if not k.startswith("_")},
                             "gate_reject_reason": reason})
        else:
            passed.append(s)

    return passed, rejected


def _dedupe(signals: list[dict]) -> list[dict]:
    """Group near-identical headlines into one card, preserving every merged
    row's URL, publisher and date as a supporting source. Lossless on sources."""
    groups: list[dict] = []

    for s in sorted(signals, key=lambda x: x["_event_dt"], reverse=True):
        canon = _canonical(s["headline"])
        # Two extractions of one article share its sentence and its date while
        # carrying different summaries, so the headline rule alone misses them.
        # Requiring BOTH the sentence and the date is what stops a shared
        # boilerplate sentence collapsing genuinely distinct events.
        ev_key = (_canonical(s.get("evidence_sentence") or ""), s["event_date"])
        match = None
        for g in groups:
            same_event = (ev_key[0] and ev_key == g["_ev_key"])
            if same_event or canon == g["_canon"] or difflib.SequenceMatcher(
                    None, canon, g["_canon"]).ratio() >= DEDUP_SIMILARITY:
                match = g
                break

        source_entry = {
            "url": s["source_url"],
            "publisher": s["source_publisher"],
            "dataset": s["dataset"],
            "event_date": s["event_date"],
            "publication_date": s["publication_date"],
        }

        if match:
            match["supporting_sources"].append(source_entry)
            match.setdefault("merged_headlines", []).append(s["headline"])
            # keep the URL-bearing row's link if the primary had none
            if not match["source_url"] and s["source_url"]:
                match["source_url"] = s["source_url"]
                match["source_publisher"] = s["source_publisher"]
        else:
            g = {k: v for k, v in s.items() if k != "_event_dt"}
            g["_canon"] = canon
            g["_ev_key"] = ev_key
            g["_event_dt"] = s["_event_dt"]
            g["signal_id"] = hashlib.sha1(canon.encode("utf-8")).hexdigest()[:12]
            g["supporting_sources"] = [source_entry]
            groups.append(g)

    for g in groups:
        g["supporting_source_count"] = len(g["supporting_sources"])
        g.pop("_ev_key", None)
    return groups


def _signals_fingerprint(signals: list[dict]) -> str:
    basis = sorted(
        [{"id": s["signal_id"], "h": s["headline"], "d": s["event_date"], "c": s["category"]}
         for s in signals],
        key=lambda x: x["id"],
    )
    payload = {"prompt_version": SIGNAL_SCORING_PROMPT_VERSION, "signals": basis}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _composite(scores: dict) -> float:
    """Python owns the weighted composite - the model is never asked for it."""
    return round(sum(float(scores[k]) * w for k, w in SCORE_WEIGHTS.items()), 2)


def _tier(confidence: float) -> str:
    for threshold, tier in TIER_THRESHOLDS:
        if confidence >= threshold:
            return tier
    return "rejected"


# Phrases that claim a buying moment the event does not establish.
ANGLE_BANNED_PHRASES = [
    "ideal time", "perfect time", "right time to", "now is the time",
    "monitor for follow-on announcements", "monitor for future announcements",
    "does not indicate any it or workforce transformation needs",
]

# How many leading / trailing words make a "stem" for the repetition check.
ANGLE_STEM_WORDS = 5


def _angle_stems(text: str) -> tuple[str, str]:
    """Opening and closing stems, for spotting two angles built to one template."""
    words = _norm_angle(text).split()
    if not words:
        return "", ""
    return (" ".join(words[:ANGLE_STEM_WORDS]),
            " ".join(words[-ANGLE_STEM_WORDS:]))


def _norm_angle(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def _angle_fault(angle: str, seen_stems: set) -> str | None:
    """Why this angle is unusable, or None. Checked in Python so the prompt is
    not the only thing standing between a stock phrase and the card."""
    n = _norm_angle(angle)
    for phrase in ANGLE_BANNED_PHRASES:
        if phrase in n:
            return f"uses the banned phrase '{phrase}'"
    opening, closing = _angle_stems(angle)
    if opening and opening in seen_stems:
        return f"opens the same way as another angle ('{opening}...')"
    if closing and closing in seen_stems:
        return f"closes the same way as another angle ('...{closing}')"
    return None


def _grounded_rationales(ground, report, sid: str,
                         rationales: dict) -> tuple[dict, dict]:
    """The rationales that are sourced, and the ones withheld.

    Each dimension is judged on its own: an invented figure in the recency
    rationale says nothing about the HP-relevance one, so only the offending
    sentence is dropped. The dimension SCORE always survives - it is the
    model's judgment of the signal, not a claim about the account.
    """
    kept, withheld = {}, {}
    for dim, text in rationales.items():
        bad_nums, bad_urls = check_text(ground, report, f"{sid}:{dim}", text)
        if bad_nums or bad_urls:
            withheld[dim] = (bad_nums or []) + (bad_urls or [])
        else:
            kept[dim] = text
    return kept, withheld


def _grounded_angle(ground, report, sid: str, entry: dict) -> str | None:
    """The sales angle, or None when it carries a figure or link the uploaded
    news never held. Scores are kept either way - only the prose is dropped."""
    angle = str(entry.get("sales_angle") or "").strip() or None
    if not angle:
        return None
    bad_nums, bad_urls = check_text(ground, report, sid, angle)
    if bad_nums or bad_urls:
        return None
    return angle


def score_news_signals(account_id: str, signals: list[dict], company_name: str) -> dict:
    """One cached GPT-4o call. The model returns the five D1-D5 dimension scores,
    their rationales, a sales angle and a gate second-opinion. It is never asked
    for the composite, the tier, the category, the dates or any source field."""
    db = get_db()
    now = datetime.now(timezone.utc)
    fingerprint = _signals_fingerprint(signals)

    existing = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "news_relevance_summary",
    })
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("signals_fingerprint") == fingerprint):
        return existing

    # Grounding corpus: the two news datasets this feature reads.
    ground = build_corpus({
        "google_news": _read_dataset_records(account_id, "google_news"),
        "news_events": _read_dataset_records(account_id, "news_events"),
    })
    report = GroundingReport(ground, ["sales_angle", "rationales"])

    roster = []
    for s in signals:
        roster.append(
            f'- id={s["signal_id"]} | date={s["event_date"]} | category={s["category"]}'
            f' | publisher={s["source_publisher"] or "unknown"}'
            f' | source_confidence={s["source_confidence"] or "unknown"}'
            f' | headline={s["headline"][:180]}'
            f' | evidence={(s["evidence_sentence"] or s["headline"])[:300]}'
        )

    hp_play_list = chr(10).join("  - " + p for p in HP_PLAYS)

    system_prompt = f"""You are a signal intelligence analyst for Account-Based Marketing. Score each signal for {company_name} using the framework below.

CONTEXT: HP Inc. is targeting {company_name} to sell client devices (Z by HP Workstations, HP Elite/Pro PCs), HP Wolf Security, Poly collaboration devices, HP Enterprise Print/MPS, and HP Anyware/DaaS. Today's date is {now.strftime('%d %B %Y')}.

GATE VALIDATION (a second opinion - hard filtering has already been applied):
Set "gate_pass" to false only if the signal does not reference a verifiable event, or does not concern {company_name} or a direct subsidiary. Otherwise true.

SCORING DIMENSIONS (each scored 1-10):

D1 - RECENCY
10 = last 30 days | 8 = 1-3 months ago | 6 = 3-6 months | 4 = 6-9 months | 2 = 9-12 months

D2 - HP RELEVANCE
Score BUYING CONTEXT, not product keywords. A signal does not have to mention a laptop to be relevant - most purchase decisions are preceded by events that never name a device. Ask: does this event change who decides, what gets funded, how many people need equipping, or where they work?
10 = explicit device refresh, endpoint security or workforce-transformation need
 8 = IT or device investment, a vendor evaluation, or a named IT/digital leader appointed
 6 = an event that reliably precedes a device or IT decision - leadership change (CEO/CFO/COO/CIO), capex increase, geographic or headcount expansion, M&A, a new office/plant/facility, an IT-infrastructure or data-centre joint venture, a large hiring programme
 4 = broad digital-transformation or technology-partnership news with no clear buying consequence
 2 = an event with no plausible path to a device, security or workforce decision (shareholder returns, community or sponsorship activity, product news in an unrelated line)

D3 - STRATEGIC IMPACT
10 = board-level initiative (expansion, workforce strategy) | 8 = C-suite decision or budget allocation | 6 = department-level initiative | 4 = operational change | 2 = routine business

D4 - ACTIONABILITY
Apply this literally. A newly appointed C-suite executive IS a 10, not background context - new leadership resets strategy and reopens budgets, and that is exactly when a seller makes contact. Do not mark an event down to 4 merely because it does not name HP.
10 = immediate outreach trigger - vendor evaluation, RFP, or a newly appointed CEO/CFO/COO/CIO/CISO
 8 = supports an active deal (budget approved, pain confirmed, refresh cycle disclosed)
 6 = useful in a conversation - gives the seller a specific, timely thing to open with
 4 = background context only, with nothing a seller could open on
 2 = no clear action

D5 - SOURCE RELIABILITY
10 = official company source (earnings, press release) | 8 = tier-1 media (Reuters, Bloomberg) | 6 = industry publication | 4 = analyst report | 2 = blog/social/unverified

SIGNALS TO SCORE:
{chr(10).join(roster)}

CRITICAL RULES:
1. Score honestly. A generic business update with no device, security or workforce relevance scores 3-4, not 6-7.
2a. NAME THE EVENT TYPE. Open by saying what kind of event this is - a leadership change, a financial result, a partnership, an investment, a product or market move - and say what it does and does NOT establish. A leadership appointment is a relationship and timing signal: new leadership resets priorities and reopens budgets, which is a reason to make contact. It is NOT evidence of a technology requirement. NEVER write "ideal time", "perfect time" or "the right time to position HP".
2b. RECOMMENDING MONITORING IS FINE - A STOCK PHRASE IS NOT. Where an event warrants nothing more than watching, say so, but name what specifically to watch for on THIS event. Every angle in this set must be a different sentence from the others: do not open or close two of them the same way. These are banned as written: "Monitor for follow-on announcements", "Monitor for future announcements", "does not indicate any IT or workforce transformation needs".
2. "sales_angle" is a 2-3 sentence brief for an HP seller. It must be an IMPLICATION, not a new fact - never introduce a number, product, customer or event that is not present in that signal's headline or evidence above.

   It MUST END WITH A USE - something the seller can actually do with this signal. One of: an outreach trigger; an opening line for a call; a specific person or function to approach; a timing window; or an explicit "monitor for X". A brief that ends by declaring the signal irrelevant is a FAILED answer and will be rejected.

   Calibrating the pitch is encouraged; dismissing the signal is not. "This is an umbrella AI-adoption announcement rather than a specific compute build-out - monitor for follow-on product integrations before leading with a workstation pitch" is a GOOD answer: it says what the evidence does not support AND what to do. "This does not support an HP conversation as it lacks relevance to devices, security or workforce transformation" is a BAD answer - it is a verdict with no use, and the relevance score already carries that judgement.

   Remember that most useful signals never mention a device. A leadership change tells the seller a strategy reset is coming and who to meet. A capex increase tells them when budget exists. An expansion tells them how many people will need equipping. Say that, tied to this signal's own evidence.

   Name the hp_play and why it applies when one does. When none applies, still give the seller a use - an opener or a thing to watch for - rather than closing the door.

   Write it as an analyst briefing a seller, not as marketing copy.
2b. "hp_play" names the single HP product line this signal most supports. It MUST be copied exactly from this list, or be null:
{hp_play_list}
Return null whenever the evidence gives no honest basis for choosing one - a dividend, an earnings figure or a community partnership usually does not. A guessed play is worse than none.
3. Do NOT return a weighted total, an overall confidence, a tier, a category, a date, a headline, an evidence sentence, a URL or a publisher. Those are computed or held elsewhere. Return only what the schema below asks for.
4. Never rewrite, paraphrase or "clean up" the evidence sentence. You are reading it, not editing it.
5. Return one entry per supplied id, using the id exactly as given.

Output JSON:
{{
  "signals": [
    {{
      "signal_id": "<id exactly as supplied>",
      "gate_pass": true,
      "gate_reject_reason": null,
      "scores": {{
        "recency": {{"score": 8, "rationale": "..."}},
        "hp_relevance": {{"score": 6, "rationale": "..."}},
        "strategic_impact": {{"score": 6, "rationale": "..."}},
        "actionability": {{"score": 4, "rationale": "..."}},
        "source_reliability": {{"score": 6, "rationale": "..."}}
      }},
      "sales_angle": "Two to three sentences: what this evidences, what it does not, and whether it warrants an HP conversation.",
      "hp_play": null
    }}
  ]
}}
"""

    user_prompt = (
        f"Score all {len(signals)} signals for {company_name}. "
        f"Return exactly one entry per supplied id, in JSON matching the schema."
    )

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)

    valid_ids = {s["signal_id"] for s in signals}
    scored: dict = {}
    angle_stems: set = set()
    angle_faults: dict = {}
    # dim -> the unsourced tokens that got its rationale withheld, per signal.
    rationale_faults: dict = {}
    if llm_res and isinstance(llm_res, dict) and isinstance(llm_res.get("signals"), list):
        for entry in llm_res["signals"]:
            if not isinstance(entry, dict):
                continue
            sid = str(entry.get("signal_id") or "").strip()
            if sid not in valid_ids:
                continue
            raw = entry.get("scores")
            if not isinstance(raw, dict):
                continue

            dims, rationales, ok = {}, {}, True
            for dim in SCORE_WEIGHTS:
                block = raw.get(dim)
                val = block.get("score") if isinstance(block, dict) else block
                try:
                    dims[dim] = max(0.0, min(10.0, float(val)))
                except (TypeError, ValueError):
                    ok = False
                    break
                if isinstance(block, dict) and block.get("rationale"):
                    rationales[dim] = str(block["rationale"]).strip()
            if not ok:
                continue

            confidence = _composite(dims)
            rationales, withheld = _grounded_rationales(ground, report, sid, rationales)
            if withheld:
                rationale_faults[sid] = withheld
            _pending_angle = _grounded_angle(ground, report, sid, entry)
            scored[sid] = {
                "signal_id": sid,
                "scores": dims,
                "rationales": rationales,
                # Dimensions whose rationale was withheld as unsourced. The
                # score for those dimensions still stands.
                "rationales_withheld": sorted(withheld) or None,
                "confidence": confidence,
                "tier": _tier(confidence),
                "sales_angle": None,   # filled below, after the quality guard
                # Enum-checked: anything the model invents is discarded, not stored.
                "hp_play": (str(entry.get("hp_play")).strip()
                            if str(entry.get("hp_play") or "").strip() in HP_PLAYS else None),
                "gate_pass": bool(entry.get("gate_pass", True)),
                "gate_reject_reason": (str(entry.get("gate_reject_reason")).strip()
                                       if entry.get("gate_reject_reason") else None),
            }

            if _pending_angle:
                fault = _angle_fault(_pending_angle, angle_stems)
                if fault:
                    angle_faults[sid] = fault
                else:
                    scored[sid]["sales_angle"] = _pending_angle
                    angle_stems.update(x for x in _angle_stems(_pending_angle) if x)

    # Prose-only retry. The five dimension scores, rationales and gate validation
    # already stored are never re-requested - only the sales angle is rewritten.
    if rationale_faults:
        logger.warning("live signals: rationale(s) withheld as unsourced on %d signal(s): %s",
                       len(rationale_faults), rationale_faults)

    if angle_faults:
        logger.warning("live signals: %d sales angle(s) rejected for phrasing: %s",
                       len(angle_faults), angle_faults)
        by_sid = {s["signal_id"]: s for s in signals}
        lines = []
        for sid, fault in sorted(angle_faults.items()):
            sig = by_sid.get(sid)
            if not sig:
                continue
            lines.append(f'- id={sid} | {fault} | headline={sig["headline"][:150]}')
        retry_system = (
            "You are rewriting ONLY the sales_angle for the signals listed below. "
            "Each was rejected for the stated reason." + chr(10) + chr(10)
            + chr(10).join(lines) + chr(10) + chr(10)
            + "Rules: name what kind of event it is and what it does and does not "
            "establish; introduce no number, product, customer or event that is not "
            "in that signal's own headline; never write 'ideal time', 'perfect time' "
            "or 'the right time to position HP'; recommending monitoring is fine but "
            "name what specifically to watch for on this event; every angle must be a "
            "different sentence, opening and closing differently from the others. "
            "A LEADERSHIP APPOINTMENT stays a strong signal: new leadership resets "
            "priorities and reopens budgets, which is a real reason to make contact "
            "early - say that, and say plainly that the appointment itself does not "
            "establish a technology requirement. Do not water it down to 'monitor for "
            "developments'."
            + chr(10) + chr(10)
            + 'Output JSON: {"signals": [{"signal_id": "<id>", "sales_angle": "..."}]}'
        )
        retry_res = generate_gpt4o_json_completion(
            retry_system,
            f"Rewrite the sales angle for these {len(lines)} signals. Return JSON.")
        if retry_res and isinstance(retry_res, dict) and isinstance(retry_res.get("signals"), list):
            for entry in retry_res["signals"]:
                if not isinstance(entry, dict):
                    continue
                sid = str(entry.get("signal_id") or "").strip()
                if sid not in scored:
                    continue
                angle = _grounded_angle(ground, report, sid, entry)
                if not angle or _angle_fault(angle, angle_stems):
                    continue
                scored[sid]["sales_angle"] = angle
                angle_stems.update(x for x in _angle_stems(angle) if x)

    if scored:
        payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_relevance_summary",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "signals_fingerprint": fingerprint,
                "scored_count": len(scored),
                "score_weights": SCORE_WEIGHTS,
                "scores": scored,
                "grounding_report": report.as_dict(),
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        if existing and existing.get("status") == "available":
            return existing
        payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_relevance_summary",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "signals_fingerprint": None,
                "scored_count": 0,
                "score_weights": SCORE_WEIGHTS,
                "scores": {},
                "notice": "Signal relevance scoring requires OPENAI_API_KEY. The signal feed below is shown unscored; no scores are invented.",
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "news_relevance_summary"},
        {"$set": payload},
        upsert=True
    )
    return payload


@requires_local_datasets(
    "google_news", "news_events",
)
def extract_recent_news_signals(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)

    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    gnews = _read_dataset_records(account_id, "google_news")
    events = _read_dataset_records(account_id, "news_events")

    raw = _normalize_signals(gnews, events)
    passed, rejected = _apply_gate(raw, now)
    deduped = _dedupe(passed)

    # 1. Widget: news_relevance_summary (inferred) - scored first so the feed can
    #    rank by it. Cached; no model call on an unchanged signal set.
    if deduped:
        score_doc = score_news_signals(account_id, deduped, company_name)
    else:
        score_doc = {"data": {"scores": {}}}
    scores = (score_doc.get("data") or {}).get("scores") or {}

    # 2. Rank and cap. Unscored signals keep their natural date order.
    for s in deduped:
        sc = scores.get(s["signal_id"])
        s["confidence"] = sc["confidence"] if sc else None
        s["tier"] = sc["tier"] if sc else None
        s.pop("_canon", None)
        s.pop("_event_dt", None)

    if scores:
        publishable = [s for s in deduped
                       if scores.get(s["signal_id"])
                       and scores[s["signal_id"]]["gate_pass"]
                       and s["confidence"] >= MIN_CONFIDENCE_TO_PUBLISH]
        publishable.sort(key=lambda s: (-s["confidence"], s["event_date"]), reverse=False)
        publishable = sorted(publishable, key=lambda s: -s["confidence"])[:MAX_SIGNALS]
    else:
        publishable = sorted(deduped, key=lambda s: s["event_date"], reverse=True)[:MAX_SIGNALS]

    if publishable:
        feed_payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_signals_feed",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_signals_count": len(publishable),
                "raw_signal_count": len(raw),
                "gate_rejected_count": len(rejected),
                "gate_rejection_summary": dict(Counter(
                    r.get("gate_reject_reason") or "unspecified" for r in rejected)),
                "deduped_from": len(passed),
                "cap": MAX_SIGNALS,
                "signals": publishable,
                "gate_rejections": rejected,
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        feed_payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_signals_feed",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "news_signals_feed"},
        {"$set": feed_payload},
        upsert=True
    )

    return [feed_payload, score_doc] if deduped else [feed_payload]
