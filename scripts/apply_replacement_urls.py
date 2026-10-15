"""Put the client's replacement news links into the account split.

The client's 14 Oct workbook (HP_220_Live_Signals_With_Replacement_URLs_2026-10-14.xlsx)
has two tabs:

  Dead links          a google_news.csv event_url that no longer resolves, and
                      the URL to use instead -> replaces event_url
  No link in the file a news_events.csv row (PredictLeads carries no link)
                      and the article URL for it -> fills source_url

Only rows whose Status is AUTO_ACCEPTED (rule-verified) or AI_APPROVED are
applied; REVIEW / UNRESOLVED rows are reported and left alone. "Position in
Live Signals" is the card's place in a scored order that changes every run,
so rows are found by account + headline + event date instead.

Each changed CSV is backed up first. A report with one line per workbook row
goes to <split>/_replacement_urls_<date>_report.csv. Upload the touched
accounts afterwards (split_account_data.py --upload --regenerate --accounts ...).

    python scripts/apply_replacement_urls.py WORKBOOK [--dry-run]
"""
import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT_DIR = REPO_ROOT / "220 account split csv"
ENCODING = "utf-8-sig"
ACCEPTED = {"AUTO_ACCEPTED", "AI_APPROVED"}
TAG = "2026-10-14"


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def headline(row: dict) -> str:
    # The same fallback the backend uses for a news_events card's headline.
    for k in ("summary", "article_sentence", "event"):
        if _s(row.get(k)):
            return _s(row[k])
    return ""


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, encoding=ENCODING, newline="") as fh:
        rd = csv.DictReader(fh)
        return list(rd.fieldnames or []), list(rd)


def write_csv(path: Path, cols: list[str], rows: list[dict]) -> None:
    with open(path, "w", encoding=ENCODING, newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def sheet(wb, name: str) -> list[dict]:
    rows = list(wb[name].iter_rows(values_only=True))
    head = [_s(h) for h in rows[0]]
    return [dict(zip(head, r)) for r in rows[1:]]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("workbook", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="report only, change no file")
    args = ap.parse_args()

    folder = {}
    for f in SPLIT_DIR.glob("*/_account.json"):
        folder[json.loads(f.read_text(encoding="utf-8"))["name_for_upload"]] = f.parent

    files: dict[Path, tuple[list[str], list[dict]]] = {}

    def load(path: Path):
        if path not in files:
            files[path] = read_csv(path)
        return files[path]

    # Accounts the workbook names by a short name ("Astra") are found by headline.
    by_headline = defaultdict(set)
    for path in SPLIT_DIR.glob("*/news_events.csv"):
        for r in load(path)[1]:
            by_headline[headline(r)].add(path.parent)

    wb = openpyxl.load_workbook(args.workbook, read_only=True, data_only=True)
    report, changed = [], set()

    for w in sheet(wb, "Dead links"):
        acct, old, new, status = _s(w["Account"]), _s(w["Link"]), _s(w["Replacement_URL"]), _s(w["Status"])
        line = {"tab": "Dead links", "account": acct, "headline": _s(w["Headline"]),
                "event_date": _s(w["Event date"]), "status": status, "url": new}
        if status not in ACCEPTED or not new:
            report.append(dict(line, result="skipped: " + (status or "no replacement"))); continue
        acct_dir = folder.get(acct)
        hits = []
        for path in ([acct_dir / "google_news.csv"] if acct_dir else SPLIT_DIR.glob("*/google_news.csv")):
            if path.exists():
                hits += [(path, r) for r in load(path)[1] if _s(r.get("event_url")) == old]
        for path, r in hits:
            r["event_url"] = new
            changed.add(path)
        report.append(dict(line, file=str(hits[0][0].relative_to(SPLIT_DIR)) if hits else "",
                           result=f"applied ({len(hits)} row)" if hits else "not matched: old link not in google_news.csv"))

    for w in sheet(wb, "No link in the file"):
        acct, new, status = _s(w["Account"]), _s(w["Replacement_URL"]), _s(w["Status"])
        head, day = _s(w["Headline"]), _s(w["Event date"])[:10]
        line = {"tab": "No link in the file", "account": acct, "headline": head,
                "event_date": day, "status": status, "url": new}
        if status not in ACCEPTED or not new:
            report.append(dict(line, result="skipped: " + (status or "no replacement"))); continue
        dirs = [folder[acct]] if acct in folder else sorted(by_headline.get(head, ()))
        if len(dirs) != 1:
            report.append(dict(line, result=f"not matched: account resolves to {len(dirs)} folders")); continue
        path = dirs[0] / "news_events.csv"
        rows = [r for r in load(path)[1] if headline(r) == head]
        dated = [r for r in rows if day in (_s(r.get("effective_date"))[:10], _s(r.get("found_at"))[:10])]
        hits = dated or rows
        if not hits:
            report.append(dict(line, file=str(path.relative_to(SPLIT_DIR)), result="not matched: headline not in news_events.csv")); continue
        # Identical headline + date rows are one card after the backend's dedupe.
        for r in hits:
            r["source_url"] = new
            note = f"client replacement URL {TAG} ({status})"
            old_note = _s(r.get("verification_note"))
            r["verification_note"] = note if not old_note or note in old_note else f"{old_note}; {note}"
        changed.add(path)
        report.append(dict(line, file=str(path.relative_to(SPLIT_DIR)),
                           result=f"applied ({len(hits)} row{'s' if len(hits) > 1 else ''})"
                           + ("" if dated else "; date differs, matched on headline")))

    out = SPLIT_DIR / f"_replacement_urls_{TAG}_report.csv"
    with open(out, "w", encoding=ENCODING, newline="") as fh:
        cols = ["tab", "account", "headline", "event_date", "status", "url", "file", "result"]
        wr = csv.DictWriter(fh, fieldnames=cols, lineterminator="\n")
        wr.writeheader()
        wr.writerows(report)

    tally = defaultdict(int)
    for r in report:
        tally[(r["tab"], r["result"].split(" (")[0].split(":")[0])] += 1
    for k, v in sorted(tally.items()):
        print(f"{k[0]:20} {k[1]:12} {v}")
    accounts = sorted({p.parent.name for p in changed})
    print(f"{len(changed)} file(s) in {len(accounts)} account(s) to change; report: {out}")

    if args.dry_run:
        return
    backup = SPLIT_DIR / f"_backup_replacement_urls_{TAG}"
    for path in changed:
        dest = backup / path.parent.name / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(path, dest)
        write_csv(path, *files[path])
    (SPLIT_DIR / f"_replacement_urls_{TAG}_accounts.txt").write_text(",".join(accounts), encoding="utf-8")
    print(f"written; originals in {backup}")


if __name__ == "__main__":
    main()
