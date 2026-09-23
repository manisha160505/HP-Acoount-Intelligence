"""Wraps every successful JSON response in the standard envelope.

Done here rather than in each route for one reason: there are 25 endpoints
with a declared `response_model`, and rewriting each to return
`Response[Account]` would mean touching every handler, restating every type,
and losing the generated OpenAPI schema for the payload itself. A handler still
returns `Account`; this puts it in `data`.

The error half is already handled - app.errors.handlers builds the failure
envelope - so this only deals with 2xx.

What is deliberately NOT wrapped:
  - file downloads and streams, which are not JSON
  - /health and /docs, which are read by things that do not know the envelope
  - anything already enveloped, so double-wrapping is impossible
"""

import json
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.observability.context import get_request_id
from app.schemas.envelope import Meta

logger = logging.getLogger(__name__)

# Read by uptime checks, the OpenAPI UI and the schema generator, none of which
# expect the envelope. /health in particular is parsed by the container
# platform, which would treat an unexpected shape as a failed check.
_UNWRAPPED_PATHS = frozenset((
    "/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico",
))


class ResponseEnvelopeMiddleware(BaseHTTPMiddleware):
    """Put a successful JSON body into `data` alongside `success` and `meta`."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # No JSON response from this API may be cached by a browser.
        #
        # Nothing here sets a Cache-Control header, and with none set a browser
        # applies HEURISTIC caching: it may reuse a response for a while without
        # asking again. Every payload here is per-account, authenticated, and
        # changes the moment a widget is regenerated - so a seller who reloads
        # after a rebuild can be served the version they already had, with
        # nothing on screen to say so. That happened: a regenerated
        # Technographic Map kept showing its previous recommendations after a
        # reload, and the data behind it was correct the whole time.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, must-revalidate"

        if request.url.path in _UNWRAPPED_PATHS:
            return response

        # Errors are enveloped by the exception handlers, which also set the
        # error half properly. Re-wrapping here would nest one inside another.
        if response.status_code >= 400:
            return response

        # 204 has no body by definition, and a 304 must not gain one.
        if response.status_code in (204, 304):
            return response

        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("application/json"):
            # A CSV or PDF download. Wrapping it would corrupt the file.
            return response

        body = await _read_body(response)
        if body is None:
            return response

        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Declared JSON but is not. Passed through rather than failing the
            # request - the response was already produced successfully.
            logger.warning(
                "Response on %s declared JSON but did not parse; left unwrapped.",
                request.url.path,
            )
            # Same reconstruction requirement as above: the stream is spent.
            return Response(
                content=body,
                status_code=response.status_code,
                headers=_headers_without_length(response),
                media_type=content_type,
            )

        # Idempotent: a handler that already returned the envelope (or an error
        # body built by the exception handlers) is passed through unchanged.
        #
        # Rebuilt rather than returned as-is: reading the body above consumed
        # the original response's body_iterator, so returning that object now
        # sends a 200 with an EMPTY body. Every early return BELOW the read
        # has to reconstruct for the same reason; the ones above it are safe
        # because they run before the stream is touched.
        if isinstance(payload, dict) and "success" in payload and "meta" in payload:
            return _rebuild(response, payload)

        enveloped = {
            "success": True,
            "data": payload,
            "error": None,
            "meta": Meta(request_id=get_request_id()).model_dump(),
        }

        return JSONResponse(
            content=enveloped,
            status_code=response.status_code,
            headers=_headers_without_length(response),
        )


def _headers_without_length(response: Response) -> dict[str, str]:
    """Every header except content-length.

    The body changes size here, and a stale content-length truncates the
    response at the old length.
    """
    return {
        k: v for k, v in response.headers.items() if k.lower() != "content-length"
    }


def _rebuild(response: Response, payload: object) -> JSONResponse:
    """Re-send an already-enveloped body after its stream has been read."""
    return JSONResponse(
        content=payload,
        status_code=response.status_code,
        headers=_headers_without_length(response),
    )


async def _read_body(response: Response) -> bytes | None:
    """Collect a response body, whether it is buffered or streamed.

    Returns None for a body that cannot be read without consuming a stream the
    caller still needs.
    """
    if hasattr(response, "body"):
        return response.body

    if hasattr(response, "body_iterator"):
        chunks = [chunk async for chunk in response.body_iterator]
        return b"".join(
            c if isinstance(c, bytes) else c.encode("utf-8") for c in chunks
        )

    return None
