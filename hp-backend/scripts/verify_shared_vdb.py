# -*- coding: utf-8 -*-
"""Verify the shared vector collections - structure, then a real query.

Run from hp-backend:  python scripts/verify_shared_vdb.py

`migrate_shared_vdb.py` moved every per-workspace vector collection into three
cluster-wide ones partitioned by a `workspace` field. That migration can be
checked structurally - counts match, ids are scoped, three indexes exist - and
for a while that was all that had been checked.

Structure is not the guarantee that matters. The whole design rests on Atlas
applying a *pre-filter* on `workspace`, and a filter that is silently ignored
looks identical from the outside: rows still come back, scores still look
sensible, and one account's evidence reaches another account's prompt. So the
last check here queries a partition that does not exist. If the filter is being
applied that returns nothing; if it is being ignored it returns the same top
rows as the real query. Zero rows is the only result that proves isolation.

Account-agnostic: every partition present is tested, whatever it is called.
"""
import asyncio
import io
import os
import sys

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import logging
logging.basicConfig(level=logging.WARNING)

from app.config.settings import settings
from app.database.mongodb import connect_to_mongo, get_db
from app.services.retrieval.client import _embedding_func
from app.services.retrieval.shared_vdb import (
    PARTITION_FIELD, shared_collection_name, shared_index_name)

NAMESPACES = ("chunks", "entities", "relationships")
# Deliberately broad and account-neutral: it has to retrieve something from any
# account's graph, so it names no company, metric or period.
QUESTION = "Who are the leaders and what are the main business segments?"

PASS, FAIL = [], []


def ck(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    print("  [%s] %-56s %s" % ("PASS" if ok else "FAIL", name, str(detail)[:48]))


def search(db, namespace, vector, partition, top_k=5):
    """The pipeline `shared_vdb.query()` builds, verbatim."""
    return list(db[shared_collection_name(namespace)].aggregate([
        {"$vectorSearch": {
            "index": shared_index_name(namespace),
            "path": "vector",
            "queryVector": vector,
            "numCandidates": 100,
            "limit": top_k,
            "filter": {PARTITION_FIELD: partition},
        }},
        {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"vector": 0}},
    ]))


async def main():
    connect_to_mongo()
    db = get_db()
    collections = db.list_collection_names()

    print("=" * 80)
    print("1. STRUCTURE")
    print("=" * 80)
    partitions = set()
    for namespace in NAMESPACES:
        name = shared_collection_name(namespace)
        if name not in collections:
            ck("%s exists" % name, False, "missing")
            continue
        total = db[name].count_documents({})
        unpartitioned = db[name].count_documents({PARTITION_FIELD: {"$exists": False}})
        ck("%s holds vectors" % name, total > 0, "%d document(s)" % total)
        ck("%s: every row names its partition" % name, unpartitioned == 0,
           "%d without one" % unpartitioned)
        here = db[name].distinct(PARTITION_FIELD)
        partitions.update(here)

        # An id that is not scoped would collide with the same id from another
        # workspace - the one failure mode that silently merges two accounts.
        unscoped = [d["_id"] for d in db[name].find({}, {"_id": 1}).limit(500)
                    if not any(str(d["_id"]).startswith(p + ":") for p in here)]
        ck("%s: ids are workspace-scoped" % name, not unscoped, unscoped[:2])

        indexes = []
        try:
            indexes = list(db[name].list_search_indexes())
        except Exception as exc:
            ck("%s: search index readable" % name, False, exc)
        index = next((i for i in indexes if i.get("name") == shared_index_name(namespace)), None)
        ck("%s: the shared index is queryable" % name,
           bool(index) and index.get("queryable"),
           index.get("status") if index else "absent")
        fields = ((index or {}).get("latestDefinition") or {}).get("fields") or []
        ck("%s: the index declares the partition filter" % name,
           any(f.get("type") == "filter" and f.get("path") == PARTITION_FIELD
               for f in fields))
        ck("%s: the index dimension matches the embedding model" % name,
           any(f.get("numDimensions") == settings.OPENAI_EMBEDDING_DIM
               for f in fields),
           settings.OPENAI_EMBEDDING_DIM)

    # Sharing the graph would merge entities across accounts; only the vectors
    # are shared. See the module docstring in `shared_vdb.py`.
    kv_left = [c for c in collections
               if c.startswith("acct_") and not c.startswith("_bak_")
               and ("chunk_entity_relation" in c or c.endswith("_full_docs")
                    or c.endswith("_doc_status"))]
    ck("per-account graph and doc-status collections were left in place",
       bool(kv_left), "%d collection(s)" % len(kv_left))

    if not partitions:
        print()
        print("no partitions - nothing indexed yet, so there is no query to prove")
        return 1 if FAIL else 0

    print()
    print("=" * 80)
    print("2. A REAL QUERY, PER PARTITION")
    print("=" * 80)
    vector = (await _embedding_func([QUESTION]))[0].tolist()
    ck("the question embeds to the indexed dimension",
       len(vector) == settings.OPENAI_EMBEDDING_DIM, len(vector))

    for partition in sorted(partitions):
        print("  %s" % partition)
        for namespace in NAMESPACES:
            rows = search(db, namespace, vector, partition)
            ck("  %s returns matches" % namespace, bool(rows),
               "%d row(s), top %.4f" % (len(rows), rows[0]["score"]) if rows else "none")
            ck("  %s returns only this partition" % namespace,
               all(r.get(PARTITION_FIELD) == partition for r in rows),
               sorted({r.get(PARTITION_FIELD) for r in rows}))

    print()
    print("=" * 80)
    print("3. THE FILTER ACTUALLY ISOLATES")
    print("=" * 80)
    # Same vector, same index, a partition that cannot exist. See the docstring.
    absent = search(db, "chunks", vector, "no_such_workspace_%d" % len(partitions))
    ck("an unknown partition returns nothing", not absent,
       "%d row(s)" % len(absent))

    print()
    print("=" * 80)
    print("%d passed, %d failed" % (len(PASS), len(FAIL)))
    if FAIL:
        print("FAILED: %s" % ", ".join(f.strip() for f in FAIL))
        return 1
    return 0


sys.exit(asyncio.run(main()))
