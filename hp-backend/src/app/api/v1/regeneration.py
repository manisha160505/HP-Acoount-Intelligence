"""Regeneration: see what is stale, preview what a run would do, and run it.

Nothing here generates inside a request, and nothing anywhere generates unless
one of these endpoints was called (29 Sep):

    POST /regeneration/preview      what a request would run - no model calls
    POST /regeneration              run it: {accounts, features, nodes, force,
                                    include_downstream, full}
    GET  /regeneration/runs         recent runs (optionally ?account_id=)
    GET  /regeneration/{run_id}     one run: its jobs, progress, errors, usage
    POST /regeneration/{run_id}/cancel
    GET  /regeneration/queue        paused or not, and why
    POST /regeneration/queue/pause | /resume
    GET  /regeneration/accounts-summary   every account's counts by status
    GET  /accounts/{id}/pipeline    one account: every section, why, progress
    POST /indexes/rebuild/preview | /indexes/rebuild   the index nodes only

`accounts` is a list of ids or exact names, or "all"; `features` a list of
feature ids or "all"; `nodes` raw section ids for the finest control. `force`
defaults to false: a current section is only re-run when it is asked for.

The older per-feature endpoints stay, as thin wrappers over the same run.
"""

from datetime import date, datetime

from bson import ObjectId
from fastapi import APIRouter, Body, Depends, HTTPException, status

from app.core.deps import require_admin_role, require_user_role
from app.database.mongodb import get_db
from app.services.regen import jobs as regen_jobs, planner, runs
from app.services.regen.engine import get_engine
from app.services.regen.graph import DEFAULT, INDEX

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


def _actor(user: dict) -> str:
    return "user:%s" % (user or {}).get("id", "?")


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


def _request(body: dict) -> dict:
    body = body or {}
    accounts = body.get("accounts")
    if accounts in (None, "", []):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail='name the accounts to run, or "all"')
    return {"accounts": accounts, "features": body.get("features"),
            "nodes": body.get("nodes"), "force": bool(body.get("force")),
            "include_downstream": bool(body.get("include_downstream"))}


def _plan_or_400(fn, **kw):
    try:
        return fn(**kw)
    except planner.PlanError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from exc


@router.post("/regeneration/preview")
def preview(body: dict = Body(...), current_user: dict = Depends(require_admin_role)):
    """What `POST /regeneration` with this body would run, and why. Writes
    nothing and calls no model."""
    req = _request(body)
    return jsonable(_plan_or_400(planner.plan, engine=get_engine(), **req))


@router.post("/regeneration", status_code=status.HTTP_202_ACCEPTED)
def start_run(body: dict = Body(...), current_user: dict = Depends(require_admin_role)):
    """Plan and queue. Returns the run with its plan; the worker does the work.
    Poll `GET /regeneration/{run_id}` for progress."""
    req = _request(body)
    run = _plan_or_400(runs.create, engine=get_engine(), **req,
                       full=bool((body or {}).get("full")), actor=_actor(current_user),
                       reason=str((body or {}).get("reason") or "")[:300])
    return jsonable(run)


@router.get("/regeneration/runs")
def list_runs(account_id: str | None = None, limit: int = 10,
              current_user: dict = Depends(require_admin_role)):
    return {"runs": jsonable(runs.recent(get_db(), account_id, limit))}


@router.get("/regeneration/queue")
def queue_state(current_user: dict = Depends(require_admin_role)):
    db = get_db()
    counts = {s: db[regen_jobs.COLLECTION].count_documents({"status": s})
              for s in regen_jobs.LIVE}
    return jsonable({**regen_jobs.queue_state(db), "jobs": counts})


@router.post("/regeneration/queue/pause")
def queue_pause(body: dict = Body(default={}),
                current_user: dict = Depends(require_admin_role)):
    regen_jobs.pause(get_db(), str((body or {}).get("reason") or "paused by an admin"),
                     by=_actor(current_user))
    return jsonable(regen_jobs.queue_state(get_db()))


@router.post("/regeneration/queue/resume")
def queue_resume(current_user: dict = Depends(require_admin_role)):
    regen_jobs.resume(get_db(), by=_actor(current_user))
    return jsonable(regen_jobs.queue_state(get_db()))


@router.get("/regeneration/accounts-summary")
def accounts_summary(current_user: dict = Depends(require_admin_role)):
    """Every account's sections counted by status. No model calls; a few
    queries per account."""
    db, engine = get_db(), get_engine()
    out = []
    for account in db["accounts"].find({}, {"name": 1}).sort("name", 1):
        account_id = str(account["_id"])
        view = planner.account_view(engine, account_id)
        counts = {}
        progress = None
        for n in view["nodes"].values():
            counts[n["status"]] = counts.get(n["status"], 0) + 1
            if n["status"] == planner.RUNNING and n["job"]:
                progress = {"node_id": n["node_id"], "label": n["label"],
                            "progress": n["job"].get("progress")}
        out.append({"account_id": account_id, "name": account.get("name"),
                    "counts": counts, "total": len(view["nodes"]),
                    "needs_run": sum(counts.get(s, 0) for s in planner.NEEDS_RUN),
                    "running": progress})
    return jsonable({"accounts": out, "queue": regen_jobs.queue_state(db)})


@router.get("/regeneration/{run_id}")
def get_run(run_id: str, current_user: dict = Depends(require_admin_role)):
    if not ObjectId.is_valid(run_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run id")
    run = runs.get(get_db(), run_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return jsonable(run)


@router.post("/regeneration/{run_id}/cancel")
def cancel_run(run_id: str, current_user: dict = Depends(require_admin_role)):
    if not ObjectId.is_valid(run_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run id")
    out = runs.cancel(get_db(), run_id, _actor(current_user))
    if not out:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return jsonable(out)


@router.get("/accounts/{account_id}/pipeline")
def account_pipeline(account_id: str, current_user: dict = Depends(require_admin_role)):
    """One account's sections grouped by status, each with why it is in that
    status (categorised), the live job's progress and the last error, plus the
    account's recent runs and the queue state. Refresh-safe: no model calls."""
    _check_account(account_id)
    db, engine = get_db(), get_engine()
    view = planner.account_view(engine, account_id)
    groups = {s: [] for s in (planner.RUNNING, planner.QUEUED, planner.FILES_MISSING,
                              planner.FAILED, planner.STALE, planner.DEGRADED,
                              planner.BLOCKED, planner.NEVER_RUN, planner.CURRENT)}
    for n in view["nodes"].values():
        groups[n["status"]].append(n)
    return jsonable({"account_id": account_id, "groups": groups,
                     "counts": {k: len(v) for k, v in groups.items()},
                     "needs_run": sum(len(groups[s]) for s in planner.NEEDS_RUN),
                     "queue": regen_jobs.queue_state(db),
                     "runs": runs.recent(db, account_id, 5)})


# --------------------------------------------------------------------------
# Index nodes only
# --------------------------------------------------------------------------

def _index_nodes(indexes) -> list:
    all_idx = [n for n in DEFAULT.order if DEFAULT[n].kind == INDEX]
    if indexes in (None, "all", ["all"], []):
        return all_idx
    wanted = ["idx_%s" % i if not str(i).startswith("idx_") else str(i)
              for i in ([indexes] if isinstance(indexes, str) else indexes)]
    unknown = [w for w in wanted if w not in all_idx]
    if unknown:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="unknown index: %s" % ", ".join(unknown))
    return wanted


@router.post("/indexes/rebuild/preview")
def index_preview(body: dict = Body(...), current_user: dict = Depends(require_admin_role)):
    req = _request({**(body or {}), "nodes": _index_nodes((body or {}).get("indexes"))})
    req["features"] = None
    return jsonable(_plan_or_400(planner.plan, engine=get_engine(), **req))


@router.post("/indexes/rebuild", status_code=status.HTTP_202_ACCEPTED)
def index_rebuild(body: dict = Body(...), current_user: dict = Depends(require_admin_role)):
    """Rebuild index nodes. `full: true` drops and rebuilds in place (the index
    is unavailable meanwhile); otherwise only changed documents are updated."""
    req = _request({**(body or {}), "nodes": _index_nodes((body or {}).get("indexes"))})
    req["features"] = None
    run = _plan_or_400(runs.create, engine=get_engine(), **req,
                       full=bool((body or {}).get("full")), actor=_actor(current_user),
                       reason="index rebuild")
    return jsonable(run)


# --------------------------------------------------------------------------
# Per-feature endpoints kept from before - now explicit runs, not forced
# --------------------------------------------------------------------------

@router.post("/accounts/{account_id}/features/{feature_id}/regenerate",
             status_code=status.HTTP_202_ACCEPTED)
def regenerate_feature(account_id: str, feature_id: str, force: bool = False,
                       current_user: dict = Depends(require_user_role)):
    """One feature of one account, as an explicit run. Sections that are
    current are skipped unless `force=true`."""
    _check_account(account_id)
    key = _check_feature(feature_id)
    result = get_engine().regenerate_feature(account_id, key, actor=_actor(current_user),
                                             force=force)
    return jsonable(result)


@router.get("/accounts/{account_id}/features/status")
def feature_status(account_id: str, current_user: dict = Depends(require_user_role)):
    """Every feature's lifecycle - CURRENT, STALE, GENERATING, FAILED or
    NEVER_GENERATED - with the producers underneath and why each is stale."""
    _check_account(account_id)
    return jsonable(get_engine().status(account_id))


@router.get("/accounts/{account_id}/regeneration/jobs")
def regeneration_jobs(account_id: str, limit: int = 20,
                      current_user: dict = Depends(require_user_role)):
    """Recent jobs: which run asked, which inputs changed, the outcome."""
    _check_account(account_id)
    rows = regen_jobs.history(get_db(), account_id, limit)
    for row in rows:
        row.pop("fence", None)
        row.pop("lease_owner", None)
    return {"jobs": jsonable(rows)}


@router.post("/regeneration/sweep")
def run_sweep(current_user: dict = Depends(require_admin_role)):
    """Formerly queued every stale node of every account. Now a report only:
    how many accounts need a run. Use POST /regeneration to run them."""
    return jsonable(get_engine().stale_report())
