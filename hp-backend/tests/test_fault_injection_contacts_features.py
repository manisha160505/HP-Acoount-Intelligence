"""Fault injection for the AI features that read the account's contacts.

Stakeholder Map talking points, the Objection Playbook ("could be raised by"),
Content Studio (personas from the stakeholder grid, generation) and the
messaging pillars. Every model call is faked - either the name inside the
feature module, or the provider client under `core/llm.py`, so the JSON retry
and the run-context failure counting are exercised end to end. No network.

What is asserted, per fault:
  * nothing unhandled reaches the caller;
  * output is never attached to a person (contact id, persona, role) other
    than the one it was written for, and invented ids are dropped;
  * a total failure is reported as one (run context failure, pending/empty
    status, deterministic fallback), not published as success;
  * a partial answer keeps the good entries and invents none of the missing.

A test marked xfail(strict=True) is a defect this file found: it stays red
until the production code is fixed, at which point strict xfail turns it into a
failure so the marker is removed.

Run: .venv/bin/python -m pytest tests/test_fault_injection_contacts_features.py -v
"""

import hashlib
import inspect
import json
import os
import re
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

from app.core import llm
from app.services.extractors import (
    content_studio as cstudio,
    objection_playbook as op,
    stakeholder_map as sm,
)
from app.services.extractors.grounding import GroundingReport, build_corpus
from app.services.messaging import pillars
from app.services.regen import context as run_context
from regen_fakes import FakeDb

ACCOUNT = "acct-fault-injection"
TP_KEY = "stakeholder_talking_points"
SM_KEYS = ("stakeholder_contacts_grid", "stakeholder_influence_map", TP_KEY)


# ---------------------------------------------------------------- fake model

class FakeClient:
    """Stands in for the OpenAI SDK client `core/llm.py` talks to.

    `responder(system, user, n)` answers call n (1-based): a str is returned
    as the raw message content, a dict/list is JSON-encoded, an exception is
    raised from the SDK call."""

    def __init__(self, responder):
        self.responder = responder
        self.sent = []
        outer = self

        class _Completions:
            def create(self, **kw):
                outer.sent.append(kw)
                msgs = kw.get("messages") or []
                system = msgs[0]["content"] if msgs else ""
                user = msgs[-1]["content"] if msgs else ""
                answer = outer.responder(system, user, len(outer.sent))
                if isinstance(answer, BaseException):
                    raise answer
                if not isinstance(answer, str):
                    answer = json.dumps(answer)
                msg = SimpleNamespace(content=answer)
                return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=msg)])

        self.chat = SimpleNamespace(completions=_Completions())

    def with_options(self, **_kw):
        return self

    def systems(self):
        return [m["messages"][0]["content"] for m in self.sent]


def use_model(monkeypatch, responder) -> FakeClient:
    client = FakeClient(responder)
    monkeypatch.setattr(llm, "get_openai_client", lambda *_a, **_k: client)
    return client


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any model call a test did not script fails loudly instead of leaving."""
    unexpected = []

    def refuse(system, _user, _n):
        unexpected.append(system[:120])
        return RuntimeError("unscripted model call")

    use_model(monkeypatch, refuse)
    yield unexpected


def make_ctx(account_id, owned, pinned=None):
    ctx = run_context.RunContext(account_id=account_id, node_id="fault-test",
                                 owned=frozenset(owned))
    ctx.pinned_widgets = dict(pinned or {})
    return ctx


# ======================================================== Stakeholder Map

def _row(name, title, dept="IT", level="manager", pid=None, **extra):
    row = {
        "Prospect full_name": name,
        "Prospect job_title": title,
        "Prospect job_department_main": dept,
        "Prospect job_level_main": level,
        "Contact professions_email": "%s@example.com" % name.split()[0].lower(),
    }
    if pid is not False:
        row["Prospect prospect_id"] = pid or name.replace(" ", "_").lower()
    row.update(extra)
    return row


ROSTER = [
    _row("Zoe Abbott", "Chief Information Officer", "IT", "cxo"),
    _row("Ben Ellis", "IT Procurement Manager", "IT", "manager"),
    _row("Cara Doyle", "VP Engineering", "Engineering", "vp"),
    _row("Dana Frost", "Head of End User Services", "IT", "director"),
]

FIRMO = [{"Business Description": "Distributes industrial parts across Europe.",
          "Linkedin Industry Category": "Wholesale",
          "Number Of Employees Range": "1001-5000"}]

ROSTER_LINE = re.compile(r"^- id=(.*?) \| name=(.*?) \| title=(.*?) \|", re.M)


def roster_of(system: str) -> list[tuple[str, str, str]]:
    return ROSTER_LINE.findall(system)


def opener_for(name: str) -> str:
    return ("I would open on %s's own remit and ask how the team plans its device "
            "estate and where the current setup causes friction for staff." % name)


def good_entry(cid, name, **over):
    entry = {"contact_id": cid, "how_to_open": opener_for(name),
             "hp_play_focus": "Account engagement / discovery"}
    entry.update(over)
    return entry


def answer_everyone(system, _user, _n):
    return {"contacts": [good_entry(cid, name) for cid, name, _t in roster_of(system)]}


@pytest.fixture
def stake(monkeypatch):
    db = FakeDb()
    data = {"prospect_contacts": list(ROSTER), "firmographics": FIRMO,
            "technographics": [], "intent_score": [], "google_news": [],
            "news_events": []}
    monkeypatch.setattr(sm, "get_db", lambda: db)
    monkeypatch.setattr("app.database.mongodb.get_db", lambda: db)
    monkeypatch.setattr("app.services.extractors.datasets.get_db", lambda: db)
    monkeypatch.setattr(sm, "_read_dataset_records",
                        lambda _aid, key, **_k: list(data.get(key, [])))
    monkeypatch.setattr(sm.translate, "to_english", lambda *_a, **_k: {})
    monkeypatch.setattr(sm.personas, "read_roles", lambda _aid: [])
    extract = inspect.unwrap(sm.extract_stakeholder_map)

    def run(rows=None, ctx=None):
        if rows is not None:
            data["prospect_contacts"] = list(rows)
        if ctx is None:
            out = extract(ACCOUNT)
        else:
            with run_context.active(ctx):
                out = extract(ACCOUNT)
        return {w["widget_key"]: w for w in out}

    return SimpleNamespace(db=db, data=data, run=run)


def grid_people(widgets) -> dict:
    """contact_id -> full_name, as the grid publishes them."""
    contacts = widgets["stakeholder_contacts_grid"]["data"].get("contacts") or []
    return {c["contact_id"]: c["full_name"] for c in contacts}


class TestStakeholderBaseline:
    def test_each_talking_point_is_keyed_to_the_contact_it_was_written_for(self, stake, monkeypatch):
        client = use_model(monkeypatch, answer_everyone)
        widgets = stake.run()
        people = grid_people(widgets)
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert widgets[TP_KEY]["status"] == "available"
        assert set(tps) == set(people)
        for cid, tp in tps.items():
            assert people[cid] in tp["how_to_open"], "opener joined to the wrong person"
        assert len(client.sent) == 1


class TestStakeholderTotalFailure:
    def test_model_returning_none_publishes_pending_not_available(self, stake, monkeypatch):
        calls = []
        monkeypatch.setattr(sm, "generate_gpt4o_json_completion",
                            lambda *a: calls.append(a) or None)
        widgets = stake.run()
        tp = widgets[TP_KEY]
        assert tp["status"] == "pending"
        assert tp["data"]["talking_points"] == {}
        assert tp["data"]["generated_count"] == 0
        # First pass plus the one bounded retry for the contacts still missing.
        assert len(calls) == 2

    def test_provider_exception_does_not_reach_the_caller(self, stake, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("connection reset"))
        widgets = stake.run()
        assert widgets[TP_KEY]["status"] == "pending"
        assert widgets[TP_KEY]["data"]["talking_points"] == {}

    def test_inside_a_run_a_failed_call_is_counted_so_the_engine_marks_it_degraded(
            self, stake, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("503 from provider"))
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.llm_failures >= 1 and ctx.llm_failures == ctx.llm_calls
        assert ctx.staged[TP_KEY]["status"] == "pending"
        # The roster is deterministic and still published.
        assert ctx.staged["stakeholder_contacts_grid"]["status"] == "available"

    def test_legacy_path_keeps_the_previous_good_result_on_failure(self, stake, monkeypatch):
        use_model(monkeypatch, answer_everyone)
        first = stake.run()[TP_KEY]
        assert first["status"] == "available"
        # Change the evidence so the cache misses, then fail the model.
        stake.data["intent_score"] = [{"Topic": "Endpoint Security", "Composite Score": "70"}]
        monkeypatch.setattr(sm, "generate_gpt4o_json_completion", lambda *_a: None)
        again = stake.run()[TP_KEY]
        assert again["status"] == "available"
        assert again["data"]["talking_points"] == first["data"]["talking_points"]

    def test_failure_notice_does_not_blame_a_missing_key_when_one_exists(self, stake, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("503 from provider"))
        data = stake.run()[TP_KEY]["data"]
        notice = data.get("notice") or ""
        assert "API key" not in notice
        # Client rule: no gap or error wording reaches the client. The empty
        # panel carries no notice; the reason is internal (-> data_gaps).
        assert "notice" not in data
        assert "API key" not in json.dumps(data, default=str)
        assert data["unavailable_reason"]


class TestStakeholderJsonRetry:
    def test_unreadable_json_then_valid_succeeds_on_the_llm_retry(self, stake, monkeypatch):
        def responder(system, user, n):
            if n == 1:
                return '{"contacts": [{"contact_id": "zoe_abbott" "how_to_open": "x"}]}'
            return answer_everyone(system, user, n)

        client = use_model(monkeypatch, responder)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        widgets_ctx = stake.run(ctx=ctx)
        tp = ctx.staged[TP_KEY]
        assert tp["status"] == "available"
        assert set(tp["data"]["talking_points"]) == set(grid_people(widgets_ctx))
        assert len(client.sent) == 2
        assert ctx.llm_failures == 0

    def test_empty_answer_then_valid_succeeds(self, stake, monkeypatch):
        client = use_model(monkeypatch, lambda s, u, n: "" if n == 1 else answer_everyone(s, u, n))
        widgets = stake.run()
        assert widgets[TP_KEY]["status"] == "available"
        assert len(client.sent) == 2

    def test_two_unreadable_answers_count_as_failure_in_a_run(self, stake, monkeypatch):
        use_model(monkeypatch, lambda *_a: '{"contacts": [,,]}')
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.llm_failures >= 1
        assert ctx.staged[TP_KEY]["status"] == "pending"

    @pytest.mark.parametrize("answer", [
        "{}",
        '{"talking_points": []}',
        '{"contacts": "none"}',
        '{"contacts": [{"contact_id": "ghost-1", "how_to_open": "Hello there."}]}',
    ], ids=["empty-object", "wrong-key", "string-not-list", "only-invented-ids"])
    def test_an_unusable_answer_is_reported_as_a_failure(self, stake, monkeypatch, answer):
        use_model(monkeypatch, lambda *_a: answer)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.staged[TP_KEY]["data"]["talking_points"] == {}
        assert ctx.llm_failures > 0, "engine will treat this run as COMPLETE"

    def test_llm_layer_asks_again_after_an_empty_object(self, monkeypatch):
        client = use_model(monkeypatch, lambda _s, _u, n: "{}" if n == 1 else '{"ok": true}')
        assert llm.generate_gpt4o_json_completion("sys", "user") == {"ok": True}
        assert len(client.sent) == 2


    def test_every_entry_rejected_by_a_guard_counts_as_a_failure_in_a_run(
            self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=opener_for(nm)
                                            + " See https://evil.example.com/deal.")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.staged[TP_KEY]["data"]["talking_points"] == {}
        assert ctx.llm_failures == 1 and ctx.llm_calls == 2

    def test_a_usable_answer_counts_no_failure(self, stake, monkeypatch):
        use_model(monkeypatch, answer_everyone)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.llm_failures == 0 and ctx.llm_calls == 1

    def test_a_partial_answer_then_an_unusable_retry_is_one_failure(self, stake, monkeypatch):
        def responder(system, _u, n):
            rows = roster_of(system)
            if n == 1:
                return {"contacts": [good_entry(c, nm) for c, nm, _t in rows[:2]]}
            return {"contacts": [good_entry("ghost", "Ghost")]}

        use_model(monkeypatch, responder)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        stake.run(ctx=ctx)
        assert ctx.staged[TP_KEY]["data"]["generated_count"] == 2
        assert ctx.llm_failures == 1


class TestStakeholderWrongPerson:
    def test_invented_contact_ids_are_dropped(self, stake, monkeypatch):
        def responder(system, _u, _n):
            real = [good_entry(cid, name) for cid, name, _t in roster_of(system)]
            fake = [good_entry("ghost_%d" % i, "Ghost %d" % i) for i in range(3)]
            return {"contacts": fake + real}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(grid_people(widgets))
        assert not any("Ghost" in tp["how_to_open"] for tp in tps.values())

    @pytest.mark.parametrize("mangle", [
        str.upper, lambda s: "id=" + s, lambda s: s.replace("_", " "), lambda s: s + "_x",
    ], ids=["upper", "prefixed", "spaces", "suffixed"])
    def test_a_near_miss_id_is_never_fuzzily_attached(self, stake, monkeypatch, mangle):
        """The model echoes an id slightly wrong. It must not land on a real
        contact - only the exact id the roster supplied counts."""
        def responder(system, _u, n):
            entries = [good_entry(mangle(cid), name) for cid, name, _t in roster_of(system)]
            return {"contacts": entries}

        client = use_model(monkeypatch, responder)
        widgets = stake.run()
        assert widgets[TP_KEY]["data"]["talking_points"] == {}
        assert widgets[TP_KEY]["status"] == "pending"
        assert len(client.sent) == 2

    def test_integer_id_echoed_for_a_numeric_prospect_id_still_matches_exactly(
            self, stake, monkeypatch):
        rows = [_row("Zoe Abbott", "Chief Information Officer", pid="1001"),
                _row("Ben Ellis", "IT Procurement Manager", pid="1002")]

        def responder(system, _u, _n):
            return {"contacts": [good_entry(int(cid), name)
                                 for cid, name, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        widgets = stake.run(rows)
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert tps["1001"]["how_to_open"] == opener_for("Zoe Abbott")
        assert tps["1002"]["how_to_open"] == opener_for("Ben Ellis")

    def test_swapped_names_inside_valid_ids_are_bound_by_id_only(self, stake, monkeypatch):
        """Documents the limit of the guard: the join is by id, so text the
        model wrote about someone else under a valid id is attached to that id.
        Nothing in the code cross-checks the prose against the person."""
        def responder(system, _u, _n):
            rows = roster_of(system)
            names = [n for _c, n, _t in rows]
            return {"contacts": [good_entry(cid, names[(i + 1) % len(names)])
                                 for i, (cid, _n, _t) in enumerate(rows)]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        people = grid_people(widgets)
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(people)
        assert sum(people[c] in tp["how_to_open"] for c, tp in tps.items()) == 0

    def test_duplicate_ids_in_one_answer_produce_one_record_per_contact(self, stake, monkeypatch):
        def responder(system, _u, _n):
            rows = roster_of(system)
            first_id, first_name, _t = rows[0]
            entries = [good_entry(cid, name) for cid, name, _t in rows]
            entries.append(good_entry(first_id, first_name,
                                      how_to_open="A second opener for %s about the "
                                                  "workplace roadmap." % first_name))
            return {"contacts": entries}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        people = grid_people(widgets)
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(people)
        assert widgets[TP_KEY]["data"]["generated_count"] == len(people)
        for cid, tp in tps.items():
            assert people[cid] in tp["how_to_open"]

    def test_the_missing_contact_retry_cannot_rewrite_a_contact_it_was_not_given(
            self, stake, monkeypatch):
        def responder(system, _u, n):
            rows = roster_of(system)
            if n == 1:      # skips the last contact
                return {"contacts": [good_entry(c, nm) for c, nm, _t in rows[:-1]]}
            # The retry roster holds only the skipped contact; the model also
            # rewrites the first contact of the full roster, whose record it
            # was not shown this time.
            return {"contacts": [good_entry(c, nm) for c, nm, _t in rows]
                    + [good_entry("zoe_abbott", "SOMEONE ELSE",
                                  how_to_open="Rewritten without Zoe's record in the prompt.")]}

        client = use_model(monkeypatch, responder)
        widgets = stake.run()
        assert len(roster_of(client.systems()[1])) == 1
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert tps["zoe_abbott"]["how_to_open"] == opener_for("Zoe Abbott")

    def test_kept_talking_points_never_move_to_a_different_person(self, stake, monkeypatch):
        """Fixed (D1): rows without a prospect id used to get a row-position id
        (contact_N), and the kept-on-failure talking points were re-joined by
        that id to whoever then sat in that row. The id is now built from the
        person, so it follows them, not the row."""
        before = [_row("Adam Best", "IT Procurement Manager", pid=False),
                  _row("Ben Ellis", "Head of End User Services", pid=False)]
        use_model(monkeypatch, answer_everyone)
        first = stake.run(before)
        assert sorted(grid_people(first).values()) == ["Adam Best", "Ben Ellis"]
        assert all(re.fullmatch(r"c-[0-9a-f]{12}", cid) for cid in grid_people(first))

        # The file is reloaded with a new person at the top; the model fails.
        after = [_row("Cara Doyle", "Chief Information Officer", pid=False), *before]
        monkeypatch.setattr(sm, "generate_gpt4o_json_completion", lambda *_a: None)
        second = stake.run(after)
        people = grid_people(second)
        for cid, tp in second[TP_KEY]["data"]["talking_points"].items():
            assert people.get(cid) and people[cid] in tp["how_to_open"], (
                "opener %r is shown on %s's card" % (tp["how_to_open"][:40], people.get(cid)))

    def test_the_fallback_id_is_built_from_the_person_like_the_contact_loaders(self):
        """Same formula as scripts/upload_shipping_list_contacts.py `stable_id`,
        so an id written by a loader and one the extractor derives agree."""
        key = "|".join(["acme ltd", "adam best", "adam@example.com", ""])
        want = "c-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
        assert sm.person_contact_id(" Acme  Ltd", "Adam  Best", "Adam@example.com", None) == want

    def test_a_row_without_a_prospect_id_keeps_its_id_when_the_file_is_reordered(
            self, stake, monkeypatch):
        rows = [_row("Adam Best", "IT Procurement Manager", pid=False),
                _row("Ben Ellis", "Head of End User Services", pid=False)]
        use_model(monkeypatch, answer_everyone)
        first = {v: k for k, v in grid_people(stake.run(rows)).items()}
        second = {v: k for k, v in grid_people(stake.run(rows[::-1])).items()}
        assert first == second

    def test_published_talking_points_carry_the_name_they_were_written_for(
            self, stake, monkeypatch):
        use_model(monkeypatch, answer_everyone)
        widgets = stake.run()
        people = grid_people(widgets)
        for cid, tp in widgets[TP_KEY]["data"]["talking_points"].items():
            assert tp["full_name"] == people[cid]

    def test_a_kept_talking_point_is_dropped_when_its_id_now_names_someone_else(
            self, stake, monkeypatch):
        use_model(monkeypatch, answer_everyone)
        stake.run([_row("Adam Best", "IT Procurement Manager", pid="p1"),
                   _row("Ben Ellis", "Head of End User Services", pid="p2")])
        # The vendor reissues p1 to a different person; the model then fails.
        monkeypatch.setattr(sm, "generate_gpt4o_json_completion", lambda *_a: None)
        second = stake.run([_row("Zed Other", "IT Procurement Manager", pid="p1"),
                            _row("Ben Ellis", "Head of End User Services", pid="p2")])
        tps = second[TP_KEY]["data"]["talking_points"]
        assert list(tps) == ["p2"]
        assert second[TP_KEY]["data"]["generated_count"] == 1
        # And it is what is stored, not only what was returned.
        stored = stake.db["account_widgets"].find_one({"widget_key": TP_KEY})
        assert list(stored["data"]["talking_points"]) == ["p2"]

    def test_legacy_entries_without_a_name_are_kept_only_under_a_person_id(self):
        contacts = [{"contact_id": "contact_3", "full_name": "Cara Doyle"},
                    {"contact_id": "p-77", "full_name": "Eve Blank"},
                    {"contact_id": "c-0123456789ab", "full_name": "Adam Best"}]
        old = {"contact_3": {"how_to_open": "written for whoever sat in row 3"},
               "p-77": {"how_to_open": "written for p-77"},
               "c-0123456789ab": {"how_to_open": "x", "full_name": "Ben Ellis"},
               "gone": {"how_to_open": "no longer on the roster", "full_name": "Gone"}}
        assert list(sm.talking_points_for_current_contacts(old, contacts)) == ["p-77"]

    def test_duplicate_prospect_ids_in_the_file_collapse_onto_one_card_id(self, stake, monkeypatch):
        """Two different people delivered under one prospect id share one
        contact_id, and so one talking point. Documented, not a model fault:
        the 21 Oct loader (scripts/upload_shipping_list_contacts.py) suffixes
        duplicates; the extractor itself does not check."""
        rows = [_row("Zoe Abbott", "Chief Information Officer", pid="dup"),
                _row("Ben Ellis", "IT Procurement Manager", pid="dup")]
        use_model(monkeypatch, answer_everyone)
        widgets = stake.run(rows)
        ids = [c["contact_id"] for c in widgets["stakeholder_contacts_grid"]["data"]["contacts"]]
        assert ids == ["dup", "dup"]
        assert list(widgets[TP_KEY]["data"]["talking_points"]) == ["dup"]


class TestStakeholderPartialAnswers:
    def test_partial_answer_keeps_good_entries_and_asks_only_for_the_rest(self, stake, monkeypatch):
        def responder(system, _u, n):
            rows = roster_of(system)
            keep = rows[:2] if n == 1 else rows
            return {"contacts": [good_entry(c, nm) for c, nm, _t in keep]}

        client = use_model(monkeypatch, responder)
        widgets = stake.run()
        people = grid_people(widgets)
        assert len(roster_of(client.systems()[0])) == 4
        assert len(roster_of(client.systems()[1])) == 2
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(people)

    def test_missing_contacts_are_left_missing_not_fabricated(self, stake, monkeypatch):
        def responder(system, _u, n):
            rows = roster_of(system)
            if n == 1:
                return {"contacts": [good_entry(c, nm) for c, nm, _t in rows[:2]]}
            return RuntimeError("timeout")

        use_model(monkeypatch, responder)
        ctx = make_ctx(ACCOUNT, SM_KEYS)
        widgets = stake.run(ctx=ctx)
        tp = ctx.staged[TP_KEY]
        people = grid_people(widgets)
        assert tp["status"] == "available"
        assert tp["data"]["generated_count"] == 2
        for cid, rec in tp["data"]["talking_points"].items():
            assert people[cid] in rec["how_to_open"]
        # The failed retry is counted, so the engine marks this run degraded.
        assert ctx.llm_failures == 1

    @pytest.mark.parametrize("blank", ["", "   ", None, "\n\t"])
    def test_entries_with_no_opener_are_dropped(self, stake, monkeypatch, blank):
        def responder(system, _u, n):
            rows = roster_of(system)
            return {"contacts": [good_entry(c, nm, how_to_open=blank) for c, nm, _t in rows]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        assert widgets[TP_KEY]["data"]["talking_points"] == {}
        assert widgets[TP_KEY]["status"] == "pending"


class TestStakeholderWrongTypes:
    @pytest.mark.parametrize("answer", [
        {"contacts": ["zoe_abbott", "ben_ellis"]},
        {"contacts": [None, 3, ["zoe_abbott"]]},
        {"contacts": {"zoe_abbott": {"how_to_open": "x"}}},
    ], ids=["list-of-strings", "junk-items", "dict-not-list"])
    def test_malformed_shapes_publish_nothing_and_do_not_crash(self, stake, monkeypatch, answer):
        use_model(monkeypatch, lambda *_a: answer)
        widgets = stake.run()
        assert widgets[TP_KEY]["data"]["talking_points"] == {}

    def test_pain_points_as_a_string_is_not_split_into_characters(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, pain_points="may raise demand for "
                                            "secure devices in this function")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tps = stake.run()[TP_KEY]["data"]["talking_points"]
        assert tps and all("pain_points" not in tp for tp in tps.values())

    def test_a_list_valued_opener_is_not_published_as_python_repr(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=[opener_for(nm), "Then ask more."])
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tps = stake.run()[TP_KEY]["data"]["talking_points"]
        for tp in tps.values():
            assert not tp["how_to_open"].startswith("[")


    def test_non_string_optional_fields_are_treated_as_missing(self, stake, monkeypatch):
        pain = ("The new distribution hub may raise demand for standard devices in "
                "the workflows this role owns.")

        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, hp_play_focus=["PC refresh"],
                                            decision_power={"text": "Owns sourcing."},
                                            pain_points=[pain, 7, {"p": "x"}, ["y"]])
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tps = stake.run()[TP_KEY]["data"]["talking_points"]
        assert tps
        for tp in tps.values():
            assert tp["hp_play_focus"] is None
            assert "decision_power" not in tp
            assert tp["pain_points"] == [pain]


class TestStakeholderGroundingGuards:
    def test_an_unsourced_figure_drops_the_entry_and_the_retry_replaces_it(self, stake, monkeypatch):
        def responder(system, _u, n):
            rows = roster_of(system)
            if n == 1:
                return {"contacts": [good_entry(c, nm, how_to_open=opener_for(nm)
                                                + " Revenue grew 37% last year.")
                                     for c, nm, _t in rows]}
            return {"contacts": [good_entry(c, nm) for c, nm, _t in rows]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(grid_people(widgets))
        assert not any("37" in tp["how_to_open"] for tp in tps.values())
        assert widgets[TP_KEY]["data"]["grounding_report"]["numbers_rejected"]

    def test_an_unsourced_url_never_reaches_storage(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=opener_for(nm)
                                            + " See https://evil.example.com/deal for more.")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tp = stake.run()[TP_KEY]
        assert tp["data"]["talking_points"] == {}
        assert "evil.example.com" not in json.dumps(tp, default=str)

    def test_an_unsourced_figure_in_a_pain_point_drops_the_whole_entry(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, pain_points=["Budget cut by 42 percent "
                                                                "may slow the refresh."])
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tp = stake.run()[TP_KEY]
        assert tp["data"]["talking_points"] == {}

    def test_a_rule_echo_in_decision_power_is_withheld(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, decision_power="Advisory input only.")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tps = stake.run()[TP_KEY]["data"]["talking_points"]
        assert tps and all("decision_power" not in tp for tp in tps.values())

    def test_a_product_opener_for_a_non_hardware_remit_never_reaches_the_card(
            self, stake, monkeypatch):
        """Fixed (D3): only hp_play_focus used to be reset and the opener still
        pitched the product. It is now a rejection: the entry is dropped and the
        missing-contact retry asks for it again."""
        rows = [_row("Hana Ito", "Head of Tax", "Finance", "director")]

        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, hp_play_focus="Endpoint security",
                                            how_to_open="I would open on HP Wolf Security "
                                            "and ask how %s protects laptops." % nm)
                                 for c, nm, _t in roster_of(system)]}

        client = use_model(monkeypatch, responder)
        tps = stake.run(rows)[TP_KEY]["data"]["talking_points"]
        assert len(client.sent) == 2, "the retry is asked to rewrite it"
        assert all("wolf security" not in tp["how_to_open"].lower() for tp in tps.values())
        assert "hana_ito" not in tps

    def test_the_retry_replaces_a_rejected_product_opener(self, stake, monkeypatch):
        rows = [_row("Hana Ito", "Head of Tax", "Finance", "director")]

        def responder(system, _u, n):
            if n == 1:
                return {"contacts": [good_entry(c, nm, how_to_open="I would open on HP Wolf "
                                                "Security and ask how %s protects laptops." % nm)
                                     for c, nm, _t in roster_of(system)]}
            return {"contacts": [good_entry(c, nm) for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tp = stake.run(rows)[TP_KEY]["data"]["talking_points"]["hana_ito"]
        assert tp["how_to_open"] == opener_for("Hana Ito")
        assert tp["hp_play_focus"] == "Account engagement / discovery"

    def test_a_product_only_in_the_focus_label_is_relabelled_not_dropped(
            self, stake, monkeypatch):
        rows = [_row("Hana Ito", "Head of Tax", "Finance", "director")]

        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, hp_play_focus="HP Wolf Security")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tp = stake.run(rows)[TP_KEY]["data"]["talking_points"]["hana_ito"]
        assert tp["hp_play_focus"] == "Account engagement / discovery"
        assert tp["how_to_open"] == opener_for("Hana Ito")

    def test_a_blocked_line_pitched_in_the_opener_is_rejected(self, stake, monkeypatch):
        """Same rule for a hardware remit's per-title block list
        (PLAY_BLOCKED_BY_TITLE): Print/MPS opened to a Cloud Operations lead."""
        rows = [_row("Omar Reed", "Head of Cloud Operations", "IT", "director")]

        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=opener_for(nm)
                                            + " HP Enterprise Printing & MPS fits here.")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        tps = stake.run(rows)[TP_KEY]["data"]["talking_points"]
        assert tps == {}

    def test_an_extremely_long_opener_is_bounded(self, stake, monkeypatch):
        """Fixed (D13): the prompt asks for 40-90 words and a 6,000-word opener
        was published unchanged. Over OPENER_REJECT_WORDS the entry is rejected
        (not trimmed) and the retry asks again; if the retry is long too,
        nothing is published for that contact."""
        long_text = "I would like to understand your device plans. " * 750

        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=nm + " " + long_text)
                                 for c, nm, _t in roster_of(system)]}

        client = use_model(monkeypatch, responder)
        tps = stake.run()[TP_KEY]["data"]["talking_points"]
        assert len(client.sent) == 2
        assert all(len(tp["how_to_open"].split()) <= sm.OPENER_REJECT_WORDS
                   for tp in tps.values())
        assert tps == {}

    def test_a_long_opener_is_rewritten_by_the_retry(self, stake, monkeypatch):
        long_text = "I would like to understand your device plans. " * 30

        def responder(system, _u, n):
            rows = roster_of(system)
            if n == 1:
                return {"contacts": [good_entry(c, nm, how_to_open=nm + " " + long_text)
                                     for c, nm, _t in rows]}
            return {"contacts": [good_entry(c, nm) for c, nm, _t in rows]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert set(tps) == set(grid_people(widgets))
        assert all(tp["how_to_open"] == opener_for(grid_people(widgets)[c])
                   for c, tp in tps.items())

    def test_an_opener_at_the_ceiling_is_kept(self, stake, monkeypatch):
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=" ".join(
                [nm] + ["word"] * (sm.OPENER_REJECT_WORDS - len(nm.split()))))
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        assert set(widgets[TP_KEY]["data"]["talking_points"]) == set(grid_people(widgets))

    def test_non_english_prose_is_kept_on_the_right_contact(self, stake, monkeypatch):
        """No language gate exists on generated prose; this pins that the join
        is still right and nothing crashes."""
        def responder(system, _u, _n):
            return {"contacts": [good_entry(c, nm, how_to_open=nm + " 様、デバイス更新の計画について伺いたいです。")
                                 for c, nm, _t in roster_of(system)]}

        use_model(monkeypatch, responder)
        widgets = stake.run()
        people = grid_people(widgets)
        for cid, tp in widgets[TP_KEY]["data"]["talking_points"].items():
            assert tp["how_to_open"].startswith(people[cid])


class TestStakeholderRosterEdges:
    def test_zero_contacts_writes_empty_and_calls_no_model(self, stake, _no_network):
        widgets = stake.run([])
        assert widgets[TP_KEY]["status"] == "empty"
        assert widgets["stakeholder_contacts_grid"]["status"] == "empty"
        assert _no_network == []

    def test_all_contacts_pending_review_is_zero_contacts(self, stake, _no_network):
        rows = [_row("Zoe Abbott", "CIO", apollo_match_status="Pending"),
                _row("Ben Ellis", "IT Manager", match_status="Needs review")]
        widgets = stake.run(rows)
        assert widgets[TP_KEY]["status"] == "empty"
        assert _no_network == []

    def test_one_contact(self, stake, monkeypatch):
        use_model(monkeypatch, answer_everyone)
        widgets = stake.run([_row("Zoe Abbott", "Chief Information Officer")])
        assert list(widgets[TP_KEY]["data"]["talking_points"]) == ["zoe_abbott"]

    def test_a_contact_with_no_title_email_or_phone(self, stake, monkeypatch):
        bare = {"Prospect full_name": "Eve Blank", "Prospect prospect_id": "eve"}
        client = use_model(monkeypatch, answer_everyone)
        widgets = stake.run([bare, _row("Zoe Abbott", "Chief Information Officer")])
        roster = roster_of(client.systems()[0])
        assert ("eve", "Eve Blank", "N/A") in roster
        tps = widgets[TP_KEY]["data"]["talking_points"]
        assert "Eve Blank" in tps["eve"]["how_to_open"]
        grid = {c["contact_id"]: c for c in widgets["stakeholder_contacts_grid"]["data"]["contacts"]}
        assert grid["eve"]["email"] is None and grid["eve"]["phone"] is None

    def test_a_contact_with_no_name_is_still_joined_by_its_own_id(self, stake, monkeypatch):
        nameless = {"Prospect job_title": "IT Director", "Prospect prospect_id": "p-77"}
        use_model(monkeypatch, answer_everyone)
        widgets = stake.run([nameless])
        assert list(widgets[TP_KEY]["data"]["talking_points"]) == ["p-77"]


# ======================================================== Objection Playbook

TECHNO = [{"Collaboration": "Zoom, Slack", "It Security": "CrowdStrike",
           "It Management": "ServiceNow",
           "Full Tech Stack": "Zoom, Slack, CrowdStrike, ServiceNow"}]

OBJECTIONS = {
    "Client Devices": "\"We refreshed laptops recently, so there is nothing to discuss.\"",
    "Collaboration": "\"Meeting rooms belong to facilities, not to me.\"",
    "Print / MPS": "\"Printing is a tiny line item for us.\"",
    "Endpoint Security": "\"Our security stack is settled and I am not reopening it.\"",
    "Device Management": "\"Device management is outsourced already.\"",
}
AREA_LINE = re.compile(r"^- area=(.+?) \| ", re.M)


def card(area, **over):
    c = {"area": area, "objection": OBJECTIONS[area],
         "reframe": "HP Wolf Security is the line to raise; the angle is how devices "
                    "in the field are covered today.",
         "counter_question": "Who decides on this area today?",
         "why_expected": "The account already runs tools here.",
         "recommended_next_step": "Book a short discovery call."}
    c.update(over)
    return c


def all_cards(system, _u, _n):
    return {"cards": [card(a) for a in AREA_LINE.findall(system)]}


@pytest.fixture
def objection(monkeypatch):
    db = FakeDb()
    data = {"technographics": TECHNO, "firmographics": FIRMO, "tech_breakdown": [],
            "prospect_contacts": [_row("Ivy Stone", "Head of IT Security", "IT", "director"),
                                  _row("Max Hale", "Sales Director", "Sales", "director")]}
    monkeypatch.setattr(op, "get_db", lambda: db)
    monkeypatch.setattr("app.database.mongodb.get_db", lambda: db)
    monkeypatch.setattr("app.services.extractors.datasets.get_db", lambda: db)
    monkeypatch.setattr(op, "read_dataset_records",
                        lambda _aid, key, **_k: list(data.get(key, [])))
    monkeypatch.setattr(op.cs, "knowledge_version", lambda _db: "cs-v")
    monkeypatch.setattr(op.rb, "knowledge_version", lambda _db: "rb-v")
    monkeypatch.setattr(op.rb, "account_evidence", lambda _aid: [])
    monkeypatch.setattr(op.rb, "account_country", lambda _aid: "")
    monkeypatch.setattr(op, "_rulebook_claims", lambda *_a, **_k: {})
    monkeypatch.setattr(op.cs, "cited_above", lambda *_a, **_k: set())
    monkeypatch.setattr(op.cs, "allocate", lambda *_a, **_k: None)
    import app.services.extractors.tech_landscape  # noqa: F401 - imported lazily by op
    extract = inspect.unwrap(op.extract_objection_playbook)

    def run(ctx=None):
        if ctx is None:
            out = extract(ACCOUNT)
        else:
            with run_context.active(ctx):
                out = extract(ACCOUNT)
        return {w["widget_key"]: w for w in out}

    return SimpleNamespace(db=db, data=data, run=run)


def cards_of(widgets):
    return widgets["objection_reframe_cards"]["data"].get("cards") or []


class TestObjectionPlaybook:
    def test_baseline_topic_owner_is_python_owned_from_the_contacts(self, objection, monkeypatch):
        use_model(monkeypatch, all_cards)
        cards = cards_of(objection.run())
        by_area = {c["area"]: c for c in cards}
        assert set(by_area) == set(OBJECTIONS)
        sec = by_area["Endpoint Security"]
        assert (sec["likely_raiser"], sec["likely_raiser_source"]) == (
            "Head of IT Security", "prospect_contacts")
        # No contact owns print: the card names the area, not a person.
        assert by_area["Print / MPS"]["likely_raiser"] == "Print / MPS"
        assert by_area["Print / MPS"]["likely_raiser_source"] == "hp_contest_area"

    def test_a_person_the_model_names_as_raiser_is_ignored(self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card(a, likely_raiser="Jane Doe (CEO)", raised_by="Jane Doe",
                                   likely_raiser_source="model")
                              for a in AREA_LINE.findall(system)]}

        use_model(monkeypatch, responder)
        widgets = objection.run()
        assert "Jane Doe" not in json.dumps(widgets["objection_reframe_cards"], default=str)
        assert all(c["likely_raiser_source"] in ("prospect_contacts", "hp_contest_area")
                   for c in cards_of(widgets))

    def test_model_returning_none_publishes_pending_with_no_cards(self, objection, monkeypatch):
        monkeypatch.setattr(op, "generate_gpt4o_json_completion", lambda *_a: None)
        rc = objection.run()["objection_reframe_cards"]
        assert rc["status"] == "pending" and rc["data"]["cards"] == []
        # The deterministic evidence widget is still published.

    def test_provider_exception_is_counted_and_does_not_crash(self, objection, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("connection reset"))
        ctx = make_ctx(ACCOUNT, ("objection_incumbent_context", "objection_reframe_cards"))
        objection.run(ctx=ctx)
        assert ctx.llm_failures == 1
        assert ctx.staged["objection_reframe_cards"]["status"] == "pending"
        assert ctx.staged["objection_incumbent_context"]["status"] == "available"

    def test_unreadable_json_then_valid_succeeds(self, objection, monkeypatch):
        client = use_model(monkeypatch, lambda s, u, n: '{"cards": [{"area": "x",}' if n == 1
                           else all_cards(s, u, n))
        assert len(cards_of(objection.run())) == len(OBJECTIONS)
        assert len(client.sent) == 2

    def test_unknown_areas_are_dropped(self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card("Client Devices"),
                              {**card("Collaboration"), "area": "Quantum Computing"},
                              {**card("Print / MPS"), "area": "print / mps"}]}

        use_model(monkeypatch, responder)
        assert [c["area"] for c in cards_of(objection.run())] == ["Client Devices"]

    @pytest.mark.parametrize("field", ["objection", "reframe", "counter_question"])
    def test_a_card_missing_required_text_is_dropped_not_filled(self, objection, monkeypatch, field):
        def responder(system, _u, _n):
            return {"cards": [card(a, **{field: "  "}) if a == "Collaboration" else card(a)
                              for a in AREA_LINE.findall(system)]}

        use_model(monkeypatch, responder)
        areas = {c["area"] for c in cards_of(objection.run())}
        assert areas == set(OBJECTIONS) - {"Collaboration"}

    def test_partial_answer_keeps_the_good_cards_and_invents_none(self, objection, monkeypatch):
        client = use_model(monkeypatch, lambda *_a: {"cards": [card("Client Devices"),
                                                              card("Endpoint Security")]})
        widgets = objection.run()
        assert sorted(c["area"] for c in cards_of(widgets)) == ["Client Devices",
                                                                "Endpoint Security"]
        assert widgets["objection_reframe_cards"]["data"]["cards_count"] == 2
        # Missing areas are not asked for again: only sector or HP-claim
        # rejections trigger the playbook's retry.
        assert len(client.sent) == 1

    @pytest.mark.parametrize("answer", [
        {"cards": "none"}, {"cards": ["Client Devices"]}, {"objections": []}, {},
    ], ids=["string", "list-of-strings", "wrong-key", "empty-object"])
    def test_malformed_shapes_publish_no_cards(self, objection, monkeypatch, answer):
        use_model(monkeypatch, lambda *_a: answer)
        rc = objection.run()["objection_reframe_cards"]
        assert rc["status"] == "pending" and rc["data"]["cards"] == []

    @pytest.mark.parametrize("extra", [" It cut costs by 37% at a peer.",
                                       " See https://evil.example.com/case."],
                             ids=["number", "url"])
    def test_hallucinated_figures_and_links_drop_the_card(self, objection, monkeypatch, extra):
        def responder(system, _u, _n):
            return {"cards": [card(a, reframe=card(a)["reframe"] + extra) if a == "Collaboration"
                              else card(a) for a in AREA_LINE.findall(system)]}

        use_model(monkeypatch, responder)
        widgets = objection.run()
        assert "Collaboration" not in {c["area"] for c in cards_of(widgets)}
        assert extra.strip() not in json.dumps(widgets, default=str)

    def test_a_duplicated_area_yields_one_card(self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card(a) for a in AREA_LINE.findall(system)]
                    + [card("Collaboration", objection="\"Video calls are not a priority "
                                                       "budget for this quarter at all.\"")]}

        use_model(monkeypatch, responder)
        ids = [c["card_id"] for c in cards_of(objection.run())]
        assert len(ids) == len(set(ids))

    def test_a_list_valued_counter_question_is_not_published_as_python_repr(
            self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card(a, counter_question=["Who decides today?", "When?"])
                              for a in AREA_LINE.findall(system)]}

        use_model(monkeypatch, responder)
        for c in cards_of(objection.run()):
            assert not c["counter_question"].startswith("[")
        # A required field that is not a string is missing: no card at all.
        assert cards_of(objection.run()) == []

    def test_a_non_string_optional_field_is_dropped_not_stringified(self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card(a, why_expected={"why": "x"},
                                   recommended_next_step=["Book a call."])
                              for a in AREA_LINE.findall(system)]}

        use_model(monkeypatch, responder)
        cards = cards_of(objection.run())
        assert len(cards) == len(OBJECTIONS)
        assert all(c["why_expected"] is None and c["recommended_next_step"] is None
                   for c in cards)

    def test_a_duplicated_area_keeps_the_first_card(self, objection, monkeypatch):
        def responder(system, _u, _n):
            return {"cards": [card(a) for a in AREA_LINE.findall(system)]
                    + [card("Collaboration", objection="\"Video calls are not a priority "
                                                       "budget for this quarter at all.\"")]}

        use_model(monkeypatch, responder)
        collab = [c for c in cards_of(objection.run()) if c["area"] == "Collaboration"]
        assert [c["objection"] for c in collab] == [OBJECTIONS["Collaboration"]]

    @pytest.mark.parametrize("answer", [
        {"cards": "none"}, {"objections": []},
        {"cards": [{"area": "Quantum Computing", "objection": "x", "reframe": "y",
                    "counter_question": "z"}]},
    ], ids=["string", "wrong-key", "only-unknown-areas"])
    def test_an_unusable_answer_is_reported_as_a_failure_in_a_run(
            self, objection, monkeypatch, answer):
        use_model(monkeypatch, lambda *_a: answer)
        ctx = make_ctx(ACCOUNT, ("objection_incumbent_context", "objection_reframe_cards"))
        objection.run(ctx=ctx)
        assert ctx.staged["objection_reframe_cards"]["data"]["cards"] == []
        assert ctx.llm_failures == 1

    def test_a_usable_answer_counts_no_failure(self, objection, monkeypatch):
        use_model(monkeypatch, all_cards)
        ctx = make_ctx(ACCOUNT, ("objection_incumbent_context", "objection_reframe_cards"))
        objection.run(ctx=ctx)
        assert ctx.llm_failures == 0 and ctx.llm_calls == 1

    def test_the_empty_panel_carries_no_client_facing_notice(self, objection, monkeypatch):
        monkeypatch.setattr(op, "generate_gpt4o_json_completion", lambda *_a: None)
        data = objection.run()["objection_reframe_cards"]["data"]
        assert "notice" not in data
        assert "API key" not in json.dumps(data, default=str)
        assert data["unavailable_reason"]

    def test_a_pending_review_contact_is_never_the_topic_owner(self, objection, monkeypatch):
        objection.data["prospect_contacts"] = [
            _row("Pat Pending", "Chief Information Security Officer", "IT", "cxo",
                 apollo_match_status="Pending")]
        use_model(monkeypatch, all_cards)
        sec = next(c for c in cards_of(objection.run()) if c["area"] == "Endpoint Security")
        assert sec["likely_raiser_source"] == "hp_contest_area"

    def test_zero_contacts_and_titleless_contacts_name_no_one(self, objection, monkeypatch):
        objection.data["prospect_contacts"] = [{"Prospect full_name": "No Title",
                                                "Prospect prospect_id": "nt"}]
        use_model(monkeypatch, all_cards)
        cards = cards_of(objection.run())
        assert cards and all(c["likely_raiser"] == c["area"] for c in cards)
        objection.data["prospect_contacts"] = []
        cards = cards_of(objection.run())
        assert cards and all(c["likely_raiser_source"] == "hp_contest_area" for c in cards)

    def test_raiser_is_a_title_not_a_contact_name(self, objection, monkeypatch):
        use_model(monkeypatch, all_cards)
        dump = json.dumps(objection.run()["objection_reframe_cards"], default=str)
        assert "Ivy Stone" not in dump and "Max Hale" not in dump


# ======================================================== Content Studio

def grid_widget(contacts):
    return {"account_id": ACCOUNT, "widget_key": "stakeholder_contacts_grid",
            "status": "available", "data": {"contacts": contacts}}


def grid_contact(cid, name, title="Chief Information Officer", **over):
    c = {"contact_id": cid, "full_name": name, "title": title, "source": "Source A",
         "hp_relevance_band": "high", "is_priority_contact": True, "stakeholder_score": 80,
         "normalized_department": "Information Technology", "seniority_band": "C-Suite",
         "influence_type": "Decision Maker"}
    c.update(over)
    return c


@pytest.fixture
def studio_db(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(cstudio, "get_db", lambda: db)
    monkeypatch.setattr("app.database.mongodb.get_db", lambda: db)
    return db


class TestContentStudioPersonas:
    def _personas(self, db, contacts):
        db["account_widgets"].insert_one(grid_widget(contacts))
        return cstudio._derive_named_personas(db, ACCOUNT)

    def test_zero_contacts_gives_no_named_persona(self, studio_db):
        assert cstudio._derive_named_personas(studio_db, ACCOUNT) == []
        assert self._personas(studio_db, []) == []

    def test_each_persona_carries_its_own_contact(self, studio_db):
        ps = self._personas(studio_db, [grid_contact("zoe", "Zoe Abbott"),
                                        grid_contact("ben", "Ben Ellis", "IT Procurement Manager")])
        assert {(p["id"], p["contact_id"], p["full_name"]) for p in ps} == {
            ("contact_zoe", "zoe", "Zoe Abbott"), ("contact_ben", "ben", "Ben Ellis")}

    def test_titleless_apollo_and_low_relevance_contacts_are_not_named(self, studio_db):
        ps = self._personas(studio_db, [
            grid_contact("a", "No Title", title=""),
            grid_contact("b", "Apollo Row", source="Apollo"),
            grid_contact("c", "Low Rel", hp_relevance_band="low"),
            grid_contact("d", "Kept One")])
        assert [p["full_name"] for p in ps] == ["Kept One"]

    def test_persona_ids_are_unique_per_contact(self, studio_db):
        ps = self._personas(studio_db, [grid_contact("2", "Zoe Abbott"),
                                        grid_contact("contact_2", "Ben Ellis")])
        assert len({p["id"] for p in ps}) == 2

    def test_each_persona_id_resolves_to_its_own_contact(self, studio_db, monkeypatch):
        monkeypatch.setattr(cstudio, "_derive_client_personas", lambda _aid: [])
        self._personas(studio_db, [grid_contact("2", "Zoe Abbott"),
                                   grid_contact("contact_2", "Ben Ellis")])
        by = lambda pid: cstudio._persona_by_id(studio_db, ACCOUNT, [], pid)  # noqa: E731
        assert by("contact_2")["full_name"] == "Zoe Abbott"
        assert by("contact_contact_2")["full_name"] == "Ben Ellis"

    def test_an_old_unprefixed_persona_id_still_resolves(self, studio_db, monkeypatch):
        """Before ids were always prefixed, contact id "contact_7" had persona
        id "contact_7"; a saved asset may still carry it."""
        monkeypatch.setattr(cstudio, "_derive_client_personas", lambda _aid: [])
        self._personas(studio_db, [grid_contact("contact_7", "Ben Ellis")])
        p = cstudio._persona_by_id(studio_db, ACCOUNT, [], "contact_7")
        assert p["full_name"] == "Ben Ellis" and p["id"] == "contact_contact_7"


def _studio_ctx(content_type="email", persona=None):
    contract = cstudio.CONTENT_TYPE_CONTRACTS[content_type]
    persona = persona or {"id": "contact_zoe", "kind": "named", "source": "Source A",
                          "title": "Chief Information Officer", "full_name": "Zoe Abbott",
                          "subtitle": "Zoe Abbott - IT - C-Suite", "contact_id": "zoe",
                          "department": "Information Technology", "seniority": "C-Suite",
                          "influence_type": "Decision Maker"}
    labels = {"A1": "Distributes industrial parts across Europe.",
              "A2": "Industry: Wholesale",
              "P1": "Title: Chief Information Officer"}
    ground = build_corpus({"firmographics": FIRMO,
                           "evidence_block": [{"text": t} for t in labels.values()]})
    report = GroundingReport(ground, ["subject_line", "opening", "body_sections", "cta"])
    return {"contract": contract, "persona": persona, "company_name": "Test Co",
            "account_block": "\n".join("[%s] %s" % kv for kv in labels.items() if kv[0][0] == "A"),
            "persona_block": "[P1] Title: Chief Information Officer",
            "labels": labels, "ground": ground, "report": report,
            "banned_names": ["zoe abbott", "ben ellis"], "fingerprint": "f" * 40,
            "instructions_text": "", "guardrails_text": "", "topic": "Device refresh",
            "additional_context": "", "content_type": content_type, "industry": ""}


@pytest.fixture
def studio(monkeypatch, studio_db):
    ctx = _studio_ctx()
    monkeypatch.setattr(cstudio, "_build_generation_context", lambda *_a, **_k: ctx)
    monkeypatch.setattr(cstudio, "_record_gate_audit", lambda *_a, **_k: None)
    monkeypatch.setattr(cstudio.cs, "allocate", lambda *_a, **_k: None)
    monkeypatch.setattr(cstudio.cs, "cited_above", lambda *_a, **_k: set())
    return SimpleNamespace(db=studio_db, ctx=ctx)


class TestContentStudioGeneration:
    def test_model_none_falls_back_to_the_deterministic_template(self, studio, monkeypatch):
        calls = []
        monkeypatch.setattr(cstudio, "generate_gpt4o_json_completion",
                            lambda *a: calls.append(a) or None)
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        latest = out["data"]["latest"]
        assert latest["is_fallback"] is True
        assert latest["persona"]["id"] == "contact_zoe"
        assert "Distributes industrial parts" in latest["generated"]["opening"]
        assert latest["generated"]["evidence_used"] == ["A1"]
        assert any("deterministic template" in w for w in latest["style_warnings"])
        assert len(calls) == 1      # a None is not retried in the feature

    def test_provider_exception_falls_back_without_crashing(self, studio, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("connection reset"))
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        assert out["data"]["latest"]["is_fallback"] is True

    @pytest.mark.parametrize("answer", [
        {"asset": "Dear Zoe, ..."}, {"asset": ["opening"]}, {"email": {}}, {"asset": {}},
    ], ids=["string", "list", "wrong-key", "empty-asset"])
    def test_malformed_assets_are_retried_then_fall_back(self, studio, monkeypatch, answer):
        client = use_model(monkeypatch, lambda *_a: answer)
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        latest = out["data"]["latest"]
        assert latest["is_fallback"] is True
        assert latest["attempts"] == 1 + cstudio.RETRY_ROUNDS
        assert len(client.sent) == 1 + cstudio.RETRY_ROUNDS

    def test_unreadable_json_on_every_attempt_is_a_fallback_not_a_crash(self, studio, monkeypatch):
        use_model(monkeypatch, lambda *_a: '{"asset": {"opening": "x",,}}')
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "email", "Device refresh")
        assert out["data"]["latest"]["is_fallback"] is True

    def test_role_type_persona_copy_naming_a_contact_is_rejected(self, studio):
        role = {"id": "it_decision_maker", "kind": "archetype", "title": "IT decision maker"}
        raw = {"asset": {"subject_line": "Re: Device refresh",
                         "opening": "Ben Ellis, your team distributes industrial parts across Europe.",
                         "body_sections": ["At HP, we help."], "cta": "Would a briefing help?",
                         "evidence_used": ["A1"]}}
        c = studio.ctx
        asset, faults, _soft = cstudio._validate_asset(raw, c["contract"], role, c["labels"],
                                                       c["ground"], c["report"], c["banned_names"])
        assert asset is None
        assert any("ben ellis" in f for f in faults)

    @staticmethod
    def _clean_linkedin(opening):
        body = ("At HP, we help distributors standardise devices for warehouse and office staff "
                "with HP Elite / Pro PCs, so a new site runs on one supported image from the first "
                "day and the service desk carries no extra load while the network of sites grows "
                "across the region.")
        return {"asset": {"opening": opening, "body_sections": [body],
                          "cta": "Would a short briefing on standard images for new sites be useful?",
                          "hp_products": ["HP Elite / Pro PCs"], "evidence_used": ["A1"]}}

    @staticmethod
    def _filled_vp_it():
        from app.services.hp import buyer_personas as bp
        return {"id": "vp-it", "kind": "client_role", "title": bp.card("vp-it")["title"],
                "is_filled": True, "full_name": "Zoe Abbott",
                "buying_committee_persona": bp.angle("vp-it")}

    def _validate(self, studio, raw, persona):
        c = _studio_ctx("linkedin_message")
        return cstudio._validate_asset(raw, c["contract"], persona, c["labels"], c["ground"],
                                       c["report"], c["banned_names"])

    def test_a_filled_role_may_be_addressed_by_its_own_contact_name(self, studio):
        raw = self._clean_linkedin("Zoe Abbott, your business distributes industrial parts "
                                   "across Europe, which puts device consistency on your agenda.")
        asset, faults, _soft = self._validate(studio, raw, self._filled_vp_it())
        assert asset is not None, faults

    def test_a_filled_role_copy_naming_a_different_contact_is_rejected(self, studio):
        raw = self._clean_linkedin("Ben Ellis told us your business distributes industrial "
                                   "parts across Europe, which puts device consistency on your agenda.")
        asset, _faults, _soft = self._validate(studio, raw, self._filled_vp_it())
        assert asset is None

    def test_a_legacy_persona_with_a_clean_answer_does_not_raise(self, studio, monkeypatch):
        clean = self._clean_linkedin("Your business distributes industrial parts across "
                                     "Europe, which puts device consistency on your agenda.")
        studio.ctx.update(_studio_ctx("linkedin_message"))
        use_model(monkeypatch, lambda *_a: clean)
        # Fixed (D10): the gates now skip the matrix checks for a persona that
        # has no matrix row, so the clean answer is published.
        out = cstudio.generate_content_asset(ACCOUNT, "contact_zoe", "linkedin_message",
                                             "Device refresh")
        assert out["data"]["latest"]["is_fallback"] is False

    def test_unknown_persona_is_a_value_error_so_the_endpoint_answers_4xx(self):
        from app.services.hp import buyer_personas as bp
        assert issubclass(bp.UnknownPersona, ValueError)
        with pytest.raises(ValueError):
            bp.card("contact_zoe")

    def test_the_gates_do_not_raise_for_a_legacy_persona(self):
        from app.services.hp import content_gates
        asset = {"opening": "Hello.", "body_sections": [{"heading": None, "text": "At HP."}],
                 "cta": "Would a briefing help?", "hp_products": ["HP Wolf Security"]}
        findings = content_gates.run(asset, persona_id="contact_zoe",
                                     content_type="linkedin_message", filled=True)
        assert not [f for f in findings if f["gate"] in ("G4", "G6")]

    def test_a_named_contact_copy_naming_a_different_contact_is_rejected(self, studio):
        raw = self._clean_linkedin("Ben Ellis told us your business distributes industrial "
                                   "parts across Europe, which puts device consistency on your agenda.")
        c = _studio_ctx("linkedin_message")
        asset, faults, _soft = cstudio._validate_asset(
            raw, c["contract"], c["persona"], c["labels"], c["ground"], c["report"],
            c["banned_names"])
        assert asset is None
        assert any("ben ellis" in f for f in faults)

    def test_a_named_contact_may_still_be_addressed_by_their_own_name(self, studio):
        raw = self._clean_linkedin("Zoe Abbott, your business distributes industrial parts "
                                   "across Europe, which puts device consistency on your agenda.")
        c = _studio_ctx("linkedin_message")
        asset, faults, _soft = cstudio._validate_asset(
            raw, c["contract"], c["persona"], c["labels"], c["ground"], c["report"],
            c["banned_names"])
        assert asset is not None, faults

    def test_a_list_valued_opening_is_missing_not_python_repr(self, studio):
        raw = self._clean_linkedin(["Your business distributes industrial parts.", "More."])
        c = _studio_ctx("linkedin_message")
        asset, faults, _soft = cstudio._validate_asset(
            raw, c["contract"], c["persona"], c["labels"], c["ground"], c["report"],
            c["banned_names"])
        assert asset is None
        assert any("opening is missing" in f for f in faults)

    def test_invented_evidence_labels_are_a_hard_fault(self, studio):
        raw = {"asset": {"subject_line": "Re: Device refresh", "opening": "Hello.",
                         "body_sections": ["At HP, we help."], "cta": "Would a briefing help?",
                         "evidence_used": ["A9", "Z1"]}}
        c = studio.ctx
        asset, faults, _soft = cstudio._validate_asset(raw, c["contract"], c["persona"], c["labels"],
                                                       c["ground"], c["report"], c["banned_names"])
        assert asset is None
        assert any("cites none of the supplied labels" in f for f in faults)

    def test_an_unsourced_figure_is_a_hard_fault(self, studio):
        raw = {"asset": {"subject_line": "Re: Device refresh",
                         "opening": "Your fleet of 4,812 laptops is ageing.",
                         "body_sections": ["At HP, we help."], "cta": "Would a briefing help?",
                         "evidence_used": ["A1"]}}
        c = studio.ctx
        asset, faults, _soft = cstudio._validate_asset(raw, c["contract"], c["persona"], c["labels"],
                                                       c["ground"], c["report"], c["banned_names"])
        assert asset is None
        assert any("unsourced number" in f for f in faults)


class TestContentStudioAngles:
    def test_model_none_gives_empty_options_not_invented_ones(self, studio, monkeypatch):
        monkeypatch.setattr(cstudio, "generate_gpt4o_json_completion", lambda *_a: None)
        out = cstudio.suggest_content_angles(ACCOUNT, "contact_zoe", "email", "Device refresh")
        assert out["status"] == "empty" and out["data"]["options"] == []
        assert out["data"]["last_error"]["notice"]

    def test_angles_drop_invented_labels_figures_and_duplicates(self, studio, monkeypatch):
        answer = {"options": [
            {"label": "Parts logistics", "summary": "Lead on European distribution.",
             "opening_line": "Your parts move across Europe.", "evidence_used": ["A1", "Q7"]},
            {"label": "Big savings", "summary": "Cut costs by 63 percent.",
             "opening_line": "x", "evidence_used": ["A2"]},
            {"label": "Again", "summary": "Lead on European distribution.",
             "opening_line": "y", "evidence_used": ["A1"]},
            "not a dict", {"label": "", "summary": "no label"},
        ]}
        use_model(monkeypatch, lambda *_a: answer)
        out = cstudio.suggest_content_angles(ACCOUNT, "contact_zoe", "email", "Device refresh")
        opts = out["data"]["options"]
        assert [o["label"] for o in opts] == ["Parts logistics"]
        assert opts[0]["evidence_used"] == ["A1"]


# ======================================================== Messaging pillars

EVIDENCE = {
    "acct_technology_stack#c1": "The account runs ServiceNow for IT service management.",
    "acct_news_signals#c2": "The account announced a new distribution hub in Rotterdam.",
}


def _ev_rows(ids):
    resolved, invalid = [], []
    for raw in ids or []:
        eid = str(raw)
        if eid in EVIDENCE:
            resolved.append({"evidence_id": eid, "dataset": "content_messaging",
                             "doc_id": eid.split("#", maxsplit=1)[0], "source_text": EVIDENCE[eid]})
        else:
            invalid.append(eid)
    return resolved, invalid


PILLAR_BODY = ("The account runs ServiceNow for IT service management and announced a new "
               "distribution hub in Rotterdam, which points to a growing estate of devices "
               "for warehouse and office staff. ") * 3
PILLAR_BENEFIT = ("HP Elite / Pro PCs give the hub a standard device image that the service "
                  "desk already supports, so new staff are productive on day one. ") * 2


def pillar_answer(**over):
    a = {"pillar_title": "Hub device rollout", "challenge_detail": PILLAR_BODY,
         "hp_benefit": PILLAR_BENEFIT, "hp_solutions": ["HP Elite / Pro PCs"],
         "proof_points": [{"proof": "The account announced a new hub.",
                           "evidence_ids": ["acct_news_signals#c2"]}],
         "target_role": "", "next_step": "Offer a rollout workshop."}
    a.update(over)
    return a


CHALLENGE = {"challenge": "A new distribution hub needs devices.", "theme": "Hub rollout",
             "evidence": [pillars._source(_ev_rows(["acct_news_signals#c2"])[0][0])]}
NO_RESTRICTIONS = {"country": "", "superlatives_blocked": False,
                   "competitor_claims_blocked": False}


@pytest.fixture
def msg(monkeypatch):
    db = FakeDb()
    monkeypatch.setattr(pillars, "get_db", lambda: db)
    monkeypatch.setattr("app.database.mongodb.get_db", lambda: db)
    monkeypatch.setattr(pillars.ev, "resolve", lambda _aid, _idx, ids: _ev_rows(ids))
    monkeypatch.setattr(pillars.index_state, "get",
                        lambda *_a: {"status": pillars.index_state.READY})
    monkeypatch.setattr(pillars.query, "ask",
                        lambda *_a, **_k: SimpleNamespace(context="\n".join(
                            "%s [%s]" % (t, e) for e, t in EVIDENCE.items())))
    monkeypatch.setattr(pillars.cs, "cited_above", lambda *_a, **_k: set())
    monkeypatch.setattr(pillars.cs, "allocate", lambda *_a, **_k: None)
    return db


def _route(candidates=None, pillar=None, umbrella=None, framing=None):
    """A responder that answers each of the four pillar prompts by its system prompt."""
    def responder(system, _u, _n):
        if system == pillars.CANDIDATE_SYSTEM:
            return candidates
        if system == pillars.PILLAR_SYSTEM:
            return pillar
        if system == pillars.UMBRELLA_SYSTEM:
            return umbrella
        if system == pillars.FRAMING_SYSTEM:
            return framing
        return RuntimeError("unknown prompt")
    return responder


GOOD_CANDIDATES = {"challenges": [{"challenge": "A new distribution hub needs devices.",
                                   "evidence_ids": ["acct_news_signals#c2"],
                                   "theme": "Hub rollout"}]}


class TestMessagingPillars:
    def test_total_failure_raises_the_designed_error_and_publishes_nothing(self, msg, monkeypatch):
        use_model(monkeypatch, lambda *_a: RuntimeError("503"))
        with pytest.raises(pillars.PillarError):
            pillars.generate_messaging_pillars(ACCOUNT)
        assert msg["account_widgets"].find_one({"widget_key": pillars.WIDGET_KEY}) is None

    def test_challenges_citing_only_invented_evidence_are_dropped(self, msg, monkeypatch):
        bad = {"challenges": [{"challenge": "Invented", "evidence_ids": ["ghost_doc#c9"]},
                              {"challenge": "No ids at all"},
                              {"challenge": "String ids", "evidence_ids": "acct_news_signals#c2"},
                              "junk"]}
        use_model(monkeypatch, _route(candidates=bad))
        with pytest.raises(pillars.PillarError, match="no account challenge survived"):
            pillars.generate_messaging_pillars(ACCOUNT)

    def test_umbrella_and_framing_failing_still_publishes_verified_pillars(self, msg, monkeypatch):
        use_model(monkeypatch, _route(candidates=GOOD_CANDIDATES, pillar=pillar_answer(),
                                      umbrella=RuntimeError("timeout"),
                                      framing=RuntimeError("timeout")))
        out = pillars.generate_messaging_pillars(ACCOUNT)
        data = out["data"]
        assert out["status"] == "available" and data["pillar_count"] == 1
        assert data["umbrella_message"] == "" and data["umbrella_withheld"]
        p = data["pillars"][0]
        # Summaries fall back to the pillar's own text, never invented.
        assert p["challenge_summary"] == CHALLENGE["challenge"]
        assert PILLAR_BENEFIT.startswith(p["benefit_summary"])

    def test_inside_a_run_the_failed_umbrella_marks_the_run_degraded(self, msg, monkeypatch):
        use_model(monkeypatch, _route(candidates=GOOD_CANDIDATES, pillar=pillar_answer(),
                                      umbrella=RuntimeError("timeout"),
                                      framing={"umbrella_headline": "A hub rollout."}))
        ctx = make_ctx(ACCOUNT, (pillars.WIDGET_KEY,))
        with run_context.active(ctx):
            pillars.generate_messaging_pillars(ACCOUNT)
        assert ctx.llm_failures >= 1
        assert ctx.staged[pillars.WIDGET_KEY]["status"] == "available"

    def test_invented_proof_ids_are_dropped_and_counted(self, msg, monkeypatch):
        answer = pillar_answer(proof_points=[
            {"proof": "Real.", "evidence_ids": ["acct_news_signals#c2"]},
            {"proof": "Invented.", "evidence_ids": ["ghost_doc#c1"]},
            {"proof": "No id."}, "junk"])
        use_model(monkeypatch, lambda *_a: answer)
        p = pillars._build_pillar(ACCOUNT, CHALLENGE, "", "", NO_RESTRICTIONS, [])
        assert [x["proof"] for x in p["proof_points"]] == ["Real."]
        # A proof citing nothing is dropped and counted exactly like one citing
        # an id that does not resolve.
        assert [d["proof"] for d in p["dropped_proofs"]] == ["Invented.", "No id."]
        assert pillars._sourced_count(p) == {"sourced": 1, "total": 1, "proposed": 3,
                                             "dropped": 2}

    def test_an_invented_target_role_is_dropped(self, msg, monkeypatch):
        use_model(monkeypatch, lambda *_a: pillar_answer(target_role="IT decision-makers"))
        p = pillars._build_pillar(ACCOUNT, CHALLENGE, "", "", NO_RESTRICTIONS,
                                  ["Head of End User Services", "Chief Financial Officer"])
        assert p["target_role"] == ""

    def test_a_role_copied_from_the_roster_is_kept(self, msg, monkeypatch):
        use_model(monkeypatch, lambda *_a: pillar_answer(target_role="Head of End User Services"))
        p = pillars._build_pillar(ACCOUNT, CHALLENGE, "", "", NO_RESTRICTIONS,
                                  ["Chief Financial Officer", "Head of End User Services"])
        assert p["target_role"] == "Head of End User Services"

    def test_a_short_role_is_not_matched_inside_another_word(self):
        roster = ["Chief Information Security Officer", "Head of IT"]
        assert pillars._matched_role("IT", roster) in ("", "Head of IT")

    def test_a_longer_written_role_is_not_matched_to_a_role_it_contains(self):
        roster = ["Director", "Director of Procurement"]
        assert pillars._matched_role("Director of Finance", roster) == ""

    @pytest.mark.parametrize("answer", [None, {}, {"hp_benefit": ""}, {"hp_benefit": ["x"]}],
                             ids=["none", "empty", "blank-benefit", "list-benefit"])
    def test_a_pillar_with_no_benefit_is_not_built(self, msg, monkeypatch, answer):
        monkeypatch.setattr(pillars, "generate_gpt4o_json_completion", lambda *_a: answer)
        assert pillars._build_pillar(ACCOUNT, CHALLENGE, "", "", NO_RESTRICTIONS, []) is None

    def test_wrong_typed_solutions_produce_no_product_and_the_pillar_is_withheld(
            self, msg, monkeypatch):
        use_model(monkeypatch, _route(candidates=GOOD_CANDIDATES,
                                      pillar=pillar_answer(hp_solutions="HP Elite / Pro PCs"),
                                      umbrella={"umbrella_message": "x"}, framing={}))
        with pytest.raises(pillars.PillarError, match="no pillar survived"):
            pillars.generate_messaging_pillars(ACCOUNT)

    def test_roles_come_from_titles_only_and_skip_blank_titles(self, msg):
        msg["account_widgets"].insert_one(grid_widget([
            grid_contact("a", "Zoe Abbott", "Chief Information Officer"),
            grid_contact("b", "No Title", ""),
            grid_contact("c", "Ben Ellis", "chief information officer")]))
        roles = pillars._stakeholder_roles(msg, ACCOUNT)
        assert roles == ["Chief Information Officer"]

    def test_no_stakeholder_grid_means_no_roles(self, msg):
        assert pillars._stakeholder_roles(msg, ACCOUNT) == []
