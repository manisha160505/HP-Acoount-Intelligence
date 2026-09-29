"""Bring an existing database under the regeneration engine, without regenerating.

Idempotent and non-destructive: nothing is deleted and no widget content is
changed. Safe to run on every startup, and after a rollback to the pre-engine
release and back.

  1. Refuse to create the `account_widgets` unique index over duplicate rows;
     report them instead.
  2. Create the engine's indexes.
  3. Record a content hash on every active dataset row whose file is on this
     machine. A dataset's version is built from these hashes; a row with no
     hash is versioned by its id until a host that has the file runs this.
  4. For every (account, producer) with no node state, adopt what
     `account_widgets` holds as a **legacy** generation: served exactly as
     today, but with no fingerprint, so it reads as STALE ("not yet verified")
     and is regenerated progressively by the sweep (owner decision O-1).
  5. Roll-forward after a rollback: widget rows the old release wrote (they
     carry no `rev`) that are newer than the node's committed generation are
     adopted again, so the newest content wins.
  6. Index nodes adopt a READY/STALE `retrieval_index_state` the same way.
  7. Cancel queued jobs no explicit run asked for (29 Sep): the automatic
     triggers of the earlier release queued them, and the worker no longer
     claims them. Their nodes simply read as stale.
  8. Narrow the model block of every committed manifest to the settings the
     node uses (29 Sep, `manifest.MODEL_KEYS`) and re-derive its fingerprint.
     Without this, the release that narrowed the fingerprint would itself make
     every model-backed node of every account read as stale. Only the model
     block changes, and only by dropping keys the node never used, so the new
     fingerprint describes exactly the inputs the output was built from.
"""

import hashlib
import logging
from datetime import UTC, datetime

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.services.regen import manifest, state
from app.services.regen.graph import DEFAULT, INDEX

logger = logging.getLogger(__name__)

# Content Messaging's index (idx_content_messaging) was removed with the
# feature on 28 Sep.
INDEX_OF_NODE = {"idx_executive_dashboard": "executive_dashboard",
                 "idx_strategy": "strategy"}


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _aware(value):
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _legacy_generation(widgets: dict, extra=None, generated_at=None) -> dict:
    return {"generation_id": ObjectId(), "fingerprint": None, "manifest": None,
            "logic_total": 0, "quality": state.COMPLETE, "legacy": True,
            "output_hash": manifest.output_hash(widgets, extra),
            "widgets": widgets, "index": extra, "degraded_retries": 0,
            "generated_at": generated_at or datetime.now(UTC)}


def _widgets_from_rows(rows: list) -> dict:
    return {r["widget_key"]: {"status": r.get("status", "empty"), "data": r.get("data") or {},
                              "source_datasets": r.get("source_datasets") or [],
                              "data_classification": r.get("data_classification")}
            for r in rows}


def run(db, graph=DEFAULT, dry_run: bool = True, file_path_for=None) -> dict:
    if file_path_for is None:
        from app.services.extractors.datasets import find_file_path as file_path_for
    report = {"dry_run": dry_run, "duplicates": [], "hashed": 0, "unhashed_missing": 0,
              "adopted": 0, "rolled_forward": 0, "indexes_adopted": 0,
              "unbound_jobs_cancelled": 0, "manifests_narrowed": 0}

    dups = list(db["account_widgets"].aggregate([
        {"$group": {"_id": {"a": "$account_id", "w": "$widget_key"}, "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}}, {"$limit": 20}]))
    if dups:
        report["duplicates"] = [d["_id"] for d in dups]
        logger.error("regen migrate: duplicate account_widgets rows - fix before "
                     "migrating: %s", report["duplicates"][:5])
        return report

    if not dry_run:
        from app.services.regen.engine import Engine
        Engine(db=db, graph=graph, versions=manifest.StaticVersions()).ensure_indexes()

    for row in db["account_data_files"].find({"status": "active",
                                              "content_sha256": {"$exists": False}}):
        path = file_path_for(row.get("file_path") or "")
        if not path:
            report["unhashed_missing"] += 1
            continue
        report["hashed"] += 1
        if not dry_run:
            db["account_data_files"].update_one(
                {"_id": row["_id"]}, {"$set": {"content_sha256": _hash_file(path)}})

    accounts = [str(a["_id"]) for a in db["accounts"].find({}, {"_id": 1})]
    for account_id in accounts:
        states = state.load_account(db, account_id)
        rows = {r["widget_key"]: r for r in db["account_widgets"].find({"account_id": account_id})}
        for nid in graph.order:
            node = graph[nid]
            if node.kind == INDEX:
                if nid in states:
                    continue
                idx = db["retrieval_index_state"].find_one(
                    {"account_id": account_id, "index": INDEX_OF_NODE.get(nid)}) or {}
                if idx.get("status") not in ("READY", "STALE"):
                    continue
                extra = {"corpus": {k: (v or {}).get("fingerprint")
                                    for k, v in (idx.get("documents") or {}).items()},
                         "index_version": idx.get("version")}
                report["indexes_adopted"] += 1
                if not dry_run:
                    _adopt(db, account_id, nid,
                           _legacy_generation({}, extra, _aware(idx.get("last_built_at"))))
                continue

            mine = [rows[k] for k in node.widgets if k in rows]
            if not mine:
                continue
            current = (states.get(nid) or {}).get("current")
            if current is None:
                newest = max((_aware(r.get("updated_at")) for r in mine
                              if isinstance(r.get("updated_at"), datetime)), default=None)
                report["adopted"] += 1
                if not dry_run:
                    _adopt(db, account_id, nid,
                           _legacy_generation(_widgets_from_rows(mine), None, newest))
                continue
            # Roll-forward: rows written by the pre-engine release carry no rev.
            if current and any("rev" not in r and isinstance(r.get("updated_at"), datetime)
                               and _aware(r["updated_at"]) > _aware(current.get("generated_at"))
                               for r in mine):
                widgets = dict(current.get("widgets") or {})
                widgets.update(_widgets_from_rows([r for r in mine if "rev" not in r]))
                report["rolled_forward"] += 1
                if not dry_run:
                    _adopt(db, account_id, nid, _legacy_generation(widgets), replace=True)

    report["manifests_narrowed"] = _narrow_model_manifests(db, graph, dry_run)
    if not dry_run:
        from app.services.regen import jobs
        report["unbound_jobs_cancelled"] = jobs.cancel_unbound(db)

    logger.info("regen migrate%s: %s", " (dry run)" if dry_run else "", report)
    return report


def _narrow_model_manifests(db, graph, dry_run: bool) -> int:
    """Step 8 of the module docstring. Idempotent: a narrowed manifest is left."""
    changed = 0
    for doc in db[state.COLLECTION].find({"current.manifest.model": {"$exists": True}},
                                         {"node_id": 1, "current.manifest": 1}):
        nid = doc.get("node_id")
        if nid not in graph:
            continue
        m = (doc.get("current") or {}).get("manifest") or {}
        old = m.get("model")
        if not isinstance(old, dict):
            continue
        new = manifest.model_inputs(graph[nid], old)
        if new == old:
            continue
        changed += 1
        if dry_run:
            continue
        m = {**m, "model": new}
        db[state.COLLECTION].update_one(
            {"_id": doc["_id"], "current.manifest.model": old},
            {"$set": {"current.manifest": m,
                      "current.fingerprint": manifest.fingerprint(m)}})
    return changed


def _adopt(db, account_id: str, node_id: str, generation: dict, replace: bool = False):
    filter_ = {"_id": state.state_id(account_id, node_id)}
    if not replace:
        filter_["current"] = None          # matches a missing or null `current`
    try:
        db[state.COLLECTION].update_one(
            filter_,
            {"$set": {"current": generation, "updated_at": datetime.now(UTC)},
             "$setOnInsert": {"account_id": account_id, "node_id": node_id,
                              "running": None, "last_failure": None},
             "$inc": {"rev": 1}},
            upsert=not replace)
    except DuplicateKeyError:
        # The node committed a generation between the scan and this write;
        # a real generation always wins over adopting the legacy rows.
        logger.info("regen migrate: %s/%s already has a generation", account_id, node_id)
