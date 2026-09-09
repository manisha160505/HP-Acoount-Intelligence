import os
import io
import csv
import json
import hashlib
import pandas as pd
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion

import logging

logger = logging.getLogger(__name__)

def _find_file_path(rel_path: str) -> str | None:
    if not rel_path:
        return None
    candidate_paths = [
        os.path.join(os.getcwd(), rel_path),
        os.path.join("/app", rel_path),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path)),
    ]
    for cp in candidate_paths:
        if os.path.exists(cp):
            return cp
    return None

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
    full_path = _find_file_path(rel_path)

    if not full_path or not os.path.exists(full_path):
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
HP_RELEVANCE_DEPT_TIERS = {
    "Information Technology": 100,
    "Engineering & Technical": 70,
    "Operations": 40,
    "Product Management": 40,
    "Executive": 40,
}
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
TALKING_POINTS_PROMPT_VERSION = 5


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


def seniority_band(raw: str | None) -> str:
    if not raw:
        return "Individual Contributor"
    key = str(raw).strip().strip('[]"\' ').lower()
    return SENIORITY_BAND_MAP.get(key, "Individual Contributor")


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


def assign_influence(persona: str | None, title: str | None,
                     band: str = "Individual Contributor",
                     department: str = UNASSIGNED_DEPT) -> str:
    """ABX Step 4 cascade: procurement -> Budget Holder; C-suite and senior
    IT/Engineering leaders -> Decision Maker; technical roles -> Technical
    Evaluator; otherwise Influencer.

    The uploaded buying-committee persona is real evidence but a coarse segment
    label - in practice it marks most of an IT roster "IT Decision Maker", which
    collapses the whole buying group into one bucket. It is therefore used as a
    fallback where the title is uninformative, not as the primary signal.

    Champion and Blocker are never assigned: the spec allows Blocker only with
    evidence that someone can stop a purchase, and we hold none.
    """
    t = (title or "").lower()
    if any(term in t for term in BUDGET_HOLDER_TITLE_TERMS):
        return "Budget Holder"

    if band == "C-Suite":
        return "Decision Maker"

    # Hands-on technical remit is checked before the seniority rule below.
    # Our seniority column bands every "Head of ..." title as Director, so
    # testing seniority first would classify the entire engineering bench as
    # Decision Makers and leave the buying group with no evaluators.
    if any(term in t for term in TECHNICAL_TITLE_TERMS):
        return "Technical Evaluator"

    if band in ("VP", "Director") and department in ("Information Technology",
                                                     "Engineering & Technical"):
        return "Decision Maker"

    if "decision maker" in (persona or "").lower():
        return "Decision Maker"

    return "Influencer"


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


def _contacts_fingerprint(contacts: list[dict]) -> str:
    """Stable hash of the contact facts the talking points are generated from.
    Regeneration is triggered by a change here, not by every page load."""
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
    payload = {"prompt_version": TALKING_POINTS_PROMPT_VERSION, "contacts": basis}
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

    triggers = []
    seen = set()
    for r in gnews + events:
        h = str(r.get("event_headline") or r.get("news_announcements")
                or r.get("summary") or r.get("title") or "").strip()
        d = str(r.get("event_date") or r.get("effective_date") or "").strip()
        if h and h.lower() not in seen:
            seen.add(h.lower())
            triggers.append(f"- {h} ({d})" if d else f"- {h}")
            labels.add(h.lower())
    if triggers:
        lines.append("Recent news and trigger events:\n" + "\n".join(triggers[:10]))

    context = "\n".join(lines) if lines else "No account-level context available."
    return context, labels


def generate_stakeholder_talking_points(account_id: str, contacts: list[dict],
                                        company_name: str) -> dict:
    """One GPT-4o call covering every contact. Returns the four inferred fields
    keyed by contact id. Never asked for scores, bands, or contact facts."""
    db = get_db()
    now = datetime.now(timezone.utc)
    fingerprint = _contacts_fingerprint(contacts)

    existing = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "stakeholder_talking_points",
    })

    # Cached: reuse while the contact facts are unchanged.
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("contacts_fingerprint") == fingerprint):
        return existing

    account_context, evidence_labels = _build_account_context(account_id)

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
4. "how_to_open" is written in the first person, as the seller. Go from a specific account trigger or the contact's own remit to a specific HP product line. 1-2 sentences.
5. "hp_play_focus" is a short category label, e.g. "PC - fleet standardisation" or "Workstation / strategic sourcing". No sentence.
6. "decision_power" explains why this ROLE can move a purchase. Base it on the remit the title implies, never on the individual. Include it ONLY where the title names a remit that actually carries purchasing or standard-setting authority over IT hardware - a chief officer, a head of procurement, or the head of a technology function. For a product owner, a branch manager, an individual contributor, or any role whose remit does not reach hardware buying, OMIT THE KEY ENTIRELY. Expect to omit it for roughly half the roster.
7. "pain_points" must be a COMPLETE SENTENCE that does BOTH of these at once: (a) names a specific item from the ACCOUNT EVIDENCE above, and (b) states the operational pressure that item creates for THIS contact's function. Note that an intent research topic is a signal that the account is researching a subject - it is evidence, NOT a pain. You must translate it into a consequence for the role.
   BAD (this is only a label pasted back, never do this): "product development & qa: research and development / test"
   BAD (this is only a headline pasted back): "ASII sets IDR 36 trillion capex for 2026, up 10% year on year"
   BAD (generic aspiration, no evidence): "Supporting product innovation"
   GOOD (shape only - a named signal, then the consequence for the role): "<named intent surge> points to <specific workload> outgrowing <specific part of the estate>, which lands on this <role's> remit first."
   GOOD (shape only): "<named event> puts <specific consequence> in front of this <role's> remit within <timeframe>."
   These two GOOD entries show the SHAPE only. Never reuse their wording. Write the sentence fresh from this contact's own role and the evidence above.
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
                record = {
                    "contact_id": cid,
                    "how_to_open": opener,
                    "hp_play_focus": str(entry.get("hp_play_focus") or "").strip() or None,
                }
                dp = str(entry.get("decision_power") or "").strip()
                if dp:
                    record["decision_power"] = dp
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
        phone = resolve_field(row, ["Contact mobile_phone", "Mobile Phone", "apollo_direct_mobile_phone"])
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
        band = seniority_band(seniority)
        influence_type = assign_influence(persona_raw, title, band, norm_dept)
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
            "influence_type": influence_type,
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
