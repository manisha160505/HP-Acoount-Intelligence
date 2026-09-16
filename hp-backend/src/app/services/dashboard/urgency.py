"""Urgency Score: five weighted drivers, one 0-100 number.

    Urgency = 20% Fleet Refresh & Dual-OS
            + 25% AI / Workstation Catalysts
            + 15% Hiring
            + 15% Expansion / Headcount Growth
            + 25% Intent

The weights are ABX's, quoted verbatim in Feature 1 Step 5 and again in its
rules section. Everything else in this module - every band, every point value,
every cap - is **delivery-side and was invented here**, on instruction, because
ABX supplies the weights and then explicitly declines to supply the rest:

    "The dashboard accepts five urgency driver values on a 0-100 scale. The
    current POC does not define a reusable raw-data-to-driver formula for all
    accounts. Do not invent one inside the dashboard."

That sentence is the reason `registry.py` held this widget out of scope and the
frontend printed TBD. It is now being knowingly overridden rather than quietly
satisfied, so every driver payload carries `authored_by: "delivery"` and the
module publishes `FORMULA_AUTHORITY` saying so. These formulas have not been
agreed by the client and belong in the next version of
`HP-Account-Intelligence-Rules.docx` before any of these numbers are presented
as HP's.

Two decisions were taken against what the Astra data actually contains, both on
explicit instruction, and both are recorded in the payload rather than hidden:

**Bands are scored as ordinal buckets.** `firmographics` carries one row, and
its size fields are bands - `Number Of Employees Range: "10001+"`,
`Yearly Revenue Range: "10B-100B"`. The input contract says these are "passed
through verbatim; NEVER parsed numerically". No number is parsed out of them
here: the band *string* is matched against a known ladder and the ladder
position scores. What that measures is company size, not urgency - a large
account scores high on Fleet Scale whether or not anything is due for refresh -
so both affected drivers publish `proxy: True` and a sentence saying what the
number really represents.

**Year-on-year growth is not computed.** It has no second period to compute
from: one firmographics row, one point in time. Rather than infer a trend from
a single observation, the Expansion driver scores size band plus dated events,
and names the absent growth terms in its payload.

The missing-input rule is kept exactly as ABX states it - *"if any of the five
urgency inputs is unavailable, keep that input unavailable and do not calculate
the overall urgency score. Do not change a missing value to 0%"*. A driver that
cannot be computed returns None, and `score()` then publishes `score: None` with
the blocking drivers named. A driver returning 0 and a driver returning None are
different things and stay different.

Evidence reuse follows ABX too: *"If one evidence item genuinely supports two
different drivers, link the same evidence ID to both drivers so the reuse is
visible."* Nothing is deduplicated across drivers; `shared_evidence` in the
payload reports which IDs landed in more than one.
"""

import json
import logging
import re
from datetime import UTC, date, datetime

from app.services.hp import intent_topic_map

logger = logging.getLogger(__name__)

# ABX Feature 1 Step 5. These five are the specification's; nothing below is.
WEIGHTS = {
    "fleet_refresh": 0.20,
    "ai_workstation": 0.25,
    "hiring": 0.15,
    "expansion": 0.15,
    "intent": 0.25,
}

DRIVER_LABELS = {
    "fleet_refresh": "Fleet Refresh & Dual-OS",
    "ai_workstation": "AI / Workstation Catalysts",
    "hiring": "Hiring",
    "expansion": "Expansion / Headcount Growth",
    "intent": "Intent",
}

# Driver order on screen, matching ABX's own listing order.
DRIVER_KEYS = ("fleet_refresh", "ai_workstation", "hiring", "expansion", "intent")

FORMULA_AUTHORITY = (
    "Weights (20/25/15/15/25) are ABX Feature 1 Step 5. The per-driver "
    "formulas are delivery-authored and not yet client-agreed: ABX states that "
    "no reusable raw-data-to-driver formula is defined and directs that one "
    "not be invented in the dashboard. These were authored on explicit "
    "instruction and require sign-off before publication.")

DRIVER_MAX = 100

# --- Fleet Refresh & Dual-OS ------------------------------------------------

OS_PRESENCE_POINTS = 30          # Windows detected in the technology stack
OS_MIX_MULTI = 25                # two or more client-OS families present
OS_MIX_SINGLE = 10               # exactly one
MAX_DEVICE_SIGNAL = 20
POINTS_PER_DEVICE_VENDOR = 10

# Client-OS families, matched against technology names. Mirrors the families
# `tech_landscape.py` already detects for the `client_os` category, so the two
# features do not disagree about what an operating system is.
OS_FAMILIES = {
    "windows": ("windows", "microsoft windows"),
    "apple": ("macos", "mac os", "osx", "os x"),
    "linux": ("linux", "centos", "ubuntu", "red hat", "redhat", "unix"),
}

# Hardware vendors whose presence indicates a managed device fleet.
DEVICE_VENDORS = ("dell", "lenovo", "hp inc", "hewlett", "acer", "asus",
                  "toshiba", "fujitsu", "intel", "amd", "nvidia")

# Employee bands, smallest to largest, matched as substrings of the band string.
# The LADDER POSITION scores, not any number read out of the text - the input
# contract forbids parsing these numerically.
EMPLOYEE_BANDS = (
    ("1-10", 5), ("11-50", 5), ("51-200", 10), ("201-500", 10),
    ("501-1000", 15), ("1001-5000", 15), ("5001-10000", 20), ("10001+", 25),
)
FLEET_SCALE_UNKNOWN = 0

# --- AI / Workstation Catalysts --------------------------------------------

POINTS_PER_AI_TOPIC = 12
MAX_AI_TOPIC_POINTS = 48
TOPIC_STRENGTH_MAX = 22
POINTS_PER_AI_ROLE = 6
MAX_AI_ROLE_POINTS = 18
POINTS_PER_AI_NEWS = 6
MAX_AI_NEWS_POINTS = 12

# The Workstation supporting-signal family, as fixed for Intent & Demand
# Signals. Kept identical so one account cannot have a topic count "AI" here and
# not there.
AI_TOPICS = ("ai", "artificial intelligence", "machine learning", "ai/ml",
             "ml", "ai chips", "data analytics", "data science",
             "vector database", "gpt", "llm", "generative ai", "deep learning")

AI_ROLE_TERMS = ("machine learning", "ml engineer", "ai engineer",
                 "data scientist", "data science", "deep learning",
                 "computer vision", "nlp", "mlops", "ai research")

# --- Hiring -----------------------------------------------------------------

# Volume bands on open postings. See `hiring()` for what "open" means here.
HIRING_VOLUME_BANDS = ((200, 40), (100, 32), (50, 24), (20, 16), (5, 8))
HIRING_VOLUME_FLOOR = 0
VELOCITY_MAX = 30
VELOCITY_WINDOW_DAYS = 90
POINTS_PER_SENIOR_TITLE = 5
MAX_SENIORITY_POINTS = 15
POINTS_PER_DEPARTMENT = 3
MAX_BREADTH_POINTS = 15

SENIOR_TERMS = ("senior", "lead", "head", "principal", "staff", "manager",
                "director", "vp", "vice president", "chief", "architect")

# --- Expansion / Headcount Growth ------------------------------------------

# Growth terms are absent by necessity - see the module docstring. The points
# they would have carried are redistributed across size band and events rather
# than left unreachable, so the driver can still reach 100.
EXPANSION_SIZE_MAX = 40
POINTS_PER_EXPANSION_EVENT = 12
MAX_EXPANSION_EVENT_POINTS = 36
POINTS_PER_FUNDING_EVENT = 12
MAX_FUNDING_POINTS = 24

# Revenue bands, smallest to largest. Ordinal, like the employee ladder.
REVENUE_BANDS = (
    ("0-1m", 5), ("1m-10m", 10), ("10m-50m", 15), ("50m-100m", 20),
    ("100m-500m", 25), ("500m-1b", 30), ("1b-10b", 35), ("10b-100b", 40),
    ("100b+", 40),
)

EXPANSION_EVENT_TERMS = ("expansion", "expand", "new office", "opens",
                         "opening", "facility", "plant", "factory",
                         "headquarters", "market entry", "enters",
                         "launch", "new site", "relocat")
FUNDING_EVENT_TERMS = ("funding", "raise", "raised", "investment", "invests",
                       "acquisition", "acquire", "acquires", "merger",
                       "stake", "ipo")

# --- Intent -----------------------------------------------------------------

PRIMARY_CATEGORY_WEIGHT = 0.55
POINTS_PER_SUPPORTING_SIGNAL = 5
MAX_SUPPORTING_POINTS = 25
POINTS_PER_TECH_CONFIRMATION = 4
MAX_TECH_CONFIRMATION_POINTS = 20
SUPPORTING_SIGNAL_THRESHOLD = 1     # a Bombora topic scoring above this counts

# Terms that make a category's score untrustworthy as a *primary* signal: "SLA"
# in a job posting is a service-level agreement, not stereolithography, and
# "identified as competitor of" is a relationship, not an interest. A flagged
# category keeps its score on screen but cannot be the account's primary.
#
# Read from Intent & Demand Signals' own dictionary rather than copied, so one
# account cannot have a category barred on this dashboard and primary on the
# Intent feature. Adding a term there changes both.
NOISY_KEYWORDS = tuple(intent_topic_map.NOISY_CATEGORY_TERMS)


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _lower(value) -> str:
    return _text(value).lower()


def _any_term(haystack: str, terms) -> bool:
    return any(term in haystack for term in terms)


def _band_points(value, ladder, default=0) -> tuple:
    """Score a band string by its position on `ladder`, never by its digits.

    Bands arrive spelled inconsistently across vendors - "10001+", "10,001+",
    "10001 +" - so comparison is on digits-and-letters only. Returns
    (points, matched_band) with matched_band None when nothing on the ladder
    matched, which scores `default` rather than guessing a neighbour.
    """
    normalised = re.sub(r"[^a-z0-9+]", "", _lower(value))
    if not normalised:
        return default, None
    for band, points in ladder:
        if re.sub(r"[^a-z0-9+]", "", band) == normalised:
            return points, band
    # A band that is not on the ladder but plainly names the top of it.
    if normalised.endswith("+"):
        return ladder[-1][1], ladder[-1][0]
    return default, None


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


def _driver(key, points, terms, evidence_ids, notes=None, proxy=False,
            proxy_note=None) -> dict:
    """One computed driver, capped at 100, with its terms and evidence shown."""
    value = max(0, min(round(points), DRIVER_MAX))
    out = {
        "key": key,
        "label": DRIVER_LABELS[key],
        "value": value,
        "max_value": DRIVER_MAX,
        "weight": WEIGHTS[key],
        "available": True,
        "authored_by": "delivery",
        "terms": terms,
        "evidence_ids": sorted(set(evidence_ids or [])),
    }
    if notes:
        out["notes"] = notes
    if proxy:
        out["proxy"] = True
        out["proxy_note"] = proxy_note
    return out


def _unavailable(key, reason) -> dict:
    """A driver that cannot be computed. Not zero - absent."""
    return {
        "key": key,
        "label": DRIVER_LABELS[key],
        "value": None,
        "max_value": DRIVER_MAX,
        "weight": WEIGHTS[key],
        "available": False,
        "authored_by": "delivery",
        "unavailable_reason": reason,
        "evidence_ids": [],
    }


def _term(label, points, max_points, basis) -> dict:
    return {"label": label, "points": round(points),
            "max_points": max_points, "basis": basis}


# ---------------------------------------------------------------------------
# Driver 1: Fleet Refresh & Dual-OS (20%)
# ---------------------------------------------------------------------------

def fleet_refresh(technologies: list, employee_band: str) -> dict:
    """Fleet Refresh driver.

    **This driver does not measure whether a refresh is due.** No dataset in
    this platform carries an OS version, a build number, a device age or an
    end-of-support date, so there is no refresh *trigger* available to score.
    What it measures is how much fleet there is to refresh and how mixed it is:
    a large heterogeneous Windows estate scores high whether it was bought last
    year or five years ago.

    That is a different question wearing the driver's name, which is why the
    payload carries `proxy: True` and says so in a sentence a seller will read.
    If OS-version or device-age data ever arrives, `OS_PRESENCE_POINTS` is the
    term to replace with an end-of-support proximity band, and this becomes the
    driver ABX is describing.
    """
    names = [_lower(t) for t in (technologies or []) if _text(t)]
    if not names and not _text(employee_band):
        return _unavailable(
            "fleet_refresh",
            "no technology detections and no employee band on file - neither "
            "the OS mix nor the fleet scale can be established")

    blob = " | ".join(names)
    families = sorted(f for f, terms in OS_FAMILIES.items()
                      if _any_term(blob, terms))
    evidence = []

    presence = OS_PRESENCE_POINTS if "windows" in families else 0
    if presence:
        evidence.append("tech:windows")

    if len(families) >= 2:
        mix_points, mix_basis = OS_MIX_MULTI, "%d client-OS families detected (%s)" % (
            len(families), ", ".join(families))
    elif len(families) == 1:
        mix_points, mix_basis = OS_MIX_SINGLE, "one client-OS family detected (%s)" % families[0]
    else:
        mix_points, mix_basis = 0, "no client-OS family detected"
    evidence.extend("tech:%s" % f for f in families)

    scale_points, band = _band_points(employee_band, EMPLOYEE_BANDS,
                                      FLEET_SCALE_UNKNOWN)
    scale_basis = ("employee band %r on the size ladder" % band if band
                   else "no recognised employee band on file")
    if band:
        evidence.append("firmographics:employee_band")

    vendors = sorted({v for v in DEVICE_VENDORS if v in blob})
    device_points = min(len(vendors) * POINTS_PER_DEVICE_VENDOR,
                        MAX_DEVICE_SIGNAL)
    evidence.extend("tech:%s" % v for v in vendors)

    total = presence + mix_points + scale_points + device_points
    return _driver(
        "fleet_refresh", total,
        [
            _term("OS presence", presence, OS_PRESENCE_POINTS,
                  "Windows detected" if presence else "Windows not detected"),
            _term("OS mix", mix_points, OS_MIX_MULTI, mix_basis),
            _term("Fleet scale", scale_points, EMPLOYEE_BANDS[-1][1], scale_basis),
            _term("Device signal", device_points, MAX_DEVICE_SIGNAL,
                  "%d hardware vendor%s detected (%s)"
                  % (len(vendors), "" if len(vendors) == 1 else "s",
                     ", ".join(vendors) or "none")),
        ],
        evidence,
        proxy=True,
        proxy_note=(
            "Measures fleet size and OS heterogeneity, NOT refresh due-ness. "
            "No OS version, device age or end-of-support date exists in any "
            "delivered dataset, so no refresh trigger can be scored. Fleet "
            "scale is the employee band's position on a fixed ladder; no "
            "number is parsed from the band."))


# ---------------------------------------------------------------------------
# Driver 2: AI / Workstation Catalysts (25%)
# ---------------------------------------------------------------------------

def ai_workstation(intent_topics: list, job_titles: list,
                   news_headlines: list) -> dict:
    """AI/Workstation driver: intent topics, their strength, AI hiring, AI news.

    `intent_topics` are (topic, score) pairs on a 0-100 scale. Topic strength
    reads the strongest AI-family topic rather than an average, because one
    strong signal is what a seller acts on; six weak ones are noise.
    """
    topics = [(t, s) for t, s in (intent_topics or []) if _text(t)]
    if not topics and not job_titles and not news_headlines:
        return _unavailable(
            "ai_workstation",
            "no intent topics, job postings or news events on file")

    matched = [(t, s) for t, s in topics if _any_term(_lower(t), AI_TOPICS)]
    topic_points = min(len(matched) * POINTS_PER_AI_TOPIC, MAX_AI_TOPIC_POINTS)
    evidence = ["intent_topic:%s" % _lower(t) for t, _ in matched]

    scores = [s for _, s in matched if isinstance(s, (int, float))]
    strongest = max(scores) if scores else 0
    strength_points = (strongest / 100.0) * TOPIC_STRENGTH_MAX

    roles = sorted({_text(t) for t in (job_titles or [])
                    if _any_term(_lower(t), AI_ROLE_TERMS)})
    role_points = min(len(roles) * POINTS_PER_AI_ROLE, MAX_AI_ROLE_POINTS)
    evidence.extend("job:%s" % r for r in roles)

    ai_news = sorted({_text(h) for h in (news_headlines or [])
                      if _any_term(_lower(h), AI_TOPICS)})
    news_points = min(len(ai_news) * POINTS_PER_AI_NEWS, MAX_AI_NEWS_POINTS)
    evidence.extend("news:%s" % h[:60] for h in ai_news)

    total = topic_points + strength_points + role_points + news_points
    return _driver(
        "ai_workstation", total,
        [
            _term("Intent topics", topic_points, MAX_AI_TOPIC_POINTS,
                  "%d AI-family topic%s present" % (len(matched),
                                                    "" if len(matched) == 1 else "s")),
            _term("Topic strength", strength_points, TOPIC_STRENGTH_MAX,
                  "strongest AI-family topic scores %s/100" % strongest),
            _term("AI hiring", role_points, MAX_AI_ROLE_POINTS,
                  "%d AI/ML role title%s in job postings"
                  % (len(roles), "" if len(roles) == 1 else "s")),
            _term("AI news", news_points, MAX_AI_NEWS_POINTS,
                  "%d AI-related event%s in the news window"
                  % (len(ai_news), "" if len(ai_news) == 1 else "s")),
        ],
        evidence)


# ---------------------------------------------------------------------------
# Driver 3: Hiring (15%)
# ---------------------------------------------------------------------------

def hiring(postings: list, scored_on: date,
           blank_status_is_open: bool = True) -> dict:
    """Hiring driver: volume, velocity, seniority, breadth.

    `blank_status_is_open` resolves input-contract open question 5.1, which is
    still unanswered by the client: 40% of Astra's postings carry no status at
    all and none says `open`. Set True here on instruction, so a blank counts as
    an open role. **If 5.1 comes back as "blank means unknown", this driver is
    retroactively wrong and this flag is the one line to change** - the payload
    records which reading produced the number.

    Velocity uses `posted_at` only. `first_seen_at` is populated on every row
    and is tempting, but it records when the crawler saw the posting, not when
    the account published it; scoring it would measure our own collection
    schedule and call the result hiring velocity.
    """
    rows = [r for r in (postings or []) if isinstance(r, dict)]
    if not rows:
        return _unavailable("hiring", "no job postings on file")

    def is_open(row):
        status = _lower(row.get("status"))
        return status == "open" or (not status and blank_status_is_open)

    open_rows = [r for r in rows if is_open(r)]
    count = len(open_rows)

    volume = HIRING_VOLUME_FLOOR
    for threshold, points in HIRING_VOLUME_BANDS:
        if count >= threshold:
            volume = points
            break

    dated = [d for d in (_parse_date(r.get("posted_at")) for r in open_rows) if d]
    if dated:
        recent = sum(1 for d in dated
                     if (scored_on - d).days <= VELOCITY_WINDOW_DAYS)
        velocity = (recent / len(dated)) * VELOCITY_MAX
        velocity_basis = ("%d of %d dated posting%s within %d days"
                          % (recent, len(dated), "" if len(dated) == 1 else "s",
                             VELOCITY_WINDOW_DAYS))
    else:
        velocity, recent = 0, 0
        velocity_basis = ("no posting carries a publication date - velocity "
                          "scores zero rather than being read from crawl dates")

    senior = sorted({_text(r.get("normalized_title") or r.get("title"))
                     for r in open_rows
                     if _any_term(_lower(r.get("normalized_title")
                                         or r.get("title")), SENIOR_TERMS)})
    seniority = min(len(senior) * POINTS_PER_SENIOR_TITLE, MAX_SENIORITY_POINTS)

    departments = set()
    for row in open_rows:
        raw = row.get("categories")
        if isinstance(raw, str) and raw.strip().startswith("["):
            try:
                raw = json.loads(raw)
            except ValueError:
                raw = [raw]
        for item in (raw if isinstance(raw, list) else [raw]):
            if _text(item):
                departments.add(_lower(item))
    breadth = min(len(departments) * POINTS_PER_DEPARTMENT, MAX_BREADTH_POINTS)

    notes = []
    undated = len(open_rows) - len(dated)
    if undated:
        notes.append("%d of %d open postings carry no publication date"
                     % (undated, len(open_rows)))
    blanks = sum(1 for r in rows if not _lower(r.get("status")))
    if blanks and blank_status_is_open:
        notes.append(
            "%d posting%s have a blank status and are counted as open "
            "(input-contract open question 5.1, unanswered)"
            % (blanks, "" if blanks == 1 else "s"))

    total = volume + velocity + seniority + breadth
    return _driver(
        "hiring", total,
        [
            _term("Volume", volume, HIRING_VOLUME_BANDS[0][1],
                  "%d open posting%s" % (count, "" if count == 1 else "s")),
            _term("Velocity", velocity, VELOCITY_MAX, velocity_basis),
            _term("Seniority", seniority, MAX_SENIORITY_POINTS,
                  "%d senior/lead title%s" % (len(senior),
                                              "" if len(senior) == 1 else "s")),
            _term("Breadth", breadth, MAX_BREADTH_POINTS,
                  "%d distinct department%s" % (len(departments),
                                                "" if len(departments) == 1 else "s")),
        ],
        ["job:%s" % t for t in senior],
        notes=notes or None)


# ---------------------------------------------------------------------------
# Driver 4: Expansion / Headcount Growth (15%)
# ---------------------------------------------------------------------------

def expansion(employee_band: str, revenue_band: str, events: list,
              scored_on: date, window_days: int = 365) -> dict:
    """Expansion driver: size bands plus dated expansion and funding events.

    **Year-on-year growth is not in this score.** `firmographics` is a single
    row describing one moment; there is no earlier period to compare against, so
    headcount growth and revenue growth - which is what this driver is named
    for - cannot be computed from the delivered data. Inferring a trend from one
    observation would be inventing the number outright.

    What stands in their place is the size band, which says how big the account
    is and not whether it is growing, so this driver publishes `proxy: True`
    for the same reason Fleet Refresh does. The event terms are real signals and
    are the part of this driver that actually measures expansion.
    """
    have_bands = bool(_text(employee_band) or _text(revenue_band))
    if not have_bands and not events:
        return _unavailable(
            "expansion",
            "no employee or revenue band and no dated events on file")

    emp_points, emp_band = _band_points(employee_band, EMPLOYEE_BANDS)
    rev_points, rev_band = _band_points(revenue_band, REVENUE_BANDS)
    # The larger of the two ladders, not their sum: they describe the same
    # company on two axes, and adding them would count size twice.
    size_points = min(max(emp_points, rev_points), EXPANSION_SIZE_MAX)
    size_basis = "employee band %r / revenue band %r" % (
        emp_band or "none", rev_band or "none")

    recent_events, evidence = [], []
    for event in (events or []):
        if not isinstance(event, dict):
            continue
        when = _parse_date(event.get("event_date") or event.get("date"))
        if when and (scored_on - when).days > window_days:
            continue
        recent_events.append(event)

    def matching(terms):
        out = []
        for event in recent_events:
            blob = _lower("%s %s" % (event.get("event_headline")
                                     or event.get("headline") or "",
                                     event.get("event_type") or ""))
            if _any_term(blob, terms):
                out.append(_text(event.get("event_headline")
                                 or event.get("headline")))
        return sorted({h for h in out if h})

    expansion_hits = matching(EXPANSION_EVENT_TERMS)
    funding_hits = matching(FUNDING_EVENT_TERMS)
    event_points = min(len(expansion_hits) * POINTS_PER_EXPANSION_EVENT,
                       MAX_EXPANSION_EVENT_POINTS)
    funding_points = min(len(funding_hits) * POINTS_PER_FUNDING_EVENT,
                         MAX_FUNDING_POINTS)
    evidence.extend("news:%s" % h[:60] for h in expansion_hits + funding_hits)

    total = size_points + event_points + funding_points
    return _driver(
        "expansion", total,
        [
            _term("Size band", size_points, EXPANSION_SIZE_MAX, size_basis),
            _term("Expansion events", event_points, MAX_EXPANSION_EVENT_POINTS,
                  "%d expansion event%s within %d days"
                  % (len(expansion_hits), "" if len(expansion_hits) == 1 else "s",
                     window_days)),
            _term("Funding / M&A", funding_points, MAX_FUNDING_POINTS,
                  "%d funding or acquisition event%s within %d days"
                  % (len(funding_hits), "" if len(funding_hits) == 1 else "s",
                     window_days)),
        ],
        evidence,
        proxy=True,
        proxy_note=(
            "Year-on-year headcount and revenue growth are NOT scored: "
            "firmographics carries a single row, so there is no prior period "
            "to compare against. The size band stands in for them and measures "
            "how large the account is, not whether it is growing. Only the "
            "event terms measure expansion directly."))


# ---------------------------------------------------------------------------
# Driver 5: Intent (25%)
# ---------------------------------------------------------------------------

def intent(category_scores: list, supporting_signals: list,
           confirmed_technologies: list) -> dict:
    """Intent driver, following the four-step Intent & Demand Signals flow.

    `category_scores` are (category, score, keywords) from the HP category
    intent file - the primary signal. `supporting_signals` are (topic, score)
    Bombora pairs. `confirmed_technologies` are the technology names found in
    the account's stack, which is what turns a supporting signal from a claim
    into a confirmed one.

    The noisy-keyword gate is the same one Intent & Demand Signals applies: a
    category whose score rests on "SLA" or "identified as competitor of" keeps
    its score but cannot be chosen as primary. For Astra that matters - its
    top-scoring category is 3D Printers at 34, carried by `jig | SLA |
    manufacturing engineer` - so the primary falls to a weaker but trustworthy
    category rather than the highest number on the row.
    """
    scored = [(c, s, k) for c, s, k in (category_scores or []) if _text(c)]
    if not scored:
        return _unavailable(
            "intent",
            "no HP category intent scores on file for this account")

    clean, flagged = [], []
    for category, value, keywords in scored:
        blob = _lower(" ".join(keywords or []) if isinstance(keywords, (list, tuple))
                      else keywords)
        if _any_term(blob, NOISY_KEYWORDS):
            flagged.append(category)
        else:
            clean.append((category, value))

    if not clean:
        return _unavailable(
            "intent",
            "every category's score rests on a flagged keyword (%s) - none can "
            "serve as the primary signal" % ", ".join(sorted(set(flagged))))

    primary, primary_score = max(clean, key=lambda pair: pair[1] or 0)
    primary_points = (primary_score or 0) * PRIMARY_CATEGORY_WEIGHT

    signals = [(t, s) for t, s in (supporting_signals or [])
               if _text(t) and (s or 0) > SUPPORTING_SIGNAL_THRESHOLD]
    signal_points = min(len(signals) * POINTS_PER_SUPPORTING_SIGNAL,
                        MAX_SUPPORTING_POINTS)

    stack = " | ".join(_lower(t) for t in (confirmed_technologies or []))
    confirmed = sorted({t for t, _ in signals if _lower(t) in stack})
    confirm_points = min(len(confirmed) * POINTS_PER_TECH_CONFIRMATION,
                         MAX_TECH_CONFIRMATION_POINTS)

    evidence = ["hp_category_intent:%s" % _lower(primary)]
    evidence.extend("intent_topic:%s" % _lower(t) for t, _ in signals)

    notes = []
    if flagged:
        notes.append(
            "category/ies barred from primary on flagged keywords: %s"
            % ", ".join(sorted(set(flagged))))

    total = primary_points + signal_points + confirm_points
    return _driver(
        "intent", total,
        [
            _term("Primary category", primary_points,
                  int(100 * PRIMARY_CATEGORY_WEIGHT),
                  "%s scores %s/100" % (primary, primary_score)),
            _term("Supporting signals", signal_points, MAX_SUPPORTING_POINTS,
                  "%d Bombora topic%s above threshold"
                  % (len(signals), "" if len(signals) == 1 else "s")),
            _term("Tech confirmation", confirm_points,
                  MAX_TECH_CONFIRMATION_POINTS,
                  "%d signal%s confirmed in the technology stack"
                  % (len(confirmed), "" if len(confirmed) == 1 else "s")),
        ],
        evidence,
        notes=notes or None)


# ---------------------------------------------------------------------------
# The composite
# ---------------------------------------------------------------------------

FORMULA = ("Urgency = 20% Fleet Refresh + 25% AI/Workstation + 15% Hiring "
           "+ 15% Expansion/Print + 25% Intent. Each driver is 0-100. If any "
           "driver is unavailable the overall score is not calculated and is "
           "never substituted with 0.")


def score(drivers: list, scored_on: date | None = None) -> dict:
    """Combine five drivers into the urgency score, or refuse to.

    ABX's missing-input rule is absolute and is implemented literally: one
    unavailable driver means `score: None`, with the blockers named so the
    dashboard can say which driver is missing rather than showing an empty dial
    with no explanation.
    """
    scored_on = scored_on or datetime.now(UTC).date()
    by_key = {d["key"]: d for d in (drivers or []) if isinstance(d, dict)}

    ordered, missing = [], []
    for key in DRIVER_KEYS:
        driver = by_key.get(key) or _unavailable(
            key, "driver was not computed for this account")
        ordered.append(driver)
        if not driver.get("available"):
            missing.append(key)

    # ABX: link one evidence ID to every driver it supports rather than
    # deduplicating, so reuse is visible instead of silently collapsed.
    seen, shared = {}, {}
    for driver in ordered:
        for evidence_id in driver.get("evidence_ids") or []:
            seen.setdefault(evidence_id, []).append(driver["key"])
    for evidence_id, keys in seen.items():
        if len(keys) > 1:
            shared[evidence_id] = sorted(keys)

    total = None
    if not missing:
        total = round(sum(d["value"] * WEIGHTS[d["key"]] for d in ordered))

    proxies = [d["key"] for d in ordered if d.get("proxy")]
    return {
        "score": total,
        "max_score": DRIVER_MAX,
        "scored_on": scored_on.isoformat(),
        "available": total is not None,
        "unavailable_drivers": missing,
        "unavailable_reason": (
            None if not missing else
            "ABX missing-input rule: %s unavailable, so the overall score is "
            "not calculated and is not substituted with 0%%."
            % ", ".join(DRIVER_LABELS[k] for k in missing)),
        "drivers": ordered,
        "shared_evidence": shared,
        "proxy_drivers": proxies,
        "formula": FORMULA,
        "formula_authority": FORMULA_AUTHORITY,
        "client_agreed": False,
    }


# ---------------------------------------------------------------------------
# Assembly: read the datasets, compute the five drivers, publish the widget
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


def _category_scores(account_id, domain) -> list:
    """(category, score, keywords) per HP category, from the wide intent export.

    Delegates the parsing to Intent & Demand Signals rather than re-reading the
    two-header-row CSV here; this only reshapes its output into the triples the
    `intent()` driver takes.
    """
    from app.services.extractors.datasets import read_dataset_rows
    from app.services.extractors.intent_demand_signals import _parse_category_file

    parsed = _parse_category_file(
        read_dataset_rows(account_id, "hp_category_intent"), domain)
    out = []
    for name, entry in (parsed.get("categories") or {}).items():
        keywords = list(entry.get("keywords_matched") or [])
        keywords.extend(entry.get("topics_researched") or [])
        out.append((name, entry.get("score"), keywords))
    return out


def build_urgency_score(account_id: str, scored_on: date | None = None) -> dict:
    """Compute and persist `exec_urgency_score` for one account.

    Each driver is fed only from datasets that are actually registered for the
    account; a dataset that is absent yields an unavailable driver, which then
    blocks the composite by ABX's rule rather than scoring zero.
    """
    from app.database.mongodb import get_db
    from app.services.extractors.datasets import account_domain
    from app.services.extractors.intent_demand_signals import _read_dataset_records

    scored_on = scored_on or datetime.now(UTC).date()
    domain = account_domain(account_id)

    firmographics = _read_dataset_records(account_id, "firmographics")
    firm = firmographics[0] if firmographics else {}
    employee_band = firm.get("Number Of Employees Range") or firm.get("employee_count")
    revenue_band = firm.get("Yearly Revenue Range") or firm.get("yearly_revenue_range")

    jobs = _read_dataset_records(account_id, "job_openings")
    news = (_read_dataset_records(account_id, "google_news")
            + _read_dataset_records(account_id, "news_events"))
    technologies = _tech_names(account_id)
    categories = _category_scores(account_id, domain)

    topics = []
    for row in _read_dataset_records(account_id, "intent_score"):
        topic = (row.get("Topic") or row.get("topic")
                 or row.get("Topic Name") or row.get("topic_name"))
        raw = (row.get("Composite Score") or row.get("composite_score")
               or row.get("Score") or row.get("score"))
        try:
            value = float(str(raw).strip()) if _text(raw) else 0
        except ValueError:
            value = 0
        if _text(topic):
            topics.append((_text(topic), value))

    drivers = [
        fleet_refresh(technologies, employee_band),
        ai_workstation(topics,
                       [r.get("normalized_title") or r.get("title") for r in jobs],
                       [r.get("event_headline") or r.get("headline") for r in news]),
        hiring(jobs, scored_on),
        expansion(employee_band, revenue_band, news, scored_on),
        intent(categories, topics, technologies),
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
        "status": "available" if payload["available"] else "partial",
        "data": payload,
        "source_datasets": ["firmographics", "technographics", "webstack",
                            "job_openings", "intent_score",
                            "hp_category_intent", "google_news", "news_events"],
        "updated_at": now,
    }
    if not existing:
        record["extracted_at"] = now
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": WIDGET_KEY},
        {"$set": record}, upsert=True)

    logger.info("urgency score for %s: %s (%d driver(s) unavailable)",
                account_id, payload["score"], len(payload["unavailable_drivers"]))
    return payload
