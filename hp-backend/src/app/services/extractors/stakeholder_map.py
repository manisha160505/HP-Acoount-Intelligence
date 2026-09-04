import os
import io
import csv
import json
import pandas as pd
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db

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

def resolve_field(row: dict, keys: list[str]) -> str | None:
    for k in keys:
        val = row.get(k)
        if val is not None:
            s = str(val).strip()
            if s and s.lower() not in ["none", "null", "nan", "[]"]:
                return s
    return None

def extract_stakeholder_map(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    contact_records = _read_dataset_records(account_id, "prospect_contacts")
    
    results = []

    # 1. Process Widget: stakeholder_contacts_grid
    extracted_contacts = []
    dept_counter = Counter()
    source_counter = Counter({"Source A": 0, "Apollo": 0})

    for row in contact_records:
        # Source Provenance Check
        is_apollo = bool(resolve_field(row, ["apollo_requested_contact", "apollo_matched_contact"]))
        source = "Apollo" if is_apollo else "Source A"
        source_counter[source] += 1

        # Full Name
        full_name = resolve_field(row, ["Prospect full_name"])
        if not full_name:
            fname = resolve_field(row, ["Prospect first_name"]) or ""
            lname = resolve_field(row, ["Prospect last_name"]) or ""
            combined = f"{fname} {lname}".strip()
            full_name = combined if combined else (resolve_field(row, ["apollo_title"]) or "Unknown Contact")

        # Title
        title = resolve_field(row, ["Prospect job_title", "apollo_title"])

        # Department (Rule #1: Prospect job_department_main -> apollo_department -> None)
        department = resolve_field(row, ["Prospect job_department_main", "apollo_department"])
        dept_key = department if department else "Unassigned"
        dept_counter[dept_key] += 1

        # Seniority (Rule #2: Prospect job_level_main -> apollo_seniority -> None)
        seniority = resolve_field(row, ["Prospect job_level_main", "apollo_seniority"])

        # Email (Rule #5: Contact professions_email -> Email -> apollo_verified_work_email -> None)
        email = resolve_field(row, ["Contact professions_email", "Email", "apollo_verified_work_email"])
        email_status = resolve_field(row, ["Contact professional_email_status", "Email Status", "apollo_zerobounce_email_status"])

        # Phone (Rule #4: Contact mobile_phone -> Mobile Phone -> apollo_direct_mobile_phone -> None)
        phone = resolve_field(row, ["Contact mobile_phone", "Mobile Phone", "apollo_direct_mobile_phone"])

        # LinkedIn URL (Rule #6: Prospect linkedin -> Prospect linkedin_url_array -> apollo_linkedin_url -> None)
        linkedin_url = resolve_field(row, ["Prospect linkedin", "Prospect linkedin_url_array", "apollo_linkedin_url"])

        # Buying Committee Persona (Rule #3: Source A only, None for Apollo)
        buying_persona = resolve_field(row, ["Prospect buying_committee_personas"]) if source == "Source A" else None

        extracted_contacts.append({
            "full_name": full_name,
            "title": title,
            "department": department,
            "seniority": seniority,
            "email": email,
            "email_status": email_status,
            "phone": phone,
            "linkedin_url": linkedin_url,
            "buying_committee_persona": buying_persona,
            "source": source
        })

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
                "contacts": extracted_contacts
            },
            "source_datasets": ["prospect_contacts"],
            "extracted_at": now,
            "updated_at": now
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
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "stakeholder_contacts_grid"},
        {"$set": contacts_payload},
        upsert=True
    )
    results.append(contacts_payload)

    # 2. Widget: stakeholder_influence_map (Derived Contract Placeholder - TBD)
    influence_payload = {
        "account_id": account_id,
        "feature_key": "stakeholder_map",
        "widget_key": "stakeholder_influence_map",
        "data_classification": "derived",
        "status": "empty",
        "data": {},
        "source_datasets": ["prospect_contacts"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "stakeholder_influence_map"},
        {"$set": influence_payload},
        upsert=True
    )
    results.append(influence_payload)

    return results
