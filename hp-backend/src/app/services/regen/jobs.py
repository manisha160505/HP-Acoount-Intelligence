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

LEASE_SECONDS = 1800
MAX_ATTEMPTS = 3
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


def enqueue(db, account_id: str, node_id: str, why: dict, *,
            priority: int = PRIORITY_UPSTREAM, force: bool = False,
            full: bool = False, rank: int = 0) -> dict:
    """Ask for a node to be regenerated. Coalesces; never creates a second live row.

    Returns {"job_id", "status", "coalesced"}.
    """
    col = db[COLLECTION]
    demand = bool(why.get("demand"))

    for _ in range(3):
        # 1. The node is running: note that it must run again once finished.
        running = col.find_one_and_update(
            {"account_id": account_id, "node_id": node_id, "status": RUNNING},
            {"$set": {"rerun_requested": True},
             "$push": {"rerun_triggers": why},
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
    """Deal with RUNNING rows whose lease has lapsed.

    Below MAX_ATTEMPTS the row goes back to PENDING for another worker. At
    MAX_ATTEMPTS it becomes FAILED - never left RUNNING, which is how a job used
    to block its node forever. Returns [(job, "reclaimed"|"failed")] so the
    engine can clear the node's `running` marker and record the failure.
    """
    now = now or _now()
    col = db[COLLECTION]
    out = []
    for job in list(col.find({"status": RUNNING, "lease_expires_at": {"$lt": now}})):
        exhausted = int(job.get("attempts") or 0) >= MAX_ATTEMPTS
        update = ({"$set": {"status": FAILED, "finished_at": now,
                            "error": {"code": "LEASE_EXPIRED",
                                      "message": "the worker stopped responding "
                                                 "and attempts are exhausted"},
                            "lease_owner": None, "lease_expires_at": None}}
                  if exhausted else
                  {"$set": {"status": PENDING, "fence": None, "lease_owner": None,
                            "lease_expires_at": None, "not_before": now,
                            "last_error": {"code": "LEASE_EXPIRED",
                                           "message": "the worker stopped responding"}}})
        changed = col.find_one_and_update(
            {"_id": job["_id"], "status": RUNNING, "fence": job.get("fence"),
             "lease_expires_at": {"$lt": now}},
            update, return_document=ReturnDocument.BEFORE)
        if changed:
            action = "failed" if exhausted else "reclaimed"
            logger.warning("regen: lease expired on %s/%s - %s",
                           job["account_id"], job["node_id"], action)
            out.append((changed, action))
            if exhausted and changed.get("rerun_requested"):
                _requeue_rerun(db, changed)
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
                 "not_runnable_on": {"$ne": worker_id}},
                {"$set": {"status": RUNNING, "fence": fence, "lease_owner": worker_id,
                          "lease_expires_at": now + timedelta(seconds=LEASE_SECONDS),
                          "heartbeat_at": now, "started_at": now,
                          "rerun_requested": False, "rerun_triggers": []}},
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


def release(db, job: dict, *, delay_seconds: float = 0, reason: str = "",
            not_runnable_here: bool = False, error: dict | None = None,
            now=None) -> bool:
    """Put a RUNNING job back to PENDING without finishing it."""
    now = now or _now()
    update = {"$set": {"status": PENDING, "fence": None, "lease_owner": None,
                       "lease_expires_at": None,
                       "not_before": now + timedelta(seconds=delay_seconds),
                       "released_reason": str(reason)[:300]}}
    if error:
        update["$set"]["last_error"] = error
    if not_runnable_here:
        update["$addToSet"] = {"not_runnable_on": job.get("lease_owner") or WORKER_ID}
    result = db[COLLECTION].update_one(
        {"_id": job["_id"], "fence": job["fence"], "status": RUNNING}, update)
    return result.matched_count == 1


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
    triggers = row.get("rerun_triggers") or [trigger("rerun", "changed while running")]
    enqueue(db, row["account_id"], row["node_id"],
            {**triggers[0], "demand": bool(row.get("rerun_demand"))},
            priority=int(row.get("rerun_priority") or PRIORITY_UPSTREAM),
            force=bool(row.get("rerun_force")), full=bool(row.get("rerun_full")),
            rank=int(row.get("rank") or 0))
    extra = triggers[1:]
    if extra:
        db[COLLECTION].update_one(
            {"account_id": row["account_id"], "node_id": row["node_id"],
             "status": PENDING},
            {"$push": {"triggers": {"$each": extra}}})


def live(db, account_id: str) -> dict:
    """node_id -> its live job row, for one account."""
    return {j["node_id"]: j for j in db[COLLECTION].find(
        {"account_id": account_id, "status": {"$in": list(LIVE)}})}


def history(db, account_id: str, limit: int = 20) -> list:
    rows = db[COLLECTION].find({"account_id": account_id}).sort(
        "requested_at", DESCENDING).limit(max(1, min(int(limit), 100)))
    return list(rows)
