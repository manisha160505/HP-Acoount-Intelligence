#!/usr/bin/env python3
"""Adopt existing widgets into the regeneration engine. Dry run by default.

    python scripts/migrate_regen.py            # report only
    python scripts/migrate_regen.py --apply    # write

Idempotent and non-destructive; see src/app/services/regen/migrate.py.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database.mongodb import get_db  # noqa: E402
from app.services.regen import migrate  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the changes")
    args = ap.parse_args()
    report = migrate.run(get_db(), dry_run=not args.apply)
    print(json.dumps(report, indent=2, default=str))
    return 1 if report["duplicates"] else 0


if __name__ == "__main__":
    sys.exit(main())
