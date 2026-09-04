import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db

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

def extract_objection_playbook(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    techno_records = _read_dataset_records(account_id, "technographics")
    firmo_records = _read_dataset_records(account_id, "firmographics")
    
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
            "company_name": c_name,
            "domain": domain_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

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
                "business_context": business_context
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

    # 2. Widget: objection_reframe_cards (Inferred - Left as Pending / TBD)
    reframe_payload = {
        "account_id": account_id,
        "feature_key": "objection_playbook",
        "widget_key": "objection_reframe_cards",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "cards": [],
            "notice": "AI-generated objection reframes, counter questions, and likely raisers are TBD for Step 8 AI model execution."
        },
        "source_datasets": ["technographics", "firmographics"],
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
