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


async def _llm_model_func(prompt, system_prompt=None, history_messages=None, **kwargs):
    """What LightRAG calls for entity extraction and answer generation.

    The SDK call is blocking, so it runs in a thread rather than stalling the
    event loop LightRAG drives its pipeline with - same shape as the supplied
    reference rig.
    """
    client = _openai_client()
    model = retrieval_model()
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


async def build_rag(account_id: str, index: str):
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
        llm_model_func=_llm_model_func,
        llm_model_name=retrieval_model(),
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
