"""No current signal about an account may disappear without saying so.

The client asked why Advantest showed 4 live signals in twelve months. The
answer was not the data and not the 365-day gate: 141 rows arrived, 72 were
correctly aged out, 65 distinct signals survived - and then all 65 went to
gpt-4o in one call. It returned valid JSON holding ten entries and stopped, and
the publish filter read "not in the answer" as "drop". On Accenture the same
thing lost 97 of 108.

Two rules come out of that, and this file holds them:

  1. the ask is batched, so the model can answer all of it
  2. a signal it still does not score is published, marked, never dropped

Run: python -m pytest tests/test_signal_batching.py -v
"""

import os
import sys
from datetime import UTC, datetime
from typing import ClassVar

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import recent_news_signals as rns, signal_scoring as ss

NOW = datetime(2026, 9, 27, tzinfo=UTC)


def _signals(n):
    return [{"signal_id": "sig%02d" % i,
             "event_date": "2026-09-%02d" % ((i % 27) + 1),
             "category": "partnership",
             "source_publisher": "Nikkei",
             "headline": "Headline %d" % i,
             "evidence_sentence": "Evidence sentence %d." % i}
            for i in range(n)]


class _Model:
    """Stands in for gpt-4o. Answers at most `cap` entries per call, which is
    exactly what the real one does when the ask is too large."""

    def __init__(self, cap=99, skip=()):
        self.cap = cap
        self.skip = set(skip)
        self.calls = []

    def __call__(self, _system, user):
        # The roster is in the system prompt; the ids asked for are parsed back
        # out of it so the fake behaves like the real call.
        ids = [line.split("id=")[1].split(" |")[0]
               for line in _system.splitlines() if line.startswith("- id=")]
        self.calls.append(ids)
        out = [{"signal_id": i, "gate_pass": True,
                "scores": {"relevance_impact": {"score": 6, "rationale": "r"}},
                "sales_angle": "angle", "event_status": "announced"}
               for i in ids if i not in self.skip][:self.cap]
        return {"signals": out}


class TestTheAskIsBatched:

    def test_sixty_five_signals_are_not_sent_in_one_call(self, monkeypatch):
        model = _Model()
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", model)
        rns._score_batches(_signals(65), "ACME", "", NOW)
        assert len(model.calls) == 9, "65 signals in batches of 8"
        assert max(len(c) for c in model.calls) <= rns.SCORING_BATCH_SIZE

    def test_every_signal_comes_back(self, monkeypatch):
        model = _Model()
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", model)
        entries = rns._score_batches(_signals(65), "ACME", "", NOW)
        assert len({e["signal_id"] for e in entries}) == 65

    def test_a_model_that_answers_only_ten_still_loses_nothing(self, monkeypatch):
        """The real failure: a cap on entries per reply. Batching keeps every
        ask under it."""
        model = _Model(cap=10)
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", model)
        entries = rns._score_batches(_signals(108), "ACME", "", NOW)
        assert len(entries) == 108

    def test_a_skipped_id_is_retried(self, monkeypatch):
        model = _Model(skip={"sig03"})
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", model)
        rns._score_batches(_signals(16), "ACME", "", NOW)
        retried = [c for c in model.calls if "sig03" in c]
        assert len(retried) == 2, "asked once in its batch, once on the retry"

    def test_one_batch_when_there_are_few_signals(self, monkeypatch):
        model = _Model()
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion", model)
        rns._score_batches(_signals(5), "ACME", "", NOW)
        assert len(model.calls) == 1

    def test_a_dead_model_returns_nothing_rather_than_raising(self, monkeypatch):
        monkeypatch.setattr(rns, "generate_gpt4o_json_completion",
                            lambda *_a, **_k: None)
        assert rns._score_batches(_signals(12), "ACME", "", NOW) == []


class TestTheRecencyBasis:

    def test_it_names_the_date(self):
        _points, basis = ss.recency_points(datetime(2026, 9, 15, tzinfo=UTC), NOW)
        assert basis == "event dated 15 Sep 2026"

    def test_it_never_says_days_old(self):
        """Frozen at extraction, that string is wrong by the time anyone reads
        it."""
        for age in (1, 11, 100, 400):
            when = datetime(2026, 9, 27, tzinfo=UTC).replace(
                year=2026 - (1 if age > 300 else 0))
            _points, basis = ss.recency_points(when, NOW)
            assert "days old" not in basis

    def test_an_undated_signal_still_says_so(self):
        points, basis = ss.recency_points(None, NOW)
        assert points == ss.RECENCY_NO_DATE
        assert "no usable event or publication date" in basis


class TestTheSourceClassification:
    """Two vocabularies for one ladder, and neither one moves a score.

    The classification names come from the Source classification column of
    HP_Live_Signal_Scoring_Logic, verbatim, and are what `classification_for`
    returns to everything else. The T0-T3 tiers come from the client's 27 Sep
    message - "T0 = SEC / stock exchange filings, company press release engine,
    T1 = established news channels, T2 = paid licensed tools, T3 = long tail" -
    and they now lead the line on the card, because the classification alone
    was still not the vocabulary they read in.

    An earlier pass declined to print the tiers on the grounds that they were
    not in the scoring document. They were asked for directly on 30 Sep. What
    matters is that this stayed a relabelling: the points are the ones
    scoring.yaml supplies, unchanged, so no signal moved position."""

    def test_each_band_carries_the_document_s_own_name(self):
        for points, name in (
                (ss.FIRST_PARTY, "First-party or authoritative"),
                (ss.ESTABLISHED_REPORTING, "Established independent reporting"),
                (ss.STRUCTURED_THIRD_PARTY, "Structured third-party evidence"),
                (ss.WEAK_SECONDARY, "Weak secondary evidence"),
                (ss.UNVERIFIABLE, "Unverifiable")):
            assert ss.classification_for(points) == name

    def test_each_band_carries_the_clients_own_tier(self):
        """Their mapping, not ours: filings, established news, paid tools,
        long tail."""
        assert ss.tier_for(ss.FIRST_PARTY) == "T0"
        assert ss.tier_for(ss.ESTABLISHED_REPORTING) == "T1"
        assert ss.tier_for(ss.STRUCTURED_THIRD_PARTY) == "T2"
        assert ss.tier_for(ss.WEAK_SECONDARY) == "T3"

    def test_unverifiable_claims_no_tier(self):
        """Their list defines four. A source that cannot be established at all
        is the one with no tier to claim, and a T4 would be us extending a
        scale they wrote."""
        assert ss.tier_for(ss.UNVERIFIABLE) == ""
        line = ss.describe_source(ss.UNVERIFIABLE, "no source URL or publisher", "")
        assert line == "Unverifiable"

    def test_relabelling_did_not_become_rescoring(self):
        """The test that says what this change was allowed to touch.

        The points are the client's, from scoring.yaml, and naming a band must
        never move one. If this fails, a display change has reached the
        score."""
        assert (ss.FIRST_PARTY, ss.ESTABLISHED_REPORTING,
                ss.STRUCTURED_THIRD_PARTY, ss.WEAK_SECONDARY,
                ss.UNVERIFIABLE) == (10, 8, 6, 3, 0)
        assert sorted(ss.SOURCE_TIERS) == [3, 6, 8, 10]
        assert set(ss.SOURCE_CLASSIFICATIONS) == {10, 8, 6, 3, 0}

    def test_the_line_leads_with_the_tier_and_names_the_publisher(self):
        """The format put to the client on 29 Sep. The band alone says nothing
        about this signal; the publisher was on the card and never in the
        explanation."""
        line = ss.describe_source(ss.ESTABLISHED_REPORTING,
                                  "established publication", "Nikkei")
        assert line == "T1 - Established news: Nikkei"

    def test_no_basis_reaches_the_line_whatever_it_says(self):
        line = ss.describe_source(ss.ESTABLISHED_REPORTING,
                                  "established publication (reuters.com)", "Reuters")
        assert line == "T1 - Established news: Reuters"

    def test_the_definition_is_never_printed(self):
        """Sahaj, 28 Sep: "only show the part written in classification n not
        definition". The first pass kept the lookup basis beside the
        classification - "Structured third-party evidence. Structured provider
        record with no underlying source URL" - and the second half of that is
        the document's definition column. Adding the tier did not bring it
        back."""
        line = ss.describe_source(ss.STRUCTURED_THIRD_PARTY,
                                  "structured provider record with no underlying "
                                  "source URL", "")
        assert line == "T2 - Licensed data tool"
        assert "underlying" not in line

    def test_the_publisher_is_not_a_definition_and_stays(self):
        """It is not from the document at all - it is who published THIS
        signal, which the band alone never says."""
        line = ss.describe_source(ss.FIRST_PARTY,
                                  "first-party company page (newsroom subdomain)",
                                  "Accenture")
        assert line == "T0 - First-party: Accenture"

    def test_a_company_newsroom_on_a_subdomain_is_first_party(self):
        """The document puts "Company newsroom" in the 10/10 row. We matched
        /newsroom as a PATH, so newsroom.accenture.com - the company speaking
        about itself - fell through to the unrecognised-domain fallback and
        scored 6 on eleven of Accenture's cards."""
        for url in ("https://newsroom.accenture.com/news/2026/x",
                    "https://investor.advantest.com/results",
                    "https://ir.sony.co.jp/en/library"):
            points, basis, _resolved = ss.source_reliability_points(url)
            assert points == ss.FIRST_PARTY, url
            assert "subdomain" in basis, url

    def test_a_path_match_still_wins_where_both_apply(self):
        """careers.example.co.jp/jobs/1 is first-party on either reading. The
        path marker is checked first, so the basis says page, not subdomain -
        and the score is the same."""
        points, basis, _resolved = ss.source_reliability_points(
            "https://careers.example.co.jp/jobs/1")
        assert points == ss.FIRST_PARTY
        assert basis == "first-party company page"

    def test_a_publisher_keeps_its_own_newsroom(self):
        """A newspaper writing about the account is reporting, not the account
        speaking. The publisher list is checked first, and stays first."""
        points, _basis, _resolved = ss.source_reliability_points(
            "https://newsroom.reuters.com/story")
        assert points == ss.ESTABLISHED_REPORTING

    def test_a_two_label_host_is_not_somebody_s_newsroom(self):
        """"media.com" and "news.com" start with a first-party prefix and are
        publishers, not a company's own page."""
        for url in ("https://media.com/story", "https://news.com/story"):
            points, _basis, _resolved = ss.source_reliability_points(url)
            assert points != ss.FIRST_PARTY, url

    def test_the_points_are_untouched(self):
        """Naming the tier must not move a score. These come from the client's
        scoring document and are frozen."""
        assert (ss.FIRST_PARTY, ss.ESTABLISHED_REPORTING, ss.STRUCTURED_THIRD_PARTY,
                ss.WEAK_SECONDARY, ss.UNVERIFIABLE) == (10, 8, 6, 3, 0)


class TestTheTierComesFromTheSourceNotThePipe:
    """Asked directly: "verify that T1 - google news rss and exa".

    Almost. Google News RSS and Exa are PIPES, and the tier belongs to what
    came through them. A recognised outlet through either pipe is T1, which is
    what was asked for - but a company press release through the same pipe is
    T0, and a licensed provider record with no publisher at all is T2. Tiering
    the pipe itself would flatten all three into one, and the specification is
    explicit that the underlying source is what gets scored.

    Google News exports carry an opaque /rss/articles/CBMi... link that decodes
    to nothing offline, so the publisher COLUMN is the only usable identity -
    which is why these cases pass a wrapped URL and a real publisher name.
    """

    def test_an_established_outlet_through_google_news_is_t1(self):
        for publisher in ("Nikkei Asia", "Reuters"):
            points, _basis, _url = ss.source_reliability_points(
                url="https://news.google.com/rss/articles/CBMiK2h0dHBz",
                publisher=publisher)
            assert points == ss.ESTABLISHED_REPORTING, publisher
            assert ss.tier_for(points) == "T1"

    def test_an_established_outlet_through_exa_is_t1(self):
        """Exa rows carry a real URL, and sometimes only a publisher name."""
        with_url, _b, _u = ss.source_reliability_points(
            url="https://asia.nikkei.com/Business/advantest-story",
            publisher="Nikkei Asia")
        name_only, _b2, _u2 = ss.source_reliability_points(
            url="", publisher="Nikkei Asia")
        assert with_url == ss.ESTABLISHED_REPORTING
        assert name_only == ss.ESTABLISHED_REPORTING
        assert ss.tier_for(name_only) == "T1"

    def test_a_company_announcement_through_a_pipe_is_t0_not_t1(self):
        """The pipe carried it; the company published it. This is the case
        that breaks if the tier is ever attached to the feed."""
        points, _basis, _url = ss.source_reliability_points(
            url="https://www.advantest.com/news/press-releases/2026-09",
            publisher="Advantest")
        assert points == ss.FIRST_PARTY
        assert ss.tier_for(points) == "T0"

    def test_a_structured_provider_record_is_t2(self):
        """T2 is the client's "paid licensed tools" - a PredictLeads or
        Explorium event with no underlying source to verify."""
        points, _basis, _url = ss.source_reliability_points(
            url="", publisher="", dataset="news_events")
        assert points == ss.STRUCTURED_THIRD_PARTY
        assert ss.tier_for(points) == "T2"

    def test_no_source_at_all_is_unverifiable_and_untiered(self):
        points, _basis, _url = ss.source_reliability_points(url="", publisher="")
        assert points == ss.UNVERIFIABLE
        assert ss.tier_for(points) == ""

    def test_an_unrecognised_outlet_is_left_for_the_caller_to_decide(self):
        """Pinned because the tier names change how the fallback READS.

        `source_reliability_points` returns UNKNOWN - not a band - for an
        outlet it has no standing for, and `recent_news_signals` currently
        settles that at 6. Under the old wording that was a neutral bucket;
        under the client's vocabulary 6 is "paid licensed tools", which a
        regional newspaper is not. Changing the fallback moves scores, so it
        waits for the client. This test records where the decision lives.
        """
        points, basis, _url = ss.source_reliability_points(
            url="https://news.google.com/rss/articles/CBMiQQQ",
            publisher="Jakarta Daily Post")
        assert points is ss.UNKNOWN
        assert "unrecognised publisher" in basis


class TestTheSourceLineIsResolvedAtReadTime:
    """The line is composed from the score, not regenerated into the widget.

    `rationales.source_reliability` is written when a signal is scored and then
    frozen inside the widget, so renaming a band the usual way - bump
    `news.logic_version` - would reach an account only by re-running Live
    Signals, and with it exec_core, opp_triggers, exec_priorities, tech_recs,
    strategy_snapshot and a full idx_executive_dashboard re-embed. For one line
    of text, on every account.

    The score itself never moved, so the dashboard composes the line from
    `scores.source_reliability` and the signal's publisher instead, and every
    account shows the current wording without regenerating any of them.

    That puts a copy of the mapping in the frontend (`sourceReliabilityLine` in
    dashboard/page.tsx), which is the thing that can drift. These assertions are
    what it is checked against: if a band is renamed here and not there, this
    fails rather than the two quietly disagreeing on screen.
    """

    EXPECTED: ClassVar[dict] = {
        10: "T0 - First-party: Nikkei",
        8: "T1 - Established news: Nikkei",
        6: "T2 - Licensed data tool: Nikkei",
        3: "T3 - Long tail: Nikkei",
        0: "Unverifiable: Nikkei",
    }

    def test_every_band_renders_the_string_the_dashboard_mirrors(self):
        for points, expected in self.EXPECTED.items():
            assert ss.describe_source(points, "any basis at all", "Nikkei") == expected

    def test_a_signal_with_no_publisher_renders_the_head_alone(self):
        assert ss.describe_source(ss.ESTABLISHED_REPORTING, "b", "") == "T1 - Established news"
        assert ss.describe_source(ss.UNVERIFIABLE, "b", "") == "Unverifiable"

    def test_the_line_needs_nothing_the_widget_does_not_already_store(self):
        """Both inputs are on a stored signal already - the reliability score
        in `scores`, the publisher on the card. Nothing has to be regenerated
        to produce the line, which is the whole point."""
        stored_score, stored_publisher = 8, "Nikkei"
        assert ss.describe_source(stored_score, "", stored_publisher) == \
            self.EXPECTED[stored_score]
