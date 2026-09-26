"""Profile the 220 split folders and classify each feature per account.

Rules follow the 25 Sep extractor trace (DATA_READINESS_AUDIT_220_2026-09-25.md s2),
re-checked against hp-backend on 26 Sep (no backend changes since).
"""
import csv, json, re, sys, collections
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd

csv.field_size_limit(10**9)
ROOT = Path("/Users/yogeshyadav/Desktop/HP/220 account split csv")
NOW = datetime(2026, 9, 26, 23, 59, tzinfo=timezone.utc)
CUTOFF = NOW - timedelta(days=365)


def rows(folder, name):
    p = folder / f"{name}.csv"
    if not p.exists() or p.stat().st_size < 5:
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def raw_rows(folder, name):
    p = folder / f"{name}.csv"
    if not p.exists():
        return []
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.reader(f))


def c(v):
    return " ".join(str(v or "").split())


def norm(d):
    d = c(d).lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split(":")[0].rstrip(".")
    return d[4:] if d.startswith("www.") else d


def dt(v):
    v = c(v)
    if not v:
        return None
    try:
        x = pd.to_datetime(v, utc=True, errors="coerce")
    except Exception:
        return None
    return None if pd.isna(x) else x.to_pydatetime()


def gated(d):
    return d is not None and CUTOFF <= d <= NOW


out = []
for folder in sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("_")):
    acc = json.loads((folder / "_account.json").read_text())
    r = {"slug": folder.name, "name": acc.get("name_for_upload"),
         "canonical_domain": norm(acc.get("domain")),
         "audit_consideration": ((acc.get("domain_audit") or {}).get("considerations") or "")}

    fm = rows(folder, "firmographics")
    r["firmo"] = len(fm)
    runtime = ""
    if fm:
        for fld in ("Company Domain", "Website"):
            if c(fm[0].get(fld)):
                runtime = norm(fm[0][fld]); break
    r["runtime_domain"] = runtime
    r["firmo_desc"] = bool(fm and c(fm[0].get("Business Description")))
    r["domain_conflict"] = bool(runtime and r["canonical_domain"] and runtime != r["canonical_domain"])

    h = rows(folder, "company_hierarchy")
    r["hierarchy"] = len(h)
    r["hierarchy_parent"] = any(c(x.get("Parent Company Name")) for x in h)

    t = rows(folder, "technographics")
    r["techno"] = len(t)
    r["techno_stack"] = any(c(x.get("Full Tech Stack")) for x in t)
    w = rows(folder, "webstack")
    r["webstack"] = len(w)
    r["webstack_tech"] = any(c(x.get("Technologies Used By Company Website")) for x in w)
    td = rows(folder, "technology_detections")
    r["tech_detect"] = len(td)
    r["tech_detect_named"] = sum(1 for x in td if c(x.get("technology_name")) or c(x.get("technology")))

    it = rows(folder, "intent_topics")
    r["intent_topics"] = len(it)
    sites = [norm(x.get("Company Website")) for x in it if c(x.get("Company Website"))]
    r["topics_mismatch"] = bool(sites) and runtime not in sites
    r["intent_score"] = len(rows(folder, "intent_score"))

    cat = raw_rows(folder, "hp_category_intent")
    r["cat_rows"] = max(0, len([x for x in cat[2:] if any(c(y) for y in x)]))
    r["cat_match"] = False
    r["cat_scored"] = False
    if len(cat) >= 3:
        hdr = [c(x).lower() for x in cat[1]]
        di = hdr.index("domain") if "domain" in hdr else 1
        ti = hdr.index("top intent score (/100)") if "top intent score (/100)" in hdr else 4
        for rec in cat[2:]:
            if len(rec) > di and norm(rec[di]) == runtime and runtime:
                r["cat_match"] = True
                if len(rec) > ti and c(rec[ti]) and c(rec[3]).lower() != "unavailable":
                    r["cat_scored"] = True
    r["cat_usable"] = r["cat_match"] and r["cat_scored"]

    pc = rows(folder, "prospect_contacts")
    r["contacts"] = len(pc)
    r["contacts_titled"] = sum(1 for x in pc if c(x.get("Prospect job_title")) or c(x.get("apollo_title")))
    r["contacts_email"] = sum(1 for x in pc if c(x.get("Email")) or c(x.get("Contact professions_email")) or c(x.get("apollo_verified_work_email")))
    r["contacts_flagged"] = sum(1 for x in pc if c(x.get("review_flags")))
    srcs = collections.Counter(c(x.get("data_source")) or "?" for x in pc)
    r["contacts_source"] = "; ".join(sorted(srcs))

    jo = rows(folder, "job_openings")
    r["jobs"] = len(jo)
    r["jobs_status_blank_all"] = bool(jo) and all(not c(x.get("status")) for x in jo)

    gn = rows(folder, "google_news")
    r["gnews"] = len(gn)
    r["gnews_pass"] = sum(1 for x in gn
                          if (c(x.get("event_headline")) or c(x.get("news_announcements")) or c(x.get("event_summary")))
                          and gated(dt(x.get("event_date"))))
    ne = rows(folder, "news_events")
    r["news_events"] = len(ne)
    ne_pass = ne_future = 0
    idstat = collections.Counter()
    for x in ne:
        if not (c(x.get("summary")) or c(x.get("article_sentence")) or c(x.get("event"))):
            continue
        d = dt(x.get("effective_date")) or dt(x.get("found_at"))
        if d and d > NOW:
            ne_future += 1
        if gated(d):
            ne_pass += 1
        idstat[c(x.get("identity_status"))] += 1
    r["news_events_pass"] = ne_pass
    r["news_events_future"] = ne_future
    r["pl_identity"] = "; ".join(f"{k}:{v}" for k, v in idstat.most_common(3))

    cf = folder / "compliance_filings"
    r["pdfs"] = len(list(cf.glob("*.pdf"))) if cf.exists() else 0
    idx = cf / "_filings_index.csv"
    r["filings_index"] = len(rows(cf, "_filings_index")) if idx.exists() else 0
    out.append(r)

df = pd.DataFrame(out)
df.to_csv(sys.argv[1] if len(sys.argv) > 1 else "profile.csv", index=False)
print(len(df), "accounts profiled")
