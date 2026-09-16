# -*- coding: utf-8 -*-
"""Rebuild one retrieval index from the command line, then regenerate its feature.

Run from hp-backend:
    python scripts/rebuild_index.py <account name> <index> [--full] [--yes]

Why this exists: the only way to start a full rebuild was
`POST /accounts/{id}/retrieval/{index}/rebuild` (`widgets.py`), which needs the
API up, an admin token, and the job worker running to pick the job up. A
retired index cannot be brought back any other way - `update_index` blocks an
incremental refresh of one on purpose - so bringing one back meant standing up
the whole stack.

It drives the real job queue rather than calling `update_index` directly, so
this takes the same path the worker takes in production: `run_job` builds the
index AND then runs the registered generator, which is what re-writes the
feature's widget. Calling `update_index` by hand would do the first half and
silently skip the second, leaving a fresh index under a stale widget.

    --full   drop and rebuild in place. Mandatory for a RETIRED index.
             There is no rollback: the index is unavailable while it runs, and
             a failure leaves no previous copy. What survives either way is the
             published widget and the evidence registry - both live outside the
             workspace - so the feature keeps rendering its last build.

Account-agnostic: the account is named on the command line and nothing about
any particular account is assumed here.
"""

import argparse
import io
import logging
import os
import sys
import time
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                              errors="replace", line_buffering=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
# LightRAG, httpx and pymongo are extremely chatty at INFO - one line per chunk
# and per request - and would bury the progress this script reports.
for _noisy in ("lightrag", "httpx", "httpcore", "openai", "pymongo"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

from app.config.settings import settings  # noqa: E402
from app.database.mongodb import connect_to_mongo, get_db  # noqa: E402
from app.services.retrieval import ingest, jobs, query, registry  # noqa: E402

logger = logging.getLogger("rebuild_index")


def _missing_dataset_files(db, account_id, index):
    """(dataset_key, stored path) for every registered file not on this machine.

    Checked against the datasets this index actually declares, so an unrelated
    missing file elsewhere in the account does not block an index that never
    reads it.
    """
    from app.services.extractors.datasets import find_file_path

    declared = set(registry.spec(index).get("datasets") or [])
    missing = []
    for row in db["account_data_files"].find({"account_id": account_id,
                                              "status": "active"}):
        key = row.get("dataset_key") or row.get("category")
        if declared and key not in declared:
            continue
        path = row.get("file_path")
        if path and not find_file_path(path):
            missing.append((key, path))
    return missing


def jobs_release(db, account_id, index):
    """Clear PENDING/RUNNING rows for one index so a fresh run can claim.

    Scoped to this account and index, and it resets `attempts` too: an
    interrupted run still incremented it, and three interruptions would
    otherwise put the job past MAX_ATTEMPTS and make it permanently
    unclaimable.
    """
    result = db[jobs.COLLECTION].update_many(
        {"account_id": account_id, "index": index,
         "status": {"$in": [jobs.PENDING, jobs.RUNNING]}},
        {"$set": {"status": "FAILED", "lease_owner": None,
                  "lease_expires_at": None, "attempts": 0,
                  "finished_at": datetime.now(UTC),
                  "last_error": "released by rebuild_index.py --release-stale-job"}})
    return result.modified_count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", help="account name, e.g. Astra")
    parser.add_argument("index", help="index key, e.g. executive_dashboard")
    parser.add_argument("--full", action="store_true",
                        help="drop and rebuild in place (required if RETIRED)")
    parser.add_argument("--yes", action="store_true",
                        help="skip the confirmation prompt")
    parser.add_argument("--release-stale-job", action="store_true",
                        help="take over a job row orphaned by an interrupted "
                             "run instead of waiting out its 30-minute lease")
    parser.add_argument("--allow-missing-files", action="store_true",
                        help="build even though registered dataset files are "
                             "not on this machine (normally a hard stop)")
    args = parser.parse_args()

    connect_to_mongo()
    db = get_db()

    account = db["accounts"].find_one({"name": args.account})
    if not account:
        raise SystemExit("no account named %r" % args.account)
    account_id = str(account["_id"])

    try:
        registry.spec(args.index)
    except registry.UnknownIndex as exc:
        raise SystemExit(str(exc))

    before = query.status(account_id, args.index)
    print("account   : %s (%s)" % (account.get("name"), account_id))
    print("index     : %s is %s, v%s, %s document(s)"
          % (args.index, before["status"], before.get("version"),
             before.get("documents")))
    print("workspace : %s" % before.get("workspace"))
    print("model     : %s%s"
          % (settings.OPENAI_MODEL_NAME,
             " (retrieval: %s)" % settings.OPENAI_RETRIEVAL_MODEL
             if settings.OPENAI_RETRIEVAL_MODEL else ""))

    # Checked before anything is queued rather than after: a blocked build that
    # has already been enqueued leaves a job row to clean up for nothing.
    ok, reason = registry.preconditions(db, account_id, args.index)
    if not ok:
        raise SystemExit("blocked: %s" % reason)

    if before["status"] == "RETIRED" and not args.full:
        raise SystemExit(
            "this index is retired - its workspace was dropped, so only "
            "--full can bring it back")

    # A registered file that is not on this machine is a WARNING inside
    # `read_dataset_records(strict=False)`, and the build proceeds on whatever
    # is left. That is right for an optional dataset and badly wrong here: the
    # first run of this script was started one directory up, every filing
    # resolved to nothing, and it began a 43-minute rebuild on 7 documents
    # instead of 19 - which would then have regenerated the feature's widget
    # from a corpus with no filings in it at all.
    #
    # So the missing files are counted BEFORE anything is queued, and a build
    # that cannot see its own inputs refuses to start.
    missing = _missing_dataset_files(db, account_id, args.index)
    if missing and not args.allow_missing_files:
        print()
        print("%d registered file(s) are not on this machine:" % len(missing))
        for dataset_key, path in missing[:8]:
            print("   %-22s %s" % (dataset_key, path))
        if len(missing) > 8:
            print("   ... and %d more" % (len(missing) - 8))
        raise SystemExit(
            "refusing to build an index that cannot see its own inputs. "
            "Dataset paths are resolved against the working directory, so run "
            "this from hp-backend/ - or pass --allow-missing-files if you "
            "really mean to index without them.")

    documents = registry.build_documents(account_id, args.index)
    print("corpus    : %d document(s), %d evidence row(s), %d chars"
          % (len(documents), sum(len(d.evidence_rows) for d in documents),
             sum(len(d.text) for d in documents)))
    generates = registry.generates(args.index)
    print("generator : %s" % ((generates or {}).get("generator") or "none"))
    print()

    if args.full and not args.yes:
        print("A full rebuild DROPS the index and rebuilds it in place. It is "
              "unavailable while it runs and a failure leaves no previous copy.")
        print("The published widget and the evidence registry are untouched.")
        if input("Type the index name to continue: ").strip() != args.index:
            raise SystemExit("aborted")
        print()

    jobs.ensure_indexes()

    # A build killed with Ctrl+C leaves its row RUNNING and leased for
    # LEASE_SECONDS (30 minutes), because nothing got the chance to release it.
    # `claim()` will not touch a live lease - correctly, since it cannot tell a
    # dead worker from a slow one - so the next run is locked out for half an
    # hour. This releases it deliberately, and only when asked.
    if args.release_stale_job:
        released = jobs_release(db, account_id, args.index)
        print("released  : %d orphaned job row(s)" % released)

    jobs.enqueue(account_id, args.index,
                 reason="rebuild_index.py", full=args.full)
    claimed = jobs.claim()
    if not claimed:
        raise SystemExit(
            "could not claim the job - a worker or another run already holds "
            "it. If a previous run was interrupted, its lease survives it for "
            "up to 30 minutes; pass --release-stale-job to take it over now.")

    print("building - an LLM call per chunk, so expect tens of minutes")
    started = time.time()
    try:
        stats = ingest.run_job(claimed)
    except KeyboardInterrupt:
        print("\ninterrupted - finished documents are recorded, so re-running "
              "this resumes rather than starting over")
        return 1

    print()
    print("=" * 72)
    print("finished in %.1f minute(s)" % ((time.time() - started) / 60.0))
    if stats.get("blocked"):
        print("  blocked: %s" % stats["blocked"])
        return 1
    for key in ("mode", "added", "changed", "removed", "unchanged", "skipped",
                "damaged", "duration_seconds"):
        if key in stats:
            print("  %-18s %s" % (key, stats[key]))
    print("  %-18s %s" % ("generator", stats.get("generated")))

    after = query.status(account_id, args.index)
    print()
    print("index now : %s, v%s, %s document(s), built %s"
          % (after["status"], after.get("version"), after.get("documents"),
             after.get("last_built_at")))
    if after.get("damaged_documents"):
        print("damaged   : %s" % after["damaged_documents"])
    return 0 if after["status"] in ("READY", "STALE") else 1


if __name__ == "__main__":
    sys.exit(main())
