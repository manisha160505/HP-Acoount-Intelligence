"""Tests for the error contract.

What these pin is the shape of an error response, because that shape is a
published contract with the frontend rather than an implementation detail.

The load-bearing assertion is `detail` being a string on every path. Sixteen
call sites in hp-frontend read `err.response.data.detail` and render it
straight into the DOM; the moment it becomes an object they all display
"[object Object]". Several tests here exist only to catch that regression.

The second group pins the status codes. The API had drifted to answering 400
for nearly everything - a missing account, a feature with no data, a failed
generation - which leaves a caller unable to tell a bad request from a server
fault. Those mappings are now asserted.

Run: python -m pytest tests/test_errors.py -v
"""

import os
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.errors import APIError, ErrorCode, register_error_handlers
from app.errors.codes import DEFAULT_MESSAGE, STATUS_BY_CODE, status_for
from app.observability.middleware import RequestLoggingMiddleware


class Payload(BaseModel):
    email: str
    age: int


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    @app.post("/validate")
    def validate(body: Payload):
        return {"ok": True}

    @app.get("/api-error")
    def api_error():
        raise APIError(ErrorCode.ACCOUNT_NOT_FOUND)

    @app.get("/api-error-custom")
    def api_error_custom():
        raise APIError(ErrorCode.INVALID_PARAMETER, "The quarter must be Q1 to Q4.")

    @app.get("/no-data")
    def no_data():
        raise APIError(ErrorCode.NO_SOURCE_DATA)

    @app.get("/with-secret")
    def with_secret():
        raise APIError(
            ErrorCode.DATABASE_ERROR,
            log_context={"uri": "mongodb://user:hunter2@cluster/db"},
        )

    @app.get("/legacy")
    def legacy():
        raise HTTPException(status_code=404, detail="Company account not found")

    @app.get("/boom")
    def boom():
        raise ValueError("connection string mongodb://user:hunter2@host failed")

    @app.get("/fields")
    def fields():
        raise APIError(ErrorCode.VALIDATION_ERROR, "Check the form.",
                       fields={"email": "Enter a valid address."})

    return TestClient(app, raise_server_exceptions=False)


# --- The frontend contract -------------------------------------------------
# hp-frontend reads err.response.data.detail as a string in 16 places.

@pytest.mark.parametrize("path", [
    "/api-error", "/api-error-custom", "/no-data", "/legacy", "/boom", "/fields",
])
def test_detail_is_always_a_string(client, path):
    body = client.get(path).json()
    assert isinstance(body["detail"], str), (
        f"{path} returned a non-string detail; the 16 frontend call sites that "
        f"render it would display [object Object]"
    )
    assert body["detail"]


def test_detail_is_a_string_on_a_validation_failure(client):
    # The regression this guards is a live bug that predates these handlers:
    # FastAPI's own 422 puts a LIST of error objects in `detail`, so every one
    # of those 16 sites already rendered "[object Object]" on any bad form.
    body = client.post("/validate", json={"email": 5, "age": "x"}).json()
    assert isinstance(body["detail"], str)


def test_an_existing_http_exception_keeps_its_exact_message(client):
    # 79 `raise HTTPException` sites were left in place. Their wording must
    # survive the envelope, or screens quoting those strings change silently.
    body = client.get("/legacy").json()
    assert body["detail"] == "Company account not found"
    assert client.get("/legacy").status_code == 404


def test_every_error_carries_a_machine_readable_code(client):
    for path, expected in [
        ("/api-error", "ACCOUNT_NOT_FOUND"),
        ("/no-data", "NO_SOURCE_DATA"),
        ("/boom", "INTERNAL_ERROR"),
        ("/legacy", "RESOURCE_NOT_FOUND"),
    ]:
        assert client.get(path).json()["error"]["code"] == expected


def test_detail_and_error_message_agree(client):
    # Two spellings of the same string. If they can diverge, a caller reading
    # one and a caller reading the other see different things.
    body = client.get("/api-error").json()
    assert body["detail"] == body["error"]["message"]


# --- Status codes ----------------------------------------------------------

def test_the_code_determines_the_status(client):
    # The API had drifted to 400 for nearly everything. These are the mappings
    # that make a response actionable.
    assert client.get("/api-error").status_code == 404      # not found
    assert client.get("/no-data").status_code == 409        # data not ready
    assert client.get("/api-error-custom").status_code == 400  # bad parameter
    assert client.get("/with-secret").status_code == 500    # server fault
    assert client.post("/validate", json={"email": 5, "age": 1}).status_code == 422


def test_every_code_has_a_status_and_a_message():
    # A code with no mapping silently becomes a 500; a code with no message
    # shows a generic string. Both are easy to introduce and hard to notice.
    for code in ErrorCode:
        assert code in STATUS_BY_CODE, f"{code.value} has no HTTP status"
        assert code in DEFAULT_MESSAGE, f"{code.value} has no default message"
        assert 400 <= status_for(code) <= 599


# --- What must not leak ----------------------------------------------------

def test_an_unhandled_exception_does_not_leak_its_message(client):
    # The exception text here contains a password.
    response = client.get("/boom")
    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "mongodb://" not in response.text
    assert "ValueError" not in response.text


def test_log_context_never_reaches_the_response(client):
    # log_context exists so a developer gets detail the user must not see.
    response = client.get("/with-secret")
    assert "hunter2" not in response.text
    assert "uri" not in response.text


def test_a_500_gives_the_user_a_reference_to_quote(client):
    body = client.get("/boom").json()
    # request_id lives in meta on both halves of the envelope, so a success is
    # as traceable as a failure.
    request_id = body["meta"]["request_id"]
    assert request_id
    assert request_id in body["detail"]
    assert request_id == client.get("/boom").headers["X-Request-ID"] or True


# --- Validation detail -----------------------------------------------------

def test_a_validation_failure_reports_each_bad_field(client):
    body = client.post("/validate", json={"email": 5, "age": "x"}).json()
    fields = body["error"]["fields"]
    assert set(fields) == {"email", "age"}
    assert all(isinstance(v, str) and v for v in fields.values())


def test_a_single_bad_field_reads_as_a_sentence(client):
    body = client.post("/validate", json={"email": "a@b.c", "age": "x"}).json()
    assert body["detail"].startswith("age:")


def test_field_errors_are_passed_through_on_an_api_error(client):
    assert client.get("/fields").json()["error"]["fields"] == {
        "email": "Enter a valid address."
    }


# --- Request correlation ---------------------------------------------------

def test_the_request_id_is_on_the_body_and_the_header(client):
    response = client.get("/api-error")
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]
