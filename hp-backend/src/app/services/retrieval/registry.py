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

# There is no STRATEGY index any more, and this is not an oversight.
#
# Strategy Chat used to be the third entry here: build a graph over the other
# features' finished widgets, retrieve fragments of it, answer from those. It no
# longer retrieves anything. The whole account is about 113,000 tokens of widget
# JSON, which fits a 1M context window whole, so the feature sends all of it in
# one pass - see services/strategy/context.py. Retrieval existed to make the
# corpus fit; the corpus did not need fitting.
#
# Consequences worth knowing before anyone puts it back:
#   * `dependents()` no longer returns anything for widgets only Strategy read
#     (exec_urgency_score among them), so republishing one queues no rebuild.
#     Correct now - the chat reads those widgets live on every question.
#   * `corpus.strategy_documents` and its `_strategy_*` builders are still in
#     corpus.py but are wired to nothing.
#   * The built index is retired separately; removing this entry stops it being
#     rebuilt, it does not delete what Atlas already holds.

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
        # It was out of scope while ABX fixed the weights but left the
        # raw-data-to-driver transformation undefined. That gap is now closed:
        # HP_Urgency_Score_Updated_Final.pdf supplies the full formula - four
        # drivers at 20/25/30/25, with every band and point value specified -
        # so the score is the client's rather than delivery-authored.
        "generates": {
            "feature_key": "executive_dashboard",
            "widget_key": "exec_strategic_priorities",
            "generator": "app.services.dashboard.priorities:generate_dashboard_intelligence",
        },
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
