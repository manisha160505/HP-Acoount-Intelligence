"""Evidence Strength: one 0-100 score per catalyst, from three stated terms.

    Evidence Strength = Filing Evidence + Recency + Source Diversity
                      = (5 x filings, max 25)
                      + (25/20/15/10/5/0 by age band)
                      + (10 x source category, max 50)

This replaces the refusal `priorities.py` used to publish. That refusal was
right about ABX's own weighting - 40/25/20/15 over four counts with no stated
normalisation - and it stays right about that. What changed is that this is a
*different, fully specified* formula: every term names its own unit, its own
points and its own cap, so nothing has to be invented to compute it. The four
ABX measures are still published alongside as the counts they are.

Two conventions the formula does not state, fixed here rather than left to
drift, both single constants so they are cheap to change:

**A fiscal year ends on 31 December** (`FISCAL_YEAR_END`). A narrative sentence
inherits its filing's reporting period - `_reporting_periods()` in `corpus.py`
reads that from the filing's own tables - and a period label like `FY2025` names
a year, not a day. Astra's year ends in December. An account whose year ends in
March would be dated up to nine months late, which crosses at most one band
boundary; when such an account arrives, this constant is where its calendar
goes.

**Age is frozen at generation time**, not measured from "now" on each render.
A score that drifts is a score that cannot be checked: the same catalyst, the
same evidence, would read 25 one week and 20 the next with nothing in the
account having changed, and no one looking at it could tell why. The scoring
date is published in the payload so the number can be recomputed and agreed.

What this module deliberately does NOT do is guess a category. A source whose
category cannot be established from its own registered fields is counted as
`uncategorised` and scores nothing, and the payload names it. Diversity is half
the available points; inferring a category from a publisher's name would be
inventing that half.
"""

import logging
import re
from datetime import date, timedelta

_ONE_DAY = timedelta(days=1)

logger = logging.getLogger(__name__)

# --- Filing Evidence -------------------------------------------------------

POINTS_PER_FILING = 5
MAX_FILING_POINTS = 25

# --- Recency ---------------------------------------------------------------

# (upper bound in months inclusive, points). Read in order, first match wins.
RECENCY_BANDS = (
    (12, 25),
    (24, 20),
    (36, 15),
    (60, 10),
)
RECENCY_BEYOND_BANDS = 5      # older than 60 months
RECENCY_NO_DATE = 0           # no usable date on any supporting source

FISCAL_YEAR_END = (12, 31)    # (month, day) - see module docstring

# --- Source Diversity ------------------------------------------------------

POINTS_PER_CATEGORY = 10
MAX_DIVERSITY_POINTS = 50

REGULATORY_FILINGS = "Regulatory Filings"
OFFICIAL_COMPANY = "Official Company Sources"
INVESTOR_MATERIALS = "Investor Materials"
GOVERNMENT = "Government Sources"
INDEPENDENT_MEDIA = "Independent Media"
UNCATEGORISED = "uncategorised"

# The closed list. Five categories x 10 points is exactly the 50-point cap, so
# the maximum is reachable in principle rather than only in arithmetic.
SOURCE_CATEGORIES = (REGULATORY_FILINGS, OFFICIAL_COMPANY, INVESTOR_MATERIALS,
                     GOVERNMENT, INDEPENDENT_MEDIA)

# A dataset that is self-evidently one category, needing no URL to establish it.
# `compliance_filings` IS the regulatory filing - the dataset key carries the
# fact that a URL would otherwise have to prove. `job_openings` are the account's
# own postings; the careers-site-vs-LinkedIn split is made below, because only
# the former is the company speaking.
DATASET_CATEGORIES = {
    "compliance_filings": REGULATORY_FILINGS,
}

# Exchanges and securities regulators, matched as host suffixes. This list is
# the one part of this module that is inherently incomplete: there are 220
# accounts across an unknown set of markets, and a regulator is only recognised
# if it is named here. An unlisted one falls through to INDEPENDENT_MEDIA, which
# is wrong but not silent - it still scores a category, and the payload's
# per-category counts show where it landed. Add markets as accounts arrive
# rather than guessing at them now.
REGULATOR_HOSTS = (
    "idx.co.id",            # Indonesia
    "sec.gov",              # United States
    "sgx.com",              # Singapore
    "bursamalaysia.com",    # Malaysia
    "set.or.th",            # Thailand
    "hkex.com.hk",          # Hong Kong
    "bseindia.com",         # India
    "nseindia.com",
    "asx.com.au",           # Australia
    "jpx.co.jp",            # Japan
    "edinet-fsa.go.jp",
    "londonstockexchange.com",
    "bundesanzeiger.de",    # Germany
    "twse.com.tw",          # Taiwan
    "krx.co.kr",            # Korea
    "psx.com.pk",           # Pakistan
    "pse.com.ph",           # Philippines
    "hose.vn",              # Vietnam
)

# Government hosts. Matched two ways because the world does not agree on where
# the "gov" goes: a suffix like `.go.id` or `.gov.sg` ends the host, while the
# UK's `gov.uk` and India's `gov.in` put it in the middle. Suffix-matching alone
# missed every one of the latter.
GOVERNMENT_SUFFIXES = (".gov", ".go.id", ".go.jp", ".go.kr", ".govt.nz")
GOVERNMENT_LABELS = ("gov", "govt", "go")

# A host that resolves nothing about who published a page. `news.google.com` is
# the one that matters here: every news row in this corpus links through it, so
# the link identifies the aggregator and not the outlet. Categorising on it
# would make twelve different publishers look like one source, which is the
# opposite of what diversity is measuring - so the URL is ignored for these
# hosts and the decision falls to the publisher name.
AGGREGATOR_HOSTS = ("news.google.com", "google.com", "bing.com",
                    "finance.yahoo.com")

# Hosts that carry someone else's content: the company posts there, but the
# platform is not the company speaking, and two accounts' LinkedIn pages are not
# two sources.
PLATFORM_HOSTS = ("linkedin.com", "facebook.com", "twitter.com", "x.com",
                  "instagram.com", "youtube.com")


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _host(url) -> str:
    """Bare lower-case host of a URL, or "" when there isn't one.

    Returns "" for anything that is not a plausible host - a bare sentence, a
    `javascript:` scheme, an empty authority. Across 220 accounts these arrive
    in vendor exports, and a string that is not a host must not be scored as
    though it were a publication.
    """
    text = _text(url)
    if not text:
        return ""
    match = re.match(r"^(?P<scheme>[a-zA-Z][\w+.-]*):(?P<rest>.*)$", text)
    if match:
        if not match.group("rest").startswith("//"):
            # `javascript:`, `mailto:`, `data:` - a scheme with no authority.
            return ""
        host = match.group("rest")[2:].split("/")[0]
    else:
        host = text.lstrip("/").split("/")[0]
    host = host.split("?")[0].split("#")[0]
    host = host.split("@")[-1].split(":")[0].lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    # A host has at least one dot and only host characters. "not a url" and
    # "https://" both fail this and score nothing.
    if "." not in host or not re.fullmatch(r"[a-z0-9.-]+", host):
        return ""
    return host


def _matches(host: str, suffixes) -> bool:
    """Whether `host` is one of `suffixes` or a subdomain of one.

    Compared label-wise rather than by `endswith` alone, so a lookalike host
    like `notidx.co.id.evil.com` does not match `idx.co.id`.
    """
    return any(host == s or host.endswith("." + s) for s in suffixes)


# A registrable name sits below these, not beside them: `astra.co.id` is one
# organisation, and `co.id` is not. Only the multi-label public suffixes the
# accounts in this platform actually use are listed; a name under an unlisted
# one is compared on its last two labels, which is right for `.com` and `.de`.
_MULTI_LABEL_SUFFIXES = (
    "co.id", "co.uk", "co.jp", "co.th", "co.kr", "co.nz", "co.in", "co.za",
    "com.au", "com.sg", "com.my", "com.ph", "com.vn", "com.tw", "com.hk",
    "com.cn", "com.br", "com.mx", "com.tr", "or.id", "or.th", "ne.jp",
    "org.uk", "ac.uk", "gov.uk", "org.au", "net.au",
)


def _registrable(host: str) -> str:
    """The organisation-owning part of a host: `careers.tesco.co.uk` -> `tesco.co.uk`."""
    labels = host.split(".")
    if len(labels) < 2:
        return host
    for suffix in _MULTI_LABEL_SUFFIXES:
        if host == suffix:
            return host
        if host.endswith("." + suffix):
            return ".".join(labels[-(suffix.count(".") + 2):])
    return ".".join(labels[-2:])


def _same_organisation(host: str, domain: str) -> bool:
    """Whether two hosts belong to the same company.

    A company's careers site is frequently on a different registrable domain
    from the one firmographics records - `tesco.co.uk` against `tesco.com`,
    `jobs.apple.com` against `apple.com`. Matching on the name below the public
    suffix catches the country-domain case, which pure subdomain matching
    misses and which will be common across 220 international accounts.

    Deliberately narrow: only the *name* is compared, and only when it is long
    enough to be distinctive. Two unrelated companies sharing a short name in
    different countries would both be the account's own site under a looser
    test, and a wrong Official Company Sources is worse than an honest
    Independent Media.
    """
    name = _registrable(host).split(".")[0]
    own = _registrable(domain).split(".")[0]
    return bool(name) and len(name) >= 4 and name == own


# ---------------------------------------------------------------------------
# Term 3: source diversity
# ---------------------------------------------------------------------------

def categorise(source: dict, account_domain: str = "") -> str:
    """Which source category one citation belongs to, or `uncategorised`.

    Decided from the fields the evidence row already carries - its dataset, its
    URL and its publisher - in that order of reliability. A dataset key is a
    fact about where the row came from; a URL can be checked; a publisher name
    is a string someone typed. Nothing is inferred beyond those.

    `account_domain` is what makes "the company's own site" decidable rather
    than guessable: a page on the account's own domain is the company speaking,
    whether it is a news release or a job posting, which is exactly the rule the
    specification gives - *"a company news page and the same company's careers
    page would both fall under Official Company Sources"*.
    """
    source = source or {}

    dataset = _text(source.get("dataset"))
    if dataset in DATASET_CATEGORIES:
        return DATASET_CATEGORIES[dataset]

    # A filing label is registered by the compliance-filings path alone, so a
    # row carrying one is a filing even if its dataset was overridden for the
    # citation's benefit.
    if _text(source.get("filing_label")):
        return REGULATORY_FILINGS

    host = _host(source.get("source_url"))
    if host and not _matches(host, AGGREGATOR_HOSTS):
        if _matches(host, REGULATOR_HOSTS):
            return REGULATORY_FILINGS

        # The label test reads the host's own segments rather than its tail, so
        # `gov.uk` and `sebi.gov.in` are recognised alongside `.go.id`. Only
        # segments from the second-last backwards are considered, which keeps a
        # company called "gov-solutions.com" out while still matching a bare
        # `gov.uk`, where the government label IS the second-last segment.
        labels = host.split(".")
        if host.endswith(GOVERNMENT_SUFFIXES) or any(
                label in GOVERNMENT_LABELS for label in labels[-2:]):
            return GOVERNMENT

        domain = _host(account_domain) or _text(account_domain).lower()
        if domain and (host == domain or host.endswith("." + domain)
                       or _same_organisation(host, domain)):
            # The account's own domain: its careers site, newsroom and investor
            # pages are all the company speaking. Investor material is called
            # out separately because a seller reads it differently.
            return (INVESTOR_MATERIALS
                    if re.search(r"\b(investor|ir)\b", host) else OFFICIAL_COMPANY)

        if _matches(host, PLATFORM_HOSTS):
            # A third-party platform. Not the company, not a publication, and
            # not independent reporting - so it establishes no category on its
            # own rather than borrowing one.
            return UNCATEGORISED

        if not domain:
            # Without the account's own domain there is no way to tell its
            # newsroom from a newspaper, so neither is claimed. Firmographics
            # supplies the domain for every account that has one; an account
            # missing it scores diversity only from evidence that names its
            # category some other way.
            return UNCATEGORISED

        # A host that is none of the above and is not an aggregator is a
        # publication: someone else writing about the account.
        return INDEPENDENT_MEDIA

    # No usable URL. A named publisher is still evidence that somebody outside
    # the account reported this, which is what the category means - but only
    # when it is not the account itself under its own name.
    publisher = _text(source.get("publisher"))
    if publisher:
        company = _text(source.get("company_name"))
        if company and publisher.lower() == company.lower():
            return OFFICIAL_COMPANY
        return INDEPENDENT_MEDIA

    return UNCATEGORISED


def diversity(sources: list, account_domain: str = "") -> dict:
    """Source-diversity term: 10 points per distinct category, capped at 50."""
    counts, uncategorised = {}, 0
    for source in (sources or []):
        category = categorise(source, account_domain)
        if category == UNCATEGORISED:
            uncategorised += 1
        else:
            counts[category] = counts.get(category, 0) + 1

    # Stable order, so two runs of the same account list them the same way.
    found = [c for c in SOURCE_CATEGORIES if c in counts]
    points = min(len(found) * POINTS_PER_CATEGORY, MAX_DIVERSITY_POINTS)
    return {
        "points": points,
        "max_points": MAX_DIVERSITY_POINTS,
        "categories": found,
        "category_counts": {c: counts[c] for c in found},
        "uncategorised_sources": uncategorised,
        "basis": "%d distinct source categor%s x %d points"
                 % (len(found), "y" if len(found) == 1 else "ies",
                    POINTS_PER_CATEGORY),
    }


# ---------------------------------------------------------------------------
# Term 1: filing evidence
# ---------------------------------------------------------------------------

def filing_evidence(sources: list) -> dict:
    """Filing term: 5 points per distinct supporting filing, capped at 25.

    A *filing* is one document, not one claim. Eight sentences quoted from one
    annual report are eight pieces of support for the recency and diversity
    terms but one filing here, which is what the specification's worked example
    counts - *"two relevant filings: 10"*.

    Only sources that survived the relevance gate in `_resolve_priorities` reach
    this function, so "relevant to the catalyst" has already been decided and is
    not re-tested here.
    """
    filings = {_text(s.get("filing_label")) for s in (sources or [])
               if _text(s.get("filing_label"))}
    points = min(len(filings) * POINTS_PER_FILING, MAX_FILING_POINTS)
    return {
        "points": points,
        "max_points": MAX_FILING_POINTS,
        "filing_count": len(filings),
        "filings": sorted(filings),
        "basis": "%d relevant filing%s x %d points"
                 % (len(filings), "" if len(filings) == 1 else "s",
                    POINTS_PER_FILING),
    }


# ---------------------------------------------------------------------------
# Term 2: recency
# ---------------------------------------------------------------------------

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun",
           "jul", "aug", "sep", "oct", "nov", "dec")


def parse_period(period) -> date | None:
    """The date a period label refers to, or None when it names no date.

    Three shapes reach this function, and they are the three the corpus
    produces - an ISO date on a news row, and the two the filing parser emits:

        2026-07-15   an event date, used as it stands
        2026-Jul     a month, taken at its last day
        FY2025       a fiscal year, taken at `FISCAL_YEAR_END`

    A label of any other shape returns None and scores zero rather than being
    coerced into a date. `period_key` in `financials.py` sorts these same
    labels; this converts them, and the two agree on which shapes exist.
    """
    text = _text(period)
    if not text:
        return None

    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", text)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)),
                        int(match.group(3)))
        except ValueError:
            return None

    match = re.match(r"^(\d{4})-([A-Za-z]{3})$", text)
    if match and match.group(2).lower() in _MONTHS:
        year, month = int(match.group(1)), _MONTHS.index(match.group(2).lower()) + 1
        if month == 12:
            return date(year, 12, 31)
        return date(year, month + 1, 1) - _ONE_DAY

    # A fiscal year, with or without the FY prefix and with or without a second
    # year after it: `FY2025`, `FY2025/26`, `2025`. The FIRST year is the one
    # taken, so a UK-style `FY2025/26` is dated at the end of 2025 rather than
    # being read as 2026 - consistent with `period_key`, which sorts on the same
    # leading year.
    # The trailing `/26` form is accepted only with a slash. A hyphen there is
    # ambiguous with the `2026-07` month shape above, and reading a malformed
    # `2025-13` as "the 2025 fiscal year" would turn a parse failure into a
    # confident wrong date.
    # A hyphenated span is accepted only behind an explicit `FY`, because
    # `2025-13` without it is a malformed month, not a fiscal year - and reading
    # that as "the 2025 fiscal year" would turn a parse failure into a
    # confident wrong date.
    match = (re.match(r"^FY(\d{4})(?:[/-]\d{2,4})?(?:\s+total)?$", text, re.I)
             or re.match(r"^(\d{4})(?:/\d{2,4})?(?:\s+total)?$", text, re.I))
    if match:
        year = int(match.group(1))
        # `date()` raises below year 1, and a four-digit year outside the range
        # a filing could plausibly report is a parse artefact rather than a
        # date. Returning None scores it zero, which is the honest answer; an
        # exception here would abandon the whole account's widget.
        if not 1900 <= year <= 2100:
            return None
        return date(year, FISCAL_YEAR_END[0], FISCAL_YEAR_END[1])

    return None


def months_between(earlier: date, later: date) -> int:
    """Whole months from `earlier` to `later`, never negative.

    Counted in calendar months rather than by dividing days, so a band boundary
    falls on the day a reader would expect: evidence dated 31 Dec 2025 is 12
    months old on 31 Dec 2026 and 13 months old the day after, regardless of
    which of those years was a leap year.

    Evidence dated after the scoring date - a filing reporting a year that has
    not ended - is zero months old, not negative.
    """
    months = (later.year - earlier.year) * 12 + (later.month - earlier.month)
    if later.day < earlier.day:
        months -= 1
    return max(months, 0)


def recency(sources: list, scored_on: date) -> dict:
    """Recency term, from the most recent dated source supporting the catalyst.

    The *most recent* one, because the term asks how current the evidence is,
    and a catalyst supported by a 2026 news item and a 2019 filing is evidenced
    now. Sources carrying no parseable period do not drag the age down; they are
    counted so the payload can say how many were undated.
    """
    dates, undated = [], 0
    for source in (sources or []):
        parsed = parse_period(source.get("period")
                              or source.get("filing_period"))
        if parsed is None:
            undated += 1
        else:
            dates.append(parsed)

    if not dates:
        return {
            "points": RECENCY_NO_DATE,
            "max_points": RECENCY_BANDS[0][1],
            "most_recent_date": None,
            "age_months": None,
            "undated_sources": undated,
            "basis": "no supporting source carries a usable date",
        }

    most_recent = max(dates)
    age = months_between(most_recent, scored_on)
    points = RECENCY_BEYOND_BANDS
    band = "more than %d months" % RECENCY_BANDS[-1][0]
    for upper, value in RECENCY_BANDS:
        if age <= upper:
            points, band = value, "within %d months" % upper
            break

    return {
        "points": points,
        "max_points": RECENCY_BANDS[0][1],
        "most_recent_date": most_recent.isoformat(),
        "age_months": age,
        "undated_sources": undated,
        "basis": "most recent supporting evidence is %s (%d month%s old)"
                 % (band, age, "" if age == 1 else "s"),
    }


# ---------------------------------------------------------------------------
# The score
# ---------------------------------------------------------------------------

MAX_SCORE = MAX_FILING_POINTS + RECENCY_BANDS[0][1] + MAX_DIVERSITY_POINTS

FORMULA = ("Evidence Strength = Filing Evidence (5 per relevant filing, max 25) "
           "+ Recency (25/20/15/10/5 by age band, 0 when undated) "
           "+ Source Diversity (10 per distinct source category, max 50).")


def score(sources: list, scored_on: date, account_domain: str = "") -> dict:
    """Evidence Strength for one catalyst, with every term's working shown.

    The three terms are published beside the total, each carrying the count it
    was computed from and a sentence saying so, because a reader who disagrees
    with 65/100 needs to see which term they disagree with. A bare number would
    be the same failure the old `evidence_score: null` was avoiding, only
    quieter.
    """
    filings = filing_evidence(sources)
    recent = recency(sources, scored_on)
    diverse = diversity(sources, account_domain)
    total = filings["points"] + recent["points"] + diverse["points"]

    return {
        "score": total,
        "max_score": MAX_SCORE,
        "scored_on": scored_on.isoformat(),
        "terms": [
            {"key": "filing_evidence", "label": "Filing evidence", **filings},
            {"key": "recency", "label": "Recency", **recent},
            {"key": "source_diversity", "label": "Source diversity", **diverse},
        ],
        "formula": FORMULA,
        "scoring_date_basis": (
            "Age is measured to the date this was generated, not to the date "
            "it is read, so the same evidence always scores the same."),
    }
