"""Tests for driving LightRAG's storage from several event loops in one process.

The production failure these pin: the query loop opens a handle, LightRAG's
process-wide `ClientManager` binds its one `AsyncMongoClient` to that loop, and
the worker's own `asyncio.run()` loop then fails every build with "Cannot use
AsyncMongoClient in different event loop". `multiloop.install()` makes the
client per loop and the shared locks loop-agnostic; `query.retrieve` hands a
retrieval started on any other loop to the query loop.

No Mongo and no network: the client is a fake that records the loop it was
created on and refuses to close on any other, which is exactly what pymongo
does. Locks are exercised with real loops on real threads, because the bugs
they guard against only exist across threads.

Run: python -m pytest tests/test_retrieval_multiloop.py -v
"""

import asyncio
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import client, multiloop, query
from app.services.retrieval.multiloop import LoopAgnosticLock

# ---------------------------------------------------------------------------
# Fakes and helpers
# ---------------------------------------------------------------------------

class FakeDb:
    def __init__(self, owner, name):
        self.owner = owner
        self.name = name


class FakeAsyncMongoClient:
    """Bound to the loop it is created on; closable only there, as pymongo's is."""

    def __init__(self, uri, **kwargs):
        self.uri = uri
        self.kwargs = kwargs
        self.loop = asyncio.get_running_loop()
        self.closed = False

    def get_database(self, name):
        return FakeDb(self, name)

    async def close(self):
        if asyncio.get_running_loop() is not self.loop:
            raise RuntimeError("Cannot use AsyncMongoClient in different event loop.")
        self.closed = True


def in_thread_loop(coro_fn, timeout=10):
    """Run `coro_fn()` under a fresh `asyncio.run()` on another thread - the worker's shape."""
    box = {}

    def run():
        try:
            box["result"] = asyncio.run(coro_fn())
        except BaseException as exc:  # re-raised on the caller's thread
            box["error"] = exc

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout)
    assert not thread.is_alive(), "the thread loop did not finish"
    if "error" in box:
        raise box["error"]
    return box["result"]


class LiveLoop:
    """A loop that keeps running on its own thread - the query loop's shape."""

    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro, timeout=10):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def close(self):
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(5)
        self.loop.close()


@pytest.fixture
def manager(monkeypatch):
    from lightrag.kg import mongo_impl

    multiloop.install()
    monkeypatch.setattr(mongo_impl, "AsyncMongoClient", FakeAsyncMongoClient)
    monkeypatch.setenv("MONGO_URI", "mongodb://fake")
    monkeypatch.setenv("MONGO_DATABASE", "hp_test")
    multiloop._clients.clear()
    yield mongo_impl.ClientManager
    multiloop._clients.clear()


# ---------------------------------------------------------------------------
# ClientManager: one client per loop
# ---------------------------------------------------------------------------

def test_one_client_per_loop_shared_within_it(manager):
    async def two_storages():
        a = await manager.get_client()
        b = await manager.get_client()
        return a, b

    a1, b1 = in_thread_loop(two_storages)
    a2, b2 = in_thread_loop(two_storages)

    assert a1.owner is b1.owner, "storages on one loop share a client"
    assert a2.owner is b2.owner
    assert a1.owner is not a2.owner, "a second loop gets its own client"
    assert a1.owner.loop is not a2.owner.loop
    assert a1.name == "hp_test"
    assert a1.owner.uri == "mongodb://fake"


def test_a_live_loop_holding_a_client_does_not_block_another_loop(manager):
    """The production shape: the query loop holds a handle open forever, the
    worker's asyncio.run() must still get a usable client of its own."""
    query_like = LiveLoop()
    try:
        held = query_like.run(manager.get_client())

        async def worker_job():
            db = await manager.get_client()
            await manager.release_client(db)
            return db

        used = in_thread_loop(worker_job)
        assert used.owner is not held.owner
        assert used.owner.closed, "the worker's client closes with its last release"
        assert not held.owner.closed, "the query loop's client is untouched"
        assert [c["ref_count"] for c in multiloop.open_clients()] == [1]

        query_like.run(manager.release_client(held))
        assert held.owner.closed
        assert multiloop.open_clients() == []
    finally:
        query_like.close()


def test_client_closes_only_when_its_last_user_releases(manager):
    async def lifecycle():
        a = await manager.get_client()
        b = await manager.get_client()
        await manager.release_client(a)
        after_first = (a.owner.closed, multiloop.open_clients()[0]["ref_count"])
        await manager.release_client(b)
        return after_first, a.owner.closed, multiloop.open_clients()

    after_first, closed, remaining = in_thread_loop(lifecycle)
    assert after_first == (False, 1)
    assert closed is True
    assert remaining == []


def test_a_closed_loop_that_never_released_is_dropped_on_the_next_call(manager, caplog):
    """A build that dies before finalising leaves a client bound to a dead loop.
    It cannot be closed from anywhere; it must not stay in the table either."""
    async def leak():
        return await manager.get_client()

    leaked = in_thread_loop(leak)
    assert len(multiloop.open_clients()) == 1
    assert leaked.owner.loop.is_closed()

    with caplog.at_level("WARNING", logger="app.services.retrieval.multiloop"):
        fresh = in_thread_loop(manager.get_client)
    assert fresh.owner is not leaked.owner
    assert not leaked.owner.closed, "a dead loop's client cannot be closed"
    assert "unreleased" in caplog.text
    # Only the fresh loop's entry remains, itself now stale.
    assert len(multiloop.open_clients()) == 1


def test_releasing_none_or_an_unknown_db_is_harmless(manager):
    async def release_strangers():
        await manager.release_client(None)
        await manager.release_client(FakeDb(None, "nobody"))
        return multiloop.open_clients()

    assert in_thread_loop(release_strangers) == []


def test_install_replaces_the_shared_locks_and_is_idempotent():
    from lightrag.kg import mongo_impl, shared_storage

    multiloop.install()
    multiloop.install()

    assert isinstance(shared_storage._internal_lock, LoopAgnosticLock)
    assert isinstance(shared_storage._data_init_lock, LoopAgnosticLock)
    assert mongo_impl.ClientManager.get_client.__func__ is multiloop._get_client
    assert mongo_impl.ClientManager.release_client.__func__ is multiloop._release_client

    # The keyed locks LightRAG hands out are the loop-agnostic kind too, and the
    # bookkeeping still drops an entry on its last release.
    keyed = shared_storage._storage_keyed_lock
    lock = keyed._get_or_create_async_lock("ns:key")
    assert isinstance(lock, LoopAgnosticLock)
    assert keyed._get_or_create_async_lock("ns:key") is lock
    keyed._release_async_lock("ns:key")
    keyed._release_async_lock("ns:key")
    assert "ns:key" not in keyed._async_lock

    # And the library's own wrappers still work on them.
    async def take_both():
        async with shared_storage.get_data_init_lock(), shared_storage.get_internal_lock():
            return (shared_storage._data_init_lock.locked(),
                    shared_storage._internal_lock.locked())

    assert in_thread_loop(take_both) == (True, True)
    assert not shared_storage._data_init_lock.locked()


# ---------------------------------------------------------------------------
# LoopAgnosticLock
# ---------------------------------------------------------------------------

def test_lock_excludes_across_two_loops_on_two_threads():
    """What an asyncio.Lock cannot do: two loops contend on one lock and never
    overlap in the critical section."""
    lock = LoopAgnosticLock()
    inside = {"now": 0, "max": 0, "entries": 0}

    async def hammer(n):
        for _ in range(n):
            async with lock:
                inside["now"] += 1
                inside["max"] = max(inside["max"], inside["now"])
                inside["entries"] += 1
                await asyncio.sleep(0)   # yield while holding, so overlap could happen
                inside["now"] -= 1

    async def many():
        await asyncio.gather(*(hammer(25) for _ in range(4)))

    threads = [threading.Thread(target=lambda: asyncio.run(many())) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(20)
    assert all(not t.is_alive() for t in threads)

    assert inside["entries"] == 3 * 4 * 25
    assert inside["max"] == 1, "two holders were inside the critical section at once"
    assert not lock.locked()


def test_lock_is_handed_over_in_order_and_freed_when_nobody_waits():
    async def scenario():
        lock = LoopAgnosticLock()
        order = []
        await lock.acquire()

        async def waiter(name):
            async with lock:
                order.append(name)

        tasks = [asyncio.create_task(waiter(n)) for n in ("first", "second", "third")]
        await asyncio.sleep(0)             # all three are queued
        assert lock.locked()
        lock.release()
        await asyncio.gather(*tasks)
        return order, lock.locked()

    assert asyncio.run(scenario()) == (["first", "second", "third"], False)


def test_a_waiter_cancelled_while_queued_simply_withdraws():
    async def scenario():
        lock = LoopAgnosticLock()
        await lock.acquire()
        waiter = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert lock.locked(), "the holder still holds it"
        lock.release()
        return lock.locked()

    assert asyncio.run(scenario()) is False


def test_a_waiter_cancelled_as_the_lock_reaches_it_passes_it_on():
    """Two orderings of the same race. Either way the lock must end up with the
    next waiter, never stuck with a task that is no longer running."""
    async def cancelled_before_hand_over_runs():
        lock = LoopAgnosticLock()
        await lock.acquire()
        doomed = asyncio.create_task(lock.acquire())
        survivor = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        lock.release()      # hand-over to `doomed` is scheduled, not yet run
        doomed.cancel()     # ...and it is cancelled first
        with pytest.raises(asyncio.CancelledError):
            await doomed
        assert await asyncio.wait_for(survivor, 1) is True
        assert lock.locked()
        lock.release()
        return lock.locked()

    async def cancelled_after_it_was_given_the_lock():
        lock = LoopAgnosticLock()
        await lock.acquire()
        doomed = asyncio.create_task(lock.acquire())
        await asyncio.sleep(0)
        lock.release()
        await asyncio.sleep(0)   # hand-over ran: the future holds the result
        doomed.cancel()          # but the task is cancelled before it resumes
        with pytest.raises(asyncio.CancelledError):
            await doomed
        return lock.locked()

    assert asyncio.run(cancelled_before_hand_over_runs()) is False
    assert asyncio.run(cancelled_after_it_was_given_the_lock()) is False


def test_release_when_free_is_an_error():
    lock = LoopAgnosticLock()
    with pytest.raises(RuntimeError):
        lock.release()


# ---------------------------------------------------------------------------
# query.retrieve from a foreign loop
# ---------------------------------------------------------------------------

class FakeRag:
    def __init__(self):
        self.loops = []

    async def aquery_llm(self, question, param=None):
        self.loops.append(asyncio.get_running_loop())
        return {"response": "ctx for %s" % question, "chunks": [
            {"file_path": "doc.pdf", "content": "some text acct#c1"}]}


@pytest.fixture
def fake_index(monkeypatch):
    rag = FakeRag()

    async def handle(account_id, index):
        return rag

    monkeypatch.setattr(client, "query_handle", handle)
    monkeypatch.setattr(query.index_state, "get",
                        lambda *_: {"status": "READY", "workspace": "acct_a1_strategy"})
    monkeypatch.setattr(query.registry, "spec", lambda *_: {"default_mode": "naive"})
    return rag


def test_retrieve_from_another_loop_runs_on_the_query_loop(fake_index):
    result = in_thread_loop(lambda: query.retrieve("a1", "strategy", "q?", only_context=True))

    assert result.context.startswith("some text")
    assert result.graph_context == "ctx for q?"
    assert fake_index.loops == [client._query_loop]
    assert client._query_loop.is_running(), "the caller's loop closed; the query loop did not"


def test_retrieve_twice_from_two_throwaway_loops_reuses_the_one_query_loop(fake_index):
    in_thread_loop(lambda: query.retrieve("a1", "strategy", "q1"))
    in_thread_loop(lambda: query.retrieve("a1", "strategy", "q2"))
    assert fake_index.loops == [client._query_loop, client._query_loop]


def test_ask_and_retrieve_land_on_the_same_loop(fake_index):
    query.ask("a1", "strategy", "q1")
    in_thread_loop(lambda: query.retrieve("a1", "strategy", "q2"))
    assert len(set(fake_index.loops)) == 1
    assert fake_index.loops[0] is client._query_loop
