"""The single response envelope.

Every endpoint returns this shape, success or failure:

    {
      "success": true,
      "data":    <the payload, shaped by T>,
      "error":   null,
      "meta":    {"request_id": "3f9a...", "timestamp": "2026-09-16T08:00:00Z"}
    }

    {
      "success": false,
      "data":    null,
      "error":   {"code": "ACCOUNT_NOT_FOUND", "message": "...", "fields": {}},
      "meta":    {"request_id": "3f9a...", "timestamp": "..."}
    }

`Response[T]` is the Python equivalent of Go's `Response[T any]`: the generic
parameter types `data`, so FastAPI generates a distinct OpenAPI schema per
endpoint and the frontend's generated types stay precise. `Response[Account]`
and `Response[list[Account]]` are different schemas, not one `Any`.

Success and failure are one class rather than two so a caller has one shape to
handle. `success` is the discriminator - checking it narrows `data` from
`T | None` to `T` in a typed client.
"""

from datetime import UTC, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ErrorDetail(BaseModel):
    """The error half. Null on success."""

    code: str = Field(..., description="Stable machine-readable code, e.g. ACCOUNT_NOT_FOUND.")
    message: str = Field(..., description="Safe to show a user. Never contains internal detail.")
    fields: dict[str, str] | None = Field(
        default=None,
        description="Per-field messages on a validation failure, keyed by field name.",
    )


class Meta(BaseModel):
    """Carried on every response, including successes.

    request_id on a SUCCESS is the point: it makes a slow or wrong-looking
    response traceable, not just a failed one. Without it, a user reporting
    "this number looks wrong" gives support nothing to search on.
    """

    request_id: str = Field(default="", description="Matches the X-Request-ID header.")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC)
        .isoformat()
        .replace("+00:00", "Z"),
        description="When the response was produced, UTC.",
    )


class Response(BaseModel, Generic[T]):
    """The envelope. `Response[Account]`, `Response[list[Widget]]`, `Response[None]`."""

    success: bool = Field(..., description="True when data is populated and error is null.")
    data: T | None = Field(default=None, description="The payload. Null on failure.")
    error: ErrorDetail | None = Field(default=None, description="Null on success.")
    meta: Meta = Field(default_factory=Meta)

    @classmethod
    def ok(cls, data: T, request_id: str = "") -> "Response[T]":
        return cls(success=True, data=data, error=None, meta=Meta(request_id=request_id))

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        request_id: str = "",
        fields: dict[str, str] | None = None,
    ) -> "Response[T]":
        return cls(
            success=False,
            data=None,
            error=ErrorDetail(code=code, message=message, fields=fields),
            meta=Meta(request_id=request_id),
        )
