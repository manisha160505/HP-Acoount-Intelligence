import hashlib
import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime

from bson import ObjectId

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.observability import pipeline
from app.services.extractors import personas
from app.services.extractors.datasets import account_display_name, read_dataset_records
from app.services.extractors.grounding import (
    HP_PRODUCT_LINES,
    GroundingReport,
    build_corpus,
    check_text,
    filter_enum_list,
    strip_unsourced_urls,
)

# Imported, not copied: a role-type proxy is judged by the same HP-relevance,
# seniority and department rules Stakeholder Map applies to a named contact
# (spec Section 3). stakeholder_map itself is not modified.
from app.services.extractors.stakeholder_map import (
    HP_RELEVANCE_FLOOR,
    NON_IT_TITLE_CAP,
    UNASSIGNED_DEPT,
    hp_relevance_band,
    normalize_department,
    score_hp_relevance,
    seniority_band,
)
from app.services.hp import (
    buyer_personas as bp,
    case_studies as cs,
    content_audit,
    content_gates,
)
from app.services.regen import context as run_context, store as widget_store

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
    grid = widget_store.get(account_id, "stakeholder_contacts_grid", db=db)
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


# The sub-state an account with no target-role file is in: spec 1.4's
# UNFILLED, which it calls "the normal path, not an error state".
_UNFILLED_ROLE = {
    "target_persona": "", "department": "", "buying_committee_angle": "",
    "contact_name": "", "actual_job_title": "", "contact_status": "",
    "is_filled": False,
}


def _derive_client_personas(account_id: str) -> list[dict]:
    """The client's eight target roles for this account, FILLED or UNFILLED.

    Spec Section 1.4. Eight fixed roles replace the five-tier derivation, and
    exactly one distinction survives from it, because it changes what the copy
    is allowed to say: whether a named contact for that role exists at this
    account.

    The eight are not a new vocabulary - they are eight of the thirty-two
    target roles `company_personas` already carries, present on all 220
    delivered files, with the contact where one was found. So this narrows the
    client's own list rather than inventing a lookup, and `buyer_personas`
    owns the matching.

    A role nobody fills is still offered: writing to "the Head of Procurement
    we have not identified yet" is a real task, and the specification expects
    it to be the common case - fill rates across the delivered files run from
    8% (AV & Collaboration) to 61% (CFO). It is never given a name.

    Ordered by the pack, not by the file, so the picker reads the same on
    every account.
    """
    by_persona = {}
    for role in personas.read_roles(account_id):
        persona_id = bp.match_role(role["target_persona"])
        # The other twenty-four roles are not this programme's personas.
        if persona_id and persona_id not in by_persona:
            by_persona[persona_id] = role

    out = []
    for persona_id in bp.PERSONA_IDS:
        # Every one of the eight, on every account. The file decides whether a
        # contact was found, never whether the persona exists - an account
        # without it has eight UNFILLED personas, not none.
        role = by_persona.get(persona_id) or _UNFILLED_ROLE
        card = bp.card(persona_id)
        angle = card["committee_angle"]
        if role["is_filled"]:
            subtitle = " · ".join(p for p in (
                role["contact_name"], role["actual_job_title"] or None,
                angle) if p)
        else:
            subtitle = " · ".join(p for p in (
                card["department"], angle,
                "no contact identified for this role") if p)
        out.append({
            "id": persona_id,
            "kind": "client_role",
            "source": personas.DATASET_KEY,
            # The pack's title, not the file's: HP may reword a title in the
            # export, and a reworded title must not change what is written.
            "title": card["title"],
            "subtitle": subtitle,
            "department": card["department"],
            # The angle comes from the pack too. The file carries one, but the
            # specification assigns these eight explicitly in Section 2.2 and
            # two of them are deliberately not what the file would say.
            "buying_committee_persona": angle,
            "full_name": role["contact_name"] or None,
            "actual_job_title": role["actual_job_title"] or None,
            "contact_status": role["contact_status"] or None,
            "is_filled": role["is_filled"],
        })
    return out


def _derive_role_proxy_personas(job_records: list[dict]) -> list[dict]:
    """Spec row 2. Role-type persona proxies from open hiring (Source B).

    A persona here is a role type - department + seniority - with the postings
    that produced it listed as evidence. Nothing names a person. Relevance is
    scored by the helper Stakeholder Map applies to a named contact; junior and
    intern postings are gated out before clustering. No status filter, matching
    intent_hiring_demand, which counts every row."""
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
    """Rows for one dataset, through the shared loader.

    This module used to carry its own copy, with a hard-coded Windows path among
    its candidates. The shared loader resolves the same locations, and inside a
    regeneration run it reads the pinned rows and records the read - which a
    private copy would silently bypass.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

# --- Generation (spec row 4: generated_content, INFERRED / SYNTHESIZED) --------
# Same flow as the other inferred extractors: fingerprint -> cache -> one GPT-4o
# JSON call -> grounding gate -> bounded retry -> keep-last-good -> upsert.
# Keyed on the request (persona x type x topic x context) because this feature
# takes seller input; the other four key on the account's data alone.

# Bump when the prompt changes so cached assets are regenerated.
CONTENT_PROMPT_VERSION = "2026-10-01.1"    # tuning row 8: estate, intent, signals, plays and filings as evidence

# The one mandated section an HP case study belongs in. Named rather than
# repeated, because the contract, the fallback template and the attach all have
# to agree on the exact string or the section is silently never found.
PROOF_POINTS_HEADING = "Proof Points"
# The 1-Pager's HP play is a section of the rendered document as well as a key
# of the structured one, and the two have to agree on the string.
HP_PLAY_HEADING = "The HP Play"
ASSET_HISTORY_MAX = 20
RETRY_ROUNDS = 2
TOPIC_MAX_CHARS = 200
CONTEXT_MAX_CHARS = 2000

# One shared preamble; the per-type block below is the only thing that varies.
# Every type returns the same JSON shape, so one validator covers all seven.
# The three-paragraph shape shared by Email and Branded Emailer; the two differ
# only in how they are composed and rendered.
# Spec Section 3.4's email. One shape, because there is one email format: the
# builder here used to be parameterised so Branded Emailer could keep
# HP_ABX_v3_final's 110-word cap while `email` moved to 120-180, and Branded
# Emailer was retired with Section 1.2.
_EMAIL_SHAPE = ("An outreach email written as HP (\"At HP, we ...\"). "
                "subject_line: MUST use the format 'Re: [specific initiative or challenge]' - it "
                "starts with 'Re: ' and then names the specific initiative or challenge this email "
                "is about, taken from the evidence. Not a generic subject, and under 80 characters. "
                "opening (one or two sentences): the hook - one specific account fact "
                "or hiring signal from the evidence, stated with confidence. "
                "body_sections: 2-3 short paragraphs, NO headings. The first restates the opening "
                "evidence as the need and names the one HP line with ONE concrete capability that "
                "meets it; each further paragraph carries another concrete item from the evidence "
                "or another capability - never an adjective in place of one. "
                "cta (one sentence): a LOW-FRICTION next step - ask for a briefing, a "
                "workshop, an assessment or a short focused discussion. Never claim an existing "
                "meeting, project or prior conversation unless the evidence states one. "
                "120-180 words in total across opening, body_sections and cta. Past 180 words none "
                "of these roles will read it. "
                "The salutation and sign-off are added automatically - do not "
                "write 'Dear', 'Sincerely' or a signature.")


# The five HP business units, named as the Opportunity Map and Intent & Demand
# name their plays.
HP_BU_TOPICS = (
    "HP Elite & Pro PCs",
    "Z by HP Workstations",
    "Poly collaboration hardware",
    "HP Enterprise Printing & Managed Print Services",
    "HP Multi Jet Fusion (3D)",
)
LIVE_SIGNAL_TOPICS_MAX = 5
# What the seller may pick (Sahaj, 27 Sep), in this order.
OFFERED_CONTENT_TYPES = ("email", "linkedin_message", "one_pager")

# Spec 1.1: three formats, and Section 1.2 says the rest leave the code rather
# than the dropdown. These are the names they had, kept so a stored asset reads
# as "Branded Emailer" rather than as a bare key, and so an attempt to generate
# one says it was retired rather than that it never existed.
#
# Their contracts are gone. An asset generated under one still renders: the
# plain text and the branded HTML were composed at generation time and stored
# on the record, so nothing re-reads a contract to display it.
RETIRED_CONTENT_TYPES = {
    "linkedin": "LinkedIn Post",
    "exec_brief": "Executive Brief",
    "follow_up": "Follow-up Note",
    "branded_emailer": "Branded Emailer",
    "landing_page": "Landing Page",
}

CONTENT_TYPE_CONTRACTS = {
    # Spec Section 3.4. The budget - 120-180 words - is NOT carried here: it
    # lives in `content_gates.WORD_BUDGETS`, which is the specification's own
    # table, and a miss there is "regenerate once" rather than a hard fault.
    # Carried in both places it would be both, and a 119-word email would be
    # withheld from the seller instead of rewritten.
    "email": {
        "title": "Email", "subtitle": "Personalized executive outreach email",
        "required": ["subject_line", "opening", "body_sections", "cta"],
        "sections": (1, 3), "subject_max": 80, "email_shaped": True,
        "subject_prefix": "Re: ",
        "shape": _EMAIL_SHAPE,
    },
    # Sahaj, 27 Sep: "Formats that we need to support - email, linkedin
    # message, One pager on how HP portfolio can deliver value for the
    # customer". A direct message to one person, not a post: no headline, no
    # hashtags, short enough to send as a connection note.
    # Spec Section 3.4: 60-110 words, one or two body paragraphs, and no
    # `greeting` key in the contract at all - "a separate greeting key is the
    # most common route to a 'Hi there,' on an unfilled role". There never was
    # one here. The budget is G12's, as above.
    "linkedin_message": {
        "title": "LinkedIn Message", "subtitle": "Short direct message to one contact",
        "required": ["opening", "body_sections", "cta"],
        "sections": (1, 2),
        "shape": ("A direct LinkedIn message to one person - NOT a public post, so no headline and "
                  "no hashtags. opening: one personalised line that references something real "
                  "about their remit or the account's evidence - a generic opener that could be "
                  "sent to anyone is the failure this format is judged on. body_sections: one or "
                  "two short paragraphs naming the one HP line and the ONE capability that meets "
                  "it. cta: one specific, low-friction ask. 60-110 words in total. Do not write a "
                  "greeting or a sign-off."),
    },
    # Spec Section 3.4: "This format does not exist in any current build. It is
    # a structured document, not prose, and the structure is what makes it
    # checkable." So it supersedes HP_ABX_v3_final's four fixed headings
    # (Account Challenge; How HP Helps; Proof Points; Next Step) with title,
    # subtitle, why_now, 2-3 evidence-backed pillars, the HP play and the ask.
    #
    # The structure is additive. `_validate_asset` projects it onto the
    # headline/opening/body_sections/cta envelope every renderer and the stored
    # asset history already read, so nothing downstream needs a second path and
    # a one-pager saved before today still renders.
    #
    # `proof_point` is the one key in the specification's contract the model
    # does NOT get. Rule 4 makes the HP line something it has to earn from the
    # remit and the evidence, so it is never shown a case study up front -
    # `_attach_proof_point` adds one afterwards, chosen from the line it
    # settled on. Handing it the study would hand it the product to work
    # backwards from, which is the failure that rule exists to prevent.
    "one_pager": {
        "title": "One-Pager", "subtitle": "How HP's portfolio can deliver value for this customer",
        "structured": True,
        "headings": True,
        "required": ["headline", "subtitle", "why_now", "pillars", "cta"],
        "optional": ["hp_play"],
        # The derived body: 2-3 pillars, then the HP play and the Proof Points
        # section Python attaches - so between two and five sections.
        "sections": (2, 5),
        "shape": ("A one-page executive brief for the account, returned as structure rather than "
                  "prose. headline: the title - under 70 characters, names the account and the "
                  "subject, not a slogan. subtitle: one line saying who this is for and what it "
                  "covers. why_now: 2-3 sentences on the account-specific trigger, drawn only from "
                  "the evidence. pillars: EXACTLY 2 or 3 - each with a short specific heading, a "
                  "'challenge' saying what the evidence shows, an 'hp_response' naming ONE concrete "
                  "HP capability that answers it (not a benefit list), and its own 'evidence_used' "
                  "citing at least one label. A pillar with no evidence is not a pillar; if the "
                  "evidence supports only one, return one and say so in why_now rather than pad to "
                  "two. hp_play: the single HP line the evidence earns and the one thing about it "
                  "that matters to this persona - omit the key entirely if no line is earned. cta: "
                  "the ask, one sentence, bounded by the committee angle. 350-500 words in total. "
                  "No subject_line and no proof point - a case study is attached afterwards."),
    },
}

# The HP lines the prompt may name, from the one list that also validates the
# answer. Typed out by hand it listed six while `HP_PRODUCT_LINES` accepted
# seventeen, so an asset could never name HP Care Pack Services, the lifecycle
# or deployment services, HP IQ or Original HP Ink - all of which the rulebook
# now carries rules for and all of which would have passed validation. Asking
# for a name the validator rejects, or withholding one it accepts, are the same
# bug in opposite directions; deriving it makes both impossible.
HP_LINES_FOR_PROMPT = ", ".join(HP_PRODUCT_LINES)

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
              + _derive_client_personas(account_id)
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


def _account_evidence(firmo_records: list[dict],
                      account_id: str = "") -> tuple[str, list[tuple[str, str]]]:
    """Spec row 3: Business Description and industry fields from firmographics.
    Returns (company_name, [(name, text), ...]). Nothing else is account evidence."""
    if not firmo_records:
        return "", []
    f = firmo_records[0]
    # DEC-052: the audit sheet name, not the vendor's name for the domain.
    name = account_display_name(account_id, f)
    desc = str(f.get("Business Description") or f.get("business_description") or "").strip()
    industry = _firmo_industry(f)
    items = []
    if desc:
        items.append(("Business description", desc))
    if industry:
        items.append(("Industry", industry))
    return name, items


# How much of each published surface reaches the prompt. Deliberately small:
# Rule 6 asks the opening to name the ONE item that matters "not a tour of the
# account", and an evidence block with twenty lines in it is a tour waiting to
# happen. These are the counts at which a seller still recognises their own
# account and the model still has to choose.
EVIDENCE_TECH_FAMILIES = 5
EVIDENCE_INTENT_THEMES = 3
EVIDENCE_SIGNALS = 3
EVIDENCE_PLAYS = 3
EVIDENCE_FILINGS = 2


def _wdata(db, account_id: str, key: str) -> dict:
    """One published widget's data, or {} when it has not been built."""
    return (widget_store.get(account_id, key, db=db) or {}).get("data") or {}


def _published_evidence(db, account_id: str) -> list[tuple[str, str]]:
    """The account's own published intelligence, as labelled evidence lines.

    Tuning row 8, Column 4. Each line comes from the widget that owns that
    judgement rather than from the dataset underneath it, so the copy cannot
    contradict the dashboard: if Live Signals gated a headline out, Content
    Studio never sees it, and if the Opportunity Map dropped a play for having
    no timing signal, no email is written around it.

    Every line is skipped when its widget has nothing to say. An account with
    no technographics simply has no technology line - there is no placeholder
    and nothing is inferred from the absence.
    """
    items: list[tuple[str, str]] = []

    # -- the installed estate -------------------------------------------------
    tech = _wdata(db, account_id, "tech_stack_matrix")
    families = ((tech.get("stack_view") or {}).get("families") or [])
    total = tech.get("total_tech_count")
    if total and families:
        named = ", ".join(
            "%s %s" % (f.get("family"), f.get("count"))
            for f in families[:EVIDENCE_TECH_FAMILIES] if f.get("family"))
        basis = (tech.get("technology_basis") or {}).get("basis") or "detected estate"
        items.append(("Technology estate",
                      "%s technologies in the %s; by family - %s"
                      % (total, basis, named)))

    # -- research intent ------------------------------------------------------
    intent = _wdata(db, account_id, "intent_category_summary")
    themes = [t for t in (intent.get("themes") or []) if t.get("theme")]
    if themes:
        provider = (intent.get("provider") or {}).get("name") or "the intent provider"
        as_of = (intent.get("observation") or {}).get("as_of") or ""
        named = "; ".join(
            "%s (%s topics, %s intensity)"
            % (t.get("theme"), t.get("topic_count"), str(t.get("intensity") or "").lower())
            for t in themes[:EVIDENCE_INTENT_THEMES])
        # The disclaimer travels with the line. Research activity read as a
        # buying decision is the misreading this data invites, and the model
        # is the last place it should be introduced.
        items.append(("Research intent",
                      "%s research activity%s - %s. This is research, not "
                      "confirmed buying intent."
                      % (provider, " as of " + as_of if as_of else "", named)))

    # -- catalysts the Live Signals gate published ----------------------------
    triggers = (_wdata(db, account_id, "opportunity_trigger_signals").get("triggers")
                or _wdata(db, account_id, "news_signals_feed").get("signals") or [])
    headlines = [" ".join(str(t.get("headline") or "").split())
                 for t in triggers if t.get("headline")]
    if headlines:
        items.append(("Published signals",
                      "; ".join(headlines[:EVIDENCE_SIGNALS])))

    # -- qualified opportunities ---------------------------------------------
    plays = _wdata(db, account_id, "opportunity_narrative_plays").get("opportunity_plays") or []
    named_plays = ["%s (%s)" % (p.get("title"), str(p.get("priority") or "").lower())
                   for p in plays[:EVIDENCE_PLAYS] if p.get("title")]
    if named_plays:
        items.append(("Qualified opportunities",
                      "the Opportunity Map carries %d play%s for this account - %s"
                      % (len(plays), "" if len(plays) == 1 else "s",
                         "; ".join(named_plays))))

    # -- filings --------------------------------------------------------------
    filings = (_wdata(db, account_id, "exec_key_metrics").get("filings_on_record")
               or {}).get("filings") or []
    titles = [" ".join(str(f.get("title") or f.get("headline") or "").split())
              for f in filings if (f.get("title") or f.get("headline"))]
    if titles:
        items.append(("Filings on record", "; ".join(titles[:EVIDENCE_FILINGS])))

    return items


def _is_named_person(persona: dict) -> bool:
    """Is this persona a specific person, or a role?

    Two kinds are: a Source A contact from the Stakeholder Map, and a client
    target role the client has told us who fills. The second is not obvious -
    a client role is a ROLE until the coverage sheet names someone in it, and
    then it is that person. Everything downstream turns on the distinction:
    which fields the model is given, which rule it is held to, whether it may
    write a name, and how the email opens. One predicate, so those five answers
    cannot disagree with each other.
    """
    kind = persona.get("kind")
    return kind == "named" or (kind == "client_role" and bool(persona.get("is_filled")))


# Rules 10 and 11 are per-persona, and a persona outside the eight has neither
# a matrix row nor an assigned angle. Rather than leave the rule blank - which
# reads to the model as "no constraint" - the fallback states the whole line
# list and the general rule, which is what the prompt said before the matrix
# existed. Only a legacy saved asset can reach it.
def _allowed_lines_for(persona: dict) -> str:
    try:
        return ", ".join(bp.allowed_lines(persona["id"]))
    except bp.UnknownPersona:
        return HP_LINES_FOR_PROMPT


def _denied_lines_for(persona: dict) -> str:
    try:
        denied = bp.denied_lines(persona["id"])
    except bp.UnknownPersona:
        return "none recorded for this persona - Rule 4 still applies in full"
    return ", ".join(denied) or "none"


def _angle_for(persona: dict) -> str:
    try:
        return bp.angle(persona["id"])
    except bp.UnknownPersona:
        return (persona.get("buying_committee_persona")
                or "not supplied - ask for a conversation")


def _persona_evidence(persona: dict) -> list[tuple[str, str]]:
    """What the model may know about the target, shaped by persona kind."""
    kind = persona["kind"]
    # The pack supplies its own "Role" line for the eight, so the client_role
    # branch starts empty rather than seeding one and getting it twice.
    items = [] if kind == "client_role" else [("Role", persona["title"])]
    if kind == "client_role":
        # Spec Section 3.3, slot 2: [P1]-[P5] from the pack, then the contact
        # as [P6] and [P7] where the role is filled.
        #
        # The pack's goals, pain points, value drivers and decision criteria
        # are deliberately NOT here. The specification is explicit about why:
        # injecting them makes the model write the persona's pain points back
        # to the persona as though they were account evidence, which reads as
        # presumption and breaks Rule 2a. This block says who is being written
        # to; the account block says what is true.
        # The pack where the id is one of the eight; the persona's own fields
        # otherwise. An asset saved before the narrowing carries an older id,
        # and it must still render rather than raise on the way to a screen.
        try:
            for _label, text in bp.generation_evidence(persona["id"]):
                field, _, value = text.partition(": ")
                items.append((field, value))
        except bp.UnknownPersona:
            items.append(("Role", persona["title"]))
            if persona.get("department"):
                items.append(("Department", persona["department"]))
            if persona.get("buying_committee_persona"):
                items.append(("Buying-committee angle",
                              persona["buying_committee_persona"]))
        if persona.get("is_filled"):
            items.append(("Name", persona.get("full_name") or "Unknown Contact"))
            if persona.get("actual_job_title"):
                items.append(("Actual job title", persona["actual_job_title"]))
        # [P6] and [P7] are omitted entirely when unfilled - not emitted empty.
        # An empty slot invites the model to fill it.
        return items
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
        # Only when there is one. "Seniority: " with nothing after it is a
        # labelled line the model can cite and learn nothing from.
        if persona.get("seniority"):
            items.append(("Seniority", persona["seniority"]))
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
# A client target role is two different things depending on whether the client
# found someone for it, and the header has to say which - the model is told to
# write to a person or to a role on the strength of this line.
CLIENT_ROLE_HEADERS = {
    True: "CLIENT TARGET ROLE - the client's buying committee (company_personas), "
          "filled by a named contact",
    False: "CLIENT TARGET ROLE - the client's buying committee (company_personas), "
           "no contact identified yet",
}


def _persona_header(persona: dict) -> str:
    """The line after "TARGET PERSONA" in the system prompt."""
    kind = persona.get("kind")
    if kind == "client_role":
        return CLIENT_ROLE_HEADERS[bool(persona.get("is_filled"))]
    return PERSONA_KIND_HEADERS.get(
        kind, PERSONA_KIND_HEADERS["archetype"])


# Placeholders in the schema are written <like this>, so an echoed placeholder is
# recognisable and discarded rather than published as content.
_PLACEHOLDER_RE = re.compile(r"^<[^<>]*>$")
_FIELD_SCHEMA = {
    "subject_line": '"<subject line>"',
    "headline": '"<headline>"',
    "opening": '"<first paragraph - names one specific evidence item>"',
    "cta": '"<one concrete next step>"',
    "hashtags": '["#<specific tag>", "#<specific tag>"]',
    # The 1-Pager's structured keys (spec Section 3.4).
    "subtitle": '"<one line: who this is for and what it covers>"',
    "why_now": '"<2-3 sentences: the account-specific trigger, from the evidence only>"',
    "hp_play": '"<the one HP line the evidence earns and what about it matters to this persona '
               '- omit this key entirely if no line is earned>"',
}

_PILLAR_SCHEMA = ('{"heading": "<short, specific>", '
                  '"challenge": "<what the evidence shows>", '
                  '"hp_response": "<ONE concrete HP capability that answers it>", '
                  '"evidence_used": ["A2"]}')
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
        elif f == "pillars":
            lines.append(f'    "pillars": [{_PILLAR_SCHEMA}, {_PILLAR_SCHEMA}]')
        else:
            lines.append(f'    "{f}": {_FIELD_SCHEMA[f]}')
    lines += ['    "hp_products": ["<HP line from the list above - or leave the list empty>"]',
              '    "evidence_used": ["A1", "P1"]',
              '    "persona_framing": "<one sentence: why this angle for this persona>"']
    return '{\n  "asset": {\n' + ",\n".join(lines) + '\n  }\n}'


def _persona_rule(kind: str, company_name: str, contract: dict,
                  persona_filled: bool = False) -> str:
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
    if kind == "client_role":
        if persona_filled:
            return (
                "THIS ROLE IS ONE THE CLIENT ASKED US TO REACH, AND THE CLIENT HAS NAMED THE "
                "PERSON IN IT. Write to that person and to the remit their title implies. NEVER "
                "state or imply who they report to, their private concerns, workload, opinions or "
                "budget. Their buying-committee angle bounds the ask, and the client supplies "
                "one of five:\n"
                "   Economic Buyer -> a decision-oriented ask is acceptable.\n"
                "   Technical Buyer -> ask for an evaluation, a technical review or a pilot; "
                "never a decision or a commercial term.\n"
                "   Finance - Budget Owner -> ask about cost, lifecycle and the shape of the "
                "case; never quote a price or discount, and never imply a budget exists.\n"
                "   Gatekeeper - Procurement & Legal -> ask about the process - how a vendor is "
                "evaluated, what documentation is needed; never pitch a product to them and "
                "never ask them to choose one.\n"
                "   Influencer / Line-of-Business Champion -> ask what their teams need and "
                "offer to show it; never a decision.\n"
                "   none supplied -> ask for a conversation."
            )
        return (
            "THIS IS A ROLE THE CLIENT ASKED US TO REACH, AND NO PERSON HAS BEEN IDENTIFIED IN "
            f"IT AT {company_name}. The role is real - the client named it as a target - so you "
            "may write to what it would be weighing. You may NOT name anyone, greet anyone, or "
            "imply you know who holds it. Address the role itself (\"As the leader responsible "
            "for ...\"), and hedge anything the evidence does not state."
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


def _request_fingerprint(evidence_cells: list[str], persona: dict, content_type: str,  # noqa: PLR0913, PLR0917 - cache keys, each one a thing that must invalidate
                         topic: str, additional_context: str,
                         instructions_text: str, guardrails_text: str,
                         case_studies_version: str = "",
                         cited_above: set | None = None) -> str:
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
        # A one-pager stores the case study in its Proof Points section, so
        # reloading the corpus has to rebuild the assets that quote it.
        "case_studies_version": case_studies_version,
        # Content Studio chooses last, so a study claimed by any of the three
        # standing surfaces changes what this asset may cite.
        "cited_above": sorted(cited_above or ()),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


# Account-agnostic by construction: one template serves every account. What
# differs per account arrives as data - the evidence blocks, the persona, and
# the account_instructions / account_guardrails documents an account team edits
# without a deploy. Never write an account's name, sector or example into it.
def _build_system_prompt(company_name: str, contract: dict, account_block: str,  # noqa: PLR0913, PLR0917 - long signature predates the lint gate
                         persona: dict, persona_block: str, topic: str,
                         additional_context: str, instructions_text: str,
                         guardrails_text: str) -> str:
    label = contract["title"]
    kind = persona["kind"]
    return f"""You are an expert ABM strategist and copywriter for HP Inc. ("HP"). You write one {label} for an HP seller to use with a target at {company_name}.

ACCOUNT EVIDENCE (use only this for any claim about {company_name}):
{account_block or 'No account evidence supplied. Make no claim about the account.'}

TARGET PERSONA ({_persona_header(persona)}):
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
5. PERSONA RULE. {_persona_rule(kind, company_name, contract, _is_named_person(persona))}
6. "opening" must name at least one item from the evidence above by its content, not by its label, and it must be the ONE item that matters for this persona and this topic - not a tour of the account. The first sentence a reader sees is the one that proves the seller knows this account.
7. "evidence_used" lists the labels ([A1], [P2] ...) you actually drew on. Only labels written above. It is checked.
8. VOICE. Write as HP - "At HP, we ..." - confident and specific, to a busy senior professional. Every paragraph must carry a concrete item from the evidence or a concrete thing the HP line gives their teams; a paragraph that could be sent to any company unchanged is a failed paragraph.
   - Do NOT use the concessive template "<praise> ... However, <vague upside>".
   - Do NOT write hollow abstractions: "as threats evolve", "unlock value", "drive efficiencies", "uncover opportunities".
   - No benefit lists and no superiority claims. "Robust performance, enhanced security features and streamlined manageability" and "industry-leading" say nothing about this account and nothing checkable about HP. Name ONE concrete capability instead - it beats four adjectives.
   - No "I hope this finds you well". No exclamation marks.
   - Windows 10 support ENDED in October 2025. Never build urgency on it as though the date were still
     ahead - no "before the deadline", no "ahead of end of support". An estate still running Windows 10
     is a present fact and may be named as one; these roles lived through that deadline and copy that
     puts it in the future tells them the sender was not paying attention.
9. Omission is the default: leave out any key you cannot fill honestly. Never emit an empty string to fill a slot.
10. PERSONA-LINE ELIGIBILITY. This persona may only be offered the HP lines listed here: {_allowed_lines_for(persona)}.
    These lines are FORBIDDEN for this persona and must not be named, described or alluded to, however well the account evidence might seem to support them: {_denied_lines_for(persona)}.
    A forbidden line is not a weak answer, it is a rejected one. If the only line the account evidence earns is a forbidden one, name no product and write the discovery-led piece per Rule 4. This is checked mechanically after generation.
11. THE ASK IS BOUNDED BY THE COMMITTEE ANGLE. This persona's angle is {_angle_for(persona)}. The closing ask must stay inside it:
    Economic Buyer -> a decision-oriented ask is acceptable.
    Technical Buyer -> ask for an evaluation, a technical review or a pilot; never a decision and never a commercial term.
    Finance - Budget Owner -> ask about cost, lifecycle and the shape of the case; never quote a price or a discount, and never imply a budget exists.
    Gatekeeper - Procurement & Legal -> ask about the process only - how a vendor is evaluated, what documentation is needed. Never pitch a product to them and never ask them to choose one.
    An ask outside the angle is a failed output even if everything else is correct.

OUTPUT CONTRACT - {label}:
{contract['shape']}
Required keys: {', '.join(contract['required'])}. Return ONLY the keys shown below; any other key is discarded.

Output JSON (replace every <placeholder> with real content):
{_output_schema(contract)}
"""


def _parse_sections(raw_sections, headed: bool) -> list[dict]:
    """The body paragraphs, normalised to {heading, text}.

    A model that returns bare strings instead of objects is accommodated - the
    paragraphs are what matter - and an unfilled placeholder is dropped rather
    than published. A heading on a format that has none is discarded here, so
    nothing downstream has to know which formats carry them.
    """
    out = []
    for section in (raw_sections or []):
        if isinstance(section, str):
            if section.strip():
                out.append({"heading": None, "text": section.strip()})
            continue
        if not isinstance(section, dict):
            continue
        text = str(section.get("text") or "").strip()
        if not text or _PLACEHOLDER_RE.match(text):
            continue
        heading = str(section.get("heading") or "").strip() if headed else ""
        if not heading or _PLACEHOLDER_RE.match(heading):
            heading = ""
        out.append({"heading": heading or None, "text": text})
    return out


def _split_hashtags(raw_tags, cta: str) -> tuple[list[str], str]:
    """The post's hashtags, and the closing line with them taken out.

    A model asked for hashtags in their own field routinely puts them at the
    end of the closing line instead, which reads as a stray "#HybridWork" in
    the middle of the copy. They are moved rather than rejected. Generic tags
    are dropped, duplicates collapse, and at most three survive.
    """
    if isinstance(raw_tags, str):
        raw_tags = raw_tags.split()
    tags_in_cta = re.findall(r"#\w+", cta)
    cta = re.sub(r"\s*#\w+", "", cta).strip()
    hashtags: list[str] = []
    seen: set[str] = set()
    for candidate in [*(raw_tags or []), *tags_in_cta]:
        tag = "#" + re.sub(r"[^\w]", "", str(candidate).lstrip("#"))
        low = tag.lower()
        if len(tag) > 1 and low not in GENERIC_HASHTAGS and low not in seen:
            seen.add(low)
            hashtags.append(tag)
    return hashtags[:3], cta


def _parse_pillars(raw_pillars, labels: dict[str, str]) -> tuple[list[dict], list[tuple[str, str]]]:
    """The 1-Pager's pillars, kept only where they are actually pillars.

    A pillar with no heading or no challenge is not one. A label the prompt
    never supplied is stripped rather than shown - a citation that looks real
    to the seller and resolves to nothing is worse than no citation - and
    returned alongside, because G2 rejects an invented label and cannot see one
    that has already been removed.
    """
    out: list[dict] = []
    dropped: list[tuple[str, str]] = []
    for index, pillar in enumerate(raw_pillars or []):
        if not isinstance(pillar, dict):
            continue
        heading = str(pillar.get("heading") or "").strip()
        challenge = str(pillar.get("challenge") or "").strip()
        if not heading or not challenge or _PLACEHOLDER_RE.match(challenge):
            continue
        cited = [str(x).strip().strip("[]").upper()
                 for x in (pillar.get("evidence_used") or [])]
        where = "pillars[%d].evidence_used" % index
        dropped += [(where, c) for c in dict.fromkeys(cited) if c not in labels]
        out.append({
            "heading": heading,
            "challenge": challenge,
            "hp_response": str(pillar.get("hp_response") or "").strip(),
            "evidence_used": [c for c in dict.fromkeys(cited) if c in labels],
        })
    return out, dropped


def _validate_asset(raw, contract: dict, persona: dict, labels: dict[str, str],  # noqa: PLR0913, PLR0917 - one argument per source of truth the validator consults
                    ground, report: GroundingReport, banned_names: list[str],
                    industry: str = "",
                    audit: list | None = None) -> tuple[dict | None, list[str], list[str]]:
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
    sections = _parse_sections(a.get("body_sections"), bool(contract.get("headings")))

    # Spec Section 3.4: the 1-Pager is structure, not prose. Parse it, then
    # project it onto headline / opening / body_sections / cta - the envelope
    # every renderer, the asset history and the Message Evaluator already read.
    # One envelope means the checks below (grounding, banned phrases, names,
    # competitors, the word count) see this format without a second code path.
    pillars: list[dict] = []
    dropped_labels: list[tuple[str, str]] = []
    subtitle = why_now = hp_play = ""
    if contract.get("structured"):
        subtitle, why_now, hp_play = _s("subtitle"), _s("why_now"), _s("hp_play")
        pillars, dropped_labels = _parse_pillars(a.get("pillars"), labels)
        # why_now IS the opening paragraph of the rendered document.
        opening = opening or why_now
        sections = [{"heading": p["heading"],
                     "text": " ".join(t for t in (p["challenge"], p["hp_response"]) if t)}
                    for p in pillars]
        if hp_play:
            sections.append({"heading": HP_PLAY_HEADING, "text": hp_play})
        # The Proof Points section is appended by `_attach_proof_point`, after
        # the HP line is settled. The model is never shown a case study.

    # Hashtags live in their own field; any the model left in the closing line move there.
    hashtags: list[str] = []
    if "hashtags" in fields:
        hashtags, cta = _split_hashtags(a.get("hashtags"), cta)

    present = {"subject_line": subject, "headline": headline, "opening": opening,
               "cta": cta, "body_sections": sections,
               "subtitle": subtitle, "why_now": why_now, "pillars": pillars}
    for k in contract["required"]:
        if not present.get(k):
            faults.append(f"{k} is missing")
    lo, hi = contract["sections"]
    if sections and not (lo <= len(sections) <= hi):
        faults.append(f"body_sections has {len(sections)} entries; {lo}-{hi} required")
    smax = contract.get("subject_max")
    if subject and smax and len(subject) > smax:
        faults.append(f"subject_line is {len(subject)} characters; at most {smax}")

    # HP_ABX_v3_final: "subject format 'Re: [specific initiative or challenge]'".
    # A hard fault, so a generic subject is rewritten rather than published.
    sprefix = contract.get("subject_prefix")
    if subject and sprefix and not subject.lower().startswith(sprefix.lower()):
        faults.append(f"subject_line must start with \"{sprefix}\" and then name the specific "
                      f"initiative or challenge; got \"{subject}\"")

    # HP_ABX_v3_final mandates the one-pager's four headings and their order.
    req_headings = contract.get("required_headings")
    if req_headings and sections:
        got = [(s["heading"] or "").strip().lower() for s in sections]
        want = [h.lower() for h in req_headings]
        if got != want:
            faults.append(
                "body_sections headings are "
                + (", ".join(f'"{s["heading"] or ""}"' for s in sections) or "(none)")
                + "; HP_ABX_v3_final requires exactly "
                + ", ".join(f'"{h}"' for h in req_headings) + " in that order")

    # `subtitle` is the only structured field the sections do not already
    # carry: why_now became the opening, the pillars and the play became
    # sections. Missing from here it would be the one line in the document no
    # gate ever read.
    texts = [subject, headline, opening, cta, framing, subtitle, " ".join(hashtags)] \
            + [s["text"] for s in sections] + [s["heading"] or "" for s in sections]
    blob = " ".join(t for t in texts if t).lower()

    # Word limits were stated in the prompt but never checked, so a model that
    # overran simply overran. HP_ABX_v3_final sets these as format rules, so
    # they are enforced here like any other contract term.
    #
    # Counted over the body a reader actually sees: the subject line, the
    # persona framing (an internal note) and the hashtags are excluded, since
    # none of them are part of the prose the limit governs.
    wmin, wmax = contract.get("words") or (None, None)
    if wmin or wmax:
        counted = [headline, subtitle, opening, cta] + [s["text"] for s in sections] \
                  + [s["heading"] or "" for s in sections]
        words = len(" ".join(t for t in counted if t).split())
        if wmax and words > wmax:
            faults.append(f"copy is {words} words; at most {wmax}")
        elif wmin and words < wmin:
            faults.append(f"copy is {words} words; at least {wmin}")

    for phrase in BANNED_PHRASES:
        if phrase in blob:
            soft.append(f"filler phrase \"{phrase}\"")
    if "!" in blob:
        soft.append("exclamation mark used")
    # A filled client role is a person the client named, so its own contact may
    # be addressed. Every other kind is a role type, and a public post names
    # nobody whatever the kind.
    if not _is_named_person(persona) or contract.get("public"):
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
    dropped_labels += [("evidence_used", u) for u in dict.fromkeys(used) if u not in labels]
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
    if contract.get("structured"):
        # Kept alongside the projection, not instead of it: G13 checks the
        # pillars, and Section 3.5 renders the PDF "from the JSON, never from a
        # model-generated blob" - which is only possible while the structure
        # survives storage.
        clean["subtitle"] = subtitle
        clean["why_now"] = why_now
        clean["pillars"] = pillars
        if hp_play:
            clean["hp_play"] = hp_play

    # Spec Section 6 (C8): the gate suite runs on every generation before the
    # seller sees it. It runs LAST, on the cleaned asset, so it judges what
    # would actually be published rather than what the model first returned.
    #
    # The checks above and the gates overlap deliberately - both look at
    # unsourced figures, both look at banned phrases - and that is cheaper than
    # deciding which one owns each rule. What the gates add is the persona:
    # the eligibility matrix and the committee angle, neither of which the
    # validator above can see.
    findings = content_gates.run(
        clean, persona_id=persona.get("id") or "", content_type=contract_key(contract),
        filled=_is_named_person(persona), corpus=ground,
        supplied_labels=list(labels), label_texts=labels,
        known_names=banned_names, competitors=COMPETITORS,
        industry=industry, required_keys=contract["required"],
        dropped_labels=dropped_labels)
    # The raw findings, for the audit ledger. A list the caller owns, because
    # only the caller knows which account this is - see `content_audit`.
    if audit is not None:
        audit.extend(findings)
    for finding in content_gates.rejects(findings):
        faults.append("%s: %s" % (finding["gate"], _gate_detail(finding)))
    for finding in content_gates.regenerates(findings):
        soft.append("%s: %s" % (finding["gate"], _gate_detail(finding)))
    if faults:
        return None, faults, soft
    return clean, [], soft


def _gate_detail(finding: dict) -> str:
    """One line a seller or a retry prompt can act on.

    These strings go back to the model as rewrite notes, so each one says what
    is wrong AND what to do instead. A gate that reports only the offending
    token ("Poly Collaboration") tells a rewrite nothing.
    """
    if finding.get("detail"):
        return str(finding["detail"])
    if finding.get("denied_line_named"):
        return ("%s is not a line this persona may be offered - name no HP product at "
                "all and write the discovery-led version" % finding["denied_line_named"])
    if finding.get("leaked_name"):
        return ("names \"%s\" - no contact has been identified in this role, so write to "
                "the role and name nobody" % finding["leaked_name"])
    if finding.get("invalid_label"):
        return ("%s cites %s, which the prompt never supplied - cite only the labels in the "
                "evidence block" % (finding.get("where_found") or "evidence_used",
                                    finding["invalid_label"]))
    if finding.get("offending_token"):
        return ("the figure %s is not in the evidence - remove it or use only figures the "
                "evidence states" % finding["offending_token"])
    if finding.get("phrase"):
        return "filler phrase \"%s\" - say the specific thing instead" % finding["phrase"]
    if finding.get("violation_type"):
        return str(finding["violation_type"])
    return finding["gate"]


def contract_key(contract: dict) -> str:
    """The content-type key for a contract, for the gates' word budgets."""
    for key, spec in CONTENT_TYPE_CONTRACTS.items():
        if spec is contract:
            return key
    return ""


# The branded-emailer and landing-page HTML renderer lived here: ~130 lines of
# inline CSS and markup composing an HP-branded email and page from the named
# fields. Both formats were retired with spec 1.2 and nothing else used it, so
# `rendered_html` is None on everything generated from now on.
#
# The field itself stays on the record. An asset generated under either format
# still displays: its HTML was composed at generation time and stored, and the
# UI reads it from there.


def _safe_fallback_asset(contract: dict, persona: dict, company_name: str, topic: str,
                         labels: dict[str, str]) -> dict | None:
    """The deterministic template, for when live generation cannot produce a
    grounded result.

    HP_ABX_v3_final, Fallback handling: "If live AI is unavailable, provide the
    deterministic template populated with the verified trigger, persona, HP play
    and next-step request fields."

    Every sentence here is composed in Python from evidence the account already
    carries, so it cannot hallucinate: there is no model in this path. It is
    marked `is_fallback` so the UI never presents it as generated copy.
    """
    if not labels:
        return None
    # The first account-evidence cell is the trigger; persona cells describe who
    # it is going to. Both are already labelled and grounded.
    trigger = next((v for k, v in labels.items() if k.startswith("A")), "")
    if not trigger:
        return None
    role = str(persona.get("title") or "this role").strip()
    subject_core = topic.strip() or "your current priorities"
    opening = (f"At HP, we track publicly reported developments at {company_name}. "
               f"This note follows one of them: {trigger}")
    body = (f"We work with {role} counterparts on the device, security and workforce "
            f"implications of changes like this. What applies to {company_name} depends on "
            f"your current estate and plans, which is why this is a question rather than a "
            f"recommendation.")
    cta = ("Would a short briefing be useful to establish whether this is relevant to your "
           "roadmap?")
    asset = {
        "opening": opening,
        "body_sections": [{"heading": None, "text": body}],
        "cta": cta,
        "persona_framing": f"Role-based version for {role}; composed from account evidence only.",
        "evidence_used": [k for k in labels if k.startswith("A")][:1],
    }
    if "subject_line" in set(_content_fields(contract)):
        asset["subject_line"] = f"Re: {subject_core}"[:contract.get("subject_max") or 80]
    if "headline" in set(_content_fields(contract)):
        asset["headline"] = f"{company_name}: {subject_core}"
    if contract.get("structured"):
        # The structured 1-Pager, composed rather than generated. Both pillars
        # carry an empty `hp_response`: this path names no HP capability at
        # all, because there is no model here to earn one and rule 4 will not
        # be satisfied by a template. The second pillar is the limit of what
        # the evidence supports, stated as such.
        asset["subtitle"] = f"Prepared for {role} at {company_name}"
        asset["why_now"] = opening
        cited = asset["evidence_used"]
        asset["pillars"] = [
            {"heading": "What was reported", "challenge": trigger,
             "hp_response": "", "evidence_used": cited},
            {"heading": "What it depends on", "challenge": body,
             "hp_response": "", "evidence_used": cited},
        ]
        asset["body_sections"] = [{"heading": p["heading"], "text": p["challenge"]}
                                  for p in asset["pillars"]]
        return asset
    if contract.get("headings"):
        # A headed format needs its mandated sections; the template fills the
        # ones it can stand behind and says nothing it cannot.
        req = contract.get("required_headings") or ["Account Challenge", "How HP Helps",
                                                    PROOF_POINTS_HEADING, "Next Step"]
        texts = {
            "Account Challenge": trigger,
            "How HP Helps": body,
            PROOF_POINTS_HEADING: "No HP proof point is attached to this account yet.",
            "Next Step": cta,
        }
        asset["body_sections"] = [{"heading": h, "text": texts.get(h, body)} for h in req]
    return asset


def _record_gate_audit(db, gate_attempts, *, account_id: str, persona_id: str,
                       content_type: str, asset_id: str, published: bool) -> None:
    """Each attempt's findings, tagged with what became of that attempt.

    The last attempt that produced an asset is the one the seller sees; every
    attempt before it was rejected and regenerated. Recording only the
    published one would leave `audit_line_eligibility.csv` empty on a batch
    where the model tried four times to sell Poly to a CFO - and Section 6
    calls that "the one to check first".
    """
    if not gate_attempts:
        return
    survivor = max((i for i, (_f, ok) in enumerate(gate_attempts) if ok),
                   default=None)
    for index, (findings, _ok) in enumerate(gate_attempts):
        if index == survivor:
            outcome = (content_audit.OUTCOME_PUBLISHED if published
                       else content_audit.OUTCOME_WITHHELD)
        elif survivor is None:
            outcome = content_audit.OUTCOME_WITHHELD
        else:
            outcome = content_audit.OUTCOME_REGENERATED
        content_audit.record(db, findings, account_id=account_id,
                             persona_id=persona_id, content_type=content_type,
                             outcome=outcome, asset_id=asset_id)


def _attach_proof_point(asset: dict, proof: dict, contract: dict) -> None:
    """Put an HP case study on a written asset, in place.

    The model does not choose this and is never shown one. It cannot be: rule 4
    makes the HP line something the model has to EARN from the persona's remit
    and the account evidence, so the line is not known until after it has
    written. Handing it a case study up front would be handing it the product to
    work backwards from, which is the failure that rule exists to prevent.

    So the study is chosen afterwards, from the line the model settled on, and
    attached by Python. Its sentence was verified against its own source when
    the corpus was loaded, so nothing here needs re-checking against this
    account's data - and must not be, since a case study is about a different
    company entirely.

    Where the format mandates a "Proof Points" section, that section's text is
    replaced. The contract tells the model to write account evidence there "if
    no HP proof point is available"; one now is, so the placeholder gives way.
    The swap is skipped if it would push the copy past the format's word limit,
    because that limit is a spec rule rather than a preference.
    """
    asset["hp_proof_point"] = proof["text"]
    asset["hp_proof_point_detail"] = proof

    if contract.get("structured"):
        # The structured 1-Pager has no mandated headings, so there is nothing
        # to replace: the Proof Points section is appended. `proof_point` is
        # the specification's key for it (Section 3.4) and Python fills it, for
        # the reason in the docstring above.
        asset["proof_point"] = proof["text"]
        sections = asset.get("body_sections") or []
        if any(str(sec.get("heading") or "").strip() == PROOF_POINTS_HEADING
               for sec in sections):
            return
        _lo, wmax = content_gates.WORD_BUDGETS.get(contract_key(contract), (None, None))
        if wmax and content_gates.asset_word_count(asset) + len(proof["text"].split()) > wmax:
            # Past the budget is past one page, and Section 3.5 says an
            # overflowing 1-Pager is out of budget rather than something to
            # shrink. The study stays on `hp_proof_point`, which the UI shows
            # beside the copy, so nothing is lost - it just is not in the page.
            return
        asset["body_sections"] = [*sections, {"heading": PROOF_POINTS_HEADING,
                                              "text": proof["text"]}]
        return

    headings = contract.get("required_headings") or []
    if PROOF_POINTS_HEADING not in headings:
        return

    sections = asset.get("body_sections") or []
    target = next((s for s in sections
                   if str(s.get("heading") or "").strip() == PROOF_POINTS_HEADING), None)
    if not target:
        return

    _wmin, wmax = contract.get("words") or (None, None)
    if wmax:
        counted = [asset.get("headline") or "", asset.get("opening") or "",
                   asset.get("cta") or ""]
        counted += [proof["text"] if sec is target else (sec.get("text") or "")
                    for sec in sections]
        counted += [sec.get("heading") or "" for sec in sections]
        if len(" ".join(t for t in counted if t).split()) > wmax:
            return

    target["text"] = proof["text"]


def _compose_greeting(persona: dict, contract: dict) -> str:
    """Salutation: the first name for a named contact. For an archetype, the role
    itself on a branded emailer ("Dear CIO,") or a placeholder the seller fills in
    on a plain email ("Dear [CIO Name],"). A placeholder for a hiring proxy, where
    no person is known."""
    kind = persona.get("kind")
    if _is_named_person(persona):
        first = str(persona.get("full_name") or "").strip().split(" ")[0]
        return f"Dear {first}," if first and first.lower() != "unknown" else "Dear [Name],"
    if kind in ("archetype", "client_role"):
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
        return "\n\n".join([*head, record.get("greeting") or "", *paras, *signoff]).strip()
    lines = [g["headline"]] if g.get("headline") else []
    lines.append(g.get("opening", ""))
    for sec in (g.get("body_sections") or []):
        lines.append((sec["heading"].upper() + "\n" if sec.get("heading") else "") + sec.get("text", ""))
    lines.append(g.get("cta", ""))
    return "\n\n".join(x for x in lines if x).strip()


def _build_generation_context(db, account_id: str, persona_id: str, content_type: str,
                              topic: str, additional_context: str) -> dict:
    """Everything both co-creation steps need: the validated request, the labelled
    evidence blocks, the grounding corpus and the cache fingerprint.

    Extracted so suggesting angles and writing the asset read the SAME evidence.
    If they drifted apart, the seller could pick an angle built on evidence the
    generator never sees. Raises ValueError for a request the account's data
    cannot serve.
    """
    content_type = str(content_type or "").strip().lower()
    contract = CONTENT_TYPE_CONTRACTS.get(content_type)
    if not contract:
        if content_type in RETIRED_CONTENT_TYPES:
            raise ValueError(
                "%s is no longer generated - the three formats are %s"
                % (RETIRED_CONTENT_TYPES[content_type],
                   ", ".join(CONTENT_TYPE_CONTRACTS[k]["title"]
                             for k in OFFERED_CONTENT_TYPES)))
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

    company_name, account_items = _account_evidence(firmo_records, account_id)
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

    # The rest of the account's published intelligence - the estate, the intent
    # themes, the gated signals, the qualified plays, the filings. Tuning row 8,
    # Column 4. Added after hiring so the two oldest lines keep their labels:
    # an asset stored yesterday cites [A1] and [A2], and those must still mean
    # the business description and the industry when it is re-read.
    account_items += _published_evidence(db, account_id)

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
    grid = widget_store.get(account_id, "stakeholder_contacts_grid", db=db)
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
                                       instructions_text, guardrails_text,
                                       cs.knowledge_version(db),
                                       cs.cited_above(db, account_id, cs.SURFACE_CONTENT))

    return {
        "contract": contract, "persona": persona, "company_name": company_name,
        "account_block": account_block, "persona_block": persona_block,
        "labels": labels, "ground": ground, "report": report,
        "banned_names": banned_names, "fingerprint": fingerprint,
        "instructions_text": instructions_text, "guardrails_text": guardrails_text,
        "topic": topic, "additional_context": additional_context,
        "content_type": content_type,
        # Only used to rank case studies. It is never a justification in the
        # copy - rule 2b forbids that - so it is carried separately from the
        # evidence block the model reads.
        "industry": _firmo_industry(firmo_records[0]) if firmo_records else "",
    }


def suggest_content_angles(account_id: str, persona_id: str, content_type: str,
                           topic: str, additional_context: str = "") -> dict:
    """Step 2 of the co-creation flow: propose 2-3 short angles for the seller to
    choose between, BEFORE any full asset is written.

    Dhruvi's requirement (docs/mails, "3. Human in the Loop / Co-creation") is
    "the user provides a brief -> the system suggests relevant options -> the
    user selects or adjusts the option -> the system generates the content
    accordingly". Each option here is a few lines, not a finished asset: one
    cheap call produces the whole set, and the expensive generate+retry loop
    runs once, on the angle the seller actually picked.

    Returns the content_angle_options widget document. Raises ValueError for a
    request the account's data cannot serve, exactly as generate_content_asset
    does, so the endpoint's error handling is unchanged.
    """
    db = get_db()
    now = datetime.now(UTC)
    ctx = _build_generation_context(db, account_id, persona_id, content_type,
                                    topic, additional_context)
    contract, persona, company_name = ctx["contract"], ctx["persona"], ctx["company_name"]

    def _payload(status_val: str, options: list, last_error: dict | None) -> dict:
        return {
            "account_id": account_id,
            "feature_key": "content_studio",
            "widget_key": "content_angle_options",
            "data_classification": "inferred",
            "status": status_val,
            "data": {
                "options": options,
                "persona_id": persona_id,
                "content_type": content_type,
                "content_type_label": contract["title"],
                "topic": topic,
                "evidence_labels": ctx["labels"],
                "last_error": last_error,
            },
            "source_datasets": ["firmographics", "prospect_contacts", "job_openings"],
            "extracted_at": now,
            "updated_at": now,
        }

    system_prompt = (
        _build_system_prompt(company_name, contract, ctx["account_block"], persona,
                             ctx["persona_block"], topic, additional_context,
                             ctx["instructions_text"], ctx["guardrails_text"])
        + "\n\nTHIS CALL IS DIFFERENT - DO NOT WRITE THE ASSET.\n"
        "Propose EXACTLY 3 distinct angles the seller could take, so they can pick one. "
        "An angle is a direction, not a draft: no salutation, no sign-off, no full copy.\n"
        "Each angle must be built on a DIFFERENT evidence item from the block above, and must "
        "cite that item's label in evidence_used. Three rewordings of one idea is a failed answer.\n"
        "Per angle return: \"label\" (3-6 words, how it reads in a picker); \"summary\" (ONE "
        "sentence on the argument it makes); \"opening_line\" (one sentence, the hook it would "
        "open on); \"evidence_used\" (labels from the evidence block, at least one).\n"
        "Use calibrated language for anything not written in the evidence.\n"
        'Output JSON: {"options": [{"label": "...", "summary": "...", '
        '"opening_line": "...", "evidence_used": ["A1"]}]}'
    )
    user_prompt = (f"Propose 3 angles for a {contract['title']} to {persona['title']} at "
                   f"{company_name} on \"{topic}\". Return JSON matching the schema.")

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)
    options, seen = [], set()
    if isinstance(llm_res, dict) and isinstance(llm_res.get("options"), list):
        for idx, o in enumerate(llm_res["options"]):
            if not isinstance(o, dict):
                continue
            label = str(o.get("label") or "").strip()
            summary = str(o.get("summary") or "").strip()
            opening = str(o.get("opening_line") or "").strip()
            if not (label and summary) or _PLACEHOLDER_RE.match(label):
                continue
            # Same grounding gate as the asset path: an angle that quotes a
            # figure the uploads never carried is dropped, not shown and then
            # caught later. A URL is stripped rather than rejecting the angle.
            bad_nums, _ = check_text(ctx["ground"], ctx["report"], f"angle{idx}",
                                     label, summary, opening)
            if bad_nums:
                logger.info("content studio: angle %d dropped, unsourced %s", idx, bad_nums)
                pipeline.guardrail(1, "angle quotes an unsourced figure",
                                   angle=idx)
                continue
            key = summary.lower()
            if key in seen:
                continue
            seen.add(key)
            options.append({
                "option_id": hashlib.sha1(
                    f"{ctx['fingerprint']}:{label}".encode()).hexdigest()[:12],
                "label": label,
                "summary": summary,
                "opening_line": opening,
                "evidence_used": [lab for lab in (o.get("evidence_used") or [])
                                  if lab in ctx["labels"]],
            })

    if not options:
        # No angles is not a failure to hide: the seller can still generate
        # directly, so the widget says so rather than blocking the feature.
        return _payload("empty", [], {
            "notice": "No angles could be proposed for this brief. You can generate directly instead.",
            "at": now.isoformat(),
        })

    payload = _payload("available", options[:3], None)
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "content_angle_options"},
        {"$set": payload}, upsert=True)
    return payload


def generate_content_asset(account_id: str, persona_id: str, content_type: str,
                           topic: str, additional_context: str = "",
                           selected_angle: str = "") -> dict:
    """One cached GPT-4o call per (persona, type, topic, context, angle). Returns
    the content_generated_assets widget document. Raises ValueError for a request
    the account's data cannot serve (unknown persona or type, empty topic).

    `selected_angle` is the option the seller picked in the co-creation step. It
    is folded into the prompt AND the cache fingerprint, so picking a different
    angle regenerates rather than serving the previous angle's asset.
    """
    db = get_db()
    now = datetime.now(UTC)

    ctx = _build_generation_context(db, account_id, persona_id, content_type,
                                    topic, additional_context)
    contract, persona = ctx["contract"], ctx["persona"]
    company_name, labels = ctx["company_name"], ctx["labels"]
    account_block, persona_block = ctx["account_block"], ctx["persona_block"]
    ground, report, banned_names = ctx["ground"], ctx["report"], ctx["banned_names"]
    instructions_text, guardrails_text = ctx["instructions_text"], ctx["guardrails_text"]
    content_type, topic = ctx["content_type"], ctx["topic"]
    additional_context = ctx["additional_context"]

    # The chosen angle is part of the cache key: picking a different angle must
    # regenerate, not serve the asset written for the previous one.
    selected_angle = str(selected_angle or "").strip()[:TOPIC_MAX_CHARS]
    industry = ctx.get("industry") or ""
    fingerprint = ctx["fingerprint"] if not selected_angle else hashlib.sha1(
        (ctx["fingerprint"] + "|" + selected_angle.lower()).encode("utf-8")).hexdigest()

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
        pipeline.cache_hit("content_generated_assets",
                           "same request against unchanged evidence")
        payload = _payload("available", cached, existing_assets, None)
        db["account_widgets"].update_one(
            {"account_id": account_id, "widget_key": "content_generated_assets"},
            {"$set": payload}, upsert=True)
        return payload

    system_prompt = _build_system_prompt(company_name, contract, account_block, persona,
                                         persona_block, topic, additional_context,
                                         instructions_text, guardrails_text)
    if selected_angle:
        # The seller chose this angle in the co-creation step. It steers the
        # argument; it does not license anything the evidence does not carry,
        # so the grounding gate still applies to every word that comes back.
        system_prompt += (
            "\n\nTHE SELLER HAS CHOSEN THIS ANGLE - write to it:\n"
            f"{selected_angle}\n"
            "Build the copy around this argument. Every claim still has to stand on the "
            "evidence block above; the angle does not authorise a fact that is not there.")
    user_prompt = (f"Write the {contract['title']} for {persona['title']} at {company_name} "
                   f"on the topic \"{topic}\". Return JSON matching the schema.")

    attempts: list[list[str]] = []
    # Every attempt's raw gate findings, paired with whether that attempt
    # produced a publishable asset. Written to the audit ledger below, once the
    # loop has finished and it is known which attempt actually stood.
    gate_attempts: list[tuple[list, bool]] = []

    def _draft(extra_instruction: str = "") -> tuple[dict | None, list[str], list[str]]:
        """One generate -> validate -> bounded-retry cycle. Returns
        (asset, faults, style_warnings); asset is None if nothing passed."""
        sys_prompt = system_prompt + extra_instruction
        best: tuple[dict, list[str]] | None = None   # cleanest publishable draft seen

        def _consider(a, sf):
            nonlocal best
            if a is not None and (best is None or len(sf) < len(best[1])):
                best = (a, sf)

        llm_res = generate_gpt4o_json_completion(sys_prompt, user_prompt)
        if llm_res is None:
            return None, ["model returned nothing - the LLM API key is missing or the call failed"], []

        attempt_findings: list = []
        a, f, sf = _validate_asset(llm_res, contract, persona, labels, ground, report,
                                   banned_names, industry, audit=attempt_findings)
        attempts.append(f + sf)
        gate_attempts.append((list(attempt_findings), a is not None))
        _consider(a, sf)
        # Bounded retry, for style warnings as well as hard faults. The model is
        # told exactly what was rejected, not asked again blindly.
        for _round in range(RETRY_ROUNDS):
            if a is not None and not sf:
                break
            notes = f + [f"{w} - replace it with a specific statement about this account; "
                         "do not substitute a synonym" for w in sf]
            retry_system = sys_prompt + (
                "\n\nRETRY - YOUR PREVIOUS ANSWER WAS REJECTED.\n"
                "Fix exactly the faults below and return the COMPLETE asset object again - every "
                "key, carrying the parts that were already correct through unchanged.\n"
                + "\n".join(f"- {x}" for x in notes) + "\n"
                "Use calibrated language (\"may\", \"could\", \"suggests\", \"worth exploring\") for "
                "anything not written in the evidence."
            )
            retry_res = generate_gpt4o_json_completion(retry_system, user_prompt)
            if retry_res is None:
                break
            attempt_findings = []
            a, f, sf = _validate_asset(retry_res, contract, persona, labels, ground,
                                       report, banned_names, industry,
                                       audit=attempt_findings)
            attempts.append(f + sf)
            gate_attempts.append((list(attempt_findings), a is not None))
            _consider(a, sf)

        # Retry budget spent: publish the cleanest draft that had no hard fault,
        # carrying its remaining style warnings, rather than withhold everything.
        if (a is None and best is not None) or (a is not None and best is not None and len(best[1]) < len(sf)):
            a, sf = best
        return a, f, sf

    # HP_ABX_v3_final asks for 2-3 LinkedIn variants; every other format is a
    # single asset. Each variant is generated and validated independently, so a
    # variant that fails the gate is dropped rather than dragging the set down.
    want_variants = int(contract.get("variants") or 1)
    variants: list[dict] = []
    asset, faults, soft = None, [], []
    for i in range(want_variants):
        extra = ""
        if want_variants > 1:
            extra = ("\n\nTHIS IS VARIANT %d OF %d. Each variant must take a GENUINELY DIFFERENT "
                     "approach - a different hook, a different evidence item and a different "
                     "closing question. Do not reword one idea." % (i + 1, want_variants))
            if variants:
                prior = "; ".join((v["asset"].get("headline") or "")[:80] for v in variants)
                extra += "\nAlready written, do not repeat these openings: " + prior
        v_asset, v_faults, v_soft = _draft(extra)
        if v_asset is not None:
            variants.append({"asset": v_asset, "soft": v_soft})
            if asset is None:
                asset, faults, soft = v_asset, v_faults, v_soft
        elif asset is None:
            faults, soft = v_faults, v_soft

    if asset is None:
        logger.warning("content studio: generation rejected for %s/%s/%s: %s",
                       account_id, persona_id, content_type, faults)
        # Spec fallback: rather than returning nothing, populate the
        # deterministic template from the verified fields. It is composed in
        # Python, so it carries no model output and cannot hallucinate.
        asset = _safe_fallback_asset(contract, persona, company_name, topic, labels)
        is_fallback = asset is not None
        if not is_fallback:
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
        soft = ["live generation did not produce a grounded draft - this is the deterministic "
                "template, composed from verified account fields only"]
        variants = []
    else:
        is_fallback = False

    # An HP case study for the line the model earned. Attached to the primary
    # asset and to every variant, so a seller comparing LinkedIn drafts sees the
    # same reference on each rather than one arbitrary draft carrying it.
    #
    # Skipped for the deterministic fallback: that template exists because
    # generation failed its checks, and it names no HP line to match against.
    if not is_fallback:
        proof_lines: list[str] = []
        for product in asset.get("hp_products") or []:
            proof_lines.extend(line for line in cs.lines_for_hp_line(product)
                               if line not in proof_lines)
        # Content Studio chooses last (see `cs.SURFACE_ORDER`): a written asset
        # is generated on request and is the cheapest thing to re-run, so it
        # yields to the three standing surfaces rather than taking a customer
        # one of them is already built around.
        # Studies this surface has already used, read back off the assets it
        # has stored. Every other surface passes `used_here` from a set it
        # builds while looping; this one generates a single asset per call, so
        # there is no loop to accumulate in and the widget itself is the record.
        # Without it the same customer was chosen again on every asset - four
        # of five drafts on the first account carried one university.
        mine = {
            (a.get("generated") or {}).get("hp_proof_point_detail", {}).get("study_id")
            for a in (existing_assets or [])
            if isinstance(a, dict) and isinstance(a.get("generated"), dict)
        }
        proof = cs.allocate(
            db, proof_lines,
            industry=cs.normalise_industry(ctx.get("industry") or ""),
            signals=cs.signals_for_opportunity(topic, content_type),
            taken=cs.cited_above(db, account_id, cs.SURFACE_CONTENT),
            used_here={m for m in mine if m})
        if proof:
            for written in [asset, *[v["asset"] for v in variants]]:
                _attach_proof_point(written, proof, contract)

    record = {
        "asset_id": fingerprint[:16],
        "request_fingerprint": fingerprint,
        "prompt_version": CONTENT_PROMPT_VERSION,
        "persona": {k: persona.get(k) for k in ("id", "kind", "title", "subtitle", "source", "full_name")},
        "content_type": content_type,
        "content_type_label": contract["title"],
        "topic": topic,
        "additional_context": additional_context or None,
        # Which co-creation angle produced this, so the card can show what the
        # seller picked rather than leaving the choice invisible after the fact.
        "selected_angle": selected_angle or None,
        "generated": asset,
        "style_warnings": soft,
        "attempts": len(attempts),
        "evidence_labels": {lab: labels[lab] for lab in asset["evidence_used"]},
        "rendered_html": None,
        "grounding_report": report.as_dict(),
        # True when live generation failed and this is the deterministic
        # template. The UI must not present it as generated copy.
        "is_fallback": is_fallback,
        "generated_at": now.isoformat(),
    }
    # Spec Section 6: "Every gate produces a machine-readable audit row."
    # Written here rather than inside the loop because only now is it known
    # which attempt stood - the last publishable one - and a row that cannot
    # say whether the seller saw the draft is a row nobody can act on.
    _record_gate_audit(db, gate_attempts, account_id=account_id,
                       persona_id=str(persona.get("id") or ""),
                       content_type=content_type, asset_id=record["asset_id"],
                       published=not is_fallback)

    record["greeting"] = _compose_greeting(persona, contract) if contract.get("email_shaped") else None
    record["plain_text"] = _compose_plain_text(record, contract)

    # The remaining variants, each composed the same way so the seller can copy
    # any of them. `record` itself stays the first variant, so every existing
    # reader of `latest` is unaffected by this field's presence.
    if len(variants) > 1:
        record["variants"] = []
        for idx, v in enumerate(variants):
            v_rec = {**record, "generated": v["asset"], "style_warnings": v["soft"],
                     "variant_index": idx + 1,
                     "evidence_labels": {lab: labels[lab] for lab in v["asset"]["evidence_used"]}}
            v_rec["plain_text"] = _compose_plain_text(v_rec, contract)
            v_rec.pop("variants", None)
            record["variants"].append({
                "variant_index": idx + 1,
                "generated": v["asset"],
                "style_warnings": v["soft"],
                "plain_text": v_rec["plain_text"],
                "evidence_labels": v_rec["evidence_labels"],
            })
        record["variant_count"] = len(variants)
    assets = [x for x in existing_assets if x.get("request_fingerprint") != fingerprint]
    assets.insert(0, record)
    assets = assets[:ASSET_HISTORY_MAX]

    payload = _payload("available", record, assets, None)
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "content_generated_assets"},
        {"$set": payload}, upsert=True)
    return payload


@pipeline.feature("content_studio")
def extract_content_studio(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    firmo_records = _read_dataset_records(account_id, "firmographics")
    job_records = _read_dataset_records(account_id, "job_openings")

    pipeline.step("datasets", "", firmographics=len(firmo_records or []),
                  jobs=len(job_records or []))

    results = []

    # 1. Target Personas: the client's eight, and only the eight (spec
    #    Section 1.4). The five-tier fallback that used to sit here - named
    #    contacts, then hiring-derived role proxies, then seven generic
    #    archetypes - offered roles the programme does not write to, and the
    #    eligibility matrix in Section 2.3 has no row for any of them, so an
    #    asset generated for one could not be checked.
    #
    #    `_derive_named_personas`, `_derive_role_proxy_personas` and
    #    `ARCHETYPE_PERSONAS` stay in the module and stay in `_persona_by_id`:
    #    an asset already saved under one of their ids still has to render.
    #    They are simply no longer offered.
    target_personas = _derive_client_personas(account_id)
    filled = sum(1 for p in target_personas if p["is_filled"])
    persona_sources = {
        # Section 4.3 asks for this flag by name, so a later switch to
        # account-derived persona fields is one visible line rather than an
        # inference from the data.
        "source": bp.PERSONA_CARD_SOURCE,
        "pack_version": bp.PERSONA_PACK_VERSION,
        "client_role": len(target_personas),
        "filled": filled,
        "unfilled": len(target_personas) - filled,
    }
    pipeline.step("personas", "", offered=len(target_personas), filled=filled,
                  unfilled=len(target_personas) - filled,
                  source=bp.PERSONA_CARD_SOURCE)

    # 2. Content Types - the three the client asked for (Sahaj, 27 Sep). The
    #    other contracts stay defined so assets already generated still render.
    content_types = [{"id": k, "title": CONTENT_TYPE_CONTRACTS[k]["title"],
                      "subtitle": CONTENT_TYPE_CONTRACTS[k]["subtitle"]}
                     for k in OFFERED_CONTENT_TYPES]

    # 3. Topic pills - Sahaj, 27 Sep: "on topics - let's keep only the 5 HP BUs
    #    and live signals as topic". The live signals are the ones Live Signals
    #    published (gated, deduplicated, ranked), not raw feed headlines; an
    #    account with none published offers the five BUs only.
    feed = (widget_store.get(account_id, "news_signals_feed", db=db) or {})
    live_signal_topics = []
    if feed.get("status") == "available":
        for sig in (feed.get("data") or {}).get("signals") or []:
            headline = " ".join(str(sig.get("headline") or "").split())
            if headline and headline not in live_signal_topics:
                live_signal_topics.append(headline)
    sourced_topics = list(HP_BU_TOPICS) + live_signal_topics[:LIVE_SIGNAL_TOPICS_MAX]

    # 4. Business Context
    business_context = {}
    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]

        c_name = account_display_name(account_id, f)
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
        "source_datasets": ["prospect_contacts", "company_personas", "job_openings",
                            "firmographics", "google_news", "news_events"],
        "extracted_at": now,
        "updated_at": now
    }

    widget_store.put(account_id, "content_persona_context", context_payload, db=db)
    results.append(context_payload)

    # The generated-assets widget is a seller's history, not a function of the
    # account's data: under the regeneration engine it has no owner and the
    # read path reports "pending" until the first asset exists. The
    # placeholder below serves only the legacy direct-call paths.
    if run_context.current() is not None:
        return results

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
