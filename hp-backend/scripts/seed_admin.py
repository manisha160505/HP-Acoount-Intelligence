# ruff: noqa: T201 - a console script; printing is its output.
"""Create the platform admin, once, from environment variables.

Run from hp-backend:
    ADMIN_EMAIL=... ADMIN_NAME="..." ADMIN_PASSWORD=... python scripts/seed_admin.py

This is the only way to create an admin. `POST /admin/users` always creates
role `user`, so an admin account cannot be minted through the API.

Safe to run again: an existing admin with that email is left untouched (its
password is NOT reset). If the email belongs to a normal user the script stops
rather than silently promoting them - that is a decision for a person to make
in the database, not a side effect of a bootstrap script.
"""

import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.core.security import get_password_hash
from app.database.mongodb import connect_to_mongo, get_db
from app.services.users_admin import ensure_indexes

MIN_PASSWORD_LENGTH = 12


def main() -> int:
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    name = (os.getenv("ADMIN_NAME") or "").strip()
    password = os.getenv("ADMIN_PASSWORD") or ""
    missing = [k for k, v in (("ADMIN_EMAIL", email), ("ADMIN_NAME", name),
                              ("ADMIN_PASSWORD", password)) if not v]
    if missing:
        print("Set %s and run again." % ", ".join(missing), file=sys.stderr)
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print("ADMIN_PASSWORD must be at least %d characters." % MIN_PASSWORD_LENGTH,
              file=sys.stderr)
        return 2

    connect_to_mongo()
    db = get_db()
    ensure_indexes(db)
    existing = db["users"].find_one({"email": email})
    if existing:
        if existing.get("role") == "admin":
            print("Admin %s already exists - nothing to do." % email)
            return 0
        print("%s exists as a %r user. Not promoting it; change the role by hand "
              "if that is intended." % (email, existing.get("role")), file=sys.stderr)
        return 1

    now = datetime.now(UTC)
    db["users"].insert_one({
        "email": email,
        "full_name": name,
        "password_hash": get_password_hash(password),
        "role": "admin",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    })
    print("Created admin %s." % email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
