"""A durable, coalesced queue for index builds.

Ingest is long - one LLM call per chunk for entity extraction - and it must
survive the process it was requested in. `BackgroundTasks` would not: a Render
restart mid-ingest drops the task silently, leaving an index half-built and
nothing recording that it happened.

So a job is a row in Mongo, and the worker leases it:

    PENDING --lease--> RUNNING --> COMPLETED
                          |
                          +-----> FAILED (attempts exhausted)

Two properties matter more than throughput:

  * **At most one live job per (account_id, index).** A trigger arriving while
    one is PENDING coalesces into it - that is the debounce, and it is what
    stops a regeneration batch of eleven widgets queuing eleven builds. A
    trigger arriving while one is RUNNING sets `rerun_requested`, so the change
    is picked up once rather than racing the build in flight.

  * **Leases expire.** A worker that dies mid-job leaves RUNNING behind; without
    an expiry that row is stuck forever and the index never rebuilds. The lease
    lets another worker reclaim it.
"""

import logging
import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

COLLECTION = "retrieval_jobs"

PENDING = "PENDING"
RUNNING = "RUNNING"
COMPLETED = "COMPLETED"
FAILED = "FAILED"

LEASE_SECONDS = 1800          # an ingest may legitimately run a long time
MAX_ATTEMPTS = 3

WORKER_ID = "%s:%d:%s" % (socket.gethostname(), os.getpid(), uuid.uuid4().hex[:6])


def _now():
    return datetime.now(timezone.utc)


def ensure_indexes():
    db = get_db()
    db[COLLECTION].create_index([("account_id", 1), ("index", 1), ("status", 1)])
    db[COLLECTION].create_index([("status", 1), ("lease_expires_at", 1)])


def enqueue(account_id: str, index: str, reason: str = "", full: bool = False) -> dict:
    """Request a build. Coalesces rather than queuing a second one."""
    db = get_db()

    live = db[COLLECTION].find_one({
        "account_id": account_id, "index": index,
        "status": {"$in": [PENDING, RUNNING]}})

    if live and live.get("status") == PENDING:
        # Coalesce. A full rebuild request wins over a pending incremental one,
        # since it supersedes it.
        update = {"requested_at": _now(), "reason": reason or live.get("reason")}
        if full:
            update["full"] = True
        db[COLLECTION].update_one({"_id": live["_id"]}, {"$set": update})
        logger.info("retrieval: coalesced into pending job for %s/%s", account_id, index)
        return db[COLLECTION].find_one({"_id": live["_id"]}, {"_id": 0})

    if live and live.get("status") == RUNNING:
        db[COLLECTION].update_one(
            {"_id": live["_id"]},
            {"$set": {"rerun_requested": True, "rerun_reason": reason}})
        logger.info("retrieval: build already running for %s/%s - flagged for rerun",
                    account_id, index)
        return db[COLLECTION].find_one({"_id": live["_id"]}, {"_id": 0})

    job = {
        "account_id": account_id,
        "index": index,
        "status": PENDING,
        "reason": reason,
        "full": bool(full),
        "requested_at": _now(),
        "started_at": None,
        "finished_at": None,
        "attempts": 0,
        "last_error": None,
        "lease_owner": None,
        "lease_expires_at": None,
        "rerun_requested": False,
    }
    db[COLLECTION].insert_one(dict(job))
    logger.info("retrieval: enqueued build for %s/%s (%s)", account_id, index, reason)
    return job


def claim(worker_id: str = WORKER_ID):
    """Lease one job: a PENDING row, or a RUNNING row whose lease has expired.

    `find_one_and_update` makes the claim atomic, so two workers cannot take
    the same job.
    """
    db = get_db()
    now = _now()
    expires = now + timedelta(seconds=LEASE_SECONDS)

    claimed = db[COLLECTION].find_one_and_update(
        {"$or": [
            {"status": PENDING},
            {"status": RUNNING, "lease_expires_at": {"$lt": now}},
        ],
         "attempts": {"$lt": MAX_ATTEMPTS}},
        {"$set": {"status": RUNNING, "lease_owner": worker_id,
                  "lease_expires_at": expires, "started_at": now},
         "$inc": {"attempts": 1}},
        sort=[("requested_at", 1)],
        return_document=True,
        projection={"_id": 1, "account_id": 1, "index": 1, "attempts": 1,
                    "reason": 1, "rerun_requested": 1, "full": 1},
    )
    if claimed:
        logger.info("retrieval: %s claimed %s/%s (attempt %d)",
                    worker_id, claimed["account_id"], claimed["index"],
                    claimed.get("attempts", 1))
    return claimed


def heartbeat(job_id, worker_id: str = WORKER_ID):
    """Extend the lease of a job still being worked on."""
    get_db()[COLLECTION].update_one(
        {"_id": job_id, "lease_owner": worker_id},
        {"$set": {"lease_expires_at": _now() + timedelta(seconds=LEASE_SECONDS)}})


def complete(job_id) -> bool:
    """Finish a job. Returns True when a rerun was requested while it ran."""
    db = get_db()
    job = db[COLLECTION].find_one({"_id": job_id}, {"rerun_requested": 1,
                                                   "account_id": 1, "index": 1,
                                                   "rerun_reason": 1})
    db[COLLECTION].update_one(
        {"_id": job_id},
        {"$set": {"status": COMPLETED, "finished_at": _now(),
                  "lease_owner": None, "lease_expires_at": None,
                  "rerun_requested": False}})
    if job and job.get("rerun_requested"):
        enqueue(job["account_id"], job["index"],
                job.get("rerun_reason") or "changed while a build was running")
        return True
    return False


def fail(job_id, error: str):
    """Record a failure. Below MAX_ATTEMPTS the row returns to PENDING."""
    db = get_db()
    job = db[COLLECTION].find_one({"_id": job_id}, {"attempts": 1})
    attempts = int((job or {}).get("attempts") or 0)
    terminal = attempts >= MAX_ATTEMPTS
    db[COLLECTION].update_one(
        {"_id": job_id},
        {"$set": {"status": FAILED if terminal else PENDING,
                  "last_error": str(error)[:2000],
                  "finished_at": _now() if terminal else None,
                  "lease_owner": None, "lease_expires_at": None}})
    logger.warning("retrieval: job %s %s - %s", job_id,
                   "failed permanently" if terminal else "will retry",
                   str(error)[:200])


def status(account_id: str, index: str = None) -> list:
    db = get_db()
    query = {"account_id": account_id}
    if index:
        query["index"] = index
    return list(db[COLLECTION].find(query, {"_id": 0}).sort("requested_at", -1).limit(20))


def pending_count() -> int:
    return get_db()[COLLECTION].count_documents({"status": {"$in": [PENDING, RUNNING]}})
