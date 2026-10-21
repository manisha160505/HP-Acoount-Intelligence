# ruff: noqa: T201 - a console script; printing is its output.
"""Check every link the dashboard can show, and record which ones are broken.

Run from hp-backend (on the VM: inside the backend container):

  1. Dry run - no HTTP request, nothing written:
       python scripts/check_links.py
       python scripts/check_links.py --account "ACME - SG" --recheck-all

     Prints the database, how many distinct links the committed widgets hold,
     how many were checked within --days, and which would be checked now.

  2. Apply - checks those links and records each verdict in `link_checks`:
       python scripts/check_links.py --apply --target-db <DB_NAME>

     --target-db must equal the DB_NAME this process is configured with, so a
     shell pointed at the wrong database refuses instead of writing to it.

The dashboard's widget read path hides every link recorded as broken; a link
never checked is shown. Only definite breakage is broken - a 404/410 or other
4xx (not 401/403/429), a host that does not exist, a bad certificate, a soft
404, a redirect loop, a removed YouTube video. A timeout, a refused or reset
connection, a 5xx or a temporary DNS failure is how a site can treat this
server's cloud address while opening fine in a browser, so those links stay
shown and are listed as "kept, not verified". The full rule is in
`app/services/links/checker.py`. Writes only `link_checks` - never a widget, so
nothing goes stale - and makes no LLM call. Safe to run again: a link checked
within --days is skipped unless --recheck-all. Run it after each data refresh,
since new widgets bring new links and old pages disappear.

Links come from the same place the dashboard reads them: each widget's
committed generation (node state), or `account_widgets` for an account or a
user output the engine does not own - `regen.store.committed_many`.
"""

import argparse
import os
import sys
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.config.settings import settings
from app.services import links
from app.services.links import store as link_store
from app.services.regen import store as widget_store


def _target() -> str:
    u = urlsplit(settings.MONGODB_URI)
    return "%s/%s" % (u.hostname or settings.MONGODB_URI, settings.DB_NAME)


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?").lower()
    except ValueError:
        return "?"


def widget_keys() -> list:
    """Every widget the dashboard's GET route serves."""
    from app.api.v1.widgets import WIDGET_REGISTRY
    return sorted({w["widget_key"] for ws in WIDGET_REGISTRY.values() for w in ws})


def gather(db, account_filter: str | None = None) -> dict:
    """url -> the names of the accounts whose dashboard shows it."""
    query = {"name": account_filter} if account_filter else {}
    accounts = {str(a["_id"]): a.get("name") or str(a["_id"])
                for a in db["accounts"].find(query, {"name": 1})}
    shown_on: dict = defaultdict(set)
    if not accounts:
        return shown_on
    for key in widget_keys():
        for account_id, doc in widget_store.committed_many(db, list(accounts), key).items():
            for url in links.collect_urls((doc or {}).get("data") or {}):
                shown_on[url].add(accounts.get(account_id, account_id))
    return shown_on


class HostLimiter:
    """At most `per_host` requests in flight to one host, and `delay` seconds
    between one request to it finishing and the next starting."""

    def __init__(self, per_host: int, delay: float, sleep=time.sleep):
        self._per_host, self._delay, self._sleep = per_host, delay, sleep
        self._locks: dict = {}
        self._guard = threading.Lock()

    def slot(self, host: str) -> threading.BoundedSemaphore:
        with self._guard:
            if host not in self._locks:
                self._locks[host] = threading.BoundedSemaphore(self._per_host)
            return self._locks[host]

    def run(self, url: str, fn):
        with self.slot(_host(url)):
            try:
                return fn(url)
            finally:
                if self._delay:
                    self._sleep(self._delay)


def _print_summary(verdicts: list, shown_on: dict) -> None:
    broken = [v for v in verdicts if not v.ok]
    unverified = Counter(v.reason for v in verdicts
                         if v.ok and v.reason.startswith("unverified"))
    print("\nChecked %d: %d ok (%d kept, not verified), %d broken (hidden)"
          % (len(verdicts), len(verdicts) - len(broken), sum(unverified.values()),
             len(broken)))
    other_ok = Counter(v.reason for v in verdicts
                       if v.ok and v.reason != "ok" and not v.reason.startswith("unverified"))
    if other_ok:
        print("Ok without a clean 2xx (paywall, script refused, special host):")
        for reason, n in other_ok.most_common():
            print("  %-34s %d" % (reason, n))
    if unverified:
        print("Kept, not verified - shown to users; this server could not confirm "
              "them (timeout, refused, 5xx, ...):")
        for reason, n in unverified.most_common():
            print("  %-34s %d" % (reason, n))
    if not broken:
        return
    print("Broken (hidden) by reason:")
    for reason, n in Counter(v.reason for v in broken).most_common():
        print("  %-34s %d" % (reason, n))
    print("Top broken hosts:")
    for host, n in Counter(_host(v.url) for v in broken).most_common(10):
        print("  %-40s %d" % (host, n))
    accounts = set().union(*(shown_on.get(v.url, set()) for v in broken))
    print("Accounts showing a broken link: %d" % len(accounts))
    print("Broken links (first 50):")
    for v in sorted(broken, key=lambda v: v.url)[:50]:
        print("  [%s %s] %s" % (v.reason, v.status or "-", v.url))


def main(argv=None, *, db=None, checker=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="check the links and record verdicts")
    ap.add_argument("--target-db", help="with --apply: must equal the configured DB_NAME")
    ap.add_argument("--days", type=float, default=7,
                    help="skip links checked within this many days (default 7)")
    ap.add_argument("--recheck-all", action="store_true", help="check every link again")
    ap.add_argument("--account", help="only this account (exact name)")
    ap.add_argument("--limit", type=int, default=0, help="check at most this many links")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--per-host", type=int, default=2, help="requests in flight per host")
    ap.add_argument("--host-delay", type=float, default=0.5,
                    help="seconds between requests to one host")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args(argv)

    if db is None:
        from app.database.mongodb import connect_to_mongo, get_db
        connect_to_mongo()
        db = get_db()
    print("Database: %s" % _target())

    shown_on = gather(db, args.account)
    if args.account and not shown_on:
        print("No links found (is %r an exact account name?)" % args.account)
    urls = sorted(shown_on)
    fresh = set() if args.recheck_all else link_store.checked_since(
        db, urls, datetime.now(UTC) - timedelta(days=args.days))
    todo = [u for u in urls if u not in fresh]
    if args.limit:
        todo = todo[:args.limit]
    known_broken = link_store.broken_urls(db, urls)
    print("%d distinct links; %d checked within %g days%s; %d to check; "
          "%d currently recorded broken"
          % (len(urls), len(fresh), args.days, " (ignored: --recheck-all)"
             if args.recheck_all else "", len(todo), len(known_broken)))

    if not args.apply:
        for host, n in Counter(_host(u) for u in todo).most_common(15):
            print("  %-40s %d" % (host, n))
        for u in todo[:20]:
            print("  would check %s" % u)
        print("\nNothing was checked or written. Re-run with --apply --target-db %s to check "
              "and record." % settings.DB_NAME)
        return 0

    if args.target_db != settings.DB_NAME:
        print("Refusing: --target-db %r does not match the configured DB_NAME %r (%s)."
              % (args.target_db, settings.DB_NAME, _target()), file=sys.stderr)
        return 2

    link_store.ensure_indexes(db)
    own_checker = checker is None
    checker = checker or links.Checker(timeout=args.timeout)
    limiter = HostLimiter(max(1, args.per_host), max(0.0, args.host_delay))
    verdicts = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            futures = {pool.submit(limiter.run, u, checker.check): u for u in todo}
            for i, fut in enumerate(as_completed(futures), 1):
                url = futures[fut]
                try:
                    verdict = fut.result()
                except Exception as exc:
                    print("  ERROR %s: %s (not recorded)" % (url, exc), file=sys.stderr)
                    continue
                link_store.record(db, verdict)
                verdicts.append(verdict)
                if i % 100 == 0:
                    print("  %d/%d" % (i, len(todo)))
    finally:
        if own_checker:
            checker.close()

    _print_summary(verdicts, shown_on)
    print("Recorded %d verdicts in %s." % (len(verdicts), link_store.COLLECTION))
    return 0


if __name__ == "__main__":
    sys.exit(main())
