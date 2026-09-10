import os
import io
import csv
import re
import json
import hashlib
import logging
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.recent_news_signals import extract_recent_news_signals
from app.services.extractors.grounding import (
    build_corpus, check_text, filter_enum_list, strip_unsourced_urls,
    GroundingReport, HP_PRODUCT_LINES,
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

# ==============================================================================
# OPPORTUNITY SCORING AND EVIDENCE DISCIPLINE
#
# Every table below describes HP's product lines or a fixed scoring band.
# Nothing here is specific to any account: vendors, contacts, industries and
# figures are all read from the uploaded files at runtime.
# ==============================================================================

NL = chr(10)

OPPORTUNITY_PROMPT_VERSION = 18
MAX_PLAYS = 5

# HP_ABX_v3_final defines NO numeric opportunity score for this feature. Plays
# are ordered by how many of its three checks they meet, with trigger recency as
# the tie-break. Any weighted score here would be invented, so there is none.
SPEC_CHECKS = ("verified_evidence", "timing_trigger", "hp_fit")

# The spec's exact wording when no official HP proof point can be sourced.
NO_PROOF_POINT = "No supporting HP proof point available"

# Composed in Python when the model will not return a timing note. It states
# exactly what the checks already record, so nothing is invented.
DEFAULT_TIMING_NOTE = ("No timing signal for this play appears in this account's data - "
                       "confirm current plans and budget timing before positioning.")

# How many rewrites a play gets for a prose fault before it is published anyway.
MAX_PROSE_REWRITES = 2

# Used to title a discovery area, so it never inherits the model's sales title.
PLAY_DISPLAY_NAMES = {
    "workstation": "Z by HP Workstations",
    "poly": "Poly Collaboration",
    "pc": "HP Elite / Pro PCs",
    "print": "HP Enterprise Print / MPS",
    "daas": "HP Anyware / DaaS",
}

# Recency bands, matching the D1 scale already used by Live Signals.
RECENCY_BANDS = [(30, 10.0), (90, 8.0), (180, 6.0), (270, 4.0), (365, 2.0)]

PLAY_RESOURCE_URLS = {
    "workstation": "https://www.hp.com/us-en/workstations.html",
    "poly": "https://www.hp.com/us-en/poly.html",
    "pc": "https://www.hp.com/us-en/laptops.html",
    "print": "https://www.hp.com/us-en/services/workforce-solutions/document-printing/managed-print-services.html",
    "daas": "https://www.hp.com/us-en/services/workforce-solutions/workforce-computing/managed-device-services.html",
    "security": "https://www.hpwolf.com/",
}
DEFAULT_RESOURCE_URL = "https://www.hp.com/us-en/services/workforce-solutions/learning-hub.html"

# Which roles plausibly own each play family. Matched on word boundaries against
# the contact's title, and against the normalised department.
PLAY_OWNER_TITLE_TOKENS = {
    "workstation": ["engineering", "technology development", "business intelligence",
                    "analytics", "design", "product development", "architect", "research"],
    "poly": ["collaboration", "communications", "applications", "end user",
             "workplace", "operations"],
    "pc": ["end user", "procurement", "information technology", "service", "operations"],
    "print": ["procurement", "facilities", "administration", "general affairs", "operations"],
    "daas": ["information technology", "procurement", "infrastructure", "cloud", "operations"],
}
PLAY_OWNER_DEPARTMENTS = {
    "workstation": ["Engineering & Technical", "Information Technology"],
    "poly": ["Information Technology", "Operations"],
    "pc": ["Information Technology", "Operations"],
    "print": ["Operations", "Information Technology", "Finance"],
    "daas": ["Information Technology", "Engineering & Technical"],
}

# Signal vocabulary per play family. At least one cited evidence quote must
# contain one of these, or the trigger -> implication -> solution chain does not
# hold and the play is not generated. Product semantics, not account data.
PLAY_SIGNAL_TOKENS = {
    "workstation": ["design", "engineering", "cad", "simulation", "modeling", "modelling",
                    "3d", "rendering", "research and development", "analytics",
                    "data insights", "machine learning", "artificial intelligence",
                    "ai", "product development", "autocad", "catia", "solidworks"],
    "poly": ["collaboration", "meeting", "conferencing", "video", "remote", "hybrid",
             "flexible working", "communication", "communications", "workplace", "teams"],
    "pc": ["workforce", "employee", "workplace", "flexible working", "device", "laptop",
           "desktop", "endpoint", "productivity", "windows", "refresh"],
    "print": ["print", "printing", "document", "documents", "paper", "scanning",
              "records", "archive", "mfp", "workflow", "workflows"],
    # Device MANAGEMENT vocabulary only. "cloud" matched Adobe Creative Cloud and
    # Atlassian Cloud, which say nothing about managing a device estate; a bare
    # "fleet" or "asset" is worse on this account, where the intent file carries
    # vehicle-fleet maintenance and financial asset tokenisation.
    "daas": ["intune", "workspace one", "airwatch", "jamf", "manageengine", "sccm",
             "ivanti", "tanium", "azure ad", "okta", "device management",
             "endpoint management", "device lifecycle", "mobile device", "mdm",
             "uem", "it asset management", "endpoint"],
}

# Phrases that disqualify a corpus item for a play even when a token matched.
# Astra is an automotive conglomerate: "fleet maintenance software" is vehicles,
# "asset tokenization" is finance, "ai chips" is silicon. None is an IT estate.
PLAY_EXCLUDE_TOKENS = {
    "daas": ["vehicle", "vehicles", "fleet maintenance", "tokenization",
             "tokenisation", "ai chips"],
    "pc": ["vehicle", "vehicles", "server"],
    "workstation": ["vehicle", "vehicles"],
}


# Language that claims a buying moment the evidence cannot establish. Wrong
# whatever the subject.
OVERCLAIM_ALWAYS = [
    "now is the perfect time", "perfect time", "perfect fit", "the right time to",
    "is ready to", "are ready to", "guarantees", "ensures", "fully compatible",
    "must have", "ideal time",
]

# Wrong only when predicated on THIS ACCOUNT. "Their operations require advanced
# engineering capability" is an unsupported claim about Astra; "design workloads
# that require high-performance computing" describes a class of work and is fine.
# Banning the bare word deleted a valid play three runs in a row.
OVERCLAIM_IF_ABOUT_ACCOUNT = [
    "require", "requires", "required", "needs", "need to", "will need",
]

# Markers that a sentence is talking about the account rather than a workload,
# a product class or the seller.
ACCOUNT_SUBJECT_MARKERS = [
    "their", "they", "the account", "the company", "the organisation",
    "the organization", "the business", "the client", "the customer",
]


NO_CONTACT_NOTE = "No matching contact identified in supplied data."


def _token_present(token: str, text: str) -> bool:
    """Word-boundary containment. A plain substring test matches 'it' inside
    'quality' and 'digital', which produces nonsense matches."""
    if not token or not text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(token.lower()) + r"(?![a-z0-9])",
                     text.lower()) is not None


def _norm_text(s: str) -> str:
    """Whitespace- and case-insensitive form, for verbatim quote checking."""
    return " ".join(str(s or "").split()).lower()


def _has_overclaim(text: str, company_name: str = "") -> list[str]:
    """Overclaiming terms in generated prose.

    Checked per sentence: a mention of the account in one sentence must not
    condemn an unrelated sentence elsewhere in the same paragraph.
    """
    found: list[str] = []
    company_tokens = [w for w in _norm_text(company_name).split() if len(w) > 3]

    for sentence in re.split(r"[.;]", str(text or "")):
        s = _norm_text(sentence)
        if not s:
            continue

        for term in OVERCLAIM_ALWAYS:
            if term in s and term not in found:
                found.append(term)

        about_account = (
            any(m in s for m in ACCOUNT_SUBJECT_MARKERS)
            or any(tok in s for tok in company_tokens)
        )
        if about_account:
            for term in OVERCLAIM_IF_ABOUT_ACCOUNT:
                if _token_present(term, s) and term not in found:
                    found.append(term)

    return sorted(found)


def _recency_score(event_dt, now) -> float:
    if not event_dt:
        return 0.0
    age = (now - event_dt).days
    if age < 0:
        return 0.0
    for limit, score in RECENCY_BANDS:
        if age <= limit:
            return score
    return 0.0


# Plays whose scale is a function of the employee population rather than of a
# specialist team. Product semantics, not account data.
POPULATION_PLAYS = ("pc", "daas", "poly", "print")

# PLAY_SIGNAL_TOKENS is deliberately broad - it answers "does this evidence touch
# the area at all". Naming the estate needs product-level precision, or "windows"
# drags in Windows Server 2008 and "analytics" drags in Google Analytics.
PLAY_ESTATE_TOKENS = {
    "pc": ["microsoft windows os", "windows 10", "windows 11", "macos", "apple ios",
           "chromeos", "elitebook", "probook", "thinkpad", "latitude", "macbook"],
    "workstation": ["autocad", "autodesk", "catia", "solidworks", "blender",
                    "inventor", "3ds max", "maya", "ansys", "revit"],
    "poly": ["microsoft teams", "zoom", "webex", "g suite", "google workspace",
             "slack", "google meet", "microsoft office 365"],
    "print": ["canon", "epson", "xerox", "ricoh", "brother", "kyocera",
              "lexmark", "papercut", "konica"],
    "daas": ["intune", "workspace one", "airwatch", "jamf", "manageengine",
             "sccm", "ivanti", "tanium", "microsoft azure ad mfa", "okta"],
}
# Never counted as part of a client-device estate.
ESTATE_EXCLUDE = ("server", "datacenter", "data center")


def _build_scale_statement(play_key: str, verified: list[dict], corpus: list[dict],
                           firmo_row: dict, stack: list[str]) -> dict | None:
    """A qualitative scale statement for the play, assembled from named source
    fields only.

    HP_ABX_v3_final: "If a number cannot be reproduced from saved inputs and a
    clear formula, remove the number and keep the impact qualitative." There is
    no HP impact formula here, so this states the scale of the opportunity from
    the account's own record instead of projecting a saving.

    Returns the statement plus the field-by-field basis, or None when no source
    field carries anything.
    """
    fragments: list[str] = []
    basis: list[str] = []

    # -- population, from firmographics -------------------------------------
    employees = str(firmo_row.get("Number Of Employees Range") or "").strip()
    if employees and play_key in POPULATION_PLAYS:
        fragments.append(f"{employees} employee estate")
        basis.append(f"firmographics -> Number Of Employees Range ({employees})")

    # -- estate, from technographics ----------------------------------------
    tokens = PLAY_ESTATE_TOKENS.get(play_key, [])
    # Word boundaries, not substrings: "g suite" is inside "Adobe Digital
    # Marketing Suite" and "windows" is inside "Windows Server 2008".
    detected = [s for s in stack
                if any(_token_present(t, _norm_text(s)) for t in tokens)
                and not any(_token_present(x, _norm_text(s)) for x in ESTATE_EXCLUDE)]
    detected = list(dict.fromkeys(detected))
    if detected:
        shown = ", ".join(detected[:4])
        fragments.append(f"{shown} detected in the technology stack")
        basis.append(f"technographics -> Full Tech Stack ({len(stack)} items; "
                     f"{shown} detected)")
    elif stack:
        # Absence is absence from THIS export, never a claim about the account.
        fragments.append(f"no vendor for this area appears among the {len(stack)} "
                         f"technologies in this account's technographics export")
        basis.append(f"technographics -> Full Tech Stack ({len(stack)} items; "
                     f"no vendor for this area detected)")

    # -- demand, from the intent topics this play cites -----------------------
    intent_hits = [(v.get("composite_score"), v["quote"]) for v in verified
                   if v.get("composite_score")]
    if intent_hits:
        score, topic = max(intent_hits, key=lambda x: x[0])
        fragments.append(f'research interest in "{topic}" at composite {score:.0f}')
        basis.append(f'intent_score -> Topic "{topic}" (Composite Score {score:.0f})')

    # -- investment, from a news headline this play cites ---------------------
    for v in verified:
        if v.get("kind") == "trigger" and re.search(r"\d", v["quote"]) and v.get("dt"):
            fragments.append(f'reported in "{v["quote"]}"')
            basis.append(f'{v["dataset"]} -> {v["field"]} ("{v["quote"]}")')
            break

    if not fragments:
        return None

    return {
        "statement": "; ".join(fragments) + ".",
        "calculation_basis": "Composed from " + "; ".join(basis) + ".",
        "fields_used": len(basis),
    }


def _match_play_contacts(play_key: str, contacts: list[dict]) -> list[dict]:
    """Real contacts from this account's own roster who plausibly own the play.
    Never invents a persona."""
    tokens = PLAY_OWNER_TITLE_TOKENS.get(play_key, [])
    depts = PLAY_OWNER_DEPARTMENTS.get(play_key, [])
    scored = []
    for c in contacts:
        title = str(c.get("title") or "")
        dept = str(c.get("normalized_department") or "")
        title_hit = any(_token_present(t, title) for t in tokens)
        dept_hit = dept in depts
        if not (title_hit or dept_hit):
            continue
        rank = (2 if title_hit else 0) + (1 if dept_hit else 0)
        scored.append((rank, c.get("stakeholder_score") or 0, c))
    scored.sort(key=lambda x: (-x[0], -x[1]))

    out = []
    for rank, _s, c in scored[:2]:
        why = (f"{c.get('influence_type') or 'Contact'} in {c.get('normalized_department')}"
               f" whose title matches this play's remit.")
        out.append({
            "contact_id": c.get("contact_id"),
            "name": c.get("full_name"),
            "title": c.get("title"),
            "influence_type": c.get("influence_type"),
            "why": why,
        })
    return out


def _opportunity_fingerprint(corpus_items: list[str], contact_ids: list[str]) -> str:
    payload = {
        "prompt_version": OPPORTUNITY_PROMPT_VERSION,
        "evidence": sorted(corpus_items),
        "contacts": sorted(contact_ids),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def generate_opportunity_map_plays_with_gpt4o(account_id: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)

    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_records = _read_dataset_records(account_id, "intent_score")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")

    inst_doc = db["account_instructions"].find_one({"account_id": account_id})
    guard_doc = db["account_guardrails"].find_one({"account_id": account_id})
    instructions_text = inst_doc.get("instructions_text", "").strip() if inst_doc else ""
    guardrails_text = guard_doc.get("guardrails_text", "").strip() if guard_doc else ""

    # ---- deterministic evidence corpus -------------------------------------
    # Every quote the model returns is checked against this. Anything it cannot
    # match is dropped rather than published.
    corpus: list[dict] = []

    bus_desc = ""
    industry_val = employees_val = revenue_val = "N/A"
    if firmo_records:
        f = firmo_records[0]
        c_name = str(f.get("Company Name") or f.get("Name") or "").strip()
        if c_name:
            company_name = c_name
        bus_desc = str(f.get("Business Description") or "").strip()
        industry_val = str(f.get("Linkedin Industry Category")
                           or f.get("Naics Description") or "N/A").strip()
        employees_val = str(f.get("Number Of Employees Range") or "N/A").strip()
        revenue_val = str(f.get("Yearly Revenue Range") or "N/A").strip()
        if bus_desc:
            corpus.append({"text": bus_desc, "dataset": "firmographics",
                           "field": "Business Description", "kind": "context"})
        for label, val in (("Number Of Employees Range", employees_val),
                           ("Yearly Revenue Range", revenue_val)):
            if val and val != "N/A":
                corpus.append({"text": val, "dataset": "firmographics", "field": label,
                               "kind": "context"})

    full_tech_stack = []
    if techno_records:
        raw_stack = str(techno_records[0].get("Full Tech Stack") or "").strip()
        full_tech_stack = [s.strip() for s in raw_stack.split(",") if s.strip()]
        for item in full_tech_stack:
            corpus.append({"text": item, "dataset": "technographics",
                           "field": "Full Tech Stack", "kind": "context"})

    intent_rows = []
    for r in intent_records:
        name = str(r.get("Topic") or "").strip()
        try:
            score = float(str(r.get("Composite Score") or 0).strip())
        except (TypeError, ValueError):
            score = 0.0
        if name:
            intent_rows.append({"topic": name, "score": score})
    intent_rows.sort(key=lambda x: -x["score"])
    for r in intent_rows[:10]:
        corpus.append({"text": r["topic"], "dataset": "intent_score", "field": "Topic",
                       "composite_score": r["score"], "kind": "trigger"})

    news_triggers, seen = [], set()
    for row in gnews_records + events_records:
        headline = str(row.get("event_headline") or row.get("news_announcements")
                       or row.get("summary") or row.get("title") or "").strip()
        if not headline or headline.lower() in seen:
            continue
        seen.add(headline.lower())
        raw_date = str(row.get("event_date") or row.get("effective_date")
                       or row.get("found_at") or "").strip()
        dt = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(raw_date[:10], fmt).replace(tzinfo=timezone.utc)
                break
            except (ValueError, TypeError):
                continue
        news_triggers.append({
            "headline": headline, "date": raw_date, "dt": dt,
            "url": str(row.get("event_url") or "").strip(),
        })
    news_triggers.sort(key=lambda t: t["dt"] or datetime.min.replace(tzinfo=timezone.utc),
                       reverse=True)
    for t in news_triggers[:10]:
        corpus.append({"text": t["headline"], "dataset": "google_news / news_events",
                       "field": "event_headline", "date": t["date"], "dt": t["dt"],
                       "url": t["url"], "kind": "trigger"})

    # Only demand a trigger citation when the account actually has triggers to
    # cite - an account with no news or intent data must not be blanked out.
    has_any_trigger_available = any(c.get("kind") == "trigger" for c in corpus)

    # Grounding corpus: every cell of every dataset this feature reads. Used to
    # reject a number, URL or product name the account's own data never carried.
    ground = build_corpus({
        "firmographics": firmo_records,
        "technographics": techno_records,
        "intent_score": intent_records,
        "google_news": gnews_records,
        "news_events": events_records,
    })
    report = GroundingReport(ground, [
        "title", "hp_capability", "inference", "recommended_cta",
        "proof_point", "source_url", "hp_products",
    ])

    corpus_blob = " || ".join(_norm_text(c["text"]) for c in corpus)
    corpus_digits = re.sub(r"[,\s]", "", corpus_blob)

    # ---- the account's real roster, for entry paths -------------------------
    grid = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "stakeholder_contacts_grid"})
    roster = ((grid or {}).get("data") or {}).get("contacts") or []

    fingerprint = _opportunity_fingerprint(
        [c["text"] for c in corpus], [str(c.get("contact_id")) for c in roster])

    existing = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "opportunity_narrative_plays"})
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("evidence_fingerprint") == fingerprint):
        return existing

    # ---- which plays the evidence can actually support -----------------------
    play_menu = {}
    for pk, tokens in PLAY_SIGNAL_TOKENS.items():
        excludes = PLAY_EXCLUDE_TOKENS.get(pk, [])
        hits = [c for c in corpus
                if any(_token_present(tok, _norm_text(c["text"])) for tok in tokens)
                and not any(_token_present(x, _norm_text(c["text"])) for x in excludes)]
        has_signal = any(h.get("kind") == "trigger" for h in hits)
        # Evidence of ANY kind makes a play eligible. Whether it also carries a
        # timing trigger is check 2's job, and failing that demotes rather than
        # deletes - gating eligibility on it would drop the play instead.
        play_menu[pk] = {
            "eligible": bool(hits),
            "has_signal": has_signal,
            "items": hits[:6],
        }

    # Resolved here, before the prompt, so the model can write to the function
    # that owns the topic instead of ending the chain at a product.
    play_contacts = {pk: _match_play_contacts(pk, roster) for pk in play_menu}

    menu_lines = []
    for pk, info in play_menu.items():
        if not info["eligible"]:
            menu_lines.append(f"- {pk.upper()}: NO SUPPORTING EVIDENCE - do not propose this play.")
            continue
        quotes = "; ".join(f'"{h["text"][:110]}"' for h in info["items"])
        line = f"- {pk.upper()}: evidence you may cite -> {quotes}"
        owners = play_contacts.get(pk) or []
        if owners:
            who = "; ".join(f'{c["name"]} ({c["title"]})' for c in owners)
            line += NL + f"    topic owners at this account: {who}"
        if not info["has_signal"]:
            line += NL + ("    NO TIMING SIGNAL for this play - write its inference as "
                          "exploratory and say so plainly.")
        menu_lines.append(line)

    eligible_keys = [k for k, v in play_menu.items() if v["eligible"]]

    # ---- prompt -------------------------------------------------------------
    intent_lines = [f"- {r['topic']} (Composite Score: {r['score']:.0f})" for r in intent_rows[:10]]
    news_lines = [f"- {t['headline']} ({t['date'] or 'undated'})"
                  + (f" | URL: {t['url']}" if t["url"] else " | URL: none")
                  for t in news_triggers[:10]]

    system_prompt = f"""You are an expert ABM strategist for HP Inc. ("HP"). You identify HP hardware and solution opportunity plays for {company_name}.

ACCOUNT OVERVIEW:
- Company: {company_name}
- Industry: {industry_val}
- Revenue Range: {revenue_val}
- Employee Count Range: {employees_val}
- Business Description: {bus_desc if bus_desc else 'N/A'}

INSTALLED TECHNOLOGY STACK ({len(full_tech_stack)} items):
{', '.join(full_tech_stack[:40]) if full_tech_stack else 'None detected in the supplied exports.'}

INTENT RESEARCH SURGES:
{chr(10).join(intent_lines) if intent_lines else 'None detected.'}

NEWS AND TRIGGER EVENTS:
{chr(10).join(news_lines) if news_lines else 'None detected.'}

ACCOUNT-SPECIFIC CUSTOM INSTRUCTIONS:
{instructions_text if instructions_text else 'None provided.'}

ACCOUNT-SPECIFIC MANDATORY GUARDRAILS:
{guardrails_text if guardrails_text else 'None provided.'}

THE ONE RULE THAT MATTERS: KEEP THE THREE KINDS OF STATEMENT APART.
  ACCOUNT EVIDENCE  - a fact about {company_name} that is written above. Nothing else qualifies.
  HP CAPABILITY     - what an HP product does. True of HP everywhere, not a fact about this account.
  INFERENCE         - your bridge from one to the other. Always hedged.
Never present an HP capability, a product-compatibility claim, or a general business assumption as account evidence. "Their operations require advanced engineering capability" is NOT evidence - nothing above says it. "<a product named in the TECHNOLOGY STACK above> appears in the installed technology stack" IS evidence. Quote the data, do not characterise the business.

EVIDENCE MUST INCLUDE A SIGNAL. The Business Description and the technology stack are CONTEXT. The INTENT RESEARCH SURGES and the NEWS AND TRIGGER EVENTS are SIGNALS. Every play must quote AT LEAST ONE signal, and should also quote context. A play built only on the company description is context with no trigger and will be rejected.

EVIDENCE AVAILABLE PER PLAY - computed from the data above, before you were asked. Propose ONLY the plays marked eligible, and cite from their listed evidence:
{chr(10).join(menu_lines)}

SECURITY TOOLING IS NOT PROOF OF A MANAGEMENT PROBLEM. Endpoint protection, MFA and identity products establish that the account has a security posture. They do NOT establish that device lifecycle management is inefficient, costly or painful. Where a play's evidence is security tooling, say what it does establish and what it does not, then frame the management angle as something to explore.
  GOOD: "indicates an established focus on endpoint security and secure access; combined with the 10,001+ employee estate this may warrant exploring whether device lifecycle management could be simplified".
  BAD: "suggests a focus on efficient device management" - the evidence does not say that.

WHERE A PLAY HAS NO TIMING SIGNAL: its evidence block above is marked NO TIMING SIGNAL. Do NOT imply timing for it and do NOT reach for an unrelated intent topic to manufacture one. Write its inference as exploratory: state what the estate evidence shows, say plainly that this account's data carries no timing signal for it, and name what a seller would need to confirm. "Worth exploring, subject to confirming X" is the correct register. "Now is the time", "the window is open", "immediate" and "urgent" are failures.

WHERE TOPIC OWNERS ARE LISTED for a play, close the chain onto that function: say what the named remit would be weighing, so the seller knows whose problem this is. Use the titles exactly as given. Never invent a name or a title, never say what a person thinks, wants or has decided - the owner is the audience for the play, not a source for it.

THE MIDDLE STEP MUST BE EVIDENCED. It is not enough that a signal exists and an HP product exists. At least one quoted signal must be ABOUT something the play speaks to - design and analytics workloads for workstations, meetings and collaboration for Poly, the employee device fleet for PCs, documents and printing for Print/MPS, device lifecycle management for DaaS. Stacking unrelated signals ("invests in property", "competes in electric vehicles") behind a product is the failure this rule exists to stop.

ELIGIBILITY - generate a play ONLY when this chain holds:
  a named signal that appears above -> a business implication -> an HP solution
Return UP TO 5 plays. Returning 3 well-evidenced plays is BETTER than 5 with one invented. If a product family has no honest chain, leave it out entirely. Do not pad.

FIELDS:
- "play_key": one of workstation | poly | pc | print | daas
- "title": the play name.
- "account_evidence": a list of 1-4 items, each {{"quote": "...", "statement": "..."}}.
    "quote" MUST be copied VERBATIM from the ACCOUNT OVERVIEW, TECHNOLOGY STACK, INTENT SURGES or NEWS above - an exact substring. It is checked against the source data and any item whose quote cannot be found is DELETED.
    "statement" is your one-line reading of that quote. It must not add any fact the quote does not carry.
- "hp_capability": 1-2 sentences on what the HP line does. This is HP product capability, not an account fact. Do not mention {company_name} in this field.
- "inference": 2-3 hedged sentences bridging the evidence to the capability. This is where the opportunity argument goes.
- "hp_products": HP product names.
- "quantified_impact": an exact figure that appears VERBATIM above, copied character for character from a line in the evidence, or null. It is re-verified against the source data. A figure is a SOURCED ACCOUNT SIGNAL, never an HP projection, and never by itself evidence of demand for a product - if you cite one, say what it does and does not establish.
- "proof_point" and "source_url": copied EXACTLY from the NEWS list above, or null. Never invent a URL.
- "timing_note": REQUIRED for any play whose evidence block is marked NO TIMING SIGNAL, otherwise null. One sentence naming what a seller would need to confirm before timing this, e.g. "no refresh cycle, budget window or project is visible in this account's data - confirm the current device refresh schedule before positioning". Never imply timing here.
- "owner_angle": REQUIRED whenever topic owners are listed for the play, otherwise null. One sentence on what that named remit would be weighing. Use the title exactly as given. Never say what the person thinks, wants or has decided.
- "entry_path": {{"timeline": "0-90 days | 90-180 days", "recommended_cta": "..."}}
    Do NOT return target buyers. The people are resolved from this account's own contact records, not by you.

LANGUAGE - these are failures, not style preferences:
- Never write "require", "will need", "is ready to", "needs", "now is the perfect time", "perfect", "ideal" or "fully compatible" about this account.
- Use "may indicate", "could create an opportunity", "suggests", "is worth exploring".
- Never claim a procurement window is open unless something above says so.

Output JSON:
{{"opportunity_plays": [{{"play_key": "...", "title": "...", "account_evidence": [{{"quote": "...", "statement": "..."}}], "hp_capability": "...", "inference": "...", "hp_products": ["..."], "quantified_impact": null, "proof_point": "...", "source_url": null, "timing_note": null, "owner_angle": null, "entry_path": {{"timeline": "0-90 days", "recommended_cta": "..."}}}}]}}
"""

    user_prompt = (
        f"Return one opportunity play for each of these play_key values, and no others: "
        f"{', '.join(eligible_keys) if eligible_keys else 'none'}. "
        f"Cite only the evidence listed for that play. Omit any play whose chain does not hold."
    )

    if not eligible_keys:
        logger.warning("opportunity map: no play family has supporting evidence for %s",
                       company_name)

    cleaned_plays: list[dict] = []
    dropped: list[str] = []
    retry_notes: dict = {}
    language_attempts: dict = {}
    # The retry asks the model to fix one fault, and it answers with a slimmer
    # object - dropping fields the first pass had already got right. Keep the
    # first answer so those fields survive the correction.
    first_pass_raw: dict = {}

    def _process(raw_plays) -> None:
        """One validation pass. Appends survivors to cleaned_plays and records
        why anything else was rejected."""
        if not isinstance(raw_plays, list):
            return
        done = {c["play_key"] for c in cleaned_plays}
        for p in raw_plays:
            if not isinstance(p, dict):
                continue
            if str(p.get("play_key") or "").strip().lower() in done:
                continue

            pk_early = str(p.get("play_key") or "").strip().lower()
            prior = first_pass_raw.get(pk_early)
            if prior:
                # Retry values win; anything it omitted falls back to this play's
                # own earlier answer. entry_path needs a nested merge or a partial
                # one still wipes timeline and recommended_cta.
                merged_entry = {**(prior.get("entry_path") or {}),
                                **(p.get("entry_path") or {})}
                p = {**prior, **p, "entry_path": merged_entry}
            elif pk_early:
                first_pass_raw[pk_early] = p
            play_key = str(p.get("play_key") or "").strip().lower()
            title = str(p.get("title") or "").strip()
            if not play_key or not title:
                continue

            # --- validate every evidence quote against the source corpus ----
            verified = []
            for item in (p.get("account_evidence") or []):
                if not isinstance(item, dict):
                    continue
                quote = str(item.get("quote") or "").strip()
                if not quote:
                    continue
                # A quote may be a comma-joined group of stack items; match each
                # part so a real citation is not thrown away on formatting.
                parts = [x.strip() for x in quote.split(",") if x.strip()] or [quote]
                matched_parts, match = [], None
                for part in parts:
                    # Intent lines are shown to the model with a "(Composite Score: N)"
                    # suffix that is not part of the stored topic - strip it back off.
                    part = re.sub(r"\s*\(composite score:[^)]*\)\s*$", "", part, flags=re.I).strip()
                    # The model sometimes prefixes a quote with the prompt's own
                    # section heading. That heading is ours, not the account's
                    # data, so it must not be stored as a verbatim quote.
                    part = re.sub(
                        r"^(installed technology stack|intent research surges|"
                        r"news and trigger events|account overview|business description)"
                        r"\s*(\([^)]*\))?\s*:\s*", "", part, flags=re.I).strip()
                    np = _norm_text(part)
                    if not np:
                        continue
                    # Bidirectional: the quote may be a fragment of a long cell, or a
                    # cell may be a fragment of a longer quoted line. The reverse
                    # direction needs a length floor and a word boundary - the tech
                    # stack contains one-letter entries like "C" and "R", which would
                    # otherwise match almost any sentence.
                    hits = []
                    for c in corpus:
                        ct = _norm_text(c["text"])
                        if not ct:
                            continue
                        if np in ct:
                            hits.append((len(ct), c))
                        elif len(ct) >= 6 and _token_present(ct, np):
                            hits.append((len(ct), c))
                    # Prefer the most specific (longest) matching cell.
                    hit = max(hits, key=lambda x: x[0])[1] if hits else None
                    if hit:
                        matched_parts.append(part)
                        # Prefer a trigger-class source when one of the parts is a trigger.
                        if match is None or (hit.get("kind") == "trigger"
                                             and match.get("kind") != "trigger"):
                            match = hit
                if not match:
                    dropped.append(f"{play_key}: unverified quote {quote[:60]!r}")
                    continue
                verified.append({
                    "quote": ", ".join(matched_parts),
                    "statement": str(item.get("statement") or "").strip(),
                    "dataset": match["dataset"],
                    "field": match["field"],
                    "kind": match.get("kind", "context"),
                    "composite_score": match.get("composite_score"),
                    "dt": match.get("dt"),
                })

            if not verified:
                dropped.append(f"{play_key}: no verifiable evidence - play dropped")
                continue

            # The chain is "a named SIGNAL -> implication -> HP solution". A
            # business description is context, not a signal, so a play carrying
            # only context has no trigger and does not qualify.
            # Check 2 - a current timing trigger. Failing it demotes the play,
            # it does not delete it: "a partial tile may be retained only if
            # missing fields are explicitly marked".
            has_trigger = any(v.get("kind") == "trigger" for v in verified)
            # Only ask for a trigger when this play's own eligible evidence
            # actually contains one. Asking otherwise is an instruction to
            # fabricate a timing signal.
            if (not has_trigger
                    and play_menu.get(play_key, {}).get("has_signal")):
                retry_notes.setdefault(play_key, (
                    "you cited only context (business description or technology stack). "
                    "Cite at least one INTENT SURGE or NEWS EVENT from this play's listed evidence"))

            # The middle step of the chain must be evidenced, not asserted: at
            # least one cited quote has to be topically about something this
            # play speaks to. "Invests in low-cost apartments" does not make a
            # printing case, however many such quotes are stacked up.
            # Check 3 - HP fit. Also demotes rather than deletes.
            signal_tokens = PLAY_SIGNAL_TOKENS.get(play_key, [])
            play_excludes = PLAY_EXCLUDE_TOKENS.get(play_key, [])
            # An excluded quote cannot carry the fit check for this play.
            fit_quotes = [v["quote"] for v in verified
                          if not any(_token_present(x, _norm_text(v["quote"]))
                                     for x in play_excludes)]
            evidence_blob = _norm_text(" ".join(fit_quotes))
            hp_fit = bool(signal_tokens) and any(_token_present(tok, evidence_blob)
                                                 for tok in signal_tokens)
            if signal_tokens and not hp_fit:
                dropped.append(f"{play_key}: cited evidence is not topically connected "
                               f"to this play - retained below, marked")

            # --- overclaim guard on the generated prose ---------------------
            prose = " ".join([str(p.get("inference") or ""),
                              " ".join(v["statement"] for v in verified)])
            overclaims = _has_overclaim(prose, company_name)
            if overclaims:
                # First and second attempts go back for a rewrite. After that the
                # play is published anyway with the fault recorded: a wording
                # problem is a far weaker reason to withhold a play than a failed
                # evidence check, and silently deleting one was losing valid
                # opportunities.
                if language_attempts.get(play_key, 0) < 2:
                    language_attempts[play_key] = language_attempts.get(play_key, 0) + 1
                    dropped.append(f"{play_key}: overclaim {overclaims} - sent for rewrite")
                    retry_notes[play_key] = (
                        "you used the banned words " + ", ".join(sorted(set(overclaims)))
                        + " - rewrite with calibrated language")
                    continue
                language_warning = overclaims
                dropped.append(f"{play_key}: overclaim {overclaims} - retained with a "
                               f"language warning after {language_attempts[play_key]} rewrites")
                logger.warning("opportunity map: %s kept despite overclaim terms %s",
                               play_key, overclaims)
            else:
                language_warning = None

            # --- quantified impact, re-verified ------------------------------
            impact_raw = p.get("quantified_impact")
            impact_val, impact_state, impact_source = None, "none", None
            if impact_raw and any(ch.isdigit() for ch in str(impact_raw)):
                digits = re.sub(r"[,\s]", "", _norm_text(impact_raw))
                # The figure must come from evidence THIS play cites, and that
                # evidence must itself be topically relevant. Otherwise a
                # dividend headline ends up as the "impact" on a device play.
                relevant_quotes = [
                    v["quote"] for v in verified
                    if not signal_tokens
                    or any(_token_present(tok, _norm_text(v["quote"])) for tok in signal_tokens)
                ]
                cited_digits = re.sub(r"[,\s]", "", _norm_text(" || ".join(relevant_quotes)))
                if digits and digits in cited_digits:
                    impact_val = str(impact_raw).strip()
                    impact_state = "sourced_signal"
                    hit = next((c for c in corpus
                                if re.sub(r"[,\s]", "", _norm_text(c["text"])).find(digits) >= 0), None)
                    if hit:
                        impact_source = f'{hit["dataset"]} -> {hit["field"]}'
                elif digits and digits in corpus_digits:
                    dropped.append(f"{play_key}: figure {impact_raw!r} is real but not from "
                                   f"evidence relevant to this play - not shown")
                else:
                    dropped.append(f"{play_key}: unverified figure {impact_raw!r}")

            # --- deterministic priority --------------------------------------
            cited_dts = [v["dt"] for v in verified if v.get("dt")]
            newest = max(cited_dts) if cited_dts else None
            cited_intent = [v["composite_score"] for v in verified if v.get("composite_score")]

            contacts = play_contacts.get(play_key) or []
            scale = _build_scale_statement(
                play_key, verified, corpus,
                firmo_records[0] if firmo_records else {}, full_tech_stack)

            checks = {
                "verified_evidence": bool(verified),
                "timing_trigger": bool(has_trigger),
                "hp_fit": bool(hp_fit) if signal_tokens else True,
            }
            checks_met = sum(1 for v in checks.values() if v)
            missing_checks = [k for k, v in checks.items() if not v]
            recency = _recency_score(newest, now)

            entry_p = p.get("entry_path") or {}

            timing_note = str(p.get("timing_note") or "").strip() or None
            owner_angle = str(p.get("owner_angle") or "").strip() or None

            # A play with no timing signal must say what would need confirming,
            # rather than quietly reading as though timing were established.
            if not has_trigger and not timing_note:
                if language_attempts.get(play_key, 0) < MAX_PROSE_REWRITES:
                    language_attempts[play_key] = language_attempts.get(play_key, 0) + 1
                    dropped.append(f"{play_key}: no timing signal and no timing_note - sent for rewrite")
                    retry_notes.setdefault(play_key, (
                        "this play has NO TIMING SIGNAL in its evidence. Return a "
                        "timing_note naming what a seller would need to confirm, and keep "
                        "the inference exploratory"))
                    continue
                # Evidence and fit are sound; only the prose is missing. Publish
                # with a note Python composes, rather than deleting the play.
                timing_note = DEFAULT_TIMING_NOTE
                dropped.append(f"{play_key}: no timing_note returned after "
                               f"{language_attempts[play_key]} rewrites - default note applied")
                logger.warning("opportunity map: %s published with the default timing note",
                               play_key)

            if not str(entry_p.get("recommended_cta") or "").strip():
                if language_attempts.get(play_key, 0) < MAX_PROSE_REWRITES:
                    language_attempts[play_key] = language_attempts.get(play_key, 0) + 1
                    dropped.append(f"{play_key}: no recommended_cta - sent for rewrite")
                    retry_notes.setdefault(play_key, (
                        "entry_path.recommended_cta was missing. Return it: the concrete "
                        "next action for this play, naming the contact or function to "
                        "approach"))
                    continue
                dropped.append(f"{play_key}: no recommended_cta after "
                               f"{language_attempts[play_key]} rewrites - published without it")

            # Where a real owner was resolved, the chain must reach them.
            if (play_contacts.get(play_key) or []) and not owner_angle:
                if language_attempts.get(play_key, 0) < MAX_PROSE_REWRITES:
                    language_attempts[play_key] = language_attempts.get(play_key, 0) + 1
                    dropped.append(f"{play_key}: owners resolved but no owner_angle - sent for rewrite")
                    retry_notes.setdefault(play_key, (
                        "topic owners were listed for this play. Return an owner_angle "
                        "saying what that named remit would be weighing"))
                    continue
                # The contacts are still on the record and still render; only the
                # sentence about them is absent. That is not worth losing a play.
                dropped.append(f"{play_key}: no owner_angle returned after "
                               f"{language_attempts[play_key]} rewrites - published without it")

            # ---- grounding gate ------------------------------------------------
            proof_point = str(p.get("proof_point") or "").strip() or None
            source_url = str(p.get("source_url") or "").strip() or None
            cta = str(entry_p.get("recommended_cta") or "").strip()
            capability = str(p.get("hp_capability") or "").strip()
            inference = str(p.get("inference") or "").strip()

            bad_nums, bad_urls = check_text(
                ground, report, play_key,
                title, capability, inference, cta, proof_point or "", source_url or "",
                timing_note or "", owner_angle or "")

            if bad_nums:
                dropped.append(f"{play_key}: unsourced number(s) {bad_nums} - sent for rewrite")
                retry_notes[play_key] = (
                    "you used the number(s) " + ", ".join(bad_nums)
                    + " which appear nowhere in this account's data - remove them or "
                      "quote a figure that does appear")
                continue

            if bad_urls:
                # A link the uploads never carried is stripped rather than shown.
                dropped.append(f"{play_key}: unsourced URL(s) {bad_urls} - stripped")
                if source_url and source_url in bad_urls:
                    source_url = None
                proof_point = strip_unsourced_urls(ground, proof_point) if proof_point else None
                capability = strip_unsourced_urls(ground, capability)
                inference = strip_unsourced_urls(ground, inference)
                cta = strip_unsourced_urls(ground, cta)

            # HP product names are an allow-list, never free text.
            products, bad_products = filter_enum_list(p.get("hp_products"), HP_PRODUCT_LINES)
            if bad_products:
                report.enum_rejected.extend(f"{play_key}: {b}" for b in bad_products)
                dropped.append(f"{play_key}: product(s) outside the HP line list {bad_products} - dropped")

            cleaned_plays.append({
                "play_key": play_key,
                "category_label": play_key.upper(),
                "title": title,
                "severity": f"{checks_met} of 3 checks",
                "checks": checks,
                "checks_met": checks_met,
                "missing_checks": missing_checks,
                "trigger_recency": recency,
                "hp_proof_point": None,
                "hp_proof_point_note": NO_PROOF_POINT,
                "account_evidence": [{k: v for k, v in item.items() if k != "dt"}
                                     for item in verified],
                "hp_capability": capability,
                "inference": inference,
                "timing_note": timing_note,
                "owner_angle": owner_angle,
                "language_warning": language_warning,
                "hp_products": products,
                "hp_resource_url": PLAY_RESOURCE_URLS.get(play_key, DEFAULT_RESOURCE_URL),
                "quantified_impact": impact_val,
                "quantified_impact_state": impact_state,
                "quantified_impact_source": impact_source,
                # Composed in Python from named fields; the model never sees or
                # supplies these, so they cannot drift.
                "scale_statement": (scale or {}).get("statement"),
                "calculation_basis": (scale or {}).get("calculation_basis"),
                "scale_fields_used": (scale or {}).get("fields_used", 0),
                "proof_point": proof_point,
                "source_url": source_url,
                "entry_path": {
                    "timeline": str(entry_p.get("timeline") or "0-90 days"),
                    "target_contacts": contacts,
                    "target_buyers_source": "prospect_contacts" if contacts else "no_match",
                    "no_contact_note": None if contacts else NO_CONTACT_NOTE,
                    "recommended_cta": cta,
                },
            })

    if dropped:
        # Always report why a play did not survive - the failure path returns the
        # previous document, which would otherwise discard these reasons.
        logger.warning("opportunity map: dropped %d item(s): %s", len(dropped), dropped)

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)
    _process((llm_res or {}).get("opportunity_plays") if isinstance(llm_res, dict) else None)

    # One bounded retry for plays rejected purely for language. The model is told
    # exactly which words it used, rather than being asked again blindly.
    for _round in range(2):
        if not retry_notes:
            break
        faults = NL.join(f"- {k.upper()}: {v}" for k, v in sorted(retry_notes.items()))
        retry_system = system_prompt + (
            NL + NL + "RETRY - YOUR PREVIOUS ANSWER WAS REJECTED." + NL
            + "Each play below was discarded for the stated reason. Fix exactly that, "
              "and return the COMPLETE play object for it - every field, including "
              "entry_path.timeline and entry_path.recommended_cta - carrying the "
              "parts that were already correct through unchanged." + NL
            + faults + NL
            + "Keep the same evidence where it was accepted. Use calibrated language "
              "(\"may indicate\", \"could create an opportunity\", \"suggests\", "
              "\"is worth exploring\") and never a banned word."
        )
        retry_user = ("Return JSON containing only these plays: "
                      + ", ".join(sorted(retry_notes)) + ".")
        retry_notes = {}
        retry_res = generate_gpt4o_json_completion(retry_system, retry_user)
        _process((retry_res or {}).get("opportunity_plays") if isinstance(retry_res, dict) else None)

    # "Compare narrative rankings for duplicate plays: combine two tiles that use
    # the same trigger, need and HP solution." Same trigger set + same play
    # family is that condition; the survivor keeps both tiles' evidence.
    merged: list[dict] = []
    for play in cleaned_plays:
        triggers = tuple(sorted(_norm_text(v["quote"]) for v in play["account_evidence"]
                                if v.get("kind") == "trigger"))
        key = (play["play_key"], triggers)
        twin = next((m for m in merged if m["_merge_key"] == key), None)
        if twin:
            seen_q = {_norm_text(v["quote"]) for v in twin["account_evidence"]}
            for v in play["account_evidence"]:
                if _norm_text(v["quote"]) not in seen_q:
                    twin["account_evidence"].append(v)
            twin["merged_from"] = twin.get("merged_from", 1) + 1
            dropped.append(f'{play["play_key"]}: merged into an earlier tile with the '
                           f'same trigger and solution')
            continue
        play["_merge_key"] = key
        merged.append(play)
    for m in merged:
        m.pop("_merge_key", None)
    cleaned_plays = merged

    # Spec ordering: all three checks first, then those missing one, tie-broken
    # by how current the cited trigger is.
    published = {p["play_key"] for p in cleaned_plays} | {a["play_key"] for a in discovery_areas} \
        if False else {p["play_key"] for p in cleaned_plays}
    withheld = sorted({d.split(":")[0].strip() for d in dropped} - published)
    if withheld:
        logger.warning("opportunity map: %d play(s) withheld entirely: %s",
                       len(withheld), withheld)

    cleaned_plays.sort(key=lambda x: (-x["checks_met"], -x.get("trigger_recency", 0.0)))
    cleaned_plays = cleaned_plays[:MAX_PLAYS]

    # A play that fails the HP-fit check is not an HP opportunity. It is retained
    # as a discovery area - what we can see, what is missing, what to confirm -
    # with the sales narrative stripped, because the evidence has not earned one.
    discovery_areas: list[dict] = []
    opportunities: list[dict] = []
    for play in cleaned_plays:
        if play["checks"].get("hp_fit", True):
            opportunities.append(play)
            continue
        entry = dict(play)
        entry["title"] = (PLAY_DISPLAY_NAMES.get(play["play_key"], play["play_key"].upper())
                          + " - no supporting evidence in this account's data")
        for field in ("inference", "hp_capability", "hp_resource_url",
                      "owner_angle", "quantified_impact", "quantified_impact_source",
                      "proof_point", "source_url"):
            entry[field] = None
        entry["quantified_impact_state"] = "none"
        entry["hp_products"] = []
        ep = dict(entry.get("entry_path") or {})
        ep["recommended_cta"] = None
        entry["entry_path"] = ep
        discovery_areas.append(entry)
        dropped.append(f'{play["play_key"]}: fails the HP-fit check - moved to '
                       f'discovery areas, sales narrative removed')
    cleaned_plays = opportunities

    if cleaned_plays or discovery_areas:
        plays_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_narrative_plays",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "evidence_fingerprint": fingerprint,
                "total_plays_count": len(cleaned_plays),
                "opportunity_plays": cleaned_plays,
                "discovery_count": len(discovery_areas),
                "discovery_areas": discovery_areas,
                "dropped": dropped,
                "grounding_report": report.as_dict(),
            },
            "source_datasets": ["firmographics", "technographics", "intent_score",
                                "google_news", "news_events", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        if existing and existing.get("status") == "available":
            return existing
        plays_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_narrative_plays",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "evidence_fingerprint": None,
                "total_plays_count": 0,
                "opportunity_plays": [],
                "dropped": dropped,
                "notice": ("No opportunity play met the evidence threshold, or generation "
                           "requires OPENAI_API_KEY. No plays are invented."),
            },
            "source_datasets": ["firmographics", "technographics", "intent_score",
                                "google_news", "news_events", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_narrative_plays"},
        {"$set": plays_payload},
        upsert=True
    )
    return plays_payload


@requires_local_datasets(
    "firmographics", "google_news", "intent_score", "news_events", "prospect_contacts", "technographics",
)
def extract_solution_narrative_opportunity_map(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_records = _read_dataset_records(account_id, "intent_score")
    
    results = []

    # 1. Widget: opportunity_context_card
    bus_desc = ""
    if firmo_records and len(firmo_records) > 0:
        bus_desc = (str(firmo_records[0].get("Business Description") or "")).strip()

    tech_stack_items = []
    if techno_records and len(techno_records) > 0:
        raw_stack = (str(techno_records[0].get("Full Tech Stack") or "")).strip()
        if raw_stack:
            tech_stack_items = [s.strip() for s in raw_stack.split(",") if s.strip()]

    top_intent_topics = []
    for r in intent_records:
        t_name = (str(r.get("Topic") or "")).strip()
        c_score_raw = (str(r.get("Composite Score") or "0")).strip()
        try:
            c_score = int(float(c_score_raw))
        except (ValueError, TypeError):
            c_score = 0

        if t_name:
            top_intent_topics.append({
                "topic_name": t_name,
                "composite_score": c_score
            })

    top_intent_topics.sort(key=lambda x: x["composite_score"], reverse=True)

    has_context = bool(bus_desc or tech_stack_items or top_intent_topics)

    if has_context:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "business_description": bus_desc,
                "full_tech_stack_sample": tech_stack_items,
                "total_tech_items_count": len(tech_stack_items),
                "top_intent_topics": top_intent_topics[:10],
                "total_intent_topics_count": len(top_intent_topics)
            },
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_context_card"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # 2. Widget: opportunity_trigger_signals
    news_res = extract_recent_news_signals(account_id)
    news_signals = news_res[0]["data"].get("signals", []) if (news_res and news_res[0]["status"] == "available") else []

    if news_signals:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_trigger_count": len(news_signals),
                "triggers": news_signals
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_trigger_signals"},
        {"$set": triggers_payload},
        upsert=True
    )
    results.append(triggers_payload)

    # 3. Widget: opportunity_narrative_plays
    # Cached inside the generator on a fingerprint of the evidence set, so this
    # costs no model call unless the uploaded data changed.
    results.append(generate_opportunity_map_plays_with_gpt4o(account_id))

    return results
