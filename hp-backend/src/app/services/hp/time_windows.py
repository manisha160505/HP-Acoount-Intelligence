"""How far back each kind of data is used. One place, so the features agree.

Client, 6 Oct ("Time period for data/signals"):

    Live Signals: last 12 months. Hiring Signals: last 12 months.
    Executive Dashboard - SEC/financial filings: last 24 months.
    Except for SEC/financial filings, keep the other applicable signals/data
    to the last 12 months wherever applicable.

Windows are measured back from the day the section is generated (Live
Signals' rule). Hiring is the one exception: its 12 months end on the date
the job data was pulled (hp/hiring_jobs.py), so a section rebuilt later does
not lose jobs that were current when the data arrived.

A row with no readable date, or a date after the window's end, is outside
the window: it cannot be shown to fall inside it. This is the Live Signals
gate's rule, now applied to every reader of the same data.
"""

from datetime import UTC, date, datetime, timedelta

# Bump when a window changes: every node that reads windowed data references
# it (regen/graph.py), so a bump marks exactly those sections stale.
TIME_WINDOWS_VERSION = 1

SIGNAL_WINDOW_DAYS = 365      # news, events, detections and other signals: 12 months
FILINGS_WINDOW_DAYS = 730     # SEC / financial filings: 24 months


def parse_date(value) -> date | None:
    """The date in a source value, or None. Accepts ISO dates and timestamps
    and the day-first / month-first forms the vendor exports use."""
    if isinstance(value, datetime):
        return (value if value.tzinfo is None else value.astimezone(UTC)).date()
    if isinstance(value, date):
        return value
    s = str(value or "").strip().replace("Z", "+00:00")
    if not s:
        return None
    for fmt in (None, "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.fromisoformat(s) if fmt is None else datetime.strptime(s[:10], fmt)  # noqa: DTZ007 - a date from source data that carries no timezone
            return (dt.astimezone(UTC) if dt.tzinfo else dt).date()
        except (ValueError, TypeError):
            continue
    return None


def today() -> date:
    return datetime.now(UTC).date()


def in_window(value, days: int, as_of: date | None = None) -> bool:
    """True when `value` is a date within the `days` before `as_of` (today)."""
    d = parse_date(value)
    end = as_of or today()
    return d is not None and end - timedelta(days=days) <= d <= end


def news_date(row: dict) -> date | None:
    """A news row's date, read the way the Live Signals gate reads it: the
    event date, else the effective date, else when it was found."""
    for key in ("event_date", "effective_date", "found_at"):
        d = parse_date(row.get(key))
        if d:
            return d
    return None


def recent_news(rows: list, as_of: date | None = None) -> list:
    """The news rows inside the 12-month signal window."""
    end = as_of or today()
    start = end - timedelta(days=SIGNAL_WINDOW_DAYS)
    out = []
    for r in rows or []:
        d = news_date(r) if isinstance(r, dict) else None
        if d is not None and start <= d <= end:
            out.append(r)
    return out


def recent_detections(rows: list, as_of: date | None = None) -> list:
    """Technology detections seen within the 12-month signal window: the last
    time a detection was seen, else when it was first seen."""
    end = as_of or today()
    start = end - timedelta(days=SIGNAL_WINDOW_DAYS)
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        d = parse_date(r.get("last_seen_at")) or parse_date(r.get("first_seen_at"))
        if d is not None and start <= d <= end:
            out.append(r)
    return out
