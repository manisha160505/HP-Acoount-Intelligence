import os
import csv
import shutil
import logging
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.security import get_password_hash
from app.services.extractors.executive_dashboard import extract_executive_dashboard
from app.services.extractors.recent_news_signals import extract_recent_news_signals
from app.services.extractors.intent_demand_signals import extract_intent_demand_signals
from app.services.extractors.solution_narrative_opportunity_map import extract_solution_narrative_opportunity_map
from app.services.extractors.stakeholder_map import extract_stakeholder_map
from app.services.extractors.tech_landscape import extract_tech_landscape

logger = logging.getLogger(__name__)

SEED_FILES = [
    ("firmographics", "firmographics.csv", "1_Firmographics (Firmographics)"),
    ("company_hierarchy", "company_hierarchy.csv", "2_Company_Hierarchy (Corporate Hierarchy)"),
    ("technographics", "technographics.csv", "4_Technographics (Technographics)"),
    ("webstack", "webstack.csv", "5_Webstack (Web Technologies & Infrastructure)"),
    ("intent_topics", "intent_topics.csv", "10_Intent_Topics (Bombora Topics)"),
    ("intent_score", "intent_score.csv", "11_Intent_Score (Bombora Composite Surge)"),
    ("job_openings", "job_openings.csv", "Job Openings (Source B)"),
    ("news_events", "news_events.csv", "News Events (Source B Timeline)"),
    ("technology_detections", "technology_detections.csv", "Technology Detections (Source B)"),
    ("google_news", "google_news.csv", "Google News RSS Data"),
    ("prospect_contacts", "prospect_contacts.csv", "14_Prospect_Contacts (Target Decision Makers)")
]

def seed_database_if_empty():
    db = get_db()
    now = datetime.now(timezone.utc)
    
    # 1. Seed Default Users
    users_col = db["users"]
    
    admin_doc = users_col.find_one({"email": "admin@hp.com"})
    if not admin_doc:
        admin_doc = {
            "email": "admin@hp.com",
            "password_hash": get_password_hash("AdminPassword123!"),
            "role": "admin",
            "full_name": "HP Enterprise Admin",
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        users_col.insert_one(admin_doc)
        logger.info("Seeded default admin user: admin@hp.com")
    elif "password_hash" not in admin_doc:
        users_col.update_one(
            {"_id": admin_doc["_id"]},
            {"$set": {"password_hash": get_password_hash("AdminPassword123!")}}
        )

    user_doc = users_col.find_one({"email": "user@hp.com"})
    if not user_doc:
        user_doc = {
            "email": "user@hp.com",
            "password_hash": get_password_hash("UserPassword123!"),
            "role": "user",
            "full_name": "HP Sales Representative",
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        users_col.insert_one(user_doc)
        logger.info("Seeded default user: user@hp.com")
    elif "password_hash" not in user_doc:
        users_col.update_one(
            {"_id": user_doc["_id"]},
            {"$set": {"password_hash": get_password_hash("UserPassword123!")}}
        )

    # 2. Seed Benchmark Company Account
    accounts_col = db["accounts"]
    astra_doc = accounts_col.find_one({
        "$or": [
            {"name": {"$regex": "Astra", "$options": "i"}},
            {"domain": "astra.co.id"}
        ]
    })

    if not astra_doc:
        astra_doc = {
            "name": "PT Astra International Tbk",
            "domain": "astra.co.id",
            "industry": "Automotive & Industrial Conglomerate",
            "hq_location": "Jakarta, Indonesia",
            "employee_range": "100,000+",
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        res = accounts_col.insert_one(astra_doc)
        astra_id = str(res.inserted_id)
        logger.info(f"Created benchmark target account 'PT Astra International Tbk' (ID: {astra_id})")
    else:
        astra_id = str(astra_doc["_id"])

    # 3. Seed Dataset CSV Files
    data_files_col = db["account_data_files"]
    backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    seed_source_dir = os.path.join(backend_root, "seed_data", "astra")

    if os.path.exists(seed_source_dir):
        for d_key, filename, display_name in SEED_FILES:
            src_file_path = os.path.join(seed_source_dir, filename)
            if not os.path.exists(src_file_path):
                continue

            existing_file = data_files_col.find_one({
                "account_id": astra_id,
                "dataset_key": d_key,
                "status": "active"
            })

            dest_dir = os.path.join(backend_root, "data", "accounts", astra_id, d_key)
            os.makedirs(dest_dir, exist_ok=True)
            dest_file_path = os.path.join(dest_dir, filename)

            # Copy seed file to destination if missing
            if not os.path.exists(dest_file_path):
                shutil.copy2(src_file_path, dest_file_path)

            rel_file_path = os.path.join("data", "accounts", astra_id, d_key, filename).replace("\\", "/")

            file_size = os.path.getsize(dest_file_path)
            row_count = 0
            try:
                with open(dest_file_path, "r", encoding="utf-8-sig", errors="replace") as f:
                    row_count = max(0, sum(1 for _ in f) - 1)
            except Exception:
                row_count = 0

            if not existing_file:
                metadata = {
                    "account_id": astra_id,
                    "dataset_key": d_key,
                    "category": d_key,
                    "display_name": display_name,
                    "original_filename": filename,
                    "stored_filename": filename,
                    "file_path": rel_file_path,
                    "file_size": file_size,
                    "row_count": row_count,
                    "status": "active",
                    "uploaded_at": now,
                    "updated_at": now
                }
                data_files_col.insert_one(metadata)
                logger.info(f"Seeded active dataset '{d_key}' for account {astra_id}")

    # 4. Trigger Extractors to Pre-Populate Widgets
    try:
        extract_executive_dashboard(astra_id)
        extract_recent_news_signals(astra_id)
        extract_intent_demand_signals(astra_id)
        extract_solution_narrative_opportunity_map(astra_id)
        extract_stakeholder_map(astra_id)
        extract_tech_landscape(astra_id)
        logger.info(f"Successfully pre-extracted all 6 features for account {astra_id}")
    except Exception as e:
        logger.warning(f"Seeder extraction notice for account {astra_id}: {e}")
