"""Accept a release's code changes as current where they do not change output.

A logic version bump, a dataset a section now declares or no longer reads, or
an upstream rebuilt, all change a section's fingerprint and mark it stale for
every account - including the accounts whose output the release does not touch.
Rebuilding those spends model calls to produce what is already on screen.

`rebase` re-stamps such a section's committed output with the fingerprint it
would have today, without regenerating it. It does so only when:

  * the section has a committed, tracked generation (not legacy, not failed,
    not running or queued);
  * every reason it is stale is code (logic/prompt version), an upstream, or a
    dataset newly declared or no longer read - never a changed file, rules,
    configuration or model;
  * the (account, section) pair is not in `affected`: the pairs the release
    does change, which are rebuilt by a run instead.

The old fingerprint is kept under `current.rebased`, so a rebased output can
always be told from a generated one. Writes are conditional on the old
fingerprint, so a generation committed meanwhile is never overwritten.
Same pattern as step 8 of regen/migrate.py.
"""

from datetime import UTC, datetime

from app.services.regen import jobs, reasons, state
from app.services.regen.engine import load_snapshot

ALLOWED = {reasons.CODE, reasons.PROMPT, reasons.UPSTREAM}


def _without_empty_upstreams(m: dict) -> dict:
    return {**m, "upstream": {k: v for k, v in (m.get("upstream") or {}).items()
                              if v is not None}}


def _eligible(why: list, old_manifest: dict, new_manifest: dict) -> bool:
    if not why:
        # A newly declared upstream that has never produced output (Hiring on
        # an account with no job file) changes the fingerprint and nothing else.
        return (_without_empty_upstreams(old_manifest)
                == _without_empty_upstreams(new_manifest))
    old_ds = old_manifest.get("datasets") or {}
    new_ds = new_manifest.get("datasets") or {}
    for r in why:
        cat = r.get("category")
        if cat in ALLOWED:
            continue
        if cat == reasons.DATA:
            key = str(r.get("key") or "").split(".", 1)[-1]
            # Declared or dropped by the release, not a file that changed.
            if (key in old_ds) != (key in new_ds):
                continue
        return False
    return True


def rebase_account(engine, account_id: str, affected: set, *, dry_run: bool = True,
                   label: str = "") -> dict:
    """{node_id: outcome} for one account. `affected` holds node ids to leave
    stale for this account."""
    db = engine.db
    snapshot = load_snapshot(db, account_id)
    manifests, fps = engine.expected_all(snapshot)
    live = jobs.live(db, account_id)
    out = {}
    for nid in engine.graph.order:
        doc = snapshot.states.get(nid) or {}
        cur = doc.get("current") or {}
        old_fp, old_m = cur.get("fingerprint"), cur.get("manifest")
        if not old_fp or not old_m or old_fp == fps[nid]:
            continue
        if nid in affected:
            out[nid] = "affected"
            continue
        if nid in live or doc.get("running"):
            out[nid] = "busy"
            continue
        failure = doc.get("last_failure") or {}
        if failure.get("fingerprint") == fps[nid]:
            out[nid] = "failed"
            continue
        why = reasons.classify(old_m, manifests[nid], rows=snapshot.rows,
                               states=snapshot.states)
        if not _eligible(why, old_m, manifests[nid]):
            out[nid] = "kept_stale:" + ",".join(sorted({r["category"] for r in why}))
            continue
        out[nid] = "rebased"
        if dry_run:
            continue
        db[state.COLLECTION].update_one(
            {"_id": state.state_id(account_id, nid), "current.fingerprint": old_fp},
            {"$set": {"current.manifest": manifests[nid],
                      "current.fingerprint": fps[nid],
                      "current.rebased": {"at": datetime.now(UTC), "from": old_fp,
                                          "reasons": sorted({r["category"] for r in why}),
                                          "by": label or "rebase"},
                      "updated_at": datetime.now(UTC)},
             "$inc": {"rev": 1}})
    return out
