"""Tests for structured logging and the request middleware.

What these pin is the log contract rather than any arithmetic. The field names
below are the ones agreed for this service and are consumed by Cloud Logging
queries and alert policies; renaming one silently breaks a dashboard rather
than a test, so the names themselves are asserted, not just their presence.

Three behaviours here were bugs found while building this and are pinned so
they cannot come back: the request id surviving into the 500 response body,
a 4xx logging below ERROR so alerts do not fire on ordinary 401s, and the
health endpoint staying out of the log entirely.

The OpenTelemetry layer is deliberately not tested for span export - that
needs a collector. What is tested is that its absence degrades to working
logs rather than a failed startup.

Run: python -m pytest tests/test_observability.py -v
"""

import json
import logging
import os
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.observability.context import request_id_var
from app.observability.logging import (
    JsonFormatter,
    PlainFormatter,
    configure_logging,
    log_level_from_env,
)
from app.observability.middleware import (
    RequestLoggingMiddleware,
    unhandled_exception_handler,
)

# The agreed contract. Asserted as a set so that adding a field is fine and
# removing or renaming one is not.
REQUIRED_REQUEST_FIELDS = {
    "timestamp", "level", "service", "request_id",
    "method", "path", "status_code", "duration_ms",
}


def _record(name="test", level=logging.INFO, msg="hello", **extra):
    record = logging.LogRecord(name, level, "f.py", 1, msg, (), None)
    for key, value in extra.items():
        setattr(record, key, value)
    return record


def _parse(formatter, record):
    return json.loads(formatter.format(record))


# --- The JSON envelope -----------------------------------------------------

def test_every_required_field_is_present_on_a_request_record():
    formatter = JsonFormatter("hp-backend", "test")
    token = request_id_var.set("rid-1")
    try:
        out = _parse(formatter, _record(
            method="GET", path="/api/v1/accounts", status_code=200, duration_ms=12.5,
        ))
    finally:
        request_id_var.reset(token)

    missing = REQUIRED_REQUEST_FIELDS - out.keys()
    assert not missing, f"log contract lost field(s): {missing}"
    assert out["service"] == "hp-backend"
    assert out["status_code"] == 200
    assert out["duration_ms"] == 12.5


def test_timestamp_is_utc_iso8601():
    # A naive local timestamp is indistinguishable from a UTC one once it
    # reaches a log store, and silently shifts every query by the offset.
    out = _parse(JsonFormatter("s", "test"), _record())
    assert out["timestamp"].endswith("Z")


def test_level_maps_to_a_cloud_logging_severity():
    # Cloud Logging reads `severity`; without it every line is DEFAULT and a
    # severity filter matches nothing.
    out = _parse(JsonFormatter("s", "test"), _record(level=logging.WARNING))
    assert out["level"] == "WARNING"
    assert out["severity"] == "WARNING"


def test_request_id_is_absent_rather_than_empty_outside_a_request():
    # The seeder and the retrieval worker log outside any request. An empty
    # string would make `request_id != ""` the only way to find real request
    # work, which is a trap worth avoiding.
    out = _parse(JsonFormatter("s", "test"), _record())
    assert "request_id" not in out


def test_exception_is_captured_as_a_structured_error_field():
    try:
        raise ValueError("bad id")
    except ValueError:
        record = logging.LogRecord(
            "t", logging.ERROR, "f.py", 1, "failed", (), sys.exc_info()
        )
    out = _parse(JsonFormatter("s", "test"), record)
    assert out["error"]["type"] == "ValueError"
    assert out["error"]["message"] == "bad id"
    assert "ValueError: bad id" in out["error"]["stack_trace"]


def test_a_non_serialisable_extra_does_not_break_the_log_call():
    # A logging call must never be the thing that fails a request. ObjectId and
    # datetime both reach these fields in this codebase.
    class Weird:
        def __repr__(self): return "<weird>"

    out = _parse(JsonFormatter("s", "test"), _record(thing=Weird()))
    assert out["thing"] == "<weird>"


def test_output_is_exactly_one_line():
    # A multi-line record is ingested as several unparseable entries.
    try:
        raise RuntimeError("multi\nline")
    except RuntimeError:
        record = logging.LogRecord(
            "t", logging.ERROR, "f.py", 1, "boom", (), sys.exc_info()
        )
    assert "\n" not in JsonFormatter("s", "test").format(record)


def test_cloud_trace_fields_only_appear_when_a_project_is_set():
    # Emitting projects//traces/... with an empty id would be worse than
    # omitting the field.
    out = _parse(JsonFormatter("s", "test", project_id=""), _record())
    assert "logging.googleapis.com/trace" not in out


# --- Level configuration ---------------------------------------------------

def test_log_level_comes_from_the_environment():
    os.environ["LOG_LEVEL"] = "debug"
    try:
        assert log_level_from_env() == "DEBUG"
    finally:
        del os.environ["LOG_LEVEL"]


def test_an_unknown_log_level_falls_back_instead_of_raising():
    # A typo in an env var should not stop the service from starting.
    os.environ["LOG_LEVEL"] = "LOUD"
    try:
        assert log_level_from_env("INFO") == "INFO"
    finally:
        del os.environ["LOG_LEVEL"]


def test_configure_logging_replaces_handlers_rather_than_stacking_them():
    # Called twice - as happens under uvicorn's reloader - this must not
    # double every line.
    configure_logging(level="INFO", log_format="json")
    configure_logging(level="INFO", log_format="json")
    assert len(logging.getLogger().handlers) == 1


def test_plain_format_stays_human_readable():
    out = PlainFormatter().format(_record(msg="ready"))
    assert "ready" in out
    assert not out.startswith("{")


# --- The middleware --------------------------------------------------------

@pytest.fixture
def client_and_logs(caplog):
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/health")
    def health(): return {"status": "ok"}

    @app.get("/api/v1/accounts/{account_id}")
    def account(account_id: str): return {"id": account_id}

    @app.get("/boom")
    def boom(): raise ValueError("exploded")

    @app.get("/missing")
    def missing(): raise HTTPException(status_code=404, detail="nope")

    return TestClient(app, raise_server_exceptions=False), caplog


def test_every_response_carries_a_request_id_header(client_and_logs):
    client, _ = client_and_logs
    assert client.get("/health").headers.get("X-Request-ID")


def test_a_caller_supplied_request_id_is_honoured(client_and_logs):
    # What makes a trace survive a hop between services.
    client, _ = client_and_logs
    response = client.get("/health", headers={"X-Request-ID": "upstream-id"})
    assert response.headers["X-Request-ID"] == "upstream-id"


def test_an_absurdly_long_caller_id_is_rejected(client_and_logs):
    # The value is copied into every log line; an unbounded caller-supplied
    # string is not something to write to a log store.
    client, _ = client_and_logs
    response = client.get("/health", headers={"X-Request-ID": "x" * 500})
    assert response.headers["X-Request-ID"] != "x" * 500


def test_the_health_endpoint_is_not_logged(client_and_logs):
    # Polled several times a minute by uptime checks; logging it buries real
    # traffic and costs money per entry.
    client, caplog = client_and_logs
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/health")
    assert not [r for r in caplog.records if r.name == "app.request"]


def test_a_served_request_logs_once_with_method_status_and_duration(client_and_logs):
    client, caplog = client_and_logs
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/v1/accounts/abc")

    records = [r for r in caplog.records if r.name == "app.request"]
    assert len(records) == 1
    assert records[0].method == "GET"
    assert records[0].status_code == 200
    assert records[0].duration_ms >= 0


def test_the_route_template_is_logged_not_the_substituted_path(client_and_logs):
    # Without this, every account id is its own series and a latency chart
    # by route degenerates into one line per account.
    client, caplog = client_and_logs
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/v1/accounts/68f1a2b3c4d5e6f7")

    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.route == "/api/v1/accounts/{account_id}"
    assert record.path == "/api/v1/accounts/68f1a2b3c4d5e6f7"


def test_a_4xx_logs_below_error(client_and_logs):
    # A 404 or a 401 is the caller's doing and routine. Logging it at ERROR
    # makes an error-rate alert fire on every expired session.
    client, caplog = client_and_logs
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/missing")

    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.levelno == logging.WARNING


def test_a_5xx_logs_at_error_with_the_traceback(client_and_logs):
    client, caplog = client_and_logs
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/boom")

    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.levelno == logging.ERROR
    assert record.status_code == 500
    assert record.exc_info is not None


def test_the_500_body_carries_the_same_request_id_as_the_header(client_and_logs):
    # Regression: the ContextVar was reset before the re-raise, so the handler
    # read an empty id and returned a body with nothing to search on - in the
    # one case where a user most needs something to quote.
    client, _ = client_and_logs
    response = client.get("/boom")
    assert response.status_code == 500
    body_id = response.json()["request_id"]
    assert body_id
    assert body_id == response.headers["X-Request-ID"]


def test_the_500_body_does_not_leak_the_exception_message(client_and_logs):
    # An exception message can carry a connection string or a key.
    client, _ = client_and_logs
    assert "exploded" not in client.get("/boom").text


def test_each_request_gets_a_distinct_id(client_and_logs):
    client, _ = client_and_logs
    first = client.get("/health").headers["X-Request-ID"]
    second = client.get("/health").headers["X-Request-ID"]
    assert first != second


def test_the_request_id_does_not_leak_between_requests(client_and_logs):
    # The ContextVar is intentionally left set through the exception path (so
    # the handler can read it), so this pins that it still does not bleed into
    # the next request.
    client, caplog = client_and_logs
    failed_id = client.get("/boom").json()["request_id"]

    # caplog accumulates across calls within a test, so the records from the
    # failing request above are cleared rather than indexed past.
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/v1/accounts/x")

    record = next(r for r in caplog.records if r.name == "app.request")
    assert record.status_code == 200
    assert response.headers["X-Request-ID"] != failed_id


# --- Graceful degradation --------------------------------------------------

def test_tracing_and_metrics_report_off_rather_than_raising():
    # The whole optional-dependency design rests on this: a developer without
    # the extras installed gets a working app, not an ImportError at startup.
    from app.observability.metrics import configure_metrics, record_request
    from app.observability.tracing import configure_tracing

    # No project and no OTLP endpoint - nothing to export to.
    assert configure_metrics("svc", otlp_endpoint="", project_id="") is False
    # Recording against disabled metrics must be a silent no-op.
    record_request("GET", "/x", 200, 1.0)

    assert configure_tracing("svc", project_id="", otlp_endpoint="") in (True, False)
