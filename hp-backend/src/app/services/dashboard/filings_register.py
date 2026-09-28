"""The account's filings list, as the client defined it.

opens_1 answer 10: *"Sec filings: pls use from filings.csv + predictleads
data->sec_filings"*. opens_2 item 11 merges the two on domain (then company name
and country), and the 18 Sep answer sets the link rule: *"use document_url where
available and source_page_url as the fallback. Do not use local_path. Where both
source URLs are blank, please exclude that record."* Item 13 sets the window:
*"last 12 months"*.

Both sources arrive in one file, `_filings_index.csv`, uploaded with the PDFs
under `compliance_filings`: the split writes the account's rows of filings 1.csv
and its PredictLeads sec_filings rows into it in filings 1.csv's columns, and
writes each PredictLeads filing's text as a PDF beside the downloaded ones. So
the documents are read by the one PDF path, and this module only lists them.

Nothing here is generated: every field is copied from a row of the list.
"""

import csv
import re
from datetime import UTC, date, datetime, timedelta

WINDOW_DAYS = 365

SOURCE_REGISTER = "filings.csv"
SOURCE_PREDICTLEADS = "PredictLeads sec_filings"

# How the split marks what came from PredictLeads (split_account_data.py).
PREDICTLEADS_CRAWL_ROUTE = "PREDICTLEADS_SEC_FILINGS"
# The PDFs the split writes from PredictLeads' text carry this filename prefix.
PREDICTLEADS_FILE_PREFIX = "predictleads_sec_"


def _text(value) -> str:
    text = " ".join(str(value if value is not None else "").split())
    return "" if text.lower() in ("nan", "none", "null") else text


def _date(value) -> date | None:
    """The date in a filings-list cell. The crawl wrote five formats, one per
    route: ISO (with or without time), YYYY/MM/DD, DD/MM/YYYY, Unix seconds
    and "May 12, 2026 10:00 AM". DD/MM/YYYY is read day first: every such row
    comes from an Australian exchange page, and each ambiguous one checks out
    that way against its reporting period (a 1H result dated 11/02, a 20-F
    dated 05/11). Anything else is undated, not guessed."""
    text = _text(value)
    if not text:
        return None
    try:
        m = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if m:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        if re.fullmatch(r"\d{9,10}(\.\d+)?", text):
            return datetime.fromtimestamp(float(text), UTC).date()
        m = re.match(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", text)
        if m:
            return datetime.strptime(" ".join(m.groups()), "%b %d %Y").replace(
                tzinfo=UTC).date()
    except (ValueError, OverflowError):
        return None
    return None


def _url_key(url: str) -> str:
    return re.sub(r"^https?://(www\.)?", "", url.strip().lower()).rstrip("/")


def is_predictleads(row: dict) -> bool:
    return _text(row.get("crawl_route")) == PREDICTLEADS_CRAWL_ROUTE


def _entry(row: dict) -> dict:
    # The client's rule, in order. local_path is never used as a link: it names
    # a folder on the crawler's machine (or, for a PredictLeads row, the PDF the
    # split wrote).
    url = _text(row.get("document_url")) or _text(row.get("source_page_url"))
    filed = _date(row.get("publication_date")) or _date(row.get("period_end"))
    return {
        "source": SOURCE_PREDICTLEADS if is_predictleads(row) else SOURCE_REGISTER,
        "title": _text(row.get("document_title")),
        "document_type": _text(row.get("document_type")),
        "reporting_period": _text(row.get("reporting_period")),
        "filed_on": filed.isoformat() if filed else None,
        "url": url,
        "url_field": ("document_url" if _text(row.get("document_url"))
                      else "source_page_url" if url else None),
        "exchange": _text(row.get("likely_exchange")),
        "document_on_file": _text(row.get("download_status")).upper() in (
            "DOWNLOADED", "SUCCESS", "GENERATED_FROM_TEXT"),
        "sha256": _text(row.get("sha256")),
    }


def register(index_rows: list, as_of: date | None = None) -> dict:
    """Every filing on record for the account, newest first, inside the window.

    Returns the listed filings plus the count of everything left out and why, so
    the card can say "12 of 18 filings are in the last 12 months" rather than
    silently showing fewer.
    """
    as_of = as_of or datetime.now(UTC).date()
    start = as_of - timedelta(days=WINDOW_DAYS)

    candidates = [_entry(r) for r in index_rows or []]

    listed, seen = [], set()
    excluded = {"no_url": 0, "outside_window": 0, "undated": 0, "duplicate": 0}
    for item in candidates:
        if not item["url"]:
            excluded["no_url"] += 1
            continue
        if not item["filed_on"]:
            # The window cannot be applied to a filing with no date, and the
            # client's rule is a window, so it is left out and counted.
            excluded["undated"] += 1
            continue
        filed = date.fromisoformat(item["filed_on"])
        if filed < start or filed > as_of + timedelta(days=1):
            excluded["outside_window"] += 1
            continue
        key = _url_key(item["url"])
        if key in seen:
            excluded["duplicate"] += 1
            continue
        seen.add(key)
        listed.append(item)

    listed.sort(key=lambda f: (f["filed_on"], f["title"]), reverse=True)
    return {
        "filings": listed,
        "total_on_record": len(candidates),
        "in_window": len(listed),
        "excluded": excluded,
        "window": {"from": start.isoformat(), "to": as_of.isoformat(),
                   "rule": "last 12 months (client, item 13)"},
        "sources": sorted({f["source"] for f in listed}),
    }


def index_rows_from_files(files: list) -> list:
    """Rows of every filings-list CSV among a compliance_filings file set.

    `files` is `dataset_file_paths(...)`'s [(original_name, path)]. Several
    list files may be active (a multi-file dataset adds on upload); their rows
    are concatenated and `register` drops a repeated link as a duplicate.
    """
    rows = []
    for name, path in files:
        if not str(name).lower().endswith(".csv"):
            continue
        with open(path, encoding="utf-8-sig", newline="") as fh:
            rows.extend(csv.DictReader(fh))
    return rows


def is_predictleads_file(name: str) -> bool:
    """A PDF the split wrote from PredictLeads' text, by its filename."""
    return str(name).lower().startswith(PREDICTLEADS_FILE_PREFIX)
