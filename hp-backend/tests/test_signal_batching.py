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
    """The names come from the Source classification column of
    HP_Live_Signal_Scoring_Logic, verbatim. The T0-T3 tiers the client
    mentioned on 27 Sep are from that message, not from the scoring document,
    so they are deliberately not used."""

    def test_each_band_carries_the_document_s_own_name(self):
        for points, name in (
                (ss.FIRST_PARTY, "First-party or authoritative"),
                (ss.ESTABLISHED_REPORTING, "Established independent reporting"),
                (ss.STRUCTURED_THIRD_PARTY, "Structured third-party evidence"),
                (ss.WEAK_SECONDARY, "Weak secondary evidence"),
                (ss.UNVERIFIABLE, "Unverifiable")):
            assert ss.classification_for(points) == name

    def test_no_tier_vocabulary_anywhere(self):
        for points in (10, 8, 6, 3, 0):
            line = ss.describe_source(points, "established publication", "Nikkei")
            assert "T0" not in line
            assert "T1" not in line
            assert "T2" not in line
            assert "T3" not in line

    def test_the_line_names_the_publisher_too(self):
        """The band alone says nothing about this signal; the publisher was on
        the card and never in the explanation."""
        line = ss.describe_source(ss.ESTABLISHED_REPORTING,
                                  "established publication", "Nikkei")
        assert line == "Established independent reporting. Nikkei"

    def test_no_basis_reaches_the_line_whatever_it_says(self):
        line = ss.describe_source(ss.ESTABLISHED_REPORTING,
                                  "established publication (reuters.com)", "Reuters")
        assert line == "Established independent reporting. Reuters"

    def test_the_definition_is_never_printed(self):
        """Sahaj, 28 Sep: "only show the part written in classification n not
        definition". The first pass kept the lookup basis beside the
        classification - "Structured third-party evidence. Structured provider
        record with no underlying source URL" - and the second half of that is
        the document's definition column."""
        line = ss.describe_source(ss.STRUCTURED_THIRD_PARTY,
                                  "structured provider record with no underlying "
                                  "source URL", "")
        assert line == "Structured third-party evidence"

    def test_the_publisher_is_not_a_definition_and_stays(self):
        """It is not from the document at all - it is who published THIS
        signal, which the band alone never says."""
        line = ss.describe_source(ss.FIRST_PARTY,
                                  "first-party company page (newsroom subdomain)",
                                  "Accenture")
        assert line == "First-party or authoritative. Accenture"

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
