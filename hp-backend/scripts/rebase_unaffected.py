#!/usr/bin/env python3
"""Keep accounts a release does not change current; rebuild only the
(account, section) pairs it does. Dry run by default. --release picks the
release (default: the latest, "windows").

Release "windows" (6 Oct, data time periods: signals 12 months, filings 24):

    python scripts/rebase_unaffected.py                       # report only
    python scripts/rebase_unaffected.py --apply               # re-stamp unaffected sections
    # A. sections that read news / technology detections; wait for the queue
    python scripts/rebase_unaffected.py --submit opp_core,tech_core,objection,stakeholder_talking_points,tech_recs
    python scripts/rebase_unaffected.py --apply
    # B. Executive Dashboard filings list, financials, CEO (no model calls); wait
    python scripts/rebase_unaffected.py --submit exec_core
    python scripts/rebase_unaffected.py --apply
    # C. Strategic Priorities (catalyst evidence older than 24 months); wait
    python scripts/rebase_unaffected.py --submit exec_priorities
    python scripts/rebase_unaffected.py --apply

It changes output only for:
  opp_core, stakeholder_talking_points   accounts with news outside the last 12 months
  objection, tech_recs                   news or technology detections outside 12 months
  tech_core                              technology detections outside 12 months
  exec_core                              accounts with filings (the list is now 24 months),
                                         and accounts in the client's 7 Oct hierarchy data
  exec_priorities                        catalyst evidence older than 24 months

Release "oct5" (PR 68/69): intent on Bombora-led accounts, objection on the
Tech breakdown fallback accounts, exec_core where a parent or subsidiaries show.

Every other stale section is re-stamped as current by regen/rebase.py, which
refuses anything stale for a changed file, rules, config or model. Order
matters: a section builds only on current upstreams, so each --submit is
followed by an --apply that re-stamps what it touched downstream.
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database.mongodb import get_db  # noqa: E402
from app.services.extractors import executive_dashboard as ed  # noqa: E402
from app.services.extractors import intent_demand_signals as ids  # noqa: E402
from app.services.extractors.datasets import (  # noqa: E402
    account_display_name,
    account_domain,
    read_dataset_records,
)
from app.services.dashboard import evidence_strength  # noqa: E402
from app.services.hp import company_relationships  # noqa: E402
from app.services.hp import time_windows  # noqa: E402
from app.services.regen import rebase, runs, store as widget_store  # noqa: E402
from app.services.regen.engine import get_engine  # noqa: E402
from app.services.retrieval import evidence as ev  # noqa: E402

LABELS = {"oct5": "rebase_unaffected 5 Oct (PR 68/69)",
          "windows": "rebase_unaffected 6 Oct (data time periods)"}


def _rows(db, account_id, key):
    return db["account_data_files"].count_documents(
        {"account_id": account_id, "dataset_key": key, "status": "active"})


def affected_oct5(db, account_id: str) -> set:
    out = set()
    if _rows(db, account_id, "tech_breakdown") and not _rows(db, account_id, "technographics"):
        out.add("objection")
    if _rows(db, account_id, "intent_score"):
        # Bombora leads today (the HP category grouping changes its summary),
        # or the export is newly accepted by the parent-domain / alias match.
        summary = widget_store.get(account_id, "intent_category_summary", db=db) or {}
        lead = (((summary.get("data") or {}).get("bu_summary") or {}).get("lead_source"))
        meta = read_dataset_records(account_id, "intent_topics", strict=False) or []
        match, _ = ids._match_provider_account(meta, account_domain(account_id))
        newly_matched = match["status"] == "matched" and match.get("matched_by") != "domain"
        if lead == "Bombora" or newly_matched:
            out.add("intent")
    name = account_display_name(account_id)
    hier = read_dataset_records(account_id, "company_hierarchy", strict=False) or []
    parent, _ = ed._resolve_parent(hier[0] if hier else None, name)
    subs = ed._subsidiaries(read_dataset_records(account_id, "subsidiaries", strict=False) or [],
                            name, parent)
    if parent or subs:
        out.add("exec_core")
    return out


def affected_windows(db, account_id: str) -> set:
    """The sections whose output the 12 / 24-month windows change."""
    out = set()
    news = [r for k in ("google_news", "news_events")
            for r in read_dataset_records(account_id, k, strict=False) or []]
    if len(time_windows.recent_news(news)) < len(news):
        out |= {"opp_core", "stakeholder_talking_points", "objection", "tech_recs"}
    detections = read_dataset_records(account_id, "technology_detections", strict=False) or []
    if len(time_windows.recent_detections(detections)) < len(detections):
        out |= {"tech_core", "objection", "tech_recs"}
    if _rows(db, account_id, "compliance_filings") or _rows(db, account_id, "filings_financials"):
        out.add("exec_core")
    # The client's 7 Oct parents and subsidiaries (hp/company_relationships.py)
    # change the summary card of every account they name.
    rel = company_relationships.for_account(account_display_name(account_id))
    if rel["override"] is not None or rel["parents"] or rel["subsidiaries"]:
        out.add("exec_core")
    oldest_ok = time_windows.today().toordinal() - time_windows.FILINGS_WINDOW_DAYS
    for row in db[ev.COLLECTION].find({"account_id": account_id, "index": "executive_dashboard"},
                                      {"period": 1, "filing_period": 1}):
        when = evidence_strength.parse_period(row.get("period") or row.get("filing_period"))
        if when is not None and when.toordinal() < oldest_ok:
            out.add("exec_priorities")
            break
    return out


RELEASES = {"oct5": affected_oct5, "windows": affected_windows}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the re-stamps")
    ap.add_argument("--release", default="windows", choices=sorted(RELEASES),
                    help="which release's affected sections to leave stale")
    ap.add_argument("--submit", default="",
                    help="comma-separated sections to run for the accounts they affect")
    args = ap.parse_args()

    db, engine = get_db(), get_engine()
    accounts = [str(a["_id"]) for a in db["accounts"].find({}, {"_id": 1})]
    label = LABELS[args.release]
    affected = {a: RELEASES[args.release](db, a) for a in accounts}

    if args.submit:
        for nid in [n.strip() for n in args.submit.split(",") if n.strip()]:
            targets = [a for a in accounts if nid in affected[a]]
            if not targets:
                print(nid, "- no affected account")
                continue
            run = runs.create(engine, accounts=targets, nodes=[nid], force=False,
                              include_downstream=False, actor="script:rebase_unaffected",
                              reason="%s: only accounts the release changes" % label)
            print(nid, "accounts:", len(targets), "run:", run.get("_id"),
                  (run.get("plan") or run).get("totals"))
        return 0

    outcomes, per_node = Counter(), Counter()
    for a in accounts:
        res = rebase.rebase_account(engine, a, affected[a], dry_run=not args.apply, label=label)
        for nid, o in res.items():
            outcomes[o.split(":")[0]] += 1
            per_node[(nid, o)] += 1
    print(json.dumps({
        "mode": "apply" if args.apply else "dry run",
        "accounts": len(accounts),
        "release": args.release,
        "affected": dict(Counter(n for nodes in affected.values() for n in nodes)),
        "sections": dict(outcomes),
        "by_section": {"%s %s" % k: v for k, v in sorted(per_node.items())},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
