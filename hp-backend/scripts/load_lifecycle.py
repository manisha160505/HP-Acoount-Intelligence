"""Load HP's product lifecycle file into Mongo.

Recommendation Tuning Logic, section J (marked new in the FINAL v4 revision):

    "Before surfacing an HP Product, Service or Solution, check the HP Lifecycle
    file if that offering is listed there. If listed and its applicable PE/EM or
    lifecycle end date has passed, do not recommend it. If it is approaching
    lifecycle end, recommend it but also flag it in the backend so that it is
    not recommended once after that date has passed in future. If the Product,
    Service or Solution is not listed in the Lifecycle file, the absence of a
    lifecycle record does not block the recommendation."

Three things this loader has to decide, because the source does not:

**Which date is "applicable".** 84 of the 146 rows carry SEVERAL dates in one
cell - "30/9/2025 / 31 October 2026 / 30 Nov 2026 / 30 June 2027" - with no
column saying which market each belongs to. A product is treated as past its
end only when the LATEST of its dates has gone: while any date is still ahead,
the platform is still being sold somewhere, and blocking on the earliest would
withdraw a recommendation for a product HP is still shipping. Once the earliest
has passed it is `approaching`, which is what section J asks to flag.

**How a row is matched to an offering.** Strictly, on the generation token.
The rulebook sells "HP EliteBook 8 G2 Series"; this file lists "HP EliteBook 8
G1i Flip" - the PREVIOUS generation, which is what a lifecycle file is for. A
loose family match would read those as the same product and suppress a current
recommendation because an older one is ending. So the generation marker (G2,
G1i, G1q, G9) must match, and a name carrying no generation never matches
anything.

**What happens on no match.** Nothing. Section J is explicit that an absent
record is not a blocker, so every uncertainty here resolves towards
recommending, never towards silently withholding.

Run:  python scripts/load_lifecycle.py [path/to/lifecycle.xlsx]
"""

import logging
import os
import re
import sys
from datetime import UTC, date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd
from dateutil import parser as date_parser
from dotenv import load_dotenv

load_dotenv()

from app.database.mongodb import get_db  # noqa: E402

logger = logging.getLogger(__name__)

COLLECTION = "hp_lifecycle"

DEFAULT_XLSX = os.path.join(
    os.path.dirname(__file__), "..", "..", "additional_data",
    "Hp lifecycle june 2026.xlsx")

# Bump when the parse changes, so a reload replaces rows written by an older one.
EXTRACTOR_VERSION = 1

NAME_COL = "Platform Description"
FAMILY_COL = "Platform Family"
DATE_COLUMNS = (
    "Global Series Planned End (PE) Date",
    "Global Series Planned End (PE) Date/ Global Account End of Manufacturing (EM) Date",
    "WW End of Mfg (EM) or Disco Date",
)
ALERT_COL = "Early Alert date to start transition (*PTT)"

# A product generation: G2, G1i, G1q, G9, G10. The letter suffix matters -
# G1i and G1q are different products, and G1i is not G2.
GENERATION_RE = re.compile(r"\bg(\d+)([a-z]?)\b", re.I)

# Words that say nothing about which product this is.
_NOISE = frozenset("""
hp series the and or of for with all in one inch pc desktop notebook
""".split())


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def generations(name: str) -> set:
    """Generation markers in a product name, normalised. Empty when none."""
    return {"g%s%s" % (m.group(1), (m.group(2) or "").lower())
            for m in GENERATION_RE.finditer(_text(name))}


def identity(name: str) -> set:
    """The distinctive words of a product name, for matching."""
    words = re.findall(r"[a-z0-9]+", _text(name).lower())
    return {w for w in words if w not in _NOISE and not GENERATION_RE.fullmatch(w)}


def parse_dates(cell) -> list:
    """Every date in one cell. Cells hold several, newline separated.

    Split on the RAW value, before `_text` - it collapses all whitespace,
    newlines included, so normalising first turned "30/9/2025 (newline) 31
    October 2026" into one string that parses as no date at all and silently
    lost the dates on 65 of 146 rows.
    """
    out = []
    raw = "" if cell is None else str(cell)
    for piece in re.split(r"[\n;]+", raw):
        piece = " ".join(piece.split()).strip()
        if not piece or piece.lower() in ("nan", "nat", "tbd", "tbc"):
            continue
        try:
            out.append(date_parser.parse(piece, dayfirst=True).date())
        except (ValueError, OverflowError, TypeError):
            continue
    return sorted(set(out))


def build_record(row) -> dict | None:
    """One stored lifecycle record, or None when the row names no product."""
    name = _text(row.get(NAME_COL))
    if not name:
        return None

    ends = []
    for column in DATE_COLUMNS:
        ends.extend(parse_dates(row.get(column)))
    ends = sorted(set(ends))

    return {
        "_id": "lifecycle::%s" % re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
        "product": name,
        "family": _text(row.get(FAMILY_COL)),
        "generations": sorted(generations(name)),
        "identity": sorted(identity(name)),
        # Every date the row carries, earliest first. `last_end` decides whether
        # the product is gone; `first_end` decides whether it is approaching.
        "end_dates": [d.isoformat() for d in ends],
        "first_end": ends[0].isoformat() if ends else None,
        "last_end": ends[-1].isoformat() if ends else None,
        "early_alert": (parse_dates(row.get(ALERT_COL)) or [None])[0].isoformat()
                       if parse_dates(row.get(ALERT_COL)) else None,
        "comments": _text(row.get("Comments")) or None,
        "source": "HP lifecycle file, %s" % _text(row.get("Last Updated"))[:10],
        "extractor_version": EXTRACTOR_VERSION,
    }


def load(path: str) -> dict:
    """Parse the workbook and replace this extractor's rows in Mongo."""
    frame = pd.read_excel(path)
    records = [r for r in (build_record(row) for _i, row in frame.iterrows()) if r]

    db = get_db()
    now = datetime.now(UTC)
    for record in records:
        record["loaded_at"] = now
        db[COLLECTION].replace_one({"_id": record["_id"]}, record, upsert=True)

    stale = db[COLLECTION].delete_many(
        {"_id": {"$nin": [r["_id"] for r in records]}})

    today = date.today()  # noqa: DTZ011 - a calendar day, not an instant
    past = sum(1 for r in records if r["last_end"] and r["last_end"] < today.isoformat())
    approaching = sum(1 for r in records
                      if r["first_end"] and r["first_end"] < today.isoformat()
                      and not (r["last_end"] and r["last_end"] < today.isoformat()))
    return {
        "rows": len(frame),
        "stored": len(records),
        "removed_stale": stale.deleted_count,
        "without_a_date": sum(1 for r in records if not r["end_dates"]),
        "without_a_generation": sum(1 for r in records if not r["generations"]),
        "past_end": past,
        "approaching_end": approaching,
        "families": len({r["family"] for r in records if r["family"]}),
    }


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_XLSX
    if not os.path.exists(path):
        print("no such file: %s" % path)
        raise SystemExit(1)
    report = load(path)
    print("loaded %s" % os.path.basename(path))
    for key, value in report.items():
        print("   %-22s %s" % (key, value))
