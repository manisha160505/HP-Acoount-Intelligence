"""Parents and subsidiaries the client supplied on 7 Oct, beside Explorium's.

`config/company_relationships.csv` is built by
`scripts/build_company_relationships.py` from two things in Dhruvi's email of
7 Oct 2026:

  * the updated parent-company mapping for 11 accounts. For those accounts it
    is the only parent source: it replaces Explorium's Company Hierarchy row,
    whose parent was wrong at source (MUFG -> US Bancorp, Viettel -> UK
    Ministry of Defence). `no_parent` means the account has none to show.
  * the merged company hierarchy sheet, which names parents and subsidiaries
    for 42 accounts. These are added to Explorium's, never in place of them:
    an account can have two parents (a direct one and an ultimate one), and
    both are shown.

Self rows were removed when the file was built, on review, so nothing here
guesses at read time which names are the account itself.

The file is part of the Executive Dashboard's logic: RELATIONSHIPS_VERSION is
referenced by its node (regen/graph.py), and a test pins the file's hash to
FILE_SHA256, so editing the data without bumping the version fails CI rather
than leaving every dashboard silently built from the old file.
"""

import csv
import hashlib
import os
from functools import lru_cache

RELATIONSHIPS_VERSION = 1
FILE_SHA256 = "766efbd6702547bec22fdba0ceaca2062dbf96bf1350653a59353f358d24fc86"

PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "..", "config", "company_relationships.csv"))


def _key(name: str) -> str:
    """The account's name, lowercased, without its ' - XX' country suffix -
    the same key `executive_dashboard._account_key` uses."""
    s = " ".join(str(name or "").lower().split())
    head, sep, tail = s.rpartition(" - ")
    return head if sep and len(tail) == 2 else s


def file_sha256(path: str = PATH) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


@lru_cache(maxsize=1)
def _load(path: str = PATH) -> dict:
    out: dict = {}
    if not os.path.exists(path):
        return out
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            entry = out.setdefault(_key(row["account"]), {
                "override": None, "parents": [], "subsidiaries": []})
            rel, company = row["relationship"], " ".join((row["company"] or "").split())
            if rel == "no_parent":
                entry["override"] = []
            elif rel == "parent" and row["source"].startswith("parent-company mapping"):
                entry["override"] = (entry["override"] or []) + [company]
            elif rel == "parent":
                entry["parents"].append(company)
            elif rel == "subsidiary":
                entry["subsidiaries"].append(company)
    return out


def for_account(account_name: str) -> dict:
    """{"override": [parents] | [] | None, "parents": [...], "subsidiaries": [...]}.

    `override` is None when the client's mapping does not cover the account;
    an empty list when it says the account has no parent.
    """
    return _load().get(_key(account_name)) or {"override": None, "parents": [],
                                               "subsidiaries": []}
