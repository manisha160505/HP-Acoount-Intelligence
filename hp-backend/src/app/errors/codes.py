"""Stable, machine-readable error codes.

The frontend branches on these rather than string-matching a message, so a
message can be reworded without breaking a caller's logic. The string values
are part of the API contract: add freely, rename never.

Each code carries the HTTP status it is returned with, so a raise site names
the condition and cannot pair it with the wrong status - which is how the same
"not found" ended up as a 400 in some handlers and a 404 in others.
"""

from enum import StrEnum
from http import HTTPStatus


class ErrorCode(StrEnum):
    """A condition the API can report. The value is what the client sees.

    StrEnum rather than `str, Enum`: members compare and serialise as their
    string value, so `code.value` and `str(code)` agree and JSON encoding needs
    no coercion. Requires 3.11, which is what the Dockerfile ships.
    """

    # --- Request shape -----------------------------------------------------
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_ID_FORMAT = "INVALID_ID_FORMAT"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    MISSING_PARAMETER = "MISSING_PARAMETER"

    # --- Authentication and authorisation ----------------------------------
    UNAUTHENTICATED = "UNAUTHENTICATED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    FORBIDDEN = "FORBIDDEN"

    # --- Resources ---------------------------------------------------------
    ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    WIDGET_NOT_FOUND = "WIDGET_NOT_FOUND"
    FEATURE_NOT_FOUND = "FEATURE_NOT_FOUND"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    ALREADY_EXISTS = "ALREADY_EXISTS"

    # --- Uploads -----------------------------------------------------------
    UNSUPPORTED_FILE_TYPE = "UNSUPPORTED_FILE_TYPE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    FILE_PARSE_ERROR = "FILE_PARSE_ERROR"
    DATASET_NOT_RECOGNISED = "DATASET_NOT_RECOGNISED"

    # --- Domain ------------------------------------------------------------
    # The distinction that matters to a seller: a feature with no source data
    # is waiting on an upload, which is actionable. A generation failure is
    # not, and should be retried rather than fixed.
    NO_SOURCE_DATA = "NO_SOURCE_DATA"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    GENERATION_FAILED = "GENERATION_FAILED"
    INDEX_NOT_READY = "INDEX_NOT_READY"

    # --- Upstream and infrastructure ---------------------------------------
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    LLM_NOT_CONFIGURED = "LLM_NOT_CONFIGURED"
    UPSTREAM_ERROR = "UPSTREAM_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


# The HTTP status each code is returned with. Keeping this here rather than at
# the raise site is the point: it is what stops the same condition being a 400
# in one handler and a 404 in another, which is the state the API was in.
STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: HTTPStatus.UNPROCESSABLE_ENTITY,
    ErrorCode.INVALID_ID_FORMAT: HTTPStatus.BAD_REQUEST,
    ErrorCode.INVALID_PARAMETER: HTTPStatus.BAD_REQUEST,
    ErrorCode.MISSING_PARAMETER: HTTPStatus.BAD_REQUEST,

    ErrorCode.UNAUTHENTICATED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.INVALID_CREDENTIALS: HTTPStatus.UNAUTHORIZED,
    ErrorCode.TOKEN_EXPIRED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.FORBIDDEN: HTTPStatus.FORBIDDEN,

    ErrorCode.ACCOUNT_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.USER_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.FILE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.WIDGET_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.FEATURE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.RESOURCE_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.ALREADY_EXISTS: HTTPStatus.CONFLICT,

    ErrorCode.UNSUPPORTED_FILE_TYPE: HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
    ErrorCode.FILE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.FILE_PARSE_ERROR: HTTPStatus.BAD_REQUEST,
    ErrorCode.DATASET_NOT_RECOGNISED: HTTPStatus.BAD_REQUEST,

    # 409, not 400: the request was well-formed and the data is simply not
    # there yet, so the fix is to upload it rather than to change the call.
    ErrorCode.NO_SOURCE_DATA: HTTPStatus.CONFLICT,
    ErrorCode.EXTRACTION_FAILED: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.GENERATION_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.INDEX_NOT_READY: HTTPStatus.CONFLICT,

    ErrorCode.LLM_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.LLM_NOT_CONFIGURED: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.UPSTREAM_ERROR: HTTPStatus.BAD_GATEWAY,
    ErrorCode.DATABASE_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.INTERNAL_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.NOT_IMPLEMENTED: HTTPStatus.NOT_IMPLEMENTED,
}

# Shown when a raise site gives no message of its own. Written for a seller
# reading it in the UI, not for a developer reading a log: it says what is
# wrong and what to do, and never names an internal component.
DEFAULT_MESSAGE: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "Some of the values sent were not valid.",
    ErrorCode.INVALID_ID_FORMAT: "That identifier is not in a valid format.",
    ErrorCode.INVALID_PARAMETER: "One of the values sent was not valid.",
    ErrorCode.MISSING_PARAMETER: "A required value was missing.",

    ErrorCode.UNAUTHENTICATED: "Please sign in to continue.",
    ErrorCode.INVALID_CREDENTIALS: "That email and password combination is not correct.",
    ErrorCode.TOKEN_EXPIRED: "Your session has expired. Please sign in again.",
    ErrorCode.FORBIDDEN: "You do not have access to this.",

    ErrorCode.ACCOUNT_NOT_FOUND: "That account could not be found.",
    ErrorCode.USER_NOT_FOUND: "That user could not be found.",
    ErrorCode.FILE_NOT_FOUND: "That file could not be found.",
    ErrorCode.WIDGET_NOT_FOUND: "That widget could not be found.",
    ErrorCode.FEATURE_NOT_FOUND: "That feature could not be found.",
    ErrorCode.RESOURCE_NOT_FOUND: "That item could not be found.",
    ErrorCode.ALREADY_EXISTS: "That already exists.",

    ErrorCode.UNSUPPORTED_FILE_TYPE: "That file type is not supported.",
    ErrorCode.FILE_TOO_LARGE: "That file is too large to upload.",
    ErrorCode.FILE_PARSE_ERROR: "That file could not be read. Check that it is not corrupted.",
    ErrorCode.DATASET_NOT_RECOGNISED: "That dataset is not one this platform recognises.",

    ErrorCode.NO_SOURCE_DATA: "There is no source data for this feature yet. "
                              "Upload the required dataset and try again.",
    ErrorCode.EXTRACTION_FAILED: "This feature could not be built from the current data.",
    ErrorCode.GENERATION_FAILED: "Generation did not complete. Please try again.",
    ErrorCode.INDEX_NOT_READY: "The search index is still building. Try again shortly.",

    ErrorCode.LLM_UNAVAILABLE: "The AI service is not responding. Please try again shortly.",
    ErrorCode.LLM_NOT_CONFIGURED: "AI generation is not configured on this environment.",
    ErrorCode.UPSTREAM_ERROR: "An upstream service did not respond correctly.",
    ErrorCode.DATABASE_ERROR: "The database could not be reached.",
    ErrorCode.INTERNAL_ERROR: "Something went wrong on our side.",
    ErrorCode.NOT_IMPLEMENTED: "That is not available yet.",
}


def status_for(code: ErrorCode) -> int:
    """The HTTP status for a code. Unmapped codes are a 500, not a crash."""
    return int(STATUS_BY_CODE.get(code, HTTPStatus.INTERNAL_SERVER_ERROR))


def message_for(code: ErrorCode) -> str:
    return DEFAULT_MESSAGE.get(code, "Something went wrong.")
