"""The 27 September client feedback on the Executive Dashboard.

Six items, of which four change what the backend produces:

  1a  the company write-up arrives as bullets, reorganised from the paragraph
      and never adding to it
  1d  the urgency "i" explanation is a list of lines, built once in the
      backend, with plain hyphens
  1e  Quick Stats is gone - the card, the three counts, and the contacts read
      that existed only to feed one of them
  1f  a priority card is bullets, and a 0/100 says why it is 0

Run: python -m pytest tests/test_exec_dashboard_feedback.py -v
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import evidence_strength, priorities, urgency
from app.services.extractors import executive_dashboard as ed

PARAGRAPH = (
    "Advantest Corporation designs and manufactures automatic test equipment "
    "for the semiconductor industry, including system-on-chip and memory "
    "testers. It also supplies measurement instruments, and reported revenue "
    "of 486 billion yen. The company operates across Japan, Asia and Europe, "
    "and is expanding its nano-technology and photonics research."
)


class _DB(dict):
    """Just enough Mongo for the bullets cache."""

    def __init__(self, stored=None):
        self.stored = stored

    def __getitem__(self, _name):
        return self

    def find_one(self, query, _projection=None):
        # widget_store looks up the node's state by _id first; no state means an
        # account the regeneration engine has not adopted, and it falls back to
        # account_widgets - which is what this fake holds.
        if isinstance(query, dict) and "_id" in query:
            return None
        return self.stored


class TestTheCompanyWriteUpAsBullets:

    def test_a_short_description_is_left_as_prose(self, monkeypatch):
        """Two lines read worse as a bullet than as a sentence."""
        called = []
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion",
                            lambda *_a, **_k: called.append(1))
        points, basis = ed._description_points(_DB(), "acct", "A small firm.", {})
        assert points == []
        assert "short enough" in basis
        assert called == []

    def test_a_long_description_becomes_bullets(self, monkeypatch):
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "points": ["Designs automatic test equipment for semiconductors.",
                       "Supplies measurement instruments; revenue 486 billion yen.",
                       "Operates across Japan, Asia and Europe."]})
        points, basis = ed._description_points(
            _DB(), "acct", PARAGRAPH, {"Business Description": PARAGRAPH})
        assert len(points) == 3
        assert "no fact added" in basis

    def test_a_figure_the_paragraph_never_carried_is_rejected(self, monkeypatch):
        """The paragraph is the only source. 42% is invented, so the bullets
        are held back and the paragraph is shown instead."""
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "points": ["Designs test equipment for semiconductors.",
                       "Grew revenue 42% year on year.",
                       "Operates across Japan, Asia and Europe."]})
        points, basis = ed._description_points(
            _DB(), "acct", PARAGRAPH, {"Business Description": PARAGRAPH})
        assert points == []
        assert "42%" in basis

    def test_too_few_bullets_falls_back_rather_than_publishing_one(self, monkeypatch):
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion",
                            lambda *_a, **_k: {"points": ["One bullet only."]})
        points, basis = ed._description_points(
            _DB(), "acct", PARAGRAPH, {"Business Description": PARAGRAPH})
        assert points == []
        assert "1 bullet" in basis

    def test_an_unchanged_paragraph_is_not_sent_twice(self, monkeypatch):
        """Same cache rule as every other generated field: the fingerprint
        covers the text and the prompt version."""
        stored = {"data": {
            "business_description_fingerprint": ed._description_fingerprint(PARAGRAPH),
            "business_description_points": ["Cached bullet one.", "Cached bullet two."],
            "business_description_points_basis": "reorganised from the description",
        }}
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion",
                            lambda *_a, **_k: pytest_fail())
        points, _basis = ed._description_points(
            _DB(stored), "acct", PARAGRAPH, {"Business Description": PARAGRAPH})
        assert points == ["Cached bullet one.", "Cached bullet two."]

    def test_a_changed_paragraph_is_regenerated(self, monkeypatch):
        stored = {"data": {
            "business_description_fingerprint": ed._description_fingerprint("something else"),
            "business_description_points": ["Stale bullet."],
        }}
        monkeypatch.setattr(ed, "generate_gpt4o_json_completion", lambda *_a, **_k: {
            "points": ["Fresh one.", "Fresh two.", "Fresh three."]})
        points, _basis = ed._description_points(
            _DB(stored), "acct", PARAGRAPH, {"Business Description": PARAGRAPH})
        assert points[0] == "Fresh one."


def pytest_fail():
    raise AssertionError("the model was called for a description that had not changed")


class TestQuickStatsIsGone:

    def test_the_counts_are_no_longer_produced(self):
        with open(ed.__file__, encoding="utf-8") as handle:
            source = handle.read()
        for field in ("solution_narratives_count", "recent_signals_count",
                      "stakeholders_mapped_count", "_cross_feature_counts"):
            assert field not in source, field

    def test_contacts_are_no_longer_read(self):
        """The only contact-derived field was the dropped count, so the read
        and the dependency went with it."""
        from app.api.v1.feature_mapping import FEATURE_MAPPINGS
        deps = FEATURE_MAPPINGS["executive_dashboard"]["dependent_datasets"]
        assert "prospect_contacts" not in deps
        assert "firmographics" in deps


class TestTheUrgencyExplanation:

    def _driver(self):
        key = next(iter(urgency.DRIVER_LABELS))
        return urgency._driver(
            key, 45,
            [urgency._term("Client OS refresh", 20, 25, "Windows 10 across the estate"),
             urgency._term("Print estate", 0, 25, "no print vendor in the export",
                           missing=True)],
            ["ev1"], notes=["Two of four components have input."],
            caveats=["Coverage is 62%."])

    def test_it_is_a_list_not_a_paragraph(self):
        lines = self._driver()["rationale_lines"]
        assert isinstance(lines, list)
        assert len(lines) == 5

    def test_it_uses_plain_hyphens(self):
        """The client: "let's not use em-dashes please and replace with just
        simple '-'"."""
        joined = " ".join(self._driver()["rationale_lines"])
        assert chr(8212) not in joined
        assert chr(8211) not in joined

    def test_a_missing_input_still_says_so(self):
        lines = self._driver()["rationale_lines"]
        assert any("missing-input rule" in line for line in lines)

    def test_the_weight_leads(self):
        assert self._driver()["rationale_lines"][0].startswith("Weight ")


class TestAZeroThatExplainsItself:

    def test_a_zero_carries_its_reason(self):
        """Advantest's six priorities each rest on one undated sentence from
        the business description. The score is right; the bare number was the
        problem."""
        scored = evidence_strength.score(
            [{"dataset": "firmographics", "field": "business_description"}],
            date(2026, 9, 27))
        assert scored["score"] == 0
        assert "not the account" in scored["zero_reason"]

    def test_a_real_score_carries_none(self):
        scored = evidence_strength.score(
            [{"dataset": "compliance_filings", "filing_label": "FY25 Annual Report",
              "filing_period": "2025"}], date(2026, 9, 27))
        assert scored["score"] > 0
        assert scored["zero_reason"] is None


class TestThePriorityCardAsBullets:

    def test_bullets_are_read_from_the_answer(self):
        assert priorities._points({"points": ["One.", "Two."]}) == ["One.", "Two."]

    def test_a_leading_dash_is_stripped(self):
        assert priorities._points({"points": ["- One.", "– Two."]}) == ["One.", "Two."]

    def test_the_older_paragraph_shape_still_renders(self):
        """A cached answer written before this change must not blank the card."""
        assert priorities._points({"description": "A paragraph."}) == ["A paragraph."]

    def test_an_empty_answer_is_empty(self):
        assert priorities._points({}) == []
        assert priorities._points({"points": []}) == []
