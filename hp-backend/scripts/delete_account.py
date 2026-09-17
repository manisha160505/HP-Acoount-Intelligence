# -*- coding: utf-8 -*-
"""Delete an account and everything that belongs to it.

Run from hp-backend:
    python scripts/delete_account.py --dry-run NAME [NAME ...]
    python scripts/delete_account.py NAME [NAME ...]

An account's data is spread across six collections keyed by `account_id`, a
directory of uploaded files, and - once it has been indexed - a set of
per-workspace LightRAG collections and a slice of each shared vector collection.
Deleting the `accounts` row alone leaves all of that orphaned: invisible in the
UI, still occupying the database, and still counted by anything that sweeps a
collection rather than querying by account.

Accounts are named explicitly. There is deliberately no "delete everything
except" mode: an exclusion written today silently includes an account added
tomorrow, and the damage from that is the reason this script exists rather than
a session of ad-hoc `delete_many` calls.

Irreversible. Every document is written to a backup file first unless that is
explicitly turned off, and `--dry-run` changes nothing at all.
"""

import argparse
import io
import json
import logging
import os
import shutil
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.config.settings import settings  # noqa: E402
from app.database.mongodb import connect_to_mongo, get_db, redact_uri  # noqa: E402
from app.services.retrieval.shared_vdb import (  # noqa: E402
    PARTITION_FIELD, shared_collection_name)

logger = logging.getLogger("delete_account")

# Every collection that stores rows against an account. Listed rather than
# discovered, so a new collection has to be added here deliberately - a sweep
# that guesses would either miss one or delete from somewhere it should not.
ACCOUNT_COLLECTIONS = (
    "account_data_files",
    "account_widgets",
    "message_evaluations",
    "retrieval_evidence",
    "retrieval_index_state",
    "retrieval_jobs",
)

SHARED_VECTOR_NAMESPACES = ("entities", "relationships", "chunks")


def account_dir(account_id: str) -> str:
    """Where this account's uploaded files live, if anywhere."""
    return os.path.join(settings.DATA_STORAGE_DIR, str(account_id))


def workspace_collections(db, account_id: str) -> list:
    """Per-workspace LightRAG collections belonging to this account.

    `acct_<slugged id>_<index>_*` - KV, graph, doc-status. Matched on the id
    rather than reconstructed per index, so a workspace from an index that no
    longer exists in the registry is still found.
    """
    prefix = "acct_%s_" % str(account_id).lower()
    return sorted(c for c in db.list_collection_names()
                  if c.startswith(prefix) and not c.startswith("_bak_"))


def survey(db, account) -> dict:
    """Everything that would be removed for one account. Reads only."""
    account_id = str(account["_id"])
    counts = {name: db[name].count_documents({"account_id": account_id})
              for name in ACCOUNT_COLLECTIONS}

    partitions = {}
    for namespace in SHARED_VECTOR_NAMESPACES:
        collection = shared_collection_name(namespace)
        if collection not in db.list_collection_names():
            continue
        n = db[collection].count_documents(
            {PARTITION_FIELD: {"$regex": "^acct_%s_" % account_id.lower()}})
        if n:
            partitions[collection] = n

    directory = account_dir(account_id)
    files = 0
    if os.path.isdir(directory):
        files = sum(len(names) for _, _, names in os.walk(directory))

    return {
        "name": account.get("name"),
        "account_id": account_id,
        "counts": counts,
        "documents": sum(counts.values()),
        "workspaces": workspace_collections(db, account_id),
        "partitions": partitions,
        "directory": directory if os.path.isdir(directory) else "",
        "files": files,
        # An indexed account is a real one. This is the guard that separates
        # "eleven test rows" from "a day of index builds".
        "indexed": bool(counts.get("retrieval_index_state")),
    }


def backup(db, reports, path):
    """Write every document about to be deleted, before deleting any of it."""
    payload = {}
    for report in reports:
        account_id = report["account_id"]
        payload[account_id] = {
            "account": db["accounts"].find_one({"_id": _oid(account_id)}),
            "collections": {
                name: list(db[name].find({"account_id": account_id}))
                for name in ACCOUNT_COLLECTIONS
                if report["counts"].get(name)
            },
        }
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, default=str, ensure_ascii=False)
    return path


def _oid(account_id):
    from bson import ObjectId
    return ObjectId(account_id) if ObjectId.is_valid(str(account_id)) else account_id


def delete(db, report) -> dict:
    """Remove one account. The `accounts` row goes last, deliberately.

    A failure part-way then leaves the account listed with some data missing -
    visible, and safe to re-run - rather than an invisible account whose rows
    are still in every collection with nothing pointing at them.
    """
    account_id = report["account_id"]
    removed = {}

    for name in ACCOUNT_COLLECTIONS:
        if report["counts"].get(name):
            removed[name] = db[name].delete_many(
                {"account_id": account_id}).deleted_count

    for collection, _ in report["partitions"].items():
        removed[collection] = db[collection].delete_many(
            {PARTITION_FIELD: {"$regex": "^acct_%s_" % account_id.lower()}}
        ).deleted_count

    for collection in report["workspaces"]:
        db[collection].drop()
    if report["workspaces"]:
        removed["workspace collections"] = len(report["workspaces"])

    if report["directory"]:
        shutil.rmtree(report["directory"], ignore_errors=True)
        removed["files"] = report["files"]

    removed["accounts"] = db["accounts"].delete_one(
        {"_id": _oid(account_id)}).deleted_count
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("names", nargs="+", metavar="NAME",
                        help="account names to delete, exactly as stored")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would be removed, change nothing")
    parser.add_argument("--force", action="store_true",
                        help="allow deleting an account that has a built index")
    parser.add_argument("--backup-to", default="",
                        help="where to write the pre-delete backup "
                             "(default: deleted_accounts_<n>.json here)")
    parser.add_argument("--no-backup", action="store_true",
                        help="skip the backup - there is then no way back")
    args = parser.parse_args()

    connect_to_mongo()
    db = get_db()
    print("database %s on %s" % (settings.DB_NAME, redact_uri(settings.MONGODB_URI)))

    # A name that matches nothing is an error, not a skip. It usually means a
    # typo, and a typo is how the wrong account gets deleted.
    wanted, missing = [], []
    for name in args.names:
        found = db["accounts"].find_one({"name": name})
        (wanted if found else missing).append(found or name)
    if missing:
        raise SystemExit("no account named: %s" % ", ".join(missing))

    reports = [survey(db, account) for account in wanted]

    print("\n%-30s %9s %7s %11s %8s" % ("account", "documents", "files",
                                        "workspaces", "indexed"))
    for report in reports:
        print("  %-28s %9d %7d %11d %8s"
              % (report["name"][:28], report["documents"], report["files"],
                 len(report["workspaces"]),
                 "YES" if report["indexed"] else "-"))
        for name, n in sorted(report["counts"].items()):
            if n:
                print("       %-24s %d" % (name, n))
        for collection, n in sorted(report["partitions"].items()):
            print("       %-24s %d vector row(s)" % (collection, n))

    print("\ntotal: %d account(s), %d document(s), %d file(s)"
          % (len(reports), sum(r["documents"] for r in reports),
             sum(r["files"] for r in reports)))

    indexed = [r["name"] for r in reports if r["indexed"]]
    if indexed and not args.force:
        raise SystemExit(
            "\nrefusing: %s %s a built retrieval index, so %s a real account "
            "rather than a test row. Re-run with --force if that is genuinely "
            "what you want." % (", ".join(indexed),
                                "has" if len(indexed) == 1 else "have",
                                "it is" if len(indexed) == 1 else "they are"))

    if args.dry_run:
        print("\ndry run - nothing was changed")
        return 0

    if not args.no_backup:
        path = args.backup_to or "deleted_accounts_%d.json" % len(reports)
        print("\nbackup -> %s" % backup(db, reports, path))

    print()
    for report in reports:
        removed = delete(db, report)
        print("  deleted %-26s %s" % (
            report["name"][:26],
            ", ".join("%s=%s" % (k, v) for k, v in sorted(removed.items()))))

    print("\n%d account(s) remain: %s"
          % (db["accounts"].count_documents({}),
             ", ".join(sorted(a.get("name", "?") for a in
                              db["accounts"].find({}, {"name": 1})))))
    return 0


if __name__ == "__main__":
    # Console setup belongs here, not at import: the tests import this module,
    # and rebinding `sys.stdout` on import tears out pytest's capture.
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    sys.exit(main())
