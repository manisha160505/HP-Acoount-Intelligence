"""The dependency graph: complete, acyclic, and derived from what the code reads.

The graph replaces three lists that each disagreed with the code, so these tests
pin it against the registries it has to cover rather than against a copy of
itself.

Run: python -m pytest tests/test_regen_graph.py -v
"""

import importlib

import pytest
import yaml

from app.services.regen.graph import (
    DEFAULT,
    INDEX,
    USER_OUTPUT_WIDGETS,
    Graph,
    GraphError,
    Node,
)


def test_default_graph_is_acyclic_and_every_upstream_comes_first():
    seen = set()
    for nid in DEFAULT.order:
        for up in DEFAULT[nid].upstream:
            assert up in seen, "%s runs before its upstream %s" % (nid, up)
        seen.add(nid)
    # 16: Content Messaging's three nodes were removed on 28 Sep (client dropped it).
    # 15: idx_strategy removed - Strategy Chat reads the whole account instead.
    assert len(DEFAULT.order) == len(DEFAULT.nodes) == 15


def test_every_registered_widget_has_exactly_one_owner_or_is_a_user_output():
    from app.api.v1.widgets import WIDGET_REGISTRY

    registered = {c["widget_key"] for contracts in WIDGET_REGISTRY.values()
                  for c in contracts}
    owned = set(DEFAULT.owner)
    assert registered - owned == set(USER_OUTPUT_WIDGETS)
    assert owned - registered == set()


def test_every_widget_owner_belongs_to_the_widgets_feature():
    from app.api.v1.widgets import WIDGET_REGISTRY

    for feature, contracts in WIDGET_REGISTRY.items():
        for c in contracts:
            owner = DEFAULT.owner.get(c["widget_key"])
            if owner:
                assert DEFAULT[owner].feature == feature, c["widget_key"]


def test_every_feature_maps_to_at_least_one_producer():
    from app.api.v1.widgets import WIDGET_REGISTRY

    for feature in WIDGET_REGISTRY:
        producers = [n for n in DEFAULT.nodes_for_feature(feature)
                     if DEFAULT[n].kind != INDEX]
        assert producers, feature


def test_declared_config_sections_exist_in_scoring_yaml():
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "config", "scoring.yaml")
    with open(path, encoding="utf-8") as fh:
        sections = set(yaml.safe_load(fh))
    for node in DEFAULT.nodes.values():
        assert set(node.config) <= sections, node.id


def test_logic_refs_resolve_to_real_constants():
    for node in DEFAULT.nodes.values():
        for ref in node.logic_refs:
            module, _, name = ref.partition(":")
            assert hasattr(importlib.import_module(module), name), ref


def test_filings_upload_touches_only_the_dashboard_chain():
    affected = DEFAULT.affected_by_dataset("compliance_filings")
    # exec_core lists the filings (the filings list CSV rides with the PDFs),
    # so the exec chain below it re-runs too.
    assert affected == ["exec_core", "tech_recs", "idx_executive_dashboard",
                        "exec_priorities", "strategy_snapshot"]
    # And nothing unrelated.
    for untouched in ("objection", "intent", "tech_core", "news", "stakeholder_roster"):
        assert untouched not in affected


def test_contacts_upload_does_not_touch_intent_or_tech_core():
    affected = set(DEFAULT.affected_by_dataset("prospect_contacts"))
    assert {"stakeholder_roster", "opp_core", "objection"} <= affected
    assert "intent" not in affected and "tech_core" not in affected


def test_the_three_splits_hold():
    # Talking points read the plays; the plays read the roster, not the points.
    assert "opp_core" in DEFAULT["stakeholder_talking_points"].upstream
    assert "stakeholder_talking_points" not in DEFAULT.ancestors("opp_core")
    # News no longer has two writers.
    assert DEFAULT.owner["news_signals_feed"] == "news"
    # Recommendations sit downstream of news; the core map does not.
    assert "news" in DEFAULT.ancestors("tech_recs")
    assert "news" not in DEFAULT.ancestors("tech_core")


def test_exec_key_metrics_has_a_single_owner():
    # The priorities generator used to rewrite it too (audit R8).
    assert DEFAULT.owner["exec_key_metrics"] == "exec_core"
    assert "exec_key_metrics" not in DEFAULT["exec_priorities"].widgets


def test_cycle_is_rejected():
    with pytest.raises(GraphError, match="cycle"):
        Graph((Node("a", "f", upstream=("c",)), Node("b", "f", upstream=("a",)),
               Node("c", "f", upstream=("b",))))


def test_two_owners_are_rejected():
    with pytest.raises(GraphError, match="two owners"):
        Graph((Node("a", "f", widgets=("w",)), Node("b", "f", widgets=("w",))))


def test_unknown_upstream_and_unknown_dataset_are_rejected():
    with pytest.raises(GraphError, match="unknown node"):
        Graph((Node("a", "f", upstream=("ghost",)),))
    with pytest.raises(GraphError, match="unknown dataset"):
        Graph((Node("a", "f", datasets=("nope",)),), known_datasets={"real"})


def test_user_outputs_cannot_be_owned():
    with pytest.raises(GraphError, match="user output"):
        Graph((Node("a", "f", widgets=("content_generated_assets",)),))


def test_dependent_datasets_include_upstream_inputs():
    # Stakeholder talking points depend on the opportunity map, which reads
    # intent_topics - so an intent_topics upload affects the stakeholder feature.
    assert "intent_topics" in DEFAULT.dependent_datasets("stakeholder_map")
