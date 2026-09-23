"""Section J: do not recommend an HP product that has reached end of life.

    "Before surfacing an HP Product, Service or Solution, check the HP Lifecycle
    file if that offering is listed there. If listed and its applicable PE/EM or
    lifecycle end date has passed, do not recommend it. If it is approaching
    lifecycle end, recommend it but also flag it in the backend so that it is
    not recommended once after that date has passed in future. If the Product,
    Service or Solution is not listed in the Lifecycle file, the absence of a
    lifecycle record does not block the recommendation."
        - HP Recommendation Tuning Logic FINAL v4, section J

Two decisions the source document leaves open, both resolved towards
recommending rather than withholding, because section J's own closing sentence
says an absent record is not a blocker.

**Which of several dates applies.** 84 of the 146 rows carry more than one date
in a single cell, with nothing saying which market each belongs to. A product
counts as past its end only when the LATEST has gone; while one is still ahead
HP is still shipping it somewhere. Once the earliest has passed the product is
`approaching`, which is the state section J asks to flag.

**What counts as the same product.** The generation marker has to match. This
file lists the generation that is ENDING - "HP EliteBook 8 G1i Flip" - while the
rulebook sells the one that is current, "HP EliteBook 8 G2 Series". Matching on
the family alone would read those as one product and withdraw a live
recommendation because its predecessor is being retired. An offering carrying no
generation marker matches nothing, and is therefore never blocked.
"""

import logging
import re
from datetime import UTC, date, datetime

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)

COLLECTION = "hp_lifecycle"

# How long before the last end date a product is called "approaching" even when
# none of its dates has passed yet. Section J does not set a window, so this is
# only a widening of the state it does define - a product whose earliest date
# has already gone is approaching regardless of this constant.
APPROACHING_WITHIN_DAYS = 180

PAST_END = "past_end"
APPROACHING = "approaching"
LISTED_FUTURE = "listed_future"
NOT_LISTED = "not_listed"

GENERATION_RE = re.compile(r"\bg(\d+)([a-z]?)\b", re.I)

_NOISE = frozenset(["hp", "series", "the", "and", "or", "of", "for", "with", "all", "in", "one", "inch", "pc", "desktop", "notebook", "customer", "presentation", "deck", "mapped", "product", "already", "selected", "portfolio"])

# At least this many distinctive words must be shared before two names are
# treated as the same product, on top of the generation matching.
MIN_SHARED_WORDS = 2


def _generations(name: str) -> set:
    return {"g%s%s" % (m.group(1), (m.group(2) or "").lower())
            for m in GENERATION_RE.finditer(str(name or ""))}


def _identity(name: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(name or "").lower())
    return {w for w in words if w not in _NOISE and not GENERATION_RE.fullmatch(w)}


def load(db=None) -> list:
    """Every stored lifecycle record. Empty when the file was never loaded."""
    # `db is not None`, never `db or ...`: a pymongo Database raises
    # NotImplementedError on truth testing, and the broad except below turned
    # that into a silent empty list - every product read as "not listed", which
    # is precisely the direction this module must never fail in by accident.
    try:
        handle = db if db is not None else get_db()
        return list(handle[COLLECTION].find({}))
    except Exception:
        logger.exception("lifecycle: could not read %s", COLLECTION)
        return []


def _match(offering: str, rows: list) -> dict | None:
    """The lifecycle row naming this exact product, or None."""
    gens = _generations(offering)
    if not gens:
        return None
    words = _identity(offering)
    if not words:
        return None

    best, best_overlap = None, 0
    for row in rows:
        if not (gens & set(row.get("generations") or ())):
            continue
        overlap = len(words & set(row.get("identity") or ()))
        if overlap >= MIN_SHARED_WORDS and overlap > best_overlap:
            best, best_overlap = row, overlap
    return best


def status_for(offering: str, today: date | None = None, rows: list | None = None) -> dict:
    """Whether this offering may be recommended, and why.

    Always returns a decision. `recommendable` is False only for a product this
    file lists AND whose last end date has passed - every other outcome,
    including "not listed" and "could not read the file", recommends.
    """
    today = today or datetime.now(UTC).date()
    rows = load() if rows is None else rows
    row = _match(offering, rows or [])

    if not row:
        return {"status": NOT_LISTED, "recommendable": True, "product": None,
                "basis": "no lifecycle record names this product, which section J "
                         "says is not a blocker"}

    first, last = row.get("first_end"), row.get("last_end")
    stamp = today.isoformat()
    common = {"product": row.get("product"), "family": row.get("family"),
              "end_dates": row.get("end_dates") or [],
              "source": row.get("source")}

    if last and last < stamp:
        return {**common, "status": PAST_END, "recommendable": False,
                "basis": "every lifecycle end date for %s has passed (last %s)"
                         % (row.get("product"), last)}

    approaching = bool(first and first < stamp)
    if not approaching and last:
        try:
            approaching = (date.fromisoformat(last) - today).days <= APPROACHING_WITHIN_DAYS
        except ValueError:
            approaching = False

    if approaching:
        return {**common, "status": APPROACHING, "recommendable": True,
                "flag": "approaching lifecycle end",
                "basis": "%s is approaching lifecycle end (dates from %s to %s)"
                         % (row.get("product"), first or "?", last or "?")}

    return {**common, "status": LISTED_FUTURE, "recommendable": True,
            "basis": "%s is listed with no end date reached (first %s)"
                     % (row.get("product"), first or "?")}
