import os
import io
import csv
import pandas as pd
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
        "dataset_key": dataset_key,
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
            # Replace NaN with empty string
            df = df.fillna("")
            return df.to_dict(orient="records")
        else:
            with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                return [row for row in reader]
    except Exception:
        return []

def extract_recent_news_signals(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")
    
    extracted_signals = []

    # 1. Process Google News RSS records (Primary)
    for row in gnews_records:
        headline = (str(row.get("event_headline") or row.get("news_announcements") or "")).strip()
        detail = (str(row.get("news_announcements") or row.get("event_headline") or "")).strip()
        date_str = (str(row.get("event_date") or "")).strip()
        event_type = (str(row.get("event_type") or "")).strip()
        source_url = (str(row.get("event_url") or "")).strip()

        if headline:
            extracted_signals.append({
                "event_headline": headline,
                "article_detail": detail,
                "event_date": date_str if date_str else "N/A",
                "event_type": event_type if event_type else "news",
                "source_url": source_url if source_url.startswith("http") else None
            })

    # 2. Process Source B News Events records (Add-on)
    for row in events_records:
        headline = (str(row.get("summary") or row.get("article_sentence") or "")).strip()
        detail = (str(row.get("article_sentence") or row.get("summary") or "")).strip()
        date_raw = (str(row.get("effective_date") or row.get("found_at") or "")).strip()
        event_type = (str(row.get("category") or row.get("event") or row.get("financing_type") or "")).strip()

        # Format date if ISO string
        date_str = "N/A"
        if date_raw:
            date_str = date_raw.split("T")[0] if "T" in date_raw else date_raw

        if headline:
            extracted_signals.append({
                "event_headline": headline,
                "article_detail": detail,
                "event_date": date_str,
                "event_type": event_type if event_type else "news",
                "source_url": None  # company_domain is a domain name, not an article URL
            })

    # 3. Sort by Date Descending
    def parse_sort_key(sig):
        d = sig.get("event_date", "")
        if d and d != "N/A":
            return d
        return "0000-00-00"

    extracted_signals.sort(key=parse_sort_key, reverse=True)

    # 4. Construct Payload
    if extracted_signals:
        news_payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_signals_feed",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_signals_count": len(extracted_signals),
                "signals": extracted_signals
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        news_payload = {
            "account_id": account_id,
            "feature_key": "recent_news_signals",
            "widget_key": "news_signals_feed",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    # Upsert news_signals_feed in MongoDB account_widgets
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "news_signals_feed"},
        {"$set": news_payload},
        upsert=True
    )

    return [news_payload]
