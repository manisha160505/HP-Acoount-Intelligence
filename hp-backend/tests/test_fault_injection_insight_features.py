"""Fault injection for the AI-backed insight features.

Every model call is faked - nothing here touches the network. Each test feeds
one class of bad answer to one feature and checks the same five promises:

  * no unhandled exception;
  * model output is never attached to an item it was not about (unknown or
    duplicate ids are dropped, not guessed);
  * a total model failure is reported as a failure / degraded, not a silent
    success;
  * a partial answer keeps the good entries and fabricates nothing;
  * published counts agree with the content published.

Tests marked `xfail(strict=True, reason="BUG: ...")` reproduce a real defect in
the current code. They fail today by design and will start XPASS-failing the
day the defect is fixed, which is the signal to drop the marker.

Features covered: Opportunity Map (plays + map narrative), Recent News /
Live Signals (scoring + translation), Executive Dashboard (business bullets +
strategic priorities), Tech Landscape recommendations, and the intent
helpers that call the model (Bombora classifier, So What).

Run: .venv/bin/python -m pytest tests/test_fault_injection_insight_features.py -v
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core import llm
from app.services.dashboard import priorities as pr
from app.services.extractors import (
    datasets,
    executive_dashboard as ed,
    intent_demand_signals as ids_mod,
    recent_news_signals as rns,
    solution_narrative_opportunity_map as opp,
)
from app.services.hp import (
    bombora_hp_classifier as bhc,
    map_narrative as mn,
    recommendations as rec,
    translate,
)
from app.services.regen import context as run_context
from app.services.retrieval import evidence as ev
from regen_fakes import FakeDb


@pytest.fixture(autouse=True)
def no_real_database(monkeypatch):
    """Any code path that reaches the real `get_db` fails at once instead of
    waiting on a server selection timeout - nothing here may leave the process."""
    from app.database import mongodb

    def refuse():
        raise RuntimeError("real database access attempted in a fault-injection test")

    monkeypatch.setattr(mongodb.db_instance, "db", None)
    monkeypatch.setattr(mongodb, "connect_to_mongo", refuse)


def _days_ago(n):
    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


def _words(n, word="context"):
    return " ".join([word] * n)


# ---------------------------------------------------------------------------
# Driving the real JSON helper end to end (retry + run_context accounting)
# ---------------------------------------------------------------------------

class _ScriptedProvider:
    """Stands in for the provider below `generate_gpt4o_json_completion`.

    Each call pops the next scripted answer: a string is returned as the
    message content, an Exception instance is raised, and once the script is
    exhausted the last answer repeats.
    """

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, _client, affinity="", **_kwargs):
        self.calls += 1
        answer = self.answers[0] if len(self.answers) == 1 else self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=answer))],
            usage=SimpleNamespace(total_tokens=10))


@pytest.fixture
def provider(monkeypatch):
    def install(*answers):
        fake = _ScriptedProvider(*answers)
        monkeypatch.setattr(llm, "get_openai_client", object)
        monkeypatch.setattr(llm, "create_completion", fake)
        return fake
    return install


class TestTheJsonHelperItself:
    """The shared contract every feature below leans on."""

    def test_malformed_then_valid_is_one_good_answer(self, provider):
        fake = provider('{"points": ["a", ', '{"points": ["a"]}')
        ctx = run_context.RunContext(account_id="a", node_id="n")
        with run_context.active(ctx):
            out = llm.generate_gpt4o_json_completion("s", "u")
        assert out == {"points": ["a"]}
        assert fake.calls == 2
        assert (ctx.llm_calls, ctx.llm_failures) == (1, 0)

    @pytest.mark.parametrize("answers", [
        ("{not json", "{still not json"),
        ("", ""),
        ("[1, 2, 3]", "[1, 2, 3]"),          # valid JSON, not an object
        (RuntimeError("provider 500"),),
    ])
    def test_total_failure_is_none_and_counted_as_failed(self, provider, answers):
        provider(*answers)
        ctx = run_context.RunContext(account_id="a", node_id="n")
        with run_context.active(ctx):
            assert llm.generate_gpt4o_json_completion("s", "u") is None
        assert ctx.llm_failures == 1

    def test_no_client_is_a_counted_failure(self, monkeypatch):
        monkeypatch.setattr(llm, "get_openai_client", lambda: None)
        ctx = run_context.RunContext(account_id="a", node_id="n")
        with run_context.active(ctx):
            assert llm.generate_gpt4o_json_completion("s", "u") is None
        assert ctx.llm_failures == 1

    def test_fenced_json_is_read(self, provider):
        provider('```json\n{"ok": true}\n```')
        assert llm.generate_gpt4o_json_completion("s", "u") == {"ok": True}


# ===========================================================================
# 1. Recent News / Live Signals
# ===========================================================================

NEWS_ROWS = [
    {"event_headline": "Acme opens Austin design studio - Reuters",
     "event_date": _days_ago(10), "event_url": "https://www.reuters.com/acme-austin",
     "news_announcements": "The studio will house the product design group."},
    {"event_headline": "Acme signs cloud partnership with Contoso - Bloomberg",
     "event_date": _days_ago(40), "event_url": "https://www.bloomberg.com/acme-contoso"},
    {"event_headline": "Acme appoints new chief information officer - Nikkei",
     "event_date": _days_ago(70), "event_url": "https://asia.nikkei.com/acme-cio"},
]

_OPENERS = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf", "Hotel"]


def _angle(k):
    """A clean 70-100 word angle with its own opening and closing stems and no
    digit anywhere, so neither the phrasing guard nor grounding touches it."""
    word = _OPENERS[k % len(_OPENERS)]
    body = ("this event is a relationship signal rather than a stated technology "
            "requirement and the seller should treat it as context for an early "
            "conversation about workplace devices security and collaboration "
            "while watching for a named programme budget or project owner that "
            "would turn it into a timed opportunity worth pursuing with the "
            "account team over the coming quarter and beyond as plans become "
            "clearer and the new priorities are announced publicly")
    return "%s reading: %s; contact the %s owner first." % (word, body, word.lower())


def _ids_in(system_prompt):
    return [line.split("id=")[1].split(" |")[0]
            for line in system_prompt.splitlines() if line.startswith("- id=")]


def _entry(sid, k, score=6, **extra):
    out = {"signal_id": sid, "gate_pass": True, "gate_reject_reason": None,
           "scores": {"relevance_impact": {"score": score, "rationale": "Level six."}},
           "matched_categories": ["major business change"],
           "sales_angle": _angle(k), "hp_play": None, "event_status": "announced"}
    out.update(extra)
    return out


@pytest.fixture
def news(monkeypatch):
    """A Live Signals run over NEWS_ROWS with the model replaced by `model`."""
    db = FakeDb()
    account_id = str(ObjectId())
    db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})
    rows = {"google_news": [dict(r) for r in NEWS_ROWS], "news_events": []}
    monkeypatch.setattr(rns, "get_db", lambda: db)
    monkeypatch.setattr(datasets, "get_db", lambda: db)
    monkeypatch.setattr(rns, "_read_dataset_records",
                        lambda _a, key: [dict(r) for r in rows.get(key, [])])
    monkeypatch.setattr(rns, "read_dataset_records", lambda *_a, **_k: [])
    calls = []

    def install(model):
        def recorder(system, user):
            calls.append((system, user))
            return model(system, user)
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", recorder)
        monkeypatch.setattr(translate, "generate_gpt4o_json_completion", recorder)

    def signals():
        """The deduped signals the scorer would be given, ids included."""
        raw = rns._normalize_signals(rows["google_news"], rows["news_events"])
        passed, _ = rns._apply_gate(raw, datetime.now(UTC))
        linked, _ = rns._split_unlinked(rns._dedupe(passed))
        return linked

    return SimpleNamespace(db=db, account_id=account_id, rows=rows, calls=calls,
                           install=install, signals=signals)


def _scoring_calls(calls):
    return [c for c in calls if "SIGNALS TO SCORE" in c[0]]


class TestNewsScoringFaults:

    def test_unknown_and_duplicate_ids_never_attach_to_a_signal(self, news):
        sigs = news.signals()
        a, b = sigs[0]["signal_id"], sigs[1]["signal_id"]

        def model(system, _user):
            if "SIGNALS TO SCORE" not in system:
                return None
            return {"signals": [
                _entry(a, 0, score=8),
                _entry("deadbeefcafe", 1, score=10),        # never supplied
                _entry(a, 2, score=0),                      # duplicate - ignored
                _entry(b.upper(), 3, score=10),             # case-mangled id
                None, {},
            ]}

        news.install(model)
        doc = rns.score_news_signals(news.account_id, sigs, "Acme")
        scores = doc["data"]["scores"]
        assert set(scores) <= {s["signal_id"] for s in sigs}
        assert "deadbeefcafe" not in scores
        assert scores[a]["scores"]["relevance_impact"] == 8.0, "first answer wins"
        assert b not in scores, "an id that does not match exactly is not guessed"
        assert doc["data"]["scored_count"] == len(scores)

    @pytest.mark.parametrize("junk", ["not a dict", 7, ["nested"]])
    def test_a_junk_element_in_the_list_drops_only_itself(self, news, junk):
        sig = news.signals()[0]
        news.install(lambda s, _u: {"signals": [junk, _entry(sig["signal_id"], 0)]}
                     if "SIGNALS TO SCORE" in s else None)
        doc = rns.score_news_signals(news.account_id, [sig], "Acme")
        assert set(doc["data"]["scores"]) == {sig["signal_id"]}

    @pytest.mark.parametrize("raw_score, expected", [
        (15, 10.0), (-3, 0.0), ("6", 6.0), ({"score": 9.4}, 9.4)])
    def test_out_of_range_scores_are_clamped(self, news, raw_score, expected):
        sig = news.signals()[0]
        block = raw_score if isinstance(raw_score, dict) else {"score": raw_score}
        news.install(lambda s, _u: {"signals": [
            {**_entry(sig["signal_id"], 0), "scores": {"relevance_impact": block}}]}
            if "SIGNALS TO SCORE" in s else None)
        doc = rns.score_news_signals(news.account_id, [sig], "Acme")
        assert doc["data"]["scores"][sig["signal_id"]]["scores"]["relevance_impact"] == expected

    @pytest.mark.parametrize("bad_scores", [
        {"relevance_impact": {"score": "high"}},
        {"relevance_impact": None},
        {},
        "six",
        None,
    ])
    def test_an_unreadable_score_drops_the_entry_rather_than_inventing_one(
            self, news, bad_scores):
        sig = news.signals()[0]
        news.install(lambda s, _u: {"signals": [
            {**_entry(sig["signal_id"], 0), "scores": bad_scores}]}
            if "SIGNALS TO SCORE" in s else None)
        doc = rns.score_news_signals(news.account_id, [sig], "Acme")
        assert doc["data"]["scores"] == {}
        assert doc["status"] == "pending"

    def test_invented_enums_fall_back(self, news):
        sig = news.signals()[0]
        news.install(lambda s, _u: {"signals": [_entry(
            sig["signal_id"], 0, hp_play="HP Quantum Laptop X", event_status="Done!")]}
            if "SIGNALS TO SCORE" in s else None)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"][
            sig["signal_id"]]
        assert got["hp_play"] is None
        assert got["event_status"] == rns.DEFAULT_EVENT_STATUS

    def test_a_string_false_gate_is_a_rejection(self, news):
        sig = news.signals()[0]
        news.install(lambda s, _u: {"signals": [_entry(
            sig["signal_id"], 0, gate_pass="false",
            gate_reject_reason="about a competitor")]}
            if "SIGNALS TO SCORE" in s else None)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"][
            sig["signal_id"]]
        assert got["gate_pass"] is False

    def test_hallucinated_number_or_url_in_prose_is_withheld_score_kept(self, news):
        sig = news.signals()[0]
        sid = sig["signal_id"]
        invented = _angle(0).replace("early conversation",
                                     "early 4,500-seat conversation (see https://evil.example/x)")

        def model(system, _user):
            if "SIGNALS TO SCORE" in system:
                return {"signals": [{**_entry(sid, 0, score=8), "sales_angle": invented,
                                     "scores": {"relevance_impact": {
                                         "score": 8,
                                         "rationale": "Acme will buy 12,000 laptops."}}}]}
            return None

        news.install(model)
        doc = rns.score_news_signals(news.account_id, [sig], "Acme")
        got = doc["data"]["scores"][sid]
        assert got["scores"]["relevance_impact"] == 8.0
        assert got["sales_angle"] is None
        assert "relevance_impact" not in got["rationales"]
        assert got["rationales_withheld"] == ["relevance_impact"]
        report = doc["data"]["grounding_report"]
        assert report["numbers_rejected"] and report["urls_rejected"]

    def test_angle_retry_answer_for_an_unknown_id_is_ignored(self, news):
        sig = news.signals()[0]
        sid = sig["signal_id"]
        short = "Short angle about the studio; contact the design owner."

        def model(system, _user):
            if "SIGNALS TO SCORE" in system:
                return {"signals": [{**_entry(sid, 0), "sales_angle": short}]}
            # The rewrite answers for an id it was never asked about.
            return {"signals": [{"signal_id": "deadbeefcafe", "sales_angle": _angle(5)}]}

        news.install(model)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"]
        assert set(got) == {sid}
        assert got[sid]["sales_angle"] == short, "the short first answer stands"

    def test_banned_phrase_angle_is_dropped_when_the_rewrite_fails(self, news):
        sig = news.signals()[0]
        sid = sig["signal_id"]
        banned = _angle(0) + " Now is the time to position HP."
        news.install(lambda s, _u: {"signals": [{**_entry(sid, 0), "sales_angle": banned}]}
                     if "SIGNALS TO SCORE" in s else None)
        got = rns.score_news_signals(news.account_id, [sig], "Acme")["data"]["scores"][sid]
        assert got["sales_angle"] is None
        assert got["scores"]["relevance_impact"] == 6.0

    def test_partial_answer_keeps_good_entries_and_reports_the_rest(self, news):
        sigs = news.signals()
        keep = sigs[0]["signal_id"]
        news.install(lambda s, _u: {"signals": [_entry(keep, 0)]}
                     if "SIGNALS TO SCORE" in s else None)
        feed, summary = rns.extract_recent_news_signals(news.account_id)

        assert set(summary["data"]["scores"]) == {keep}
        # Asked once in its batch; the retry for the two missing answers about
        # neither, so it is asked again once.
        assert len(_scoring_calls(news.calls)) == 1 + rns.ANSWER_ATTEMPTS
        data = feed["data"]
        published = data["signals"]
        assert data["total_signals_count"] == len(published) == len(sigs)
        assert data["not_assessed_count"] == len(sigs) - 1
        assert data["model_rejected_count"] == 0
        unscored = [s for s in published if s["signal_id"] != keep]
        assert all(not s["relevance_assessed"] and s["confidence"] is None
                   and s["sales_angle"] is None for s in unscored), \
            "nothing is fabricated for a signal the model never scored"
        assert published[0]["signal_id"] == keep, "scored signals rank first"

    def test_model_rejection_is_counted_and_not_published(self, news):
        sigs = news.signals()
        reject = sigs[1]["signal_id"]
        news.install(lambda s, _u: {"signals": [
            _entry(x, k, gate_pass=(x != reject),
                   gate_reject_reason=("competitor story" if x == reject else None))
            for k, x in enumerate(_ids_in(s))]} if "SIGNALS TO SCORE" in s else None)
        feed, _summary = rns.extract_recent_news_signals(news.account_id)
        data = feed["data"]
        assert reject not in {s["signal_id"] for s in data["signals"]}
        assert data["model_rejected_count"] == 1
        assert data["total_signals_count"] == len(data["signals"]) == len(sigs) - 1

    def test_zero_news_is_empty_and_calls_no_model(self, news):
        news.rows["google_news"] = []
        news.install(lambda *_a: pytest.fail("no model call expected"))
        out = rns.extract_recent_news_signals(news.account_id)
        assert len(out) == 1 and out[0]["status"] == "empty"
        assert news.calls == []

    def test_very_long_and_non_english_fields_do_not_break_scoring(self, news):
        long_headline = "Acme " + _words(3000, "expansion")
        news.rows["google_news"] = [
            {"event_headline": long_headline, "event_date": _days_ago(5),
             "event_url": "https://www.reuters.com/long"},
            {"event_headline": "アクメ、千歳に新工場を開設", "event_date": _days_ago(6),
             "event_url": "https://www.nikkei.com/acme-jp"}]

        def model(system, user):
            if "SIGNALS TO SCORE" in system:
                return {"signals": [_entry(x, k) for k, x in enumerate(_ids_in(system))]}
            # Translation answers in a script that is still not English.
            items = json.loads(user)["items"]
            return {"items": [{"i": i["i"], "english": "アクメ"} for i in items]}

        news.install(model)
        feed, summary = rns.extract_recent_news_signals(news.account_id)
        assert summary["data"]["scored_count"] == 2
        jp = next(s for s in feed["data"]["signals"] if "nikkei" in s["source_url"])
        assert jp["headline"] == "アクメ、千歳に新工場を開設", "untranslatable stays original"
        assert "headline_original" not in jp
        # The roster line is clipped, so a huge headline cannot blow the prompt.
        assert all(len(line) < 1000 for c in _scoring_calls(news.calls)
                   for line in c[0].splitlines() if line.startswith("- id="))

    @pytest.mark.parametrize("answer", [
        None,
        {},
        {"signals": [{"signal_id": "deadbeefcafe", "scores": {
            "relevance_impact": {"score": 8}}}]},
        {"signals": "eight entries"},
    ], ids=["none", "empty-dict", "unknown-ids", "wrong-type"])
    def test_no_scores_still_publishes_the_unscored_feed(self, news, answer):
        news.install(lambda *_a: answer)
        feed, summary = rns.extract_recent_news_signals(news.account_id)
        assert summary["data"]["scores"] == {}
        assert feed["status"] == "available"
        assert feed["data"]["total_signals_count"] == len(feed["data"]["signals"]) == 3
        assert feed["data"]["model_rejected_count"] == 0
        assert all(not s["relevance_assessed"] for s in feed["data"]["signals"])

    def test_inside_a_run_a_dead_model_is_counted_as_a_failure(self, news, provider):
        """End to end through app.core.llm: every scoring call fails, and the
        run context records it, which is what makes the engine mark the section
        degraded and keep the previous summary."""
        monkey_target = rns.generate_gpt4o_json_completion
        assert monkey_target is llm.generate_gpt4o_json_completion
        provider("{broken", "{broken")
        sigs = news.signals()
        ctx = run_context.RunContext(account_id=news.account_id, node_id="news",
                                     owned=frozenset({"news_relevance_summary",
                                                      "news_signals_feed"}))
        with run_context.active(ctx):
            doc = rns.score_news_signals(news.account_id, sigs, "Acme")
        assert doc["data"]["scores"] == {}
        assert ctx.llm_failures >= 1

    def test_malformed_then_valid_scores_end_to_end(self, news, provider):
        sigs = news.signals()
        good = json.dumps({"signals": [_entry(s["signal_id"], k)
                                       for k, s in enumerate(sigs)]})
        fake = provider("{\"signals\": [", good)
        ctx = run_context.RunContext(account_id=news.account_id, node_id="news",
                                     owned=frozenset({"news_relevance_summary"}))
        with run_context.active(ctx):
            doc = rns.score_news_signals(news.account_id, sigs, "Acme")
        assert doc["data"]["scored_count"] == len(sigs)
        assert fake.calls == 2
        assert ctx.llm_failures == 0

    def test_a_schema_wrong_answer_inside_a_run_is_not_a_silent_success(
            self, news, provider):
        provider("{}")
        sigs = news.signals()
        ctx = run_context.RunContext(account_id=news.account_id, node_id="news",
                                     owned=frozenset({"news_relevance_summary"}))
        with run_context.active(ctx):
            doc = rns.score_news_signals(news.account_id, sigs, "Acme")
        assert doc["data"]["scored_count"] == 0
        assert ctx.llm_failures >= 1


class TestNewsOffTargetAnswers:
    """A readable answer about none of what was asked is asked again, and one
    bad answer out of many no longer throws away a whole account's fresh news.

    21 Oct run: News failed on about one account in ten, each over a single
    such answer among 10-40 calls - most of them sales-angle rewrites - and the
    engine kept yesterday's news for the account.
    """

    @staticmethod
    def _in_run(news, sigs):
        ctx = run_context.RunContext(account_id=news.account_id, node_id="news",
                                     owned=frozenset({"news_relevance_summary"}))
        with run_context.active(ctx):
            doc = rns.score_news_signals(news.account_id, sigs, "Acme")
        return doc, ctx

    def test_an_off_target_scoring_answer_is_asked_again(self, news):
        sigs = news.signals()
        tries = []

        def model(system, _user):
            if "SIGNALS TO SCORE" not in system:
                return None
            tries.append(1)
            if len(tries) == 1:
                return {"signals": [_entry("deadbeefcafe", 0)]}   # never sent
            return {"signals": [_entry(sid, k) for k, sid in enumerate(_ids_in(system))]}

        news.install(model)
        doc, ctx = self._in_run(news, sigs)
        assert len(tries) == 2
        assert doc["data"]["scored_count"] == len(sigs)
        assert ctx.llm_failures == 0

    def test_a_scoring_failure_recovered_by_the_resend_is_not_a_failure(self, news):
        sigs = news.signals()
        tries = []

        def model(system, _user):
            if "SIGNALS TO SCORE" not in system:
                return None
            tries.append(1)
            if len(tries) <= rns.ANSWER_ATTEMPTS:              # the first batch, twice
                return {"signals": []}
            return {"signals": [_entry(sid, k) for k, sid in enumerate(_ids_in(system))]}

        news.install(model)
        doc, ctx = self._in_run(news, sigs)
        assert doc["data"]["scored_count"] == len(sigs)
        assert ctx.llm_failures == 0

    def test_signals_still_unscored_after_every_retry_fail_the_section(self, news):
        news.install(lambda s, _u: {"signals": []} if "SIGNALS TO SCORE" in s else None)
        doc, ctx = self._in_run(news, news.signals())
        assert doc["data"]["scores"] == {}
        assert ctx.llm_failures >= 1

    def test_a_failed_angle_rewrite_keeps_the_fresh_news(self, news):
        sigs = news.signals()
        def short(k):    # under the brief, and unlike the others in phrasing
            w = _OPENERS[k]
            return "%s note on this event: a brief angle for the %s owner." % (w, w.lower())
        rewrites = []

        def model(system, _user):
            if "SIGNALS TO SCORE" in system:
                return {"signals": [_entry(sid, k, sales_angle=short(k))
                                    for k, sid in enumerate(_ids_in(system))]}
            if "rewriting ONLY the sales_angle" in system:
                rewrites.append(1)
                return {"signals": [{"signal_id": "deadbeefcafe", "sales_angle": "x"}]}
            return None

        news.install(model)
        doc, ctx = self._in_run(news, sigs)
        assert rewrites, "the too-short angles were sent for a rewrite"
        assert len(rewrites) == rns.ANSWER_ATTEMPTS * len(sigs), "each asked again once"
        assert ctx.llm_failures == 0
        assert doc["data"]["scored_count"] == len(sigs)
        # The first-pass angle stays, rather than none.
        assert sorted(s["sales_angle"] for s in doc["data"]["scores"].values()) == sorted(
            short(k) for k in range(len(sigs)))

    def test_an_off_target_rewrite_answered_on_the_second_try_is_used(self, news):
        sig = news.signals()[0]
        sid = sig["signal_id"]
        rewrites = []

        def model(system, _user):
            if "SIGNALS TO SCORE" in system:
                return {"signals": [_entry(sid, 0, sales_angle="Too short an angle.")]}
            if "rewriting ONLY the sales_angle" in system:
                rewrites.append(1)
                if len(rewrites) == 1:
                    return {"signals": []}
                return {"signals": [{"signal_id": sid, "sales_angle": _angle(1)}]}
            return None

        news.install(model)
        doc, ctx = self._in_run(news, [sig])
        assert len(rewrites) == 2
        assert doc["data"]["scores"][sid]["sales_angle"] == _angle(1)
        assert ctx.llm_failures == 0

    def test_failures_not_counted_still_counts_the_calls(self):
        ctx = run_context.RunContext(account_id="a", node_id="n")
        with run_context.active(ctx):
            with run_context.failures_not_counted():
                run_context.note_llm(failed=True)
            run_context.note_llm(failed=True)
        assert ctx.llm_calls == 2
        assert ctx.llm_failures == 1


class TestTranslationFaults:

    def test_bad_rows_never_land_on_another_item(self, monkeypatch):
        texts = ["アクメ決算2026年", "トヨタ新工場", "日本経済新聞"]

        def model(_s, _u):
            return {"items": [
                {"i": 0, "english": "Acme results"},            # drops 2026
                {"i": 1, "english": "トヨタ"},                   # not English
                {"i": 2, "english": "Nikkei"},
                {"i": 9, "english": "Out of range"},
                {"i": "x", "english": "Bad index"},
                {"i": 2, "english": ""},                        # empty duplicate
                "junk",
            ]}

        monkeypatch.setattr(translate, "generate_gpt4o_json_completion", model)
        got = translate.to_english(texts, FakeDb(), "headline")
        assert got == {"日本経済新聞": "Nikkei"}

    @pytest.mark.parametrize("answer", [None, {}, {"items": "x"}, {"items": [1, 2]}])
    def test_total_failure_keeps_the_original(self, monkeypatch, answer):
        monkeypatch.setattr(translate, "generate_gpt4o_json_completion",
                            lambda *_a: answer)
        assert translate.one("トヨタ新工場", FakeDb(), "headline") == "トヨタ新工場"

    def test_overlong_translation_is_rejected(self):
        assert translate.acceptable("トヨタ", "Toyota " + "x" * 400, "headline") == ""


# ===========================================================================
# 2. Opportunity Map
# ===========================================================================

OPP_DATA = {
    "firmographics": [{"Business Description": "Acme Corp builds industrial pumps.",
                       "Number Of Employees Range": "1,001 - 5,000",
                       "Linkedin Industry Category": "Machinery"}],
    "technographics": [{"Full Tech Stack": "Zoom, Microsoft Teams, Slack"}],
    "google_news": [{"event_headline": "Acme expands hybrid working policy for staff",
                     "event_date": _days_ago(20),
                     "event_url": "https://www.reuters.com/acme-hybrid"}],
}

ROSTER = [{"contact_id": "c-1", "full_name": "Jane Roe",
           "title": "Head of Workplace Collaboration",
           "normalized_department": "Information Technology",
           "influence_type": "Decision Maker", "stakeholder_score": 80}]

POLY_CAPABILITY = ("Poly video bars, headsets and room systems from HP are certified "
                   "for Microsoft Teams and Zoom and are managed centrally through "
                   "the Poly Lens service.")
POLY_INFERENCE = (
    "The installed technology stack lists Microsoft Teams and Zoom, and the news "
    "reports that Acme expands hybrid working policy for staff. Taken together this "
    "may indicate that meeting spaces and personal collaboration devices are worth "
    "exploring with the workplace team. Poly Collaboration may be relevant to this "
    "opportunity, subject to confirming how many rooms and hybrid workers are in "
    "scope, which the supplied data does not state. A seller could open by asking "
    "how meeting rooms are equipped today and what the hybrid policy changes for "
    "staff who split time between home and office.")
POLY_OWNER = ("The Head of Workplace Collaboration would be weighing how room and "
              "headset choices fit the hybrid policy.")


def _poly_play(**over):
    play = {"play_key": "poly", "title": "Hybrid meeting rooms",
            "account_evidence": [
                {"quote": "Acme expands hybrid working policy for staff",
                 "statement": "A hybrid working policy is expanding."},
                {"quote": "Microsoft Teams", "statement": "Teams is installed."}],
            "hp_capability": POLY_CAPABILITY, "inference": POLY_INFERENCE,
            "hp_products": ["Poly Collaboration"], "proof_point": None,
            "source_url": None, "timing_note": None, "owner_angle": POLY_OWNER}
    play.update(over)
    return play


@pytest.fixture
def opp_run(monkeypatch):
    """Runs the plays generator with `answers` scripted for each model call."""
    def go(answers, data=OPP_DATA, roster=ROSTER, existing=None):
        db = FakeDb()
        account_id = str(ObjectId())
        db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme Corp"})
        monkeypatch.setattr(opp, "get_db", lambda: db)
        monkeypatch.setattr(datasets, "get_db", lambda: db)
        monkeypatch.setattr(opp, "_read_dataset_records",
                            lambda _a, key: [dict(r) for r in data.get(key, [])])
        monkeypatch.setattr(opp, "read_dataset_rows", lambda *_a, **_k: [])
        monkeypatch.setattr(opp, "account_domain", lambda _a: "acme.example")

        def widget(_a, key, **_k):
            if key == "stakeholder_contacts_grid":
                return {"data": {"contacts": roster}}
            if key == "opportunity_narrative_plays":
                return existing
            return None

        monkeypatch.setattr(opp.widget_store, "get", widget)
        script = list(answers)
        calls = []

        def model(system, user):
            calls.append((system, user))
            answer = script[0] if len(script) == 1 else script.pop(0)
            return answer() if callable(answer) else answer

        monkeypatch.setattr(opp, "generate_gpt4o_json_completion", model)
        payload = opp.generate_opportunity_map_plays_with_gpt4o(account_id)
        return SimpleNamespace(payload=payload, calls=calls, db=db)
    return go


def _plays(payload):
    return (payload.get("data") or {}).get("opportunity_plays") or []


class TestOpportunityMapFaults:

    def test_a_clean_play_publishes_with_roster_contacts_only(self, opp_run):
        play = _poly_play(entry_path={"target_contacts": [
            {"contact_id": "fake", "name": "Invented Person", "title": "CEO"}]})
        run = opp_run([{"opportunity_plays": [play]}])
        plays = _plays(run.payload)
        assert run.payload["status"] == "available"
        assert [p["play_key"] for p in plays] == ["poly"]
        contacts = plays[0]["entry_path"]["target_contacts"]
        assert {c["contact_id"] for c in contacts} <= {c["contact_id"] for c in ROSTER}
        assert run.payload["data"]["total_plays_count"] == len(plays)

    @pytest.mark.parametrize("answer", [
        None, {}, {"opportunity_plays": None}, {"opportunity_plays": "poly"},
        {"plays": [_poly_play()]}, {"opportunity_plays": [None, 3, "x"]}])
    def test_no_usable_answer_publishes_nothing_invented(self, opp_run, answer):
        run = opp_run([answer], roster=[])
        assert _plays(run.payload) == []
        assert run.payload["status"] == "pending"
        assert run.payload["data"]["total_plays_count"] == 0

    def test_no_usable_answer_keeps_previous_plays_on_legacy_path(self, opp_run):
        previous = {"status": "available", "data": {"opportunity_plays": [{"x": 1}]}}
        run = opp_run([None], existing=previous)
        assert run.payload is previous

    def test_hallucinated_quote_drops_the_play(self, opp_run):
        play = _poly_play(account_evidence=[
            {"quote": "Acme signed a 5,000-seat Poly deal last week", "statement": "x"}])
        run = opp_run([{"opportunity_plays": [play]}])
        assert _plays(run.payload) == []
        assert any("unverified quote" in d for d in run.payload["data"]["dropped"])

    def test_hallucinated_number_is_rewritten_or_dropped_never_published(self, opp_run):
        bad = _poly_play(inference=POLY_INFERENCE + " Acme runs 4,812 meeting rooms.")
        run = opp_run([{"opportunity_plays": [bad]}])     # every retry repeats it
        assert _plays(run.payload) == []
        assert any("unsourced number" in d for d in run.payload["data"]["dropped"])
        assert len(run.calls) == 3, "first pass plus the two bounded retries"

        fixed = opp_run([{"opportunity_plays": [bad]}, {"opportunity_plays": [_poly_play()]}])
        assert [p["play_key"] for p in _plays(fixed.payload)] == ["poly"]
        assert "4,812" not in json.dumps(fixed.payload["data"]["opportunity_plays"])

    def test_hallucinated_url_is_stripped(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(
            source_url="https://made-up.example/acme-poly",
            proof_point="See https://made-up.example/acme-poly for details.")]}])
        play = _plays(run.payload)[0]
        assert play["source_url"] is None
        assert "made-up.example" not in (play["proof_point"] or "")

    def test_invented_hp_product_is_dropped_and_recorded(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(
            hp_products=["Poly Collaboration", "Acme TurboRoom 9000"])]}])
        play = _plays(run.payload)[0]
        assert play["hp_products"] == ["Poly Collaboration"]
        assert run.payload["data"]["grounding_report"]["enum_rejected"]

    def test_duplicate_play_in_one_answer_is_merged_not_doubled(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(), _poly_play(title="Again")]}])
        plays = _plays(run.payload)
        assert len(plays) == 1
        assert plays[0].get("merged_from") == 2

    def test_empty_text_fields_are_not_published(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(title=""),
                                              _poly_play(play_key="  ")]}])
        assert _plays(run.payload) == []

    def test_very_long_prose_is_published_only_after_its_rewrites(self, opp_run):
        long_play = _poly_play(inference=POLY_INFERENCE + " " + _words(2000, "detail"))
        run = opp_run([{"opportunity_plays": [long_play]}])
        assert len(run.calls) == 3
        assert any("words; the brief is" in d for d in run.payload["data"]["dropped"])

    def test_zero_inputs_publish_nothing(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play()]}], data={}, roster=[])
        assert _plays(run.payload) == []
        assert run.payload["status"] == "pending"

    def test_malformed_then_valid_end_to_end(self, opp_run, provider, monkeypatch):
        provider("{\"opportunity_plays\": [", json.dumps({"opportunity_plays": [_poly_play()]}))
        run = opp_run([lambda: llm.generate_gpt4o_json_completion("s", "u")])
        assert [p["play_key"] for p in _plays(run.payload)] == ["poly"]

    def test_an_unknown_play_key_is_not_published(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(
            play_key="quantum", title="Quantum computing refresh")]}])
        assert "quantum" not in {p["play_key"] for p in _plays(run.payload)}

    def test_a_wrong_typed_evidence_list_drops_one_play_not_the_feature(self, opp_run):
        run = opp_run([{"opportunity_plays": [_poly_play(account_evidence=5),
                                              _poly_play()]}])
        assert [p["play_key"] for p in _plays(run.payload)] == ["poly"]


# ---------------------------------------------------------------------------
# Technographic map narrative (map_narrative.py)
# ---------------------------------------------------------------------------

def _categories():
    return [
        {"category_key": "collab", "category_name": "Collaboration",
         "hp_relationship_label": "Complement",
         "vendors": [{"vendor_name": "Zoom", "description": "Video meetings"},
                     {"vendor_name": "Slack", "description": "Chat"}]},
        {"category_key": "pcs", "category_name": "PC/Laptop Brands",
         "hp_relationship_label": "Compete",
         "vendors": [{"vendor_name": "Dell", "description": "PCs"}]},
    ]


GOOD_MEANING = ("Zoom is detected in this estate. " + _words(75, "positioning")).strip()


class TestMapNarrativeFaults:

    @pytest.mark.parametrize("answer", [None, {}, {"categories": "x"},
                                        {"categories": None}])
    def test_no_usable_answer_leaves_fields_absent(self, monkeypatch, answer):
        monkeypatch.setattr(mn, "generate_gpt4o_json_completion", lambda *_a: answer)
        cats = _categories()
        out = mn.generate_map_narrative(cats, ["Zoom", "Slack", "Dell"], "Acme")
        assert out["generated"] == 0 and out["strategic_read"] is None
        assert all("what_it_means" not in c for c in cats)
        assert all("hp_play" not in v for c in cats for v in c["vendors"])

    def test_unknown_ids_and_invented_products_never_attach(self, monkeypatch):
        answer = {"strategic_read": "Collaboration complements HP.",
                  "categories": [
                      {"category_key": "collab", "what_it_means": GOOD_MEANING,
                       "vendors": [
                           {"vendor_name": "zoom ", "hp_product": "Poly Collaboration",
                            "play_text": "Poly devices are certified for Zoom."},
                           {"vendor_name": "Teams", "hp_product": "Poly Collaboration",
                            "play_text": "Not detected, must not attach."},
                           {"vendor_name": "Slack", "hp_product": "Acme TurboChat",
                            "play_text": "Invented product."}]},
                      {"category_key": "ghost", "what_it_means": GOOD_MEANING},
                      {"category_key": "pcs", "what_it_means": "",
                       "vendors": [{"vendor_name": "Dell", "hp_product": "HP Elite",
                                    "play_text": "Elite is 50% faster than Dell."}]}]}
        monkeypatch.setattr(mn, "generate_gpt4o_json_completion", lambda *_a: answer)
        cats = _categories()
        out = mn.generate_map_narrative(cats, ["Zoom", "Slack", "Dell"], "Acme")
        collab, pcs = cats
        assert collab["what_it_means"] == GOOD_MEANING
        assert collab["vendors"][0]["hp_play"]["product"] == "Poly Collaboration"
        assert "hp_play" not in collab["vendors"][1], "invented HP line"
        assert "what_it_means" not in pcs, "empty text is not published"
        assert "hp_play" not in pcs["vendors"][0], "unsourced figure"
        assert "pcs.Dell.play_text" in out["rejected"]
        # strategic read + one meaning + one vendor play
        assert out["generated"] == 3

    def test_a_wrong_typed_vendor_list_skips_that_category(self, monkeypatch):
        answer = {"categories": [
            {"category_key": "collab", "what_it_means": GOOD_MEANING, "vendors": 5},
            {"category_key": "pcs", "what_it_means": GOOD_MEANING, "vendors": []}]}
        monkeypatch.setattr(mn, "generate_gpt4o_json_completion", lambda *_a: answer)
        cats = _categories()
        out = mn.generate_map_narrative(cats, ["Zoom", "Slack", "Dell"], "Acme")
        assert out["generated"] == 2

    def test_a_retry_about_another_category_is_not_attached(self, monkeypatch):
        short = "Zoom is detected; Poly complements it."
        other = "Dell is detected in the PC estate. " + _words(75, "compete")
        answers = [{"categories": [{"category_key": "collab", "what_it_means": short}]},
                   {"categories": [{"category_key": "pcs", "what_it_means": other}]}]
        monkeypatch.setattr(mn, "generate_gpt4o_json_completion",
                            lambda *_a: answers.pop(0))
        cats = _categories()
        mn.generate_map_narrative(cats, ["Zoom", "Slack", "Dell"], "Acme")
        assert cats[0]["what_it_means"] == short


# ===========================================================================
# 3. Executive Dashboard
# ===========================================================================

PARAGRAPH = (
    "Acme Corporation designs and manufactures industrial pumps and valves for "
    "the water and energy sectors. It reported revenue of 486 billion yen and "
    "operates plants across Japan, Asia and Europe. The company is expanding its "
    "digital monitoring services and investing in automation of its factories "
    "and service centres worldwide.")


class _BulletsDb(dict):
    """Just enough Mongo for the bullets cache (nothing cached)."""

    def __getitem__(self, _name):
        return self

    def find_one(self, *_a, **_k):
        return None


def _bullets(monkeypatch, answer):
    monkeypatch.setattr(ed, "generate_gpt4o_json_completion", lambda *_a, **_k: answer)
    return ed._description_points(_BulletsDb(), "acct", PARAGRAPH,
                                  {"Business Description": PARAGRAPH})


class TestExecutiveSummaryBulletFaults:

    @pytest.mark.parametrize("answer", [None, {}, {"points": None}, {"points": []},
                                        {"points": ["", "  ", ""]}])
    def test_no_usable_answer_shows_the_paragraph(self, monkeypatch, answer):
        points, basis = _bullets(monkeypatch, answer)
        assert points == []
        assert "paragraph is shown instead" in basis

    def test_a_partial_answer_below_the_minimum_falls_back(self, monkeypatch):
        points, _basis = _bullets(monkeypatch, {"points": ["Designs pumps.", "Has plants."]})
        assert points == []

    def test_extra_bullets_are_capped(self, monkeypatch):
        points, _basis = _bullets(monkeypatch, {"points": ["Point %s." % w for w in
                                                           "abcdefgh"]})
        assert len(points) == ed.DESCRIPTION_POINTS_MAX

    def test_hallucinated_figure_holds_bullets_back(self, monkeypatch):
        points, basis = _bullets(monkeypatch, {"points": [
            "Designs pumps.", "Revenue grew 31% last year.", "Plants in Asia."]})
        assert points == [] and "31%" in basis

    def test_malformed_then_valid_end_to_end(self, monkeypatch, provider):
        provider('{"points": [', json.dumps({"points": ["Designs pumps.",
                                                        "Plants in Asia.",
                                                        "Expands monitoring."]}))
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion",
                            llm.generate_gpt4o_json_completion)
        points, _basis = ed._description_points(_BulletsDb(), "acct", PARAGRAPH,
                                                {"Business Description": PARAGRAPH})
        assert len(points) == 3

    def test_a_string_instead_of_a_list_is_not_split_into_characters(self, monkeypatch):
        points, _basis = _bullets(monkeypatch, {"points": "Acme designs pumps."})
        assert all(len(p) > 1 for p in points)

    def test_a_null_bullet_is_not_published_as_none(self, monkeypatch):
        points, _basis = _bullets(monkeypatch, {"points": [
            "Designs pumps.", None, "Plants in Asia.", "Expands monitoring."]})
        assert "None" not in points


# ---------------------------------------------------------------------------
# Strategic priorities (dashboard/priorities.py)
# ---------------------------------------------------------------------------

ACCT = "acct-1"


@pytest.fixture
def evidence_db(monkeypatch):
    db = FakeDb()
    rows = [
        ("doc_a#c1", "Acme is investing in factory automation across its plants.", "2025"),
        ("doc_a#c2", "Automation of service centres continues in 2025.", "2025"),
        ("doc_b#c1", "Acme expands digital monitoring services for customers.", None),
        ("doc_c#c1", "Acme opened a sustainability office in Osaka.", None),
    ]
    for eid, text, period in rows:
        row = {"account_id": ACCT, "index": pr.INDEX, "evidence_id": eid,
               "doc_id": eid.split("#")[0], "dataset": "compliance_filings",
               "field": "narrative", "source_text": text}
        if period:
            row["filing_period"] = period
        db[ev.COLLECTION].insert_one(row)
    monkeypatch.setattr(ev, "get_db", lambda: db)
    monkeypatch.setattr(pr, "get_db", lambda: db)
    return db


def _candidate(title, ids, theme="other"):
    return {"title": title, "theme": theme, "why_now": "Stated in filings.",
            "evidence_ids": ids}


class TestPriorityResolutionFaults:

    def test_unknown_and_foreign_ids_are_dropped_and_counted(self, evidence_db):
        kept, dropped, invalid = pr._resolve_priorities(ACCT, [
            _candidate("Factory automation", ["doc_a#c1", "doc_zz#c9", "not-an-id"]),
            _candidate("Invented priority", ["doc_zz#c1"]),
            _candidate("", ["doc_a#c1"]),
            "junk", None,
        ])
        assert [p["title"] for p in kept] == ["Factory automation"]
        assert [s["evidence_id"] for s in kept[0]["sources"]] == ["doc_a#c1"]
        assert kept[0]["invalid_evidence_ids"] == ["not-an-id", "doc_zz#c9"]
        assert dropped[0]["reason"] == "no resolvable account evidence"
        assert invalid == 3

    def test_off_topic_evidence_is_not_attached(self, evidence_db):
        kept, dropped, _ = pr._resolve_priorities(ACCT, [
            _candidate("Strengthen sustainability", ["doc_a#c1"])])
        assert kept == []
        assert "does not mention" in dropped[0]["reason"]

    def test_wrong_types_in_a_candidate_do_not_publish_garbage(self, evidence_db):
        kept, _dropped, _ = pr._resolve_priorities(ACCT, [
            _candidate("Factory automation", "doc_a#c1"),       # string, not list
            _candidate(["Factory", "automation"], ["doc_a#c1"])])
        # A bare string id is read character by character and resolves nothing;
        # a list title is stringified. Neither crashes.
        assert all(isinstance(p["title"], str) for p in kept)

    def test_duplicate_ids_count_once(self, evidence_db):
        kept, _d, _i = pr._resolve_priorities(ACCT, [
            _candidate("Factory automation", ["doc_a#c1"] * 4),
            _candidate("Automation of service centres", ["doc_a#c1", "doc_a#c2"])])
        by_title = {p["title"]: p for p in kept}
        fa = by_title["Factory automation"]
        assert fa["measures"]["support_count"] == 1
        assert len(fa["sources"]) == 1

    def test_a_non_list_evidence_ids_drops_only_that_candidate(self, evidence_db):
        kept, _d, _i = pr._resolve_priorities(ACCT, [
            _candidate("Factory automation", 7),
            _candidate("Digital monitoring services", ["doc_b#c1"])])
        assert [p["title"] for p in kept] == ["Digital monitoring services"]


def _priority(sources_text, title="Factory automation"):
    return {"title": title, "theme": "other",
            "sources": [{"source_text": t, "evidence_id": "doc_a#c%d" % i}
                        for i, t in enumerate(sources_text, 1)],
            "measures": {"support_count": len(sources_text), "distinct_sections": 1}}


GOOD_POINTS = [
    "Acme is investing in factory automation across its plants in Japan and Europe.",
    "Automation of service centres continues in 2025 according to the filing.",
    "HP Elite PCs can support plant engineers working across automated sites.",
]


class TestPriorityDescriptionFaults:

    @pytest.mark.parametrize("answer", [None, {}, {"points": []}, {"points": ["", " "]},
                                        RuntimeError("boom")])
    def test_failure_uses_the_python_fallback(self, monkeypatch, answer):
        def model(*_a):
            if isinstance(answer, Exception):
                raise answer
            return answer
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", model)
        out = pr._describe(_priority([PARAGRAPH]), ["HP Elite PCs: business PCs"], "Acme")
        assert out["written_by"] == "python"
        assert out["rejected_reason"] == "empty"
        assert "evidenced by 1 source sentence" in out["text"]

    def test_invented_hp_product_is_rejected(self, monkeypatch):
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", lambda *_a: {
            "points": [*GOOD_POINTS[:2], "HP Quantum Fabric would suit the plants."]})
        out = pr._describe(_priority([PARAGRAPH, "Automation in 2025."]),
                           ["HP Elite PCs: business PCs"], "Acme")
        assert out["written_by"] == "python"
        assert "Quantum" in out["rejected_reason"]

    def test_unsourced_figure_is_rejected(self, monkeypatch):
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", lambda *_a: {
            "points": [*GOOD_POINTS[:2], "Acme will spend 777 million on robots."]})
        out = pr._describe(_priority([PARAGRAPH, "Automation continues in 2025."]),
                           [], "Acme")
        assert out["written_by"] == "python"
        assert "777" in out["rejected_reason"]

    def test_very_long_answer_is_rejected(self, monkeypatch):
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", lambda *_a: {
            "points": [_words(200, "automation") + "."]})
        out = pr._describe(_priority([PARAGRAPH]), [], "Acme")
        assert out["written_by"] == "python"
        assert "longer than the brief" in out["rejected_reason"]

    def test_a_figure_that_is_only_a_substring_of_a_year_is_rejected(self):
        ok, _why = pr._validate_description(
            "Acme grew automation revenue 20% in the year.",
            "Automation of service centres continues in 2025.", "")
        assert ok is False

    def test_a_non_list_points_answer_falls_back(self, monkeypatch):
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion",
                            lambda *_a: {"points": 7})
        out = pr._describe(_priority([PARAGRAPH]), [], "Acme")
        assert out["written_by"] == "python"


@pytest.fixture
def dashboard(monkeypatch, evidence_db):
    monkeypatch.setattr(pr.index_state, "get",
                        lambda *_a: {"status": pr.index_state.READY})
    monkeypatch.setattr(pr.query, "ask", lambda *_a, **_k: SimpleNamespace(
        context="[doc_a#c1] ...", mode="local", workspace="w", stale=False))
    monkeypatch.setattr(pr.widget_store, "get", lambda *_a, **_k: None)
    monkeypatch.setattr(pr.cs, "cited_above", lambda *_a, **_k: set())
    monkeypatch.setattr(pr.cs, "allocate", lambda *_a, **_k: None)

    def install(candidates, news_candidates=None, description=None):
        def model(system, user):
            if system == pr.CANDIDATE_SYSTEM:
                return (news_candidates if "recent events" in user else candidates)
            return description
        monkeypatch.setattr(pr, "generate_gpt4o_json_completion", model)
    return install


class TestDashboardEndToEnd:

    @pytest.mark.parametrize("answer", [None, {}, {"priorities": "x"},
                                        {"priorities": [_candidate("Ghost", ["zz#c1"])]}])
    def test_total_failure_is_an_error_not_an_empty_success(self, dashboard, answer):
        dashboard(answer, news_candidates=answer)
        with pytest.raises(pr.DashboardError):
            pr.generate_dashboard_intelligence(ACCT)

    def test_partial_answer_publishes_only_evidenced_priorities(self, dashboard):
        dashboard({"priorities": [
            _candidate("Factory automation", ["doc_a#c1", "doc_a#c2"]),
            _candidate("Invented priority", ["doc_zz#c1"])]},
            news_candidates={"priorities": [
                _candidate("Digital monitoring services", ["doc_b#c1", "bad"])]},
            description=None)
        payload = pr.generate_dashboard_intelligence(ACCT)
        data = payload["data"]
        titles = [p["title"] for p in data["priorities"]]
        assert titles == ["Factory automation", "Digital monitoring services"]
        assert data["priority_count"] == len(data["priorities"])
        assert data["generation"]["news_fallback_used"] is True
        assert data["generation"]["invalid_evidence_count"] == 2
        assert all(p["description"]["written_by"] == "python" for p in data["priorities"])
        assert len(data["generation"]["descriptions_rejected"]) == 2
        assert data["executive_summary"]["assembled_by"] == "python"


# ===========================================================================
# 4. Tech Landscape recommendations
# ===========================================================================

def _rec_candidate(rule_id, family="HP Elite / Pro PCs"):
    return {"rule_id": rule_id, "rule_condition": "Windows estate detected",
            "hp_family": family, "device_type": "notebook",
            "account_evidence": ["Microsoft Windows 10 detected"],
            "evidence_tier": {"tier": "Opportunity", "permitted_language": "x"},
            "evidence_ids": ["e1"], "confidence": rec.CONFIDENCE_CONFIRMED,
            "approved_facts": [{"text": "HP EliteBook 840 G11 offers up to 64 GB memory.",
                                "qualifiers": ["up to"], "conditions": []}]}


@pytest.fixture
def recs(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(rec, "get_db", lambda: db)
    monkeypatch.setattr(rec, "knowledge_version", lambda _db: "k1")
    monkeypatch.setattr(rec, "account_data_as_of", lambda _a: {"as_of": "2026-09-01"})
    monkeypatch.setattr(rec, "_account_evidence", lambda _db, _a: {
        "texts": ["Microsoft Windows 10 detected", "Acme has 1,001 - 5,000 employees"],
        "company_name": "Acme", "hq_location": "US", "tech_stack": [],
        "categories": [], "triggers": []})
    monkeypatch.setattr(rec.widget_store, "get", lambda *_a, **_k: None)

    def run(answer, candidates=None):
        cands = candidates or [_rec_candidate("1"), _rec_candidate("2")]
        monkeypatch.setattr(rec, "_rulebook_candidates",
                            lambda *_a: ([dict(c) for c in cands], [], "r1"))
        monkeypatch.setattr(rec, "generate_gpt4o_json_completion", lambda *_a: answer)
        return rec.generate_hp_recommendations("acct")
    return run


def _prose(rule_id, **over):
    out = {"rule_id": rule_id,
           "rationale": "Microsoft Windows 10 detected creates a relevant conversation.",
           "why_this_product": "HP EliteBook 840 G11 offers up to 64 GB memory.",
           "discovery_question": "How is the Windows estate managed today?"}
    out.update(over)
    return out


class TestRecommendationFaults:

    @pytest.mark.parametrize("answer", [None, {}, {"recommendations": "x"},
                                        {"recommendations": [None, 5]}])
    def test_failure_keeps_python_decided_cards_with_no_prose(self, recs, answer):
        payload = recs(answer)
        cards = payload["data"]["recommendations"]
        assert payload["status"] == "available"
        assert payload["data"]["recommendations_count"] == len(cards) == 2
        assert all(c["rationale"] is None and c["why_this_product"] is None
                   and c["discovery_question"] is None for c in cards)

    def test_prose_attaches_only_to_its_own_rule(self, recs):
        payload = recs({"recommendations": [
            _prose(1),                                  # int id matches "1"
            _prose("99", rationale="Ghost rule."),      # unknown id
            {"rationale": "No id at all."}]})
        by_id = {c["rule_id"]: c for c in payload["data"]["recommendations"]}
        assert by_id["1"]["rationale"].startswith("Microsoft Windows 10")
        assert by_id["2"]["rationale"] is None
        assert "Ghost" not in json.dumps(payload["data"]["recommendations"])

    def test_hallucinated_account_figure_drops_account_prose(self, recs):
        payload = recs({"recommendations": [_prose(
            "1", rationale="Acme runs 12,345 Windows laptops.")]})
        card = payload["data"]["recommendations"][0]
        assert card["rationale"] is None and card["discovery_question"] is None
        assert card["why_this_product"] is not None, "product prose judged on its own"

    def test_hallucinated_product_figure_drops_product_prose(self, recs):
        payload = recs({"recommendations": [_prose(
            "1", why_this_product="HP EliteBook 840 G11 offers up to 128 GB memory.")]})
        card = payload["data"]["recommendations"][0]
        assert card["why_this_product"] is None
        assert card["rationale"] is not None

    def test_hallucinated_url_in_product_prose_is_dropped(self, recs):
        payload = recs({"recommendations": [_prose(
            "1", why_this_product="HP EliteBook offers business features; see "
                                  "https://hp-deals.example.com/elite-offer")]})
        card = payload["data"]["recommendations"][0]
        assert "hp-deals.example.com" not in (card["why_this_product"] or "")

    def test_no_candidates_means_no_model_call(self, recs, monkeypatch):
        monkeypatch.setattr(rec, "_rulebook_candidates", lambda *_a: ([], [], "r1"))
        monkeypatch.setattr(rec, "generate_gpt4o_json_completion",
                            lambda *_a: pytest.fail("no model call expected"))
        payload = rec.generate_hp_recommendations("acct")
        assert payload["status"] == "pending"
        assert payload["data"]["recommendations_count"] == 0


# ===========================================================================
# 5. Intent helpers
# ===========================================================================

class TestBomboraClassifierFaults:

    def test_total_failure_raises_rather_than_publishing_partial_averages(
            self, monkeypatch):
        monkeypatch.setattr(bhc, "generate_gpt4o_json_completion", lambda *_a: None)
        with pytest.raises(RuntimeError, match="unclassified"):
            bhc.classify_topics(FakeDb(), ["Laptops", "Printers"])

    def test_bad_rows_are_dropped_and_retried(self, monkeypatch):
        answers = [
            {"topics": [
                {"i": 0, "category": bhc.tm.CAT_PC},
                {"i": 5, "category": bhc.tm.CAT_PRINT},       # out of range
                {"i": "1", "category": bhc.tm.CAT_PRINT},     # string index
                {"i": 1, "category": "Printers & Stuff"},     # invented category
                "junk"]},
            {"topics": [{"i": 0, "category": bhc.tm.CAT_PRINT}]},  # retry: Printers
        ]
        calls = []
        monkeypatch.setattr(bhc, "generate_gpt4o_json_completion",
                            lambda _s, u: calls.append(json.loads(u)) or answers.pop(0))
        labels = bhc.classify_topics(FakeDb(), ["Laptops", "Printers"])
        assert labels["laptops"]["category"] == bhc.tm.CAT_PC
        assert labels["printers"]["category"] == bhc.tm.CAT_PRINT
        assert [t["topic"] for t in calls[1]["topics"]] == ["Printers"]

    def test_none_label_is_kept_as_long_tail(self, monkeypatch):
        monkeypatch.setattr(bhc, "generate_gpt4o_json_completion", lambda *_a: {
            "topics": [{"i": 0, "category": "NONE", "reason": "x" * 500}]})
        labels = bhc.classify_topics(FakeDb(), ["Data centre GPUs"])
        assert labels["data centre gpus"]["category"] == bhc.NOT_RELEVANT
        assert len(labels["data centre gpus"]["reason"]) <= 160


class TestIntentSoWhatFaults:

    def _cats(self):
        return [{"category": "PC", "primary": {"score": 70, "stage": "Decision"},
                 "evidence_tier": {"tier": "Conversation Starter"}},
                {"category": "Print", "primary": {"score": 40, "stage": "Research"},
                 "evidence_tier": {"tier": "Context Only"}}]

    @pytest.mark.parametrize("answer", [None, {}, {"categories": "x"},
                                        RuntimeError("boom")])
    def test_failure_is_an_empty_map(self, monkeypatch, answer):
        def model(*_a):
            if isinstance(answer, Exception):
                raise answer
            return answer
        monkeypatch.setattr(ids_mod, "generate_gpt4o_json_completion", model)
        assert ids_mod._so_what("Acme", self._cats()) == {}

    def test_a_retry_about_another_category_is_not_attached(self, monkeypatch):
        pc_short = "PC research suggests a conversation."
        print_text = "Print research " + _words(83, "print")
        answers = [{"categories": [{"category": "PC", "so_what": pc_short}]},
                   {"categories": [{"category": "Print", "so_what": print_text}]}]
        monkeypatch.setattr(ids_mod, "generate_gpt4o_json_completion",
                            lambda *_a: answers.pop(0))
        out = ids_mod._so_what("Acme", self._cats())
        assert out.get("PC") == pc_short
