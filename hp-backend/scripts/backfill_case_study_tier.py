"""Set `source_tier` on the loaded case studies, and change nothing else.

The client's 25 Sep ranking makes source tier the last sort key: "HP.com (T0)
before third-party (T2)". The column is in `hp_case_studies_final.csv` and the
loader never carried it across, so all 89 stored studies have no tier.

This is a backfill rather than a reload. `load_case_studies.py` calls gpt-4o
once per study, and the prose it writes is already cited on cards across the
product - a reload would re-roll every headline and outcome sentence to fix one
passthrough field. The tier needs no model: it is read straight from the CSV row
the study came from, joined on `source_case_study_id` -> `case_study_id`.

All 89 join, and no study spans rows with conflicting tiers.

    python scripts/backfill_case_study_tier.py            # dry run
    python scripts/backfill_case_study_tier.py --apply
"""

import argparse
import csv
import io
import logging
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database.mongodb import get_db  # noqa: E402
from app.services.hp import case_studies as cs  # noqa: E402

DEFAULT_CSV = os.path.join(os.path.dirname(__file__), "..", "..",
                           "additional_data", "hp_case_studies_final.csv")

logger = logging.getLogger(__name__)


def tiers_by_id(path: str) -> dict:
    """{case_study_id: tier} from the delivered CSV."""
    out: dict = {}
    with io.open(path, encoding="utf-8-sig", errors="replace") as handle:
        for row in csv.DictReader(handle):
            key = (row.get("case_study_id") or "").strip()
            tier = (row.get("source_tier") or "").strip().upper()
            if not key or not tier:
                continue
            # A merged study spans several rows. They agree in this delivery;
            # if a future one does not, the strongest source wins rather than
            # whichever row happens to be read last.
            current = out.get(key)
            out[key] = min(current, tier) if current else tier
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not os.path.isfile(args.csv):
        sys.exit("No case-study CSV at %s" % args.csv)

    lookup = tiers_by_id(args.csv)
    print("CSV: %d case_study_id values carry a tier" % len(lookup))

    db = get_db()
    docs = [d for d in db[cs.COLLECTION].find({}) if d.get("_id") != cs.VERSION_DOC_ID]
    print("stored studies: %d" % len(docs))

    planned, unmatched = [], []
    for doc in docs:
        key = str(doc.get("source_case_study_id") or "").strip()
        tier = lookup.get(key)
        if not tier:
            unmatched.append(doc.get("customer") or key or "?")
            continue
        if doc.get("source_tier") == tier:
            continue
        planned.append((doc["_id"], tier, doc.get("customer")))

    print("to set    : %d" % len(planned))
    print("unmatched : %d %s" % (len(unmatched), unmatched[:5] if unmatched else ""))
    print("tiers     :", dict(Counter(t for _, t, _ in planned)))

    if not args.apply:
        print("\ndry run - nothing written. Re-run with --apply.")
        return

    for _id, tier, _customer in planned:
        # $set on one field: nothing else about the document is touched.
        db[cs.COLLECTION].update_one({"_id": _id}, {"$set": {"source_tier": tier}})
    print("\nwrote source_tier on %d studies" % len(planned))


if __name__ == "__main__":
    main()
