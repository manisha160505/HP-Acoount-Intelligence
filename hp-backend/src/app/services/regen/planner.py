"""What a regeneration request would run, and why - without running anything.

The one place that decides what work a request means. `POST /regeneration/preview`
returns its answer as is; `POST /regeneration` enqueues exactly the nodes it
marks `run`. Both call `plan()`, so a preview can never disagree with the run
that follows it.

A request names accounts (ids, exact names, or "all") and features (ids or
"all"), optionally raw node ids, plus `force` and `include_downstream`:

  * a requested node runs when it is not current - stale, failed, never run or
    degraded - or when `force` is set;
  * a node that is current is skipped, unless forced;
  * a node already queued or running is not queued again: the run attaches to
    the existing job (one effective job however often it is asked for);
  * an ancestor that is not current is added, because the engine refuses to
    build on stale input - it is listed with `needed_by` and is never forced;
  * an index node whose preconditions are unmet (blocked) is left alone unless
    forced: nothing will change until an input does, and a node that needs it
    is reported as unable to run;
  * downstream nodes are NOT added unless `include_downstream`. They are
    already marked stale wherever their ancestors are, and they show up in the
    next preview; running them is a separate decision.

Every account is read once: its snapshot, the fingerprints its inputs produce
now, and the live jobs. Nothing here writes.
"""

from bson import ObjectId

from app.services.regen import coverage, jobs, reasons, state
from app.services.regen.graph import INDEX

# The statuses the admin page groups nodes by. They refine state.derive's
# lifecycle with what the queue and the committed quality say.
RUNNING = "RUNNING"
QUEUED = "QUEUED"
FAILED = "FAILED"
STALE = "STALE"
NEVER_RUN = "NEVER_RUN"
DEGRADED = "DEGRADED"
BLOCKED = "BLOCKED"
# A section whose own data files are recorded in the database but not on this
# server's disk. It cannot run here until they are uploaded again (28-29 Sep:
# Accenture, Advantest and Astra's filings each showed as "queued" for hours
# while the worker kept handing them back).
FILES_MISSING = "FILES_MISSING"
# Not one file uploaded for anything the section is built from (its own
# datasets or an ancestor's). Running it would spend model calls on an empty
# account, so the planner never does unless forced; it used to show as
# "never run", which hid that the fix is an upload, not a Submit.
NO_DATA = "NO_DATA"
CURRENT = "CURRENT"
NEEDS_RUN = (FAILED, STALE, NEVER_RUN, DEGRADED)

RUN = "run"
SKIP_CURRENT = "skip_current"
IN_PROGRESS = "in_progress"
CANNOT_RUN = "cannot_run"


class PlanError(ValueError):
    """A request that names something that does not exist."""


def node_status(entry: dict, job: dict | None) -> str:
    lifecycle = entry["lifecycle"]
    if job and job.get("status") == jobs.RUNNING:
        return RUNNING
    if job and job.get("status") == jobs.PENDING:
        return QUEUED
    if lifecycle == state.CURRENT:
        return DEGRADED if entry.get("quality") == state.DEGRADED else CURRENT
    if lifecycle == state.FAILED:
        return FAILED
    if lifecycle == state.NEVER_GENERATED:
        return NEVER_RUN
    if entry.get("blocked"):
        return BLOCKED
    return STALE


def account_view(engine, account_id: str) -> dict:
    """Every node of one account: status, why, the live job and the last error.

    This is what the admin page's Pipeline panel shows and what `plan()` works
    from. Costs a few queries and no model calls.
    """
    from app.services.regen.engine import load_snapshot

    snapshot = load_snapshot(engine.db, account_id)
    manifests, fps = engine.expected_all(snapshot)
    live = jobs.live(engine.db, account_id)
    derived = state.derive(engine.graph, snapshot.states, fps, live,
                           rows=snapshot.rows)
    account_name = _account_name(engine.db, account_id)
    provided = {k for k, rows in snapshot.rows.items() if rows}

    nodes = {}
    for nid in engine.graph.order:
        node = engine.graph[nid]
        entry = derived[nid]
        doc = snapshot.states.get(nid) or {}
        current = doc.get("current") or {}
        job = live.get(nid)
        # A queued job the worker handed back because files were missing. It
        # is not going to run by waiting, so it does not count as queued.
        handed_back = bool(job and job.get("status") == jobs.PENDING
                           and job.get("not_runnable_on"))
        status = node_status(entry, None if handed_back else job)

        # The section's own files - the ones a run pins and opens. Checked on
        # this server's disk, which is where the worker runs.
        missing = [r for key in node.datasets for r in snapshot.rows.get(key) or []
                   if not engine.file_exists(r)]
        if missing and (handed_back or status in NEEDS_RUN):
            status = FILES_MISSING

        why = []
        if status == NEVER_RUN:
            why.append(reasons._reason(reasons.NEVER, "Never generated for this account"))
        elif current and not current.get("fingerprint"):
            why.extend(reasons.classify(None, manifests[nid]))      # legacy
        elif current and current.get("fingerprint") != fps[nid]:
            why.extend(reasons.classify(current.get("manifest"), manifests[nid],
                                        rows=snapshot.rows, states=snapshot.states))
        if status == FAILED and entry.get("last_error"):
            err = entry["last_error"]
            why.insert(0, reasons._reason(
                reasons.FAILED, err.get("code") or "error",
                str(err.get("message") or "")[:300]))
        if entry.get("blocked_by"):
            why.extend(reasons.waiting_on(entry["blocked_by"], derived))
        if missing:
            why.insert(0, reasons.files_missing(missing))

        # A section with no uploaded file anywhere in what it is built from
        # has nothing to generate from: running it would spend model calls on
        # an empty account. A section that reads no dataset at all (Strategy
        # snapshot) counts as having data when an ancestor does.
        closure = set(node.datasets)
        for up in engine.graph.ancestors(nid):
            closure.update(engine.graph[up].datasets)
        has_data = engine.graph.has_data(nid, snapshot.rows)
        if not has_data and status in NEEDS_RUN:
            status = NO_DATA
            why.insert(0, reasons.no_data(sorted(closure)))
        # The section's own datasets with no file for this account: the data
        # gaps to fill. It may still run on the rest, with less to go on. One
        # another source already fills for the same card is listed apart as
        # covered (regen/coverage.py) - unless the section has nothing to run
        # on, where the cover shows nothing either.
        not_provided, covered = [], []
        for k in sorted(k for k in node.datasets if not snapshot.rows.get(k)):
            by = None if status == NO_DATA else coverage.covered_by(k, account_name, provided)
            if by:
                covered.append({"dataset": k, "label": reasons.dataset_label(k), "covered_by": by})
            else:
                not_provided.append(k)

        nodes[nid] = {
            "node_id": nid,
            "label": reasons.node_label(nid),
            "feature": node.feature,
            "feature_label": reasons.feature_label(node.feature),
            "kind": node.kind,
            "llm": bool(node.llm),
            "status": status,
            "lifecycle": entry["lifecycle"],
            "quality": entry.get("quality"),
            "reasons": why,
            "categories": reasons.categories(why),
            "blocked_by": entry.get("blocked_by"),
            "generated_at": entry.get("generated_at"),
            "last_error": entry.get("last_error"),
            "job": _job_view(job),
            "upstream": list(node.upstream),
            "has_data": has_data,
            "datasets": sorted(closure),
            "datasets_not_provided": [{"dataset": k, "label": reasons.dataset_label(k)}
                                      for k in not_provided],
            "datasets_covered": covered,
            "missing_files": [{"dataset": r.get("dataset_key") or r.get("category"),
                               "label": reasons.dataset_label(
                                   str(r.get("dataset_key") or r.get("category") or "")),
                               "file": r.get("original_filename") or r.get("stored_filename"),
                               "path": r.get("file_path")} for r in missing],
            "handed_back": handed_back,
        }
    return {"account_id": account_id, "nodes": nodes, "derived": derived,
            "fingerprints": fps, "data_gaps": data_gaps(nodes),
            "data_covered": data_covered(nodes)}


def _account_name(db, account_id: str) -> str:
    if not ObjectId.is_valid(str(account_id)):
        return ""
    doc = db["accounts"].find_one({"_id": ObjectId(str(account_id))}, {"name": 1})
    return (doc or {}).get("name") or ""


def data_gaps(nodes: dict) -> list:
    """Every dataset some section reads but this account has no file for,
    with the sections that read it - what to upload, in one list."""
    gaps: dict = {}
    for n in nodes.values():
        for d in n["datasets_not_provided"]:
            entry = gaps.setdefault(d["dataset"], {**d, "sections": [], "blocks": []})
            entry["sections"].append(n["label"])
            if n["status"] == NO_DATA:
                entry["blocks"].append(n["label"])
    # The ones that leave a section with nothing at all to build from first.
    return sorted(gaps.values(), key=lambda g: (not g["blocks"], g["label"].lower()))


def data_covered(nodes: dict) -> list:
    """Every unprovided dataset another source fills, with what fills it and
    the sections that read it - not gaps, listed so nothing is hidden."""
    out: dict = {}
    for n in nodes.values():
        for d in n["datasets_covered"]:
            out.setdefault(d["dataset"], {**d, "sections": []})["sections"].append(n["label"])
    return sorted(out.values(), key=lambda c: c["label"].lower())


def _job_view(job: dict | None) -> dict | None:
    if not job:
        return None
    return {"id": str(job.get("_id")), "status": job.get("status"),
            "requested_at": job.get("requested_at"), "started_at": job.get("started_at"),
            "progress": job.get("progress"), "force": bool(job.get("force")),
            "run_ids": [str(r) for r in (job.get("run_ids") or [])],
            "attempts": int(job.get("attempts") or 0)}


def resolve_accounts(db, accounts) -> list:
    """Account ids for "all", a list of ids, or a list of exact names."""
    if accounts in ("all", ["all"]):
        return [(str(a["_id"]), a.get("name") or "") for a in
                db["accounts"].find({}, {"name": 1}).sort("name", 1)]
    if isinstance(accounts, str):
        accounts = [accounts]
    out = []
    for ref in accounts or []:
        ref = str(ref or "").strip()
        doc = None
        if ObjectId.is_valid(ref):
            doc = db["accounts"].find_one({"_id": ObjectId(ref)}, {"name": 1})
        if doc is None:
            doc = db["accounts"].find_one({"name": ref}, {"name": 1})
        if doc is None:
            raise PlanError("account %r not found" % ref)
        out.append((str(doc["_id"]), doc.get("name") or ""))
    if not out:
        raise PlanError("name at least one account, or \"all\"")
    return out


def resolve_nodes(graph, features=None, nodes=None) -> list:
    """Requested node ids, in dependency order."""
    wanted = set()
    if nodes:
        for nid in nodes:
            if nid not in graph:
                raise PlanError("unknown section %r" % nid)
            wanted.add(nid)
    if features in ("all", ["all"]) or (not features and not nodes):
        wanted.update(graph.order)
    elif features:
        for fid in ([features] if isinstance(features, str) else features):
            nids = graph.nodes_for_feature(fid)
            if not nids:
                raise PlanError("unknown feature %r" % fid)
            wanted.update(nids)
    return [n for n in graph.order if n in wanted]


def plan_account(engine, account_id: str, requested: list, *, force: bool = False,
                 include_downstream: bool = False, view: dict | None = None) -> dict:
    view = view or account_view(engine, account_id)
    graph, nodes = engine.graph, view["nodes"]
    wanted = set(requested)
    if include_downstream:
        for nid in requested:
            wanted |= graph.descendants(nid)

    decisions = {}

    def decide(nid, needed_by=None):
        n = nodes[nid]
        if n["status"] in (RUNNING, QUEUED):
            return IN_PROGRESS
        if n["status"] == FILES_MISSING:
            return CANNOT_RUN
        if needed_by is None and force:
            return RUN
        if n["status"] == BLOCKED or not n["has_data"]:
            return CANNOT_RUN
        if n["status"] in NEEDS_RUN:
            return RUN
        # Current, but asked for only because a descendant was: nothing to do.
        return SKIP_CURRENT

    for nid in graph.order:
        if nid in wanted:
            decisions[nid] = {"action": decide(nid), "needed_by": [], "forced": False}

    # Ancestors that must be current before a planned node can be built. One
    # with no data at all (Hiring on an account with no job file) is not
    # waited for: it will never be built, and the node runs without it, the
    # same way a section runs on the datasets it has.
    for nid in list(graph.order):
        d = decisions.get(nid)
        if not d or d["action"] != RUN:
            continue
        for up in graph.ancestors(nid):
            if nodes[up]["status"] in (CURRENT, DEGRADED) or not nodes[up]["has_data"]:
                continue
            if up in decisions and decisions[up]["action"] != SKIP_CURRENT:
                decisions[up]["needed_by"].append(nid)
                continue
            action = decide(up, needed_by=nid)
            decisions[up] = {"action": action, "needed_by": [nid], "forced": False}

    # A node whose ancestor can never become current in this run cannot run.
    for nid in graph.order:
        d = decisions.get(nid)
        if not d or d["action"] != RUN:
            continue
        stuck = [up for up in graph.ancestors(nid)
                 if decisions.get(up, {}).get("action") == CANNOT_RUN
                 and nodes[up]["has_data"]]
        if stuck:
            d["action"] = CANNOT_RUN
            d["blocked_by"] = stuck

    items = []
    for nid in graph.order:
        if nid not in decisions:
            continue
        d, n = decisions[nid], nodes[nid]
        forced = d["action"] == RUN and force and nid in wanted \
            and n["status"] not in NEEDS_RUN
        items.append({**{k: n[k] for k in ("node_id", "label", "feature", "feature_label",
                                           "kind", "llm", "status", "reasons",
                                           "categories", "job")},
                      "action": d["action"], "forced": forced,
                      "requested": nid in wanted,
                      "needed_by": sorted(set(d["needed_by"]), key=graph.rank),
                      "blocked_by": d.get("blocked_by") or n.get("blocked_by"),
                      "has_data": n["has_data"],
                      "missing_files": n["missing_files"],
                      "handed_back": n["handed_back"]})
    counts = {a: sum(1 for i in items if i["action"] == a)
              for a in (RUN, SKIP_CURRENT, IN_PROGRESS, CANNOT_RUN)}
    counts["llm_sections"] = sum(1 for i in items if i["action"] == RUN and i["llm"])
    counts["index_builds"] = sum(1 for i in items
                                 if i["action"] == RUN and i["kind"] == INDEX)
    # What stays behind: downstream of what runs, not asked for.
    running = {i["node_id"] for i in items if i["action"] == RUN}
    left_stale = sorted({d for nid in running for d in graph.descendants(nid)}
                        - set(decisions), key=graph.rank)
    return {"account_id": account_id, "items": items, "counts": counts,
            "downstream_left_stale": left_stale}


def plan(engine, *, accounts, features=None, nodes=None, force: bool = False,
         include_downstream: bool = False) -> dict:
    """The whole request: one entry per account, and totals."""
    requested = resolve_nodes(engine.graph, features, nodes)
    out, totals = [], {RUN: 0, SKIP_CURRENT: 0, IN_PROGRESS: 0, CANNOT_RUN: 0,
                       "llm_sections": 0, "index_builds": 0,
                       "accounts": 0, "accounts_with_work": 0}
    for account_id, name in resolve_accounts(engine.db, accounts):
        entry = plan_account(engine, account_id, requested, force=force,
                             include_downstream=include_downstream)
        entry["account_name"] = name
        out.append(entry)
        totals["accounts"] += 1
        if entry["counts"][RUN]:
            totals["accounts_with_work"] += 1
        for key, value in entry["counts"].items():
            totals[key] = totals.get(key, 0) + value
    return {"request": {"accounts": accounts, "features": features, "nodes": nodes,
                        "force": bool(force),
                        "include_downstream": bool(include_downstream)},
            "requested_nodes": requested, "accounts": out, "totals": totals}
