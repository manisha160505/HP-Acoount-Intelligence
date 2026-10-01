"""The gate audit ledger, and the six CSVs Section 6 asks for.

    "Every gate produces a machine-readable audit row. An empty audit file is a
     pass. A non-empty audit file lists specific rows to fix."
    "Written per generation batch, to be reviewed before a batch is released to
     sellers."
                     - HP220 Content Studio & Message Evaluator Build Spec, 6

`content_gates.audit_rows()` has produced those rows since the gates were
built. Nothing collected them, so the six files existed as filenames and never
as files.

**Why a ledger and not a batch job.** Section 7's coverage run reads as a
one-off sweep of five accounts before release, and it could have been written
that way. But Content Studio does not generate at build time the way the other
features do - it needs a seller's persona, format and topic - so a sweep has to
invent 24 topics per account and judge content nobody asked for. Recording what
the gates find on real generations instead gives the same six files, from real
sellers writing to real accounts, accumulating from each account's first use.
The sweep is then an export with a date range rather than a run.

**Every attempt is recorded, not only what was published.** A rejected draft is
retried, and the retry usually passes - so a ledger of published output only
would show an empty `audit_line_eligibility.csv` on a batch where the model
tried to sell Poly to a CFO four times. The specification calls that file "the
one to check first", which it cannot be if the retry hides it. Each row carries
the outcome, so a reviewer can separate "caught and fixed" from "reached a
seller".
"""

import csv
import logging
import os
from datetime import UTC, datetime

from app.services.hp import content_gates

logger = logging.getLogger(__name__)

COLLECTION = "content_gate_audit"

# What happened to the draft these findings were raised against.
OUTCOME_PUBLISHED = "published"      # the seller saw it, warnings and all
OUTCOME_REGENERATED = "regenerated"  # rejected, retried, a later attempt stood
OUTCOME_WITHHELD = "withheld"        # rejected to the end; nothing published

# Which feature the draft came from. A rewrite is scored by the same gates and
# is the version the seller actually sends, so it belongs in the same files.
SURFACE_GENERATION = "content_studio"
SURFACE_REWRITE = "evaluator_rewrite"

# The order the CSVs are written in, and the columns Section 6 specifies for
# each. `audit_other.csv` is ours: the specification names six files and
# fourteen gates, and G3, G5, G10, G11, G12, G13 and G14 have no file of their
# own. They go here rather than nowhere.
CSV_COLUMNS = {
    content_gates.AUDIT_UNSOURCED_NUMBERS:
        ("account_id", "persona_id", "format", "offending_token", "sentence"),
    content_gates.AUDIT_LINE_ELIGIBILITY:
        ("account_id", "persona_id", "denied_line_named", "where_found"),
    content_gates.AUDIT_ASK_BOUND:
        ("account_id", "persona_id", "committee_angle", "ask_text", "violation_type"),
    content_gates.AUDIT_NAME_LEAK:
        ("account_id", "persona_id", "leaked_name", "sentence"),
    content_gates.AUDIT_BANNED_PHRASES:
        ("account_id", "persona_id", "phrase", "sentence"),
    content_gates.AUDIT_EVIDENCE_LABELS:
        ("account_id", "persona_id", "invalid_label"),
    content_gates.AUDIT_OTHER:
        ("account_id", "persona_id", "format", "gate", "detail"),
}

# Added to every row on the way out, so a reviewer looking at a line can find
# the generation it came from without joining anything.
TRACE_COLUMNS = ("gate", "action", "outcome", "surface", "recorded_at")


def record(db, findings, *, account_id: str, persona_id: str,
           content_type: str, outcome: str, surface: str = SURFACE_GENERATION,
           asset_id: str = "") -> int:
    """Write one attempt's gate findings to the ledger. Returns rows written.

    Never raises into a generation. A seller waiting on an email should not
    lose it because an audit insert failed - the draft is the product and the
    ledger is the paperwork.
    """
    if not findings:
        return 0
    try:
        rows = content_gates.audit_rows(
            findings, account_id=account_id, persona_id=persona_id,
            content_type=content_type)
    except Exception:
        logger.exception("content audit: could not shape rows for %s", account_id)
        return 0

    now = datetime.now(UTC)
    documents = []
    for audit_file, entries in rows.items():
        for entry in entries:
            documents.append({
                **entry,
                "audit_file": audit_file,
                "outcome": outcome,
                "surface": surface,
                "asset_id": asset_id,
                "recorded_at": now,
            })
    if not documents:
        return 0
    try:
        db[COLLECTION].insert_many(documents)
    except Exception:
        logger.exception("content audit: insert failed for %s", account_id)
        return 0
    return len(documents)


def read(db, *, account_id: str = "", since=None, surface: str = "",
         outcome: str = "") -> list:
    """Ledger rows, newest first. Every filter is optional."""
    query: dict = {}
    if account_id:
        query["account_id"] = account_id
    if surface:
        query["surface"] = surface
    if outcome:
        query["outcome"] = outcome
    if since:
        query["recorded_at"] = {"$gte": since}
    try:
        return list(db[COLLECTION].find(query, {"_id": 0}).sort("recorded_at", -1))
    except Exception:
        logger.exception("content audit: read failed")
        return []


def export(db, out_dir: str, **filters) -> dict:
    """Write the six files (plus `audit_other`). Returns {filename: row count}.

    Every file is written even when it is empty, headers and all. An empty file
    is the pass signal Section 6 describes, and a missing file is ambiguous
    between "nothing to report" and "nobody ran the export".
    """
    os.makedirs(out_dir, exist_ok=True)
    rows = read(db, **filters)

    by_file: dict = {name: [] for name in CSV_COLUMNS}
    for row in rows:
        by_file.setdefault(row.get("audit_file") or content_gates.AUDIT_OTHER,
                           []).append(row)

    written = {}
    for name, columns in CSV_COLUMNS.items():
        path = os.path.join(out_dir, name)
        header = [*columns, *TRACE_COLUMNS]
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in by_file.get(name) or []:
                writer.writerow([_cell(row.get(column)) for column in header])
        written[name] = len(by_file.get(name) or [])
    return written


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return " ".join(str(value).split())


def is_clean(counts: dict) -> bool:
    """Section 7's release gate: "All must be empty before release."."""
    return not any(counts.values())
