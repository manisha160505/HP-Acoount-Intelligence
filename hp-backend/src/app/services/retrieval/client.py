"""LightRAG wiring for the retrieval layer.

One place decides how a LightRAG handle is built, so the rest of the codebase
never imports the library directly and never learns its constructor.

Three things here are load-bearing and easy to get wrong:

  * **The settings are the existing ones.** `OPENAI_API_KEY` and
    `OPENAI_ENDPOINT` already point at the Azure deployment for every other
    feature; the retrieval layer reuses them rather than introducing a second
    OpenAI configuration that can drift. The only genuinely new setting is the
    embedding model, because nothing embedded anything before.

  * **The Mongo backends read their own environment variables**, and they are
    not the names the published docs give. The installed 1.5.7 reads
    `MONGO_URI`, `MONGO_DATABASE` and `MONGODB_WORKSPACE` - the documented
    `MONGODB_URI` / `MONGODB_DB_NAME` are silently ignored, which would leave
    LightRAG connecting to `mongodb://root:root@localhost:27017/` while
    appearing configured. They are set here from `settings` immediately before
    a handle is constructed.

  * **A workspace name becomes a storage namespace**, so it is restricted to
    `[A-Za-z0-9_]`. Anything else - a `::` separator, a hyphen - is rejected
    rather than sanitised silently, because two accounts whose names sanitise
    to the same string would share an index.
"""

import asyncio
import logging
import os
import re
import threading

from app.config.settings import settings

logger = logging.getLogger(__name__)

WORKSPACE_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Kept modest: these bound how much of the LLM budget one ingest can spend.
LLM_MAX_ASYNC = 4
EMBEDDING_MAX_ASYNC = 8
EMBEDDING_BATCH_NUM = 32


class RetrievalConfigError(Exception):
    """The retrieval layer cannot be configured from the current settings."""


def _slug(value) -> str:
    """Lowercase, underscore-separated, alphanumeric only."""
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", str(value or ""))).strip("_").lower()


def workspace_name(account_id: str, index: str) -> str:
    """The storage namespace for one index of one account.

    Two things now hang off this name. It prefixes the per-workspace KV, graph
    and doc-status collections, as it always did - and it is also the value of
    the `workspace` field that partitions the shared vector collections, which
    makes it an isolation boundary rather than just a naming convention. That
    is why an unusable name raises here instead of being sanitised: two accounts
    whose names collapsed to the same string would share a partition.

    The workspace is stable across builds, not numbered per build. An earlier
    design numbered it so a replacement could be built beside the live one and
    swapped in atomically, which needed two workspaces to coexist - impossible
    when each cost three Atlas vector indexes against a cap of three. The shared
    vector layer removes that particular cost, but the stable name is kept
    because the update strategy no longer needs a swap: a normal change touches
    only the documents that changed, in place. `version` lives in
    `retrieval_index_state`, not in the name.
    """
    account = _slug(account_id)
    idx = _slug(index)
    if not account or not idx:
        raise RetrievalConfigError(
            "cannot build a workspace name from account_id=%r index=%r"
            % (account_id, index))
    name = "acct_%s_%s" % (account, idx)
    if not WORKSPACE_RE.match(name):
        raise RetrievalConfigError("workspace %r is not [A-Za-z0-9_]" % name)
    return name


def _openai_client():
    from openai import OpenAI

    api_key = (settings.OPENAI_API_KEY or "").strip()
    if not api_key:
        raise RetrievalConfigError(
            "OPENAI_API_KEY is not set - the retrieval layer cannot embed or extract")
    kwargs = {"api_key": api_key}
    endpoint = (settings.OPENAI_ENDPOINT or "").strip()
    if endpoint:
        kwargs["base_url"] = endpoint
    return OpenAI(**kwargs)


def retrieval_model() -> str:
    """The model the retrieval layer runs on.

    Falls back to the application-wide model, so setting
    `OPENAI_RETRIEVAL_MODEL` moves ONLY the RAG layer - extraction and answer
    synthesis - onto a different deployment while the other features stay where
    they are.
    """
    return (settings.OPENAI_RETRIEVAL_MODEL or settings.OPENAI_MODEL_NAME
            or "gpt-4o").strip()


# Models that reject a custom temperature, learned at runtime rather than
# hardcoded. gpt-5.6-sol answers `temperature=0` with "Only the default (1)
# value is supported", so sending it fails every call. Rather than maintain a
# list that goes stale, the first rejection is remembered and the request is
# retried without it - one wasted call per process, then never again.
_NO_TEMPERATURE = set()
_TEMPERATURE_REJECTED = "does not support"


async def _llm_model_func(prompt, system_prompt=None, history_messages=None,
                          _model_override=None, **kwargs):
    """What LightRAG calls for entity extraction and answer generation.

    The SDK call is blocking, so it runs in a thread rather than stalling the
    event loop LightRAG drives its pipeline with - same shape as the supplied
    reference rig.
    """
    client = _openai_client()
    model = _model_override or retrieval_model()
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(history_messages or [])
    messages.append({"role": "user", "content": prompt})

    def _call(with_temperature: bool):
        extra = {"temperature": 0} if with_temperature else {}
        return client.chat.completions.create(
            model=model, messages=messages, **extra)

    try:
        response = await asyncio.to_thread(_call, model not in _NO_TEMPERATURE)
    except Exception as exc:
        if model in _NO_TEMPERATURE or _TEMPERATURE_REJECTED not in str(exc) \
                or "temperature" not in str(exc):
            raise
        logger.info("retrieval: %s rejects a custom temperature - using its "
                    "default for the rest of this process", model)
        _NO_TEMPERATURE.add(model)
        response = await asyncio.to_thread(_call, False)

    return response.choices[0].message.content


async def _embedding_func(texts):
    import numpy as np

    client = _openai_client()
    response = await asyncio.to_thread(
        client.embeddings.create,
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=list(texts),
    )
    return np.array([item.embedding for item in response.data])


def _apply_mongo_env():
    """Point LightRAG's Mongo backends at the same cluster the app uses.

    Set immediately before a handle is built rather than at import, so a test
    or a script that overrides MONGODB_URI still gets a consistent pair.
    """
    uri = (settings.MONGODB_URI or "").strip()
    if not uri:
        raise RetrievalConfigError("MONGODB_URI is not set")
    os.environ["MONGO_URI"] = uri
    os.environ["MONGO_DATABASE"] = settings.DB_NAME


def query_model() -> str:
    """The model LightRAG uses at QUERY time, as distinct from build time.

    Answering a question still costs a model call inside LightRAG - it extracts
    keywords from the question before it searches. On the retrieval model that
    call is several seconds of a seller's wait, and it is doing something far
    simpler than entity extraction.

    Safe to differ from the build model: the graph is already written, and
    nothing at query time changes it. Extraction stays on the retrieval model so
    the graph is built consistently; the question is parsed by the faster one.
    """
    return (settings.OPENAI_MODEL_NAME or "gpt-4o").strip()


async def _query_llm_model_func(prompt, system_prompt=None, history_messages=None,
                                **kwargs):
    """The same call as `_llm_model_func`, on the query-time model."""
    return await _llm_model_func(prompt, system_prompt, history_messages,
                                 _model_override=query_model(), **kwargs)


async def build_rag(account_id: str, index: str, for_query: bool = False):
    """An initialised LightRAG handle for one workspace.

    The caller owns the handle and must `finalize_storages()` it. Nothing is
    cached here: a handle is bound to one workspace, and workspaces change on
    every build.
    """
    from lightrag import LightRAG
    from lightrag.kg.shared_storage import initialize_pipeline_status
    from lightrag.utils import EmbeddingFunc

    from app.services.retrieval import shared_vdb

    workspace = workspace_name(account_id, index)
    _apply_mongo_env()
    shared_vdb.register()

    # MONGODB_WORKSPACE is deliberately NOT set, and must not be.
    #
    # It used to be, and it was a cross-account data race. Every Mongo storage
    # reads that variable in its constructor and lets it OVERRIDE the workspace
    # passed here - so with the ingest worker on one thread and FastAPI's
    # threadpool on others (every widget handler is a sync `def`, and several
    # call `asyncio.run(...retrieve...)`), one thread could set the variable for
    # account A while another was between its own write and storage
    # construction. The second handle would then be built against A's workspace
    # while believing it was B's: A's graph updated with B's data, or B's
    # answers drawn from A's corpus.
    #
    # The variable is redundant - `workspace=` below is authoritative - so the
    # fix is simply not to set it, and to refuse to run if something else has.
    if (os.environ.get("MONGODB_WORKSPACE") or "").strip():
        raise RetrievalConfigError(
            "MONGODB_WORKSPACE is set in the environment. It overrides the "
            "per-handle workspace inside LightRAG's storage constructors, which "
            "would let one account's handle be built against another's "
            "workspace. Unset it.")

    rag = LightRAG(
        working_dir=_working_dir(),
        workspace=workspace,
        kv_storage="MongoKVStorage",
        doc_status_storage="MongoDocStatusStorage",
        # Per-workspace, exactly as before: physical separation, and it costs no
        # Atlas index capacity. The subclass only declines to create the Atlas
        # Search index the base would add, because the cluster's index cap
        # counts search and vector indexes together and that capacity is
        # reserved for the three shared vector indexes.
        graph_storage="HpMongoGraphStorage",
        # Three shared collections for every account, partitioned by workspace
        # with an Atlas pre-filter. This is what makes account #2 possible: the
        # index cost is now constant rather than three per account per index.
        vector_storage="HpSharedVectorStorage",
        # Both sides of the merge belong here. The storage classes above came
        # with the shared-vector migration; the model split below came with
        # Strategy Chat, where a query handle answers on `query_model()` while a
        # build still extracts on `retrieval_model()`. They are independent
        # choices - which collections the vectors live in, and which model reads
        # them - so taking either alone would have silently dropped a feature.
        llm_model_func=_query_llm_model_func if for_query else _llm_model_func,
        llm_model_name=query_model() if for_query else retrieval_model(),
        llm_model_max_async=LLM_MAX_ASYNC,
        embedding_func=EmbeddingFunc(
            embedding_dim=settings.OPENAI_EMBEDDING_DIM,
            func=_embedding_func,
        ),
        embedding_batch_num=EMBEDDING_BATCH_NUM,
        embedding_func_max_async=EMBEDDING_MAX_ASYNC,
        # Both caches live in KV storage, and that storage is prefixed by
        # workspace - so the cache is PER INDEX, not shared between them. A new
        # index therefore starts with an empty cache and extracts everything
        # itself, which is why each index's graph is uniformly built by whatever
        # model was configured at the time.
        #
        # Within one index the cache is keyed on the prompt text alone; it
        # records no model. Changing the model does not invalidate it, so a
        # rebuild replays the previous model's extractions unless the cache is
        # cleared first. Worth knowing before assuming a rebuild re-extracts.
        enable_llm_cache=True,
        enable_llm_cache_for_entity_extract=True,
    )
    await rag.initialize_storages()
    await initialize_pipeline_status()
    logger.info("retrieval: opened workspace %s", workspace)
    return rag


def _working_dir() -> str:
    """Local scratch. Holds no index state when Mongo backends are in use, but
    LightRAG still wants a path it can write to."""
    path = os.path.join(os.getcwd(), "rag_storage")
    os.makedirs(path, exist_ok=True)
    return path


# ---------------------------------------------------------------------------
# A warm handle for querying
# ---------------------------------------------------------------------------
#
# Opening a LightRAG handle costs 8.2 seconds, measured: it connects, lists
# collections thirteen times, checks and creates indexes, and initialises every
# storage backend. Doing that per question made it more than half the wait -
# more than the vector search and the graph reads put together.
#
# It cannot simply be cached, because LightRAG's Mongo backend is an
# `AsyncMongoClient`, and that binds to the event loop it was created on:
#
#     Cannot use AsyncMongoClient in different event loop.
#
# `asyncio.run()` creates a fresh loop per call, so a handle built on one call's
# loop is dead by the next. The fix is therefore not just a cache - it is a
# cache plus a loop that outlives the request. One background thread owns a
# permanent event loop, every handle is created on it, and queries are submitted
# to it from whichever thread FastAPI happens to use.
#
# Ingest deliberately does NOT use this. A build mutates storage, runs for the
# better part of an hour and then finalises; it keeps its own short-lived handle
# so a failed build can never leave a poisoned one behind for queries.

_query_loop = None
_query_thread = None
_query_handles = {}
_query_lock = threading.Lock()


def _ensure_query_loop():
    """The long-lived loop that owns every cached handle."""
    global _query_loop, _query_thread
    with _query_lock:
        if _query_loop is not None and _query_loop.is_running():
            return _query_loop
        loop = asyncio.new_event_loop()

        def run():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=run, name="retrieval-query-loop",
                                  daemon=True)
        thread.start()
        _query_loop, _query_thread = loop, thread
        logger.info("retrieval: started the query event loop")
        return loop


def run_on_query_loop(coro, timeout: float = 180.0):
    """Await a coroutine on the shared query loop, from any thread."""
    loop = _ensure_query_loop()
    return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)


async def query_handle(account_id: str, index: str):
    """A warm LightRAG handle for one workspace, created once per process.

    A coroutine, not a blocking call, and that distinction is load-bearing. It is
    awaited from inside `retrieve`, which is itself already running on the query
    loop - so a version that submitted work to that loop and blocked on the
    result deadlocked instantly, waiting for a loop that was waiting for it.

    The handle it returns is bound to whichever loop awaits this, which is the
    query loop by construction, because that is the only place `retrieve` runs.
    """
    workspace = workspace_name(account_id, index)
    handle = _query_handles.get(workspace)
    if handle is not None:
        return handle

    handle = await build_rag(account_id, index, for_query=True)
    # No lock needed around this: every creation happens on the single query
    # loop, so there is no concurrent writer to race with.
    _query_handles[workspace] = handle
    return handle


def forget_query_handle(workspace: str):
    """Drop the cached handle for a workspace.

    Called whenever a workspace is dropped or rebuilt. A handle kept across a
    rebuild would answer from storage that no longer exists, which reads as "no
    such fact" rather than as an error.
    """
    with _query_lock:
        handle = _query_handles.pop(workspace, None)
    if handle is None:
        return
    try:
        run_on_query_loop(handle.finalize_storages(), timeout=30)
    except Exception:
        logger.warning("retrieval: could not finalise the cached handle for %s",
                       workspace)
    logger.info("retrieval: released the cached query handle for %s", workspace)


def drop_workspace(workspace: str) -> dict:
    """Erase one workspace: its own collections, and its rows in the shared ones.

    Both halves are required, and the second is the one that is easy to forget.
    A workspace's KV, graph and doc-status collections carry its name as a
    prefix and are dropped outright. Its VECTORS, however, live in the three
    shared collections alongside every other account's - so they have to be
    deleted by partition. Dropping only the prefixed collections would leave a
    full set of orphaned vectors behind, and the next build would then retrieve
    chunks whose graph and text no longer exist.

    Shared collections are never themselves dropped: they hold every account's
    data, and their indexes take minutes to rebuild during which no account can
    be queried.

    Search indexes on the prefixed collections are dropped explicitly before the
    collections, because dropping a collection releases its indexes eventually
    but not synchronously - and the cluster's cap counts search and vector
    indexes together, so a lingering one can starve the shared vector indexes.
    """
    from app.database.mongodb import get_db
    from app.services.retrieval.shared_vdb import PARTITION_FIELD, shared_collection_name

    if not workspace or not WORKSPACE_RE.match(workspace):
        raise RetrievalConfigError("refusing to drop %r - not a workspace name"
                                   % workspace)
    forget_query_handle(workspace)

    db = get_db()
    dropped = {"workspace": workspace, "search_indexes": 0, "collections": 0,
               "vectors": 0}

    # The workspace's own collections.
    for name in [c for c in db.list_collection_names()
                 if c == workspace or c.startswith(workspace + "_")]:
        try:
            for idx in db[name].list_search_indexes():
                try:
                    db[name].drop_search_index(idx["name"])
                    dropped["search_indexes"] += 1
                except Exception:
                    logger.warning("retrieval: could not drop search index %s on %s",
                                   idx.get("name"), name)
        except Exception:
            pass
        db[name].drop()
        dropped["collections"] += 1

    # Its rows in the shared vector collections.
    for namespace in ("entities", "relationships", "chunks"):
        collection = shared_collection_name(namespace)
        try:
            result = db[collection].delete_many({PARTITION_FIELD: workspace})
            dropped["vectors"] += result.deleted_count
        except Exception:
            # Left behind, a stale partition would answer queries for a
            # workspace whose graph is gone. Loud, not swallowed.
            logger.exception(
                "retrieval: could not clear partition %s from %s - stale vectors "
                "may remain and must be removed before rebuilding",
                workspace, collection)
            raise

    logger.info("retrieval: dropped workspace %s (%d collections, %d search "
                "indexes, %d shared vectors)", workspace, dropped["collections"],
                dropped["search_indexes"], dropped["vectors"])
    return dropped
