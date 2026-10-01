"""Plan, run and commit: the whole regeneration path in one place.

**Nothing expensive happens on its own** (29 Sep). An upload, a delete, a config
edit, a deploy, a restart, a rule, prompt or model change and a committed
upstream node can all make nodes stale - staleness is derived from fingerprints
on every read, so nothing needs to be written for it - but none of them queues
work. Work exists only when someone asks for it: `runs.create` (behind
`POST /regeneration` and the admin page's Submit) plans the request with
`planner.plan` and enqueues exactly the nodes it names, each tagged with the
run's id; the worker claims nothing else. Before this, every one of those
triggers enqueued, and the account-wide sweep ran every stale node of every
account every ten minutes - one account uploaded file by file ran its sections
41 times (28 Sep).

A job that does not succeed never goes back to the queue (29 Sep). It ends
FAILED with its reason - its own error, the model quota running out, its files
missing on this server, the worker stopping under it, or a restart/deploy
interrupting it - and stays that way, previous output kept, until someone
submits it again. An exhausted quota also pauses the whole queue, so the
sections still waiting do not each fail on it; an admin resumes it.

The worker runs one job at a time per account:

    claim -> gate -> pin -> skip? -> files here? -> run -> validate -> commit
          -> finish -> mirror -> nudge dependents already queued

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
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import bson
from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.observability import pipeline
from app.services.extractors.datasets import DatasetFileMissing
from app.services.regen import context as run_context, data_gaps, jobs, manifest, planner, runs, state
from app.services.regen.graph import DEFAULT, INDEX
from app.services.regen.store import WIDGET_FIELDS, shape

logger = logging.getLogger(__name__)

CONTENT_STATUSES = frozenset({"available", "partial", "empty", "pending", "error",
                              "unavailable", "unverified"})
MAX_GENERATION_BYTES = 12 * 1024 * 1024
# Well inside jobs.LEASE_SECONDS, so a missed beat or two does not lapse a live job.
HEARTBEAT_SECONDS = 30
# How often a producer's progress is written to its job row, at most.
PROGRESS_EVERY_SECONDS = 2.0
# How long the queue stays paused after the provider refuses for quota. The
# pause itself is right - without it the sections queued behind the refusal
# each burn their attempts on the same exhausted quota and all end FAILED - but
# it used to need an admin to lift it, so a 429 at 2am stopped every account
# until somebody opened the Pipeline tab. A quota window closes on its own;
# this is how long we assume that takes. 0 restores the old behaviour: paused
# until a human resumes.
QUOTA_PAUSE_SECONDS = max(0, int(os.getenv("REGEN_QUOTA_PAUSE_SECONDS", "900")))

MANUAL = "manual"
QUOTA = "QUOTA_EXHAUSTED"
FILES_MISSING = "FILES_MISSING"


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
        runs.ensure_indexes(self.db)
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

    # ------------------------------------------------------- stale, not queued

    def stale_nodes(self, account_id: str, scope=None) -> list:
        """The nodes of one account that are not current, with why.

        What an upload, a delete or a config edit reports back - and all it
        does. `scope` narrows the answer to the nodes a change can reach.
        """
        view = planner.account_view(self, account_id)
        out = []
        for nid, n in view["nodes"].items():
            if scope is not None and nid not in scope:
                continue
            if n["status"] in (planner.CURRENT,):
                continue
            out.append({"node_id": nid, "label": n["label"], "feature": n["feature"],
                        "status": n["status"], "categories": n["categories"],
                        "reasons": n["reasons"]})
        return out

    def notify_input_changed(self, account_id: str, what: str, actor: str = "",
                             datasets=None, nodes=None) -> list:
        """The one call an upload, delete or config edit makes. Queues NOTHING.

        Returns the nodes the change left stale (readers of the dataset, the
        named nodes, and everything downstream of them), so the caller can say
        what a Submit would now run. Kept as a named call so every input change
        still passes through one place.
        """
        scope = None
        if datasets is not None or nodes is not None:
            direct = set(nodes or [])
            for key in datasets or []:
                direct.update(self.graph.readers_of_dataset(key))
            scope = set(direct)
            for nid in direct:
                scope |= self.graph.descendants(nid)
        stale = self.stale_nodes(account_id, scope=scope)
        logger.info("regen: %s on %s by %s - %d node(s) now need a run, none queued",
                    what, account_id, actor or "system", len(stale))
        return stale

    def regenerate_feature(self, account_id: str, feature_id: str, actor: str = "",
                           force: bool = False) -> dict:
        """One feature of one account, as an explicit run. Not forced unless asked."""
        nids = self.graph.nodes_for_feature(feature_id)
        if not nids:
            raise KeyError(feature_id)
        return {**self.regenerate_nodes(account_id, nids, actor, force,
                                        detail="regenerate %s" % feature_id),
                "feature_id": feature_id}

    def regenerate_nodes(self, account_id: str, nids, actor: str = "",
                         force: bool = False, detail: str = "", full: bool = False,
                         demand: bool = True) -> dict:
        """These nodes of one account, as an explicit run (see `runs.create`).

        Kept for the per-feature endpoints; everything goes through the planner,
        so stale ancestors are included, current nodes are skipped unless
        forced, and a node already queued is not queued twice. `demand` is
        accepted for compatibility and no longer means anything: nothing is
        ever generated without being asked for.
        """
        run = runs.create(self, accounts=[account_id], nodes=list(nids), force=force,
                          full=full, actor=actor, reason=detail)
        items = run["plan"]["accounts"][0]["items"] if run["plan"]["accounts"] else []
        live = jobs.live(self.db, account_id)
        by_node = {i["node_id"]: i for i in items}
        out = []
        for nid in [n for n in self.graph.order if n in set(nids)]:
            job = live.get(nid)
            item = by_node.get(nid) or {}
            out.append({"node_id": nid, "lifecycle": item.get("status"),
                        "action": item.get("action"),
                        "job": ({"id": str(job["_id"]), "status": job["status"],
                                 "coalesced": item.get("action") == planner.IN_PROGRESS}
                                if job else None)})
        return {"account_id": account_id, "run_id": str(run["_id"]), "nodes": out,
                "totals": run["totals"]}

    # ------------------------------------------------------------------ worker

    def run_once(self) -> dict | None:
        """Reclaim lapsed leases, then claim and run one job. None when idle
        or when the queue is paused."""
        for job, _action in jobs.reclaim_expired(self.db):
            state.clear_running(self.db, job["account_id"], job["node_id"], job["_id"])
            self.record_job_failure(job, jobs.WORKER_STOPPED, jobs.WORKER_STOPPED_MESSAGE)
        # A quota pause lifts itself once its window has passed; an admin's
        # does not. Checked before the claim so the first poll after the
        # window ends picks work up rather than waiting for a human.
        jobs.lift_expired_pause(self.db)
        if jobs.queue_state(self.db)["paused"]:
            return None
        job = jobs.claim(self.db, self.worker_id)
        if not job:
            return None
        try:
            return self.run_job(job)
        except Exception as exc:
            return self._engine_error(job, exc)

    def _engine_error(self, job: dict, exc: Exception) -> dict:
        """An exception from the engine itself, not from a producer (those go
        through _fail). It is a bug, so another attempt would hit it again:
        fail the job now. Left RUNNING it lapsed, was reclaimed with no attempt
        counted (it never reached start_attempt) and crashed again, forever -
        the 'messaging_context' loop of 28 Sep."""
        account_id, nid = job["account_id"], job["node_id"]
        logger.error("regen.engine_error %s/%s", account_id, nid, exc_info=exc)
        error = {"code": "ENGINE_ERROR",
                 "message": ("%s: %s" % (type(exc).__name__, exc))[:500]}
        jobs.finish(self.db, job, jobs.FAILED, error=error,
                    result={"outcome": "engine_error"})
        state.clear_running(self.db, account_id, nid, job["_id"])
        self.record_job_failure(job, "ENGINE_ERROR", error["message"])
        return {"outcome": "failed", "node_id": nid, "error": error}

    def record_job_failure(self, job: dict, code: str, message: str) -> None:
        """Mark the node FAILED for the inputs this job was building, so the
        admin page shows it under Failed with this reason. For a job that
        stopped before it recorded its target, the target is worked out now."""
        account_id, nid = job["account_id"], job["node_id"]
        target = job.get("target_fingerprint")
        if not target and nid in self.graph:
            try:
                target = self.expected_all(load_snapshot(self.db, account_id))[1][nid]
            except Exception:
                target = None
        if target:
            state.record_failure(self.db, account_id, nid, job["_id"], target,
                                 code, message)

    def run_job(self, job: dict) -> dict:  # noqa: PLR0911 - one return per outcome
        account_id, nid = job["account_id"], job["node_id"]
        if nid not in self.graph:
            # Queued before a deploy removed the node (Content Messaging, 28
            # Sep). Left RUNNING it crashed the loop on every claim until its
            # lease ran out, then came back.
            jobs.finish(self.db, job, jobs.CANCELLED,
                        result={"outcome": "node_removed"})
            logger.warning("regen.cancelled %s/%s - node no longer in the graph",
                           account_id, nid)
            return {"outcome": "cancelled", "node_id": nid}
        node = self.graph[nid]
        started = time.monotonic()
        snapshot = load_snapshot(self.db, account_id)
        manifests, fps = self.expected_all(snapshot)
        live = jobs.live(self.db, account_id)
        derived = state.derive(self.graph, snapshot.states, fps, live)

        # Gate: build only on upstream output that is itself current. An
        # ancestor the run queued is waited for; one nobody queued (it failed
        # earlier in this run, or the plan could not include it) will not
        # become current by waiting, so the job ends here and the node stays
        # stale with `blocked_by`. Nothing is pulled in: only a run adds work.
        bad = [up for up in node.upstream if derived[up]["lifecycle"] != state.CURRENT]
        stuck = [up for up in bad if up not in live]
        if stuck:
            jobs.finish(self.db, job, jobs.SKIPPED,
                        result={"outcome": "blocked_by", "blocked_by": stuck})
            logger.info("regen.blocked %s/%s by %s", account_id, nid, stuck)
            return {"outcome": "blocked", "node_id": nid, "blocked_by": stuck}
        if bad:
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
            logger.warning("regen.files_missing %s/%s - %s", account_id, nid, missing[:3])
            return self._fail(job, target, GenerationError(
                FILES_MISSING, "%d data file(s) are not on this server - upload them "
                "again, then submit: %s" % (len(missing), ", ".join(
                    str(p).rsplit("/", 1)[-1] for p in missing[:5]))), started)

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
        ctx.on_progress = self._progress_writer(job)
        wall_started = time.time()

        try:
            with _Heartbeat(self.db, job, self.heartbeat_seconds), \
                    run_context.active(ctx):
                result = self._runner(node)(account_id, **(
                    {"full": bool(job.get("full"))} if node.kind == INDEX else {}))
            if run_context.quota_exhausted_since(wall_started):
                return self._quota_pause(job, target, ctx, started)
            generation = self._validate(node, ctx, result, current, target, m, job)
        except (NotRunnableHere, DatasetFileMissing) as exc:
            return self._fail(job, target, GenerationError(
                FILES_MISSING, "a data file is not on this server - upload it again, "
                "then submit: %s" % exc), started, ctx)
        except Exception as exc:
            if run_context.quota_exhausted_since(wall_started):
                return self._quota_pause(job, target, ctx, started)
            return self._fail(job, target, exc, started, ctx)

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
            "duration_ms": duration, "changed_inputs": changed[:20],
            **_usage(ctx)})
        logger.info("regen.committed %s/%s quality=%s %dms fp=%s", account_id, nid,
                    generation["quality"], duration, target[:12])
        pipeline.step("regen", "%s committed (%s, %.1fs)" % (
            nid, generation["quality"], duration / 1000), account=account_id)

        if current:
            state.write_history(self.db, account_id, nid, current,
                                int(committed.get("rev") or 0) - 1)
        if self.mirror_enabled and node.widgets:
            self._mirror(account_id, generation, int(committed.get("rev") or 0))

        # Dependents a run already queued can go now. Dependents nobody asked
        # for are left stale - derived, shown on the admin page - not queued.
        self._nudge_dependents(account_id, nid)
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

    def _progress_writer(self, job):
        """A throttled writer of `job.progress`, for `run_context.progress`."""
        last = [0.0]

        def write(done, total, label):
            now = time.monotonic()
            if done < total and now - last[0] < PROGRESS_EVERY_SECONDS:
                return
            last[0] = now
            jobs.set_progress(self.db, job, done, total, label)
        return write

    def _quota_pause(self, job, target, ctx, started) -> dict:
        """The provider's quota ran out during this run. The job FAILS with that
        reason - nothing is committed, its output may be a fallback - and the
        queue pauses, so the sections still waiting do not each fail on the
        same quota. The pause lifts itself after QUOTA_PAUSE_SECONDS, so a
        refusal overnight costs that window rather than the night; an admin can
        resume sooner. This section stays FAILED either way and is submitted
        again by hand - an index build then continues from the documents it
        finished."""
        account_id, nid = job["account_id"], job["node_id"]
        jobs.pause(self.db, "model quota exhausted while %s/%s ran (%d model call(s), "
                   "%d token(s) before it stopped)" % (account_id, nid, ctx.api_calls,
                                                       ctx.tokens), by="engine",
                   seconds=QUOTA_PAUSE_SECONDS)
        logger.warning("regen.quota %s/%s - quota exhausted; failed, queue paused "
                       "until resumed", account_id, nid)
        return self._fail(job, target, GenerationError(
            QUOTA, "the model provider refused for quota after every wait - resume "
            "the queue when the quota is back and submit this section again"),
            started, ctx)

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
            # Why each placeholder field is empty - the client sees neutral
            # wording, the reason is kept here. Audit only, outside the hash.
            "data_gaps": data_gaps.collect_all(widgets),
            "index": extra,
            "soft_reads": dict(ctx.soft_reads),
            # Which file rows the run read - audit only, outside the fingerprint.
            "dataset_rows": {k: [str(r.get("_id")) for r in rows]
                             for k, rows in ctx.pinned_rows.items()},
            "llm": {"calls": ctx.llm_calls, "failures": ctx.llm_failures,
                    "model": (m.get("model") or {}).get("chat"), **_usage(ctx)},
            "job_id": job["_id"],
            "generated_at": datetime.now(UTC),
        }

    def _fail(self, job, target, exc, started, ctx=None) -> dict:
        """The run failed. It stays FAILED - no automatic retry of any kind -
        with its error on the job and the node, and the previous output kept.
        Whoever fixes the cause submits it again."""
        account_id, nid = job["account_id"], job["node_id"]
        code = getattr(exc, "code", None) or "ERROR"
        message = "%s: %s" % (type(exc).__name__, exc) if code == "ERROR" else str(exc)
        error = {"code": code, "message": message[:500]}
        jobs.finish(self.db, job, jobs.FAILED, error=error, result={
            "outcome": "failed", "fingerprint": target,
            "duration_ms": int((time.monotonic() - started) * 1000),
            **(_usage(ctx) if ctx is not None else {})})
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

    # ------------------------------------------------------------------ report

    def stale_report(self) -> dict:
        """How many nodes of every account are not current. Queues nothing.

        What startup and the periodic check log, so a deploy that changed a
        prompt says "37 accounts have stale outputs" instead of regenerating
        them.
        """
        summary = {"accounts": 0, "accounts_needing_run": 0, "by_status": {}}
        for account in self.db["accounts"].find({}, {"_id": 1}):
            account_id = str(account["_id"])
            summary["accounts"] += 1
            try:
                view = planner.account_view(self, account_id)
            except Exception:
                logger.exception("regen: stale report failed for account %s", account_id)
                continue
            statuses = [n["status"] for n in view["nodes"].values()]
            for st in statuses:
                summary["by_status"][st] = summary["by_status"].get(st, 0) + 1
            if any(st in planner.NEEDS_RUN for st in statuses):
                summary["accounts_needing_run"] += 1
        return summary

    def sweep(self, *_a, **_kw) -> dict:
        """Formerly: reconcile and enqueue every account. Now only the report."""
        return self.stale_report()


def _usage(ctx) -> dict:
    return {"llm_calls": ctx.llm_calls, "llm_failures": ctx.llm_failures,
            "api_calls": ctx.api_calls, "tokens": ctx.tokens,
            "embedding_calls": ctx.embedding_calls, "embedded_texts": ctx.embedded_texts}


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
