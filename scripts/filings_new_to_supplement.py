#!/usr/bin/env python3
"""Turn the client's `filings new.csv` (29 Sep) into a filings supplement.

The split (split_account_data.py) and the downloader (fetch_filings.py) read
filings 1.csv plus supplements in filings 1.csv's exact columns. This writes
the new list's rows in those columns, keeping only what adds something:

  * rows with no filing to fetch are left out - the list marks unlisted and
    government bodies with nothing to file as SOVEREIGN_NON_CORPORATE /
    UNAVAILABLE_UNLISTED (validation_status EXPLAINED_NOT_APPLICABLE);
  * a document already listed (same document_url in filings 1.csv or an
    earlier supplement) or already on disk (same sha256 as a placed PDF) is
    left out, so no account gets the same filing twice.

row_id becomes "N29-<row_id>" so it cannot collide with filings 1.csv's. The
new list's extra column, filing_number, is dropped (not in filings 1.csv).

Usage
    python3 scripts/filings_new_to_supplement.py
"""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILINGS_DIR = ROOT / "project-documentation" / "04_Data_and_Source_Definitions" / "Filings"
SOURCE = ROOT / "filings new.csv"
BASE = FILINGS_DIR / "filings 1.csv"
EARLIER = [FILINGS_DIR / "filings_client_supplement_2026-09-26.csv"]
OUT = FILINGS_DIR / "filings_client_supplement_2026-09-29.csv"
REPORT = ROOT / "220 account split csv" / "_filings_download_report.csv"
ENCODING = "utf-8-sig"

NO_FILING = {"SOVEREIGN_NON_CORPORATE", "UNAVAILABLE_UNLISTED"}
# (sales territory, company) of rows left out by an existing client ruling.
# DEC-054f: Astra's own documents belong to PT_ASTRA_INTERNATIONAL_TBK, not to
# its subsidiary FIF (fetch_filings.FILINGS_OVERRIDES drops the same pair).
RULED_OUT = {("FEDERAL INTERNATIONAL FINANCE, PT - ID", "Astra International Group"):
             "Astra's document under FIF (DEC-054f: filed under Astra)"}


def read(path: Path) -> tuple[list[dict], list[str]]:
    with open(path, encoding=ENCODING, newline="") as fh:
        reader = csv.DictReader(fh)
        return list(reader), list(reader.fieldnames)


def main() -> None:
    new_rows, _ = read(SOURCE)
    base_rows, columns = read(BASE)
    known_urls = {r["document_url"].strip() for r in base_rows if r["document_url"].strip()}
    for path in EARLIER:
        if path.exists():
            known_urls |= {r["document_url"].strip() for r in read(path)[0]
                           if r["document_url"].strip()}
    on_disk = {r["sha256"] for r in read(REPORT)[0] if r.get("file") and r.get("sha256")}

    kept, why = [], Counter()
    for row in new_rows:
        if row["download_status"] in NO_FILING:
            why["no filing (not listed / sovereign)"] += 1
            continue
        ruling = RULED_OUT.get((row["sales_territory_name"], row["company"]))
        if ruling:
            why[ruling] += 1
            continue
        if row["document_url"].strip() in known_urls:
            why["already in filings 1.csv"] += 1
            continue
        if row["sha256"] and row["sha256"] in on_disk:
            why["same document already on disk"] += 1
            continue
        out = {c: row.get(c, "") for c in columns}
        out["row_id"] = "N29-%s" % row["row_id"]
        kept.append(out)
        why["added"] += 1

    with open(OUT, "w", encoding=ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(kept)
    print("%d row(s) in %s -> %d kept in %s" % (len(new_rows), SOURCE.name, len(kept),
                                                OUT.relative_to(ROOT)))
    for reason, n in why.most_common():
        print("  %4d  %s" % (n, reason))


if __name__ == "__main__":
    main()
