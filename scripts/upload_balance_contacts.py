#!/usr/bin/env python
"""Load the client's contacts for the balance accounts (Sahaj, 11 Oct).

23 accounts had no contacts. The client sent `contacts_for_ingest final.csv`
(595 people, 20 accounts) in its own 26-column layout, with these decisions:

  1. no per-account cap - load every row in the file;
  2. the 33 wrong-employer rows are already removed from it;
  3. keep contacts from every country;
  4. personas come from the job titles, as for the other 192 accounts - so the
     file's `committee_angle` is not loaded as a persona;
  5. show every email with its confidence label, CATCH_ALL included, and the
     phone with no "unvalidated" tag;
  6. the three accounts with no contacts lose the Stakeholder Map
     (hp-backend/config/account_overrides.yaml).

This converts each account's rows to the `prospect_contacts.csv` layout the
Stakeholder Map already reads (the Apollo columns), writes them into the
account's split folder, and uploads them. It is a dry run unless --apply:

    hp-backend/.venv/bin/python scripts/upload_balance_contacts.py            # convert + report
    export HP_BASE_URL=https://34-100-196-59.sslip.io HP_EMAIL=... HP_PASSWORD=...
    hp-backend/.venv/bin/python scripts/upload_balance_contacts.py --apply    # upload

Nothing is regenerated here: the upload marks the Stakeholder Map stale for
these accounts and the run is submitted separately.

The source file holds personal data. It is read from where the client's
attachment was saved and is never copied into the repository; the split
folders it writes to are git-ignored.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_account_data import OUTPUT_DIR, _api, _api_token, _api_upload

DATASET_KEY = "prospect_contacts"
DEFAULT_SOURCE = Path.home() / "Downloads" / "contacts_for_ingest final.csv"
DATA_SOURCE = "Client contacts file (contacts_for_ingest final.csv, 11 Oct 2026)"

# The file's account name where it differs from the platform's.
ACCOUNT_ALIASES = {
    "PILIPINAS SHELL PETROLEUM CORP - PH": "PILIPINAS SHELL PETROLEUM CORPORATION - PH",
}

# The file's seniority words -> the values the Stakeholder Map bands on
# (stakeholder_map.SENIORITY_BAND_MAP). Anything else is passed in lower case
# and bands as an individual contributor.
SENIORITY = {
    "c-level": "c_suite", "c suite": "c_suite", "c-suite": "c_suite", "c-team": "c_suite",
    "vp": "vp", "president/vice president": "vp",
    "director": "director", "head": "head", "manager": "manager", "owner": "owner",
}

# The file's department -> the department keys the Stakeholder Map labels
# (stakeholder_map.DEPT_LABELS). A department with no equivalent is passed as
# the client wrote it; "Other / Unclassified" is left blank.
DEPARTMENT = {
    "it & technology": "master_information_technology",
    "finance": "master_finance",
    "legal & compliance": "master_legal",
    "operations": "master_operations",
    "human resources": "master_human_resources",
}
# The sub-department decides where the department alone is too broad:
# "Executive & General Management" holds both the executive team (the
# Stakeholder Map's "Executive") and general managers, who are not.
SUB_DEPARTMENT = {
    "sales & commercial": "master_sales",
    "marketing & communications": "master_marketing",
    "executive leadership": "c_suite",
    "general management": "General Management",
}

# The client's confidence tiers, shown beside the email exactly as the file
# gives them (5: "show every email with its confidence label"). NONE means the
# row has no email, so there is nothing to label.
EMAIL_TIERS = ("VERIFIED", "VALID_RISKY", "CATCH_ALL", "UNKNOWN")

COUNTRY = {"AU": "Australia", "NZ": "New Zealand", "US": "United States", "KR": "South Korea",
           "ES": "Spain"}


def clean(value) -> str:
    return " ".join(str(value or "").split())


def department(row: dict) -> str:
    sub = SUB_DEPARTMENT.get(clean(row.get("sub_department")).lower())
    if sub:
        return sub
    raw = clean(row.get("department"))
    if raw.lower().startswith("other"):
        return ""
    return DEPARTMENT.get(raw.lower(), raw)


def country(row: dict) -> str:
    raw = clean(row.get("person_country"))
    return COUNTRY.get(raw.upper(), raw.title() if raw.islower() or raw.istitle() else raw) \
        if raw else ""


def convert(row: dict, account: dict) -> dict:
    """One row of the client's file in the prospect_contacts layout."""
    name = clean(row["full_name"])
    first, _, last = name.partition(" ")
    title = clean(row["job_title"])
    seniority = clean(row.get("seniority"))
    seniority = SENIORITY.get(seniority.lower(), seniority.lower())
    email = clean(row.get("email"))
    tier = clean(row.get("email_confidence")).upper()
    status = tier if email and tier in EMAIL_TIERS else ""
    phone = clean(row.get("phone"))
    linkedin = clean(row.get("linkedin_url"))
    dept = department(row)
    return {
        "Company Name": account["vendor_company_name"],
        "Company Domain": account.get("domain") or "",
        "Prospect first_name": first,
        "Prospect last_name": last,
        "Prospect full_name": name,
        "Prospect country_name": country(row),
        "Prospect linkedin": linkedin,
        "Prospect company_name": clean(row.get("company")),
        "Prospect job_department_main": dept,
        "Prospect job_level_main": seniority,
        "Prospect job_title": title,
        "Email": email,
        "Email Status": status,
        "Mobile Phone": phone,
        "data_source": DATA_SOURCE,
        # The other 192 accounts' contacts are vendor-matched people; these are
        # the same kind, so they carry the same marker and are treated alike.
        "apollo_matched_contact": name,
        "apollo_match_status": "Client file",
        "apollo_title": title,
        "apollo_seniority": seniority,
        "apollo_department": dept,
        "apollo_verified_work_email": email,
        "apollo_linkedin_url": linkedin,
    }


def header() -> list:
    """The prospect_contacts columns, from an account that already has them."""
    for path in sorted(OUTPUT_DIR.glob("*/prospect_contacts.csv")):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            cols = next(csv.reader(fh), [])
        if "apollo_matched_contact" in cols and "Prospect full_name" in cols:
            return cols
    sys.exit("no existing prospect_contacts.csv to take the column layout from")


def folders() -> dict:
    out = {}
    for path in OUTPUT_DIR.glob("*/_account.json"):
        account = json.loads(path.read_text(encoding="utf-8"))
        out[clean(account.get("name_for_upload")).lower()] = (path.parent, account)
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="The client's CSV.")
    parser.add_argument("--base-url", default="", help="Deployed backend (default $HP_BASE_URL).")
    parser.add_argument("--apply", action="store_true", help="Actually upload.")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.exists():
        sys.exit(f"{source} not found - pass --source")
    with open(source, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    by_folder, cols = folders(), header()
    grouped = defaultdict(list)
    for row in rows:
        name = clean(row["account"])
        grouped[ACCOUNT_ALIASES.get(name, name)].append(row)
    unknown = [a for a in grouped if a.lower() not in by_folder]
    if unknown:
        sys.exit("no split folder for: " + ", ".join(unknown))

    # Convert and write. Local only: the upload below is the gated step.
    paths, seen = {}, Counter()
    for name, account_rows in sorted(grouped.items()):
        folder, account = by_folder[name.lower()]
        out = [convert(r, account) for r in account_rows]
        path = folder / f"{DATASET_KEY}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(out)
        paths[name] = path
        seen[name] = len(out)
    print(f"Converted {sum(seen.values())} contacts for {len(seen)} accounts "
          f"from {source.name}\n")

    base_url = (args.base_url or os.getenv("HP_BASE_URL") or "").rstrip("/")
    if not base_url:
        for name, n in seen.most_common():
            print(f"  {n:4d}  {name}")
        print("\nFiles written. Set HP_BASE_URL (and HP_EMAIL / HP_PASSWORD) to plan the upload.")
        return

    token = _api_token(base_url)
    status, accounts = _api(f"{base_url}/api/v1/accounts", token)
    if status != 200 or not isinstance(accounts, list):
        sys.exit(f"could not list accounts (HTTP {status}): {accounts}")
    on_server = {clean(a.get("name")).lower(): a for a in accounts}

    print(f"Backend: {base_url}   {'APPLY' if args.apply else 'DRY RUN - nothing is sent'}\n")
    failed = 0
    for name, path in paths.items():
        acct = on_server.get(name.lower())
        if not acct:
            print(f"  NOT FOUND {name}  (no such account on the server)")
            failed += 1
            continue
        data = path.read_bytes()
        status, files = _api(f"{base_url}/api/v1/accounts/{acct['id']}/data", token)
        active = next((f for f in files if f.get("dataset_key") == DATASET_KEY
                       and f.get("status") == "active"), None) if isinstance(files, list) else None
        if active and (active.get("stored_filename") or "").split("_", 1)[0] \
                == hashlib.sha256(data).hexdigest()[:12]:
            print(f"  same      {name}  (already on the server)")
            continue
        if not args.apply:
            print(f"  would up  {seen[name]:4d} contact(s)  {name}"
                  + ("  (replaces the file on the server)" if active else ""))
            continue
        status, body = _api_upload(f"{base_url}/api/v1/accounts/{acct['id']}/data",
                                   token, DATASET_KEY, path)
        if status in (200, 201):
            print(f"  uploaded  {seen[name]:4d} contact(s)  {name}")
        else:
            failed += 1
            print(f"  FAILED    {name}  HTTP {status}: {(body or {}).get('detail')}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to upload.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
