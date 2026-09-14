# -*- coding: utf-8 -*-
"""Verify the Executive Dashboard index and the widgets built on it.

Run from hp-backend:  python scripts/verify_executive_dashboard.py [account name]

Checks the guarantees that matter for this feature and would otherwise only be
noticed by a seller reading a wrong number:

  * no invented scores - ABX weights a strategic-priority score but never
    defines how its four terms become numbers, so the measures are published raw
    and the composite stays null
  * ordering is the stated raw rule, not a hidden score
  * page exclusions are structural and explained, and no page carrying figures
    was dropped
  * the footnote-marker corruption (2024 extracting as 20248) is repaired
  * every filed figure carries a period, a unit and a page, or is absent
  * every published figure matches its evidence row exactly, and every cited
    sentence is the registered one rather than a model's paraphrase
  * news priorities only appear as a fallback

Account-agnostic: pass a name, or it defaults to the first account with a
compliance_filings dataset.
"""
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.database.mongodb import connect_to_mongo, get_db
connect_to_mongo()
db = get_db()

from app.services.retrieval import evidence as ev
from app.services.retrieval import financials, pdf, query
from app.services.extractors.datasets import dataset_file_paths

IDX = "executive_dashboard"

if len(sys.argv) > 1:
    account = db["accounts"].find_one({"name": sys.argv[1]})
else:
    owner = db["account_data_files"].find_one(
        {"dataset_key": "compliance_filings", "status": "active"})
    account = db["accounts"].find_one(
        {"_id": __import__("bson").ObjectId(owner["account_id"])}) if owner else None
if not account:
    raise SystemExit("no account with compliance filings - pass a name as an argument")
AID = str(account["_id"])
print("account: %s (%s)" % (account.get("name"), AID))
print()
PASS, FAIL = [], []


def ck(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %-52s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:60]))


widget = db["account_widgets"].find_one(
    {"account_id": AID, "widget_key": "exec_strategic_priorities"}) or {}
data = widget.get("data") or {}
priorities = data.get("priorities") or []
reported = data.get("reported_metrics") or []
blob = json.dumps(data, default=str)

print("=" * 80)
print("3. NO INVENTED SCORES")
print("=" * 80)
ck("every priority has evidence_score = null",
   bool(priorities) and all(p.get("evidence_score") is None for p in priorities),
   "%d priorities" % len(priorities))
ck("every priority says why the score is unavailable",
   all(p.get("score_unavailable_reason") for p in priorities))
ck("the payload declares scores unavailable",
   data.get("evidence_scores_available") is False)
# No 0-100 priority number anywhere in the payload.
score_keys = [k for k in re.findall(r'"(\w*score\w*)":', blob)
              if k not in ("evidence_score", "score_unavailable_reason",
                           "evidence_scores_available", "composite_score")]
ck("no other score field appears in the payload", not score_keys, score_keys[:4])
ck("every priority carries all four ABX measures",
   all(set(p.get("measures") or {}) >=
       {"support_count", "distinct_sections", "most_recent_date",
        "independent_source_count"} for p in priorities))

print()
print("=" * 80)
print("4. ORDERING IS HONEST")
print("=" * 80)
ck("the payload names its ordering basis", bool(data.get("ordering_basis")))
order = [(-(p["measures"]["support_count"]), -(p["measures"]["distinct_sections"]))
         for p in priorities]
ck("rendered order matches the raw measures", order == sorted(order),
   " ".join("%d/%d" % (-a, -b) for a, b in order))

print()
print("=" * 80)
print("5. EXCLUSIONS ARE STRUCTURAL AND EXPLAINED")
print("=" * 80)
files = dataset_file_paths(AID, "compliance_filings", strict=False)
excluded_total = kept_total = 0
leaked = []
for original, path in files:
    doc = pdf.read_pdf(path)
    excluded_total += len(doc["excluded"])
    kept_total += len(doc["pages"])
    import fitz
    handle = fitz.open(path)
    for entry in doc["excluded"]:
        raw = pdf.page_text(handle[entry["page"] - 1])[0]
        if pdf.FIGURE_RE.search(raw) or pdf.FINANCIAL_TERMS_RE.search(raw):
            leaked.append((original, entry["page"]))
    handle.close()
    if any(not e.get("reason") for e in doc["excluded"]):
        leaked.append((original, "missing reason"))
ck("every excluded page carries a reason and none held figures",
   not leaked, "%d kept, %d excluded" % (kept_total, excluded_total))

print()
print("=" * 80)
print("6. GIBBERISH REPAIRED")
print("=" * 80)
survivors = []
for original, path in files:
    for page in pdf.read_pdf(path)["pages"]:
        if pdf.YEAR_FOOTNOTE_RE.search(page["text"]):
            survivors.append((original, page["page"]))
ck("no 20248-style token survives into a document", not survivors, survivors[:3])
rows = list(db[ev.COLLECTION].find({"account_id": AID, "index": IDX}, {"_id": 0}))
ck("no such token reached the evidence registry",
   not [r for r in rows if pdf.YEAR_FOOTNOTE_RE.search(r.get("source_text") or "")])

print()
print("=" * 80)
print("7. EVERY FINANCIAL CLAIM IS CHECKABLE")
print("=" * 80)
fin_rows = [r for r in rows if r.get("dataset") == "compliance_filings"
            and r.get("value") is not None]
bare = [r for r in fin_rows if not r.get("period") or not r.get("unit")
        or not r.get("page")]
ck("no filed figure lacks period, unit or page", not bare,
   "%d figures registered, %d bare" % (len(fin_rows), len(bare)))
spot = [r for r in fin_rows if r.get("value") == 323392.0]
ck("Net Revenue 323,392 resolves to FY2025 IDR billion p.14",
   bool(spot) and spot[0]["period"] == "FY2025"
   and spot[0]["unit"] == "IDR billion" and spot[0]["page"] == 14,
   "%s %s p.%s" % (spot[0]["period"], spot[0]["unit"], spot[0]["page"]) if spot else "absent")
ck("its quote is the row as printed",
   bool(spot) and "Pendapatan Bersih" in (spot[0].get("quote") or "")
   and "233,485" in (spot[0].get("quote") or ""))

print()
print("=" * 80)
print("8. NO LLM AUTHORED A FACT")
print("=" * 80)
by_id = {r["evidence_id"]: r for r in rows}
mismatched = []
for metric in reported:
    row = by_id.get(metric.get("evidence_id"))
    if not row:
        mismatched.append((metric.get("metric"), "evidence row missing"))
        continue
    for field in ("value", "period", "unit", "page"):
        if metric.get(field) != row.get(field):
            mismatched.append((metric.get("metric"), field))
ck("published figures match their evidence rows exactly", not mismatched,
   "%d reported metric(s), %d mismatch" % (len(reported), len(mismatched)))

unresolved = []
for priority in priorities:
    for source in priority.get("sources") or []:
        row = by_id.get(source.get("evidence_id"))
        if not row:
            unresolved.append(source.get("evidence_id"))
        elif source.get("source_text") != row.get("source_text"):
            unresolved.append("%s text differs" % source.get("evidence_id"))
ck("every cited sentence is the registered one, not a paraphrase",
   not unresolved, unresolved[:3])

summary = data.get("executive_summary") or {}
ck("the executive summary was assembled in Python",
   summary.get("assembled_by") == "python", summary.get("assembled_by"))

print()
print("=" * 80)
print("9. NEWS STAYS A FALLBACK")
print("=" * 80)
from_news = [p for p in priorities if p.get("from_news_fallback")]
used = (data.get("generation") or {}).get("news_fallback_used")
ck("no news-sourced priority when filings supplied enough",
   (len(priorities) - len(from_news)) < 3 or not from_news,
   "%d filing-backed, %d from news, fallback_used=%s"
   % (len(priorities) - len(from_news), len(from_news), used))

print()
print("=" * 80)
print("INDEX STATE")
print("=" * 80)
state = query.status(AID, IDX)
print("  status %s, %s document(s), %d evidence row(s)"
      % (state["status"], state.get("documents"), len(rows)))
cm = query.status(AID, "content_messaging")
house = db["account_widgets"].find_one(
    {"account_id": AID, "widget_key": "messaging_pillars_output"}) or {}
print("  content_messaging is %s; its message house still has %d pillar(s)"
      % (cm["status"], len((house.get("data") or {}).get("pillars") or [])))

print()
print("=" * 80)
print("%d passed, %d failed" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED: %s" % ", ".join(FAIL))
