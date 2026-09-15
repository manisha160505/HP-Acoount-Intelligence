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
import threading
import os
import re

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
    """The storage namespace for one index of one account. One, not one per build.

    An earlier design numbered the workspace per build so a new one could be
    built alongside the live one and swapped in atomically. That does not fit
    the cluster: one workspace costs three Atlas vector search indexes
    (`_chunks`, `_entities`, `_relationships`) and the free tier's hard cap is
    three, so two workspaces cannot coexist - the second build fails with
    "The maximum number of FTS indexes has been reached for this instance size."

    So the workspace is stable, and safety comes from the update strategy
    instead: a normal change touches only the documents that changed, in place,
    which never needs a second workspace. `version` survives as metadata in
    `retrieval_index_state`, not as part of the name.
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
    from lightrag.utils import EmbeddingFunc
    from lightrag.kg.shared_storage import initialize_pipeline_status

    workspace = workspace_name(account_id, index)
    _apply_mongo_env()
    os.environ["MONGODB_WORKSPACE"] = workspace

    rag = LightRAG(
        working_dir=_working_dir(),
        workspace=workspace,
        kv_storage="MongoKVStorage",
        doc_status_storage="MongoDocStatusStorage",
        graph_storage="MongoGraphStorage",
        vector_storage="MongoVectorDBStorage",
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
    """Delete every collection and search index belonging to one workspace.

    Necessary, not housekeeping. Each workspace costs three Atlas vector search
    indexes (chunks, entities, relationships) and thirteen collections, and a
    cluster has a hard cap on search indexes - so a retired workspace left in
    place permanently consumes capacity a future build needs.

    Search indexes are dropped explicitly before the collections: dropping a
    collection releases its indexes eventually, but not synchronously, and a
    build starting immediately afterwards can still hit the cap.
    """
    from app.database.mongodb import get_db

    if not workspace or not WORKSPACE_RE.match(workspace):
        raise RetrievalConfigError("refusing to drop %r - not a workspace name"
                                   % workspace)
    forget_query_handle(workspace)

    db = get_db()
    dropped = {"workspace": workspace, "search_indexes": 0, "collections": 0}

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

    logger.info("retrieval: dropped workspace %s (%d collections, %d search indexes)",
                workspace, dropped["collections"], dropped["search_indexes"])
    return dropped
