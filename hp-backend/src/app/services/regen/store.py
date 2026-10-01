"""The one way to read or publish a generated widget.

Reads return the same document shape `account_widgets` rows have always had, so
a read site changes from

    db["account_widgets"].find_one({"account_id": a, "widget_key": k})
to
    widget_store.get(a, k)

and nothing downstream of it notices. What changes is where the answer comes
from:

  * **Inside a producer run** - the widget this run already staged; otherwise the
    upstream widget pinned when the run started, so everything the run reads
    agrees with the fingerprint it will be committed under; otherwise (an
    undeclared read) the live committed value, recorded so the run fails
    validation instead of silently depending on something it never declared.
  * **Outside a run** - the committed generation in `node_state`. Before the
    migration has created node states for an account, `account_widgets` is
    read instead, so switching read sites does not blank the dashboard.

User-request outputs (generated assets, angle options, the evaluator pointer)
have no owning node and are read from `account_widgets` as before.
"""

import logging
from datetime import UTC, datetime

from app.services.regen import context as run_context
from app.services.regen.graph import DEFAULT, USER_OUTPUT_WIDGETS
from app.services.regen.state import COLLECTION as STATE_COLLECTION, state_id

logger = logging.getLogger(__name__)

WIDGET_FIELDS = ("status", "data", "source_datasets", "data_classification")


def _db(db):
    if db is not None:
        return db
    from app.database.mongodb import get_db
    return get_db()


def shape(account_id: str, widget_key: str, widget: dict, graph=DEFAULT,
          generation: dict | None = None) -> dict:
    """A committed or staged widget in the legacy `account_widgets` row shape."""
    generation = generation or {}
    owner = graph.owner.get(widget_key)
    stamp = generation.get("generated_at") or widget.get("updated_at")
    return {
        "account_id": account_id,
        "widget_key": widget_key,
        "feature_key": graph[owner].feature if owner else widget.get("feature_key"),
        "status": widget.get("status", "empty"),
        "data": widget.get("data") or {},
        "source_datasets": widget.get("source_datasets") or [],
        "data_classification": widget.get("data_classification"),
        "extracted_at": stamp,
        "updated_at": stamp,
        "generation_id": generation.get("generation_id"),
        "generation_quality": generation.get("quality"),
    }


def committed(db, account_id: str, widget_key: str, graph=DEFAULT) -> dict | None:
    """The committed widget, ignoring any run context."""
    db = _db(db)
    owner = graph.owner.get(widget_key)
    if owner is None:
        return db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": widget_key})
    doc = db[STATE_COLLECTION].find_one({"_id": state_id(account_id, owner)},
                                        {"current": 1})
    if doc is None:
        # No node state at all: the account predates the engine and the
        # migration has not run for it yet.
        return db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": widget_key})
    current = doc.get("current") or {}
    widget = (current.get("widgets") or {}).get(widget_key)
    if widget is None:
        return None
    return shape(account_id, widget_key, widget, graph, current)


def committed_many(db, account_ids, widget_key: str, graph=DEFAULT) -> dict:
    """`committed` for one widget across many accounts, in two queries.

    For list views (the account picker shows every account's urgency score):
    calling `committed` per account would cost up to two round trips each.
    Resolution per account is exactly `committed`'s - node state when the
    account has one, `account_widgets` when it does not.
    """
    db = _db(db)
    account_ids = [str(a) for a in account_ids]
    owner = graph.owner.get(widget_key)
    out: dict = dict.fromkeys(account_ids)

    legacy_ids = account_ids
    if owner is not None:
        ids = {state_id(a, owner): a for a in account_ids}
        found = set()
        for doc in db[STATE_COLLECTION].find({"_id": {"$in": list(ids)}},
                                             {"current": 1}):
            account_id = ids[doc["_id"]]
            found.add(account_id)
            current = doc.get("current") or {}
            widget = (current.get("widgets") or {}).get(widget_key)
            if widget is not None:
                out[account_id] = shape(account_id, widget_key, widget, graph, current)
        legacy_ids = [a for a in account_ids if a not in found]

    if legacy_ids:
        for doc in db["account_widgets"].find(
                {"account_id": {"$in": legacy_ids}, "widget_key": widget_key}):
            out[doc["account_id"]] = doc
    return out


def get(account_id: str, widget_key: str, *, soft: bool = False, db=None,
        graph=DEFAULT) -> dict | None:
    """Read one widget. `soft=True` marks a read that must not create a
    dependency - case-study allocation (`cited_above`) is the only one."""
    ctx = run_context.current()
    if ctx is None or ctx.account_id != str(account_id):
        return committed(db, account_id, widget_key, graph)

    if widget_key in ctx.staged:
        return shape(account_id, widget_key, ctx.staged[widget_key], graph)

    if soft:
        found = committed(db, account_id, widget_key, graph)
        ctx.soft_reads[widget_key] = str((found or {}).get("generation_id") or "")
        return found

    ctx.widget_reads.add(widget_key)
    if widget_key in ctx.pinned_widgets:
        pinned = ctx.pinned_widgets[widget_key]
        return dict(pinned) if pinned is not None else None
    return committed(db, account_id, widget_key, graph)


def get_many(account_id: str, widget_keys, *, db=None, graph=DEFAULT) -> dict:
    return {k: get(account_id, k, db=db, graph=graph) for k in widget_keys}


def put(account_id: str, widget_key: str, payload: dict, *, db=None) -> None:
    """Publish one widget.

    Inside a run it is staged and committed with the rest of the run's widgets,
    or not at all. Outside a run - the legacy paths that still call extractors
    directly until they are cut over - it is written straight to
    `account_widgets` exactly as the extractors always did.
    """
    ctx = run_context.current()
    if ctx is not None and ctx.account_id == str(account_id):
        if widget_key not in ctx.owned:
            ctx.foreign_puts.append(widget_key)
            return
        ctx.staged[widget_key] = {k: payload.get(k) for k in WIDGET_FIELDS}
        return

    db = _db(db)
    body = dict(payload)
    body.setdefault("account_id", account_id)
    body.setdefault("widget_key", widget_key)
    body.setdefault("updated_at", datetime.now(UTC))
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": widget_key},
        {"$set": body}, upsert=True)


def keep(account_id: str, widget_key: str) -> dict | None:
    """Publish this node's previously committed widget unchanged.

    For a producer's own cache hit: the inputs its cache key covers are
    unchanged, so the stored widget is still the right answer. It has to be
    said explicitly - a widget a run simply did not publish fails validation,
    because silently carrying the old one forward would commit content built
    from old inputs under the new fingerprint.

    Outside a run it does nothing (the legacy paths left the row in place).
    Returns the kept widget document, or None if there is nothing to keep.
    """
    ctx = run_context.current()
    if ctx is None or ctx.account_id != str(account_id):
        return None
    if widget_key not in ctx.owned:
        ctx.foreign_puts.append(widget_key)
        return None
    previous = ctx.pinned_widgets.get(widget_key)
    if previous is None:
        return None
    ctx.staged[widget_key] = {k: previous.get(k) for k in WIDGET_FIELDS}
    return previous


def is_user_output(widget_key: str) -> bool:
    return widget_key in USER_OUTPUT_WIDGETS
