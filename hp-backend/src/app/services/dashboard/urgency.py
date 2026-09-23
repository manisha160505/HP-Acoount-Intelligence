"""Urgency Score: four weighted drivers, one 0-100 number.

    Urgency = 20% Workplace Technology and OS Opportunity
            + 25% AI and Workstation Opportunity
            + 30% Growth and Expansion Signals
            + 25% HP Solution Intent

This implements `HP_Urgency_Score_Updated_Final.pdf` ("HP Account Urgency Score
Final Logic"), which is the first version of this score the **client** has
authored. It replaces the five delivery-invented drivers that stood here before
(20/25/15/15/25 over Fleet Refresh, AI/Workstation, Hiring, Expansion, Intent).
Two structural changes came with it:

**Hiring is no longer a driver.** The PDF states it directly - *"The former
standalone Hiring and Workforce Demand driver has been removed. Its remaining
hiring-volume signal is incorporated here [Growth and Expansion]. The 30% weight
preserves the previous combined 15% Hiring + 15% Growth weighting."* Recent
hiring volume is now term B of Growth and Expansion, worth 50 of that driver's
100 points.

**The missing-input rule is inverted.** The old rule refused to compute a score
at all if any driver was unavailable. The PDF replaces it: *"Missing inputs
contribute 0 points only to the affected component. The remaining available
components are still calculated."* A component with no data now scores 0 and the
composite still publishes. `MISSING_INPUT_RULE` records this, because it is the
one change that makes new numbers appear where the dashboard previously showed
N/A, and anyone reading a score for the first time should be able to find out
why.

Every band, point value and cap below is quoted from the PDF. Where the PDF
leaves something to judgement, the module says so in the payload rather than
choosing quietly. Three such places exist, all published as `caveats`:

**One calculation feeds every surface.** A driver's contribution is its value
times its weight, rounded once; the total is the sum of exactly those published
figures, and the headline score is that total rounded. `exact_score` carries the
unrounded total so a reader can trace the headline without re-deriving it.
Summing the unrounded products behind the scenes would let the contributions on
screen add up to something the headline contradicts, which is the defect the
source document itself has (its section 4 prints 12.33 from a component its own
table gives as 50.4, and its closing line prints 61 against a table summing to
64.43). The screen's own numbers are the authority.

**Intent trend is scored from the file's own words.** Section 4B scores
Increasing=10 / Stable=5 / Decreasing=0. The client has ruled the HP category
intent file the source of truth - its scores and fields are vendor-verified and
are used as supplied - so the label is scored as written and presented without
qualification. The same ruling emptied the keyword-noise gate
(`NOISY_CATEGORY_TERMS`), so the primary category is simply the highest-scoring
one, exactly as the PDF states.

**The workforce growth proxy needs `extended_company`.** Section 3A reads dated
`associated_members` values out of `social_stats`. That dataset is registered but
was marked `not_consumed`; it is now read here. Where it is absent or carries no
comparable history the component scores 0 per the missing-input rule, and the
term says which of the two it was.

**Qualifying technologies are matched against a published list.** Sections 1C and
2A define qualification in prose ("documented connection to an HP workplace
solution") plus examples. The examples are encoded literally below as
`WORKPLACE_TECHNOLOGIES` and `AI_ML_TECHNOLOGIES`; a technology not on the list
does not qualify. This under-counts rather than over-counts, which is the safe
direction for a score a seller acts on.

Evidence reuse follows the previous rule, which the PDF does not contradict: if
one evidence item supports two drivers it is linked to both rather than
deduplicated, and `shared_evidence` reports which IDs landed in more than one.
"""

import json
import logging
import re
from datetime import UTC, date, datetime

from app.config import scoring as _scoring
from app.services.hp import intent_topic_map

logger = logging.getLogger(__name__)

# Every weight, band and cap below is loaded from config/scoring.yaml rather
# than written here, so the client's numbers can be retuned without editing
# this module. The names are unchanged, so nothing downstream moves.
_CFG = _scoring.section("urgency")

# HP_Urgency_Score_Updated_Final.pdf, "Overall scoring model".
WEIGHTS = _scoring.weights("urgency")

DRIVER_LABELS = {
    "workplace_os": "Workplace Technology and OS Opportunity",
    "ai_workstation": "AI and Workstation Opportunity",
    "growth_expansion": "Growth and Expansion Signals",
    "hp_solution_intent": "HP Solution Intent",
}

# Driver order on screen, matching the PDF's own listing order.
DRIVER_KEYS = ("workplace_os", "ai_workstation", "growth_expansion",
               "hp_solution_intent")

FORMULA_AUTHORITY = (
    "Weights (20/25/30/25) and every band, point value and cap below are from "
    "HP_Urgency_Score_Updated_Final.pdf, 'HP Account Urgency Score Final "
    "Logic', supplied by the client. This supersedes the delivery-authored "
    "20/25/15/15/25 formula that stood here previously.")

MISSING_INPUT_RULE = (
    "Missing inputs contribute 0 points only to the affected component; the "
    "remaining components are still calculated and the overall score still "
    "publishes. This REPLACES the earlier rule, under which one unavailable "
    "driver blocked the whole score.")

SCOPE_NOTE = (
    "Uses fields present in the supplied Astra-format datasets. It does not "
    "assume access to PC brands, printer brands, device age, Windows version, "
    "warranty data or other unavailable account fields.")

DRIVER_MAX = _CFG["driver_max"]

# Job records are eligible only inside this window (PDF: "only records dated
# within the latest 12 months are eligible for scoring"). The same window
# governs news events in sections 2C and 3C.
WINDOW_DAYS = _CFG["window_days"]

# --- 1. Workplace Technology and OS Opportunity (20%) -----------------------

# A. Account scale - 30 points. Source A, 1_Firmographics, Number Of Employees
# Range. Ladder position scores; no number is parsed out of the band string.
EMPLOYEE_BANDS = _scoring.bands("urgency", "employee_bands")
ACCOUNT_SCALE_MAX = _CFG["account_scale_max"]

# Aliases for how vendors actually spell these bands. Each maps to a band above.
EMPLOYEE_BAND_ALIASES = {
    "10001+": "10001-49999",
    "50001+": "50000+",
    "50000ormore": "50000+",
    "1-10": "below250", "11-50": "below250", "51-200": "below250",
    "201-500": "251-1000", "501-1000": "251-1000",
    "1-250": "below250", "250-1000": "251-1000",
}

# B. OS environment - 40 points. Highest applicable rule wins.
OS_ENVIRONMENT_MAX = _CFG["os_environment_max"]
OS_COMBINATION_POINTS = (
    (("linux", "windows"), 40),
    (("linux", "apple"), 35),
    (("linux", "other"), 35),
    (("windows", "apple"), 30),
    (("windows", "other"), 30),
    (("apple", "other"), 20),
    (("linux",), 30),
    (("windows",), 25),
    (("apple",), 15),
    (("other",), 10),
)

# OS families. "Apple iOS is treated as an Apple OS family, not as macOS" - the
# PDF's own Astra note - so iOS and iPadOS sit in the apple family.
OS_FAMILIES = {
    "windows": ("windows", "microsoft windows"),
    "apple": ("macos", "mac os", "osx", "os x", "ios", "ipados", "apple ios"),
    "linux": ("linux", "centos", "ubuntu", "red hat", "redhat", "debian",
              "suse", "fedora"),
    # "Another recognised OS may include ChromeOS, Unix or Android."
    "other": ("chromeos", "chrome os", "unix", "android", "solaris", "aix"),
}

# C. Workplace technology footprint - 30 points, banded on the COUNT of distinct
# qualifying technologies. Capped: "an account with 12 qualifying technologies
# still receives 30/30, not 12 x 5 = 60."
WORKPLACE_FOOTPRINT_BANDS = _scoring.bands("urgency", "workplace_footprint_bands")
WORKPLACE_FOOTPRINT_MAX = _CFG["workplace_footprint_max"]

# The PDF's qualifying examples, encoded literally. A technology qualifies only
# where the PDF names it or names its category; anything else does not count.
WORKPLACE_TECHNOLOGIES = {
    "microsoft intune": "Endpoint and device management",
    "intune": "Endpoint and device management",
    "microsoft entra": "Identity and access management",
    "entra id": "Identity and access management",
    "azure ad": "Identity and access management",
    "azure active directory": "Identity and access management",
    "servicenow": "IT service management / workplace operations",
    "power bi": "Business intelligence and workplace analytics",
    "tableau": "Business intelligence and workplace analytics",
    "power automate": "Automation and workflow",
    "microsoft teams": "Collaboration",
    "vmware vsphere": "Virtual desktop / digital workspace",
    "vmware esxi": "Virtual desktop / digital workspace",
    "vmware horizon": "Virtual desktop / digital workspace",
    "vsphere": "Virtual desktop / digital workspace",
    "esxi": "Virtual desktop / digital workspace",
    "vmware": "Virtual desktop / digital workspace",
    "microsoft 365": "Other workplace technologies",
    "office 365": "Other workplace technologies",
    "google workspace": "Other workplace technologies",
    "g suite": "Other workplace technologies",
    "sharepoint": "Other workplace technologies",
    "zoom": "Other workplace technologies",
    "webex": "Other workplace technologies",
    "splunk": "Other workplace technologies",
}

# --- 2. AI and Workstation Opportunity (25%) --------------------------------

# A. Breadth - 35 points, on how many of the four core families are present.
# Keyed by how many core families were found, so the YAML's string keys are
# converted back to ints here - a lookup by `len(families)` would otherwise
# silently miss every time and score zero.
AI_BREADTH_POINTS = {int(k): v for k, v in
                     (_CFG.get("ai_breadth_points") or {}).items()}
AI_BREADTH_MAX = _CFG["ai_breadth_max"]

# "Similar terms are grouped into the same family and counted once."
AI_CORE_FAMILIES = {
    "AI / Artificial Intelligence": ("artificial intelligence", "ai"),
    "ML / Machine Learning": ("machine learning", "ml"),
    "Generative AI / GenAI": ("generative ai", "genai", "gen ai"),
    "LLM / Large Language Models": ("llm", "large language model", "vllm"),
}

# A family term that is a bare acronym would match inside unrelated words
# ("ml" in "html", "ai" in "chain"), so acronyms are matched as whole tokens.
AI_FAMILY_ACRONYMS = {"ai", "ml", "llm", "vllm", "genai"}

# A. Depth - 35 points, banded on the COUNT of distinct detailed evidence items
# (detailed AI/ML intent signals + qualifying AI/ML technologies).
AI_DEPTH_BANDS = _scoring.bands("urgency", "ai_depth_bands")
AI_DEPTH_MAX = _CFG["ai_depth_max"]

# "Qualifying technology examples include PyTorch, TensorFlow, Keras,
# scikit-learn, Apache Spark MLlib and other technologies clearly identified as
# AI/ML development, training, inference or deployment technologies."
AI_ML_TECHNOLOGIES = (
    "pytorch", "tensorflow", "keras", "scikit-learn", "scikit learn",
    "sklearn", "spark mllib", "mllib", "hugging face", "huggingface",
    "onnx", "xgboost", "lightgbm", "mlflow", "kubeflow", "sagemaker",
    "vertex ai", "azure machine learning", "databricks ml", "openai",
    "anthropic", "langchain", "nvidia cuda", "cudnn", "tensorrt",
)

# A detailed AI/ML intent signal: any intent topic that clearly relates to AI or
# ML. "Generic analytics, cloud, database or software evidence is excluded
# unless it clearly relates to AI or ML."
AI_DEPTH_TERMS = (
    "ai", "artificial intelligence", "machine learning", "ml", "deep learning",
    "neural", "generative ai", "genai", "llm", "large language model",
    "openai", "gpt", "vector database", "model training", "inference",
    "mlops", "ai chips", "computer vision", "nlp",
    "natural language processing", "transformer", "embedding",
)

# B. Workstation intent - 15 points, linear on the score. hp_intent_results,
# Workstations Intent Score: points = score / 100 x 15.
WORKSTATION_INTENT_MAX = _CFG["workstation_intent_max"]

# C. Recent AI initiatives - 5 points per unique verified AI event in the last
# 12 months, capped at 15.
POINTS_PER_AI_EVENT = _CFG["points_per_ai_event"]
AI_EVENT_MAX = _CFG["ai_event_max"]

# "Qualifying events must explicitly concern AI, machine learning, generative
# AI, large language models, an AI centre of excellence, AI infrastructure, or
# an AI partnership or investment. General technology announcements do not
# qualify."
AI_EVENT_TERMS = (
    "artificial intelligence", "machine learning", "generative ai", "genai",
    "large language model", "llm", "ai centre of excellence",
    "ai center of excellence", "ai infrastructure", "ai partnership",
    "ai investment", "ai lab", "ai research", "deep learning",
)

# --- 3. Growth and Expansion Signals (30%) ----------------------------------

# A. Workforce growth proxy - 25 points. Source B, extended_company,
# social_stats, dated associated_members values. A LinkedIn proxy, not verified
# headcount.
GROWTH_BANDS = _scoring.bands("urgency", "growth_bands")
GROWTH_MAX = 25

# B. Recent hiring volume - 50 points, banded on eligible job records.
HIRING_VOLUME_BANDS = _scoring.bands("urgency", "hiring_volume_bands")
HIRING_VOLUME_MAX = _CFG["hiring_volume_max"]

# C. Verified growth and expansion events - 10 points each, capped at 25.
POINTS_PER_GROWTH_EVENT = _CFG["points_per_growth_event"]
GROWTH_EVENT_MAX = _CFG["growth_event_max"]

GROWTH_EVENT_TERMS = (
    "new office", "headquarters", "facility", "plant", "factory",
    "data centre", "data center", "operational site", "new site",
    "expansion", "expands", "expanding", "capacity", "new market",
    "market entry", "enters", "capex", "capital expenditure", "investment",
    "invests", "acquisition", "acquires", "merger", "joint venture",
    "workforce expansion", "new business unit", "hiring spree", "relocat",
)

# "Do not count ordinary product launches, routine earnings announcements,
# general partnerships, awards, residential developments, generic capex or
# investment with no identified growth purpose."
GROWTH_EVENT_EXCLUSIONS = (
    "product launch", "launches product", "quarterly results",
    "earnings call", "annual results", "wins award", "award for",
    "residential", "apartment", "housing project",
)

# --- 4. HP Solution Intent (25%) --------------------------------------------

# Source: hp_intent_results. "Use the fields belonging to the highest-scoring HP
# category."
HP_CATEGORY_INTENT_MAX = _CFG["hp_category_intent_max"]      # A: score / 100 x 60
INTENT_TREND_POINTS = _CFG["intent_trend_points"]
INTENT_TREND_MAX = _CFG["intent_trend_max"]            # B
BUYING_STAGE_POINTS = _CFG["buying_stage_points"]
BUYING_STAGE_MAX = _CFG["buying_stage_max"]            # C
RESEARCH_VOLUME_POINTS = _CFG["research_volume_points"]
RESEARCH_VOLUME_MAX = _CFG["research_volume_max"]         # D

# Keyword-noise gate, now empty by client instruction (Sep 2026).
#
# This used to bar a category whose score rested on an ambiguous keyword from
# becoming the account's primary. The client has ruled that the category file
# is the source of truth - its scores are vendor-verified and used as supplied
# - so the dictionary is empty and this driver now does exactly what the PDF
# says: "use the fields belonging to the highest-scoring HP category", with no
# eligibility test in front of it.
#
# The tuple is still read from Intent & Demand Signals' own dictionary rather
# than copied, so if terms are ever put back both features gate identically.
NOISY_KEYWORDS = tuple(intent_topic_map.NOISY_CATEGORY_TERMS)


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _lower(value) -> str:
    return _text(value).lower()


def _any_term(haystack: str, terms) -> bool:
    return any(term in haystack for term in terms)


def _token_match(haystack: str, term: str) -> bool:
    """Whole-token match, so "ml" does not fire inside "html"."""
    return re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(term),
                     haystack) is not None


def _normalise_band(value) -> str:
    """Compare band strings on letters and digits only.

    Bands arrive spelled inconsistently across vendors - "10001+", "10,001 +",
    "10001 - 49999" - so punctuation and case are stripped before comparison.
    """
    return re.sub(r"[^a-z0-9+]", "", _lower(value))


def _employee_band_points(value) -> tuple:
    """Score an employee band by ladder position, never by its digits.

    The input contract says these bands are "passed through verbatim; NEVER
    parsed numerically". No number is read out of the string: the normalised
    band is looked up on the PDF's ladder, through an alias table for the
    spellings vendors actually use. Returns (points, matched_band), with
    matched_band None when nothing matched - which scores 0 rather than
    guessing a neighbour.
    """
    normalised = _normalise_band(value)
    if not normalised:
        return 0, None
    # The alias table is written in the ladder's own spelling, so its target is
    # normalised too before comparison - otherwise "10001+" resolves to
    # "10001-49999" and then fails to match the normalised ladder key.
    alias = EMPLOYEE_BAND_ALIASES.get(normalised)
    normalised = _normalise_band(alias) if alias else normalised
    for band, points in EMPLOYEE_BANDS:
        if _normalise_band(band) == normalised:
            return points, band
    return 0, None


def _round_half_up(value, places=0):
    """Round halves away from zero, as the PDF's worked example does.

    Python rounds halves to even, so 63.3 x 25% = 15.825 becomes 15.82 where the
    document prints 15.83. The composite is unaffected either way, but the
    per-driver contributions are shown on screen next to the document, so they
    match it.
    """
    from decimal import ROUND_HALF_UP, Decimal

    quantum = Decimal(1).scaleb(-places)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    return float(rounded) if places else int(rounded)


def _banded(count, bands, floor=0):
    """First band whose threshold `count` reaches. Bands run high to low."""
    for threshold, points in bands:
        if count >= threshold:
            return points
    return floor


def _parse_date(value):
    """A date from an ISO-8601 timestamp or plain date, else None."""
    text = _text(value)
    if not text:
        return None
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)),
                    int(match.group(3)))
    except ValueError:
        return None


def _number(value):
    """A number from a possibly-formatted numeric cell, else None.

    Returns an int for a whole value so scores render as "34/100" rather than
    "34.0/100" in the basis strings a seller reads.
    """
    text = _text(value).replace(",", "")
    if not text:
        return None
    if not re.match(r"^-?\d+(\.\d+)?$", text):
        return None
    number = float(text)
    return int(number) if number.is_integer() else number


def _driver(key, points, terms, evidence_ids, notes=None, caveats=None) -> dict:
    """One computed driver, capped at 100, with its terms and evidence shown."""
    value = max(0, min(_round_half_up(points, 2), DRIVER_MAX))
    out = {
        "key": key,
        "label": DRIVER_LABELS[key],
        "value": value,
        "max_value": DRIVER_MAX,
        "weight": WEIGHTS[key],
        "available": True,
        "authored_by": "client",
        "terms": terms,
        "evidence_ids": sorted(set(evidence_ids or [])),
    }
    if notes:
        out["notes"] = notes
    if caveats:
        out["caveats"] = caveats
    return out


def _term(label, points, max_points, basis, missing=False) -> dict:
    """One scoring component.

    `missing` marks a component that scored 0 because its input was absent
    rather than because the account scored badly. Under the PDF's missing-input
    rule both are 0, and this flag is the only thing that keeps them
    distinguishable on screen.
    """
    out = {"label": label, "points": _round_half_up(points, 2),
           "max_points": max_points, "basis": basis}
    if missing:
        out["missing_input"] = True
    return out


def _recent(events, scored_on, window_days=WINDOW_DAYS) -> list:
    """Dated event dicts inside the window. An undated event is excluded.

    The PDF scopes both news components to "within the last 12 months", so an
    event with no usable date cannot be shown to qualify and is left out rather
    than assumed recent.
    """
    out = []
    for event in (events or []):
        if not isinstance(event, dict):
            continue
        when = _parse_date(event.get("event_date") or event.get("date")
                           or event.get("published_at"))
        if when and (scored_on - when).days <= window_days:
            out.append(event)
    return out


def _headline(event) -> str:
    return _text(event.get("event_headline") or event.get("headline")
                 or event.get("title"))


# ---------------------------------------------------------------------------
# Driver 1: Workplace Technology and OS Opportunity (20%)
# ---------------------------------------------------------------------------

def workplace_os(technologies: list, employee_band: str) -> dict:
    """Account scale (30) + OS environment (40) + workplace footprint (30).

    Sources: Source A 1_Firmographics for the employee band, Source A
    4_Technographics Full Tech Stack for both technology components.
    """
    names = [_text(t) for t in (technologies or []) if _text(t)]
    blob = " | ".join(_lower(n) for n in names)
    evidence = []

    # A. Account scale - 30 points.
    scale_points, band = _employee_band_points(employee_band)
    scale_basis = ("employee range %r on the PDF's size ladder" % band if band
                   else "no recognised employee range on file")
    if band:
        evidence.append("firmographics:employee_range")

    # B. OS environment - 40 points, highest applicable rule.
    families = {f for f, terms in OS_FAMILIES.items() if _any_term(blob, terms)}
    os_points, os_rule = 0, None
    for combination, points in OS_COMBINATION_POINTS:
        if set(combination) <= families and points > os_points:
            os_points, os_rule = points, " + ".join(combination)
    os_basis = ("%s detected - highest applicable rule (%s)"
                % (", ".join(sorted(families)), os_rule) if os_rule
                else "no OS detected")
    evidence.extend("tech:os:%s" % f for f in sorted(families))

    # C. Workplace technology footprint - 30 points on the distinct count.
    qualifying = {}
    for name in names:
        lowered = _lower(name)
        for term, category in WORKPLACE_TECHNOLOGIES.items():
            if term in lowered:
                qualifying.setdefault(category, set()).add(term)
    distinct = sorted({t for terms in qualifying.values() for t in terms})
    footprint_points = _banded(len(distinct), WORKPLACE_FOOTPRINT_BANDS)
    evidence.extend("tech:%s" % t for t in distinct)

    total = scale_points + os_points + footprint_points
    return _driver(
        "workplace_os", total,
        [
            _term("Account scale", scale_points, ACCOUNT_SCALE_MAX,
                  scale_basis, missing=not band),
            _term("OS environment", os_points, OS_ENVIRONMENT_MAX, os_basis,
                  missing=not families),
            _term("Workplace technology footprint", footprint_points,
                  WORKPLACE_FOOTPRINT_MAX,
                  "%d distinct qualifying HP-relevant workplace technolog%s (%s)"
                  % (len(distinct), "y" if len(distinct) == 1 else "ies",
                     ", ".join(distinct) or "none"),
                  missing=not names),
        ],
        evidence,
        caveats=[
            "A technology qualifies for the footprint component only where the "
            "PDF names it or its category. Technologies outside that list do "
            "not count, so this component under-counts rather than over-counts.",
            "Account scale is the employee range's position on a fixed ladder; "
            "no number is parsed from the band string.",
        ])


# ---------------------------------------------------------------------------
# Driver 2: AI and Workstation Opportunity (25%)
# ---------------------------------------------------------------------------

def ai_workstation(intent_topics: list, technologies: list,
                   workstation_intent_score, news_events: list,
                   scored_on: date) -> dict:
    """Breadth (35) + Depth (35) + Workstation intent (15) + AI events (15).

    `intent_topics` are (topic, score) pairs from Source A 11_intent_score.
    Breadth counts core AI/ML families; Depth counts every distinct detailed
    AI/ML intent signal plus every distinct qualifying AI/ML technology.
    """
    topics = [_text(t) for t, _ in (intent_topics or []) if _text(t)]
    tech_names = [_text(t) for t in (technologies or []) if _text(t)]
    evidence = []

    # A. Breadth - 35 points on the count of core families present.
    families = []
    for family, terms in AI_CORE_FAMILIES.items():
        for topic in topics:
            lowered = _lower(topic)
            hit = any(_token_match(lowered, term) if term in AI_FAMILY_ACRONYMS
                      else term in lowered for term in terms)
            if hit:
                families.append(family)
                break
    breadth_points = AI_BREADTH_POINTS.get(len(families), 0)
    evidence.extend("intent_family:%s" % f for f in families)

    # A. Depth - 35 points on distinct detailed evidence items.
    depth_topics = sorted({_lower(t) for t in topics
                           if any(_token_match(_lower(t), term)
                                  if term in AI_FAMILY_ACRONYMS
                                  else term in _lower(t)
                                  for term in AI_DEPTH_TERMS)})
    depth_tech = sorted({term for term in AI_ML_TECHNOLOGIES
                         for name in tech_names if term in _lower(name)})
    depth_count = len(depth_topics) + len(depth_tech)
    depth_points = _banded(depth_count, AI_DEPTH_BANDS)
    evidence.extend("intent_topic:%s" % t for t in depth_topics)
    evidence.extend("tech:%s" % t for t in depth_tech)

    # B. Workstation intent - 15 points, linear.
    ws_score = _number(workstation_intent_score)
    ws_points = (ws_score / 100.0) * WORKSTATION_INTENT_MAX if ws_score else 0
    ws_basis = ("Workstations intent score %s/100 -> %s/100 x %d"
                % (ws_score, ws_score, WORKSTATION_INTENT_MAX) if ws_score
                else "no Workstations intent score on file")

    # C. Recent AI initiatives - 5 points each, capped at 15.
    ai_events = sorted({_headline(e) for e in _recent(news_events, scored_on)
                        if _any_term(_lower(_headline(e)), AI_EVENT_TERMS)}
                       - {""})
    event_points = min(len(ai_events) * POINTS_PER_AI_EVENT, AI_EVENT_MAX)
    evidence.extend("news:%s" % h[:60] for h in ai_events)

    total = breadth_points + depth_points + ws_points + event_points
    return _driver(
        "ai_workstation", total,
        [
            _term("AI/ML breadth", breadth_points, AI_BREADTH_MAX,
                  "%d of 4 core AI/ML families detected (%s)"
                  % (len(families), ", ".join(families) or "none"),
                  missing=not topics),
            _term("AI/ML depth", depth_points, AI_DEPTH_MAX,
                  "%d detailed AI/ML evidence items (%d intent signal%s + "
                  "%d qualifying technolog%s)"
                  % (depth_count, len(depth_topics),
                     "" if len(depth_topics) == 1 else "s", len(depth_tech),
                     "y" if len(depth_tech) == 1 else "ies"),
                  missing=not topics and not tech_names),
            _term("Workstation intent", ws_points, WORKSTATION_INTENT_MAX,
                  ws_basis, missing=ws_score is None),
            _term("Recent AI initiatives", event_points, AI_EVENT_MAX,
                  "%d unique verified AI event%s within %d days"
                  % (len(ai_events), "" if len(ai_events) == 1 else "s",
                     WINDOW_DAYS),
                  missing=not news_events),
        ],
        evidence,
        caveats=[
            "An AI event qualifies only when the headline explicitly concerns "
            "AI, ML, generative AI, LLMs, an AI centre of excellence, AI "
            "infrastructure, or an AI partnership or investment. General "
            "technology announcements do not qualify. An event with no usable "
            "date cannot be shown to fall inside the 12-month window and is "
            "excluded rather than assumed recent.",
        ])


# ---------------------------------------------------------------------------
# Driver 3: Growth and Expansion Signals (30%)
# ---------------------------------------------------------------------------

def growth_expansion(social_stats: list, postings: list, news_events: list,
                     scored_on: date, blank_status_is_open: bool = True) -> dict:
    """Workforce growth (25) + hiring volume (50) + growth events (25).

    This driver absorbed the former standalone Hiring driver: the PDF removes it
    and folds its volume signal in here as term B, with the 30% weight standing
    in for the previous 15% Hiring + 15% Growth.

    `social_stats` are dated `associated_members` observations from Source B
    `extended_company` - a LinkedIn workforce proxy, not verified headcount.
    """
    evidence, notes = [], []

    # A. Workforce growth proxy - 25 points.
    observations = []
    for row in (social_stats or []):
        if not isinstance(row, dict):
            continue
        when = _parse_date(row.get("date") or row.get("as_of")
                           or row.get("observed_at"))
        members = _number(row.get("associated_members")
                          or row.get("associatedMembers"))
        if when and members:
            observations.append((when, members))
    observations.sort()

    if len(observations) >= 2:
        (first_date, first_members) = observations[0]
        (last_date, last_members) = observations[-1]
        growth_pct = ((last_members - first_members) / first_members) * 100
        growth_points = _banded(growth_pct, GROWTH_BANDS) if growth_pct > 0 else 0
        growth_basis = ("%s associated members on %s and %s on %s -> %.1f%%"
                        % (int(first_members), first_date.isoformat(),
                           int(last_members), last_date.isoformat(), growth_pct))
        growth_missing = False
        evidence.append("extended_company:social_stats")
    else:
        # Nothing is derived from a single point or from an undated one: a
        # growth rate needs two comparable dated observations, and inventing
        # the second would be inventing the account's trajectory. The reason
        # separates "no rows delivered" from "rows delivered but unusable",
        # because those are different problems for whoever chases the data.
        if not social_stats:
            detail = ("no extended_company/social_stats rows are on file for "
                      "this account")
        elif not observations:
            detail = ("%d social_stats row%s on file, none carrying both a "
                      "date and an associated_members value"
                      % (len(social_stats),
                         "" if len(social_stats) == 1 else "s"))
        else:
            detail = ("only 1 dated associated_members observation is on "
                      "file; two are needed to measure growth between them")
        growth_points, growth_basis = 0, (
            "comparable associated-members history unavailable - %s" % detail)
        growth_missing = True

    # B. Recent hiring volume - 50 points.
    rows = [r for r in (postings or []) if isinstance(r, dict)]

    def eligible(row):
        # "consider job records whose posted_at date falls within the latest 12
        # months. If posted_at is blank, use first_seen_at as the available
        # job-date proxy."
        when = _parse_date(row.get("posted_at")) or _parse_date(
            row.get("first_seen_at"))
        if when is None:
            return False
        if (scored_on - when).days > WINDOW_DAYS:
            return False
        # "both blank-status and closed-status job records are included"
        status = _lower(row.get("status"))
        return bool(status) or blank_status_is_open

    eligible_rows = [r for r in rows if eligible(r)]
    hiring_points = _banded(len(eligible_rows), HIRING_VOLUME_BANDS)

    undated = sum(1 for r in rows
                  if not _parse_date(r.get("posted_at"))
                  and not _parse_date(r.get("first_seen_at")))
    if undated:
        notes.append("%d job record%s carry neither posted_at nor "
                     "first_seen_at and are excluded from the volume count"
                     % (undated, "" if undated == 1 else "s"))
    blanks = sum(1 for r in rows if not _lower(r.get("status")))
    if blanks:
        notes.append(
            "%d job record%s have a blank status; the PDF's agreed rule for "
            "this dataset counts blank-status and closed-status records alike"
            % (blanks, "" if blanks == 1 else "s"))

    # C. Verified growth and expansion events - 10 points each, capped at 25.
    growth_events = []
    for event in _recent(news_events, scored_on):
        headline = _headline(event)
        blob = _lower("%s %s" % (headline, event.get("event_type") or ""))
        if not headline or not _any_term(blob, GROWTH_EVENT_TERMS):
            continue
        if _any_term(blob, GROWTH_EVENT_EXCLUSIONS):
            continue
        growth_events.append(headline)
    unique_events = sorted(set(growth_events))
    event_points = min(len(unique_events) * POINTS_PER_GROWTH_EVENT,
                       GROWTH_EVENT_MAX)
    evidence.extend("news:%s" % h[:60] for h in unique_events)

    total = growth_points + hiring_points + event_points
    return _driver(
        "growth_expansion", total,
        [
            _term("Workforce growth proxy", growth_points, GROWTH_MAX,
                  growth_basis, missing=growth_missing),
            _term("Recent hiring volume", hiring_points, HIRING_VOLUME_MAX,
                  "%d eligible job record%s in the last %d days"
                  % (len(eligible_rows), "" if len(eligible_rows) == 1 else "s",
                     WINDOW_DAYS),
                  missing=not rows),
            _term("Verified growth and expansion events", event_points,
                  GROWTH_EVENT_MAX,
                  "%d unique verified growth/expansion event%s within %d days"
                  % (len(unique_events), "" if len(unique_events) == 1 else "s",
                     WINDOW_DAYS),
                  missing=not news_events),
        ],
        evidence,
        notes=notes or None,
        caveats=[
            "associated_members is a LinkedIn workforce proxy, not verified "
            "employee headcount. Growth is measured between the earliest and "
            "latest comparable dated observations on file.",
            "This driver absorbed the former standalone Hiring driver; its "
            "30% weight stands in for the previous 15% Hiring + 15% Growth.",
        ])


# ---------------------------------------------------------------------------
# Driver 4: HP Solution Intent (25%)
# ---------------------------------------------------------------------------

def hp_solution_intent(categories: list) -> dict:
    """Category strength (60) + trend (10) + buying stage (15) + volume (15).

    `categories` are dicts from the hp_intent_results / hp_category_intent file:
    {name, score, trend_label, stage, research_volume, keywords}. All four
    components read the fields belonging to the **highest-scoring** category, as
    the PDF directs. The keyword-eligibility gate that used to sit in front of
    that choice is disabled (`NOISY_CATEGORY_TERMS` is empty by client
    instruction), so the highest-scoring category is always the primary.
    """
    entries = [c for c in (categories or [])
               if isinstance(c, dict) and _text(c.get("name"))]
    if not entries:
        return _driver(
            "hp_solution_intent", 0,
            [
                _term("HP-category intent strength", 0, HP_CATEGORY_INTENT_MAX,
                      "no HP category intent scores on file", missing=True),
                _term("Intent trend", 0, INTENT_TREND_MAX,
                      "no category on file", missing=True),
                _term("Buying stage", 0, BUYING_STAGE_MAX,
                      "no category on file", missing=True),
                _term("Research volume", 0, RESEARCH_VOLUME_MAX,
                      "no category on file", missing=True),
            ],
            [],
            notes=["Scores 0 under the PDF's missing-input rule, not because "
                   "the account researched nothing."])

    clean, flagged = [], []
    for entry in entries:
        keywords = entry.get("keywords")
        blob = _lower(" ".join(keywords) if isinstance(keywords, (list, tuple))
                      else keywords)
        (flagged if _any_term(blob, NOISY_KEYWORDS) else clean).append(entry)

    notes = []
    if flagged:
        notes.append("category/ies barred from primary on flagged keywords: %s"
                     % ", ".join(sorted({_text(e.get("name")) for e in flagged})))

    pool = clean or entries
    if not clean:
        notes.append("every category's score rests on a flagged keyword, so "
                     "the highest-scoring category is used as supplied.")

    primary = max(pool, key=lambda e: _number(e.get("score")) or 0)
    name = _text(primary.get("name"))
    score_value = _number(primary.get("score")) or 0

    # A. HP-category intent strength - 60 points, linear.
    strength_points = (score_value / 100.0) * HP_CATEGORY_INTENT_MAX

    # B. Intent trend - 10 points.
    #
    # The category file's Intent Trend is taken as supplied. The client has
    # ruled the file the source of truth, so the basis states the direction
    # and its source without qualifying it.
    trend_label = _lower(primary.get("trend_label") or primary.get("trend"))
    trend_points = INTENT_TREND_POINTS.get(trend_label, 0)
    trend_basis = (
        "%s intent trend is %s per the category file"
        % (name, _text(primary.get("trend_label")))
        if trend_label else
        "%s has no intent trend on file" % name)

    # C. Buying stage - 15 points.
    stage = _lower(primary.get("stage"))
    stage_points = BUYING_STAGE_POINTS.get(stage, 0)
    if not stage_points and stage:
        # "Decision" and "Purchase" arrive as separate words in some exports.
        for term, points in BUYING_STAGE_POINTS.items():
            if term in stage:
                stage_points = max(stage_points, points)
    stage_basis = "%s buying stage is %s" % (
        name, _text(primary.get("stage")) or "unavailable")

    # D. Research volume - 15 points.
    volume = _lower(primary.get("research_volume"))
    volume_points = RESEARCH_VOLUME_POINTS.get(volume, 0)
    volume_basis = "%s research volume is %s" % (
        name, _text(primary.get("research_volume")) or "unavailable")

    total = strength_points + trend_points + stage_points + volume_points
    return _driver(
        "hp_solution_intent", total,
        [
            _term("HP-category intent strength", strength_points,
                  HP_CATEGORY_INTENT_MAX,
                  "highest category %s scores %s/100" % (name, score_value),
                  missing=not score_value),
            _term("Intent trend", trend_points,
                  INTENT_TREND_MAX, trend_basis, missing=not trend_label),
            _term("Buying stage", stage_points, BUYING_STAGE_MAX, stage_basis,
                  missing=not stage),
            _term("Research volume", volume_points, RESEARCH_VOLUME_MAX,
                  volume_basis, missing=not volume),
        ],
        ["hp_category_intent:%s" % _lower(name)],
        notes=notes or None)


# ---------------------------------------------------------------------------
# The composite
# ---------------------------------------------------------------------------

FORMULA = ("Urgency = (Workplace Technology and OS x 20%) + (AI and "
           "Workstation x 25%) + (Growth and Expansion x 30%) + (HP Solution "
           "Intent x 25%). Each driver is scored out of 100. Missing inputs "
           "contribute 0 to their own component only; the remaining components "
           "are still calculated.")


def score(drivers: list, scored_on: date | None = None) -> dict:
    """Combine the four drivers into the urgency score.

    Under the PDF's missing-input rule the composite always computes: a driver
    with no data contributes 0 rather than blocking the score. `missing_inputs`
    lists the components that scored 0 for want of data, so a low score can be
    read as "little evidence" rather than "poor account".
    """
    scored_on = scored_on or datetime.now(UTC).date()
    by_key = {d["key"]: d for d in (drivers or []) if isinstance(d, dict)}

    ordered, missing_inputs = [], []
    for key in DRIVER_KEYS:
        driver = by_key.get(key)
        if driver is None:
            driver = _driver(
                key, 0,
                [_term("All components", 0, DRIVER_MAX,
                       "driver was not computed for this account",
                       missing=True)],
                [],
                notes=["Scores 0 under the PDF's missing-input rule."])
        ordered.append(driver)
        for term in driver.get("terms") or []:
            if term.get("missing_input"):
                missing_inputs.append("%s / %s" % (driver["label"],
                                                   term["label"]))

    # One evidence ID is linked to every driver it supports rather than
    # deduplicated, so reuse is visible instead of silently collapsed.
    seen, shared = {}, {}
    for driver in ordered:
        for evidence_id in driver.get("evidence_ids") or []:
            seen.setdefault(evidence_id, []).append(driver["key"])
    for evidence_id, keys in seen.items():
        if len(keys) > 1:
            shared[evidence_id] = sorted(keys)

    # One calculation feeds every surface. Each driver's contribution is
    # driver value x weight, rounded once to 2dp; the exact total is the SUM OF
    # THOSE SAME published figures, and the headline score is that total
    # rounded to a whole number.
    #
    # Summing the unrounded products instead would be defensible arithmetic and
    # is what this module did previously, but it lets the four contributions on
    # screen add up to something the headline score contradicts - 2.89 + 2.95 +
    # 9.26 + 20.40 = 35.50 displayed under a score of 35. Anyone checking the
    # column by hand finds a discrepancy they cannot explain, which is exactly
    # the 49.3-vs-50.4 problem the source document has. The screen's own
    # numbers are therefore the authority.
    weighted = {d["key"]: _round_half_up(d["value"] * WEIGHTS[d["key"]], 2)
                for d in ordered}
    exact_total = _round_half_up(sum(weighted.values()), 2)
    total = _round_half_up(exact_total)

    return {
        "score": total,
        "max_score": DRIVER_MAX,
        "scored_on": scored_on.isoformat(),
        "available": True,
        "drivers": ordered,
        "weighted_contributions": weighted,
        # The unrounded sum of the contributions above, published so a reader
        # can see where the headline `score` came from without re-deriving it.
        # score == round(exact_score) == round(sum(weighted_contributions)).
        "exact_score": exact_total,
        "missing_inputs": missing_inputs,
        "shared_evidence": shared,
        "formula": FORMULA,
        "formula_authority": FORMULA_AUTHORITY,
        "missing_input_rule": MISSING_INPUT_RULE,
        "scope_note": SCOPE_NOTE,
        "client_agreed": True,
        # The scoring config that produced this score. A startup sweep compares
        # it against the current config and regenerates the widgets whose stamp
        # no longer matches, so retuning a weight reaches the dashboard instead
        # of leaving a score computed by rules that no longer exist.
        "scoring_config_version": _scoring.version("urgency"),
    }


# ---------------------------------------------------------------------------
# Assembly: read the datasets, compute the four drivers, publish the widget
# ---------------------------------------------------------------------------

WIDGET_KEY = "exec_urgency_score"


def _tech_names(account_id) -> list:
    """Technology names from the account's stack, technographics + webstack.

    Reuses the Intent feature's own inventory builder so both features see the
    same stack. A technology listed on one screen and absent on the other would
    be a bug a reader could see.
    """
    from app.services.extractors.intent_demand_signals import _read_dataset_records, _tech_inventory

    inventory = _tech_inventory(
        _read_dataset_records(account_id, "technographics"),
        _read_dataset_records(account_id, "webstack"))
    names = []
    for item in inventory or []:
        name = item.get("name") if isinstance(item, dict) else item
        if _text(name):
            names.append(_text(name))
    return names


def _hp_categories(account_id, domain) -> list:
    """Per-HP-category entries from the wide intent export.

    Delegates the parsing to Intent & Demand Signals rather than re-reading the
    two-header-row CSV here; this only reshapes its output into the dicts
    `hp_solution_intent()` takes. `trend_label` is the file's own Intent Trend
    words - the parser deliberately leaves `trend` None because it cannot be
    verified, and section 4B of the PDF scores the label regardless.
    """
    from app.services.extractors.datasets import read_dataset_rows
    from app.services.extractors.intent_demand_signals import _parse_category_file

    parsed = _parse_category_file(
        read_dataset_rows(account_id, "hp_category_intent"), domain)
    out = []
    for name, entry in (parsed.get("categories") or {}).items():
        keywords = list(entry.get("keywords_matched") or [])
        keywords.extend(entry.get("topics_researched") or [])
        out.append({
            "name": name,
            "score": entry.get("score"),
            "trend_label": entry.get("trend_label"),
            "stage": entry.get("stage"),
            "research_volume": entry.get("research_volume"),
            "keywords": keywords,
        })
    return out


def _workstation_intent_score(categories: list):
    """The Workstations category's own intent score, for driver 2 term B."""
    for entry in categories or []:
        if "workstation" in _lower(entry.get("name")):
            return entry.get("score")
    return None


def _social_stats(account_id) -> list:
    """Dated associated_members observations from Source B extended_company.

    `social_stats` arrives as a JSON blob in one column rather than as rows, so
    it is parsed here. A row that is not parseable JSON, or that carries no
    dated members value, contributes nothing - which scores the workforce growth
    component 0 under the missing-input rule.
    """
    from app.services.extractors.intent_demand_signals import _read_dataset_records

    out = []
    for row in _read_dataset_records(account_id, "extended_company"):
        raw = row.get("social_stats") or row.get("socialStats")
        if isinstance(raw, str) and raw.strip():
            try:
                raw = json.loads(raw)
            except ValueError:
                continue
        if isinstance(raw, dict):
            # {"2025-07-31": {"associated_members": 14217}, ...}
            for when, value in raw.items():
                if isinstance(value, dict):
                    out.append({"date": when, **value})
                else:
                    out.append({"date": when, "associated_members": value})
        elif isinstance(raw, list):
            out.extend(item for item in raw if isinstance(item, dict))
    return out


def build_urgency_score(account_id: str, scored_on: date | None = None) -> dict:
    """Compute and persist `exec_urgency_score` for one account.

    Each driver is fed only from datasets that are actually registered for the
    account. Under the PDF's missing-input rule an absent dataset scores its own
    component 0 and the composite still publishes, with the affected components
    named in `missing_inputs`.
    """
    from app.database.mongodb import get_db
    from app.services.extractors.datasets import account_domain
    from app.services.extractors.intent_demand_signals import _read_dataset_records

    scored_on = scored_on or datetime.now(UTC).date()
    domain = account_domain(account_id)

    firmographics = _read_dataset_records(account_id, "firmographics")
    firm = firmographics[0] if firmographics else {}
    employee_band = (firm.get("Number Of Employees Range")
                     or firm.get("employee_count"))

    jobs = _read_dataset_records(account_id, "job_openings")
    news = (_read_dataset_records(account_id, "google_news")
            + _read_dataset_records(account_id, "news_events"))
    technologies = _tech_names(account_id)
    categories = _hp_categories(account_id, domain)

    topics = []
    for row in _read_dataset_records(account_id, "intent_score"):
        topic = (row.get("Topic") or row.get("topic")
                 or row.get("Topic Name") or row.get("topic_name"))
        raw = (row.get("Composite Score") or row.get("composite_score")
               or row.get("Score") or row.get("score"))
        value = _number(raw) or 0
        if _text(topic):
            topics.append((_text(topic), value))

    drivers = [
        workplace_os(technologies, employee_band),
        ai_workstation(topics, technologies,
                       _workstation_intent_score(categories), news, scored_on),
        growth_expansion(_social_stats(account_id), jobs, news, scored_on),
        hp_solution_intent(categories),
    ]
    payload = score(drivers, scored_on)

    now = datetime.now(UTC)
    db = get_db()
    existing = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": WIDGET_KEY}) or {}
    record = {
        "account_id": account_id,
        "feature_key": "executive_dashboard",
        "widget_key": WIDGET_KEY,
        "data_classification": "derived",
        "status": "available" if not payload["missing_inputs"] else "partial",
        "data": payload,
        "source_datasets": ["firmographics", "technographics", "webstack",
                            "job_openings", "intent_score",
                            "hp_category_intent", "extended_company",
                            "google_news", "news_events"],
        "updated_at": now,
    }
    if not existing:
        record["extracted_at"] = now
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": WIDGET_KEY},
        {"$set": record}, upsert=True)

    logger.info("urgency score for %s: %s (%d component(s) missing input)",
                account_id, payload["score"], len(payload["missing_inputs"]))
    return payload
