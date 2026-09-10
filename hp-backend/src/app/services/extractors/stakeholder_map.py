import os
import io
import re
import csv
import json
import hashlib
import pandas as pd
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.grounding import (
    build_corpus, check_text, GroundingReport,
)

import logging
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

def resolve_field(row: dict, keys: list[str]) -> str | None:
    for k in keys:
        val = row.get(k)
        if val is not None:
            s = str(val).strip()
            if s and s.lower() not in ["none", "null", "nan", "[]"]:
                return s
    return None

# ==============================================================================
# DETERMINISTIC SCORING TABLES
# Every band, type and 0-100 score below is computed in Python. The LLM is never
# asked for a score, band, influence type, priority or relevance value.
# Composite weights are the HP_ABX_v3_final formula:
#   25% seniority + 25% HP relevance + 20% influence + 15% data completeness
#   + 15% priority
# ==============================================================================

COMPOSITE_WEIGHTS = {
    "seniority": 0.25,
    "hp_relevance": 0.25,
    "influence": 0.20,
    "data_completeness": 0.15,
    "priority": 0.15,
}

# --- 1. Seniority -------------------------------------------------------------
# Raw `Prospect job_level_main` -> standard band. "head" is a department-head
# role, so it bands with Director.
SENIORITY_BAND_MAP = {
    "c_suite": "C-Suite",
    "c-suite": "C-Suite",
    "cxo": "C-Suite",
    "vp": "VP",
    "vice_president": "VP",
    "director": "Director",
    "head": "Director",
    "manager": "Manager",
    "owner": "Manager",
}
# A c_suite tag is only honoured when the title corroborates it. HP_ABX_v3_final
# Feature 3 rule 4: "If the mapped seniority does not fit the original title,
# keep the original title and send only the mapped field for review."
# `office` separates a department name ("CIO Office") from a person
# ("Chief Operating Officer" - "Officer" is a different word).
OFFICE_NAME_RE = re.compile(r"\boffice\b", re.I)
EXECUTIVE_TITLE_RE = re.compile(
    r"\b(chief\s+\w+(\s+\w+)?\s+officer"
    r"|ceo|cio|coo|cto|cfo|ciso|president|managing\s+director)\b",
    re.I,
)
SENIORITY_UNCORROBORATED_BAND = "Manager"

SENIORITY_SCORES = {
    "C-Suite": 100,
    "VP": 75,
    "Director": 50,
    "Manager": 25,
    "Individual Contributor": 10,
}

# --- 2. HP relevance ----------------------------------------------------------
# Replaces the reference app's securityRelevance (Palo Alto leftover). Highest
# matching tier wins, scanned over normalised department + original title.
HP_RELEVANCE_TIERS = [
    (100, ["procurement", "infrastructure", "end user", "end-user", "workplace",
           "device", "fleet", "cio", "chief information", "information technology"]),
    (70, ["engineer", "architect", "network", "data cent", "data centre",
          "data center", "cloud", "devops", "security", "developer", "technology"]),
    (40, ["operations", "product", "executive", "business"]),
]
# A department slug suggests relevance but never asserts the top tier on its own -
# only a title keyword reaches 100. Source A's "Data" label maps to Information
# Technology, which would otherwise score an HR role in that department at 100.
HP_RELEVANCE_DEPT_TIERS = {
    "Information Technology": 70,
    "Engineering & Technical": 70,
    "Operations": 40,
    "Product Management": 40,
    "Executive": 40,
}
# A clearly non-IT title overrides an inflated department and caps the score.
NON_IT_TITLE_TERMS = ["employment relations", "people experience", "human resources",
                      "recruitment", "payroll", "tax", "legal", "audit",
                      "corporate communications", "industrial relations"]
NON_IT_TITLE_CAP = 40
HP_RELEVANCE_FLOOR = 20
HP_SKILL_TERMS = ["sap", "azure", "aws", "autocad", "catia", "vmware", "cisco", "windows"]
HP_SKILL_BONUS = 10

# --- 3. Influence -------------------------------------------------------------
INFLUENCE_SCORES = {
    "Decision Maker": 100,
    "Budget Holder": 85,
    "Champion": 70,
    # Raised from the reference app's 40. For a hardware sale the person
    # evaluating the estate outranks a generic influencer, and ABX Step 4 lists
    # them as peers.
    "Technical Evaluator": 60,
    "Influencer": 50,
    "Blocker": 30,
}
BUDGET_HOLDER_TITLE_TERMS = ["procurement", "infrastructure strategy", "purchasing", "sourcing"]
TECHNICAL_TITLE_TERMS = ["infrastructure", "engineer", "engineering", "collaboration", "it ",
                         "network", "cloud", "system", "technology", "developer", "software",
                         "application", "architect", "end user", "end-user", "data governance",
                         "technical", "devops", "operations excellence"]

# --- 3b. Play / role plausibility --------------------------------------------
# Title signals that make an HP line implausible for a contact. Used to hand the
# model a per-contact "do not propose" list, because a general instruction did
# not hold. Product semantics only - nothing account-specific.
PLAY_BLOCKED_BY_TITLE = {
    "HP Enterprise Printing & MPS": [
        "cloud", "infrastructure", "network", "data governance", "software",
        "application", "developer", "devops", "architect", "security",
        "business intelligence", "analytics", "cio", "engineering", "technology development",
    ],
    "Z by HP Workstations": [
        "employment relations", "people experience", "human resources", "recruitment",
        "payroll", "tax", "legal", "audit", "corporate communications",
        "industrial relations", "branch manager",
    ],
    "Poly Studio": [
        "tax", "legal", "audit", "payroll", "procurement",
    ],
}

# Canonical phrasings of the decision_power rule itself. The model echoed these
# back verbatim in v6 instead of writing a role-specific statement.
DECISION_POWER_ECHOES = [
    "this role typically participates in or owns decisions of this kind",
    "evaluation, standards and requirements influence only",
    "may discuss budget ownership and procurement authority",
    "advisory input only",
]


def blocked_plays_for(title: str | None) -> list[str]:
    """HP lines that do not plausibly follow from this contact's remit."""
    t = (title or "").lower()
    return [play for play, terms in PLAY_BLOCKED_BY_TITLE.items()
            if any(term in t for term in terms)]


def _is_rule_echo(text: str) -> bool:
    """True when decision_power just repeats the instruction back."""
    t = " ".join((text or "").split()).strip().lower().rstrip(".")
    return any(t == e or t.startswith(e) for e in DECISION_POWER_ECHOES)


# --- 4. Data completeness -----------------------------------------------------
DATA_COMPLETENESS_POINTS = {
    "base": 20,
    "linkedin": 15,
    "email": 20,
    "email_valid": 10,
    "phone": 20,
    "profile": 15,
}

# --- 5. Priority --------------------------------------------------------------
HIGH_PRIORITY_DEPTS = {
    "Information Technology",
    "Engineering & Technical",
    "Operations",
    "Executive",
}
PRIORITY_SCORES = {"High": 100, "Medium": 50, "Low": 10}

# --- Department normalisation -------------------------------------------------
# Two source vocabularies land in the same column: Apollo emits slugs, Source A
# emits short labels. Both normalise onto one set.
DEPT_LABELS = {
    "master_information_technology": "Information Technology",
    "master_engineering_technical": "Engineering & Technical",
    "master_operations": "Operations",
    "master_finance": "Finance",
    "master_legal": "Legal",
    "master_marketing": "Marketing",
    "master_sales": "Sales",
    "master_human_resources": "Human Resources",
    "product_management": "Product Management",
    "consulting": "Consulting",
    "c_suite": "Executive",
    "it": "Information Technology",
    "data": "Information Technology",
    "engineering": "Engineering & Technical",
    "operations": "Operations",
    "finance": "Finance",
    "legal": "Legal",
    "marketing": "Marketing",
    "sales": "Sales",
    "human resources": "Human Resources",
}
UNASSIGNED_DEPT = "Unassigned"

HP_RELEVANCE_BAND_THRESHOLDS = [(70, "high"), (40, "medium")]
PRIORITY_CONTACT_MIN_COMPOSITE = 60

# Bump when the talking-points prompt changes, so cached output is regenerated
# rather than served stale against an older set of instructions.
TALKING_POINTS_PROMPT_VERSION = 8


def normalize_department(raw: str | None) -> str:
    """Map either source vocabulary onto one department set.

    Multi-value rows ("c_suite; master_operations") resolve to the first
    non-executive function, falling back to Executive when that is all there is.
    """
    if not raw:
        return UNASSIGNED_DEPT
    parts = [p.strip().lower() for p in str(raw).replace(",", ";").split(";") if p.strip()]
    if not parts:
        return UNASSIGNED_DEPT
    for p in parts:
        if p in ("c_suite", "c-suite"):
            continue
        label = DEPT_LABELS.get(p)
        if label:
            return label
    for p in parts:
        label = DEPT_LABELS.get(p)
        if label:
            return label
    return str(raw).strip().title() or UNASSIGNED_DEPT


def seniority_band(raw: str | None, title: str | None = None) -> tuple[str, bool]:
    """Returns (band, source_conflict).

    A `c_suite` tag is trusted only when the title names the role. Where it does
    not - "CIO Office", "CEO Office Taks Force" - the row is office staff
    attached to an executive rather than the executive, so we band by the title
    and flag the disagreement. The original title is never altered.
    """
    if not raw:
        return "Individual Contributor", False
    key = str(raw).strip().strip('[]"\' ').lower()
    band = SENIORITY_BAND_MAP.get(key, "Individual Contributor")

    if band == "C-Suite":
        t = title or ""
        corroborated = bool(EXECUTIVE_TITLE_RE.search(t)) and not OFFICE_NAME_RE.search(t)
        if not corroborated:
            return SENIORITY_UNCORROBORATED_BAND, True

    return band, False


def normalize_phone(raw: str | None) -> str | None:
    """Undo the float typing Excel applies to phone columns during xlsx->CSV.

    "6281293986658.0" -> "+6281293986658". Corrects a type coercion; never
    invents a number, and no digit regrouping (spacing conventions differ per
    country and guessing them introduces a different kind of wrong).
    """
    if not raw:
        return None
    v = str(raw).strip()
    v = re.sub(r"\.0+$", "", v)
    plus = v.startswith("+")
    digits = re.sub(r"\D", "", v)
    if not digits:
        return None
    if plus or 10 <= len(digits) <= 15:
        return "+" + digits
    return digits


def score_seniority(band: str) -> int:
    return SENIORITY_SCORES.get(band, SENIORITY_SCORES["Individual Contributor"])


def score_hp_relevance(title: str | None, department: str, skills: str | None) -> int:
    haystack = f"{(title or '').lower()} {department.lower()}"
    tier = HP_RELEVANCE_DEPT_TIERS.get(department, 0)
    for score, terms in HP_RELEVANCE_TIERS:
        if score <= tier:
            break
        if any(t in haystack for t in terms):
            tier = max(tier, score)
            break
    if tier == 0:
        tier = HP_RELEVANCE_FLOOR

    t = (title or "").lower()
    if any(term in t for term in NON_IT_TITLE_TERMS):
        return min(tier, NON_IT_TITLE_CAP)

    if skills:
        s = skills.lower()
        if any(t in s for t in HP_SKILL_TERMS):
            tier = min(100, tier + HP_SKILL_BONUS)
    return tier


def hp_relevance_band(score: int) -> str:
    for threshold, band in HP_RELEVANCE_BAND_THRESHOLDS:
        if score >= threshold:
            return band
    return "low"


# Departments where an "IT Decision Maker" persona label is credible. Outside
# these the label is a segment tag, not evidence of authority over IT hardware.
PERSONA_DECISION_DEPARTMENTS = {
    "Information Technology",
    "Engineering & Technical",
    "Executive",
}


def assign_influence(persona: str | None, title: str | None,
                     band: str = "Individual Contributor",
                     department: str = UNASSIGNED_DEPT) -> tuple[str, str]:
    """ABX Step 4 cascade: procurement -> Budget Holder; C-suite and senior
    IT/Engineering leaders -> Decision Maker; technical roles -> Technical
    Evaluator; otherwise Influencer.

    The uploaded buying-committee persona is real evidence but a coarse segment
    label - in practice it marks most of an IT roster "IT Decision Maker", which
    collapses the whole buying group into one bucket. It is therefore used as a
    fallback where the title is uninformative, not as the primary signal.

    Champion and Blocker are never assigned: the spec allows Blocker only with
    evidence that someone can stop a purchase, and we hold none.

    Returns (influence_type, influence_source) so the deciding branch stays
    inspectable.
    """
    t = (title or "").lower()
    if any(term in t for term in BUDGET_HOLDER_TITLE_TERMS):
        return "Budget Holder", "title_budget_term"

    if band == "C-Suite":
        return "Decision Maker", "c_suite"

    # Hands-on technical remit is checked before the seniority rule below.
    # Our seniority column bands every "Head of ..." title as Director, so
    # testing seniority first would classify the entire engineering bench as
    # Decision Makers and leave the buying group with no evaluators.
    if any(term in t for term in TECHNICAL_TITLE_TERMS):
        return "Technical Evaluator", "technical_title"

    # A clearly non-IT title overrides an IT department label. The department
    # column is unreliable here - Astra's employment-relations lead is filed
    # under "Data" - and the same NON_IT_TITLE_TERMS that cap HP relevance must
    # also stop an HR, tax, legal or comms role inheriting IT authority.
    non_it_title = any(term in t for term in NON_IT_TITLE_TERMS)

    if (not non_it_title and band in ("VP", "Director")
            and department in ("Information Technology", "Engineering & Technical")):
        return "Decision Maker", "senior_in_it"

    # The persona column is a coarse segment tag, not a statement of authority:
    # 18 of Astra's 23 rows carry a Decision-Maker label, including finance,
    # sales and product roles. Taken at face value it hands IT purchasing
    # authority to a tax lead and two product owners, so it is gated.
    persona_l = (persona or "").lower()
    if "business decision maker" in persona_l:
        # Explicitly a BUSINESS decision maker - they decide for their own unit,
        # which says nothing about authority over IT hardware.
        return "Influencer", "persona_business_not_it"
    if "decision maker" in persona_l:
        if department in PERSONA_DECISION_DEPARTMENTS and not non_it_title:
            return "Decision Maker", "persona_gated"
        return "Influencer", "persona_outside_it"

    return "Influencer", "default_influencer"


def score_influence(influence_type: str) -> int:
    return INFLUENCE_SCORES.get(influence_type, INFLUENCE_SCORES["Influencer"])


def score_data_completeness(email: str | None, email_status: str | None,
                            phone: str | None, linkedin: str | None,
                            profile: str | None) -> int:
    pts = DATA_COMPLETENESS_POINTS["base"]
    if linkedin:
        pts += DATA_COMPLETENESS_POINTS["linkedin"]
    if email:
        pts += DATA_COMPLETENESS_POINTS["email"]
        if (email_status or "").strip().lower() == "valid":
            pts += DATA_COMPLETENESS_POINTS["email_valid"]
    if phone:
        pts += DATA_COMPLETENESS_POINTS["phone"]
    if profile:
        pts += DATA_COMPLETENESS_POINTS["profile"]
    return min(100, pts)


def assign_priority(department: str, band: str) -> str:
    """Department + band only - deliberately independent of the composite, so
    feeding it back in at 15% is not circular."""
    if department in HIGH_PRIORITY_DEPTS:
        return "High" if band in ("C-Suite", "VP") else "Medium"
    return "Low"


def score_priority(priority: str) -> int:
    return PRIORITY_SCORES.get(priority, PRIORITY_SCORES["Low"])


def composite_score(components: dict) -> int:
    return round(sum(components[k] * COMPOSITE_WEIGHTS[k] for k in COMPOSITE_WEIGHTS))


PAIN_POINT_MIN_WORDS = 12


def _is_evidence_label(text: str, evidence_labels: set[str]) -> bool:
    """True when the model echoed a supplied intent topic or headline back
    instead of writing a pain point.

    Prompt wording alone has proven unreliable here - it has failed in both
    directions - so the rule is enforced in code as well.
    """
    t = text.strip().lower().rstrip(".")
    if len(t.split()) < PAIN_POINT_MIN_WORDS:
        return True
    for label in evidence_labels:
        lab = label.strip().lower().rstrip(".")
        if not lab:
            continue
        if t == lab or (len(lab) > 20 and (t.startswith(lab) or lab.startswith(t))):
            return True
    return False


def _contacts_fingerprint(contacts: list[dict], account_context: str = "") -> str:
    """Stable hash of everything the talking points are generated from.

    The account context belongs here as much as the contacts do: the openers cite
    news, intent and technology evidence, so hashing contacts alone served stale
    text whenever the account's news changed but its roster did not.
    """
    basis = [
        {
            "id": c.get("contact_id"),
            "n": c.get("full_name"),
            "t": c.get("title"),
            "d": c.get("normalized_department"),
            "p": c.get("buying_committee_persona"),
            "s": c.get("skills"),
        }
        for c in contacts
    ]
    basis.sort(key=lambda x: str(x["id"]))
    payload = {"prompt_version": TALKING_POINTS_PROMPT_VERSION,
               "contacts": basis,
               "account_context": account_context}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _build_account_context(account_id: str) -> tuple[str, set[str]]:
    """Account-level inference context only - firmographics, technographics,
    intent_score, google_news, news_events. None of this becomes a contact fact.

    Also returns the set of raw evidence labels (intent topic names, news
    headlines) so the parser can reject output that merely echoes a label back
    instead of stating a pressure."""
    firmo = _read_dataset_records(account_id, "firmographics")
    techno = _read_dataset_records(account_id, "technographics")
    intent = _read_dataset_records(account_id, "intent_score")
    gnews = _read_dataset_records(account_id, "google_news")
    events = _read_dataset_records(account_id, "news_events")

    lines = []
    if firmo:
        f = firmo[0]
        desc = str(f.get("Business Description") or "").strip()
        industry = str(f.get("Linkedin Industry Category") or f.get("Naics Description") or "").strip()
        emp = str(f.get("Number Of Employees Range") or "").strip()
        rev = str(f.get("Yearly Revenue Range") or "").strip()
        lines.append(f"Industry: {industry or 'N/A'} | Employees: {emp or 'N/A'} | Revenue: {rev or 'N/A'}")
        if desc:
            lines.append(f"Business description: {desc}")

    if techno:
        stack = str(techno[0].get("Full Tech Stack") or "").strip()
        if stack:
            items = [s.strip() for s in stack.split(",") if s.strip()]
            lines.append(f"Installed technology ({len(items)} items): {', '.join(items[:40])}")

    labels: set[str] = set()
    topics = []
    for r in intent[:10]:
        name = str(r.get("Topic") or "").strip()
        sc = str(r.get("Composite Score") or "").strip()
        if name:
            topics.append(f"{name} ({sc})")
            labels.add(name.lower())
    if topics:
        lines.append("Intent research surges: " + "; ".join(topics))

    # Newest first. Taking the file's first ten rows fed the prompt whatever the
    # export happened to list first - for this account a 2017 headline and a 2022
    # press release - while a newly uploaded recent trigger sitting past row ten
    # was never seen at all.
    triggers = []
    seen = set()
    for r in gnews + events:
        h = str(r.get("event_headline") or r.get("news_announcements")
                or r.get("summary") or r.get("title") or "").strip()
        d = str(r.get("event_date") or r.get("effective_date") or "").strip()
        if not h or h.lower() in seen:
            continue
        seen.add(h.lower())
        dt = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(d[:10], fmt)
                break
            except (ValueError, TypeError):
                continue
        triggers.append((dt, f"- {h} ({d})" if d else f"- {h}"))
        labels.add(h.lower())

    # Undated rows sort last rather than being dropped - they are still evidence.
    triggers.sort(key=lambda t: t[0] or datetime.min, reverse=True)
    if triggers:
        lines.append("Recent news and trigger events:\n"
                     + "\n".join(line for _dt, line in triggers[:10]))

    context = "\n".join(lines) if lines else "No account-level context available."
    return context, labels


def generate_stakeholder_talking_points(account_id: str, contacts: list[dict],
                                        company_name: str) -> dict:
    """One GPT-4o call covering every contact. Returns the four inferred fields
    keyed by contact id. Never asked for scores, bands, or contact facts."""
    db = get_db()
    now = datetime.now(timezone.utc)
    # Built before the fingerprint: it must be covered by it, or a news change
    # leaves the cached openers citing a trigger that is no longer current.
    account_context, evidence_labels = _build_account_context(account_id)
    fingerprint = _contacts_fingerprint(contacts, account_context)

    existing = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "stakeholder_talking_points",
    })

    # Cached: reuse while the contacts AND the account evidence are unchanged.
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("contacts_fingerprint") == fingerprint):
        return existing

    # Grounding corpus: every cell of the datasets this feature is allowed to
    # reason over. A number or URL absent from it never reaches storage.
    ground = build_corpus({
        k: _read_dataset_records(account_id, k) for k in
        ("prospect_contacts", "firmographics", "technographics",
         "intent_score", "google_news", "news_events")
    })
    report = GroundingReport(ground, ["how_to_open", "hp_play_focus",
                                      "decision_power", "pain_points"])

    def _roster_block(subset):
        lines = []
        for c in subset:
            parts = [
                f'id={c["contact_id"]}',
                f'name={c.get("full_name") or "Unknown"}',
                f'title={c.get("title") or "N/A"}',
                f'department={c.get("normalized_department")}',
                f'seniority={c.get("seniority_band")}',
                f'influence={c.get("influence_type")}',
            ]
            if c.get("buying_committee_persona"):
                parts.append(f'buying_persona={c["buying_committee_persona"]}')
            if c.get("skills"):
                parts.append(f'skills={c["skills"][:180]}')
            if c.get("career_history"):
                parts.append(f'past_roles={c["career_history"][:180]}')
            blocked = blocked_plays_for(c.get("title"))
            if blocked:
                parts.append("DO_NOT_PROPOSE=" + "; ".join(blocked))
            lines.append("- " + " | ".join(parts))
        return chr(10).join(lines)

    def _system_prompt(roster: str) -> str:
        return f"""You are an expert ABM strategist for HP Inc. ("HP"). You write the opening angle an HP seller should use with each named contact at {company_name}.

ACCOUNT EVIDENCE (use only this for account-level claims):
{account_context}

CONTACT ROSTER (use only a contact's own record for anything about that person):
{roster}

CRITICAL RULES:
1. You represent HP Inc. Never refer to Dell, Lenovo, Huawei, Acer, Canon or Zoom as "our" product.
2. Ground every statement in that contact's own record or the account evidence above. Invent nothing.
3. Reference HP products by name (Z by HP Workstations, HP EliteBook/ProBook PCs, HP Wolf Security, Poly Studio, HP Enterprise Printing & MPS, HP DaaS, HP Anyware).
3a. AN HP PLAY MUST BE EARNED, NOT ASSIGNED. Before naming a product, the whole chain has to hold:
      this contact's role and department + their buying-committee persona + a relevant account trigger or installed technology -> a plausible HP product.
    Do NOT start from a product and work backwards to justify it. Do NOT give someone a product merely because every other contact has one.
    IF THE CHAIN DOES NOT HOLD: set "hp_play_focus" to "Account engagement / discovery", name NO product anywhere in "how_to_open", and open on this contact's own remit and what you want to learn from them. That is a correct answer, not a failure. A forced product match IS a failure.
    BAD (the product does not follow from the role): a CIO Office or Cloud Operations contact opened on HP Enterprise Printing & MPS.
3b. ABSOLUTE: where a contact's roster line carries DO_NOT_PROPOSE, those HP lines are forbidden for that contact. Do not name them in "hp_play_focus" and do not mention them anywhere in "how_to_open". If that leaves no product with an honest chain, use "Account engagement / discovery".
    GOOD (the chain is visible): a technology-development and business-intelligence remit + an analytics/AI account signal -> Z by HP Workstations.
    GOOD (the chain is visible): a data-governance remit + a security/tokenisation account signal -> HP Wolf Security.
4. "how_to_open" is written in the first person, as the seller. Go from a specific account trigger or the contact's own remit to a specific HP product line. 1-2 sentences.
4a. EVERY CONTACT GETS A DIFFERENT ANGLE. Before writing, count the distinct triggers and technology items in the ACCOUNT EVIDENCE and spread them across the roster. Do not use the same account trigger for more than two contacts, and never pair the same trigger with the same product twice across the roster. Where the evidence runs out, open on the contact's own remit rather than reusing a trigger a third time. Procurement, CIO office, technical evaluator, operations, data governance and engineering must read differently in SUBSTANCE - what the seller is there to do and learn - not merely in the closing clause. If you find yourself writing the same sentence with a different job title, stop and open on that role's own remit instead.
5. "hp_play_focus" is a short category label, e.g. "PC - fleet standardisation" or "Workstation / strategic sourcing", or "Account engagement / discovery" where no product chain holds. No sentence.
6. "decision_power" explains what this ROLE can do in a purchase. Base it on the remit the title implies, never on the individual, and NEVER claim more than this contact's supplied influence type allows:
      influence=Budget Holder      -> may discuss budget ownership and procurement authority.
      influence=Decision Maker     -> may say the role typically participates in or owns decisions of this kind. Do not overstate it as sole authority.
      influence=Technical Evaluator -> evaluation, standards and requirements influence ONLY. NEVER describe them as a decision owner, and never say they decide, approve or authorise a purchase.
      influence=Influencer         -> advisory input only. NEVER imply purchasing authority of any kind.
    WRITE IT SPECIFICALLY. Name the actual remit in the contact's own title - "As the head of IT project procurement, this role runs the sourcing route any hardware purchase has to pass through." Do NOT repeat the rule text above back to me: "This role typically participates in or owns decisions of this kind" and "Evaluation, standards and requirements influence only" are FAILED answers. Every contact's decision_power must be a different sentence.
    Include the field ONLY where the title names a remit that actually reaches IT hardware. For a product owner, a branch manager, an individual contributor, or any role whose remit does not reach hardware buying, OMIT THE KEY ENTIRELY. Expect to omit it for roughly half the roster.
7. "pain_points" are POTENTIAL pain points, INFERRED. The account evidence can establish that a signal exists at the account. It can NEVER establish that this person feels pressure from it, and you do not know their workload, priorities or concerns.
   Each entry must be a COMPLETE SENTENCE that does BOTH of these at once: (a) names a specific item from the ACCOUNT EVIDENCE above, and (b) states the pressure that item MAY create for THIS contact's FUNCTION. An intent research topic is a signal that the account is researching a subject - it is evidence, NOT a pain. You must translate it into a possible consequence for the role.
   HEDGE EVERY ENTRY. Use "may", "could", "likely", "suggests" or "points to". Write about the demand on the FUNCTION, never about the individual's experience.
   BAD (only a label pasted back, never do this): "product development & qa: research and development / test"
   BAD (only a headline pasted back): "ASII sets IDR 36 trillion capex for 2026, up 10% year on year"
   BAD (generic aspiration, no evidence): "Supporting product innovation"
   BAD (asserts a person's internal state as fact): "<signal> increases pressure on this contact to ensure secure and compliant data governance."
   GOOD (shape only - a named signal, hedged, aimed at the function): "<named signal> may increase demand for <specific capability> in workflows this role owns."
   GOOD (shape only): "<named event> could bring <specific consequence> into this <role's> remit within <timeframe>."
   VARY THE SENTENCE SHAPE. Do not end more than one entry across the whole roster with "which could impact this role's remit" or "which could impact this role's function", and do not open more than two with "The account's interest in". Repeating one template across the roster is a failed answer.
   These GOOD entries show the SHAPE only. Never reuse their wording. Write the sentence fresh from this contact's own role and the evidence above.
   If you cannot write such a sentence for this contact, OMIT THE KEY ENTIRELY. A finance, legal, HR, sales or product role will usually have none.
7a. Omission is the default for fields 6 and 7. Do not include the key with an empty string or empty array - leave the key out. Never state an individual's private concerns, motivations, opinions or budget.
8. NEVER state or imply who anyone reports to. No reporting lines, no org structure.
9. Do NOT output scores, rankings, priority, influence type, HP relevance, email, phone, LinkedIn or employment status. Those are computed elsewhere.
10. Output JSON with one entry per contact id supplied above:
{{
  "contacts": [
    {{
      "contact_id": "<the id exactly as supplied>",
      "how_to_open": "First-person opener tying a specific trigger or remit to an HP product line.",
      "hp_play_focus": "Short category label",
      "decision_power": "Role-based authority statement, or omit the field",
      "pain_points": ["Evidenced pressure", "..."]
    }}
  ]
}}
"""

    valid_ids = {c["contact_id"] for c in contacts}
    by_id = {c["contact_id"]: c for c in contacts}
    generated: dict = {}
    rejected: list[str] = []

    def _run(subset: list[dict]) -> None:
        """One model pass over `subset`, merging any usable entries into `generated`."""
        if not subset:
            return
        user_prompt = (
            f"Write the opening angle for every contact listed for {company_name}. "
            f"Return exactly one entry per contact id supplied - {len(subset)} entries - "
            f"in JSON matching the schema."
        )
        llm_res = generate_gpt4o_json_completion(_system_prompt(_roster_block(subset)), user_prompt)
        if not (llm_res and isinstance(llm_res, dict) and isinstance(llm_res.get("contacts"), list)):
            return
        for entry in llm_res["contacts"]:
                if not isinstance(entry, dict):
                    continue
                cid = str(entry.get("contact_id") or "").strip()
                if cid not in valid_ids:
                    continue
                opener = str(entry.get("how_to_open") or "").strip()
                if not opener:
                    continue
                play_focus = str(entry.get("hp_play_focus") or "").strip() or None
                dp_raw = str(entry.get("decision_power") or "").strip()
                pains_raw = [str(x).strip() for x in (entry.get("pain_points") or [])
                             if str(x).strip()]

                bad_nums, bad_urls = check_text(
                    ground, report, cid, opener, play_focus or "", dp_raw, *pains_raw)
                if bad_nums or bad_urls:
                    # Nothing about a person may carry a figure or link the
                    # account's own files never held.
                    rejected.append(f"{cid}: unsourced {bad_nums or ''}{bad_urls or ''}")
                    continue

                record = {
                    "contact_id": cid,
                    "how_to_open": opener,
                    "hp_play_focus": play_focus,
                }
                dp = str(entry.get("decision_power") or "").strip()
                if dp and not _is_rule_echo(dp):
                    record["decision_power"] = dp
                elif dp:
                    rejected.append(f"decision_power echo: {dp}")

                # Enforce the per-contact block list rather than trusting the
                # prompt: v6 still opened a Cloud Operations lead on Print/MPS.
                contact = by_id.get(cid)
                for play in blocked_plays_for(contact.get("title") if contact else None):
                    needle = play.lower()
                    if (needle in record["how_to_open"].lower()
                            or needle in (record["hp_play_focus"] or "").lower()):
                        rejected.append(f"blocked play {play} proposed for {cid}")
                        record["hp_play_focus"] = "Account engagement / discovery"
                        record["play_blocked"] = play
                        break
                pains = entry.get("pain_points")
                if isinstance(pains, list):
                    cleaned = []
                    for raw_p in pains:
                        p = str(raw_p).strip()
                        if not p:
                            continue
                        if _is_evidence_label(p, evidence_labels):
                            rejected.append(p)
                            continue
                        cleaned.append(p)
                    if cleaned:
                        record["pain_points"] = cleaned
                generated[cid] = record

    _run(contacts)
    # One bounded retry for any contact the model skipped, so coverage is complete.
    missing = [c for c in contacts if c["contact_id"] not in generated]
    if missing:
        _run(missing)

    if rejected:
        logger.info(
            "stakeholder talking points: dropped %d pain point(s) that only echoed "
            "an evidence label: %s", len(rejected), rejected
        )

    if generated:
        payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_talking_points",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "contacts_fingerprint": fingerprint,
                "generated_count": len(generated),
                "talking_points": generated,
                "grounding_report": report.as_dict(),
            },
            "source_datasets": ["prospect_contacts", "firmographics", "technographics",
                                "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        # Generation failed. Preserve the last valid result if one exists.
        if existing and existing.get("status") == "available":
            return existing
        payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_talking_points",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "contacts_fingerprint": None,
                "generated_count": 0,
                "talking_points": {},
                "notice": "Stakeholder talking points require OPENAI_API_KEY. No content is generated without it.",
            },
            "source_datasets": ["prospect_contacts", "firmographics", "technographics",
                                "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "stakeholder_talking_points"},
        {"$set": payload},
        upsert=True
    )
    return payload


@requires_local_datasets(
    "firmographics", "google_news", "intent_score", "news_events", "prospect_contacts", "technographics",
)
def extract_stakeholder_map(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)

    contact_records = _read_dataset_records(account_id, "prospect_contacts")

    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    results = []

    # 1. Widget: stakeholder_contacts_grid (deterministic)
    extracted_contacts = []
    dept_counter = Counter()
    source_counter = Counter({"Source A": 0, "Apollo": 0})

    for idx, row in enumerate(contact_records):
        # --- existing deterministic fields, unchanged ---------------------------
        is_apollo = bool(resolve_field(row, ["apollo_requested_contact", "apollo_matched_contact"]))
        source = "Apollo" if is_apollo else "Source A"
        source_counter[source] += 1

        full_name = resolve_field(row, ["Prospect full_name"])
        if not full_name:
            fname = resolve_field(row, ["Prospect first_name"]) or ""
            lname = resolve_field(row, ["Prospect last_name"]) or ""
            combined = f"{fname} {lname}".strip()
            full_name = combined if combined else (resolve_field(row, ["apollo_title"]) or "Unknown Contact")

        title = resolve_field(row, ["Prospect job_title", "apollo_title"])
        department = resolve_field(row, ["Prospect job_department_main", "apollo_department"])
        dept_key = department if department else "Unassigned"
        dept_counter[dept_key] += 1

        seniority = resolve_field(row, ["Prospect job_level_main", "apollo_seniority"])
        email = resolve_field(row, ["Contact professions_email", "Email", "apollo_verified_work_email"])
        email_status = resolve_field(row, ["Contact professional_email_status", "Email Status", "apollo_zerobounce_email_status"])
        phone = normalize_phone(resolve_field(row, ["Contact mobile_phone", "Mobile Phone", "apollo_direct_mobile_phone"]))
        linkedin_url = resolve_field(row, ["Prospect linkedin", "Prospect linkedin_url_array", "apollo_linkedin_url"])
        buying_persona = resolve_field(row, ["Prospect buying_committee_personas"]) if source == "Source A" else None

        # --- new derived keys (additive only) -----------------------------------
        contact_id = resolve_field(row, ["Prospect prospect_id"]) or f"contact_{idx + 1}"
        persona_raw = resolve_field(row, ["Prospect buying_committee_personas"])
        skills = resolve_field(row, ["Prospect skills"])
        career_history = resolve_field(row, ["Prospect experience"])
        city = resolve_field(row, ["Prospect city"])
        country = resolve_field(row, ["Prospect country_name"])

        norm_dept = normalize_department(department)
        band, seniority_conflict = seniority_band(seniority, title)
        influence_type, influence_source = assign_influence(persona_raw, title, band, norm_dept)
        priority = assign_priority(norm_dept, band)

        components = {
            "seniority": score_seniority(band),
            "hp_relevance": score_hp_relevance(title, norm_dept, skills),
            "influence": score_influence(influence_type),
            "data_completeness": score_data_completeness(email, email_status, phone,
                                                         linkedin_url, skills or career_history),
            "priority": score_priority(priority),
        }
        composite = composite_score(components)

        location_parts = [p for p in [city, country] if p]
        contact_location = ", ".join(location_parts) if location_parts else None

        extracted_contacts.append({
            # existing fields - names and values unchanged
            "full_name": full_name,
            "title": title,
            "department": department,
            "seniority": seniority,
            "email": email,
            "email_status": email_status,
            "phone": phone,
            "linkedin_url": linkedin_url,
            "buying_committee_persona": buying_persona,
            "source": source,
            # new derived keys
            "contact_id": contact_id,
            "normalized_department": norm_dept,
            "seniority_band": band,
            "seniority_source_conflict": seniority_conflict,
            "influence_type": influence_type,
            "influence_source": influence_source,
            "priority": priority,
            "hp_relevance_score": components["hp_relevance"],
            "hp_relevance_band": hp_relevance_band(components["hp_relevance"]),
            "score_components": components,
            "score_weights": COMPOSITE_WEIGHTS,
            "stakeholder_score": composite,
            "contact_location": contact_location,
            "skills": skills,
            "career_history": career_history,
            "is_priority_contact": False,
        })

    # --- Priority Contacts: pure threshold, no hardcoded count -----------------
    for c in extracted_contacts:
        c["is_priority_contact"] = (
            c["stakeholder_score"] >= PRIORITY_CONTACT_MIN_COMPOSITE
            and c["hp_relevance_band"] != "low"
        )

    # Coverage pass (ABX Step 6): if no Budget Holder made the cut but one exists
    # in the roster, promote the highest-scoring one.
    if extracted_contacts and not any(
        c["is_priority_contact"] and c["influence_type"] == "Budget Holder"
        for c in extracted_contacts
    ):
        budget_holders = [c for c in extracted_contacts if c["influence_type"] == "Budget Holder"]
        if budget_holders:
            best = max(budget_holders, key=lambda c: c["stakeholder_score"])
            best["is_priority_contact"] = True

    extracted_contacts.sort(
        key=lambda c: (not c["is_priority_contact"], -c["stakeholder_score"], c["full_name"])
    )

    relevance_counter = Counter(c["hp_relevance_band"] for c in extracted_contacts)
    priority_count = sum(1 for c in extracted_contacts if c["is_priority_contact"])

    if extracted_contacts:
        contacts_payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_contacts_grid",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_contacts_count": len(extracted_contacts),
                "source_breakdown": dict(source_counter),
                "department_distribution": dict(dept_counter.most_common()),
                "contacts": extracted_contacts,
                "priority_contacts_count": priority_count,
                "relevance_breakdown": {
                    "high": relevance_counter.get("high", 0),
                    "medium": relevance_counter.get("medium", 0),
                    "low": relevance_counter.get("low", 0),
                },
                "score_weights": COMPOSITE_WEIGHTS,
                "priority_threshold": PRIORITY_CONTACT_MIN_COMPOSITE,
            },
            "source_datasets": ["prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        contacts_payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_contacts_grid",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "stakeholder_contacts_grid"},
        {"$set": contacts_payload},
        upsert=True
    )
    results.append(contacts_payload)

    # 2. Widget: stakeholder_influence_map (derived) - grouping, coverage, ranking
    if extracted_contacts:
        groups = {}
        for c in extracted_contacts:
            groups.setdefault(c["normalized_department"], []).append(c)

        department_groups = []
        for dept, members in groups.items():
            surfaced = [m for m in members if m["is_priority_contact"] or m["hp_relevance_band"] in ("high", "medium")]
            lower = [m for m in members if m not in surfaced]
            department_groups.append({
                "department": dept,
                "total_count": len(members),
                "hp_relevant_count": len(surfaced),
                "lower_relevance_count": len(lower),
                "surfaced_contact_ids": [m["contact_id"] for m in surfaced],
                "lower_relevance_contact_ids": [m["contact_id"] for m in lower],
            })
        # Order departments by HP-relevance weight, not headcount.
        department_groups.sort(key=lambda g: (-g["hp_relevant_count"], -g["total_count"], g["department"]))

        influence_breakdown = Counter(c["influence_type"] for c in extracted_contacts)
        seniority_breakdown = Counter(c["seniority_band"] for c in extracted_contacts)

        entry_path = [
            {
                "order": i + 1,
                "contact_id": c["contact_id"],
                "full_name": c["full_name"],
                "title": c["title"],
                "department": c["normalized_department"],
                "stakeholder_score": c["stakeholder_score"],
                "score_components": c["score_components"],
                "reason": ", ".join(
                    f"{k.replace('_', ' ')} {v}"
                    for k, v in sorted(c["score_components"].items(), key=lambda kv: -kv[1])[:2]
                ),
            }
            for i, c in enumerate(
                sorted(extracted_contacts, key=lambda c: -c["stakeholder_score"])[:10]
            )
        ]

        influence_payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_influence_map",
            "data_classification": "derived",
            "status": "available",
            "data": {
                "department_groups": department_groups,
                "influence_breakdown": dict(influence_breakdown),
                "seniority_breakdown": dict(seniority_breakdown),
                "buying_group_coverage": {
                    role: influence_breakdown.get(role, 0)
                    for role in ["Decision Maker", "Budget Holder", "Technical Evaluator", "Influencer"]
                },
                "ranked_entry_path": entry_path,
                "score_weights": COMPOSITE_WEIGHTS,
            },
            "source_datasets": ["prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }
    else:
        influence_payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_influence_map",
            "data_classification": "derived",
            "status": "empty",
            "data": {},
            "source_datasets": ["prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "stakeholder_influence_map"},
        {"$set": influence_payload},
        upsert=True
    )
    results.append(influence_payload)

    # 3. Widget: stakeholder_talking_points (inferred) - cached GPT-4o output
    if extracted_contacts:
        talking_points_payload = generate_stakeholder_talking_points(
            account_id, extracted_contacts, company_name
        )
    else:
        talking_points_payload = {
            "account_id": account_id,
            "feature_key": "stakeholder_map",
            "widget_key": "stakeholder_talking_points",
            "data_classification": "inferred",
            "status": "empty",
            "data": {},
            "source_datasets": ["prospect_contacts", "firmographics", "technographics",
                                "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now,
        }
        db["account_widgets"].update_one(
            {"account_id": account_id, "widget_key": "stakeholder_talking_points"},
            {"$set": talking_points_payload},
            upsert=True
        )
    results.append(talking_points_payload)

    return results
