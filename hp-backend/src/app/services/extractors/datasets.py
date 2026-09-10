"""One place that turns a registered dataset into rows.

Every extractor used to carry its own copy of this logic. Seven of them also
carried an absolute path to one developer's machine as a fallback, which is
dead weight anywhere else and violates the account-agnostic rule.

The distinction that matters here is between two situations the old code
collapsed into the same empty list:

  * no file is registered for this dataset  -> legitimately nothing to read
  * a file IS registered but is absent from this machine's disk

Only the metadata lives in MongoDB; the CSV bytes live on local disk
(`account_data.py` writes them there and stores the path). With a shared
database that second case is normal - a teammate's database row points at a
file that only exists on the uploader's machine. Returning `[]` for it made
extractors publish empty widgets over perfectly good stored ones, for
everybody. So it raises instead.
"""

import csv
import functools
import logging
import os

import pandas as pd

from app.database.mongodb import get_db

logger = logging.getLogger(__name__)


class DatasetFileMissing(Exception):
    """A dataset is registered as active but its file is not on this machine."""

    def __init__(self, dataset_key: str, rel_path: str):
        self.dataset_key = dataset_key
        self.rel_path = rel_path
        super().__init__(
            f"dataset '{dataset_key}' is registered but its file is not on this "
            f"machine (expected at '{rel_path}')"
        )


def find_file_path(rel_path: str) -> str | None:
    """Absolute path for a stored relative path, or None if it is not here.

    Ordered by how specific the guess is. The working directory comes first
    because the seeder writes datasets relative to it; the `__file__` walks
    cover being started from somewhere else; `/app` covers the container.
    """
    if not rel_path:
        return None

    here = os.path.dirname(__file__)
    for candidate in (
        os.path.join(os.getcwd(), rel_path),
        os.path.join("/app", rel_path),
        os.path.abspath(os.path.join(here, "..", "..", "..", rel_path)),
        os.path.abspath(os.path.join(here, "..", "..", rel_path)),
        os.path.abspath(os.path.join(here, "..", rel_path)),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _parse(full_path: str) -> list[dict]:
    ext = os.path.splitext(full_path)[1].lower()
    try:
        if ext in (".xlsx", ".xls"):
            return pd.read_excel(full_path).fillna("").to_dict(orient="records")
        with open(full_path, "r", encoding="utf-8-sig", errors="replace") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        logger.exception("Could not parse dataset file %s", full_path)
        return []


def read_dataset_records(account_id: str, dataset_key: str,
                         strict: bool = True) -> list[dict]:
    """Rows for one dataset.

    Returns [] when nothing is registered. Raises DatasetFileMissing when a
    file IS registered and cannot be found locally, unless `strict` is False.
    """
    db = get_db()
    file_doc = db["account_data_files"].find_one({
        "account_id": account_id,
        "$or": [{"dataset_key": dataset_key}, {"category": dataset_key}],
        "status": "active",
    })
    if not file_doc:
        return []

    rel_path = file_doc.get("file_path", "")
    full_path = find_file_path(rel_path)
    if not full_path:
        if strict:
            raise DatasetFileMissing(dataset_key, rel_path)
        logger.warning("dataset '%s' registered at '%s' is not on this machine",
                       dataset_key, rel_path)
        return []

    return _parse(full_path)


def missing_local_datasets(account_id: str) -> list[str]:
    """Datasets registered active for this account whose file is not here."""
    db = get_db()
    missing = []
    for doc in db["account_data_files"].find(
            {"account_id": account_id, "status": "active"},
            {"dataset_key": 1, "category": 1, "file_path": 1}):
        key = doc.get("dataset_key") or doc.get("category") or "?"
        if not find_file_path(doc.get("file_path", "")):
            missing.append(key)
    return sorted(set(missing))


def requires_local_datasets(*dataset_keys: str):
    """Abort an extractor when the files it reads are not on this machine.

    Checked before the extractor runs, not during, so a run can never write
    some widgets and then bail - it either has its inputs or it does nothing.

    The extractor names its own datasets at the decoration site rather than
    looking them up in FEATURE_MAPPINGS, because that module lives in the API
    layer and importing it here would invert the dependency.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(account_id: str, *args, **kwargs):
            db = get_db()
            absent = []
            for key in dataset_keys:
                doc = db["account_data_files"].find_one({
                    "account_id": account_id,
                    "$or": [{"dataset_key": key}, {"category": key}],
                    "status": "active",
                }, {"file_path": 1})
                if doc and not find_file_path(doc.get("file_path", "")):
                    absent.append(key)

            if absent:
                logger.error(
                    "%s skipped for account %s: %s registered but not on this "
                    "machine. Stored widgets left untouched rather than "
                    "overwritten with empty data.",
                    fn.__name__, account_id, ", ".join(absent),
                )
                return []
            return fn(account_id, *args, **kwargs)
        return wrapper
    return decorator
