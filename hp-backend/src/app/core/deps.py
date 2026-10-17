"""Who is calling, and may they.

Every request is authenticated by an access token (see `app.core.security`):
the Bearer header for API calls, or the `hp_access` cookie for the few routes a
browser reaches by a plain link or a page-close beacon, which cannot set a
header. Either way the token's session must still be live and its user active.

A user flagged `must_change_password` - every new account until its first
password change - may only reach the routes that use `get_signed_in_user`
(who am I, change password, sign out). Every other dependency refuses them.

Account access: a seller sees only the accounts listed in their
`account_ids`; admins see every account. Every route with an `{account_id}` in
its path that a seller can reach depends on `require_account_access` (or its
`_flexible` twin), and tests/test_account_access.py fails if one does not.
"""

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Cookie, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_access_token
from app.database.mongodb import get_db
from app.errors import APIError, ErrorCode
from app.services import sessions

ACCESS_COOKIE = "hp_access"

SUPER_ADMIN = "super_admin"
ADMIN = "admin"
USER = "user"
ADMIN_ROLES = frozenset({SUPER_ADMIN, ADMIN})
ALL_ROLES = frozenset({SUPER_ADMIN, ADMIN, USER})

security_bearer = HTTPBearer(auto_error=False)


def is_admin(role: str | None) -> bool:
    return role in ADMIN_ROLES


def _unauthenticated(message: str | None = None) -> APIError:
    return APIError(ErrorCode.UNAUTHENTICATED, message,
                    headers={"WWW-Authenticate": "Bearer"})


def _principal(raw_token: str | None) -> dict:
    if not raw_token:
        raise _unauthenticated()
    claims = decode_access_token(raw_token)
    if not claims:
        raise APIError(ErrorCode.TOKEN_EXPIRED, headers={"WWW-Authenticate": "Bearer"})
    db = get_db()
    user_id, sid = claims["sub"], claims["sid"]
    try:
        user = db["users"].find_one({"_id": ObjectId(user_id)})
    except (InvalidId, TypeError):
        user = None
    if not user:
        raise _unauthenticated()
    # A missing field predates activation and means active.
    if user.get("is_active", True) is False:
        raise _unauthenticated("This account has been deactivated.")
    if not sessions.is_live(db, sid, user_id):
        raise APIError(ErrorCode.TOKEN_EXPIRED, headers={"WWW-Authenticate": "Bearer"})
    return {
        "id": user_id,
        "email": user["email"],
        "full_name": user.get("full_name") or user["email"],
        # From the database, not the token: a demotion applies at once.
        "role": user["role"],
        "session_id": sid,
        "must_change_password": bool(user.get("must_change_password")),
        "account_ids": [str(a) for a in user.get("account_ids") or []],
    }


def _bearer(credentials: HTTPAuthorizationCredentials | None) -> str | None:
    return credentials.credentials if credentials else None


def _ready(user: dict) -> dict:
    if user["must_change_password"]:
        raise APIError(ErrorCode.PASSWORD_CHANGE_REQUIRED)
    return user


def get_signed_in_user(credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer)):
    """Signed in, password change or not. Only for /auth/me, /auth/logout and
    /auth/change-password."""
    return _principal(_bearer(credentials))


def get_current_user(credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer)):
    return _ready(_principal(_bearer(credentials)))


def get_current_user_flexible(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
    hp_access: str | None = Cookie(None),
):
    """`get_current_user`, also accepting the `hp_access` cookie.

    For a PDF opened in a new tab, a download link, or the page-close beacon:
    none can carry a header. The token used to ride in `?token=`, where it was
    written into server logs and browser history.
    """
    return _ready(_principal(_bearer(credentials) or hp_access))


def _role_in(user: dict, roles: frozenset) -> dict:
    if user["role"] not in roles:
        raise APIError(ErrorCode.FORBIDDEN)
    return user


def require_user_role(current_user: dict = Depends(get_current_user)):
    return _role_in(current_user, ALL_ROLES)


def require_user_role_flexible(current_user: dict = Depends(get_current_user_flexible)):
    """`require_user_role`, for a route reached by a plain link.

    `get_current_user_flexible` carries no role check, so on its own it admits
    any authenticated principal whatever their role. A route that serves a
    document needs both.
    """
    return _role_in(current_user, ALL_ROLES)


def require_admin_role(current_user: dict = Depends(get_current_user)):
    return _role_in(current_user, ADMIN_ROLES)


def require_super_admin(current_user: dict = Depends(get_current_user)):
    return _role_in(current_user, frozenset({SUPER_ADMIN}))


def can_see_account(user: dict, account_id: str) -> bool:
    return is_admin(user["role"]) or account_id in user.get("account_ids", ())


def _account_allowed(user: dict, account_id: str) -> dict:
    # Not found rather than forbidden: a seller learns nothing about accounts
    # that are not theirs, not even that the id exists.
    if not can_see_account(user, account_id):
        raise APIError(ErrorCode.ACCOUNT_NOT_FOUND)
    return user


def require_account_access(account_id: str, current_user: dict = Depends(require_user_role)):
    """`require_user_role`, and the `{account_id}` in the path is one of theirs."""
    return _account_allowed(current_user, account_id)


def require_account_access_flexible(account_id: str,
                                    current_user: dict = Depends(require_user_role_flexible)):
    """`require_account_access` for a route reached by a plain link."""
    return _account_allowed(current_user, account_id)
