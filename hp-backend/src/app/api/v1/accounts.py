from datetime import datetime, timezone
import re
from fastapi import APIRouter, Depends, HTTPException, Query, status
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.deps import require_admin_role, require_user_role
from app.schemas.account import AccountCreate, AccountStatusUpdate, AccountResponse

router = APIRouter(prefix="/accounts", tags=["Account Management"])

def serialize_account(doc: dict) -> dict:
    return {
        "id": str(doc["_id"]),
        "name": doc["name"],
        "status": doc.get("status", "active"),
        "created_at": doc["created_at"].isoformat() if isinstance(doc.get("created_at"), datetime) else str(doc.get("created_at", "")),
        "updated_at": doc["updated_at"].isoformat() if isinstance(doc.get("updated_at"), datetime) else str(doc.get("updated_at", ""))
    }

@router.get("/user-list", response_model=list[AccountResponse])
def list_active_accounts_for_user(
    current_user: dict = Depends(require_user_role)
):
    db = get_db()
    cursor = db["accounts"].find({"status": "active"}).sort("name", 1)
    return [serialize_account(doc) for doc in cursor]

@router.get("", response_model=list[AccountResponse])
def list_accounts(
    search: str | None = Query(None, description="Search accounts by company name"),
    current_user: dict = Depends(require_admin_role)
):
    db = get_db()
    query = {}
    if search and search.strip():
        regex_pattern = re.escape(search.strip())
        query["name"] = {"$regex": regex_pattern, "$options": "i"}
    
    cursor = db["accounts"].find(query).sort("updated_at", -1)
    return [serialize_account(doc) for doc in cursor]

@router.post("", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
def create_account(
    account_in: AccountCreate,
    current_user: dict = Depends(require_admin_role)
):
    db = get_db()
    account_name = account_in.name.strip()
    
    # Check for duplicate name (case-insensitive)
    existing = db["accounts"].find_one({"name": {"$regex": f"^{re.escape(account_name)}$", "$options": "i"}})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with the name '{account_name}' already exists."
        )
    
    now = datetime.now(timezone.utc)
    new_doc = {
        "name": account_name,
        "status": "active",
        "created_at": now,
        "updated_at": now
    }
    
    result = db["accounts"].insert_one(new_doc)
    new_doc["_id"] = result.inserted_id
    
    return serialize_account(new_doc)

@router.get("/{account_id}", response_model=AccountResponse)
def get_account(
    account_id: str,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")
    
    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    return serialize_account(account)

@router.patch("/{account_id}", response_model=AccountResponse)
def update_account(
    account_id: str,
    account_in: AccountCreate,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")
    
    db = get_db()
    account_name = account_in.name.strip()
    
    # Check duplicate if name is changing
    existing = db["accounts"].find_one({
        "_id": {"$ne": ObjectId(account_id)},
        "name": {"$regex": f"^{re.escape(account_name)}$", "$options": "i"}
    })
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An account with the name '{account_name}' already exists."
        )
    
    now = datetime.now(timezone.utc)
    updated = db["accounts"].find_one_and_update(
        {"_id": ObjectId(account_id)},
        {"$set": {"name": account_name, "updated_at": now}},
        return_document=True
    )
    
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    return serialize_account(updated)

@router.patch("/{account_id}/status", response_model=AccountResponse)
def update_account_status(
    account_id: str,
    status_in: AccountStatusUpdate,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")
    
    db = get_db()
    now = datetime.now(timezone.utc)
    updated = db["accounts"].find_one_and_update(
        {"_id": ObjectId(account_id)},
        {"$set": {"status": status_in.status, "updated_at": now}},
        return_document=True
    )
    
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    
    return serialize_account(updated)
