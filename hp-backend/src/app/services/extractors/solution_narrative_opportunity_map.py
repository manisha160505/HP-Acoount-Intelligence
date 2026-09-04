import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.recent_news_signals import extract_recent_news_signals

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
    full_path = os.path.join(os.getcwd(), rel_path)
    
    if not os.path.exists(full_path):
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

def extract_solution_narrative_opportunity_map(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_records = _read_dataset_records(account_id, "intent_score")
    
    results = []

    # 1. Widget: opportunity_context_card (Deterministic Narrative Context)
    bus_desc = ""
    if firmo_records and len(firmo_records) > 0:
        bus_desc = (str(firmo_records[0].get("Business Description") or "")).strip()

    tech_stack_items = []
    if techno_records and len(techno_records) > 0:
        raw_stack = (str(techno_records[0].get("Full Tech Stack") or "")).strip()
        if raw_stack:
            tech_stack_items = [s.strip() for s in raw_stack.split(",") if s.strip()]

    top_intent_topics = []
    for r in intent_records:
        t_name = (str(r.get("Topic") or "")).strip()
        c_score_raw = (str(r.get("Composite Score") or "0")).strip()
        try:
            c_score = int(float(c_score_raw))
        except (ValueError, TypeError):
            c_score = 0

        if t_name:
            top_intent_topics.append({
                "topic_name": t_name,
                "composite_score": c_score
            })

    top_intent_topics.sort(key=lambda x: x["composite_score"], reverse=True)

    has_context = bool(bus_desc or tech_stack_items or top_intent_topics)

    if has_context:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "business_description": bus_desc,
                "full_tech_stack_sample": tech_stack_items,
                "total_tech_items_count": len(tech_stack_items),
                "top_intent_topics": top_intent_topics[:10],
                "total_intent_topics_count": len(top_intent_topics)
            },
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_context_card"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # 2. Widget: opportunity_trigger_signals (Deterministic Trigger Events)
    # Reuses normalized event extraction architecture from Step 7.2
    news_res = extract_recent_news_signals(account_id)
    news_signals = news_res[0]["data"].get("signals", []) if (news_res and news_res[0]["status"] == "available") else []

    if news_signals:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_trigger_count": len(news_signals),
                "triggers": news_signals
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_trigger_signals"},
        {"$set": triggers_payload},
        upsert=True
    )
    results.append(triggers_payload)

    # 3. Widget: opportunity_narrative_plays (STRICTLY UNTOUCHED - Inferred TBD Placeholder)
    plays_payload = {
        "account_id": account_id,
        "feature_key": "solution_narrative_opportunity_map",
        "widget_key": "opportunity_narrative_plays",
        "data_classification": "inferred",
        "status": "empty",
        "data": {},
        "source_datasets": ["firmographics", "technographics", "google_news"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_narrative_plays"},
        {"$set": plays_payload},
        upsert=True
    )
    results.append(plays_payload)

    return results
