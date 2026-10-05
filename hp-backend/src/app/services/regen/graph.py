"""Which producer owns which widget, and what each one reads.

This is the single declaration of the dependency graph. The three lists it
replaces - `FEATURE_MAPPINGS.dependent_datasets`, `INDEX_REGISTRY.datasets` and
`scoring_refresh.STAMPED_WIDGETS` - each disagreed with what the code actually
read (audit section 3), so a dataset upload could leave a widget built from the
old file with nothing marking it stale. Every entry below was traced to a read
site in the producer, and at run time the engine compares what a producer
actually read against what it declares here.

A node is a producer (writes widgets) or an index (builds a LightRAG workspace
that later producers query). Features are what the API and the UI speak in;
nodes are what the engine schedules. Three features had to be split into two
producers each, because as single units they formed cycles - stakeholder map
and opportunity map read each other, and tech landscape sits both above and
below news. At producer grain the graph is acyclic, which `Graph` checks at
import.

`cited_above` (case-study allocation) is deliberately NOT an edge: the owner
ruled it a non-invalidating read, and as an edge it would close cycles.
"""

from dataclasses import dataclass, field

PRODUCER = "producer"
INDEX = "index"

# Scoring sections, knowledge corpora and the other non-dataset inputs a node can
# declare. Anything else is a typo, and a typo here is a missed invalidation.
CONFIG_SECTIONS = frozenset({"urgency", "evidence_strength", "live_signal",
                             "tech_confidence"})
KNOWLEDGE = frozenset({"rulebook", "case_studies", "product_knowledge", "lifecycle"})

# The eight datasets `rulebook.account_evidence` reads (rulebook.py:326-351).
RULEBOOK_EVIDENCE = ("firmographics", "technographics", "job_openings",
                     "intent_topics", "news_events", "google_news", "webstack",
                     "technology_detections")

# Widgets produced on a seller's request and kept as history. They are not
# derived from the account's inputs, so they are never stale and no node owns
# them; the store serves them from `account_widgets` as before.
USER_OUTPUT_WIDGETS = frozenset({"content_generated_assets", "content_angle_options",
                                 "evaluator_feedback_score"})


class GraphError(ValueError):
    """The declared graph is not usable - raised at import, so the app refuses
    to start rather than scheduling from a broken graph."""


@dataclass(frozen=True)
class Node:
    id: str
    feature: str
    kind: str = PRODUCER
    widgets: tuple = ()
    datasets: tuple = ()
    upstream: tuple = ()
    config: tuple = ()
    knowledge: tuple = ()
    account_config: bool = False       # account_instructions + account_guardrails
    account_record: bool = True        # accounts.name / accounts.domain
    llm: bool = False
    # Own counter, bumped for any logic change not captured by `logic_refs`.
    # Never lowered: a revert is a bump (the downgrade guard compares it).
    logic_version: int = 1
    # "module:CONSTANT" references to prompt/dictionary versions that already
    # exist in the producer's code, so bumping one invalidates the node without
    # anyone also remembering to bump `logic_version`.
    logic_refs: tuple = ()
    run: str = ""                      # "module:function", resolved lazily
    extra: dict = field(default_factory=dict, compare=False, hash=False)

    def __post_init__(self):
        # Every reader of job openings goes through hp/hiring_jobs.py, so every
        # node that declares the dataset depends on its selection rules too.
        if "job_openings" in self.datasets and HIRING_RULES_REF not in self.logic_refs:
            object.__setattr__(self, "logic_refs", (*self.logic_refs, HIRING_RULES_REF))


HIRING_RULES_REF = "app.services.hp.hiring_jobs:HIRING_RULES_VERSION"


_P = "app.services.regen.producers"

# Content Messaging (messaging_context, idx_content_messaging, messaging_pillars)
# was removed on 28 Sep: the client dropped the module (Sahaj, 27 Sep). Its
# producers and corpus builder are still in the code, unscheduled.
NODES = (
    Node("stakeholder_roster", "stakeholder_map",
         widgets=("stakeholder_contacts_grid", "stakeholder_influence_map"),
         # company_personas: the client's buying committee (Manisha, 28 Sep).
         datasets=("prospect_contacts", "company_personas"),
         # 2: the 27 Sep feedback. Every contact carries `source_label`
         # ("Explorium + Contacts Waterfall Tools"), each department group
         # carries its whole roster in `contact_ids`, the roster is ordered by
         # seniority rather than the composite score, and `source_breakdown`
         # and `ranked_entry_path` are gone. All of it is Python, so nothing
         # else here would have moved the fingerprint.
         logic_version=2,
         run=f"{_P}:stakeholder_roster"),
    Node("tech_core", "tech_landscape",
         widgets=("technographic_map", "tech_stack_matrix",
                  "tech_detections_reference", "webstack_breakdown"),
         datasets=("technographics", "technology_detections", "webstack",
                   "tech_breakdown", "firmographics", "hp_category_intent"),
         config=("tech_confidence",), knowledge=("rulebook", "case_studies"),
         llm=True,
         # 2: detected technology pools Technographics with the intent file's
         # Related Technologies, falling back to WebStack + Tech_Breakdown
         # when there is no estate; webstack_breakdown groups tech_breakdown.
         # 3: tech_stack_matrix carries stack_view - every technology as a card
         # in eight families with its HP play (Sahaj, 27 Sep; Caterpillar layout).
         # 4: tech_stack_matrix also carries category_groups - the whole estate
         # clubbed into the export's own 20 category columns, with what the
         # export left uncategorised in a group of its own.
         # 5: Client OS reads its spellings from one shared OS table, so "Mac
         # OS" with a space is recognised (Sahaj, 30 Sep) - which also carries
         # the Apple card through the Driver 1 gate, because "mac os" is a
         # named WXP 04 technology and "apple ios" alone is not. Plus a
         # reconciliation pass after suppression: the header count is recounted
         # from the cards that survived, and a "what it means for HP" paragraph
         # naming a card that was removed is dropped. All of it is stored
         # inside the widget, so the bump is what rewrites it.
         logic_version=5,
         logic_refs=("app.services.hp.map_narrative:MAP_NARRATIVE_PROMPT_VERSION",),
         run=f"{_P}:tech_core"),
    Node("objection", "objection_playbook",
         widgets=("objection_incumbent_context", "objection_reframe_cards"),
         # tech_breakdown is the evidence fallback when technographics is empty.
         datasets=tuple(sorted({"technographics", "tech_breakdown", "firmographics",
                                "prospect_contacts", *RULEBOOK_EVIDENCE})),
         knowledge=("rulebook", "case_studies"), llm=True,
         logic_refs=("app.services.extractors.objection_playbook:OBJECTION_PROMPT_VERSION",),
         run=f"{_P}:objection"),
    Node("intent", "intent_demand_signals",
         widgets=("intent_topics_table", "intent_category_summary"),
         datasets=("intent_score", "intent_topics",
                   "hp_category_intent", "technographics", "webstack",
                   "firmographics"),
         knowledge=("case_studies",), llm=True,
         logic_refs=("app.services.hp.intent_topic_map:DICTIONARY_VERSION",
                     "app.services.extractors.intent_demand_signals:"
                     "BU_READ_PROMPT_VERSION",
                     "app.services.hp.bombora_hp_classifier:PROMPT_VERSION"),
         # 2: Sahaj 27 Sep - no trend or volume in the So What, no proof point,
         # a business-unit summary led by Bombora.
         # 3: intent_hiring_demand removed; jobs are the hiring node's alone.
         # 4: a Bombora export filed under the account's parent/subdomain or a
         # confirmed alias is used (client, 5 Oct: NSW Health, IAG NZ).
         logic_version=4,
         run=f"{_P}:intent"),
    # The Hiring Signals section of Intent & Demand Signals, and the one hiring
    # output: the Executive Dashboard's job postings tile reads
    # hiring_postings_summary too. Its own node so a job upload rebuilds it
    # without re-running the intent model calls. Deterministic: the shared job
    # selection plus the O*NET theme table.
    Node("hiring", "intent_demand_signals",
         widgets=("hiring_postings_summary", "hiring_family_breakdown",
                  "hiring_tech_tags", "hiring_theme_cards"),
         datasets=("job_openings",),
         logic_refs=("app.services.hp.hiring_themes:THEMES_VERSION",),
         run=f"{_P}:hiring"),
    Node("opp_core", "solution_narrative_opportunity_map",
         widgets=("opportunity_context_card", "opportunity_narrative_plays"),
         datasets=("firmographics", "technographics", "intent_score",
                   "google_news", "news_events", "hp_category_intent",
                   "intent_topics"),
         upstream=("stakeholder_roster",),
         knowledge=("rulebook", "case_studies"), account_config=True, llm=True,
         logic_refs=("app.services.extractors.solution_narrative_opportunity_map:"
                     "OPPORTUNITY_PROMPT_VERSION",),
         run=f"{_P}:opp_core"),
    Node("content_persona", "content_studio",
         widgets=("content_persona_context",),
         # Topics are the 5 HP BUs + the published Live Signals (Sahaj, 27 Sep),
         # so the feed is read, not the raw news files or the Bombora topics.
         datasets=("firmographics", "job_openings", "prospect_contacts",
                   "company_personas"),
         upstream=("stakeholder_roster", "news"),
         # 3: the 30 Sep build specification, Section 1.4. The picker offers the
         # client's eight target roles and nothing else - the named, role-proxy
         # and archetype tiers are gone from the assembly - and
         # `persona_sources` reports the pack rather than four tier counts.
         # All Python, so nothing else here would have moved the fingerprint.
         #
         # The pack is a logic input in its own right: editing a persona card or
         # a row of the eligibility matrix changes what this widget offers, so
         # it has to invalidate the widget without anyone remembering to bump.
         logic_refs=("app.services.hp.buyer_personas:PERSONA_PACK_VERSION",),
         logic_version=3,
         run=f"{_P}:content_persona"),
    Node("news", "recent_news_signals",
         widgets=("news_relevance_summary", "news_signals_feed"),
         datasets=("google_news", "news_events", "firmographics"),
         upstream=("opp_core", "intent", "tech_core"),
         config=("live_signal",), knowledge=("case_studies",), llm=True,
         # 2: the source line names the scoring document's classification and
         # the publisher, and no longer repeats the document's definition
         # column (Sahaj, 28 Sep). The line is composed in Python but stored
         # inside the scored entry, and `describe_source` runs behind this
         # feature's own fingerprint cache - which `cache_suffix()` keys on
         # this number, so the bump is what re-scores and rewrites it.
         # NOT bumped for the tier names added on 30 Sep ("T1 - Established
         # news: Nikkei"). A bump would have been the usual lever, but it
         # marks this node stale on every account and re-runs everything
         # downstream of it - exec_core, opp_triggers, exec_priorities,
         # tech_recs, strategy_snapshot and a full idx_executive_dashboard
         # re-embed - to change one line of text. So the tier is derived at
         # READ time from the reliability score the widget already stores,
         # and nothing goes stale. See `signal_scoring.describe_source` and
         # its mirror in the dashboard.
         logic_version=2,
         logic_refs=("app.services.extractors.recent_news_signals:"
                     "SIGNAL_SCORING_PROMPT_VERSION",),
         run=f"{_P}:news"),
    Node("stakeholder_talking_points", "stakeholder_map",
         widgets=("stakeholder_talking_points",),
         datasets=("prospect_contacts", "company_personas", "firmographics",
                   "technographics", "intent_score", "google_news", "news_events"),
         upstream=("stakeholder_roster", "opp_core"),
         llm=True,
         logic_refs=("app.services.extractors.stakeholder_map:"
                     "TALKING_POINTS_PROMPT_VERSION",),
         run=f"{_P}:stakeholder_talking_points"),
    Node("opp_triggers", "solution_narrative_opportunity_map",
         widgets=("opportunity_trigger_signals",),
         upstream=("news",), account_record=False,
         run=f"{_P}:opp_triggers"),
    Node("exec_core", "executive_dashboard",
         widgets=("exec_summary_card", "exec_key_metrics", "exec_urgency_score"),
         datasets=("firmographics", "company_hierarchy", "subsidiaries", "job_openings",
                   "technographics", "webstack",
                   "intent_score", "hp_category_intent", "extended_company",
                   "google_news", "news_events", "compliance_filings",
                   "filings_financials"),
         upstream=("news", "opp_core"),
         config=("urgency",),
         # The company description is reorganised into bullets by one cached,
         # grounded model call (client feedback 1.a, 27 Sep).
         llm=True,
         logic_refs=("app.services.extractors.executive_dashboard:SUMMARY_PROMPT_VERSION",),
         # 2: exec_key_metrics lists the filings on record (the filings list
         # CSV uploaded with the PDFs under compliance_filings); Quick Stats
         # counts and the contacts read dropped (client feedback 1.e).
         # 3: exec_key_metrics carries reported_metrics from the filings index
         # (filings_financials.csv) when it is uploaded.
         # 4: exec_hiring_velocity counts the Hiring Signals selection (country
         # check + last 12 months) as job_postings_12m, not every row.
         # 5: exec_hiring_velocity removed; the tile reads hiring_postings_summary.
         # job_openings stays for the urgency score's Growth driver.
         # 6: exec_summary_card's parent is Ultimate Parent Name (column E) and it
         # lists the Subsidiaries sheet (client, 5 Oct, issue list v3).
         logic_version=6,
         run=f"{_P}:exec_core"),
    Node("evaluator_personas", "message_evaluator",
         widgets=("evaluator_persona_context",),
         datasets=("firmographics", "prospect_contacts", "company_personas"),
         upstream=("stakeholder_roster", "stakeholder_talking_points"),
         # 2: the 30 Sep build specification, Sections 4.2 and 4.3. The audience
         # is the client's eight target roles and each one now carries its
         # hardcoded card, replacing the contacts -> client roles -> hiring
         # fallback chain. All Python, so nothing else here would have moved the
         # fingerprint.
         #
         # The pack is a logic input for the same reason it is one on
         # `content_persona`: the card IS the widget's content now, so editing a
         # card has to invalidate it without anyone remembering to bump.
         logic_refs=("app.services.hp.buyer_personas:PERSONA_PACK_VERSION",),
         logic_version=2,
         run=f"{_P}:evaluator_personas"),
    Node("tech_recs", "tech_landscape",
         widgets=("technographic_hp_recommendations",),
         datasets=tuple(sorted({*RULEBOOK_EVIDENCE, "hp_category_intent"})),
         upstream=("tech_core", "exec_core", "intent", "opp_triggers"),
         knowledge=("rulebook", "product_knowledge", "lifecycle"), llm=True,
         logic_refs=("app.services.hp.recommendations:RECOMMENDATION_PROMPT_VERSION",),
         run=f"{_P}:tech_recs"),
    Node("idx_executive_dashboard", "executive_dashboard", kind=INDEX,
         datasets=("compliance_filings",),
         upstream=("exec_core", "news", "opp_triggers", "stakeholder_roster",
                   "tech_core", "intent", "hiring"),
         llm=True,
         # 2: PredictLeads filings (PDFs written from their text) join the
         # narrative but not the financial claims.
         # 3: hiring documents read the Hiring Signals widgets, not
         # exec_hiring_velocity / intent_hiring_demand.
         logic_version=3, run=f"{_P}:index_executive_dashboard"),
    Node("exec_priorities", "executive_dashboard",
         widgets=("exec_strategic_priorities",),
         upstream=("idx_executive_dashboard", "exec_core", "tech_recs", "opp_core"),
         config=("evidence_strength",), knowledge=("case_studies",),
         account_record=False, llm=True,
         logic_refs=("app.services.dashboard.priorities:PROMPT_VERSION",),
         run=f"{_P}:exec_priorities"),
    Node("strategy_snapshot", "strategy_chat",
         widgets=("strategy_snapshot_context", "strategy_chat_interface"),
         upstream=("exec_core", "stakeholder_roster", "opp_core", "tech_core",
                   "intent", "hiring", "news", "exec_priorities"),
         run=f"{_P}:strategy_snapshot"),
    # No idx_strategy: Strategy Chat reads the account's committed widgets whole
    # on every question (services/strategy/context.py), so there is no index to
    # build. Jobs queued for it before the deploy are cancelled by the engine as
    # "node_removed".
)


class Graph:
    """A validated, indexed view over a tuple of nodes.

    Tests build their own small graphs; the application uses `DEFAULT`.
    """

    def __init__(self, nodes, known_datasets=None, known_widgets=None):
        self.nodes = {}
        for node in nodes:
            if node.id in self.nodes:
                raise GraphError("node %r declared twice" % node.id)
            self.nodes[node.id] = node

        self.owner = {}
        for node in self.nodes.values():
            for key in node.widgets:
                if key in self.owner:
                    raise GraphError("widget %r has two owners: %s and %s"
                                     % (key, self.owner[key], node.id))
                if key in USER_OUTPUT_WIDGETS:
                    raise GraphError("widget %r is a user output and cannot be "
                                     "owned by a node" % key)
                self.owner[key] = node.id

        for node in self.nodes.values():
            if node.kind not in (PRODUCER, INDEX):
                raise GraphError("node %r has unknown kind %r" % (node.id, node.kind))
            if node.kind == INDEX and node.widgets:
                raise GraphError("index node %r cannot own widgets" % node.id)
            for up in node.upstream:
                if up not in self.nodes:
                    raise GraphError("node %r depends on unknown node %r"
                                     % (node.id, up))
                if up == node.id:
                    raise GraphError("node %r depends on itself" % node.id)
            for name in node.config:
                if name not in CONFIG_SECTIONS:
                    raise GraphError("node %r declares unknown config section %r"
                                     % (node.id, name))
            for name in node.knowledge:
                if name not in KNOWLEDGE:
                    raise GraphError("node %r declares unknown knowledge %r"
                                     % (node.id, name))
            if known_datasets is not None:
                for key in node.datasets:
                    if key not in known_datasets:
                        raise GraphError("node %r declares unknown dataset %r"
                                         % (node.id, key))
            if known_widgets is not None:
                for key in node.widgets:
                    if key not in known_widgets:
                        raise GraphError("node %r owns unknown widget %r"
                                         % (node.id, key))

        self.downstream = {nid: [] for nid in self.nodes}
        for node in self.nodes.values():
            for up in node.upstream:
                self.downstream[up].append(node.id)

        self.order = self._toposort()
        self._rank = {nid: i for i, nid in enumerate(self.order)}

    def _toposort(self) -> list:
        """Kahn's algorithm, ties broken by declaration order for stable output."""
        declared = list(self.nodes)
        indegree = {nid: len(self.nodes[nid].upstream) for nid in declared}
        ready = [nid for nid in declared if indegree[nid] == 0]
        order = []
        while ready:
            nid = ready.pop(0)
            order.append(nid)
            for child in sorted(self.downstream[nid], key=declared.index):
                indegree[child] -= 1
                if indegree[child] == 0:
                    ready.append(child)
        if len(order) != len(declared):
            stuck = sorted(nid for nid in declared if indegree[nid] > 0)
            raise GraphError("dependency cycle among: %s" % ", ".join(stuck))
        return order

    def __getitem__(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def __contains__(self, node_id) -> bool:
        return node_id in self.nodes

    def rank(self, node_id: str) -> int:
        return self._rank[node_id]

    def ancestors(self, node_id: str) -> set:
        seen, stack = set(), list(self.nodes[node_id].upstream)
        while stack:
            nid = stack.pop()
            if nid not in seen:
                seen.add(nid)
                stack.extend(self.nodes[nid].upstream)
        return seen

    def descendants(self, node_id: str) -> set:
        seen, stack = set(), list(self.downstream[node_id])
        while stack:
            nid = stack.pop()
            if nid not in seen:
                seen.add(nid)
                stack.extend(self.downstream[nid])
        return seen

    def readers_of_dataset(self, dataset_key: str) -> list:
        """Nodes that read this dataset directly, in dependency order."""
        return [nid for nid in self.order if dataset_key in self.nodes[nid].datasets]

    def affected_by_dataset(self, dataset_key: str) -> list:
        """Direct readers plus everything downstream of them, in dependency order."""
        hit = set(self.readers_of_dataset(dataset_key))
        for nid in list(hit):
            hit |= self.descendants(nid)
        return [nid for nid in self.order if nid in hit]

    def features(self) -> dict:
        """feature_id -> its nodes, in dependency order."""
        out = {}
        for nid in self.order:
            out.setdefault(self.nodes[nid].feature, []).append(nid)
        return out

    def nodes_for_feature(self, feature_id: str) -> list:
        return self.features().get(feature_id, [])

    def upstream_widgets(self, node_id: str) -> set:
        """Every widget a node may read without declaring anything more."""
        keys = set()
        for up in self.nodes[node_id].upstream:
            keys.update(self.nodes[up].widgets)
        return keys

    def dependent_datasets(self, feature_id: str) -> list:
        """What an upload of any of these datasets changes for this feature,
        including through the feature's upstream nodes. The value
        `FEATURE_MAPPINGS.dependent_datasets` is generated from."""
        keys = set()
        for nid in self.nodes_for_feature(feature_id):
            for member in {nid} | self.ancestors(nid):
                keys.update(self.nodes[member].datasets)
        return sorted(keys)


def _build_default() -> Graph:
    # Validated against the dataset registry here; against WIDGET_REGISTRY in
    # the tests, because importing the API layer from a service would invert
    # the dependency.
    from app.schemas.account_data import DATASET_REGISTRY

    return Graph(NODES, known_datasets=set(DATASET_REGISTRY))


DEFAULT = _build_default()
