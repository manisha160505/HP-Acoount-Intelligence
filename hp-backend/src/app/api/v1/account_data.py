import csv
import io
import logging
import os
import re
import time
from datetime import UTC, datetime

import pandas as pd
from bson import ObjectId
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.api.v1.feature_mapping import FEATURE_MAPPINGS
from app.config.settings import settings
from app.core.deps import get_current_user_flexible, require_admin_role
from app.database.mongodb import get_db
from app.errors import ErrorCode
from app.observability import pipeline
from app.schemas.account_data import DATASET_REGISTRY, AccountDataFileResponse

logger = logging.getLogger(__name__)
from app.services.extractors.content_messaging import extract_content_messaging
from app.services.extractors.content_studio import extract_content_studio
from app.services.extractors.executive_dashboard import extract_executive_dashboard
from app.services.extractors.intent_demand_signals import extract_intent_demand_signals
from app.services.extractors.message_evaluator import extract_message_evaluator
from app.services.extractors.objection_playbook import extract_objection_playbook
from app.services.extractors.recent_news_signals import extract_recent_news_signals
from app.services.extractors.solution_narrative_opportunity_map import (
    extract_solution_narrative_opportunity_map,
)
from app.services.extractors.stakeholder_map import extract_stakeholder_map
from app.services.extractors.strategy_chat import extract_strategy_chat
from app.services.extractors.tech_landscape import extract_tech_landscape

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
    """Make a basename safe to write to disk.

    The character class had a stray "border-" in it, which is why stored names
    came out mangled: "My Report 2026" -> "My Re_ort 2026". As written it read as
    the literals a/space/b/o/r/d/e plus the range r-z, so the twelve lowercase
    letters outside that range (c f g h i j k l m n p q) were each replaced with
    an underscore while spaces were let through.

    Only the stored filename was affected. The extension is appended separately
    by the caller and `original_filename` is kept in the metadata, so no file
    became unreadable and nothing needs re-uploading.
    """
    cleaned = re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)
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

# feature_key -> extractor. Which datasets each one depends on is read from
# FEATURE_MAPPINGS rather than repeated here.
FEATURE_EXTRACTORS = {
    "executive_dashboard": extract_executive_dashboard,
    "recent_news_signals": extract_recent_news_signals,
    "intent_demand_signals": extract_intent_demand_signals,
    "solution_narrative_opportunity_map": extract_solution_narrative_opportunity_map,
    "stakeholder_map": extract_stakeholder_map,
    "tech_landscape": extract_tech_landscape,
    "objection_playbook": extract_objection_playbook,
    "content_messaging": extract_content_messaging,
    "content_studio": extract_content_studio,
    "strategy_chat": extract_strategy_chat,
    "message_evaluator": extract_message_evaluator,
}


def _features_for_dataset(dataset_key: str) -> list[str]:
    """Features that declare this dataset as a dependency, in registry order."""
    return [
        fk for fk, spec in FEATURE_MAPPINGS.items()
        if dataset_key in (spec.get("dependent_datasets") or [])
        and fk in FEATURE_EXTRACTORS
    ]


def _run_dependent_extractors(account_id: str, dataset_key: str) -> tuple[list, list]:
    """Re-run every feature that depends on this dataset.

    Returns (regenerated, failed). A failure never blocks the upload - the file
    is stored either way - but it is logged and returned rather than swallowed,
    which is how a broken regeneration used to pass as a 201.
    """
    regenerated, failed = [], []
    features = _features_for_dataset(dataset_key)
    # What this upload is about to set off. Without it a dataset landing looks
    # identical whether it triggered eight features or none.
    pipeline.step("upload", "%s -> %d feature(s): %s"
                  % (dataset_key, len(features), ", ".join(features) or "none"))
    for feature_key in features:
        try:
            FEATURE_EXTRACTORS[feature_key](account_id)
            regenerated.append(feature_key)
        except Exception as exc:
            logger.warning("re-extraction failed for %s after %s changed: %s",
                           feature_key, dataset_key, exc, exc_info=True)
            # The exception text is in the log line above with the traceback.
            # What reaches the UI is the feature name and a stable reason: an
            # extractor's internal message ("KeyError: 'revenue_usd'") tells a
            # seller nothing and can carry row data from the source file.
            failed.append({
                "feature": feature_key,
                "error": "This feature could not be rebuilt from the new data.",
                "code": ErrorCode.EXTRACTION_FAILED.value,
            })

    _queue_retrieval_updates(account_id, dataset_key, regenerated)
    return regenerated, failed


def _queue_retrieval_updates(account_id: str, dataset_key: str, regenerated: list):
    """Queue an index update once the whole regeneration batch has finished.

    Here rather than inside the loop above: one dataset change re-runs several
    extractors, and enqueueing per extractor would ask for the same index
    several times. The queue coalesces anyway, but asking once is the point of
    doing it after the batch - that is the debounce.

    Queued, never run inline. A retrieval build takes minutes and an LLM call
    per chunk; an upload must not wait on it, and an index that fails to build
    must not fail the upload.
    """
    from app.services.retrieval import registry
    from app.services.retrieval.ingest import request_update, requeue_dependents

    # Two reasons an index is behind, and they are not the same reason.
    #
    # A dataset it reads directly changed - that is this loop, matched on
    # `datasets`. Or a widget it reads was republished by one of the extractors
    # that just ran - that is `requeue_dependents` below, which resolves widget
    # -> index through the registry. Both paths now share that one mapping with
    # the `/regenerate` endpoint and with `_run_generator`, so a widget added to
    # a registry entry becomes visible to all three at once.
    for index, spec in registry.INDEX_REGISTRY.items():
        if not spec.get("enabled"):
            continue
        if dataset_key not in (spec.get("datasets") or []):
            continue
        try:
            request_update(account_id, index,
                           reason="%s changed" % dataset_key)
        except Exception:
            logger.exception("could not queue a retrieval update for %s", index)

    requeue_dependents(account_id, _widgets_of(regenerated),
                       reason="%s changed" % dataset_key)


def _widgets_of(features) -> list:
    """Every widget key the given features publish."""
    from app.api.v1.widgets import WIDGET_REGISTRY

    return [c["widget_key"] for feature in (features or [])
            for c in WIDGET_REGISTRY.get(feature, []) if c.get("widget_key")]


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
        if file_ext == ".pdf":
            # A filing has pages, not rows. Counting them here doubles as the
            # validity check the CSV branch gets from parsing: a file PyMuPDF
            # cannot open is rejected at upload rather than surfacing later as
            # an index that built from nothing.
            import fitz
            with fitz.open(stream=content, filetype="pdf") as pdf_doc:
                row_count = pdf_doc.page_count
            if row_count == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="PDF contains no pages."
                )
        elif file_ext in [".xlsx", ".xls"]:
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
            detail=f"Error reading file structure: {e!s}"
        ) from e

    # 6. Storage Path & Filename Determination
    dataset_dir = os.path.join(settings.DATA_STORAGE_DIR, account_id, key_clean)
    os.makedirs(dataset_dir, exist_ok=True)

    if dataset_info["type"] == "single_file_csv":
        stored_filename = dataset_info["canonical_filename"]
    # Multi-file News Datasets
    elif file_id_to_replace and ObjectId.is_valid(file_id_to_replace):
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

    now = datetime.now(UTC)

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

    # Regenerate every feature that declares this dataset as a dependency. The
    # table is derived from FEATURE_MAPPINGS, so a feature that gains a dataset
    # cannot silently fall out of the trigger set the way two of them had.
    regenerated, failed = _run_dependent_extractors(account_id, key_clean)

    payload = serialize_data_file(new_metadata)
    payload["regenerated"] = regenerated
    payload["regeneration_failed"] = failed
    return payload

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
            except OSError:
                # The record below is still marked deleted, so the file is now
                # orphaned on disk with nothing pointing at it. Logged rather
                # than swallowed: silently leaking files is how a data volume
                # fills up with no trace of why. Not raised - the user asked
                # for the record to go, and a stuck file should not fail that.
                logger.warning(
                    "Could not delete the file behind data file %s; the record is "
                    "marked deleted but %s remains on disk.",
                    file_id, full_path, exc_info=True,
                )

    now = datetime.now(UTC)
    db["account_data_files"].update_one(
        {"_id": ObjectId(file_id)},
        {"$set": {"status": "deleted", "updated_at": now}}
    )

    db["accounts"].update_one(
        {"_id": ObjectId(account_id)},
        {"$set": {"updated_at": now}}
    )

    # A widget must stop presenting data derived from a file that is gone.
    dataset_key = str(file_doc.get("dataset_key") or file_doc.get("category") or "").strip().lower()
    regenerated, failed = _run_dependent_extractors(account_id, dataset_key)

    return {
        "status": "success",
        "message": f"File '{file_doc.get('original_filename')}' deleted successfully.",
        "regenerated": regenerated,
        "regeneration_failed": failed,
    }

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
