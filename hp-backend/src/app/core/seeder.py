import os
import csv
import shutil
import logging
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.security import get_password_hash

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

def _find_backend_root() -> str:
    """Resolve backend root where seed_data and data directories reside across Docker, local, and module contexts."""
    candidates = [
        os.getcwd(),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, "seed_data", "astra")):
            return c
    return os.getcwd()

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
            "full_name": "HP System Administrator",
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
            "full_name": "HP Enterprise Sales Representative",
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
            "status": "active",
            "is_active": True,
            "created_at": now,
            "updated_at": now
        }
        res = accounts_col.insert_one(astra_doc)
        astra_id = str(res.inserted_id)
        logger.info(f"Created benchmark target account 'PT Astra International Tbk' (ID: {astra_id})")
    else:
        astra_id = str(astra_doc["_id"])
        accounts_col.update_one(
            {"_id": astra_doc["_id"]},
            {"$set": {"status": "active", "is_active": True, "updated_at": now}}
        )

    # 3. Seed Dataset CSV Files
    data_files_col = db["account_data_files"]
    backend_root = _find_backend_root()
    seed_source_dir = os.path.join(backend_root, "seed_data", "astra")
    logger.info(f"Using seed source directory: {seed_source_dir}")

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

            # Create destination dirs in both backend_root and current working directory
            target_dirs = {
                os.path.join(backend_root, "data", "accounts", astra_id, d_key),
                os.path.join(os.getcwd(), "data", "accounts", astra_id, d_key)
            }

            dest_file_path = None
            for dest_dir in target_dirs:
                os.makedirs(dest_dir, exist_ok=True)
                dest_path = os.path.join(dest_dir, filename)
                if not dest_file_path:
                    dest_file_path = dest_path
                # Copy seed file to destination if missing or different size
                if not os.path.exists(dest_path) or os.path.getsize(dest_path) == 0:
                    shutil.copy2(src_file_path, dest_path)

            rel_file_path = os.path.join("data", "accounts", astra_id, d_key, filename).replace("\\", "/")

            file_size = os.path.getsize(dest_file_path) if dest_file_path and os.path.exists(dest_file_path) else 0
            row_count = 0
            try:
                if dest_file_path and os.path.exists(dest_file_path):
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
            else:
                # Ensure status is active and row_count/size are up to date
                data_files_col.update_one(
                    {"_id": existing_file["_id"]},
                    {"$set": {
                        "status": "active",
                        "file_path": rel_file_path,
                        "file_size": file_size,
                        "row_count": row_count,
                        "updated_at": now
                    }}
                )

    # 4. Trigger every extractor to pre-populate widgets.
    #
    # These used to be seven hand-written calls inside one try, so the first
    # failure silently skipped the rest, and objection_playbook,
    # content_messaging, content_studio and strategy_chat were never listed at
    # all - Objection Playbook was blank on every fresh clone. FEATURE_EXTRACTORS
    # is the same table the upload trigger and the read-path bootstrap use, so a
    # feature cannot be wired into one and missed by another.
    #
    # Imported here rather than at module scope: widgets.py pulls in the API
    # layer, which imports this module's package.
    from app.api.v1.widgets import FEATURE_EXTRACTORS

    # Only features with NOTHING stored are extracted here, which is what the
    # function name has always promised.
    #
    # Running every extractor on every startup meant each `--reload` rewrote all
    # the widgets: a file save restarted uvicorn, the seeder fired, and freshly
    # generated output was replaced by whatever the reloaded process produced.
    # On a shared cluster it is worse - any developer restarting overwrites
    # documents everyone else is looking at.
    #
    # Data changes are already covered: upload and delete re-run the dependent
    # features, the read path bootstraps a feature with nothing stored, and
    # POST /widgets/{feature}/regenerate forces one on demand.
    existing_features = set(
        db["account_widgets"].distinct("feature_key", {"account_id": astra_id}))

    succeeded, failed, skipped = [], [], []
    for feature_key, extractor in FEATURE_EXTRACTORS.items():
        if feature_key in existing_features:
            skipped.append(feature_key)
            continue
        try:
            extractor(astra_id)
            succeeded.append(feature_key)
        except Exception:
            failed.append(feature_key)
            logger.exception("Seeder: extractor for '%s' failed on account %s",
                             feature_key, astra_id)

    logger.info("Seeder: %d feature(s) extracted, %d already populated and left "
                "untouched, for account %s",
                len(succeeded), len(skipped), astra_id)
    if failed:
        logger.warning("Seeder: these features did not extract: %s", ", ".join(failed))
