# ruff: noqa: T201 - a console script; printing is its output.
"""One-time local setup for sign-in: fills the .env files for a laptop.

Run from hp-backend:
    python scripts/setup_local_env.py

  ../.env and .env      JWT_PRIVATE_KEY (one new ES256 key, the same in both:
                        both files are loaded) and AUTH_COOKIE_SECURE=false.
                        JWT_SECRET, JWT_ALGORITHM and ACCESS_TOKEN_EXPIRE_MINUTES
                        are no longer read; they are commented out, not deleted.
  ../hp-frontend/.env.local
                        NEXT_PUBLIC_API_URL=http://localhost:8000. localhost,
                        not 127.0.0.1: the browser only sends the sign-in
                        cookies to the same site as the page (localhost:3000).

Safe to run again: a key already present is kept, so nobody is signed out.
For local use only - production gets its key from deploy/env.prod.example's
instructions and keeps AUTH_COOKIE_SECURE on.
"""

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.core.security import generate_private_key_pem

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
BACKEND_ENVS = [REPO / ".env", BACKEND / ".env"]
FRONTEND_ENV = REPO / "hp-frontend" / ".env.local"
RETIRED = ("JWT_SECRET", "JWT_ALGORITHM", "ACCESS_TOKEN_EXPIRE_MINUTES")
LOCAL_HOSTS = ("localhost", "127.0.0.1")


def _value(lines: list[str], key: str) -> str | None:
    for line in lines:
        m = re.match(r"\s*%s\s*=\s*(.*)$" % re.escape(key), line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return None


def _set(lines: list[str], key: str, value: str) -> list[str]:
    """`key=value`, replacing an existing line for `key` or appending one."""
    out, done = [], False
    for line in lines:
        if re.match(r"\s*%s\s*=" % re.escape(key), line):
            if not done:
                out.append("%s=%s" % (key, value))
                done = True
            continue
        out.append(line)
    if not done:
        out.append("%s=%s" % (key, value))
    return out


def main() -> int:
    key_line = None
    for path in BACKEND_ENVS:
        if path.exists():
            existing = _value(path.read_text().splitlines(), "JWT_PRIVATE_KEY")
            if existing:
                key_line = existing
                break
    reused = key_line is not None
    if not reused:
        key_line = '"%s"' % generate_private_key_pem().strip().replace("\n", "\\n")
    else:
        key_line = '"%s"' % key_line

    for path in BACKEND_ENVS:
        if not path.exists():
            print("  skip   %s (not found)" % path)
            continue
        lines = path.read_text().splitlines()
        uri = _value(lines, "MONGODB_URI") or ""
        if uri and not any(h in uri for h in LOCAL_HOSTS):
            print("  skip   %s - MONGODB_URI is not local; this script is for laptops only" % path)
            continue
        changed = []
        out = []
        for line in lines:
            if any(re.match(r"\s*%s\s*=" % k, line) for k in RETIRED):
                out.append("# no longer read (ES256 keys replaced it): " + line)
                changed.append(line.split("=", 1)[0].strip() + " commented out")
            else:
                out.append(line)
        if _value(out, "JWT_PRIVATE_KEY") is None:
            out += ["", "# Sign-in: ES256 signing key and local http cookies (scripts/setup_local_env.py)"]
            out = _set(out, "JWT_PRIVATE_KEY", key_line)
            changed.append("JWT_PRIVATE_KEY added")
        if (_value(out, "AUTH_COOKIE_SECURE") or "").lower() != "false":
            out = _set(out, "AUTH_COOKIE_SECURE", "false")
            changed.append("AUTH_COOKIE_SECURE=false")
        if changed:
            path.write_text("\n".join(out) + "\n")
        print("  %-6s %s%s" % ("update" if changed else "ok", path,
                               (": " + ", ".join(changed)) if changed else ""))

    if FRONTEND_ENV.exists():
        lines = FRONTEND_ENV.read_text().splitlines()
        if _value(lines, "NEXT_PUBLIC_API_URL") != "http://localhost:8000":
            FRONTEND_ENV.write_text("\n".join(_set(lines, "NEXT_PUBLIC_API_URL",
                                                   "http://localhost:8000")) + "\n")
            print("  update %s: NEXT_PUBLIC_API_URL=http://localhost:8000" % FRONTEND_ENV)
        else:
            print("  ok     %s" % FRONTEND_ENV)
    else:
        FRONTEND_ENV.write_text("NEXT_PUBLIC_API_URL=http://localhost:8000\n")
        print("  create %s" % FRONTEND_ENV)

    print("Signing key: %s." % ("kept the existing one" if reused else "generated a new one"))
    print("Restart the backend and the frontend dev server to pick these up.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
