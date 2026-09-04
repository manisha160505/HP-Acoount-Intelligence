import os
import io
import csv
import json
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db

ARCHETYPE_PERSONAS = [
    {
        "id": "ciso",
        "label": "CISO — Chief Information Security Officer",
        "short_title": "CISO",
        "department": "Information Security / IT Risk",
        "seniority": "C-Level",
        "target_persona": "Security Decision Maker",
        "matching_keywords": ["security", "risk", "governance", "audit", "compliance"]
    },
    {
        "id": "cio",
        "label": "CIO — Chief Information Officer",
        "short_title": "CIO",
        "department": "CIO Office / Executive IT",
        "seniority": "C-Level",
        "target_persona": "Executive IT Decision Maker",
        "matching_keywords": ["cio", "chief information", "pdca", "information technology"]
    },
    {
        "id": "cto",
        "label": "CTO — Chief Technology Officer",
        "short_title": "CTO",
        "department": "Technology / Engineering",
        "seniority": "C-Level",
        "target_persona": "Technology Decision Maker",
        "matching_keywords": ["cto", "technology development", "technology officer", "engineering"]
    },
    {
        "id": "vp_infra",
        "label": "VP Infrastructure — VP of Infrastructure & Infrastructure Security",
        "short_title": "VP Infrastructure",
        "department": "IT Operations / Infrastructure",
        "seniority": "VP / Director",
        "target_persona": "Infrastructure Lead",
        "matching_keywords": ["infrastructure", "development operations", "cloud operation", "system administrator", "devops"]
    },
    {
        "id": "sec_architect",
        "label": "Security Architect — Security Architect / Director of Security",
        "short_title": "Security Architect",
        "department": "Security Architecture / Governance",
        "seniority": "Director / Head",
        "target_persona": "Security Evaluator",
        "matching_keywords": ["security", "risk advisory", "governance", "threat"]
    },
    {
        "id": "net_architect",
        "label": "Network Architect — Network Architect / Director of Network Engineering",
        "short_title": "Network Architect",
        "department": "Network Engineering / Communications",
        "seniority": "Director / Head",
        "target_persona": "Network Lead",
        "matching_keywords": ["network", "cloud", "telecommunications", "systems"]
    },
    {
        "id": "it_director",
        "label": "IT Director — IT Director / Director of Applications",
        "short_title": "IT Director",
        "department": "Applications Operations / Enterprise Systems",
        "seniority": "Director / Head",
        "target_persona": "Applications Lead",
        "matching_keywords": ["applications", "software quality", "data governance", "business intelligence", "procurement"]
    },
    {
        "id": "procurement_finance",
        "label": "Procurement/Finance — CFO / VP of Procurement / Finance Executive",
        "short_title": "Procurement / Finance",
        "department": "Procurement / Corporate Finance",
        "seniority": "Director / Head",
        "target_persona": "Economic Buyer",
        "matching_keywords": ["procurement", "finance", "tax", "accounting", "purchasing"]
    }
]

def _find_file_path(rel_path: str) -> str | None:
    if not rel_path:
        return None
    candidate_paths = [
        os.path.join(os.getcwd(), rel_path),
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

def extract_message_evaluator(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    
    account_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"
    
    contacts_records = _read_dataset_records(account_id, "prospect_contacts")
    job_records = _read_dataset_records(account_id, "job_openings")
    
    results = []
    
    # 1. Map contacts to Archetypes
    calibrated_personas = []
    
    for arch in ARCHETYPE_PERSONAS:
        matching_contact = None
        
        for c in contacts_records:
            full_title = (str(c.get("Prospect job_title") or c.get("apollo_title") or "")).lower()
            dept = (str(c.get("Prospect job_department_main") or c.get("apollo_department") or "")).lower()
            skills = (str(c.get("Prospect skills") or "")).lower()
            
            combined_text = f"{full_title} {dept} {skills}"
            if any(k in combined_text for k in arch["matching_keywords"]):
                matching_contact = c
                break
                
        # If no specific match, fallback to general contact or account role proxy
        if not matching_contact and contacts_records:
            matching_contact = contacts_records[0]
            
        contact_name = "Account Executive Lead"
        contact_title = arch["short_title"]
        contact_dept = arch["department"]
        contact_seniority = arch["seniority"]
        contact_email = None
        contact_phone = None
        contact_linkedin = None
        buying_persona = arch["target_persona"]
        source_name = "Archetype Template"
        
        if matching_contact:
            fname = (str(matching_contact.get("Prospect full_name") or "")).strip()
            if not fname:
                fn = (str(matching_contact.get("Prospect first_name") or "")).strip()
                ln = (str(matching_contact.get("Prospect last_name") or "")).strip()
                fname = f"{fn} {ln}".strip()
            if fname:
                contact_name = fname
                
            t = (str(matching_contact.get("Prospect job_title") or matching_contact.get("apollo_title") or "")).strip()
            if t:
                contact_title = t
                
            d = (str(matching_contact.get("Prospect job_department_main") or matching_contact.get("apollo_department") or "")).strip()
            if d:
                contact_dept = d
                
            s = (str(matching_contact.get("Prospect job_level_main") or matching_contact.get("apollo_seniority") or "")).strip()
            if s:
                contact_seniority = s
                
            em = (str(matching_contact.get("Contact professions_email") or matching_contact.get("Email") or matching_contact.get("apollo_verified_work_email") or "")).strip()
            if em:
                contact_email = em
                
            ph = (str(matching_contact.get("Contact mobile_phone") or matching_contact.get("Mobile Phone") or matching_contact.get("apollo_direct_mobile_phone") or "")).strip()
            if ph:
                contact_phone = ph
                
            li = (str(matching_contact.get("Prospect linkedin") or matching_contact.get("apollo_linkedin_url") or "")).strip()
            if li:
                contact_linkedin = li
                
            bp = (str(matching_contact.get("Prospect buying_committee_personas") or "")).strip()
            if bp:
                buying_persona = bp.replace('[', '').replace(']', '').replace('"', '')
                
            source_name = "14_prospect_contacts.csv"
            
        calibrated_personas.append({
            "id": arch["id"],
            "label": arch["label"],
            "short_title": arch["short_title"],
            "archetype_role": arch["label"],
            "account_name": account_name,
            "matched_contact": {
                "name": contact_name,
                "title": contact_title,
                "department": contact_dept,
                "seniority": contact_seniority,
                "email": contact_email,
                "phone": contact_phone,
                "linkedin_url": contact_linkedin,
                "buying_committee_persona": buying_persona,
                "data_source": source_name
            },
            "behavioral_profile": {
                "decision_orientation": "Inferred TBD",
                "risk_tolerance": "Inferred TBD",
                "communication_style": "Inferred TBD",
                "primary_concerns": ["Inferred TBD", "Inferred TBD"],
                "objection_triggers": ["Inferred TBD", "Inferred TBD"]
            }
        })
        
    # 2. Extract job openings role proxies
    job_proxies = []
    for j in job_records[:10]:
        jt = (str(j.get("title") or j.get("normalized_title") or "")).strip()
        jsen = (str(j.get("seniority") or "mid")).strip()
        if jt and jt not in [p["title"] for p in job_proxies]:
            job_proxies.append({
                "title": jt,
                "seniority": jsen,
                "source": "job_openings.csv"
            })
            
    persona_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_persona_context",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "account_name": account_name,
            "total_contacts_mapped": len(contacts_records),
            "archetypes": calibrated_personas,
            "job_role_proxies": job_proxies
        },
        "source_datasets": ["prospect_contacts", "job_openings"],
        "extracted_at": now,
        "updated_at": now
    }
    
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_persona_context"},
        {"$set": persona_payload},
        upsert=True
    )
    results.append(persona_payload)
    
    # 3. Widget: evaluator_feedback_score schema
    feedback_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_feedback_score",
        "data_classification": "inferred",
        "status": "empty",
        "data": {
            "evaluation_engine": "Inferred TBD",
            "supported_modes": ["LITE", "DEEP"],
            "funnel_stages": [
                "Initial Outreach / Cold Prospecting",
                "Follow-up / Re-engagement",
                "Discovery / Meeting Request",
                "Solution Presentation / Pitch",
                "Objection Handling",
                "Executive Briefing",
                "Proposal / Commercial Closing"
            ],
            "content_formats": [
                "Cold Email",
                "LinkedIn Message / InMail",
                "Sales Call Script / Phone Pitch",
                "Executive Briefing / One-Pager",
                "Follow-up Email"
            ]
        },
        "source_datasets": ["prospect_contacts", "job_openings"],
        "extracted_at": now,
        "updated_at": now
    }
    
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_feedback_score"},
        {"$set": feedback_payload},
        upsert=True
    )
    results.append(feedback_payload)
    
    return results
