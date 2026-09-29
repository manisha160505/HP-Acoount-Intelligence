"""The durable job queue every regeneration goes through.

The retrieval queue this generalises (`services/retrieval/jobs.py`) had the
right shape - a job is a Mongo row and the worker leases it, so a restart loses
nothing - and three defects the engine must not inherit:

  * a job that ran out of attempts while RUNNING was never reclaimed and never
    failed, and because `enqueue` treated RUNNING as live, its index could not
    be rebuilt again (audit R3);
  * the lease was never extended, so a long build could be reclaimed while it
    was still running (R13);
  * coalescing was check-then-insert with no unique index, so two triggers
    could create two pending jobs (R14).

Two rules replace them:

  * **One live row per node** (`uniq_live_job_per_node`, PENDING or RUNNING).
    A trigger arriving while the node runs sets `rerun_requested` on the
    running row; finishing that row re-enqueues. There is never a PENDING row
    beside a RUNNING one, so claiming cannot collide with the unique index.
  * **One RUNNING row per account** (`uniq_running_per_account`). An index is
    rebuilt in place while its consumers query it live; if two nodes of one
    account could run together, a consumer could build from a half-rebuilt
    index and still record the fingerprint of a complete one. Accounts still
    run in parallel with each other.

Every write made on behalf of a running job is scoped by its `fence`, a token
issued at claim. A worker whose lease expired and was reclaimed can wake up and
try to heartbeat, finish or commit - and match nothing.

**Only an explicit run creates work** (29 Sep). A job carries the ids of the
regeneration runs that asked for it (`run_ids`), and `claim` takes nothing
else: an upload, a deploy or a committed upstream can make a node stale but can
never put a job in front of the worker. Two runs asking for the same node share
one job. The queue can also be paused - by hand, or by the engine when the
model provider's quota is exhausted - and nothing is claimed until it resumes.
"""

import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

COLLECTION = "regen_jobs"
CONTROL = "regen_control"
QUEUE_DOC = "queue"

PENDING = "PENDING"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
SKIPPED = "SKIPPED"
FAILED = "FAILED"
FENCED = "FENCED"
CANCELLED = "CANCELLED"
LIVE = (PENDING, RUNNING)
TERMINAL = (SUCCEEDED, SKIPPED, FAILED, FENCED, CANCELLED)

# Claim order. A seller's click must not wait behind a 220-account sweep.
PRIORITY_MANUAL = 30
PRIORITY_INPUT = 20        # upload, delete, config edit
PRIORITY_UPSTREAM = 10
PRIORITY_SWEEP = 5
PRIORITY_LEGACY = 0

# Renewed by the engine's heartbeat every HEARTBEAT_SECONDS while a job runs,
# so a live job never lapses however long it takes. It only bounds how long a
# job whose worker died (a deploy, a crash, an OOM kill) stays RUNNING before
# another worker takes it back: 30 minutes left Live Signals looking
# "generating" for half an hour after every deploy (28 Sep).
LEASE_SECONDS = 150
MAX_ATTEMPTS = 3
# A job whose worker died under it (crash, out of memory, a kill) or was
# stopped by a restart or deploy. Not re-queued: it fails with this reason and
# is submitted again by hand.
WORKER_STOPPED = "WORKER_STOPPED"
WORKER_STOPPED_MESSAGE = ("the worker running it stopped responding (crash or kill) "
                          "- submit it again")
INTERRUPTED = "INTERRUPTED"
INTERRUPTED_MESSAGE = ("stopped by a backend restart or deploy while it ran - "
                       "submit it again (an index build continues from where it "
                       "stopped)")
GATE_RETRY_SECONDS = 60

WORKER_ID = "%s:%d:%s" % (socket.gethostname(), os.getpid(), uuid.uuid4().hex[:6])


def _now():
    return datetime.now(UTC)


def ensure_indexes(db) -> None:
    col = db[COLLECTION]
    col.create_index([("account_id", ASCENDING), ("node_id", ASCENDING)],
                     name="uniq_live_job_per_node", unique=True,
                     partialFilterExpression={"status": {"$in": list(LIVE)}})
    col.create_index([("account_id", ASCENDING)],
                     name="uniq_running_per_account", unique=True,
                     partialFilterExpression={"status": RUNNING})
    col.create_index([("status", ASCENDING), ("priority", DESCENDING),
                      ("rank", ASCENDING), ("requested_at", ASCENDING)],
                     name="claim_scan")
    col.create_index([("account_id", ASCENDING), ("requested_at", DESCENDING)],
                     name="account_history")


def trigger(kind: str, detail: str = "", actor: str = "", demand: bool = False) -> dict:
    """One reason a job exists. `actor` is a user id or `system:<what>`; never
    an email or a payload."""
    return {"type": kind, "detail": str(detail)[:300], "actor": actor or "system",
            "demand": bool(demand), "at": _now()}


def enqueue(db, account_id: str, node_id: str, why: dict, *,  # noqa: PLR0913 - every option is a queue field
            priority: int = PRIORITY_UPSTREAM, force: bool = False,
            full: bool = False, rank: int = 0, run_id=None) -> dict:
    """Ask for a node to be regenerated. Coalesces; never creates a second live row.

    `run_id` is the explicit regeneration run asking for it. A job with no run
    is never claimed, so every caller that means work passes one.

    Returns {"job_id", "status", "coalesced"}.
    """
    col = db[COLLECTION]
    demand = bool(why.get("demand"))
    runs = [run_id] if run_id is not None else []

    for _ in range(3):
        # 1. The node is running: note that it must run again once finished.
        running = col.find_one_and_update(
            {"account_id": account_id, "node_id": node_id, "status": RUNNING},
            {"$set": {"rerun_requested": True},
             "$push": {"rerun_triggers": why},
             "$addToSet": {"rerun_run_ids": {"$each": runs}},
             "$max": {"rerun_force": bool(force), "rerun_full": bool(full),
                      "rerun_priority": int(priority), "rerun_demand": demand}},
            projection={"_id": 1},
            return_document=ReturnDocument.AFTER)
        if running:
            logger.info("regen: %s/%s running - rerun requested (%s)",
                        account_id, node_id, why.get("type"))
            return {"job_id": running["_id"], "status": RUNNING, "coalesced": True}

        # 2. Coalesce into the pending row, or create it. `force`, `full`,
        # `priority` and `demand` are only ever in `$max` - Mongo rejects a
        # path that appears in two operators, and `$max` sets it on insert.
        # `not_before` is in `$min`, so a manual trigger pulls forward a job
        # that was waiting out a retry backoff.
        try:
            before = col.find_one_and_update(
                {"account_id": account_id, "node_id": node_id, "status": PENDING},
                {"$push": {"triggers": why},
                 "$addToSet": {"run_ids": {"$each": runs}},
                 "$max": {"force": bool(force), "full": bool(full),
                          "priority": int(priority), "demand": demand},
                 "$min": {"not_before": _now()},
                 "$setOnInsert": {
                     "account_id": account_id, "node_id": node_id,
                     "status": PENDING, "requested_at": _now(), "rank": int(rank),
                     "attempts": 0, "rerun_requested": False,
                     "not_runnable_on": [], "fence": None,
                     "lease_owner": None, "lease_expires_at": None,
                 }},
                upsert=True,
                projection={"_id": 1},
                return_document=ReturnDocument.BEFORE)
        except DuplicateKeyError:
            # The pending row became RUNNING between step 1 and step 2, or a
            # concurrent enqueue inserted first. Either way step 1 or the
            # coalesce now matches.
            continue

        if before:
            return {"job_id": before["_id"], "status": PENDING, "coalesced": True}
        created = col.find_one({"account_id": account_id, "node_id": node_id,
                                "status": PENDING}, {"_id": 1})
        logger.info("regen: enqueued %s/%s (%s, priority %d%s)", account_id, node_id,
                    why.get("type"), priority, ", force" if force else "")
        return {"job_id": created["_id"] if created else None, "status": PENDING,
                "coalesced": False}

    raise RuntimeError("could not enqueue %s/%s after 3 attempts" % (account_id, node_id))


def reclaim_expired(db, now=None) -> list:
    """Fail RUNNING rows whose lease has lapsed - their worker is gone.

    Never back to PENDING (29 Sep): a job that did not finish shows as FAILED
    with the reason, and is submitted again by hand. Before, it was re-queued
    up to MAX_ATTEMPTS times. Returns [(job, "failed")] so the engine can clear
    the node's `running` marker and record the failure on the node.
    """
    now = now or _now()
    col = db[COLLECTION]
    out = []
    for job in list(col.find({"status": RUNNING, "lease_expires_at": {"$lt": now}})):
        changed = col.find_one_and_update(
            {"_id": job["_id"], "status": RUNNING, "fence": job.get("fence"),
             "lease_expires_at": {"$lt": now}},
            {"$set": {"status": FAILED, "finished_at": now,
                      "error": {"code": WORKER_STOPPED, "message": WORKER_STOPPED_MESSAGE},
                      "result": {"outcome": "failed", "reason": WORKER_STOPPED},
                      "lease_owner": None, "lease_expires_at": None}},
            return_document=ReturnDocument.BEFORE)
        if changed:
            logger.warning("regen: lease expired on %s/%s - failed (worker stopped)",
                           job["account_id"], job["node_id"])
            out.append((changed, "failed"))
    return out


def claim(db, worker_id: str = WORKER_ID, now=None, max_tries: int = 20) -> dict | None:
    """Lease the highest-priority runnable PENDING job.

    The gate (are this node's ancestors current?) reads other documents, so it
    cannot be part of this filter; the engine evaluates it after the claim and
    releases the job if it does not pass.
    """
    now = now or _now()
    col = db[COLLECTION]
    busy = set(col.distinct("account_id", {"status": RUNNING}))

    for _ in range(max_tries):
        fence = uuid.uuid4().hex
        try:
            job = col.find_one_and_update(
                {"status": PENDING, "not_before": {"$lte": now},
                 "account_id": {"$nin": sorted(busy)},
                 "not_runnable_on": {"$ne": worker_id},
                 # Only work an explicit run asked for (see the module doc).
                 "run_ids.0": {"$exists": True}},
                {"$set": {"status": RUNNING, "fence": fence, "lease_owner": worker_id,
                          "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                          "heartbeat_at": now, "started_at": now, "progress": None,
                          "rerun_requested": False, "rerun_triggers": [],
                          "rerun_run_ids": []}},
                # Within a priority, ancestors first: a dependent claimed ahead
                # of the ancestor it waits on is only gated and released again.
                sort=[("priority", DESCENDING), ("rank", ASCENDING),
                      ("requested_at", ASCENDING)],
                return_document=ReturnDocument.AFTER)
        except DuplicateKeyError as exc:
            # Another worker took a job in the same account a moment ago. Skip
            # that account for the rest of this pass.
            account = _account_from_dup(exc)
            if account:
                busy.add(account)
            else:
                busy |= set(col.distinct("account_id", {"status": RUNNING}))
            continue
        return job
    return None


def _account_from_dup(exc) -> str | None:
    details = getattr(exc, "details", None) or {}
    key = details.get("keyValue") or {}
    return key.get("account_id")


def heartbeat(db, job: dict, now=None) -> bool:
    """Extend the lease. False means the job was reclaimed from under us."""
    now = now or _now()
    result = db[COLLECTION].update_one(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING},
        {"$set": {"lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                  "heartbeat_at": now}})
    return result.matched_count == 1


def start_attempt(db, job: dict, target: str, previous: str | None,
                  changed_inputs: list) -> bool:
    """Record that the run is really starting. Gate releases and "not runnable
    here" never reach this, so they never use up an attempt."""
    result = db[COLLECTION].update_one(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING},
        {"$inc": {"attempts": 1},
         "$set": {"target_fingerprint": target, "previous_fingerprint": previous,
                  "changed_inputs": list(changed_inputs or [])[:50]}})
    return result.matched_count == 1


def release(db, job: dict, *, delay_seconds: float = 0, reason: str = "",  # noqa: PLR0913 - every option is a queue field
            not_runnable_here: bool = False, error: dict | None = None,
            refund_attempt: bool = False, spent: dict | None = None,
            now=None) -> bool:
    """Put a RUNNING job back to PENDING without finishing it.

    `refund_attempt` gives back the attempt `start_attempt` counted - for a run
    stopped by something that is not its own failure (the quota). `spent` is
    the usage of the attempt that stopped ({"api_calls": n, "tokens": n, ...}):
    added to the job's `spent` totals, so what a stopped attempt cost is not
    lost when the next attempt finishes.
    """
    now = now or _now()
    update = {"$set": {"status": PENDING, "fence": None, "lease_owner": None,
                       "lease_expires_at": None, "progress": None,
                       "not_before": now + timedelta(seconds=delay_seconds),
                       "released_reason": str(reason)[:300]}}
    if error:
        update["$set"]["last_error"] = error
    inc = {}
    if refund_attempt:
        inc["attempts"] = -1
    for key, value in (spent or {}).items():
        if value:
            inc["spent.%s" % key] = int(value)
    if inc:
        update["$inc"] = inc
    if not_runnable_here:
        update["$addToSet"] = {"not_runnable_on": job.get("lease_owner") or WORKER_ID}
    result = db[COLLECTION].update_one(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING}, update)
    return result.matched_count == 1


def fail_owned(db, worker_id: str = WORKER_ID, now=None) -> list:
    """Fail every job this worker is running, on shutdown.

    A restart or deploy stops the producer threads mid-job. The jobs are marked
    FAILED ("interrupted") straight away - never left RUNNING for a lease to
    lapse, never re-queued - so the admin page shows exactly what was cut off.
    """
    now = now or _now()
    failed = []
    for job in list(db[COLLECTION].find({"status": RUNNING, "lease_owner": worker_id})):
        result = db[COLLECTION].update_one(
            {"_id": job["_id"], "fence": job.get("fence"), "status": RUNNING},
            {"$set": {"status": FAILED, "finished_at": now,
                      "error": {"code": INTERRUPTED, "message": INTERRUPTED_MESSAGE},
                      "result": {"outcome": "failed", "reason": INTERRUPTED},
                      "lease_owner": None, "lease_expires_at": None}})
        if result.matched_count:
            failed.append(job)
    return failed


def finish(db, job: dict, outcome: str, *, result: dict | None = None,
           error: dict | None = None, now=None) -> bool:
    """Move a RUNNING job to a terminal state, then honour any rerun request.

    One atomic update that returns the row as it was: if a trigger set
    `rerun_requested` before this update, the returned row says so and the
    rerun is enqueued; if it arrives after, the row is already terminal and the
    trigger creates a fresh PENDING row on its own. No rerun can be lost in
    between.
    """
    if outcome not in TERMINAL:
        raise ValueError("not a terminal outcome: %r" % outcome)
    now = now or _now()
    before = db[COLLECTION].find_one_and_update(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING},
        {"$set": {"status": outcome, "finished_at": now, "result": result or {},
                  "error": error, "lease_owner": None, "lease_expires_at": None}},
        return_document=ReturnDocument.BEFORE)
    if not before:
        return False
    if before.get("rerun_requested"):
        _requeue_rerun(db, before)
    return True


def _requeue_rerun(db, row: dict) -> None:
    """A run asked for this node while it was running: run it again for them.
    Only explicit runs set `rerun_requested`, so this is never automatic work;
    with no run id recorded (a row from before 29 Sep) nothing is re-queued."""
    run_ids = list(row.get("rerun_run_ids") or [])
    if not run_ids:
        return
    triggers = row.get("rerun_triggers") or [trigger("rerun", "changed while running")]
    enqueue(db, row["account_id"], row["node_id"],
            {**triggers[0], "demand": bool(row.get("rerun_demand"))},
            priority=int(row.get("rerun_priority") or PRIORITY_UPSTREAM),
            force=bool(row.get("rerun_force")), full=bool(row.get("rerun_full")),
            rank=int(row.get("rank") or 0), run_id=run_ids[0])
    extra = triggers[1:]
    db[COLLECTION].update_one(
        {"account_id": row["account_id"], "node_id": row["node_id"],
         "status": PENDING},
        {"$push": {"triggers": {"$each": extra}},
         "$addToSet": {"run_ids": {"$each": run_ids}}})


def live(db, account_id: str) -> dict:
    """node_id -> its live job row, for one account."""
    return {j["node_id"]: j for j in db[COLLECTION].find(
        {"account_id": account_id, "status": {"$in": list(LIVE)}})}


def history(db, account_id: str, limit: int = 20) -> list:
    rows = db[COLLECTION].find({"account_id": account_id}).sort(
        "requested_at", DESCENDING).limit(max(1, min(int(limit), 100)))
    return list(rows)


def attach_run(db, job_id, run_id) -> None:
    """Record that another run is also waiting on this live job."""
    db[COLLECTION].update_one({"_id": job_id, "status": {"$in": list(LIVE)}},
                              {"$addToSet": {"run_ids": run_id}})


def clear_not_runnable(db, account_id: str, node_id: str) -> None:
    """Forget which workers handed this node's queued job back for missing
    files - called once the files are on disk again."""
    db[COLLECTION].update_one(
        {"account_id": account_id, "node_id": node_id, "status": PENDING},
        {"$set": {"not_runnable_on": [], "released_reason": None}})


def set_progress(db, job: dict, done: int, total: int, label: str = "") -> None:
    db[COLLECTION].update_one(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING},
        {"$set": {"progress": {"done": int(done), "total": int(total),
                               "label": label, "at": _now()}}})


def cancel_run(db, run_id) -> dict:
    """Cancel what this run is still waiting for. A job another run also asked
    for stays, without this run; RUNNING jobs are left to finish."""
    col = db[COLLECTION]
    cancelled = col.update_many(
        {"run_ids": [run_id], "status": PENDING},
        {"$set": {"status": CANCELLED, "finished_at": _now(),
                  "result": {"outcome": "cancelled"}}}).modified_count
    detached = col.update_many(
        {"run_ids": run_id, "status": PENDING},
        {"$pull": {"run_ids": run_id}}).modified_count
    return {"cancelled": cancelled, "detached": detached}


def cancel_unbound(db) -> int:
    """Cancel queued jobs no run asked for - the automatic triggers of the
    release before 29 Sep. Their nodes stay stale, which the admin page shows."""
    return db[COLLECTION].update_many(
        {"status": PENDING, "$or": [{"run_ids": {"$exists": False}},
                                    {"run_ids": {"$size": 0}}]},
        {"$set": {"status": CANCELLED, "finished_at": _now(),
                  "result": {"outcome": "cancelled",
                             "reason": "queued automatically before regeneration "
                                       "became explicit"}}}).modified_count


# ---------------------------------------------------------------------------
# Queue control: paused by an admin, or by the engine on an exhausted quota.
#
# An admin's pause holds until an admin lifts it. The engine's does not: a
# quota refusal is a window that closes on its own, and a pause with no way out
# meant one 429 overnight stopped every account until somebody opened the
# Pipeline tab the next morning. So the engine's pause carries the time it
# expires and the worker lifts it then - see `lift_expired_pause`.
# ---------------------------------------------------------------------------

def queue_state(db) -> dict:
    doc = db[CONTROL].find_one({"_id": QUEUE_DOC}) or {}
    return {"paused": bool(doc.get("paused")), "reason": doc.get("reason"),
            "paused_at": doc.get("paused_at"), "paused_by": doc.get("paused_by"),
            "resumed_at": doc.get("resumed_at"),
            "resume_after": doc.get("resume_after")}


def pause(db, reason: str, by: str = "system", seconds: int = 0) -> bool:
    """Pause the queue. False when it was already paused (the first reason is
    kept - it is the one that explains the pause).

    `seconds` sets when it lifts by itself. 0 means never: that is an admin's
    pause, and the one the engine falls back to when the window is configured
    away.
    """
    if queue_state(db)["paused"]:
        return False
    until = _now() + timedelta(seconds=seconds) if seconds > 0 else None
    if until:
        reason = "%s - resumes by itself at %s unless resumed sooner" % (
            str(reason)[:220], until.strftime("%H:%M UTC"))
    db[CONTROL].update_one(
        {"_id": QUEUE_DOC},
        {"$set": {"paused": True, "reason": str(reason)[:300], "paused_at": _now(),
                  "paused_by": by, "resume_after": until}},
        upsert=True)
    logger.warning("regen: queue paused by %s - %s", by, reason)
    return True


def lift_expired_pause(db) -> bool:
    """Resume a pause whose window has passed. True when this call lifted it.

    Conditional on the same fields it reads, so two workers polling together
    resume once between them rather than both writing `resumed_at`.
    """
    now = _now()
    result = db[CONTROL].update_one(
        {"_id": QUEUE_DOC, "paused": True,
         "resume_after": {"$ne": None, "$lte": now}},
        {"$set": {"paused": False, "resumed_at": now,
                  "resumed_by": "engine:quota-window", "resume_after": None}})
    if result.modified_count:
        logger.warning("regen: queue resumed - the pause window has passed")
        return True
    return False


def resume(db, by: str = "") -> None:
    db[CONTROL].update_one(
        {"_id": QUEUE_DOC},
        {"$set": {"paused": False, "resumed_at": _now(), "resumed_by": by}},
        upsert=True)
