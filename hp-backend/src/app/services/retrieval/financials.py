"""Reading reported figures out of filing tables, in Python, with the receipts.

ABX Feature 1 sets the bar this module has to clear:

    "Before showing a financial number, check: correct company/business unit,
     correct metric, correct reporting period, and correct unit/currency. If the
     source is unclear, do not show the number."

    "Put financial numbers into a consistent format before comparing them. Keep
     the original currency and value, any converted value, the financial period,
     and what the number covers."

So a figure is never lifted on its own. A claim is registered only when four
things are recovered together from the page itself - **metric, period, value and
unit** - and it carries the row it came from as a verbatim quote. Anything that
cannot be bound on all four is skipped, and the skip is counted. Absent beats
unlabelled: this corpus contains `323,392` on a page where a careless reader
would find no currency at all, and publishing that as a revenue figure would be
worse than publishing nothing.

The binding is possible because `pdf.py` rebuilds tables from word coordinates,
so a row arrives whole:

    Uraian              2025    2024    2023    2022    2021  Description
    Pendapatan Bersih 323,392 328,480 316,565 301,379 233,485 Net Revenue

The header names the periods, the row's position names the metric, and the page
states the unit - *"The figures in all tables and graphs are expressed in
billions of Rupiah"*. Take any one away and the row is not registered.

No model is involved at any point. LightRAG's answer may point at a page; the
value shown to a seller is read from here.
"""

import logging
import os
import re

logger = logging.getLogger(__name__)

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
MONTH_RE = re.compile(r"^(%s)\b" % "|".join(MONTHS), re.I)

YEAR_RE = re.compile(r"^(19[89]\d|20[0-4]\d)$")

# A figure as filings write one: 323,392  1,627  (1,234)  56%  12.4
FIGURE_TOKEN_RE = re.compile(r"^\(?-?\d{1,3}(?:,\d{3})*(?:\.\d+)?\)?%?$|^\(?-?\d+(?:\.\d+)?\)?%?$")

# Scale words, in both languages this corpus uses.
SCALES = [
    (r"\btrillions?\b|\btriliun\w*", "trillion"),
    (r"\bbillions?\b|\bmiliar\w*|\bmilyar\w*", "billion"),
    (r"\bmillions?\b|\bjuta\w*", "million"),
    (r"\bthousands?\b|\bribu\w*", "thousand"),
]

# How far apart a scale word and a currency may sit and still describe the same
# figures. The statement that fixes the unit for the highlights table is
# "expressed in billions of Rupiah" - two words apart, but split across a line
# break by the page's column width, so the search runs over the whole page with
# the line breaks flattened rather than line by line.
UNIT_PROXIMITY_CHARS = 60

# Currencies. Named explicitly so an unrecognised one is skipped rather than
# guessed - a figure attributed to the wrong currency is worse than no figure.
CURRENCIES = [
    (r"\bRupiah\b|\bIDR\b|\bRp\b", "IDR"),
    (r"\bUS\$|\bUSD\b|\bU\.S\. dollars?\b|\bUS dollars?\b", "USD"),
    (r"\bSGD\b|\bSingapore dollars?\b", "SGD"),
    (r"\bEUR\b|\beuros?\b", "EUR"),
    (r"\bJPY\b|\byen\b", "JPY"),
]

# Units a document's own title can establish, for tables of counts rather than
# money. Generic industry terms, never account names: a wholesales report counts
# vehicles, and saying so is reading the title, not inventing a unit.
TITLE_UNITS = [
    (r"wholesale", "vehicles (wholesales)"),
    (r"retail sales", "vehicles (retail sales)"),
]


class Claim(dict):
    """One reported figure with everything needed to check it."""


def _tokens(line: str) -> list:
    return [t for t in str(line or "").split() if t]


def _is_figure(token: str) -> bool:
    return bool(FIGURE_TOKEN_RE.match(token))


def _numeric_run(tokens: list) -> tuple:
    """(start, end) of the longest contiguous run of figures, or None.

    Contiguous because a table row is label, then figures, then label - and a
    stray number inside a metric name ("Tier 1 capital") must not be mistaken
    for the first column.
    """
    best = None
    start = None
    for i, token in enumerate([*tokens, ""]):
        if token and _is_figure(token):
            if start is None:
                start = i
        elif start is not None:
            if best is None or i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    return best


def parse_value(token: str) -> tuple:
    """(number, is_percent) for a figure token, or (None, False).

    Parentheses mean negative in every filing convention this corpus uses.
    """
    raw = token.strip()
    percent = raw.endswith("%")
    if percent:
        raw = raw[:-1]
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()").replace(",", "")
    if not raw or not re.match(r"^-?\d+(\.\d+)?$", raw):
        return None, percent
    value = float(raw)
    return (-value if negative else value), percent


def detect_unit(page_text: str) -> tuple:
    """(unit, quote) stated on the page, or (None, None).

    Read from a sentence on the page, not assumed. Both a full sentence -
    *"expressed in billions of Rupiah"* - and a column caption - *"(dalam miliar
    Rupiah)"* - resolve; a page that states neither yields no monetary claims at
    all, which is the intended outcome rather than a gap to paper over.
    """
    flat = " ".join(str(page_text or "").split())
    if not flat:
        return None, None

    scales = [(m.start(), name) for pattern, name in SCALES
              for m in re.finditer(pattern, flat, re.I)]
    currencies = [(m.start(), name) for pattern, name in CURRENCIES
                  for m in re.finditer(pattern, flat, re.I)]
    if not scales or not currencies:
        return None, None

    best = None
    for s_at, scale in scales:
        for c_at, currency in currencies:
            distance = abs(s_at - c_at)
            if distance <= UNIT_PROXIMITY_CHARS and (best is None or distance < best[0]):
                best = (distance, s_at, c_at, scale, currency)
    if best is None:
        return None, None

    _, s_at, c_at, scale, currency = best
    start = max(0, min(s_at, c_at) - 70)
    end = min(len(flat), max(s_at, c_at) + 70)
    return "%s %s" % (currency, scale), flat[start:end]


def detect_title_unit(filename: str) -> tuple:
    """(unit, quote) a document title establishes for tables of counts."""
    name = os.path.basename(str(filename or ""))
    for pattern, unit in TITLE_UNITS:
        if re.search(pattern, name, re.I):
            return unit, "document title: %s" % name
    return None, None


def _header_periods(tokens: list) -> tuple:
    """(periods, has_trailing_label) for a header row, or (None, False).

    Two header shapes appear in this corpus.

    A comparative header names its years outright - `Uraian 2025 2024 2023 2022
    2021 Description` - and the trailing cell tells us the table repeats its
    labels in a second language on the right.

    A monthly header names one year and then its months - `Product Item 2026 Jan
    Feb ... Dec Total`. The row that follows may be short, because a report
    issued in July has only seven months of data; the columns are still known,
    and `bind_row` takes the first N of them rather than guessing which months
    are missing.
    """
    years = [t for t in tokens if YEAR_RE.match(t)]
    months = [t for t in tokens if MONTH_RE.match(t)]

    if len(months) >= 3 and len(years) == 1:
        year = years[0]
        periods = ["%s-%s" % (year, m.title()[:3]) for m in months]
        if any(t.lower() == "total" for t in tokens):
            periods.append("FY%s total" % year)
        return periods, False

    if len(years) >= 2:
        run = _numeric_run(tokens)
        trailing = bool(run and run[1] < len(tokens))
        return ["FY%s" % y for y in years], trailing

    return None, False


def bind_row(tokens: list, periods: list, has_trailing_label: bool) -> tuple:
    """(label, [(period, token)]) for one data row, or (None, []).

    The count decides everything. A row carrying exactly as many figures as the
    header has columns binds one to one. A shorter row binds only when the
    header ends in a total column - the year in progress - in which case the
    figures are the first months and the last figure is the total.

    Any other count is a row this parser does not understand: a merged cell, a
    footnote, a sub-header. It returns nothing and the caller counts it. Nothing
    is bound by proximity or best fit, because a figure under the wrong year is
    indistinguishable from a correct one once it reaches a seller.
    """
    run = _numeric_run(tokens)
    if not run or not periods:
        return None, []

    start, end = run
    figures = tokens[start:end]
    leading = " ".join(tokens[:start]).strip(" :-")
    trailing = " ".join(tokens[end:]).strip(" :-")

    label = trailing if (has_trailing_label and trailing) else leading
    label = label.strip(" :-•")
    if not label or not re.search(r"[^\W\d_]{2}", label):
        return None, []

    if len(figures) == len(periods):
        return label, list(zip(periods, figures))

    is_partial_year = periods and periods[-1].lower().endswith("total")
    if is_partial_year and 1 < len(figures) < len(periods):
        months = periods[:len(figures) - 1]
        return label, list(zip([*months, periods[-1]], figures))

    return None, []


def _heading(tokens: list):
    """The heading a colon-terminated line introduces, or None.

    These pages print a heading in both languages on one line - "Laba yang
    Diatribusikan kepada: Profit Attributable to:" - so the segment after the
    last colon that still has words is the English one, which is what the rest
    of the pipeline reads.
    """
    line = " ".join(tokens).strip()
    if not line.endswith(":") or len(tokens) > 14:
        return None
    parts = [p.strip() for p in line.split(":") if p.strip()]
    return parts[-1] if parts else None


def page_claims(page: dict, file_name: str) -> tuple:
    """(claims, skipped) for one extracted page.

    `skipped` counts rows that held figures but could not be bound on all four
    of metric, period, value and unit - kept as a number so a build can report
    how much of a page it declined to read rather than silently dropping it.
    """
    text = page.get("text") or ""
    unit, unit_quote = detect_unit(text)
    title_unit, title_quote = detect_title_unit(file_name)

    claims, skipped = [], 0
    periods, has_trailing = None, False
    table_index, table_header = 0, None
    section = None

    for line in text.splitlines():
        tokens = _tokens(line)
        if not tokens:
            continue

        header, trailing = _header_periods(tokens)
        if header:
            periods, has_trailing = header, trailing
            table_index += 1
            table_header = " ".join(tokens)[:200]
            section = None
            continue

        if not any(_is_figure(t) for t in tokens):
            # A heading inside a table is load-bearing. This report states
            # "Owners of the Parent" twice in one table - once under "Profit
            # Attributable to:" and again under "Comprehensive Income
            # Attributable to:" - with different figures. Without the heading
            # the two rows cannot be told apart by label, and whichever came
            # last would be published under both.
            #
            # Only a line ending in a colon counts. Not every wordy line is a
            # heading: a long metric name wraps onto its own line too, and
            # treating that as a heading named Total Liabilities "Investments
            # in Joint - Total Liabilities", which is worse than the ambiguity
            # it was meant to fix. The colon is the document's own marker that a
            # list follows. Anything else ends the current heading rather than
            # becoming one, so a heading cannot leak past the rows it governs.
            section = _heading(tokens) if periods else None
            continue
        if not periods:
            # A sentence that happens to contain a number, not a table row.
            continue

        label, bound = bind_row(tokens, periods, has_trailing)
        if not bound:
            skipped += 1
            continue

        quote = " ".join(tokens)[:400]
        for period, token in bound:
            value, percent = parse_value(token)
            if value is None:
                skipped += 1
                continue

            if percent:
                row_unit, row_quote = "%", "value is written as a percentage"
            elif unit:
                row_unit, row_quote = unit, unit_quote
            elif title_unit:
                row_unit, row_quote = title_unit, title_quote
            else:
                skipped += 1
                continue

            claims.append(Claim({
                "metric": label,
                "section": section,
                "period": period,
                "value": value,
                "value_text": token,
                "unit": row_unit,
                "unit_basis": row_quote,
                "page": page.get("page"),
                "file": file_name,
                "quote": quote,
                # Which table on the page this row belongs to. An annual report
                # reports "Net Revenue" in the consolidated highlights and again
                # in each segment breakdown, and reading a trend across those
                # would compare the whole company with one division - exactly
                # the "correct company/business unit" check ABX demands. A
                # series is therefore only ever assembled within one table.
                "table_id": "%s#p%s#t%d" % (file_name, page.get("page"),
                                            table_index),
                "table_header": table_header,
            }))

    return claims, skipped


def document_claims(document: dict) -> tuple:
    """(claims, stats) for one extracted PDF."""
    claims, skipped = [], 0
    for page in document.get("pages") or []:
        page_rows, page_skipped = page_claims(page, document.get("file") or "")
        claims.extend(page_rows)
        skipped += page_skipped
    stats = {"file": document.get("file"), "claims": len(claims),
             "unbound_rows": skipped,
             "pages_with_claims": len({c["page"] for c in claims})}
    logger.info("financials: %s - %d claim(s) across %d page(s), %d row(s) "
                "not bound", stats["file"], stats["claims"],
                stats["pages_with_claims"], skipped)
    return claims, stats


def series(claims: list, metric: str, table_id: str, section=None) -> list:
    """Every period of one metric within one table, oldest first.

    `table_id` is required rather than optional. Dropping it would silently
    compare a consolidated figure with a segment one that happens to share a
    name, and the result would look like a perfectly ordinary trend.

    Periods sort in the right order as written - `FY2021`..`FY2025`, or
    `2026-Jan`..`2026-Jul` by month index.
    """
    wanted = str(metric or "").strip().lower()
    rows = [c for c in claims
            if c["metric"].strip().lower() == wanted and c["table_id"] == table_id
            and (section is None or (c.get("section") or "") == section)]
    return sorted(rows, key=lambda c: period_key(c["period"]))


def period_key(period: str) -> tuple:
    """Sortable form of a period label, oldest first."""
    text = str(period or "")
    match = re.match(r"^(\d{4})-([A-Za-z]{3})$", text)
    if match:
        month = match.group(2).title()
        return (int(match.group(1)),
                MONTHS.index(month) + 1 if month in MONTHS else 0)
    match = re.match(r"^FY(\d{4})", text)
    if match:
        # A full-year total sorts after that year's months.
        return (int(match.group(1)), 13 if "total" in text.lower() else 0)
    return (0, 0)


def summary_table(claims: list) -> str | None:
    """The table_id of the document's multi-year summary, or None.

    Chosen as the table covering the most distinct periods, which is what a
    financial-highlights table is by construction - a segment breakdown carries
    one or two periods, the highlights table carries five. Picking it by shape
    rather than by matching a heading keeps this account-agnostic.
    """
    by_table = {}
    for claim in claims:
        by_table.setdefault(claim["table_id"], set()).add(claim["period"])
    if not by_table:
        return None
    return max(by_table, key=lambda t: (len(by_table[t]), t))


def metrics_in_table(claims: list, table_id: str) -> list:
    """(metric, section) pairs in one table, in the order they appear."""
    seen, out = set(), []
    for claim in claims:
        if claim["table_id"] != table_id:
            continue
        # Keyed on section AND metric, because one table can state the same
        # label under two headings with different figures.
        key = (claim.get("section") or "", claim["metric"].strip().lower())
        if key not in seen:
            seen.add(key)
            out.append((claim["metric"].strip(), claim.get("section")))
    return out
