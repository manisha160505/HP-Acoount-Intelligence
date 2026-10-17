from typing import Literal

from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials

from app.config.settings import settings
from app.core.deps import (
    ACCESS_COOKIE,
    get_current_user,
    get_signed_in_user,
    require_super_admin,
    security_bearer,
)
from app.core.security import decode_access_token
from app.database.mongodb import get_db
from app.schemas.auth import MessageResponse
from app.schemas.user import (
    ChangePasswordRequest,
    TokenResponse,
    TourCompletedResponse,
    UserLogin,
    UserResponse,
)
from app.services import auth as auth_service, sessions, user_audit

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE = "hp_refresh"
# Sent only to the auth routes: nothing else has any use for it.
REFRESH_COOKIE_PATH = "/api/v1/auth"
# Sent to every API route, accepted only where a header cannot be set (a PDF
# link, a download, the page-close beacon); see get_current_user_flexible.
ACCESS_COOKIE_PATH = "/api/v1"


def _cookie(response: Response, name: str, value: str, path: str, max_age: int) -> None:
    response.set_cookie(name, value, max_age=max_age, path=path, httponly=True,
                        secure=settings.AUTH_COOKIE_SECURE, samesite="strict")


def _set_session_cookies(response: Response, body: TokenResponse, refresh_token: str | None):
    _cookie(response, ACCESS_COOKIE, body.access_token, ACCESS_COOKIE_PATH, body.expires_in)
    if refresh_token:
        _cookie(response, REFRESH_COOKIE, refresh_token, REFRESH_COOKIE_PATH,
                settings.SESSION_IDLE_DAYS * 86400)


def _clear_session_cookies(response: Response) -> None:
    for name, path in ((ACCESS_COOKIE, ACCESS_COOKIE_PATH), (REFRESH_COOKIE, REFRESH_COOKIE_PATH)):
        response.delete_cookie(name, path=path, httponly=True,
                               secure=settings.AUTH_COOKIE_SECURE, samesite="strict")


@router.post("/login", response_model=TokenResponse)
def login(login_data: UserLogin, request: Request, response: Response):
    body, refresh_token = auth_service.authenticate_user(
        login_data, request.headers.get("user-agent", ""))
    _set_session_cookies(response, body, refresh_token)
    return body


@router.post("/refresh", response_model=TokenResponse)
def refresh(response: Response, hp_refresh: str | None = Cookie(None)):
    """A fresh access token from the refresh cookie. Also how a reloaded page
    learns who is signed in: the access token lives only in memory. A dead
    cookie is left to expire: its session is already revoked server-side."""
    body, new_refresh = auth_service.refresh_session(hp_refresh)
    _set_session_cookies(response, body, new_refresh)
    return body


@router.get("/me", response_model=UserResponse)
def get_me(current_user: dict = Depends(get_signed_in_user)):
    return current_user


@router.post("/me/tour-completed", response_model=TourCompletedResponse)
def tour_completed(tour: Literal["dashboard", "admin"] = "dashboard",
                   current_user: dict = Depends(get_current_user)):
    """A product tour - the dashboard's, or the admin pages' with ?tour=admin -
    has been finished or closed: do not start it again on any device. Safe to
    call more than once."""
    return TourCompletedResponse(
        tour=tour, tour_completed_at=auth_service.mark_tour_completed(current_user, tour))


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response,
           credentials: HTTPAuthorizationCredentials | None = Depends(security_bearer),
           hp_refresh: str | None = Cookie(None)):
    """Ends this browser's session. Needs no valid access token: signing out
    with an expired one must still end the session behind the cookie."""
    claims = decode_access_token(credentials.credentials) if credentials else None
    auth_service.logout(claims["sid"] if claims else None, hp_refresh)
    _clear_session_cookies(response)
    return MessageResponse(message="Successfully logged out.")


@router.post("/change-password", response_model=MessageResponse)
def change_password(body: ChangePasswordRequest, response: Response,
                    current_user: dict = Depends(get_signed_in_user)):
    auth_service.change_password(current_user, body)
    _clear_session_cookies(response)
    return MessageResponse(message="Password changed. Please sign in with your new password.")


@router.post("/sessions/revoke-all", response_model=MessageResponse)
def sign_out_everyone(current_user: dict = Depends(require_super_admin)):
    """Super admin only: end every session but the caller's own."""
    db = get_db()
    count = sessions.revoke_everyone(db, "signed out by super admin %s" % current_user["id"],
                                     keep_sid=current_user["session_id"])
    user_audit.record(db, current_user, user_audit.SESSIONS_REVOKED_ALL, None, {"sessions": count})
    return MessageResponse(message="Signed out %d session(s)." % count)
