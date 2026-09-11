import os
import io
import re
import csv
import json
import logging
import pandas as pd
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
import html as _html
import hashlib
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.grounding import (
    build_corpus, check_text, strip_unsourced_urls, filter_enum_list,
    GroundingReport, HP_PRODUCT_LINES,
)
# Imported, not copied: a role-type proxy is judged by the same HP-relevance,
# seniority and department rules Stakeholder Map applies to a named contact
# (spec Section 3). stakeholder_map itself is not modified.
from app.services.extractors.stakeholder_map import (
    score_hp_relevance, hp_relevance_band, seniority_band, normalize_department,
    NON_IT_TITLE_CAP, UNASSIGNED_DEPT, HP_RELEVANCE_FLOOR,
)

logger = logging.getLogger(__name__)

# --- Persona sources (spec Section 7) ------------------------------------------
# Row 1  named persona      <- Stakeholder Map grid, Source A rows only
# Row 2  role-type proxy    <- job_openings (title, normalized_title, seniority)
# Row 3  company context    <- firmographics
# The contacts export is empty in every verified test, so in production row 2
# is the path that carries the persona, not a fallback.

NAMED_PERSONA_MAX = 8
ROLE_PROXY_MAX = 5

# Generic HP ABM audiences. Not sourced from any dataset - kept so the screen
# still offers a target on an account whose contacts export is empty and whose
# hiring carries no HP-relevant role. Always ranked after sourced personas.
# The subtitle reaches the prompt as persona evidence, so it describes a role
# any account could have - never an event or unit ("expansion", "regional",
# "Centre of Excellence") the model would then repeat as fact about the account.
ARCHETYPE_PERSONAS = [
    {"id": "cio_it", "kind": "archetype", "source": None, "salutation": "CIO", "title": "CIO / IT Leadership", "subtitle": "Chief Information Officer and IT decision makers"},
    {"id": "infra_workplace", "kind": "archetype", "source": None, "salutation": "IT Infrastructure Leader", "title": "Infrastructure & Workplace IT", "subtitle": "Device fleet owners, infrastructure strategy & commercial teams"},
    {"id": "engineering_ai", "kind": "archetype", "source": None, "salutation": "Engineering Leader", "title": "Engineering / AI & Compute Leadership", "subtitle": "AI, ML and data science leads, GPU/compute buyers"},
    {"id": "security_wolf", "kind": "archetype", "source": None, "salutation": "Security Leader", "title": "Security Leadership (Wolf Security)", "subtitle": "Endpoint security and risk decision makers"},
    {"id": "procurement_finance", "kind": "archetype", "source": None, "salutation": "Procurement Leader", "title": "Procurement / Finance", "subtitle": "IT procurement and budget holders"},
    {"id": "operations", "kind": "archetype", "source": None, "salutation": "Operations Leader", "title": "Operations & Facilities", "subtitle": "Site and office leads, print & workplace services"},
    {"id": "hr_workforce", "kind": "archetype", "source": None, "salutation": "HR Leader", "title": "HR / Workforce Experience", "subtitle": "Device refresh, hybrid work and onboarding programs"},
]

# job_openings `categories` slugs -> the vocabulary DEPT_LABELS already
# normalises, so a posting lands in the same department set as a contact.
JOB_CATEGORY_ALIASES = {
    "information_technology": "it",
    "data": "data",
    "data_analysis": "data",
    "engineering": "engineering",
    "software_development": "engineering",
    "product_management": "product_management",
    "operations": "operations",
    "finance": "finance",
    "legal": "legal",
    "marketing": "marketing",
    "sales": "sales",
    "human_resources": "human resources",
}
# A posting whose every category sits outside IT hardware buying is not a
# persona even when the title carries an IT keyword: "Security Supervisor" under
# protective services is a guard post, not endpoint security; "Medical Network"
# under sales is a sales role. Excluded rather than capped, because a cap at
# NON_IT_TITLE_CAP is the medium band, which the proxy filter keeps. Mixed with
# a neutral function (operations, finance) the score is capped instead. Same
# idea as NON_IT_TITLE_TERMS, applied to the field job_openings actually has.
NON_IT_JOB_CATEGORIES = {"military_and_protective_services", "human_resources",
                         "legal", "sales", "marketing", "administration", "manual_work",
                         "healthcare_services", "education", "food"}
IT_JOB_CATEGORIES = {"information_technology", "data", "data_analysis", "engineering",
                     "software_development", "product_management"}
# The alias labels that resolve to an IT-side department, for the mixed-category
# tie-break in _job_department.
IT_ALIAS_LABELS = {"it", "data", "engineering", "product_management"}
# An internship is excluded outright, whatever seniority the row claims.
PROXY_EXCLUDED_CATEGORIES = {"internship"}

# The hiring rule: a posting proves an open role, never a person. Seniority is
# gated on the export's own raw value because SENIORITY_BAND_MAP has no entry
# for "mid_senior" and would band it with junior.
PROXY_EXCLUDED_SENIORITY = {"junior", "intern", "internship", "entry", "entry_level", "trainee"}
PROXY_SENIORITY_LABELS = {"mid_senior": "Mid-senior", "manager": "Manager", "director": "Director",
                          "head": "Director", "vp": "VP", "vice_president": "VP",
                          "c_suite": "C-Suite", "c_level": "C-Suite"}

# Business-unit suffixes the export appends to titles ("Data Engineer - GSI",
# "Backend Developer ADMO"). Stripped only for clustering; the original title
# is what the persona lists as evidence.
_BU_SUFFIX_RE = re.compile(r"\s*[-\u2013]\s*([A-Z]{2,6})$")
_TRAILING_CAPS_RE = re.compile(r"\s+([A-Z]{3,6})$")
# A suffix that names the job's function, not its unit. Kept, so "Manager - IT"
# or "Consultant SAP" in another account's export does not cluster as "Manager".
_ROLE_ACRONYMS = {"IT", "ICT", "HR", "HRBP", "AI", "ML", "BI", "QA", "QC", "UX", "UI", "OT", "IOT",
                  "SAP", "AWS", "GCP", "ERP", "CRM", "MIS", "SRE", "SOC", "NOC", "GIS", "CAD", "CAE",
                  "VDI", "API", "SQL", "PMO", "EHS", "HSE", "CEO", "CFO", "CIO", "CTO", "COO", "CISO"}
_DANGLING_RE = re.compile(r"(?:^|\s)(?:of|for|in|and|&)$", re.I)


def _canonical_title(title: str) -> str:
    t = title.strip()
    for rx in (_BU_SUFFIX_RE, _TRAILING_CAPS_RE):
        m = rx.search(t)
        if not m:
            continue
        head = t[:m.start()].rstrip()
        # Keep it when it is a function acronym, when stripping would leave "Head
        # of", or when the title is all caps and a unit code is not distinguishable.
        if (m.group(1) in _ROLE_ACRONYMS or _DANGLING_RE.search(head)
                or not any(ch.islower() for ch in head)):
            continue
        t = head
    return t.strip() or title.strip()


def _job_department(raw, title: str = "") -> tuple[str, list[str]]:
    """Department for a posting from its `categories` cell, plus the raw slugs.

    A mixed-category posting whose title carries no IT keyword belongs to its
    non-IT function: "Finance AR Analyst" tagged data_analysis + finance is a
    finance role that uses data, not an IT role, and must not land in the IT
    cluster on the strength of the category alone."""
    cats: list[str] = []
    text = str(raw or "").strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list):
                cats = [str(c).strip().lower() for c in parsed if str(c).strip()]
            elif parsed:
                cats = [str(parsed).strip().lower()]
        except (ValueError, TypeError):
            cats = [c.strip().lower() for c in text.replace(",", ";").split(";") if c.strip()]
    mapped = [JOB_CATEGORY_ALIASES[c] for c in cats if c in JOB_CATEGORY_ALIASES]
    if mapped:
        it_side = [m for m in mapped if m in IT_ALIAS_LABELS]
        other = [m for m in mapped if m not in IT_ALIAS_LABELS]
        if it_side and other and score_hp_relevance(title, UNASSIGNED_DEPT, None) <= HP_RELEVANCE_FLOOR:
            return normalize_department(";".join(other)), cats
        return normalize_department(";".join(mapped)), cats
    if cats:
        return cats[0].replace("_", " ").title(), cats
    return UNASSIGNED_DEPT, cats


def _derive_named_personas(db, account_id: str) -> list[dict]:
    """Spec row 1. Consumed from Stakeholder Map's stored grid, never re-parsed
    from prospect_contacts. Apollo-sourced rows are excluded ("Source A only").
    Empty when the contacts export is empty, in which case the role-type proxy
    carries the persona."""
    grid = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "stakeholder_contacts_grid"})
    contacts = ((grid or {}).get("data") or {}).get("contacts") or []

    eligible = [c for c in contacts
                if c.get("source") == "Source A"
                and c.get("hp_relevance_band") != "low"
                and str(c.get("title") or "").strip()]
    eligible.sort(key=lambda c: (not c.get("is_priority_contact"),
                                 -(c.get("stakeholder_score") or 0),
                                 str(c.get("full_name") or "")))

    personas = []
    for c in eligible[:NAMED_PERSONA_MAX]:
        cid = str(c.get("contact_id") or "").strip()
        pid = cid if cid.startswith("contact_") else f"contact_{cid}"
        dept = c.get("normalized_department") or c.get("department") or UNASSIGNED_DEPT
        band = c.get("seniority_band") or "Individual Contributor"
        personas.append({
            "id": pid,
            "kind": "named",
            "source": "Source A",
            "title": str(c.get("title")).strip(),
            "subtitle": f"{c.get('full_name') or 'Unknown Contact'} \u00b7 {dept} \u00b7 {band}",
            "contact_id": cid,
            "full_name": c.get("full_name"),
            "department": dept,
            "seniority": band,
            "influence_type": c.get("influence_type"),
            "buying_committee_persona": c.get("buying_committee_persona"),
            "hp_relevance_band": c.get("hp_relevance_band"),
            "stakeholder_score": c.get("stakeholder_score"),
            "is_priority_contact": bool(c.get("is_priority_contact")),
        })
    return personas


def _derive_role_proxy_personas(job_records: list[dict]) -> list[dict]:
    """Spec row 2. Role-type persona proxies from open hiring (Source B).

    A persona here is a role type - department + seniority - with the postings
    that produced it listed as evidence. Nothing names a person. Relevance is
    scored by the helper Stakeholder Map applies to a named contact; junior and
    intern postings are gated out before clustering. No status filter, matching
    exec_hiring_velocity and intent_hiring_demand, which count every row."""
    groups: dict[tuple[str, str], dict] = {}
    for row in job_records:
        title = str(row.get("normalized_title") or row.get("title") or "").strip()
        if not title:
            continue
        sen_raw = str(row.get("seniority") or "").strip().lower()
        if not sen_raw or sen_raw in PROXY_EXCLUDED_SENIORITY:
            continue

        dept, cats = _job_department(row.get("categories"), title)
        if set(cats) & PROXY_EXCLUDED_CATEGORIES:
            continue
        if cats and set(cats) <= NON_IT_JOB_CATEGORIES:
            continue
        score = score_hp_relevance(title, dept, None)
        if cats and set(cats) & NON_IT_JOB_CATEGORIES and not set(cats) & IT_JOB_CATEGORIES:
            score = min(score, NON_IT_TITLE_CAP)
        if hp_relevance_band(score) == "low":
            continue

        sen_label = PROXY_SENIORITY_LABELS.get(sen_raw) or seniority_band(sen_raw, title)[0]
        g = groups.setdefault((dept, sen_label), {
            "department": dept, "seniority": sen_label, "seniority_raw": sen_raw,
            "titles": Counter(), "raw_titles": [], "best_score": 0,
        })
        g["titles"][_canonical_title(title)] += 1
        if title not in g["raw_titles"]:
            g["raw_titles"].append(title)
        g["best_score"] = max(g["best_score"], score)

    personas = []
    for (dept, sen_label), g in groups.items():
        count = sum(g["titles"].values())
        top = [t for t, _ in g["titles"].most_common(3)]
        head = dept if dept != UNASSIGNED_DEPT else top[0]
        slug = re.sub(r"[^a-z0-9]+", "_", f"{head} {sen_label}".lower()).strip("_")
        personas.append({
            "id": f"role_{slug}",
            "kind": "role_proxy",
            "source": "job_openings",
            "title": f"{head} \u2014 {sen_label}",
            "subtitle": (f"Role-type proxy from {count} open posting{'s' if count != 1 else ''}: "
                         + ", ".join(top)),
            "department": dept,
            "seniority": sen_label,
            "seniority_raw": g["seniority_raw"],
            "posting_count": count,
            "sample_titles": top,
            "source_titles": g["raw_titles"][:10],
            "hp_relevance_score": g["best_score"],
            "hp_relevance_band": hp_relevance_band(g["best_score"]),
            "hiring_rule_note": "Inferred from open hiring. No individual is known to hold this role.",
        })
    personas.sort(key=lambda p: (-p["hp_relevance_score"], -p["posting_count"], p["title"]))
    return personas[:ROLE_PROXY_MAX]

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    db = get_db()
    file_doc = db["account_data_files"].find_one({
        "account_id": account_id,
        "$or": [{"dataset_key": dataset_key}, {"category": dataset_key}],
        "status": "active"
    })
    
    if not file_doc:
        return []
    
    rel_path = file_doc.get("file_path", "")
    candidate_paths = [
        os.path.join(os.getcwd(), rel_path),
        os.path.join("/app", rel_path),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", rel_path)),
        os.path.join(r"C:\hp-account\HP-Acoount-Intelligence\hp-backend", rel_path)
    ]
    
    full_path = None
    for cp in candidate_paths:
        if os.path.exists(cp):
            full_path = cp
            break
            
    if not full_path:
        return []
    
    ext = os.path.splitext(full_path)[1].lower()
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(full_path)
            df = df.fillna("")
            return df.to_dict(orient="records")
        else:
            with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                return [row for row in reader]
    except Exception:
        return []

# --- Generation (spec row 4: generated_content, INFERRED / SYNTHESIZED) --------
# Same flow as the other inferred extractors: fingerprint -> cache -> one GPT-4o
# JSON call -> grounding gate -> bounded retry -> keep-last-good -> upsert.
# Keyed on the request (persona x type x topic x context) because this feature
# takes seller input; the other four key on the account's data alone.

# Bump when the prompt changes so cached assets are regenerated.
CONTENT_PROMPT_VERSION = "2026-09-11.7"
ASSET_HISTORY_MAX = 20
RETRY_ROUNDS = 2
TOPIC_MAX_CHARS = 200
CONTEXT_MAX_CHARS = 2000

# One shared preamble; the per-type block below is the only thing that varies.
# Every type returns the same JSON shape, so one validator covers all seven.
# The three-paragraph shape shared by Email and Branded Emailer; the two differ
# only in how they are composed and rendered.
_EMAIL_SHAPE = ("A three-paragraph outreach email written as HP (\"At HP, we ...\"). "
                  "subject_line: under 80 characters, names the account and the subject. "
                  "opening (paragraph 1, one or two sentences): the hook - one specific account fact "
                  "or hiring signal from the evidence, stated with confidence. "
                  "body_sections (paragraph 2): EXACTLY ONE paragraph, no heading, two or three "
                  "sentences, at most 60 words - restate the paragraph-1 evidence as the need, then "
                  "name the one HP line with ONE concrete capability that meets it. "
                  "cta (paragraph 3, one sentence): a question asking for a brief, focused discussion. "
                  "90-130 words in total. The salutation and sign-off are added automatically - do not "
                  "write 'Dear', 'Sincerely' or a signature.")

CONTENT_TYPE_CONTRACTS = {
    "email": {
        "title": "Email", "subtitle": "Personalized executive outreach email",
        "required": ["subject_line", "opening", "body_sections", "cta"],
        "sections": (1, 2), "subject_max": 80, "email_shaped": True,
        "shape": _EMAIL_SHAPE,
    },
    "linkedin": {
        "title": "LinkedIn Post", "subtitle": "Social selling content for LinkedIn",
        "required": ["headline", "opening", "body_sections", "cta"],
        "optional": ["hashtags"],
        "sections": (1, 3), "public": True,
        "shape": ("A public LinkedIn post the seller publishes on their own feed, in the first person. "
                  "People in this persona's ROLE are the audience - write for them, never to one person. "
                  "headline: the hook - ONE line under 120 characters, shown before '...see more'; a "
                  "sharp observation or question for this role, not a slogan. "
                  "opening: one or two short sentences that set up the insight from one evidence item. "
                  "body_sections: 2-3 very short paragraphs of one or two sentences each, NO headings. "
                  "One of them may instead be a short list of 2-3 points, each on its own line "
                  "starting with '\u2022 '. "
                  "cta: one closing question that invites people in this role to comment. "
                  "hashtags: 2-3 specific hashtags for this topic and role - never #HP, #Innovation or "
                  "other generic tags - and keep hashtags OUT of every other field. "
                  "120-200 words in total."),
    },
    "one_pager": {
        "title": "One-Pager", "subtitle": "Single-page solution overview for the account",
        "headings": True,
        "required": ["headline", "opening", "body_sections", "cta"],
        "sections": (3, 4),
        "shape": ("A one-page solution overview for the account. headline; opening summary paragraph; "
                  "3-4 body_sections each WITH a heading, covering: the situation the evidence shows, "
                  "what HP proposes, why now, and the next step; cta is the recommended action. "
                  "250-400 words. No subject_line."),
    },
    "exec_brief": {
        "title": "Executive Brief", "subtitle": "2-page intelligence brief for leadership",
        "headings": True,
        "required": ["headline", "opening", "body_sections", "cta"],
        "sections": (3, 5),
        "shape": ("An executive intelligence brief for HP leadership preparing to engage this account. "
                  "headline; opening is the one-paragraph bottom line; 3-5 body_sections each WITH a "
                  "heading (account snapshot, the persona and their remit, the evidence, the recommended "
                  "HP angle or discovery plan, risks and unknowns); cta is the recommended internal "
                  "next step. 350-550 words. Third person throughout. No subject_line."),
    },
    "follow_up": {
        "title": "Follow-up Note", "subtitle": "Post-meeting follow-up with next steps",
        "required": ["subject_line", "opening", "body_sections", "cta"],
        "sections": (1, 2), "subject_max": 80, "email_shaped": True,
        "shape": ("A short post-meeting follow-up email written as HP. subject_line; opening thanks briefly and "
                  "restates the one thing discussed that matters - drawn from the seller's additional "
                  "context if supplied, otherwise from the evidence; 1-2 body_sections with agreed next "
                  "steps; cta confirms the next meeting or action. Under 150 words. No headline. The "
                  "salutation and sign-off are added automatically."),
    },
    "branded_emailer": {
        "title": "Branded Emailer", "subtitle": "HP-branded email with visual preview and HTML download",
        "required": ["subject_line", "opening", "body_sections", "cta"],
        "sections": (1, 2), "subject_max": 80, "email_shaped": True,
        # Greets the role ("Dear CIO,") and carries no sign-off - the sender is the
        # From line of the branded layout.
        "greeting_role": True, "signoff": False,
        "shape": _EMAIL_SHAPE,
    },
    "landing_page": {
        "title": "Landing Page", "subtitle": "HP-branded landing page with visual preview and HTML download",
        "headings": True,
        "required": ["headline", "opening", "body_sections", "cta"],
        "sections": (3, 4),
        "shape": ("Copy for an HP-branded landing page. headline is the hero line; opening is the hero "
                  "sub-paragraph; 3-4 body_sections each WITH a short heading, as page sections; cta is "
                  "the primary button label plus one sentence. Under 300 words. Return copy only - the "
                  "layout is rendered separately. No subject_line."),
    },
}

HP_LINES_FOR_PROMPT = ("Z by HP Workstations, HP Elite / Pro PCs (EliteBook, ProBook), HP Wolf Security, "
                       "Poly Collaboration (Poly Studio), HP Enterprise Print / MPS, HP Anyware / DaaS")

# Soft warnings only - never block publication. Kept to genuinely hollow phrases;
# the confident HP voice of the reference emails ("At HP, we are impressed by ...",
# "purpose-built", "seamlessly") is allowed.
BANNED_PHRASES = [
    "i hope this finds you well", "i hope this email finds you", "as threats evolve",
    "unlock value", "drive efficiencies", "uncover opportunities", "best possible experience",
    "game-changing", "synerg", "stay ahead of the curve",
]
# The hiring rule as enforced: the copy may say the ACCOUNT is recruiting for the
# listed roles - the postings show that - but for a role-type or archetype
# persona it may never name a person (checked below) or claim to know who the
# reader is (prompt rule 5). The salutation is composed in Python, so a name can
# only reach a role-type reader through the body, which the name check covers.
EMAIL_SIGNOFF = "Sincerely,\n\nThe HP Inc. Team"
COMPETITORS = ["dell", "lenovo", "huawei", "acer", "canon", "zoom", "apple", "asus", "samsung"]
# Rule 1 names the same list the "our <competitor>" check enforces.
COMPETITORS_FOR_PROMPT = ", ".join(c.title() for c in COMPETITORS[:-1]) + f" or {COMPETITORS[-1].title()}"


def _persona_by_id(db, account_id: str, job_records: list[dict], persona_id: str) -> dict | None:
    """Re-derived rather than read back from the context widget, so the persona
    the model is given is the one the account's data supports right now."""
    for p in (_derive_named_personas(db, account_id)
              + _derive_role_proxy_personas(job_records)
              + ARCHETYPE_PERSONAS):
        if p["id"] == persona_id:
            return p
    return None


def _firmo_industry(f: dict) -> str:
    """The industry line of a firmographics row. One reader for the prompt
    evidence and the Business Context panel, so an export that spells the
    columns in snake_case loses the industry in neither."""
    parts = [str(f.get(title) or f.get(snake) or "").strip() for title, snake in (
        ("Linkedin Industry Category", "linkedin_industry_category"),
        ("Naics Description", "naics_description"),
        ("Sic Code Description", "sic_code_description"))]
    parts = [p for p in parts if p]
    if parts:
        return " / ".join(dict.fromkeys(parts))
    return str(f.get("Industry Classification") or f.get("industry") or "").strip()


def _account_evidence(firmo_records: list[dict]) -> tuple[str, list[tuple[str, str]]]:
    """Spec row 3: Business Description and industry fields from firmographics.
    Returns (company_name, [(name, text), ...]). Nothing else is account evidence."""
    if not firmo_records:
        return "", []
    f = firmo_records[0]
    name = str(f.get("Company Name") or f.get("company_name") or f.get("Name") or "").strip()
    desc = str(f.get("Business Description") or f.get("business_description") or "").strip()
    industry = _firmo_industry(f)
    items = []
    if desc:
        items.append(("Business description", desc))
    if industry:
        items.append(("Industry", industry))
    return name, items


def _persona_evidence(persona: dict) -> list[tuple[str, str]]:
    """What the model may know about the target, shaped by persona kind."""
    kind = persona["kind"]
    items = [("Role", persona["title"])]
    if kind == "named":
        items.append(("Name", persona.get("full_name") or "Unknown Contact"))
        items.append(("Department", persona.get("department") or UNASSIGNED_DEPT))
        items.append(("Seniority band", persona.get("seniority") or "Individual Contributor"))
        if persona.get("influence_type"):
            items.append(("Influence type", persona["influence_type"]))
        if persona.get("buying_committee_persona"):
            items.append(("Buying-committee persona", persona["buying_committee_persona"]))
    elif kind == "role_proxy":
        items.append(("Department", persona.get("department") or UNASSIGNED_DEPT))
        items.append(("Seniority", persona.get("seniority") or ""))
        n = persona.get("posting_count") or 0
        titles = persona.get("source_titles") or persona.get("sample_titles") or []
        items.append(("Open postings",
                      f"{n} posting{'s' if n != 1 else ''} in job_openings: " + ", ".join(titles)))
    else:
        items.append(("Description", persona.get("subtitle") or ""))
    return items


def _label_block(prefix: str, items: list[tuple[str, str]]) -> tuple[str, dict[str, str]]:
    """Number evidence lines [A1], [P2] ... so a citation is a checkable token
    rather than a paraphrase the model could drift from."""
    lines, labels = [], {}
    for i, (name, text) in enumerate(items, start=1):
        lab = f"{prefix}{i}"
        labels[lab] = f"{name}: {text}"
        lines.append(f"[{lab}] {name}: {text}")
    return "\n".join(lines), labels


PERSONA_KIND_HEADERS = {
    "named": "NAMED CONTACT - Source A, from Stakeholder Map",
    "role_proxy": "ROLE-TYPE PROXY - inferred from open hiring (job_openings)",
    "archetype": "GENERIC ARCHETYPE - not sourced from account data",
}


# Placeholders in the schema are written <like this>, so an echoed placeholder is
# recognisable and discarded rather than published as content.
_PLACEHOLDER_RE = re.compile(r"^<[^<>]*>$")
_FIELD_SCHEMA = {
    "subject_line": '"<subject line>"',
    "headline": '"<headline>"',
    "opening": '"<first paragraph - names one specific evidence item>"',
    "cta": '"<one concrete next step>"',
    "hashtags": '["#<specific tag>", "#<specific tag>"]',
}
GENERIC_HASHTAGS = {"#hp", "#hpinc", "#innovation", "#technology", "#business", "#success"}


def _content_fields(contract: dict) -> list[str]:
    return contract["required"] + contract.get("optional", [])


def _output_schema(contract: dict) -> str:
    """The JSON example the model sees - only the keys this content type uses, so
    it is never shown a field it should leave empty."""
    lines = []
    for f in _content_fields(contract):
        if f == "body_sections":
            item = ('{"heading": "<short heading>", "text": "<paragraph>"}' if contract.get("headings")
                    else '{"text": "<paragraph>"}')
            lines.append(f'    "body_sections": [{item}]')
        else:
            lines.append(f'    "{f}": {_FIELD_SCHEMA[f]}')
    lines += ['    "hp_products": ["<HP line from the list above - or leave the list empty>"]',
              '    "evidence_used": ["A1", "P1"]',
              '    "persona_framing": "<one sentence: why this angle for this persona>"']
    return '{\n  "asset": {\n' + ",\n".join(lines) + '\n  }\n}'


def _persona_rule(kind: str, company_name: str, contract: dict) -> str:
    if contract.get("public"):
        return (
            "THIS IS A PUBLIC POST. The persona only tells you the AUDIENCE - people who hold this "
            "kind of role. Never name, address or describe an individual, and never greet anyone. "
            "\"You\" may speak to the audience in general (\"If you lead a data team ...\"), never "
            "to one specific person. Write about what this kind of role weighs, so readers in it "
            f"recognise themselves. {company_name} may be mentioned only through a fact in the "
            "ACCOUNT EVIDENCE - never speculate in public about its needs, gaps or buying plans."
        )
    if kind == "named":
        salutation = "; the salutation is added automatically" if contract.get("email_shaped") else ""
        return (
            f"This is a specific, named contact{salutation}. Write to the "
            "remit their title implies. NEVER state or imply who they report to, their private concerns, "
            "workload, opinions or budget. Their influence type bounds the ask: Technical Evaluator "
            "or Influencer -> ask for input or an evaluation conversation, never a decision; Budget "
            "Holder or Decision Maker -> a decision-oriented ask is acceptable; none supplied -> ask "
            "for a conversation."
        )
    if kind == "role_proxy":
        return (
            "THIS IS A ROLE TYPE INFERRED FROM OPEN HIRING. No person is known to hold it. HIRING "
            f"RULE: you may say that {company_name} is recruiting for the listed roles - the postings "
            "show that - but never name a person, never claim to know who the reader is, and never "
            "attribute a decision, opinion or workload to them. Address the reader by role "
            "(\"As the leader building this team ...\") and write to what that FUNCTION would be "
            "weighing, hedged where the evidence stops (\"may\", \"could\", \"suggests\")."
        )
    return (
        "This is a generic HP ABM audience. No account evidence about this role exists. Do NOT "
        f"claim the role exists at {company_name}, and do not attribute any account fact to it. "
        "Write to what such a role typically weighs, and lean entirely on the ACCOUNT EVIDENCE "
        "for anything specific to the account."
    )


def _request_fingerprint(evidence_cells: list[str], persona: dict, content_type: str,
                         topic: str, additional_context: str,
                         instructions_text: str, guardrails_text: str) -> str:
    # The account team's instructions and guardrails are part of the key, so an
    # edit to them regenerates on the next request instead of serving the cache.
    payload = {
        "prompt_version": CONTENT_PROMPT_VERSION,
        "evidence": sorted(evidence_cells),
        "persona": {k: persona.get(k) for k in ("id", "kind", "title", "subtitle", "source")},
        "content_type": content_type,
        "topic": topic.strip().lower(),
        "context": additional_context.strip().lower(),
        "instructions": instructions_text.strip(),
        "guardrails": guardrails_text.strip(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# Account-agnostic by construction: one template serves every account. What
# differs per account arrives as data - the evidence blocks, the persona, and
# the account_instructions / account_guardrails documents an account team edits
# without a deploy. Never write an account's name, sector or example into it.
def _build_system_prompt(company_name: str, contract: dict, account_block: str,
                         persona: dict, persona_block: str, topic: str,
                         additional_context: str, instructions_text: str,
                         guardrails_text: str) -> str:
    label = contract["title"]
    kind = persona["kind"]
    return f"""You are an expert ABM strategist and copywriter for HP Inc. ("HP"). You write one {label} for an HP seller to use with a target at {company_name}.

ACCOUNT EVIDENCE (use only this for any claim about {company_name}):
{account_block or 'No account evidence supplied. Make no claim about the account.'}

TARGET PERSONA ({PERSONA_KIND_HEADERS[kind]}):
{persona_block}

SELLER INPUT (the subject the seller chose - NOT evidence about the account):
Topic: {topic}
Additional context from the seller: {additional_context.strip() or 'None provided.'}

ACCOUNT-SPECIFIC CUSTOM INSTRUCTIONS (set by the account team for {company_name}; they steer emphasis and tone, they are NOT evidence, and where they conflict with the CRITICAL RULES the rules win):
{instructions_text or 'None provided.'}

ACCOUNT-SPECIFIC MANDATORY GUARDRAILS (set by the account team for {company_name}; always obey them - they can only narrow what you write, never relax a CRITICAL RULE):
{guardrails_text or 'None provided.'}

CRITICAL RULES:
1. You represent HP Inc. Never refer to {COMPETITORS_FOR_PROMPT} as "our" product. Never disparage a named competitor.
2. Ground every statement about {company_name} in the ACCOUNT EVIDENCE or the TARGET PERSONA block. Invent nothing: no numbers, percentages, URLs, customer names, product SKUs or events that are not written above. If you need a figure and none is supplied, write without one. This is checked mechanically and an unsourced number is rejected.
2a. QUOTE THE DATA, DO NOT CHARACTERISE THE BUSINESS. "Their operations require reliable technology" and "technology plays a critical role in supporting your goals" are NOT evidence - nothing above says them, and the reader knows their own company. Name the specific item instead: a phrase from the business description, a role from the persona block, a posting title. Never open by summarising the business description back to the reader.
2b. INDUSTRY IS NOT JUSTIFICATION. The industry and business description say what {company_name} does - one industry or many sectors - not what technology it needs. Do NOT use an industry or sector name as the reason for a device, workstation, security, collaboration or print need - nothing in the evidence links an industry to a technology requirement. "Because you operate in <industry>, your systems must be reliable" is a FAILED sentence, whatever the industry.
3. THE TOPIC IS NOT EVIDENCE. The seller chose it as the subject. It tells you what to write about, not what is true of the account. A claim about the account still needs a citation above; otherwise hedge it ("may", "could", "suggests", "worth exploring").
4. AN HP PLAY MUST BE EARNED, NOT ASSIGNED. Before naming a product the chain has to hold: this persona's remit + the account evidence -> a plausible HP line. Do NOT start from the topic's product and work backwards. IF THE CHAIN DOES NOT HOLD: name no product, return "hp_products": [], and write a discovery-led piece that opens on the persona's own remit and what the seller wants to learn. That is a correct answer, not a failure. A forced product match IS a failure.
   HP lines you may name: {HP_LINES_FOR_PROMPT}.
   Name AT MOST ONE HP line - the one the chain earns. The topic names the line under discussion; do not add a second line as a bonus, and do not list a product's feature set. Say the one thing about it that matters to THIS persona.
5. PERSONA RULE. {_persona_rule(kind, company_name, contract)}
6. "opening" must name at least one item from the evidence above by its content, not by its label, and it must be the ONE item that matters for this persona and this topic - not a tour of the account. The first sentence a reader sees is the one that proves the seller knows this account.
7. "evidence_used" lists the labels ([A1], [P2] ...) you actually drew on. Only labels written above. It is checked.
8. VOICE. Write as HP - "At HP, we ..." - confident and specific, to a busy senior professional. Every paragraph must carry a concrete item from the evidence or a concrete thing the HP line gives their teams; a paragraph that could be sent to any company unchanged is a failed paragraph.
   - Do NOT use the concessive template "<praise> ... However, <vague upside>".
   - Do NOT write hollow abstractions: "as threats evolve", "unlock value", "drive efficiencies", "uncover opportunities".
   - No benefit lists and no superiority claims. "Robust performance, enhanced security features and streamlined manageability" and "industry-leading" say nothing about this account and nothing checkable about HP. Name ONE concrete capability instead - it beats four adjectives.
   - No "I hope this finds you well". No exclamation marks.
9. Omission is the default: leave out any key you cannot fill honestly. Never emit an empty string to fill a slot.

OUTPUT CONTRACT - {label}:
{contract['shape']}
Required keys: {', '.join(contract['required'])}. Return ONLY the keys shown below; any other key is discarded.

Output JSON (replace every <placeholder> with real content):
{_output_schema(contract)}
"""


def _validate_asset(raw, contract: dict, persona: dict, labels: dict[str, str],
                    ground, report: GroundingReport, banned_names: list[str]) -> tuple[dict | None, list[str], list[str]]:
    """Python owns the truth. Returns (clean_asset, hard_faults, style_warnings).

    A hard fault - an unsourced figure, a claim about a person no dataset
    supports, a competitor called "our", a missing required key, no evidence
    cited - means the asset is not published and the faults go back as retry
    notes. A style warning (a banned filler phrase, an exclamation mark) is
    also sent for rewrite, but once the retry budget is spent the draft is
    published with the warnings attached rather than withheld: a seller can fix
    a phrase; they cannot fix a number that was never in the data."""
    faults: list[str] = []
    soft: list[str] = []
    a = raw.get("asset") if isinstance(raw, dict) else None
    if not isinstance(a, dict):
        return None, ["no \"asset\" object was returned"], []

    fields = set(_content_fields(contract))

    def _s(key) -> str:
        v = str(a.get(key) or "").strip()
        return "" if _PLACEHOLDER_RE.match(v) else v

    # Only the fields this content type uses survive - a subject line on a
    # LinkedIn post is discarded here, whatever the model returned.
    subject = _s("subject_line") if "subject_line" in fields else ""
    headline = _s("headline") if "headline" in fields else ""
    opening, cta, framing = _s("opening"), _s("cta"), _s("persona_framing")
    sections: list[dict] = []
    for s in (a.get("body_sections") or []):
        if isinstance(s, dict):
            t = str(s.get("text") or "").strip()
            if t and not _PLACEHOLDER_RE.match(t):
                heading = str(s.get("heading") or "").strip() if contract.get("headings") else ""
                sections.append({"heading": None if (not heading or _PLACEHOLDER_RE.match(heading)) else heading,
                                 "text": t})
        elif isinstance(s, str) and s.strip():
            sections.append({"heading": None, "text": s.strip()})

    # Hashtags live in their own field; any the model left in the closing line move there.
    hashtags: list[str] = []
    if "hashtags" in fields:
        raw_tags = a.get("hashtags") or []
        if isinstance(raw_tags, str):
            raw_tags = raw_tags.split()
        tags_in_cta = re.findall(r"#\w+", cta)
        cta = re.sub(r"\s*#\w+", "", cta).strip()
        for t in list(raw_tags) + tags_in_cta:
            tag = "#" + re.sub(r"[^\w]", "", str(t).lstrip("#"))
            if len(tag) > 1 and tag.lower() not in GENERIC_HASHTAGS \
                    and tag.lower() not in {x.lower() for x in hashtags}:
                hashtags.append(tag)
        hashtags = hashtags[:3]

    present = {"subject_line": subject, "headline": headline, "opening": opening,
               "cta": cta, "body_sections": sections}
    for k in contract["required"]:
        if not present.get(k):
            faults.append(f"{k} is missing")
    lo, hi = contract["sections"]
    if sections and not (lo <= len(sections) <= hi):
        faults.append(f"body_sections has {len(sections)} entries; {lo}-{hi} required")
    smax = contract.get("subject_max")
    if subject and smax and len(subject) > smax:
        faults.append(f"subject_line is {len(subject)} characters; at most {smax}")

    texts = [subject, headline, opening, cta, framing, " ".join(hashtags)] \
            + [s["text"] for s in sections] + [s["heading"] or "" for s in sections]
    blob = " ".join(t for t in texts if t).lower()

    for phrase in BANNED_PHRASES:
        if phrase in blob:
            soft.append(f"filler phrase \"{phrase}\"")
    if "!" in blob:
        soft.append("exclamation mark used")
    if persona["kind"] != "named" or contract.get("public"):
        why = "a public post never names a contact" if contract.get("public") \
            else "copy written to a role type, not a person"
        for name in banned_names:
            if name in blob:
                faults.append(f"names a contact (\"{name}\") - {why}")
    for comp in COMPETITORS:
        if f"our {comp}" in blob:
            faults.append(f"refers to {comp} as \"our\" product - you represent HP")

    # Grounding gate: a number the uploads never carried is rejected; a URL they
    # never carried is stripped rather than shown.
    bad_nums, bad_urls = check_text(ground, report, "asset", *texts)
    if bad_nums:
        faults.append("unsourced number(s) " + ", ".join(bad_nums)
                      + " - remove them or use only figures written in the evidence")
    if bad_urls:
        subject, headline, opening, cta, framing = (strip_unsourced_urls(ground, t)
                                                    for t in (subject, headline, opening, cta, framing))
        for s in sections:
            s["text"] = strip_unsourced_urls(ground, s["text"])

    products, bad_products = filter_enum_list(a.get("hp_products"), HP_PRODUCT_LINES)
    if bad_products:
        report.enum_rejected.extend(f"asset: {b}" for b in bad_products)

    used = [str(x).strip().strip("[]").upper() for x in (a.get("evidence_used") or [])]
    kept_labels = [u for u in dict.fromkeys(used) if u in labels]
    if labels and not kept_labels:
        faults.append("evidence_used cites none of the supplied labels")

    if faults:
        return None, faults, soft

    clean = {
        "opening": opening,
        "body_sections": sections,
        "cta": cta,
        "hp_products": products,
        "evidence_used": kept_labels,
    }
    if subject:
        clean["subject_line"] = subject
    if headline:
        clean["headline"] = headline
    if framing:
        clean["persona_framing"] = framing
    if hashtags:
        clean["hashtags"] = hashtags
    return clean, [], soft


# --- HTML rendering for the two branded types ---------------------------------------
# The model returns copy only; the layout is composed here from named fields, the
# same way scale_statement is composed in the opportunity map - so nothing in the
# markup can drift from what passed the grounding gate. Inline CSS only, no
# external assets, so the file the seller downloads is self-contained.
HTML_CONTENT_TYPES = {"branded_emailer", "landing_page"}
_HP_BLUE = "#0096D6"
_HP_NAVY = "#0D2A4B"
_HTML_STYLE = f"""
  body{{margin:0;background:#F2F4F7;font-family:Arial,Helvetica,sans-serif;color:#1F2933;-webkit-font-smoothing:antialiased}}
  .wrap{{max-width:640px;margin:0 auto;background:#fff}}
  .page .wrap{{max-width:960px}}
  .bar{{background:{_HP_NAVY};color:#fff;padding:14px 32px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;display:flex;justify-content:space-between;align-items:center}}
  .bar b{{font-size:18px;letter-spacing:0}}
  .hero{{background:{_HP_BLUE};color:#fff;padding:40px 32px}}
  .page .hero{{padding:72px 48px}}
  .hero h1{{margin:0 0 12px;font-size:28px;line-height:1.2}}
  .page .hero h1{{font-size:40px;max-width:720px}}
  .hero p{{margin:0;font-size:16px;line-height:1.5;max-width:640px;opacity:.95}}
  .sec{{padding:24px 32px;border-bottom:1px solid #E5E8EC}}
  .page .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:0;padding:24px 24px}}
  .page .grid .sec{{border:1px solid #E5E8EC;margin:12px;border-radius:8px}}
  .sec h2{{margin:0 0 8px;font-size:15px;color:{_HP_NAVY};text-transform:uppercase;letter-spacing:.06em}}
  .sec p{{margin:0;font-size:15px;line-height:1.6}}
  .cta{{padding:32px;text-align:center}}
  .btn{{display:inline-block;background:{_HP_BLUE};color:#fff;text-decoration:none;padding:14px 28px;border-radius:4px;font-weight:bold;font-size:15px}}
  .cta p{{margin:12px 0 0;font-size:14px;color:#52606D}}
  .foot{{padding:20px 32px;font-size:11px;color:#7B8794;line-height:1.5}}
  .tag{{display:inline-block;background:#E6F5FC;color:{_HP_NAVY};font-size:11px;padding:3px 8px;border-radius:3px;margin-right:6px}}
"""


# Branded emailer: blue accent bar, HP mark, greeting and paragraphs - the same
# body the Content Studio preview shows under its From / To / Subject header.
# No flexbox and a solid-colour fallback for the gradient, for email clients.
_EMAIL_STYLE = f"""
  body{{margin:0;padding:24px 12px;background:#F2F4F7;font-family:Arial,Helvetica,sans-serif;color:#334155;-webkit-font-smoothing:antialiased}}
  .card{{max-width:640px;margin:0 auto;background:#fff;border:1px solid #E2E8F0;border-radius:12px;overflow:hidden}}
  .accent{{height:6px;background:{_HP_BLUE};background:linear-gradient(90deg,{_HP_BLUE},#00629B)}}
  .content{{padding:24px 28px 28px;font-size:15px;line-height:1.7}}
  .brand{{margin-bottom:20px}}
  .mark{{display:inline-block;vertical-align:middle;width:28px;height:28px;line-height:28px;border-radius:50%;background:{_HP_BLUE};color:#fff;text-align:center;font-weight:bold;font-style:italic;font-size:13px}}
  .brandname{{display:inline-block;vertical-align:middle;margin-left:8px;font-size:12px;font-weight:bold;color:#0F172A}}
  .content p{{margin:0 0 18px}}
  .content p:last-child{{margin-bottom:0}}
"""


def _render_branded_email(record: dict) -> str:
    g = record.get("generated") or {}
    e = _html.escape
    paras = ([record.get("greeting") or "", g.get("opening") or ""]
             + [sec.get("text") or "" for sec in (g.get("body_sections") or [])]
             + [g.get("cta") or ""])
    body = "".join(f"<p>{e(x)}</p>" for x in paras if x)
    subject = e(g.get("subject_line") or record.get("topic") or "HP")
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{subject}</title><style>{_EMAIL_STYLE}</style></head><body>"
        "<div class=\"card\"><div class=\"accent\"></div><div class=\"content\">"
        "<div class=\"brand\"><span class=\"mark\">hp</span><span class=\"brandname\">HP</span></div>"
        f"{body}</div></div></body></html>"
    )


def _split_cta(cta: str) -> tuple[str, str]:
    """'Book a briefing - one sentence' -> ('Book a briefing', 'one sentence').
    Falls back to the whole string as the label."""
    for sep in (" - ", " – ", " — ", ": "):
        if sep in cta:
            label, rest = cta.split(sep, 1)
            if 2 <= len(label.split()) <= 7:
                return label.strip(), rest.strip()
    return cta.strip(), ""


def render_asset_html(record: dict) -> str | None:
    """Self-contained HTML for a branded_emailer or landing_page record; None
    for every other type."""
    ctype = record.get("content_type")
    if ctype not in HTML_CONTENT_TYPES:
        return None
    if ctype == "branded_emailer":
        return _render_branded_email(record)
    g = record.get("generated") or {}
    e = _html.escape
    persona = (record.get("persona") or {}).get("title") or ""
    topic = record.get("topic") or ""
    headline = g.get("headline") or g.get("subject_line") or topic
    opening = g.get("opening") or ""
    sections = g.get("body_sections") or []
    btn, cta_rest = _split_cta(g.get("cta") or "")
    products = g.get("hp_products") or []

    sec_html = "".join(
        "<div class=\"sec\">" + (f"<h2>{e(sec.get('heading'))}</h2>" if sec.get("heading") else "")
        + f"<p>{e(sec.get('text') or '')}</p></div>"
        for sec in sections
    )
    if ctype == "landing_page":
        sec_html = f"<div class=\"grid\">{sec_html}</div>"
    tags = "".join(f"<span class=\"tag\">{e(x)}</span>" for x in products)
    title_tag = e(g.get("subject_line") or headline)
    body_cls = "page" if ctype == "landing_page" else "mail"

    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<title>{title_tag}</title><style>{_HTML_STYLE}</style></head>"
        f"<body class=\"{body_cls}\"><div class=\"wrap\">"
        f"<div class=\"bar\"><b>HP</b><span>{e(persona)}</span></div>"
        f"<div class=\"hero\"><h1>{e(headline)}</h1><p>{e(opening)}</p></div>"
        f"{sec_html}"
        f"<div class=\"cta\"><a class=\"btn\" href=\"#\">{e(btn) or 'Talk to HP'}</a>"
        + (f"<p>{e(cta_rest)}</p>" if cta_rest else "") + "</div>"
        f"<div class=\"foot\">{tags}<br>Prepared for {e(persona)} · Topic: {e(topic)} · "
        "© HP Inc. Draft generated from account intelligence; review before sending.</div>"
        "</div></body></html>"
    )


def _compose_greeting(persona: dict, contract: dict) -> str:
    """Salutation: the first name for a named contact. For an archetype, the role
    itself on a branded emailer ("Dear CIO,") or a placeholder the seller fills in
    on a plain email ("Dear [CIO Name],"). A placeholder for a hiring proxy, where
    no person is known."""
    kind = persona.get("kind")
    if kind == "named":
        first = str(persona.get("full_name") or "").strip().split(" ")[0]
        return f"Dear {first}," if first and first.lower() != "unknown" else "Dear [Name],"
    if kind == "archetype":
        role = persona.get("salutation") or re.split(r"\s*[/(]\s*", str(persona.get("title") or ""))[0].strip()
        if not role:
            return "Dear [Name],"
        return f"Dear {role}," if contract.get("greeting_role") else f"Dear [{role} Name],"
    return "Dear [Name],"


def _compose_plain_text(record: dict, contract: dict) -> str:
    """The asset as one copyable text. Email types follow the reference layout:
    Subject / salutation / three paragraphs / sign-off. Composed from the
    validated fields, so it cannot carry anything the gate did not pass."""
    g = record.get("generated") or {}
    paras = [g.get("opening", "")] + [s.get("text", "") for s in (g.get("body_sections") or [])] + [g.get("cta", "")]
    paras = [x for x in paras if x]
    if contract.get("public"):
        post = [g.get("headline", ""), g.get("opening", "")] \
            + [sec.get("text", "") for sec in (g.get("body_sections") or [])] \
            + [g.get("cta", ""), " ".join(g.get("hashtags") or [])]
        return "\n\n".join(x for x in post if x).strip()
    if contract.get("email_shaped"):
        head = [f"Subject: {g['subject_line']}"] if g.get("subject_line") else []
        signoff = [EMAIL_SIGNOFF] if contract.get("signoff", True) else []
        return "\n\n".join(head + [record.get("greeting") or ""] + paras + signoff).strip()
    lines = [g["headline"]] if g.get("headline") else []
    lines.append(g.get("opening", ""))
    for sec in (g.get("body_sections") or []):
        lines.append((sec["heading"].upper() + "\n" if sec.get("heading") else "") + sec.get("text", ""))
    lines.append(g.get("cta", ""))
    return "\n\n".join(x for x in lines if x).strip()


def generate_content_asset(account_id: str, persona_id: str, content_type: str,
                           topic: str, additional_context: str = "") -> dict:
    """One cached GPT-4o call per (persona, type, topic, context). Returns the
    content_generated_assets widget document. Raises ValueError for a request
    the account's data cannot serve (unknown persona or type, empty topic)."""
    db = get_db()
    now = datetime.now(timezone.utc)

    content_type = str(content_type or "").strip().lower()
    contract = CONTENT_TYPE_CONTRACTS.get(content_type)
    if not contract:
        raise ValueError(f"Unknown content_type '{content_type}'")
    topic = str(topic or "").strip()[:TOPIC_MAX_CHARS]
    if not topic:
        raise ValueError("topic is required")
    additional_context = str(additional_context or "").strip()[:CONTEXT_MAX_CHARS]

    firmo_records = _read_dataset_records(account_id, "firmographics")
    contacts_records = _read_dataset_records(account_id, "prospect_contacts")
    job_records = _read_dataset_records(account_id, "job_openings")

    persona = _persona_by_id(db, account_id, job_records, persona_id)
    if not persona:
        raise ValueError(f"Unknown persona_id '{persona_id}' for this account")

    company_name, account_items = _account_evidence(firmo_records)
    if not company_name:
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)}) if ObjectId.is_valid(account_id) else None
        company_name = (account_doc or {}).get("name") or "Target Account"

    # Open hiring as account evidence (job_openings is sanctioned for this
    # feature): the HP-relevant clusters, so any persona's copy can say what the
    # account is recruiting for, the way the reference emails do.
    hiring_clusters = _derive_role_proxy_personas(job_records)
    if hiring_clusters:
        parts = [f"{c['posting_count']} {c['department']} ({c['seniority']}): {', '.join(c['sample_titles'])}"
                 for c in hiring_clusters]
        account_items.append(("Open hiring", f"{len(job_records)} open postings; HP-relevant roles - "
                              + "; ".join(parts)))

    account_block, a_labels = _label_block("A", account_items)
    persona_block, p_labels = _label_block("P", _persona_evidence(persona))
    labels = {**a_labels, **p_labels}

    inst_doc = db["account_instructions"].find_one({"account_id": account_id})
    guard_doc = db["account_guardrails"].find_one({"account_id": account_id})
    instructions_text = (inst_doc or {}).get("instructions_text", "").strip()
    guardrails_text = (guard_doc or {}).get("guardrails_text", "").strip()

    # Grounding corpus: the three sanctioned datasets, plus the seller's own
    # typed input - a figure the seller supplied is theirs to stand behind, not
    # something the model invented.
    ground = build_corpus({
        "firmographics": firmo_records,
        "prospect_contacts": contacts_records,
        "job_openings": job_records,
        "seller_input": [{"topic": topic, "additional_context": additional_context}],
        # Derived from the data above (posting counts, cluster sizes); a figure the
        # model quotes back from the evidence block must not be rejected.
        "evidence_block": [{"text": t} for t in labels.values()],
    })
    report = GroundingReport(ground, ["subject_line", "headline", "opening", "body_sections",
                                      "cta", "persona_framing"])

    # Names the copy may not use when the target is a role type, not a person.
    grid = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "stakeholder_contacts_grid"})
    banned_names = []
    for c in (((grid or {}).get("data") or {}).get("contacts") or []):
        n = str(c.get("full_name") or "").strip().lower()
        if n and " " in n and n != "unknown contact":
            banned_names.append(n)
    for r in contacts_records:
        n = str(r.get("Prospect full_name") or "").strip().lower()
        if n and " " in n and n not in banned_names:
            banned_names.append(n)

    fingerprint = _request_fingerprint(list(labels.values()), persona, content_type, topic, additional_context,
                                       instructions_text, guardrails_text)

    existing = db["account_widgets"].find_one({
        "account_id": account_id, "widget_key": "content_generated_assets"})
    existing_assets = list(((existing or {}).get("data") or {}).get("assets") or [])

    def _payload(status: str, latest, assets: list[dict], last_error) -> dict:
        return {
            "account_id": account_id,
            "feature_key": "content_studio",
            "widget_key": "content_generated_assets",
            "data_classification": "inferred",
            "status": status,
            "data": {
                "latest": latest,
                "assets": assets,
                "generated_count": len(assets),
                "last_error": last_error,
            },
            "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
            "extracted_at": now,
            "updated_at": now,
        }

    # Cached: the same request against unchanged evidence costs no model call.
    cached = next((x for x in existing_assets if x.get("request_fingerprint") == fingerprint), None)
    if cached:
        payload = _payload("available", cached, existing_assets, None)
        db["account_widgets"].update_one(
            {"account_id": account_id, "widget_key": "content_generated_assets"},
            {"$set": payload}, upsert=True)
        return payload

    system_prompt = _build_system_prompt(company_name, contract, account_block, persona,
                                         persona_block, topic, additional_context,
                                         instructions_text, guardrails_text)
    user_prompt = (f"Write the {contract['title']} for {persona['title']} at {company_name} "
                   f"on the topic \"{topic}\". Return JSON matching the schema.")

    attempts: list[list[str]] = []
    best: tuple[dict, list[str]] | None = None   # cleanest publishable draft seen so far

    def _consider(asset, soft):
        nonlocal best
        if asset is not None and (best is None or len(soft) < len(best[1])):
            best = (asset, soft)

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)
    if llm_res is None:
        asset, faults, soft = None, ["model returned nothing - OPENAI_API_KEY missing or the call failed"], []
    else:
        asset, faults, soft = _validate_asset(llm_res, contract, persona, labels, ground, report, banned_names)
        attempts.append(faults + soft)
        _consider(asset, soft)
        # Bounded retry, for style warnings as well as hard faults. The model is
        # told exactly what was rejected, not asked again blindly.
        for _round in range(RETRY_ROUNDS):
            if asset is not None and not soft:
                break
            notes = faults + [f"{w} - replace it with a specific statement about this account; "
                              "do not substitute a synonym" for w in soft]
            retry_system = system_prompt + (
                "\n\nRETRY - YOUR PREVIOUS ANSWER WAS REJECTED.\n"
                "Fix exactly the faults below and return the COMPLETE asset object again - every "
                "key, carrying the parts that were already correct through unchanged.\n"
                + "\n".join(f"- {f}" for f in notes) + "\n"
                "Use calibrated language (\"may\", \"could\", \"suggests\", \"worth exploring\") for "
                "anything not written in the evidence."
            )
            retry_res = generate_gpt4o_json_completion(retry_system, user_prompt)
            if retry_res is None:
                break
            asset, faults, soft = _validate_asset(retry_res, contract, persona, labels, ground, report, banned_names)
            attempts.append(faults + soft)
            _consider(asset, soft)

    # Retry budget spent: publish the cleanest draft that had no hard fault,
    # carrying its remaining style warnings, rather than withhold everything.
    if asset is None and best is not None:
        asset, soft = best
    elif asset is not None and best is not None and len(best[1]) < len(soft):
        asset, soft = best

    if asset is None:
        logger.warning("content studio: generation rejected for %s/%s/%s: %s",
                       account_id, persona_id, content_type, faults)
        last_error = {
            "faults": faults,
            "attempts": attempts,
            "persona_id": persona_id,
            "content_type": content_type,
            "topic": topic,
            "at": now.isoformat(),
            "notice": "The generated draft did not pass the grounding and style checks and was not published. "
                      "Earlier assets are kept.",
        }
        payload = _payload("available" if existing_assets else "pending", None, existing_assets, last_error)
        db["account_widgets"].update_one(
            {"account_id": account_id, "widget_key": "content_generated_assets"},
            {"$set": payload}, upsert=True)
        return payload

    record = {
        "asset_id": fingerprint[:16],
        "request_fingerprint": fingerprint,
        "prompt_version": CONTENT_PROMPT_VERSION,
        "persona": {k: persona.get(k) for k in ("id", "kind", "title", "subtitle", "source", "full_name")},
        "content_type": content_type,
        "content_type_label": contract["title"],
        "topic": topic,
        "additional_context": additional_context or None,
        "generated": asset,
        "style_warnings": soft,
        "attempts": len(attempts),
        "evidence_labels": {lab: labels[lab] for lab in asset["evidence_used"]},
        "rendered_html": None,
        "grounding_report": report.as_dict(),
        "generated_at": now.isoformat(),
    }
    record["greeting"] = _compose_greeting(persona, contract) if contract.get("email_shaped") else None
    record["plain_text"] = _compose_plain_text(record, contract)
    record["rendered_html"] = render_asset_html(record)
    assets = [x for x in existing_assets if x.get("request_fingerprint") != fingerprint]
    assets.insert(0, record)
    assets = assets[:ASSET_HISTORY_MAX]

    payload = _payload("available", record, assets, None)
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "content_generated_assets"},
        {"$set": payload}, upsert=True)
    return payload


def extract_content_studio(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")
    job_records = _read_dataset_records(account_id, "job_openings")
    intent_records = _read_dataset_records(account_id, "intent_score")
    
    results = []

    # 1. Target Personas, in spec order: named (Source A, via Stakeholder Map)
    #    -> role-type proxy (Source B, job_openings) -> generic archetype.
    named_personas = _derive_named_personas(db, account_id)
    role_proxy_personas = _derive_role_proxy_personas(job_records)
    target_personas = named_personas + role_proxy_personas + ARCHETYPE_PERSONAS
    persona_sources = {
        "named": len(named_personas),
        "role_proxy": len(role_proxy_personas),
        "archetype": len(ARCHETYPE_PERSONAS),
    }

    # 2. Content Types - one entry per output contract
    content_types = [{"id": k, "title": v["title"], "subtitle": v["subtitle"]}
                     for k, v in CONTENT_TYPE_CONTRACTS.items()]

    # 3. Sourced Topic Pills (Product Lines + Intent Surge Topics + Live News Events from CSVs)
    product_line_topics = [
        "Z by HP Workstations",
        "Poly collaboration hardware",
        "HP Elite & Pro PCs",
        "HP Enterprise Printing & Managed Print Services"
    ]

    intent_topics = []
    for row in intent_records[:5]:
        t = str(row.get("Topic") or row.get("topic_name") or "").strip()
        if t:
            intent_topics.append(t)

    news_topics = []
    seen_headlines = set()

    for row in gnews_records:
        headline = str(row.get("event_headline") or row.get("news_announcements") or row.get("title") or "").strip()
        if headline and headline.lower() not in seen_headlines:
            seen_headlines.add(headline.lower())
            news_topics.append(headline)

    for row in events_records:
        headline = str(row.get("event_headline") or row.get("title") or "").strip()
        if headline and headline.lower() not in seen_headlines:
            seen_headlines.add(headline.lower())
            news_topics.append(headline)

    sourced_topics = product_line_topics + intent_topics + news_topics[:5]

    # 4. Business Context
    business_context = {}
    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]
        
        c_name = str(f.get("Company Name") or f.get("company_name") or f.get("Name") or "").strip()
        domain_val = str(f.get("Company Domain") or f.get("company_domain") or f.get("Domain") or f.get("Website") or f.get("website") or "").strip()
        desc_val = str(f.get("Business Description") or f.get("business_description") or "").strip()

        city = str(f.get("City Name") or f.get("city_name") or "").strip()
        region = str(f.get("Region Name") or f.get("region_name") or "").strip()
        country = str(f.get("Country Name") or f.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_loc_val = ", ".join(loc_parts) if loc_parts else str(f.get("HQ Location") or f.get("hq_location") or "").strip()

        ind_val = _firmo_industry(f)

        emp_val = str(f.get("Number Of Employees Range") or f.get("employee_count_range") or f.get("Employee Count") or f.get("employee_count") or "").strip()
        rev_val = str(f.get("Yearly Revenue Range") or f.get("yearly_revenue_range") or f.get("Yearly Revenue") or f.get("revenue") or "").strip()

        business_context = {
            "company_name": c_name,
            "domain": domain_val,
            "business_description": desc_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

    # Widget 1: content_persona_context (Deterministic)
    context_payload = {
        "account_id": account_id,
        "feature_key": "content_studio",
        "widget_key": "content_persona_context",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "target_personas": target_personas,
            "content_types": content_types,
            "sourced_topics": sourced_topics,
            "business_context": business_context,
            "persona_sources": persona_sources
        },
        "source_datasets": ["prospect_contacts", "job_openings", "firmographics", "google_news", "news_events"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "content_persona_context"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # Widget 2: content_generated_assets (Inferred). Request-scoped: assets are
    # produced by generate_content_asset() behind POST .../content_studio/generate
    # and kept as history here. A page load returns that history and never calls
    # the model - there is no default persona or type to generate for.
    existing = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "content_generated_assets"})
    existing_data = (existing or {}).get("data") or {}
    if existing and (existing_data.get("assets") or existing_data.get("last_error")):
        results.append(existing)
        return results

    generated_payload = {
        "account_id": account_id,
        "feature_key": "content_studio",
        "widget_key": "content_generated_assets",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "latest": None,
            "assets": [],
            "generated_count": 0,
            "last_error": None,
            "notice": "No content generated yet. Choose a target persona, a content type and a topic, then Generate."
        },
        "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "content_generated_assets"},
        {"$set": generated_payload},
        upsert=True
    )
    results.append(generated_payload)

    return results
