"""Tests for the Evidence Strength score.

The two worked examples below were supplied with the formula, and they are the
contract: if either stops producing its stated total, the score shown on a
catalyst card no longer means what the people who specified it agreed it means.
They are pinned first for that reason.

The rest pin the decisions the formula did not state and this implementation had
to make - the fiscal year end, the frozen scoring date, and what happens to a
source whose category cannot be established. Each is a constant or a branch that
someone will eventually want to change; these tests are what tells them what
else moves when they do.

Run: python -m pytest tests/test_evidence_strength.py -v
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import evidence_strength as es  # noqa: E402


DOMAIN = "astra.co.id"
SCORED_ON = date(2026, 9, 15)


def filing(label, period="FY2025"):
    return {"dataset": "compliance_filings", "filing_label": label,
            "filing_period": period}


def news(publisher, period, url="https://news.google.com/rss/articles/x"):
    return {"dataset": "google_news", "publisher": publisher,
            "source_url": url, "period": period}


def job(url="https://career.astra.co.id/lowongan/1", period="2026-05-01"):
    return {"dataset": "job_openings", "source_url": url, "period": period}


# ---------------------------------------------------------------------------
# The supplied worked examples
# ---------------------------------------------------------------------------

def test_worked_example_one_scores_65():
    """Two filings (10) + within 12 months (25) + three categories (30) = 65."""
    sources = [
        filing("2025-Astra-Annual-Report.pdf", "FY2025"),
        filing("Astra-Annual-Report-2024.pdf", "FY2024"),
        news("IDNFinancials", "2026-06-22"),
        job(),
    ]
    result = es.score(sources, SCORED_ON, DOMAIN)
    assert result["score"] == 65
    assert result["max_score"] == 100
    points = {t["key"]: t["points"] for t in result["terms"]}
    assert points == {"filing_evidence": 10, "recency": 25,
                      "source_diversity": 30}


def test_worked_example_two_scores_55():
    """Two filings (10) + within 12 months (25) + two categories (20) = 55."""
    sources = [
        filing("2025-Astra-Annual-Report.pdf", "FY2025"),
        filing("Astra-Annual-Report-2024.pdf", "FY2024"),
        news("Reuters", "2026-06-01"),
    ]
    result = es.score(sources, SCORED_ON, DOMAIN)
    assert result["score"] == 55
    points = {t["key"]: t["points"] for t in result["terms"]}
    assert points == {"filing_evidence": 10, "recency": 25,
                      "source_diversity": 20}


def test_three_terms_not_four():
    """The card draws one bar per term, and the formula has exactly three."""
    result = es.score([filing("A.pdf")], SCORED_ON, DOMAIN)
    assert [t["key"] for t in result["terms"]] == [
        "filing_evidence", "recency", "source_diversity"]


# ---------------------------------------------------------------------------
# Filing evidence: a filing is a document, not a claim
# ---------------------------------------------------------------------------

def test_many_claims_from_one_filing_count_once():
    """Eight sentences from one annual report are one filing, not eight.

    This is the distinction the worked example turns on - "two relevant
    filings: 10" - and the one the old `support_count` measure could not make.
    """
    sources = [filing("2025-Astra-Annual-Report.pdf") for _ in range(8)]
    assert es.filing_evidence(sources)["points"] == 5
    assert es.filing_evidence(sources)["filing_count"] == 1


def test_filing_points_are_capped_at_25():
    sources = [filing("report-%d.pdf" % n) for n in range(9)]
    term = es.filing_evidence(sources)
    assert term["filing_count"] == 9
    assert term["points"] == 25


def test_sources_with_no_filing_label_score_nothing():
    assert es.filing_evidence([news("Reuters", "2026-01-01"), job()])["points"] == 0


# ---------------------------------------------------------------------------
# Recency: the bands, and the two conventions
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("period, expected", [
    ("2026-06-22", 25),   # 2 months
    ("FY2025", 25),       # 8 months
    ("FY2024", 20),       # 20 months
    ("FY2023", 15),       # 32 months
    ("FY2021", 10),       # 56 months
    ("FY2019", 5),        # 80 months
])
def test_recency_bands(period, expected):
    assert es.recency([{"period": period}], SCORED_ON)["points"] == expected


def test_undated_evidence_scores_zero_rather_than_being_guessed():
    term = es.recency([{"period": "sometime in 2025"}], SCORED_ON)
    assert term["points"] == 0
    assert term["most_recent_date"] is None
    assert term["undated_sources"] == 1


def test_the_most_recent_source_sets_the_age():
    """A catalyst evidenced by a 2026 news item is current, whatever else it cites.

    The undated and the ancient sources travel with it and are counted, but they
    do not drag the band down: the question the term asks is whether there is
    recent evidence, not whether all of it is recent.
    """
    sources = [filing("old.pdf", "FY2019"), {"period": "no date here"},
               news("IDNFinancials", "2026-08-01")]
    term = es.recency(sources, SCORED_ON)
    assert term["points"] == 25
    assert term["most_recent_date"] == "2026-08-01"
    assert term["undated_sources"] == 1


def test_fiscal_year_is_taken_at_its_end_not_its_start():
    """FY2025 means 31 December 2025, which is the convention Astra files on.

    Taking it at 1 January instead would age every filing by a further eleven
    months and push FY2025 out of the top band, so this is not a detail. An
    account whose fiscal year ends in another month changes FISCAL_YEAR_END.
    """
    assert es.parse_period("FY2025") == date(2025, 12, 31)
    assert es.parse_period("2025") == date(2025, 12, 31)


def test_month_period_is_taken_at_its_last_day():
    assert es.parse_period("2026-Jul") == date(2026, 7, 31)
    assert es.parse_period("2026-Feb") == date(2026, 2, 28)
    assert es.parse_period("2026-Dec") == date(2026, 12, 31)


def test_evidence_dated_after_the_scoring_date_is_not_negatively_aged():
    """A filing reporting a year that has not ended yet is current, not -3 months."""
    term = es.recency([{"period": "FY2026"}], SCORED_ON)
    assert term["age_months"] == 0
    assert term["points"] == 25


def test_the_score_does_not_drift_with_the_calendar():
    """The same evidence scores the same whenever it is read.

    Age is measured to the date the widget was generated, which is published
    alongside. Measuring to "now" instead would silently drop a catalyst from 25
    to 20 overnight with nothing in the account having changed.
    """
    sources = [filing("A.pdf", "FY2025"), news("Reuters", "2026-06-01")]
    first = es.score(sources, date(2026, 9, 15), DOMAIN)
    later = es.score(sources, date(2026, 9, 15), DOMAIN)
    assert first["score"] == later["score"]
    assert first["scored_on"] == "2026-09-15"

    # A year later, generated afresh, it genuinely is older.
    aged = es.score(sources, date(2027, 9, 15), DOMAIN)
    assert aged["score"] < first["score"]


# ---------------------------------------------------------------------------
# Source diversity: categories, and what refuses to be one
# ---------------------------------------------------------------------------

def test_a_filing_needs_no_url_to_be_a_regulatory_filing():
    """The dataset key carries what a URL would otherwise have to prove.

    Filings are registered with a page and a filename and never a link, so
    requiring a URL here would score the corpus's most reliable evidence at
    nothing.
    """
    assert es.categorise(filing("AR.pdf"), DOMAIN) == es.REGULATORY_FILINGS


def test_company_careers_page_and_newsroom_are_one_category():
    """The rule as specified: both are the company speaking, so both count once."""
    careers = job("https://career.astra.co.id/lowongan/1")
    newsroom = {"dataset": "google_news",
                "source_url": "https://www.astra.co.id/news/pr-2026"}
    assert es.categorise(careers, DOMAIN) == es.OFFICIAL_COMPANY
    assert es.categorise(newsroom, DOMAIN) == es.OFFICIAL_COMPANY
    assert es.diversity([careers, newsroom], DOMAIN)["points"] == 10


def test_google_news_links_fall_through_to_the_publisher():
    """Every news row in this corpus links through news.google.com.

    Categorising on that host would make twelve different outlets look like one
    source and collapse the term that is half the score, so an aggregator host
    is ignored and the publisher name decides.
    """
    first = news("IDNFinancials", "2026-06-01")
    second = news("Reuters", "2026-06-02")
    assert es.categorise(first, DOMAIN) == es.INDEPENDENT_MEDIA
    assert es.categorise(second, DOMAIN) == es.INDEPENDENT_MEDIA


def test_a_third_party_platform_establishes_no_category():
    """A LinkedIn posting is not the company's own site and not a publication."""
    assert es.categorise(job("https://www.linkedin.com/jobs/view/1"),
                         DOMAIN) == es.UNCATEGORISED


def test_a_source_with_nothing_to_go_on_is_counted_not_guessed():
    """news_events carries no URL and no publisher, so it names no category.

    It is counted in `uncategorised_sources` so the payload can say how much
    evidence could not be categorised, rather than quietly scoring it as media.
    """
    result = es.diversity([{"dataset": "news_events"}], DOMAIN)
    assert result["points"] == 0
    assert result["categories"] == []
    assert result["uncategorised_sources"] == 1


def test_regulator_and_government_hosts_are_distinguished():
    idx = {"dataset": "x", "source_url": "https://www.idx.co.id/listed/z"}
    bps = {"dataset": "x", "source_url": "https://www.bps.go.id/statistics"}
    assert es.categorise(idx, DOMAIN) == es.REGULATORY_FILINGS
    assert es.categorise(bps, DOMAIN) == es.GOVERNMENT


def test_diversity_is_capped_at_50_and_the_five_categories_reach_it():
    """Five categories at 10 points each is exactly the cap, so it is reachable."""
    sources = [
        filing("AR.pdf"),
        job("https://career.astra.co.id/1"),
        {"dataset": "x", "source_url": "https://investor.astra.co.id/fin"},
        {"dataset": "x", "source_url": "https://www.bps.go.id/q"},
        news("Reuters", "2026-01-01"),
    ]
    result = es.diversity(sources, DOMAIN)
    assert result["points"] == 50
    assert len(result["categories"]) == len(es.SOURCE_CATEGORIES)


def test_repeating_one_category_does_not_raise_the_score():
    """Ten news articles are one category. Diversity counts kinds, not sources."""
    sources = [news("Outlet %d" % n, "2026-01-01") for n in range(10)]
    assert es.diversity(sources, DOMAIN)["points"] == 10


# ---------------------------------------------------------------------------
# The whole score
# ---------------------------------------------------------------------------

def test_a_catalyst_with_no_evidence_scores_zero():
    result = es.score([], SCORED_ON, DOMAIN)
    assert result["score"] == 0
    assert all(t["points"] == 0 for t in result["terms"])


def test_every_term_publishes_the_count_it_was_computed_from():
    """A reader who disagrees with 65/100 has to be able to see which term to blame."""
    result = es.score([filing("A.pdf"), news("Reuters", "2026-06-01")],
                      SCORED_ON, DOMAIN)
    by_key = {t["key"]: t for t in result["terms"]}
    assert by_key["filing_evidence"]["filing_count"] == 1
    assert by_key["recency"]["age_months"] == 3
    assert by_key["source_diversity"]["category_counts"] == {
        es.REGULATORY_FILINGS: 1, es.INDEPENDENT_MEDIA: 1}
    assert all(t["basis"] for t in result["terms"])


def test_the_score_is_the_sum_of_its_three_terms():
    """No rounding, no weighting, no fourth term hiding in the total."""
    sources = [filing("A.pdf"), filing("B.pdf"), news("Reuters", "2026-06-01"),
               job()]
    result = es.score(sources, SCORED_ON, DOMAIN)
    assert result["score"] == sum(t["points"] for t in result["terms"])
    assert result["score"] <= es.MAX_SCORE


# ---------------------------------------------------------------------------
# The other 219 accounts
#
# Everything above was written against one Indonesian account. These pin the
# behaviour on the markets, domain shapes and malformed vendor data the rest of
# the platform will bring, each of which was a real defect when first tested.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://www.idx.co.id/listed/x",           # Indonesia
    "https://www.sec.gov/Archives/y",           # United States
    "https://www.sgx.com/securities/z",         # Singapore
    "https://www.bseindia.com/corporates/a",    # India
    "https://www.nseindia.com/b",
    "https://disclosure.edinet-fsa.go.jp/c",    # Japan
    "https://www.bundesanzeiger.de/d",          # Germany
    "https://www.hkex.com.hk/e",                # Hong Kong
    "https://www.asx.com.au/f",                 # Australia
])
def test_exchanges_and_regulators_are_regulatory_filings(url):
    """Only `idx.co.id` and `sec.gov` were listed at first.

    Every other market's regulator fell through to Independent Media, which put
    an exchange disclosure in the same category as a newspaper and quietly
    changed the diversity score of every non-Indonesian account.
    """
    assert es.categorise({"dataset": "x", "source_url": url},
                         DOMAIN) == es.REGULATORY_FILINGS


@pytest.mark.parametrize("url", [
    "https://www.bps.go.id/statistics",   # suffix form
    "https://www.gov.uk/filing",          # label form, host IS gov.uk
    "https://www.gov.sg/programme",
    "https://www.sebi.gov.in/legal",      # label in the middle
    "https://data.gov.au/dataset",
])
def test_government_hosts_are_recognised_wherever_gov_sits(url):
    """`.gov` as a suffix misses `gov.uk` and `sebi.gov.in` entirely.

    The world does not agree on where the government label goes, so the host's
    own segments are read rather than only its tail.
    """
    assert es.categorise({"dataset": "x", "source_url": url},
                         DOMAIN) == es.GOVERNMENT


@pytest.mark.parametrize("url", [
    "https://gov-solutions.com/x",
    "https://government-news.com/x",
    "https://mygov.private.com/x",
])
def test_a_company_with_gov_in_its_name_is_not_a_government(url):
    assert es.categorise({"dataset": "x", "source_url": url},
                         DOMAIN) != es.GOVERNMENT


def test_a_companys_country_domain_is_still_its_own_site():
    """Firmographics records one domain; the careers site often sits on another.

    `tesco.co.uk` against a recorded `tesco.com` is the same company, and
    reading its own job postings as independent media would credit the account
    with a category it has not got.
    """
    careers = job("https://careers.tesco.co.uk/jobs/1")
    assert es.categorise(careers, "tesco.com") == es.OFFICIAL_COMPANY
    assert es.categorise(job("https://jobs.apple.com/en-us/details/1"),
                         "apple.com") == es.OFFICIAL_COMPANY


def test_an_unrelated_company_is_not_the_account():
    assert es.categorise({"dataset": "x", "source_url": "https://www.reuters.com/a"},
                         "apple.com") == es.INDEPENDENT_MEDIA


def test_a_lookalike_host_does_not_borrow_a_category():
    """Suffix matching alone would read this as the Indonesian exchange."""
    assert es.categorise(
        {"dataset": "x", "source_url": "https://notidx.co.id.evil.com/x"},
        DOMAIN) == es.INDEPENDENT_MEDIA


@pytest.mark.parametrize("url", [
    "not a url", "javascript:alert(1)", "mailto:someone@example.com",
    "https://", "", None,
])
def test_a_string_that_is_not_a_url_scores_no_category(url):
    """Vendor exports carry these. A sentence is not a publication.

    Before the host was validated, every one of these was read as an
    independent media source and silently added 10 points.
    """
    assert es.categorise({"dataset": "x", "source_url": url},
                         DOMAIN) == es.UNCATEGORISED


def test_without_an_account_domain_a_website_names_no_category():
    """An account whose firmographics row has no domain.

    With nothing to compare against, the account's own newsroom and a newspaper
    are indistinguishable, so neither is claimed rather than guessing.
    """
    source = {"dataset": "x", "source_url": "https://www.example.com/news"}
    assert es.categorise(source, "") == es.UNCATEGORISED
    assert es.categorise(source, None) == es.UNCATEGORISED


@pytest.mark.parametrize("domain", [
    "ASTRA.CO.ID", "https://www.astra.co.id/", "  astra.co.id  ", "www.astra.co.id",
])
def test_the_account_domain_is_normalised_before_comparison(domain):
    """220 firmographics rows will not agree on how to write a domain."""
    assert es.categorise(job("https://career.astra.co.id/1"),
                         domain) == es.OFFICIAL_COMPANY


@pytest.mark.parametrize("period, expected", [
    ("FY2025", "2025-12-31"),
    ("FY2025/26", "2025-12-31"),      # UK / India span, first year wins
    ("FY2025-26", "2025-12-31"),
    ("2025", "2025-12-31"),
    ("FY2026 total", "2026-12-31"),
    ("2026-Jul", "2026-07-31"),
    ("2026-06-22", "2026-06-22"),
])
def test_the_period_shapes_other_markets_produce(period, expected):
    assert es.parse_period(period).isoformat() == expected


@pytest.mark.parametrize("period", [
    "FY0000", "0000", "FY9999", "FY25", "Q3 2026", "31 March 2025",
    "2025-13", "2025-06", "", "   ", None, "unknown",
])
def test_an_unparseable_period_returns_none_and_never_raises(period):
    """`FY0000` raised ValueError from `date()` and abandoned the whole widget.

    A period this code cannot read is a zero for recency, which is the honest
    answer and what the formula already specifies for undated evidence. It must
    never be an exception, and it must never become a confident wrong date -
    `2025-13` is a malformed month, not the 2025 fiscal year.
    """
    assert es.parse_period(period) is None


def test_scoring_never_raises_on_hostile_input():
    """One malformed row must not cost an account its dashboard."""
    sources = [
        {"dataset": None, "filing_label": None, "source_url": None,
         "period": None, "publisher": None},
        {"source_url": 12345, "period": ["not", "a", "string"]},
        {"filing_label": "", "period": "FY0000"},
        {},
    ]
    result = es.score(sources, SCORED_ON, DOMAIN)
    assert result["score"] == 0
    assert result["max_score"] == 100
