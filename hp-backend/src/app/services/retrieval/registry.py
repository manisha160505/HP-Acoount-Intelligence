"""What each index contains, and what must exist before it can be built.

Account-agnostic, the same shape as `DATASET_REGISTRY`: an index is declared
here, never hardcoded at a call site, so adding the Executive Dashboard or
Strategy index later is a registry entry plus a corpus builder.

Three indexes are planned. Only Content Messaging is live; the other two are
declared with `enabled: False` so their preconditions are visible without
pretending they can be built.
"""

from app.services.retrieval import corpus

CONTENT_MESSAGING = "content_messaging"
EXECUTIVE_DASHBOARD = "executive_dashboard"
STRATEGY = "strategy"

INDEX_REGISTRY = {
    CONTENT_MESSAGING: {
        "label": "Content Messaging",
        "enabled": True,
        "builder": corpus.content_messaging_documents,
        # The datasets the 11-features reference assigns this feature. Source A
        # `News_Events` is deliberately absent - the document records it as
        # "Not used", with Google News RSS primary and `news_events` the add-on.
        "datasets": ["firmographics", "technographics", "intent_score",
                     "google_news", "news_events"],
        # Widgets whose content enters the corpus. A missing one narrows the
        # corpus; it does not block the build, because ABX treats these as
        # enrichment over the dataset fields rather than as the feature's spine.
        "widgets": ["messaging_context_card", "opportunity_narrative_plays",
                    "news_signals_feed", "technographic_map",
                    "technographic_hp_recommendations"],
        # Without these there is nothing worth indexing.
        "required_widgets": ["messaging_context_card"],
        "default_mode": "mix",
        # The feature this index feeds. A successful build regenerates it, so a
        # data change reaches the message house on its own - the same way every
        # other feature rebuilds when a file it depends on is replaced.
        #
        # Named as a dotted path rather than imported: the generator imports the
        # retrieval layer, and importing it here would close a cycle.
        #
        # `messaging_pillars_output` is deliberately absent from `widgets` above.
        # If the generated house fed back into the corpus, every build would
        # change the corpus and trigger the next one, forever.
        "generates": {
            "feature_key": "content_messaging",
            "widget_key": "messaging_pillars_output",
            "generator": "app.services.messaging.pillars:generate_messaging_pillars",
        },
    },
    EXECUTIVE_DASHBOARD: {
        "label": "Executive Dashboard",
        "enabled": True,
        "builder": corpus.executive_dashboard_documents,
        # The datasets the 11-features reference assigns Feature 1 -
        # firmographics, company hierarchy and job openings - plus the filings
        # themselves, which are the only source of a reported financial figure
        # rather than a band, and the datasets behind the cleaned outputs ABX
        # Step 4 says to reuse.
        "datasets": ["compliance_filings", "firmographics", "company_hierarchy",
                     "job_openings", "prospect_contacts", "technographics",
                     "intent_score", "google_news", "news_events"],
        # The cleaned feature outputs ABX Step 4 names: "reuse the cleaned
        # Recent News, Stakeholder Map, Tech Landscape and Intent outputs".
        "widgets": ["exec_summary_card", "exec_key_metrics",
                    "exec_hiring_velocity", "news_signals_feed",
                    "opportunity_trigger_signals", "stakeholder_influence_map",
                    "technographic_map", "intent_topics_table",
                    "intent_hiring_demand"],
        "required_widgets": ["exec_summary_card"],
        "default_mode": "mix",
        # `exec_strategic_priorities` is what this index produces, so it is
        # absent from `widgets` above: a generated widget feeding its own corpus
        # would change the corpus on every build and trigger the next one.
        #
        # `exec_urgency_score` is computed by `urgency.py`, not retrieved, so it
        # is absent from `widgets` above for the same reason
        # `exec_strategic_priorities` is.
        #
        # It was out of scope until now: ABX fixes the weights but leaves the
        # raw-data-to-driver transformation undefined - "The current POC does
        # not define a reusable raw-data-to-driver formula for all accounts" -
        # and directs that one not be invented here. That direction has been
        # knowingly overridden on instruction; the driver formulas are
        # delivery-authored, every payload says so, and they need client
        # sign-off before the number is presented as HP's.
        "generates": {
            "feature_key": "executive_dashboard",
            "widget_key": "exec_strategic_priorities",
            "generator": "app.services.dashboard.priorities:generate_dashboard_intelligence",
        },
    },
    STRATEGY: {
        "label": "Strategy",
        "enabled": True,
        "builder": corpus.strategy_documents,
        # Deliberately empty. `datasets` exists to queue a rebuild the moment a
        # raw file is uploaded, and this index must NOT rebuild then: its corpus
        # is the other features' finished widgets, and at upload time those have
        # not regenerated yet. Rebuilding on the file would index the previous
        # answers and call them current.
        #
        # The right trigger fires one step later. `dependents()` below maps a
        # republished widget to the indexes that read it, and all three paths
        # that republish widgets use it - the dataset endpoints, the
        # `/regenerate` endpoint, and `_run_generator` after an index build. A
        # new filing therefore reaches the chat as: PDF -> dashboard rebuilds ->
        # exec_strategic_priorities republished -> strategy queued by
        # `requeue_dependents` -> strategy rebuilds.
        #
        # That last arrow was missing until the trigger work: the chain read
        # correctly here but nothing implemented it, and it appeared to hold
        # only because a data change queued both indexes at once and the worker
        # happened to run them in the right order.
        "datasets": [],
        # The finished outputs of the other ten features. ABX: "Use the finished
        # account intelligence: facts, priorities, stakeholders, technology,
        # signals, narratives, objections, intent and HP recommendations."
        #
        # EVERY widget of all eight contributing features. Message Evaluator and
        # Content Studio are excluded by instruction: they publish a user's own
        # draft message and generated assets, which are outputs of the platform
        # rather than intelligence about the account.
        #
        # Three entries here are listed but deliberately NOT built into separate
        # documents - `opportunity_context_card`, `opportunity_trigger_signals`
        # and `messaging_context_card`. Their content is already in the corpus
        # via the widget that consumed them; `opportunity_trigger_signals`
        # ["triggers"] IS `news_signals_feed`["signals"], the same published
        # list. Listing them still gets a rebuild queued when they change, so
        # nothing goes stale, without the graph holding two witnesses to one
        # fact. `corpus.py` names what covers each where it declines to build.
        "widgets": ["exec_summary_card", "exec_strategic_priorities",
                    "exec_key_metrics", "exec_hiring_velocity",
                    "exec_urgency_score",
                    "stakeholder_contacts_grid", "stakeholder_influence_map",
                    "stakeholder_talking_points",
                    "news_signals_feed", "news_relevance_summary",
                    "opportunity_narrative_plays", "opportunity_context_card",
                    "opportunity_trigger_signals",
                    "objection_reframe_cards", "objection_incumbent_context",
                    "technographic_map", "technographic_hp_recommendations",
                    "tech_stack_matrix", "tech_detections_reference",
                    "webstack_breakdown",
                    "intent_topics_table", "intent_category_summary",
                    "intent_hiring_demand",
                    "messaging_pillars_output", "messaging_context_card"],
        # Enough of an account to be worth asking questions about. Not the whole
        # list: a feature that has not run yet narrows the corpus, and the chat
        # says what it does not know rather than refusing to open.
        "required_widgets": ["exec_summary_card", "stakeholder_contacts_grid"],
        # `naive` is vector search over the chunks and nothing else - no entity
        # walk, no relation walk, no graph in the context at all.
        #
        # It is by far the fastest (measured ~2s against mix's ~3s warm and
        # ~6-9s cold), because it skips the work every other mode does. What it
        # gives up is the reason this index is a graph: a question like "who
        # should I approach about AI workstations" needs a person joined to an
        # intent topic joined to a technology, and that join exists only in the
        # relationships. Under naive the answer can only draw on whatever a
        # single chunk happens to say.
        #
        # Worth knowing: if this stays, the graph is dead weight. Extraction
        # builds it on every index rebuild - an LLM call per chunk, the bulk of
        # a 17-minute build - and naive never reads it.
        #
        # Set to naive on request, to be evaluated against real questions.
        # Put back to "mix" to restore the blended behaviour.
        "default_mode": "naive",
        # No `generates` hook. This index answers questions; it does not produce
        # a widget, and a widget it produced would feed its own corpus.
    },
}

INDEX_KEYS = sorted(INDEX_REGISTRY)


class UnknownIndex(Exception):
    pass


def spec(index: str) -> dict:
    if index not in INDEX_REGISTRY:
        raise UnknownIndex("unknown index %r - expected one of %s"
                           % (index, ", ".join(INDEX_KEYS)))
    return INDEX_REGISTRY[index]


def is_enabled(index: str) -> bool:
    return bool(spec(index).get("enabled"))


def preconditions(db, account_id: str, index: str) -> tuple:
    """(ok, reason). Why an index cannot be built yet, in words a seller reads."""
    entry = spec(index)
    if not entry.get("enabled"):
        return False, entry.get("notice") or "This index is not enabled yet."

    missing = []
    for key in entry.get("required_widgets") or []:
        found = db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": key})
        if not found or found.get("status") != "available":
            missing.append(key)
    if missing:
        return False, ("waiting on %s - run the feature that produces it first"
                       % ", ".join(missing))
    return True, "ready to build"


def dependents(widget_key: str, enabled_only: bool = True) -> list:
    """Indexes whose corpus is built from this widget, in registry order.

    The inverse of each entry's `widgets` list, and the one place that answers
    "what goes stale when this widget is republished". It existed before only as
    a scan in the API layer that answered a coarser question - which FEATURES
    feed an index - so a single widget write could not be traced to the indexes
    that actually read it.

    `enabled_only` because a disabled index cannot be built: `request_update`
    would discard the job anyway, and queuing one would only look like work.
    """
    key = str(widget_key or "").strip()
    if not key:
        return []
    return [index for index, entry in INDEX_REGISTRY.items()
            if key in (entry.get("widgets") or [])
            and (not enabled_only or entry.get("enabled"))]


def dependents_of(widget_keys, enabled_only: bool = True) -> list:
    """`dependents` for several widgets at once, deduped, in registry order.

    A regeneration republishes a feature's widgets together, and the caller
    wants one job per index rather than one per widget. The queue coalesces
    duplicates anyway, but asking for the same build five times makes the logs
    read as though five were needed.
    """
    wanted = {k for k in (widget_keys or []) if str(k or "").strip()}
    if not wanted:
        return []
    return [index for index, entry in INDEX_REGISTRY.items()
            if wanted & set(entry.get("widgets") or [])
            and (not enabled_only or entry.get("enabled"))]


def build_documents(account_id: str, index: str) -> list:
    entry = spec(index)
    builder = entry.get("builder")
    if not builder:
        raise UnknownIndex("index %r has no corpus builder" % index)
    return builder(account_id, index)


def generates(index: str) -> dict | None:
    """What this index feeds, if anything."""
    return spec(index).get("generates")


def load_generator(index: str):
    """Resolve the declared generator to a callable, or None.

    Imported on demand rather than at module load: the generator imports the
    retrieval layer, so importing it from here would close a cycle.
    """
    hook = generates(index)
    if not hook or not hook.get("generator"):
        return None
    module_path, _, func_name = str(hook["generator"]).partition(":")
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, func_name, None)
