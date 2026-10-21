import hashlib
import logging
import os
import shutil
from datetime import UTC, datetime

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

SEED_FILES = [
    ("firmographics", "firmographics.csv", "1_Firmographics (Firmographics)"),
    ("company_hierarchy", "company_hierarchy.csv", "2_Company_Hierarchy (Corporate Hierarchy)"),
    ("technographics", "technographics.csv", "4_Technographics (Technographics)"),
    ("webstack", "webstack.csv", "5_Webstack (Web Technologies & Infrastructure)"),
    ("intent_topics", "intent_topics.csv", "10_Intent_Topics (Bombora Topics)"),
    ("intent_score", "intent_score.csv", "11_Intent_Score (Bombora Composite Surge)"),
    ("hp_category_intent", "hp_category_intent.csv", "HP Category Intent (Intent Data - Wide)"),
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
    now = datetime.now(UTC)

    # Users are no longer seeded: a known default password on every fresh
    # database is an open door. Accounts are created by the super admin.

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
        logger.info("Created benchmark target account 'PT Astra International Tbk' (ID: %s)",
                    astra_id)
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
    logger.info("Using seed source directory: %s", seed_source_dir)

    if os.path.exists(seed_source_dir):
        for d_key, filename, display_name in SEED_FILES:
            src_file_path = os.path.join(seed_source_dir, filename)
            if not os.path.exists(src_file_path):
                continue

            # Seeded once, into a database that has never held this dataset
            # for Astra. Any record - active, replaced or deleted - means
            # someone has managed it since, and startup must leave it alone.
            #
            # This used to "refresh" the active record on every start: it
            # pointed file_path back at the pilot copy and rewrote its size,
            # row count and hash. Every deploy silently swapped an uploaded
            # file for the pilot one - on 21 Oct the #106 deploy put Astra's
            # 23 pilot contacts back over the client's 17 - and the changed
            # hash marked 13 sections stale, ready to rebuild from the wrong
            # contacts. A deleted dataset would likewise have come back.
            if data_files_col.find_one({"account_id": astra_id, "dataset_key": d_key},
                                       {"_id": 1}):
                continue

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
            content_sha256 = None
            if dest_file_path and os.path.exists(dest_file_path):
                with open(dest_file_path, "rb") as fh:
                    content_sha256 = hashlib.sha256(fh.read()).hexdigest()

            row_count = 0
            try:
                if dest_file_path and os.path.exists(dest_file_path):
                    with open(dest_file_path, encoding="utf-8-sig", errors="replace") as f:
                        row_count = max(0, sum(1 for _ in f) - 1)
            except Exception:
                row_count = 0

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
                "content_sha256": content_sha256,
                "status": "active",
                "uploaded_at": now,
                "updated_at": now
            }
            data_files_col.insert_one(metadata)
            logger.info("Seeded active dataset '%s' for account %s", d_key, astra_id)

    # 4. Nothing is generated here.
    #
    # This used to run every extractor with nothing stored, at startup, inside
    # the request-free boot path - model calls included. Generation now belongs
    # to the regeneration engine: the first page view of a feature, or the first
    # upload, queues it, and the background worker builds it. Startup only
    # registers the data.
