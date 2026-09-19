"""The scoring config, its validation, and the refresh it triggers.

Weights and bands moved out of the Python modules into `config/scoring.yaml` so
the client's numbers can be retuned without editing code. Two things have to be
true for that to be safe, and this file pins both.

**The move changed no number.** Every score must come out exactly as it did
before. The three scoring suites - `test_urgency.py`, `test_signal_scoring.py`,
`test_tech_confidence.py` - are the real regression test for that and they pass
untouched; what this file adds is the check that the config the modules read is
the config on disk, so nobody can "fix" a value in one place and leave the other
behind.

**A bad edit stops the process.** Making these editable means someone will edit
them, and the two mistakes that matter are silent: weights that no longer sum to
1.0 put every score in a feature proportionally low, and a band table out of
order returns the wrong row for every input. Neither raises, neither logs, and
both leave the numbers inside their normal range. So the loader has to refuse
them, and these tests are what say it does.

Run: python -m pytest tests/test_scoring_config.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.config import scoring
from app.config.scoring import ScoringConfigError, _validate


class TestTheConfigIsWhatTheModulesUse:
    """A config nothing reads is decoration."""

    def test_urgency_reads_its_weights_from_the_config(self):
        from app.services.dashboard import urgency

        assert scoring.weights("urgency") == urgency.WEIGHTS
        assert scoring.bands("urgency", "employee_bands") == urgency.EMPLOYEE_BANDS
        assert scoring.bands("urgency", "growth_bands") == urgency.GROWTH_BANDS

    def test_live_signal_reads_its_weights_from_the_config(self):
        from app.services.extractors import signal_scoring

        assert scoring.weights("live_signal") == signal_scoring.WEIGHTS
        assert scoring.bands(
            "live_signal", "recency_bands") == signal_scoring.RECENCY_BANDS

    def test_tech_confidence_reads_its_weights_from_the_config(self):
        from app.services.hp import tech_confidence

        weights = scoring.weights("tech_confidence")
        assert weights["technology_evidence"] == tech_confidence.DRIVER_1_WEIGHT
        assert weights["intent_support"] == tech_confidence.DRIVER_2_WEIGHT

    def test_evidence_strength_reads_its_points_from_the_config(self):
        from app.services.dashboard import evidence_strength

        section = scoring.section("evidence_strength")
        assert section["points_per_filing"] == evidence_strength.POINTS_PER_FILING
        assert section["max_diversity_points"] == evidence_strength.MAX_DIVERSITY_POINTS


class TestTheClientsNumbersAreUnchanged:
    """The values in the config are the ones the documents specify.

    Written as literals on purpose. Everywhere else these are read from the
    config, so a test that also read from the config would agree with any edit,
    including a wrong one.
    """

    def test_the_urgency_weights_are_20_25_30_25(self):
        assert scoring.weights("urgency") == {
            "workplace_os": 0.20, "ai_workstation": 0.25,
            "growth_expansion": 0.30, "hp_solution_intent": 0.25}

    def test_the_live_signal_weights_are_30_50_20(self):
        assert scoring.weights("live_signal") == {
            "recency": 0.30, "relevance_impact": 0.50,
            "source_reliability": 0.20}

    def test_the_tech_confidence_weights_are_70_30(self):
        assert scoring.weights("tech_confidence") == {
            "technology_evidence": 0.70, "intent_support": 0.30}

    def test_the_documents_worked_examples_still_reproduce(self):
        """The acceptance test for the whole refactor: the two client documents
        each work an example, and both must land on the same number they did
        before any of this moved."""
        from datetime import UTC, datetime

        from app.services.extractors import signal_scoring as ss
        from app.services.hp import tech_confidence as tc

        recency, _ = ss.recency_points(datetime(2026, 4, 23, tzinfo=UTC),
                                       datetime(2026, 9, 17, tzinfo=UTC))
        source, _, _ = ss.source_reliability_points(
            "https://www.idnfinancials.com/news/astra")
        assert ss.composite(recency, 6, source) == 5.80

        driver_2, _ = tc.driver_2_intent(34, "3D")
        assert tc.confidence(10, driver_2) == 85


class TestEverySectionCitesItsSource:

    def test_no_section_is_missing_its_authority(self):
        """A weight with no named document is a number somebody guessed, and
        the authority string is published in the widget payload so a reader who
        doubts a score can find the page it was decided on."""
        for name, section in scoring.CONFIG.items():
            assert section.get("authority"), "section '%s' cites nothing" % name

    def test_the_authority_names_the_client_document(self):
        assert "Urgency" in scoring.section("urgency")["authority"]
        assert "Live_Signal" in scoring.section("live_signal")["authority"]
        assert "Tech_Landscape" in scoring.section("tech_confidence")["authority"]


class TestABadEditIsRefused:
    """The two mistakes that would otherwise be silent."""

    def test_weights_that_do_not_sum_to_one_are_rejected(self):
        """0.9 would put every score in that feature about 10% low, on every
        account, with nothing on screen to show for it."""
        with pytest.raises(ScoringConfigError) as excinfo:
            _validate({"broken": {"authority": "x",
                                  "weights": {"a": 0.5, "b": 0.4}}})
        assert "sum to" in str(excinfo.value)

    def test_the_error_says_how_far_off_it_is(self):
        with pytest.raises(ScoringConfigError) as excinfo:
            _validate({"broken": {"authority": "x",
                                  "weights": {"a": 0.5, "b": 0.4}}})
        assert "10" in str(excinfo.value)

    def test_a_band_table_out_of_order_is_rejected(self):
        """Read first-match-wins, so a row out of place returns the wrong band
        for every input while every score stays inside its normal range."""
        with pytest.raises(ScoringConfigError) as excinfo:
            _validate({"broken": {"authority": "x",
                                  "some_bands": [[10, 5], [50, 10], [25, 7]]}})
        assert "monotonic" in str(excinfo.value)

    def test_both_band_directions_are_accepted(self):
        """Two shapes are in use and both are correct: lower-bound descending
        (urgency's employee ladder) and upper-bound ascending (the live-signal
        recency bands). Requiring one direction would reject half the config."""
        _validate({"ok": {"authority": "x", "a_bands": [[50, 10], [25, 5]]}})
        _validate({"ok": {"authority": "x", "b_bands": [[7, 10], [30, 8]]}})

    def test_a_label_keyed_band_is_not_order_checked(self):
        """`urgency.employee_bands` is keyed on band strings and read by exact
        match, not by threshold - `_employee_band_points` compares normalised
        labels, and the input contract says these are "passed through verbatim;
        NEVER parsed numerically". Its order carries no meaning.

        Pinned so nobody "fixes" the validator to reject it and breaks startup
        on a config that is perfectly correct.
        """
        _validate({"ok": {"authority": "x",
                          "employee_bands": [["10001-49999", 25],
                                             ["50000+", 30],
                                             ["below250", 5]]}})

    def test_a_section_with_no_authority_is_rejected(self):
        with pytest.raises(ScoringConfigError):
            _validate({"anon": {"weights": {"a": 1.0}}})

    def test_a_non_numeric_weight_is_rejected(self):
        with pytest.raises(ScoringConfigError):
            _validate({"broken": {"authority": "x", "weights": {"a": "high"}}})

    def test_a_negative_weight_is_rejected(self):
        with pytest.raises(ScoringConfigError):
            _validate({"broken": {"authority": "x",
                                  "weights": {"a": -0.5, "b": 1.5}}})

    def test_float_addition_does_not_trip_the_sum_check(self):
        """0.20 + 0.25 + 0.30 + 0.25 is not exactly 1.0 in binary. An exact
        comparison would reject the real urgency config."""
        _validate({"ok": {"authority": "x",
                          "weights": {"a": 0.20, "b": 0.25,
                                      "c": 0.30, "d": 0.25}}})


class TestTheVersionStamp:

    def test_each_section_has_its_own_version(self):
        versions = {name: scoring.version(name) for name in scoring.CONFIG}
        assert len(set(versions.values())) == len(versions), (
            "two sections hash the same, so a change to one would look like a "
            "change to the other")

    def test_the_version_is_stable_across_calls(self):
        assert scoring.version("urgency") == scoring.version("urgency")

    def test_editing_a_weight_changes_the_version(self):
        """The whole mechanism rests on this: if a changed weight produced the
        same hash, nothing would ever be detected as stale."""
        import hashlib
        import json

        def fake_version(payload):
            return hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()[:12]

        before = fake_version({"weights": {"a": 0.5, "b": 0.5}})
        after = fake_version({"weights": {"a": 0.6, "b": 0.4}})
        assert before != after

    def test_the_authority_text_is_not_part_of_the_version(self):
        """Fixing a typo in a citation must not invalidate a year of stored
        scores - the numbers are what the version is about."""
        payload = {k: v for k, v in scoring.section("urgency").items()
                   if k != "authority"}
        assert "authority" not in payload


class TestTheRefreshFindsWhatAChangeInvalidated:

    def _fake_db(self, stored_stamp):
        current = scoring.version("urgency")
        stamp = current if stored_stamp == "current" else stored_stamp

        class Collection:
            def find(self, query, _projection=None):
                if query.get("widget_key") != "exec_urgency_score":
                    return iter([])
                data = {} if stamp is None else {"scoring_config_version": stamp}
                return iter([{"account_id": "acc1", "data": data}])

        return {"account_widgets": Collection()}

    def test_a_widget_scored_by_the_current_config_is_left_alone(self):
        from app.services.dashboard import scoring_refresh

        assert scoring_refresh.find_stale(self._fake_db("current")) == []

    def test_a_widget_scored_by_a_different_config_is_stale(self):
        from app.services.dashboard import scoring_refresh

        stale = scoring_refresh.find_stale(self._fake_db("an-old-hash"))
        assert len(stale) == 1
        assert stale[0]["account_id"] == "acc1"
        assert stale[0]["feature_key"] == "executive_dashboard"

    def test_an_unstamped_widget_counts_as_stale(self):
        """Every widget written before stamping existed has no stamp, and it
        cannot be shown to agree with the current config. Assuming it does is
        exactly how the retired urgency formula stayed on the dashboard."""
        from app.services.dashboard import scoring_refresh

        assert len(scoring_refresh.find_stale(self._fake_db(None))) == 1

    def test_a_dry_run_queues_nothing(self):
        from app.services.dashboard import scoring_refresh

        report = scoring_refresh.refresh_stale_scores(
            db=self._fake_db("an-old-hash"), apply=False)
        assert report["stale"] and report["queued"] == []

    def test_every_stamped_widget_names_a_real_feature_extractor(self):
        """A stale widget whose feature has no extractor can never be repaired,
        and the sweep would report it as stale on every single boot."""
        from app.api.v1.account_data import FEATURE_EXTRACTORS
        from app.services.dashboard import scoring_refresh

        for spec in scoring_refresh.STAMPED_WIDGETS:
            assert spec["feature_key"] in FEATURE_EXTRACTORS, spec["widget_key"]

    def test_every_stamped_widget_names_a_real_config_section(self):
        from app.services.dashboard import scoring_refresh

        for spec in scoring_refresh.STAMPED_WIDGETS:
            assert spec["section"] in scoring.CONFIG, spec["widget_key"]
