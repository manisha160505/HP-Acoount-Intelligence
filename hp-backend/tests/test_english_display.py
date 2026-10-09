"""Vendor names and titles in English on the Executive Dashboard, Stakeholder
Map and filings (client, 9 Oct). The originals are kept for the hover.

Run: python -m pytest tests/test_english_display.py -v
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config import account_overrides
from app.services.extractors import executive_dashboard as ed
from app.services.extractors.stakeholder_map import seniority_band
from app.services.hp import translate
from regen_fakes import FakeDb

ANSWERS = {
    "イオン九州（株）": "AEON Kyushu Co., Ltd.",
    "กระทรวงการคลัง": "Ministry of Finance",
    "CIO 最高情報責任者": "CIO Chief Information Officer",
    "有価証券報告書 2025/04/01 - 2026/03/31": "Annual Securities Report 2025/04/01 - 2026/03/31",
    "売上収益 9,999": "Revenue 9,999",
    "吉田憲一郎": "Kenichiro Yoshida",
    "代表取締役社長": "President and Representative Director",
}


@pytest.fixture(autouse=True)
def model(monkeypatch):
    def fake(_system, user):
        items = json.loads(user)["items"]
        return {"items": [{"i": i["i"], "english": ANSWERS.get(i["text"], "")} for i in items]}
    monkeypatch.setattr(translate, "generate_gpt4o_json_completion", fake)


def test_company_names_in_english_with_originals_and_no_repeats():
    names = ["イオン九州（株）", "AEON Kyushu Co., Ltd.", "Aeon Mall"]
    shown, original = ed._in_english(FakeDb(), names)
    assert shown == ["AEON Kyushu Co., Ltd.", "Aeon Mall"], "a translation that repeats is dropped"
    assert original == {"AEON Kyushu Co., Ltd.": "イオン九州（株）"}


def test_english_names_are_untouched():
    shown, original = ed._in_english(FakeDb(), ["Verigy US", "Crea SRL"])
    assert shown == ["Verigy US", "Crea SRL"] and original == {}


def test_a_hidden_parent_hides_its_original_too():
    data = {"parent_company": "Ministry of Finance", "parent_companies": ["Ministry of Finance"],
            "parent_companies_original": {"Ministry of Finance": "กระทรวงการคลัง"}}
    out = account_overrides.masked("BHP BILLITON - AU", "exec_summary_card", data)
    assert out["parent_companies"] == [] and out["parent_companies_original"] == {}


def test_filings_titles_figures_and_ceo_in_english():
    filings = [{"title": "有価証券報告書 2025/04/01 - 2026/03/31"}]
    reported = [{"filing_label": "有価証券報告書 2025/04/01 - 2026/03/31", "quote": "売上収益 9,999"}]
    chief = {"name": "吉田憲一郎", "title": "代表取締役社長",
             "filing_label": "有価証券報告書 2025/04/01 - 2026/03/31"}
    ed._filings_in_english(FakeDb(), filings, reported, chief)
    assert filings[0]["title"].startswith("Annual Securities Report")
    assert filings[0]["title_original"].startswith("有価証券報告書")
    assert reported[0]["quote"] == "売上収益 9,999", "the row as printed is never rewritten"
    assert reported[0]["quote_en"] == "Revenue 9,999"
    assert chief["name"] == "Kenichiro Yoshida" and chief["name_original"] == "吉田憲一郎"
    assert chief["title"] == "President and Representative Director"


def test_the_filings_register_output_is_translated_in_place():
    """The extractor passes the register's listed filings, not the register:
    passing the dict made every Executive Dashboard build fail (9 Oct)."""
    from datetime import date

    from app.services.dashboard import filings_register
    register = filings_register.register(
        [{"document_title": "有価証券報告書 2025/04/01 - 2026/03/31",
          "publication_date": "2026-06-20", "document_url": "https://example.com/ar.pdf"}],
        as_of=date(2026, 10, 9))
    ed._filings_in_english(FakeDb(), register.get("filings") or [], [], None)
    assert register["filings"][0]["title"].startswith("Annual Securities Report")
    assert register["filings"][0]["title_original"].startswith("有価証券報告書")


def test_a_translated_cio_title_is_read_as_c_suite():
    """The seniority rule matches English words; the Japanese title said
    nothing it could read."""
    english = translate.one("CIO 最高情報責任者", FakeDb(), "job_title")
    assert seniority_band("c_suite", english)[0] == seniority_band("c_suite", "CIO")[0]
