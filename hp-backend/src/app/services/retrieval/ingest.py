"""Building and updating an index, within a one-workspace budget.

There is one workspace per (account, index) and no second one to build a
replacement in, so a full rebuild replaces data in place. (Workspaces used to
cost three Atlas vector indexes each against a cluster cap of three, which is
why no replacement could ever be built beside the live one; vectors now live in
three shared, partitioned collections, so the cap is no longer what constrains
this - the stable workspace name is.) Two paths, with deliberately different
promises:

**Incremental** - what a data change actually triggers.

    fingerprint diff
        unchanged  -> skipped, costs nothing
        changed    -> adelete_by_doc_id(id) then ainsert(new, ids=[id])
        added      -> ainsert
        removed    -> adelete_by_doc_id

    Only affected documents are touched. A single changed CSV never rebuilds
    the index. A document that fails to re-index keeps its OLD fingerprint, so
    it is retried next run instead of being recorded as current, and is listed
    in `damaged_documents` meanwhile.

**Full rebuild** - admin action only.

    drop the workspace -> rebuild every document in place

    Not atomic, and there is no rollback. While it runs nothing is queryable;
    if it fails there is nothing to fall back to. Status is BUILDING throughout
    and FAILED if it does not finish. On this tier that is the honest trade, and
    nothing in this module pretends otherwise.

The stable `doc_id` is what makes the incremental path safe. Re-inserting
changed content without deleting first would leave both versions in the graph -
the documented behaviour is *"Modified content gets a new ID; old chunks remain
until explicit deletion"* - so delete always precedes insert.
"""

import asyncio
import logging
import time

from app.database.mongodb import get_db
from app.services.retrieval import client, corpus, evidence, index_state, registry

logger = logging.getLogger(__name__)


class BuildBlocked(Exception):
    """The index cannot be built yet - not a failure."""


async def _ingest_document(rag, doc, replace: bool):
    """Insert one document, deleting any previous copy of it first."""
    if replace:
        try:
            await rag.adelete_by_doc_id(doc.doc_id)
        except Exception:
            # A document LightRAG has no record of is not an error - the delete
            # is defensive, because insert-without-delete is what strands old
            # chunks in the graph.
            logger.debug("retrieval: nothing to delete for %s", doc.doc_id)
    await rag.ainsert(doc.text, ids=[doc.doc_id], file_paths=[doc.file_path])


async def update_index(account_id: str, index: str, full: bool = False,
                       progress=None) -> dict:
    """Bring one index up to date. `full=True` drops and rebuilds in place."""
    db = get_db()
    started = time.time()
    stats = {"mode": index_state.FULL if full else index_state.INCREMENTAL,
             "added": 0, "changed": 0, "removed": 0, "unchanged": 0,
             "damaged": [], "skipped": False, "duration_seconds": 0.0}

    # A retired index stays retired until someone explicitly rebuilds it. An
    # ordinary data change must not bring it back: rebuilding costs an LLM call
    # per chunk, and a retired index was retired on purpose.
    if index_state.is_retired(account_id, index) and not full:
        raise BuildBlocked(
            "this index was retired - rebuild it explicitly to bring it back")

    ok, reason = registry.preconditions(db, account_id, index)
    if not ok:
        index_state.set_status(account_id, index, index_state.BLOCKED, reason)
        raise BuildBlocked(reason)

    documents = registry.build_documents(account_id, index)
    if not documents:
        index_state.set_status(account_id, index, index_state.BLOCKED,
                               "the corpus is empty for this account")
        raise BuildBlocked("the corpus is empty for this account")

    fingerprints = corpus.fingerprints(documents)
    by_id = {d.doc_id: d for d in documents}
    delta = index_state.diff(account_id, index, fingerprints)
    # An interrupted build counts as an index to update, not as nothing. Its
    # finished documents are recorded and still in the workspace, so the work
    # left is the ordinary incremental delta - see `index_state.is_resumable`.
    resuming = index_state.is_resumable(account_id, index)
    have_index = index_state.has_index(account_id, index) or resuming
    if resuming:
        logger.info("retrieval: resuming an interrupted %s build for account %s "
                    "- %d document(s) already indexed",
                    index, account_id, len(delta["unchanged"]))

    if not full and have_index and not (delta["added"] or delta["changed"]
                                        or delta["removed"]):
        stats["skipped"] = True
        stats["unchanged"] = len(delta["unchanged"])
        logger.info("retrieval: %s/%s unchanged - nothing to do", account_id, index)
        return stats

    # A first build has nothing to update incrementally.
    full = full or not have_index
    stats["mode"] = index_state.FULL if full else index_state.INCREMENTAL

    index_state.begin_build(account_id, index, stats["mode"])

    if full:
        # Dropped BEFORE the rebuild, because there is no room for a second
        # workspace. This is the window where nothing is queryable.
        workspace = client.workspace_name(account_id, index)
        logger.warning("retrieval: dropping workspace %s for a full rebuild - "
                       "nothing is queryable until it completes", workspace)
        client.drop_workspace(workspace)
        evidence.purge(account_id, index)
        targets = list(documents)
        removals = []
    else:
        targets = [by_id[k] for k in (delta["added"] + delta["changed"])]
        removals = list(delta["removed"])

    rag = None
    applied = {"added": [], "changed": [], "removed": [], "failed": []}
    # Start from what is already recorded, so a document we do not touch keeps
    # its existing fingerprint and a failure does not mark it current.
    recorded = {} if full else dict(
        index_state.get(account_id, index).get("documents") or {})

    try:
        rag = await client.build_rag(account_id, index)

        for doc_id in removals:
            try:
                await rag.adelete_by_doc_id(doc_id)
                recorded.pop(doc_id, None)
                applied["removed"].append(doc_id)
            except Exception as exc:
                logger.warning("retrieval: could not remove %s - %s", doc_id, exc)
                applied["failed"].append(doc_id)

        for i, doc in enumerate(targets, 1):
            if progress:
                progress(i, len(targets), doc.unit_key)
            is_change = doc.doc_id in delta["changed"]
            try:
                await _ingest_document(rag, doc, replace=(is_change or full))
                evidence.replace_document_evidence(
                    account_id, index, doc.doc_id, doc.evidence_rows)
                recorded[doc.doc_id] = fingerprints[doc.doc_id]
                # Committed per document, not only at the end of the run. A
                # build that dies at document 10 of 19 - out of memory, a
                # deploy, Ctrl-C - then resumes from document 11 instead of
                # re-extracting everything. The status stays BUILDING until the
                # run completes, so a half-built index is still not queryable.
                index_state.record_document(account_id, index, doc.doc_id,
                                            fingerprints[doc.doc_id])
                applied["changed" if is_change else "added"].append(doc.doc_id)
            except BaseException as exc:
                # One bad document does not abandon the rest. Its fingerprint is
                # deliberately NOT recorded, so the next run retries it.
                logger.exception("retrieval: %s failed to index", doc.doc_id)
                applied["failed"].append(doc.doc_id)
                if full:
                    raise
                _ = exc

        if full:
            await _verify(rag, documents)
            index_state.finish_build(account_id, index, fingerprints, index_state.FULL)
        else:
            index_state.record_incremental(account_id, index, recorded, applied,
                                           damaged=applied["failed"])

    except BuildBlocked:
        raise
    except BaseException as exc:
        # BaseException, not Exception: LightRAG raises SystemExit when it
        # cannot create a Mongo vector index ("Program cannot continue"), and
        # SystemExit does not inherit from Exception - so an `except Exception`
        # here let a real failure through with the state still reading BUILDING.
        index_state.fail_build(account_id, index,
                               "%s: %s" % (type(exc).__name__, exc), stats["mode"])
        raise
    finally:
        if rag is not None:
            try:
                await rag.finalize_storages()
            except Exception:
                logger.exception("retrieval: finalize_storages failed")

    stats["added"] = len(applied["added"])
    stats["changed"] = len(applied["changed"])
    stats["removed"] = len(applied["removed"])
    stats["unchanged"] = len(delta["unchanged"])
    stats["damaged"] = applied["failed"]
    stats["duration_seconds"] = round(time.time() - started, 1)
    return stats


async def _verify(rag, documents):
    """Refuse to call a full rebuild successful when nothing landed.

    A silently-empty graph is the documented failure when the model or key is
    misconfigured - the reference rig warns `ainsert` "can complete
    'successfully' while producing a near-empty graph". A document can also fail
    on its own: LightRAG catches an extraction timeout internally, logs it,
    marks that document `failed` and carries on, so the insert call returns
    perfectly normally with one document missing from the graph.

    Status is read from `rag.doc_status.get_by_id`, which returns a dict with a
    real `status` and `error_msg`. An earlier version asked `aget_docs_by_ids`
    instead and checked `status.status` on what it returned - that attribute is
    always `None` in 1.5.7, so the failed-document branch could never run. It
    reported "verified 19 document(s) landed" on a build where one had timed
    out, and the index went READY with a hole in it. Presence was the only thing
    it ever actually checked.
    """
    doc_ids = [d.doc_id for d in documents]
    missing, failed = [], []

    for doc_id in doc_ids:
        try:
            record = await rag.doc_status.get_by_id(doc_id)
        except Exception:
            record = None
        if not record:
            missing.append(doc_id)
            continue
        status = record.get("status") if isinstance(record, dict) else None
        status = getattr(status, "value", status)
        if str(status or "").lower() == "failed":
            failed.append("%s (%s)" % (doc_id,
                                       str(record.get("error_msg") or "")[:120]))

    if missing or failed:
        raise RuntimeError(
            "rebuild did not land %d document(s) - %s"
            % (len(missing) + len(failed), "; ".join((missing + failed)[:3])))
    logger.info("retrieval: verified %d document(s) landed", len(doc_ids))


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

def run_job(job) -> dict:
    from app.services.retrieval import jobs

    account_id, index = job["account_id"], job["index"]
    full = bool(job.get("full"))
    try:
        stats = asyncio.run(update_index(account_id, index, full=full))
        # The index is only half the job: whatever it feeds has to follow it,
        # or the data moves and the feature built on top quietly goes stale.
        stats["generated"] = _run_generator(account_id, index, stats)
        jobs.complete(job["_id"])
        return stats
    except BuildBlocked as exc:
        jobs.complete(job["_id"])
        logger.info("retrieval: %s/%s blocked - %s", account_id, index, exc)
        return {"blocked": str(exc)}
    except BaseException as exc:
        jobs.fail(job["_id"], "%s: %s" % (type(exc).__name__, exc))
        raise


def _run_generator(account_id: str, index: str, stats: dict) -> dict:
    """Regenerate the feature this index feeds, after a build that changed it.

    Deliberately not part of `update_index`: the index is valid whether or not
    the feature on top of it regenerates, and conflating the two would let a
    prompt failure mark a perfectly good index as failed.

    Never raises. A generation failure is recorded and logged, the job still
    completes, and the previously published output stays exactly as it was -
    the generator raises before it writes, so there is nothing half-written to
    clean up.
    """
    if stats.get("skipped"):
        # Unchanged corpus, unchanged output. Regenerating would spend several
        # model calls to produce what is already stored.
        return {"ran": False, "reason": "corpus unchanged"}

    hook = registry.generates(index)
    if not hook:
        return {"ran": False, "reason": "this index feeds nothing"}

    generator = registry.load_generator(index)
    if not generator:
        logger.warning("retrieval: %s declares a generator that will not import",
                       index)
        return {"ran": False, "reason": "generator could not be loaded"}

    try:
        generator(account_id)
        index_state.clear_generation_error(account_id, index)
        logger.info("retrieval: regenerated %s for account %s after an index build",
                    hook.get("feature_key") or index, account_id)
        # The widget this index just republished feeds other indexes, and until
        # now nothing told them.
        #
        # `registry.py` describes the chain "PDF -> dashboard rebuilds ->
        # exec_strategic_priorities republished -> strategy rebuilds", but no
        # code implemented the last arrow. It appeared to work because a data
        # change queued both indexes at once and the worker runs them in
        # request order, so the dashboard's generator happened to write the new
        # priorities before the strategy job was claimed. Nothing guaranteed
        # that: a dashboard rebuild started on its own - which is how this
        # feature is usually rebuilt - left the chat answering from the previous
        # priorities indefinitely. Astra's chat sat three widgets behind exactly
        # this way.
        queued = requeue_dependents(account_id, hook.get("widget_key"),
                                    skip=index,
                                    reason="%s republished by %s"
                                           % (hook.get("widget_key"), index))
        return {"ran": True, "widget_key": hook.get("widget_key"),
                "queued": queued}
    except Exception as exc:
        detail = "%s: %s" % (type(exc).__name__, exc)
        logger.warning("retrieval: %s built, but regenerating %s failed - %s. "
                       "The previous output is unchanged.",
                       index, hook.get("feature_key") or index, detail)
        index_state.note_generation_error(account_id, index, detail)
        return {"ran": False, "reason": detail}


def drain(max_jobs: int = 10) -> list:
    """Claim and run queued jobs until there are none."""
    from app.services.retrieval import jobs

    done = []
    for _ in range(max_jobs):
        job = jobs.claim()
        if not job:
            break
        try:
            done.append({"account_id": job["account_id"], "index": job["index"],
                         "stats": run_job(job)})
        except Exception as exc:
            done.append({"account_id": job["account_id"], "index": job["index"],
                         "error": str(exc)})
    return done


# Startup seeding runs extractors for any feature with nothing stored. Those
# extractors trigger index updates, so on a fresh clone - or any `--reload`
# where a widget happens to be missing - startup would enqueue ingest work
# nobody asked for. The seeder wraps itself in `suppressed()` so that cannot
# happen: indexing is driven by real data changes, never by the application
# starting.
_SUPPRESSED = False


class suppressed:
    """Context manager that turns `request_update` into a no-op."""

    def __enter__(self):
        global _SUPPRESSED
        self._previous = _SUPPRESSED
        _SUPPRESSED = True
        return self

    def __exit__(self, *exc):
        global _SUPPRESSED
        _SUPPRESSED = self._previous
        return False


def is_suppressed() -> bool:
    return _SUPPRESSED


def requeue_dependents(account_id: str, widget_keys, skip: str = "",
                       reason: str = "") -> list:
    """Queue every index whose corpus is built from these widgets.

    The one entry point for "a widget was republished, so whatever reads it is
    now behind". Feature code calls this instead of reasoning about indexes:
    which index consumes which widget is declared in the registry, and a new
    widget becomes visible to the chat by being listed there rather than by
    anyone remembering to add a call here.

    Never raises and never builds inline. A queueing failure must not fail the
    regeneration that triggered it - the widget is already written and correct,
    and the index catching up later is a smaller problem than a 500 on a
    successful regenerate.

    `skip` omits the index that did the republishing, which would otherwise
    queue itself: a generated widget feeding its own corpus changes the corpus
    on every build and triggers the next one.

    Returns the indexes queued, so a caller can log or assert on them. Note the
    queue coalesces, so several widgets from one regeneration produce one job
    per index, not one per widget.
    """
    keys = [widget_keys] if isinstance(widget_keys, str) else list(widget_keys or [])
    keys = [k for k in keys if k]
    if not keys:
        return []

    queued = []
    for index in registry.dependents_of(keys):
        if skip and index == skip:
            continue
        try:
            if request_update(account_id, index,
                              reason=reason or "%s republished" % ", ".join(keys[:3])):
                queued.append(index)
        except Exception:
            logger.exception("retrieval: could not queue %s after %s changed",
                             index, ", ".join(keys[:3]))
    if queued:
        logger.info("retrieval: %s changed - queued %s for account %s",
                    ", ".join(keys[:3]), ", ".join(queued), account_id)
    return queued


def request_update(account_id: str, index: str, reason: str = "", full: bool = False):
    """The only thing feature code calls. Enqueues; never builds inline.

    Nothing in a request path and nothing at application startup may wait on an
    ingest, so this returns a queued job at most - and nothing at all while
    seeding.
    """
    from app.services.retrieval import jobs

    if _SUPPRESSED:
        logger.info("retrieval: suppressed - not queuing %s for %s (%s)",
                    index, account_id, reason or "no reason given")
        return None
    if not registry.is_enabled(index):
        logger.debug("retrieval: %s is not enabled - no job queued", index)
        return None
    return jobs.enqueue(account_id, index, reason, full=full)


def refresh_evidence_metadata(account_id: str, index: str) -> dict:
    """Rewrite the evidence registry from the corpus, without touching the graph.

    The registry gained `publisher` and `source_url` after this account was
    first indexed, so its existing rows carry neither and a news citation has no
    link to offer. A full rebuild would fix it at the cost of re-extracting every
    document - minutes of work and an LLM call per chunk - to change metadata the
    graph never sees.

    It is safe to do directly because evidence ids are deterministic: the builder
    numbers claims in the order the document is assembled, so identical content
    yields identical ids. **Guarded on the fingerprint** - a document whose
    content has changed is skipped, because then the ids would shift and the
    markers already embedded in the indexed text would point at the wrong rows.
    Those documents need a real re-ingest, which the normal path will do.
    """
    state = index_state.get(account_id, index)
    recorded = state.get("documents") or {}
    if not recorded:
        raise BuildBlocked("nothing is indexed for this account yet")

    documents = registry.build_documents(account_id, index)
    fingerprints = corpus.fingerprints(documents)

    refreshed, skipped, rows = [], [], 0
    for doc in documents:
        stored = recorded.get(doc.doc_id) or {}
        if stored.get("fingerprint") != fingerprints[doc.doc_id]["fingerprint"]:
            # Content moved since indexing; its ids would not line up.
            skipped.append(doc.doc_id)
            continue
        evidence.replace_document_evidence(
            account_id, index, doc.doc_id, doc.evidence_rows)
        refreshed.append(doc.doc_id)
        rows += len(doc.evidence_rows)

    logger.info("retrieval: refreshed evidence for %d document(s) (%d rows), "
                "skipped %d changed", len(refreshed), rows, len(skipped))
    return {"refreshed": refreshed, "skipped": skipped, "rows": rows}


def retire_index(account_id: str, index: str, reason: str = "") -> dict:
    """Drop an index's workspace and mark it retired.

    The reason this exists rather than calling `client.drop_workspace` directly:
    dropping the data alone leaves `retrieval_index_state` still reading READY
    and naming a workspace that no longer holds anything. The next query or data
    change would then reopen it and answer from an empty graph, reporting "no
    such fact" rather than "no index" - a silent wrong answer instead of an
    honest refusal.

    What retiring now reclaims is storage, not Atlas index capacity: the three
    shared vector indexes serve every account and are never dropped. The
    account's rows are removed from the shared collections by partition.

    What survives: the published widget and the evidence registry, both stored
    outside the workspace. The feature keeps rendering its last build with
    working source chips; it simply cannot retrieve or regenerate until rebuilt.
    """
    workspace = client.workspace_name(account_id, index)
    dropped = client.drop_workspace(workspace)
    state = index_state.retire(account_id, index, reason)
    return {"workspace": workspace, "dropped": dropped, "status": state["status"]}
