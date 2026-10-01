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

    def test_a_missing_input_reads_neutrally(self):
        """Client, 1 Oct: no partial-data wording on screen. The line reads "No
        signal observed"; the real basis stays on the term (and in data_gaps)."""
        driver = self._driver()
        assert "Print estate: 0.0/25 - No signal observed" in driver["rationale_lines"]
        assert not any("missing-input" in line or "no print vendor" in line
                       for line in driver["rationale_lines"])
        assert driver["terms"][1]["basis"] == "no print vendor in the export"

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

    def test_a_dash_quoted_from_the_data_is_made_plain(self):
        from app.services.dashboard import urgency
        lines = urgency.rationale_lines({"weight": 0.2, "terms": [
            {"label": "Hiring", "points": 3, "max_points": 5,
             "basis": "roles \u2014 engineering \u2013 design"}]})
        assert chr(8212) not in " ".join(lines) and chr(8211) not in " ".join(lines)


class TestSupportingClaimsArePoints:
    """1 Oct: a supporting claim is one short point, never a paragraph."""

    FIRMO = (
        "Accenture plc is a global professional services firm that delivers a "
        "wide array of strategy, consulting, interactive, technology, and "
        "operations services worldwide. Its cybersecurity portfolio includes "
        "cyber defense, applied and managed security, operational technology "
        "(OT) security, security strategy and risk management, and "
        "industry-specific security products. Additionally, Accenture provides "
        "cloud solutions, ecosystem development, marketing st"
    )

    def test_the_sentence_about_the_priority_is_chosen(self):
        wanted = priorities._content_words("Strengthen cybersecurity and security")
        point = priorities.claim_point(self.FIRMO, wanted)
        assert point.startswith("Its cybersecurity portfolio")
        assert point in self.FIRMO or point[:-1] in self.FIRMO

    def test_a_cut_off_fragment_is_never_the_point(self):
        point = priorities.claim_point(self.FIRMO, priorities._content_words("marketing"))
        assert "marketing st" not in point

    def test_a_long_sentence_ends_at_a_clause_with_no_ellipsis(self):
        long = ("We offer " + ", ".join("service line %d" % i for i in range(20))
                + ", and more.")
        point = priorities.claim_point(long, set())
        assert len(point.split()) <= priorities.CLAIM_POINT_MAX_WORDS
        assert point.endswith(".") and "..." not in point and "…" not in point

    def test_a_short_sentence_is_left_whole(self):
        text = "Revenue grew 8% in local currency."
        assert priorities.claim_point(text, set()) == text

    def test_empty_text_gives_no_point(self):
        assert priorities.claim_point("", {"cloud"}) == ""

    def test_the_registered_text_is_kept_beside_the_point(self):
        row = {"evidence_id": "e1", "source_text": self.FIRMO}
        out = priorities._source(row, {"cybersecurity"})
        assert out["source_text"] == self.FIRMO
        assert out["claim_point"] and len(out["claim_point"]) < len(self.FIRMO)

    def test_inc_does_not_end_a_sentence(self):
        text = ("Advantest partnered with PDF Solutions Inc. focused on "
                "cloud-based software solutions. It also tests memory.")
        point = priorities.claim_point(text, {"cloud"})
        assert point == ("Advantest partnered with PDF Solutions Inc. focused on "
                         "cloud-based software solutions.")

    def test_an_inline_bullet_is_a_break(self):
        text = ("Its main strategy focuses on: • Improving service quality "
                "for customers through operational excellence.")
        point = priorities.claim_point(text, {"service", "quality"})
        assert point == ("Improving service quality for customers through "
                         "operational excellence.")
        assert "•" not in point

    def test_a_heading_run_into_the_text_is_dropped(self):
        text = ("About Accenture Accenture helps the world's leading enterprises "
                "reinvent by building their digital core.")
        assert priorities.claim_point(text, {"digital"}).startswith("Accenture helps")

    def test_a_cut_off_point_after_a_lead_in_is_used_not_the_lead_in(self):
        text = ("Its main strategy focuses on: • Improving service quality "
                "for customers through operational excellence, resource "
                "development, and innovation ASTRA Infra has continued to strive c")
        point = priorities.claim_point(text, {"operational", "excellence"})
        assert point == ("Improving service quality for customers through "
                         "operational excellence, resource development.")

    def test_a_connective_opener_is_dropped(self):
        text = ("Furthermore, Advantest has established strategic alliances "
                "with STMicroelectronics.")
        assert priorities.claim_point(text, {"alliances"}).startswith("Advantest has")

    def test_a_long_sentence_ends_before_a_trailing_which_clause(self):
        text = ("ASTRA Infra has continued to implement its main operational "
                "excellence strategy across every toll road concession it runs "
                "which focuses on service quality resource development and "
                "innovation for customers.")
        point = priorities.claim_point(text, {"excellence"})
        assert point.endswith("concession it runs.")
        assert len(point.split()) <= priorities.CLAIM_POINT_MAX_WORDS

    def test_a_point_starts_with_a_capital(self):
        text = "agreement to acquire a majority stake in Dragos is our strategy."
        assert priorities.claim_point(text, {"dragos"})[0] == "A"

    def test_reading_the_widget_never_changes_the_stored_payload(self):
        stored = {"priorities": [{"title": "Grow cybersecurity", "sources": [
            {"evidence_id": "e1", "source_text": self.FIRMO}]}]}
        shown = priorities.with_claim_points(stored)
        assert "claim_point" not in stored["priorities"][0]["sources"][0]
        assert shown["priorities"][0]["sources"][0]["claim_point"]
        assert shown["priorities"][0]["sources"][0]["source_text"] == self.FIRMO

    def test_a_section_heading_run_into_the_text_is_dropped(self):
        text = ("Transformational Leadership To prepare future leaders who are "
                "capable of leading change.")
        assert priorities.claim_point(text, {"leaders"}).startswith("To prepare")

    def test_a_company_name_opening_a_sentence_is_not_a_heading(self):
        text = "Advantest Corporation designs automatic test equipment."
        assert priorities.claim_point(text, {"test"}) == text

    def test_a_trailing_list_marker_is_dropped(self):
        text = "Increasing focus on professional IT services for the segment; d."
        assert priorities.claim_point(text, {"services"}).endswith("segment.")

    def test_a_leading_and_is_dropped(self):
        text = "and operational dashboards that increase traffic monitoring productivity."
        assert priorities.claim_point(text, {"dashboards"}).startswith("Operational")

    def test_a_cut_never_leaves_an_adjective_without_its_noun(self):
        text = ("Our strategy is to be the reinvention partner of choice for our "
                "clients and lead in the safe, widespread adoption of AI, and to "
                "be the most client-focused firm.")
        point = priorities.claim_point(text, {"strategy"})
        assert not point.endswith("the safe.")
        assert point.endswith(("our clients.", "adoption of AI."))


class TestALongSourceIsSeveralPoints:
    """1 Oct: a long paragraph becomes 3 to 6 points; a short source stays one."""

    LONG = " ".join([
        "Accenture plc is a global professional services firm.",
        "It offers application services such as agile transformation and DevOps.",
        "Its cybersecurity portfolio includes cyber defense and managed security.",
        "It also provides cloud solutions and ecosystem development.",
        "The company supports talent and organizational development.",
        "Accenture operates digital commerce and infrastructure services.",
        "It offers OT security and security strategy services.",
        "It provides intelligent automation including robotic process automation.",
        "Accenture supports engineering and research digitization.",
        "Accenture runs managed edge and IoT device services.",
    ])

    def test_a_short_source_is_one_point(self):
        text = "Revenue grew 8% in local currency."
        assert priorities.claim_points(text, {"revenue"}) == [text]

    def test_a_long_source_is_capped_at_six(self):
        wanted = {"accenture", "services", "security", "cloud", "provides", "offers"}
        points = priorities.claim_points(self.LONG, wanted)
        assert 3 <= len(points) <= 6

    def test_a_long_source_gives_at_least_three(self):
        points = priorities.claim_points(self.LONG, {"cybersecurity"})
        assert len(points) == 3
        assert any("cybersecurity" in p for p in points)

    def test_points_keep_the_source_order(self):
        points = priorities.claim_points(self.LONG, {"security"})
        assert points == sorted(points, key=self.LONG.index)

    def test_every_point_is_short_and_finished(self):
        for point in priorities.claim_points(self.LONG, {"security"}):
            assert len(point.split()) <= priorities.CLAIM_POINT_MAX_WORDS + 8
            assert point.endswith(".") and not point.endswith("...")

    def test_the_source_carries_the_list_and_the_single_point(self):
        out = priorities._source({"evidence_id": "e1", "source_text": self.LONG},
                                 {"security"})
        assert len(out["claim_points"]) >= 3 and out["claim_point"]

    def test_a_cut_never_drops_the_verb_after_an_aside(self):
        text = ("Advantest Corporation, a Japanese entity founded in Tokyo in "
                "1954, specializes in the research, development, manufacturing, "
                "and global sale of automated test equipment.")
        point = priorities.claim_point(text, {"advantest"})
        assert "specializes" in point
