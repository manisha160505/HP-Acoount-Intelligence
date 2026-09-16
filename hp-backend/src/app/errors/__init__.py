"""Application error handling.

Raise `APIError` with a code; the handler turns it into the standard body and
the code decides the HTTP status.

    from app.errors import APIError, ErrorCode

    raise APIError(ErrorCode.ACCOUNT_NOT_FOUND)
    raise APIError(ErrorCode.NO_SOURCE_DATA,
                   log_context={"account_id": account_id})
"""

from app.errors.codes import ErrorCode, message_for, status_for
from app.errors.exceptions import APIError, error_body
from app.errors.handlers import register_error_handlers

__all__ = [
    "APIError",
    "ErrorCode",
    "error_body",
    "message_for",
    "register_error_handlers",
    "status_for",
]
