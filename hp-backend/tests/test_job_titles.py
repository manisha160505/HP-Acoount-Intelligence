"""Job titles in English for the hiring cards (client, 9 Oct).

The job file's own English is used first; only titles with none go to the
model, once each, cached. A bad answer keeps the posted title.

Run: python -m pytest tests/test_job_titles.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import job_titles as jt, translate
from regen_fakes import FakeDb

KOREAN = "[SDx] IT PM - 로봇SI 프로젝트 제안/수행"
JAPANESE = "ガラス基板における自動検査・工程改善エンジニア"


@pytest.fixture
def model(monkeypatch):
    """A fake translator model that records what it was asked and answers
    from `answers`."""
    calls, answers = [], {}

    def fake(_system, user):
        import json
        asked = json.loads(user)["items"]
        calls.append([t["text"] for t in asked])
        return {"items": [{"i": t["i"], "english": answers.get(t["text"], "")}
                          for t in asked]}

    monkeypatch.setattr(translate, "generate_gpt4o_json_completion", fake)
    return calls, answers


def test_english_titles_need_nothing(model):
    calls, _ = model
    english, n = jt.english_titles([{"title": "Backend Developer"}], FakeDb())
    assert english == {"Backend Developer": "Backend Developer"} and n == 0
    assert calls == []


def test_the_job_files_own_translation_comes_first(model):
    calls, _ = model
    jobs = [{"title": KOREAN, "translated_title": "IT Project Manager",
             "normalized_title": "Something Else"},
            {"title": JAPANESE, "translated_title": "", "normalized_title": "Inspection Engineer"}]
    english, n = jt.english_titles(jobs, FakeDb())
    assert english[KOREAN] == "IT Project Manager"
    assert english[JAPANESE] == "Inspection Engineer"
    assert calls == [] and n == 0


def test_titles_with_no_english_go_to_the_model_once_and_are_cached(model):
    calls, answers = model
    answers[JAPANESE] = "Automated Inspection and Process Improvement Engineer (Glass Substrates)"
    db = FakeDb()
    jobs = [{"title": JAPANESE, "normalized_title": JAPANESE}] * 3

    english, n = jt.english_titles(jobs, db)
    assert english[JAPANESE].startswith("Automated Inspection")
    assert n == 1 and calls == [[JAPANESE]], "asked once, for the one distinct title"

    # Another account, same title: served from the cache, no call.
    english, n = jt.english_titles([{"title": JAPANESE}], db)
    assert english[JAPANESE].startswith("Automated Inspection")
    assert len(calls) == 1


@pytest.mark.parametrize("answer", ["", "   ", "ガラス基板エンジニア", "x" * 200])
def test_a_bad_translation_keeps_the_posted_title(model, answer):
    _, answers = model
    answers[JAPANESE] = answer
    english, n = jt.english_titles([{"title": JAPANESE}], FakeDb())
    assert english[JAPANESE] == JAPANESE and n == 0


def test_no_model_keeps_the_posted_title(monkeypatch):
    monkeypatch.setattr(translate, "generate_gpt4o_json_completion", lambda *_a: None)
    english, n = jt.english_titles([{"title": JAPANESE}], FakeDb())
    assert english[JAPANESE] == JAPANESE and n == 0


def test_is_english():
    assert jt.is_english("SAP ERP ABAP Developer")
    assert jt.is_english("Développeur")          # accented Latin is fine
    assert not jt.is_english(KOREAN)
    assert not jt.is_english(JAPANESE)
    assert not jt.is_english("วิศวกร")            # Thai
