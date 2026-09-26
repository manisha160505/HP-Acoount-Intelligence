#!/usr/bin/env python3
"""Download the filing documents listed in filings 1.csv into the account split.

Route B of project-documentation/07_Internal_Generated/Engineering/
FILINGS_PLAN_2026-09-25.md. Reads, never writes, filings 1.csv.

Which account a row belongs to is not decided here. It is read back from the
split's own compliance_filings/_filings_index.csv files and
_unassigned_filings.csv (written by split_account_data.assign_filings), with
exactly the overrides in FILINGS_OVERRIDES on top: the client's written
re-keys (DEC-054f) and rows held back because the document is plainly another
company's and nobody has ruled on it.

URL rule (client, 18 Sep, DEC-025): document_url first, source_page_url as the
fallback, never local_path; a row with neither is excluded. A failed file is
skipped, not the company (opens_2 item 12).

Only responses that are real PDFs are kept - the compliance_filings dataset
accepts .pdf only (schemas/account_data.py) and services/retrieval/pdf.py reads
it with PyMuPDF. HTML viewer pages, JSON and error pages are recorded as
non-document responses, not converted.

Output
    <split>/<ACCOUNT>/compliance_filings/<file>.pdf     placed documents
    Filings/pdfs/_unplaced/<file>.pdf                   downloaded, not placed
    Filings/pdfs/_manual/<file>.pdf                     INPUT: browser downloads for
                                                        hosts that block scripts
    <split>/_filings_download_report.csv                one row per CSV row
    <split>/_filings_download_summary.json              the counts

Usage
    hp-backend/.venv/bin/python scripts/fetch_filings.py [--limit N] [--host H]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse as up
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SPLIT_DIR = REPO_ROOT / "220 account split csv"
FILINGS_DIR = REPO_ROOT / "project-documentation" / "04_Data_and_Source_Definitions" / "Filings"
FILINGS_CSV = FILINGS_DIR / "filings 1.csv"
# Client-supplied rows in filings 1.csv's columns, appended after it (the
# split reads the same list - FILINGS_SUPPLEMENT_FILES in split_account_data).
FILINGS_SUPPLEMENTS = [FILINGS_DIR / "filings_client_supplement_2026-09-26.csv"]
UNPLACED_DIR = FILINGS_DIR / "pdfs" / "_unplaced"
# PDFs downloaded by hand in a browser, for hosts that refuse scripts
# (bankmandiri.co.id hangs; investor.cimbniaga.co.id serves an AWS WAF
# challenge). A file here is used for a URL when its name equals a .pdf path
# segment of that URL, "+" and %-escapes decoded - which is what a browser
# saves it as. Checked before the network, after files reused from last run.
MANUAL_DIR = FILINGS_DIR / "pdfs" / "_manual"
REPORT_CSV = SPLIT_DIR / "_filings_download_report.csv"
SUMMARY_JSON = SPLIT_DIR / "_filings_download_summary.json"
ENCODING = "utf-8-sig"

# (account the split filed the row under, company column) -> what to do.
# "move" re-keys to another account, "drop" and "hold" keep the row out of
# every account folder. Each entry names its authority.
FILINGS_OVERRIDES = {
    ("SUNWAY_HOLDINGS_INCORPORATED_BHD", "FLETCHER BUILDING HOLDINGS NEW ZEALAND LIMITED"):
        ("move", "FLETCHER_BUILDING_HOLDINGS_LIMITED",
         "client re-key DEC-054f: Fletcher Building Holdings NZ -> fletcherbuilding.com"),
    ("UNITED_OVERSEAS_BANK_MALAYSIA_BHD", "FONTERRA CO-OPERATIVE GROUP LIMITED"):
        ("move", "FONTERRA_CO_OPERATIVE_GROUP_LIMITED",
         "client re-key DEC-054f: Fonterra -> fonterra.com"),
    ("FEDERAL_INTERNATIONAL_FINANCE_PT", "Astra International Group"):
        ("drop", "PT_ASTRA_INTERNATIONAL_TBK",
         "Astra's own document (r2.astra.co.id) also indexed under PT_ASTRA_INTERNATIONAL_TBK; "
         "DEC-054f re-keys Astra rows to Astra, so not repeated under FIF"),
    ("MITRA_ADHI_PERKASA", "PT Bank Negara Indonesia (Persero) Tbk"):
        ("hold", "",
         "territory says Mitra Adhi Perkasa but the document is Bank Negara Indonesia's "
         "(bni.co.id), which is not one of the 220; no client ruling - not guessed"),
    # Charoen Pokphand's only row; the document is another group's.
    ("CHAROEN_POKPHAND_GROUP_CO_LTD", "CHAROEN POKPHAND GROUP CO LTD"):
        ("hold", "",
         "document is Central Pattana's (investor.centralpattana.co.th, Central Group), not "
         "Charoen Pokphand's; no client ruling - not guessed"),
    ("VIETNAM_POST_CORPORATION", "VIETNAM POST CORPORATION"):
        ("hold", "",
         "document is VPBank's (vpbank.com.vn) filed under Vietnam Post; the client's C1 "
         "answer (25 Sep 12:02 UTC attachment) is not on this machine - not guessed"),
}

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
HEADERS = {"User-Agent": USER_AGENT,
           "Accept": "application/pdf,text/html;q=0.9,*/*;q=0.8",
           "Accept-Language": "en;q=0.9"}
PER_HOST_DELAY = 1.0          # seconds between requests to one host
DEADLINE = 300                # seconds per URL, retries included
MAX_BYTES = 300 * 1024 * 1024
RETRIES = 2

REPORT_COLUMNS = [
    "src_row", "company", "country", "sales_territory_name", "domain",
    "document_title", "document_type", "reporting_period", "fiscal_year",
    "publication_date", "source_page_url", "document_url", "index_sha256",
    "index_download_status", "index_error",
    "split_account", "account_slug", "placement", "placement_reason",
    "url_used", "url_field", "http_status", "content_type", "status", "error",
    "bytes", "sha256", "sha256_matches_index", "pages", "file",
    "duplicate_of_src_row", "downloaded_at",
]


# --------------------------------------------------------------------------
# Mapping: read back from the split, overrides on top
# --------------------------------------------------------------------------

def _read(path: Path) -> list[dict]:
    with open(path, newline="", encoding=ENCODING) as fh:
        return list(csv.DictReader(fh))


def load_rows() -> tuple[list[dict], list[str]]:
    with open(FILINGS_CSV, newline="", encoding=ENCODING) as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        columns = list(reader.fieldnames)
    for path in FILINGS_SUPPLEMENTS:
        if path.exists():
            with open(path, newline="", encoding=ENCODING) as fh:
                reader = csv.DictReader(fh)
                if list(reader.fieldnames) != columns:
                    raise SystemExit(f"{path.name} does not have filings 1.csv's columns")
                rows += list(reader)
    for i, row in enumerate(rows, start=1):
        row["src_row"] = i
    return rows, columns


def split_assignment(rows: list[dict], columns: list[str]) -> None:
    """Set row["split_account"] from the split's own files; '' = unassigned.

    Index rows are verbatim copies of source rows, so a full-row key finds
    them; a Counter handles rows the source repeats word for word.
    """
    def key(r):
        return tuple(r.get(c, "") for c in columns)

    pending: dict[tuple, list[str]] = defaultdict(list)
    for path in sorted(SPLIT_DIR.glob("*/compliance_filings/_filings_index.csv")):
        slug = path.parent.parent.name
        for r in _read(path):
            pending[key(r)].append(slug)
    unassigned = Counter(key(r) for r in _read(SPLIT_DIR / "_unassigned_filings.csv"))
    unassigned_reason = {key(r): r.get("reason", "") for r in
                         _read(SPLIT_DIR / "_unassigned_filings.csv")}

    for row in rows:
        k = key(row)
        if pending.get(k):
            row["split_account"] = pending[k].pop(0)
            row["split_reason"] = ""
        elif unassigned[k]:
            unassigned[k] -= 1
            row["split_account"] = ""
            row["split_reason"] = unassigned_reason.get(k, "")
        else:
            raise SystemExit(f"source row {row['src_row']} is in neither an index nor "
                             f"_unassigned_filings.csv - the split is out of date; re-run it")
    left = sum(len(v) for v in pending.values()) + sum(unassigned.values())
    if left:
        raise SystemExit(f"{left} split row(s) match no source row - the split is out of date")


def decide_placement(rows: list[dict]) -> None:
    by_account_url = defaultdict(set)
    for row in rows:
        if row["split_account"]:
            by_account_url[row["split_account"]].add(row["document_url"])

    for row in rows:
        slug = row["split_account"]
        rule = FILINGS_OVERRIDES.get((slug, row["company"]))
        if not slug:
            row.update(account_slug="", placement="unassigned",
                       placement_reason=row["split_reason"])
        elif rule is None:
            row.update(account_slug=slug, placement="placed",
                       placement_reason=f"split: matched_by index ({slug})")
        elif rule[0] == "move":
            row.update(account_slug=rule[1], placement="placed", placement_reason=rule[2])
        elif rule[0] == "drop":
            if row["document_url"] not in by_account_url[rule[1]]:
                raise SystemExit(f"row {row['src_row']}: expected the same document_url "
                                 f"under {rule[1]} - check the override")
            row.update(account_slug="", placement="excluded_duplicate", placement_reason=rule[2])
        else:
            row.update(account_slug="", placement="held", placement_reason=rule[2])


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

_host_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)
_host_last: dict[str, float] = {}


def _polite(host: str) -> None:
    with _host_locks[host]:
        wait = PER_HOST_DELAY - (time.monotonic() - _host_last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        _host_last[host] = time.monotonic()


def _looks_pdf(head: bytes) -> bool:
    return b"%PDF-" in head[:1024]


def fetch(url: str) -> dict:
    """One URL -> {ok, tmp, http_status, content_type, error, bytes, sha256}.

    curl rather than requests: --max-time is a hard wall clock, and some hosts
    hold a TLS connection open without sending, which no per-read timeout ends.
    """
    host = up.urlparse(url).netloc.lower()
    out = {"ok": False, "tmp": None, "http_status": "", "content_type": "", "error": "",
           "bytes": 0, "sha256": ""}
    _polite(host)
    fd, tmp = tempfile.mkstemp(suffix=".part", dir=UNPLACED_DIR.parent)
    os.close(fd)
    cmd = ["curl", "-sS", "-L", "--compressed", "-A", USER_AGENT,
           "-H", "Accept: " + HEADERS["Accept"], "-H", "Accept-Language: " + HEADERS["Accept-Language"],
           "--connect-timeout", "20", "--max-time", str(DEADLINE),
           "--retry", str(RETRIES), "--retry-delay", "3", "--retry-max-time", str(DEADLINE),
           "--max-filesize", str(MAX_BYTES), "-o", tmp, "-w", "%{http_code}\t%{content_type}", url]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3 * DEADLINE)
        code, _, ctype = proc.stdout.partition("\t")
        out["http_status"] = code if code not in ("", "000") else ""
        out["content_type"] = ctype.split(";")[0].strip()
        if proc.returncode != 0:
            out["error"] = f"curl exit {proc.returncode}: {proc.stderr.strip()[:200]}"
        elif code.isdigit() and int(code) >= 400:
            out["error"] = f"HTTP {code}"
    except subprocess.TimeoutExpired:
        out["error"] = f"no answer within {3 * DEADLINE}s"
    if out["error"]:
        os.unlink(tmp)
        return out

    size = os.path.getsize(tmp)
    with open(tmp, "rb") as fh:
        head = fh.read(1024)
    out.update(bytes=size, sha256=_sha_file(Path(tmp)))
    if not _looks_pdf(head):
        os.unlink(tmp)
        snippet = re.sub(r"\s+", " ", head[:120].decode("utf-8", "replace"))
        out["error"] = (f"non-PDF response ({out['content_type'] or 'no type'}, "
                        f"{size} bytes): {snippet}")
        return out
    out.update(ok=True, tmp=tmp)
    return out


def previous_downloads() -> dict:
    """{url: (file, sha256, bytes, downloaded_at)} from the last report, for files still on disk."""
    if not REPORT_CSV.exists():
        return {}
    out = {}
    for r in _read(REPORT_CSV):
        if r.get("status") == "downloaded" and r.get("url_used") and r.get("file"):
            out.setdefault(r["url_used"], (REPO_ROOT / r["file"], r["sha256"], r["bytes"],
                                          r.get("downloaded_at", "")))
    return out


def manual(url: str) -> dict | None:
    """A temp copy of a hand-downloaded PDF for url from MANUAL_DIR, else None."""
    if not MANUAL_DIR.exists():
        return None
    names = {up.unquote_plus(seg) for seg in up.urlparse(url).path.split("/")
             if seg.lower().endswith(".pdf")}
    for name in names:
        path = MANUAL_DIR / name
        if path.is_file():
            with open(path, "rb") as fh:
                if not _looks_pdf(fh.read(1024)):
                    return None
            fd, tmp = tempfile.mkstemp(suffix=".part", dir=UNPLACED_DIR.parent)
            with os.fdopen(fd, "wb") as b, open(path, "rb") as a:
                b.write(a.read())
            return {"ok": True, "tmp": tmp, "http_status": "manual",
                    "content_type": "application/pdf", "error": "",
                    "bytes": path.stat().st_size, "sha256": _sha_file(path)}
    return None


def reused(url: str, reuse: dict) -> dict | None:
    """A temp copy of the file an earlier run downloaded from url, if its
    sha256 on disk is still what that run recorded; else None (fetch again)."""
    hit = reuse.get(url)
    if not hit or not hit[0].exists() or _sha_file(hit[0]) != hit[1]:
        return None
    fd, tmp = tempfile.mkstemp(suffix=".part", dir=UNPLACED_DIR.parent)
    with os.fdopen(fd, "wb") as b, open(hit[0], "rb") as a:
        b.write(a.read())
    return {"ok": True, "tmp": tmp, "http_status": "reused", "content_type": "application/pdf",
            "error": "", "bytes": int(hit[2] or 0), "sha256": hit[1], "downloaded_at": hit[3]}


def pdf_pages(path: str) -> tuple[int, str]:
    import pymupdf
    try:
        with pymupdf.open(path) as doc:
            return doc.page_count, ""
    except Exception as exc:  # noqa: BLE001 - any failure means unreadable
        return 0, f"PyMuPDF cannot open it: {exc}"


# --------------------------------------------------------------------------
# Naming and placement
# --------------------------------------------------------------------------

def _clean_name(value: str) -> str:
    value = re.sub(r"[^\w.\-]+", "_", value, flags=re.ASCII).strip("._")
    return re.sub(r"_+", "_", value)[:150]


def base_filename(row: dict) -> str:
    """The crawler's own filename (basename of local_path) - deterministic and
    what the client's Drive copy is called. Only the name is used, never the
    path. Rows without one get company_period_row."""
    name = os.path.basename(row.get("local_path", "").replace("\\", "/"))
    if name.lower().endswith(".pdf"):
        return _clean_name(name[:-4]) + ".pdf"
    stem = f"{row['company']}_{row.get('reporting_period') or row.get('fiscal_year')}_row{row['src_row']}"
    return _clean_name(stem.lower()) + ".pdf"


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def place(row: dict, result: dict, folder: Path, seen: dict) -> None:
    """Move the downloaded temp file into folder, never overwriting a
    different document. seen: {(folder, sha256): (file, src_row)}."""
    folder.mkdir(parents=True, exist_ok=True)
    sha = result["sha256"]
    if (folder, sha) in seen:
        name, first = seen[(folder, sha)]
        row.update(status="duplicate_document", file=str((folder / name).relative_to(REPO_ROOT)),
                   duplicate_of_src_row=first)
        os.unlink(result["tmp"])
        return
    name = base_filename(row)
    target = folder / name
    if target.exists() and _sha_file(target) != sha:
        target = folder / f"{target.stem}__row{row['src_row']}.pdf"
    if target.exists() and _sha_file(target) == sha:
        os.unlink(result["tmp"])
    else:
        os.replace(result["tmp"], target)
    seen[(folder, sha)] = (target.name, row["src_row"])
    row.update(status="downloaded", file=str(target.relative_to(REPO_ROOT)))


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="first N URL rows only (testing)")
    ap.add_argument("--host", default="", help="only URLs on this host (testing)")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--refetch", action="store_true",
                    help="download every URL again instead of reusing files the last "
                         "report recorded (reused only when the sha256 on disk still matches)")
    args = ap.parse_args()

    rows, columns = load_rows()
    split_assignment(rows, columns)
    decide_placement(rows)
    UNPLACED_DIR.mkdir(parents=True, exist_ok=True)

    # Which rows get a download attempt: every row with a URL, placed or not,
    # so held and unassigned rows can be placed later by moving a file.
    todo = []
    for row in rows:
        # sha256 / error in the source are the crawler's; keep them apart
        # from what this run measures.
        row["index_sha256"], row["index_error"] = row.get("sha256", ""), row.get("error", "")
        row["index_download_status"] = row.get("download_status", "")
        row.update(sha256="", error="")
        row.update({c: "" for c in REPORT_COLUMNS if c not in row})
        doc, src = row["document_url"].strip(), row["source_page_url"].strip()
        if not doc.startswith("http") and not src.startswith("http"):
            row["status"] = "url_missing"
            row["error"] = "document_url and source_page_url both blank - excluded (DEC-025)"
            continue
        if row["placement"] == "excluded_duplicate":
            row["status"] = "not_attempted"
            row["error"] = "same document_url is fetched for its own account"
            continue
        if args.host and args.host not in up.urlparse(doc or src).netloc:
            row["status"] = "not_attempted"
            continue
        todo.append(row)
    if args.limit:
        for row in todo[args.limit:]:
            row["status"] = "not_attempted"
        todo = todo[:args.limit]

    reuse = {} if args.refetch else previous_downloads()

    # One fetch per distinct URL; rows sharing a URL share the result.
    cache: dict[str, dict] = {}
    cache_lock = threading.Lock()
    url_events: dict[str, threading.Event] = {}

    def get(url: str) -> dict:
        with cache_lock:
            ev = url_events.get(url)
            owner = ev is None
            if owner:
                ev = url_events[url] = threading.Event()
        if owner:
            cache[url] = reused(url, reuse) or manual(url) or fetch(url)
            ev.set()
        ev.wait()
        return cache[url]

    def work(row: dict) -> None:
        doc, src = row["document_url"].strip(), row["source_page_url"].strip()
        attempts = [("document_url", doc)] if doc.startswith("http") else []
        if src.startswith("http") and src != doc:
            attempts.append(("source_page_url", src))
        errors = []
        for field, url in attempts:
            res = get(url)
            row.update(url_used=url, url_field=field, http_status=res["http_status"],
                       content_type=res["content_type"], bytes=res["bytes"])
            if res["ok"]:
                row["_result"] = res
                row["error"] = "; ".join(errors)
                return
            errors.append(f"{field}: {res['error']}")
        row["error"] = "; ".join(errors)
        row["status"] = ("non_document_response"
                         if all("non-PDF" in e for e in errors) else "download_failed")

    # Group by host so one slow host does not hold the others up.
    by_host = defaultdict(list)
    for row in todo:
        by_host[up.urlparse(row["document_url"] or row["source_page_url"]).netloc.lower()].append(row)
    started = time.monotonic()
    done = Counter()

    def run_host(host_rows):
        for row in host_rows:
            work(row)
            done["n"] += 1
            if done["n"] % 25 == 0:
                print(f"  {done['n']}/{len(todo)} rows, {time.monotonic() - started:.0f}s",
                      flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(run_host, sorted(by_host.values(), key=len, reverse=True)))

    # Placement is serial, in source order, so file names are deterministic.
    # Rows sharing a URL share one download: the first row takes the temp
    # file, later rows copy what the first one placed.
    placed_by_url: dict[str, Path] = {}
    seen: dict = {}
    now = datetime.now(UTC).isoformat(timespec="seconds")
    for row in todo:
        res = row.pop("_result", None)
        if res is None:
            continue
        res = dict(res)
        if row["url_used"] in placed_by_url:
            fd, tmp = tempfile.mkstemp(suffix=".part", dir=UNPLACED_DIR.parent)
            with os.fdopen(fd, "wb") as b, open(placed_by_url[row["url_used"]], "rb") as a:
                b.write(a.read())
            res["tmp"] = tmp
        elif not os.path.exists(res["tmp"]):
            row.update(status="invalid_document",
                       error="same URL as an earlier row whose file was rejected")
            continue
        pages, err = pdf_pages(res["tmp"])
        row.update(sha256=res["sha256"], bytes=res["bytes"], pages=pages,
                   downloaded_at=res.get("downloaded_at") or now,
                   sha256_matches_index=("" if not row["index_sha256"] else
                                         "yes" if row["index_sha256"] == res["sha256"] else "no"))
        if err or pages == 0:
            row.update(status="invalid_document", error=err or "PDF with 0 pages")
            os.unlink(res["tmp"])
            continue
        folder = (SPLIT_DIR / row["account_slug"] / "compliance_filings"
                  if row["placement"] == "placed" else UNPLACED_DIR)
        place(row, res, folder, seen)
        placed_by_url.setdefault(row["url_used"], REPO_ROOT / row["file"])

    write_report(rows)
    write_summary(rows)


def write_report(rows: list[dict]) -> None:
    with open(REPORT_CSV, "w", newline="", encoding=ENCODING) as fh:
        w = csv.DictWriter(fh, fieldnames=REPORT_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow(row)


def write_summary(rows: list[dict]) -> None:
    status = Counter(r["status"] for r in rows)
    placement = Counter(r["placement"] for r in rows)
    placed_ok = [r for r in rows if r["placement"] == "placed" and r["status"] == "downloaded"]
    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": " + ".join(str(p.relative_to(REPO_ROOT))
                             for p in [FILINGS_CSV, *FILINGS_SUPPLEMENTS] if p.exists()),
        "rows": len(rows),
        "rows_with_url": sum(1 for r in rows if r["status"] != "url_missing"),
        "status": dict(status),
        "placement": dict(placement),
        "placed_files": len(placed_ok),
        "accounts_with_placed_files": len({r["account_slug"] for r in placed_ok}),
        "sha256_matches_index": dict(Counter(r["sha256_matches_index"] for r in rows
                                             if r["status"] in ("downloaded", "duplicate_document"))),
        "overrides": {f"{k[0]} | {k[1]}": v[0] + (f" -> {v[1]}" if v[1] else "") + f" ({v[2]})"
                      for k, v in FILINGS_OVERRIDES.items()},
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
