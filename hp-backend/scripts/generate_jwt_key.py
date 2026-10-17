# ruff: noqa: T201 - a console script; printing is its output.
"""Print a new ES256 signing key as a line for .env.

Run from hp-backend:
    python scripts/generate_jwt_key.py

Paste the printed JWT_PRIVATE_KEY=... line into the backend's .env (production:
the .env next to docker-compose.prod.yml) and restart. The key is the only thing
that can mint a valid access token, so it never goes in git, a chat or a ticket.

Replacing it signs every access token out at once; browsers then refresh onto
the new key without anyone signing in again. To end the sessions themselves,
use "sign out everyone" (POST /api/v1/auth/sessions/revoke-all).
"""

import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.core.security import generate_private_key_pem


def main() -> int:
    pem = generate_private_key_pem().strip().replace("\n", "\\n")
    print('JWT_PRIVATE_KEY="%s"' % pem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
