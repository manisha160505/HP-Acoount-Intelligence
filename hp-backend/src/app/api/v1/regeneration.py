"""Regeneration: ask for a feature to be rebuilt, and see where every feature stands.

Features are what this API speaks; the engine schedules producers underneath
(`services/regen/graph.py`), and several features are two producers. Nothing
here generates inline - a request queues work and returns, and the background
worker commits it.
"""

from datetime import date, datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status

from app.core.deps import require_admin_role, require_user_role
from app.database.mongodb import get_db
from app.services.regen import jobs as regen_jobs
from app.services.regen.engine import get_engine
from app.services.regen.graph import DEFAULT

router = APIRouter(tags=["Regeneration"])


def jsonable(value):
    """ObjectIds and datetimes, recursively, in a form the response can carry."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [jsonable(v) for v in value]
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _check_account(account_id: str) -> None:
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Invalid account ID format")
    if not get_db()["accounts"].find_one({"_id": ObjectId(account_id)}, {"_id": 1}):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Company account not found")


def _check_feature(feature_id: str) -> str:
    key = str(feature_id or "").strip().lower()
    if not DEFAULT.nodes_for_feature(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Feature '%s' is not regenerable." % feature_id)
    return key


@router.post("/accounts/{account_id}/features/{feature_id}/regenerate",
             status_code=status.HTTP_202_ACCEPTED)
def regenerate_feature(account_id: str, feature_id: str, force: bool = True,
                       current_user: dict = Depends(require_user_role)):
    """Queue one feature for regeneration and return at once.

    `force` (default true for a click) regenerates even when nothing changed,
    bypassing the model caches. Repeated clicks coalesce into one job. Upstream
    features that are stale are rebuilt first; features that depend on this one
    follow once it commits.
    """
    _check_account(account_id)
    key = _check_feature(feature_id)
    result = get_engine().regenerate_feature(
        account_id, key, actor="user:%s" % current_user.get("id", "?"), force=force)
    return jsonable(result)


@router.get("/accounts/{account_id}/features/status")
def feature_status(account_id: str, current_user: dict = Depends(require_user_role)):
    """Every feature's lifecycle - CURRENT, STALE, GENERATING, FAILED or
    NEVER_GENERATED - with the producers underneath, why each is stale, the
    last error, and any live job."""
    _check_account(account_id)
    return jsonable(get_engine().status(account_id))


@router.get("/accounts/{account_id}/regeneration/jobs")
def regeneration_jobs(account_id: str, limit: int = 20,
                      current_user: dict = Depends(require_user_role)):
    """Recent jobs: what triggered each, which inputs changed, the outcome and
    how long it took."""
    _check_account(account_id)
    rows = regen_jobs.history(get_db(), account_id, limit)
    for row in rows:
        row.pop("fence", None)
        row.pop("lease_owner", None)
    return {"jobs": jsonable(rows)}


@router.post("/regeneration/sweep")
def run_sweep(current_user: dict = Depends(require_admin_role)):
    """Reconcile every account now, instead of waiting for the periodic sweep.

    For after a knowledge reload (rulebook, case studies, lifecycle) or a
    scoring-config change: the sweep sees the new versions and queues what they
    invalidated.
    """
    return jsonable(get_engine().sweep())
