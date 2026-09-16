"""Request logging middleware.

The app had no request-level logging at all: an unhandled exception in a route
returned a 500 with nothing in the log identifying which call produced it, and
a slow endpoint was invisible. This emits exactly one record per request with
the method, path, status and latency, tagged with an id that every log line
written while handling that request also carries.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.observability.context import request_id_var
from app.observability.metrics import record_error, record_request

logger = logging.getLogger("app.request")

# Polled by uptime checks and the container platform several times a minute.
# Logging them buries real traffic and, on a per-entry billing model, costs
# more than it tells anyone.
_QUIET_PATHS = frozenset(("/health", "/metrics", "/favicon.ico"))

# Trusted from the caller so a trace survives a hop between services; a fresh
# one is minted when absent. Both spellings are in use by common proxies.
_ID_HEADERS = ("x-request-id", "x-correlation-id")


def _incoming_request_id(request: Request) -> str:
    for header in _ID_HEADERS:
        value = (request.headers.get(header) or "").strip()
        # Bounded: the value is echoed into a response header and into every
        # log line, and an unbounded caller-supplied string is not something to
        # copy into a log store.
        if value and len(value) <= 128:
            return value
    return uuid.uuid4().hex


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Assign a request id, time the call, log the outcome once."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = _incoming_request_id(request)
        token = request_id_var.set(request_id)

        # The matched route template ("/api/v1/accounts/{account_id}") is only
        # known after the router runs, so it is read from the response below;
        # the raw path is what is available here.
        path = request.url.path
        method = request.method
        quiet = path in _QUIET_PATHS

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            route = _route_template(request)
            record_error(type(exc).__name__, route)
            record_request(method, route, 500, duration_ms)
            # The one place an unhandled route exception is guaranteed to be
            # recorded with the request that caused it. Re-raised afterwards so
            # that behaviour is unchanged for anything downstream; the handler
            # registered in main.py is what turns it into the 500 body.
            logger.exception(
                "%s %s failed", method, path,
                extra={
                    "method": method,
                    "path": path,
                    "route": route,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(request),
                },
            )
            # Deliberately NOT reset here. The exception handler registered in
            # main.py runs after this re-raise and reads the id out of this same
            # ContextVar to put it in the 500 body; resetting first left that
            # body carrying an empty id, which is the one case where a user most
            # needs something to quote. The var is request-scoped in an async
            # context, so leaving it set cannot leak into another request.
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        route = _route_template(request)

        # Recorded even for the quiet paths: a health check that starts failing
        # or slowing down is exactly what an alert should catch, and unlike a
        # log line a metric point costs nothing per occurrence.
        record_request(method, route, response.status_code, duration_ms)

        # Lets the browser - and the frontend console logger - quote the exact
        # id to search for, which is what makes a user-reported bug traceable.
        response.headers["X-Request-ID"] = request_id

        if not quiet:
            # A 5xx is the server's fault and a 4xx is usually the caller's;
            # logging both at ERROR makes the alert policy on error rate fire
            # on ordinary 401s and 404s.
            if response.status_code >= 500:
                level = logging.ERROR
            elif response.status_code >= 400:
                level = logging.WARNING
            else:
                level = logging.INFO

            logger.log(
                level, "%s %s %s", method, path, response.status_code,
                extra={
                    "method": method,
                    "path": path,
                    "route": route,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(request),
                },
            )

        request_id_var.reset(token)
        return response


def _route_template(request: Request) -> str:
    """The un-substituted route path, for grouping metrics.

    Without it, every account id becomes its own distinct `path` value and a
    latency chart by path degenerates into one series per account.
    """
    route = request.scope.get("route")
    return getattr(route, "path", "") or request.url.path


def _client_ip(request: Request) -> str:
    """The caller's address, preferring the proxy's forwarded-for entry.

    Only the first entry is taken: the rest of that header is appended by
    intermediate proxies and the leftmost is the original client.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Turn an uncaught exception into a 500 that names the request.

    FastAPI's default returns a bare "Internal Server Error" with no id, so a
    user reporting a failure gives support nothing to search on. The exception
    itself is logged by the middleware above; deliberately not repeated here,
    and deliberately not included in the body - the message can carry a
    connection string or a key.
    """
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
            "request_id": request_id_var.get(),
        },
        headers={"X-Request-ID": request_id_var.get()},
    )
