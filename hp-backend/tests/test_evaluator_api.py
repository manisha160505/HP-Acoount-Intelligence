"""The Message Evaluator's API: live format checks, and refusals by error code.

AEON, 12 Nov: every refusal reached the seller as "Something went wrong", so a
rewrite that only needed a change unticked read as a broken system. A refusal
the seller can act on now carries its own code; the screen words it.

Run: python -m pytest tests/test_evaluator_api.py -v
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_error_handlers
from app.services.evaluator import evaluate as E
from auth_harness import add_user, auth, body

pytest_plugins = ["auth_harness"]

DRAFT = ("Subject: Lower TCO for AEON\n\nHi Taro,\n\nWe help retailers modernise their "
         "device estate.\n\nWould you be open to a call?\n\nSincerely,\nAnna")


@pytest.fixture
def api(db):
    from app.api.v1.router import api_v1_router
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(api_v1_router)
    return TestClient(app)


@pytest.fixture
def seller(db):
    account = str(db["accounts"].insert_one({"name": "AEON", "status": "active"}).inserted_id)
    return account, add_user(db, "seller@example.com", account_ids=[account])


def test_the_checks_come_back_for_a_draft(api, seller):
    account, user = seller
    r = api.post("/api/v1/accounts/%s/widgets/message_evaluator/checks" % account,
                 headers=auth(user), json={"format": "email", "message": DRAFT})
    assert r.status_code == 200, r.text
    checks = {c["check"]: c["passed"] for c in body(r)["checks"]}
    assert checks == {"length": True, "subject_line": True, "greeting": True,
                      "sign_off": True, "next_step_request": True}


def test_an_unknown_format_is_refused(api, seller):
    account, user = seller
    r = api.post("/api/v1/accounts/%s/widgets/message_evaluator/checks" % account,
                 headers=auth(user), json={"format": "fax", "message": DRAFT})
    assert r.status_code == 400


@pytest.mark.parametrize("code", ["REWRITE_TOO_LONG", "REWRITE_UNSUPPORTED_FIGURE",
                                  "EVALUATION_NOT_FOUND"])
def test_a_refusal_the_seller_can_act_on_keeps_its_code(api, seller, monkeypatch, code):
    account, user = seller

    def refuse(*_a, **_k):
        raise E.EvaluationError("what to do", code)

    monkeypatch.setattr(E, "rewrite_message", refuse)
    r = api.post("/api/v1/accounts/%s/widgets/message_evaluator/rewrite" % account,
                 headers=auth(user), json={"fingerprint": "f" * 32,
                                           "selected_recommendations": ["x"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_any_other_refusal_has_no_code_the_screen_words(api, seller, monkeypatch):
    account, user = seller

    def refuse(*_a, **_k):
        raise E.EvaluationError("Something went wrong. Please try again.")

    monkeypatch.setattr(E, "rewrite_message", refuse)
    r = api.post("/api/v1/accounts/%s/widgets/message_evaluator/rewrite" % account,
                 headers=auth(user), json={"fingerprint": "f" * 32,
                                           "selected_recommendations": ["x"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "EXTRACTION_FAILED"
