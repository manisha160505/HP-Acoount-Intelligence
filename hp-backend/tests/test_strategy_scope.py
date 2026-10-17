"""Strategy Chat turns away a question that is not about the account.

Live site, 17 Oct: asked for a poem about the ocean, the chat wrote one; asked
for a cake recipe, it said it had "drafted an answer about" the account. The
scope check reads the question alone, refuses only what has no plausible link
to the account or to selling to it, and lets everything else through to the
evidence checks - including whenever the model gives no clear answer.

Run: python -m pytest tests/test_strategy_scope.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.observability import steps
from app.services.strategy import chat

COMPANY = "ACME CORP - PH"


@pytest.fixture
def model(monkeypatch):
    """The scope model's reply, and every prompt it was sent."""
    state = {"reply": {"in_scope": True}, "calls": []}

    def fake(system, user):
        state["calls"].append((system, user))
        return state["reply"]

    monkeypatch.setattr(chat, "generate_gpt4o_json_completion", fake)
    return state


# --- the verdict --------------------------------------------------------------

@pytest.mark.parametrize("reply, expected", [
    ({"in_scope": True}, True),
    ({"in_scope": False}, False),
    ({"in_scope": "false"}, False),
    ({"in_scope": "true"}, True),
    # Fails open: a real question wrongly refused costs more than an odd one
    # let through, and the odd one still faces the evidence checks.
    (None, True),
    ({}, True),
    ({"in_scope": None}, True),
    ({"something_else": False}, True),
])
def test_only_an_explicit_no_refuses(model, reply, expected):
    model["reply"] = reply
    assert chat._in_scope(COMPANY, "Write me a poem") is expected


def test_the_prompt_names_the_account_and_carries_the_question(model):
    chat._in_scope(COMPANY, "Who should I approach first?")
    system, user = model["calls"][0]
    assert COMPANY in system and "{company}" not in system
    assert "Who should I approach first?" in user


def test_a_brace_in_the_company_name_does_not_break_the_prompt(model):
    chat._in_scope("ODD {NAME} LTD", "q")
    assert "ODD {NAME} LTD" in model["calls"][0][0]


# --- the turn -----------------------------------------------------------------

@pytest.fixture
def prepared(monkeypatch, model):
    """`_prepare` with the account stubbed, recording whether it was read."""
    built = []
    monkeypatch.setattr(chat.widget_store, "get",
                        lambda *_a, **_k: {"data": {"company_name": COMPANY}})
    monkeypatch.setattr(chat.account_context, "build",
                        lambda account_id: built.append(account_id) or
                        ("===== exec_summary_card =====\nx",
                         [{"widget_key": "exec_summary_card"}]))

    def run(question, persona=None):
        monkeypatch.setattr(chat.strategy_personas, "resolve",
                            lambda *_a: persona)
        return chat._prepare(None, steps.StepTimer(), "a1",
                             [{"role": "user", "content": question}],
                             "advisor", "p1" if persona else None)
    return run, built


def test_an_off_topic_question_is_refused_before_the_account_is_read(model, prepared):
    run, built = prepared
    model["reply"] = {"in_scope": False}
    out = run("Write me a short poem about the ocean.")["done"]
    assert out["available"] is False
    assert out["unavailable_cause"] == chat.CAUSE_OFF_TOPIC
    assert out["answer"] == out["answer_clean"]
    assert out["answer"].startswith(
        "I can only help with questions about %s and how HP can sell" % COMPANY)
    assert "drafted" not in out["answer"] and "Stakeholder Map" not in out["answer"]
    assert out["citations"] == [] and built == []


def test_an_account_question_goes_on_to_be_answered(model, prepared):
    run, built = prepared
    turn = run("Who is the strongest entry point for AI PCs?")
    assert "done" not in turn
    assert turn["question"] == "Who is the strongest entry point for AI PCs?"
    assert built == ["a1"]


def test_a_failed_scope_call_still_answers(model, prepared):
    run, built = prepared
    model["reply"] = None
    assert "done" not in run("What objections should I expect?")
    assert built == ["a1"]


def test_a_greeting_is_answered_without_the_scope_call(model, prepared):
    run, _ = prepared
    out = run("hi")["done"]
    assert out["topic"] == "greeting" and model["calls"] == []


def test_a_rehearsal_refuses_in_its_own_words(model, prepared):
    run, _ = prepared
    model["reply"] = {"in_scope": False}
    persona = {"persona_id": "p1", "name": "A Person", "title": "CIO"}
    out = run("Tell me a joke", persona=persona)["done"]
    assert out["mode"] == "roleplay"
    assert out["answer"] == ("That is outside this rehearsal. Ask the CIO "
                             "something you would raise in a real meeting "
                             "with %s." % COMPANY)
    assert out["persona"]["title"] == "CIO"
