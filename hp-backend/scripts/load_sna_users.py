# ruff: noqa: T201 - a console script; printing is its output.
"""Create the client's users from "Bridge AI users FY26 SNA.xlsx".

Two steps, run from hp-backend (on the VM: inside the backend container):

  1. Plan - writes nothing to the database:
       python scripts/load_sna_users.py --sheet "<sheet.xlsx>" --credentials ~/HP_user_credentials.xlsx

     Prints which sheet rows match which accounts, who would be created and
     with which accounts, and writes (or tops up) the credentials workbook with
     a random temporary password for each new person. Run it again as often as
     you like: passwords already in the file are kept.

  2. Apply - creates the users, with the passwords from that same file:
       SUPER_ADMIN_PASSWORD='...' python scripts/load_sna_users.py --sheet "<sheet.xlsx>" \\
           --credentials ~/HP_user_credentials.xlsx --apply --target-db <DB_NAME>

     --target-db must equal the DB_NAME this process is configured with, so a
     shell pointed at the wrong database refuses instead of writing to it.

Safe to run again: an existing user is left as they are (password, role and
accounts), unless --add-accounts, which gives each existing seller the sheet's
accounts they lack and keeps all their others, or --sync-accounts, which sets
each existing seller's accounts to exactly the sheet's (removing any an admin
added since). Prefer --add-accounts on a live site. The super admin (default bridge@gmail.com) is created if
missing, with SUPER_ADMIN_PASSWORD and no forced change; every other new user
must set their own password at first sign-in. No email is sent to anyone.

The credentials workbook holds live passwords: it is refused anywhere inside a
git work tree unless git ignores that path. Keep it out of chats and tickets,
and delete it once everyone has signed in.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, get_db
from app.services import user_import, users_admin


def _git_would_track(path: Path) -> bool:
    folder = path.parent
    try:
        inside = subprocess.run(["git", "-C", str(folder), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return False          # no git here (e.g. the container): nothing could commit it
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False
    ignored = subprocess.run(["git", "-C", str(folder), "check-ignore", "-q", str(path)],
                             check=False)
    return ignored.returncode != 0


def _target() -> str:
    u = urlsplit(settings.MONGODB_URI)
    return "%s/%s" % (u.hostname or settings.MONGODB_URI, settings.DB_NAME)


def _print_plan(plan: user_import.Plan, sheet: user_import.Sheet,
                existing: dict[str, dict]) -> None:
    exact = sum(1 for m in plan.matched if m[2] == "exact")
    aliased = [m for m in plan.matched if m[2] == "alias"]
    print("\nAccounts: %d sheet rows - %d matched exactly, %d through the alias list, %d unmatched"
          % (len(sheet.rows), exact, len(aliased), len(plan.unmatched)))
    for sheet_name, ours, _ in aliased:
        print("  alias      %s  ->  %s" % (sheet_name, ours))
    for name in plan.unmatched:
        print("  UNMATCHED  %s  (its sellers get no account for it)" % name)
    if plan.accounts_not_in_sheet:
        print("  In the database but not in the sheet (admins only): %s"
              % "; ".join(plan.accounts_not_in_sheet))
    for line in sheet.invalid:
        print("  SKIPPED not an email: %s" % line)
    for note in plan.notes:
        print("  note: %s" % note)

    by = {}
    for p in plan.people:
        by.setdefault((p.role, p.status), []).append(p)
    print("\nPeople: %d (%d admins, %d sellers)" % (
        len(plan.people), sum(p.role == "admin" for p in plan.people),
        sum(p.role == "user" for p in plan.people)))
    for (role, status), people in sorted(by.items()):
        print("  %-6s %-13s %d" % (role, status, len(people)))
    for p in plan.people:
        if p.status == "role_differs":
            print("  ROLE DIFFERS %s is %s in the database, %s in the sheet - left as is"
                  % (p.email, p.current_role, p.role))
    none = [p.email for p in plan.people if p.role == "user" and not p.account_ids]
    if none:
        print("  Sellers with no matched account: %s" % ", ".join(none))

    # What --add-accounts would give, and what --sync-accounts would also take
    # away, per existing seller.
    gains, losses = [], []
    for p in plan.people:
        if p.status != "exists" or p.role != "user":
            continue
        have = [str(a) for a in existing[p.email].get("account_ids") or []]
        add = [plan.account_names.get(a, a) for a in p.account_ids if a not in have]
        drop = [plan.account_names.get(a, a) for a in have if a not in p.account_ids]
        if add:
            gains.append("  + %s: %s" % (p.email, ", ".join(add)))
        if drop:
            losses.append("  - %s: %s" % (p.email, ", ".join(drop)))
    print("\nExisting sellers who would gain accounts (--add-accounts or --sync-accounts): %d"
          % len(gains))
    print("\n".join(gains))
    print("Existing sellers who have accounts the sheet does not give them "
          "(kept by --add-accounts, removed by --sync-accounts): %d" % len(losses))
    print("\n".join(losses))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sheet", required=True, help="the client's .xlsx (tabs Sales and Admin)")
    ap.add_argument("--credentials", required=True,
                    help="credentials workbook to write (plan) or read (apply)")
    ap.add_argument("--apply", action="store_true", help="create the users")
    ap.add_argument("--target-db", help="with --apply: must equal the configured DB_NAME")
    ap.add_argument("--super-admin-email", default="bridge@gmail.com")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--sync-accounts", action="store_true",
                      help="set existing sellers' accounts to exactly the sheet's")
    mode.add_argument("--add-accounts", action="store_true",
                      help="give existing sellers the sheet's accounts they lack; remove none")
    args = ap.parse_args()

    cred_path = Path(args.credentials).expanduser().resolve()
    if _git_would_track(cred_path):
        print("Refusing: %s is inside a git work tree and not ignored. Put the credentials "
              "file outside the repository (e.g. ~/HP_user_credentials.xlsx)." % cred_path,
              file=sys.stderr)
        return 2

    connect_to_mongo()
    db = get_db()
    print("Database: %s" % _target())

    sheet = user_import.read_sheet(args.sheet)
    accounts = [{"id": str(a["_id"]), "name": a.get("name") or ""}
                for a in db["accounts"].find({}, {"name": 1})]
    existing = {u["email"]: u for u in db["users"].find(
        {}, {"email": 1, "role": 1, "account_ids": 1})}
    plan = user_import.build_plan(sheet, accounts, existing)
    _print_plan(plan, sheet, existing)

    passwords = user_import.load_credentials(cred_path)
    sa_email = args.super_admin_email.strip().lower()
    sa_line = ("exists" if sa_email in existing else "will be created") + " (%s)" % sa_email

    if not args.apply:
        added = user_import.fill_passwords(plan, passwords)
        user_import.write_credentials(cred_path, plan, passwords)
        cred_path.chmod(0o600)
        print("\nSuper admin: %s" % sa_line)
        print("Credentials: %s - %d password(s) in the file, %d new this run."
              % (cred_path, len(passwords), len(added)))
        print("Nothing was written to the database. Re-run with --apply --target-db %s to create "
              "the users." % settings.DB_NAME)
        return 0

    if args.target_db != settings.DB_NAME:
        print("Refusing: --target-db %r does not match the configured DB_NAME %r (%s)."
              % (args.target_db, settings.DB_NAME, _target()), file=sys.stderr)
        return 2
    if not cred_path.exists():
        print("Refusing: %s does not exist. Run once without --apply to create it." % cred_path,
              file=sys.stderr)
        return 2
    users_admin.ensure_indexes(db)
    try:
        counts = user_import.apply(db, plan, passwords, super_admin_email=sa_email,
                                   super_admin_password=os.getenv("SUPER_ADMIN_PASSWORD"),
                                   sync_accounts=args.sync_accounts,
                                   add_accounts=args.add_accounts)
    except ValueError as exc:
        print("Refusing: %s" % exc, file=sys.stderr)
        return 2
    print("\nDone: super admin created %d, users created %d, existing sellers' accounts updated %d."
          % (counts["super_admin_created"], counts["created"], counts["accounts_synced"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
