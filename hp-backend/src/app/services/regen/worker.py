"""Background threads that drain the regeneration queue and run the sweep.

In-process, like the retrieval worker it replaces: the queue is in Mongo, so
moving this to its own service later is a deployment change, not a redesign.

The worker only ever claims jobs an explicit regeneration run created; the
"sweep" thread only reports how much is stale. Neither starts work on its own.

Off unless switched on. `REGEN_WORKER_ENABLED=1` and `REGEN_SWEEP_ENABLED=1`
are set by the compose files that run the real service; a laptop pointed at a
shared database reads it without generating anything - otherwise two machines
with different code would each regenerate the other's output.
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

POLL_SECONDS = 5
SWEEP_SECONDS = int(os.getenv("REGEN_SWEEP_SECONDS", "600"))
STARTUP_SWEEP_DELAY = 30

_stop = threading.Event()
_threads: list = []
_engine = None


def worker_enabled() -> bool:
    return os.getenv("REGEN_WORKER_ENABLED", "") == "1"


def sweep_enabled() -> bool:
    return os.getenv("REGEN_SWEEP_ENABLED", "") == "1"


def _work_loop(engine):
    logger.info("regen worker %s: started", engine.worker_id)
    while not _stop.is_set():
        try:
            outcome = engine.run_once()
        except Exception:
            # A queue failure - a dropped connection - must not kill the worker,
            # or regeneration stops silently.
            logger.exception("regen worker: loop error")
            outcome = None
        if outcome is None:
            _stop.wait(POLL_SECONDS)
    logger.info("regen worker: stopped")


def _sweep_loop(engine):
    """Report, never run: how many accounts have outputs that need a run.

    Until 29 Sep this reconciled every account and ENQUEUED every stale node -
    so a deploy that changed one prompt regenerated that section for every
    account, and a restart re-queued whatever was stale. Now it only logs the
    count; the admin page shows the detail and Submit does the work.
    """
    if _stop.wait(STARTUP_SWEEP_DELAY):
        return
    while not _stop.is_set():
        try:
            summary = engine.stale_report()
            logger.info("regen: %d of %d account(s) have outputs that need a run "
                        "(nothing queued - submit from the admin page) %s",
                        summary["accounts_needing_run"], summary["accounts"],
                        summary["by_status"])
        except Exception:
            logger.exception("regen stale report: failed")
        if _stop.wait(SWEEP_SECONDS):
            return


def start(engine=None) -> list:
    """Start the enabled threads once. Safe to call repeatedly."""
    if any(t.is_alive() for t in _threads):
        return _threads
    if not (worker_enabled() or sweep_enabled()):
        logger.info("regen: worker and sweep disabled on this host")
        return []

    from app.services.regen.engine import get_engine
    global _engine
    engine = engine or get_engine()
    engine.ensure_indexes()
    _engine = engine
    _stop.clear()
    _threads.clear()
    workers = max(1, int(os.getenv("REGEN_WORKERS", "1")))
    if worker_enabled():
        for i in range(workers):
            _threads.append(threading.Thread(target=_work_loop, args=(engine,),
                                             name="regen-worker-%d" % i, daemon=True))
    if sweep_enabled():
        _threads.append(threading.Thread(target=_sweep_loop, args=(engine,),
                                         name="regen-sweep", daemon=True))
    for t in _threads:
        t.start()
    return _threads


def stop(timeout: float = 5.0) -> None:
    _stop.set()
    _release_running()
    for t in _threads:
        t.join(timeout=timeout)


def _release_running() -> None:
    """Give this process's running jobs back to the queue before it exits.

    The producer threads are daemons and die with the process mid-job; handed
    back now, the next backend picks those jobs up as soon as it starts instead
    of when their leases lapse. Anything the old threads still try to commit is
    fenced off, because the release cleared their fence.
    """
    if _engine is None or not worker_enabled():
        return
    from app.services.regen import jobs, state
    try:
        for job in jobs.release_owned(_engine.db, _engine.worker_id):
            state.clear_running(_engine.db, job["account_id"], job["node_id"], job["_id"])
            logger.info("regen: handed %s/%s back to the queue on shutdown",
                        job["account_id"], job["node_id"])
    except Exception:
        logger.exception("regen: could not hand running jobs back on shutdown")
