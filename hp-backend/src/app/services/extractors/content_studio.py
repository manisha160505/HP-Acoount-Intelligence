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
    "firmographics", "google_news", "job_openings", "news_events", "prospect_contacts",
)
def extract_content_studio(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")
    contacts_records = _read_dataset_records(account_id, "prospect_contacts")
    intent_records = _read_dataset_records(account_id, "intent_score")
    
    results = []

    # 1. Target Personas (Combining standard ABM personas + directly sourced decision makers)
    base_personas = [
        {"id": "cio_it", "title": "CIO / IT Leadership", "subtitle": "Chief Information Officer and IT decision makers"},
        {"id": "infra_workplace", "title": "Infrastructure & Workplace IT", "subtitle": "Device fleet owners, infrastructure strategy & commercial teams"},
        {"id": "engineering_ai", "title": "Engineering / AI & Compute Leadership", "subtitle": "AI Centre of Excellence, ML and GPU/compute buyers"},
        {"id": "security_wolf", "title": "Security Leadership (Wolf Security)", "subtitle": "Endpoint security and risk decision makers"},
        {"id": "procurement_finance", "title": "Procurement / Finance", "subtitle": "Regional IT procurement and budget holders"},
        {"id": "operations", "title": "Regional Operations", "subtitle": "New office / expansion leads, print & workplace services"},
        {"id": "hr_workforce", "title": "HR / Workforce Experience", "subtitle": "Device refresh, hybrid work and onboarding programs"}
    ]

    # Parse contact decision makers directly from prospect_contacts.csv
    sourced_contact_personas = []
    seen_titles = set()
    for row in contacts_records:
        title = str(row.get("Prospect job_title") or row.get("title") or row.get("Job Title") or "").strip()
        name = str(row.get("Prospect full_name") or row.get("full_name") or row.get("Name") or "").strip()
        dept = str(row.get("Prospect job_department") or row.get("department") or "").strip()

        if title and title.lower() not in seen_titles and len(title) > 3:
            seen_titles.add(title.lower())
            p_id = f"contact_{len(sourced_contact_personas) + 1}"
            subtitle_str = f"Sourced Contact: {name} ({dept})" if name and dept else f"Sourced Target Title in Account"
            sourced_contact_personas.append({
                "id": p_id,
                "title": title.title(),
                "subtitle": subtitle_str,
                "is_sourced_contact": True
            })

    target_personas = base_personas + sourced_contact_personas[:5]

    # 2. Content Types
    content_types = [
        {"id": "email", "title": "Email", "subtitle": "Personalized executive outreach email"},
        {"id": "linkedin", "title": "LinkedIn Post", "subtitle": "Social selling content for LinkedIn"},
        {"id": "one_pager", "title": "One-Pager", "subtitle": "Single-page solution overview for the account"},
        {"id": "exec_brief", "title": "Executive Brief", "subtitle": "2-page intelligence brief for leadership"},
        {"id": "follow_up", "title": "Follow-up Note", "subtitle": "Post-meeting follow-up with next steps"},
        {"id": "branded_emailer", "title": "Branded Emailer", "subtitle": "HP-branded email with visual preview and HTML download"},
        {"id": "landing_page", "title": "Landing Page", "subtitle": "HP-branded landing page with visual preview and HTML download"}
    ]

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
            "business_context": business_context
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

    # Widget 2: content_generated_assets (Inferred - Left as Pending / TBD)
    generated_payload = {
        "account_id": account_id,
        "feature_key": "content_studio",
        "widget_key": "content_generated_assets",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "generated_content": "Inferred TBD",
            "notice": "Persona-targeted ABM content generation (executive outreach email, one-pager, executive brief, landing page HTML) using LLM prompts is TBD for Step 8 AI model execution."
        },
        "source_datasets": ["prospect_contacts", "job_openings"],
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
