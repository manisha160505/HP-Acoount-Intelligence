import os
import io
import csv
import time
import re
import pandas as pd
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.deps import require_admin_role, require_user_role, get_current_user_flexible
from app.config.settings import settings
from app.schemas.account_data import DATASET_REGISTRY, AccountDataFileResponse
from app.services.extractors.executive_dashboard import extract_executive_dashboard
from app.services.extractors.recent_news_signals import extract_recent_news_signals
from app.services.extractors.intent_demand_signals import extract_intent_demand_signals
from app.services.extractors.solution_narrative_opportunity_map import extract_solution_narrative_opportunity_map
from app.services.extractors.stakeholder_map import extract_stakeholder_map
from app.services.extractors.tech_landscape import extract_tech_landscape
from app.services.extractors.objection_playbook import extract_objection_playbook
from app.services.extractors.content_messaging import extract_content_messaging
from app.services.extractors.content_studio import extract_content_studio
from app.services.extractors.strategy_chat import extract_strategy_chat

router = APIRouter(prefix="/accounts/{account_id}/data", tags=["Raw Data Management (Admin Only)"])

def serialize_data_file(doc: dict) -> dict:
    dataset_key = doc.get("dataset_key") or doc.get("category", "")
    registry_item = DATASET_REGISTRY.get(dataset_key, {})
    display_name = doc.get("display_name") or registry_item.get("display_name", dataset_key)
    
    return {
        "id": str(doc["_id"]),
        "account_id": doc["account_id"],
        "dataset_key": dataset_key,
        "display_name": display_name,
        "original_filename": doc["original_filename"],
        "stored_filename": doc["stored_filename"],
        "file_path": doc["file_path"],
        "file_size": doc.get("file_size", 0),
        "row_count": doc.get("row_count", 0),
        "status": doc.get("status", "active"),
        "uploaded_at": doc["uploaded_at"].isoformat() if isinstance(doc.get("uploaded_at"), datetime) else str(doc.get("uploaded_at", "")),
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else str(doc.get("updated_at", ""))
    }

def sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r'[^a border-zA-Z0-9_\.-]', '_', filename)
    return cleaned if cleaned else "dataset_file"

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

@router.post("", response_model=AccountDataFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_account_data(
    account_id: str,
    dataset_key: str = Form(...),
    file_id_to_replace: str | None = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(require_admin_role)
):
    # 1. Validate Account ID
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")
    
    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    # 2. Validate Dataset Key
    key_clean = dataset_key.strip().lower()
    if key_clean not in DATASET_REGISTRY:
        allowed_keys = ", ".join(DATASET_REGISTRY.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid dataset_key '{dataset_key}'. Must be one of: {allowed_keys}"
        )

    dataset_info = DATASET_REGISTRY[key_clean]
    allowed_exts = dataset_info["allowed_extensions"]

    # 3. Validate File Extension
    original_filename = file.filename or "uploaded_file"
    file_ext = os.path.splitext(original_filename)[1].lower()
    
    if file_ext not in allowed_exts:
        exts_str = ", ".join(allowed_exts)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{file_ext}' for dataset '{dataset_info['display_name']}'. Allowed formats: {exts_str}"
        )

    # 4. Read File Content & Check non-empty
    content = await file.read()
    file_size = len(content)
    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty (0 bytes). Please upload a valid data file."
        )

    # 5. Parse Content & Count Rows
    row_count = 0
    try:
        if file_ext in [".xlsx", ".xls"]:
            df = pd.read_excel(io.BytesIO(content))
            row_count = len(df)
        else:
            text_content = content.decode("utf-8-sig", errors="replace")
            csv_io = io.StringIO(text_content)
            reader = list(csv.reader(csv_io))
            if len(reader) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV file contains no readable content."
                )
            row_count = max(0, len(reader) - 1)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error reading file structure: {str(e)}"
        )

    # 6. Storage Path & Filename Determination
    dataset_dir = os.path.join(settings.DATA_STORAGE_DIR, account_id, key_clean)
    os.makedirs(dataset_dir, exist_ok=True)

    if dataset_info["type"] == "single_file_csv":
        stored_filename = dataset_info["canonical_filename"]
    else:
        # Multi-file News Datasets
        if file_id_to_replace and ObjectId.is_valid(file_id_to_replace):
            old_doc = db["account_data_files"].find_one({"_id": ObjectId(file_id_to_replace)})
            if old_doc and old_doc.get("stored_filename"):
                stored_filename = old_doc["stored_filename"]
            else:
                timestamp = int(time.time())
                sanitized_name = sanitize_filename(os.path.splitext(original_filename)[0])
                stored_filename = f"{key_clean}_{timestamp}_{sanitized_name}{file_ext}"
        else:
            timestamp = int(time.time())
            sanitized_name = sanitize_filename(os.path.splitext(original_filename)[0])
            stored_filename = f"{key_clean}_{timestamp}_{sanitized_name}{file_ext}"

    relative_file_path = os.path.join("data", "accounts", account_id, key_clean, stored_filename).replace("\\", "/")
    absolute_file_path = os.path.join(dataset_dir, stored_filename)

    # Write file to disk
    with open(absolute_file_path, "wb") as f:
        f.write(content)

    now = datetime.now(timezone.utc)

    # 7. Metadata Persistence in MongoDB
    if dataset_info["type"] == "single_file_csv":
        # Single-file datasets: mark previous active record as replaced
        db["account_data_files"].update_many(
            {"account_id": account_id, "dataset_key": key_clean, "status": "active"},
            {"$set": {"status": "replaced", "updated_at": now}}
        )
    elif file_id_to_replace and ObjectId.is_valid(file_id_to_replace):
        # Specific file replacement in multi-file news
        db["account_data_files"].update_one(
            {"_id": ObjectId(file_id_to_replace)},
            {"$set": {"status": "replaced", "updated_at": now}}
        )

    new_metadata = {
        "account_id": account_id,
        "dataset_key": key_clean,
        "category": key_clean,
        "display_name": dataset_info["display_name"],
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "file_path": relative_file_path,
        "file_size": file_size,
        "row_count": row_count,
        "status": "active",
        "uploaded_at": now,
        "updated_at": now
    }

    res = db["account_data_files"].insert_one(new_metadata)
    new_metadata["_id"] = res.inserted_id

    # Touch account updated_at
    db["accounts"].update_one(
        {"_id": ObjectId(account_id)},
        {"$set": {"updated_at": now}}
    )

    # Trigger selective re-extraction for dependent widgets
    if key_clean in ["firmographics", "company_hierarchy", "job_openings"]:
        try:
            extract_executive_dashboard(account_id)
        except Exception:
            pass
    if key_clean in ["google_news", "news_events"]:
        try:
            extract_recent_news_signals(account_id)
        except Exception:
            pass
    if key_clean in ["intent_score", "intent_topics", "job_openings"]:
        try:
            extract_intent_demand_signals(account_id)
        except Exception:
            pass
    if key_clean in ["firmographics", "technographics", "intent_score", "google_news", "news_events"]:
        try:
            extract_solution_narrative_opportunity_map(account_id)
        except Exception:
            pass
    if key_clean in ["prospect_contacts"]:
        try:
            extract_stakeholder_map(account_id)
        except Exception:
            pass
    if key_clean in ["technographics", "technology_detections", "webstack"]:
        try:
            extract_tech_landscape(account_id)
        except Exception:
            pass
    if key_clean in ["firmographics", "technographics", "intent_score", "google_news", "news_events"]:
        try:
            extract_content_messaging(account_id)
        except Exception:
            pass
    if key_clean in ["prospect_contacts", "job_openings", "firmographics", "google_news", "news_events"]:
        try:
            extract_content_studio(account_id)
        except Exception:
            pass
    if key_clean in ["firmographics", "company_hierarchy", "technographics", "webstack", "job_openings", "google_news", "news_events", "intent_score", "technology_detections", "prospect_contacts"]:
        try:
            extract_strategy_chat(account_id)
        except Exception:
            pass

    return serialize_data_file(new_metadata)

@router.get("", response_model=list[AccountDataFileResponse])
def get_account_data_files(
    account_id: str,
    status_filter: str = "active",
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    query = {"account_id": account_id}
    if status_filter:
        query["status"] = status_filter

    cursor = db["account_data_files"].find(query).sort("uploaded_at", -1)
    return [serialize_data_file(doc) for doc in cursor]

@router.delete("/{file_id}")
def delete_account_data_file(
    account_id: str,
    file_id: str,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id) or not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account or file ID format")

    db = get_db()
    file_doc = db["account_data_files"].find_one({"_id": ObjectId(file_id), "account_id": account_id})
    if not file_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data file record not found")

    # Delete physical file if exists
    rel_path = file_doc.get("file_path", "")
    if rel_path:
        full_path = _find_file_path(rel_path)
        if full_path and os.path.exists(full_path):
            try:
                os.remove(full_path)
            except Exception:
                pass

    now = datetime.now(timezone.utc)
    db["account_data_files"].update_one(
        {"_id": ObjectId(file_id)},
        {"$set": {"status": "deleted", "updated_at": now}}
    )

    db["accounts"].update_one(
        {"_id": ObjectId(account_id)},
        {"$set": {"updated_at": now}}
    )

    return {"status": "success", "message": f"File '{file_doc.get('original_filename')}' deleted successfully."}

@router.get("/download/{dataset_key}")
def download_account_data_file(
    account_id: str,
    dataset_key: str,
    current_user: dict = Depends(get_current_user_flexible)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    key_clean = dataset_key.strip().lower()
    file_doc = db["account_data_files"].find_one({
        "account_id": account_id,
        "$or": [{"dataset_key": key_clean}, {"category": key_clean}],
        "status": "active"
    })

    if not file_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active data file found for dataset '{dataset_key}' in this account."
        )

    rel_path = file_doc.get("file_path", "")
    full_path = _find_file_path(rel_path)

    if not full_path or not os.path.exists(full_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File record exists in database but physical file is missing from server disk."
        )

    filename = file_doc.get("original_filename") or file_doc.get("stored_filename", "data.csv")
    ext = os.path.splitext(filename)[1].lower()
    media_type = "text/csv"
    if ext in [".xlsx", ".xls"]:
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    return FileResponse(
        path=full_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""}
    )
