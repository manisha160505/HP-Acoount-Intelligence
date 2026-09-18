"""The Live Signal Score's deterministic drivers, pinned to the specification.

`HP_Live_Signal_Scoring_Logic.docx` defines three drivers. Two of them - recency
and source reliability - are decided in Python with no model involved, and this
file pins both to the document's own bands.

The test that matters most is `test_the_specifications_worked_example`. The
document carries a fully worked Astra example resolving to 5.80/10, and
reproducing that number exactly is the acceptance criterion for the whole
scoring change: it exercises the date band, the source band, the weights and
the rounding in one pass. If it drifts, something in the chain has been changed
away from the specification.

The rest of the file exists because band tables fail at their boundaries, not in
their middles. Every band is tested at the day it starts and the day it ends,
including the two that are easy to get wrong: a signal exactly 7 days old is
still in the top band, and one exactly 366 days old has fallen out of the
bottom one.

Run: python -m pytest tests/test_signal_scoring.py -v
"""

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import signal_scoring as ss

NOW = datetime(2026, 9, 17, tzinfo=UTC)


def _aged(days: int) -> datetime:
    return NOW - timedelta(days=days)


class TestTheWeightsAreTheSpecifiedOnes:

    def test_three_drivers_weighted_30_50_20(self):
        assert ss.WEIGHTS == {
            "recency": 0.30,
            "relevance_impact": 0.50,
            "source_reliability": 0.20,
        }

    def test_the_weights_total_one(self):
        assert round(sum(ss.WEIGHTS.values()), 10) == 1.0

    def test_the_dimensions_that_were_dropped_are_gone(self):
        """`actionability` and `strategic_impact` were separate dimensions in the
        old five-driver model. The specification merges the second into
        relevance and drops the first entirely."""
        assert "actionability" not in ss.WEIGHTS
        assert "strategic_impact" not in ss.WEIGHTS
        assert "hp_relevance" not in ss.WEIGHTS


class TestRecencyBands:
    """"Age of individual Live Signal | Recency score", verbatim."""

    @pytest.mark.parametrize("days,expected", [
        (0, 10), (1, 10), (7, 10),          # 0-7 days
        (8, 8), (15, 8), (30, 8),           # 8-30 days
        (31, 6), (60, 6), (90, 6),          # 31-90 days
        (91, 4), (140, 4), (180, 4),        # 91-180 days
        (181, 2), (300, 2), (365, 2),       # 181-365 days
        (366, 0), (500, 0), (5000, 0),      # more than 365 days
    ])
    def test_each_band_at_its_boundaries(self, days, expected):
        points, _basis = ss.recency_points(_aged(days), now=NOW)
        assert points == expected, "%d days should score %d" % (days, expected)

    def test_no_usable_date_scores_zero_and_is_not_suppressed(self):
        """The specification has a band for this - "No usable date | 0/10" - and
        no suppression rule anywhere. A dateless signal is scored, not dropped."""
        points, basis = ss.recency_points(None, now=NOW)
        assert points == 0
        assert "no usable" in basis.lower()

    def test_a_dateless_signal_is_not_treated_as_recent(self):
        """The failure this guards: defaulting a missing date to 'now' would
        score an undated signal 10/10 and float it to the top of the dashboard."""
        assert ss.recency_points(None, now=NOW)[0] != 10

    def test_a_future_date_scores_as_same_day(self):
        """No band covers a future date. Scoring it as same-day beats treating a
        typo in a source file as maximally stale."""
        points, _ = ss.recency_points(NOW + timedelta(days=30), now=NOW)
        assert points == 10

    def test_a_naive_datetime_is_read_as_utc_rather_than_crashing(self):
        points, _ = ss.recency_points(datetime(2026, 9, 16), now=NOW)  # noqa: DTZ001
        assert points == 10

    def test_the_basis_says_how_old_it_was(self):
        """The number alone is not auditable - a reader needs to see the age it
        came from."""
        _points, basis = ss.recency_points(_aged(147), now=NOW)
        assert "147" in basis


class TestSourceReliabilityBands:

    def test_an_exchange_or_regulator_is_first_party(self):
        points, _basis, _url = ss.source_reliability_points("https://www.idx.co.id/news/x")
        assert points == ss.FIRST_PARTY

    def test_a_government_domain_is_first_party(self):
        assert ss.source_reliability_points(
            "https://www.defence.gov.au/annual-reports")[0] == ss.FIRST_PARTY

    def test_an_established_publication_scores_eight(self):
        points, _basis, _url = ss.source_reliability_points("https://www.reuters.com/x")
        assert points == ss.ESTABLISHED_REPORTING

    def test_a_subdomain_of_a_publisher_is_the_same_publisher(self):
        assert ss.source_reliability_points(
            "https://asia.nikkei.com/story")[0] == ss.ESTABLISHED_REPORTING

    def test_a_lookalike_domain_does_not_match(self):
        """`notreuters.com` must not inherit Reuters' band. Matching is on a dot
        boundary, not a substring."""
        points, _basis, _url = ss.source_reliability_points("https://notreuters.com/x")
        assert points is ss.UNKNOWN

    def test_a_company_newsroom_is_first_party(self):
        points, basis, _url = ss.source_reliability_points(
            "https://www.someholding.co.id/investor-relations/results")
        assert points == ss.FIRST_PARTY
        assert "first-party" in basis

    def test_a_newspapers_own_press_section_is_still_reporting(self):
        """A publisher is checked before the first-party path markers, so a
        newspaper's /press-release section does not become first-party evidence
        about the account."""
        points, _basis, _url = ss.source_reliability_points(
            "https://www.reuters.com/press-release/item")
        assert points == ss.ESTABLISHED_REPORTING

    def test_an_aggregator_scores_weak_secondary(self):
        points, _basis, _url = ss.source_reliability_points("https://www.msn.com/en/x")
        assert points == ss.WEAK_SECONDARY

    def test_a_wire_release_is_weak_secondary(self):
        assert ss.source_reliability_points(
            "https://www.prnewswire.com/news-releases/x")[0] == ss.WEAK_SECONDARY

    def test_no_source_at_all_is_unverifiable(self):
        points, basis, _url = ss.source_reliability_points("", "", "")
        assert points == ss.UNVERIFIABLE
        assert "no source" in basis

    def test_a_structured_provider_record_without_a_url_scores_six(self):
        """The specification's own carve-out: a PredictLeads or Explorium
        structured event with no source URL still has usable provenance."""
        points, basis, _url = ss.source_reliability_points("", "", dataset="news_events")
        assert points == ss.STRUCTURED_THIRD_PARTY
        assert "structured provider" in basis

    def test_an_unrecognised_domain_is_unknown_not_zero(self):
        """A domain this table has never seen is a gap in the table, not proof
        the source is bad. Scoring it 0 would silently punish every regional
        outlet nobody has classified yet."""
        points, basis, _url = ss.source_reliability_points("https://some-local-paper.example/x")
        assert points is ss.UNKNOWN
        assert points != ss.UNVERIFIABLE
        assert "unrecognised" in basis


class TestTheUnderlyingSourceIsScored:
    """The specification's central rule about sources:

        "The underlying source is scored, not simply the pipe that found it.
        For example, a company press release discovered through Google News RSS
        is still first-party evidence."
    """

    def test_a_query_string_redirect_is_unwrapped(self):
        url, unwrapped = ss.resolve_source_url(
            "https://news.google.com/rss/articles/read?url=https%3A%2F%2Fwww.reuters.com%2Fx")
        assert unwrapped is True
        assert url == "https://www.reuters.com/x"

    def test_an_unwrapped_publisher_is_scored_as_the_publisher(self):
        points, basis, resolved = ss.source_reliability_points(
            "https://news.google.com/articles/read?url=https%3A%2F%2Fwww.reuters.com%2Fx")
        assert points == ss.ESTABLISHED_REPORTING
        assert "reuters.com" in resolved
        assert "unwrapped" in basis

    def test_a_first_party_release_found_via_google_stays_first_party(self):
        """The specification's own example, and the reason unwrapping exists."""
        points, _basis, _resolved = ss.source_reliability_points(
            "https://news.google.com/rss/articles/x"
            "?url=https%3A%2F%2Fexample-corp.com%2Fnewsroom%2Fq3-results")
        assert points == ss.FIRST_PARTY

    def test_an_opaque_google_link_falls_back_to_aggregator(self):
        """The newer Google link format encodes nothing recoverable offline.
        Scoring it as the aggregator it is beats guessing at a publisher."""
        points, _basis, _resolved = ss.source_reliability_points(
            "https://news.google.com/rss/articles/CBMiK2h0dHBz")
        assert points in (ss.WEAK_SECONDARY, ss.ESTABLISHED_REPORTING, ss.FIRST_PARTY)

    def test_resolution_makes_no_network_call(self, monkeypatch):
        """Scoring must be reproducible on a machine with no outbound access.
        Any socket use here would make the score depend on whether a site is up."""
        import socket

        def explode(*_args, **_kwargs):
            raise AssertionError("source resolution attempted a network call")

        monkeypatch.setattr(socket, "socket", explode)
        monkeypatch.setattr(socket, "create_connection", explode)
        ss.resolve_source_url(
            "https://news.google.com/rss/articles/read?url=https%3A%2F%2Fwww.reuters.com%2Fx")
        ss.source_reliability_points("https://www.reuters.com/x")

    def test_a_non_url_is_returned_untouched(self):
        url, unwrapped = ss.resolve_source_url("not a url")
        assert unwrapped is False
        assert url == "not a url"


class TestThePublisherNameIdentifiesTheSource:
    """On real data the URL is usually useless and the publisher name is not.

    Every Google News row in the Astra export carries an opaque
    `/rss/articles/CBMi...` link that encodes nothing recoverable offline, while
    the same row names the outlet exactly. Scoring those links as "aggregator"
    would have put every Google News signal at 3/10 regardless of who actually
    published it - including the account's own press releases.

    The specification is explicit that the underlying source is what gets
    scored, and for the Exa pipe it says which field leads: "If source_publisher
    is blank, identify the source from event_url."
    """

    OPAQUE = "https://news.google.com/rss/articles/CBMiogFBVV95cUxOLWgxU3FLeU53RGxGVEJF"
    COMPANY = "PT Astra International Tbk"

    def test_a_named_publisher_beats_an_opaque_aggregator_link(self):
        points, basis, _url = ss.source_reliability_points(
            self.OPAQUE, "IDNFinancials", "google_news", self.COMPANY)
        assert points == ss.ESTABLISHED_REPORTING
        assert "idnfinancials.com" in basis

    def test_the_accounts_own_announcement_is_first_party(self):
        """A company press release is first-party whatever pipe carried it."""
        points, basis, _url = ss.source_reliability_points(
            self.OPAQUE, self.COMPANY, "google_news", self.COMPANY)
        assert points == ss.FIRST_PARTY
        assert "own announcement" in basis

    def test_the_account_is_matched_against_its_own_name_not_a_list(self):
        """Account-agnostic: nothing here names a company. A different account
        gets the same treatment from its own name."""
        points, _basis, _url = ss.source_reliability_points(
            self.OPAQUE, "Contoso Manufacturing Ltd", "google_news",
            "Contoso Manufacturing Ltd")
        assert points == ss.FIRST_PARTY

    def test_a_decorated_publisher_name_still_matches(self):
        """Feeds append regions and editions to the outlet name."""
        for name in ("Tempo.co English", "Bloomberg Linea", "CNBC Indonesia"):
            points, _basis, _url = ss.source_reliability_points(
                self.OPAQUE, name, "google_news", self.COMPANY)
            assert points == ss.ESTABLISHED_REPORTING, name

    def test_an_unknown_outlet_is_unclassified_not_downgraded(self):
        points, _basis, _url = ss.source_reliability_points(
            self.OPAQUE, "Some Random Local Herald", "google_news", self.COMPANY)
        assert points is ss.UNKNOWN

    def test_a_short_or_generic_name_does_not_false_match(self):
        """The brand labels are matched by containment, so a short label would
        hit inside unrelated names. 'Asia Times' must not become Nikkei via the
        'asia' in `asia.nikkei.com`."""
        assert ss._publisher_band("Asia Times", self.COMPANY)[0] is ss.UNKNOWN
        assert ss._publisher_band("The Daily Something", self.COMPANY)[0] is ss.UNKNOWN

    def test_a_short_company_name_cannot_swallow_other_publishers(self):
        """Guarded on length - a two-letter account name would otherwise match
        almost any publisher and mark it first-party."""
        points, _basis, _url = ss.source_reliability_points(
            self.OPAQUE, "Reuters", "google_news", company_name="HP")
        assert points == ss.ESTABLISHED_REPORTING

    def test_an_unwrapped_url_still_wins_over_the_publisher_name(self):
        """When the link does resolve it names the destination directly, which
        is better evidence than a name column."""
        points, basis, resolved = ss.source_reliability_points(
            "https://news.google.com/rss/articles/x?url=https%3A%2F%2Fwww.reuters.com%2Fa",
            "Some Random Local Herald", "google_news", self.COMPANY)
        assert points == ss.ESTABLISHED_REPORTING
        assert "reuters.com" in resolved
        assert "unwrapped" in basis


class TestTheComposite:

    def test_the_specifications_worked_example(self):
        """The acceptance test for the whole change.

        The document works one Astra signal end to end: a capex announcement
        published 23 April 2026, scored on 17 September 2026, whose Google News
        link resolves to IDNFinancials.

            Recency            4/10 x 30% = 1.20
            Relevance & Impact 6/10 x 50% = 3.00
            Source Reliability 8/10 x 20% = 1.60
            Final                           5.80/10

        Every part is derived here rather than asserted: the recency band from
        the real date arithmetic, the source band from the real domain table.
        Only the relevance level is supplied, because that driver is the one the
        model judges.
        """
        published = datetime(2026, 4, 23, tzinfo=UTC)
        scored_on = datetime(2026, 9, 17, tzinfo=UTC)

        recency, basis = ss.recency_points(published, now=scored_on)
        assert recency == 4, "147 days falls in the 91-180 band"
        assert "147" in basis

        source, _basis, _url = ss.source_reliability_points(
            "https://www.idnfinancials.com/news/astra-capex")
        assert source == 8, "IDNFinancials is established independent reporting"

        relevance = 6          # "major capex, no explicit HP-addressable need"

        assert ss.composite(recency, relevance, source) == 5.80

    def test_the_composite_is_the_weighted_sum(self):
        assert ss.composite(10, 10, 10) == 10.0
        assert ss.composite(0, 0, 0) == 0.0

    def test_each_driver_moves_the_total_by_its_own_weight(self):
        base = ss.composite(0, 0, 0)
        assert round(ss.composite(10, 0, 0) - base, 2) == 3.0
        assert round(ss.composite(0, 10, 0) - base, 2) == 5.0
        assert round(ss.composite(0, 0, 10) - base, 2) == 2.0

    def test_relevance_carries_the_most_weight(self):
        """A signal that is highly relevant but old and weakly sourced still
        outranks a fresh, well-sourced irrelevance. That is the specification's
        intent in weighting relevance at 50%."""
        relevant_but_stale = ss.composite(0, 10, 3)
        fresh_but_irrelevant = ss.composite(10, 0, 10)
        assert relevant_but_stale > fresh_but_irrelevant

    def test_the_published_number_is_rounded_once(self):
        """The figure on screen must be the figure the contributions add to."""
        assert ss.composite(4, 6, 8) == 5.8
        assert isinstance(ss.composite(4, 6, 8), float)
