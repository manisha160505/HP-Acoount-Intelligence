# ruff: noqa: T201 - a console script; printing is its output.
"""Dummy users for trying user management on a laptop. Local databases only.

Run from hp-backend:
    python scripts/seed_local_test_users.py

Creates (skipping any email that already exists):
    bridge@gmail.com           super admin, no forced change (LOCAL_SUPER_ADMIN_PASSWORD,
                               default TEST_PASSWORD)
    test.admin@example.com     admin - every account
    seller.astra@example.com   seller - Astra
    seller.japan@example.com   seller - ADVANTEST, SONY
    seller.multi@example.com   seller - Astra, ACCENTURE, SONY
    seller.none@example.com    seller - no accounts ("no accounts assigned" screen)

Everyone but the super admin signs in with TEST_PASSWORD and is sent to set a
new password first. The real super admin password never goes in this file: the
repository is public. Refuses to run unless MONGODB_URI points at this machine:
these passwords are in the source on purpose and must never reach a shared
database.
"""

import os
import sys
from datetime import UTC, datetime
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.config.settings import settings
from app.core.security import get_password_hash
from app.database.mongodb import connect_to_mongo, get_db
from app.services import users_admin

TEST_PASSWORD = "Test@12345"
SUPER_ADMIN_PASSWORD = os.getenv("LOCAL_SUPER_ADMIN_PASSWORD") or TEST_PASSWORD

# email -> (role, account names as stored locally)
USERS = {
    "test.admin@example.com": ("admin", []),
    "seller.astra@example.com": ("user", ["Astra"]),
    "seller.japan@example.com": ("user", ["ADVANTEST CORPORATION - JP", "SONY CORPORATION - JP"]),
    "seller.multi@example.com": ("user", ["Astra", "ACCENTURE INC - PH", "SONY CORPORATION - JP"]),
    "seller.none@example.com": ("user", []),
}


def main() -> int:
    host = urlsplit(settings.MONGODB_URI).hostname
    if host not in ("localhost", "127.0.0.1", "::1"):
        print("Refusing: MONGODB_URI points at %r, not this machine." % host, file=sys.stderr)
        return 2
    connect_to_mongo()
    db = get_db()
    users_admin.ensure_indexes(db)
    ids = {a["name"]: str(a["_id"]) for a in db["accounts"].find({}, {"name": 1})}
    now = datetime.now(UTC)
    print("Database: %s/%s" % (host, settings.DB_NAME))

    def create(email, role, account_names, password, must_change):
        if db["users"].find_one({"email": email}):
            print("  exists   %s" % email)
            return
        missing = [n for n in account_names if n not in ids]
        if missing:
            print("  skipped  %s - no local account named %s" % (email, missing))
            return
        db["users"].insert_one({
            "email": email, "full_name": email, "role": role,
            "password_hash": get_password_hash(password),
            "account_ids": [ids[n] for n in account_names], "is_active": True,
            "must_change_password": must_change, "created_at": now,
            "created_by": "seed_local_test_users", "last_login_at": None,
        })
        print("  created  %-28s %-11s %s" % (email, role, ", ".join(account_names) or "-"))

    create("bridge@gmail.com", "super_admin", [], SUPER_ADMIN_PASSWORD, False)
    for email, (role, names) in USERS.items():
        create(email, role, names, TEST_PASSWORD, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
