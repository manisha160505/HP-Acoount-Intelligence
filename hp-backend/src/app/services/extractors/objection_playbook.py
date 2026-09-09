import os
import io
import csv
import re
import json
import difflib
import hashlib
import logging
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.grounding import (
    build_corpus, check_text, GroundingReport,
)

logger = logging.getLogger(__name__)
from app.services.extractors.stakeholder_map import (
    normalize_department,
    resolve_field,
)

TECHNOGRAPHICS_CATEGORY_COLUMNS = [
    "Testing And Qa",
    "Sales",
    "Prog Langs And Frameworks",
    "Productivity And Operations",
    "Product And Design",
    "Platform And Storage",
    "Operations Software",
    "Operations Management",
    "Marketing",
    "It Security",
    "It Management",
    "Hr",
    "Finance And Accounting",
    "Ecommerce",
    "Devops And Development",
    "Customer Management",
    "Computer Networks",
    "Communications",
    "Collaboration",
    "Bi And Analytics"
]

# ==============================================================================
# HP CONTEST AREAS
#
# These tables describe HP's product lines and the fixed Explorium category
# schema. Nothing here is specific to any account - vendors, categories and
# contacts are all read from the uploaded files at runtime.
# ==============================================================================

# Which technographics category columns speak to each area HP competes in.
AREA_CATEGORY_COLUMNS = {
    "Client Devices": ["Platform And Storage", "It Management"],
    "Collaboration": ["Collaboration", "Communications"],
    "Print / MPS": ["Productivity And Operations", "Operations Management"],
    "Endpoint Security": ["It Security", "Computer Networks"],
    "Device Management": ["It Management", "Computer Networks"],
}

# Vendor tokens that indicate a competing product is present in an area. Matched
# case-insensitively on word boundaries against the stack entries.
# Technologies that ARE the area. These carry the objection and the reframe.
AREA_PRIMARY_TOKENS = {
    "Client Devices": ["dell", "lenovo", "asus", "acer", "msi", "apple ios", "macos",
                       "chromeos", "microsoft windows", "thinkpad", "latitude",
                       "macbook", "matebook", "surface laptop"],
    "Collaboration": ["zoom", "microsoft teams", "webex", "poly", "logitech",
                      "g suite", "google workspace", "slack", "ringcentral",
                      "microsoft office 365", "google meet"],
    "Print / MPS": ["canon", "epson", "xerox", "ricoh", "brother", "kyocera",
                    "lexmark", "sharp", "konica", "papercut", "printer"],
    # Endpoint protection only. Network security and identity are adjacent, not
    # endpoint security, and are listed as context below.
    "Endpoint Security": ["symantec", "kaspersky", "defender", "crowdstrike",
                          "sentinelone", "mcafee", "sophos", "trend micro",
                          "bitdefender", "eset", "carbon black", "cylance"],
    # Device management only. MFA and identity providers authenticate people;
    # they do not manage a device estate, so they are not primary here.
    "Device Management": ["intune", "workspace one", "airwatch", "jamf", "manageengine",
                          "sccm", "ivanti", "tanium", "ninjaone"],
}

# Adjacent technologies worth showing, but never the basis of the argument.
AREA_CONTEXT_TOKENS = {
    "Endpoint Security": ["cisco asa", "cisco ironport", "fortinet", "fortigate",
                          "fortimanager", "aruba clearpass", "palo alto",
                          "check point", "azure ad", "okta"],
}



# Which contact functions plausibly own each area. Matched against the
# normalised department and, word-boundary-wise, against the job title.
AREA_OWNER_DEPARTMENTS = {
    "Client Devices": ["Information Technology", "Operations"],
    "Collaboration": ["Information Technology", "Operations"],
    "Print / MPS": ["Operations", "Information Technology", "Finance"],
    "Endpoint Security": ["Information Technology", "Engineering & Technical"],
    "Device Management": ["Information Technology", "Engineering & Technical"],
}
# Only a STRONG title match resolves to a named contact. A weak match means the
# nearest technically-adjacent person, which is not the same as the owner, so the
# card names the owning function instead.
AREA_OWNER_STRONG_TOKENS = {
    "Client Devices": ["procurement", "end user", "information technology",
                       "it operations", "infrastructure"],
    "Collaboration": ["collaboration", "communications", "end user", "workplace"],
    "Print / MPS": ["procurement", "facilities", "general affairs", "administration"],
    "Endpoint Security": ["security", "ciso", "infosec", "cyber",
                          "information security"],
    "Device Management": ["information technology", "it operations", "infrastructure",
                          "procurement", "end user"],
}
AREA_OWNER_WEAK_TOKENS = {
    "Client Devices": ["operations", "technology"],
    "Collaboration": ["applications", "operations", "technology"],
    "Print / MPS": ["operations", "finance"],
    "Endpoint Security": ["risk", "governance", "compliance", "infrastructure"],
    "Device Management": ["operations", "technology"],
}


# HP_ABX_v3_final: "typically 5-10 when evidence supports that many".
# The count stays evidence-led, so fewer than five is still valid.
MAX_OBJECTIONS = 10

# The spec's exact wording when no official HP proof point can be sourced.
# No HP proof-point corpus is supplied to this system, so this is what shows.
NO_PROOF_POINT = "No supporting HP proof point available"

# Bump when the objection prompt changes so cached output is regenerated.
OBJECTION_PROMPT_VERSION = 5

# The dataset key used everywhere in evidence, prompts and UI. Never the Source A
# sheet name - the application speaks in dataset keys.
TECHNOGRAPHICS_DATASET_KEY = "technographics"

# The catch-all column. Category columns are a subset of it, so both are read.
FULL_STACK_COLUMN = "Full Tech Stack"

NL = chr(10)


# Sector words drawn from an account's own Business Description. They pass the
# grounding check - they really are in the data - but nothing in the evidence
# links a sector to a device, security or print need, so using one as
# justification is an unsupported inference rather than a sourced fact.
SECTOR_WORDS = [
    "automotive", "financial services", "heavy equipment", "mining", "construction",
    "energy", "agriculture", "agribusiness", "infrastructure", "logistics",
    "property development", "plantations", "forestry", "banking", "insurance",
    "toll road", "palm oil", "coal",
]


def _sector_terms_used(text: str, business_description: str) -> list[str]:
    """Sector words present in BOTH the generated prose and this account's own
    description - i.e. a sector being leaned on as justification."""
    t = " ".join(str(text or "").split()).lower()
    bd = " ".join(str(business_description or "").split()).lower()
    return sorted({w for w in SECTOR_WORDS if w in t and w in bd})


def _norm_objection(text: str) -> str:
    """Case- and whitespace-insensitive form, for spotting two objections that
    differ only in wording."""
    return " ".join(str(text or "").split()).lower().strip('"“”')


def _token_present(token: str, text: str) -> bool:
    """Word-boundary containment. A plain substring test matches 'it' inside
    'quality' and 'digital', which produces nonsense owners and vendors."""
    if not token or not text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(token.lower()) + r"(?![a-z0-9])",
                     text.lower()) is not None

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

def _build_area_evidence(techno_row: dict) -> list[dict]:
    """One entry per HP contest area, carrying the verbatim technographics cells
    that speak to it and the vendors detected in them.

    An area with no detected vendor is kept, flagged `not_in_technographics`.
    That flag means only that this export does not name one - never that the
    account has no such vendor, capability or process."""
    full_stack = [v.strip() for v in
                  str(techno_row.get(FULL_STACK_COLUMN) or "").split(",") if v.strip()]

    areas = []
    for area, columns in AREA_CATEGORY_COLUMNS.items():
        tokens = AREA_PRIMARY_TOKENS.get(area, [])
        context_tokens = AREA_CONTEXT_TOKENS.get(area, [])
        cells, detected, seen = [], [], set()

        # The category columns say WHERE a vendor was detected.
        for col in columns:
            raw = str(techno_row.get(col) or "").strip()
            if not raw:
                continue
            values = [v.strip() for v in raw.split(",") if v.strip()]
            hits = [v for v in values
                    if any(_token_present(t, v) for t in tokens) and v not in seen]
            if hits:
                cells.append({"column": col, "values": hits})
            for v in hits:
                seen.add(v)
                detected.append(v)

        # Full Tech Stack is a superset of the category columns - several vendors
        # appear only there, so it is scanned too rather than silently missed.
        stack_only = [v for v in full_stack
                      if any(_token_present(t, v) for t in tokens) and v not in seen]
        if stack_only:
            cells.append({"column": FULL_STACK_COLUMN, "values": stack_only})
            for v in stack_only:
                seen.add(v)
                detected.append(v)

        # Adjacent technologies: shown, but they cannot carry the objection.
        context_detected = []
        if context_tokens:
            pool = list(full_stack)
            for col in columns:
                raw = str(techno_row.get(col) or "").strip()
                pool.extend(v.strip() for v in raw.split(",") if v.strip())
            for v in pool:
                if v in seen or v in context_detected:
                    continue
                if any(_token_present(t, v) for t in context_tokens):
                    context_detected.append(v)

        if detected:
            parts = [c["column"] + ": " + ", ".join(c["values"]) for c in cells]
            evidence = TECHNOGRAPHICS_DATASET_KEY + " -> " + area + " | " + " | ".join(parts)
            if context_detected:
                evidence += " | supporting context: " + ", ".join(context_detected)
        else:
            evidence = (TECHNOGRAPHICS_DATASET_KEY + " -> " + area
                        + ": no vendor for this area appears in this account's"
                        + " technographics evidence")

        areas.append({
            "area": area,
            "columns": [c["column"] for c in cells],
            "cells": cells,
            "detected_vendors": detected,
            "context_vendors": context_detected,
            "not_in_technographics": not detected,
            "evidence": evidence,
        })
    return areas


def _resolve_likely_raiser(area: str, contacts: list[dict]) -> tuple[str, str]:
    """A real title from the account's own contacts where one plausibly owns the
    area, else the area name itself. Returns (raiser, source)."""
    dept_targets = AREA_OWNER_DEPARTMENTS.get(area, [])
    strong_tokens = AREA_OWNER_STRONG_TOKENS.get(area, [])

    best = None
    for row in contacts:
        title = resolve_field(row, ["Prospect job_title", "apollo_title"]) or ""
        dept_raw = resolve_field(row, ["Prospect job_department_main", "apollo_department"])
        dept = normalize_department(dept_raw)

        matched = [t for t in strong_tokens if _token_present(t, title)]
        if not matched:
            # A weak or department-only match is the nearest technically adjacent
            # person, not the owner of this subject. Naming them would overstate.
            continue
        rank = len(matched) + (1 if dept in dept_targets else 0)
        if best is None or rank > best[0]:
            best = (rank, title.strip(), matched[0])

    if best and best[1]:
        return best[1], "prospect_contacts"
    return area, "hp_contest_area"


def _evidence_fingerprint(areas: list[dict], business_description: str) -> str:
    basis = sorted(
        [{"a": a["area"], "e": a["evidence"], "r": a.get("likely_raiser", "")} for a in areas],
        key=lambda x: x["a"],
    )
    payload = {
        "prompt_version": OBJECTION_PROMPT_VERSION,
        "areas": basis,
        "business_description": business_description,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def generate_objection_cards(account_id: str, areas: list[dict],
                             company_name: str, business_description: str) -> dict | None:
    """One cached GPT-4o call. The model writes only the objection, the reframe
    and the counter question. The evidence, the vendor list, the area and the
    likely raiser are owned by Python and are never sent back for rewriting."""
    db = get_db()
    now = datetime.now(timezone.utc)
    fingerprint = _evidence_fingerprint(areas, business_description)

    existing = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "objection_reframe_cards",
    })
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("evidence_fingerprint") == fingerprint):
        return existing

    # Grounding corpus: the datasets this feature reasons over.
    ground = build_corpus({
        k: _read_dataset_records(account_id, k) for k in
        ("technographics", "firmographics", "prospect_contacts")
    })
    report = GroundingReport(ground, ["objection", "reframe", "counter_question"])

    roster = []
    for a in areas:
        state = ("NO VENDOR DETECTED IN THE TECHNOGRAPHICS EVIDENCE"
                 if a["not_in_technographics"]
                 else "vendors detected: " + ", ".join(a["detected_vendors"]))
        roster.append(
            "- area=" + a["area"] + " | " + state + NL
            + "    evidence (verbatim, do not rewrite): " + a["evidence"] + NL
            + "    topic owner at this account: " + a["likely_raiser"]
        )

    system_prompt = (
"You are an HP enterprise sales strategist preparing a seller to meet " + company_name + "." + NL + NL
+ "ABOUT THE ACCOUNT (from its firmographics record):" + NL
+ (business_description or "No business description supplied.") + NL + NL
+ "HP competes in these areas: client devices (HP Elite/Pro PCs, Z by HP Workstations), "
  "collaboration hardware (Poly), print and managed print services, endpoint security "
  "(HP Wolf Security), and device management (HP Anyware / DaaS)." + NL + NL
+ "EVIDENCE - one block per area, drawn from this account's technographics dataset:" + NL
+ NL.join(roster) + NL + NL
+ "WRITE, FOR EACH AREA, one objection card." + NL + NL
+ "WHAT AN OBJECTION IS HERE:" + NL
+ "An objection is a HYPOTHETICAL. It is push-back a buyer working in that area MIGHT raise, "
  "that the seller should be ready for. It is NOT something anyone at " + company_name + " has said. "
  "Never write it as reported speech. Never attribute it to the topic owner or any person. "
  "Never imply it has been raised. The topic owner is given only so the seller knows who tends "
  "to own that subject - treat them as the audience, not the speaker." + NL + NL
+ "PRIMARY vs SUPPORTING CONTEXT: each area's evidence line lists the technologies that ARE that area, and may then list 'supporting context' - adjacent products that sit beside it without performing its function. Build the objection and the reframe on the PRIMARY technologies only. You may acknowledge context, but never write as though a context product performs the area's job: multi-factor authentication is not device management, and a network firewall is not endpoint protection." + NL + NL+ "RULES ON EVIDENCE:" + NL
+ "1. Never introduce a vendor, product, number, customer or event that is not in that area's own "
  "evidence block above. If a vendor is not listed there, it does not exist for the purposes of this card." + NL
+ "2. An objection must be answerable from that area's own evidence. If no PC vendor is listed, do NOT "
  "write a 'we already standardised on Dell/Lenovo' objection - there is nothing to support it." + NL
+ "3. WHERE NO VENDOR WAS DETECTED: this means only that the technographics evidence does not name one. "
  "It does NOT mean the account has no such vendor, no such process, or an open field. You MUST NOT write "
  "'they have no incumbent', 'there is no standard', 'the field is open', 'greenfield', or any equivalent "
  "claim about the account. Frame it as a visibility gap - the evidence does not show one, and a vendor may "
  "well exist undetected - and make the counter question one that FINDS OUT who owns that decision today." + NL
+ "4. Never rewrite, paraphrase or tidy the evidence string. You are reading it, not editing it." + NL
+ "5. The account description above lists the sectors this business operates in. Do NOT use a sector name as justification for a device, security, collaboration or print need - nothing in the evidence links a sector to a technology requirement. Write \"across the account's diverse business units\" instead of naming mining, financial services, heavy equipment or any other sector as a reason." + NL + NL
+ "FIELDS:" + NL
+ '- "objection": the anticipated push-back, in a buyer\'s own words, in quotes. One sentence. '
  "It must be something a busy buyer would actually say to get rid of a seller - a brush-off, a "
  "budget line, a we-already-have-this. NEVER write the buyer confessing ignorance or a lack of "
  "visibility about their own estate; that is our evidence gap, not theirs, and putting it in "
  "their mouth is wrong. For an area with no vendor detected, the realistic objection is the "
  "buyer DEPRIORITISING the topic - 'there is no RFP open for that', 'that is handled', 'why "
  "are we even discussing this' - not the buyer admitting they do not know." + NL
+ '- "reframe": the seller\'s answer. Two sentences at most, and it must do BOTH of these: '
  "name the specific HP line that applies (HP Elite/Pro PCs, Z by HP Workstations, Poly, HP "
  "Enterprise Print/MPS, HP Wolf Security, HP Anyware/DaaS) AND give the concrete angle for "
  "this account, tied to a vendor or fact in that area's evidence. A reframe that names no HP "
  "line is a FAILED answer." + NL
+ '- "counter_question": one question the seller can ask next that advances the conversation.' + NL
+ '- "why_expected": one sentence on why THIS account would raise this, tied to its own evidence above. Not a general statement about buyers.' + NL
+ '- "recommended_next_step": the concrete next action for the seller after the counter question - a meeting, a discovery item, a thing to confirm. One short sentence.' + NL + NL
+ "STYLE - these are hard bans, and a card that breaks them is a failed answer:" + NL
+ "- Do NOT open the reframe by complimenting or validating the buyer. No 'It is great that you', "
  "'It is excellent that you', 'It is clear that you have invested', 'It is understandable that'. "
  "Start with the substance." + NL
+ "- Do NOT use the concessive template '<praise> ... However, <vague upside>'. Every one of your "
  "reframes must have a different shape from the others." + NL
+ "- Do NOT write filler abstractions: 'as threats evolve', 'optimise performance', 'uncover "
  "opportunities', 'drive efficiencies', 'streamline', 'best possible experience'. Say the "
  "specific thing about THIS account instead." + NL
+ "- Write as one seasoned seller briefing another, not as marketing copy." + NL + NL
+ "Return one entry per supplied area, using the area name exactly as given." + NL + NL
+ "Output JSON:" + NL
+ '{ "cards": [ { "area": "<area name exactly as supplied>", "objection": "...", '
  '"reframe": "...", "counter_question": "...", "why_expected": "...", '
  '"recommended_next_step": "..." } ] }' + NL
    )

    user_prompt = (
        "Write one objection card for each of the " + str(len(areas)) + " areas supplied, for "
        + company_name + ". Return JSON matching the schema."
    )

    rejected_sectors: list[str] = []

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)

    by_area = {a["area"]: a for a in areas}
    cards = []
    if llm_res and isinstance(llm_res, dict) and isinstance(llm_res.get("cards"), list):
        for entry in llm_res["cards"]:
            if not isinstance(entry, dict):
                continue
            area = str(entry.get("area") or "").strip()
            src_area = by_area.get(area)
            if not src_area:
                continue
            objection = str(entry.get("objection") or "").strip()
            reframe = str(entry.get("reframe") or "").strip()
            counter = str(entry.get("counter_question") or "").strip()
            if not (objection and reframe and counter):
                continue

            sectors = _sector_terms_used(reframe + " " + counter, business_description)
            if sectors:
                # Grounded but unsupported: the sector is real, the link from
                # sector to technology need is not.
                rejected_sectors.append(f"{area}: {', '.join(sectors)}")
                continue

            bad_nums, bad_urls = check_text(ground, report, area,
                                            objection, reframe, counter)
            if bad_nums or bad_urls:
                # A figure or link the technographics never carried has no place
                # in a card that is meant to be evidence-led.
                continue
            cards.append({
                "card_id": hashlib.sha1(area.encode("utf-8")).hexdigest()[:12],
                "area": area,
                "objection": objection,
                "reframe": reframe,
                "counter_question": counter,
                "why_expected": str(entry.get("why_expected") or "").strip() or None,
                "recommended_next_step": str(entry.get("recommended_next_step") or "").strip() or None,
                # No HP proof-point corpus is supplied to this system, so the
                # spec's empty state is shown rather than an unrelated case study.
                "hp_proof_point": None,
                "hp_proof_point_note": NO_PROOF_POINT,
                # technographics carries no link, date or confidence column, so
                # these are recorded as absent rather than invented.
                "evidence_source_link": None,
                "evidence_date": None,
                "evidence_confidence": None,
                # Python-owned, never model-supplied.
                "evidence": src_area["evidence"],
                "evidence_columns": src_area["columns"],
                "detected_vendors": src_area["detected_vendors"],
                "context_vendors": src_area.get("context_vendors", []),
                "not_in_technographics": src_area["not_in_technographics"],
                "likely_raiser": src_area["likely_raiser"],
                "likely_raiser_source": src_area["likely_raiser_source"],
            })

    if rejected_sectors:
        logger.warning("objection playbook: %d card(s) leaned on a sector as "
                       "justification, retrying: %s", len(rejected_sectors), rejected_sectors)
        retry_system = system_prompt + (
            NL + NL + "RETRY - REJECTED." + NL
            + "These cards used a business sector as justification for a technology "
              "need: " + "; ".join(rejected_sectors) + "." + NL
            + "A sector is not evidence of a technology requirement. Rewrite those "
              "cards without naming any sector - say \"across the account's diverse "
              "business units\" - and return the COMPLETE card object for each."
        )
        retry_user = ("Return JSON containing only these areas: "
                      + ", ".join(sorted({s.split(':')[0] for s in rejected_sectors})) + ".")
        rejected_sectors = []
        retry_res = generate_gpt4o_json_completion(retry_system, retry_user)
        if retry_res and isinstance(retry_res, dict) and isinstance(retry_res.get("cards"), list):
            have = {c["area"] for c in cards}
            for entry in retry_res["cards"]:
                if not isinstance(entry, dict):
                    continue
                area = str(entry.get("area") or "").strip()
                src_area = by_area.get(area)
                if not src_area or area in have:
                    continue
                objection = str(entry.get("objection") or "").strip()
                reframe = str(entry.get("reframe") or "").strip()
                counter = str(entry.get("counter_question") or "").strip()
                if not (objection and reframe and counter):
                    continue
                if _sector_terms_used(reframe + " " + counter, business_description):
                    continue
                if any(check_text(ground, report, area, objection, reframe, counter)):
                    continue
                cards.append({
                    "card_id": hashlib.sha1(area.encode("utf-8")).hexdigest()[:12],
                    "area": area,
                    "objection": objection,
                    "reframe": reframe,
                    "counter_question": counter,
                    "why_expected": str(entry.get("why_expected") or "").strip() or None,
                    "recommended_next_step": str(entry.get("recommended_next_step") or "").strip() or None,
                    "hp_proof_point": None,
                    "hp_proof_point_note": NO_PROOF_POINT,
                    "evidence_source_link": None,
                    "evidence_date": None,
                    "evidence_confidence": None,
                    "evidence": src_area["evidence"],
                    "evidence_columns": src_area["columns"],
                    "detected_vendors": src_area["detected_vendors"],
                    "context_vendors": src_area.get("context_vendors", []),
                    "not_in_technographics": src_area["not_in_technographics"],
                    "likely_raiser": src_area["likely_raiser"],
                    "likely_raiser_source": src_area["likely_raiser_source"],
                })

    # "If two objections differ only in wording, merge them and preserve
    # persona-specific variants inside one entry."
    merged: list[dict] = []
    for card in cards:
        canon = re.sub(r"[^a-z0-9 ]", "", _norm_objection(card["objection"]))
        twin = next((m for m in merged
                     if difflib.SequenceMatcher(None, canon, m["_canon"]).ratio() >= 0.85), None)
        if twin:
            twin.setdefault("variants", []).append({
                "area": card["area"],
                "objection": card["objection"],
                "likely_raiser": card["likely_raiser"],
            })
            continue
        card["_canon"] = canon
        merged.append(card)
    for m in merged:
        m.pop("_canon", None)
    cards = merged[:MAX_OBJECTIONS]

    if cards:
        return {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_reframe_cards",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "evidence_fingerprint": fingerprint,
                "cards_count": len(cards),
                "cards": cards,
                "grounding_report": report.as_dict(),
                "disclaimer": ("Anticipated objections a seller should be ready for, generated "
                               "from this account's technographics evidence. Not statements made "
                               "by any contact."),
            },
            "source_datasets": ["technographics", "firmographics", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }

    if existing and existing.get("status") == "available":
        return existing
    return None


def extract_objection_playbook(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    techno_records = _read_dataset_records(account_id, "technographics")
    firmo_records = _read_dataset_records(account_id, "firmographics")
    contact_records = _read_dataset_records(account_id, "prospect_contacts")

    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"
    
    results = []

    # 1. Widget: objection_incumbent_context (Deterministic)
    incumbent_techs = []
    active_categories = []

    if techno_records and len(techno_records) > 0:
        row = techno_records[0]
        raw_full = str(row.get("Full Tech Stack") or "").strip()
        if raw_full:
            incumbent_techs = [s.strip() for s in raw_full.split(",") if s.strip()]

        for col in TECHNOGRAPHICS_CATEGORY_COLUMNS:
            val = str(row.get(col) or "").strip()
            if val:
                active_categories.append(col)

    business_context = {}
    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]
        
        c_name = str(f.get("Company Name") or f.get("company_name") or f.get("Name") or "").strip()
        domain_val = str(f.get("Company Domain") or f.get("company_domain") or f.get("Domain") or f.get("Website") or f.get("website") or "").strip()
        
        city = str(f.get("City Name") or f.get("city_name") or "").strip()
        region = str(f.get("Region Name") or f.get("region_name") or "").strip()
        country = str(f.get("Country Name") or f.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_loc_val = ", ".join(loc_parts) if loc_parts else str(f.get("HQ Location") or f.get("hq_location") or "").strip()

        linkedin_ind = str(f.get("Linkedin Industry Category") or f.get("linkedin_industry_category") or "").strip()
        naics = str(f.get("Naics Description") or f.get("naics_description") or "").strip()
        sic = str(f.get("Sic Code Description") or f.get("sic_code_description") or "").strip()
        ind_parts = [p for p in [linkedin_ind, naics, sic] if p]
        ind_val = " / ".join(list(dict.fromkeys(ind_parts))) if ind_parts else str(f.get("Industry Classification") or f.get("industry") or "").strip()

        emp_val = str(f.get("Number Of Employees Range") or f.get("employee_count_range") or f.get("Employee Count") or f.get("employee_count") or "").strip()
        rev_val = str(f.get("Yearly Revenue Range") or f.get("yearly_revenue_range") or f.get("Yearly Revenue") or f.get("revenue") or "").strip()

        business_context = {
            "business_description": str(f.get("Business Description")
                                        or f.get("business_description") or "").strip(),
            "company_name": c_name,
            "domain": domain_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

    # Per-area evidence, and who at this account owns each area. Both entirely
    # deterministic and both computed before any model call.
    area_evidence = []
    if techno_records:
        area_evidence = _build_area_evidence(techno_records[0])
        for a in area_evidence:
            raiser, raiser_source = _resolve_likely_raiser(a["area"], contact_records)
            a["likely_raiser"] = raiser
            a["likely_raiser_source"] = raiser_source

    if incumbent_techs or business_context:
        incumbent_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_incumbent_context",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_incumbents_count": len(incumbent_techs),
                "incumbent_technologies": incumbent_techs,
                "relevant_categories": active_categories,
                "business_context": business_context,
                "area_evidence": area_evidence
            },
            "source_datasets": ["technographics", "firmographics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        incumbent_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_incumbent_context",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technographics", "firmographics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "objection_incumbent_context"},
        {"$set": incumbent_payload},
        upsert=True
    )
    results.append(incumbent_payload)

    # 2. Widget: objection_reframe_cards (Inferred). Cached on a fingerprint of
    #    the evidence set, so a page load costs no model call.
    reframe_payload = None
    if area_evidence:
        reframe_payload = generate_objection_cards(
            account_id,
            area_evidence,
            company_name,
            str(business_context.get("business_description") or "").strip(),
        )

    if reframe_payload is None:
        reframe_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_reframe_cards",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "evidence_fingerprint": None,
                "cards_count": 0,
                "cards": [],
                "notice": ("Objection generation requires OPENAI_API_KEY. The incumbent "
                           "evidence below is shown as extracted; no objections are invented."),
            },
            "source_datasets": ["technographics", "firmographics", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "objection_reframe_cards"},
        {"$set": reframe_payload},
        upsert=True
    )
    results.append(reframe_payload)

    return results
