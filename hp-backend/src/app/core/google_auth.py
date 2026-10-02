"""Vertex AI without an API key: an OAuth token from Application Default
Credentials (2 Oct).

The GCP organisation that owns the project blocks API keys bound to service
accounts (iam.managed.disableServiceAccountApiKeyCreation), so on the VM the
backend authenticates as the VM's own service account and on a laptop as the
developer (`gcloud auth application-default login`). Used when
LLM_PROVIDER=vertex and GEMINI_API_KEY is empty; an express-mode key, when set,
still goes in x-goog-api-key exactly as before.
"""

import logging
import threading

logger = logging.getLogger(__name__)

SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

_lock = threading.Lock()
_credentials = None


class GoogleAuthError(RuntimeError):
    """No usable Application Default Credentials on this host."""


def access_token() -> str:
    """A valid OAuth access token, refreshed shortly before it expires.

    Tokens last an hour; google-auth reports one as invalid a few minutes early,
    so a long run never sends an expired one. Safe to call before every request:
    a still-valid token is returned without a network call."""
    global _credentials
    with _lock:
        if _credentials is None:
            import google.auth
            from google.auth.exceptions import DefaultCredentialsError

            try:
                _credentials, _ = google.auth.default(scopes=list(SCOPES))
            except DefaultCredentialsError as exc:
                raise GoogleAuthError(
                    "No Google credentials for Vertex AI: set GEMINI_API_KEY, or run "
                    "`gcloud auth application-default login` (laptop) / give the VM a "
                    "service account with the cloud-platform scope.") from exc
        if not _credentials.valid:
            import google.auth.transport.requests

            _credentials.refresh(google.auth.transport.requests.Request())
        return _credentials.token


def vertex_headers(api_key: str) -> dict:
    """Auth headers for a direct Vertex AI request: the express key when one is
    set, otherwise a bearer token. Never a ?key= query - a URL ends up in error
    messages and so in the logs."""
    if api_key:
        return {"x-goog-api-key": api_key}
    return {"Authorization": "Bearer %s" % access_token()}
