"""Reconcile, run and commit: the whole regeneration path in one place.

Every trigger - an upload, a delete, a config edit, a manual click, a logic
change picked up by the sweep, an upstream node committing - calls
`reconcile(account)`. Reconcile works out the fingerprint each node would have
if it ran now, compares it with what is committed, and enqueues the nodes that
differ. The worker then runs one job at a time per account:

    claim -> gate -> pin -> skip? -> files here? -> run -> validate -> commit
          -> finish -> mirror -> reconcile (dependents)

The guarantees and where they come from:

  * a failed run never touches the committed output - `state.commit` is the
    only write that changes it, and it happens after validation;
  * a reader never sees half a run - the commit is one document;
  * no node is built on a stale or failed upstream - the gate;
  * no node runs twice at once, and no two nodes of one account run at once -
    the unique partial indexes in `jobs`, and the fence on every write;
  * CURRENT always means "built from exactly the current inputs" - it is
    derived by `state.derive` from fingerprints, never stored.
"""

import importlib
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import bson
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.observability import pipeline
from app.services.extractors.datasets import DatasetFileMissing
from app.services.regen import context as run_context, jobs, manifest, state
from app.services.regen.graph import DEFAULT, INDEX
from app.services.regen.store import WIDGET_FIELDS, shape

logger = logging.getLogger(__name__)

CONTENT_STATUSES = frozenset({"available", "partial", "empty", "pending", "error",
                              "unavailable", "unverified"})
MAX_GENERATION_BYTES = 12 * 1024 * 1024
HEARTBEAT_SECONDS = 60
# Automatic retries of a node that failed (or published a degraded result) for
# unchanged inputs: after 1 h, 6 h and 24 h, then only by hand.
RETRY_SCHEDULE = (3600, 6 * 3600, 24 * 3600)
LEGACY_ACCOUNTS_PER_SWEEP = 5

# Failures that another attempt cannot fix. They fail the job at once instead of
# spending the retry budget on the same outcome.
DETERMINISTIC = frozenset({"VALIDATION", "UNDECLARED_INPUT", "FOREIGN_WRITE",
                           "TOO_LARGE", "DEGRADED", "NO_RUNNER"})

MANUAL = "manual"
INPUT = "input_changed"
UPSTREAM = "upstream_committed"
SWEEP = "sweep"
PULLED = "pulled_by_dependent"

_PRIORITY = {MANUAL: jobs.PRIORITY_MANUAL, INPUT: jobs.PRIORITY_INPUT,
             UPSTREAM: jobs.PRIORITY_UPSTREAM, PULLED: jobs.PRIORITY_UPSTREAM,
             SWEEP: jobs.PRIORITY_SWEEP}


class NotRunnableHere(Exception):
    """A pinned dataset file is not on this worker's disk. Not a failure: the
    job is released for a worker that has it, without using an attempt."""


class GenerationError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class AccountSnapshot:
    account_id: str
    rows: dict = field(default_factory=dict)          # dataset_key -> [active rows]
    states: dict = field(default_factory=dict)        # node_id -> node_state doc
    account_record: str = ""
    account_config: str = ""

    def output_hash(self, node_id: str):
        current = (self.states.get(node_id) or {}).get("current") or {}
        return current.get("output_hash")


def load_snapshot(db, account_id: str) -> AccountSnapshot:
    rows: dict = {}
    for row in db["account_data_files"].find(
            {"account_id": account_id, "status": "active"},
            {"dataset_key": 1, "category": 1, "content_sha256": 1, "file_path": 1,
             "original_filename": 1, "stored_filename": 1, "uploaded_at": 1}):
        key = str(row.get("dataset_key") or row.get("category") or "").strip().lower()
        if key:
            rows.setdefault(key, []).append(row)
    for group in rows.values():
        group.sort(key=lambda r: str(r.get("content_sha256") or r.get("_id")))

    account = None
    if ObjectId.is_valid(str(account_id)):
        account = db["accounts"].find_one({"_id": ObjectId(str(account_id))},
                                          {"name": 1, "domain": 1})
    return AccountSnapshot(
        account_id=account_id,
        rows=rows,
        states=state.load_account(db, account_id),
        account_record=manifest.account_record_hash(account),
        account_config=manifest.account_config_hash(
            db["account_instructions"].find_one({"account_id": account_id}),
            db["account_guardrails"].find_one({"account_id": account_id})),
    )


def _default_file_exists(row: dict) -> bool:
    from app.services.extractors.datasets import find_file_path
    return bool(find_file_path(row.get("file_path") or ""))


class _Heartbeat:
    """Keeps a running job's lease alive while its producer works."""

    def __init__(self, db, job, interval):
        self.db, self.job, self.interval = db, job, interval
        self.lost = False
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True,
                                        name="regen-heartbeat")

    def _run(self):
        while not self._stop.wait(self.interval):
            try:
                if not jobs.heartbeat(self.db, self.job):
                    self.lost = True
                    return
            except Exception:
                logger.exception("regen: heartbeat failed for %s", self.job.get("_id"))

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=5)
        return False


class Engine:
    def __init__(self, db=None, graph=DEFAULT, *, versions=None, runners=None,  # noqa: PLR0913 - each one a seam the tests replace
                 worker_id: str = jobs.WORKER_ID, strict_reads: bool | None = None,
                 file_exists=None, heartbeat_seconds: float = HEARTBEAT_SECONDS,
                 mirror: bool = True):
        if db is None:
            from app.database.mongodb import get_db
            db = get_db()
        self.db = db
        self.graph = graph
        self.versions = versions or manifest.Versions(db)
        self.runners = dict(runners or {})
        self.worker_id = worker_id
        if strict_reads is None:
            import os
            strict_reads = os.getenv("REGEN_STRICT_READS", "") == "1"
        self.strict_reads = strict_reads
        self.file_exists = file_exists or _default_file_exists
        self.heartbeat_seconds = heartbeat_seconds
        self.mirror_enabled = mirror

    # ------------------------------------------------------------------ setup

    def ensure_indexes(self) -> None:
        jobs.ensure_indexes(self.db)
        state.ensure_indexes(self.db)
        if not self.mirror_enabled:
            return
        # The mirror's guarded upsert relies on a unique (account, widget) index:
        # without it a guard miss would INSERT a duplicate row instead of failing.
        dups = list(self.db["account_widgets"].aggregate([
            {"$group": {"_id": {"a": "$account_id", "w": "$widget_key"},
                        "n": {"$sum": 1}}},
            {"$match": {"n": {"$gt": 1}}}, {"$limit": 5}]))
        if dups:
            self.mirror_enabled = False
            logger.error("regen: account_widgets has duplicate (account, widget) rows "
                         "(%s ...) - compatibility mirror disabled until they are "
                         "removed", dups[:2])
            return
        self.db["account_widgets"].create_index(
            [("account_id", 1), ("widget_key", 1)], name="uniq_widget", unique=True)

    # --------------------------------------------------------------- manifests

    def expected_all(self, snapshot: AccountSnapshot) -> tuple:
        manifests, fps = {}, {}
        for nid in self.graph.order:
            m = manifest.expected(self.graph[nid], snapshot, self.versions)
            manifests[nid] = m
            fps[nid] = manifest.fingerprint(m)
        return manifests, fps

    def status(self, account_id: str) -> dict:
        snapshot = load_snapshot(self.db, account_id)
        manifests, fps = self.expected_all(snapshot)
        derived = state.derive(self.graph, snapshot.states, fps,
                               jobs.live(self.db, account_id))
        for nid, entry in derived.items():
            current = (snapshot.states.get(nid) or {}).get("current") or {}
            entry["changed_inputs"] = (
                manifest.diff(current.get("manifest"), manifests[nid])
                if entry["lifecycle"] == state.STALE and current.get("manifest") else [])
            entry["feature"] = self.graph[nid].feature
            entry["kind"] = self.graph[nid].kind
            # False before the migration has adopted this account: its widgets
            # are still served from account_widgets and have no engine state.
            entry["tracked"] = nid in snapshot.states
        features = {fid: {"lifecycle": state.feature_lifecycle(self.graph, derived, fid),
                          "nodes": nids}
                    for fid, nids in self.graph.features().items()}
        return {"account_id": account_id, "nodes": derived, "features": features}

    # --------------------------------------------------------------- reconcile

    def reconcile(self, account_id: str, why: dict, *, sweep_legacy: bool = False,
                  only=None, scope=None) -> list:
        """Enqueue every node whose committed output no longer matches its inputs.

        `why` is a `jobs.trigger(...)`. Its type sets the priority and decides
        which classes of node are enqueued (design section 6.4). `scope` limits
        where a demand may start generating something that has never been built
        (or re-verify legacy output): the readers of the dataset that changed,
        or the direct dependents of the node that committed - never the whole
        account. Nodes whose inputs actually changed are exact by fingerprint and
        are queued wherever they are. Returns the plan
        - one entry per node acted on - for logging and tests.
        """
        snapshot = load_snapshot(self.db, account_id)
        manifests, fps = self.expected_all(snapshot)
        live = jobs.live(self.db, account_id)
        kind = why.get("type")
        demand = bool(why.get("demand"))
        priority = _PRIORITY.get(kind, jobs.PRIORITY_UPSTREAM)
        now = datetime.now(UTC)
        plan = []

        for nid in self.graph.order:
            if only is not None and nid not in only:
                continue
            doc = snapshot.states.get(nid) or {}
            current = doc.get("current") or None
            failure = doc.get("last_failure") or None
            fp = fps[nid]
            job = live.get(nid)

            if job and (job.get("status") == jobs.PENDING or
                        (job.get("status") == jobs.RUNNING and
                         (doc.get("running") or {}).get("target_fingerprint") == fp)):
                continue                          # already queued for these inputs

            cls, enqueue, prio = None, False, priority
            if failure and failure.get("fingerprint") == fp and not (
                    current and current.get("fingerprint") == fp
                    and current.get("quality") == state.COMPLETE):
                cls = "failed"
                enqueue = kind == MANUAL or _due(failure.get("at"), failure.get("count"), now)
            elif current and current.get("fingerprint") == fp:
                if current.get("quality") == state.DEGRADED:
                    cls = "degraded"
                    enqueue = kind == MANUAL or _due(current.get("generated_at"),
                                                     current.get("degraded_retries", 0) + 1,
                                                     now)
                else:
                    cls = "fresh"
            elif current and not current.get("fingerprint"):
                cls = "legacy"
                in_scope = scope is None or nid in scope
                enqueue = ((demand or kind in (MANUAL, INPUT)) and in_scope) or sweep_legacy
                if sweep_legacy and not (demand or kind in (MANUAL, INPUT)):
                    prio = jobs.PRIORITY_LEGACY
            elif current:
                cls = "dirty"
                enqueue = True
            else:
                cls = "never"
                enqueue = (demand or kind == MANUAL) and (scope is None or nid in scope)

            if not enqueue:
                continue
            result = jobs.enqueue(self.db, account_id, nid,
                                  {**why, "detail": why.get("detail") or cls},
                                  priority=prio, force=bool(why.get("force")),
                                  rank=self.graph.rank(nid))
            plan.append({"node_id": nid, "class": cls, "job": result,
                         "changed_inputs": manifest.diff((current or {}).get("manifest"),
                                                         manifests[nid])})
        if plan:
            pipeline.step("regen", "%s -> queued %s" % (
                kind, ", ".join("%s(%s)" % (p["node_id"], p["class"]) for p in plan)),
                account=account_id)
        return plan

    def notify_input_changed(self, account_id: str, what: str, actor: str = "",
                             datasets=None, nodes=None) -> list:
        """The one call an upload, delete or config edit makes.

        `datasets` / `nodes` name what changed, so nothing unrelated is built
        for the first time on its account: a firmographics upload must not start
        generating features that never read firmographics.
        """
        scope = None
        if datasets is not None or nodes is not None:
            scope = set(nodes or [])
            for key in datasets or []:
                scope.update(self.graph.readers_of_dataset(key))
        return self.reconcile(account_id, jobs.trigger(INPUT, what, actor, demand=True),
                              scope=scope)

    def regenerate_feature(self, account_id: str, feature_id: str, actor: str = "",
                           force: bool = True) -> dict:
        """Manual regeneration of one feature: its nodes, forced."""
        nids = self.graph.nodes_for_feature(feature_id)
        if not nids:
            raise KeyError(feature_id)
        return {**self.regenerate_nodes(account_id, nids, actor, force,
                                        detail="regenerate %s" % feature_id),
                "feature_id": feature_id}

    def regenerate_nodes(self, account_id: str, nids, actor: str = "",
                         force: bool = True, detail: str = "", full: bool = False,
                         demand: bool = True) -> dict:
        """Queue these nodes at manual priority.

        Ancestors that are stale are pulled in by the gate when these run.
        Ancestors that FAILED would otherwise sit out their retry backoff and
        leave this request waiting behind them, so they are forced too.
        `demand=False` queues only nodes that already have output - a page view
        must not start generating a feature nobody has loaded data for.
        """
        nids = [n for n in self.graph.order if n in set(nids)]
        why = jobs.trigger(MANUAL, detail or "regenerate %s" % ", ".join(nids), actor,
                           demand=demand)
        snapshot = load_snapshot(self.db, account_id)
        _manifests, fps = self.expected_all(snapshot)
        derived = state.derive(self.graph, snapshot.states, fps,
                               jobs.live(self.db, account_id))
        failed_ancestors = sorted(
            {a for nid in nids for a in self.graph.ancestors(nid)
             if derived[a]["lifecycle"] == state.FAILED} - set(nids),
            key=self.graph.rank)
        queued = {}
        for nid in failed_ancestors + nids:
            queued[nid] = jobs.enqueue(self.db, account_id, nid, why,
                                       priority=jobs.PRIORITY_MANUAL, force=force,
                                       full=full and self.graph[nid].kind == INDEX,
                                       rank=self.graph.rank(nid))
        return {"account_id": account_id,
                "nodes": [{"node_id": nid, "lifecycle": derived[nid]["lifecycle"],
                           "job": {"id": str(queued[nid]["job_id"]),
                                   "status": queued[nid]["status"],
                                   "coalesced": queued[nid]["coalesced"]}}
                          for nid in nids],
                "forced_ancestors": failed_ancestors}

    # ------------------------------------------------------------------ worker

    def run_once(self) -> dict | None:
        """Reclaim lapsed leases, then claim and run one job. None when idle."""
        for job, action in jobs.reclaim_expired(self.db):
            if action == "failed":
                state.record_failure(self.db, job["account_id"], job["node_id"],
                                     job["_id"], job.get("target_fingerprint") or "",
                                     "LEASE_EXPIRED",
                                     "the worker stopped responding and attempts "
                                     "are exhausted")
            else:
                state.clear_running(self.db, job["account_id"], job["node_id"],
                                    job["_id"])
        job = jobs.claim(self.db, self.worker_id)
        if not job:
            return None
        return self.run_job(job)

    def run_job(self, job: dict) -> dict:
        account_id, nid = job["account_id"], job["node_id"]
        node = self.graph[nid]
        started = time.monotonic()
        snapshot = load_snapshot(self.db, account_id)
        manifests, fps = self.expected_all(snapshot)
        live = jobs.live(self.db, account_id)
        derived = state.derive(self.graph, snapshot.states, fps, live)

        # Gate: build only on upstream output that is itself current.
        bad = [up for up in node.upstream if derived[up]["lifecycle"] != state.CURRENT]
        # An ancestor that cannot become current without an input changing -
        # blocked, or failed and not being forced - would only be pulled, fail
        # or block again, and gate this job again, every minute. Finish the job
        # instead; the node stays STALE with `blocked_by`, and the reconcile
        # after that ancestor next commits re-queues it.
        stuck = [up for up in bad if up not in live and (
            derived[up].get("blocked")
            or (derived[up]["lifecycle"] == state.FAILED and not job.get("force")))]
        if stuck:
            jobs.finish(self.db, job, jobs.SKIPPED,
                        result={"outcome": "blocked_by", "blocked_by": stuck})
            logger.info("regen.blocked %s/%s by %s", account_id, nid, stuck)
            return {"outcome": "blocked", "node_id": nid, "blocked_by": stuck}
        if bad:
            self._pull(account_id, bad, derived, live, job)
            jobs.release(self.db, job, delay_seconds=jobs.GATE_RETRY_SECONDS,
                         reason="waiting on %s" % ", ".join(bad))
            logger.info("regen.gated %s/%s waiting on %s", account_id, nid, bad)
            return {"outcome": "gated", "node_id": nid, "waiting_on": bad}

        target = fps[nid]
        m = manifests[nid]
        current = (snapshot.states.get(nid) or {}).get("current") or None

        # Downgrade guard: older code sharing the database never overwrites
        # output produced by newer logic.
        if current and int(current.get("logic_total") or 0) > m["logic"]["total"]:
            jobs.finish(self.db, job, jobs.SKIPPED,
                        result={"outcome": "newer_logic_committed"})
            return {"outcome": "skipped", "node_id": nid, "reason": "newer logic"}

        if (not job.get("force") and not job.get("full") and current
                and current.get("fingerprint") == target
                and current.get("quality") == state.COMPLETE):
            jobs.finish(self.db, job, jobs.SKIPPED, result={"outcome": "unchanged"})
            logger.info("regen.skipped %s/%s fingerprint unchanged", account_id, nid)
            return {"outcome": "skipped", "node_id": nid, "reason": "unchanged"}

        pinned_rows = {k: list(snapshot.rows.get(k) or []) for k in node.datasets}
        missing = [r.get("file_path") for rows in pinned_rows.values() for r in rows
                   if not self.file_exists(r)]
        if missing:
            jobs.release(self.db, job, not_runnable_here=True,
                         reason="%d pinned file(s) not on this machine" % len(missing))
            logger.warning("regen.not_runnable_here %s/%s - %s", account_id, nid,
                           missing[:3])
            return {"outcome": "not_runnable_here", "node_id": nid}

        previous = (current or {}).get("fingerprint")
        changed = manifest.diff((current or {}).get("manifest"), m)
        if not jobs.start_attempt(self.db, job, target, previous, changed):
            return {"outcome": "fenced", "node_id": nid}
        state.mark_running(self.db, account_id, nid, job, target)
        logger.info("regen.claimed %s/%s attempt %d changed=%s", account_id, nid,
                    int(job.get("attempts") or 0) + 1, changed[:5])

        ctx = run_context.RunContext(
            account_id=account_id, node_id=nid, pinned_rows=pinned_rows,
            pinned_widgets=self._pin_widgets(account_id, node, snapshot),
            owned=frozenset(node.widgets), force=bool(job.get("force")), manifest=m)

        try:
            with _Heartbeat(self.db, job, self.heartbeat_seconds), \
                    run_context.active(ctx):
                result = self._runner(node)(account_id, **(
                    {"full": bool(job.get("full"))} if node.kind == INDEX else {}))
            generation = self._validate(node, ctx, result, current, target, m, job)
        except (NotRunnableHere, DatasetFileMissing) as exc:
            jobs.release(self.db, job, not_runnable_here=True, reason=str(exc))
            state.clear_running(self.db, account_id, nid, job["_id"])
            return {"outcome": "not_runnable_here", "node_id": nid}
        except Exception as exc:
            return self._fail(job, target, exc, started)

        committed = state.commit(self.db, account_id, nid, job["fence"], generation)
        if committed is None:
            jobs.finish(self.db, job, jobs.FENCED,
                        result={"outcome": "fenced", "fingerprint": target})
            logger.warning("regen.fenced %s/%s - lease was reclaimed; result discarded",
                           account_id, nid)
            return {"outcome": "fenced", "node_id": nid}

        duration = int((time.monotonic() - started) * 1000)
        jobs.finish(self.db, job, jobs.SUCCEEDED, result={
            "outcome": "committed", "generation_id": generation["generation_id"],
            "fingerprint": target, "quality": generation["quality"],
            "duration_ms": duration, "llm_calls": ctx.llm_calls,
            "llm_failures": ctx.llm_failures, "changed_inputs": changed[:20]})
        logger.info("regen.committed %s/%s quality=%s %dms fp=%s", account_id, nid,
                    generation["quality"], duration, target[:12])
        pipeline.step("regen", "%s committed (%s, %.1fs)" % (
            nid, generation["quality"], duration / 1000), account=account_id)

        if current:
            state.write_history(self.db, account_id, nid, current,
                                int(committed.get("rev") or 0) - 1)
        if self.mirror_enabled and node.widgets:
            self._mirror(account_id, generation, int(committed.get("rev") or 0))

        self._nudge_dependents(account_id, nid)
        self.reconcile(account_id, jobs.trigger(UPSTREAM, nid,
                                                demand=bool(job.get("demand"))),
                       scope=set(self.graph.downstream.get(nid) or []))
        return {"outcome": "committed", "node_id": nid,
                "generation_id": generation["generation_id"],
                "quality": generation["quality"]}

    # ---------------------------------------------------------------- helpers

    def _runner(self, node):
        fn = self.runners.get(node.id)
        if fn is not None:
            return fn
        if not node.run:
            raise GenerationError("NO_RUNNER", "node %s has no runner" % node.id)
        module_path, _, name = node.run.partition(":")
        try:
            return getattr(importlib.import_module(module_path), name)
        except (ImportError, AttributeError) as exc:
            raise GenerationError("NO_RUNNER", "runner %s not found: %s"
                                  % (node.run, exc)) from exc

    def _pin_widgets(self, account_id: str, node, snapshot) -> dict:
        """The committed widgets this run may read: its upstream nodes' and its
        own (a producer's LLM cache reads its own previous output)."""
        pinned = {}
        for nid in (*node.upstream, node.id):
            current = (snapshot.states.get(nid) or {}).get("current") or {}
            for key in self.graph[nid].widgets:
                widget = (current.get("widgets") or {}).get(key)
                pinned[key] = (shape(account_id, key, widget, self.graph, current)
                               if widget is not None else None)
        return pinned

    def _pull(self, account_id, bad, derived, live, job):
        """Enqueue the ancestors a gated job is waiting on, if nobody has.

        Without this a job blocked by a stale ancestor that no trigger queued
        (a legacy output, say) would wait forever.
        """
        for up in bad:
            if up in live:
                continue
            lifecycle = derived[up]["lifecycle"]
            if derived[up].get("blocked"):
                continue
            if lifecycle in (state.STALE, state.NEVER_GENERATED):
                jobs.enqueue(self.db, account_id, up,
                             jobs.trigger(PULLED, job["node_id"],
                                          demand=bool(job.get("demand"))),
                             priority=int(job.get("priority") or jobs.PRIORITY_UPSTREAM),
                             rank=self.graph.rank(up))
            elif lifecycle == state.FAILED and job.get("force"):
                jobs.enqueue(self.db, account_id, up,
                             jobs.trigger(PULLED, job["node_id"], demand=True),
                             priority=int(job.get("priority") or jobs.PRIORITY_MANUAL),
                             force=True, rank=self.graph.rank(up))

    def _validate(self, node, ctx, result, current, target, m, job) -> dict:
        """Everything a run must satisfy before its output may be committed."""
        if ctx.foreign_puts:
            raise GenerationError("FOREIGN_WRITE", "%s wrote widgets it does not own: %s"
                                  % (node.id, sorted(set(ctx.foreign_puts))))

        allowed_widgets = set(node.widgets) | self.graph.upstream_widgets(node.id)
        undeclared = sorted((ctx.widget_reads - allowed_widgets)
                            | {"dataset:%s" % d for d in
                               ctx.dataset_reads - set(node.datasets)})
        if undeclared:
            message = "%s read inputs it does not declare: %s" % (node.id, undeclared)
            if self.strict_reads:
                raise GenerationError("UNDECLARED_INPUT", message)
            logger.error("regen.undeclared_input %s/%s %s", ctx.account_id, node.id,
                         undeclared)

        extra = None
        if node.kind == INDEX:
            result = dict(result or {})
            quality = result.get("quality") or state.COMPLETE
            if quality not in (state.COMPLETE, state.DEGRADED, state.BLOCKED):
                raise GenerationError("VALIDATION", "index %s returned quality %r"
                                      % (node.id, quality))
            extra = {"corpus": result.get("corpus") or {},
                     "index_version": result.get("index_version")}
            widgets = {}
        else:
            missing = sorted(set(node.widgets) - set(ctx.staged))
            if missing:
                raise GenerationError("VALIDATION", "%s did not publish %s"
                                      % (node.id, missing))
            widgets = {k: ctx.staged[k] for k in node.widgets}
            for key, widget in widgets.items():
                if widget.get("status") not in CONTENT_STATUSES:
                    raise GenerationError("VALIDATION", "%s.%s has status %r"
                                          % (node.id, key, widget.get("status")))
            size = len(bson.encode({"w": widgets}))
            if size > MAX_GENERATION_BYTES:
                raise GenerationError("TOO_LARGE", "%s output is %d bytes" % (node.id, size))
            quality = state.DEGRADED if ctx.llm_failures else state.COMPLETE
            if isinstance(result, dict) and result.get("quality") in (
                    state.COMPLETE, state.DEGRADED):
                quality = result["quality"]

            # A fallback after a model failure must not replace a good result.
            # Only when nothing better exists is it worth publishing.
            if (quality == state.DEGRADED and current
                    and current.get("quality") != state.DEGRADED):
                raise GenerationError(
                    "DEGRADED", "%d of %d model call(s) failed; the previous output "
                    "is kept" % (ctx.llm_failures, ctx.llm_calls))

        retries = 0
        if quality == state.DEGRADED and current and current.get("fingerprint") == target:
            retries = int(current.get("degraded_retries") or 0) + 1

        return {
            "generation_id": ObjectId(),
            "fingerprint": target,
            "manifest": m,
            "logic_total": m["logic"]["total"],
            "output_hash": manifest.output_hash(widgets, extra),
            "quality": quality,
            "degraded_retries": retries,
            "widgets": widgets,
            "index": extra,
            "soft_reads": dict(ctx.soft_reads),
            # Which file rows the run read - audit only, outside the fingerprint.
            "dataset_rows": {k: [str(r.get("_id")) for r in rows]
                             for k, rows in ctx.pinned_rows.items()},
            "llm": {"calls": ctx.llm_calls, "failures": ctx.llm_failures,
                    "model": (m.get("model") or {}).get("chat")},
            "job_id": job["_id"],
            "generated_at": datetime.now(UTC),
        }

    def _fail(self, job, target, exc, started) -> dict:
        account_id, nid = job["account_id"], job["node_id"]
        code = getattr(exc, "code", None) or "ERROR"
        message = "%s: %s" % (type(exc).__name__, exc) if code == "ERROR" else str(exc)
        attempts = int(job.get("attempts") or 0) + 1
        error = {"code": code, "message": message[:500]}

        if code not in DETERMINISTIC and attempts < jobs.MAX_ATTEMPTS:
            delay = 60 * (4 ** attempts)
            jobs.release(self.db, job, delay_seconds=delay, reason="retry", error=error)
            state.clear_running(self.db, account_id, nid, job["_id"])
            logger.warning("regen.retry %s/%s attempt %d in %ds - %s", account_id, nid,
                           attempts, delay, message[:200])
            return {"outcome": "retry", "node_id": nid, "error": error}

        jobs.finish(self.db, job, jobs.FAILED, error=error, result={
            "outcome": "failed", "fingerprint": target,
            "duration_ms": int((time.monotonic() - started) * 1000)})
        state.record_failure(self.db, account_id, nid, job["_id"], target, code, message)
        logger.warning("regen.failed %s/%s %s - %s (previous output kept)", account_id,
                       nid, code, message[:200])
        pipeline.step("regen", "%s FAILED %s - previous output kept" % (nid, code),
                      account=account_id)
        return {"outcome": "failed", "node_id": nid, "error": error}

    def _nudge_dependents(self, account_id: str, nid: str) -> None:
        """A dependent that was gated on this node can run now, not after its
        gate-retry delay."""
        downstream = self.graph.downstream.get(nid) or []
        if downstream:
            self.db[jobs.COLLECTION].update_many(
                {"account_id": account_id, "node_id": {"$in": downstream},
                 "status": jobs.PENDING, "released_reason": {"$regex": "^waiting on"}},
                {"$set": {"not_before": datetime.now(UTC)}})

    def _mirror(self, account_id: str, generation: dict, rev: int) -> None:
        """Copy committed widgets to `account_widgets` for a rollback to the
        pre-engine release. Never read by the new code; a newer copy wins."""
        for key, widget in (generation.get("widgets") or {}).items():
            body = shape(account_id, key, widget, self.graph, generation)
            body.pop("generation_quality", None)
            body["rev"] = rev
            try:
                self.db["account_widgets"].update_one(
                    {"account_id": account_id, "widget_key": key,
                     "$or": [{"rev": {"$lt": rev}}, {"rev": {"$exists": False}}]},
                    {"$set": body}, upsert=True)
            except DuplicateKeyError:
                pass                  # a newer generation's copy is already there
            except Exception:
                logger.exception("regen: mirror of %s/%s failed", account_id, key)

    # ------------------------------------------------------------------- sweep

    def sweep(self, legacy_accounts: int = LEGACY_ACCOUNTS_PER_SWEEP) -> dict:
        """The safety net: reconcile every account.

        Catches every change nothing announced - a deploy with a new prompt
        version, an edited scoring config, a reloaded rulebook - and every crash
        window between a commit and the reconcile after it. A few accounts per
        pass also get their legacy (pre-engine) outputs queued, at the lowest
        priority, so they are verified progressively rather than all at once.
        """
        summary = {"accounts": 0, "queued": 0, "legacy_accounts": []}
        legacy_budget = legacy_accounts
        for account in self.db["accounts"].find({}, {"_id": 1}):
            account_id = str(account["_id"])
            summary["accounts"] += 1
            try:
                plan = self.reconcile(account_id, jobs.trigger(SWEEP, "periodic"))
                summary["queued"] += len(plan)
                if legacy_budget > 0 and self._has_legacy(account_id) \
                        and not jobs.live(self.db, account_id):
                    plan = self.reconcile(account_id, jobs.trigger(SWEEP, "legacy"),
                                          sweep_legacy=True)
                    if plan:
                        legacy_budget -= 1
                        summary["legacy_accounts"].append(account_id)
                        summary["queued"] += len(plan)
            except Exception:
                logger.exception("regen: sweep failed for account %s", account_id)
        return summary

    def _has_legacy(self, account_id: str) -> bool:
        return self.db[state.COLLECTION].count_documents(
            {"account_id": account_id, "current.fingerprint": None,
             "current": {"$ne": None}}) > 0


def _due(since, count, now) -> bool:
    """Whether an automatic retry is due under RETRY_SCHEDULE."""
    count = int(count or 1)
    if count > len(RETRY_SCHEDULE):
        return False
    if since is None:
        return True
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)
    return now - since >= timedelta(seconds=RETRY_SCHEDULE[count - 1])


_default_engine = None
_default_lock = threading.Lock()


def get_engine() -> Engine:
    global _default_engine
    with _default_lock:
        if _default_engine is None:
            _default_engine = Engine()
        return _default_engine


__all__ = [
    "WIDGET_FIELDS",
    "AccountSnapshot",
    "Engine",
    "GenerationError",
    "NotRunnableHere",
    "get_engine",
    "load_snapshot",
]
