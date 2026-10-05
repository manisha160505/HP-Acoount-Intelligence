#!/usr/bin/env python3
"""Keep accounts the 5 Oct release does not change current; rebuild only the
(account, section) pairs it does. Dry run by default.

    python scripts/rebase_unaffected.py                       # 1. report only
    python scripts/rebase_unaffected.py --apply               # 2. re-stamp unaffected sections
    python scripts/rebase_unaffected.py --submit intent,objection   # 3. wait for it to finish
    python scripts/rebase_unaffected.py --apply               # 4. re-stamp News etc. after intent
    python scripts/rebase_unaffected.py --submit exec_core    # 5. no model calls; wait
    python scripts/rebase_unaffected.py --apply               # 6. re-stamp what exec_core touched

The release changes output only for:
  intent      accounts whose Bombora export is used (HP category grouping,
              and the parent-domain / confirmed-alias match of PR #69)
  objection   accounts with no Technographics but a Tech breakdown (fallback)
  exec_core   accounts with a parent or subsidiaries to show (no model call:
              the profile bullets are cached on the description)
Every other stale section is re-stamped as current by regen/rebase.py, which
refuses anything stale for a changed file, rules, config or model.

Order matters: the Executive Dashboard builds only on a current News, and News
reads intent. So intent runs first, step 4 re-stamps News, then exec_core.
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
from app.services.regen import rebase, runs, store as widget_store  # noqa: E402
from app.services.regen.engine import get_engine  # noqa: E402

LABEL = "rebase_unaffected 5 Oct (PR 68/69)"


def _rows(db, account_id, key):
    return db["account_data_files"].count_documents(
        {"account_id": account_id, "dataset_key": key, "status": "active"})


def affected_nodes(db, account_id: str) -> set:
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


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the re-stamps")
    ap.add_argument("--submit", default="",
                    help="comma-separated sections to run for the accounts they affect")
    args = ap.parse_args()

    db, engine = get_db(), get_engine()
    accounts = [str(a["_id"]) for a in db["accounts"].find({}, {"_id": 1})]
    affected = {a: affected_nodes(db, a) for a in accounts}

    if args.submit:
        for nid in [n.strip() for n in args.submit.split(",") if n.strip()]:
            targets = [a for a in accounts if nid in affected[a]]
            if not targets:
                print(nid, "- no affected account")
                continue
            run = runs.create(engine, accounts=targets, nodes=[nid], force=False,
                              include_downstream=False, actor="script:rebase_unaffected",
                              reason="%s: only accounts the release changes" % LABEL)
            print(nid, "accounts:", len(targets), "run:", run.get("_id"),
                  (run.get("plan") or run).get("totals"))
        return 0

    outcomes, per_node = Counter(), Counter()
    for a in accounts:
        res = rebase.rebase_account(engine, a, affected[a], dry_run=not args.apply, label=LABEL)
        for nid, o in res.items():
            outcomes[o.split(":")[0]] += 1
            per_node[(nid, o)] += 1
    print(json.dumps({
        "mode": "apply" if args.apply else "dry run",
        "accounts": len(accounts),
        "affected": {n: sum(1 for s in affected.values() if n in s)
                     for n in ("intent", "objection", "exec_core")},
        "sections": dict(outcomes),
        "by_section": {"%s %s" % k: v for k, v in sorted(per_node.items())},
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
