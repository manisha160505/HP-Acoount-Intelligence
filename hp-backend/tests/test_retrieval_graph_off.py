"""Index builds no longer extract a knowledge graph, and the dashboard reads
chunks.

The Executive Dashboard asked LightRAG for `mix` and consumed
`RetrievalResult.context` - the chunk text. It never touched `answer` or
`graph_context`, and on 1.5.7 `raw["context"]` comes back empty, so the entity
and relationship text `mix` assembles was retrieved and dropped. The graph was
therefore extracted at build time (a model call per chunk, doubled by gleaning:
the dominant cost of a build) and assembled at query time, for nothing.

So: extraction off at insert, `naive` at query. Four things are pinned here,
because each of them fails silently rather than loudly.

**The library option still exists.** Skipping extraction is not a constructor
flag in 1.5.7 - there is none - it is the per-document character `"!"` in
`process_options`. A LightRAG upgrade that renames or drops it would make
`insert_document` pass a meaningless string and quietly start building graphs
again, at full cost, with nothing reading them.

**The two halves cannot drift.** Graph building off and a graph query mode is
an index that answers from an empty graph. `mix` survives that by design
(`operate.py` lets `mix` alone continue when the graph returns nothing) and
`local`/`global`/`hybrid` return nothing at all - either way the failure looks
like an account with no data rather than a misconfiguration.

**Chunking is unchanged.** `insert_document` replaces `ainsert`, which resolves
a fixed-token chunk snapshot of its own. A different chunker would re-chunk
every document and invalidate nothing visible - the stored fingerprints hash the
corpus text, not the chunks - so retrieval would simply change.

**`top_k` means what the caller wrote.** LightRAG sizes a chunk search as
`chunk_top_k or top_k`, and `chunk_top_k` is not None: it defaults to 20. In
naive mode the chunk search IS the retrieval, so `top_k=60` from `priorities.py`
silently becoming 20 would cut the dashboard's evidence by two thirds.

Run: python -m pytest tests/test_retrieval_graph_off.py -v
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import client, registry

# What LightRAG's own `addon_params` looks like before anything is configured;
# `resolve_chunk_options` falls back to its defaults for an empty mapping.
ADDON_PARAMS = {}


class FakeRag:
    """Records what `insert_document` asks the library to do."""

    addon_params = ADDON_PARAMS

    def __init__(self):
        self.enqueued = []
        self.processed = 0

    async def apipeline_enqueue_documents(self, text, ids=None, file_paths=None,
                                          track_id=None, **kwargs):
        self.enqueued.append({"text": text, "ids": ids,
                              "file_paths": file_paths, **kwargs})
        return "track-1"

    async def apipeline_process_enqueue_documents(self):
        self.processed += 1


def _insert(monkeypatch, build_graph: bool) -> FakeRag:
    monkeypatch.setattr(client, "BUILD_GRAPH", build_graph)
    rag = FakeRag()
    asyncio.run(client.insert_document(
        rag, "PT Example reported net revenue of IDR 323,392 billion.",
        "doc-1", "firmographics.csv"))
    return rag


# ---------------------------------------------------------------------------
# The library option
# ---------------------------------------------------------------------------

def test_the_skip_graph_option_is_still_what_the_library_calls_it():
    """`client.SKIP_GRAPH_OPTION` is written out, not imported - so check it.

    Importing `lightrag.constants` at startup to get one character would make
    a library that renamed it fail the import of the whole app. This fails a
    test instead, which is the loud half of the trade.
    """
    from lightrag.constants import PROCESS_OPTION_SKIP_KG

    assert client.SKIP_GRAPH_OPTION == PROCESS_OPTION_SKIP_KG


def test_the_library_reads_that_option_as_skip_the_graph():
    """Not just that the constant exists - that it still decodes to skip_kg."""
    from lightrag.parser.routing import parse_process_options

    assert parse_process_options(client.SKIP_GRAPH_OPTION).skip_kg is True
    assert parse_process_options("").skip_kg is False


# ---------------------------------------------------------------------------
# What insert_document sends
# ---------------------------------------------------------------------------

def test_an_insert_skips_entity_extraction_by_default(monkeypatch):
    rag = _insert(monkeypatch, build_graph=False)
    assert len(rag.enqueued) == 1
    assert rag.enqueued[0]["process_options"] == "!"
    # Enqueueing alone indexes nothing; the second call is what processes it.
    assert rag.processed == 1


def test_the_switch_puts_graph_building_back(monkeypatch):
    """RAG_BUILD_GRAPH=true has to be a real way back, not a dead knob."""
    rag = _insert(monkeypatch, build_graph=True)
    assert rag.enqueued[0]["process_options"] is None
    assert rag.processed == 1


def test_the_document_keeps_its_id_and_file_path(monkeypatch):
    """The id is how a changed document is replaced; the path is its citation."""
    rag = _insert(monkeypatch, build_graph=False)
    assert rag.enqueued[0]["ids"] == ["doc-1"]
    assert rag.enqueued[0]["file_paths"] == ["firmographics.csv"]


def test_chunking_is_the_same_snapshot_ainsert_would_have_resolved(monkeypatch):
    """Replacing `ainsert` must not change how a document is chunked.

    `ainsert` resolves this snapshot from `addon_params` before enqueueing and
    so does `insert_document`. If they differed, every document would re-chunk
    on the next build with nothing to show it: the stored fingerprints hash the
    corpus text, not the chunks.
    """
    from lightrag.parser.routing import resolve_chunk_options

    rag = _insert(monkeypatch, build_graph=False)
    assert rag.enqueued[0]["chunk_options"] == resolve_chunk_options(ADDON_PARAMS)


# ---------------------------------------------------------------------------
# The query mode, and the pairing
# ---------------------------------------------------------------------------

def test_the_executive_dashboard_answers_in_naive_mode():
    assert registry.spec("executive_dashboard")["default_mode"] == "naive"


def test_no_enabled_index_asks_for_a_graph_mode_while_the_graph_is_off():
    """The pairing, stated as a test rather than as a comment.

    With `RAG_BUILD_GRAPH` off by default, a freshly built index holds chunks
    and no entities. An index whose `default_mode` walks the graph would answer
    from an empty one and read as an account with no data. So: turn graph
    building back on, or leave every enabled index on naive.
    """
    if client.BUILD_GRAPH:
        return
    graph_modes = {"mix", "hybrid", "local", "global"}
    asking = [index for index, entry in registry.INDEX_REGISTRY.items()
              if entry.get("enabled")
              and (entry.get("default_mode") or "mix") in graph_modes]
    assert asking == [], (
        "%s ask for a graph mode, but inserts no longer build one - set "
        "RAG_BUILD_GRAPH=true or move them to naive" % ", ".join(asking))


def test_a_chunk_search_is_sized_by_the_top_k_the_caller_asked_for():
    """`top_k` alone does not size it - `chunk_top_k` defaults to 20, not None.

    Pinned against the library's own default rather than against the literal,
    so the test says why the argument is passed at all.
    """
    from lightrag import QueryParam
    from lightrag.constants import DEFAULT_CHUNK_TOP_K

    assert QueryParam(mode="naive").chunk_top_k == DEFAULT_CHUNK_TOP_K
    assert DEFAULT_CHUNK_TOP_K != 60
    param = QueryParam(mode="naive", top_k=60, chunk_top_k=60)
    assert (param.chunk_top_k or param.top_k) == 60
