#!/usr/bin/env python
"""Write the six audit CSVs the build specification asks for.

    python scripts/export_content_audit.py [--account <id>] [--days N]
                                           [--surface content_studio|evaluator_rewrite]
                                           [--out <dir>]

Spec Section 6 names six files and says "an empty audit file is a pass. A
non-empty audit file lists specific rows to fix." Section 7 makes them the
release gate: "Review the six audit CSVs. All must be empty before release."

Every Content Studio generation and every Message Evaluator rewrite already
runs the fourteen gates and writes what they find to the ledger
(`content_gate_audit`). This turns the ledger into those files. It reads; it
never generates, so it costs nothing and can be run as often as you like.

  * **No arguments** - everything on record, all 220 accounts.
  * **--account** - one account, for the per-account check as each is built.
  * **--days 7** - the last week, for a release cut.

Exit code 0 when every file is empty, 1 when any has rows - so it can gate a
release from a script rather than from somebody remembering to look.

What a row means. Each carries an `outcome`:

    published     the gate fired and the seller saw the draft anyway. These
                  are the rows that matter most; a `reject` here should be
                  impossible and is a bug in the pipeline, not in the copy.
    regenerated   the gate fired, the draft was rejected, a later attempt
                  stood. The system worked. Still worth reading in bulk: forty
                  line-eligibility regenerations means the prompt is steering
                  into denied products.
    withheld      rejected to the end. Nothing reached the seller.
"""
import argparse
import os
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "hp-backend", "src"))

from app.database.mongodb import get_db
from app.services.hp import content_audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account", default="", help="one account id")
    parser.add_argument("--days", type=int, default=0,
                        help="only findings from the last N days")
    parser.add_argument("--surface", default="",
                        choices=["", content_audit.SURFACE_GENERATION,
                                 content_audit.SURFACE_REWRITE])
    parser.add_argument("--outcome", default="",
                        choices=["", content_audit.OUTCOME_PUBLISHED,
                                 content_audit.OUTCOME_REGENERATED,
                                 content_audit.OUTCOME_WITHHELD])
    parser.add_argument("--out", default="audit",
                        help="directory to write the CSVs into")
    args = parser.parse_args()

    filters = {}
    if args.account:
        filters["account_id"] = args.account
    if args.surface:
        filters["surface"] = args.surface
    if args.outcome:
        filters["outcome"] = args.outcome
    if args.days:
        filters["since"] = datetime.now(UTC) - timedelta(days=args.days)

    counts = content_audit.export(get_db(), args.out, **filters)

    scope = args.account or "all accounts"
    if args.days:
        scope += f", last {args.days} day" + ("" if args.days == 1 else "s")
    print(f"Gate audit - {scope}\n")
    for name, rows in counts.items():
        print(f"  {name:<34} {rows if rows else 'empty'}")

    print(f"\nWritten to {os.path.abspath(args.out)}/")
    if content_audit.is_clean(counts):
        print("All six files empty - clean for release.")
        return 0
    print("Rows to review before release. Read audit_line_eligibility.csv "
          "first: it is the gate with no regeneration allowance, and the "
          "failure that costs seller trust.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
