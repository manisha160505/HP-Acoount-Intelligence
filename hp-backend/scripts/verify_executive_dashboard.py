# -*- coding: utf-8 -*-
"""Verify the Executive Dashboard index and the widgets built on it.

Run from hp-backend:  python scripts/verify_executive_dashboard.py [account name]

Checks the guarantees that matter for this feature and would otherwise only be
noticed by a seller reading a wrong number:

  * no invented scores - every published number reproduces from a formula that
    states its own units, and ABX's four raw measures are published unchanged
    beside it
  * the urgency composite reproduces from its own weighted drivers, names the
    two that are proxies, and says which of its formulas were delivery-authored
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
from app.services.extractors.datasets import (account_domain,
                                              dataset_file_paths)
from app.services.dashboard import evidence_strength, urgency
from datetime import date

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
print("3. SCORES ARE COMPUTED, NOT INVENTED")
print("=" * 80)
# This section used to assert that NO score was published. That was right about
# ABX's own weighting - 40/25/20/15 over four counts, with no stated way to turn
# a count into a number - and it stays right about it. What replaced the refusal
# is a different, fully specified formula (`evidence_strength.py`), so the
# question here is no longer "is there a score" but "can this codebase show its
# working for every number it prints".
domain = account_domain(AID)
strengths = [p.get("evidence_strength") for p in priorities]
ck("every priority carries an evidence strength",
   bool(priorities) and all(strengths), "%d priorities" % len(priorities))
ck("no priority still carries the superseded refusal",
   not any("evidence_score" in p or "score_unavailable_reason" in p
           for p in priorities))
ck("the payload declares scores available and names the formula",
   data.get("evidence_scores_available") is True
   and data.get("evidence_strength_formula") == evidence_strength.FORMULA
   and data.get("evidence_strength_max") == evidence_strength.MAX_SCORE)
ck("every score publishes all three terms' working",
   all(s and [t.get("key") for t in s.get("terms") or []] ==
       ["filing_evidence", "recency", "source_diversity"] for s in strengths))
ck("every total equals the sum of its own terms",
   all(s and s.get("score") == sum(t["points"] for t in s["terms"])
       for s in strengths),
   " ".join(str(s["score"]) for s in strengths if s))
# Recomputed from the stored sources, not merely checked for internal
# consistency: the published number has to fall out of the formula a second
# time, from the evidence the card cites.
again = [evidence_strength.score(p.get("sources") or [],
                                 date.fromisoformat(data["scored_on"]), domain)
         for p in priorities]
ck("every score reproduces from the sources the card cites",
   bool(again) and all(a["score"] == s["score"] for a, s in zip(again, strengths)))
# A score that drifts cannot be agreed: the same catalyst would read 25 one week
# and 20 the next with nothing having changed.
ck("ages are frozen at generation, so scores do not drift with the clock",
   bool(data.get("scored_on"))
   and all(s.get("scored_on") == data["scored_on"] for s in strengths))
# Nothing else 0-100 may appear. The named keys are the defined formula's own.
score_keys = [k for k in re.findall(r'"(\w*score\w*)":', blob)
              if k not in ("score", "max_score", "scored_on",
                           "evidence_scores_available", "evidence_strength_max",
                           "composite_score")]
ck("no other score field appears in the payload", not score_keys, score_keys[:4])
ck("every priority carries all four ABX measures",
   all(set(p.get("measures") or {}) >=
       {"support_count", "distinct_sections", "most_recent_date",
        "independent_source_count"} for p in priorities))

print()
print("=" * 80)
print("3b. THE URGENCY COMPOSITE")
print("=" * 80)
urg = (db["account_widgets"].find_one(
    {"account_id": AID, "widget_key": "exec_urgency_score"}) or {}).get("data") or {}
drivers = urg.get("drivers") or []
by_key = {d.get("key"): d for d in drivers}
ck("the urgency widget exists with all five ABX drivers",
   set(by_key) == set(urgency.DRIVER_KEYS), ", ".join(sorted(by_key)))
ck("each driver carries the ABX weight",
   all(by_key.get(k, {}).get("weight") == w
       for k, w in urgency.WEIGHTS.items()))
# ABX: "if any of the five urgency inputs is unavailable, keep that input
# unavailable and do not calculate a composite". A missing dataset must cost the
# composite, never be scored as a zero.
unavailable = [d["key"] for d in drivers if not d.get("available")]
ck("a missing input blocks the composite rather than scoring zero",
   (urg.get("available") is True and not unavailable)
   or (urg.get("available") is False and bool(urg.get("unavailable_reason"))),
   unavailable or "all five available")
if urg.get("available"):
    total = sum(d["value"] * d["weight"] for d in drivers)
    ck("the published composite reproduces from its drivers",
       round(total) == urg.get("score"),
       "%.1f -> %s" % (total, urg.get("score")))
# Two drivers measure something adjacent to what they are named after - no
# dataset carries OS version, device age or end-of-support - and must say so.
ck("every proxy driver is labelled and explains what it really measures",
   all(by_key[k].get("proxy") is True and by_key[k].get("proxy_note")
       for k in urg.get("proxy_drivers") or []),
   ", ".join(urg.get("proxy_drivers") or []) or "none")
# The weights are ABX's; every band and point value below them was authored
# here. A seller must not read a delivery-authored number as the spec's.
ck("delivery-authored formulas say so on every driver",
   bool(urg.get("formula_authority") == urgency.FORMULA_AUTHORITY)
   and all(d.get("authored_by") for d in drivers))
ck("the composite records whether the client has agreed the formula",
   isinstance(urg.get("client_agreed"), bool), urg.get("client_agreed"))

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
