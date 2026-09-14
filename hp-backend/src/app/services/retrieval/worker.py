"""The background worker that drains the retrieval job queue.

An in-process thread for now, reading the same Mongo collection a dedicated
Render worker would read. That is the point of putting the queue in the
database rather than in memory: moving this loop to its own service later is a
deployment change, not a redesign, and until then a single web instance still
gets its indexes built.

Deliberate properties:

  * **Nothing runs at import or during seeding.** `start()` is called from the
    application lifespan after startup has finished, and every job it runs goes
    through `ingest.update_index`, which is never invoked inline by a request.

  * **One job at a time.** Ingest is LLM-bound and already parallel internally;
    running two builds concurrently would multiply the token spend without
    finishing sooner, and two builds of the SAME index would collide in the one
    workspace the cluster allows.

  * **A crash loses nothing.** The job row stays leased; when the lease expires
    another worker - or this one after a restart - reclaims it.
"""

import logging
import threading
import time

logger = logging.getLogger(__name__)

POLL_SECONDS = 15
IDLE_LOG_EVERY = 240        # how often to say "still here" when there is nothing

_thread = None
_stop = threading.Event()


def _loop():
    from app.services.retrieval import ingest, jobs

    logger.info("retrieval worker: started")
    quiet_for = 0

    while not _stop.is_set():
        try:
            job = jobs.claim()
            if not job:
                quiet_for += POLL_SECONDS
                if quiet_for >= IDLE_LOG_EVERY:
                    logger.debug("retrieval worker: idle")
                    quiet_for = 0
                _stop.wait(POLL_SECONDS)
                continue

            quiet_for = 0
            logger.info("retrieval worker: building %s for account %s%s",
                        job["index"], job["account_id"],
                        " (full rebuild)" if job.get("full") else "")
            started = time.time()
            try:
                stats = ingest.run_job(job)
                logger.info("retrieval worker: finished %s for %s in %.0fs - %s",
                            job["index"], job["account_id"], time.time() - started,
                            stats)
            except BaseException:
                # run_job has already recorded the failure on both the job and
                # the index state; the loop must survive it either way.
                logger.exception("retrieval worker: job failed")

        except Exception:
            # A failure in the queue itself - a dropped connection, say - must
            # not kill the worker, or indexes stop building silently.
            logger.exception("retrieval worker: loop error")
            _stop.wait(POLL_SECONDS)

    logger.info("retrieval worker: stopped")


def start():
    """Start the worker once. Safe to call repeatedly."""
    global _thread
    if _thread is not None and _thread.is_alive():
        return _thread

    from app.services.retrieval import jobs
    try:
        jobs.ensure_indexes()
    except Exception:
        logger.exception("retrieval worker: could not ensure job indexes")

    _stop.clear()
    _thread = threading.Thread(target=_loop, name="retrieval-worker", daemon=True)
    _thread.start()
    return _thread


def stop(timeout: float = 5.0):
    _stop.set()
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=timeout)


def is_running() -> bool:
    return _thread is not None and _thread.is_alive()
