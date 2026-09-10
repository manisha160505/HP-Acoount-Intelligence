import os
import io
import csv
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

def _find_file_path(rel_path: str) -> str | None:
    """Shared implementation - see datasets.py."""
    return find_file_path(rel_path)

def _read_dataset_csv(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

@requires_local_datasets(
    "company_hierarchy", "firmographics", "job_openings", "prospect_contacts",
)
def extract_executive_dashboard(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_rows = _read_dataset_csv(account_id, "firmographics")
    hier_rows = _read_dataset_csv(account_id, "company_hierarchy")
    job_rows = _read_dataset_csv(account_id, "job_openings")
    contact_rows = _read_dataset_csv(account_id, "prospect_contacts")
    
    results = []

    # 1. exec_summary_card
    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]
        
        # Extract location string
        city = (row.get("City Name") or row.get("city_name") or "").strip()
        region = (row.get("Region Name") or row.get("region_name") or "").strip()
        country = (row.get("Country Name") or row.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_location = ", ".join(loc_parts) if loc_parts else "N/A"
        
        # Extract industry
        naics = (row.get("Naics Description") or row.get("naics_description") or "").strip()
        sic = (row.get("Sic Code Description") or row.get("sic_code_description") or "").strip()
        linkedin_ind = (row.get("Linkedin Industry Category") or row.get("linkedin_industry_category") or "").strip()
        ind_parts = [p for p in [linkedin_ind, naics, sic] if p]
        industry_classification = " / ".join(list(dict.fromkeys(ind_parts))) if ind_parts else "N/A"
        
        # Hierarchy fields
        parent_company = ""
        ultimate_parent = ""
        if hier_rows and len(hier_rows) > 0:
            h_row = hier_rows[0]
            parent_company = (h_row.get("Parent Company Name") or h_row.get("parent_company_name") or "").strip()
            ultimate_parent = (h_row.get("Ultimate Parent Name") or h_row.get("ultimate_parent_name") or "").strip()

        summary_data = {
            "company_name": (row.get("Company Name") or row.get("Name") or "").strip(),
            "domain": (row.get("Company Domain") or row.get("Website") or "").strip(),
            "business_description": (row.get("Business Description") or "").strip(),
            "industry_classification": industry_classification,
            "hq_location": hq_location,
            "parent_company": parent_company,
            "ultimate_parent": ultimate_parent,
            "stakeholders_mapped_count": len(contact_rows)
        }
        
        summary_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_summary_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": summary_data,
            "source_datasets": ["firmographics", "company_hierarchy", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        summary_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_summary_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "company_hierarchy"],
            "extracted_at": now,
            "updated_at": now
        }

    # Upsert exec_summary_card in MongoDB account_widgets
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"},
        {"$set": summary_payload},
        upsert=True
    )
    results.append(summary_payload)

    # 2. exec_key_metrics
    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]
        emp_count = (row.get("Number Of Employees Range") or row.get("number_of_employees_range") or "").strip()
        revenue = (row.get("Yearly Revenue Range") or row.get("yearly_revenue_range") or "").strip()

        metrics_data = {
            "employee_count": emp_count if emp_count else "N/A",
            "revenue": revenue if revenue else "N/A"
        }
        
        metrics_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_key_metrics",
            "data_classification": "deterministic",
            "status": "available",
            "data": metrics_data,
            "source_datasets": ["firmographics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        metrics_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_key_metrics",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_key_metrics"},
        {"$set": metrics_payload},
        upsert=True
    )
    results.append(metrics_payload)

    # 3. exec_hiring_velocity
    if job_rows and len(job_rows) > 0:
        sample_roles = []
        for r in job_rows[:5]:
            t = (r.get("title") or r.get("normalized_title") or "").strip()
            if t and t not in sample_roles:
                sample_roles.append(t)
        
        hiring_data = {
            "open_job_count": len(job_rows),
            "sample_roles": sample_roles
        }

        hiring_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_hiring_velocity",
            "data_classification": "deterministic",
            "status": "available",
            "data": hiring_data,
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        hiring_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_hiring_velocity",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_hiring_velocity"},
        {"$set": hiring_payload},
        upsert=True
    )
    results.append(hiring_payload)

    return results
