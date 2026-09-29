"""The function the engine runs for each node.

Each is a thin call into the existing extractor, which keeps its logic
unchanged: inside a run, `widget_store.put` stages what it publishes and the
engine commits it, and the dataset loader reads the rows pinned at the start.
Where a feature became two producers, the extractor's `parts` argument selects
the half this node owns.

Imports are local so importing the graph does not import every extractor.
"""


def stakeholder_roster(account_id: str):
    from app.services.extractors.stakeholder_map import extract_stakeholder_map
    return extract_stakeholder_map(account_id, parts=("roster",))


def stakeholder_talking_points(account_id: str):
    from app.services.extractors.stakeholder_map import extract_stakeholder_map
    return extract_stakeholder_map(account_id, parts=("talking_points",))


def tech_core(account_id: str):
    from app.services.extractors.tech_landscape import extract_tech_landscape
    return extract_tech_landscape(account_id, parts=("core",))


def tech_recs(account_id: str):
    from app.services.hp.recommendations import publish_hp_recommendations
    return publish_hp_recommendations(account_id)


def objection(account_id: str):
    from app.services.extractors.objection_playbook import extract_objection_playbook
    return extract_objection_playbook(account_id)


def intent(account_id: str):
    from app.services.extractors.intent_demand_signals import extract_intent_demand_signals
    return extract_intent_demand_signals(account_id)


def messaging_context(account_id: str):
    from app.services.extractors.content_messaging import extract_content_messaging
    return extract_content_messaging(account_id)


def opp_core(account_id: str):
    from app.services.extractors.solution_narrative_opportunity_map import (
        extract_solution_narrative_opportunity_map,
    )
    return extract_solution_narrative_opportunity_map(account_id, parts=("core",))


def opp_triggers(account_id: str):
    from app.services.extractors.solution_narrative_opportunity_map import (
        publish_trigger_signals,
    )
    return publish_trigger_signals(account_id)


def content_persona(account_id: str):
    from app.services.extractors.content_studio import extract_content_studio
    return extract_content_studio(account_id)


def news(account_id: str):
    from app.services.extractors.recent_news_signals import extract_recent_news_signals
    return extract_recent_news_signals(account_id)


def exec_core(account_id: str):
    from app.services.extractors.executive_dashboard import extract_executive_dashboard
    return extract_executive_dashboard(account_id)


def evaluator_personas(account_id: str):
    from app.services.extractors.message_evaluator import extract_message_evaluator
    return extract_message_evaluator(account_id)


def exec_priorities(account_id: str):
    from app.services.dashboard.priorities import generate_dashboard_intelligence
    return generate_dashboard_intelligence(account_id)


def messaging_pillars(account_id: str):
    from app.services.messaging.pillars import generate_messaging_pillars
    return generate_messaging_pillars(account_id)


def strategy_snapshot(account_id: str):
    from app.services.extractors.strategy_chat import extract_strategy_chat
    return extract_strategy_chat(account_id)


# ---------------------------------------------------------------------------
# Index nodes
# ---------------------------------------------------------------------------

def _index(account_id: str, index: str, full: bool) -> dict:
    """Build one retrieval index, on its own event loop, and report what it built.

    `asyncio.run` gives the build a fresh loop that is closed afterwards, which
    is what lets LightRAG's per-loop Mongo client and pipeline ingress rebind
    for the next build (see retrieval/multiloop.py); the run context is copied
    into that loop, so the corpus builder still reads the pinned widgets.

    The index is changed in place, so the engine always commits what the build
    actually did: `degraded` when documents failed to index, `blocked` when the
    index's preconditions are not met. The output hash covers the corpus
    fingerprints and the index version, so an unchanged corpus leaves the
    consumers current and an admin full rebuild refreshes them.
    """
    import asyncio

    from app.services.retrieval import index_state, ingest

    try:
        from app.services.regen import context as run_context
        stats = asyncio.run(ingest.update_index(account_id, index, full=full,
                                                progress=run_context.progress))
    except ingest.BuildBlocked as exc:
        state = index_state.get(account_id, index)
        return {"quality": "blocked", "corpus": {}, "reason": str(exc),
                "index_version": state.get("version")}
    state = index_state.get(account_id, index)
    return {"quality": "degraded" if stats.get("damaged") else "complete",
            "corpus": {k: (v or {}).get("fingerprint")
                       for k, v in (state.get("documents") or {}).items()},
            "index_version": state.get("version"),
            "stats": stats}


def index_executive_dashboard(account_id: str, full: bool = False):
    return _index(account_id, "executive_dashboard", full)


def index_content_messaging(account_id: str, full: bool = False):
    return _index(account_id, "content_messaging", full)


