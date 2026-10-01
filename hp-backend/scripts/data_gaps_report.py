# -*- coding: utf-8 -*-
"""Why an account shows "No signal observed" / "Not disclosed". Read-only.

Run from hp-backend:  python scripts/data_gaps_report.py "<account name>" [widget_key]

The client sees only neutral wording where a value is absent; the real reason
is recorded per field in each committed generation (`current.data_gaps`, see
app/services/regen/data_gaps.py). A generation committed before that field
existed has none, so for those the reasons are worked out from the stored
widgets with the same rules - the output says which.
"""
import io
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.database.mongodb import connect_to_mongo, get_db
connect_to_mongo()
db = get_db()

from app.services.regen import data_gaps

if len(sys.argv) < 2:
    sys.exit(__doc__)
name, only = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else None)

accounts = list(db.accounts.find({"name": {"$regex": "^%s$" % name, "$options": "i"}},
                                 {"name": 1}))
if not accounts:
    accounts = list(db.accounts.find({"name": {"$regex": name, "$options": "i"}}, {"name": 1}))
if len(accounts) != 1:
    sys.exit("%d accounts match %r: %s" % (len(accounts), name,
                                           ", ".join(a["name"] for a in accounts[:10])))
account_id = str(accounts[0]["_id"])
print("%s (%s)\n" % (accounts[0]["name"], account_id))

codes = Counter()
for node in db.node_state.find({"account_id": account_id}, {"node_id": 1, "current": 1}):
    current = node.get("current") or {}
    stored = "data_gaps" in current
    gaps = current["data_gaps"] if stored else data_gaps.collect_all(current.get("widgets"))
    gaps = [g for g in gaps if not only or g["widget"] == only]
    if not gaps:
        continue
    print("== %s  (%s)" % (node["node_id"], "recorded" if stored
                            else "derived - generated before data_gaps existed"))
    for g in gaps:
        codes[g["code"]] += 1
        print("  %-24s %-22s %s\n  %24s %s" % (g["widget"], g["code"], g["field"] or "(widget)",
                                              "", g["reason"]))
    print()

print("totals:", ", ".join("%s %d" % kv for kv in codes.most_common()) or "no gaps")
