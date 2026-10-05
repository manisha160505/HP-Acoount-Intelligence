"""The plain-English rule book behind the admin Rules page.

Each feature has one file in `catalog/`, named by its WIDGET_REGISTRY key. The
prose in it (what a rule is for, how to read it) has to be written by a person,
but nothing a reader could act on is copied by hand:

  numbers   are references, not literals. `{{scoring:urgency.weights.workplace_os|pct}}`
            in any text field, or `ref:` on a constant, is read from
            config/scoring.yaml or the Python constant at request time. Retune
            a weight and the Rules page shows the new weight.

  constants carry the value the prose was written against (`stated`) beside
            the reference. When the live value differs the constant is marked
            `stale` and the page says so - the prompt to re-read the prose
            around it. tests/test_rules_catalog.py fails on any stale constant.

  examples  are recomputed by tests/test_rules_examples.py, which calls the
            real functions with each example's inputs and asserts the result
            the catalog states. A rule whose example is pinned there is marked
            `verified` (the test proves every such id has a test). Nothing in
            this module runs code named in a catalog file: it reads constant
            values, never calls them.

  sources   name `path:function`. The test checks the function still exists in
            that file, so a rename or a move breaks the build, not the page.

What this cannot catch is a change in behaviour that keeps the numbers, the
example results and the function names - a new filter, say. Those still need
the catalog edited by whoever changes the rule; the `sources` list is where to
look first.

Nothing here changes how a feature behaves. It reads the same config and calls
the same functions the features call.
"""

from __future__ import annotations

import importlib
import logging
import math
import re
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.config import scoring

logger = logging.getLogger(__name__)

CATALOG_DIR = Path(__file__).resolve().parent / "catalog"

# {{ ref }} or {{ ref|format }} inside any text field.
_PLACEHOLDER = re.compile(r"\{\{\s*([^}|]+?)\s*(?:\|\s*([a-z0-9_]+)\s*)?\}\}")

# Text fields that may carry placeholders. Lists of strings are covered too.
_TEXT_FIELDS = ("summary", "purpose", "logic", "formula", "output", "doc_source")


# The only modules a `py:` reference may read a constant from.
_REF_MODULES = ("app.services.", "app.config.")


class RulesCatalogError(RuntimeError):
    """A catalog file cannot be read or refers to something that does not exist."""


# --------------------------------------------------------------------------- refs

def _walk(value: Any, path: list[str], ref: str) -> Any:
    for part in path:
        if isinstance(value, dict):
            if part in value:
                value = value[part]
            elif part.isdigit() and int(part) in value:
                value = value[int(part)]
            else:
                raise RulesCatalogError("%s: no key %r" % (ref, part))
        elif isinstance(value, (list, tuple)) and part.lstrip("-").isdigit():
            value = value[int(part)]
        else:
            try:
                value = getattr(value, part)
            except AttributeError as exc:
                raise RulesCatalogError("%s: no attribute %r" % (ref, part)) from exc
    return value


def resolve_ref(ref: str) -> Any:
    """Read the live value a catalog reference points at.

    scoring:<section>.<key>[.<key>...]   config/scoring.yaml, as loaded
    py:<module>:<NAME>[.<key>...]        a module-level constant, then keys/indexes
    """
    kind, _, rest = ref.partition(":")
    if kind == "scoring":
        name, *path = rest.split(".")
        return _walk(scoring.section(name), path, ref)
    if kind == "py":
        module_name, _, attr = rest.partition(":")
        if not attr:
            raise RulesCatalogError("%s: expected py:<module>:<NAME>" % ref)
        if not module_name.startswith(_REF_MODULES):
            raise RulesCatalogError("%s: only app.services and app.config are readable" % ref)
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            raise RulesCatalogError("%s: cannot import %s" % (ref, module_name)) from exc
        value = _walk(module, attr.split("."), ref)
        if callable(value):
            raise RulesCatalogError("%s: is a function or class, not a value" % ref)
        return value
    raise RulesCatalogError("%s: unknown reference kind %r" % (ref, kind))


def _num(value: float) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int) or float(value).is_integer():
        return f"{int(value):,}"
    return ("%.4f" % value).rstrip("0").rstrip(".")


def format_value(value: Any, fmt: str | None = None) -> str:
    """How a resolved value reads in prose. `pct` turns 0.25 into 25%,
    `count` a collection into its size."""
    if fmt == "count" and isinstance(value, (list, tuple, set, frozenset, dict)):
        return _num(len(value))
    if fmt == "pct" and isinstance(value, (int, float)):
        return "%s%%" % _num(value * 100)
    if fmt == "x" and isinstance(value, (int, float)):
        return "×%s" % _num(value)
    if fmt == "list" and isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return ", ".join(str(v) for v in items)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _num(value)
    if isinstance(value, (set, frozenset)):
        return ", ".join(sorted(str(v) for v in value))
    if isinstance(value, dict):
        return "; ".join("%s → %s" % (k, format_value(v)) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        # A band table: [(threshold, points), ...] reads as "threshold → points".
        if value and all(isinstance(v, (list, tuple)) and len(v) == 2 for v in value):
            return "; ".join("%s → %s" % (format_value(a), format_value(b)) for a, b in value)
        return ", ".join(format_value(v) for v in value)
    return str(value)


def interpolate(text: str | None) -> str | None:
    if not text or "{{" not in text:
        return text
    return _PLACEHOLDER.sub(lambda m: format_value(resolve_ref(m.group(1)), m.group(2)), text)


# ---------------------------------------------------------------------- comparing

def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
        return [_jsonable(v) for v in items]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "__dict__"):
        return {k: _jsonable(v) for k, v in vars(value).items() if not k.startswith("_")}
    return str(value)


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b or a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-6)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b, strict=True))
    return a == b


# ------------------------------------------------------------------------ loading

@cache
def _raw(feature_key: str) -> dict:
    path = CATALOG_DIR / ("%s.yaml" % feature_key)
    if not path.exists():
        raise RulesCatalogError("no rules catalog for feature %r" % feature_key)
    with path.open(encoding="utf-8") as handle:
        doc = yaml.safe_load(handle) or {}
    if doc.get("feature_key") != feature_key:
        raise RulesCatalogError("%s declares feature_key %r" % (path.name, doc.get("feature_key")))
    return doc


def catalog_keys() -> list[str]:
    return sorted(p.stem for p in CATALOG_DIR.glob("*.yaml"))


def _resolve_rule(rule: dict) -> dict:
    out = dict(rule)
    for field in _TEXT_FIELDS:
        if isinstance(out.get(field), str):
            out[field] = interpolate(out[field])
    for field in ("inputs", "conditions"):
        if out.get(field):
            out[field] = [interpolate(s) if isinstance(s, str) else s for s in out[field]]
    if out.get("table"):
        table = dict(out["table"])
        table["rows"] = [[interpolate(c) if isinstance(c, str) else c for c in row]
                         for row in table.get("rows") or []]
        out["table"] = table
    if out.get("constants"):
        consts = []
        for c in out["constants"]:
            c = dict(c)
            if c.get("ref"):
                try:
                    live = resolve_ref(c["ref"])
                    c["value"] = format_value(live, c.get("format"))
                    if "stated" in c:
                        if c.get("format") == "count" and hasattr(live, "__len__"):
                            live = len(live)
                        c["stale"] = not _same(_jsonable(live), _jsonable(c["stated"]))
                except RulesCatalogError as exc:
                    c["value"] = None
                    c["error"] = str(exc)
            consts.append(c)
        out["constants"] = consts
    example = out.get("example")
    if example:
        example = dict(example)
        for field in ("scenario", "result"):
            if isinstance(example.get(field), str):
                example[field] = interpolate(example[field])
        if example.get("steps"):
            example["steps"] = [interpolate(s) for s in example["steps"]]
        out["example"] = example
    return out


def feature_rules(feature_key: str) -> dict:
    """One feature's rule book with every reference resolved against live config."""
    doc = _raw(feature_key)
    rules = [_resolve_rule(r) for r in doc.get("rules") or []]
    return {
        "feature_key": feature_key,
        "purpose": interpolate(doc.get("purpose")),
        "final_output": interpolate(doc.get("final_output")),
        "how_it_combines": interpolate(doc.get("how_it_combines")),
        "rules": rules,
        "undetermined": doc.get("undetermined") or [],
        "discrepancies": doc.get("discrepancies") or [],
    }


# --------------------------------------------------------------- reader's view
#
# What the Rules page shows a business reader: the rule in plain English and
# nothing about where it lives. Source paths, document names, live-value
# references, the code's raw example output and the authoring flags stay in
# the catalog for maintainers and tests, and are never sent to the page.
# A rule marked `internal: true` (software mechanics such as caching or
# rebuild timing) is left out together with everything beneath it.

_READER_RULE_FIELDS = ("id", "parent", "name", "kind", "summary", "purpose", "inputs", "logic",
                       "formula", "conditions", "table", "output", "uses")


def _visible(rules: list[dict]) -> list[dict]:
    hidden = {r["id"] for r in rules if r.get("internal")}
    by_id = {r["id"]: r for r in rules}

    def under_hidden(rule: dict) -> bool:
        parent = rule.get("parent")
        while parent:
            if parent in hidden:
                return True
            parent = (by_id.get(parent) or {}).get("parent")
        return False

    return [r for r in rules if r["id"] not in hidden and not under_hidden(r)]


# A snake_case name such as `exec_key_metrics` or `apollo_match_status`.
_IDENTIFIER = re.compile(r"\b[a-z0-9]+_[a-z0-9_]+\b")


def _is_bookkeeping(constant: dict) -> bool:
    """Not for the page: version stamps, software settings marked `internal`,
    and lists of internal names (section keys, column names, file names)."""
    if constant.get("internal") or "VERSION" in (constant.get("ref") or ""):
        return True
    if "version" in constant["label"].lower():
        return True
    return len(_IDENTIFIER.findall(format_value(constant.get("value")))) >= 1


def _reader_rule(rule: dict) -> dict:
    out = {k: rule[k] for k in _READER_RULE_FIELDS if rule.get(k) not in (None, "", [])}
    consts = [{"label": c["label"], "value": format_value(c["value"])}
              for c in rule.get("constants") or []
              if c.get("value") not in (None, "") and not c.get("error") and not _is_bookkeeping(c)]
    if consts:
        out["constants"] = consts
    example = rule.get("example") or {}
    shown = {k: example[k] for k in ("scenario", "steps", "result") if example.get(k)}
    if shown:
        shown["verified"] = bool(example.get("verified"))
        out["example"] = shown
    return out


def reader_view(feature_key: str) -> dict:
    full = feature_rules(feature_key)
    return {
        "feature_key": feature_key,
        "purpose": full["purpose"],
        "final_output": full["final_output"],
        "how_it_combines": full["how_it_combines"],
        "rules": [_reader_rule(r) for r in _visible(full["rules"])],
    }


def reader_summary(feature_key: str) -> dict:
    doc = _raw(feature_key)
    rules = _visible(doc.get("rules") or [])
    return {
        "feature_key": feature_key,
        "purpose": interpolate(doc.get("purpose")),
        "rule_count": len(rules),
        "top_level_rules": [r["name"] for r in rules if not r.get("parent")],
    }
