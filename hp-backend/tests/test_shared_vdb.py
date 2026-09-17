"""Isolation tests for the shared vector layer.

Every account's vectors live in three shared collections, so the only thing
keeping one account's chunks out of another's prompt is this module's scoping
and filtering. These tests exist to make a regression in that logic fail loudly
rather than silently leak.

They use a fake Mongo collection rather than a live cluster: the questions being
asked are "what `_id` did we write", "what did the pipeline contain" and "what
came back out", all of which are answerable without a server. The one thing a
fake cannot verify is whether Atlas honours the pre-filter - that needs a real
cluster, and `test_atlas_isolation.py` covers it behind an env guard.

Run: python -m pytest tests/test_shared_vdb.py -v
"""

import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import shared_vdb
from app.services.retrieval.shared_vdb import (
    PARTITION_FIELD,
    SharedVectorConfigError,
    shared_collection_name,
    shared_index_name,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length=None):
        return list(self._docs)

    # The driver's cursors are async-iterable as well as awaitable-to-list, and
    # the graph batch reads stream with `async for` rather than materialising.
    def __aiter__(self):
        self._iter = iter(list(self._docs))
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class FakeCollection:
    """Enough of an AsyncCollection to observe what the storage does."""

    def __init__(self, docs=None, search_indexes=None):
        self.docs = list(docs or [])
        self.search_indexes = list(search_indexes or [])
        self.captured_pipeline = None
        self.created_indexes = []
        self.deleted_filters = []

    async def aggregate(self, pipeline, **kwargs):
        self.captured_pipeline = pipeline
        stage = pipeline[0]["$vectorSearch"]
        wanted = (stage.get("filter") or {}).get(PARTITION_FIELD)
        # Model an Atlas pre-filter: only matching docs are candidates.
        hits = [d for d in self.docs
                if wanted is None or d.get(PARTITION_FIELD) == wanted]
        return FakeCursor([dict(d, score=0.9) for d in hits[:stage["limit"]]])

    def find(self, query, projection=None):
        def matches(doc):
            for key, value in query.items():
                if key == "$or":
                    if not any(all(doc.get(k) == v for k, v in clause.items())
                               for clause in value):
                        return False
                elif doc.get(key) != value:
                    return False
            return True

        return FakeCursor([{"_id": d["_id"]} for d in self.docs if matches(d)])

    async def delete_many(self, query):
        self.deleted_filters.append(query)
        before = len(self.docs)
        if "_id" in query and "$in" in query["_id"]:
            doomed = set(query["_id"]["$in"])
            self.docs = [d for d in self.docs if d["_id"] not in doomed]
        else:
            self.docs = [d for d in self.docs
                         if not all(d.get(k) == v for k, v in query.items())]
        return types.SimpleNamespace(deleted_count=before - len(self.docs))

    async def list_search_indexes(self):
        return FakeCursor(self.search_indexes)

    async def create_search_index(self, model):
        # `SearchIndexModel.document` is {name, type, definition: {...}} - keep
        # the real shape so the assertions below check what Atlas would receive.
        self.created_indexes.append(dict(getattr(model, "document", None) or {}))
        return "ok"


def make_storage(workspace="acct_a1_content_messaging", namespace="chunks",
                 collection=None, dim=1536):
    """A shared storage instance wired to a fake collection.

    The base constructor wants a live Mongo client, so it is bypassed and the
    attributes it would have set are supplied directly - the subclass logic
    under test reads only these.
    """
    shared_vdb.register()
    cls = shared_vdb.HpSharedVectorStorage
    storage = cls.__new__(cls)

    storage.namespace = namespace
    storage.workspace = workspace
    storage.meta_fields = {"content", "entity_name", "src_id", "tgt_id",
                           "file_path"}
    storage.embedding_func = types.SimpleNamespace(embedding_dim=dim)
    storage.cosine_better_than_threshold = 0.2
    storage._pending_vector_docs = {}
    storage._pending_vector_deletes = set()
    storage._flush_lock = asyncio.Lock()
    storage._data = collection if collection is not None else FakeCollection()
    storage.global_config = {}
    storage._max_batch_size = 32

    # Mirror what __init__ derives.
    storage.partition = workspace
    storage.final_namespace = shared_collection_name(namespace)
    storage._collection_name = storage.final_namespace
    storage._index_name = shared_index_name(namespace)
    storage.meta_fields = set(storage.meta_fields) | {PARTITION_FIELD}
    return storage


def vector_doc(workspace, doc_id, **extra):
    return {"_id": "%s:%s" % (workspace, doc_id), PARTITION_FIELD: workspace,
            "content": "text of %s" % doc_id, **extra}


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

def test_collections_and_indexes_are_shared_not_per_workspace():
    """The whole point: names carry no account, so the count stays constant."""
    assert shared_collection_name("chunks") == "shared_vdb_chunks"
    assert shared_index_name("entities") == "shared_vdb_entities_idx"

    a = make_storage(workspace="acct_a1_content_messaging")
    b = make_storage(workspace="acct_b2_content_messaging")
    assert a._collection_name == b._collection_name
    assert a._index_name == b._index_name
    assert a.partition != b.partition


# ---------------------------------------------------------------------------
# Id scoping
# ---------------------------------------------------------------------------

def test_ids_are_scoped_on_write_and_unscoped_on_read():
    storage = make_storage(workspace="acct_a1_x")
    assert storage._scope("chunk-abc") == "acct_a1_x:chunk-abc"
    assert storage._unscope("acct_a1_x:chunk-abc") == "chunk-abc"
    # An id that is not ours is returned untouched rather than mangled.
    assert storage._unscope("acct_b2_x:chunk-abc") == "acct_b2_x:chunk-abc"


def test_identical_ids_in_two_partitions_do_not_collide():
    """Chunk ids are content hashes, so shared boilerplate WILL repeat."""
    a = make_storage(workspace="acct_a1_x")
    b = make_storage(workspace="acct_b2_x")
    assert a._scope("chunk-same") != b._scope("chunk-same")


def test_upsert_stamps_the_partition_and_scopes_the_id():
    storage = make_storage()
    asyncio.run(storage.upsert({"chunk-1": {"content": "hello"}}))

    assert list(storage._pending_vector_docs) == ["%s:chunk-1" % storage.partition]
    source = storage._pending_vector_docs["%s:chunk-1" % storage.partition].source
    assert source[PARTITION_FIELD] == storage.partition
    assert source["_id"] == "%s:chunk-1" % storage.partition


def test_partition_field_survives_the_meta_fields_filter():
    """The base upsert drops any key not in meta_fields, so this must be in it."""
    storage = make_storage()
    assert PARTITION_FIELD in storage.meta_fields


# ---------------------------------------------------------------------------
# Query isolation
# ---------------------------------------------------------------------------

def test_query_sends_an_atlas_prefilter():
    collection = FakeCollection([vector_doc("acct_a1_x", "chunk-1")])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    asyncio.run(storage.query("q", top_k=5, query_embedding=[0.1] * 1536))

    stage = collection.captured_pipeline[0]["$vectorSearch"]
    assert stage["filter"] == {PARTITION_FIELD: "acct_a1_x"}
    assert stage["index"] == shared_index_name("chunks")


def test_query_never_returns_another_partitions_rows():
    """The isolation guarantee, stated as a test."""
    collection = FakeCollection([
        vector_doc("acct_a1_x", "chunk-mine"),
        vector_doc("acct_b2_x", "chunk-theirs"),
    ])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    results = asyncio.run(storage.query("q", top_k=10,
                                        query_embedding=[0.1] * 1536))

    assert [r["id"] for r in results] == ["chunk-mine"]
    assert all("theirs" not in str(r) for r in results)


def test_query_drops_foreign_rows_even_if_the_prefilter_is_ignored():
    """Defence in depth.

    If Atlas ever ignored a filter on an undeclared path, the pre-filter would
    silently stop isolating. The post-check is the backstop, so it is tested
    against a collection that deliberately ignores the filter.
    """
    class UnfilteredCollection(FakeCollection):
        async def aggregate(self, pipeline, **kwargs):
            self.captured_pipeline = pipeline
            return FakeCursor([dict(d, score=0.9) for d in self.docs])

    collection = UnfilteredCollection([
        vector_doc("acct_a1_x", "chunk-mine"),
        vector_doc("acct_b2_x", "chunk-theirs"),
    ])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    results = asyncio.run(storage.query("q", top_k=10,
                                        query_embedding=[0.1] * 1536))
    assert [r["id"] for r in results] == ["chunk-mine"]


def test_query_returns_unscoped_ids():
    """Callers match these against text_chunks KV keys, which are unscoped."""
    collection = FakeCollection([vector_doc("acct_a1_x", "chunk-1")])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    results = asyncio.run(storage.query("q", top_k=5,
                                        query_embedding=[0.1] * 1536))
    assert results[0]["id"] == "chunk-1"
    assert results[0]["_id"] == "chunk-1"
    assert PARTITION_FIELD not in results[0]


# ---------------------------------------------------------------------------
# Deletes
# ---------------------------------------------------------------------------

def test_delete_entity_relation_spares_other_partitions():
    """The base query has no partition predicate; entity names like "HP" repeat."""
    collection = FakeCollection([
        dict(vector_doc("acct_a1_x", "rel-1"), src_id="HP", tgt_id="Dell"),
        dict(vector_doc("acct_b2_x", "rel-2"), src_id="HP", tgt_id="Lenovo"),
    ])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    asyncio.run(storage.delete_entity_relation("HP"))

    remaining = [d["_id"] for d in collection.docs]
    assert remaining == ["acct_b2_x:rel-2"]


def test_drop_removes_only_this_partition_and_keeps_the_index():
    collection = FakeCollection([
        vector_doc("acct_a1_x", "chunk-1"),
        vector_doc("acct_b2_x", "chunk-2"),
    ])
    storage = make_storage(workspace="acct_a1_x", collection=collection)

    result = asyncio.run(storage.drop())

    assert result["status"] == "success"
    assert [d["_id"] for d in collection.docs] == ["acct_b2_x:chunk-2"]
    # A dropped-and-recreated shared index would take every account offline.
    assert collection.created_indexes == []


def test_delete_scopes_ids():
    storage = make_storage(workspace="acct_a1_x")
    asyncio.run(storage.delete(["chunk-1"]))
    assert storage._pending_vector_deletes == {"acct_a1_x:chunk-1"}


# ---------------------------------------------------------------------------
# Index definition — the fail-closed guard
# ---------------------------------------------------------------------------

def test_new_index_declares_the_filter_field():
    collection = FakeCollection()
    storage = make_storage(collection=collection)

    asyncio.run(storage.create_vector_index_if_not_exists())

    created = collection.created_indexes[0]
    assert created["name"] == shared_index_name("chunks")
    assert created["type"] == "vectorSearch"

    fields = created["definition"]["fields"]
    # Without this declaration the `filter` in query() has nothing to match on.
    assert {"type": "filter", "path": PARTITION_FIELD} in fields
    vector_field = next(f for f in fields if f["type"] == "vector")
    assert vector_field["numDimensions"] == 1536
    assert vector_field["path"] == "vector"


def test_existing_index_without_a_filter_field_is_refused():
    """The hole the base class would leave open.

    The base accepts any index whose name and dimension match. On a shared
    collection that means serving queries through an index that cannot filter -
    every one of them spanning all accounts. It must refuse to start.
    """
    collection = FakeCollection(search_indexes=[{
        "name": shared_index_name("chunks"),
        "latestDefinition": {"fields": [
            {"type": "vector", "path": "vector", "numDimensions": 1536}]},
    }])
    storage = make_storage(collection=collection)

    with pytest.raises(SharedVectorConfigError, match="filter field"):
        asyncio.run(storage.create_vector_index_if_not_exists())


def test_existing_index_with_a_filter_field_is_accepted():
    collection = FakeCollection(search_indexes=[{
        "name": shared_index_name("chunks"),
        "latestDefinition": {"fields": [
            {"type": "vector", "path": "vector", "numDimensions": 1536},
            {"type": "filter", "path": PARTITION_FIELD}]},
    }])
    storage = make_storage(collection=collection)

    asyncio.run(storage.create_vector_index_if_not_exists())
    assert collection.created_indexes == []


def test_dimension_mismatch_is_refused():
    collection = FakeCollection(search_indexes=[{
        "name": shared_index_name("chunks"),
        "latestDefinition": {"fields": [
            {"type": "vector", "path": "vector", "numDimensions": 768},
            {"type": "filter", "path": PARTITION_FIELD}]},
    }])
    storage = make_storage(collection=collection, dim=1536)

    with pytest.raises(SharedVectorConfigError, match="dimension"):
        asyncio.run(storage.create_vector_index_if_not_exists())


# ---------------------------------------------------------------------------
# Construction guards
# ---------------------------------------------------------------------------

def test_registration_declares_both_classes_to_lightrag():
    from lightrag.kg import STORAGE_IMPLEMENTATIONS, STORAGES

    shared_vdb.register()
    assert STORAGES["HpSharedVectorStorage"] == "app.services.retrieval.shared_vdb"
    assert STORAGES["HpMongoGraphStorage"] == "app.services.retrieval.shared_vdb"
    assert "HpSharedVectorStorage" in \
        STORAGE_IMPLEMENTATIONS["VECTOR_STORAGE"]["implementations"]
    assert "HpMongoGraphStorage" in \
        STORAGE_IMPLEMENTATIONS["GRAPH_STORAGE"]["implementations"]


def test_graph_storage_creates_no_atlas_search_index():
    """It would compete for the cap, which counts search and vector together."""
    shared_vdb.register()
    cls = shared_vdb.HpMongoGraphStorage
    storage = cls.__new__(cls)
    storage.workspace = "acct_a1_x"
    storage._collection_name = "acct_a1_x_chunk_entity_relation"
    storage.collection = FakeCollection()

    asyncio.run(storage.create_search_index_if_not_exists())
    assert storage.collection.created_indexes == []


# ---------------------------------------------------------------------------
# The batch graph reads LightRAG never implemented for Mongo
#
# `BaseGraphStorage` supplies both as sequential loops with an `await` inside,
# and Mongo does not override them, so on a remote Atlas cluster every relation
# cost its own round trip: one question spent 147 seconds on 1,659 of them.
#
# What these pin is the PYTHON mapping - which asked-for pair each returned
# document belongs to, and what an absent one does. Whether the aggregation
# itself matches `count_documents({"$or": ...})` cannot honestly be tested
# against a fake, because a fake would only be testing my model of Mongo; that
# equivalence is checked against the real graph, including a self-loop, by the
# batch-equivalence run in the verification script.
# ---------------------------------------------------------------------------

class FakeEdgeCollection:
    """Records what it was asked, and answers from a canned edge list."""

    def __init__(self, edges=None, degrees=None):
        self.edges = list(edges or [])
        self.degrees = dict(degrees or {})
        self.find_queries = []
        self.pipelines = []

    def find(self, query, projection=None):
        self.find_queries.append(query)
        clauses = query.get("$or") or []
        hits = [dict(e) for e in self.edges
                if any(all(e.get(k) == v for k, v in c.items()) for c in clauses)]
        return FakeCursor(hits)

    async def aggregate(self, pipeline, **kwargs):
        self.pipelines.append(pipeline)
        return FakeCursor([{"_id": node, "degree": n}
                           for node, n in self.degrees.items()])


def graph_storage(collection):
    shared_vdb.register()
    cls = shared_vdb.HpMongoGraphStorage
    storage = cls.__new__(cls)
    storage.workspace = "acct_x_strategy"
    storage.edge_collection = collection
    return storage


def edge_doc(lo, hi, **extra):
    return {"_id": "oid", "edge_lo": lo, "edge_hi": hi,
            "source_node_id": lo, "target_node_id": hi,
            "description": "%s-%s" % (lo, hi), **extra}


def test_get_edges_batch_asks_once_for_every_pair():
    collection = FakeEdgeCollection([edge_doc("A", "B"), edge_doc("B", "C")])
    got = asyncio.run(graph_storage(collection).get_edges_batch(
        [{"src": "A", "tgt": "B"}, {"src": "B", "tgt": "C"}]))
    assert set(got) == {("A", "B"), ("B", "C")}
    assert len(collection.find_queries) == 1, "one query, not one per pair"


def test_get_edges_batch_matches_a_reversed_pair():
    """(A,B) and (B,A) are one undirected edge, and both keys are wanted."""
    collection = FakeEdgeCollection([edge_doc("A", "B")])
    got = asyncio.run(graph_storage(collection).get_edges_batch(
        [{"src": "B", "tgt": "A"}, {"src": "A", "tgt": "B"}]))
    assert set(got) == {("A", "B"), ("B", "A")}
    assert got[("A", "B")]["description"] == got[("B", "A")]["description"]


def test_get_edges_batch_omits_a_pair_with_no_edge():
    """Absent, not None - the base leaves a missing pair out of the dict."""
    collection = FakeEdgeCollection([edge_doc("A", "B")])
    got = asyncio.run(graph_storage(collection).get_edges_batch(
        [{"src": "A", "tgt": "B"}, {"src": "X", "tgt": "Y"}]))
    assert set(got) == {("A", "B")}


def test_get_edges_batch_strips_the_mongo_id():
    """`get_edge` pops it so a fetched edge can be re-upserted."""
    collection = FakeEdgeCollection([edge_doc("A", "B")])
    got = asyncio.run(graph_storage(collection).get_edges_batch(
        [{"src": "A", "tgt": "B"}]))
    assert "_id" not in got[("A", "B")]


def test_edge_degrees_batch_sums_both_endpoints():
    collection = FakeEdgeCollection(degrees={"A": 3, "B": 5})
    got = asyncio.run(graph_storage(collection).edge_degrees_batch([("A", "B")]))
    assert got == {("A", "B"): 8}
    assert len(collection.pipelines) == 1, "one aggregation, not two per pair"


def test_edge_degrees_batch_treats_an_unknown_node_as_zero():
    """`count_documents` returns 0 for a node with no edges."""
    collection = FakeEdgeCollection(degrees={"A": 2})
    got = asyncio.run(graph_storage(collection).edge_degrees_batch(
        [("A", "MISSING"), ("MISSING", "ALSO_MISSING")]))
    assert got == {("A", "MISSING"): 2, ("MISSING", "ALSO_MISSING"): 0}


def test_edge_degrees_batch_dedupes_endpoints_before_counting():
    """The pipeline must `$setUnion` an edge's endpoints.

    `node_degree` counts with `$or`, which counts a self-loop ONCE. Grouping on
    the two endpoint fields separately would count it twice, so a self-loop
    would silently score double and rank higher than it should.
    """
    collection = FakeEdgeCollection(degrees={"A": 1})
    asyncio.run(graph_storage(collection).edge_degrees_batch([("A", "A")]))
    stages = collection.pipelines[0]
    assert any("$setUnion" in str(stage) for stage in stages), (
        "endpoints are not deduplicated - a self-loop will count twice")


def test_batch_reads_handle_empty_input():
    collection = FakeEdgeCollection()
    storage = graph_storage(collection)
    assert asyncio.run(storage.get_edges_batch([])) == {}
    assert asyncio.run(storage.edge_degrees_batch([])) == {}
    assert not collection.find_queries and not collection.pipelines
