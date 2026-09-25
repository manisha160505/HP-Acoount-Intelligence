"""Sections C and D: how strong a recommendation is allowed to be.

    Opportunity           "At least 2 logically related independent data
                           pipelines supporting the same HP-addressable
                           opportunity in the current loaded account-data
                           snapshot. Duplicate coverage of the same underlying
                           event counts as one pipeline signal, not multiple
                           corroborating signals."

    Conversation Starter  "1 strong, directly relevant signal ... but without a
                           second independent pipeline confirming the same
                           opportunity."

    Context Only          "Evidence is useful for account understanding but is
                           weak/ambiguous, older based on its own event/source
                           date, or does not establish an HP-addressable
                           opportunity."
        - HP Recommendation Tuning Logic FINAL v4, section C

This is NOT a score, and it does not replace one. The three scoring documents
each define their own scale for their own feature - Live Signals 0-10, Tech
Landscape Confidence 0-100%, Urgency 0-100 - and those stand. A tier says what
the PROSE may claim on top of whatever the number says: a card can be a
confident 85% Tech Landscape match and still only be allowed to say "this
creates a relevant conversation", because one pipeline saw it.

The counting rule that does the work is `pipelines`. Two rows from
`google_news` and `news_events` describing the same announcement are one
pipeline, not two, because both map to News - which is section B's
"do not count the same event twice" falling out of the mapping rather than
needing a second dedup pass.
"""

import logging

logger = logging.getLogger(__name__)

OPPORTUNITY = "Opportunity"
CONVERSATION_STARTER = "Conversation Starter"
CONTEXT_ONLY = "Context Only"

# Section C's threshold, named rather than inlined.
PIPELINES_FOR_OPPORTUNITY = 2

# Dataset key -> the data pipeline it belongs to, in the document's own
# vocabulary. Several keys per pipeline is the point: the two news feeds and
# the three intent files are each ONE source of corroboration, however many
# rows they contribute.
DATASET_PIPELINES = {
    "firmographics": "Firmographics",
    "company_hierarchy": "Firmographics",
    "extended_company": "Firmographics",

    "technographics": "Technographics",
    "technology_detections": "Technographics",
    "webstack": "Technographics",
    # A widget-derived restatement of the technology export - one vendor per
    # cell where the raw row is a comma-joined list. It is the same pipeline,
    # and omitting it read a rule matched on "Kaspersky" as having no evidence
    # at all, because the short derived cell is what the token matcher finds.
    "technographic_map": "Technographics",

    "hp_category_intent": "Intent",
    "intent_score": "Intent",
    "intent_topics": "Intent",

    "job_openings": "Hiring",

    "google_news": "News",
    "news_events": "News",

    "compliance_filings": "Filings",

    "prospect_contacts": "Contacts",
}

# Pipelines that describe the account rather than evidencing a need. They are
# real corroboration when something else has already established the
# opportunity - the document's own Opportunity Map example leans on an employee
# band - but on their own they cannot lift anything above Context Only.
CONTEXT_PIPELINES = frozenset(("Firmographics", "Contacts"))

# The client's relevance ladder, 25 Sep email, verbatim:
#
#   "Technology only (Intune/ServiceNow): an internal 'possible fit' only, NOT
#    recommended.
#    Technology plus related account evidence: 'HP WXP may be relevant to this
#    opportunity.'
#    A clear opportunity plus the Rulebook's conditions supported: 'HP WXP is
#    relevant to this opportunity.'"
#
# This is a second axis on top of the v4 section C tiers, not a replacement for
# them. A tier says how strong the EVIDENCE is; a rung says how an HP OFFERING
# may be worded on the back of it. They line up one to one, which is why the
# rung is derived from the tier rather than computed again from the same
# pipelines.
RELEVANCE_NOT_RECOMMENDED = "possible fit"
RELEVANCE_MAY = "may be relevant"
RELEVANCE_IS = "is relevant"

RELEVANCE_BY_TIER = {
    OPPORTUNITY: RELEVANCE_IS,
    CONVERSATION_STARTER: RELEVANCE_MAY,
    CONTEXT_ONLY: RELEVANCE_NOT_RECOMMENDED,
}

# The sentence a feature may write for each rung. The offering's name is
# substituted in; nothing else about the phrasing is the model's choice.
RELEVANCE_WORDING = {
    RELEVANCE_IS: '"%s is relevant to this opportunity."',
    RELEVANCE_MAY: '"%s may be relevant to this opportunity."',
    RELEVANCE_NOT_RECOMMENDED: (
        "Do not recommend %s. It is a possible fit internally; say only that "
        "the technology was detected and name the integration route."),
}


def relevance_for(tier: str, conditions_unevaluable: bool = False) -> str:
    """How strongly an HP offering may be worded on this evidence.

    `conditions_unevaluable` is the client's rule 5: "A Rulebook condition that
    cannot be evaluated counts as unmet. The offering can reach 'may be
    relevant' but never 'is relevant'." Seat-count and licence-tier rules are
    the live examples - the data carries an employee band, not a seat count, so
    those conditions can never be tested and must not produce a settled claim.
    """
    rung = RELEVANCE_BY_TIER.get(str(tier or ""), RELEVANCE_NOT_RECOMMENDED)
    if conditions_unevaluable and rung == RELEVANCE_IS:
        return RELEVANCE_MAY
    return rung


PERMITTED_LANGUAGE = {
    OPPORTUNITY: ("May state that the combined evidence indicates or supports "
                  "an HP-addressable opportunity, and recommend a specific "
                  "seller focus. An offering whose conditions are supported "
                  "\"is relevant to this opportunity\"."),
    CONVERSATION_STARTER: ("An offering here \"may be relevant to this "
                           "opportunity\" - never \"is relevant\". Do not "
                           "state a confirmed need, project or buying motion."),
    CONTEXT_ONLY: ("Present as seller context only. Do not create an HP "
                   "opportunity or product recommendation. A detected "
                   "technology is a possible integration route, nothing more."),
}

# Section D's wording, for an account where nothing is addressable.
NO_PLAY = "No supported HP play at this time"


def pipeline_of(dataset: str) -> str | None:
    """The pipeline a dataset key belongs to, or None when it is not one."""
    return DATASET_PIPELINES.get(str(dataset or "").strip().lower())


def pipelines(rows) -> set:
    """The distinct pipelines behind these evidence rows.

    `rows` are the provenanced dicts the matchers already pass around -
    anything carrying a `dataset`. Duplicate coverage collapses here: two rows
    from the two news feeds are one News pipeline, which is section B's rule
    without a second dedup pass.
    """
    found = set()
    for row in rows or []:
        name = pipeline_of((row or {}).get("dataset") if isinstance(row, dict) else row)
        if name:
            found.add(name)
    return found


def _no_signal(category_intent) -> bool:
    """Whether the HP-category intent for this offering reads as No Signal.

    Explicitly 0, or the export's own "No Signal" wording. `None` does not
    count: an unknown score is absence of evidence, and section 3's "Missing
    data must remain missing" forbids reading that as a negative.
    """
    if category_intent is None:
        return False
    if isinstance(category_intent, str):
        return category_intent.strip().lower() in ("no signal", "none", "0")
    try:
        return float(category_intent) == 0
    except (TypeError, ValueError):
        return False


def tier_for(rows, hp_addressable: bool = True, category_intent=None) -> dict:
    """The tier this evidence earns, and what the prose may then claim.

    `hp_addressable` is the caller's own answer to "did anything actually match
    an HP offering" - a rulebook rule firing, a play qualifying. Section C is
    explicit that evidence which does not establish an HP-addressable
    opportunity is Context Only however much of it there is, so a caller that
    has nothing matched says so and the count cannot override it.
    """
    found = pipelines(rows)
    corroborating = found - CONTEXT_PIPELINES

    # Banned output K1: "Recommend an active HP Poly motion solely because Cisco
    # WebEx, TelePresence or other collaboration technologies are detected ...
    # Treat collaboration technology as contextual evidence; do not prioritize a
    # Poly opportunity unless separate current evidence supports it."
    #
    # Generalised to any offering whose own HP category reads No Signal:
    # detected technology becomes context, so it can no longer corroborate on
    # its own. Hiring, news or filings still can - that is the "separate current
    # evidence" the rule allows, and this demotes the technology rather than
    # suppressing the offering.
    no_signal = _no_signal(category_intent)
    if no_signal:
        corroborating = corroborating - {"Technographics"}

    if not hp_addressable or not corroborating:
        tier = CONTEXT_ONLY
    elif len(corroborating) >= PIPELINES_FOR_OPPORTUNITY:
        tier = OPPORTUNITY
    else:
        tier = CONVERSATION_STARTER

    return {
        "tier": tier,
        "pipelines": sorted(found),
        "corroborating_pipelines": sorted(corroborating),
        "pipeline_count": len(corroborating),
        "threshold": PIPELINES_FOR_OPPORTUNITY,
        "permitted_language": PERMITTED_LANGUAGE[tier],
        "category_intent": category_intent,
        "technology_demoted_for_no_signal": no_signal or None,
        "basis": _basis(tier, sorted(corroborating), sorted(found),
                        hp_addressable, no_signal),
    }


def _basis(tier: str, corroborating: list, found: list,
            addressable: bool, no_signal: bool = False) -> str:
    if no_signal and not corroborating:
        return ("the HP category for this offering shows no intent signal, so "
                "the detected technology is account context rather than "
                "corroboration (banned output K1)")
    if not addressable:
        return ("no HP offering matches this evidence, so it is account context "
                "rather than an opportunity")
    if tier == CONTEXT_ONLY:
        return ("only %s evidence supports this, which describes the account "
                "rather than establishing a need"
                % (", ".join(found) or "no"))
    if tier == CONVERSATION_STARTER:
        return ("one pipeline supports this (%s); section C needs %d "
                "independent pipelines before it is an opportunity"
                % (corroborating[0], PIPELINES_FOR_OPPORTUNITY))
    return ("%d independent pipelines support this: %s"
            % (len(corroborating), ", ".join(corroborating)))
