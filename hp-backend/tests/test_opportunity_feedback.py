"""The 27 September client feedback on the Opportunity Map.

Three items, §5:

  5.1a  "Delete the Quantified Impact and Supporting Signal section and
        timeline entire box with Target buyers and Next steps."
  5.1b  "the case study mapping in this case doesn't match ... the point is
        about the use case of 3D printers for a manufacturing company, whereas
        the case study is linking to HP Managed services for printers ... We
        need to fine tune the matching of tags for case studies accordingly."
        Answered on the client's own terms: "we need to match the case studies
        via the tagging provided in the case studies file only."
  5.2   "Are we sure we found Win 7 still in their fleet via their tech stack?
        ... I think this would have been Win 10, can we please double check."

5.1b was a real bug and not in the matcher. The model keyed the play "3d"
correctly; `normalize_hp_product` then read the word "print" inside "HP 3D
Printing Solutions" and tagged it HP Enterprise Print / MPS, because the HP
line list had no 3D member at all. The case-study lookup did the right thing
with the wrong input. The tests below pin both halves shut.

Run: python -m pytest tests/test_opportunity_feedback.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from app.services.extractors.grounding import (
    HP_PRODUCT_LINES,
    filter_enum_list,
    normalize_hp_product,
)
from app.services.extractors.tech_versions import spellings, superseded
from app.services.hp import case_studies as cs

LINE_3D_PRODUCT = "HP Multi Jet Fusion (3D)"


# ------------------------------------------------------------------- 5.1b
class TestA3DPlayIsNotAPrintPlay:

    def test_the_3d_line_exists(self):
        assert LINE_3D_PRODUCT in HP_PRODUCT_LINES

    @pytest.mark.parametrize("written", [
        "HP 3D Printing Solutions",
        "3D printing",
        "HP Multi Jet Fusion",
        "HP Metal Jet",
        "additive manufacturing",
    ])
    def test_a_3d_name_resolves_to_3d(self, written):
        """Every one of these contains "print" or would otherwise fall through
        to the print line, which is exactly what the client saw."""
        assert normalize_hp_product(written) == LINE_3D_PRODUCT

    @pytest.mark.parametrize("written", [
        "HP Managed Print Services",
        "HP Enterprise Print / MPS",
        "MPS",
    ])
    def test_a_print_name_still_resolves_to_print(self, written):
        assert normalize_hp_product(written) == "HP Enterprise Print / MPS"

    def test_the_model_s_own_wording_survives_the_enum(self):
        kept, rejected = filter_enum_list(["HP 3D Printing Solutions"], HP_PRODUCT_LINES)
        assert kept == [LINE_3D_PRODUCT]
        assert rejected == []

    def test_the_3d_line_reaches_the_3d_studies(self):
        assert cs.lines_for_hp_line(LINE_3D_PRODUCT) == (cs.LINE_3D,)


def _study(customer, product, route, industry, tags=(), tier="T0"):
    return {
        "customer": customer,
        "product_featured": product,
        "hp_route": route,
        "industry": industry,
        "signal_tags": list(tags),
        "source_tier": tier,
        "headline": "HP published a case study with %s." % customer,
        "outcome": "a stated result",
    }


class _DB:
    def __init__(self, studies):
        self.studies = studies

    def __getitem__(self, _name):
        return self

    def find(self, *_a, **_k):
        return list(self.studies)

    def find_one(self, *_a, **_k):
        return None


CORPUS = [
    _study("CNC Würfel", "HP Multi Jet Fusion", "3D Printing", "Automotive",
           ("Production-Optimization",)),
    _study("CSX", "HP Managed Print Services", "Print", "Automotive",
           ("Production-Optimization",)),
    _study("A Builder", "HP SitePrint", "Print", "Other"),
]


class TestTheProofPointFollowsTheFilesTags:

    def test_a_3d_play_gets_a_3d_study(self):
        found = cs.match(_DB(CORPUS), cs.lines_for_hp_line(LINE_3D_PRODUCT),
                         industry="Automotive", signals=["Production-Optimization"])
        assert [s["customer"] for s in found] == ["CNC Würfel"]

    def test_a_3d_play_never_gets_the_managed_print_study(self):
        """The exact card the client sent back."""
        found = cs.match(_DB(CORPUS), cs.lines_for_hp_line(LINE_3D_PRODUCT),
                         industry="Automotive", signals=["Production-Optimization"])
        assert all(s["customer"] != "CSX" for s in found)

    def test_a_print_play_never_gets_a_3d_study(self):
        found = cs.match(_DB(CORPUS), cs.lines_for_hp_line("HP Enterprise Print / MPS"),
                         industry="Automotive", signals=["Production-Optimization"])
        assert [s["customer"] for s in found] == ["CSX"]

    def test_siteprint_answers_neither(self):
        """It is tagged hp_route "Print" and is a construction layout printer."""
        for line in (cs.LINE_PRINT, cs.LINE_3D):
            found = cs.match(_DB(CORPUS), (line,))
            assert all(s["customer"] != "A Builder" for s in found)

    def test_a_line_with_no_study_still_returns_nothing(self):
        assert cs.match(_DB(CORPUS), (cs.LINE_SECURITY,)) == []


# -------------------------------------------------------------------- 5.2
class TestTheNewestVersionWins:
    """The account's own export lists Microsoft Windows 7 AND Windows 10 in one
    cell of Platform And Storage. The file is right; the card led with the
    wrong half of it."""

    def test_the_older_windows_is_superseded(self):
        assert superseded(["Microsoft Windows 7", "Windows 10",
                           "Oracle Linux", "VMware"]) == {"Microsoft Windows 7"}

    def test_one_version_of_a_product_is_never_superseded(self):
        assert superseded(["Windows 10", "Apache Tomcat", "Tableau Software"]) == set()

    def test_a_vendor_prefix_does_not_split_the_family(self):
        """"Microsoft Windows 7" and "Windows 10" have to be one product or
        this rule never fires, which was the whole point."""
        assert superseded(["Microsoft Windows 7", "Windows 10"])

    def test_a_decimal_version_orders_numerically(self):
        assert superseded(["Oracle Solaris 10", "Oracle Solaris 11.4"]) \
            == {"Oracle Solaris 10"}

    def test_a_name_with_no_version_is_left_alone(self):
        assert superseded(["Linux", "Unix", "Docker"]) == set()

    def test_different_products_never_compare(self):
        assert superseded(["SQL Server 2019", "Windows 10"]) == set()

    def test_prose_spelling_is_matched_as_well_as_the_exports(self):
        """The export says "Microsoft Windows 7"; the sentence that started
        this said "(Windows 7)". Checking only the export's spelling left the
        inference contrasting the two versions under a corrected quote."""
        assert "windows 7" in spellings("Microsoft Windows 7")
        assert "microsoft windows 7" in spellings("Microsoft Windows 7")

    def test_an_unversioned_name_has_one_spelling(self):
        assert spellings("Docker") == ("docker",)

    @pytest.mark.parametrize("names", [
        ["Microsoft Office 365", "Microsoft Office 2016"],
        ["Cisco Catalyst 6500", "Cisco Catalyst 6503"],
        ["Cisco 2504", "Cisco 3825", "Cisco 5500", "Cisco ASA 5500"],
    ])
    def test_a_model_number_is_not_a_version(self, names):
        """The first run of this rule fired on all of these: Office 365 read
        as older than Office 2016, and a Catalyst 6500 as an older 6503. They
        are different products, not older versions of one another."""
        assert superseded(names) == set()

    def test_a_release_year_supersedes_an_earlier_year(self):
        assert superseded(["SQL Server 2016", "Microsoft SQL Server 2019"])             == {"SQL Server 2016"}

    def test_a_year_and_a_release_number_never_compare(self):
        """Windows 2000 is not a newer Windows 10."""
        assert superseded(["Windows 2000", "Windows 10"]) == set()

    def test_it_reads_no_end_of_life_dates(self):
        """Deliberately not an EOL table - support dates are knowledge from
        outside the account's files and they age. A single Windows 7 with no
        newer version in the same export stays usable evidence."""
        assert superseded(["Microsoft Windows 7", "Oracle Linux"]) == set()


# ------------------------------------------------------------------- 5.1a
class TestTheDeletedSectionsAreGone:
    """Asserted against the extractor's source: these are prompt fields and
    payload keys, and a reader of the module should not find them back."""

    def _source(self):
        import inspect

        from app.services.extractors import solution_narrative_opportunity_map as som
        return inspect.getsource(som)

    def test_the_model_is_no_longer_asked_for_a_quantified_impact(self):
        src = self._source()
        assert '"quantified_impact"' not in src
        assert "quantified_impact_state" not in src

    def test_the_model_is_no_longer_asked_for_a_timeline_or_a_cta(self):
        src = self._source()
        assert "recommended_cta" not in src
        assert '"timeline"' not in src

    def test_the_contacts_stay(self):
        """They are matched in Python from this account's own contact rows,
        the Discovery Areas still list them, and the feature-mapping contract
        pins the field."""
        assert '"target_contacts"' in self._source()

    def test_the_account_evidence_stays(self):
        """Only its rendering went. It is the publication gate - a play with no
        verifiable evidence is still dropped - and it sets the priority, the
        discovery-area split and the sort order."""
        src = self._source()
        assert "no verifiable evidence - play dropped" in src
        assert '"account_evidence": verified' in src or "account_evidence" in src

    def test_the_scale_statement_stays(self):
        """Composed in Python from named fields, still shown on Discovery
        Areas, still indexed for Strategy Chat."""
        assert '"scale_statement"' in self._source()

    def test_the_opportunity_corpus_suggests_no_timeline(self):
        import inspect

        from app.services.retrieval import corpus
        assert "Suggested timeline" not in inspect.getsource(corpus)
