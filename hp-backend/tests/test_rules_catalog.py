"""The Rules page's catalog stays tied to the code it describes.

These are the checks that make the catalog something other than a second,
hand-kept copy of the rules: every feature is covered, every number it quotes
resolves to live config or a live constant, every worked example still comes
out the way it says when the real function computes it, and every source it
names still exists. A formula change that leaves an example wrong fails here.

Run: PYTHONPATH=src python -m pytest tests/test_rules_catalog.py -v
"""

import re
from pathlib import Path

import pytest

from app.api.v1.widgets import WIDGET_REGISTRY
from app.services import rules_catalog
from auth_harness import add_user, auth, body

pytest_plugins = ["auth_harness"]

REPO_ROOT = Path(__file__).resolve().parents[2]
KINDS = {"score", "selection", "filter", "guardrail", "model", "display", "source"}
# A quoted 'TBD' is a value the code handles, not an unfinished rule.
PLACEHOLDER_TEXT = re.compile(
    r"(?<!['\"])\b(TBD|TODO|to be added|will be added|added later|lorem)\b(?!['\"])", re.I)


def _rules():
    for key in rules_catalog.catalog_keys():
        for rule in rules_catalog._raw(key).get("rules") or []:
            yield key, rule


def _ids():
    return ["%s.%s" % (k, r["id"]) for k, r in _rules()]


def test_every_feature_has_a_catalog_and_nothing_else_does():
    assert set(rules_catalog.catalog_keys()) == set(WIDGET_REGISTRY)


@pytest.mark.parametrize("key", sorted(WIDGET_REGISTRY))
def test_feature_shape(key):
    doc = rules_catalog._raw(key)
    assert doc.get("purpose") and doc.get("final_output"), key
    rules = doc.get("rules") or []
    assert rules, "%s has no rules" % key
    ids = [r["id"] for r in rules]
    assert len(ids) == len(set(ids)), "%s has duplicate rule ids" % key
    for r in rules:
        assert r.get("parent") in (None, *ids), "%s.%s: unknown parent" % (key, r["id"])
    for d in doc.get("discrepancies") or []:
        assert d.get("rule_id") in (None, *ids), "%s: discrepancy on unknown rule" % key
        assert d.get("doc") and d.get("code")


@pytest.mark.parametrize(("key", "rule"), list(_rules()), ids=_ids())
def test_rule_is_complete(key, rule):
    assert rule.get("name") and rule.get("purpose") and rule.get("logic"), rule["id"]
    assert rule.get("kind") in KINDS, rule["id"]
    assert rule.get("sources"), "%s.%s names no source" % (key, rule["id"])
    text = repr(rule)
    assert not PLACEHOLDER_TEXT.search(text), "%s.%s has placeholder text" % (key, rule["id"])


@pytest.mark.parametrize(("key", "rule"), list(_rules()), ids=_ids())
def test_sources_exist(key, rule):
    for source in rule["sources"]:
        path, _, name = source.partition(":")
        file = REPO_ROOT / path
        assert file.exists(), "%s.%s: %s does not exist" % (key, rule["id"], path)
        if name:
            n = re.escape(name)
            pattern = (r"^\s*(?:async\s+)?(?:def|class)\s+%s\b|^%s\s*[:=]"
                       r"|^\s*(?:export\s+)?(?:const|let|var|function)\s+%s\b" % (n, n, n))
            assert re.search(pattern, file.read_text(encoding="utf-8"), re.M), (
                "%s.%s: %s is not defined in %s" % (key, rule["id"], name, path))


@pytest.mark.parametrize("key", sorted(WIDGET_REGISTRY))
def test_every_reference_resolves_and_matches_what_the_prose_says(key):
    resolved = rules_catalog.feature_rules(key)
    for rule in resolved["rules"]:
        for c in rule.get("constants") or []:
            assert not c.get("error"), "%s.%s: %s" % (key, rule["id"], c["error"])
            assert not c.get("stale"), "%s.%s: %s is now %s, the text says %r" % (
                key, rule["id"], c["ref"], c["value"], c["stated"])


def test_interpolation_reads_live_config(monkeypatch):
    from app.config import scoring
    assert rules_catalog.interpolate("{{scoring:urgency.weights.growth_expansion|pct}}") == "30%"
    patched = dict(scoring.CONFIG["urgency"], weights={"growth_expansion": 0.4})
    monkeypatch.setitem(scoring.CONFIG, "urgency", patched)
    assert rules_catalog.interpolate("{{scoring:urgency.weights.growth_expansion|pct}}") == "40%"


def test_a_changed_constant_is_marked_stale(monkeypatch):
    from app.config import scoring
    rule = {"id": "r", "constants": [{"label": "w", "ref": "scoring:urgency.weights.growth_expansion",
                                      "stated": 0.3}]}
    assert rules_catalog._resolve_rule(rule)["constants"][0]["stale"] is False
    patched = dict(scoring.CONFIG["urgency"], weights={"growth_expansion": 0.4})
    monkeypatch.setitem(scoring.CONFIG, "urgency", patched)
    assert rules_catalog._resolve_rule(rule)["constants"][0]["stale"] is True


def test_references_read_values_never_functions():
    with pytest.raises(rules_catalog.RulesCatalogError):
        rules_catalog.resolve_ref("py:app.config.scoring:section")
    with pytest.raises(rules_catalog.RulesCatalogError):
        rules_catalog.resolve_ref("py:os:sep")


@pytest.fixture
def rules_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.v1.rules import router
    from app.errors import register_error_handlers
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    return TestClient(app)


def test_endpoint_is_admin_only(db, rules_client):
    admin = add_user(db, "boss@example.com", role="admin")
    seller = add_user(db, "seller@example.com")
    r = rules_client.get("/api/v1/admin/rules", headers=auth(admin))
    assert r.status_code == 200, r.text
    data = body(r)
    assert data["missing"] == []
    assert [f["feature_key"] for f in data["features"]] == list(WIDGET_REGISTRY)
    r = rules_client.get("/api/v1/admin/rules/executive_dashboard", headers=auth(admin))
    assert r.status_code == 200 and body(r)["rules"]
    assert rules_client.get("/api/v1/admin/rules/nope", headers=auth(admin)).status_code == 404
    assert rules_client.get("/api/v1/admin/rules", headers=auth(seller)).status_code == 403


# What a business reader must never see on the Rules page: fields that point
# into the code or documents, and file or code references inside the text.
INTERNAL_FIELDS = {"sources", "doc_source", "confidence", "uncommitted", "internal", "ref", "stated",
                   "format", "expect", "error", "stale"}
INTERNAL_TEXT = re.compile(r"\.py\b|hp-backend|hp-frontend|\.docx\b|\.yaml\b|py:app|scoring:|_FINAL\b", re.I)


@pytest.mark.parametrize("key", sorted(WIDGET_REGISTRY))
def test_reader_view_carries_no_code_or_document_references(key):
    import json
    view = rules_catalog.reader_view(key)
    for rule in view["rules"]:
        fields = set(rule) | set(rule.get("example") or {})
        fields |= {f for c in rule.get("constants") or [] for f in c}
        assert not fields & INTERNAL_FIELDS, (rule["id"], fields & INTERNAL_FIELDS)
    text = json.dumps(view, ensure_ascii=False)
    hit = INTERNAL_TEXT.search(text)
    assert not hit, "%s: reader view mentions %r" % (key, text[max(0, hit.start() - 80):hit.end() + 80])


def test_internal_rules_and_their_parts_are_hidden(monkeypatch):
    rules = [{"id": "a", "name": "A"}, {"id": "b", "name": "B", "internal": True},
             {"id": "c", "parent": "b", "name": "C"}, {"id": "d", "parent": "a", "name": "D"}]
    assert [r["id"] for r in rules_catalog._visible(rules)] == ["a", "d"]


# ------------------------------------------------------------- rule books

def test_lifecycle_table_status_agrees_with_the_engine():
    """The table reads each row's status from its dates; the engine reaches a
    status by matching an offering to a row. Wherever the engine matches a row,
    both must say the same thing."""
    from datetime import date

    from app.services.hp import lifecycle
    from app.services.rules_catalog import reference
    today = date(2026, 10, 5)
    rows = [
        {"product": "HP EliteBook 840 G9 Notebook", "family": "Notebooks", "generations": ["g9"],
         "identity": ["elitebook", "840", "notebook"], "first_end": "2025-01-31", "last_end": "2026-03-31"},
        {"product": "HP EliteBook 860 G10 Notebook", "family": "Notebooks", "generations": ["g10"],
         "identity": ["elitebook", "860", "notebook"], "first_end": "2025-09-30", "last_end": "2027-06-30"},
        {"product": "HP ZBook Fury 16 G11 Mobile Workstation", "family": "Workstations",
         "generations": ["g11"], "identity": ["zbook", "fury", "16", "mobile", "workstation"],
         "first_end": "2027-06-30", "last_end": "2028-01-31"},
    ]
    for row in rows:
        engine = lifecycle.status_for(row["product"], today=today, rows=[row])
        if engine["status"] != lifecycle.NOT_LISTED:
            assert reference.lifecycle_row_status(row, today) == engine["status"], row["product"]
    assert [reference.lifecycle_row_status(r, today) for r in rows] == [
        lifecycle.PAST_END, lifecycle.APPROACHING, lifecycle.LISTED_FUTURE]


def test_reference_sets_build_and_hide_matching_aids(db):
    import json

    from app.services.rules_catalog import reference
    db["hp_rulebook"].insert_one({
        "_id": "B::care-03", "kind": "rule", "part": "B", "family": "CARE", "order": 3,
        "rule_label": "CARE 03", "offering": "HP Care Pack", "signal_text": "High ticket volume",
        "system_action": "Recommend a Care Pack.", "allowed_facts": ["Next business day onsite"],
        "conditions": [{"text": "Device must be under warranty"}], "prohibitions": [],
        "signal_tokens": ["ticket volume"], "observable_terms": ["servicenow"], "is_new": True})
    index = {s["key"]: s for s in reference.reference_index(db)}
    assert set(index) == set(reference.REFERENCE_SETS)
    assert index["hp_rulebook"]["count"] == 1
    book = reference.reference_set(db, "hp_rulebook")
    entry = book["sections"][0]["entries"][0]
    assert entry["label"] == "CARE 03" and entry["group"] == "Care Packs and support"
    assert "New in the latest revision" in entry["badges"]
    text = json.dumps(book)
    assert "servicenow" not in text and "signal_tokens" not in text
    for key in reference.REFERENCE_SETS:
        for feature in reference.REFERENCE_SETS[key]["used_by"]:
            assert feature in WIDGET_REGISTRY


def test_rule_book_links_point_at_real_rule_books():
    from app.services.rules_catalog import reference
    linked = 0
    for key in rules_catalog.catalog_keys():
        for rule in rules_catalog._raw(key)["rules"]:
            for target in rule.get("uses") or []:
                assert target in reference.REFERENCE_SETS, (key, rule["id"], target)
                assert key in reference.REFERENCE_SETS[target]["used_by"], (key, rule["id"], target)
                linked += 1
    assert linked
