"""The regeneration engine end to end: invalidation, explicit runs, order,
atomicity, failure, coalescing, concurrency, restart - and cost safety: nothing
runs unless a run asked for it (29 Sep).

Runs against an in-memory Mongo fake, and ALSO against a real mongod when
`REGEN_TEST_MONGO_URI` is set (a throwaway database is created and dropped).
The real-server run is what proves the partial unique indexes, the fenced
`find_one_and_update` commit and the `$max`/`$min` upserts behave as the engine
assumes; the fake cannot prove that on its own.

The graph used here is small and synthetic:

    A(d1) -> B(d2) -> C          D(d3)     (D shares nothing with A, B, C)

Run: python -m pytest tests/test_regen_engine.py -v
     REGEN_TEST_MONGO_URI=mongodb://localhost:27017 python -m pytest tests/test_regen_engine.py
"""

import hashlib
import os
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.services.extractors.datasets import read_dataset_records
from app.services.regen import (
    context as run_context,
    jobs,
    manifest,
    planner,
    runs,
    state,
    store as widget_store,
)
from app.services.regen.engine import Engine, load_snapshot
from app.services.regen.graph import Graph, Node
from regen_fakes import FakeDb

NODES = (
    Node("A", "fa", widgets=("a",), datasets=("d1",)),
    Node("B", "fb", widgets=("b",), datasets=("d2",), upstream=("A",)),
    Node("C", "fc", widgets=("c",), upstream=("B",)),
    Node("D", "fd", widgets=("dw",), datasets=("d3",)),
)


def _mongo_db():
    uri = os.getenv("REGEN_TEST_MONGO_URI")
    if not uri:
        pytest.skip("set REGEN_TEST_MONGO_URI to also run against a real mongod")
    from pymongo import MongoClient
    client = MongoClient(uri, serverSelectionTimeoutMS=2000)
    name = "regen_test_%s" % uuid.uuid4().hex[:10]
    return client, client[name], name


@pytest.fixture(params=["fake", "mongo"])
def db(request):
    if request.param == "fake":
        yield FakeDb()
        return
    client, database, name = _mongo_db()
    try:
        yield database
    finally:
        client.drop_database(name)
        client.close()


class Harness:
    """A graph, runners with switchable behaviour, and helpers to drive them."""

    def __init__(self, db, tmp_path, nodes=NODES):
        self.db = db
        self.tmp = tmp_path
        self.graph = Graph(nodes)
        self.log = []                      # (account, node) in run order
        self.fail = {}                     # node -> exception to raise
        self.partial_then_fail = set()     # nodes that put, then raise
        self.degrade = set()               # nodes whose "model call" fails
        self.skip_widget = set()           # nodes that forget to publish
        self.foreign = set()               # nodes that write another's widget
        self.undeclared = set()            # nodes that read an undeclared dataset
        self.gate = {}                     # node -> threading.Event to block on
        self.runners = {n.id: self._runner(n.id) for n in nodes}
        self.engine = self.make_engine()
        self.engine.ensure_indexes()

    def make_engine(self, worker_id="w1", graph=None, **kw):
        return Engine(db=self.db, graph=graph or self.graph,
                      versions=manifest.StaticVersions(),
                      runners=self.runners, worker_id=worker_id, strict_reads=True,
                      heartbeat_seconds=3600, **kw)

    def account(self):
        account_id = str(ObjectId())
        self.db["accounts"].insert_one({"_id": ObjectId(account_id), "name": "Acme"})
        return account_id

    def add_file(self, account_id, key, content, replace=True):
        path = self.tmp / ("%s_%s_%s.csv" % (account_id, key, uuid.uuid4().hex[:6]))
        path.write_text(content)
        if replace:
            self.db["account_data_files"].update_many(
                {"account_id": account_id, "dataset_key": key, "status": "active"},
                {"$set": {"status": "replaced"}})
        self.db["account_data_files"].insert_one({
            "account_id": account_id, "dataset_key": key, "status": "active",
            "file_path": str(path), "original_filename": path.name,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "uploaded_at": datetime.now(UTC)})
        return path

    def _runner(self, nid):
        def run(account_id, **_kw):
            self.log.append((account_id, nid))
            if nid in self.gate:
                self.gate[nid].wait(10)
            if nid in self.fail:
                raise self.fail[nid]
            if nid in self.degrade:
                run_context.note_llm(failed=True)
            data = {"node": nid, "updated_at": datetime.now(UTC)}
            if nid == "A":
                data["rows"] = read_dataset_records(account_id, "d1")
            elif nid == "B":
                a = widget_store.get(account_id, "a") or {}
                data["from_a"] = (a.get("data") or {}).get("rows")
                data["rows"] = read_dataset_records(account_id, "d2")
            elif nid == "C":
                b = widget_store.get(account_id, "b") or {}
                data["from_b"] = (b.get("data") or {}).get("rows")
            elif nid == "D":
                data["rows"] = read_dataset_records(account_id, "d3")
            if nid in self.undeclared:
                read_dataset_records(account_id, "d3")
            if nid in self.foreign:
                widget_store.put(account_id, "dw", {"status": "available", "data": {}})
            key = {"A": "a", "B": "b", "C": "c", "D": "dw"}[nid]
            if nid not in self.skip_widget:
                widget_store.put(account_id, key, {"status": "available", "data": data})
            if nid in self.partial_then_fail:
                raise RuntimeError("died after publishing")
        return run

    def drain(self, engine=None, limit=200):
        engine = engine or self.engine
        outcomes = []
        for _ in range(limit):
            out = engine.run_once()
            if out is None:
                return outcomes
            outcomes.append(out)
        raise AssertionError("queue did not drain: %s" % outcomes[-10:])

    def ran(self, account_id):
        return [nid for acct, nid in self.log if acct == account_id]

    def widget(self, account_id, key):
        return widget_store.committed(self.db, account_id, key, self.graph)

    def lifecycle(self, account_id, nid):
        return self.engine.status(account_id)["nodes"][nid]["lifecycle"]

    def status(self, account_id, nid):
        return planner.account_view(self.engine, account_id)["nodes"][nid]["status"]

    def upload(self, account_id, key, content):
        """What the upload endpoint does: store the file, report what is stale."""
        self.add_file(account_id, key, content)
        return self.engine.notify_input_changed(account_id, key, "user:1",
                                                datasets=[key])

    def submit(self, account_id=None, engine=None, **kw):
        """The admin's Submit: an explicit run."""
        kw.setdefault("accounts", [account_id] if account_id else "all")
        return runs.create(engine or self.engine, actor="user:1", **kw)

    def live_jobs(self, account_id=None):
        query = {"status": {"$in": list(jobs.LIVE)}}
        if account_id:
            query["account_id"] = account_id
        return list(self.db[jobs.COLLECTION].find(query))


@pytest.fixture
def h(db, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "GATE_RETRY_SECONDS", 0)
    # Anything a producer reads outside what the engine pinned (an undeclared
    # dataset, deliberately, in one test) goes through the app's own
    # connection. Point that at this test's database too - otherwise it reaches
    # whatever MongoDB the machine has, and on CI, which has none, times out.
    from app.database import mongodb
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    return Harness(db, tmp_path)


def _loaded(h):
    acct = h.account()
    h.add_file(acct, "d1", "x\n1\n")
    h.add_file(acct, "d2", "y\n2\n")
    h.add_file(acct, "d3", "z\n3\n")
    h.submit(acct)
    h.drain()
    h.log.clear()
    return acct


def _enqueue(h, acct, nid, **kw):
    """A job as a run creates it (tests of the queue itself)."""
    return jobs.enqueue(h.db, acct, nid, jobs.trigger("manual"),
                        run_id=kw.pop("run_id", ObjectId()), **kw)


# --------------------------------------------------------------------------
# Cost safety: nothing runs unless a run asked for it
# --------------------------------------------------------------------------

def test_an_upload_queues_nothing_and_reports_what_is_stale(h):
    acct = _loaded(h)
    stale = h.upload(acct, "d1", "x\n10\n")
    assert [n["node_id"] for n in stale] == ["A", "B", "C"]
    assert stale[0]["categories"] == ["data_file"]
    assert h.live_jobs() == [] and h.drain() == [] and h.ran(acct) == []


def test_five_uploads_then_one_submit_run_each_section_once(h):
    acct = h.account()
    for i, (key, content) in enumerate([("d1", "x\n1\n"), ("d2", "y\n2\n"),
                                        ("d3", "z\n3\n"), ("d1", "x\n4\n"),
                                        ("d2", "y\n5\n")]):
        h.upload(acct, key, content)
        assert h.live_jobs() == [], "upload %d queued work" % i
    h.submit(acct)
    h.drain()
    ran = h.ran(acct)
    assert sorted(ran) == ["A", "B", "C", "D"] and len(ran) == 4
    assert ran.index("A") < ran.index("B") < ran.index("C")
    assert h.widget(acct, "b")["data"]["from_a"] == [{"x": "4"}]


def test_a_restart_or_deploy_with_stale_outputs_runs_nothing(h):
    acct = _loaded(h)
    h.add_file(acct, "d3", "z\n42\n")
    bumped = Graph(tuple(Node(**{**n.__dict__, "logic_version": 2}) if n.id == "B" else n
                         for n in NODES))
    fresh = h.make_engine("after-deploy", graph=bumped)
    report = fresh.stale_report()
    assert report["accounts_needing_run"] == 1
    assert fresh.sweep() == report                 # the old name only reports too
    assert h.drain(fresh) == [] and h.live_jobs() == []


def test_a_logic_change_makes_only_that_section_and_its_dependents_stale(h):
    acct = _loaded(h)
    bumped = Graph(tuple(Node(**{**n.__dict__, "logic_version": 2}) if n.id == "B" else n
                         for n in NODES))
    engine = h.make_engine(graph=bumped)
    view = planner.account_view(engine, acct)["nodes"]
    assert view["A"]["status"] == planner.CURRENT
    assert view["D"]["status"] == planner.CURRENT
    assert view["B"]["status"] == planner.STALE
    assert view["B"]["categories"] == ["code"]
    assert view["C"]["status"] == planner.STALE          # waiting on B
    assert h.drain(engine) == []
    h.submit(acct, engine=engine)
    h.drain(engine)
    assert h.ran(acct) == ["B"]            # C re-checked, cut off: identical output


def test_a_prompt_change_is_reported_as_a_prompt_change():
    from app.services.regen import reasons
    old = {"logic": {"own": 1, "refs": {"m:PROMPT_VERSION": 3}, "total": 4}}
    new = {"logic": {"own": 1, "refs": {"m:PROMPT_VERSION": 4}, "total": 5}}
    out = reasons.classify(old, new)
    assert [r["category"] for r in out] == ["prompt"]
    assert out[0]["old"] == 3 and out[0]["new"] == 4


def test_account_run_touches_only_that_account(h):
    one, two = _loaded(h), _loaded(h)
    h.upload(one, "d1", "x\n99\n")
    h.upload(two, "d1", "x\n98\n")
    h.submit(one)
    h.drain()
    assert h.ran(one) == ["A", "B", "C"] and h.ran(two) == []
    assert h.status(two, "A") == planner.STALE


def test_feature_run_runs_that_feature_for_every_account_that_needs_it(h):
    one, two, three = _loaded(h), _loaded(h), _loaded(h)
    h.upload(one, "d3", "z\n1\n")
    h.upload(two, "d3", "z\n2\n")
    h.upload(one, "d1", "x\n5\n")          # A stale too, but not asked for
    h.submit(accounts="all", features=["fd"])
    h.drain()
    assert h.ran(one) == ["D"] and h.ran(two) == ["D"] and h.ran(three) == []
    assert h.status(one, "A") == planner.STALE


def test_account_and_feature_run_runs_exactly_that_pair(h):
    one, two = _loaded(h), _loaded(h)
    for acct in (one, two):
        h.upload(acct, "d3", "z\n7\n")
        h.upload(acct, "d2", "y\n7\n")
    h.submit(one, features=["fd"])
    h.drain()
    assert h.ran(one) == ["D"] and h.ran(two) == []


def test_all_accounts_run_skips_what_is_current(h):
    one, two = _loaded(h), _loaded(h)
    h.upload(one, "d3", "z\n8\n")
    run = h.submit(accounts="all")
    assert run["totals"]["run"] == 1
    assert run["totals"]["skip_current"] == 7
    h.drain()
    assert h.ran(one) == ["D"] and h.ran(two) == []


def test_a_requested_section_brings_its_stale_ancestors_but_not_its_dependents(h):
    acct = _loaded(h)
    h.upload(acct, "d1", "x\n2\n")
    plan = planner.plan(h.engine, accounts=[acct], features=["fb"])
    items = {i["node_id"]: i for i in plan["accounts"][0]["items"]}
    assert items["A"]["action"] == planner.RUN and items["A"]["needed_by"] == ["B"]
    assert items["B"]["action"] == planner.RUN and "C" not in items
    assert plan["accounts"][0]["downstream_left_stale"] == ["C"]
    h.submit(acct, features=["fb"])
    h.drain()
    assert h.ran(acct) == ["A", "B"]
    assert h.status(acct, "C") == planner.STALE


def test_include_downstream_runs_the_dependents_too(h):
    acct = _loaded(h)
    h.upload(acct, "d2", "y\n3\n")
    h.submit(acct, features=["fb"], include_downstream=True)
    h.drain()
    assert h.ran(acct) == ["B", "C"]


def test_force_is_the_only_way_to_rerun_a_current_section(h):
    acct = _loaded(h)
    run = h.submit(acct, features=["fd"])
    assert run["status"] == runs.NOTHING_TO_DO and h.drain() == []
    run = h.submit(acct, features=["fd"], force=True)
    item = run["plan"]["accounts"][0]["items"][0]
    assert item["action"] == planner.RUN and item["forced"] is True
    h.drain()
    assert h.ran(acct) == ["D"]


def test_two_identical_requests_make_one_job(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n5\n")
    first, second = h.submit(acct), h.submit(acct)
    assert first["totals"]["queued"] == 1
    assert second["totals"]["queued"] == 0 and second["totals"]["attached"] == 1
    live = h.live_jobs(acct)
    assert len(live) == 1 and set(live[0]["run_ids"]) == {first["_id"], second["_id"]}
    h.drain()
    assert h.ran(acct) == ["D"]
    assert runs.get(h.db, second["_id"])["status"] == runs.SUCCEEDED


def test_a_current_result_costs_nothing(h):
    acct = _loaded(h)
    plan = planner.plan(h.engine, accounts=[acct])
    assert plan["totals"]["run"] == 0 and plan["totals"]["llm_sections"] == 0


def test_a_section_with_no_data_is_not_run(h):
    acct = h.account()
    h.upload(acct, "d1", "x\n1\n")
    plan = planner.plan(h.engine, accounts=[acct])
    actions = {i["node_id"]: i["action"] for i in plan["accounts"][0]["items"]}
    assert actions["D"] == planner.CANNOT_RUN           # d3 was never uploaded
    assert actions["A"] == actions["B"] == actions["C"] == planner.RUN
    h.submit(acct)
    h.drain()
    assert sorted(h.ran(acct)) == ["A", "B", "C"]


def test_unbound_jobs_are_never_claimed(h):
    acct = _loaded(h)
    jobs.enqueue(h.db, acct, "D", jobs.trigger("input_changed"))   # no run
    assert h.drain() == []
    assert jobs.cancel_unbound(h.db) == 1
    assert h.live_jobs() == []


# --------------------------------------------------------------------------
# Failure: no automatic retry
# --------------------------------------------------------------------------

def test_a_failed_section_is_not_retried_and_dependents_do_not_build_on_it(h):
    acct = _loaded(h)
    before = {k: h.widget(acct, k)["data"] for k in ("a", "b", "c")}
    h.fail["A"] = RuntimeError("model down")
    h.upload(acct, "d1", "x\n2\n")
    h.submit(acct)
    outcomes = h.drain()
    assert h.ran(acct) == ["A"]                         # once - no retry
    assert [o["outcome"] for o in outcomes if o["node_id"] == "A"] == ["failed"]
    assert h.live_jobs() == []
    assert h.status(acct, "A") == planner.FAILED
    assert h.status(acct, "B") == planner.STALE
    for key in ("a", "b", "c"):
        assert h.widget(acct, key)["data"] == before[key]
    view = planner.account_view(h.engine, acct)["nodes"]
    assert view["A"]["last_error"]["code"] == "ERROR"
    assert view["A"]["reasons"][0]["category"] == "failed"
    assert view["B"]["blocked_by"] == ["A"]
    # Nothing brings it back on its own: not the report, not time.
    h.engine.stale_report()
    assert h.drain() == []

    # Fixed and submitted again: the chain completes.
    del h.fail["A"]
    h.submit(acct)
    h.drain()
    assert [h.lifecycle(acct, n) for n in "ABC"] == [state.CURRENT] * 3


def test_quota_exhaustion_fails_the_section_and_pauses_the_queue(h):
    acct = _loaded(h)

    def quota(account_id, **_kw):
        h.log.append((account_id, "D"))
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["D"] = quota
    h.upload(acct, "d3", "z\n6\n")
    h.submit(acct)
    out = h.drain()
    assert [o["outcome"] for o in out] == ["failed"]
    assert out[0]["error"]["code"] == "QUOTA_EXHAUSTED"
    assert jobs.queue_state(h.db)["paused"] is True
    assert h.live_jobs(acct) == []                      # never back in the queue
    node = planner.account_view(h.engine, acct)["nodes"]["D"]
    assert node["status"] == planner.FAILED
    assert node["reasons"][0]["label"] == "QUOTA_EXHAUSTED"
    # The quota is back: an admin resumes and submits it again.
    h.engine.runners["D"] = h._runner("D")
    jobs.resume(h.db, "user:1")
    h.submit(acct)
    h.drain()
    assert h.status(acct, "D") == planner.CURRENT


def test_a_run_that_dies_after_publishing_commits_nothing(h):
    acct = _loaded(h)
    before = h.widget(acct, "b")
    h.partial_then_fail.add("B")
    h.upload(acct, "d2", "y\n5\n")
    h.submit(acct)
    h.drain()
    after = h.widget(acct, "b")
    assert after["data"] == before["data"]
    assert after["generation_id"] == before["generation_id"]


def test_missing_widget_fails_validation(h):
    acct = _loaded(h)
    h.skip_widget.add("D")
    h.submit(acct, features=["fd"], force=True)
    h.drain()
    status = h.engine.status(acct)["nodes"]["D"]
    # The forced rerun failed, but the committed output was built from exactly
    # the current inputs, so it is still CURRENT; the failure is reported.
    assert status["lifecycle"] == state.CURRENT
    assert status["last_error"]["code"] == "VALIDATION"
    # With changed inputs the same failure makes the node FAILED.
    h.upload(acct, "d3", "z\n9\n")
    h.submit(acct)
    h.drain()
    assert h.lifecycle(acct, "D") == state.FAILED


def test_writing_another_nodes_widget_fails_the_run(h):
    acct = _loaded(h)
    before = h.widget(acct, "dw")
    h.foreign.add("A")
    h.submit(acct, features=["fa"], force=True)
    h.drain()
    assert h.engine.status(acct)["nodes"]["A"]["last_error"]["code"] == "FOREIGN_WRITE"
    assert h.widget(acct, "dw")["generation_id"] == before["generation_id"]


def test_undeclared_input_fails_in_strict_mode(h):
    acct = _loaded(h)
    h.undeclared.add("A")
    h.submit(acct, features=["fa"], force=True)
    h.drain()
    assert h.engine.status(acct)["nodes"]["A"]["last_error"]["code"] == "UNDECLARED_INPUT"


def test_degraded_result_never_replaces_a_complete_one(h):
    acct = _loaded(h)
    before = h.widget(acct, "dw")
    h.degrade.add("D")
    h.upload(acct, "d3", "z\n4\n")
    h.submit(acct)
    h.drain()
    assert h.widget(acct, "dw")["generation_id"] == before["generation_id"]
    assert h.lifecycle(acct, "D") == state.FAILED
    assert h.engine.status(acct)["nodes"]["D"]["last_error"]["code"] == "DEGRADED"


def test_degraded_first_result_is_committed_and_marked(h):
    h.degrade.add("D")
    acct = h.account()
    h.upload(acct, "d3", "z\n1\n")
    h.submit(acct)
    h.drain()
    widget = h.widget(acct, "dw")
    assert widget["status"] == "available"
    assert widget["generation_quality"] == state.DEGRADED
    # Shown as degraded - part of the next Submit - and never retried alone.
    assert h.status(acct, "D") == planner.DEGRADED
    assert h.drain() == []


def test_run_records_usage_and_progress(h):
    acct = _loaded(h)

    def busy(account_id, **_kw):
        h.log.append((account_id, "D"))
        run_context.note_api_call(120)
        run_context.note_api_call(80)
        run_context.progress(1, 2, "half")
        widget_store.put(account_id, "dw", {"status": "available", "data": {"n": 1}})

    h.engine.runners["D"] = busy
    h.upload(acct, "d3", "z\n11\n")
    run = h.submit(acct)
    h.drain()
    got = runs.get(h.db, run["_id"])
    assert got["status"] == runs.SUCCEEDED
    assert got["usage"]["model_calls"] == 2 and got["usage"]["tokens"] == 200
    [job] = got["jobs"]
    assert job["node_id"] == "D" and job["changed_inputs"] == ["datasets.d3"]


# --------------------------------------------------------------------------
# Coalescing, concurrency, fencing, restart
# --------------------------------------------------------------------------

def test_duplicate_triggers_coalesce_into_one_job(h):
    acct = _loaded(h)
    for i in range(3):
        jobs.enqueue(h.db, acct, "D", jobs.trigger("manual", "click %d" % i, "user:1"),
                     priority=jobs.PRIORITY_MANUAL, force=True, run_id=ObjectId())
    live = h.live_jobs(acct)
    assert len(live) == 1 and len(live[0]["triggers"]) == 3
    assert len(live[0]["run_ids"]) == 3
    h.drain()
    assert h.ran(acct) == ["D"]


def test_a_request_during_a_run_requests_exactly_one_rerun(h):
    acct = _loaded(h)
    _enqueue(h, acct, "D", force=True)
    job = jobs.claim(h.db, "w1")
    assert job["node_id"] == "D"
    for _ in range(3):
        _enqueue(h, acct, "D", force=True)
    assert jobs.finish(h.db, job, jobs.SUCCEEDED)
    pending = list(h.db[jobs.COLLECTION].find({"account_id": acct, "node_id": "D",
                                               "status": jobs.PENDING}))
    assert len(pending) == 1 and len(pending[0]["run_ids"]) == 3


def test_one_running_job_per_account_many_accounts_in_parallel(h):
    one, two = _loaded(h), _loaded(h)
    for acct in (one, two):
        for nid in ("A", "D"):
            _enqueue(h, acct, nid, force=True)
    first = jobs.claim(h.db, "w1")
    second = jobs.claim(h.db, "w2")
    third = jobs.claim(h.db, "w3")
    assert first and second and third is None
    assert first["account_id"] != second["account_id"]


def test_concurrent_workers_never_run_the_same_account_twice(h):
    acct = _loaded(h)
    for nid in ("A", "D"):
        _enqueue(h, acct, nid, force=True)
    release = threading.Event()
    h.gate["A"] = release
    h.gate["D"] = release
    engines = [h.make_engine("w%d" % i) for i in range(3)]
    results = []
    threads = [threading.Thread(target=lambda e=e: results.append(e.run_once()))
               for e in engines]
    for t in threads:
        t.start()
    import time
    time.sleep(0.3)
    running = h.db[jobs.COLLECTION].count_documents({"account_id": acct,
                                                     "status": jobs.RUNNING})
    release.set()
    for t in threads:
        t.join(10)
    assert running == 1


def test_a_reclaimed_workers_late_commit_is_fenced_out(h):
    acct = _loaded(h)
    started, release = threading.Event(), threading.Event()

    def slow(account_id, **_kw):
        started.set()
        release.wait(10)
        widget_store.put(account_id, "dw", {"status": "available", "data": {"v": "late"}})

    h.runners["D"] = slow
    _enqueue(h, acct, "D", force=True)
    slow_engine = h.make_engine("slow")
    outcome = {}
    t = threading.Thread(target=lambda: outcome.update(slow_engine.run_once()))
    t.start()
    started.wait(5)
    # The lease lapses; another worker reclaims and finishes the job.
    h.db[jobs.COLLECTION].update_one({"account_id": acct, "node_id": "D",
                                      "status": jobs.RUNNING},
                                     {"$set": {"lease_expires_at":
                                               datetime.now(UTC) - timedelta(seconds=1)}})
    h.runners["D"] = h._runner("D")
    h.drain(h.make_engine("rescuer"))
    rescued = h.widget(acct, "dw")
    release.set()
    t.join(10)
    assert h.widget(acct, "dw")["generation_id"] == rescued["generation_id"]
    assert h.widget(acct, "dw")["data"].get("v") != "late"
    # The job row now carries the rescuer's fence, so the late worker cannot
    # even mark it - its result is simply discarded.
    assert outcome["outcome"] == "fenced"


def test_exhausted_lease_fails_the_job_instead_of_blocking_the_node(h):
    acct = _loaded(h)
    _enqueue(h, acct, "D", force=True)
    job = jobs.claim(h.db, "ghost")
    h.db[jobs.COLLECTION].update_one(
        {"_id": job["_id"]},
        {"$set": {"attempts": jobs.MAX_ATTEMPTS,
                  "lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)}})
    state.mark_running(h.db, acct, "D", job, "fp")
    assert h.engine.run_once() is None
    assert h.db[jobs.COLLECTION].find_one({"_id": job["_id"]})["status"] == jobs.FAILED
    assert (h.db[state.COLLECTION].find_one({"_id": state.state_id(acct, "D")})
            .get("running")) is None
    # The node is not stuck: the next run runs it.
    h.submit(acct, features=["fd"], force=True)
    h.drain()
    assert h.lifecycle(acct, "D") == state.CURRENT


def test_queued_jobs_survive_a_restart(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n77\n")
    h.submit(acct)
    # The process "restarts": a brand-new engine with no memory drains the queue.
    fresh = h.make_engine("after-restart")
    h.drain(fresh)
    assert h.ran(acct) == ["D"]
    assert h.widget(acct, "dw")["data"]["rows"] == [{"z": "77"}]


def test_a_file_missing_when_the_job_starts_fails_it_with_the_reason(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n8\n")
    h.submit(acct)
    row = h.db["account_data_files"].find_one({"account_id": acct, "dataset_key": "d3",
                                               "status": "active"})
    os.remove(row["file_path"])
    out = h.engine.run_once()
    assert out["outcome"] == "failed" and out["error"]["code"] == "FILES_MISSING"
    assert h.live_jobs(acct) == []                      # never back in the queue
    node = planner.account_view(h.engine, acct)["nodes"]["D"]
    assert node["status"] == planner.FILES_MISSING
    assert node["last_error"]["code"] == "FILES_MISSING"


def test_cancelling_a_run_removes_its_queued_jobs(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n12\n")
    run = h.submit(acct)
    out = runs.cancel(h.db, run["_id"], "user:1")
    assert out["cancelled"] == 1 and h.live_jobs() == []
    assert runs.get(h.db, run["_id"])["status"] == runs.CANCELLED


# --------------------------------------------------------------------------
# Logic changes, legacy data, mirror, downgrade guard
# --------------------------------------------------------------------------

def test_older_code_never_overwrites_newer_logic(h):
    acct = _loaded(h)
    bumped = Graph(tuple(Node(**{**n.__dict__, "logic_version": 5}) if n.id == "D" else n
                         for n in NODES))
    newer = h.make_engine("new", graph=bumped)
    h.submit(acct, engine=newer, features=["fd"])
    h.drain(newer)
    committed = h.widget(acct, "dw")["generation_id"]
    h.submit(acct, features=["fd"], force=True)     # old code, logic 1
    h.drain()
    assert h.widget(acct, "dw")["generation_id"] == committed


def test_legacy_output_is_reported_stale_and_only_run_when_submitted(h):
    accounts = [_loaded(h) for _ in range(3)]
    for acct in accounts:
        h.db[state.COLLECTION].update_many({"account_id": acct},
                                           {"$set": {"current.fingerprint": None}})
        assert h.status(acct, "A") == planner.STALE
        assert planner.account_view(h.engine, acct)["nodes"]["A"]["categories"] == ["legacy"]
    assert h.engine.stale_report()["accounts_needing_run"] == 3
    assert h.drain() == []
    h.submit(accounts[0])
    h.drain()
    assert sorted(h.ran(accounts[0])) == ["A", "B", "C", "D"]
    assert h.ran(accounts[1]) == []


def test_mirror_keeps_account_widgets_in_step_and_never_goes_backwards(h):
    acct = _loaded(h)
    mirrored = h.db["account_widgets"].find_one({"account_id": acct, "widget_key": "dw"})
    committed = h.widget(acct, "dw")
    assert mirrored["data"] == committed["data"] and mirrored["rev"] >= 1
    h.engine._mirror(acct, {"widgets": {"dw": {"status": "available",
                                               "data": {"old": True}}}}, rev=0)
    again = h.db["account_widgets"].find_one({"account_id": acct, "widget_key": "dw"})
    assert again["data"] == committed["data"]


def test_status_reports_every_lifecycle(h):
    acct = h.account()
    assert h.lifecycle(acct, "A") == state.NEVER_GENERATED
    # Nothing uploaded: the fix is an upload, so it says so instead of "never run".
    assert h.status(acct, "A") == planner.NO_DATA
    h.upload(acct, "d1", "x\n1\n")
    assert h.status(acct, "A") == planner.NEVER_RUN
    h.submit(acct, features=["fa"])
    assert h.status(acct, "A") == planner.QUEUED
    job = jobs.claim(h.db, "w9")
    assert job["node_id"] == "A"
    assert h.lifecycle(acct, "A") == state.GENERATING
    assert h.status(acct, "A") == planner.RUNNING
    h.engine.run_job(job)
    assert h.lifecycle(acct, "A") == state.CURRENT
    features = h.engine.status(acct)["features"]
    assert features["fa"]["lifecycle"] == state.CURRENT
    assert features["fd"]["lifecycle"] == state.NEVER_GENERATED


def test_a_restart_fails_the_running_job_as_interrupted(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n40\n")
    h.submit(acct)
    job = jobs.claim(h.db, "old-backend")
    target = h.engine.expected_all(load_snapshot(h.db, acct))[1]["D"]
    jobs.start_attempt(h.db, job, target, None, [])
    other = _loaded(h)
    _enqueue(h, other, "D", force=True)
    theirs = jobs.claim(h.db, "another-worker")

    failed = jobs.fail_owned(h.db, "old-backend")
    assert [r["_id"] for r in failed] == [job["_id"]]
    h.engine.record_job_failure(failed[0], jobs.INTERRUPTED, jobs.INTERRUPTED_MESSAGE)
    row = h.db[jobs.COLLECTION].find_one({"_id": job["_id"]})
    assert row["status"] == jobs.FAILED and row["error"]["code"] == jobs.INTERRUPTED
    assert h.status(acct, "D") == planner.FAILED
    # Another worker's job is not touched.
    assert h.db[jobs.COLLECTION].find_one({"_id": theirs["_id"]})["status"] == jobs.RUNNING
    # The old worker's late commit is fenced out, and nothing re-queues it.
    assert not jobs.finish(h.db, job, jobs.SUCCEEDED)
    assert jobs.claim(h.db, "new-backend") is None


def test_a_dead_workers_lease_lapses_within_minutes():
    from app.services.regen import engine as regen_engine
    assert jobs.LEASE_SECONDS <= 300
    assert regen_engine.HEARTBEAT_SECONDS * 3 <= jobs.LEASE_SECONDS


def test_an_engine_crash_fails_the_job_instead_of_looping(h, monkeypatch):
    acct = _loaded(h)
    _enqueue(h, acct, "D", force=True)

    def boom(_job):
        raise RuntimeError("engine bug")

    monkeypatch.setattr(h.engine, "run_job", boom)
    out = h.engine.run_once()
    assert out["outcome"] == "failed" and out["error"]["code"] == "ENGINE_ERROR"
    assert h.live_jobs(acct) == []


def test_a_job_whose_worker_died_is_failed_not_requeued(h):
    acct = _loaded(h)
    _enqueue(h, acct, "D", force=True)
    job = jobs.claim(h.db, "dies")
    h.db[jobs.COLLECTION].update_one(
        {"_id": job["_id"]},
        {"$set": {"lease_expires_at": datetime.now(UTC) - timedelta(seconds=1)}})
    assert h.engine.run_once() is None
    row = h.db[jobs.COLLECTION].find_one({"_id": job["_id"]})
    assert row["status"] == jobs.FAILED and row["error"]["code"] == jobs.WORKER_STOPPED
    assert h.live_jobs(acct) == []


# --------------------------------------------------------------------------
# Files recorded in the database but not on this server
# --------------------------------------------------------------------------

def test_a_section_whose_files_are_missing_cannot_run_and_says_why(h):
    acct = _loaded(h)
    path = h.upload(acct, "d3", "z\n21\n") and h.db["account_data_files"].find_one(
        {"account_id": acct, "dataset_key": "d3", "status": "active"})["file_path"]
    os.remove(path)
    node = planner.account_view(h.engine, acct)["nodes"]["D"]
    assert node["status"] == planner.FILES_MISSING
    assert node["reasons"][0]["category"] == "files_missing"
    assert len(node["missing_files"]) == 1
    run = h.submit(acct)
    item = next(i for i in run["plan"]["accounts"][0]["items"] if i["node_id"] == "D")
    assert item["action"] == planner.CANNOT_RUN
    assert h.live_jobs() == [] and h.drain() == []


def test_a_section_failed_for_missing_files_runs_again_once_they_are_back(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n22\n")
    h.submit(acct)
    row = h.db["account_data_files"].find_one({"account_id": acct, "dataset_key": "d3",
                                               "status": "active"})
    os.remove(row["file_path"])
    assert h.engine.run_once()["outcome"] == "failed"
    assert h.status(acct, "D") == planner.FILES_MISSING
    # Still missing: a submit does not run it.
    assert h.submit(acct)["totals"]["queued"] == 0
    with open(row["file_path"], "w") as fh:
        fh.write("z\n22\n")
    assert h.status(acct, "D") == planner.FAILED
    assert h.submit(acct)["totals"]["queued"] == 1
    h.drain()
    assert h.ran(acct) == ["D"] and h.status(acct, "D") == planner.CURRENT


def test_a_dataset_a_section_starts_reading_is_not_reported_as_deleted():
    from app.services.regen import reasons
    old = {"datasets": {"a": "v1"}}
    new = {"datasets": {"a": "v1", "filings_financials": "none"}}
    [r] = reasons.classify(old, new)
    assert r["category"] == "data_file" and "newly read" in r["detail"]
    assert "deleted" not in r["detail"]



def test_usage_of_a_run_stopped_by_the_quota_is_recorded(h):
    acct = _loaded(h)

    def quota(account_id, **_kw):
        run_context.note_api_call(100)
        run_context.note_api_call(100)
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["D"] = quota
    h.upload(acct, "d3", "z\n31\n")
    run = h.submit(acct)
    h.drain()
    got = runs.get(h.db, run["_id"])
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert got["usage"]["model_calls"] == 2 and got["usage"]["tokens"] == 200


# Quota pause: a window that closes on its own
#
# The pause is right - without it the sections queued behind a refusal each burn
# their attempts on the same exhausted quota and all end FAILED. What was wrong
# is that only an admin could lift it, so a 429 at 2am stopped every account
# until somebody opened the Pipeline tab.

def test_a_quota_pause_records_when_it_lifts(h):
    acct = _loaded(h)

    def quota(account_id, **_kw):
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["D"] = quota
    h.upload(acct, "d3", "z\n6\n")
    h.submit(acct)
    h.drain()

    queue = jobs.queue_state(h.db)
    assert queue["paused"] is True
    assert queue["resume_after"] is not None
    assert "resumes by itself" in queue["reason"]


def test_the_queue_carries_on_once_the_window_has_passed(h):
    """The rest of the queue is what the pause was protecting. It should not
    need a human to get it back."""
    acct = _loaded(h)

    def quota(account_id, **_kw):
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["D"] = quota
    h.upload(acct, "d3", "z\n6\n")
    h.submit(acct)
    h.drain()
    assert jobs.queue_state(h.db)["paused"] is True
    assert h.engine.run_once() is None              # nothing runs while it stands

    h.db[jobs.CONTROL].update_one(
        {"_id": jobs.QUEUE_DOC},
        {"$set": {"resume_after": datetime.now(UTC) - timedelta(seconds=1)}})

    assert jobs.lift_expired_pause(h.db) is True
    assert jobs.queue_state(h.db)["paused"] is False
    doc = h.db[jobs.CONTROL].find_one({"_id": jobs.QUEUE_DOC})
    assert doc["resumed_by"] == "engine:quota-window"    # not a human's resume


def test_the_section_that_hit_the_quota_is_not_requeued_by_the_window(h):
    """"Failed stays failed" is the branch's rule and the window does not bend
    it: the pause lifting lets the OTHER sections run, nothing more."""
    acct = _loaded(h)

    def quota(account_id, **_kw):
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["D"] = quota
    h.upload(acct, "d3", "z\n6\n")
    h.submit(acct)
    h.drain()

    h.db[jobs.CONTROL].update_one(
        {"_id": jobs.QUEUE_DOC},
        {"$set": {"resume_after": datetime.now(UTC) - timedelta(seconds=1)}})
    jobs.lift_expired_pause(h.db)

    assert h.live_jobs(acct) == []
    assert planner.account_view(h.engine, acct)["nodes"]["D"]["status"] == planner.FAILED


def test_a_pause_with_no_window_waits_for_a_human(h):
    """REGEN_QUOTA_PAUSE_SECONDS=0, and an admin's pause, which never carries
    one."""
    jobs.pause(h.db, "paused by an admin", by="user:1")
    assert jobs.queue_state(h.db)["resume_after"] is None
    assert jobs.lift_expired_pause(h.db) is False
    assert jobs.queue_state(h.db)["paused"] is True


def test_an_admin_can_still_resume_inside_the_window(h):
    jobs.pause(h.db, "model quota exhausted", by="engine", seconds=900)
    assert jobs.lift_expired_pause(h.db) is False        # not yet
    jobs.resume(h.db, "user:1")
    assert jobs.queue_state(h.db)["paused"] is False


def test_two_workers_lift_one_pause_between_them(h):
    jobs.pause(h.db, "model quota exhausted", by="engine", seconds=900)
    h.db[jobs.CONTROL].update_one(
        {"_id": jobs.QUEUE_DOC},
        {"$set": {"resume_after": datetime.now(UTC) - timedelta(seconds=1)}})
    lifted = [jobs.lift_expired_pause(h.db), jobs.lift_expired_pause(h.db)]
    assert lifted == [True, False]
