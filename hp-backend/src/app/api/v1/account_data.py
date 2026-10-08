import csv
import hashlib
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
from app.core.deps import (
    get_current_user_flexible,
    require_admin_role,
    require_user_role,
    require_user_role_flexible,
)
from app.database.mongodb import get_db
from app.schemas.account_data import DATASET_REGISTRY, AccountDataFileResponse
from app.services.extractors.datasets import find_file_path
from app.services.hp import link_health

logger = logging.getLogger(__name__)
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
    """Kept as a name; the resolution itself belongs to `datasets`.

    This was a second, older copy of the same walk, and it was missing the
    four-level candidate that reaches the backend root where the datasets
    actually live - its walks stop at `src/`, so the only candidate that ever
    resolved was the working-directory one. `datasets.find_file_path` carries the
    fix and the `/app` candidate the container needs, and is the one every
    extractor already goes through. Two copies of this is how they drifted apart
    in the first place.
    """
    return find_file_path(rel_path)

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
    "content_studio": extract_content_studio,
    "strategy_chat": extract_strategy_chat,
    "message_evaluator": extract_message_evaluator,
}


def _notify_regeneration(account_id: str, dataset_key: str, what: str,
                         current_user: dict) -> dict:
    """Report which sections the change left stale. Runs and queues NOTHING.

    Uploading, replacing or deleting a file only stores it (29 Sep): an account
    uploaded file by file used to run its sections once per file. The admin
    submits the account when its files are in, and one run regenerates each
    stale section once. `queued` stays in the response, always empty, for
    callers that read it.

    Never raises: the file is stored either way.
    """
    try:
        from app.services.regen.engine import get_engine
        stale = get_engine().notify_input_changed(
            account_id, what, "user:%s" % (current_user or {}).get("id", "?"),
            datasets=[dataset_key])
    except Exception:
        logger.exception("could not work out what %s left stale", what)
        return {"queued": [], "stale": [], "features": []}
    nodes = [n["node_id"] for n in stale]
    return {"queued": [], "stale": nodes,
            "stale_sections": [{"node_id": n["node_id"], "label": n["label"],
                                "status": n["status"], "categories": n["categories"]}
                               for n in stale],
            "features": sorted({n["feature"] for n in stale}),
            "note": "Stored. Nothing runs until the account is submitted."}


def _features_for_dataset(dataset_key: str) -> list[str]:
    """Features that declare this dataset as a dependency, in registry order."""
    return [
        fk for fk, spec in FEATURE_MAPPINGS.items()
        if dataset_key in (spec.get("dependent_datasets") or [])
        and fk in FEATURE_EXTRACTORS
    ]


@router.post("", response_model=AccountDataFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_account_data(
    account_id: str,
    dataset_key: str = Form(...),
    file_id_to_replace: str | None = Form(None),
    # Bulk loading, one account at a time: a feature that declares seven
    # datasets is otherwise re-run seven times as they arrive, six of them
    # against data that is still incomplete. The loader sets this on every
    # upload and then regenerates each feature once, at the end, which is both
    # cheaper and the only way the first run sees the whole account.
    # Default false, so a single upload from the UI behaves exactly as before.
    defer_extraction: bool = Form(False),
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
    # The dataset's version is built from these hashes, so re-uploading
    # identical bytes changes nothing downstream.
    content_sha256 = hashlib.sha256(content).hexdigest()
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

    # Every stored file is immutable: a new upload never overwrites the bytes an
    # existing row points at. A regeneration run pins the file rows it starts
    # from, and a row whose file changed underneath it would make the output
    # disagree with the fingerprint it is committed under. Single-file datasets
    # are content-addressed; multi-file ones get a fresh name even when they
    # replace a specific file.
    if dataset_info["type"] == "single_file_csv":
        stored_filename = f"{content_sha256[:12]}_{dataset_info['canonical_filename']}"
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
        "content_sha256": content_sha256,
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

    payload = serialize_data_file(new_metadata)
    if defer_extraction:
        # Kept for the bulk loader, which sets it: every upload is deferred now,
        # and this only skips working out what became stale.
        payload["regeneration"] = {"queued": [], "stale": [], "features": [],
                                   "deferred": True}
    else:
        payload["regeneration"] = _notify_regeneration(
            account_id, key_clean, "dataset %s uploaded" % key_clean, current_user)
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
    # Files are content-addressed, so an identical re-upload shares this path
    # with another row. Only remove the bytes when no other live row uses them.
    shared = rel_path and db["account_data_files"].count_documents({
        "file_path": rel_path, "_id": {"$ne": file_doc["_id"]},
        "status": {"$in": ["active", "replaced"]}})
    if rel_path and not shared:
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

    return {
        "status": "success",
        "message": f"File '{file_doc.get('original_filename')}' deleted successfully.",
        "regeneration": _notify_regeneration(
            account_id, dataset_key, "dataset %s deleted" % dataset_key, current_user),
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
    elif ext == ".pdf":
        # A filing served as text/csv downloads as garbage. compliance_filings
        # is mostly PDFs, so this route could never open one.
        media_type = "application/pdf"

    return FileResponse(
        path=full_path,
        media_type=media_type,
        filename=filename,
        headers={"Content-Disposition": f"inline; filename=\"{filename}\""}
    )


# The one dataset whose individual files may be opened in a browser, and the one
# extension allowed out of it.
#
# Deliberately a pinned constant rather than a parameter. The other datasets hold
# the client's own records - prospect_contacts carries names, emails and phone
# numbers - and this route's whole purpose is to be reachable from a plain link,
# so widening it would turn an evidence chip into a way to pull contact data.
# Filings are public company documents; a seller opening one is reading what the
# company itself published.
VIEWABLE_DATASET = "compliance_filings"
VIEWABLE_EXTENSION = ".pdf"


def _viewable_filings(db, account_id: str) -> dict:
    """{original_filename: row}, the filings of this account that can be opened.

    One query, one ordering rule, used by both routes below - so the manifest can
    never advertise a filing the document route would refuse, and the two can
    never disagree about which of two same-named rows is current.

    `compliance_filings` is a multi-file dataset, so two active rows can share an
    `original_filename`. `dataset_file_paths` returns them `sorted()`, so the
    corpus read the lexicographically first path and the evidence quotes come
    from that file; ascending `file_path` reproduces that, and `setdefault` keeps
    the first.
    """
    # `.sort()` on the cursor rather than a `sort=` kwarg: that is the pymongo
    # cursor API and it is what the test double implements too.
    rows = db["account_data_files"].find(
        {"account_id": account_id,
         "dataset_key": VIEWABLE_DATASET,
         "status": "active"},
    ).sort([("file_path", 1)])
    out: dict = {}
    for row in rows:
        name = str(row.get("original_filename") or "")
        if name.lower().endswith(VIEWABLE_EXTENSION):
            out.setdefault(name, row)
    return out


@router.get("/filings")
def list_account_filings(
    account_id: str,
    current_user: dict = Depends(require_user_role),
):
    """Which filings this account has an openable copy of.

    The frontend links evidence to a filing by its `filing_label`, and that label
    is true of the corpus at the time the widget was built - not necessarily now.
    A filing that has since been re-uploaded leaves its old row `replaced`, and a
    filing can be registered on an account whose PDF is not on this machine; in
    both cases the document route correctly refuses, and a chip that had linked
    optimistically would open a tab containing a 404.

    A dead link is worse than plain text, which is the rule `caseStudies.ts`
    already applies to HP's retired case studies. So the UI is told the set it may
    link, and anything outside it falls back to the filing's public URL, or to
    plain text. That is what keeps "where we have it we show it, where we do not
    we say nothing" true for this feature.

    Filenames and page counts only - no paths, no URLs, no bytes. Read with the
    ordinary Bearer header, so unlike the document route no token appears in a
    URL.
    """
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid account ID format")

    db = get_db()
    if not db["accounts"].find_one({"_id": ObjectId(account_id)}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Company account not found")

    filings = []
    for name, row in _viewable_filings(db, account_id).items():
        if not find_file_path(row.get("file_path", "")):
            # Registered but not on this machine. Advertising it would promise a
            # link that 404s, which is the whole thing this route prevents.
            continue
        # `row_count` is the page count for a PDF, so the UI can tell whether a
        # cited page is really in the document.
        pages = row.get("row_count")
        filings.append({"filename": name,
                        "pages": int(pages) if isinstance(pages, int) else None})

    # An account with no filings answers with an empty list. That is an answer,
    # not an error - most accounts have none.
    return {"filings": sorted(filings, key=lambda f: f["filename"])}


@router.get("/unreachable-links")
def list_unreachable_links(
    account_id: str,
    current_user: dict = Depends(require_user_role),
):
    """This account's evidence links that are known not to open.

    The dashboard shows a source only when it has a link that opens (client,
    7 Oct), so it hides these. Verdicts come from
    `scripts/check_evidence_links.py`; see `services.hp.link_health` for what
    counts as dead. A link that has never been checked is not listed.

    URLs that already appear in this account's own widgets - nothing the
    dashboard could not already read.
    """
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid account ID format")

    db = get_db()
    if not db["accounts"].find_one({"_id": ObjectId(account_id)}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Company account not found")
    return {"unreachable": link_health.unreachable(db, account_id)}


@router.get("/filing")
def view_account_filing(
    account_id: str,
    name: str,
    current_user: dict = Depends(require_user_role_flexible),
):
    """One of this account's filing PDFs, inline, addressed by its own filename.

    The client, 6 Oct: evidence sources must be clickable. A catalyst's evidence
    reads "australia_post_2024-FY_annual_report.pdf p.11", and the public URL for
    that document is unreliable - of 481 filing URLs the crawl attempted, 116
    failed or returned something that was not a document. The copy we hold always
    opens, and a browser will jump straight to the cited page from the `#page=`
    fragment the link carries.

    `name` is the registered `original_filename`, which is exactly the
    `filing_label` already on every evidence row - so a link can be built from a
    stored widget with no rebuild.

    **`name` never becomes part of a path.** It is used only as an equality match
    against `account_data_files`, and the file served is the matched row's own
    `file_path`. So "../../etc/passwd" matches no row and 404s; there is no
    traversal to defend against because no path is ever assembled from input.
    This is why the lookup is by name rather than by a sanitised path.

    `download/{dataset_key}` cannot do this job: compliance_filings is a
    multi-file dataset, so its `find_one` returns an arbitrary one of several
    active rows.
    """
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid account ID format")

    wanted = (name or "").strip()
    if not wanted or not wanted.lower().endswith(VIEWABLE_EXTENSION):
        # Covers `_filings_index.csv`, which is uploaded into this same dataset.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such filing for this account.")

    db = get_db()
    if not db["accounts"].find_one({"_id": ObjectId(account_id)}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Company account not found")

    # The same resolver the manifest uses, so the two can never disagree about
    # which filing is openable or about which of two same-named rows is current.
    file_doc = _viewable_filings(db, account_id).get(wanted)
    if not file_doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such filing for this account.")

    full_path = find_file_path(file_doc.get("file_path", ""))
    if not full_path or not os.path.exists(full_path):
        # Registered but not on this machine - the ordinary state of a developer
        # checkout. Says nothing about where it was expected.
        logger.info("filing view: %s is registered for %s but not on this machine",
                    wanted, account_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="That filing is not available on this server.")

    return FileResponse(
        path=full_path,
        media_type="application/pdf",
        filename=file_doc.get("original_filename") or wanted,
        # Inline, so the browser renders it and honours `#page=`. Set through
        # Starlette's own parameter rather than a hand-written header, which
        # would be emitted alongside the one `filename=` already produces.
        content_disposition_type="inline",
        # The stored bytes are immutable - a new upload writes a new row and a
        # new file, never over these. `private` because the link carries a token.
        headers={"Cache-Control": "private, max-age=3600"},
    )
