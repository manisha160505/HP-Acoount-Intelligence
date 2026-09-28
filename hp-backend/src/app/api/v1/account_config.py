import logging
from datetime import UTC, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import require_admin_role
from app.database.mongodb import get_db
from app.schemas.account_config import (
    AccountGuardrailsResponse,
    AccountGuardrailsUpdate,
    AccountInstructionsResponse,
    AccountInstructionsUpdate,
)

router = APIRouter(prefix="/accounts/{account_id}", tags=["Account Configuration (Admin Only)"])

logger = logging.getLogger(__name__)

def _notify_regeneration(account_id: str, what: str, current_user: dict) -> None:
    """Instructions and guardrails reach the Opportunity Map's prompt, so an edit
    makes it stale. Queued, never run here; never fails the save."""
    try:
        from app.services.regen.engine import get_engine
        from app.services.regen.graph import DEFAULT
        get_engine().notify_input_changed(
            account_id, what, "user:%s" % (current_user or {}).get("id", "?"),
            nodes=[n for n, node in DEFAULT.nodes.items() if node.account_config])
    except Exception:
        logger.exception("could not queue regeneration after %s", what)

@router.get("/instructions", response_model=AccountInstructionsResponse)
def get_instructions(
    account_id: str,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    doc = db["account_instructions"].find_one({"account_id": account_id})
    if not doc:
        now_str = datetime.now(UTC).isoformat()
        return {
            "account_id": account_id,
            "instructions_text": "",
            "updated_at": now_str
        }

    updated_at_val = doc.get("updated_at")
    updated_at_str = updated_at_val.isoformat() if isinstance(updated_at_val, datetime) else str(updated_at_val or "")

    return {
        "account_id": account_id,
        "instructions_text": doc.get("instructions_text", ""),
        "updated_at": updated_at_str
    }

@router.put("/instructions", response_model=AccountInstructionsResponse)
def update_instructions(
    account_id: str,
    payload: AccountInstructionsUpdate,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    now = datetime.now(UTC)
    db["account_instructions"].update_one(
        {"account_id": account_id},
        {
            "$set": {
                "account_id": account_id,
                "instructions_text": payload.instructions_text,
                "updated_at": now
            }
        },
        upsert=True
    )

    db["accounts"].update_one(
        {"_id": ObjectId(account_id)},
        {"$set": {"updated_at": now}}
    )
    _notify_regeneration(account_id, "account instructions edited", current_user)

    return {
        "account_id": account_id,
        "instructions_text": payload.instructions_text,
        "updated_at": now.isoformat()
    }

@router.get("/guardrails", response_model=AccountGuardrailsResponse)
def get_guardrails(
    account_id: str,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    doc = db["account_guardrails"].find_one({"account_id": account_id})
    if not doc:
        now_str = datetime.now(UTC).isoformat()
        return {
            "account_id": account_id,
            "enabled": False,
            "guardrails_text": "",
            "updated_at": now_str
        }

    updated_at_val = doc.get("updated_at")
    updated_at_str = updated_at_val.isoformat() if isinstance(updated_at_val, datetime) else str(updated_at_val or "")

    return {
        "account_id": account_id,
        "enabled": doc.get("enabled", False),
        "guardrails_text": doc.get("guardrails_text", ""),
        "updated_at": updated_at_str
    }

@router.put("/guardrails", response_model=AccountGuardrailsResponse)
def update_guardrails(
    account_id: str,
    payload: AccountGuardrailsUpdate,
    current_user: dict = Depends(require_admin_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    now = datetime.now(UTC)
    db["account_guardrails"].update_one(
        {"account_id": account_id},
        {
            "$set": {
                "account_id": account_id,
                "enabled": payload.enabled,
                "guardrails_text": payload.guardrails_text,
                "updated_at": now
            }
        },
        upsert=True
    )

    db["accounts"].update_one(
        {"_id": ObjectId(account_id)},
        {"$set": {"updated_at": now}}
    )
    _notify_regeneration(account_id, "account guardrails edited", current_user)

    return {
        "account_id": account_id,
        "enabled": payload.enabled,
        "guardrails_text": payload.guardrails_text,
        "updated_at": now.isoformat()
    }
