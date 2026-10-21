"""A readable but schema-wrong model answer is a failed call, not a success.

`generate_gpt4o_json_completion` counts any parseable object as a good call.
Each insight feature that reads an answer it cannot use - `{}`, a wrong-typed
list, nothing about what it asked - notes the failure itself, so the engine
marks the run degraded and keeps the previous good output. None is NOT noted a
second time: the helper already counted it.

Companion to test_fault_injection_insight_features.py, whose fixtures it reuses.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import test_fault_injection_insight_features as fi
from app.services.dashboard import priorities as pr
from app.services.extractors import executive_dashboard as ed, grounding
from app.services.hp import map_narrative as mn
from app.services.regen import context as run_context
from test_fault_injection_insight_features import (
    PARAGRAPH,
    _BulletsDb,
    _categories,
    _entry,
    _priority,
    _prose,
    _rec_candidate,
)

# The companion file's fixtures, made available here (pytest finds a fixture
# by the module-level name it is bound to).
no_real_database = fi.no_real_database
news = fi.news
recs = fi.recs
evidence_db = fi.evidence_db


def _in_run(fn):
    ctx = run_context.RunContext(account_id="a", node_id="n")
    with run_context.active(ctx):
        out = fn()
    return out, ctx.llm_failures


class TestMapNarrative:

    @pytest.mark.parametrize("answer, failures", [
        (None, 0), ({}, 1), ({"categories": "x"}, 1), ({"categories": []}, 1),
        ({"categories": [{"category_key": "ghost", "what_it_means": "x"}]}, 1),
        ({"categories": [{"category_key": "collab", "what_it_means": "Zoom."}]}, 0)])
    def test_schema_wrong_answer_is_noted(self, monkeypatch, answer, failures):
        monkeypatch.setattr(mn, "generate_gpt4o_json_completion", lambda *_a: answer)
        cats = _categories()
        _out, noted = _in_run(lambda: mn.generate_map_narrative(cats, ["Zoom"], "Acme"))
        # The short collab meaning triggers one length retry, which answers the
        # same thing again - an answer about the category asked, so no failure.
        assert noted == failures


class TestExecutiveBullets:

    @pytest.mark.parametrize("answer, failures", [
        (None, 0), ({"points": []}, 1), ({"points": "Acme designs pumps."}, 1),
        ({"points": [None, 7]}, 1),
        ({"points": ["Designs pumps.", "Plants in Asia.", "Expands monitoring."]}, 0)])
    def test_schema_wrong_answer_is_noted(self, monkeypatch, answer, failures):
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion", lambda *_a, **_k: answer)
        _out, noted = _in_run(lambda: ed._description_points(
            _BulletsDb(), "acct", PARAGRAPH, {"Business Description": PARAGRAPH}))
        assert noted == failures


class TestPriorities:

    @pytest.mark.parametrize("answer, failures", [
        (None, 0), ({}, 1), ({"priorities": "x"}, 1), ({"priorities": [1, None]}, 1),
        ({"priorities": []}, 0), ({"priorities": [{"title": "t"}]}, 0)])
    def test_candidate_answer_shape(self, answer, failures):
        _out, noted = _in_run(lambda: pr._candidates_in(answer))
        assert noted == failures

    @pytest.mark.parametrize("answer, failures", [
        (None, 0), ({"points": 7}, 1), ({"points": []}, 1), ({"points": [None]}, 1)])
    def test_description_answer_shape(self, monkeypatch, answer, failures):
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", lambda *_a: answer)
        out, noted = _in_run(lambda: pr._describe(_priority([PARAGRAPH]), [], "Acme"))
        assert out["written_by"] == "python"
        assert "None" not in out["text"]
        assert noted == failures

    @pytest.mark.parametrize("body, ok", [
        ("Revenue rose 20% in the year.", False),          # only inside "2025"
        ("Automation continues in 2025.", True),
        ("Automation continues in 2025, across 3 sites.", True),   # one digit, unchecked
        ("Margin was 5% in the year.", False),             # a percent is always checked
        ("Capacity reached 1,250 units.", True),
        ("Capacity reached 125 units.", False),            # a substring of 1,250
    ])
    def test_figures_compare_as_whole_tokens(self, body, ok):
        evidence = "Automation of service centres continues in 2025. Capacity 1,250 units."
        assert pr._validate_description(body, evidence, "")[0] is ok

    def test_a_string_evidence_ids_drops_only_that_candidate(self, evidence_db):
        kept, dropped, _i = pr._resolve_priorities("acct-1", [
            {"title": "Factory automation", "evidence_ids": "doc_a#c1"},
            {"title": "Digital monitoring services", "evidence_ids": ["doc_b#c1"]}])
        assert [p["title"] for p in kept] == ["Digital monitoring services"]
        assert dropped[0]["reason"] == "evidence_ids is not a list"


class TestRecommendations:

    @pytest.mark.parametrize("answer, failures", [
        (None, 0), ({}, 1), ({"recommendations": "x"}, 1),
        ({"recommendations": [_prose("99")]}, 1),
        ({"recommendations": [_prose("1")]}, 0)])
    def test_schema_wrong_answer_is_noted(self, recs, answer, failures):
        payload, noted = _in_run(lambda: recs(answer))
        assert payload["data"]["recommendations_count"] == 2, "cards still publish"
        assert noted == failures

    def test_an_approved_fact_url_in_product_prose_stands(self, recs):
        cand = _rec_candidate("1")
        cand["approved_facts"] = [{"text": "See https://www.hp.com/elite for the range.",
                                   "qualifiers": [], "conditions": []}]
        payload = recs({"recommendations": [_prose(
            "1", why_this_product="See https://www.hp.com/elite for the range.")]},
            candidates=[cand])
        card = payload["data"]["recommendations"][0]
        assert card["why_this_product"] == "See https://www.hp.com/elite for the range."


class TestNewsGate:

    @pytest.mark.parametrize("value, passed", [
        (True, True), ("true", True), ("Yes", True), ("1", True),
        (False, False), ("false", False), ("no", False), (None, False), (0, False)])
    def test_only_an_unambiguous_yes_passes(self, news, value, passed):
        from app.services.extractors import recent_news_signals as rns
        sig = news.signals()[0]
        news.install(lambda s, _u: {"signals": [_entry(sig["signal_id"], 0, gate_pass=value)]}
                     if "SIGNALS TO SCORE" in s else None)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"]
        assert got[sig["signal_id"]]["gate_pass"] is passed

    def test_a_missing_gate_keeps_the_default_pass(self, news):
        from app.services.extractors import recent_news_signals as rns
        sig = news.signals()[0]
        entry = _entry(sig["signal_id"], 0)
        entry.pop("gate_pass")
        news.install(lambda s, _u: {"signals": [entry]} if "SIGNALS TO SCORE" in s else None)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"]
        assert got[sig["signal_id"]]["gate_pass"] is True


class TestEnumList:

    @pytest.mark.parametrize("values, kept", [
        (None, []), ("", []), (5, []), ("HP Elite / Pro PCs", []),
        (["Poly Collaboration", 7], ["Poly Collaboration"])])
    def test_a_non_list_is_rejected_whole(self, values, kept):
        got, _rejected = grounding.filter_enum_list(values, grounding.HP_PRODUCT_LINES)
        assert got == kept


class TestCitedIdLists:
    """`evidence.resolve` and Messaging pillars take the citation list a model
    wrote. A repeated id is one source (first-cited order kept), and a value
    that is not a list resolves nothing - the same rule as the priorities fix."""

    def test_resolve_dedupes_and_keeps_the_first_cited_order(self, evidence_db):
        from app.services.retrieval import evidence as ev
        rows, invalid = ev.resolve(fi.ACCT, pr.INDEX,
                                   ["doc_b#c1", "doc_a#c1", "doc_b#c1", " doc_a#c1 ",
                                    "bad", "bad"])
        assert [r["evidence_id"] for r in rows] == ["doc_b#c1", "doc_a#c1"]
        assert invalid == ["bad"]

    @pytest.mark.parametrize("ids", [None, "doc_a#c1", 7, {"doc_a#c1": 1}])
    def test_resolve_of_a_non_list_is_nothing(self, evidence_db, ids):
        from app.services.retrieval import evidence as ev
        assert ev.resolve(fi.ACCT, pr.INDEX, ids) == ([], [])

    def test_a_pillar_challenge_cites_each_source_once(self, monkeypatch):
        from app.services.messaging import pillars
        seen = []

        def resolve(_aid, _idx, ids):
            seen.append(list(ids))
            return [{"evidence_id": i, "source_text": "t", "dataset": "d",
                     "doc_id": i.split("#")[0], "field": "f"} for i in ids], []

        monkeypatch.setattr(pillars.ev, "resolve", resolve)
        kept, dropped, _i = pillars._resolve_challenges("acct", [
            {"challenge": "Ageing fleet", "evidence_ids": ["d#c1", "d#c2", "d#c1"]},
            {"challenge": "Cost pressure", "evidence_ids": "d#c1"},
            {"challenge": "Hybrid work", "evidence_ids": 3}])
        assert seen == [["d#c1", "d#c2"]]
        assert [p["challenge"] for p in kept] == ["Ageing fleet"]
        assert len(kept[0]["evidence"]) == 2
        assert [d["reason"] for d in dropped] == ["evidence_ids is not a list"] * 2
