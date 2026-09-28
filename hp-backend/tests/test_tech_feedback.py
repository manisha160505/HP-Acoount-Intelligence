"""The 27 September client feedback on the Technographic Map.

Two items, §6:

  6.1  "was the confidence score provided in the data we shared or are we
       calculating it on our end? ... I would stay away from this, hence,
       let's drop the confidence score."

       We calculate it, from the client's own
       HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx, and no uploaded
       file carries a confidence column. It leaves the card - but not the
       pipeline: `is_publishable` decides which vendor cards exist at all, so
       the scoring has to keep running. These tests hold that line.

  6.2  "we mention about 281 technologies detected - we need to club those in
       relevant categories and show here and also, have a download button to
       extract the whole techstack."

       The categories are the export's own 20 columns. They only name 186 of
       Advantest's 281 technologies, because the export truncates every
       category cell ("... Google Cloud APIs (+16 more)"), so the remainder
       gets a group of its own rather than disappearing.

Run: python -m pytest tests/test_tech_feedback.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.tech_landscape import (
    UNCATEGORISED_LABEL,
    _category_names,
    category_groups,
    multi_category_technologies,
)
from app.services.hp import tech_confidence as tconf


# -------------------------------------------------------------------- 6.2
class TestTheExportsTruncationMarker:

    def test_a_truncated_cell_yields_only_real_technologies(self):
        assert _category_names("Apache, Assemble, Google Cloud APIs (+16 more)") \
            == ["Apache", "Assemble", "Google Cloud APIs"]

    def test_the_marker_never_becomes_a_technology(self):
        for cell in ("A (+16 more)", "A, B (+1 more)", "A, B (+ 20 MORE )"):
            assert not any("more)" in name for name in _category_names(cell))

    def test_an_untruncated_cell_is_unchanged(self):
        assert _category_names("TestNG, test IO") == ["TestNG", "test IO"]

    def test_an_empty_cell_yields_nothing(self):
        assert _category_names("") == []
        assert _category_names(None) == []

    def test_a_repeated_name_appears_once(self):
        assert _category_names("A, B, A") == ["A", "B"]


MATRIX = {
    "Bi And Analytics": ["Tableau", "Databricks", "SageMaker"],
    "Sales": ["NetSuite"],
    "Ecommerce": [],
}
FULL = ["Tableau", "Databricks", "SageMaker", "NetSuite", "ABBYY", "Agilent"]


class TestTheWholeStackIsReachable:

    def test_every_technology_is_reachable(self):
        groups = category_groups(MATRIX, FULL)
        placed = {t for g in groups for t in g["technologies"]}
        assert placed == set(FULL)

    def test_a_technology_the_export_files_twice_appears_in_both(self):
        """NetSuite is under BI, Sales, Finance, IT Management and Customer
        Management on the real export. That is the file's own reading and it is
        not flattened to one."""
        groups = category_groups(
            {"Sales": ["NetSuite"], "Finance And Accounting": ["NetSuite"]},
            ["NetSuite"])
        assert [g["category"] for g in groups] == ["Finance And Accounting", "Sales"]
        assert multi_category_technologies(groups) == 1

    def test_nothing_is_counted_twice_when_the_export_files_it_once(self):
        assert multi_category_technologies(category_groups(MATRIX, FULL)) == 0

    def test_what_the_export_did_not_categorise_has_its_own_group(self):
        groups = category_groups(MATRIX, FULL)
        last = groups[-1]
        assert last["category"] == UNCATEGORISED_LABEL
        assert last["technologies"] == ["ABBYY", "Agilent"]

    def test_that_group_says_why_it_exists(self):
        """A reader must be able to tell whose gap it is - the export's, not
        ours."""
        groups = category_groups(MATRIX, FULL)
        assert "truncates" in groups[-1]["note"]

    def test_it_is_last_even_when_it_is_the_largest(self):
        groups = category_groups({"Sales": ["A"]}, ["A"] + ["t%d" % i for i in range(40)])
        assert groups[-1]["category"] == UNCATEGORISED_LABEL
        assert groups[-1]["count"] == 40

    def test_there_is_no_such_group_when_everything_is_categorised(self):
        groups = category_groups({"Sales": ["A", "B"]}, ["A", "B"])
        assert [g["category"] for g in groups] == ["Sales"]

    def test_an_empty_category_produces_no_group(self):
        groups = category_groups(MATRIX, FULL)
        assert "Ecommerce" not in [g["category"] for g in groups]

    def test_groups_run_largest_first(self):
        groups = category_groups(
            {"A": ["1"], "B": ["1", "2", "3"], "C": ["1", "2"]}, ["1", "2", "3"])
        assert [g["category"] for g in groups] == ["B", "C", "A"]

    def test_a_tie_breaks_on_the_category_name(self):
        groups = category_groups({"Sales": ["a"], "Hr": ["b"]}, ["a", "b"])
        assert [g["category"] for g in groups] == ["Hr", "Sales"]

    def test_the_uncategorised_group_keeps_the_exports_order(self):
        groups = category_groups({"Sales": ["B"]}, ["C", "B", "A"])
        assert groups[-1]["technologies"] == ["C", "A"]

    def test_a_case_difference_is_not_a_second_technology(self):
        """The category cell and Full Tech Stack do not always agree on case."""
        groups = category_groups({"Sales": ["NetSuite"]}, ["netsuite", "Agilent"])
        assert [g["category"] for g in groups] == ["Sales", UNCATEGORISED_LABEL]
        assert groups[-1]["technologies"] == ["Agilent"]

    def test_no_technographics_row_yields_nothing(self):
        assert category_groups({}, []) == []


# -------------------------------------------------------------------- 6.1
class TestTheScoreStillRuns:
    """Dropped from the card, not from the pipeline."""

    def test_the_formula_is_still_the_clients_own(self):
        assert tconf.FORMULA_AUTHORITY.startswith(
            "HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL")

    def test_the_weights_are_untouched(self):
        assert tconf.confidence(10, 10) == 100
        assert tconf.confidence(10, 0) == 70
        assert tconf.confidence(0, 10) == 30

    def test_a_card_with_no_technology_evidence_is_still_suppressed(self):
        """This is the part that would silently change the visible card set if
        the scoring were removed along with the display."""
        assert tconf.is_publishable(10)
        assert tconf.is_publishable(5)
        assert not tconf.is_publishable(0)


class TestTheNumberIsNoLongerNarrated:
    """Deleting it from the card is not enough if the index still quotes it."""

    def test_the_technology_corpus_states_no_confidence(self):
        import inspect

        from app.services.retrieval import corpus
        src = inspect.getsource(corpus)
        assert "(confidence: %s)" not in src
        assert "confidence_text" not in src
