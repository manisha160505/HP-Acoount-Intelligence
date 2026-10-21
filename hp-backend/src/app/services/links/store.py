"""Link verdicts, one row per URL, in `link_checks`.

    {_id: url, ok: bool, status: int | None, reason: str, final_url: str | None,
     detail: str, checked_at: datetime}

Written only by `scripts/check_links.py`; read by the widget read path, which
asks one question per response: which of these URLs are known broken. A URL
with no row has never been checked and counts as working - hiding every link
until the first check ran would empty the dashboard, and the script fills the
table after each data refresh.

Nothing here touches a widget, so a changed verdict never marks a section stale.
"""

from datetime import UTC, datetime

COLLECTION = "link_checks"


def ensure_indexes(db) -> None:
    db[COLLECTION].create_index([("checked_at", 1)], name="checked_at")


def record(db, verdict, now: datetime | None = None) -> None:
    db[COLLECTION].update_one(
        {"_id": verdict.url},
        {"$set": {"ok": bool(verdict.ok), "status": verdict.status,
                  "reason": verdict.reason, "final_url": verdict.final_url,
                  "detail": verdict.detail or "",
                  "checked_at": now or datetime.now(UTC)}},
        upsert=True)


def broken_urls(db, urls) -> set:
    """The URLs among `urls` last checked as broken. One query."""
    wanted = sorted({u for u in urls if isinstance(u, str) and u})
    if not wanted:
        return set()
    rows = db[COLLECTION].find({"_id": {"$in": wanted}, "ok": False}, {"_id": 1})
    return {str(r["_id"]) for r in rows}


def checked_since(db, urls, since: datetime) -> set:
    """The URLs among `urls` with a verdict newer than `since`."""
    wanted = sorted(set(urls))
    if not wanted:
        return set()
    rows = db[COLLECTION].find({"_id": {"$in": wanted}, "checked_at": {"$gte": since}},
                               {"_id": 1})
    return {str(r["_id"]) for r in rows}
