"""The deterministic half of the Live Signal Score.

    Live Signal Score = 30% Recency
                      + 50% Signal Relevance and Impact
                      + 20% Source Reliability

This implements `HP_Live_Signal_Scoring_Logic.docx`, the client's scoring
specification for news and event signals. It replaces the five model-scored
D1-D5 dimensions that stood in `recent_news_signals.py` before.

Two of the three drivers are decided here, in Python, with no model involved:

**Recency is arithmetic.** The old implementation asked GPT-4o to score how
recent an event was, which is a date subtraction wearing a costume. The
specification gives explicit day bands, so `recency_points` computes it.

**Source reliability is a lookup.** The specification's bands describe classes
of publisher, not judgements about an article, so the work is classifying a
domain rather than reading prose. The one genuinely uncertain case - a domain
nobody has classified - falls to `UNKNOWN`, and the caller decides whether to
ask the model.

Only Signal Relevance and Impact stays with the model, because deciding that
"opens a new factory" is a business trigger and "announces a dividend" is not
is a semantic call. That lives in `recent_news_signals.py`.

## The rule that matters most

The specification scores **the underlying source, not the pipe that found it**:

    "a company press release discovered through Google News RSS is still
    first-party evidence"

So a `news.google.com` URL is never itself the source. `resolve_source_url`
unwraps it to the publisher underneath before the domain is classified, and
does it **offline** - the redirect target is encoded in the URL itself, so no
network call is needed and none is made. A scorer that reached out to the
network would be untestable, slow, and would score differently depending on
whether a site happened to be up.

## Missing inputs score zero; they are not suppressed

Every band table here has a bottom row for absent data - no usable date scores
0, an untraceable source scores 0 - and the signal still carries a score. The
specification contains no suppression rule at all. The decision to keep a
publish floor is the caller's, and it is deliberate: see
`MIN_CONFIDENCE_TO_PUBLISH` in `recent_news_signals.py`.
"""

import base64
import binascii
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, unquote, urlparse

from app.config import scoring as _scoring

# Weights and bands come from config/scoring.yaml so the client's numbers can
# be retuned without editing this module.
_CFG = _scoring.section("live_signal")

# ==============================================================================
# Driver weights. Python owns the composite - the model is never asked for it.
# ==============================================================================

WEIGHTS = _scoring.weights("live_signal")

DRIVER_MAX = _CFG["driver_max"]

# The specification's authority string, published so a reader can trace a score
# back to the document that defines it.
FORMULA = ("Live Signal Score = (Recency x 30%) + (Signal Relevance and Impact "
           "x 50%) + (Source Reliability x 20%)")
FORMULA_AUTHORITY = "HP_Live_Signal_Scoring_Logic.docx"

# ==============================================================================
# Driver 1 - Recency (30%)
# ==============================================================================

# "Age of individual Live Signal | Recency score", verbatim from the
# specification. Read as (maximum age in days, points); the first row whose
# bound the age satisfies wins.
RECENCY_BANDS = _scoring.bands("live_signal", "recency_bands")
RECENCY_OVER_365 = _CFG["recency_over_max"]

# "No usable date | 0/10". Scored, not suppressed, and not treated as recent.
RECENCY_NO_DATE = _CFG["recency_no_date"]


def recency_points(event_dt: datetime | None, now: datetime | None = None) -> tuple[int, str]:
    """Points for how old a signal is, and the basis for that number.

    `event_dt` must already carry the specification's date precedence: the
    actual event date where available, otherwise the publication date, and
    never the date the platform crawled the record. `_build_signals` in
    `recent_news_signals.py` applies that precedence when it parses each row.

    A future-dated event scores as same-day rather than as an error: the
    specification has no band for it, and treating a typo in a source file as
    365-days-stale would be a worse answer than treating it as new.
    """
    if event_dt is None:
        return RECENCY_NO_DATE, "no usable event or publication date"

    now = now or datetime.now(UTC)
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=UTC)

    age_days = max((now - event_dt).days, 0)

    for max_days, points in RECENCY_BANDS:
        if age_days <= max_days:
            return points, "%d days old" % age_days
    return RECENCY_OVER_365, "%d days old, over 365" % age_days


# ==============================================================================
# Driver 3 - Source Reliability (20%)
# ==============================================================================

FIRST_PARTY = _CFG["source_first_party"]
ESTABLISHED_REPORTING = _CFG["source_established"]
STRUCTURED_THIRD_PARTY = _CFG["source_structured"]
WEAK_SECONDARY = _CFG["source_weak"]
UNVERIFIABLE = _CFG["source_unverifiable"]

# A domain nobody has classified. Distinct from UNVERIFIABLE, which means there
# is no source at all - an unrecognised publisher is a gap in this table, not
# evidence that the source is bad, so the caller can choose to ask the model
# rather than silently scoring it 0.
UNKNOWN = None

# --- 10/10: first-party or authoritative --------------------------------------
# "Company newsroom, investor relations, official company filing,
# government/regulatory source, official procurement/tender, official careers
# page, or official partner announcement directly confirming the event."
#
# Matched on URL path rather than domain, because first-party status is a
# property of the page: astra.co.id/investor-relations is first-party, and so
# is any other company's. Account-agnostic by construction - no company domain
# is ever listed here.
FIRST_PARTY_PATH_MARKERS = (
    "/investor-relations", "/investor_relations", "/investors", "/ir/",
    "/newsroom", "/news-room", "/press-release", "/press-releases",
    "/press/", "/media-release", "/media-releases", "/media-centre",
    "/media-center", "/announcements", "/corporate-news",
    "/careers", "/jobs/", "/vacancies",
    "/annual-report", "/annual-reports", "/financial-results",
    "/results/", "/disclosure", "/disclosures", "/filings",
    "/tender", "/tenders", "/procurement",
)

# Regulators, exchanges and government. These are institutions, not companies,
# so naming them is not account-specific.
AUTHORITATIVE_DOMAIN_SUFFIXES = (
    ".gov", ".gov.uk", ".gov.au", ".gov.sg", ".gov.my", ".gov.ph", ".gov.vn",
    ".go.id", ".go.jp", ".go.kr", ".go.th",
    ".govt.nz", ".gc.ca", ".europa.eu",
)
AUTHORITATIVE_DOMAINS = frozenset({
    "sec.gov", "idx.co.id", "asx.com.au", "sgx.com", "bursamalaysia.com",
    "set.or.th", "pse.com.ph", "hkex.com.hk", "jpx.co.jp", "krx.co.kr",
    "nzx.com", "londonstockexchange.com", "nasdaq.com", "nyse.com",
    "disclosure.edinet-fsa.go.jp", "dart.fss.or.kr",
})

# --- 8/10: established independent reporting ----------------------------------
# "Established business, financial, technology, national/international news or
# industry publication with identifiable reporting."
ESTABLISHED_PUBLISHERS = frozenset({
    "reuters.com", "bloomberg.com", "ft.com", "wsj.com", "nikkei.com",
    "cnbc.com", "forbes.com", "fortune.com", "economist.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "apnews.com", "afp.com",
    "theguardian.com", "nytimes.com", "washingtonpost.com", "time.com",
    "businessinsider.com", "axios.com", "politico.com",
    "techcrunch.com", "theverge.com", "wired.com", "zdnet.com", "cnet.com",
    "arstechnica.com", "theregister.com", "computerworld.com", "infoworld.com",
    "networkworld.com", "crn.com", "channelfutures.com", "itpro.com",
    "scmp.com", "straitstimes.com", "channelnewsasia.com", "todayonline.com",
    "thejakartapost.com", "jakartaglobe.id", "kompas.com", "tempo.co",
    "bisnis.com", "kontan.co.id", "idnfinancials.com", "katadata.co.id",
    "thestar.com.my", "nst.com.my", "theedgemalaysia.com", "malaymail.com",
    "bangkokpost.com", "nationthailand.com", "inquirer.net",
    "philstar.com", "rappler.com", "businessworld.com.ph",
    "vnexpress.net", "vietnamnews.vn", "tuoitrenews.vn",
    "afr.com", "smh.com.au", "theage.com.au", "news.com.au", "abc.net.au",
    "nzherald.co.nz", "stuff.co.nz", "rnz.co.nz",
    "japantimes.co.jp", "asia.nikkei.com", "koreaherald.com",
    "koreatimes.co.kr", "chosun.com", "yonhapnews.co.kr",
    "economictimes.indiatimes.com", "livemint.com", "business-standard.com",
})

# --- 3/10: weak secondary evidence --------------------------------------------
# "Aggregator, repost or secondary summary where the original evidence cannot
# clearly be established."
AGGREGATOR_DOMAINS = frozenset({
    "news.google.com", "news.yahoo.com", "finance.yahoo.com", "msn.com",
    "flipboard.com", "feedly.com", "smartnews.com", "newsbreak.com",
    "medium.com", "substack.com", "blogspot.com", "wordpress.com",
    "linkedin.com", "facebook.com", "twitter.com", "x.com", "reddit.com",
    "prnewswire.com", "businesswire.com", "globenewswire.com", "einpresswire.com",
    "openpr.com", "prlog.org", "issuewire.com",
})

# Datasets that are structured provider evidence rather than a published
# article. The specification scores these 6/10 when no underlying source URL is
# supplied: "PredictLeads or Explorium structured event, where no underlying
# source url/publisher is available to independently verify it".
STRUCTURED_PROVIDER_DATASETS = frozenset({"news_events", "job_openings", "hiring_events"})


def _registrable(host: str) -> str:
    """Strip a leading www. so 'www.reuters.com' and 'reuters.com' agree."""
    host = (host or "").lower().strip()
    return host[4:] if host.startswith("www.") else host


def _squash(text: str) -> str:
    """Lowercase, alphanumeric only. 'Tempo.co English' -> 'tempocoenglish'."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


# Brand labels pulled out of the domain tables, for matching a publisher NAME
# against them. A publisher string is matched by containment because feeds
# decorate the name: "Tempo.co English", "Reuters UK", "CNBC Indonesia".
#
# The domain cannot be squashed whole - "idnfinancials.com" becomes
# "idnfinancialscom", which the publisher "IDNFinancials" does not contain. So
# the TLD-ish labels are dropped and the brand labels kept.

# Country and generic top-level labels, plus the geographic and section
# prefixes publishers put in front of a brand. Neither identifies an outlet.
_NON_BRAND_LABELS = frozenset({
    "com", "co", "uk", "us", "org", "net", "info", "biz",
    "id", "my", "au", "ph", "vn", "jp", "kr", "th", "nz", "sg", "in", "cn", "hk",
    "asia", "edition", "www", "news", "en", "english", "global", "world",
    "amp", "m", "mobile",
})

# Five characters minimum. A shorter label is too easy to hit inside an
# unrelated publisher name, and a false match here silently promotes a random
# outlet to first-party or tier-1 reporting.
_MIN_BRAND_LEN = 5


def _brand_labels(domain: str) -> list[str]:
    """The identifying labels of a domain. 'idnfinancials.com' ->
    ['idnfinancials']; 'asia.nikkei.com' -> ['nikkei']; 'bbc.co.uk' -> []."""
    return [label for label in domain.lower().split(".")
            if label not in _NON_BRAND_LABELS and len(label) >= _MIN_BRAND_LEN]


# Brands below the length floor that are distinctive enough to match anyway.
# Deliberately short: every entry has to be a string that does not occur inside
# unrelated publisher names. "time" is the counter-example and is NOT here - it
# would match "Asia Times", "The Times" and "Financial Times".
_SHORT_BRANDS = (("cnbc", "cnbc.com"),)


def _roots(domains, extra=()) -> tuple:
    """(brand label, domain) pairs, longest label first so the most specific
    match wins."""
    pairs = [(label, d) for d in domains for label in _brand_labels(d)]
    pairs.extend(extra)
    return tuple(sorted(set(pairs), key=lambda pair: -len(pair[0])))


_ESTABLISHED_ROOTS = _roots(ESTABLISHED_PUBLISHERS, _SHORT_BRANDS)
_AGGREGATOR_ROOTS = _roots(AGGREGATOR_DOMAINS)


def _publisher_band(publisher: str, company_name: str = "") -> tuple[int | None, str]:
    """Classify a source from its publisher NAME rather than its URL.

    This exists because the URL is often useless. Real Google News RSS exports
    carry an opaque `/rss/articles/CBMi...` link that encodes nothing
    recoverable offline, while the same row names the publisher in its own
    column - so the name is the only usable identity for the underlying source,
    and the specification is explicit that the underlying source is what gets
    scored.

    The specification says as much for the Exa.ai pipe: *"If source_publisher is
    blank, identify the source from event_url"* - the name leads, the URL is the
    fallback.

    A publisher that IS the account is first-party evidence: a press release on
    the company's own feed is a company announcement whatever pipe carried it.
    That is matched against the account's own name rather than any hardcoded
    list, so it stays account-agnostic.
    """
    squashed = _squash(publisher)
    if not squashed:
        return UNKNOWN, ""

    # The account talking about itself. Guarded on length so a short or generic
    # company name cannot swallow unrelated publishers.
    company = _squash(company_name)
    if len(company) >= 6 and (company in squashed or squashed in company):
        return FIRST_PARTY, "the account's own announcement"

    # Aggregators are checked first: a name matching both is the pipe.
    for root, domain in _AGGREGATOR_ROOTS:
        if root in squashed:
            return WEAK_SECONDARY, "aggregator or syndicated release (%s)" % domain

    for root, domain in _ESTABLISHED_ROOTS:
        if root in squashed:
            return ESTABLISHED_REPORTING, "established publication (%s)" % domain

    return UNKNOWN, ""


def _domain_matches(host: str, known: frozenset) -> bool:
    """True when the host is a known domain or a subdomain of one.

    Subdomains count because publishers put newsrooms on them - `asia.nikkei.com`
    and `edition.cnn.com` are the same publisher as the apex. Matching is on a
    dot boundary so `notreuters.com` cannot match `reuters.com`.
    """
    if not host:
        return False
    if host in known:
        return True
    return any(host.endswith("." + domain) for domain in known)


# ==============================================================================
# Unwrapping the pipe to reach the real source
# ==============================================================================

_GOOGLE_NEWS_HOSTS = ("news.google.com", "news.url.google.com")
_URL_IN_QUERY_KEYS = ("url", "u", "q", "target", "redirect")
_HTTP_RE = re.compile(rb"https?://[\x20-\x7e]{4,}")


def _decode_google_news_path(path: str) -> str:
    """Recover the destination URL encoded in a Google News article path.

    Google News article links carry the destination inside a base64 blob in the
    path (`/rss/articles/CBMi...`). The blob is a protobuf, not a bare URL, so
    this does not try to parse it properly - it decodes the bytes and looks for
    the first http(s) run inside, which is where the destination sits.

    Returns "" when nothing decodable is found, which is the honest answer for
    the newer opaque link format. The caller then treats the Google URL as what
    it is: an aggregator, scoring 3, rather than guessing at a publisher.
    """
    segment = ""
    for part in path.split("/"):
        if len(part) > len(segment) and re.fullmatch(r"[A-Za-z0-9_\-]+", part or ""):
            segment = part
    if len(segment) < 16:
        return ""

    padded = segment.replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)
    try:
        raw = base64.b64decode(padded, validate=False)
    except (binascii.Error, ValueError):
        return ""

    match = _HTTP_RE.search(raw)
    if not match:
        return ""

    found = match.group(0).decode("utf-8", "ignore")
    # The protobuf puts a length-prefixed field after the URL, so trim at the
    # first byte that cannot appear in one.
    found = re.split(r"[^\x21-\x7e]", found)[0]
    found = found.rstrip("\\\"'<>)")
    return found if len(found) > 12 else ""


def resolve_source_url(url: str) -> tuple[str, bool]:
    """Unwrap an aggregator link to the underlying source. Offline.

    Returns `(url, was_unwrapped)`. The specification requires the underlying
    source to be scored rather than the pipe that carried it, and every
    mechanism used here is contained in the URL itself - a query parameter or a
    base64 blob - so no network request is made. That keeps scoring
    reproducible: the same CSV scores the same way on a developer's machine, in
    CI, and on a server with no outbound access.
    """
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        return raw, False

    try:
        parsed = urlparse(raw)
    except ValueError:
        return raw, False

    host = _registrable(parsed.netloc)

    # Any redirector that names its destination in the query string.
    query = parse_qs(parsed.query or "")
    for key in _URL_IN_QUERY_KEYS:
        for candidate in query.get(key, []):
            target = unquote(candidate or "").strip()
            if target.startswith(("http://", "https://")) and _registrable(
                    urlparse(target).netloc) != host:
                return target, True

    if any(host == h or host.endswith("." + h) for h in _GOOGLE_NEWS_HOSTS):
        decoded = _decode_google_news_path(parsed.path or "")
        if decoded:
            return decoded, True

    return raw, False


def source_reliability_points(
    url: str = "",
    publisher: str = "",
    dataset: str = "",
    company_name: str = "",
) -> tuple[int | None, str, str]:
    """Points for how well the source can be verified.

    Returns `(points, basis, resolved_url)`. `points` is None when the source is
    real but unclassified - the caller decides whether to ask the model or fall
    back - which is deliberately different from 0, meaning there is no usable
    source at all.

    Order matters. An unwrapped URL is the best evidence, because it names the
    destination directly. Failing that the publisher NAME is used, because on
    real Google News data the URL is an opaque redirect that identifies nothing
    while the publisher column names the outlet exactly. Only when neither
    settles it does the raw URL's own domain decide, and for an aggregator link
    that means scoring the pipe - which is the honest answer once nothing better
    is available.
    """
    resolved, unwrapped = resolve_source_url(url)
    via = " (unwrapped from the aggregator link)" if unwrapped else ""

    if not resolved:
        # No URL at all. The publisher name can still identify the source; a
        # structured provider record carries usable provenance without either.
        named, named_basis = _publisher_band(publisher, company_name)
        if named is not UNKNOWN:
            return named, named_basis + ", named without a URL", ""
        if dataset in STRUCTURED_PROVIDER_DATASETS:
            return (STRUCTURED_THIRD_PARTY,
                    "structured provider record with no underlying source URL",
                    "")
        if publisher.strip():
            return UNKNOWN, "publisher named but no URL to verify it", ""
        return UNVERIFIABLE, "no source URL or publisher", ""

    # A URL that stayed wrapped identifies nothing, so let the publisher name
    # speak before the aggregator's own domain does.
    if not unwrapped:
        host_now = _registrable(urlparse(resolved).netloc)
        if _domain_matches(host_now, AGGREGATOR_DOMAINS):
            named, named_basis = _publisher_band(publisher, company_name)
            if named is not UNKNOWN:
                return named, named_basis + ", via an aggregator link", resolved
            if publisher.strip():
                # The outlet is named but unrecognised. That is not band 3,
                # which the specification reserves for evidence whose origin
                # "cannot clearly be established" - here it can, we simply have
                # no standing for that outlet. Left unclassified so the caller
                # applies its own fallback rather than penalising a regional
                # publisher for being absent from the table.
                return (UNKNOWN,
                        "unrecognised publisher '%s' behind an aggregator link"
                        % publisher.strip()[:60], resolved)

    parsed = urlparse(resolved)
    host = _registrable(parsed.netloc)
    path = (parsed.path or "").lower()

    if not host:
        return UNVERIFIABLE, "source URL carries no host", resolved

    # Regulators, exchanges and government first: an exchange filing is
    # authoritative regardless of the path it sits on.
    if _domain_matches(host, AUTHORITATIVE_DOMAINS) or host.endswith(
            AUTHORITATIVE_DOMAIN_SUFFIXES):
        return FIRST_PARTY, "regulatory, exchange or government source" + via, resolved

    # An aggregator that could not be unwrapped is the pipe, not the source.
    if _domain_matches(host, AGGREGATOR_DOMAINS):
        return WEAK_SECONDARY, "aggregator or syndicated release" + via, resolved

    if _domain_matches(host, ESTABLISHED_PUBLISHERS):
        return ESTABLISHED_REPORTING, "established publication" + via, resolved

    # A company's own newsroom, IR page or careers page. Checked after the
    # publisher list so a newspaper's own /press-release section is still scored
    # as reporting rather than as first-party evidence about the account.
    if any(marker in path for marker in FIRST_PARTY_PATH_MARKERS):
        return FIRST_PARTY, "first-party company page" + via, resolved

    return UNKNOWN, "unrecognised domain '%s'" % host, resolved


# ==============================================================================
# The composite. Python owns it; the model is never asked for a total.
# ==============================================================================

# ==============================================================================
# Publishing rules. NOT from the specification - it defines neither a tier nor a
# floor - so these are delivery decisions, kept deliberately:
#
#   the tier renders as a badge on every signal card, and
#   the floor is what keeps a signal with no date and no traceable source off
#   the dashboard, which the specification would otherwise allow at 5.0/10.
#
# They live in the same config section as the weights so they are retunable
# together, and they are declared here rather than in `recent_news_signals.py`
# so the whole scoring contract is in one module.
# ==============================================================================

TIER_THRESHOLDS = _scoring.bands("live_signal", "tier_thresholds")
MIN_CONFIDENCE_TO_PUBLISH = _CFG["min_confidence_to_publish"]
MAX_SIGNALS = _CFG["max_signals"]
DEDUP_SIMILARITY = _CFG["dedup_similarity"]


def composite(recency: float, relevance_impact: float, source_reliability: float) -> float:
    """The weighted total, out of 10, rounded once for display.

    Rounding once here and publishing exactly this number keeps the figure on
    screen consistent with the contributions shown beside it - the defect the
    urgency score had to solve the same way.
    """
    total = (float(recency) * WEIGHTS["recency"]
             + float(relevance_impact) * WEIGHTS["relevance_impact"]
             + float(source_reliability) * WEIGHTS["source_reliability"])
    return round(total, 2)


def version_stamp() -> str:
    """The scoring config this module is currently running.

    Recorded on every widget it scores. A startup sweep compares the stamp
    against the live config and regenerates what no longer matches - the
    mechanism that makes an edit to `config/scoring.yaml` actually reach the
    dashboard.
    """
    return _scoring.version("live_signal")
