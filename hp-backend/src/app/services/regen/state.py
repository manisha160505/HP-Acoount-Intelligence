"""The committed output of every (account, node), and what state it is in.

`node_state` is one document per (account, node). Its `current` field IS the
committed generation - the widgets, the manifest they were built from and the
fingerprint of that manifest - so committing a run is one `find_one_and_update`
that replaces `current` whole. A single-document write is atomic on a standalone
mongod, which is what the VM runs: there are no multi-document transactions to
lean on, and none are needed. A reader sees the whole of one generation or the
whole of the previous one, never a mix (audit R5).

The commit is scoped by the fence of the job doing it. A worker whose lease was
reclaimed can finish its run and try to commit; its fence no longer matches and
the write changes nothing.

Lifecycle is never stored as the truth. `derive()` works it out from the
committed fingerprint, the fingerprint the inputs produce now, the ancestors
and the live jobs, every time it is asked - a stored "CURRENT" can be wrong the
moment a file is uploaded; a derived one cannot.
"""

import logging
from datetime import UTC, datetime

from bson import ObjectId
from pymongo import DESCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.write_concern import WriteConcern

logger = logging.getLogger(__name__)

COLLECTION = "node_state"
HISTORY = "node_history"
HISTORY_KEEP = 3

NEVER_GENERATED = "NEVER_GENERATED"
CURRENT = "CURRENT"
STALE = "STALE"
GENERATING = "GENERATING"
FAILED = "FAILED"

COMPLETE = "complete"
DEGRADED = "degraded"
BLOCKED = "blocked"          # index node whose preconditions are unmet


def _now():
    return datetime.now(UTC)


def state_id(account_id: str, node_id: str) -> str:
    return "%s:%s" % (account_id, node_id)


def ensure_indexes(db) -> None:
    db[COLLECTION].create_index([("account_id", 1), ("node_id", 1)],
                                name="account_node")
    db[HISTORY].create_index([("account_id", 1), ("node_id", 1), ("rev", -1)],
                             name="account_node_rev")


def load_account(db, account_id: str) -> dict:
    """node_id -> node_state document, for one account."""
    return {d["node_id"]: d for d in db[COLLECTION].find({"account_id": account_id})}


def mark_running(db, account_id: str, node_id: str, job: dict, target: str) -> None:
    db[COLLECTION].update_one(
        {"_id": state_id(account_id, node_id)},
        {"$set": {"running": {"job_id": job["_id"], "fence": job["fence"],
                              "target_fingerprint": target, "started_at": _now()},
                  "updated_at": _now()},
         "$setOnInsert": {"account_id": account_id, "node_id": node_id,
                          "current": None, "last_failure": None, "rev": 0}},
        upsert=True)


def commit(db, account_id: str, node_id: str, fence: str, current: dict) -> dict | None:
    """Make `current` the committed generation, if this run still holds the node.

    Journaled (`j: true`): the job row is marked SUCCEEDED right after this, and
    a host crash must not leave a "succeeded" job pointing at a flip that was
    never made durable.
    """
    col = db[COLLECTION].with_options(write_concern=WriteConcern(j=True))
    generation = dict(current)
    generation.setdefault("generation_id", ObjectId())
    generation.setdefault("generated_at", _now())
    return col.find_one_and_update(
        {"_id": state_id(account_id, node_id), "running.fence": fence},
        {"$set": {"current": generation, "running": None, "last_failure": None,
                  "updated_at": _now()},
         "$inc": {"rev": 1}},
        return_document=ReturnDocument.AFTER)


def clear_running(db, account_id: str, node_id: str, job_id) -> None:
    """Drop the running marker, only if it still belongs to this job."""
    db[COLLECTION].update_one(
        {"_id": state_id(account_id, node_id), "running.job_id": job_id},
        {"$set": {"running": None, "updated_at": _now()}})


def record_failure(db, account_id: str, node_id: str, job_id, fingerprint: str,
                   code: str, message: str) -> None:
    """Note that the run for `fingerprint` failed. The committed output is untouched.

    `count` counts consecutive failures for the same fingerprint; it drives the
    sweep's retry backoff and resets when the inputs change.
    """
    col = db[COLLECTION]
    doc = col.find_one({"_id": state_id(account_id, node_id)}, {"last_failure": 1}) or {}
    previous = doc.get("last_failure") or {}
    count = int(previous.get("count") or 0) + 1 \
        if previous.get("fingerprint") == fingerprint else 1
    try:
        col.update_one(
            {"_id": state_id(account_id, node_id),
             "$or": [{"running": None}, {"running.job_id": job_id}]},
            {"$set": {"last_failure": {"fingerprint": fingerprint, "code": code,
                                       "message": str(message)[:500], "at": _now(),
                                       "job_id": job_id, "count": count},
                      "running": None, "updated_at": _now()},
             "$setOnInsert": {"account_id": account_id, "node_id": node_id,
                              "current": None, "rev": 0}},
            upsert=True)
    except DuplicateKeyError:
        # The document exists and another job now holds the node: this
        # failure belongs to a superseded run and must not overwrite its state.
        logger.info("regen: failure of superseded job %s on %s/%s not recorded",
                    job_id, account_id, node_id)


def write_history(db, account_id: str, node_id: str, generation: dict, rev: int) -> None:
    """Best-effort audit copy, capped. Never read to serve anything."""
    try:
        db[HISTORY].insert_one({"account_id": account_id, "node_id": node_id,
                                "rev": rev, "generation": generation,
                                "archived_at": _now()})
        old = list(db[HISTORY].find({"account_id": account_id, "node_id": node_id},
                                    {"_id": 1}).sort("rev", DESCENDING).skip(HISTORY_KEEP))
        if old:
            db[HISTORY].delete_many({"_id": {"$in": [d["_id"] for d in old]}})
    except Exception:
        logger.exception("regen: could not archive %s/%s rev %s", account_id, node_id, rev)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

def is_usable_upstream(entry: dict) -> bool:
    """Whether a node's output may be built on. Degraded counts; blocked does not."""
    return entry["lifecycle"] == CURRENT


def derive(graph, states: dict, expected_fps: dict, live_jobs: dict) -> dict:
    """node_id -> {lifecycle, reasons, blocked_by} for one account.

    Walked in dependency order so a node can see its ancestors' result:

      GENERATING       a RUNNING job exists for the node
      CURRENT          committed fingerprint == expected, not blocked, and every
                       upstream node CURRENT
      FAILED           the last failure was for the expected fingerprint (the
                       output shown is the last committed one)
      NEVER_GENERATED  nothing committed
      STALE            anything else - the reasons say which input or ancestor

    CURRENT is checked before FAILED: a run that failed and was then superseded
    by a successful one for the same inputs is current, whatever the failure
    record still says.
    """
    out = {}
    for nid in graph.order:
        node = graph[nid]
        doc = states.get(nid) or {}
        current = doc.get("current") or None
        failure = doc.get("last_failure") or None
        job = live_jobs.get(nid)
        want = expected_fps.get(nid)

        bad_up = [up for up in node.upstream
                  if out.get(up, {}).get("lifecycle") != CURRENT]
        reasons, blocked_by = [], None

        if job and job.get("status") == "RUNNING":
            lifecycle = GENERATING
        elif (current and current.get("fingerprint")
              and current.get("fingerprint") == want
              and current.get("quality") != BLOCKED and not bad_up):
            lifecycle = CURRENT
        elif failure and failure.get("fingerprint") == want:
            lifecycle = FAILED
            reasons.append("generation failed: %s" % (failure.get("code") or "error"))
        elif not current:
            lifecycle = NEVER_GENERATED
        else:
            lifecycle = STALE
            if not current.get("fingerprint"):
                reasons.append("legacy output - not yet verified against its inputs")
            elif current.get("fingerprint") != want:
                reasons.append("inputs changed")
            if current.get("quality") == BLOCKED:
                reasons.append("index preconditions not met")

        if bad_up:
            blocked_by = bad_up
            reasons.append("waiting on %s" % ", ".join(
                "%s (%s)" % (up, out[up]["lifecycle"].lower()) for up in bad_up))

        out[nid] = {"lifecycle": lifecycle, "reasons": reasons,
                    "blocked_by": blocked_by,
                    # Built for exactly these inputs, but its preconditions were
                    # not met (an index with no required widget). Nothing will
                    # change until an input does, so nothing should retry it.
                    "blocked": bool(current and current.get("quality") == BLOCKED
                                    and current.get("fingerprint") == want),
                    "quality": (current or {}).get("quality"),
                    "generated_at": (current or {}).get("generated_at"),
                    "generation_id": (current or {}).get("generation_id"),
                    "fingerprint": (current or {}).get("fingerprint"),
                    "last_error": ({"code": failure.get("code"),
                                    "message": failure.get("message"),
                                    "at": failure.get("at")} if failure else None),
                    "job": ({"id": str(job.get("_id")), "status": job.get("status")}
                            if job else None)}
    return out


def feature_lifecycle(graph, derived: dict, feature_id: str) -> str:
    states = [derived[n]["lifecycle"] for n in graph.nodes_for_feature(feature_id)
              if graph[n].kind == "producer"]
    if not states:
        return NEVER_GENERATED
    for level in (GENERATING, FAILED, STALE):
        if level in states:
            return level
    if all(s == NEVER_GENERATED for s in states):
        return NEVER_GENERATED
    if NEVER_GENERATED in states:
        return STALE
    return CURRENT
