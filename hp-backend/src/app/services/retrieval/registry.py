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
        # `exec_urgency_score` is out of scope. ABX fixes its weights but leaves
        # the raw-data-to-driver transformation undefined - "The current POC does
        # not define a reusable raw-data-to-driver formula for all accounts" -
        # and its own missing-input rule then forbids computing an overall score.
        "generates": {
            "feature_key": "executive_dashboard",
            "widget_key": "exec_strategic_priorities",
            "generator": "app.services.dashboard.priorities:generate_dashboard_intelligence",
        },
    },
    STRATEGY: {
        "label": "Strategy",
        "enabled": False,
        "builder": None,
        "datasets": [],
        "widgets": [],
        "required_widgets": [],
        "default_mode": "mix",
        "notice": ("Corpus is the finished widgets of every other feature. Built "
                   "last, once those outputs are final."),
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
