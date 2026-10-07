# -*- coding: utf-8 -*-
"""Check every evidence link the dashboard can show, and record which ones open.

Run from hp-backend:
    python scripts/check_evidence_links.py --dry-run            # check, write nothing
    python scripts/check_evidence_links.py                      # check and record
    python scripts/check_evidence_links.py --account "ACME - SG"
    python scripts/check_evidence_links.py --csv dead_links.csv

The dashboard shows a source only when it has a link that opens (client, 7 Oct).
This is what tells it which links do not: each verdict is recorded in
`link_health`, one row per URL, and the dashboard hides the DEAD ones. See
`app/services/hp/link_health.py` for what counts as DEAD and why a 403 or a
timeout does not.

Writes only `link_health` - never a widget, so nothing goes stale. No LLM call.
A link checked within --max-age-days is not fetched again; run it after each
data refresh, since new widgets bring new links and old pages disappear.
"""

import argparse
import csv
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.database.mongodb import connect_to_mongo, get_db  # noqa: E402
from app.services.hp import link_health  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Check every evidence link.")
    ap.add_argument("--account", help="only this account (exact name)")
    ap.add_argument("--max-age-days", type=float, default=7,
                    help="skip links checked more recently than this (0 = check all)")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--dry-run", action="store_true", help="check, but record nothing")
    ap.add_argument("--csv", help="also write the DEAD and UNSURE links, with accounts, here")
    args = ap.parse_args()

    connect_to_mongo()
    db = get_db()
    query = {"name": args.account} if args.account else {}
    accounts = {str(a["_id"]): a.get("name") or str(a["_id"])
                for a in db["accounts"].find(query, {"name": 1})}
    if not accounts:
        raise SystemExit("no account matched")

    shown_on = defaultdict(set)  # url -> account names
    for account_id, name in accounts.items():
        for url in link_health.account_urls(db, account_id):
            shown_on[url].add(name)
    print("%d accounts, %d distinct links" % (len(accounts), len(shown_on)))

    fresh = set()
    if args.max_age_days > 0:
        since = datetime.now(UTC) - timedelta(days=args.max_age_days)
        fresh = {r["_id"] for r in db[link_health.COLLECTION].find(
            {"_id": {"$in": list(shown_on)}, "checked_at": {"$gte": since}}, {"_id": 1})}
    todo = sorted(set(shown_on) - fresh)
    print("%d checked within %g days, %d to check now%s" % (
        len(fresh), args.max_age_days, len(todo), " (dry run)" if args.dry_run else ""))

    results, started = {}, time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for i, (url, result) in enumerate(zip(todo, pool.map(link_health.check, todo)), 1):
            results[url] = result
            if not args.dry_run:
                link_health.record(db, url, result)
            if i % 250 == 0:
                print("  %d/%d  (%.0fs)" % (i, len(todo), time.time() - started), flush=True)

    counts = defaultdict(int)
    for verdict, *_ in results.values():
        counts[verdict] += 1
    print("\nOK %d   DEAD %d   UNSURE %d   (%.0fs)" % (
        counts[link_health.OK], counts[link_health.DEAD], counts[link_health.UNSURE],
        time.time() - started))

    # Every DEAD link on these accounts, including ones recorded on an earlier run.
    dead = {url: r for url, r in results.items() if r[0] == link_health.DEAD}
    if not args.dry_run:
        for row in db[link_health.COLLECTION].find(
                {"_id": {"$in": list(fresh)}, "verdict": link_health.DEAD}):
            dead.setdefault(row["_id"], (row["verdict"], row.get("http_status"),
                                         row.get("final_url"), row.get("note")))
    hit = sorted({n for u in dead for n in shown_on[u]})
    print("%d dead link(s), hidden on %d account(s)" % (len(dead), len(hit)))
    for url in sorted(dead)[:40]:
        _, status, final, note = dead[url]
        print("  %s  [%s %s]  %d account(s)" % (url, status, note, len(shown_on[url])))
    if len(dead) > 40:
        print("  ... and %d more" % (len(dead) - 40))

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["verdict", "url", "http_status", "note", "final_url", "accounts"])
            for url, (verdict, status, final, note) in sorted(results.items()):
                if verdict != link_health.OK:
                    w.writerow([verdict, url, status or "", note, final,
                                "; ".join(sorted(shown_on[url]))])
        print("\nWrote %s" % args.csv)


if __name__ == "__main__":
    main()
