"""Index state: what is indexed, at what version, and whether it can be trusted.

There is **one workspace per (account, index)**. It names that account's KV,
graph and doc-status collections, and it is also the partition value separating
its vectors from every other account's inside the three shared vector
collections - so it is an isolation boundary, not just a label.

A workspace no longer costs any Atlas search index capacity of its own (the
three shared vector indexes serve every account), but builds are still not
atomic: the workspace is stable rather than numbered per build, so a full
rebuild replaces data in place. The two paths therefore still differ in what
they can promise:

  **Incremental update** - the normal case. Fingerprints identify the documents
  that actually changed; only those are deleted and re-inserted, under their
  own stable `doc_id`. Everything else is untouched. A failure here damages at
  most the documents being replaced, and the state records which, so the rest
  of the index keeps answering.

  **Full rebuild** - admin action only. The workspace is dropped and rebuilt in
  place. **This is not atomic and there is no rollback.** While it runs there is
  no queryable index, and if it fails there is nothing to fall back to. The
  status says so: `BUILDING` throughout, `FAILED` if it does not finish. Nothing
  here claims otherwise, because on this tier it would be a lie.
"""

import logging
from datetime import datetime, timezone

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

COLLECTION = "retrieval_index_state"

READY = "READY"
BUILDING = "BUILDING"
STALE = "STALE"
FAILED = "FAILED"
BLOCKED = "BLOCKED"
# Deliberately retired: the workspace was dropped to free Atlas vector-index
# capacity for another index. Distinct from FAILED, because nothing went wrong,
# and distinct from BLOCKED, because the data is there - only the index is not.
# It exists so that a retired index cannot be silently recreated by an ordinary
# query or data change, which would take the capacity straight back.
RETIRED = "RETIRED"

STATUSES = (READY, BUILDING, STALE, FAILED, BLOCKED, RETIRED)

FULL = "full"
INCREMENTAL = "incremental"


def _now():
    return datetime.now(timezone.utc)


def get(account_id: str, index: str) -> dict:
    db = get_db()
    found = db[COLLECTION].find_one(
        {"account_id": account_id, "index": index}, {"_id": 0})
    if found:
        return found
    return {
        "account_id": account_id,
        "index": index,
        "status": BLOCKED,
        "workspace": None,
        "version": 0,
        "documents": {},
        "last_built_at": None,
        "last_build_mode": None,
        "last_error": None,
        "build_count": 0,
        "damaged_documents": [],
    }


def save(state: dict) -> dict:
    db = get_db()
    state["updated_at"] = _now()
    db[COLLECTION].update_one(
        {"account_id": state["account_id"], "index": state["index"]},
        {"$set": state}, upsert=True)
    return state


def set_status(account_id: str, index: str, status: str, error=None) -> dict:
    if status not in STATUSES:
        raise ValueError("unknown status %r" % status)
    state = get(account_id, index)
    state["status"] = status
    state["last_error"] = error
    return save(state)


def begin_build(account_id: str, index: str, mode: str) -> dict:
    """Mark a build in progress.

    For a full rebuild this is the honest warning that nothing is queryable:
    the workspace is about to be dropped, so `BUILDING` means unavailable, not
    "serving the old copy".
    """
    from app.services.retrieval.client import workspace_name

    state = get(account_id, index)
    state["workspace"] = workspace_name(account_id, index)
    state["status"] = BUILDING
    state["last_build_mode"] = mode
    state["last_error"] = None
    save(state)
    logger.info("retrieval: %s %s build started for account %s (workspace %s)",
                index, mode, account_id, state["workspace"])
    return state


def finish_build(account_id: str, index: str, documents: dict, mode: str) -> dict:
    """Record a successful build and the fingerprints it actually produced."""
    state = get(account_id, index)
    state["documents"] = documents
    state["version"] = int(state.get("version") or 0) + 1
    state["status"] = READY
    state["last_error"] = None
    state["last_built_at"] = _now()
    state["last_build_mode"] = mode
    state["build_count"] = int(state.get("build_count") or 0) + 1
    state["damaged_documents"] = []
    save(state)
    logger.info("retrieval: %s %s build finished for account %s - v%d, %d documents",
                index, mode, account_id, state["version"], len(documents))
    return state


def record_document(account_id: str, index: str, doc_id: str,
                    fingerprint: dict) -> None:
    """Record one document as indexed, the moment it finishes.

    Without this, a build's progress exists only in memory until the whole run
    completes, and anything that stops the process - the machine running out of
    memory, a deploy, an operator pressing Ctrl-C - discards every document
    already extracted. That is expensive in exactly the case where it hurts
    most: a 19-document filing corpus killed at document 10 would re-extract all
    ten from scratch.

    Written as a targeted `$set` on the one document's key rather than rewriting
    the map, so a concurrent reader never sees a half-written state, and the
    status is deliberately left as BUILDING - one finished document does not
    make the index queryable.
    """
    get_db()[COLLECTION].update_one(
        {"account_id": account_id, "index": index},
        {"$set": {"documents.%s" % doc_id: fingerprint,
                  "updated_at": _now()}},
        upsert=True)


def record_incremental(account_id: str, index: str, documents: dict,
                       applied: dict, damaged=None) -> dict:
    """Record an incremental update, including any document left inconsistent.

    `documents` is the fingerprint map as it now stands - only the entries that
    were successfully re-indexed are updated, so a document that failed keeps
    its old fingerprint and will be retried on the next run rather than being
    silently considered current.
    """
    state = get(account_id, index)
    state["documents"] = documents
    state["version"] = int(state.get("version") or 0) + 1
    state["last_built_at"] = _now()
    state["last_build_mode"] = INCREMENTAL
    state["build_count"] = int(state.get("build_count") or 0) + 1
    state["last_applied"] = applied
    state["damaged_documents"] = list(damaged or [])
    # A partial failure leaves the index usable but not wholly current.
    state["status"] = STALE if damaged else READY
    state["last_error"] = (
        "%d document(s) could not be updated: %s" % (len(damaged), ", ".join(damaged[:5]))
        if damaged else None)
    save(state)
    logger.info("retrieval: %s incremental update for account %s - "
                "%d added, %d changed, %d removed, %d damaged",
                index, account_id, len(applied.get("added") or []),
                len(applied.get("changed") or []), len(applied.get("removed") or []),
                len(damaged or []))
    return state


def fail_build(account_id: str, index: str, error: str, mode: str = None) -> dict:
    """Record a failed build.

    After a failed FULL rebuild the workspace has already been dropped, so there
    is nothing to serve - status is FAILED and stays that way until someone
    rebuilds. After a failed incremental update the rest of the index is intact,
    so status is STALE.
    """
    state = get(account_id, index)
    mode = mode or state.get("last_build_mode")
    state["status"] = FAILED if mode == FULL else (
        STALE if state.get("workspace") else FAILED)
    state["last_error"] = str(error)[:2000]
    save(state)
    logger.warning("retrieval: %s %s build failed for account %s - %s (status %s)",
                   index, mode, account_id, str(error)[:200], state["status"])
    return state


def diff(account_id: str, index: str, fingerprints: dict) -> dict:
    """What changed since the last successful build."""
    state = get(account_id, index)
    stored = state.get("documents") or {}
    return {
        "added": [k for k in fingerprints if k not in stored],
        "changed": [k for k in fingerprints
                    if k in stored
                    and stored[k].get("fingerprint") != fingerprints[k]["fingerprint"]],
        "removed": [k for k in stored if k not in fingerprints],
        "unchanged": [k for k in fingerprints
                      if k in stored
                      and stored[k].get("fingerprint") == fingerprints[k]["fingerprint"]],
    }


def has_index(account_id: str, index: str) -> bool:
    """Whether anything has ever been built and is still supposed to exist."""
    state = get(account_id, index)
    return bool(state.get("workspace")) and state.get("status") in (READY, STALE)


def is_resumable(account_id: str, index: str) -> bool:
    """Whether a build stopped part-way and its finished documents still stand.

    A build that is interrupted - the machine runs out of memory, the process is
    deployed over, an operator presses Ctrl-C - leaves the status at BUILDING,
    because nothing ever reached `finish_build`. The workspace and every
    document that completed are still there, and `record_document` wrote each
    one's fingerprint as it landed.

    Without this, `has_index` reads BUILDING as "nothing exists", the next run
    is promoted to a full rebuild, and the first thing it does is drop the
    workspace - discarding the finished documents *and* the extraction cache
    that made them cheap. A 19-document filing corpus killed at document 11
    would pay for all 19 again.

    Concurrency is not the risk it looks like: index builds are coalesced
    through the job queue, so two builds of the same index do not run at once.
    Resuming what is demonstrably present is the better failure mode.
    """
    state = get(account_id, index)
    return (state.get("status") == BUILDING
            and bool(state.get("workspace"))
            and bool(state.get("documents")))


def workspace(account_id: str, index: str):
    return get(account_id, index).get("workspace")


def note_generation_error(account_id: str, index: str, error: str) -> dict:
    """Record that the feature this index feeds failed to regenerate.

    Kept separate from `last_error`, and it does NOT change `status`: the index
    itself built correctly and is queryable, so calling it FAILED would be
    wrong. What failed is the thing downstream of it, and the UI shows that as
    its own line rather than as an index fault.
    """
    state = get(account_id, index)
    state["generation_error"] = str(error)[:2000]
    state["generation_error_at"] = _now()
    return save(state)


def clear_generation_error(account_id: str, index: str) -> dict:
    state = get(account_id, index)
    state.pop("generation_error", None)
    state.pop("generation_error_at", None)
    save(state)
    get_db()[COLLECTION].update_one(
        {"account_id": account_id, "index": index},
        {"$unset": {"generation_error": "", "generation_error_at": ""}})
    return state


def retire(account_id: str, index: str, reason: str = "") -> dict:
    """Mark an index retired after its workspace has been dropped.

    The stored fingerprints are cleared with it: whatever is rebuilt later
    starts from nothing, so a partial rebuild cannot believe documents are
    already indexed when the collections holding them are gone.

    The published output and the evidence registry are left alone - they live
    outside the workspace, so the feature keeps rendering its last build with
    working citations.
    """
    state = get(account_id, index)
    state["status"] = RETIRED
    state["last_error"] = reason or "the workspace was dropped"
    state["documents"] = {}
    state["retired_at"] = _now()
    save(state)
    logger.warning("retrieval: %s retired for account %s - %s",
                   index, account_id, state["last_error"])
    return state


def is_retired(account_id: str, index: str) -> bool:
    return get(account_id, index).get("status") == RETIRED
