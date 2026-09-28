"""Run the new-source extraction over every split account folder, offline.

Dhruvi's 27 Sep email names three sources the pipeline did not read in full:
filings (filings 1.csv + PredictLeads sec_filings), Related Technologies, and
Explorium Tech_Breakdown. The split keeps them in the files the application
already defines:

  compliance_filings/_filings_index.csv   filings 1.csv + PredictLeads rows
  compliance_filings/predictleads_sec_*.pdf  each PredictLeads filing's text
  webstack.csv                            + "Tech Breakdown - <category>" columns
  hp_category_intent.csv                  Related Technologies (unchanged)

This runs the SAME functions the producers call - `filings_register.register`
for the Executive Dashboard's filings list, `pdf.read_pdf` + the corpus's
narrative page test for the PredictLeads PDFs, `_parse_tech_breakdown` and the
category-file parse for the Technographic Map - so the output for all 220
accounts can be checked before any upload. No database, no LLM.

Writes, under project-documentation/07_Internal_Generated/Analysis/:
  NEW_SOURCES_EXTRACTION_220.csv   one row per account
  NEW_SOURCES_EXTRACTION_220.json  the widget fields each account would get

Run from the repo root: hp-backend/.venv/bin/python scripts/extract_new_sources_220.py
"""

import csv
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "hp-backend" / "src"))
csv.field_size_limit(sys.maxsize)

from app.services.dashboard import filings_register  # noqa: E402
from app.services.extractors.intent_demand_signals import (  # noqa: E402
    _norm_domain,
    _parse_category_file,
)
from app.services.extractors.tech_landscape import _parse_tech_breakdown  # noqa: E402
from app.services.retrieval import corpus, pdf  # noqa: E402

SPLIT = REPO / "220 account split csv"
OUT = REPO / "project-documentation" / "07_Internal_Generated" / "Analysis"


def records(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def rows(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.reader(fh))


def narrative_pages(path: Path) -> tuple[int, list]:
    """(pages read back, pages that pass the corpus's narrative test)."""
    doc = pdf.read_pdf(str(path))
    passing = []
    for page in doc["pages"]:
        themes = [n for n, pat in corpus.PRIORITY_THEMES.items()
                  if re.search(pat, page["text"], re.I)]
        if (len(themes) >= corpus.MIN_NARRATIVE_THEMES
                and corpus._sentence_share(page["text"]) >= corpus.MIN_SENTENCE_SHARE):
            passing.append({"page": page["page"], "themes": themes})
    return len(doc["pages"]), passing


def main():
    as_of = datetime.now(UTC).date()
    table, detail = [], {}
    for folder in sorted(p for p in SPLIT.iterdir() if (p / "_account.json").exists()):
        ident = json.loads((folder / "_account.json").read_text())
        name = ident.get("name_for_upload") or folder.name
        firmo = records(folder / "firmographics.csv")
        # The runtime domain: firmographics' Company Domain, as account_domain() resolves it.
        domain = _norm_domain((firmo[0].get("Company Domain") if firmo else "")
                              or ident.get("domain") or "")

        # --- Executive Dashboard: filings list + PDFs
        filing_dir = folder / "compliance_filings"
        index = records(filing_dir / "_filings_index.csv")
        filings = filings_register.register(index, as_of=as_of)
        all_pdfs = sorted(filing_dir.glob("*.pdf")) if filing_dir.exists() else []
        pl_pdfs = [p for p in all_pdfs if filings_register.is_predictleads_file(p.name)]
        pl_read, pl_narrative = 0, []
        for p in pl_pdfs:
            n, passing = narrative_pages(p)
            pl_read += n
            pl_narrative += [{"file": p.name, **x} for x in passing]

        # --- Technographic Map: Tech_Breakdown (in webstack) + Related Technologies
        webstack = records(folder / "webstack.csv")
        breakdown = _parse_tech_breakdown(webstack)
        cat = _parse_category_file(rows(folder / "hp_category_intent.csv"), domain)
        researched = []
        if cat.get("status") == "matched":
            for cname, entry in (cat.get("categories") or {}).items():
                techs = [t for t in (entry.get("related_technologies") or []) if t]
                if techs:
                    researched.append({"hp_category": cname, "technologies": techs})
        techno = records(folder / "technographics.csv")
        full_stack = [t for t in str((techno[0].get("Full Tech Stack") if techno else "") or "")
                      .split(",") if t.strip()]

        table.append({
            "account": name,
            "domain": domain,
            "filings_list_rows": len(index),
            "filings_list_predictleads_rows": sum(1 for r in index
                                                  if filings_register.is_predictleads(r)),
            "filings_on_record_12m": filings["in_window"],
            "filings_excluded_no_url": filings["excluded"]["no_url"],
            "filings_excluded_older": filings["excluded"]["outside_window"],
            "filings_excluded_undated": filings["excluded"]["undated"],
            "filings_duplicates": filings["excluded"]["duplicate"],
            "latest_filing": filings["filings"][0]["filed_on"] if filings["filings"] else "",
            "filing_pdfs": len(all_pdfs),
            "predictleads_pdfs": len(pl_pdfs),
            "predictleads_pdf_pages_read": pl_read,
            "predictleads_narrative_pages": len(pl_narrative),
            "tech_breakdown_categories": len([c for c in breakdown if not c["page_metadata"]]),
            "tech_breakdown_technologies": sum(len(c["technologies"]) for c in breakdown
                                               if not c["page_metadata"]),
            "intent_file_status": cat.get("status"),
            "related_tech_categories": len(researched),
            "related_technologies": sum(len(r["technologies"]) for r in researched),
            "technographics_detected": len(full_stack),
            "researched_only": bool(researched) and not full_stack,
        })
        detail[name] = {
            "exec_key_metrics.filings_on_record": filings,
            "exec_dashboard_index.predictleads_narrative_pages": pl_narrative,
            "webstack_breakdown.breakdown": breakdown,
            "technographic_map.researched_technologies": researched,
        }

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "NEW_SOURCES_EXTRACTION_220.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(table[0]))
        w.writeheader()
        w.writerows(table)
    (OUT / "NEW_SOURCES_EXTRACTION_220.json").write_text(
        json.dumps({"generated_at": datetime.now(UTC).isoformat(), "as_of": as_of.isoformat(),
                    "accounts": detail}, indent=1, ensure_ascii=False, default=str))

    n = len(table)

    def have(k):
        return sum(1 for r in table if r[k])
    print(f"accounts: {n}")
    for k in ("filings_list_rows", "filings_list_predictleads_rows", "filings_on_record_12m",
              "filing_pdfs", "predictleads_pdfs", "predictleads_pdf_pages_read",
              "predictleads_narrative_pages", "tech_breakdown_categories",
              "related_tech_categories", "researched_only"):
        print(f"  {k:32} {have(k):4} accounts   total {sum(int(r[k]) for r in table)}")
    print("  intent file status:", {s: sum(1 for r in table if r['intent_file_status'] == s)
                                    for s in sorted({r['intent_file_status'] for r in table})})


if __name__ == "__main__":
    main()
