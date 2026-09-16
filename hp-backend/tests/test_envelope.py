"""Tests for the response envelope.

Every endpoint returns {success, data, error, meta}. What these pin is the
contract the frontend depends on, because the frontend does NOT read the
envelope directly - the axios interceptor unwraps `data` before any screen
sees it, so a change in this shape breaks 33 call sites silently rather than
loudly.

The three properties that matter:
  - a success puts the handler's payload in `data`, unchanged
  - a failure puts a code in `error` and leaves `data` null
  - `meta.request_id` is present on BOTH, so a success is traceable too

The paths deliberately left unwrapped (health, file downloads) are pinned
here as well: wrapping a CSV download would corrupt the file, and wrapping
/health would break the container platform's health check.

Run: python -m pytest tests/test_envelope.py -v
"""

import os
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.errors import APIError, ErrorCode, register_error_handlers
from app.observability.envelope_middleware import ResponseEnvelopeMiddleware
from app.observability.middleware import RequestLoggingMiddleware
from app.schemas.envelope import Response as Envelope


class Account(BaseModel):
    id: str
    name: str


@pytest.fixture
def client():
    app = FastAPI()
    app.add_middleware(ResponseEnvelopeMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    register_error_handlers(app)

    @app.get("/object", response_model=Account)
    def one():
        return Account(id="1", name="Astra")

    @app.get("/list", response_model=list[Account])
    def many():
        return [Account(id="1", name="Astra"), Account(id="2", name="HP")]

    @app.get("/dict")
    def raw():
        return {"access_token": "t0k", "user": {"email": "a@b.c"}}

    @app.get("/empty-list")
    def empty():
        return []

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/download")
    def download():
        return PlainTextResponse("a,b\n1,2", media_type="text/csv")

    @app.get("/missing")
    def missing():
        raise APIError(ErrorCode.ACCOUNT_NOT_FOUND)

    @app.get("/legacy")
    def legacy():
        raise HTTPException(status_code=404, detail="Company account not found")

    @app.delete("/gone", status_code=204)
    def gone():
        return None

    return TestClient(app, raise_server_exceptions=False)


# --- Success ---------------------------------------------------------------

def test_an_object_payload_goes_into_data_unchanged(client):
    body = client.get("/object").json()
    assert body["success"] is True
    assert body["data"] == {"id": "1", "name": "Astra"}
    assert body["error"] is None


def test_a_list_payload_stays_a_list(client):
    # The frontend does response.data.length and response.data[0].id, so the
    # list must not be turned into an object with a wrapper key.
    body = client.get("/list").json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 2
    assert body["data"][0]["id"] == "1"


def test_an_empty_list_is_still_a_list_not_null(client):
    # `data: null` for an empty collection would make every `.map` throw.
    body = client.get("/empty-list").json()
    assert body["data"] == []
    assert body["success"] is True


def test_a_plain_dict_payload_survives_destructuring(client):
    # AuthProvider does: const { access_token, user } = response.data
    data = client.get("/dict").json()["data"]
    assert data["access_token"] == "t0k"
    assert data["user"]["email"] == "a@b.c"


def test_meta_carries_a_request_id_on_success(client):
    # The reason meta exists on successes: a response that returned the wrong
    # number is as worth tracing as one that failed.
    response = client.get("/object")
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_meta_carries_a_utc_timestamp(client):
    assert client.get("/object").json()["meta"]["timestamp"].endswith("Z")


# --- Failure ---------------------------------------------------------------

def test_a_failure_has_null_data_and_a_code(client):
    body = client.get("/missing").json()
    assert body["success"] is False
    assert body["data"] is None
    assert body["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_a_failure_still_exposes_detail_as_a_string(client):
    # 16 frontend sites read err.response.data.detail and render it. They run
    # on the RAW body, because the success interceptor never sees a rejection.
    for path in ("/missing", "/legacy"):
        body = client.get(path).json()
        assert isinstance(body["detail"], str)
        assert body["detail"] == body["error"]["message"]


def test_a_failure_carries_the_request_id_in_meta(client):
    response = client.get("/missing")
    assert response.json()["meta"]["request_id"] == response.headers["X-Request-ID"]


# --- What must not be wrapped ----------------------------------------------

def test_health_is_not_wrapped(client):
    # Parsed by the container platform's health check, which does not know the
    # envelope and would read an unexpected shape as a failure.
    body = client.get("/health").json()
    assert body == {"status": "ok"}
    assert "success" not in body


def test_a_file_download_is_untouched(client):
    # Wrapping a CSV in JSON would corrupt the downloaded file.
    response = client.get("/download")
    assert response.text == "a,b\n1,2"
    assert response.headers["content-type"].startswith("text/csv")


def test_a_204_keeps_an_empty_body(client):
    response = client.delete("/gone")
    assert response.status_code == 204
    assert response.content == b""


def test_wrapping_is_idempotent(client):
    # A handler that already returns the envelope must not be nested inside
    # another one.
    app = FastAPI()
    app.add_middleware(ResponseEnvelopeMiddleware)

    @app.get("/already")
    def already():
        return Envelope[Account].ok(Account(id="1", name="Astra")).model_dump()

    body = TestClient(app).get("/already").json()
    assert body["data"] == {"id": "1", "name": "Astra"}
    assert not isinstance(body["data"], dict) or "success" not in body["data"]


# --- The generic model -----------------------------------------------------

def test_the_envelope_is_generic_over_its_payload():
    # Response[Account] and Response[list[Account]] must be distinct schemas,
    # or the generated OpenAPI types collapse to Any and the frontend loses
    # its typing.
    one = Envelope[Account].model_json_schema()
    many = Envelope[list[Account]].model_json_schema()
    assert one != many


def test_ok_and_fail_build_consistent_shapes():
    ok = Envelope[Account].ok(Account(id="1", name="A"), request_id="r1")
    assert ok.success is True and ok.error is None and ok.meta.request_id == "r1"

    bad = Envelope[Account].fail("X_CODE", "went wrong", request_id="r2")
    assert bad.success is False and bad.data is None
    assert bad.error.code == "X_CODE" and bad.meta.request_id == "r2"
