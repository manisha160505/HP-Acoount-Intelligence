"""Executive Dashboard filing figures from `filings_financials.csv`.

scripts/filings_to_csv.py writes one row per filing PDF of an account - annual,
half-year and quarterly - with every figure the dashboard shows as its own set
of columns (revenue, net_income, employees, ceo), each verified against the
page it was read from. This module decides, deterministically, what the
dashboard shows from those rows. The client's rules (HP_ABX_v3_final, Feature
1) it applies:

  * "3-5 years of financial metrics where available: revenue, revenue growth,
    net income, headcount growth", and "CEO and employee count" in the header.
  * "do not compare total-company revenue for financial year 2025 with one
    business unit's quarterly revenue for financial year 2026" - a full year
    is only ever compared with a full year, a quarter with the same quarter.
  * "If the source is for a subsidiary or segment, label it ... do not show it
    as total-company data" - segment and parent-only figures are never used;
    a filing by another entity (a parent's annual report filed under its
    subsidiary's account) is shown only under that entity's name.
  * "If a financial metric fails the reporting-period or whole-company check,
    remove that metric from the current card. Show the last verified period
    with its date if one exists" - the latest filing is used; where it lacks a
    metric, the most recent older filing that has it verified is used, and the
    card says so.

Growth is taken from the same filing's own comparative first (one document,
one basis), and only otherwise from two filings a year apart.
"""

import re
from datetime import date, timedelta

from app.services.dashboard import filings_register
from app.services.dashboard.priorities import _format_value
from app.services.hp import time_windows

SOURCE = "filings_financials"

ANNUAL = ("FY",)
INTERIM = ("Q1", "Q2", "Q3", "1H", "9M")
GROUP_SCOPES = ("consolidated", "standalone_only")

LABELS = {"revenue": "Revenue", "net_income": "Net income", "employees": "Employees"}
# Interim cards for the flow measures only: a quarter-end headcount is not a
# different kind of figure from a year-end one.
INTERIM_METRICS = ("revenue", "net_income")
SERIES_YEARS = 5
SCALE_FACTOR = {"": 1.0, "units": 1.0, "thousand": 1e3, "ten thousand": 1e4, "lakh": 1e5,
                "million": 1e6, "crore": 1e7, "hundred million": 1e8, "billion": 1e9,
                "trillion": 1e12}
# How far apart two period ends may be and still be "a year apart" / "the same
# period": fiscal years end on the last day of a month, and a 52-53 week year
# moves the end by a few days.
YEAR_TOLERANCE_DAYS = 20
# "Show the last verified period with its date" - but not a figure so old it
# misleads: a fallback more than this many years behind the latest filing of
# its kind is not shown.
MAX_FALLBACK_YEARS = 2
# A figure in thousands this large is shown in millions (the original value
# and unit stay on the card as original_value_text / original_unit_text).
DISPLAY_IN_MILLIONS_FROM = 100_000

REVIEW_COLUMNS = ["account", "company", "item", "period", "period_end", "value_text",
                  "change_text", "change_basis", "source_file", "source_page",
                  "fallback_note", "entity_note", "flags"]


def _text(value) -> str:
    text = " ".join(str(value if value is not None else "").split())
    return "" if text.lower() in ("nan", "none", "null") else text


def _number(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _date(value):
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None


_LEGAL = re.compile(r"\b(co|ltd|limited|corp|corporation|company|inc|plc|pt|tbk|bhd|berhad|"
                    r"public|pcl|jsc|the)\b|[^a-z0-9 ]")


def _entity_key(row: dict) -> str:
    """The filing company's name, reduced for comparing: "Hanjin KAL Co., Ltd."
    and "Hanjin Kal Co., Ltd" are one company; Hyundai Motor and Hyundai Mobis
    are two. A group account's filings can come from several group members,
    and a figure is only ever compared with the same company's."""
    name = (_text(row.get("filing_entity_english")) or _text(row.get("filing_entity"))).lower()
    return " ".join(_LEGAL.sub(" ", name).split())


def _same_entity(a: dict, b: dict) -> bool:
    """One company, allowing for how filings spell it: every word of the
    shorter name matches a word of the other, a word matching one it begins
    ("australia"/"australian", "post"/"postal"). An unnamed side matches."""
    x, y = _entity_key(a).split(), _entity_key(b).split()
    if not x or not y:
        return True
    short, full = (x, y) if len(x) <= len(y) else (y, x)

    def same(u, v):
        return u == v or (min(len(u), len(v)) >= 4 and (u.startswith(v) or v.startswith(u)))
    return all(any(same(u, v) for v in full) for u in short)


def _entity_name(row: dict) -> str:
    return _text(row.get("filing_entity_english")) or _text(row.get("filing_entity"))


def _usable(row: dict, metric: str) -> bool:
    return (_text(row.get(metric + "_check")) == "verified"
            and _number(row.get(metric)) is not None
            and _text(row.get(metric + "_scope")) in GROUP_SCOPES
            and _text(row.get("entity_match")) in ("same", "different", "unknown")
            and _date(row.get("period_end")) is not None)


def _abs(row: dict, metric: str, value=None) -> float:
    v = _number(row.get(metric)) if value is None else value
    return v * SCALE_FACTOR.get(_text(row.get(metric + "_scale")), 1.0)


def _display(value, row: dict, metric: str) -> str:
    """A figure as the card shows it: thousands of a large amount in millions."""
    if (_text(row.get(metric + "_scale")) == "thousand" and value is not None
            and abs(value) >= DISPLAY_IN_MILLIONS_FROM):
        return _format_value(round(value / 1000.0, 1),
                             "%s million" % _text(row.get(metric + "_currency")))
    return _format_value(value, _unit(row, metric))


def _unit(row: dict, metric: str) -> str:
    if metric == "employees":
        return "employees"
    scale = _text(row.get(metric + "_scale"))
    currency = _text(row.get(metric + "_currency"))
    return currency if scale in ("", "units") else "%s %s" % (currency, scale)


def _period(row: dict) -> str:
    end = _date(row.get("period_end"))
    ptype = _text(row.get("period_type"))
    return ("FY%d" % end.year) if ptype in ANNUAL else "%d-%s" % (end.year, ptype)


def _year_apart(later: date, earlier: date) -> bool:
    try:
        target = later.replace(year=later.year - 1)
    except ValueError:  # 29 Feb
        target = later.replace(year=later.year - 1, day=28)
    return abs((target - earlier).days) <= YEAR_TOLERANCE_DAYS


def _newest_first(rows: list) -> list:
    return sorted(rows, key=lambda r: (_date(r.get("period_end")),
                                       _text(r.get("publication_date"))), reverse=True)


def _change(row: dict, metric: str, peers: list) -> dict:
    """Period-on-period change: the filing's own comparative, else the filing a
    year earlier. {} when neither exists."""
    end = _date(row["period_end"])
    prior = _number(row.get(metric + "_prior"))
    prior_end = _date(row.get(metric + "_prior_period_end"))
    if prior not in (None, 0) and prior_end and _year_apart(end, prior_end):
        base = {"abs": _abs(row, metric, prior), "end": prior_end,
                "value_text": _display(prior, row, metric),
                "basis": "both from %s" % _text(row.get("file"))}
    else:
        base = None
        for other in peers:
            other_end = _date(other.get("period_end"))
            if (other is not row and _year_apart(end, other_end)
                    and _same_entity(other, row)
                    and _text(other.get(metric + "_currency")) == _text(row.get(metric + "_currency"))
                    and _abs(other, metric)):
                base = {"abs": _abs(other, metric), "end": other_end,
                        "value_text": _display(_number(other[metric]), other, metric),
                        "basis": "%s vs %s" % (_text(row.get("file")), _text(other.get("file")))}
                break
        if base is None:
            return {}
    pct = (_abs(row, metric) - base["abs"]) / abs(base["abs"]) * 100.0
    previous_period = ("FY%d" % base["end"].year if _text(row.get("period_type")) in ANNUAL
                       else "%d-%s" % (base["end"].year, _text(row.get("period_type"))))
    return {"previous_period": previous_period,
            "previous_value_text": base["value_text"],
            "change_pct": round(pct, 1),
            "change_text": "%+.1f%%" % pct,
            "direction": "up" if pct > 0 else ("down" if pct < 0 else "flat"),
            "change_basis": "%s vs %s, %s" % (_period(row), previous_period, base["basis"])}


def _series(row: dict, metric: str, peers: list) -> list:
    """Up to SERIES_YEARS full years, newest filing winning a year it restated.
    Only figures in the headline's currency, from the same entity match."""
    points = {}
    currency = _text(row.get(metric + "_currency"))
    for other in _newest_first(peers):
        if (_text(other.get(metric + "_currency")) != currency
                or not _same_entity(other, row)):
            continue
        entries = [(_date(other["period_end"]), _number(other[metric]))]
        prior_end = _date(other.get(metric + "_prior_period_end"))
        if prior_end and _number(other.get(metric + "_prior")) is not None:
            entries.append((prior_end, _number(other[metric + "_prior"])))
        for item in _text(other.get(metric + "_history")).split(";"):
            end, _, value = item.partition("=")
            if _date(end) and _number(value) is not None:
                entries.append((_date(end), _number(value)))
        for end, value in entries:
            key = (end.year, end.month)
            if key not in points:
                points[key] = {"period": "FY%d" % end.year, "end": end,
                               "value_text": _display(value, other, metric)}
    ordered = sorted(points.values(), key=lambda p: p["end"])[-SERIES_YEARS:]
    return [{"period": p["period"], "value_text": p["value_text"]} for p in ordered]


def _card(row: dict, metric: str, peers: list, company: str, newest_of_type,
          several_entities: bool = False) -> dict:
    label = LABELS[metric]
    ptype = _text(row.get("period_type"))
    if ptype in INTERIM:
        label = "%s (%s)" % (label, ptype)
    entity_note = ""
    entity = _entity_name(row)
    if _text(row.get("entity_match")) == "different":
        label = "%s - %s" % (label, entity)
        entity_note = ("Reported by %s, not %s: the filing on record for this account "
                       "is that entity's." % (entity, company))
    elif several_entities and entity:
        # A group account whose filings come from several group companies:
        # say whose figure this is.
        label = "%s - %s" % (label, entity)
        entity_note = ("%s's figure; this account's filings come from several %s "
                       "companies." % (entity, company))
    fallback_note = ""
    if newest_of_type is not None and _date(newest_of_type["period_end"]) > _date(row["period_end"]):
        fallback_note = ("The latest filing (%s, %s) does not state it; shown from the last "
                         "filing that does." % (_period(newest_of_type),
                                                _text(newest_of_type.get("file"))))
    value = _number(row[metric])
    card = {
        "metric": label,
        "metric_key": metric,
        "value": value,
        "value_text": _display(value, row, metric),
        "period": _period(row),
        "period_type": ptype,
        "period_end": _text(row.get("period_end")),
        "unit": _unit(row, metric),
        "original_value_text": _text(row.get(metric + "_text")),
        "original_unit_text": _text(row.get(metric + "_unit")),
        "source": "%s p.%s" % (_text(row.get("file")), _text(row.get(metric + "_page"))),
        "page": _text(row.get(metric + "_page")),
        "filing_label": _text(row.get("document_title")) or _text(row.get("file")),
        "document_url": _text(row.get("document_url")),
        "quote": "%s %s" % (_text(row.get(metric + "_label")), _text(row.get(metric + "_text"))),
        "scope": _text(row.get(metric + "_scope")),
        "basis": "reported",
        "fallback_note": fallback_note,
        "entity_note": entity_note,
        "entity": entity,
        "flags": ";".join(f for f in (_text(row.get(metric + "_flags")),
                                      "entity_unconfirmed" if _text(row.get("entity_match")) == "unknown" else "")
                          if f),
    }
    card.update(_change(row, metric, peers))
    if ptype in ANNUAL:
        series = _series(row, metric, peers)
        if len(series) > 1:
            card["series"] = series
    return card


def _choose(rows: list, metric: str, types: tuple):
    """The newest usable row of the given period types, and the newest row of
    those types at all (to say when the first had to fall back)."""
    of_type = [r for r in rows if _text(r.get("period_type")) in types
               and _date(r.get("period_end"))]
    usable = [r for r in of_type if _usable(r, metric)]
    if of_type and usable:
        newest = max(_date(r["period_end"]) for r in of_type)
        usable = [r for r in usable
                  if (newest - _date(r["period_end"])).days <= MAX_FALLBACK_YEARS * 366]
    if not usable:
        return None, None, []
    # A filing by the account's own entity beats another entity's; one that
    # named no distinctive entity sits between the two.
    same = ([r for r in usable if _text(r.get("entity_match")) == "same"]
            or [r for r in usable if _text(r.get("entity_match")) == "unknown"])
    pool = same or usable
    return _newest_first(pool)[0], _newest_first(of_type)[0], pool


def _published(value):
    """A publication date in any form the filings crawl wrote it (the filings
    list's reader: ISO, YYYY/MM/DD, day-first DD/MM/YYYY, ...), else ISO."""
    return filings_register._date(value) or _date(value)


def _filed_on(row: dict, as_of: date | None = None):
    """When the filing was published, else the end of the period it covers.

    A publication date after today is not one. Where the filings crawl found
    no date it wrote the year's end - 2026-12-31 on 37 rows in 25 accounts
    (9 Oct), Accenture's Q3 FY26 release of 18 Jun 2026 among them - and the
    window then dropped filings already out as not yet published."""
    published = _published(row.get("publication_date"))
    if published is not None and published <= (as_of or time_windows.today()):
        return published
    return _date(row.get("period_end"))


def recent_filings(rows: list, as_of: date | None = None) -> list:
    """Filings published in the last 24 months (client, 6 Oct: "Executive
    Dashboard - SEC/financial filings: last 24 months"). Undated rows are left
    out: the window cannot be shown to hold for them."""
    end = as_of or time_windows.today()
    start = end - timedelta(days=time_windows.FILINGS_WINDOW_DAYS)
    return [r for r in rows or [] if (d := _filed_on(r, end)) is not None and start <= d <= end]


def reported_metrics(rows: list, company: str = "", as_of: date | None = None) -> list:
    """The filing cards, in dashboard order. [] when nothing verified."""
    rows = recent_filings(rows, as_of)
    company = company or next((_text(r.get("company")) for r in rows if _text(r.get("company"))), "")
    named = [r for r in rows if _text(r.get("entity_match")) in ("same", "unknown")
             and _entity_key(r) and any(_usable(r, m) for m in LABELS)]
    several = any(not _same_entity(a, b) for a in named for b in named)
    cards = []
    for metric in ("revenue", "net_income", "employees"):
        annual, newest_annual, annual_pool = _choose(rows, metric, ANNUAL)
        if annual is not None:
            cards.append(_card(annual, metric, annual_pool, company, newest_annual, several))
        if metric not in INTERIM_METRICS and annual is not None:
            continue
        interim, _newest_interim, interim_pool = _choose(rows, metric, INTERIM)
        # A quarter is shown when it is newer than the last full year, or when
        # there is no full year at all. Compared only with the same quarter.
        if interim is not None and (annual is None or
                                    _date(interim["period_end"]) > _date(annual["period_end"])):
            same_type = [r for r in interim_pool
                         if _text(r.get("period_type")) == _text(interim.get("period_type"))]
            cards.append(_card(interim, metric, same_type, company, None, several))
    return cards


def ceo(rows: list, as_of: date | None = None) -> dict | None:
    """The CEO named in the newest filing that names one, verified in its text,
    among filings published in the last 24 months."""
    named = [r for r in recent_filings(rows, as_of) if _text(r.get("ceo_check")) == "verified"
             and _text(r.get("entity_match")) == "same"]
    if not named:
        return None
    row = _newest_first([r for r in named if _date(r.get("period_end"))] or named)[0]
    return {"name": _text(row.get("ceo_name")), "title": _text(row.get("ceo_title")),
            "source": "%s p.%s" % (_text(row.get("file")), _text(row.get("ceo_page"))),
            "as_of": _text(row.get("period_end")),
            "filing_label": _text(row.get("document_title"))}


def review_rows(account: str, rows: list) -> list:
    """What the dashboard will show for one account, flat, for a reviewer."""
    company = next((_text(r.get("company")) for r in rows if _text(r.get("company"))), "")
    out = []
    for card in reported_metrics(rows, company):
        out.append({"account": account, "company": company, "item": card["metric"],
                    "period": card["period"], "period_end": card["period_end"],
                    "value_text": card["value_text"],
                    "change_text": card.get("change_text", ""),
                    "change_basis": card.get("change_basis", ""),
                    "source_file": card["source"].rsplit(" p.", 1)[0],
                    "source_page": card["page"], "fallback_note": card["fallback_note"],
                    "entity_note": card["entity_note"], "flags": card["flags"]})
    person = ceo(rows)
    if person:
        out.append({"account": account, "company": company, "item": "CEO",
                    "period_end": person["as_of"],
                    "value_text": "%s (%s)" % (person["name"], person["title"]),
                    "source_file": person["source"].rsplit(" p.", 1)[0],
                    "source_page": person["source"].rsplit(" p.", 1)[-1]})
    if not out:
        out.append({"account": account, "company": company, "item": "(nothing verified)"})
    return out
