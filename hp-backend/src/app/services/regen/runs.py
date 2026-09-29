"""Explicit regeneration runs: the only thing that puts work in the queue.

A run is one request - "these accounts, these features, force or not" - turned
into jobs by the planner and recorded in `regen_runs`, so afterwards anyone can
see who asked, what it planned, what it skipped and what it cost.

The run document holds the request and the plan's counts. Progress is not
copied onto it: it is read from the jobs (`regen_jobs.run_ids`) every time, so
it can never disagree with the queue. A job two runs asked for is shared, and
appears in both.
"""

from datetime import UTC, datetime

from bson import ObjectId

from app.services.regen import jobs, planner
from app.services.regen.graph import INDEX

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
            "usage": {"model_calls": int(result.get("api_calls") or 0),
                      "tokens": int(result.get("tokens") or 0),
                      "embedding_calls": int(result.get("embedding_calls") or 0),
                      "embedded_texts": int(result.get("embedded_texts") or 0)}}


def status_of(run: dict, job_rows: list) -> str:
    if run.get("status") in (CANCELLED, NOTHING_TO_DO) and not any(
            j["status"] in jobs.LIVE for j in job_rows):
        return run["status"]
    if any(j["status"] in jobs.LIVE for j in job_rows):
        return RUNNING
    if any(j["status"] == jobs.FAILED for j in job_rows):
        return COMPLETED_WITH_FAILURES
    return SUCCEEDED


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
        db[COLLECTION].update_one({"_id": run["_id"]},
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
    query = {"account_ids": account_id} if account_id else {}
    rows = db[COLLECTION].find(query, {"planned": 0}).sort("created_at", -1).limit(
        max(1, min(int(limit), 50)))
    return list(rows)


def cancel(db, run_id, actor: str = "") -> dict | None:
    run = db[COLLECTION].find_one({"_id": ObjectId(str(run_id))})
    if not run:
        return None
    result = jobs.cancel_run(db, run["_id"])
    db[COLLECTION].update_one({"_id": run["_id"]},
                              {"$set": {"status": CANCELLED, "cancelled_at": _now(),
                                        "cancelled_by": actor or "system"}})
    return {"run_id": str(run["_id"]), **result}
