# -*- coding: utf-8 -*-
"""Copy this machine's database into a shared cluster (Atlas).

The point of the move is that the team inherits the widgets that have already
been generated - the GPT-4o output in particular, which costs API calls to
reproduce and is not in the repository.

Only metadata moves. The CSV bytes stay on local disk (`account_data.py` writes
them there and stores the path), so `account_data_files` rows will point at
files that exist only on the machine that uploaded them. That is expected and
handled: `requires_local_datasets` stops an extractor on a machine without the
files instead of overwriting good widgets with empty ones.

Usage, from hp-backend/. Put the Atlas string in hp-backend/.env as ATLAS_URI
first; the script reads it from there so the password stays out of shell
history and the process list.

    python scripts/migrate_to_atlas.py             # dry run, changes nothing
    python scripts/migrate_to_atlas.py --apply     # writes

Dry run by default. Re-running --apply is safe: writes are upserts by _id.
"""
import argparse
import io
import os
import re
import sys

from pymongo import MongoClient
from pymongo.errors import PyMongoError

# Everything the app owns. Ordered so that referenced documents land first.
COLLECTIONS = ["users", "accounts", "account_data_files", "account_widgets"]

_CREDENTIALS = re.compile(r"://([^:/@]+):([^@]+)@")


def redact(uri: str) -> str:
    return _CREDENTIALS.sub(r"://\1:***@", str(uri or ""))


def _uri_from_env_file() -> str | None:
    """ATLAS_URI, else MONGODB_URI, from hp-backend/.env.

    Reading it from the file keeps the password out of shell history, out of
    the process list, and out of any transcript of this session.
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            ".env")
    if not os.path.exists(env_path):
        return None
    found = {}
    with io.open(env_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            found[key.strip()] = value.strip().strip('"').strip("'")
    return found.get("ATLAS_URI") or found.get("MONGODB_URI")


def connect(uri: str, label: str) -> MongoClient:
    client = MongoClient(uri, serverSelectionTimeoutMS=8000)
    try:
        client.admin.command("ping")
    except PyMongoError as exc:
        sys.exit("Cannot reach the %s cluster at %s: %s\n"
                 "For Atlas, check the password and that this machine's IP is "
                 "allowlisted." % (label, redact(uri), type(exc).__name__))
    return client


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="mongodb://localhost:27017",
                    help="source URI (default: local)")
    ap.add_argument("--source-db", default="hp_account_db")
    ap.add_argument("--target", default=None,
                    help="destination URI. Omit it and the script reads ATLAS_URI "
                         "(then MONGODB_URI) from hp-backend/.env, so the password "
                         "never has to be typed on a command line.")
    ap.add_argument("--target-db", default="hp_account_db")
    ap.add_argument("--apply", action="store_true",
                    help="actually write; without it nothing is changed")
    args = ap.parse_args()

    target_uri = args.target or _uri_from_env_file()
    if not target_uri:
        sys.exit("No target URI. Either pass --target, or set ATLAS_URI in "
                 "hp-backend/.env and re-run.")
    args.target = target_uri

    # Falling back to MONGODB_URI is convenient once .env already points at
    # Atlas, but before that it resolves to the local database - which would
    # make --apply upsert every document onto itself. Refuse rather than
    # pretend that did something.
    if (args.target, args.target_db) == (args.source, args.source_db):
        sys.exit("Target resolves to the same database as the source (%s / %s). "
                 "Set ATLAS_URI in hp-backend/.env to the Atlas connection string, "
                 "or pass --target explicitly."
                 % (redact(args.source), args.source_db))

    src = connect(args.source, "source")[args.source_db]
    dst = connect(args.target, "target")[args.target_db]

    print("source: %s / %s" % (redact(args.source), args.source_db))
    print("target: %s / %s" % (redact(args.target), args.target_db))
    print("mode  : %s\n" % ("APPLY - will write" if args.apply else "dry run - no writes"))

    total_written = 0
    for name in COLLECTIONS:
        docs = list(src[name].find({}))
        existing = dst[name].count_documents({}) if args.apply or True else 0
        print("  %-20s source=%-5d target(before)=%-5d" % (name, len(docs), existing))

        if not args.apply or not docs:
            continue

        # Upsert by _id so a re-run is a no-op rather than a duplicate.
        written = 0
        for doc in docs:
            doc_id = doc["_id"]
            payload = {k: v for k, v in doc.items() if k != "_id"}
            dst[name].update_one({"_id": doc_id}, {"$set": payload}, upsert=True)
            written += 1
        total_written += written
        print("  %-20s wrote %d, target(after)=%d"
              % ("", written, dst[name].count_documents({})))

    print()
    if not args.apply:
        print("Dry run complete. Re-run with --apply to write.")
        return 0

    print("Migrated %d document(s).\n" % total_written)
    print("Verify per-collection counts match, then point MONGODB_URI in")
    print("hp-backend/.env at the target and restart the backend.")
    print("Note: uploaded CSVs are NOT copied - they stay on the machine that")
    print("uploaded them. Extractors skip rather than blank widgets elsewhere.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
