"""What a node's output was built from, and the fingerprint of that.

A manifest lists exactly the inputs that can change a node's output - dataset
contents, the committed output of each upstream node, the node's own logic
version, scoring config, knowledge corpora, account settings and the model -
and nothing else. The fingerprint is its hash. Two runs with the same
fingerprint are expected to produce the same output; a stored output whose
fingerprint differs from the one the current inputs produce is stale.

Three deliberate choices:

  * **Dataset versions come from stored content hashes only.** Files live on
    one machine's disk, but the database is shared. A version that depended on
    whether this machine has the file would differ between hosts, and two hosts
    would each see the other's output as stale forever. Whether the file is
    present is a question for the worker about to run, not part of the version.

  * **Upstream nodes contribute their committed OUTPUT hash**, not their input
    fingerprint. An upstream that regenerates to identical content leaves its
    dependents current - that is what stops one upload from rippling through
    every model-backed feature when nothing they read actually changed.

  * **Wall-clock time and case-study allocation are excluded.** Including
    "today" would make every node stale every day; allocation was ruled a
    non-invalidating read.
"""

import hashlib
import importlib
import json
import logging
import threading
import time
from datetime import date, datetime

from app.services.regen import context as run_context

logger = logging.getLogger(__name__)

NONE = "none"

# Keys stripped from output before hashing. They change on every run, or on
# uploads the output does not depend on, and would otherwise make every rerun
# look like a change - which defeats early cutoff and cascades regeneration
# through every dependent. Pinned by a test that runs each producer twice.
VOLATILE_KEYS = frozenset({
    "updated_at", "extracted_at", "generated_at", "created_at", "scored_on",
    "as_of_date", "as_of", "computed_at", "refreshed_at", "last_refreshed",
    "generation_id", "rev", "_id",
})
VOLATILE_PREFIXES = ("data_as_of",)
VOLATILE_SUFFIXES = ("_refreshed_at", "_generated_at", "_updated_at", "_uploaded_at")


def _default(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, set | frozenset):
        return sorted(value, key=str)
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    return str(value)


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=_default)


def digest(value) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _is_volatile(key) -> bool:
    key = str(key)
    return (key in VOLATILE_KEYS or key.startswith(VOLATILE_PREFIXES)
            or key.endswith(VOLATILE_SUFFIXES))


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if not _is_volatile(k)}
    if isinstance(value, list | tuple):
        return [strip_volatile(v) for v in value]
    return value


def output_hash(widgets: dict, extra=None) -> str:
    """Hash of what a node published, ignoring run-to-run noise."""
    return digest({"widgets": strip_volatile(widgets or {}), "extra": extra})


def fingerprint(manifest: dict) -> str:
    return digest(manifest)


# ---------------------------------------------------------------------------
# Logic versions
# ---------------------------------------------------------------------------

_ref_cache: dict = {}


def _resolve_ref(ref: str):
    if ref in _ref_cache:
        return _ref_cache[ref]
    module_path, _, name = ref.partition(":")
    value = getattr(importlib.import_module(module_path), name)
    _ref_cache[ref] = value
    return value


def logic(node) -> dict:
    """The node's logic version: its own counter plus every referenced
    prompt/dictionary constant.

    `total` is what the downgrade guard compares. It only ever grows as long as
    no referenced integer is ever lowered - which is the rule for them anyway.
    """
    refs = {ref: _resolve_ref(ref) for ref in node.logic_refs}
    total = int(node.logic_version) + sum(v for v in refs.values()
                                          if isinstance(v, int) and not isinstance(v, bool))
    return {"own": int(node.logic_version), "refs": refs, "total": total}


# ---------------------------------------------------------------------------
# Versions of things outside the account
# ---------------------------------------------------------------------------

class Versions:
    """Config, knowledge and model versions, cached briefly.

    A sweep computes manifests for every node of every account; reading the
    four knowledge version documents each time would be thousands of queries
    for values that change a few times a month.
    """

    def __init__(self, db, ttl_seconds: float = 60.0):
        self.db = db
        self.ttl = ttl_seconds
        self._cache: dict = {}
        self._lock = threading.Lock()

    def _cached(self, key, compute):
        now = time.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < self.ttl:
                return hit[1]
        value = compute()
        with self._lock:
            self._cache[key] = (now, value)
        return value

    def config(self, section: str) -> str:
        from app.config import scoring
        return self._cached(("config", section), lambda: scoring.version(section))

    def knowledge(self, name: str) -> str:
        return self._cached(("knowledge", name), lambda: self._knowledge(name))

    def _knowledge(self, name: str) -> str:
        if name == "rulebook":
            from app.services.hp import rulebook
            return rulebook.knowledge_version(self.db) or NONE
        if name == "case_studies":
            from app.services.hp import case_studies
            return case_studies.knowledge_version(self.db) or NONE
        if name == "product_knowledge":
            from app.services.hp import recommendations
            return recommendations.knowledge_version(self.db) or NONE
        if name == "lifecycle":
            # The lifecycle loader stores no version document, so the version is
            # the content itself. The whole collection is a few hundred rows.
            rows = sorted(self.db["hp_lifecycle"].find({}), key=lambda r: str(r.get("_id")))
            return digest(rows) if rows else NONE
        raise KeyError(name)

    def models(self) -> dict:
        from app.config.settings import settings
        # The provider is part of it: the same model name on two providers is
        # not the same model, and a switch must invalidate every LLM node.
        return {"provider": settings.llm_provider,
                "chat": settings.chat_model,
                "retrieval": settings.retrieval_model,
                "embedding": settings.embedding_identity}


class StaticVersions:
    """Fixed versions, for tests and dry runs."""

    def __init__(self, config=None, knowledge=None, models=None):
        self._config = dict(config or {})
        self._knowledge = dict(knowledge or {})
        self._models = dict(models or {"chat": "test-model"})

    def config(self, section):
        return self._config.get(section, NONE)

    def knowledge(self, name):
        return self._knowledge.get(name, NONE)

    def models(self):
        return dict(self._models)


# ---------------------------------------------------------------------------
# One account's inputs
# ---------------------------------------------------------------------------

def dataset_version(rows: list) -> str:
    """Version of one dataset for one account, from its active rows' content.

    Content only: re-uploading identical bytes creates a new row but must not
    make anything stale. Which rows a run actually read is recorded on the
    generation for audit (`dataset_rows`), outside the fingerprint.

    A row uploaded before content hashes existed and not yet backfilled
    contributes its own id: stable, the same on every host, and it changes when
    the row is replaced - which is all a version has to do.
    """
    if not rows:
        return NONE
    parts = sorted(str(r.get("content_sha256") or "unhashed:%s" % r.get("_id"))
                   for r in rows)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def account_record_hash(account: dict | None) -> str:
    account = account or {}
    return digest({"name": str(account.get("name") or "").strip(),
                   "domain": str(account.get("domain") or "").strip().lower()})


def account_config_hash(instructions: dict | None, guardrails: dict | None) -> str:
    instructions, guardrails = instructions or {}, guardrails or {}
    return digest({"instructions": instructions.get("instructions_text") or "",
                   "guardrails": guardrails.get("guardrails_text") or "",
                   "guardrails_enabled": guardrails.get("enabled")})


def expected(node, snapshot, versions) -> dict:
    """The manifest this node would be built from if it ran now.

    `snapshot` is an `engine.AccountSnapshot`: active rows by dataset, committed
    node states, and the account-level hashes.
    """
    manifest = {
        "node": node.id,
        "logic": logic(node),
        "datasets": {key: dataset_version(snapshot.rows.get(key) or [])
                     for key in node.datasets},
        "upstream": {up: snapshot.output_hash(up) for up in node.upstream},
    }
    if node.config:
        manifest["config"] = {s: versions.config(s) for s in node.config}
    if node.knowledge:
        manifest["knowledge"] = {k: versions.knowledge(k) for k in node.knowledge}
    if node.account_config:
        manifest["account_config"] = snapshot.account_config
    if node.account_record:
        manifest["account_record"] = snapshot.account_record
    if node.llm:
        manifest["model"] = model_inputs(node, versions.models())
    return manifest


# Which model settings each kind of node actually uses. Until 29 Sep every
# model-backed node carried all four, so an embedding change made the Objection
# Playbook stale although it never embeds, and a chat-model change made every
# index stale although indexes extract with the retrieval model.
MODEL_KEYS = {"producer": ("provider", "chat"),
              "index": ("provider", "retrieval", "embedding")}


def model_inputs(node, models: dict) -> dict:
    keys = MODEL_KEYS.get(node.kind, MODEL_KEYS["producer"])
    return {k: models[k] for k in keys if k in models}


def diff(old: dict | None, new: dict) -> list:
    """Which inputs differ, as dotted keys ("datasets.technographics").

    This is the "why" recorded on a job and shown with a stale widget.
    """
    if not old:
        return ["(no previous manifest)"]
    changed = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if isinstance(a, dict) and isinstance(b, dict) and key != "logic":
            for sub in sorted(set(a) | set(b)):
                if a.get(sub) != b.get(sub):
                    changed.append("%s.%s" % (key, sub))
        else:
            changed.append(key)
    return changed


def cache_suffix() -> str:
    """A suffix for a producer's own LLM cache key.

    The producers keep their fingerprint caches as an optimisation, but those
    keys are narrower than the manifest. Without this, a config or model change
    would make the engine run the node, the cache would hit on its narrower key,
    and the old answer would be committed under the new fingerprint - current
    forever. Empty outside a run, so legacy callers keep their existing keys.
    """
    ctx = run_context.current()
    if ctx is None or not ctx.manifest:
        return ""
    m = ctx.manifest
    return digest({k: m.get(k) for k in ("logic", "config", "knowledge", "model",
                                         "account_config")})[:16]
