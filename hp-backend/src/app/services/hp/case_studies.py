"""Pick the HP case study that supports a recommendation, or none at all.

`scripts/load_case_studies.py` builds the corpus; this chooses from it. Five
features have shipped an empty proof-point slot since they were written, and
this is what fills them.

## The rule that governs everything here

From the client's own instruction on how case studies are to be used:

    "Where there is no clear relationship between the account-level data and the
    available HP Product/Service/Solution information or Case Studies, we should
    not force a match. The platform can still provide a general LLM-generated
    recommendation based on the available account evidence, without incorrectly
    associating an HP offering or an unrelated case study."

So **returning nothing is a correct answer**, and a frequent one. `match()`
requires the HP product line to agree before anything else is considered;
industry and account signals only order what is already relevant. A study that
merely shares an industry is not evidence about an HP product, and attaching one
would be exactly the forced match the instruction forbids.

## Why the join is on a computed line, not on a column

Three columns could say what a study is about and none is dependable alone.
`hp_route` has four values - 3D Printing, Workstations, Print, PC-Notebook - and
reaches no security, workforce or device-management study at all.
`solution_categories` is worse: all 192 rows tagged `hp_route = "3D Printing"`
also carry `Print / Managed Print`, so joining on it would file every 3D study
behind a print recommendation. `product_featured`, HP's own product tag, covers
more ground but is absent on fourteen named-customer studies and wrong on
others - the study that finally surfaced the problem is tagged `HP EliteBook`
and is entirely about HP Managed Device Services.

So the line is computed per study by `canonical_line()`, reading the offering
the model took from HP's own title and use case first and falling back to the
tag. That is what recovered the corpus's only collaboration study, which had no
product tag at all and was therefore invisible to a query on one.

## Expect a lot of misses, and let them happen

Most of the corpus is 3D printing, and the Opportunity Map has no 3D card for
those studies to attach to. Collaboration has exactly one study and DaaS none of
its own - device services stands in for it, because managing a fleet is the same
conversation. On a typical account perhaps half the surfaces will carry a proof
point and the rest will correctly carry none.
"""

import logging

logger = logging.getLogger(__name__)

COLLECTION = "hp_case_studies"
VERSION_DOC_ID = "__knowledge_version__"

# What a study is about, as one canonical line.
#
# Two fields could answer that and neither is dependable on its own.
# `product_featured` is HP's own tag: absent on fourteen named-customer studies
# and wrong on others - the Universidad Andrés Bello study is tagged
# "HP EliteBook" and is entirely about HP Managed Device Services. `hp_offering`
# is what the model read out of HP's own title and use case, which is right far
# more often but is free text: "HP Z Workstations", "HP Z workstation" and
# "HP Z Workstation" all appear.
#
# So the offering is preferred, the tag is the fallback, and both are reduced to
# a canonical line by keyword. Ordered most specific first - a Metal Jet study
# must be claimed by 3D before anything else reads "jet".
LINE_3D = "3d"
LINE_WORKSTATION = "workstation"
LINE_PC = "pc"
LINE_SECURITY = "security"
LINE_PRINT = "print"
LINE_WXP = "wxp"
LINE_COLLABORATION = "collaboration"
LINE_DEVICE_SERVICES = "device_services"
LINE_SITEPRINT = "siteprint"

# PROVISIONAL - replace when the Rulebook is wired in.
#
# Which HP offering belongs to which line is read here from keywords, and those
# keywords are this module's own reading rather than anything the client
# defined. HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook is
# the file that settles it authoritatively; it is not loaded yet. When it is,
# this table should give way to its definitions rather than being kept in step
# with them by hand.
OFFERING_KEYWORDS = (
    (LINE_3D, ("multi jet fusion", "jet fusion", "metal jet", "3d print", "3d")),
    (LINE_SITEPRINT, ("siteprint",)),
    (LINE_WORKSTATION, ("z workstation", "zbook", "z by hp", "workstation")),
    (LINE_SECURITY, ("wolf security", "wolf pro", "sure click")),
    (LINE_WXP, ("workforce experience", "wxp")),
    (LINE_COLLABORATION, ("collaboration", "poly", "conferencing", "meeting room")),
    (LINE_DEVICE_SERVICES, ("managed device", "device as a service", "daas",
                            "dynamic configuration", "device life extension")),
    (LINE_PRINT, ("managed print", "pagewide", "print")),
    (LINE_PC, ("elitebook", "dragonfly", "omnibook", "probook", "elite pc",
               "pro pc", "laptop", "notebook")),
)


def canonical_line(study: dict) -> str:
    """The one line a study speaks to, or "" when nothing names an offering."""
    for source in (study.get("hp_offering"), study.get("product_featured")):
        text = _norm(source)
        if not text:
            continue
        for line, keywords in OFFERING_KEYWORDS:
            if any(word in text for word in keywords):
                return line
    return ""


# The platform's HP product lines, to the canonical lines above.
#
# `HP Anyware / DaaS` maps to device services: the corpus has no study tagged
# DaaS, but it holds several about managing a device fleet, which is the same
# conversation. Poly Collaboration reaches the collaboration line - the corpus
# has exactly one such study, Ulster University, and it was invisible until the
# offering was read from the text rather than the tag.
HP_LINE_TO_LINES = {
    "z by hp workstations": (LINE_WORKSTATION,),
    "hp elite / pro pcs": (LINE_PC, LINE_DEVICE_SERVICES),
    "hp wolf security": (LINE_SECURITY,),
    "hp enterprise print / mps": (LINE_PRINT,),
    "poly collaboration": (LINE_COLLABORATION,),
    "hp anyware / daas": (LINE_DEVICE_SERVICES, LINE_WXP),
    "hp workforce experience platform": (LINE_WXP,),

    # The service lines the rulebook names. Added when the Objection Playbook
    # was wired to it: without them "Client Devices" reached no rule at all,
    # because every rule that speaks to a client-device objection - support
    # cover, deployment, lifecycle - sits in one of these three families and
    # this map had no route to them.
    #
    # All three are device services in the sense this codebase already uses the
    # term: they attach to a client estate rather than constituting one. That
    # is the same reading under which "HP Elite / Pro PCs" already carries
    # LINE_DEVICE_SERVICES beside LINE_PC.
    "hp care pack services": (LINE_DEVICE_SERVICES,),
    "hp deployment & configuration services": (LINE_DEVICE_SERVICES,),
    "hp lifecycle & sustainability services": (LINE_DEVICE_SERVICES,),

    # Ink is print supplies, so it reaches the print line and nothing else.
    "original hp ink": (LINE_PRINT,),

    # HP IQ for Enterprise is deliberately absent. It is the rulebook's
    # enterprise-AI family and no canonical line here corresponds to it;
    # attaching it to the workforce line would be a guess, and IQ rules already
    # reach the Opportunity Map through their own routing type.

    # Alternate spellings of lines already mapped above. The same canonical
    # lines, so a study or rule tagged with either wording resolves identically
    # rather than falling through as unmapped.
    "hp elitebook": (LINE_PC, LINE_DEVICE_SERVICES),
    "hp probook": (LINE_PC, LINE_DEVICE_SERVICES),
    "poly studio": (LINE_COLLABORATION,),
    "hp enterprise printing & mps": (LINE_PRINT,),
    "hp anyware": (LINE_DEVICE_SERVICES, LINE_WXP),
    "hp daas": (LINE_DEVICE_SERVICES, LINE_WXP),
}

# The Objection Playbook's five fixed areas. An area is a technology category
# rather than an HP line, so this is a second door into the same corpus.
AREA_TO_LINES = {
    "client devices": (LINE_PC, LINE_DEVICE_SERVICES),
    "device management": (LINE_WXP, LINE_DEVICE_SERVICES),
    "endpoint security": (LINE_SECURITY,),
    "print / mps": (LINE_PRINT,),
    "collaboration": (LINE_COLLABORATION,),
}

# Ranking, in the order the client settled on 25 Sep:
#
#     "1. Same use case -> 2. Same industry -> 3. APJ/APAC region ->
#      4. Stated outcome/metric -> 5. HP.com (T0) before third-party (T2)"
#     "the same use case should always be the first priority. Region should not
#      override the use-case match."
#
# The weights are spaced so a lower key can never outrank a higher one however
# the counts fall: one shared use-case tag beats any combination of industry,
# outcome and tier. Before this, industry was the highest key at 10 and the use
# case scored 3 - and never fired at all, because no caller passed `signals`.
#
# Region (key 3) is deliberately absent. It is not in the corpus and cannot be
# derived: all 89 studies carry a global HP URL ("us-en" pages, or GetDocument
# ids), so none of them says where the customer is. Inventing a region from the
# customer's name would be a guess presented as a fact. The client has been
# asked for a region column; the key slots in between industry and outcome when
# it arrives.
SCORE_PER_SHARED_SIGNAL = 100  # key 1, use case
SCORE_SAME_INDUSTRY = 10       # key 2
SCORE_HAS_OUTCOME = 4          # key 4, a stated result
SCORE_HP_PUBLISHED = 2         # key 5, T0 over T2
SCORE_HAS_CHALLENGE = 1
# A study whose source described no engagement carries only its attribution -
# "HP published a case study with X featuring Y". Real, citable, and the weakest
# thing here, so anything narrated outranks it.
SCORE_NARRATED = 2

# The corpus's own use-case vocabulary, read off `signal_tags` (present on all
# 89 studies). These are the tags the case-study file itself supplies in
# `account_signal_match`; nothing here is invented.
#
# The map goes from the opportunity a feature is already holding - an objection
# area, a play's opportunity type, a Tech Map or Intent category - to the tags
# that describe the same work. That direction matters: the client asked for case
# studies to be checked against "the account evidence/use case", and refused a
# fixed Rulebook-to-case-study table. The Rulebook is not consulted here.
USE_CASE_TAGS = {
    "Engineering-Product-Development": (
        "workstation", "engineering", "design", "cad", "3d", "product development",
        "simulation", "rendering", "modelling", "modeling", "prototyp"),
    "Production-Optimization": (
        "production", "manufactur", "factory", "throughput", "tooling",
        "additive", "supply chain", "cost reduction", "efficiency"),
    "Industrial-Manufacturing": (
        "industrial", "manufactur", "heavy equipment", "automotive", "mining",
        "plant", "machinery"),
    "Digital-Transformation": (
        "digital transformation", "modernis", "moderniz", "transformation",
        "cloud", "automation", "digitis", "digitiz"),
    # "fleet" on its own is not here: it matches "Print Fleet & Document
    # Infrastructure", which is a different fleet entirely. The corpus has no
    # print use-case tag, so a print opportunity correctly matches nothing and
    # falls back to industry and outcome.
    "Fleet-Refresh": (
        "device fleet", "fleet refresh", "refresh", "pc", "laptop", "notebook",
        "client device", "device lifecycle", "daas", "device as a service",
        "deployment"),
    "Workforce-Modernization": (
        "workforce", "employee experience", "hybrid", "flexible working",
        "wxp", "workforce experience", "productivity", "endpoint experience"),
    "Security": (
        "security", "endpoint protection", "threat", "wolf", "compliance",
        "zero trust"),
    "Remote-Collaboration": (
        "collaboration", "poly", "meeting", "conferencing", "hybrid workplace",
        "video"),
}


def signals_for_opportunity(*texts) -> list:
    """The corpus's use-case tags an opportunity speaks to.

    Callers pass whatever names the opportunity they are about to attach proof
    to - a category name, a play title and its type, an objection area. Several
    arguments are accepted because the name alone is often too short to match on
    ("PC", "3D"), while the title beside it is not.

    Returns [] when nothing matches, which leaves ranking exactly as it was
    before this existed: industry, then outcome, then tier.
    """
    blob = " ".join(_norm(t) for t in texts if _norm(t))
    if not blob:
        return []
    return [tag for tag, words in USE_CASE_TAGS.items()
            if any(word in blob for word in words)]

# How far down the ranked list a caller will look.
PROOF_POINT_CANDIDATES = 5

# How deep `allocate` searches for an uncited study. Deeper than any single
# surface needs, because several surfaces draw on one line - four reach device
# services - and the fourth still has to find something rather than give up and
# repeat what the first took.
ALLOCATION_DEPTH = 25


# The corpus labels each study with one of eleven industries. An account's
# industry arrives as whatever its firmographics record says, which is a
# slash-joined pile of classification systems - Astra's is "automation machinery
# manufacturing / Other Industrial Machinery Manufacturing / Industrial
# machinery, nec". Matched on keywords because no two vocabularies agree, and
# ordered most specific first: a car maker is Automotive rather than the
# Industrial Manufacturing its SIC code also implies.
INDUSTRY_KEYWORDS = (
    ("Automotive", ("automotive", "vehicle", "car ", "motor", "automobile")),
    ("Aerospace", ("aerospace", "aviation", "aircraft", "space", "defence", "defense")),
    ("Healthcare", ("health", "medical", "hospital", "pharma", "clinic",
                    "prosthet", "orthot", "life science")),
    ("Education", ("education", "university", "college", "school", "academic")),
    ("Logistics", ("logistic", "freight", "shipping", "warehous", "supply chain")),
    ("Media & Entertainment", ("media", "entertainment", "broadcast", "film",
                               "cinema", "publishing")),
    ("Consumer Goods", ("consumer goods", "retail", "fmcg", "apparel", "food",
                        "beverage")),
    ("IT Services", ("it services", "systems integrat", "managed service",
                     "consulting", "outsourc")),
    ("Technology", ("software", "technology", "saas", "semiconductor",
                    "electronics", "telecom")),
    # Last: almost any manufacturer's classification string mentions one of
    # these, so a more specific industry above must get first refusal.
    ("Industrial Manufacturing", ("manufactur", "industrial", "machinery",
                                  "engineering", "production", "factory",
                                  "construction", "heavy equipment", "mining")),
)


def normalise_industry(raw: str) -> str:
    """An account's industry string as one of the corpus's own labels, or "".

    Returning "" is fine - industry only orders results that already matched on
    product, so an unrecognised one costs relevance, never correctness.
    """
    text = " ".join(str(raw or "").split()).lower()
    if not text:
        return ""
    for label, keywords in INDUSTRY_KEYWORDS:
        if any(word in text for word in keywords):
            return label
    return ""


def knowledge_version(db) -> str:
    """The loaded corpus's version, for a feature's cache fingerprint.

    A card stores the proof point it was given, so reloading the corpus with
    corrected prose must invalidate the cards that cite it. Without this the
    Endpoint Security card kept a sentence written from a photograph caption
    long after the loader had replaced it - the evidence had not changed, so
    nothing asked for the card again.

    Returns "" when the corpus has never been loaded, which is stable: a
    feature that has no proof points to lose should not rebuild every run.
    """
    try:
        doc = db[COLLECTION].find_one({"_id": VERSION_DOC_ID}) or {}
    except Exception:
        logger.exception("case studies: could not read the knowledge version")
        return ""
    return str(doc.get("knowledge_version") or "")


def _norm(value) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def lines_for_hp_line(hp_line: str) -> tuple:
    """The canonical lines an HP product line corresponds to."""
    return HP_LINE_TO_LINES.get(_norm(hp_line), ())


def lines_for_product_text(text: str) -> tuple:
    """The canonical lines named anywhere in a piece of product text.

    `lines_for_hp_line` is an exact lookup, so it answers only for names
    spelled exactly as the map spells them. The features name their HP play in
    their own words - "HP Multi Jet Fusion (3D)", "Poly Collaboration
    Hardware", "HP Enterprise Printing & Managed Print Services" - and every
    one of those missed. This runs the same token map that validates HP product
    names everywhere else, then maps what it finds.
    """
    from app.services.extractors import grounding

    lowered = str(text or "").lower()
    if not lowered.strip():
        return ()
    out: list = []
    for tokens, canonical in grounding.HP_LINE_TOKENS:
        if not any(token in lowered for token in tokens):
            continue
        for line in lines_for_hp_line(canonical):
            if line not in out:
                out.append(line)

    # Then the corpus's own vocabulary, which is what classified the studies in
    # the first place. Without this, 3D is unreachable: `HP_LINE_TO_LINES` has
    # no key for it, so "HP Multi Jet Fusion (3D)" mapped to nothing while 63 of
    # the 89 studies sit on the 3D line. Using one table for both directions is
    # also what keeps them from drifting apart.
    for line, keywords in OFFERING_KEYWORDS:
        if line in out:
            continue
        if any(keyword in lowered for keyword in keywords):
            out.append(line)
    return tuple(out)


def lines_for_area(area: str) -> tuple:
    """The canonical lines an Objection Playbook area corresponds to."""
    return AREA_TO_LINES.get(_norm(area), ())


def _score(study: dict, industry: str, signals) -> tuple:
    """Ranking key, highest first. Returned as a tuple so ties break stably."""
    points = 0
    if industry and _norm(study.get("industry")) == _norm(industry):
        points += SCORE_SAME_INDUSTRY

    wanted = {_norm(s) for s in (signals or []) if _norm(s)}
    shared = wanted & {_norm(t) for t in (study.get("signal_tags") or [])}
    points += SCORE_PER_SHARED_SIGNAL * len(shared)

    if study.get("outcome"):
        points += SCORE_HAS_OUTCOME
    # Key 5: HP's own page before a third party's. T0 is hp.com, T2 is everyone
    # else. A study with no tier recorded is not penalised - absence of the
    # field is not evidence that HP did not publish it.
    if _norm(study.get("source_tier")) == "t0":
        points += SCORE_HP_PUBLISHED
    if study.get("challenge"):
        points += SCORE_HAS_CHALLENGE
    if not study.get("attribution_only"):
        points += SCORE_NARRATED

    # Ties are common: on a card where no study matches the account's industry,
    # every candidate with a stated outcome scores the same. Breaking that on
    # the customer's name is arbitrary - it once put a Chilean university ahead
    # of two equally relevant studies purely because "universidad" sorts late.
    #
    # The number of source assets is a better tie-break: a study HP published
    # across several pages has more behind it than a single stub, so it is the
    # fuller thing for a seller to hand over. The name stays last, only so a
    # rerun on unchanged data returns the same order.
    return (points, int(study.get("merged_from_assets") or 1),
            _norm(study.get("customer")))


def match(db, lines, industry: str = "", signals=None, limit: int = 1) -> list:
    """Case studies supporting a recommendation about `lines`.

    `lines` is the canonical lines to accept - use `lines_for_hp_line` or
    `lines_for_area` to get them. An empty `lines` returns nothing, which is the
    honest answer for an HP line the corpus does not cover, rather than falling
    back to industry alone.

    The line is computed in Python rather than queried, because it comes from
    whichever of two unreliable fields actually names an offering. The corpus is
    under a hundred documents, so reading it whole costs nothing.
    """
    wanted = {_norm(line) for line in (lines or []) if _norm(line)}
    if not wanted:
        return []

    try:
        everything = list(db[COLLECTION].find({"_id": {"$ne": VERSION_DOC_ID}}))
    except Exception:
        logger.exception("case studies: lookup failed for %s", wanted)
        return []

    # A study with no headline is unpublishable - `as_proof_point` returns None
    # for it - so it is dropped here rather than allowed to win a card and then
    # render as nothing. One exists: every figure it carried came from text
    # clipped mid-sentence, so every sentence written from it was rejected.
    candidates = [s for s in everything
                  if canonical_line(s) in wanted and str(s.get("headline") or "").strip()]

    candidates.sort(key=lambda s: _score(s, industry, signals), reverse=True)
    return candidates[:max(1, limit)]


def as_proof_point(study: dict) -> dict | None:
    """One study in the shape a feature stores on a card.

    `text` is assembled from fields the model already wrote and that were
    already number-checked at load time, so nothing here needs re-verifying
    against anything - which is the point of enriching once rather than per
    render. The outcome is appended only when the study has one; most do not,
    and a headline alone is still a real HP customer a seller can point to.
    """
    if not study:
        return None

    headline = str(study.get("headline") or "").strip()
    if not headline:
        return None

    outcome = str(study.get("outcome") or "").strip()
    return {
        "text": ("%s %s" % (headline, outcome)).strip() if outcome else headline,
        # Carried so cross-surface allocation can match on identity rather than
        # on a display name. Two HP studies can share a customer name; none
        # share an id.
        "study_id": str(study.get("_id") or "") or None,
        "customer": study.get("customer"),
        "industry": study.get("industry"),
        "hp_product": study.get("product_featured"),
        "headline": headline,
        "outcome": outcome or None,
        "challenge": study.get("challenge") or None,
        "use_case": study.get("use_case") or None,
        "why_relevant": study.get("why_relevant") or None,
        "source_url": study.get("source_url"),
        "source": "hp_case_studies",
    }


# The surfaces that cite a case study, in the order they get to choose.
#
# Allocation has to be DETERMINISTIC, not first-come. If each feature simply
# avoided whatever the others had already stored, the answer would depend on
# which feature was regenerated last: regenerate the map and it takes one
# study; regenerate messaging first and messaging takes it instead. A seller
# would watch references shuffle between surfaces for no reason they could see.
#
# So the order is fixed here and a surface yields ONLY to the surfaces above it.
# Whatever regenerates, the same surface wins the same study.
#
# Ordered by how little freedom each has. The Objection Playbook's five areas
# are fixed, always rendered, and land on the corpus's thinnest lines
# (collaboration holds one study, security one, print two), so it chooses
# first. The Opportunity Map's plays vary with the account but each names its
# own HP lines. Messaging pillars name several lines each, so they have the
# most room to move. Content Studio is one asset generated on request and is
# the easiest thing to re-run, so it goes last.
SURFACE_OBJECTIONS = "objection_reframe_cards"
SURFACE_OPPORTUNITIES = "opportunity_narrative_plays"
SURFACE_MESSAGING = "messaging_pillars_output"
SURFACE_CONTENT = "content_generated_assets"

# The Executive Dashboard picks LAST. Its catalysts are derived from whatever
# the account's own filings say, so the HP line a catalyst touches is the most
# flexible of any surface - it can nearly always take the next-best study, while
# the Objection Playbook's five fixed areas cannot.
SURFACE_EXEC = "exec_strategic_priorities"

# The three signal surfaces the client added on 24 Sep: proof may strengthen an
# existing recommendation in Live Signals' "Implication for HP", Intent's "So
# What for HP" and the Technographic Map's "what it means for HP" - "nowhere
# else", and "we are not trying to compulsorily include it".
#
# They pick AFTER the Executive Dashboard, and therefore last of all. Each one
# strengthens a recommendation that already stands on its own evidence, so an
# empty slot costs the reader nothing, while taking a study from the Objection
# Playbook - where the card exists to carry proof - costs a great deal. The
# Stakeholder Map is deliberately absent: it was asked for under item 30 and
# then withdrawn ("Sahaj mentioned not right now").
SURFACE_SIGNALS = "news_signals_feed"
SURFACE_INTENT = "intent_category_summary"
SURFACE_TECHMAP = "technographic_map"

SURFACE_ORDER = (SURFACE_OBJECTIONS, SURFACE_OPPORTUNITIES,
                 SURFACE_MESSAGING, SURFACE_CONTENT, SURFACE_EXEC,
                 SURFACE_SIGNALS, SURFACE_INTENT, SURFACE_TECHMAP)

# Where each surface keeps the records that carry a proof point. A path is
# walked by `_walk` below; "[]" means "every item in this list".
SURFACE_PATHS = {
    SURFACE_OBJECTIONS: ("data", "cards", "[]"),
    SURFACE_OPPORTUNITIES: ("data", "opportunity_plays", "[]"),
    SURFACE_MESSAGING: ("data", "pillars", "[]"),
    SURFACE_CONTENT: ("data", "assets", "[]", "generated"),
    SURFACE_EXEC: ("data", "priorities", "[]"),
    SURFACE_SIGNALS: ("data", "signals", "[]"),
    SURFACE_INTENT: ("data", "hp_categories", "[]"),
    SURFACE_TECHMAP: ("data", "categories", "[]"),
}


def _quality_tier(study: dict, industry: str) -> tuple:
    """What a reader would actually notice, highest first.

    Spreading customers across surfaces is only worth doing while it costs
    nothing a seller can see. These are the two things they would see:

      - whether the study is in their prospect's industry, which is what makes
        a proof point persuasive rather than merely true;
      - whether it tells a story at all, rather than being the bare attribution
        written for a source that described no engagement.

    Everything else `_score` weighs - a shared signal tag, a stated challenge -
    orders equally good candidates and is invisible on the page. So variety may
    trade those away, and may never trade these.
    """
    return (
        1 if industry and _norm(study.get("industry")) == _norm(industry) else 0,
        0 if study.get("attribution_only") else 1,
    )


def _walk(node, path):
    """Every value at `path` inside a widget document."""
    if not path:
        yield node
        return
    head, rest = path[0], path[1:]
    if head == "[]":
        for item in (node if isinstance(node, list) else []):
            yield from _walk(item, rest)
    elif isinstance(node, dict):
        yield from _walk(node.get(head), rest)


def _study_identity(study: dict) -> str:
    """A corpus row, in the same terms a stored proof point is recognised by."""
    return _identity({"study_id": str(study.get("_id") or ""),
                      "customer": study.get("customer")})


def _identity(detail) -> str:
    """How a stored proof point is recognised again.

    The id when one is there. A record written before proof points carried an
    id falls back to the customer name, so an older widget still reserves its
    study instead of being silently re-cited somewhere else.
    """
    if not isinstance(detail, dict):
        return ""
    return str(detail.get("study_id") or "").strip() or _norm(detail.get("customer"))


def cited_above(db, account_id: str, surface: str) -> set:
    """Studies already cited on this account by higher-priority surfaces.

    Read from what those surfaces actually stored rather than from a ledger of
    our own: the widgets ARE the record, so there is no second copy to fall out
    of step when one is regenerated, deleted, or was written before any of this
    existed.

    A surface not named in `SURFACE_ORDER` yields to all of them, which is the
    safe default for a caller added later.
    """
    try:
        rank = SURFACE_ORDER.index(surface)
    except ValueError:
        rank = len(SURFACE_ORDER)

    taken: set = set()
    for above in SURFACE_ORDER[:rank]:
        try:
            doc = db["account_widgets"].find_one(
                {"account_id": account_id, "widget_key": above})
        except Exception:
            logger.exception("case studies: could not read %s for allocation", above)
            continue
        for record in _walk(doc or {}, SURFACE_PATHS[above]):
            if not isinstance(record, dict):
                continue
            key = _identity(record.get("hp_proof_point_detail"))
            if key:
                taken.add(key)
    return taken


def allocate(db, lines, industry: str = "", signals=None,
             taken=None, used_here=None) -> dict | None:
    """The best study for one card, preferring one nothing else has cited.

    Two exclusion sets, because the two kinds of repeat are not equally bad:

    `used_here` - studies this surface has already cited on an earlier card. A
    HARD constraint. The five objection cards, or the pillars of one message
    house, are read together as a single document, so the same customer twice
    reads as a mistake rather than as emphasis. Rather than repeat, this
    returns None and the card carries no proof point.

    `taken` - studies cited on OTHER surfaces, from `cited_above`. A SOFT
    constraint. Nobody reads the objection playbook and the message house side
    by side, so a genuinely apt study appearing on both is a far smaller cost
    than a weak study, or an empty slot, on either. It is avoided where the
    corpus allows and repeated where it does not.

    Variety is a tie-break, never a trade. The best candidate sets the quality
    bar (`_quality_tier`) and an uncited study is preferred only if it meets
    that same bar - so spreading customers about can never cost the reader an
    industry match or a narrated story. Where a line holds a single study -
    collaboration holds exactly one - the cross-surface repeat is correct and
    is returned.

    Returns the stored shape, or None when the lines reach nothing usable.
    """
    spoken = {str(t) for t in (taken or []) if str(t)}
    mine = {str(t) for t in (used_here or []) if str(t)}

    candidates = [study for study in match(db, lines, industry, signals,
                                           limit=ALLOCATION_DEPTH)
                  if str(study.get("headline") or "").strip()
                  and _study_identity(study) not in mine]
    if not candidates:
        return None

    bar = _quality_tier(candidates[0], industry)
    for study in candidates:
        if _quality_tier(study, industry) < bar:
            break           # ranked by tier, so nothing below here clears it
        if _study_identity(study) not in spoken:
            return as_proof_point(study)

    # Everything good enough is cited on another surface. Repeat the best of
    # them rather than drop to a weaker study or leave the card empty.
    return as_proof_point(candidates[0])


def proof_point_for(db, lines, industry: str = "", signals=None) -> dict | None:
    """The best supporting study, ready to store, or None.

    Walks the ranked list rather than taking the top one, so a study that
    cannot be rendered does not cost the caller its proof point.
    """
    for study in match(db, lines, industry, signals, limit=PROOF_POINT_CANDIDATES):
        point = as_proof_point(study)
        if point:
            return point
    return None
