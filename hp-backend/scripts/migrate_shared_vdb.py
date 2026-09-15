"""Move per-workspace vectors into the three shared collections.

Nothing is re-embedded and nothing is re-extracted. The stored documents already
carry everything the shared layer needs - `{_id, created_at, <meta>, vector}` -
so this is a copy that rewrites `_id` and adds the `workspace` field. Extraction
is the expensive part of an index build (an LLM call per chunk) and it is
untouched here; expect this to run in seconds, not minutes.

What moves and what does not
----------------------------
    acct_<a>_<idx>_entities        ->  shared_vdb_entities
    acct_<a>_<idx>_relationships   ->  shared_vdb_relationships
    acct_<a>_<idx>_chunks          ->  shared_vdb_chunks

Everything else - KV, graph, doc-status - stays exactly where it is. Those
collections cost no Atlas index capacity, and sharing the graph would merge
entities across accounts (see the module docstring in `shared_vdb.py`).

The unavoidable outage
----------------------
The cluster's index cap counts search and vector indexes together, and the old
per-workspace indexes are using the slots the shared ones need. So the old
indexes must be dropped BEFORE the shared ones can be created, and between those
two points no account can be queried. Vector index builds are not instant.

Run this during a window where that is acceptable, with the retrieval worker
stopped. `--dry-run` first.

Usage:
    python scripts/migrate_shared_vdb.py --dry-run
    python scripts/migrate_shared_vdb.py
    python scripts/migrate_shared_vdb.py --drop-backups   # after verifying
"""

import argparse
import logging
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database.mongodb import connect_to_mongo, get_db, redact_uri  # noqa: E402
from app.config.settings import settings  # noqa: E402
from app.services.retrieval.shared_vdb import (  # noqa: E402
    PARTITION_FIELD, shared_collection_name, shared_index_name)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_shared_vdb")

NAMESPACES = ("entities", "relationships", "chunks")
BACKUP_PREFIX = "_bak_"
# Atlas builds an index asynchronously; this is how long we wait for queryable.
INDEX_TIMEOUT_SECONDS = 600


def find_legacy_collections(db):
    """(collection_name, workspace, namespace) for every per-workspace vector set."""
    found = []
    for name in db.list_collection_names():
        if not name.startswith("acct_") or name.startswith(BACKUP_PREFIX):
            continue
        for namespace in NAMESPACES:
            suffix = "_" + namespace
            if name.endswith(suffix):
                # The workspace is the collection name minus the namespace
                # suffix - identical to what `workspace_name()` produces at
                # runtime, which is what makes the partition values line up.
                found.append((name, name[:-len(suffix)], namespace))
                break
    return sorted(found)


def copy_collection(db, source_name, workspace, namespace, dry_run):
    """Copy one legacy collection into its shared counterpart. Idempotent."""
    target_name = shared_collection_name(namespace)
    source = db[source_name]
    total = source.count_documents({})
    if not total:
        logger.info("  %s is empty - nothing to copy", source_name)
        return 0

    already = db[target_name].count_documents({PARTITION_FIELD: workspace})
    if already >= total:
        logger.info("  %s -> %s: %d already present, skipping",
                    source_name, target_name, already)
        return 0

    if dry_run:
        logger.info("  would copy %d document(s) %s -> %s (partition %s)",
                    total, source_name, target_name, workspace)
        return total

    # Written as an explicit bulk_write rather than an aggregation $merge: the
    # volumes here are small, and a plain upsert loop behaves identically on
    # every server version and is trivially resumable.
    from pymongo import ReplaceOne

    operations, copied = [], 0
    for doc in source.find({}):
        scoped = dict(doc)
        scoped["_id"] = "%s:%s" % (workspace, doc["_id"])
        scoped[PARTITION_FIELD] = workspace
        operations.append(ReplaceOne({"_id": scoped["_id"]}, scoped, upsert=True))
        if len(operations) >= 500:
            db[target_name].bulk_write(operations, ordered=False)
            copied += len(operations)
            operations = []
    if operations:
        db[target_name].bulk_write(operations, ordered=False)
        copied += len(operations)

    landed = db[target_name].count_documents({PARTITION_FIELD: workspace})
    if landed != total:
        raise RuntimeError(
            "%s -> %s: copied %d but only %d landed in partition %s - refusing "
            "to continue" % (source_name, target_name, copied, landed, workspace))

    logger.info("  %s -> %s: %d document(s) in partition %s",
                source_name, target_name, landed, workspace)
    return copied


def drop_legacy_indexes(db, collection_name, dry_run):
    """Release the search-index slots the shared indexes need."""
    dropped = 0
    try:
        for index in db[collection_name].list_search_indexes():
            name = index.get("name")
            if dry_run:
                logger.info("  would drop search index %s on %s", name,
                            collection_name)
            else:
                db[collection_name].drop_search_index(name)
                logger.info("  dropped search index %s on %s", name,
                            collection_name)
            dropped += 1
    except Exception as exc:
        # Not fatal: a local Mongo has no search indexes at all.
        logger.debug("  no search indexes on %s (%s)", collection_name, exc)
    return dropped


def drop_stray_graph_indexes(db, dry_run):
    """Remove the per-workspace graph search indexes.

    `HpMongoGraphStorage` no longer creates these, but any created before this
    migration still occupy slots the shared vector indexes need.
    """
    dropped = 0
    for name in db.list_collection_names():
        if not name.startswith("acct_") or "chunk_entity_relation" not in name:
            continue
        dropped += drop_legacy_indexes(db, name, dry_run)
    return dropped


def create_shared_indexes(db, dry_run):
    """Create the three shared vector indexes and wait until they are queryable."""
    from pymongo.operations import SearchIndexModel

    dim = settings.OPENAI_EMBEDDING_DIM
    created = []

    for namespace in NAMESPACES:
        collection_name = shared_collection_name(namespace)
        index_name = shared_index_name(namespace)

        if collection_name not in db.list_collection_names():
            logger.info("  %s does not exist (no data migrated) - skipping index",
                        collection_name)
            continue

        existing = []
        try:
            existing = [i["name"] for i in
                        db[collection_name].list_search_indexes()]
        except Exception:
            pass
        if index_name in existing:
            logger.info("  %s already exists", index_name)
            continue

        if dry_run:
            logger.info("  would create %s on %s (dim %d, filter on %r)",
                        index_name, collection_name, dim, PARTITION_FIELD)
            continue

        model = SearchIndexModel(
            definition={"fields": [
                {"type": "vector", "numDimensions": dim, "path": "vector",
                 "similarity": "cosine"},
                # The isolation boundary. Without it the runtime guard in
                # shared_vdb refuses to serve queries at all.
                {"type": "filter", "path": PARTITION_FIELD},
            ]},
            name=index_name,
            type="vectorSearch",
        )
        db[collection_name].create_search_index(model)
        created.append((collection_name, index_name))
        logger.info("  creating %s on %s", index_name, collection_name)

    for collection_name, index_name in created:
        _wait_until_queryable(db, collection_name, index_name)


def _wait_until_queryable(db, collection_name, index_name):
    deadline = time.time() + INDEX_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            for index in db[collection_name].list_search_indexes():
                if index.get("name") != index_name:
                    continue
                if index.get("queryable"):
                    logger.info("  %s is queryable", index_name)
                    return
                if index.get("status") == "FAILED":
                    raise RuntimeError(
                        "%s failed to build: %s"
                        % (index_name, index.get("statusDetail")))
        except RuntimeError:
            raise
        except Exception as exc:
            logger.debug("  polling %s: %s", index_name, exc)
        time.sleep(5)
    raise RuntimeError(
        "%s did not become queryable within %ds - check the Atlas console; "
        "retrieval stays down until it does" % (index_name, INDEX_TIMEOUT_SECONDS))


def rename_to_backup(db, collection_name, dry_run):
    backup = BACKUP_PREFIX + collection_name
    if dry_run:
        logger.info("  would rename %s -> %s", collection_name, backup)
        return
    if backup in db.list_collection_names():
        db[backup].drop()
    db[collection_name].rename(backup)
    logger.info("  renamed %s -> %s", collection_name, backup)


def drop_backups(db):
    removed = 0
    for name in db.list_collection_names():
        if name.startswith(BACKUP_PREFIX):
            db[name].drop()
            logger.info("dropped %s", name)
            removed += 1
    logger.info("removed %d backup collection(s)", removed)
    return removed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would happen, change nothing")
    parser.add_argument("--drop-backups", action="store_true",
                        help="delete _bak_* collections from an earlier run and exit")
    args = parser.parse_args()

    connect_to_mongo()
    db = get_db()
    logger.info("database %s on %s", settings.DB_NAME,
                redact_uri(settings.MONGODB_URI))

    if args.drop_backups:
        drop_backups(db)
        return 0

    legacy = find_legacy_collections(db)
    if not legacy:
        logger.info("no per-workspace vector collections found - either this has "
                    "already run, or nothing has been indexed yet")
        # Still ensure the shared indexes exist, so a fresh deployment is ready.
        create_shared_indexes(db, args.dry_run)
        return 0

    workspaces = sorted({w for _, w, _ in legacy})
    logger.info("found %d collection(s) across %d workspace(s): %s",
                len(legacy), len(workspaces), ", ".join(workspaces))

    logger.info("step 1/4: copying vectors into the shared collections")
    for collection_name, workspace, namespace in legacy:
        copy_collection(db, collection_name, workspace, namespace, args.dry_run)

    logger.info("step 2/4: dropping old search indexes to free capacity "
                "(retrieval is DOWN from here until step 3 completes)")
    for collection_name, _, _ in legacy:
        drop_legacy_indexes(db, collection_name, args.dry_run)
    drop_stray_graph_indexes(db, args.dry_run)

    logger.info("step 3/4: creating the shared vector indexes")
    create_shared_indexes(db, args.dry_run)

    logger.info("step 4/4: renaming old collections to %s* "
                "(kept as the rollback path)", BACKUP_PREFIX)
    for collection_name, _, _ in legacy:
        rename_to_backup(db, collection_name, args.dry_run)

    if args.dry_run:
        logger.info("dry run - nothing was changed")
    else:
        logger.info("done. Verify retrieval for each account, then run with "
                    "--drop-backups to reclaim the space.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
