#!/usr/bin/env python3
"""Extract the Executive Dashboard's filing figures from every compliance-filing PDF.

One row per PDF, one set of columns per figure the dashboard shows. The
columns follow the client's Feature 1 spec (HP_ABX_v3_final.docx):

    "3-5 years of financial metrics where available: revenue, revenue growth,
     net income, headcount growth"  +  header: "CEO and employee count"
    "Keep the original currency and value ... the financial period, and
     whether the number covers a full year, a quarter, or the latest twelve
     months."
    "Before showing a financial number, check: correct company/business unit,
     correct metric, correct reporting period, and correct unit/currency."

So each metric (revenue, net_income, employees) carries its value as written,
unit, currency, scale, row label, page, the prior-period comparative from the
same document (growth is then computed on one basis), and the document's
multi-year history where it prints one. The row also records whose statements
they are (filing_entity, entity_match), their scope (consolidated or not) and
the period (period_type, period_end).

How a value is read
    A model (the project's configured LLM) is shown the filing's relevant
    pages and asked to COPY each figure exactly as printed, with its row label,
    unit caption and page. Python then accepts the figure only if:
      * the value, as written, is on the cited page, within reach of its row
        label (the label must be on that page too);
      * the unit caption is on that page and resolves, through the fixed table
        in UNIT_RULES, to a currency and a scale;
    and parses the number itself (commas, dot-thousands, parentheses and the
    Japanese triangle for negatives). A figure that fails any check is left
    blank and <metric>_check says why. The model never supplies a number that
    reaches the CSV unchecked.

    Each PDF's model output is cached on its sha256 and PROMPT_VERSION, so a
    rerun reproduces the same CSV without calling the model.

Outputs
    <split>/_filings_extract.csv                one row per PDF, every account
    <split>/<ACCOUNT>/filings_financials.csv    that account's rows - upload
                                                with dataset_key=filings_financials
    <split>/_filings_dashboard_view.csv         what the dashboard will show per
                                                account (the backend's own
                                                resolver, for review)

PredictLeads' generated PDFs (predictleads_sec_*.pdf) are skipped: their text
feeds the narrative only, never the financial claims (decision of 28 Sep).

Usage
    hp-backend/.venv/bin/python scripts/filings_to_csv.py [--account SLUG ...]
        [--workers N] [--llm-workers N] [--refresh]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPLIT_DIR = ROOT / "220 account split csv"
BACKEND = ROOT / "hp-backend"
BACKEND_SRC = BACKEND / "src"
REPORT_CSV = SPLIT_DIR / "_filings_download_report.csv"
EXTRACT_CSV = SPLIT_DIR / "_filings_extract.csv"
VIEW_CSV = SPLIT_DIR / "_filings_dashboard_view.csv"
CACHE_DIR = SPLIT_DIR / "_filings_extract_cache"
ACCOUNT_CSV_NAME = "filings_financials.csv"
ENCODING = "utf-8-sig"

PROMPT_VERSION = 3
PREDICTLEADS_PREFIX = "predictleads_sec_"
RATE_LIMIT_RETRIES = 4
RATE_LIMIT_BACKOFF = 30  # seconds, times the attempt number

METRICS = ("revenue", "net_income", "employees")

# --------------------------------------------------------------------------
# Choosing the pages to show the model
# --------------------------------------------------------------------------
# Terms per language the 220's filings are written in: English, Japanese,
# Thai, Korean, Indonesian/Malay, Vietnamese, Chinese.
PAGE_TERMS = {
    "revenue": r"revenue|net sales|turnover|total income|operating income|売上高|売上収益|営業収益|"
               r"รายได้|매출|영업수익|pendapatan|penjualan|doanh thu|营业收入|營業收入|营业总收入",
    "net_income": r"net (income|profit)|profit (for|attributable)|当期純利益|当期利益|帰属する|"
                  r"กำไรสุทธิ|กำไรสำหรับ|당기순이익|순이익|laba bersih|laba tahun berjalan|"
                  r"lợi nhuận sau thuế|净利润|淨利|归属于",
    "employees": r"employees|headcount|workforce|full[- ]time|従業員|พนักงาน|직원|임직원|"
                 r"karyawan|pegawai|nhân viên|lao động|员工|員工|职工",
    "ceo": r"chief executive|\bceo\b|managing director|president|代表取締役|社長|"
           r"ประธานเจ้าหน้าที่บริหาร|กรรมการผู้จัดการ|대표이사|direktur utama|presiden direktur|"
           r"tổng giám đốc|总经理|總經理|董事长",
}
SUMMARY_TERMS = (r"highlights|financial summary|key figures|five[- ]year|主要な経営指標|"
                 r"ข้อมูลทางการเงินที่สำคัญ|요약재무|ikhtisar|chỉ tiêu tài chính|主要会计数据")
CONSOLIDATED_TERMS = r"consolidated|連結|งบการเงินรวม|연결|konsolidasian|hợp nhất|合并|合併"
MAX_PAGES = 16          # beyond the first two
MAX_PAGE_CHARS = 7000
MAX_TOTAL_CHARS = 100_000

# --------------------------------------------------------------------------
# Units: caption as written -> (currency, scale). Checked in order; the first
# scale and the first currency found both apply.
# --------------------------------------------------------------------------
SCALE_RULES = [
    (r"(?<=\d)\s?(b|bn)\b", 1e9, "billion"),
    (r"百万|百萬|ล้าน|백만|triệu|juta|\bmillions?\b|\bmn\b|\bmil\b|\$\s?m\b|(?<![a-z])m\b", 1e6, "million"),
    (r"億|억", 1e8, "hundred million"),
    (r"千|พัน|천|nghìn|ngàn|ribu|\bthousands?\b|['’]000|\b000s\b|(?<![a-z])k\b", 1e3, "thousand"),
    (r"万|萬", 1e4, "ten thousand"),
    (r"兆|triliun|\btrillions?\b|nghìn tỷ", 1e12, "trillion"),
    (r"十億|miliar|milyar|\bbillions?\b|\bbn\b|tỷ", 1e9, "billion"),
    (r"\bcrores?\b", 1e7, "crore"),
    (r"\blakhs?\b", 1e5, "lakh"),
]
CURRENCY_RULES = [
    (r"円|\byen\b|\bJPY\b|¥", "JPY"),
    (r"บาท|\bbaht\b|\bTHB\b", "THB"),
    (r"원|\bwon\b|\bKRW\b|₩", "KRW"),
    (r"\bRupiah\b|\bIDR\b|\bRp\b", "IDR"),
    (r"đồng|\bdong\b|\bVND\b|VNĐ", "VND"),
    (r"人民币|人民幣|\bRMB\b|\bCNY\b|元", "CNY"),
    (r"\bRM\b|RM(?=['’\d\s])|\bringgit\b|\bMYR\b", "MYR"),
    (r"\bPHP\b|\bPhP\b|₱|\bpesos?\b", "PHP"),
    (r"\bINR\b|₹|\brupees?\b|\bRs\.?", "INR"),
    (r"\bNZD\b|NZ\$", "NZD"),
    (r"\bAUD\b|A\$|\bAustralian dollars?\b", "AUD"),
    (r"\bSGD\b|S\$|\bSingapore dollars?\b", "SGD"),
    (r"\bHKD\b|HK\$", "HKD"),
    (r"\bTWD\b|NT\$", "TWD"),
    (r"\bUSD\b|US\$|\bU\.?S\.? dollars?\b", "USD"),
    (r"\bEUR\b|€|\beuros?\b", "EUR"),
    (r"\bGBP\b|£", "GBP"),
]
# A bare "$": the dollar of the filing's country, flagged.
COUNTRY_DOLLAR = {"AU": "AUD", "NZ": "NZD", "SG": "SGD", "HK": "HKD", "US": "USD", "TW": "TWD"}
HEADCOUNT_UNIT_RE = re.compile(r"person|people|employee|staff|headcount|member|number|名|人|คน|명|orang|"
                               r"người|fte",
                               re.I)
# A chief executive's title, in the filings' languages; a COO/CFO/chair is not.
CEO_TITLE_RE = re.compile(r"CEO|chief executive|managing director|president|最高経営責任者|社長|"
                          r"대표이사|กรรมการผู้จัดการ|ประธานเจ้าหน้าที่บริหาร|direktur utama|"
                          r"presiden direktur|tổng giám đốc|总经理|總經理|总裁|總裁", re.I)
NOT_CEO_RE = re.compile(r"\bCOO\b|\bCFO\b|chief operating|chief financial|chair", re.I)
# Countries whose filings write 1.234.567 for thousands.
DOT_THOUSANDS = {"ID", "VN"}

# How far a value may sit from its row label on the page, in characters of
# the whitespace-flattened text. Japanese tables put the label on one line and
# the figures two lines later.
LABEL_WINDOW_BEFORE = 80
LABEL_WINDOW_AFTER = 900

SYSTEM_PROMPT = """You read a company's regulatory filing and copy figures out of it for a sales dashboard.

You are given selected pages, each starting with a marker like === PAGE 12 ===. Every "page" you return is the number in that marker, never the page number printed on the document itself.

Copy, never compute or convert. value_as_written is the number only, exactly as printed (digits, separators, parentheses or minus/triangle sign), without currency symbols or words. Every other *_as_written field must be copied character for character from the page you cite, including commas, dots, parentheses and minus/triangle signs. If a figure is not printed on these pages, return null for it. Never estimate, never add numbers, never convert currencies or scales.

Figures wanted, for the WHOLE company (the group's consolidated statements when there are any):
- revenue: the line the company names revenue / net sales / sales / turnover / operating revenue for the period. Use "total income" or "total operating income" ONLY for a bank, insurer or other financial company, or when no revenue or sales line exists.
- net_income: net profit for the period, preferring the amount attributable to owners of the parent.
- employees: total number of employees (a headcount, not a cost).
Prefer a multi-year financial highlights or summary table when the filing has one, otherwise the consolidated income statement.

Also:
- The period the filing reports on: its type (FY, Q1, Q2, Q3, 1H, 9M, LTM) and end date.
- filing_entity: the company whose statements these are, as named in the filing, plus its English name.
- statement_scope for each figure: "consolidated" (group), "standalone_only" (the company has no subsidiaries / no consolidated statements), "separate" (parent-company-only while consolidated statements exist), or "segment".
- ceo: the person whose title is Chief Executive Officer (CEO, Group CEO, 最高経営責任者). Only when nobody holds a CEO title, the top executive: Managing Director, President Director / Direktur Utama, 代表取締役社長, 대표이사, กรรมการผู้จัดการ, Tổng Giám đốc. Never a COO, CFO or chairman. title_as_written is that person's title exactly as printed.

Return JSON only, in exactly this shape:
{
 "filing_entity": "...", "filing_entity_english": "...",
 "period": {"type": "FY|Q1|Q2|Q3|1H|9M|LTM", "period_end": "YYYY-MM-DD", "label_as_written": "..."},
 "currency": "ISO code of the reporting currency",
 "metrics": {
   "revenue": {"value_as_written": "...", "unit_as_written": "the unit caption for this figure, e.g. (百万円) or $m or in millions of Baht", "row_label_as_written": "...", "page": 0, "statement_scope": "...",
               "prior_value_as_written": "... or null", "prior_period_end": "YYYY-MM-DD or null",
               "history": [{"period_end": "YYYY-MM-DD", "value_as_written": "..."}]},
   "net_income": { same fields },
   "employees": { same fields; unit_as_written may be null or e.g. persons }
 },
 "ceo": {"name_as_written": "...", "title_as_written": "...", "page": 0}
}
history: every other period printed in the same row as the figure (e.g. a five-year table), oldest first. Use null for any object you cannot find."""

# --------------------------------------------------------------------------
# Output columns
# --------------------------------------------------------------------------
BASE_COLUMNS = [
    "account", "company", "country", "file", "document_title", "document_type",
    "reporting_period", "publication_date", "document_url", "sha256",
    "filing_entity", "filing_entity_english", "entity_match",
    "period_type", "period_end", "period_label", "period_check", "currency",
]
METRIC_FIELDS = ["", "_text", "_unit", "_currency", "_scale", "_label", "_page",
                 "_scope", "_prior", "_prior_period_end", "_history", "_check", "_flags"]
TAIL_COLUMNS = ["ceo_name", "ceo_title", "ceo_page", "ceo_check",
                "extraction_status", "pages_sent", "model", "prompt_version"]
COLUMNS = (BASE_COLUMNS + [m + f for m in METRICS for f in METRIC_FIELDS] + TAIL_COLUMNS)


def _text(value) -> str:
    text = " ".join(str(value if value is not None else "").split())
    return "" if text.lower() in ("nan", "none", "null") else text


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding=ENCODING, newline="") as fh:
        return list(csv.DictReader(fh))


def norm(text: str) -> str:
    """Page text or a copied string, flattened for matching: NFKC (full-width
    digits and commas become ASCII), unified minus signs, no whitespace."""
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = text.replace("−", "-").replace("–", "-").replace("—", "-").replace("▲", "△")
    return re.sub(r"\s+", "", text)


# --------------------------------------------------------------------------
# Filing metadata
# --------------------------------------------------------------------------

def filing_metadata() -> dict:
    """{absolute pdf path: metadata} from the download report."""
    meta = {}
    for row in _read(REPORT_CSV):
        if row.get("file"):
            meta[str((ROOT / row["file"]).resolve())] = {
                "company": row.get("company"), "country": _text(row.get("country")).upper(),
                "document_title": row.get("document_title"),
                "document_type": row.get("document_type"),
                "reporting_period": row.get("reporting_period"),
                "publication_date": row.get("publication_date"),
                "document_url": row.get("url_used") or row.get("document_url"),
                "sha256": row.get("sha256"),
            }
    return meta


# --------------------------------------------------------------------------
# Stage 1 (process pool): read the PDF, choose pages
# --------------------------------------------------------------------------

def _init_worker() -> None:
    sys.path.insert(0, str(BACKEND_SRC))
    logging.disable(logging.INFO)


def read_and_select(path: str) -> dict:
    from app.services.retrieval import pdf
    try:
        document = pdf.read_pdf(path)
    except Exception as exc:
        return {"path": path, "error": "unreadable: %s" % str(exc)[:200]}
    pages = {p["page"]: p["text"] for p in document["pages"]}
    if sum(len(t) for t in pages.values()) < 300:
        return {"path": path, "error": "no text layer (scanned)"}

    def score(text):
        low = text.lower()
        hits = sum(1 for pattern in PAGE_TERMS.values() if re.search(pattern, low, re.I))
        figures = len(re.findall(r"\d[\d,.]{3,}", text))
        s = hits * 3 + min(figures, 60) / 15
        if re.search(SUMMARY_TERMS, low, re.I):
            s += 4
        if re.search(CONSOLIDATED_TERMS, low, re.I):
            s += 1
        return s

    first = sorted(pages)[:2]
    ranked = sorted((p for p in pages if p not in first),
                    key=lambda p: (-score(pages[p]), p))[:MAX_PAGES]
    chosen, total = [], 0
    for p in first + ranked:
        text = pages[p][:MAX_PAGE_CHARS]
        if total + len(text) > MAX_TOTAL_CHARS:
            break
        chosen.append(p)
        total += len(text)
    chosen.sort()
    return {"path": path, "pages": pages, "chosen": chosen,
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


# --------------------------------------------------------------------------
# Stage 2 (threads): the model, cached
# --------------------------------------------------------------------------

def ask_model(read: dict, refresh: bool) -> tuple[dict | None, str]:
    """(parsed JSON or None, model name). Cached on sha256 + PROMPT_VERSION."""
    sys.path.insert(0, str(BACKEND_SRC))
    from app.config.settings import settings
    model = settings.chat_model
    CACHE_DIR.mkdir(exist_ok=True)
    cache = CACHE_DIR / ("%s_v%d.json" % (read["sha256"], PROMPT_VERSION))
    if cache.exists() and not refresh:
        cached = json.loads(cache.read_text())
        return cached.get("response"), cached.get("model", model)

    from app.core.llm import _parse_json, create_completion, get_openai_client
    body = "\n\n".join("=== PAGE %d ===\n%s" % (p, read["pages"][p][:MAX_PAGE_CHARS])
                       for p in read["chosen"])
    client = get_openai_client()
    parsed = None
    # Vertex answers 429 when too many filings are in flight; back off and try
    # again rather than recording the filing as unread.
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        try:
            response = create_completion(
                client, model=model, temperature=0,
                response_format={"type": "json_object"},
                messages=[{"role": "system", "content": SYSTEM_PROMPT},
                          {"role": "user", "content": body + "\n\nReturn JSON only."}])
            content = response.choices[0].message.content
            parsed = _parse_json(content) if content else None
            break
        except Exception as exc:
            if "429" in str(exc) and attempt < RATE_LIMIT_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF * (attempt + 1))
                continue
            logging.getLogger(__name__).warning("model failed on %s: %s", read["path"], exc)
            return None, model
    if parsed is not None:
        cache.write_text(json.dumps({"model": model, "response": parsed},
                                    ensure_ascii=False, indent=1))
    return parsed, model


# --------------------------------------------------------------------------
# Stage 3: check and parse, in Python
# --------------------------------------------------------------------------

def parse_number(written: str, country: str) -> tuple[float | None, str]:
    """(value, flag) from a figure as printed."""
    text = norm(written)
    token = re.search(r"[(△-]?\d[\d,.]*\)?", text)
    if not token:
        return None, ""
    raw = token.group(0)
    negative = (raw.startswith(("(", "-", "△")) or raw.endswith(")")
                or text.startswith(("(", "-", "△")))
    raw = raw.strip("()△-").rstrip(".,")
    flag = ""
    if "," in raw and "." in raw:
        decimal = "." if raw.rfind(".") > raw.rfind(",") else ","
        thousands = "," if decimal == "." else "."
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3}){2,}", raw):
        raw = raw.replace(".", "")
    elif re.fullmatch(r"\d{1,3}\.\d{3}", raw) and country in DOT_THOUSANDS:
        raw = raw.replace(".", "")
        flag = "dot_read_as_thousands"
    elif re.fullmatch(r"\d{1,3}(,\d{3})+", raw):
        raw = raw.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", raw):
        raw = raw.replace(",", ".")
    if not re.fullmatch(r"\d+(\.\d+)?", raw):
        return None, ""
    value = float(raw)
    return (-value if negative else value), flag


def parse_unit(unit: str, page_text: str, currency_hint: str, country: str,
               headcount: bool) -> tuple[str, float, str, str]:
    """(currency, scale factor, scale name, flag). currency '' = unresolved."""
    text = unicodedata.normalize("NFKC", _text(unit))
    if headcount:
        return "", 1.0, "", ""
    scale, scale_name = 1.0, ""
    for pattern, factor, name in SCALE_RULES:
        if re.search(pattern, text, re.I):
            scale, scale_name = factor, name
            break
    for pattern, code in CURRENCY_RULES:
        if re.search(pattern, text, re.I):
            return code, scale, scale_name, ""
    if "$" in text and country in COUNTRY_DOLLAR:
        return COUNTRY_DOLLAR[country], scale, scale_name, "currency_from_country"
    # A caption with a scale and no currency ("in millions"): the reporting
    # currency the model named, only if the page itself names that currency.
    hint = _text(currency_hint).upper()
    for pattern, code in CURRENCY_RULES:
        if code == hint and re.search(pattern, page_text, re.I):
            return code, scale, scale_name, "currency_from_page"
    return "", scale, scale_name, ""


def label_anchor(page_n: str, label_n: str) -> str:
    """The part of the label to look for on the page: all of it, or - when the
    page breaks the label across lines with figures in between ("親会社の所有者
    に帰属する" ... "当期利益") - its longest leading or trailing part that is
    on the page, provided that part is at least half the label. '' if none."""
    if not label_n:
        return ""
    if label_n in page_n:
        return label_n
    need = max(4, (len(label_n) + 1) // 2)
    for size in range(len(label_n) - 1, need - 1, -1):
        for part in (label_n[:size], label_n[-size:]):
            if part in page_n:
                return part
    return ""


def near_label(page_n: str, label_n: str, value_n: str) -> bool:
    """The value appears within reach of one of the label's occurrences."""
    label_n = label_anchor(page_n, label_n)
    if not label_n or not value_n:
        return False
    start = 0
    while True:
        at = page_n.find(label_n, start)
        if at < 0:
            return False
        lo = max(0, at - LABEL_WINDOW_BEFORE)
        hi = at + len(label_n) + LABEL_WINDOW_AFTER
        if value_n in page_n[lo:hi]:
            return True
        start = at + 1


def check_metric(metric: str, item: dict, pages: dict, currency_hint: str,
                 country: str) -> dict:
    """The metric's columns, filled only for what passed; _check says why not."""
    out = {metric + f: "" for f in METRIC_FIELDS}
    if not isinstance(item, dict) or not _text(item.get("value_as_written")):
        out[metric + "_check"] = "not found"
        return out
    headcount = metric == "employees"
    written = _text(item.get("value_as_written"))
    label = _text(item.get("row_label_as_written"))
    unit = _text(item.get("unit_as_written"))
    try:
        page = int(item.get("page"))
    except (TypeError, ValueError):
        page = None
    out.update({metric + "_text": written, metric + "_label": label,
                metric + "_unit": unit, metric + "_page": page or "",
                metric + "_scope": _text(item.get("statement_scope")).lower()})

    value_n = norm(written)
    label_n = norm(label)

    def failure(page_no):
        text_n = norm(pages.get(page_no, ""))
        if page_no not in pages:
            return "cited page not among those read"
        if value_n not in text_n:
            return "value not on cited page"
        if not label_anchor(text_n, label_n):
            return "row label not on cited page"
        if not near_label(text_n, label_n, value_n):
            return "value not beside its row label"
        return ""

    reason = failure(page)
    moved = False
    if reason:
        # Models often cite the page number printed on the document rather
        # than the reader's page. The same strict check is run on the other
        # pages read; the figure is accepted only where its label and value
        # sit together, and the move is flagged.
        for other in sorted(pages):
            if other != page and not failure(other):
                page, moved = other, True
                break
        else:
            out[metric + "_check"] = reason
            return out
    out[metric + "_page"] = page
    page_text = pages[page]
    page_n = norm(page_text)

    value, number_flag = parse_number(written, country)
    if value is None:
        out[metric + "_check"] = "value not a number"
        return out
    if headcount:
        if unit and not HEADCOUNT_UNIT_RE.search(unit):
            out[metric + "_check"] = "unit is not a headcount"
            return out
        currency, scale, scale_name, unit_flag = "", 1.0, "", ""
    else:
        if not unit or norm(unit) not in page_n:
            out[metric + "_check"] = "unit caption not on cited page"
            return out
        currency, scale, scale_name, unit_flag = parse_unit("%s %s" % (unit, written), page_text,
                                                            currency_hint, country, headcount)
        if not currency:
            out[metric + "_check"] = "currency not stated"
            return out

    flags = [f for f in (number_flag, unit_flag, "page_from_text" if moved else "") if f]
    out.update({metric: value, metric + "_currency": currency,
                metric + "_scale": scale_name or ("units" if not headcount else "")})

    # The comparative and the history: same row, so same label window.
    prior_w = _text(item.get("prior_value_as_written"))
    if prior_w and near_label(page_n, label_n, norm(prior_w)):
        prior, _ = parse_number(prior_w, country)
        if prior is not None:
            out[metric + "_prior"] = prior
            out[metric + "_prior_period_end"] = _text(item.get("prior_period_end"))
    elif prior_w:
        flags.append("prior_not_verified")
    history = []
    for h in item.get("history") or []:
        if not isinstance(h, dict):
            continue
        hw = _text(h.get("value_as_written"))
        end = _text(h.get("period_end"))
        if hw and re.fullmatch(r"\d{4}-\d{2}-\d{2}", end) and near_label(page_n, label_n, norm(hw)):
            hv, _ = parse_number(hw, country)
            if hv is not None:
                history.append("%s=%s" % (end, hv))
    out[metric + "_history"] = ";".join(history)
    out[metric + "_check"] = "verified"
    out[metric + "_flags"] = ";".join(flags)
    return out


LEGAL_WORDS = re.compile(
    r"\b(the|limited|ltd|inc|incorporated|corp|corporation|co|company|plc|pt|tbk|persero|bhd|"
    r"berhad|sdn|public|pcl|group|holdings?|jsc|joint stock|n\.?v|b\.?v|ag|sa|llc|kk|"
    r"branch|office)\b|[^\w\s]")


# Words that say what kind of body it is, not which one: a filing that names
# itself only "The Bank and Its Subsidiaries" has named nobody.
GENERIC_WORDS = {"bank", "banking", "its", "subsidiaries", "and", "of", "for", "in",
                 "consolidated", "entity", "parent", "financial", "statements"}


def entity_match(filing_entity: str, company: str) -> str:
    """'same' when the names agree, 'different' when the filing is another
    entity's (a parent, a subsidiary, a misfiled document), 'unknown' when the
    filing named no distinctive entity.

    Two names agree when most of their distinctive words match, a word
    matching another it begins (Australia/Australian, Post/Postal,
    Bank/Banking), or when one is the other's initials (ST Engineering /
    Singapore Technologies Engineering, ANZ / Australia and New Zealand)."""
    def words(name):
        return [w for w in LEGAL_WORDS.sub(" ", _text(name).lower()).split() if len(w) > 1]

    def same_word(x, y):
        return x == y or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x)))

    a, b = words(filing_entity), words(company)
    if not b or not [w for w in a if w not in GENERIC_WORDS]:
        return "unknown"
    matched = sum(1 for x in a if any(same_word(x, y) for y in b))
    if matched / min(len(a), len(b)) >= 0.5:
        return "same"
    # Initials: a short word on one side spelling the other side's words.
    for short, full in ((a, b), (b, a)):
        initials = "".join(w[0] for w in full)
        for w in short:
            if 2 <= len(w) <= 5 and w in initials:
                rest = [x for x in short if x != w]
                if all(any(same_word(x, y) for y in full) for x in rest):
                    return "same"
    return "different"


def build_row(meta: dict, account: str, file_name: str, read: dict,
              response: dict | None, model: str) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update({"account": account, "company": meta.get("company") or "",
                "country": meta.get("country") or "", "file": file_name,
                "document_title": meta.get("document_title") or "",
                "document_type": meta.get("document_type") or "",
                "reporting_period": meta.get("reporting_period") or "",
                "publication_date": meta.get("publication_date") or "",
                "document_url": meta.get("document_url") or "",
                "sha256": read.get("sha256") or meta.get("sha256") or "",
                "pages_sent": ",".join(str(p) for p in read.get("chosen") or []),
                "model": model, "prompt_version": PROMPT_VERSION})
    if response is None:
        row["extraction_status"] = "model gave no answer"
        return row

    pages = read["pages"]
    country = row["country"]
    entity = _text(response.get("filing_entity"))
    entity_en = _text(response.get("filing_entity_english")) or entity
    row["filing_entity"], row["filing_entity_english"] = entity, entity_en
    row["entity_match"] = entity_match(entity_en, row["company"])

    period = response.get("period") or {}
    ptype = _text(period.get("type")).upper()
    pend = _text(period.get("period_end"))
    row["period_type"] = ptype if ptype in ("FY", "Q1", "Q2", "Q3", "1H", "9M", "LTM") else ""
    row["period_end"] = pend if re.fullmatch(r"\d{4}-\d{2}-\d{2}", pend) else ""
    row["period_label"] = _text(period.get("label_as_written"))
    # The filing list's own period, where it has one, must agree on the type.
    listed = re.search(r"(FY|Q[1-4]|[12]H|H1|9M)$", _text(row["reporting_period"]).upper())
    listed_type = {"H1": "1H", "Q4": "FY"}.get(listed.group(1), listed.group(1)) if listed else ""
    row["period_check"] = ("no period" if not row["period_type"] or not row["period_end"]
                           else "differs from filing list (%s)" % listed_type
                           if listed_type and listed_type != row["period_type"] else "ok")
    row["currency"] = _text(response.get("currency")).upper()[:3]

    metrics = response.get("metrics") or {}
    for metric in METRICS:
        row.update(check_metric(metric, metrics.get(metric), pages, row["currency"], country))

    ceo = response.get("ceo") or {}
    name = _text(ceo.get("name_as_written")) if isinstance(ceo, dict) else ""
    if name:
        all_text = norm(" ".join(pages.values()))
        row["ceo_name"], row["ceo_title"] = name, _text(ceo.get("title_as_written"))
        row["ceo_page"] = ceo.get("page") or ""
        title = row["ceo_title"]
        if norm(name) not in all_text:
            row["ceo_check"] = "name not in filing"
        elif not CEO_TITLE_RE.search(title) or (NOT_CEO_RE.search(title)
                                                 and not re.search(r"CEO|chief executive|最高経営責任者",
                                                                   title, re.I)):
            row["ceo_check"] = "title is not a chief executive's"
        else:
            row["ceo_check"] = "verified"
    else:
        row["ceo_check"] = "not found"

    got = sum(1 for m in METRICS if row[m + "_check"] == "verified")
    row["extraction_status"] = ("ok" if got == len(METRICS) else
                                "partial" if got or row["ceo_check"] == "verified" else "none verified")
    return row


# --------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--account", nargs="*", help="only these account folder names")
    ap.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--llm-workers", type=int, default=8)
    ap.add_argument("--refresh", action="store_true", help="ignore the model cache")
    args = ap.parse_args()

    sys.path.insert(0, str(BACKEND_SRC))
    os.chdir(BACKEND)  # settings read hp-backend/.env
    logging.basicConfig(level=logging.WARNING)

    meta = filing_metadata()
    pdfs = sorted(SPLIT_DIR.glob("*/compliance_filings/*.pdf"))
    if args.account:
        pdfs = [p for p in pdfs if p.parent.parent.name in set(args.account)]
    pdfs = [p for p in pdfs if not p.name.lower().startswith(PREDICTLEADS_PREFIX)]
    print("%d filing PDF(s) (PredictLeads text PDFs skipped)" % len(pdfs))

    reads = {}
    with ProcessPoolExecutor(args.workers, initializer=_init_worker) as pool:
        for result in pool.map(read_and_select, [str(p) for p in pdfs]):
            reads[result["path"]] = result
    print("  read: %d with text, %d without"
          % (sum(1 for r in reads.values() if "error" not in r),
             sum(1 for r in reads.values() if "error" in r)))

    rows = []

    def work(path: Path) -> dict:
        read = reads[str(path)]
        m = meta.get(str(path.resolve()), {})
        account = path.parent.parent.name
        if "error" in read:
            row = {c: "" for c in COLUMNS}
            row.update({"account": account, "company": m.get("company") or "",
                        "country": m.get("country") or "", "file": path.name,
                        "document_title": m.get("document_title") or "",
                        "reporting_period": m.get("reporting_period") or "",
                        "extraction_status": read["error"]})
            return row
        response, model = ask_model(read, args.refresh)
        return build_row(m, account, path.name, read, response, model)

    with ThreadPoolExecutor(args.llm_workers) as pool:
        futures = [pool.submit(work, p) for p in pdfs]
        for done, fut in enumerate(as_completed(futures), 1):
            rows.append(fut.result())
            if done % 25 == 0 or done == len(futures):
                print("  %d/%d extracted" % (done, len(futures)))

    rows.sort(key=lambda r: (r["account"], r["period_end"], r["file"]))

    from app.services.dashboard import filings_financials as ff
    view = []
    by_account = {}
    for row in rows:
        by_account.setdefault(row["account"], []).append(row)
    for account, account_rows in sorted(by_account.items()):
        view.extend(ff.review_rows(account, account_rows))

    # Every run rewrites the account files from scratch, so an upload never
    # carries a figure this run did not verify.
    if not args.account:
        with open(EXTRACT_CSV, "w", encoding=ENCODING, newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        with open(VIEW_CSV, "w", encoding=ENCODING, newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=ff.REVIEW_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(view)
    for account, account_rows in by_account.items():
        with open(SPLIT_DIR / account / ACCOUNT_CSV_NAME, "w", encoding=ENCODING,
                  newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(account_rows)

    status = Counter(r["extraction_status"] for r in rows)
    verified = {m: sum(1 for r in rows if r[m + "_check"] == "verified") for m in METRICS}
    reasons = Counter(r[m + "_check"] for r in rows for m in METRICS
                      if r[m + "_check"] not in ("verified", ""))
    shown = {v["account"] for v in view if v.get("value_text")}
    print("\n%d PDF row(s), %d account(s)" % (len(rows), len(by_account)))
    print("  status: %s" % dict(status))
    print("  verified per metric: %s; CEO: %d" % (verified, sum(
        1 for r in rows if r["ceo_check"] == "verified")))
    print("  not verified, why: %s" % dict(reasons.most_common()))
    print("  accounts with at least one dashboard figure: %d" % len(shown))
    if not args.account:
        print("Wrote %s, %s" % (EXTRACT_CSV.relative_to(ROOT), VIEW_CSV.relative_to(ROOT)))
    print("Wrote %s in %d account folder(s)" % (ACCOUNT_CSV_NAME, len(by_account)))


if __name__ == "__main__":
    main()
