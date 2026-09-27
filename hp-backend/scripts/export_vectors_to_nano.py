# -*- coding: utf-8 -*-
"""Copy the shared Atlas vector collections into NanoVectorDB files.

Run from hp-backend:
    python scripts/export_vectors_to_nano.py --dry-run
    python scripts/export_vectors_to_nano.py --source-uri mongodb://localhost:27017
    python scripts/export_vectors_to_nano.py --source-uri ... --compare-uri "$ATLAS_URI"

Switching VECTOR_STORAGE from "atlas" to "nano" moves the vectors out of
`shared_vdb_{entities,relationships,chunks}` and into one directory per
workspace under RAG_STORAGE_DIR. The vectors themselves need not be recomputed:
every row already carries the embedding it was indexed with. This writes those
rows through LightRAG's own `NanoVectorDBStorage` - an "embedding function" that
returns each row's stored vector - so the files are exactly what a build would
have written, without an embedding call or a byte of hand-rolled file format.

Reads only from Mongo. Writes only files under RAG_STORAGE_DIR, and refuses to
overwrite a workspace that already has vector files unless --replace is given.

Verification, per workspace and namespace:
  * the file holds as many rows as the collection partition;
  * sampled rows, queried with their own vector, come back first;
  * with --compare-uri (the Atlas cluster), the same sampled queries run as
    Atlas `$vectorSearch` exactly as `shared_vdb.py` builds it, and the top-10
    ids are compared with NanoVectorDB's. NanoVectorDB searches exhaustively
    and Atlas approximately, and Nano stores float16, so near-ties can swap -
    the overlap is reported, not required to be perfect.
"""

import argparse
import asyncio
import os
import random
import sys

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from pymongo import MongoClient  # noqa: E402

from app.config.settings import settings  # noqa: E402
from app.database.mongodb import redact_uri  # noqa: E402
from app.services.retrieval.client import rag_storage_dir  # noqa: E402
from app.services.retrieval.shared_vdb import (  # noqa: E402
    PARTITION_FIELD, shared_collection_name, shared_index_name)

NAMESPACES = ("entities", "relationships", "chunks")

# LightRAG's meta_fields per vector namespace (lightrag.py, 1.5.7). Only these
# are kept by NanoVectorDBStorage.upsert; listed so a missing one shows up here.
META_FIELDS = {
    "entities": {"entity_name", "source_id", "content", "file_path"},
    "relationships": {"src_id", "tgt_id", "source_id", "content", "file_path"},
    "chunks": {"full_doc_id", "content", "file_path"},
}

# The cut-off `_vector_storage_config` applies for nano: Atlas's default 0.2 on
# its (1 + cos) / 2 scale. Only used for the verification queries here.
NANO_THRESHOLD = -0.6
ATLAS_SCORE_THRESHOLD = 0.2
SAMPLES = 5
TOP_K = 10


def unscope(scoped_id: str) -> str:
    return scoped_id.split(":", 1)[1] if ":" in scoped_id else scoped_id


def load_partitions(db) -> dict:
    """{workspace: {namespace: [docs]}} from the shared collections."""
    out = {}
    for namespace in NAMESPACES:
        name = shared_collection_name(namespace)
        if name not in db.list_collection_names():
            continue
        for doc in db[name].find({}):
            out.setdefault(doc[PARTITION_FIELD], {}).setdefault(namespace, []).append(doc)
    return out


def _storage(namespace, workspace, root, vectors_by_content):
    from lightrag.kg.nano_vector_db_impl import NanoVectorDBStorage
    from lightrag.utils import EmbeddingFunc

    async def stored_vector(texts, **_):
        return np.array([vectors_by_content[t] for t in texts], dtype=np.float32)

    return NanoVectorDBStorage(
        namespace=namespace, workspace=workspace,
        global_config={"working_dir": root, "embedding_batch_num": 256,
                       "vector_db_storage_cls_kwargs": {
                           "cosine_better_than_threshold": NANO_THRESHOLD}},
        embedding_func=EmbeddingFunc(embedding_dim=settings.OPENAI_EMBEDDING_DIM,
                                     func=stored_vector),
        meta_fields=META_FIELDS[namespace])


async def write(namespace, workspace, docs, root):
    vectors = {d["content"]: d["vector"] for d in docs}
    store = _storage(namespace, workspace, root, vectors)
    await store.initialize()
    await store.upsert({
        unscope(d["_id"]): {k: v for k, v in d.items() if k in META_FIELDS[namespace]}
        for d in docs})
    await store.index_done_callback()
    await store.finalize()


async def verify(namespace, workspace, docs, root, atlas_db):
    store = _storage(namespace, workspace, root, {})
    await store.initialize()
    rows = len((await store.client_storage)["data"])

    self_hits, overlaps = 0, []
    for doc in random.Random(7).sample(docs, min(SAMPLES, len(docs))):
        vector = np.array(doc["vector"], dtype=np.float32)
        nano = [r["id"] for r in await store.query("", TOP_K, query_embedding=vector)]
        self_hits += bool(nano) and nano[0] == unscope(doc["_id"])
        if atlas_db is not None:
            atlas = [unscope(r["_id"]) for r in atlas_db[shared_collection_name(namespace)].aggregate([
                {"$vectorSearch": {"index": shared_index_name(namespace), "path": "vector",
                                   "queryVector": doc["vector"], "numCandidates": 100,
                                   "limit": TOP_K, "filter": {PARTITION_FIELD: workspace}}},
                {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
                {"$match": {"score": {"$gte": ATLAS_SCORE_THRESHOLD}}},
                {"$project": {"_id": 1}}])]
            if atlas:
                overlaps.append(len(set(atlas) & set(nano)) / len(atlas))
    await store.finalize()
    return rows, self_hits, min(SAMPLES, len(docs)), overlaps


async def main_async(args):
    from lightrag.kg.shared_storage import initialize_share_data

    source_uri = args.source_uri or settings.MONGODB_URI
    source = MongoClient(source_uri, serverSelectionTimeoutMS=8000)[settings.DB_NAME]
    atlas = (MongoClient(args.compare_uri, serverSelectionTimeoutMS=8000)[settings.DB_NAME]
             if args.compare_uri else None)
    root = rag_storage_dir()
    print("source   %s / %s" % (redact_uri(source_uri), settings.DB_NAME))
    print("compare  %s" % (redact_uri(args.compare_uri) if atlas is not None else "-"))
    print("target   %s\n" % root)

    partitions = load_partitions(source)
    if args.workspace:
        partitions = {w: p for w, p in partitions.items() if w in args.workspace}
    if not partitions:
        raise SystemExit("no shared vector rows found - nothing to export")

    existing = [w for w in partitions
                if any(os.path.exists(os.path.join(root, w, "vdb_%s.json" % n))
                       for n in NAMESPACES)]
    if existing and not args.replace and not args.dry_run:
        raise SystemExit("refusing: vector files already exist for %s. Re-run with "
                         "--replace to overwrite them." % ", ".join(sorted(existing)))

    initialize_share_data()
    failed = False
    for workspace in sorted(partitions):
        for namespace in NAMESPACES:
            docs = partitions[workspace].get(namespace) or []
            if not docs:
                continue
            missing = sorted({f for d in docs for f in ("content", "vector") if f not in d})
            if missing:
                raise SystemExit("%s/%s rows lack %s" % (workspace, namespace, missing))
            label = "%-52s %-13s %6d" % (workspace, namespace, len(docs))
            if args.dry_run:
                print(label)
                continue
            if args.replace:
                path = os.path.join(root, workspace, "vdb_%s.json" % namespace)
                if os.path.exists(path):
                    os.remove(path)
            await write(namespace, workspace, docs, root)
            rows, hits, sampled, overlaps = await verify(namespace, workspace, docs, root, atlas)
            ok = rows == len(docs) and hits == sampled
            failed |= not ok
            print("%s  -> %6d rows  self-match %d/%d%s  %s" % (
                label, rows, hits, sampled,
                ("  atlas top-%d overlap %.0f%%" % (TOP_K, 100 * sum(overlaps) / len(overlaps))
                 if overlaps else ""),
                "OK" if ok else "MISMATCH"))

    if args.dry_run:
        print("\ndry run - nothing was written")
    elif failed:
        raise SystemExit("\nverification failed - do not switch VECTOR_STORAGE to nano")
    else:
        print("\nall workspaces exported and verified")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source-uri", default="",
                        help="Mongo holding shared_vdb_* (default: MONGODB_URI)")
    parser.add_argument("--compare-uri", default="",
                        help="Atlas cluster to compare search results against")
    parser.add_argument("--workspace", action="append",
                        help="only this workspace (repeatable)")
    parser.add_argument("--replace", action="store_true",
                        help="overwrite existing vector files")
    parser.add_argument("--dry-run", action="store_true",
                        help="list what would be exported, write nothing")
    asyncio.run(main_async(parser.parse_args()))


if __name__ == "__main__":
    main()
