"""The shared translator for vendor text shown to sellers (client, 9 Oct).

Only non-English text is sent; each string is translated once and cached; an
answer is used only if it is English, of a sane length and keeps every number.
Anything else keeps the original.

Run: python -m pytest tests/test_translate.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import translate as tr
from regen_fakes import FakeDb

HEADLINE = "アドバンテスト、2026年度の設備投資を300億円に"
COMPANY = "イオン九州（株）"


@pytest.fixture
def model(monkeypatch):
    """A fake model: records each batch, answers from `answers`."""
    calls, answers = [], {}

    def fake(_system, user):
        asked = json.loads(user)
        calls.append((asked["kind"], [i["text"] for i in asked["items"]]))
        return {"items": [{"i": i["i"], "english": answers.get(i["text"], "")}
                          for i in asked["items"]]}

    monkeypatch.setattr(tr, "generate_gpt4o_json_completion", fake)
    return calls, answers


def test_english_is_never_sent(model):
    calls, _ = model
    assert tr.to_english(["Advantest opens Chitose office", ""], FakeDb(), "headline") == {}
    assert calls == []


def test_translated_once_then_served_from_the_cache(model):
    calls, answers = model
    answers[COMPANY] = "AEON Kyushu Co., Ltd."
    db = FakeDb()
    assert tr.to_english([COMPANY, COMPANY], db, "company") == {COMPANY: "AEON Kyushu Co., Ltd."}
    assert len(calls) == 1 and calls[0][1] == [COMPANY], "asked once, deduplicated"
    assert tr.one(COMPANY, db, "company") == "AEON Kyushu Co., Ltd."
    assert len(calls) == 1, "second time from the cache"


def test_the_cache_is_per_kind(model):
    calls, answers = model
    answers["日経"] = "Nikkei"
    db = FakeDb()
    tr.to_english(["日経"], db, "publisher")
    tr.to_english(["日経"], db, "company")
    assert len(calls) == 2


def test_numbers_must_survive(model):
    _, answers = model
    answers[HEADLINE] = "Advantest sets FY2026 capex at 30 billion yen"   # 300 lost
    assert tr.to_english([HEADLINE], FakeDb(), "headline") == {}
    answers[HEADLINE] = "Advantest sets FY2026 capital spending at 300 hundred-million yen"
    assert tr.one(HEADLINE, FakeDb(), "headline").endswith("300 hundred-million yen")


@pytest.mark.parametrize("answer", ["", "  ", "イオン九州", "x" * 500])
def test_a_bad_answer_keeps_the_original(model, answer):
    _, answers = model
    answers[COMPANY] = answer
    assert tr.one(COMPANY, FakeDb(), "company") == COMPANY


def test_no_model_keeps_the_original(monkeypatch):
    monkeypatch.setattr(tr, "generate_gpt4o_json_completion", lambda *_a: None)
    assert tr.one(COMPANY, FakeDb(), "company") == COMPANY


def test_fullwidth_digits_count_as_the_same_number():
    assert tr.acceptable("２０２６年度", "FY2026", "headline") == "FY2026"


def test_an_unknown_kind_is_a_programming_error():
    with pytest.raises(ValueError):
        tr.to_english(["x"], FakeDb(), "poem")


def test_is_english():
    assert tr.is_english("Développeur SAP")
    assert not tr.is_english(HEADLINE)
    assert not tr.is_english("กระทรวงการคลัง")
    assert not tr.is_english("보안 엔지니어")


def test_the_database_is_only_opened_when_something_needs_translating(model):
    """Callers pass `get_db` itself. All-English data - nearly every account -
    must not open a connection (CI has no database, and a page of English needs
    no cache)."""
    opened = []

    def get_db():
        opened.append(1)
        return FakeDb()

    assert tr.to_english(["Chief Information Officer", ""], get_db, "job_title") == {}
    assert opened == []
    _, answers = model
    answers[COMPANY] = "AEON Kyushu Co., Ltd."
    assert tr.to_english([COMPANY], get_db, "company") == {COMPANY: "AEON Kyushu Co., Ltd."}
    assert opened == [1]
