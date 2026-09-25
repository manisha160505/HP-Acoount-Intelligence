import difflib
import hashlib
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

from bson import ObjectId

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors import signal_scoring
from app.services.extractors.datasets import (
    find_file_path,
    read_dataset_records,
    requires_local_datasets,
)
from app.services.extractors.grounding import (
    GroundingReport,
    build_corpus,
    check_text,
)
from app.services.hp import case_studies as cs

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

NL = chr(10)

# ==============================================================================
# SCORING - `HP_Live_Signal_Scoring_Logic.docx` is the sole scoring authority.
#
# Three drivers, and only ONE of them is a model judgement:
#
#   Recency            30%   computed from the date      (signal_scoring)
#   Relevance & Impact 50%   judged by the model         (this module)
#   Source Reliability 20%   looked up from the domain   (signal_scoring)
#
# This replaced a five-dimension model-scored set (recency, hp_relevance,
# strategic_impact, actionability, source_reliability at 25/30/20/15/10). Two of
# those dimensions were asking GPT-4o for things Python can decide exactly: how
# old a date is, and how reputable a domain is. `actionability` and
# `strategic_impact` are gone entirely - the specification folds the second into
# relevance and does not keep the first.
#
# Python still owns the composite and the tier. The model is never asked for a
# total, a tier, a date or a source field.
# ==============================================================================

SCORE_WEIGHTS = signal_scoring.WEIGHTS

# The only dimension the model scores. Recency and source reliability are
# computed and injected, so asking for them would invite a second opinion on a
# question that already has an exact answer.
MODEL_SCORED_DIMS = ("relevance_impact",)
TIER_THRESHOLDS = [list(r) for r in signal_scoring.TIER_THRESHOLDS]
MIN_CONFIDENCE_TO_PUBLISH = signal_scoring.MIN_CONFIDENCE_TO_PUBLISH
MAX_SIGNALS = signal_scoring.MAX_SIGNALS
GATE_MAX_AGE_DAYS = 365
DEDUP_SIMILARITY = signal_scoring.DEDUP_SIMILARITY

# Bump when the scoring prompt changes so cached output is regenerated.
# 10 - three drivers per HP_Live_Signal_Scoring_Logic.docx. The model now
#      scores only Relevance and Impact, on the document's 0/3/6/8/10 scale;
#      recency and source reliability are computed in `signal_scoring`.
# 11 - the Implication for HP is published on the signal instead of being left
#      in the score document; the angle now reads the account's earned
#      opportunities, intent and technology; and it is written to the tuning
#      logic's 70-100 word band.
# 12 - the word band is retried rather than fatal. Enforcing it as a hard
#      reject dropped every angle the model wrote and published cards with no
#      implication at all, which is worse than a short one.
# 13 - the JSON schema still asked for "two to three sentences", which is what
#      the model was answering; rule 2 asking for 70-100 words lost the argument.
# 14 - the angle rewrite is one call per signal. Batched, the model answered
#      eight at about fifty words each whatever the brief said.
# 15 - the length retry is given the account context the first pass had, so
#      "connect this event to what is established about the account" is a brief
#      the model can actually meet.
# 16 - and a shape to write it in: three named parts rather than a word count,
#      which is what the first pass already had and the retry did not.
# 17 - the feeds' own Low/High relevance rating is no longer sent to the model
#      (client, 23 Sep), the 2.0 publish floor is gone and the S/A/B/C letters
#      are retired in favour of the 0-10 score.
SIGNAL_SCORING_PROMPT_VERSION = 17

# Recommendation Tuning Logic, Live Signals: "Minimum 70 words; maximum 100
# words." Enforced through the existing angle guard and its one retry, so a
# short angle is rewritten rather than dropped.
ANGLE_MIN_WORDS = 70
ANGLE_MAX_WORDS = 100

# Whether the event has actually happened. A plant that "will be built" and one
# that "has opened" are different sales conversations, so the card must not read
# the same for both. "unknown" is the honest default and renders no badge -
# the model is told to choose it rather than guess between the others.
EVENT_STATUSES = ["completed", "announced", "planned", "rumoured", "unknown"]
DEFAULT_EVENT_STATUS = "unknown"

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
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)  # noqa: DTZ007 - parses a date from source data that carries no timezone
            return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
        except (ValueError, TypeError):
            continue
    return None


def _sort_timestamp(signal: dict) -> float:
    """Epoch seconds for tie-break ordering. `_event_dt` has been popped by the
    time ranking runs, so re-parse; an unparseable or missing date sorts last
    rather than raising or silently ordering as if it were the epoch."""
    dt = _parse_date(signal.get("event_date") or "")
    return dt.timestamp() if dt else float("-inf")


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


def _account_context(account_id: str) -> str:
    """What else is known about this account, for the Implication for HP.

    The Recommendation Tuning Logic is explicit that Live Signals must "start
    with the specific news event and connect it with relevant Intent,
    Technographics, Hiring, Filings and existing Opportunity Map findings", and
    that where those are absent the event is surfaced as context rather than an
    opportunity.

    Without them the model saw one headline and nothing else, so every angle it
    could honestly write was a variation on "this does not indicate a
    technology need" - true, and useless. Read from the widgets rather than the
    raw datasets, so the context is what the platform has already verified and
    published elsewhere.
    """
    db = get_db()

    def widget(key):
        return (db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": key}) or {}).get("data") or {}

    lines = []

    plays = widget("opportunity_narrative_plays")
    earned = [str(p.get("title") or "").strip()
              for p in (plays.get("opportunity_plays") or [])
              + (plays.get("service_plays") or [])
              if str(p.get("title") or "").strip()]
    if earned:
        lines.append("HP opportunities this account's evidence has already "
                     "earned: " + "; ".join(earned[:8]))

    topics = [str(t.get("topic_name") or "") for t in
              (widget("intent_topics_table").get("topics") or [])[:12]
              if t.get("topic_name")]
    if topics:
        lines.append("Research intent topics: " + ", ".join(topics))

    stack = [str(x) for x in
             (widget("tech_stack_matrix").get("full_tech_stack") or [])[:25] if x]
    if stack:
        lines.append("Detected technologies: " + ", ".join(stack))

    return NL.join(lines)


def _signals_fingerprint(signals: list[dict], context: str = "") -> str:
    basis = sorted(
        [{"id": s["signal_id"], "h": s["headline"], "d": s["event_date"], "c": s["category"]}
         for s in signals],
        key=lambda x: x["id"],
    )
    payload = {"prompt_version": SIGNAL_SCORING_PROMPT_VERSION,
               "signals": basis,
               # The angle now reads the account's opportunities, intent and
               # technology, so a change in any of them has to rebuild it.
               "account_context": context}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _composite(scores: dict) -> float:
    """Python owns the weighted composite - the model is never asked for it.

    Delegates to `signal_scoring` so the weights live in exactly one place: the
    module that carries the specification. A second copy here would be a second
    thing to forget when the document changes.
    """
    return signal_scoring.composite(
        scores["recency"], scores["relevance_impact"], scores["source_reliability"])


def _deterministic_dims(signal: dict, now: datetime,
                        company_name: str = "") -> tuple[dict, dict]:
    """The two drivers Python decides, with the basis for each.

    Returns `(scores, bases)`. Source reliability can come back as None when the
    domain is real but unclassified; that is not the same as a missing source,
    so it falls back to "structured third-party evidence" - the band the
    specification already uses for a record whose provenance is usable but
    unconfirmed - rather than to zero. Scoring an unrecognised regional outlet
    as unverifiable would quietly bury every signal from one.
    """
    recency, recency_basis = signal_scoring.recency_points(signal.get("_event_dt"), now)

    points, source_basis, resolved = signal_scoring.source_reliability_points(
        url=signal.get("source_url") or "",
        publisher=signal.get("source_publisher") or "",
        dataset=signal.get("dataset") or "",
        company_name=company_name,
    )
    if points is signal_scoring.UNKNOWN:
        points = signal_scoring.STRUCTURED_THIRD_PARTY
        source_basis = source_basis + "; scored as structured third-party evidence"

    return (
        {"recency": recency, "source_reliability": points},
        {"recency": recency_basis, "source_reliability": source_basis,
         "resolved_source_url": resolved or None},
    )


def _tier(confidence: float) -> str | None:
    """The letter band, or None once the bands are emptied.

    Kept as a function rather than deleted so the config still decides: a
    deployment that wants the letters back restores `tier_thresholds` and they
    return. With the list empty - which is the client's 25 Sep position - every
    signal carries its 0-10 score and no letter.
    """
    if not TIER_THRESHOLDS:
        return None
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


def _angle_length_fault(angle: str) -> str | None:
    """Why this angle misses the brief's word band, or None.

    Kept apart from `_angle_fault` because the two failures deserve different
    treatment. A banned phrase or a duplicated opening makes an angle unusable
    and it is dropped. Being short does not: the first version of this check
    rejected every angle the model wrote - they ran 36 to 60 words against a
    70-100 brief - and the cards published with no implication at all, which is
    worse than a short one. Length is retried, and the best answer is kept.
    """
    words = len(str(angle or "").split())
    if words and not (ANGLE_MIN_WORDS <= words <= ANGLE_MAX_WORDS):
        return f"is {words} words; the brief is {ANGLE_MIN_WORDS}-{ANGLE_MAX_WORDS}"
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
    now = datetime.now(UTC)
    account_context = _account_context(account_id)
    fingerprint = _signals_fingerprint(signals, account_context)

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
            # The feeds' own Low/High relevance rating is deliberately NOT
            # sent. The client, 23 Sep: "pls do not use low/high confidence
            # columns from those feeds". It stays on the row for provenance.
            ""
            f' | headline={s["headline"][:180]}'
            f' | evidence={(s["evidence_sentence"] or s["headline"])[:300]}'
        )

    hp_play_list = chr(10).join("  - " + p for p in HP_PLAYS)

    system_prompt = f"""You are a signal intelligence analyst for Account-Based Marketing. Score each signal for {company_name} using the framework below.

CONTEXT: HP Inc. is targeting {company_name} to sell client devices (Z by HP Workstations, HP Elite/Pro PCs), HP Wolf Security, Poly collaboration devices, HP Enterprise Print/MPS, and HP Anyware/DaaS. Today's date is {now.strftime('%d %B %Y')}.

WHAT ELSE IS KNOWN ABOUT THIS ACCOUNT - use it to connect the event to something already established, never as a new fact about the event:
{account_context or "(nothing else is established for this account yet)"}

CONNECT THE EVENT. An event on its own rarely establishes a technology requirement, and saying so is not an answer. Where one of the opportunities, intent topics or detected technologies above relates to this event, say how the event affects THAT - whether it makes it more timely, larger, or better funded - and open the conversation there. Where nothing above relates, surface the event as seller context and say what to watch for. Never invent a connection that the list above does not support.

GATE VALIDATION (a second opinion - hard filtering has already been applied):
Set "gate_pass" to false only if the signal does not reference a verifiable event, or does not concern {company_name} or a direct subsidiary. Otherwise true.

THE ONE DIMENSION YOU SCORE: SIGNAL RELEVANCE AND IMPACT

Recency and source reliability are computed from the data and are NOT yours to score. Do not return them.

Choose exactly one level - 10, 8, 6, 3 or 0. These are the only permitted values; there is no 9, 7, 5, 4, 2 or 1.

10 - DIRECT HP-ADDRESSABLE NEED. A current requirement, procurement, refresh, replacement, deployment, support need or solution requirement is EXPLICITLY STATED.
  Products: PC/notebook refresh, business-PC or AI-PC procurement, desktop/AiO replacement, workstation requirement, print-fleet refresh, Poly requirement.
  Services: device support, onsite or predictive support, deployment, factory imaging, provisioning, BIOS configuration, asset tagging, Autopilot/Intune registration, installation, lifecycle or device recovery.
  Solutions: workforce-experience or DEX requirement, endpoint-security requirement, secure print, print/scan workflow, enterprise or employee AI requirement.

8 - HP-RELEVANT TECHNOLOGY OR WORKPLACE INITIATIVE. A specific initiative directly related to an HP-addressable area is explicitly stated, but no actual procurement or requirement is.
  Enterprise AI/GenAI, employee or on-device AI, AI compute, workstation/HPC initiative; digital workplace transformation, DEX, endpoint modernisation, Windows migration, device management, VDI; endpoint security, Zero Trust, ransomware or device-security initiative; print/scan or document-workflow modernisation; endpoint-support modernisation, fleet sustainability, device-reliability initiative.

6 - MAJOR BUSINESS CHANGE THAT COULD CREATE HP DEMAND. A significant account change is explicitly stated, but no HP-related technology requirement is.
  New office, HQ, factory, facility or site; geographic or capacity expansion; significant hiring or workforce growth; major capex or investment tied to growth, operations or capacity; acquisition, merger, JV, new business unit or major operational capability.

3 - GENERAL ACCOUNT SIGNAL WITH WEAK HP CONNECTION. Useful account intelligence, but no HP-addressable need or initiative is established.
  General strategic partnership, customer-facing AI or product launch, general cloud partnership, executive appointment, award, consumer-facing digital initiative, general corporate announcement.

0 - NO MEANINGFUL HP CONNECTION. No identifiable HP product, service or solution opportunity.
  Share-price movement, dividend announcement, routine earnings with no relevant initiative, sponsorship, consumer promotion, unrelated legal or corporate news.

TWO RULES THAT DECIDE THE LEVEL:

TAKE THE HIGHEST LEVEL, NEVER ADD. A signal carrying several pieces of evidence scores the highest level any single piece supports. "New factory" (6) plus "hiring growth" (6) is 6, not 12. "New factory" (6) plus "enterprise AI initiative" (8) is 8, not 14. List every matched category in "matched_categories" regardless of which one set the score.

DO NOT SCORE A NEED THAT MERELY FOLLOWS LOGICALLY. The score may not rise because a requirement would plausibly result from the event. A large capex announcement is 6 even though new facilities will eventually need equipping, because the capex statement does not itself establish a PC, workstation, support, security or print requirement. Only what the signal explicitly states counts.

SIGNALS TO SCORE:
{chr(10).join(roster)}

CRITICAL RULES:
1. Score honestly. A generic business update with no device, security or workforce relevance scores 3-4, not 6-7.
2a. NAME THE EVENT TYPE. Open by saying what kind of event this is - a leadership change, a financial result, a partnership, an investment, a product or market move - and say what it does and does NOT establish. A leadership appointment is a relationship and timing signal: new leadership resets priorities and reopens budgets, which is a reason to make contact. It is NOT evidence of a technology requirement. NEVER write "ideal time", "perfect time" or "the right time to position HP".
2b. RECOMMENDING MONITORING IS FINE - A STOCK PHRASE IS NOT. Where an event warrants nothing more than watching, say so, but name what specifically to watch for on THIS event. Every angle in this set must be a different sentence from the others: do not open or close two of them the same way. These are banned as written: "Monitor for follow-on announcements", "Monitor for future announcements", "does not indicate any IT or workforce transformation needs".
2. "sales_angle" is the Implication for HP: what this event changes for HP and what the seller should do because of it. Between 70 and 100 words. It must be an IMPLICATION, not a new fact - never introduce a number, product, customer or event that is not present in that signal's headline or evidence above.

   It MUST END WITH A USE - something the seller can actually do with this signal. One of: an outreach trigger; an opening line for a call; a specific person or function to approach; a timing window; or an explicit "monitor for X". A brief that ends by declaring the signal irrelevant is a FAILED answer and will be rejected.

   Calibrating the pitch is encouraged; dismissing the signal is not. "This is an umbrella AI-adoption announcement rather than a specific compute build-out - monitor for follow-on product integrations before leading with a workstation pitch" is a GOOD answer: it says what the evidence does not support AND what to do. "This does not support an HP conversation as it lacks relevance to devices, security or workforce transformation" is a BAD answer - it is a verdict with no use, and the relevance score already carries that judgement.

   Remember that most useful signals never mention a device. A leadership change tells the seller a strategy reset is coming and who to meet. A capex increase tells them when budget exists. An expansion tells them how many people will need equipping. Say that, tied to this signal's own evidence.

   Name the hp_play and why it applies when one does. When none applies, still give the seller a use - an opener or a thing to watch for - rather than closing the door.

   Write it as an analyst briefing a seller, not as marketing copy.
2b. "hp_play" names the single HP product line this signal most supports. It MUST be copied exactly from this list, or be null:
{hp_play_list}
Return null whenever the evidence gives no honest basis for choosing one - a dividend, an earnings figure or a community partnership usually does not. A guessed play is worse than none.
2c. "event_status" says whether the event HAS HAPPENED, judged only from the tense and wording of that signal's own headline and evidence. Copy exactly one of these strings:
  - "completed"  - it has already happened ("opened", "has acquired", "reported Q3 results", "completed")
  - "announced"  - formally stated by the company as decided but not yet done ("announces plans to", "to build", "will launch", "has signed an agreement to")
  - "planned"    - under consideration or targeted, not yet committed ("aims to", "is exploring", "targets 2027", "eyes expansion")
  - "rumoured"   - reported second-hand or unconfirmed ("reportedly", "sources say", "is said to be", "speculation")
  - "unknown"    - the wording does not settle it
Judge the EVENT, not the article: a story published today about a factory that opened last year is "completed". Do not infer from the date alone. If the tense is genuinely ambiguous return "unknown" - that is a correct answer, not a failure, and is far better than guessing. Never use a status to make a signal sound more urgent than its wording supports.
3. Do NOT return a weighted total, an overall confidence, a tier, a category, a date, a headline, an evidence sentence, a URL or a publisher. Do NOT return a recency or source-reliability score - both are computed from the data and yours would be discarded. Return only what the schema below asks for.
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
        "relevance_impact": {{"score": 6, "rationale": "Name the level and say what the signal explicitly states - and what it does not."}}
      }},
      "matched_categories": ["major business change: new facility", "workforce growth"],
      "sales_angle": "70-100 words: what this event establishes and what it does not, how it affects something already known about this account, and what the seller should do next.",
      "hp_play": null,
      "event_status": "announced"
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
    # The signal behind each id, so the computed drivers can read its date and
    # source without a second pass over the list.
    by_id = {s["signal_id"]: s for s in signals}
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
            for dim in MODEL_SCORED_DIMS:
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

            # Recency and source reliability are computed, not asked for. They
            # are injected after the model's answer so a model that returns them
            # anyway cannot override the arithmetic.
            computed, bases = _deterministic_dims(by_id[sid], now, company_name)
            dims.update(computed)
            confidence = _composite(dims)

            rationales, withheld = _grounded_rationales(ground, report, sid, rationales)
            if withheld:
                rationale_faults[sid] = withheld

            # The computed drivers' bases are attached AFTER grounding, not
            # before. Grounding exists to stop the model asserting a number the
            # account's own data does not carry - but "148 days old" is Python's
            # arithmetic on a date this signal already holds, not a claim about
            # the account, and the news corpus naturally contains no such
            # figure. Running these through the check withheld every recency
            # basis that mentioned an age, which is most of them, and left the
            # score on screen with nothing explaining it.
            rationales["recency"] = bases["recency"]
            rationales["source_reliability"] = bases["source_reliability"]
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
                # Enum-checked like hp_play: an invented status falls back to
                # "unknown", which renders no badge, rather than being stored.
                "event_status": (str(entry.get("event_status")).strip().lower()
                                 if str(entry.get("event_status") or "").strip().lower()
                                 in EVENT_STATUSES else DEFAULT_EVENT_STATUS),
                "gate_pass": bool(entry.get("gate_pass", True)),
                "gate_reject_reason": (str(entry.get("gate_reject_reason")).strip()
                                       if entry.get("gate_reject_reason") else None),
            }

            if _pending_angle:
                fault = _angle_fault(_pending_angle, angle_stems)
                if fault:
                    angle_faults[sid] = fault
                else:
                    # Stored even when short, so a failed rewrite leaves the
                    # card with an implication rather than none.
                    scored[sid]["sales_angle"] = _pending_angle
                    angle_stems.update(x for x in _angle_stems(_pending_angle) if x)
                    length_fault = _angle_length_fault(_pending_angle)
                    if length_fault:
                        angle_faults[sid] = length_fault

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
            "developments'. "
            # A word count alone does not lengthen the answer - every rewrite
            # came back near fifty however many times the band was repeated.
            # What the first pass has and this did not is a SHAPE: three named
            # parts, each owing its own sentences. Asked for the parts the model
            # writes them; asked for a number it writes to its own default.
            "Write it in three parts, run together as continuous prose with no "
            "headings, labels or bullets:" + chr(10)
            + "(1) TWO SENTENCES on what this event is and what it establishes "
            "for HP - and say plainly what it does NOT establish." + chr(10)
            + "(2) TWO SENTENCES connecting it to what is already established "
            "about this account, naming the specific intent topic, detected "
            "technology, hiring pattern or earned HP opportunity from the list "
            "below that it bears on." + chr(10)
            + "(3) ONE SENTENCE on what the seller should do next and what "
            "specifically to watch for on this event." + chr(10)
            + "The five sentences together must total %d to %d words. Anything "
            "shorter than %d is rejected again, and the room is for part (2), "
            "not for padding parts (1) and (3)."
            % (ANGLE_MIN_WORDS, ANGLE_MAX_WORDS, ANGLE_MIN_WORDS)
            # The retry asks for exactly that connection, so it has to be given
            # the same account context the first pass had. Without it the model
            # was told to connect the event to what is established about the
            # account and handed nothing to connect it to, which is why the
            # rewrites kept coming back at the length that earned the rejection.
            # Nothing new is introduced by this: it is the platform's own
            # published findings, already grounded where they were written.
            + (chr(10) + chr(10) + "WHAT IS ALREADY ESTABLISHED ABOUT THIS "
               "ACCOUNT (connect the event to this; introduce nothing beyond "
               "it and the signal's own headline):" + chr(10) + account_context
               if account_context else "")
            + chr(10) + chr(10)
            + 'Output JSON: {"signals": [{"signal_id": "<id>", "sales_angle": "..."}]}'
        )
        # One call per signal, not one call for all of them.
        #
        # The batched rewrite was asked for the 70-100 word band three separate
        # ways - the rule, the JSON schema and this retry - and kept returning
        # about fifty. Asked for eight angles in one response the model spends
        # its budget across them; asked for one it writes to the brief. The cost
        # is bounded by MAX_SIGNALS, and only the angles that actually missed
        # are retried.
        rewritten = []
        for sid, fault in sorted(angle_faults.items()):
            sig = by_sid.get(sid)
            if not sig:
                continue
            one = generate_gpt4o_json_completion(
                retry_system,
                "Rewrite the sales angle for this one signal and return JSON "
                "containing only it." + NL
                + f'- id={sid} | {fault} | headline={sig["headline"][:150]}'
                + NL + f'  evidence={(sig.get("evidence_sentence") or sig["headline"])[:300]}')
            for entry in ((one or {}).get("signals") or []):
                if isinstance(entry, dict):
                    rewritten.append(entry)

        retry_res = {"signals": rewritten}
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
                # Keep whichever answer is closer to the brief. A rewrite asked
                # for length can come back shorter than what it replaced, and
                # overwriting unconditionally would publish the worse of two
                # valid angles.
                def _miss(text):
                    n = len(str(text or "").split())
                    if not n:
                        return 10 ** 6
                    return max(ANGLE_MIN_WORDS - n, n - ANGLE_MAX_WORDS, 0)

                if _miss(angle) > _miss(scored[sid].get("sales_angle")):
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
                "scoring_config_version": signal_scoring.version_stamp(),
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
                "scoring_config_version": signal_scoring.version_stamp(),
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
    now = datetime.now(UTC)

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
        # Unscored signals carry the honest default, so the card always has a
        # value to read and never renders a stale or missing status.
        s["event_status"] = (sc or {}).get("event_status") or DEFAULT_EVENT_STATUS
        # The Implication for HP, which the Recommendation Tuning Logic makes
        # this feature's mandatory seller-facing output.
        #
        # It has been generated, grounded, quality-guarded and retried all
        # along - and then left in the score document, because only confidence,
        # tier and status were copied across. Every card on screen carried a
        # headline, a date and a score, and nothing saying what the event means
        # for HP or what to do about it.
        s["sales_angle"] = (sc or {}).get("sales_angle")
        s["hp_play"] = (sc or {}).get("hp_play")
        s["rationales"] = (sc or {}).get("rationales")
        s.pop("_canon", None)
        s.pop("_event_dt", None)

    if scores:
        publishable = [s for s in deduped
                       if scores.get(s["signal_id"])
                       and scores[s["signal_id"]]["gate_pass"]
                       and s["confidence"] >= MIN_CONFIDENCE_TO_PUBLISH]
        # Confidence descending, ties broken by newest event first. Sorting on
        # the parsed datetime rather than the raw event_date string keeps mixed
        # date formats ordering correctly; undated signals sort last.
        publishable = sorted(
            publishable,
            key=lambda s: (-s["confidence"], -_sort_timestamp(s)),
        )[:MAX_SIGNALS]

        # F9: a case study may strengthen the Implication for HP, and nowhere
        # else on this card. Applied after ranking so proof goes to the signals
        # that will actually be published, and only where the signal already
        # names an HP play - proof for a line the angle never mentions is
        # decoration, not evidence.
        try:
            _db = get_db()
            _firmo = (read_dataset_records(account_id, "firmographics",
                                           strict=False) or [{}])[0]
            _industry = cs.normalise_industry(
                _firmo.get("Linkedin Industry Category")
                or _firmo.get("Naics Description") or "")
            _taken = cs.cited_above(_db, account_id, cs.SURFACE_SIGNALS)
            _here: set = set()
            for _sig in publishable:
                # The named play only. Reading the HP line out of the angle
                # instead was tried and was wrong in almost every case: the
                # angles for these events say in terms that they establish no
                # technology requirement, and matching an incidental
                # "collaboration" or "workstation" in that sentence put a NASA
                # workstation story under a capital-expenditure announcement.
                # Where the model names no play, the honest output is no proof.
                if not _sig.get("sales_angle") or not _sig.get("hp_play"):
                    continue
                _lines = cs.lines_for_product_text(str(_sig.get("hp_play") or ""))
                if not _lines:
                    continue
                _point = cs.allocate(_db, _lines, industry=_industry,
                                     signals=cs.signals_for_opportunity(
                                         _sig.get("hp_play")),
                                     taken=_taken, used_here=_here)
                if _point:
                    _sig["hp_proof_point"] = _point
                    if _point.get("study_id"):
                        _here.add(_point["study_id"])
        except Exception:
            logger.exception("live signals: proof allocation failed for %s", account_id)
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
