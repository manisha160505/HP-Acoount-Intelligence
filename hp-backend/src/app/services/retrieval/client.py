"""LightRAG wiring for the retrieval layer.

One place decides how a LightRAG handle is built, so the rest of the codebase
never imports the library directly and never learns its constructor.

Three things here are load-bearing and easy to get wrong:

  * **The settings are the application's.** The provider, key, endpoint and
    models are the resolved `settings.llm_*` / `chat_model` / `retrieval_model`
    / `embedding_*` values every other feature uses (Gemini by default, Azure
    OpenAI with LLM_PROVIDER=openai), so the two cannot drift.

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
import collections
import logging
import os
import re
import shutil
import threading
import time

from app.config.settings import backend_path, settings
from app.observability.logging import quieten_noisy_loggers

logger = logging.getLogger(__name__)

WORKSPACE_RE = re.compile(r"^[A-Za-z0-9_]+$")

# Kept modest: these bound how much of the LLM budget one ingest can spend.
# The extraction calls of one index build run this many at a time - the main
# lever on how long a build takes (a Strategy Chat index is several hundred
# calls, one after another in pairs at 2). Raising it finishes sooner but
# spends the provider's per-minute quota faster; on a quota 429 the engine
# pauses the queue rather than failing. Set RAG_LLM_MAX_ASYNC to change it.
LLM_MAX_ASYNC = max(1, int(os.getenv("RAG_LLM_MAX_ASYNC", "2")))
# LightRAG re-asks the model once per chunk for entities it missed ("gleaning")
# - up to twice the extraction calls for a small gain in recall. 1 is
# LightRAG's default; RAG_EXTRACT_GLEANING=0 skips the second pass.
EXTRACT_GLEANING = max(0, int(os.getenv("RAG_EXTRACT_GLEANING", "1")))
# Whether an insert extracts entities and relationships at all.
#
# Off, because the only enabled index does not read the graph it was paying
# for. The Executive Dashboard answers in `naive` mode and `priorities.py`
# consumes `RetrievalResult.context` - the chunk text - and nothing else; the
# entity and relationship text `mix` assembles never reached it. Extraction is
# the dominant cost of a build (one model call per chunk, doubled by gleaning)
# and the main thing a wave of accounts spends its quota on.
#
# RAG_BUILD_GRAPH=true puts it back, for an index whose `default_mode` is a
# graph mode. Both halves have to move together - see
# `test_retrieval_graph_off.py`, which fails if one does and the other does not.
BUILD_GRAPH = (os.getenv("RAG_BUILD_GRAPH", "false").strip().lower()
               in ("1", "true", "yes", "on"))
# LightRAG's `PROCESS_OPTION_SKIP_KG`, written out rather than imported from
# `lightrag.constants`: this module is imported at startup, and a library that
# has renamed the constant should fail a test rather than fail the import.
# `test_retrieval_graph_off.py` checks it against the installed package.
SKIP_GRAPH_OPTION = "!"
EMBEDDING_MAX_ASYNC = 8
# Vertex express mode rate-limits far lower than Azure did: eight concurrent
# batches drew 429s on the first production build (28 Sep).
VERTEX_EMBEDDING_MAX_ASYNC = 2
VERTEX_EMBEDDING_MAX_ASYNC_CAP = 16
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

    api_key = settings.llm_api_key
    if not api_key:
        raise RetrievalConfigError(
            "%s is not set - the retrieval layer cannot embed or extract"
            % settings.llm_api_key_name)
    return OpenAI(**settings.llm_client_kwargs)


def retrieval_model() -> str:
    """The model the retrieval layer runs on.

    Falls back to the application-wide model, so setting the provider's
    `*_RETRIEVAL_MODEL` moves ONLY the RAG layer - extraction and answer
    synthesis - onto a different deployment while the other features stay where
    they are.
    """
    return settings.retrieval_model


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
        from app.core.llm import create_completion
        return create_completion(client, model=model, messages=messages, **extra)

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


def _vertex_embed(texts: list) -> list:
    """Embeddings from Vertex AI's native predict method.

    Vertex's OpenAI-compatible endpoint serves chat to an express-mode API key
    but refuses it on /embeddings ("API keys are not supported by this API"),
    while `publishers/google/models/<model>:predict` accepts it. The output
    dimension is pinned so it always matches settings.embedding_dim."""
    if not settings.llm_api_key:
        raise RetrievalConfigError("%s is not set - the retrieval layer cannot embed"
                                   % settings.llm_api_key_name)
    vectors = []
    for start in range(0, len(texts), EMBEDDING_BATCH_NUM):
        batch = texts[start:start + EMBEDDING_BATCH_NUM]
        response = _vertex_post(
            {"instances": [{"content": t} for t in batch],
             "parameters": {"outputDimensionality": settings.embedding_dim}})
        vectors.extend(p["embeddings"]["values"] for p in response.json()["predictions"])
    return vectors


# Waits inside ONE embedding request before sending it again, when the
# provider answers 429 or 5xx for a moment (not a retry of a failed build).
VERTEX_RETRY_WAITS = (2, 5, 10, 20, 30)
# What LightRAG allows one embedding call before killing it: it cuts the call
# off at twice this (`priority_limit_async_func_call`). Its default of 30 s
# gave 60 s, less than the 67 s of waits above, so a request that hit Vertex's
# per-minute embedding limit was killed just before its last attempt - which is
# the one that lands once the minute has passed. One killed call fails the whole
# index build (Advantest, 29 Sep: document 12 of 14 every time, because the
# first 11 used up the minute). 120 gives 240 s: all the waits plus the attempts
# themselves. test_retrieval_embedding_timeout.py keeps it above the waits.
EMBEDDING_TIMEOUT = 120


def _vertex_embed_url(location: str) -> str:
    host = ("aiplatform.googleapis.com" if location == "global"
            else "%s-aiplatform.googleapis.com" % location)
    return ("https://%s/v1/publishers/google/models/%s:predict"
            % (host, settings.embedding_model))


_location_lock = threading.Lock()
_location_turn = 0


def _locations_in_turn() -> list:
    """Every embedding region, starting one further along on each call, so
    concurrent batches land in different regions instead of all on the first."""
    global _location_turn
    locations = settings.vertex_embedding_locations
    with _location_lock:
        start = _location_turn % len(locations)
        _location_turn += 1
    return locations[start:] + locations[:start]


def _vertex_post(body: dict):
    """POST with the key in a header - never ?key=, which httpx puts in every
    error message and so in the logs - with the short waits above.

    Vertex's embedding limit is per region: a 429 moves the request straight
    on to the next region, and only when every region has answered 429 does it
    wait. With one region this is exactly the old behaviour."""
    import httpx

    for wait in (*VERTEX_RETRY_WAITS, None):
        for location in _locations_in_turn():
            response = httpx.post(_vertex_embed_url(location),
                                  headers={"x-goog-api-key": settings.llm_api_key},
                                  json=body, timeout=120)
            if response.status_code != 429:
                break
        if not (response.status_code == 429 or response.status_code >= 500):
            break
        if wait is None:
            if response.status_code == 429:
                from app.services.regen import context as run_context
                run_context.note_quota_exhausted()
            break
        logger.info("retrieval: embeddings answered %d (%d region(s) tried), waiting "
                    "%ds before sending it again", response.status_code,
                    len(settings.vertex_embedding_locations), wait)
        time.sleep(wait)
    response.raise_for_status()
    return response


async def _embedding_func(texts):
    import numpy as np

    from app.services.regen import context as run_context
    run_context.note_embedding(len(texts))
    if settings.llm_provider == "vertex":
        return np.array(await asyncio.to_thread(_vertex_embed, list(texts)))

    client = _openai_client()
    response = await asyncio.to_thread(
        client.embeddings.create,
        model=settings.embedding_model,
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
    return settings.chat_model


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

    from app.services.retrieval import multiloop, shared_vdb

    workspace = workspace_name(account_id, index)
    _apply_mongo_env()
    shared_vdb.register()
    # Before the first LightRAG is constructed: this process drives LightRAG
    # from the query loop AND the worker's per-job loops, and the library's
    # Mongo client and shared locks are single-loop objects until patched.
    multiloop.install()

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
        # "atlas": three shared collections for every account, partitioned by
        # workspace with an Atlas pre-filter - what makes account #2 possible
        # under the cluster's index cap. "nano": per-workspace files, for a
        # MongoDB without $vectorSearch. See `_vector_storage_config`.
        **_vector_storage_config(),
        # Both sides of the merge belong here. The storage classes above came
        # with the shared-vector migration; the model split below came with
        # Strategy Chat, where a query handle answers on `query_model()` while a
        # build still extracts on `retrieval_model()`. They are independent
        # choices - which collections the vectors live in, and which model reads
        # them - so taking either alone would have silently dropped a feature.
        llm_model_func=_query_llm_model_func if for_query else _llm_model_func,
        llm_model_name=query_model() if for_query else retrieval_model(),
        llm_model_max_async=LLM_MAX_ASYNC,
        entity_extract_max_gleaning=EXTRACT_GLEANING,
        embedding_func=EmbeddingFunc(
            embedding_dim=settings.embedding_dim,
            func=_embedding_func,
        ),
        embedding_batch_num=EMBEDDING_BATCH_NUM,
        # Two concurrent batches per region (each has its own limit), capped:
        # a long region list should not open dozens of connections at once.
        embedding_func_max_async=(min(VERTEX_EMBEDDING_MAX_ASYNC
                                      * len(settings.vertex_embedding_locations),
                                      VERTEX_EMBEDDING_MAX_ASYNC_CAP)
                                  if settings.llm_provider == "vertex"
                                  else EMBEDDING_MAX_ASYNC),
        # Long enough for one request to sit out its own 429 waits. See
        # EMBEDDING_TIMEOUT.
        default_embedding_timeout=EMBEDDING_TIMEOUT,
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
    # LightRAG installs its own handler and level as the handle comes up, which
    # undoes what `configure_logging` set at startup. Put it back.
    quieten_noisy_loggers()
    logger.info("retrieval: opened workspace %s", workspace)
    return rag


async def insert_document(rag, text: str, doc_id: str, file_path: str) -> None:
    """Index one document, with or without building the graph from it.

    This is `rag.ainsert(text, ids=[doc_id], file_paths=[file_path])` with one
    thing added, and it is here rather than in `ingest.py` for the reason the
    module docstring gives: one place knows the library.

    **Why not `ainsert`.** The switch that skips entity extraction is a
    per-DOCUMENT option, not a constructor flag - 1.5.7 has no
    `skip_kg`/`enable_graph` field on `LightRAG` at all. It is the character
    `"!"` in `process_options` (`lightrag/constants.py`,
    `PROCESS_OPTION_SKIP_KG`), read in `pipeline.process_single_document`:

        # Stage 2: entity/relation extraction (after text_chunks are saved).
        # When the user opted out via process_options '!', skip extraction
        # entirely; chunks remain in the vector store so naive / mix
        # retrieval still works.

    `ainsert` does not take `process_options` and its own docstring says to
    call the two pipeline methods directly when you need it. It is a wrapper
    around exactly those two, so this reproduces it rather than reimplementing
    anything.

    **Chunking must not change.** `ainsert` resolves a fixed-token (F) chunk
    snapshot before enqueueing, and so does this. A different chunker would
    re-chunk every document and invalidate nothing visibly - the stored
    fingerprints hash the corpus text, not the chunks - so it would simply
    change what is retrieved, quietly.
    """
    from lightrag.parser.routing import resolve_chunk_options

    await rag.apipeline_enqueue_documents(
        text,
        [doc_id],
        [file_path],
        chunk_options=resolve_chunk_options(rag.addon_params),
        process_options=None if BUILD_GRAPH else SKIP_GRAPH_OPTION,
    )
    await rag.apipeline_process_enqueue_documents()


VECTOR_BACKENDS = ("atlas", "nano")


def vector_backend() -> str:
    backend = (settings.VECTOR_STORAGE or "").strip().lower()
    if backend not in VECTOR_BACKENDS:
        raise RetrievalConfigError("VECTOR_STORAGE must be one of %s, not %r"
                                   % (", ".join(VECTOR_BACKENDS), settings.VECTOR_STORAGE))
    return backend


def _vector_storage_config() -> dict:
    """The LightRAG constructor arguments that pick the vector store.

    The threshold is the part that must not drift. Atlas scores a cosine index
    as `(1 + cosine) / 2`, and LightRAG compares its threshold (default 0.2)
    against that score - so on Atlas the cut-off has always been cosine >= -0.6,
    which in practice keeps every top-k result. NanoVectorDB compares the same
    threshold against raw cosine, where 0.2 would drop results Atlas returns.
    Converting it keeps the retrieved set the same after the switch.
    """
    if vector_backend() == "atlas":
        return {"vector_storage": "HpSharedVectorStorage"}

    from lightrag.constants import DEFAULT_COSINE_THRESHOLD
    from lightrag.utils import get_env_value

    atlas_score = get_env_value("COSINE_THRESHOLD", DEFAULT_COSINE_THRESHOLD, float)
    return {"vector_storage": "NanoVectorDBStorage",
            "cosine_better_than_threshold": 2 * atlas_score - 1}


def rag_storage_dir() -> str:
    """LightRAG's working directory: with "nano", the only copy of every vector."""
    return backend_path(settings.RAG_STORAGE_DIR)


def workspace_vector_dir(workspace: str) -> str:
    """Where NanoVectorDB keeps one workspace's `vdb_*.json` files."""
    return os.path.join(rag_storage_dir(), workspace)


def _working_dir() -> str:
    path = rag_storage_dir()
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
# so a failed build can never leave a poisoned one behind for queries. That
# handle is genuinely its own only because `multiloop.py` gives each loop its
# own Mongo client - LightRAG's default is one client per process, which the
# cached handles here had bound to this loop, and the worker's loop then failed
# on it with "Cannot use AsyncMongoClient in different event loop".

#
# The cache is bounded (QUERY_HANDLE_CACHE_SIZE), least recently used first
# out. With "nano" a handle holds its workspace's vectors in memory, so one
# handle per account ever queried would grow without limit. An evicted handle
# that a question is still using is closed when that question releases it,
# not under it.

_query_loop = None
_query_thread = None
_query_handles = collections.OrderedDict()   # workspace -> handle, oldest first
_handle_users = {}                           # id(handle) -> questions using it
_retiring = {}                               # id(handle) -> handle evicted while in use
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


def submit_to_query_loop(coro):
    """Schedule a coroutine on the query loop; returns a `concurrent.futures.Future`.

    The caller decides how to wait: block on it from a plain thread, or
    `asyncio.wrap_future` it from a coroutine running on some other loop.
    """
    return asyncio.run_coroutine_threadsafe(coro, _ensure_query_loop())


def run_on_query_loop(coro, timeout: float = 180.0):
    """Await a coroutine on the shared query loop, from any thread."""
    return submit_to_query_loop(coro).result(timeout)


def on_query_loop() -> bool:
    """True when the caller is running on the query loop itself."""
    try:
        return asyncio.get_running_loop() is _query_loop
    except RuntimeError:
        return False


async def query_handle(account_id: str, index: str):
    """A warm LightRAG handle for one workspace, created once per process.

    A coroutine, not a blocking call, and that distinction is load-bearing. It is
    awaited from inside `retrieve`, which is itself already running on the query
    loop - so a version that submitted work to that loop and blocked on the
    result deadlocked instantly, waiting for a loop that was waiting for it.

    The handle it returns is bound to whichever loop awaits this, which is the
    query loop by construction, because that is the only place `retrieve` runs.

    Every call must be paired with `release_query_handle` once the question is
    answered; that pairing is what lets eviction avoid closing a handle mid-use.
    """
    workspace = workspace_name(account_id, index)
    handle = _query_handles.get(workspace)
    if handle is None:
        built = await build_rag(account_id, index, for_query=True)
        # Two questions can both miss and both build while the first awaits.
        # Keep whichever landed first; the loser was never shared.
        handle = _query_handles.get(workspace)
        if handle is None:
            handle = _query_handles[workspace] = built
        else:
            await _finalise_quietly(built, workspace)
    _query_handles.move_to_end(workspace)
    _handle_users[id(handle)] = _handle_users.get(id(handle), 0) + 1
    await _evict_query_handles()
    return handle


async def release_query_handle(handle):
    """The question using `handle` is done. Runs on the query loop."""
    users = _handle_users.get(id(handle))
    if users is None:
        return
    if users > 1:
        _handle_users[id(handle)] = users - 1
        return
    del _handle_users[id(handle)]
    retired = _retiring.pop(id(handle), None)
    if retired is not None:
        await _finalise_quietly(retired, "an evicted workspace")


async def _evict_query_handles():
    """Close the least recently used handles beyond the cache size."""
    limit = max(1, int(settings.QUERY_HANDLE_CACHE_SIZE))
    while len(_query_handles) > limit:
        workspace, handle = _query_handles.popitem(last=False)
        if _handle_users.get(id(handle)):
            _retiring[id(handle)] = handle
        else:
            await _finalise_quietly(handle, workspace)
        logger.info("retrieval: evicted the cached query handle for %s", workspace)


async def _finalise_quietly(handle, workspace):
    try:
        await handle.finalize_storages()
    except Exception:
        logger.warning("retrieval: could not finalise the query handle for %s",
                       workspace)


def forget_query_handle(workspace: str):
    """Drop the cached handle for a workspace.

    Called whenever a workspace is dropped or rebuilt. A handle kept across a
    rebuild would answer from storage that no longer exists, which reads as "no
    such fact" rather than as an error.
    """
    async def _forget():
        # On the query loop, like every other change to the handle cache, and
        # never under a question still using the handle - that one is retired
        # and finalised when its last user lets go, as eviction already does.
        with _query_lock:
            handle = _query_handles.pop(workspace, None)
        if handle is None:
            return False
        if _handle_users.get(id(handle)):
            _retiring[id(handle)] = handle
        else:
            await _finalise_quietly(handle, workspace)
        return True

    try:
        released = run_on_query_loop(_forget(), timeout=30)
    except Exception:
        logger.warning("retrieval: could not finalise the cached handle for %s",
                       workspace)
        return
    if released:
        logger.info("retrieval: released the cached query handle for %s", workspace)


def drop_workspace(workspace: str, keep_llm_cache: bool = False) -> dict:
    """Erase one workspace: its own collections, its rows in the shared ones,
    and its NanoVectorDB files.

    `keep_llm_cache` spares `<workspace>_llm_response_cache`: LightRAG's record
    of every extraction and summary call, keyed by the prompt. A full rebuild
    with the same extraction model then re-reads identical chunks from it at no
    model cost - an embedding change re-embeds, it does not need the graph
    extracted again. Retiring an index drops it with everything else.

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
                 if (c == workspace or c.startswith(workspace + "_"))
                 and not (keep_llm_cache and c == workspace + "_llm_response_cache")]:
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

    # Its NanoVectorDB files. Cleared whichever backend is configured, like the
    # shared rows above: a leftover from the other backend would resurface the
    # day someone switches back.
    vector_dir = workspace_vector_dir(workspace)
    dropped["vector_files"] = 0
    if os.path.isdir(vector_dir):
        dropped["vector_files"] = len(os.listdir(vector_dir))
        # Not ignore_errors: a half-removed directory would answer queries for
        # a workspace whose graph is gone, exactly like a stale partition.
        shutil.rmtree(vector_dir)

    logger.info("retrieval: dropped workspace %s (%d collections, %d search "
                "indexes, %d shared vectors, %d vector files)", workspace,
                dropped["collections"], dropped["search_indexes"],
                dropped["vectors"], dropped["vector_files"])
    return dropped
