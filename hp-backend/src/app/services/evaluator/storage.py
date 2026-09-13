"""Storage for message evaluations.

Evaluations differ from every other output in this system: they are produced on
demand, repeated against the same persona, and compared against each other. So
they live in their own collection rather than being squeezed into a single
widget document that only holds one value per key.

Isolation is the point. Every read and write filters on `account_id`, and the
persona is resolved inside that account before scoring starts - the
specification is explicit that "the evaluator context contains no other account
data". A persona id from another account is refused rather than silently
returning nothing.
"""

import hashlib
import logging
from datetime import datetime, timezone

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

COLLECTION = "message_evaluations"
WIDGET_KEY = "evaluator_feedback_score"


def message_fingerprint(message: str, persona_id: str, objective: str,
                        fmt: str, mode: str) -> str:
    """Identity of one evaluation request.

    Re-submitting the same message against the same persona, objective, format
    and mode returns the stored result instead of paying for another model call.
    """
    payload = "||".join([
        " ".join(str(message or "").split()),
        str(persona_id or ""), str(objective or ""), str(fmt or ""), str(mode or ""),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def resolve_persona(account_id: str, persona_id: str) -> dict | None:
    """The persona, but only if it belongs to this account.

    Returns None when the id is unknown here - including when it is a perfectly
    valid persona on a different account, which is the case that matters.
    """
    db = get_db()
    widget = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "evaluator_persona_context",
    }) or {}
    personas = (widget.get("data") or {}).get("persona_archetypes") or []
    for persona in personas:
        if str(persona.get("persona_id")) == str(persona_id):
            return persona
    return None


def find_existing(account_id: str, fingerprint: str) -> dict | None:
    db = get_db()
    return db[COLLECTION].find_one(
        {"account_id": account_id, "fingerprint": fingerprint},
        {"_id": 0})


def next_version(account_id: str, persona_id: str) -> int:
    """Version numbers run per persona, so the UI can show V1, V2 … per target."""
    db = get_db()
    latest = db[COLLECTION].find_one(
        {"account_id": account_id, "persona_contact_id": persona_id},
        sort=[("version", -1)], projection={"version": 1})
    return int((latest or {}).get("version") or 0) + 1


def save(evaluation: dict) -> dict:
    """Persist one evaluation and update the widget pointer."""
    db = get_db()
    now = datetime.now(timezone.utc)
    evaluation["created_at"] = now

    db[COLLECTION].update_one(
        {"account_id": evaluation["account_id"],
         "fingerprint": evaluation["fingerprint"]},
        {"$set": evaluation},
        upsert=True,
    )

    # The widget carries a pointer and the headline number only. The dashboard
    # renders from it without scanning history, and the full evaluation stays
    # in its own collection.
    db["account_widgets"].update_one(
        {"account_id": evaluation["account_id"], "widget_key": WIDGET_KEY},
        {"$set": {
            "account_id": evaluation["account_id"],
            "feature_key": "message_evaluator",
            "widget_key": WIDGET_KEY,
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "latest_fingerprint": evaluation["fingerprint"],
                "persona_contact_id": evaluation["persona_contact_id"],
                "version": evaluation["version"],
                "objective": evaluation["objective"],
                "formula_used": evaluation.get("formula_used"),
                "composite": evaluation.get("composite"),
                "composite_available": evaluation.get("composite") is not None,
                "evaluations_stored": db[COLLECTION].count_documents(
                    {"account_id": evaluation["account_id"]}),
            },
            "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
            "extracted_at": now,
            "updated_at": now,
        }},
        upsert=True,
    )
    return evaluation


def history(account_id: str, persona_id: str = None, limit: int = 20) -> list:
    db = get_db()
    query = {"account_id": account_id}
    if persona_id:
        query["persona_contact_id"] = persona_id
    return list(db[COLLECTION]
                .find(query, {"_id": 0, "message_text": 0})
                .sort("created_at", -1)
                .limit(limit))
