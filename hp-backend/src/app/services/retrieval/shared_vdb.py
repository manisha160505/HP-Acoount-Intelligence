"""Shared Atlas Vector Search infrastructure, partitioned by workspace.

Why this module exists
----------------------
A LightRAG workspace prefixes every Mongo collection it owns, which gives each
account physical separation - and costs three Atlas Vector Search indexes, one
per vector namespace (entities, relationships, chunks). Two enabled indexes per
account therefore cost six, and the cluster's cap is three *shared across search
and vector indexes alike*. Account #2 was arithmetically impossible; account #1
was already over budget.

The expensive thing is the search index, and **only the vector stores need one**.
KV, graph and doc-status collections cost no index capacity at all. So the split
is drawn there:

    vectors (entities, relationships, chunks)
        -> THREE shared collections, THREE indexes, for every account forever
        -> isolation is logical: a `workspace` field + an Atlas pre-filter

    KV, graph, doc_status
        -> per-(account, index) collections exactly as before
        -> isolation is physical, and free

Why the graph is NOT shared
---------------------------
This is the load-bearing reason the split sits here and not further along.

LightRAG keys a graph node by its entity *name* - `upsert_node` writes
`update_one({"_id": node_id})` and `_merge_nodes_then_upsert` reads the existing
node by name and unions its descriptions and `source_id`s. In one shared
collection, "HP" from account A and "HP" from account B become a single node
whose `source_id` spans both accounts. At query time `_get_node_data` walks
`get_nodes_batch` -> `_find_most_related_edges_from_entities` **by name**, so
account B's chunks would surface in account A's prompt.

No vector filter can prevent that, because the graph walk never touches the
vector store. The same applies to the KV cache (keyed on prompt hash with no
workspace component - B asking A's question would get A's cached *answer*),
chunk ids (content hashes, so shared boilerplate collides), and doc-status
(scanned by status with no partition predicate, so A's pipeline would pick up
B's pending documents). Partitioning all of that means scoping some sixty-five
methods including `$graphLookup` BFS and paginated status scans, where one
missed predicate is a silent cross-account leak - re-litigated on every LightRAG
upgrade. Not worth it when those collections are free.

How isolation is enforced here
------------------------------
Two independent mechanisms, deliberately redundant:

  1. **Scoped ids.** Every `_id` becomes `"{workspace}:{id}"`. Ids are
     `chunk-|ent-|rel-` plus 32 hex characters and a workspace is `[A-Za-z0-9_]+`,
     so `:` appears in neither and the split is unambiguous.

  2. **An Atlas pre-filter.** The index declares `{"type": "filter", "path":
     "workspace"}` and every `$vectorSearch` carries `filter: {"workspace": ...}`.
     Atlas applies this *before* the semantic search, so the candidate pool is
     the partition rather than the whole collection - recall is unchanged.

The filter is the one that matters, and it only works if the running index
actually declares the filter path. What Atlas does with a filter on an
*undeclared* path is not documented clearly enough to rely on, so
`create_vector_index_if_not_exists` **fails closed**: an existing index whose
definition lacks the filter field raises rather than serving queries that might
silently span accounts. The base class's version checks only name and dimension
and would accept such an index happily - that is precisely the hole being shut.

What this module does NOT protect against
-----------------------------------------
Shared collections mean anyone holding database credentials sees every account's
chunk text in one place. This module guarantees isolation at the application
layer; physical separation of the vector data is what the shared-infrastructure
decision traded away.
"""

import logging

logger = logging.getLogger(__name__)

# The exact release this module's private-attribute coupling was verified
# against. See the "Upgrading LightRAG" note at the bottom of this file.
VERIFIED_LIGHTRAG_VERSION = "1.5.7"

SHARED_PREFIX = "shared_vdb"
PARTITION_FIELD = "workspace"
_SCOPE_SEP = ":"

# `register()` is idempotent but does real import work; a module-level flag
# keeps repeated `build_rag()` calls from redoing it.
_REGISTERED = False


class SharedVectorConfigError(Exception):
    """The shared vector layer is not safe to use as configured."""


def shared_collection_name(namespace: str) -> str:
    return "%s_%s" % (SHARED_PREFIX, namespace)


def shared_index_name(namespace: str) -> str:
    return "%s_%s_idx" % (SHARED_PREFIX, namespace)


def _build_classes():
    """Define the storage subclasses against the installed LightRAG.

    Built inside a function rather than at import so that importing this module
    never drags in LightRAG - `client.py` is imported by request paths that must
    not pay that cost, and the library is a heavy import.
    """
    import contextlib

    # `_canonical_edge_endpoints` is the library's own sorted-pair helper, the
    # one `get_edge` uses to hit the unique `(edge_lo, edge_hi)` index. Imported
    # rather than reimplemented so a change to its rule cannot leave the batch
    # override looking up a key the single-edge path no longer writes.
    from lightrag.kg.mongo_impl import (
        MongoGraphStorage,
        MongoVectorDBStorage,
        _canonical_edge_endpoints,
    )

    class HpSharedVectorStorage(MongoVectorDBStorage):
        """One shared collection per namespace, partitioned by workspace.

        Only the methods that touch an id or issue a query are overridden. The
        base class's deferred-embedding buffers, batching limits and flush
        machinery are reused untouched - they operate on whatever ids they are
        given, so scoping on the way in and unscoping on the way out is a
        complete seal.
        """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            # `self.workspace` is resolved by the base constructor from the
            # passed workspace (and, historically, the MONGODB_WORKSPACE env
            # var - which client.py now refuses to set).
            partition = (self.workspace or "").strip()
            if not partition:
                # An unpartitioned instance on a shared collection would read
                # and write every account's vectors. There is no safe default.
                raise SharedVectorConfigError(
                    "HpSharedVectorStorage requires a workspace - an empty one "
                    "would share every account's vectors in one partition")
            if _SCOPE_SEP in partition:
                raise SharedVectorConfigError(
                    "workspace %r contains %r, which is the id scope separator"
                    % (partition, _SCOPE_SEP))
            self.partition = partition

            # Point every path at the shared collection and index. Setting
            # `final_namespace` too is deliberate: the base class derives its
            # flush lock from it, so all workspaces writing one collection share
            # one writer lock, which is the correct lock.
            self.final_namespace = shared_collection_name(self.namespace)
            self._collection_name = self.final_namespace
            self._index_name = shared_index_name(self.namespace)

            # The base `upsert` copies through only keys listed in meta_fields,
            # so without this the partition value would be dropped before it
            # ever reached the document.
            self.meta_fields = set(self.meta_fields) | {PARTITION_FIELD}

        # -- id scoping ---------------------------------------------------

        def _scope(self, doc_id: str) -> str:
            return "%s%s%s" % (self.partition, _SCOPE_SEP, doc_id)

        def _unscope(self, doc_id: str) -> str:
            prefix = self.partition + _SCOPE_SEP
            return doc_id[len(prefix):] if str(doc_id).startswith(prefix) else doc_id

        def _unscope_doc(self, doc):
            """Return a copy with `_id`/`id` as the caller's unscoped id.

            Callers match these ids against `text_chunks` KV keys and pass them
            back to `delete()`, so a scoped id leaking out would silently fail
            to match anything.
            """
            if not isinstance(doc, dict):
                return doc
            out = dict(doc)
            if "_id" in out:
                out["_id"] = self._unscope(out["_id"])
                out["id"] = out["_id"]
            elif "id" in out:
                out["id"] = self._unscope(out["id"])
            out.pop(PARTITION_FIELD, None)
            return out

        # -- writes -------------------------------------------------------

        async def upsert(self, data):
            if not data:
                return None
            scoped = {}
            for key, value in data.items():
                payload = dict(value)
                payload[PARTITION_FIELD] = self.partition
                scoped[self._scope(key)] = payload
            return await super().upsert(scoped)

        async def delete(self, ids):
            if not ids:
                return None
            return await super().delete([self._scope(i) for i in list(ids)])

        async def delete_entity(self, entity_name: str):
            from lightrag.utils import compute_mdhash_id

            entity_id = compute_mdhash_id(entity_name, prefix="ent-")
            # Routed through our own `delete` so the id is scoped exactly once.
            await self.delete([entity_id])

        async def delete_entity_relation(self, entity_name: str):
            """Delete this partition's relations mentioning `entity_name`.

            Reimplemented rather than delegated: the base finds relations with
            `{"$or": [{"src_id": name}, {"tgt_id": name}]}` and no partition
            predicate. On a shared collection that matches - and deletes - every
            other account's relations that happen to name the same entity, and
            entity names like "HP" are exactly the ones accounts share.
            """
            def _prune_pending():
                doomed = [k for k, v in self._pending_vector_docs.items()
                          if v.source.get("src_id") == entity_name
                          or v.source.get("tgt_id") == entity_name]
                for doc_id in doomed:
                    self._pending_vector_docs.pop(doc_id, None)

            async with self._flush_lock:
                if self._data is None:
                    _prune_pending()
                    return

                cursor = self._data.find(
                    {PARTITION_FIELD: self.partition,
                     "$or": [{"src_id": entity_name}, {"tgt_id": entity_name}]},
                    {"_id": 1},
                )
                relations = await cursor.to_list(length=None)
                if not relations:
                    _prune_pending()
                    return

                ids = [r["_id"] for r in relations]
                await self._data.delete_many({"_id": {"$in": ids}})
                _prune_pending()
                logger.debug("[%s] deleted %d relation vector(s) for %s",
                             self.partition, len(ids), entity_name)

        async def drop(self):
            """Remove this partition's vectors. Never touches the index.

            The base implementation drops the whole collection and recreates the
            index; here that would wipe every other account and take the shared
            index offline while it rebuilt.
            """
            try:
                async with self._flush_lock:
                    self._pending_vector_docs.clear()
                    self._pending_vector_deletes.clear()
                    if self._data is not None:
                        await self._data.delete_many(
                            {PARTITION_FIELD: self.partition})
                logger.info("[%s] dropped partition from %s",
                            self.partition, self._collection_name)
                return {"status": "success",
                        "message": "partition %s dropped" % self.partition}
            except Exception as exc:
                logger.exception("[%s] could not drop partition", self.partition)
                return {"status": "error", "message": str(exc)}

        # -- reads --------------------------------------------------------

        async def query(self, query: str, top_k: int, query_embedding=None):
            """Atlas Vector Search, pre-filtered to this partition.

            Reimplemented because the base builds a fixed `$vectorSearch` stage
            with no `filter` key and nothing threads one in - `QueryParam` never
            reaches a vector store, and the abstract signature carries no filter
            argument. The filter is a *pre*-filter: Atlas restricts the candidate
            pool before searching, so `numCandidates` still yields a full pool
            from within the partition and recall matches the per-workspace
            collections this replaces.
            """
            if query_embedding is not None:
                query_vector = (query_embedding.tolist()
                                if hasattr(query_embedding, "tolist")
                                else list(query_embedding))
            else:
                from lightrag.kg.mongo_impl import DEFAULT_QUERY_PRIORITY

                embedding = await self.embedding_func(
                    [query], context="query", _priority=DEFAULT_QUERY_PRIORITY)
                query_vector = embedding[0].tolist()

            pipeline = [
                {"$vectorSearch": {
                    "index": self._index_name,
                    "path": "vector",
                    "queryVector": query_vector,
                    "numCandidates": 100,
                    "limit": top_k,
                    # The isolation boundary.
                    "filter": {PARTITION_FIELD: self.partition},
                }},
                {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                {"$match": {"score": {"$gte": self.cosine_better_than_threshold}}},
                {"$project": {"vector": 0}},
            ]

            cursor = await self._data.aggregate(pipeline, allowDiskUse=True)
            results = await cursor.to_list(length=None)

            out = []
            for doc in results:
                # Defence in depth: if a filter were ever silently ignored, this
                # keeps another partition's row from reaching a prompt. It should
                # never fire - so say so loudly if it does.
                if doc.get(PARTITION_FIELD) != self.partition:
                    logger.error(
                        "[%s] shared vector search returned a row from partition "
                        "%r - the Atlas pre-filter is not being applied; dropping "
                        "it. Check that %s declares a filter field on %r.",
                        self.partition, doc.get(PARTITION_FIELD),
                        self._index_name, PARTITION_FIELD)
                    continue
                unscoped = self._unscope_doc(doc)
                unscoped["distance"] = doc.get("score")
                unscoped["created_at"] = doc.get("created_at")
                out.append(unscoped)
            return out

        async def get_by_id(self, id: str):
            found = await super().get_by_id(self._scope(id))
            return self._unscope_doc(found) if found else None

        async def get_by_ids(self, ids):
            if not ids:
                return []
            found = await super().get_by_ids([self._scope(i) for i in ids])
            return [self._unscope_doc(d) for d in found if d is not None]

        async def get_vectors_by_ids(self, ids):
            if not ids:
                return {}
            vectors = await super().get_vectors_by_ids(
                [self._scope(i) for i in ids])
            return {self._unscope(k): v for k, v in vectors.items()}

        # -- index --------------------------------------------------------

        async def create_vector_index_if_not_exists(self):
            """Create the shared index, or refuse to run against an unsafe one.

            Fails closed on purpose. The base class accepts any existing index
            whose name and dimension match, which on a shared collection would
            happily serve an index with no filter field - and every query would
            then search across all accounts. Rather than auto-repair (dropping a
            shared index takes every account offline), this raises and says what
            to do.
            """
            from pymongo.operations import SearchIndexModel

            expected_dim = self.embedding_func.embedding_dim

            cursor = await self._data.list_search_indexes()
            existing = await cursor.to_list(length=None)
            for index in existing:
                if index.get("name") != self._index_name:
                    continue

                fields = (index.get("latestDefinition") or {}).get("fields") or []
                dim = next((f.get("numDimensions") for f in fields
                            if f.get("type") == "vector"
                            and f.get("path") == "vector"), None)
                if dim is not None and dim != expected_dim:
                    raise SharedVectorConfigError(
                        "shared vector index %s has dimension %s but the "
                        "embedding model produces %s - drop the index and "
                        "re-migrate rather than mixing dimensions"
                        % (self._index_name, dim, expected_dim))

                has_filter = any(f.get("type") == "filter"
                                 and f.get("path") == PARTITION_FIELD
                                 for f in fields)
                if not has_filter:
                    raise SharedVectorConfigError(
                        "shared vector index %s does not declare a filter field "
                        "on %r, so account partitioning cannot be enforced and "
                        "a query could span accounts. Drop this index and let it "
                        "be recreated (every account is unqueryable until the "
                        "rebuild finishes)."
                        % (self._index_name, PARTITION_FIELD))

                logger.info("shared vector index %s is present and partition-safe",
                            self._index_name)
                return

            model = SearchIndexModel(
                definition={"fields": [
                    {"type": "vector",
                     "numDimensions": expected_dim,
                     "path": "vector",
                     "similarity": "cosine"},
                    # Without this declaration the `filter` in `query()` has
                    # nothing to match on.
                    {"type": "filter", "path": PARTITION_FIELD},
                ]},
                name=self._index_name,
                type="vectorSearch",
            )
            await self._data.create_search_index(model)
            logger.info("created shared vector index %s (dim %s, partitioned on %r)",
                        self._index_name, expected_dim, PARTITION_FIELD)

    class HpMongoGraphStorage(MongoGraphStorage):
        """Per-workspace graph storage that does not spend index capacity.

        Identical to the base in every respect except one: the base creates an
        Atlas *Search* index (`entity_id_search_idx`) on each workspace's node
        collection, and the cluster's cap counts search and vector indexes
        together. Left enabled, a graph store could take the last free slot the
        moment one opened - during migration, say - and the shared vector index
        creation would then fail hard (LightRAG raises SystemExit there).

        The index only accelerates `search_labels`, which nothing in this project
        calls; the base falls back to regex without it.
        """

        async def create_search_index_if_not_exists(self):
            logger.debug(
                "[%s] skipping the per-workspace Atlas Search index - index "
                "capacity is reserved for the shared vector indexes",
                self.workspace)

        async def initialize(self):
            await super().initialize()
            # `node_degrees_batch` groups on these two fields, and nothing
            # indexes them - the base builds only the unique `(edge_lo,
            # edge_hi)` index. Without this every degree lookup is a collection
            # scan.
            #
            # An ordinary index, not an Atlas Search or vector index, so it
            # costs none of the capacity this module exists to protect: the
            # cluster's cap counts search and vector indexes only.
            with contextlib.suppress(Exception):
                await self.edge_collection.create_index(
                    [("source_node_id", 1)], name="hp_edge_source_idx")
                await self.edge_collection.create_index(
                    [("target_node_id", 1)], name="hp_edge_target_idx")

        # -------------------------------------------------------------------
        # The two batch reads LightRAG never implemented for Mongo.
        #
        # `BaseGraphStorage` supplies both as sequential `for` loops with an
        # `await` inside - "Override this method for better performance in
        # storage backends that support batch operations" - and Neo4j and
        # Postgres do override them. Mongo does not, so on a remote Atlas
        # cluster every relation cost its own network round trip.
        #
        # One Strategy Chat question retrieved 553 relations and spent 147
        # seconds on 1,659 sequential round trips: 553 `find_one` for the edges
        # and 1,106 unindexed `count_documents` for their degrees, at ~130ms
        # each. The same work is three queries.
        #
        # Both must return exactly what the base returns, including which pairs
        # are absent - retrieval ranks on these numbers, so a subtly different
        # degree is a subtly different answer rather than a visible failure.
        # -------------------------------------------------------------------

        async def get_edges_batch(self, pairs: list) -> dict:
            """Every edge in one query, keyed by the pair as it was asked for.

            Matches `get_edge`: canonical `(edge_lo, edge_hi)` lookup served by
            the existing unique index, `_id` stripped so a fetched edge can be
            re-upserted without pushing an immutable field into `$set`, and a
            pair with no edge simply absent from the result.
            """
            wanted = [(str(p["src"]), str(p["tgt"])) for p in (pairs or [])]
            if not wanted:
                return {}

            clauses, by_canonical = [], {}
            for src, tgt in wanted:
                lo, hi = _canonical_edge_endpoints(src, tgt)
                if (lo, hi) not in by_canonical:
                    clauses.append({"edge_lo": lo, "edge_hi": hi})
                # Several asked-for pairs can share one canonical edge - (A,B)
                # and (B,A) are the same undirected edge - and each of them
                # wants its own key in the result.
                by_canonical.setdefault((lo, hi), []).append((src, tgt))

            out = {}
            # `find` hands back a cursor directly; only `aggregate` is awaitable.
            cursor = self.edge_collection.find({"$or": clauses})
            async for doc in cursor:
                key = (doc.get("edge_lo"), doc.get("edge_hi"))
                doc.pop("_id", None)
                for pair in by_canonical.get(key, []):
                    out[pair] = dict(doc)
            return out

        async def edge_degrees_batch(self, edge_pairs: list) -> dict:
            """Degree of both endpoints of every pair, in one aggregation.

            The base computes `node_degree(src) + node_degree(tgt)` per pair,
            and `node_degree` counts edges matching `source == id OR target ==
            id`. That `$or` counts a SELF-LOOP ONCE, while grouping on the two
            endpoint fields separately would count it twice. `$setUnion`
            deduplicates an edge's endpoints before counting, which is what
            keeps this identical to the base rather than merely close to it.
            """
            pairs = [(str(s), str(t)) for s, t in (edge_pairs or [])]
            if not pairs:
                return {}

            nodes = sorted({n for pair in pairs for n in pair})
            degrees = {}
            cursor = await self.edge_collection.aggregate([
                {"$match": {"$or": [{"source_node_id": {"$in": nodes}},
                                    {"target_node_id": {"$in": nodes}}]}},
                {"$project": {"ends": {"$setUnion": [["$source_node_id"],
                                                     ["$target_node_id"]]}}},
                {"$unwind": "$ends"},
                {"$match": {"ends": {"$in": nodes}}},
                {"$group": {"_id": "$ends", "degree": {"$sum": 1}}},
            ], allowDiskUse=True)
            async for doc in cursor:
                degrees[doc.get("_id")] = doc.get("degree") or 0

            # A node with no edges is absent from the aggregation and scores 0,
            # exactly as `count_documents` would return 0 for it.
            return {(src, tgt): degrees.get(src, 0) + degrees.get(tgt, 0)
                    for src, tgt in pairs}

    return HpSharedVectorStorage, HpMongoGraphStorage


def register():
    """Teach LightRAG about these classes, by name. Idempotent.

    LightRAG resolves a storage class by looking its name up in `kg.STORAGES`
    for a dotted module path and importing it, so registering is two dict
    entries - no monkeypatch of the library's own classes, no vendored copy of
    `mongo_impl.py`, and nothing that a reinstall would undo.
    """
    global _REGISTERED
    if _REGISTERED:
        return

    import lightrag
    from lightrag.kg import STORAGE_IMPLEMENTATIONS, STORAGES

    version = getattr(lightrag, "__version__", "unknown")
    if version != VERIFIED_LIGHTRAG_VERSION:
        # Not fatal: the coupling may well survive. But it was verified against
        # one release and the failure mode is a silent leak, so it must be said.
        logger.warning(
            "retrieval: lightrag %s is installed, but the shared vector storage "
            "was verified against %s. Re-check shared_vdb.py against the new "
            "MongoVectorDBStorage before trusting account isolation.",
            version, VERIFIED_LIGHTRAG_VERSION)

    shared_vector, graph = _build_classes()

    module = __name__
    for cls in (shared_vector, graph):
        globals()[cls.__name__] = cls
        STORAGES[cls.__name__] = module

    # `verify_storage_implementation` checks the name against these lists and
    # rejects anything unknown, so the new names have to be declared.
    for kind, name in (("VECTOR_STORAGE", shared_vector.__name__),
                       ("GRAPH_STORAGE", graph.__name__)):
        impls = STORAGE_IMPLEMENTATIONS.get(kind, {}).get("implementations")
        if impls is not None and name not in impls:
            impls.append(name)

    _REGISTERED = True
    logger.info("retrieval: registered shared vector storage (%s) and "
                "capacity-free graph storage (%s)",
                shared_vector.__name__, graph.__name__)


# `STORAGES` maps a class name to a module path and LightRAG then does
# `getattr(module, name)`, so the classes must be attributes of this module.
# `register()` installs them into globals() above; these names exist so that an
# import of them before registration fails loudly rather than mysteriously.
def __getattr__(name):
    if name in ("HpSharedVectorStorage", "HpMongoGraphStorage"):
        raise AttributeError(
            "%s is not built yet - call shared_vdb.register() before asking "
            "LightRAG to resolve it" % name)
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# Upgrading LightRAG
# ------------------
# This module subclasses `MongoVectorDBStorage` and touches private attributes
# (`_pending_vector_docs`, `_pending_vector_deletes`, `_flush_lock`, `_data`,
# `_index_name`, `_collection_name`, `final_namespace`). That is a deliberate
# trade - the alternative was vendoring a 4,600-line module - but it means a
# LightRAG bump is not a routine dependency update. Before changing the pin:
#
#   1. Re-read `MongoVectorDBStorage.upsert/query/delete*/get_*/drop` and confirm
#      the buffer and flush contract still holds.
#   2. Confirm `$vectorSearch` is still built in `query()` and still lacks a
#      filter parameter (if upstream adds one, delete the override and use it).
#   3. Run tests/test_shared_vdb.py, including the two-workspace isolation case
#      against a real Atlas cluster.
#   4. Re-check the graph batch reads. `HpMongoGraphStorage` overrides
#      `get_edges_batch` and `edge_degrees_batch` because `MongoGraphStorage`
#      never implemented them and `BaseGraphStorage`'s fallbacks are sequential
#      loops - one question spent 147 seconds on 1,659 round trips. If a bump
#      implements them for Mongo, DELETE these overrides and use upstream's.
#      If it changes their signatures or the canonical `(edge_lo, edge_hi)`
#      scheme they rely on, the overrides break quietly: retrieval would keep
#      working while ranking on different degree numbers. The equivalence check
#      against the live graph is what catches that, not the unit tests.
#
# The version warning in `register()` is the tripwire, not a substitute for this.
