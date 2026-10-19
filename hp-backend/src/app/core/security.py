"""Passwords and access tokens.

Access tokens are ES256 JWTs: the server signs with a private key held only in
the environment (JWT_PRIVATE_KEY) and verifies with its public half. A token
carries the user, their role at sign-in and the session it belongs to (`sid`);
every request also checks that session is still live, so a token stops working
the moment its session is revoked rather than when it expires.
"""

import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from passlib.context import CryptContext

from app.config.settings import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_ALGORITHM = "ES256"
ACCESS_TOKEN_TYPE = "access"
MIN_PASSWORD_LENGTH = 8


class SigningKeyMissing(RuntimeError):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def password_problem(new_password: str, current_hash: str | None) -> str | None:
    """Why `new_password` is not acceptable, or None when it is.

    At least MIN_PASSWORD_LENGTH characters, and not the password being
    replaced - which at first sign-in is the temporary one an admin handed out,
    so "changing" it to itself would leave a password other people have seen.
    """
    if len(new_password) < MIN_PASSWORD_LENGTH:
        return "Password must be at least %d characters." % MIN_PASSWORD_LENGTH
    if current_hash and verify_password(new_password, current_hash):
        return "New password must be different from your old password."
    return None


# No 0/O, 1/l/I: these are read off a screen or a spreadsheet and typed in.
_TEMP_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def generate_temporary_password(length: int = 12) -> str:
    """A random password for an admin to hand out; the user replaces it at
    first sign-in. Always holds an upper, a lower and a digit."""
    while True:
        pw = "".join(secrets.choice(_TEMP_ALPHABET) for _ in range(length))
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw) \
                and any(c.isdigit() for c in pw):
            return pw


# Recovery codes are read off a screen and typed back: upper case, no 0/O, 1/I/L.
_RECOVERY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_recovery_code() -> str:
    """A one-time code a user saves when they set a password, to set a new one
    themselves if they forget it. 16 characters (about 79 bits), shown as
    XXXX-XXXX-XXXX-XXXX. Stored only as a hash."""
    raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def normalize_recovery_code(code: str) -> str:
    """What is hashed and compared: case and dashes or spaces do not matter."""
    return "".join(ch for ch in (code or "").upper() if ch.isalnum())


def generate_private_key_pem() -> str:
    key = ec.generate_private_key(ec.SECP256R1())
    return key.private_bytes(serialization.Encoding.PEM,
                             serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@lru_cache(maxsize=4)
def _keys(pem: str):
    if not pem.strip():
        raise SigningKeyMissing(
            "JWT_PRIVATE_KEY is not set. Run `python scripts/generate_jwt_key.py` "
            "and put the line it prints in .env.")
    # A .env value is one line; a PEM written there has its newlines as \n.
    private = serialization.load_pem_private_key(pem.replace("\\n", "\n").encode(),
                                                 password=None)
    if not isinstance(private, ec.EllipticCurvePrivateKey) or \
            not isinstance(private.curve, ec.SECP256R1):
        raise SigningKeyMissing("JWT_PRIVATE_KEY must be a P-256 (ES256) EC private key.")
    return private, private.public_key()


def ensure_signing_key() -> None:
    """Raise at startup rather than on the first sign-in."""
    _keys(settings.JWT_PRIVATE_KEY)


def create_access_token(user_id: str, role: str, session_id: str) -> str:
    private, _ = _keys(settings.JWT_PRIVATE_KEY)
    now = datetime.now(UTC)
    claims = {
        "sub": user_id,
        "role": role,
        "sid": session_id,
        "typ": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(claims, private, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """The claims of a valid, unexpired access token, else None."""
    _, public = _keys(settings.JWT_PRIVATE_KEY)
    try:
        claims = jwt.decode(token, public, algorithms=[JWT_ALGORITHM],
                            options={"require": ["exp", "sub", "sid"]})
    except jwt.PyJWTError:
        return None
    return claims if claims.get("typ") == ACCESS_TOKEN_TYPE else None
