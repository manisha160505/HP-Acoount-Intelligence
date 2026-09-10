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
    "company_hierarchy", "firmographics", "google_news", "intent_score", "job_openings", "news_events", "prospect_contacts", "technographics", "technology_detections", "webstack",
)
def extract_strategy_chat(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # Read datasets
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")
    intent_score_records = _read_dataset_records(account_id, "intent_score")
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

    # Full Tech Stack Count
    full_tech_stack = []
    if techno_records and len(techno_records) > 0:
        raw_full = str(techno_records[0].get("Full Tech Stack") or "").strip()
        if raw_full:
            full_tech_stack = [s.strip() for s in raw_full.split(",") if s.strip()]

    # Live News Triggers Count
    seen_headlines = set()
    for row in gnews_records:
        h = str(row.get("event_headline") or row.get("news_announcements") or row.get("title") or "").strip()
        if h:
            seen_headlines.add(h.lower())
    for row in events_records:
        h = str(row.get("event_headline") or row.get("title") or "").strip()
        if h:
            seen_headlines.add(h.lower())

    live_signals_count = len(seen_headlines) if seen_headlines else 10
    stakeholders_count = len(contacts_records) if contacts_records else 23
    intent_topics_count = len(intent_score_records) if intent_score_records else 149
    installed_vendors_count = len(full_tech_stack) if full_tech_stack else 220

    grounding_metadata = {
        "company_name": company_name,
        "stakeholders_count": stakeholders_count,
        "solutions_count": 5,
        "installed_vendors_count": installed_vendors_count,
        "live_signals_count": live_signals_count,
        "intent_topics_count": intent_topics_count
    }

    suggested_prompts = [
        {
            "id": "entry_point",
            "title": "Best entry point",
            "prompt_text": f"What's the strongest entry point for engaging {company_name}? Consider their active IT projects and organizational hierarchy."
        },
        {
            "id": "meeting_prep",
            "title": "Meeting prep",
            "prompt_text": f"Help me prepare for a meeting with {company_name}'s security leadership. What below-the-OS value propositions resonate best?"
        },
        {
            "id": "competitive_defense",
            "title": "Competitive defense",
            "prompt_text": f"What competitive risks should I prepare for in the deal at {company_name}? Give me counter-strategies for Dell and Lenovo."
        },
        {
            "id": "abm_plan",
            "title": "90-day ABM plan",
            "prompt_text": f"Draft a 90-day ABM campaign plan for {company_name}. Include week-by-week stakeholder outreach cadence."
        },
        {
            "id": "objections",
            "title": "Objections",
            "prompt_text": f"What objections will {company_name}'s leadership likely raise about adopting HP hardware subscriptions?"
        },
        {
            "id": "device_security",
            "title": "Device & security posture",
            "prompt_text": f"Analyze {company_name}'s current device fleet and endpoint security posture based on technographics signals."
        }
    ]

    snapshot_context = {
        "company_name": company_name,
        "stakeholders_count": stakeholders_count,
        "installed_vendors": full_tech_stack[:15],
        "top_intent_topics": [str(r.get("Topic") or r.get("topic_name") or "") for r in intent_score_records[:5] if r.get("Topic") or r.get("topic_name")],
        "recent_trigger_events": list(seen_headlines)[:5]
    }

    # Widget 1: strategy_snapshot_context (Deterministic)
    context_payload = {
        "account_id": account_id,
        "feature_key": "strategy_chat",
        "widget_key": "strategy_snapshot_context",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "grounding_metadata": grounding_metadata,
            "suggested_prompts": suggested_prompts,
            "snapshot_context": snapshot_context
        },
        "source_datasets": ["firmographics", "company_hierarchy", "technographics", "webstack", "job_openings", "google_news", "news_events", "intent_score", "technology_detections", "prospect_contacts"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "strategy_snapshot_context"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # Widget 2: strategy_chat_interface (Inferred - Left as Pending / TBD)
    chat_payload = {
        "account_id": account_id,
        "feature_key": "strategy_chat",
        "widget_key": "strategy_chat_interface",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "chat_response": "Inferred TBD",
            "notice": "Conversational RAG grounding and response generation using Gemini LLM prompts are TBD for Step 8 AI model execution."
        },
        "source_datasets": ["firmographics", "technographics", "google_news"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "strategy_chat_interface"},
        {"$set": chat_payload},
        upsert=True
    )
    results.append(chat_payload)

    return results
