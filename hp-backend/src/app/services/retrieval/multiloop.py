"""LightRAG's single-process state, made safe to drive from several event loops.

LightRAG's Mongo backends and its `shared_storage` module assume that one
process means one event loop. This process runs several: the permanent
"retrieval-query-loop" thread that owns every cached query handle (client.py),
the ingest worker's fresh `asyncio.run()` loop per job, FastAPI's own loop, and
whatever loop a test or a script brings. Three things in 1.5.7 bind themselves
to whichever loop touches them first and then BREAK - not degrade - when a
second loop arrives:

  1. `mongo_impl.ClientManager` holds ONE `AsyncMongoClient` for the process,
     ref-counted across every storage of every handle. pymongo binds an async
     client to the loop it first runs on, so once the query loop had opened a
     handle, the worker's build died with "Cannot use AsyncMongoClient in
     different event loop" - the production failure this module exists for.
     The query handles are never finalised (that is the point of caching them),
     so the count never returned to zero and the client never rebound.

  2. `shared_storage._internal_lock` and `_data_init_lock` are plain
     `asyncio.Lock`s created once per process. Every storage `initialize()`
     takes the second, so two loops building handles at the same time contend
     on it - and an `asyncio.Lock` binds to the loop of its first WAITER, then
     raises "is bound to a different event loop" for any other.

  3. `KeyedUnifiedLock` hands out one `asyncio.Lock` per key, process-wide,
     from dicts it updates without a lock because it assumes a single loop. The
     vector stores' flush lock is keyed on the SHARED collection name, so the
     query loop's `shared_vdb_chunks` instance and the worker's share one lock.

The fix keeps the library's shape and changes only what is loop-bound:

  * the Mongo client becomes one per running loop, released and closed when
    that loop's last storage lets go of it;
  * the shared locks become `LoopAgnosticLock`s - an asyncio-style mutex that
    wakes each waiter on its own loop, so it can be awaited from any loop on
    any thread and is still ONE lock. Mutual exclusion across loops is kept,
    not traded for per-loop copies: `_internal_lock` guards plain dicts that
    two threads would otherwise mutate at once.

Nothing here edits site-packages. `install()` patches at runtime, once per
process, from `client.build_rag()` - before the first handle exists, so none of
these objects is in use when it is replaced.
"""

import asyncio
import collections
import logging
import os
import threading

logger = logging.getLogger(__name__)

_INSTALLED = False
_INSTALL_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# A mutex that any loop can await
# ---------------------------------------------------------------------------

class LoopAgnosticLock:
    """An asyncio-style mutex that can be awaited from any event loop, on any thread.

    A drop-in for the three methods LightRAG uses on an `asyncio.Lock`:
    `await acquire()`, `release()` and `locked()`. State lives behind a
    `threading.Lock`; a waiter parks on a future of its OWN loop and is woken
    through that loop's `call_soon_threadsafe`, the one cross-thread entry
    point asyncio guarantees.

    Ownership passes straight from the releaser to the first live waiter, as in
    `asyncio.Lock`: fair, and never observed free while someone is queued. A
    waiter cancelled after ownership reached it passes the lock on.
    """

    def __init__(self):
        self._mutex = threading.Lock()
        self._locked = False
        self._waiters = collections.deque()   # (loop, future), arrival order

    def locked(self) -> bool:
        return self._locked

    async def acquire(self) -> bool:
        loop = asyncio.get_running_loop()
        with self._mutex:
            if not self._locked:
                self._locked = True
                return True
            fut = loop.create_future()
            self._waiters.append((loop, fut))
        try:
            await fut
        except BaseException:
            with self._mutex:
                queued = (loop, fut) in self._waiters
                if queued:
                    self._waiters.remove((loop, fut))
            # Not queued means ownership was already on its way here. A future
            # carrying the result means this waiter owns the lock and must pass
            # it on; one cancelled first was skipped by `_hand_over` already.
            if not queued and fut.done() and not fut.cancelled():
                self.release()
            raise
        return True

    def release(self):
        with self._mutex:
            if not self._locked:
                raise RuntimeError("Lock is not acquired.")
            self._pass_on()

    def _pass_on(self):
        """Hand the lock to the next live waiter, or free it. Caller holds `_mutex`."""
        while self._waiters:
            loop, fut = self._waiters.popleft()
            if fut.done() or loop.is_closed():
                continue
            try:
                loop.call_soon_threadsafe(self._hand_over, fut)
                return
            except RuntimeError:
                continue   # the loop closed between the check and the call
        self._locked = False

    def _hand_over(self, fut):
        # Runs on the waiter's own loop, so the future cannot change underneath.
        if fut.done():
            with self._mutex:
                self._pass_on()
        else:
            fut.set_result(True)

    async def __aenter__(self):
        await self.acquire()

    async def __aexit__(self, *exc):
        self.release()


# ---------------------------------------------------------------------------
# One Mongo client per event loop
# ---------------------------------------------------------------------------

_clients = {}                     # running loop -> {"client", "db", "ref_count"}
_clients_mutex = threading.Lock()


async def _get_client(cls):
    """`ClientManager.get_client`, keyed by the running loop.

    Reads the same environment variables and config fallbacks as the original,
    so pointing LightRAG at the cluster (`client._apply_mongo_env`) is unchanged.
    """
    from lightrag.kg import mongo_impl

    loop = asyncio.get_running_loop()
    with _clients_mutex:
        # A loop that closed without releasing - a build that died before its
        # handle was finalised - leaves a client that can never be closed, since
        # closing needs the loop it was bound to. Drop the reference and say so.
        for stale in [known for known in _clients if known.is_closed()]:
            entry = _clients.pop(stale)
            logger.warning("retrieval: dropped a Mongo client with %d unreleased "
                           "reference(s) from a closed event loop", entry["ref_count"])

        entry = _clients.get(loop)
        if entry is None:
            uri = os.environ.get("MONGO_URI", mongo_impl.config.get(
                "mongodb", "uri", fallback="mongodb://root:root@localhost:27017/"))
            database = os.environ.get("MONGO_DATABASE", mongo_impl.config.get(
                "mongodb", "database", fallback="LightRAG"))
            client = mongo_impl.AsyncMongoClient(
                uri, driver=mongo_impl.DriverInfo(name="LightRAG",
                                                  version=mongo_impl.__version__))
            entry = {"client": client, "db": client.get_database(database),
                     "ref_count": 0}
            _clients[loop] = entry
            logger.info("retrieval: opened a Mongo client for event loop %#x "
                        "(%d loop(s) hold one)", id(loop), len(_clients))
        entry["ref_count"] += 1
        return entry["db"]


async def _release_client(cls, db):
    """`ClientManager.release_client`: close a loop's client when its last user lets go."""
    if db is None:
        return
    closing = None
    with _clients_mutex:
        for loop, entry in list(_clients.items()):
            if entry["db"] is db:
                entry["ref_count"] -= 1
                if entry["ref_count"] <= 0:
                    del _clients[loop]
                    closing = (loop, entry["client"])
                break
    if closing is None:
        return

    # Outside the mutex, because closing talks to the server. And only on the
    # client's own loop - pymongo refuses any other - so a db released from a
    # foreign loop is dropped rather than closed.
    loop, client = closing
    if loop is asyncio.get_running_loop():
        await client.close()
        logger.info("retrieval: closed the Mongo client for event loop %#x", id(loop))
    else:
        logger.warning("retrieval: a Mongo client was released from a loop other "
                       "than its own and cannot be closed there - dropped")


def open_clients() -> list:
    """`[{"loop", "ref_count"}, ...]` - what is open right now. For tests and diagnostics."""
    with _clients_mutex:
        return [{"loop": loop, "ref_count": entry["ref_count"]}
                for loop, entry in _clients.items()]


# ---------------------------------------------------------------------------
# Keyed locks: thread-safe bookkeeping, loop-agnostic locks
# ---------------------------------------------------------------------------

_keyed_mutex = threading.Lock()


def _keyed_get_or_create(self, combined_key):
    with _keyed_mutex:
        lock = self._async_lock.get(combined_key)
        if lock is None:
            lock = self._async_lock[combined_key] = LoopAgnosticLock()
        self._async_lock_count[combined_key] = \
            self._async_lock_count.get(combined_key, 0) + 1
        return lock


def _keyed_release_under(original):
    def _release(self, combined_key):
        with _keyed_mutex:
            original(self, combined_key)
    return _release


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

# Every private name this module reaches into. Checked before anything is
# patched so a LightRAG upgrade that renames one fails at the first build with
# the name in the message, instead of half-patching and failing in the worker.
_SHARED_STORAGE_NAMES = ("initialize_share_data", "_is_multiprocess", "_internal_lock",
                         "_data_init_lock", "KeyedUnifiedLock")
_KEYED_LOCK_NAMES = ("_get_or_create_async_lock", "_release_async_lock")
_MONGO_IMPL_NAMES = ("ClientManager", "AsyncMongoClient", "DriverInfo", "config",
                     "__version__")


def install():
    """Patch LightRAG for multi-loop use. Idempotent; runs before the first handle."""
    global _INSTALLED
    with _INSTALL_LOCK:
        if _INSTALLED:
            return

        from lightrag.kg import mongo_impl, shared_storage

        for module, names in ((shared_storage, _SHARED_STORAGE_NAMES),
                              (shared_storage.KeyedUnifiedLock, _KEYED_LOCK_NAMES),
                              (mongo_impl, _MONGO_IMPL_NAMES)):
            for name in names:
                if not hasattr(module, name):
                    raise RuntimeError(
                        "lightrag has no %s.%s - multiloop.py was written against "
                        "1.5.7 and must be re-checked before this build can run"
                        % (getattr(module, "__name__", module), name))

        # The shared locks are created by initialize_share_data(), which the
        # LightRAG constructor also calls and which is a no-op once done. So
        # run it here first, then replace the locks before any storage can
        # hold one. Multi-worker mode keeps its locks elsewhere and is not a
        # deployment this service has; refuse rather than half-protect it.
        shared_storage.initialize_share_data()
        if shared_storage._is_multiprocess:
            raise RuntimeError("retrieval: LightRAG is in multi-process mode, which "
                               "multiloop.py does not cover")
        shared_storage._internal_lock = LoopAgnosticLock()
        shared_storage._data_init_lock = LoopAgnosticLock()

        keyed = shared_storage.KeyedUnifiedLock
        keyed._get_or_create_async_lock = _keyed_get_or_create
        keyed._release_async_lock = _keyed_release_under(keyed._release_async_lock)

        mongo_impl.ClientManager.get_client = classmethod(_get_client)
        mongo_impl.ClientManager.release_client = classmethod(_release_client)

        _INSTALLED = True
        logger.info("retrieval: LightRAG storage patched for use from several event loops")
