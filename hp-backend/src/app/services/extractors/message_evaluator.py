import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

@requires_local_datasets(
    "firmographics", "job_openings", "prospect_contacts",
)
def extract_message_evaluator(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    contacts_records = _read_dataset_records(account_id, "prospect_contacts")
    
    results = []

    # Get dynamic company name
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"
    
    if firmo_records and len(firmo_records) > 0:
        f_name = str(firmo_records[0].get("Company Name") or firmo_records[0].get("company_name") or "").strip()
        if f_name:
            company_name = f_name

    # 1. Persona Archetypes
    base_personas = [
        {"id": "procurement_finance", "title": "Regional IT Procurement / Corporate IT", "default_contact_match": "Stephen Dharma", "department": "IT Procurement"},
        {"id": "cio_it", "title": "CIO / IT Leadership", "default_contact_match": "Mochamad (ivan) Triawan", "department": "Technology Development"},
        {"id": "infra_workplace", "title": "Infrastructure & Workplace IT", "subtitle": "Device fleet owners", "department": "IT Operations"},
        {"id": "security_wolf", "title": "Security Leadership (Wolf Security)", "subtitle": "Endpoint risk decision makers", "department": "Risk Advisory"},
        {"id": "engineering_ai", "title": "Engineering / AI & Compute Leadership", "subtitle": "AI & GPU compute buyers", "department": "Data Enablement"}
    ]

    sourced_contact_personas = []
    seen_titles = set()
    for row in contacts_records:
        title = str(row.get("Prospect job_title") or row.get("title") or "").strip()
        name = str(row.get("Prospect full_name") or row.get("full_name") or "").strip()
        dept = str(row.get("Prospect job_department") or row.get("department") or "").strip()

        if title and title.lower() not in seen_titles and len(title) > 3:
            seen_titles.add(title.lower())
            p_id = f"contact_{len(sourced_contact_personas) + 1}"
            sourced_contact_personas.append({
                "id": p_id,
                "title": title.title(),
                "default_contact_match": name if name else "Target Executive",
                "department": dept if dept else "Corporate",
                "is_sourced_contact": True
            })

    persona_archetypes = base_personas + sourced_contact_personas[:5]

    # 2. Business Context
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
            "company_name": c_name,
            "domain": domain_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

    # Widget 1: evaluator_persona_context (Deterministic)
    persona_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_persona_context",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "company_name": company_name,
            "persona_archetypes": persona_archetypes,
            "business_context": business_context
        },
        "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_persona_context"},
        {"$set": persona_payload},
        upsert=True
    )
    results.append(persona_payload)

    # Widget 2: evaluator_feedback_score (Inferred - Left as Pending / TBD)
    score_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_feedback_score",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "feedback_score": "Inferred TBD",
            "notice": "Message effectiveness scoring, guardrail rules evaluation, and rewrite recommendations using LLM prompts are TBD for Step 8 AI model execution."
        },
        "source_datasets": ["prospect_contacts", "job_openings"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_feedback_score"},
        {"$set": score_payload},
        upsert=True
    )
    results.append(score_payload)

    return results
