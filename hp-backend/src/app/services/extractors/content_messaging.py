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

def extract_content_messaging(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Read approved 5 datasets ONLY
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_score_records = _read_dataset_records(account_id, "intent_score")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")

    results = []

    # A. Business Context
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

    # B. Technology Evidence
    full_tech_stack = []
    category_matrix = {}
    if techno_records and len(techno_records) > 0:
        t = techno_records[0]
        raw_full = str(t.get("Full Tech Stack") or "").strip()
        if raw_full:
            full_tech_stack = [s.strip() for s in raw_full.split(",") if s.strip()]

        for col in TECHNOGRAPHICS_CATEGORY_COLUMNS:
            val = str(t.get(col) or "").strip()
            if val:
                items = [item.strip() for item in val.split(",") if item.strip()]
                if items:
                    category_matrix[col] = items

    technology_evidence = {
        "full_tech_stack": full_tech_stack,
        "category_matrix": category_matrix,
        "total_tech_count": len(full_tech_stack)
    }

    # C. Intent Evidence (from intent_score.csv)
    intent_topics_list = []
    for r in intent_score_records:
        t_name = str(r.get("Topic") or r.get("topic_name") or r.get("topic") or "").strip()
        c_score = str(r.get("Composite Score") or r.get("composite_score") or r.get("score") or "").strip()
        if t_name or c_score:
            intent_topics_list.append({
                "topic_name": t_name,
                "composite_score": c_score
            })

    intent_evidence = {
        "topics": intent_topics_list,
        "total_topics_count": len(intent_topics_list)
    }

    # D. News / Trigger Evidence (from google_news.csv + news_events.csv)
    triggers_list = []
    seen_headlines = set()

    for row in gnews_records:
        headline = str(row.get("event_headline") or row.get("news_announcements") or row.get("title") or "").strip()
        e_date = str(row.get("event_date") or row.get("date") or "").strip()
        e_type = str(row.get("event_type") or "Google News").strip()
        s_url = str(row.get("event_url") or row.get("source_url") or row.get("url") or "").strip()

        if headline and headline.lower() not in seen_headlines:
            seen_headlines.add(headline.lower())
            triggers_list.append({
                "event_headline": headline,
                "event_date": e_date,
                "event_type": e_type,
                "source_url": s_url
            })

    for row in events_records:
        headline = str(row.get("event_headline") or row.get("title") or "").strip()
        e_date = str(row.get("event_date") or row.get("date") or "").strip()
        e_type = str(row.get("event_type") or "News Event").strip()
        s_url = str(row.get("source_url") or row.get("event_url") or "").strip()

        if headline and headline.lower() not in seen_headlines:
            seen_headlines.add(headline.lower())
            triggers_list.append({
                "event_headline": headline,
                "event_date": e_date,
                "event_type": e_type,
                "source_url": s_url
            })

    news_evidence = {
        "total_trigger_count": len(triggers_list),
        "triggers": triggers_list
    }

    total_sourced_signals = len(full_tech_stack) + len(intent_topics_list) + len(triggers_list)

    if business_context or full_tech_stack or intent_topics_list or triggers_list:
        context_payload = {
            "account_id": account_id,
            "feature_key": "content_messaging",
            "widget_key": "messaging_context_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_sourced_signals": total_sourced_signals,
                "business_context": business_context,
                "technology_evidence": technology_evidence,
                "intent_evidence": intent_evidence,
                "news_evidence": news_evidence
            },
            "source_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        context_payload = {
            "account_id": account_id,
            "feature_key": "content_messaging",
            "widget_key": "messaging_context_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "messaging_context_card"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # 2. Widget: messaging_pillars_output (Inferred - Left as Pending / TBD)
    pillars_payload = {
        "account_id": account_id,
        "feature_key": "content_messaging",
        "widget_key": "messaging_pillars_output",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "umbrella_message": "Inferred TBD",
            "pillars": [],
            "why_hp": [],
            "notice": "AI campaign message house synthesis (umbrella message, messaging pillars, challenge/benefit pairs, and Why HP positioning) is TBD for Step 8 AI model execution."
        },
        "source_datasets": ["firmographics", "technographics", "intent_score"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "messaging_pillars_output"},
        {"$set": pillars_payload},
        upsert=True
    )
    results.append(pillars_payload)

    return results
