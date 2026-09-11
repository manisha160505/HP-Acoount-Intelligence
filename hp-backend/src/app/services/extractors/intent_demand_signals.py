import os
import io
import csv
import json
import pandas as pd
from collections import Counter
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

def _find_file_path(rel_path: str) -> str | None:
    """Shared implementation - see datasets.py."""
    return find_file_path(rel_path)

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

@requires_local_datasets(
    "intent_score", "intent_topics", "job_openings",
)
def extract_intent_demand_signals(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    score_records = _read_dataset_records(account_id, "intent_score")
    topics_meta_records = _read_dataset_records(account_id, "intent_topics")
    job_records = _read_dataset_records(account_id, "job_openings")
    
    results = []

    # 1. Process Widget: intent_topics_table
    default_intent_level = ""
    if topics_meta_records and len(topics_meta_records) > 0:
        default_intent_level = (str(topics_meta_records[0].get("Level Of Intent") or "")).strip()

    extracted_topics = []
    for row in score_records:
        t_name = (str(row.get("Topic") or "")).strip()
        c_score_raw = str(row.get("Composite Score") or "").strip()
        
        try:
            c_score = int(float(c_score_raw))
        except (ValueError, TypeError):
            c_score = 0

        if t_name:
            extracted_topics.append({
                "topic_name": t_name,
                "composite_score": c_score,
                "intent_level": default_intent_level
            })

    # Sort topics by composite score descending
    extracted_topics.sort(key=lambda x: x["composite_score"], reverse=True)

    if extracted_topics:
        topics_payload = {
            "account_id": account_id,
            "feature_key": "intent_demand_signals",
            "widget_key": "intent_topics_table",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_topics_count": len(extracted_topics),
                "level_of_intent": default_intent_level,
                "topics": extracted_topics
            },
            "source_datasets": ["intent_score", "intent_topics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        topics_payload = {
            "account_id": account_id,
            "feature_key": "intent_demand_signals",
            "widget_key": "intent_topics_table",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["intent_score", "intent_topics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "intent_topics_table"},
        {"$set": topics_payload},
        upsert=True
    )
    results.append(topics_payload)

    # 2. Process Widget: intent_hiring_demand
    if job_records and len(job_records) > 0:
        sen_counter = Counter()
        cat_counter = Counter()

        for j in job_records:
            sen = (str(j.get("seniority") or "")).strip().lower()
            if sen:
                sen_counter[sen] += 1
            else:
                sen_counter["unspecified"] += 1

            cat_raw = (str(j.get("categories") or "")).strip()
            if cat_raw:
                try:
                    # Parse JSON array string e.g. ["information_technology", "management"]
                    cat_list = json.loads(cat_raw)
                    if isinstance(cat_list, list):
                        for c in cat_list:
                            cat_counter[str(c).strip().lower()] += 1
                    else:
                        cat_counter[cat_raw.lower()] += 1
                except Exception:
                    cat_counter[cat_raw.lower()] += 1

        hiring_payload = {
            "account_id": account_id,
            "feature_key": "intent_demand_signals",
            "widget_key": "intent_hiring_demand",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "open_job_count": len(job_records),
                "seniority_breakdown": dict(sen_counter),
                "category_breakdown": dict(cat_counter.most_common(10))
            },
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        hiring_payload = {
            "account_id": account_id,
            "feature_key": "intent_demand_signals",
            "widget_key": "intent_hiring_demand",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "intent_hiring_demand"},
        {"$set": hiring_payload},
        upsert=True
    )
    results.append(hiring_payload)

    return results
