"""Explicit regeneration runs: the only thing that puts work in the queue.

A run is one request - "these accounts, these features, force or not" - turned
into jobs by the planner and recorded in `regen_runs`, so afterwards anyone can
see who asked, what it planned, what it skipped and what it cost.

The run document holds the request and the plan's counts. Progress is not
copied onto it: it is read from the jobs (`regen_jobs.run_ids`) every time, so
it can never disagree with the queue. A job two runs asked for is shared, and
appears in both.

The run's `status` IS stored, and made terminal as soon as its last job is:
every terminal job transition in `jobs` (finish, fail_owned, reclaim_expired)
calls `settle` for the job's runs. Before 21 Oct only `get` did that, so a run
nobody opened stayed RUNNING forever. `recent` and `get` still compute it from
the jobs too, so an old run is listed right before it is settled.
"""

import logging
from datetime import UTC, datetime

from bson import ObjectId

from app.services.regen import jobs, planner
from app.services.regen.graph import INDEX

logger = logging.getLogger(__name__)

COLLECTION = "regen_runs"
MANUAL = "manual"

PLANNED = "PLANNED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
COMPLETED_WITH_FAILURES = "COMPLETED_WITH_FAILURES"
CANCELLED = "CANCELLED"
NOTHING_TO_DO = "NOTHING_TO_DO"


def _now():
    return datetime.now(UTC)


def ensure_indexes(db) -> None:
    db[COLLECTION].create_index([("created_at", -1)], name="recent")
    db[COLLECTION].create_index([("account_ids", 1), ("created_at", -1)],
                                name="by_account")
    db[jobs.COLLECTION].create_index([("run_ids", 1)], name="by_run")
    # "Does this run still have a live (or a failed) job?" - asked by `settle`
    # after every job finishes, so it must be one index lookup, not a scan of a
    # 2,000-job run.
    db[jobs.COLLECTION].create_index([("run_ids", 1), ("status", 1)],
                                     name="by_run_status")
    # Saved partial progress (Live Signals' scored batches): kept long enough
    # for a failed section to be fixed and submitted again, then dropped.
    db["llm_batch_progress"].create_index([("saved_at", 1)], name="expire_progress",
                                          expireAfterSeconds=14 * 24 * 3600)


def create(engine, *, accounts,  # noqa: PLR0913 - the request's fields
           features=None, nodes=None, force: bool = False,
           include_downstream: bool = False, full: bool = False, actor: str = "",
           reason: str = "") -> dict:
    """Plan the request and queue exactly what the plan says to run.

    `full` applies to index nodes only: drop and rebuild instead of updating
    in place. Returns the run document with its plan.
    """
    db = engine.db
    the_plan = planner.plan(engine, accounts=accounts, features=features, nodes=nodes,
                            force=force, include_downstream=include_downstream)
    run_id = ObjectId()
    why = jobs.trigger(MANUAL, (reason or "regeneration run %s" % run_id)[:300],
                       actor, demand=True)
    why["run_id"] = run_id
    queued = attached = 0
    for entry in the_plan["accounts"]:
        for item in entry["items"]:
            if item["action"] == planner.RUN:
                node = engine.graph[item["node_id"]]
                jobs.enqueue(db, entry["account_id"], item["node_id"], why,
                             priority=jobs.PRIORITY_MANUAL, force=item["forced"],
                             full=bool(full) and node.kind == INDEX,
                             rank=engine.graph.rank(item["node_id"]), run_id=run_id)
                if item.get("handed_back"):
                    # Its files are back: let every worker take it again.
                    jobs.clear_not_runnable(db, entry["account_id"], item["node_id"])
                queued += 1
            elif item["action"] == planner.IN_PROGRESS and item.get("job"):
                jobs.attach_run(db, ObjectId(item["job"]["id"]), run_id)
                attached += 1

    doc = {
        "_id": run_id,
        "status": RUNNING if (queued or attached) else NOTHING_TO_DO,
        "request": {**the_plan["request"], "full": bool(full)},
        "reason": reason,
        "actor": actor or "system",
        "created_at": _now(),
        "account_ids": [e["account_id"] for e in the_plan["accounts"]],
        "totals": {**the_plan["totals"], "queued": queued, "attached": attached},
        # Per account: what was planned, compactly. The full reasons are in the
        # preview the caller already has; the jobs carry their own changed inputs.
        "planned": [{"account_id": e["account_id"], "account_name": e.get("account_name"),
                     "run": [i["node_id"] for i in e["items"]
                             if i["action"] == planner.RUN],
                     "in_progress": [i["node_id"] for i in e["items"]
                                     if i["action"] == planner.IN_PROGRESS],
                     "skipped_current": [i["node_id"] for i in e["items"]
                                         if i["action"] == planner.SKIP_CURRENT],
                     "cannot_run": [i["node_id"] for i in e["items"]
                                    if i["action"] == planner.CANNOT_RUN]}
                    for e in the_plan["accounts"]],
    }
    if doc["status"] == NOTHING_TO_DO:
        doc["finished_at"] = doc["created_at"]
    db[COLLECTION].insert_one(doc)
    if doc["status"] == RUNNING:
        # The jobs were queued before this document existed, so a fast one
        # can already have finished - and its `settle` found no run to update.
        try:
            settled = settle(db, [run_id])
        except Exception:
            # The run is stored and its jobs queued; `recent`/`get` settle it
            # later. Failing the Submit here would only invite a second one.
            logger.exception("regen: could not settle new run %s", run_id)
            settled = {}
        if run_id in settled:
            doc["status"] = settled[run_id]
    return {**doc, "plan": the_plan}


def _job_summary(job: dict) -> dict:
    result = job.get("result") or {}
    return {"job_id": str(job["_id"]), "account_id": job["account_id"],
            "node_id": job["node_id"], "status": job["status"],
            "outcome": result.get("outcome"), "quality": result.get("quality"),
            "forced": bool(job.get("force")), "attempts": int(job.get("attempts") or 0),
            "requested_at": job.get("requested_at"), "started_at": job.get("started_at"),
            "finished_at": job.get("finished_at"), "progress": job.get("progress"),
            "duration_ms": result.get("duration_ms"),
            "changed_inputs": job.get("changed_inputs") or result.get("changed_inputs"),
            "error": job.get("error") or job.get("last_error"),
            "released_reason": job.get("released_reason"),
            "blocked_by": result.get("blocked_by"),
            # Every attempt: the one that finished (result) plus any stopped by
            # the quota before it (spent).
            "usage": {"model_calls": _used(job, "api_calls"),
                      "tokens": _used(job, "tokens"),
                      "embedding_calls": _used(job, "embedding_calls"),
                      "embedded_texts": _used(job, "embedded_texts")}}


def _used(job: dict, key: str) -> int:
    return (int((job.get("result") or {}).get(key) or 0)
            + int((job.get("spent") or {}).get(key) or 0))


def _status(stored: str | None, has_live: bool, has_failed: bool) -> str:
    """A run's status from its stored one and what its jobs are doing."""
    if stored in (CANCELLED, NOTHING_TO_DO) and not has_live:
        return stored
    if has_live:
        return RUNNING
    if has_failed:
        return COMPLETED_WITH_FAILURES
    return SUCCEEDED


def status_of(run: dict, job_rows: list) -> str:
    return _status(run.get("status"),
                   any(j["status"] in jobs.LIVE for j in job_rows),
                   any(j["status"] == jobs.FAILED for j in job_rows))


def _has_job(db, run_id, status) -> bool:
    """Served by `by_run_status`: one lookup however big the run is."""
    return db[jobs.COLLECTION].find_one({"run_ids": run_id, "status": status},
                                        {"_id": 1}) is not None


def _has_live(db, run_id) -> bool:
    return _has_job(db, run_id, {"$in": list(jobs.LIVE)})


def _last_finished(db, run_id):
    row = db[jobs.COLLECTION].find_one(
        {"run_ids": run_id, "finished_at": {"$exists": True}}, {"finished_at": 1},
        sort=[("finished_at", -1)])
    return (row or {}).get("finished_at")


def settle(db, run_ids) -> dict:
    """Make each of these runs terminal if it is RUNNING and none of its jobs
    is live any more. Returns {run_id: new status} for the runs it changed.

    Called after every terminal job transition, with that job's run ids. Cheap
    while a run is still going: one indexed lookup finds a live job and stops.
    The write is conditional on the run still being RUNNING, so a run that was
    cancelled - or settled by another worker a moment ago - is left alone, and
    two workers finishing a run's last two jobs together settle it once.
    """
    out = {}
    for run_id in dict.fromkeys(run_ids or []):
        if _has_live(db, run_id):
            continue
        run = db[COLLECTION].find_one({"_id": run_id, "status": RUNNING}, {"_id": 1})
        if not run:
            continue
        status = _status(RUNNING, False, _has_job(db, run_id, jobs.FAILED))
        finished = _last_finished(db, run_id) or _now()
        result = db[COLLECTION].update_one(
            {"_id": run_id, "status": RUNNING},
            {"$set": {"status": status, "finished_at": finished}})
        if result.modified_count:
            out[run_id] = status
    return out


def get(db, run_id) -> dict | None:
    run = db[COLLECTION].find_one({"_id": ObjectId(str(run_id))})
    if not run:
        return None
    rows = list(db[jobs.COLLECTION].find({"run_ids": run["_id"]}).sort(
        [("rank", 1), ("requested_at", 1)]))
    summaries = [_job_summary(j) for j in rows]
    status = status_of(run, rows)
    if status != run.get("status") and status not in (RUNNING,):
        finished = max((j.get("finished_at") for j in rows if j.get("finished_at")),
                       default=_now())
        # Conditional on what was read, so a cancel landing in between wins.
        db[COLLECTION].update_one({"_id": run["_id"], "status": run.get("status")},
                                  {"$set": {"status": status, "finished_at": finished}})
        run["finished_at"] = finished
    counts = {}
    for j in rows:
        counts[j["status"]] = counts.get(j["status"], 0) + 1
    usage = {k: sum(s["usage"][k] for s in summaries)
             for k in ("model_calls", "tokens", "embedding_calls", "embedded_texts")}
    total = len(rows)
    done = sum(1 for j in rows if j["status"] in jobs.TERMINAL)
    return {**run, "status": status, "jobs": summaries, "job_counts": counts,
            "usage": usage, "progress": {"done": done, "total": total}}


def recent(db, account_id: str | None = None, limit: int = 10) -> list:
    """The latest runs, with the status `get` would give each.

    Only a run stored RUNNING or CANCELLED can differ from what its jobs say,
    so only those are looked at - one indexed lookup each - and a RUNNING one
    with no live job left is settled on the way (a run from before settling
    existed, or one whose last job's settle failed).
    """
    query = {"account_ids": account_id} if account_id else {}
    rows = list(db[COLLECTION].find(query, {"planned": 0}).sort("created_at", -1).limit(
        max(1, min(int(limit), 50))))
    for run in rows:
        if run.get("status") not in (RUNNING, CANCELLED):
            continue
        if _has_live(db, run["_id"]):
            run["status"] = RUNNING
        elif run["status"] == RUNNING:
            try:
                settle(db, [run["_id"]])
            except Exception:
                # A listing must not fail on a write: show what it would be.
                logger.exception("regen: could not settle run %s", run["_id"])
                run["status"] = _status(RUNNING, False,
                                        _has_job(db, run["_id"], jobs.FAILED))
                continue
            # Re-read rather than trust our own write: another worker may have
            # settled it a moment earlier.
            fresh = db[COLLECTION].find_one({"_id": run["_id"]},
                                            {"status": 1, "finished_at": 1}) or {}
            run["status"] = fresh.get("status", run["status"])
            if fresh.get("finished_at"):
                run["finished_at"] = fresh["finished_at"]
    return rows


def stuck(db, limit: int = 1000) -> list:
    """Runs stored RUNNING with no live job: what `settle` would finish, and
    the status each would get. Read-only - for scripts/finalize_stuck_runs.py."""
    out = []
    for run in db[COLLECTION].find({"status": RUNNING},
                                   {"planned": 0}).sort("created_at", 1).limit(limit):
        if _has_live(db, run["_id"]):
            continue
        status = _status(RUNNING, False, _has_job(db, run["_id"], jobs.FAILED))
        out.append({**run, "would_be": status})
    return out


def cancel(db, run_id, actor: str = "") -> dict | None:
    """Cancel what a run has not started yet. Only a run that is still going:
    a run whose jobs have all finished keeps its outcome (it is settled here
    first, in case it was never settled), and `cancelled` is 0."""
    run = db[COLLECTION].find_one({"_id": ObjectId(str(run_id))})
    if not run:
        return None
    settle(db, [run["_id"]])
    marked = db[COLLECTION].update_one(
        {"_id": run["_id"], "status": RUNNING},
        {"$set": {"status": CANCELLED, "cancelled_at": _now(),
                  "cancelled_by": actor or "system"}}).modified_count
    if not marked:
        current = (db[COLLECTION].find_one({"_id": run["_id"]}, {"status": 1})
                   or {}).get("status")
        # Cancelled already but something of it is still queued (a rerun put
        # back after the first cancel): cancel that, the status stays.
        if not (current == CANCELLED and _has_live(db, run["_id"])):
            return {"run_id": str(run["_id"]), "cancelled": 0, "detached": 0,
                    "status": current}
    result = jobs.cancel_run(db, run["_id"])
    return {"run_id": str(run["_id"]), **result, "status": CANCELLED}
