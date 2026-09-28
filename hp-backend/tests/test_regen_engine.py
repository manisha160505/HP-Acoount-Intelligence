"""The regeneration engine end to end: invalidation, order, atomicity, failure,
coalescing, concurrency and restart.

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
from app.services.regen import context as run_context, jobs, manifest, state, store as widget_store
from app.services.regen.engine import Engine
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

    def upload(self, account_id, key, content):
        self.add_file(account_id, key, content)
        return self.engine.notify_input_changed(account_id, key, "user:1")


@pytest.fixture
def h(db, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "GATE_RETRY_SECONDS", 0)
    return Harness(db, tmp_path)


def _loaded(h):
    acct = h.account()
    h.add_file(acct, "d1", "x\n1\n")
    h.add_file(acct, "d2", "y\n2\n")
    h.add_file(acct, "d3", "z\n3\n")
    h.engine.notify_input_changed(acct, "initial load", "user:1")
    h.drain()
    h.log.clear()
    return acct


# --------------------------------------------------------------------------
# Invalidation and ordering
# --------------------------------------------------------------------------

def test_first_load_generates_everything_in_dependency_order(h):
    acct = h.account()
    for key, content in (("d1", "x\n1\n"), ("d2", "y\n2\n"), ("d3", "z\n3\n")):
        h.add_file(acct, key, content)
    h.engine.notify_input_changed(acct, "initial load", "user:1")
    h.drain()
    ran = h.ran(acct)
    assert ran.index("A") < ran.index("B") < ran.index("C")
    assert sorted(ran) == ["A", "B", "C", "D"]
    for nid in "ABCD":
        assert h.lifecycle(acct, nid) == state.CURRENT


def test_document_change_regenerates_only_affected_nodes_in_order(h):
    acct = _loaded(h)
    h.upload(acct, "d1", "x\n10\n")
    assert h.lifecycle(acct, "A") == state.STALE
    # B and C are stale too, before anything has run: their ancestor is.
    assert h.lifecycle(acct, "B") == state.STALE
    assert h.lifecycle(acct, "C") == state.STALE
    assert h.lifecycle(acct, "D") == state.CURRENT
    h.drain()
    assert h.ran(acct) == ["A", "B", "C"]
    assert h.widget(acct, "b")["data"]["from_a"] == [{"x": "10"}]
    assert h.widget(acct, "c")["data"]["from_b"] == [{"y": "2"}]


def test_change_to_a_leaf_dataset_leaves_its_upstream_alone(h):
    acct = _loaded(h)
    h.upload(acct, "d2", "y\n20\n")
    h.drain()
    assert h.ran(acct) == ["B", "C"]


def test_unrelated_node_is_never_regenerated(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n30\n")
    h.drain()
    assert h.ran(acct) == ["D"]


def test_identical_reupload_regenerates_nothing(h):
    acct = _loaded(h)
    plan = h.upload(acct, "d1", "x\n1\n")
    assert plan == []
    assert h.drain() == []


def test_early_cutoff_unchanged_upstream_output_does_not_cascade(h):
    acct = _loaded(h)
    # Force A to rerun; it produces the same content (volatile fields aside).
    h.engine.regenerate_feature(acct, "fa", "user:1")
    h.drain()
    assert h.ran(acct) == ["A"]


def test_account_isolation(h):
    one, two = _loaded(h), _loaded(h)
    h.upload(one, "d1", "x\n99\n")
    h.drain()
    assert h.ran(two) == []
    assert h.lifecycle(two, "A") == state.CURRENT


# --------------------------------------------------------------------------
# Manual and independent regeneration
# --------------------------------------------------------------------------

def test_manual_regenerate_runs_only_that_feature_and_is_forced(h):
    acct = _loaded(h)
    out = h.engine.regenerate_feature(acct, "fd", "user:7")
    assert [n["node_id"] for n in out["nodes"]] == ["D"]
    h.drain()
    assert h.ran(acct) == ["D"]          # forced although nothing changed
    job = h.db[jobs.COLLECTION].find_one({"account_id": acct, "node_id": "D",
                                          "status": jobs.SUCCEEDED},
                                         sort=[("finished_at", -1)])
    assert job["triggers"][0]["actor"] == "user:7"


def test_never_generated_nodes_are_not_built_by_the_sweep(h):
    acct = h.account()
    h.add_file(acct, "d1", "x\n1\n")
    summary = h.engine.sweep()
    assert summary["queued"] == 0
    assert h.lifecycle(acct, "A") == state.NEVER_GENERATED


def test_gate_pulls_a_stale_ancestor_nobody_queued(h):
    acct = _loaded(h)
    # Make A legacy (unverified) without queueing it, then ask for C.
    h.db[state.COLLECTION].update_one({"_id": state.state_id(acct, "A")},
                                      {"$set": {"current.fingerprint": None}})
    h.engine.regenerate_feature(acct, "fc", "user:1")
    h.drain()
    ran = h.ran(acct)
    assert "A" in ran and ran.index("A") < ran.index("C")


# --------------------------------------------------------------------------
# Failure keeps the previous output; downstream does not build on it
# --------------------------------------------------------------------------

def test_failed_upstream_blocks_dependents_and_keeps_every_previous_output(h):
    acct = _loaded(h)
    before = {k: h.widget(acct, k)["data"] for k in ("a", "b", "c")}
    h.fail["A"] = RuntimeError("model down")
    h.upload(acct, "d1", "x\n2\n")
    for _ in range(jobs.MAX_ATTEMPTS + 1):
        h.drain()
        h.db[jobs.COLLECTION].update_many({"status": jobs.PENDING},
                                          {"$set": {"not_before": datetime.now(UTC)}})
    assert h.lifecycle(acct, "A") == state.FAILED
    assert h.lifecycle(acct, "B") == state.STALE
    assert h.lifecycle(acct, "C") == state.STALE
    assert "B" not in h.ran(acct) and "C" not in h.ran(acct)
    for key in ("a", "b", "c"):
        assert h.widget(acct, key)["data"] == before[key]
    status = h.engine.status(acct)["nodes"]
    assert status["A"]["last_error"]["code"] == "ERROR"
    assert status["B"]["blocked_by"] == ["A"]

    # Recovery: the next successful run releases the chain.
    del h.fail["A"]
    h.engine.regenerate_feature(acct, "fa", "user:1")
    h.drain()
    assert [h.lifecycle(acct, n) for n in "ABC"] == [state.CURRENT] * 3


def test_a_run_that_dies_after_publishing_commits_nothing(h):
    acct = _loaded(h)
    before = h.widget(acct, "b")
    h.partial_then_fail.add("B")
    h.upload(acct, "d2", "y\n5\n")
    h.drain()
    after = h.widget(acct, "b")
    assert after["data"] == before["data"]
    assert after["generation_id"] == before["generation_id"]


def test_missing_widget_fails_validation(h):
    acct = _loaded(h)
    h.skip_widget.add("D")
    h.engine.regenerate_feature(acct, "fd", "user:1")
    h.drain()
    status = h.engine.status(acct)["nodes"]["D"]
    # The forced rerun failed, but the committed output was built from exactly
    # the current inputs, so it is still CURRENT; the failure is reported.
    assert status["lifecycle"] == state.CURRENT
    assert status["last_error"]["code"] == "VALIDATION"
    # With changed inputs the same failure makes the node FAILED.
    h.upload(acct, "d3", "z\n9\n")
    h.drain()
    assert h.lifecycle(acct, "D") == state.FAILED


def test_writing_another_nodes_widget_fails_the_run(h):
    acct = _loaded(h)
    before = h.widget(acct, "dw")
    h.foreign.add("A")
    h.engine.regenerate_feature(acct, "fa", "user:1")
    h.drain()
    assert h.engine.status(acct)["nodes"]["A"]["last_error"]["code"] == "FOREIGN_WRITE"
    assert h.widget(acct, "dw")["generation_id"] == before["generation_id"]


def test_undeclared_input_fails_in_strict_mode(h):
    acct = _loaded(h)
    h.undeclared.add("A")
    h.engine.regenerate_feature(acct, "fa", "user:1")
    h.drain()
    assert h.engine.status(acct)["nodes"]["A"]["last_error"]["code"] == "UNDECLARED_INPUT"


def test_degraded_result_never_replaces_a_complete_one(h):
    acct = _loaded(h)
    before = h.widget(acct, "dw")
    h.degrade.add("D")
    h.upload(acct, "d3", "z\n4\n")
    h.drain()
    assert h.widget(acct, "dw")["generation_id"] == before["generation_id"]
    assert h.lifecycle(acct, "D") == state.FAILED
    assert h.engine.status(acct)["nodes"]["D"]["last_error"]["code"] == "DEGRADED"


def test_degraded_first_result_is_committed_and_marked(h):
    h.degrade.add("D")
    acct = h.account()
    h.add_file(acct, "d3", "z\n1\n")
    h.engine.notify_input_changed(acct, "load", "user:1")
    h.drain()
    widget = h.widget(acct, "dw")
    assert widget["status"] == "available"
    assert widget["generation_quality"] == state.DEGRADED
    # Its retry is scheduled, not immediate.
    assert h.engine.sweep()["queued"] == 0


# --------------------------------------------------------------------------
# Coalescing, concurrency, fencing, restart
# --------------------------------------------------------------------------

def test_duplicate_triggers_coalesce_into_one_job(h):
    acct = _loaded(h)
    for i in range(3):
        jobs.enqueue(h.db, acct, "D", jobs.trigger("manual", "click %d" % i, "user:1"),
                     priority=jobs.PRIORITY_MANUAL, force=True)
    live = list(h.db[jobs.COLLECTION].find({"account_id": acct, "node_id": "D",
                                            "status": {"$in": list(jobs.LIVE)}}))
    assert len(live) == 1 and len(live[0]["triggers"]) == 3
    h.drain()
    assert h.ran(acct) == ["D"]


def test_trigger_during_a_run_requests_exactly_one_rerun(h):
    acct = _loaded(h)
    jobs.enqueue(h.db, acct, "D", jobs.trigger("manual"), force=True)
    job = jobs.claim(h.db, "w1")
    assert job["node_id"] == "D"
    for _ in range(3):
        jobs.enqueue(h.db, acct, "D", jobs.trigger("manual"), force=True)
    assert jobs.finish(h.db, job, jobs.SUCCEEDED)
    pending = list(h.db[jobs.COLLECTION].find({"account_id": acct, "node_id": "D",
                                               "status": jobs.PENDING}))
    assert len(pending) == 1


def test_one_running_job_per_account_many_accounts_in_parallel(h):
    one, two = _loaded(h), _loaded(h)
    for acct in (one, two):
        for nid in ("A", "D"):
            jobs.enqueue(h.db, acct, nid, jobs.trigger("manual"), force=True)
    first = jobs.claim(h.db, "w1")
    second = jobs.claim(h.db, "w2")
    third = jobs.claim(h.db, "w3")
    assert first and second and third is None
    assert first["account_id"] != second["account_id"]


def test_concurrent_workers_never_run_the_same_account_twice(h):
    acct = _loaded(h)
    for nid in ("A", "D"):
        jobs.enqueue(h.db, acct, nid, jobs.trigger("manual"), force=True)
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
    jobs.enqueue(h.db, acct, "D", jobs.trigger("manual"), force=True)
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
    jobs.enqueue(h.db, acct, "D", jobs.trigger("manual"), force=True)
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
    # The node is not stuck: a new trigger queues and runs.
    h.engine.regenerate_feature(acct, "fd", "user:1")
    h.drain()
    assert h.lifecycle(acct, "D") == state.CURRENT


def test_queued_jobs_survive_a_restart(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n77\n")
    # The process "restarts": a brand-new engine with no memory drains the queue.
    fresh = h.make_engine("after-restart")
    h.drain(fresh)
    assert h.ran(acct) == ["D"]
    assert h.widget(acct, "dw")["data"]["rows"] == [{"z": "77"}]


def test_file_missing_here_releases_without_spending_an_attempt(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n8\n")
    row = h.db["account_data_files"].find_one({"account_id": acct, "dataset_key": "d3",
                                               "status": "active"})
    os.remove(row["file_path"])
    out = h.engine.run_once()
    assert out["outcome"] == "not_runnable_here"
    job = h.db[jobs.COLLECTION].find_one({"account_id": acct, "node_id": "D",
                                          "status": jobs.PENDING})
    assert job["attempts"] == 0 and "w1" in job["not_runnable_on"]
    assert h.engine.run_once() is None       # w1 will not take it again


# --------------------------------------------------------------------------
# Logic changes, legacy data, mirror, downgrade guard
# --------------------------------------------------------------------------

def test_logic_version_change_invalidates_through_the_same_path(h):
    acct = _loaded(h)
    bumped = Graph(tuple(Node(**{**n.__dict__, "logic_version": 2}) if n.id == "B" else n
                         for n in NODES))
    engine = h.make_engine(graph=bumped)
    assert engine.status(acct)["nodes"]["B"]["lifecycle"] == state.STALE
    engine.sweep()
    h.drain(engine)
    assert h.ran(acct) == ["B"]            # C cut off: identical output


def test_older_code_never_overwrites_newer_logic(h):
    acct = _loaded(h)
    bumped = Graph(tuple(Node(**{**n.__dict__, "logic_version": 5}) if n.id == "D" else n
                         for n in NODES))
    newer = h.make_engine("new", graph=bumped)
    newer.regenerate_feature(acct, "fd", "user:1")
    h.drain(newer)
    committed = h.widget(acct, "dw")["generation_id"]
    h.engine.regenerate_feature(acct, "fd", "user:1")     # old code, logic 1
    h.drain()
    assert h.widget(acct, "dw")["generation_id"] == committed


def test_legacy_output_is_stale_and_regenerated_progressively(h):
    accounts = [_loaded(h) for _ in range(3)]
    for acct in accounts:
        h.db[state.COLLECTION].update_many({"account_id": acct},
                                           {"$set": {"current.fingerprint": None}})
        assert h.lifecycle(acct, "A") == state.STALE
    summary = h.engine.sweep(legacy_accounts=2)
    assert len(summary["legacy_accounts"]) == 2
    queued = list(h.db[jobs.COLLECTION].find({"status": jobs.PENDING}))
    assert queued and all(j["priority"] == jobs.PRIORITY_LEGACY for j in queued)


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
    h.add_file(acct, "d1", "x\n1\n")
    h.engine.notify_input_changed(acct, "load", "user:1")
    job = jobs.claim(h.db, "w9")
    assert job["node_id"] == "A"
    assert h.lifecycle(acct, "A") == state.GENERATING
    h.engine.run_job(job)
    assert h.lifecycle(acct, "A") == state.CURRENT
    features = h.engine.status(acct)["features"]
    assert features["fa"]["lifecycle"] == state.CURRENT
    assert features["fd"]["lifecycle"] == state.NEVER_GENERATED


def test_a_failed_ancestor_parks_dependents_instead_of_retrying_them(h):
    acct = _loaded(h)
    h.fail["A"] = RuntimeError("model down")
    h.upload(acct, "d1", "x\n3\n")
    for _ in range(jobs.MAX_ATTEMPTS + 1):
        h.drain()
        h.db[jobs.COLLECTION].update_many({"status": jobs.PENDING},
                                          {"$set": {"not_before": datetime.now(UTC)}})
    # A new input for B arrives while A is failed: B is parked, not cycled.
    h.upload(acct, "d2", "y\n4\n")
    outcomes = h.drain()
    assert [o["outcome"] for o in outcomes if o["node_id"] == "B"] == ["blocked"]
    assert h.db[jobs.COLLECTION].count_documents(
        {"account_id": acct, "status": {"$in": list(jobs.LIVE)}}) == 0
    assert h.engine.status(acct)["nodes"]["B"]["blocked_by"] == ["A"]
    # A recovers: B is re-queued by the reconcile after A commits, and runs.
    del h.fail["A"]
    h.engine.regenerate_feature(acct, "fa", "user:1")
    h.drain()
    assert [h.lifecycle(acct, n) for n in "ABC"] == [state.CURRENT] * 3


def test_first_upload_builds_only_what_reads_it_and_what_depends_on_that(h):
    acct = h.account()
    h.add_file(acct, "d1", "x\n1\n")
    plan = h.engine.notify_input_changed(acct, "d1 uploaded", "user:1", datasets=["d1"])
    assert [p["node_id"] for p in plan] == ["A"]
    h.drain()
    assert sorted(h.ran(acct)) == ["A", "B", "C"]      # B and C follow A's commit
    assert h.lifecycle(acct, "D") == state.NEVER_GENERATED
