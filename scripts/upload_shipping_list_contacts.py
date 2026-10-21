#!/usr/bin/env python
"""Load the client's final contact file (Dhruvi, 19 and 21 Oct).

`HP220_FINAL_contacts_20Oct2026.xlsx`, tab "finalised columns": 3,371 people
for 212 accounts, phone numbers checked. Accounts not in the file (about 7,
mostly government bodies, unlikely to get contacts) keep what they have. The
19 Oct `shipping_list_with_four_tabs.xlsx` loads too, with --sheet "Shipping List".

Decisions (19-21 Oct email thread):

  1. every account in the file gets the file's contacts, Astra included - its
     pilot contacts are replaced;
  2. the columns we loaded before are loaded again: name, title, department,
     seniority, country and city (when the tab has them), email, phone, LinkedIn.
     Personas come from the job titles, as for every other account, so
     `committee_angle` is not loaded;
  3. email tag (column J, `email_status`): shown as provided, but
       - only when there is an email address;
       - catch_all and CATCH_ALL are one tag, CATCH_ALL;
       - a status that only says nothing could be found or checked (unknown,
         unavailable, not found, could_not_verify, unverified, N/A ...) is
         left blank, as is a blank status. The same rule applies to the phone
         tag. A contact is never dropped for it;
  4. phone (column K): shown only when there is a number, with its line type
     (column M, `phone_line_type`: MOBILE, LANDLINE, VOIP) as the phone tag. No number, no
     phone and no tag. A number the spreadsheet stored in scientific notation
     ("8.17048E+11") has lost its digits; it is treated as no number and listed
     in the report, never shown.

This converts each account's rows to the `prospect_contacts.csv` layout the
features already read (see upload_balance_contacts.py), writes them into the
account's split folder and uploads them. It is a dry run unless --apply:

    hp-backend/.venv/bin/python scripts/upload_shipping_list_contacts.py --source <xlsx>
    export HP_BASE_URL=https://hp.abx.220.bridgeai.ai HP_EMAIL=bridge@gmail.com HP_PASSWORD=...
    hp-backend/.venv/bin/python scripts/upload_shipping_list_contacts.py --source <xlsx> --apply
    ... --apply --regenerate     # then one run for the uploaded accounts (super admin)

Uploading only marks the accounts' contact-based sections stale. --regenerate
submits one run for exactly the accounts uploaded, downstream sections
included; it needs the super admin's login.

The source file holds personal data. It is read from wherever it was saved and
is never copied into the repository; the split folders it writes to are
git-ignored.
"""

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from split_account_data import _api, _api_token, _api_upload
from upload_balance_contacts import (
    DATASET_KEY,
    DEPARTMENT,
    SENIORITY,
    clean,
    folders,
    header,
)

SHEET = "finalised columns"
PHONE_TAG_COLUMN = "Phone Line Type"

# The server's account name where it differs from the split's upload name.
SERVER_NAMES = {"pt astra international tbk - id": "astra"}

# role_department -> the Stakeholder Map's department keys, beyond the 11 Oct
# file's vocabulary. A department with no key is passed as written.
DEPARTMENTS = {**DEPARTMENT, "legal": "master_legal", "executive": "c_suite"}

# Highest first: a cell such as "head; director" bands on the senior value.
SENIORITY_RANK = ["c_suite", "vp", "director", "head", "manager", "owner"]

# A status that only says nothing could be found or checked - unknown,
# unavailable, not found, could not verify, unverified, N/A and the like - is
# no information, so it shows no tag (client, 21 Oct), for email and phone
# alike. The contact itself is always kept.
NO_INFO_TAG = re.compile(
    r"^$|unknown|unavailable|not[\s_-]*(found|available|verified|provided|checked)"
    r"|could[\s_-]*not|can[\s_-]*not|cannot|unable|unverified|unverifiable|invalid"
    r"|pending|error|failed|^(n/?a|na|none|null|nil|-+)$",
    re.IGNORECASE)


def no_info(tag: str) -> bool:
    return bool(NO_INFO_TAG.search(clean(tag)))


PHONE_TAGS = {"MOBILE", "LANDLINE", "VOIP"}
SCIENTIFIC = re.compile(r"\d[eE][+-]?\d+$")


def seniority(raw) -> str:
    parts = [SENIORITY.get(p, p) for p in (s.strip().lower() for s in clean(raw).split(";")) if p]
    ranked = [p for p in SENIORITY_RANK if p in parts]
    return ranked[0] if ranked else (parts[0] if parts else "")


def email_tag(email: str, status) -> str:
    if not email:
        return ""
    tag = clean(status)
    if no_info(tag):
        return ""
    return "CATCH_ALL" if tag.upper() == "CATCH_ALL" else tag


def person_key(name) -> str:
    return re.sub(r"[^a-z]", "", clean(name).lower())


def phone_digits(value) -> set[str]:
    """Every phone-like number in a cell, as digits ("6281293986658.0" too)."""
    out = set()
    for m in re.findall(r"\+?\d[\d\s\-().]{6,}\d", str(value or "")):
        digits = re.sub(r"\D", "", re.sub(r"\.0+$", "", m))
        if len(digits) >= 8:
            out.add(digits)
    return out


PREVIOUS_PHONE_COLUMNS = ("Mobile Phone", "Contact mobile_phone", "Phone Numbers",
                          "apollo_direct_mobile_phone", "apollo_direct_mobile_phone_as_delivered",
                          "apollo_added_phone")


def read_previous(folder: Path | None) -> dict[str, dict[str, set[str]]]:
    """account folder name -> person -> the numbers their earlier record held."""
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    if folder is None:
        return out
    for path in folder.glob("*/prospect_contacts.csv"):
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for r in csv.DictReader(fh):
                for col in PREVIOUS_PHONE_COLUMNS:
                    out[path.parent.name][person_key(r.get("Prospect full_name"))] |= \
                        phone_digits(r.get(col))
    return out


def restore(damaged: str, known: set[str]) -> str:
    """The one known number that "8.17048E+11" can be: same length, same
    leading digits. Empty when there is none, or more than one."""
    mantissa, _, exponent = damaged.upper().partition("E")
    lead = mantissa.replace(".", "")
    length = int(exponent) + 1
    hits = [d for d in known if len(d) == length and d.startswith(lead)]
    return hits[0] if len(hits) == 1 else ""


def phone_and_tag(raw, line_type, known: set[str] = frozenset()) -> tuple[str, str, str]:
    """(number, tag, how): how is "", "restored" or "damaged". A damaged number
    that cannot be restored is dropped with its tag."""
    number = clean(raw)
    how = ""
    if not number:
        return "", "", ""
    if SCIENTIFIC.search(number):
        number = restore(number, known)
        if not number:
            return "", "", "damaged"
        how = "restored"
    tag = clean(line_type).upper()
    return number, tag if tag in PHONE_TAGS and not no_info(tag) else "", how


def convert(row: dict, account: dict, known: set[str] = frozenset(),
            data_source: str = "Client contact file") -> tuple[dict, str]:
    """One shipping-list row in the prospect_contacts layout, and what happened
    to its phone number ("", "restored" or "damaged"). `known`: the numbers
    this person's earlier record held."""
    name = clean(row.get("full_name"))
    first, _, last = name.partition(" ")
    title = clean(row.get("job_title"))
    level = seniority(row.get("seniority"))
    dept_raw = clean(row.get("role_department"))
    dept = DEPARTMENTS.get(dept_raw.lower(), dept_raw)
    email = clean(row.get("email"))
    phone, phone_tag, how = phone_and_tag(row.get("phone"), row.get("phone_line_type"), known)
    linkedin = clean(row.get("linkedin_url"))
    return {
        "Company Name": account["vendor_company_name"],
        "Company Domain": account.get("domain") or "",
        "Prospect first_name": first,
        "Prospect last_name": last,
        "Prospect full_name": name,
        "Prospect country_name": clean(row.get("person_country")),
        "Prospect city": clean(row.get("person_city")),
        "Prospect linkedin": linkedin,
        "Prospect job_department_main": dept,
        "Prospect job_level_main": level,
        "Prospect job_title": title,
        "Email": email,
        "Email Status": email_tag(email, row.get("email_status")),
        "Mobile Phone": phone,
        PHONE_TAG_COLUMN: phone_tag,
        "data_source": data_source,
        # The same kind of vendor-matched person as every other account's
        # contacts, so the same marker and the same treatment.
        "apollo_matched_contact": name,
        "apollo_match_status": "Shipping list",
        "apollo_title": title,
        "apollo_seniority": level,
        "apollo_department": dept,
        "apollo_verified_work_email": email,
        "apollo_linkedin_url": linkedin,
    }, how


def read_rows(source: Path, sheet: str = SHEET) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    if sheet not in wb.sheetnames:
        sys.exit(f"{source.name} has no '{sheet}' tab (tabs: {', '.join(wb.sheetnames)})")
    rows = wb[sheet].iter_rows(values_only=True)
    head = [clean(h) for h in next(rows, ())]
    out = [dict(zip(head, r)) for r in rows if r and any(c not in (None, "") for c in r)]
    missing = {"account_name", "account_country", "full_name", "email", "email_status",
               "phone", "phone_line_type"} - set(head)
    if missing:
        sys.exit(f"'{sheet}' lacks column(s): {', '.join(sorted(missing))}")
    return out


def match(name: str, country: str, by_folder: dict):
    """The split folder for a file row: its name, else its name plus " - CC"."""
    key = " ".join(name.split()).lower()
    hit = by_folder.get(key)
    if hit is None and country:
        hit = by_folder.get(f"{key} - {country.strip().lower()}")
    return hit


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source", required=True, help="The client's contact workbook.")
    parser.add_argument("--sheet", default=SHEET, help=f"Tab to read (default: {SHEET}).")
    parser.add_argument("--previous", default="",
                        help="Folder of the earlier contacts (<account>/prospect_contacts.csv), "
                             "to restore damaged phone numbers from.")
    parser.add_argument("--base-url", default="", help="Deployed backend (default $HP_BASE_URL).")
    parser.add_argument("--apply", action="store_true", help="Actually upload.")
    parser.add_argument("--regenerate", action="store_true",
                        help="With --apply: submit one run for the uploaded accounts.")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if not source.exists():
        sys.exit(f"{source} not found")
    rows = read_rows(source, args.sheet)
    data_source = f"Client contact file ({source.name} / {args.sheet})"
    previous_dir = Path(args.previous).expanduser() if args.previous else None
    if previous_dir is not None and not previous_dir.is_dir():
        sys.exit(f"--previous {previous_dir} is not a folder")
    previous = read_previous(previous_dir)

    by_folder = folders()
    cols = header()
    if PHONE_TAG_COLUMN not in cols:
        cols.insert(cols.index("Mobile Phone") + 1, PHONE_TAG_COLUMN)

    grouped, unknown = defaultdict(list), Counter()
    for row in rows:
        name, country = clean(row.get("account_name")), clean(row.get("account_country"))
        hit = match(name, country, by_folder)
        if hit is None:
            unknown[f"{name} ({country})"] += 1
            continue
        grouped[clean(hit[1]["name_for_upload"])].append(row)
    if unknown:
        sys.exit("no split folder for: " + "; ".join(f"{k} x{v}" for k, v in unknown.items()))

    # Convert and write. Local only: the upload below is the gated step.
    paths, seen, damaged, restored = {}, Counter(), defaultdict(list), Counter()
    tags = Counter()
    for name, account_rows in sorted(grouped.items()):
        folder, account = by_folder[name.lower()]
        known_here = previous.get(folder.name, {})
        out = []
        for r in account_rows:
            converted, how = convert(r, account, known_here.get(person_key(r.get("full_name")), set()),
                                     data_source)
            out.append(converted)
            tags["email:" + (converted["Email Status"] or "-")] += 1
            tags["phone:" + (converted[PHONE_TAG_COLUMN] or "-")] += 1
            if how == "damaged":
                damaged[name].append(clean(r.get("full_name")))
            elif how == "restored":
                restored[name] += 1
        path = folder / f"{DATASET_KEY}.csv"
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(out)
        paths[name] = path
        seen[name] = len(out)

    print(f"Converted {sum(seen.values())} contacts for {len(seen)} accounts from "
          f"{source.name} / {args.sheet}")
    print("Email tags: " + ", ".join(f"{k[6:]} {v}" for k, v in sorted(tags.items())
                                     if k.startswith("email:")))
    print("Phone tags: " + ", ".join(f"{k[6:]} {v}" for k, v in sorted(tags.items())
                                     if k.startswith("phone:")))
    n_bad = sum(len(v) for v in damaged.values())
    print(f"Phone numbers stored in scientific notation: {sum(restored.values()) + n_bad}. "
          f"Restored from earlier contacts: {sum(restored.values())}. "
          f"Dropped, not shown: {n_bad} in {len(damaged)} accounts"
          + ("" if previous_dir or not n_bad else " (pass --previous to restore what can be)")
          + "\n")

    base_url = (args.base_url or __import__("os").getenv("HP_BASE_URL") or "").rstrip("/")
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
    failed, uploaded, counts = 0, [], Counter()
    for name, path in paths.items():
        acct = on_server.get(name.lower()) or on_server.get(SERVER_NAMES.get(name.lower(), ""))
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
            counts["same"] += 1
            continue
        if not args.apply:
            counts["would upload"] += 1
            print(f"  would up  {seen[name]:4d} contact(s)  {name}"
                  + ("  (replaces the file on the server)" if active else ""))
            continue
        status, body = _api_upload(f"{base_url}/api/v1/accounts/{acct['id']}/data",
                                   token, DATASET_KEY, path)
        if status in (200, 201):
            counts["uploaded"] += 1
            uploaded.append(acct["id"])
            print(f"  uploaded  {seen[name]:4d} contact(s)  {name}")
        else:
            failed += 1
            print(f"  FAILED    {name}  HTTP {status}: {(body or {}).get('detail')}")
    print("\n" + ", ".join(f"{k}: {v}" for k, v in counts.items()) + f", failed: {failed}")

    if not args.apply:
        print("\nDry run. Re-run with --apply to upload.")
    elif args.regenerate and uploaded:
        status, body = _api(f"{base_url}/api/v1/regeneration", token, payload={
            "accounts": uploaded, "include_downstream": True,
            "reason": f"contacts from {source.name}"})
        if status in (200, 201, 202):
            totals = (body or {}).get("totals") or {}
            print(f"\nSubmitted run {(body or {}).get('_id')} for {len(uploaded)} account(s): "
                  f"{totals.get('run', 0)} section(s) to run, "
                  f"{totals.get('skip_current', 0)} already current.")
        else:
            failed += 1
            detail = (body or {}).get("detail") or (body or {}).get("error")
            print(f"\nSubmit FAILED HTTP {status}: {detail} (the super admin's login is needed)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
