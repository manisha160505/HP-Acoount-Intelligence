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

# Ranking. Deliberately small: the candidate set after the product filter is
# usually under a dozen, so elaborate scoring would be false precision.
SCORE_SAME_INDUSTRY = 10
SCORE_PER_SHARED_SIGNAL = 3
SCORE_HAS_OUTCOME = 4          # a stated result is the most persuasive thing here
SCORE_HAS_CHALLENGE = 1
# A study whose source described no engagement carries only its attribution -
# "HP published a case study with X featuring Y". Real, citable, and the weakest
# thing here, so anything narrated outranks it.
SCORE_NARRATED = 2

# How far down the ranked list a caller will look. Features that cite one study
# per card walk it themselves to skip customers already used elsewhere.
PROOF_POINT_CANDIDATES = 5


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
