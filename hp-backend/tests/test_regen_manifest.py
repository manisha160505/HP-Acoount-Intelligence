"""Fingerprints: exact, stable, and blind to everything that is not an input.

Run: python -m pytest tests/test_regen_manifest.py -v
"""

from datetime import UTC, datetime

from app.services.regen import context as run_context, manifest
from app.services.regen.engine import AccountSnapshot
from app.services.regen.graph import Node


def _snapshot(rows=None, states=None, record="r", config="c"):
    return AccountSnapshot(account_id="acct", rows=rows or {}, states=states or {},
                           account_record=record, account_config=config)


NODE = Node("n", "f", widgets=("w",), datasets=("d1", "d2"), upstream=("up",),
            config=("urgency",), knowledge=("rulebook",), account_config=True,
            llm=True, logic_version=3)
VERSIONS = manifest.StaticVersions(config={"urgency": "u1"},
                                   knowledge={"rulebook": "k1"},
                                   models={"chat": "m1"})


def _fp(snapshot, node=NODE, versions=VERSIONS):
    return manifest.fingerprint(manifest.expected(node, snapshot, versions))


def test_fingerprint_is_deterministic_and_order_independent():
    rows = {"d1": [{"_id": 1, "content_sha256": "aa"}, {"_id": 2, "content_sha256": "bb"}]}
    reordered = {"d1": [{"_id": 2, "content_sha256": "bb"}, {"_id": 1, "content_sha256": "aa"}]}
    assert _fp(_snapshot(rows)) == _fp(_snapshot(reordered))
    assert manifest.digest({"a": 1, "b": 2}) == manifest.digest({"b": 2, "a": 1})


def test_identical_reupload_keeps_the_version_new_content_changes_it():
    old = {"d1": [{"_id": 1, "content_sha256": "aa"}]}
    same_bytes_new_row = {"d1": [{"_id": 99, "content_sha256": "aa"}]}
    new_bytes = {"d1": [{"_id": 99, "content_sha256": "cc"}]}
    assert (manifest.dataset_version(old["d1"])
            == manifest.dataset_version(same_bytes_new_row["d1"]))
    assert _fp(_snapshot(old)) != _fp(_snapshot(new_bytes))


def test_unhashed_rows_are_versioned_by_id_not_by_local_disk():
    v1 = manifest.dataset_version([{"_id": "row1"}])
    v2 = manifest.dataset_version([{"_id": "row2"}])
    assert v1 not in (v2, manifest.NONE)


def test_every_declared_input_moves_the_fingerprint():
    base = _snapshot({"d1": [{"_id": 1, "content_sha256": "a"}]},
                     {"up": {"current": {"output_hash": "h1"}}})
    fp = _fp(base)
    # an upstream output
    assert _fp(_snapshot(base.rows, {"up": {"current": {"output_hash": "h2"}}})) != fp
    # account config and record
    assert _fp(_snapshot(base.rows, base.states, config="c2")) != fp
    # config, knowledge, model
    for versions in (
            manifest.StaticVersions({"urgency": "u2"}, {"rulebook": "k1"}, {"chat": "m1"}),
            manifest.StaticVersions({"urgency": "u1"}, {"rulebook": "k2"}, {"chat": "m1"}),
            manifest.StaticVersions({"urgency": "u1"}, {"rulebook": "k1"}, {"chat": "m2"})):
        assert _fp(base, versions=versions) != fp
    # logic version
    bumped = Node(**{**NODE.__dict__, "logic_version": 4})
    assert _fp(base, node=bumped) != fp


def test_undeclared_inputs_do_not_move_the_fingerprint():
    base = _snapshot({"d1": [{"_id": 1, "content_sha256": "a"}]})
    other = _snapshot({"d1": [{"_id": 1, "content_sha256": "a"}],
                       "unrelated": [{"_id": 5, "content_sha256": "zz"}]},
                      {"stranger": {"current": {"output_hash": "x"}}})
    assert _fp(base) == _fp(other)


def test_logic_refs_count_toward_the_total():
    import sys
    import types
    mod = types.ModuleType("regen_test_consts")
    mod.PROMPT = 7
    sys.modules["regen_test_consts"] = mod
    manifest._ref_cache.clear()
    node = Node("n", "f", logic_version=2, logic_refs=("regen_test_consts:PROMPT",))
    assert manifest.logic(node)["total"] == 9
    mod.PROMPT = 8
    manifest._ref_cache.clear()
    assert manifest.logic(node)["total"] == 10


def test_volatile_fields_do_not_change_the_output_hash():
    a = {"w": {"status": "available", "data": {"x": 1, "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
                                               "data_as_of": "2026-09-01",
                                               "nested": [{"generated_at": "t1", "v": 2}]}}}
    b = {"w": {"status": "available", "data": {"x": 1, "updated_at": datetime(2026, 2, 1, tzinfo=UTC),
                                               "data_as_of": "2026-09-20",
                                               "nested": [{"generated_at": "t2", "v": 2}]}}}
    c = {"w": {"status": "available", "data": {"x": 2}}}
    assert manifest.output_hash(a) == manifest.output_hash(b)
    assert manifest.output_hash(a) != manifest.output_hash(c)


def test_diff_names_the_changed_inputs():
    old = {"datasets": {"d1": 1, "d2": 1}, "upstream": {"up": "h1"}, "logic": {"total": 1}}
    new = {"datasets": {"d1": 2, "d2": 1}, "upstream": {"up": "h1"}, "logic": {"total": 2}}
    assert manifest.diff(old, new) == ["datasets.d1", "logic"]


def test_cache_suffix_tracks_config_and_is_empty_outside_a_run():
    assert manifest.cache_suffix() == ""
    ctx = run_context.RunContext("a", "n", manifest={"config": {"x": "1"}})
    with run_context.active(ctx):
        one = manifest.cache_suffix()
    ctx2 = run_context.RunContext("a", "n", manifest={"config": {"x": "2"}})
    with run_context.active(ctx2):
        two = manifest.cache_suffix()
    assert one and two and one != two
