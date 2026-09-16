"""Exception handlers.

Four of them, covering every way a request can fail, so that a caller sees one
body shape regardless of which layer raised:

    APIError                -> the code's status, the code's message
    HTTPException           -> unchanged status, wrapped in the envelope
    RequestValidationError  -> 422 with per-field messages
    Exception               -> 500, message withheld, logged in full

Registered in main.py. The request logging middleware still emits the log line
for the request itself; these add the error-specific context.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors.codes import ErrorCode
from app.errors.exceptions import APIError, error_body
from app.observability.context import get_request_id

logger = logging.getLogger(__name__)

# A status with no more specific code. Only consulted for a bare HTTPException
# raised without a code of its own.
_CODE_BY_STATUS = {
    400: ErrorCode.INVALID_PARAMETER,
    401: ErrorCode.UNAUTHENTICATED,
    403: ErrorCode.FORBIDDEN,
    404: ErrorCode.RESOURCE_NOT_FOUND,
    409: ErrorCode.ALREADY_EXISTS,
    413: ErrorCode.FILE_TOO_LARGE,
    415: ErrorCode.UNSUPPORTED_FILE_TYPE,
    422: ErrorCode.VALIDATION_ERROR,
    500: ErrorCode.INTERNAL_ERROR,
    501: ErrorCode.NOT_IMPLEMENTED,
    502: ErrorCode.UPSTREAM_ERROR,
    503: ErrorCode.LLM_UNAVAILABLE,
}


def _json(status: int, body: dict[str, Any], headers: dict[str, str] | None = None):
    merged = {"X-Request-ID": get_request_id()} if get_request_id() else {}
    merged.update(headers or {})
    return JSONResponse(status_code=status, content=body, headers=merged)


async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    """An error the application raised deliberately."""
    # 5xx means the server is at fault and someone should look; 4xx is the
    # caller's doing and routine. Logging both at ERROR is how an alert policy
    # ends up firing on ordinary 404s.
    level = logging.ERROR if exc.status_code >= 500 else logging.INFO
    logger.log(
        level, "%s: %s", exc.code.value, exc.message,
        extra={
            "error_code": exc.code.value,
            "status_code": exc.status_code,
            "path": request.url.path,
            # Developer detail, deliberately kept out of the response body.
            **exc.log_context,
        },
        # A 5xx carries the traceback; a 4xx has nothing to trace.
        exc_info=exc.status_code >= 500,
    )

    return _json(
        exc.status_code,
        error_body(exc.code.value, exc.message, get_request_id(), exc.fields),
        exc.headers,
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """A plain HTTPException, from FastAPI itself or a not-yet-migrated handler.

    Wrapped rather than rejected: there are 79 `raise HTTPException` sites in
    this codebase and they keep working exactly as before, gaining the envelope
    without being rewritten. The `detail` they set stays the user-facing
    message, so no wording changes.
    """
    code = _CODE_BY_STATUS.get(exc.status_code, ErrorCode.INTERNAL_ERROR)

    # detail is normally a string here, but it is typed as Any and FastAPI's
    # own raises sometimes pass a dict or a list.
    detail = exc.detail
    message = detail if isinstance(detail, str) else str(detail)

    if exc.status_code >= 500:
        logger.error("HTTP %s on %s: %s", exc.status_code, request.url.path, message,
                     extra={"status_code": exc.status_code, "error_code": code.value})

    return _json(
        exc.status_code,
        error_body(code.value, message, get_request_id()),
        getattr(exc, "headers", None),
    )


async def validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A request that failed schema validation.

    FastAPI's default body puts a list of error objects in `detail`, which the
    frontend renders as "[object Object]" because it expects a string. This
    turns it into one readable sentence plus a per-field map a form can use.
    """
    fields: dict[str, str] = {}
    for err in exc.errors():
        # loc is ("body", "email") or ("query", "limit"); the first element is
        # the location and the rest is the path to the field.
        parts = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
        name = ".".join(parts) or "request"
        fields[name] = err.get("msg", "This value is not valid.")

    if len(fields) == 1:
        name, why = next(iter(fields.items()))
        message = f"{name}: {why}"
    else:
        message = f"{len(fields)} values were not valid: {', '.join(sorted(fields))}."

    logger.info(
        "Request validation failed on %s", request.url.path,
        extra={"error_code": ErrorCode.VALIDATION_ERROR.value,
               "status_code": 422, "invalid_fields": sorted(fields)},
    )

    return _json(
        422,
        error_body(ErrorCode.VALIDATION_ERROR.value, message, get_request_id(), fields),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Anything that reached the top uncaught.

    The message is withheld on purpose: an exception string can carry a
    connection string, a key or a row of customer data. The caller gets the
    request id instead, which is enough to find the full traceback in the log.
    """
    # LOG004 is suppressed below because ruff only recognises a literal
    # `except:` block. This IS the exception handler - FastAPI invokes it while
    # the exception is being
    # handled, so sys.exc_info() is populated and .exception() attaches the
    # traceback correctly. Downgrading to .error() would silently drop it.
    logger.exception(  # noqa: LOG004
        "Unhandled %s on %s", type(exc).__name__, request.url.path,
        extra={"error_code": ErrorCode.INTERNAL_ERROR.value,
               "status_code": 500,
               "exception_type": type(exc).__name__},
    )

    request_id = get_request_id()
    message = "Something went wrong on our side."
    if request_id:
        message = f"{message} Quote reference {request_id} if you report this."

    return _json(500, error_body(ErrorCode.INTERNAL_ERROR.value, message, request_id))


def register_error_handlers(app: FastAPI) -> None:
    """Install all four. Order does not matter; FastAPI dispatches by type."""
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
