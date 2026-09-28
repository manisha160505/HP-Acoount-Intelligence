"""Background threads that drain the regeneration queue and run the sweep.

In-process, like the retrieval worker it replaces: the queue is in Mongo, so
moving this to its own service later is a deployment change, not a redesign.

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
    if _stop.wait(STARTUP_SWEEP_DELAY):
        return
    while not _stop.is_set():
        try:
            summary = engine.sweep(int(os.getenv("REGEN_LEGACY_ACCOUNTS_PER_SWEEP", "5")))
            logger.info("regen sweep: %d account(s), %d job(s) queued",
                        summary["accounts"], summary["queued"])
        except Exception:
            logger.exception("regen sweep: failed")
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
    engine = engine or get_engine()
    engine.ensure_indexes()
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
    for t in _threads:
        t.join(timeout=timeout)
