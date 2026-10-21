# ruff: noqa: T201 - a console script; printing is its output.
"""Finish regeneration runs left RUNNING although none of their jobs is live.

Before 21 Oct a run's status was only made terminal when someone opened it
(GET /regeneration/{run_id}), so a run nobody opened - scripts/vm_runs/*, a
Submit whose tab was closed - stayed RUNNING in `regen_runs` for good. The job
path now settles runs itself; this script settles the ones left from before.

Run from hp-backend (on the VM: inside the backend container):

  1. Dry run - writes nothing:
       python scripts/finalize_stuck_runs.py

     Prints the database, then every run stored RUNNING with no PENDING or
     RUNNING job, and the status it would get (SUCCEEDED, or
     COMPLETED_WITH_FAILURES when one of its jobs FAILED).

  2. Apply - writes those statuses:
       python scripts/finalize_stuck_runs.py --apply --target-db <DB_NAME>

     --target-db must equal the DB_NAME this process is configured with, so a
     shell pointed at the wrong database refuses instead of writing to it.

Safe to run again: each write is conditional on the run still being RUNNING
with no live job (the same `runs.settle` the job path calls), so a run that a
worker settled, or that picked up a live job, in the meantime is left alone.
Runs that still have live jobs are never touched.
"""

import argparse
import os
import sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, get_db
from app.services.regen import runs


def _target() -> str:
    u = urlsplit(settings.MONGODB_URI)
    return "%s/%s" % (u.hostname or settings.MONGODB_URI, settings.DB_NAME)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the statuses")
    ap.add_argument("--target-db", help="with --apply: must equal the configured DB_NAME")
    ap.add_argument("--limit", type=int, default=1000,
                    help="at most this many runs, oldest first (default 1000)")
    args = ap.parse_args()

    print("Database: %s" % _target())
    if args.apply and args.target_db != settings.DB_NAME:
        print("Refusing: --target-db %r does not match the configured DB_NAME %r (%s)."
              % (args.target_db, settings.DB_NAME, _target()), file=sys.stderr)
        return 2

    connect_to_mongo()
    db = get_db()

    stuck = runs.stuck(db, limit=args.limit)
    print("\nRuns stored RUNNING with no live job: %d" % len(stuck))
    by_status = {}
    for run in stuck:
        by_status[run["would_be"]] = by_status.get(run["would_be"], 0) + 1
        accounts = run.get("account_ids") or []
        print("  %s  created %s  by %-20s  %3d account(s)  ->  %s"
              % (run["_id"], run.get("created_at"), run.get("actor") or "?",
                 len(accounts), run["would_be"]))
    for status, n in sorted(by_status.items()):
        print("  %-24s %d" % (status, n))

    if not args.apply:
        print("\nNothing was written. Re-run with --apply --target-db %s to write these."
              % settings.DB_NAME)
        return 0
    if not stuck:
        print("\nNothing to write.")
        return 0

    changed = runs.settle(db, [run["_id"] for run in stuck])
    skipped = len(stuck) - len(changed)
    print("\nDone: %d run(s) settled%s." % (
        len(changed), (", %d left alone (changed meanwhile)" % skipped) if skipped else ""))
    for run_id, status in changed.items():
        print("  %s  ->  %s" % (run_id, status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
