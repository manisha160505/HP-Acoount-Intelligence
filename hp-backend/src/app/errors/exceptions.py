"""The exception the application raises, and the body it becomes.

One class, `APIError`, carrying a code that determines the status. Raise sites
name the condition rather than picking a number, which is what keeps the same
condition from being a 400 in one handler and a 404 in another.
"""

from typing import Any

from app.errors.codes import ErrorCode, message_for, status_for


class APIError(Exception):
    """An error to report to the caller.

    The handler in `app.errors.handlers` turns this into the standard JSON
    body. `message` is shown to the user, so it must stay free of internal
    detail; anything a developer needs goes in `log_context`, which is logged
    and never serialised.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        status_code: int | None = None,
        fields: dict[str, str] | None = None,
        # Never reaches the response. For the log line only.
        log_context: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message or message_for(code)
        # The code decides the status. The override exists for the handful of
        # cases where the same condition genuinely maps to two statuses, and
        # should be rare enough to notice in review.
        self.status_code = status_code or status_for(code)
        # Per-field messages for a form: {"email": "Enter a valid address."}
        self.fields = fields or {}
        self.log_context = log_context or {}
        self.headers = headers or {}

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"


def error_body(
    code: str,
    message: str,
    request_id: str = "",
    fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    """The failure half of the standard envelope.

        {
          "success": false,
          "data":    null,
          "error":   {"code": "...", "message": "...", "fields": {...}},
          "meta":    {"request_id": "...", "timestamp": "..."},
          "detail":  "..."
        }

    `detail` is the same string as `error.message` and is kept deliberately.
    Sixteen call sites in the frontend read `err.response.data.detail` and
    render it straight into the DOM; those run on the RAW body, because the
    axios success-unwrapping never sees a failed response. Dropping `detail`
    would break all sixteen, so it stays as a top-level alias.

    It also fixes a live bug: FastAPI's own 422 returns `detail` as an ARRAY,
    so those sixteen sites already rendered "[object Object]" on any
    validation failure.
    """
    from datetime import UTC, datetime

    error: dict[str, Any] = {"code": code, "message": message}
    if fields:
        error["fields"] = fields

    return {
        "success": False,
        "data": None,
        "error": error,
        "meta": {
            "request_id": request_id,
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        },
        # Compatibility alias. See the docstring.
        "detail": message,
    }
