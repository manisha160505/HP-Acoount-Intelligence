"""Structured JSON logging.

The app previously logged `LEVELNAME [name] message` to stderr. That is
readable at a terminal and close to useless in a log store: the request, the
status and the latency of a call were spread across separate lines with
nothing joining them, and an exception arrived as an untagged multi-line
traceback.

Every record now serialises to one JSON object on one line, carrying the
fields agreed for this service:

    timestamp level service request_id method path status_code duration_ms error

Request-scoped fields are absent on records emitted outside a request (the
seeder, the retrieval worker) rather than emitted empty, so a query for
`request_id` matches only real request work.

Google Cloud Logging is addressed by naming the fields the way it already
understands: `severity` rather than `level`, and the trace fields under the
`logging.googleapis.com/*` keys. A JSON line on stdout is then parsed into a
structured entry by the platform's built-in agent with no sidecar - which is
why the Cloud Logging client library is optional here rather than required.
"""

import json
import logging
import os
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from app.observability.context import get_request_id

# Attributes LogRecord always carries. Anything on a record that is not in this
# set was attached by the caller via `extra=` and belongs in the JSON output -
# that is what lets a call site add a field without touching the formatter.
_RESERVED = frozenset((
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs",
    "message", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
))

# Python level names to the severities Cloud Logging recognises. WARNING and
# the rest coincide; only the two ends differ.
_SEVERITY = {
    "DEBUG": "DEBUG",
    "INFO": "INFO",
    "WARNING": "WARNING",
    "ERROR": "ERROR",
    "CRITICAL": "CRITICAL",
}


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a single-line JSON object.

    `service` is stamped on every record so logs from the backend, the worker
    and any future service stay distinguishable once they share a log store.
    """

    def __init__(self, service: str, environment: str, project_id: str = "") -> None:
        super().__init__()
        self.service = service
        self.environment = environment
        self.project_id = project_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            # Explicit UTC with a real timezone, not naive local time: the
            # container's clock is UTC but a developer's laptop is not, and a
            # log store cannot tell the difference from an unsuffixed string.
            "timestamp": datetime.fromtimestamp(
                record.created, tz=UTC
            ).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            # Cloud Logging reads this one; `level` above stays for anything
            # that does not.
            "severity": _SEVERITY.get(record.levelname, "DEFAULT"),
            "service": self.service,
            "environment": self.environment,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = get_request_id()
        if request_id:
            payload["request_id"] = request_id

        # Correlate a log line with its span in Cloud Trace. Imported lazily so
        # that logging keeps working when OpenTelemetry is not installed.
        trace_id, span_id = _current_trace_context()
        if trace_id:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id
            if self.project_id:
                payload["logging.googleapis.com/trace"] = (
                    f"projects/{self.project_id}/traces/{trace_id}"
                )
                payload["logging.googleapis.com/spanId"] = span_id

        # Fields passed by the caller as `extra=` - method, path, status_code,
        # duration_ms on the request-completion record, and whatever a feature
        # chooses to attach elsewhere.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            payload["error"] = {
                "type": exc_type.__name__ if exc_type else "UnknownError",
                "message": str(exc_value),
                "stack_trace": "".join(
                    traceback.format_exception(exc_type, exc_value, exc_tb)
                ),
            }

        # `default=str` rather than letting a non-serialisable value raise:
        # a log call must never be the thing that breaks a request. ObjectId
        # and datetime are both common in this codebase's extra fields.
        return json.dumps(payload, default=str, ensure_ascii=False)


def _current_trace_context() -> tuple[str, str]:
    """The active OTel trace and span ids as hex, or ("", "") if untraced."""
    try:
        from opentelemetry import trace
    except ImportError:
        return "", ""

    span = trace.get_current_span()
    ctx = span.get_span_context()
    if not ctx.is_valid:
        return "", ""
    return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")


class PlainFormatter(logging.Formatter):
    """Human-readable output for local development.

    Keeps the request id visible - it is the thing that makes a local log
    useful when several browser tabs are hitting the API at once - but drops
    the JSON envelope, which is unreadable in a terminal.
    """

    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.levelname:<8} [{record.name}] {record.getMessage()}"

        request_id = get_request_id()
        if request_id:
            base = f"{record.levelname:<8} [{record.name}] ({request_id[:8]}) {record.getMessage()}"

        # Surface the request-completion fields inline; without them the
        # plain format would hide the status and latency the JSON one shows.
        status = getattr(record, "status_code", None)
        duration = getattr(record, "duration_ms", None)
        if status is not None and duration is not None:
            base = f"{base} [{status} in {duration}ms]"

        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def configure_logging(
    level: str = "INFO",
    log_format: str = "json",
    service: str = "hp-backend",
    environment: str = "development",
    project_id: str = "",
) -> None:
    """Install the chosen formatter on the root logger.

    Replaces the root handlers rather than adding to them, so calling this
    after something else (uvicorn, a library, a previous call) has configured
    logging does not double every line.
    """
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # stdout, not stderr: on Cloud Run and GKE, stderr is flagged as an error
    # regardless of the record's own severity, which would turn every INFO
    # line into an alert-worthy entry.
    handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        handler.setFormatter(JsonFormatter(service, environment, project_id))
    else:
        handler.setFormatter(PlainFormatter())
    root.addHandler(handler)

    # Uvicorn installs its own handlers and marks its loggers non-propagating,
    # so without this its lines bypass the formatter above and arrive as
    # unstructured text among the JSON. Its access log is silenced outright -
    # the request middleware emits the same information with the request id,
    # the duration and the route attached, and two lines per request in a log
    # store is one too many.
    for name in ("uvicorn", "uvicorn.error"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        uv.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers.clear()
    access.propagate = False
    access.disabled = True

    # Chatty at INFO and none of it actionable: pymongo logs every server
    # heartbeat, httpx a line per outbound call.
    # "httpx2" as well as "httpx": the vendored client some installs ship
    # under registers its logger under that name and is just as chatty.
    for noisy in ("pymongo", "httpx", "httpx2", "httpcore", "urllib3",
                  "openai._base_client"):
        logging.getLogger(noisy).setLevel(
            max(logging.WARNING, logging.getLogger().level)
        )


def log_level_from_env(default: str = "INFO") -> str:
    """LOG_LEVEL, validated. An unknown value falls back rather than raising."""
    candidate = (os.getenv("LOG_LEVEL") or default).strip().upper()
    return candidate if candidate in _SEVERITY else default
