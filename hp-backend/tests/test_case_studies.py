"""Choosing an HP case study to support a recommendation - and refusing to.

Five features shipped an empty proof-point slot for as long as they have
existed. This is what fills them, and the thing it has to get right is not
finding a study - it is declining to.

The client's instruction is explicit:

    "Where there is no clear relationship between the account-level data and the
    available HP Product/Service/Solution information or Case Studies, we should
    not force a match."

A proof point is the one place this product cites a named third party by name,
under HP's logo, with a link a seller may forward to a customer. An irrelevant
one is worse than an empty slot, so much of what follows tests the refusals.

The corpus is small and lopsided - most of its named studies are 3D printing,
and collaboration has exactly one - so empty is the normal answer for several
surfaces and must stay that way rather than being softened later.

Run: python -m pytest tests/test_case_studies.py -v
"""

import os
import sys
from typing import ClassVar

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import case_studies as cs


class FakeCollection:
    """The corpus, without a database.

    `find` returns everything but the version document, which is all `match`
    asks of it: the line a study speaks to is computed in Python, not queried,
    because it comes from whichever of two unreliable fields actually names an
    offering.
    """

    def __init__(self, studies, version=None):
        self.studies = studies
        self.version = version

    def find(self, query, _projection=None):
        excluded = (query.get("_id") or {}).get("$ne")
        return iter([s for s in self.studies if s.get("_id") != excluded])

    def find_one(self, query, _projection=None):
        wanted = query.get("_id")
        if wanted == cs.VERSION_DOC_ID:
            if not self.version:
                return None
            return {"_id": wanted, "knowledge_version": self.version}
        return next((s for s in self.studies if s.get("_id") == wanted), None)


class FakeWidgets:
    """The account_widgets collection, holding whatever other surfaces stored."""

    def __init__(self, widgets=None):
        self.widgets = widgets or {}

    def find_one(self, query, _projection=None):
        return self.widgets.get(query.get("widget_key"))


def fake_db(studies, version=None, widgets=None):
    return {cs.COLLECTION: FakeCollection(studies, version),
            "account_widgets": FakeWidgets(widgets)}


def cited(surface, *customers):
    """A stored widget for `surface` citing each of `customers`."""
    records = [{"hp_proof_point_detail": {"study_id": c.lower(), "customer": c}}
               for c in customers]
    path = cs.SURFACE_PATHS[surface]
    if surface == cs.SURFACE_CONTENT:
        records = [{"generated": r} for r in records]
    return {surface: {"data": {path[1]: records}}}


def study(customer, product, industry="Other", tags=(), outcome=None,
          challenge=None, offering=None):
    return {
        "_id": customer.lower(),
        "customer": customer,
        "product_featured": product,
        "hp_offering": offering,
        "industry": industry,
        "signal_tags": list(tags),
        "headline": "%s used %s." % (customer, product or offering),
        "outcome": outcome,
        "challenge": challenge,
        "use_case": "Doing the thing.",
        "why_relevant": "Relevant when the thing is needed.",
        "source_url": "https://h20195.www2.hp.com/%s.pdf" % customer.lower(),
    }


CORPUS = [
    study("Kinepolis", "HP EliteBook", "Media & Entertainment",
          ("Fleet-Refresh",), outcome="Setup time fell by 71%."),
    study("DLG", "HP EliteBook", "Other", ("Digital-Transformation",),
          outcome="A 15% reduction in device failures."),
    study("Carlsberg", "HP EliteBook", "Consumer Goods"),
    study("Siemens", "HP Z Workstation", "Automotive",
          ("Engineering-Product-Development",)),
    study("City of Bonn", "HP Wolf Security", "Other"),
    study("STERNAUTO", "HP Managed Print Services", "Automotive"),
    study("Aereco", "HP Multi Jet Fusion", "Technology",
          ("Industrial-Manufacturing", "Production-Optimization")),
]


class TestItRefusesRatherThanForcing:
    """The half that matters most."""

    def test_a_line_with_no_studies_returns_nothing(self):
        """The corpus above holds no collaboration study, so the collaboration
        area gets silence rather than the nearest thing."""
        assert cs.lines_for_area("Collaboration") == (cs.LINE_COLLABORATION,)
        assert cs.proof_point_for(
            fake_db(CORPUS), cs.lines_for_area("Collaboration"),
            industry="Automotive") is None

    def test_industry_alone_never_produces_a_match(self):
        """An automotive study is not evidence about a product nobody asked
        about. Without a line filter there is nothing to be relevant TO, and
        matching on industry alone is the forced match the client forbids."""
        assert cs.match(fake_db(CORPUS), (), industry="Automotive") == []

    def test_an_unknown_hp_line_matches_nothing(self):
        assert cs.lines_for_hp_line("HP Something Invented") == ()
        assert cs.proof_point_for(
            fake_db(CORPUS), cs.lines_for_hp_line("HP Something Invented")) is None

    def test_an_empty_corpus_returns_nothing_rather_than_raising(self):
        assert cs.proof_point_for(fake_db([]), (cs.LINE_PC,)) is None

    def test_a_study_naming_no_offering_is_never_reachable(self):
        """A row with neither a tag nor an offering speaks to no line, and an
        unreachable study is the right outcome - the alternative is filing it
        under whichever card happens to ask first."""
        nameless = study("Anon Ltd", "", "Automotive")
        assert cs.canonical_line(nameless) == ""
        for line in (cs.LINE_PC, cs.LINE_PRINT, cs.LINE_SECURITY):
            assert cs.match(fake_db([nameless]), (line,)) == []


class TestTheCanonicalLine:
    """What a study is about, from two fields that each lie in their own way."""

    def test_the_offering_beats_a_wrong_product_tag(self):
        """Verbatim from the corpus: a study tagged HP EliteBook that is
        entirely about managed device services. The tag is HP's, and wrong."""
        assert cs.canonical_line({
            "product_featured": "HP EliteBook",
            "hp_offering": "HP Managed Device Services",
        }) == cs.LINE_DEVICE_SERVICES

    def test_an_untagged_study_is_still_placed(self):
        """Ulster University, the corpus's only collaboration study, carries no
        product tag at all. Joining on the tag made it invisible."""
        assert cs.canonical_line({
            "product_featured": "",
            "hp_offering": "HP Managed Collaboration Services",
        }) == cs.LINE_COLLABORATION

    def test_the_tag_is_used_when_no_offering_was_read(self):
        assert cs.canonical_line({
            "product_featured": "HP Wolf Security", "hp_offering": None,
        }) == cs.LINE_SECURITY

    def test_free_text_spelling_does_not_matter(self):
        """The offering is what the model read out of HP's prose, so "HP Z
        Workstations", "HP Z workstation" and "HP Z Workstation" all appear."""
        for spelling in ("HP Z Workstations", "HP Z workstation",
                         "HP Z Workstation", "Z by HP"):
            assert cs.canonical_line({"hp_offering": spelling}) == cs.LINE_WORKSTATION

    def test_metal_jet_is_3d_rather_than_print(self):
        """Ordering matters: several 3D offerings contain a word a later rule
        would also claim."""
        assert cs.canonical_line({"hp_offering": "HP Metal Jet 3D printing"}) == cs.LINE_3D
        assert cs.canonical_line({"hp_offering": "HP Multi Jet Fusion"}) == cs.LINE_3D

    def test_siteprint_is_not_managed_print(self):
        """A construction layout robot has nothing to do with an MPS card."""
        assert cs.canonical_line({"hp_offering": "HP SitePrint"}) == cs.LINE_SITEPRINT


class TestItPicksTheRightOne:

    def test_the_line_filter_is_absolute(self):
        found = cs.match(fake_db(CORPUS), (cs.LINE_SECURITY,), limit=9)
        assert [s["customer"] for s in found] == ["City of Bonn"]

    def test_a_matching_industry_is_preferred(self):
        found = cs.match(fake_db(CORPUS), (cs.LINE_PC,),
                         industry="Media & Entertainment", limit=1)
        assert found[0]["customer"] == "Kinepolis"

    def test_a_stated_outcome_outranks_one_without(self):
        """Between two equally relevant studies, the one that says what
        changed is the more useful to a seller."""
        found = cs.match(fake_db(CORPUS), (cs.LINE_PC,), limit=3)
        assert found[0]["customer"] in ("Kinepolis", "DLG")
        assert found[-1]["customer"] == "Carlsberg"    # no outcome, no tags

    def test_shared_signals_lift_a_study(self):
        found = cs.match(fake_db(CORPUS), (cs.LINE_PC,),
                         signals=["Digital-Transformation"], limit=1)
        assert found[0]["customer"] == "DLG"

    def test_the_order_is_stable_across_calls(self):
        """A rerun on unchanged data must not reshuffle the proof point on a
        card - a seller who saw one reference yesterday should see it today."""
        args = (fake_db(CORPUS), (cs.LINE_PC,), "Other", ["Digital-Transformation"])
        first = [s["customer"] for s in cs.match(*args, limit=3)]
        second = [s["customer"] for s in cs.match(*args, limit=3)]
        assert first == second

    def test_two_lines_on_one_card_are_both_searched(self):
        """Client Devices asks for PCs and device services, because a fleet
        story answers a device objection as well as a laptop story does."""
        managed = study("Universidad", "HP EliteBook", "Education",
                        offering="HP Managed Device Services")
        found = cs.match(fake_db([*CORPUS, managed]),
                         cs.lines_for_area("Client Devices"), limit=9)
        names = [s["customer"] for s in found]
        assert "Universidad" in names
        assert "Kinepolis" in names
        assert "City of Bonn" not in names


class TestTheLineMapping:

    @pytest.mark.parametrize("hp_line,expected", [
        ("Z by HP Workstations", cs.LINE_WORKSTATION),
        ("HP Elite / Pro PCs", cs.LINE_PC),
        ("HP Wolf Security", cs.LINE_SECURITY),
        ("HP Enterprise Print / MPS", cs.LINE_PRINT),
        ("Poly Collaboration", cs.LINE_COLLABORATION),
        ("HP Anyware / DaaS", cs.LINE_DEVICE_SERVICES),
        ("HP Workforce Experience Platform", cs.LINE_WXP),
    ])
    def test_each_hp_line_reaches_its_lines(self, hp_line, expected):
        assert expected in cs.lines_for_hp_line(hp_line)

    @pytest.mark.parametrize("area,expected", [
        ("Client Devices", cs.LINE_PC),
        ("Endpoint Security", cs.LINE_SECURITY),
        ("Print / MPS", cs.LINE_PRINT),
        ("Device Management", cs.LINE_WXP),
        ("Collaboration", cs.LINE_COLLABORATION),
    ])
    def test_each_objection_area_reaches_its_lines(self, area, expected):
        assert expected in cs.lines_for_area(area)

    def test_the_mapping_is_case_and_space_insensitive(self):
        assert cs.lines_for_hp_line("  hp wolf security ") == (cs.LINE_SECURITY,)

    def test_every_mapped_line_is_one_a_study_can_be_given(self):
        """A typo here is invisible: the lookup returns nothing and the slot
        stays empty, looking exactly like "no study exists"."""
        known = {line for line, _ in cs.OFFERING_KEYWORDS}
        for mapping in (cs.HP_LINE_TO_LINES, cs.AREA_TO_LINES):
            for key, lines in mapping.items():
                for line in lines:
                    assert line in known, "%s -> unknown line %r" % (key, line)

    def test_every_objection_area_is_mapped(self):
        """All five areas are fixed and always rendered. One missing from the
        map is a card that can never carry a proof point."""
        for area in ("Client Devices", "Device Management", "Endpoint Security",
                     "Print / MPS", "Collaboration"):
            assert cs.lines_for_area(area), "%s reaches no line" % area


class TestIndustryNormalisation:
    """An account's industry arrives as a pile of classification systems; the
    corpus uses eleven labels. These have to meet somewhere."""

    def test_astras_real_firmographics_string(self):
        """Verbatim from Astra's record."""
        assert cs.normalise_industry(
            "automation machinery manufacturing / Other Industrial Machinery "
            "Manufacturing / Industrial machinery, nec") == "Industrial Manufacturing"

    @pytest.mark.parametrize("raw,expected", [
        ("Motor Vehicle Manufacturing", "Automotive"),
        ("Hospitals and Health Care", "Healthcare"),
        ("Higher Education", "Education"),
        ("Computer Software", "Technology"),
        ("Freight and Logistics", "Logistics"),
        ("Aerospace and Defence", "Aerospace"),
    ])
    def test_common_classifications(self, raw, expected):
        assert cs.normalise_industry(raw) == expected

    def test_a_specific_industry_beats_the_manufacturing_catch_all(self):
        """Almost every manufacturer's classification mentions manufacturing,
        so a car maker must be matched as Automotive before the broader rule
        claims it."""
        assert cs.normalise_industry("Automotive parts manufacturing") == "Automotive"
        assert cs.normalise_industry("Aircraft engine manufacturing") == "Aerospace"

    def test_an_unrecognised_industry_is_empty_not_wrong(self):
        """Industry only orders results that already matched on line, so
        returning nothing costs relevance and never correctness."""
        assert cs.normalise_industry("Zoological gardens") == ""
        assert cs.normalise_industry("") == ""
        assert cs.normalise_industry(None) == ""


class TestTheStoredProofPoint:

    def test_it_carries_what_a_seller_needs_to_cite_it(self):
        point = cs.as_proof_point(CORPUS[0])
        assert point["customer"] == "Kinepolis"
        assert point["source_url"].startswith("https://")
        assert point["source"] == "hp_case_studies"

    def test_the_outcome_is_appended_when_there_is_one(self):
        point = cs.as_proof_point(CORPUS[0])
        assert "71%" in point["text"]

    def test_a_study_with_no_outcome_is_still_a_proof_point(self):
        """Most of the corpus has no stated outcome. A named HP customer using
        the product is still something a seller can point at."""
        point = cs.as_proof_point(CORPUS[2])       # Carlsberg
        assert point is not None
        assert point["outcome"] is None
        assert "Carlsberg" in point["text"]

    def test_a_study_with_no_headline_is_not_published(self):
        assert cs.as_proof_point({"customer": "X", "headline": ""}) is None
        assert cs.as_proof_point(None) is None


class TestTieBreaking:
    """On many cards nothing matches the account's industry, so several studies
    score identically. What breaks that tie has to be defensible, because it
    decides which customer's name a seller puts in front of a client."""

    TIED: ClassVar[list] = [
        dict(study("Kinepolis", "HP EliteBook", "Media & Entertainment",
                   outcome="Setup time fell by 71%."), merged_from_assets=2),
        dict(study("DLG", "HP EliteBook", "Other",
                   outcome="A 15% reduction in device failures."),
             merged_from_assets=1),
    ]

    def test_the_fuller_study_wins_a_tie(self):
        """A study HP published across several assets has more behind it than a
        single stub, so it is the better thing to hand a customer."""
        found = cs.match(fake_db(self.TIED), (cs.LINE_PC,), limit=2)
        assert found[0]["customer"] == "Kinepolis"

    def test_the_name_is_never_the_first_tie_break(self):
        """It once was, and it put a Chilean university ahead of two equally
        relevant studies purely because "universidad" sorts late in the
        alphabet. Sorting by name is stable, not meaningful."""
        alphabetically_last = dict(
            study("Zzz Corp", "HP EliteBook", "Other"), merged_from_assets=1)
        found = cs.match(fake_db([*self.TIED, alphabetically_last]),
                         (cs.LINE_PC,), limit=3)
        assert found[0]["customer"] != "Zzz Corp"

    def test_industry_still_outranks_everything(self):
        """Source richness must never beat actual relevance."""
        thin_but_relevant = dict(
            study("Local Manufacturer", "HP EliteBook", "Industrial Manufacturing"),
            merged_from_assets=1)
        found = cs.match(fake_db([*self.TIED, thin_but_relevant]),
                         (cs.LINE_PC,), industry="Industrial Manufacturing",
                         limit=3)
        assert found[0]["customer"] == "Local Manufacturer"


class TestTheCorpusVersion:
    """A card stores the proof point it was given, so a feature's cache has to
    notice when the corpus behind it is reloaded."""

    def test_it_reports_the_loaded_version(self):
        assert cs.knowledge_version(fake_db(CORPUS, "abc123")) == "abc123"

    def test_an_unloaded_corpus_reports_an_empty_version(self):
        """Stable rather than random: a platform with no case studies loaded
        must not rebuild every feature on every run."""
        assert cs.knowledge_version(fake_db(CORPUS)) == ""
        assert cs.knowledge_version(fake_db([])) == ""

    def test_a_broken_database_does_not_raise(self):
        class Exploding:
            def find_one(self, *_a, **_k):
                raise RuntimeError("no connection")
        assert cs.knowledge_version({cs.COLLECTION: Exploding()}) == ""


class TestAttributionOnlyStudies:
    """Some source rows describe no engagement - a photograph caption, a clause
    clipped mid-word. The loader states the attribution for those instead of
    letting the model write a sentence from nothing. They are still real HP
    customers with a real link, so they stay usable - just never preferred."""

    def test_a_narrated_study_outranks_an_attribution_only_one(self):
        bare = {
            "_id": "bare", "customer": "City of Somewhere",
            "product_featured": "HP EliteBook", "hp_offering": None,
            "industry": "Other", "signal_tags": [],
            "headline": "HP published a case study with City of Somewhere "
                        "featuring HP EliteBook.",
            "outcome": None, "challenge": None,
            "attribution_only": True,
            "source_url": "https://h20195.www2.hp.com/somewhere.pdf",
        }
        found = cs.match(fake_db([bare, *CORPUS]), (cs.LINE_PC,), limit=9)
        assert found[0]["customer"] != "City of Somewhere"
        assert found[-1]["customer"] == "City of Somewhere"

    def test_it_is_still_publishable(self):
        """Better than an empty slot: it names a real HP customer and carries
        the public hp.com link a seller can forward."""
        point = cs.as_proof_point({
            "customer": "City of Somewhere",
            "headline": "HP published a case study with City of Somewhere.",
            "source_url": "https://h20195.www2.hp.com/somewhere.pdf",
        })
        assert point is not None
        assert point["outcome"] is None
        assert point["source_url"].startswith("https://")


class TestAnUnpublishableStudyNeverWinsACard:
    """Every sentence a study carried can be rejected - one in the corpus lost
    its headline that way, because each figure in it came from text clipped
    mid-sentence. It must not then win a card and render as nothing."""

    HEADLESS: ClassVar[dict] = {
        "_id": "headless", "customer": "Sculpteo", "product_featured": "HP EliteBook",
        "hp_offering": None, "industry": "Industrial Manufacturing",
        "signal_tags": [], "headline": "", "outcome": "Everything was rejected.",
        "challenge": "So was this.", "merged_from_assets": 9,
        "source_url": "https://h20195.www2.hp.com/sculpteo.pdf",
    }

    def test_it_is_not_returned_by_match(self):
        """It would otherwise outrank the rest: an outcome, a challenge and
        nine source assets all score."""
        found = cs.match(fake_db([self.HEADLESS, *CORPUS]), (cs.LINE_PC,), limit=9)
        assert "Sculpteo" not in [s["customer"] for s in found]

    def test_the_caller_still_gets_a_proof_point(self):
        point = cs.proof_point_for(fake_db([self.HEADLESS, *CORPUS]), (cs.LINE_PC,))
        assert point is not None
        assert point["customer"] != "Sculpteo"

    def test_a_corpus_of_only_unpublishable_studies_returns_none(self):
        assert cs.proof_point_for(fake_db([self.HEADLESS]), (cs.LINE_PC,)) is None


class TestCrossSurfaceAllocation:
    """The same customer was appearing on an objection card, an opportunity
    play and a messaging pillar at once. The corpus is lopsided - most of it is
    3D printing, which no PC or print surface can reach - so the handful of
    studies a given account CAN use get drawn on by every feature.

    Spreading them is worth doing, but only while it is free. These tests are
    mostly about the cases where it is not free and the repeat is correct.
    """

    def test_an_uncited_study_is_preferred_over_a_repeat(self):
        """Two equally good studies, one already on another surface: take the
        other one."""
        point = cs.allocate(fake_db(CORPUS), (cs.LINE_PC,),
                            taken={"kinepolis"})
        assert point["customer"] == "DLG"

    def test_the_best_study_is_still_taken_when_nothing_is_cited(self):
        assert cs.allocate(fake_db(CORPUS), (cs.LINE_PC,))["customer"] \
            == cs.proof_point_for(fake_db(CORPUS), (cs.LINE_PC,))["customer"]

    def test_a_line_with_one_study_repeats_rather_than_going_empty(self):
        """Collaboration holds exactly one study in the real corpus. A seller
        reading the Collaboration card needs it whether or not the Poly play
        cites the same customer - silence would be the worse answer."""
        only = study("Ulster University", "", "Education",
                     offering="HP Managed Collaboration Services")
        point = cs.allocate(fake_db([only]), (cs.LINE_COLLABORATION,),
                            taken={"ulster university"})
        assert point is not None
        assert point["customer"] == "Ulster University"

    def test_variety_never_costs_the_industry_match(self):
        """An in-industry study that is already cited beats an out-of-industry
        one that is free. Relevance is what makes a proof point persuasive;
        being unused is not something the reader can even see."""
        relevant = study("Local Manufacturer", "HP EliteBook",
                         "Industrial Manufacturing", outcome="It went well.")
        point = cs.allocate(fake_db([relevant, *CORPUS]), (cs.LINE_PC,),
                            industry="Industrial Manufacturing",
                            taken={"local manufacturer"})
        assert point["customer"] == "Local Manufacturer"

    def test_variety_never_costs_a_narrated_study(self):
        """A bare attribution - written where the source described no
        engagement - must not be preferred just because it is unused."""
        bare = {
            "_id": "bare", "customer": "City of Somewhere",
            "product_featured": "HP EliteBook", "hp_offering": None,
            "industry": "Other", "signal_tags": [], "attribution_only": True,
            "headline": "HP published a case study with City of Somewhere.",
            "outcome": None, "challenge": None,
            "source_url": "https://h20195.www2.hp.com/somewhere.pdf",
        }
        point = cs.allocate(fake_db([bare, *CORPUS]), (cs.LINE_PC,),
                            taken={"kinepolis", "dlg", "carlsberg"})
        assert point["customer"] in ("Kinepolis", "DLG")

    def test_it_carries_the_study_id_so_the_next_caller_can_exclude_it(self):
        point = cs.allocate(fake_db(CORPUS), (cs.LINE_SECURITY,))
        assert point["study_id"] == "city of bonn"

    def test_an_unreachable_line_still_returns_nothing(self):
        assert cs.allocate(fake_db(CORPUS), ()) is None
        assert cs.allocate(fake_db([]), (cs.LINE_PC,)) is None


class TestWhoYieldsToWhom:
    """Allocation must not depend on which feature was regenerated last. A
    surface yields only to the surfaces above it in `SURFACE_ORDER`, so the
    same surface wins the same study however the account is rebuilt."""

    def test_the_objection_playbook_yields_to_nobody(self):
        """It chooses first: its five areas are fixed and land on the corpus's
        thinnest lines, so it has the least room to move."""
        widgets = cited(cs.SURFACE_OPPORTUNITIES, "Kinepolis")
        assert cs.cited_above(fake_db(CORPUS, widgets=widgets),
                              "acct", cs.SURFACE_OBJECTIONS) == set()

    def test_the_map_yields_to_the_playbook_only(self):
        widgets = {**cited(cs.SURFACE_OBJECTIONS, "Kinepolis"),
                   **cited(cs.SURFACE_MESSAGING, "DLG")}
        taken = cs.cited_above(fake_db(CORPUS, widgets=widgets), "acct",
                               cs.SURFACE_OPPORTUNITIES)
        assert taken == {"kinepolis"}

    def test_content_studio_yields_to_all_three(self):
        widgets = {**cited(cs.SURFACE_OBJECTIONS, "Kinepolis"),
                   **cited(cs.SURFACE_OPPORTUNITIES, "DLG"),
                   **cited(cs.SURFACE_MESSAGING, "Carlsberg")}
        taken = cs.cited_above(fake_db(CORPUS, widgets=widgets), "acct",
                               cs.SURFACE_CONTENT)
        assert taken == {"kinepolis", "dlg", "carlsberg"}

    def test_a_surface_nobody_declared_yields_to_everything(self):
        """The safe default for a feature wired up later: it takes what is
        left rather than displacing a surface that is already built."""
        widgets = cited(cs.SURFACE_OBJECTIONS, "Kinepolis")
        assert cs.cited_above(fake_db(CORPUS, widgets=widgets),
                              "acct", "some_new_widget") == {"kinepolis"}

    def test_an_older_record_without_an_id_still_reserves_its_study(self):
        """Proof points stored before they carried an id fall back to the
        customer name, so a rebuild does not re-cite them elsewhere."""
        widgets = {cs.SURFACE_OBJECTIONS: {"data": {"cards": [
            {"hp_proof_point_detail": {"customer": "Kinepolis"}}]}}}
        assert cs.cited_above(fake_db(CORPUS, widgets=widgets),
                              "acct", cs.SURFACE_MESSAGING) == {"kinepolis"}

    def test_a_surface_with_no_proof_points_reserves_nothing(self):
        widgets = {cs.SURFACE_OBJECTIONS: {"data": {"cards": [
            {"area": "Print / MPS", "hp_proof_point_detail": None}]}}}
        assert cs.cited_above(fake_db(CORPUS, widgets=widgets),
                              "acct", cs.SURFACE_MESSAGING) == set()

    def test_a_missing_widget_is_not_an_error(self):
        assert cs.cited_above(fake_db(CORPUS), "acct", cs.SURFACE_CONTENT) == set()

    def test_every_surface_has_a_path(self):
        """A surface in the order with no path would raise mid-generation."""
        for surface in cs.SURFACE_ORDER:
            assert surface in cs.SURFACE_PATHS


class TestTheTwoKindsOfRepeat:
    """A repeat inside one document and a repeat across two features are not
    the same mistake, so they are not held to the same rule.

    The five objection cards, or the pillars of one message house, are read
    together: the same customer twice there reads as an error. Nobody reads the
    playbook and the message house side by side, so a genuinely apt study on
    both costs far less than a weak one - or an empty slot - on either.
    """

    def test_the_same_customer_is_never_cited_twice_in_one_document(self):
        """Even when it means the card carries nothing. This is the bug that
        prompted the split: one message house named the same university on two
        pillars because every alternative was taken elsewhere."""
        only_one = [study("Ulster University", "", "Education",
                          offering="HP Managed Collaboration Services")]
        assert cs.allocate(fake_db(only_one), (cs.LINE_COLLABORATION,),
                           used_here={"ulster university"}) is None

    def test_a_cross_feature_repeat_is_allowed_when_nothing_else_fits(self):
        """The same line, the same single study, but cited by another feature
        rather than by this one: the seller still gets it."""
        only_one = [study("Ulster University", "", "Education",
                          offering="HP Managed Collaboration Services")]
        point = cs.allocate(fake_db(only_one), (cs.LINE_COLLABORATION,),
                            taken={"ulster university"})
        assert point["customer"] == "Ulster University"

    def test_the_two_sets_apply_together(self):
        """`used_here` removes a study from consideration entirely; `taken`
        only pushes it down. With the best study used on this document and the
        second cited elsewhere, the third - uncited and equally good - wins."""
        point = cs.allocate(fake_db(CORPUS), (cs.LINE_PC,),
                            taken={"dlg"}, used_here={"kinepolis"})
        assert point["customer"] == "Carlsberg"

    def test_a_study_used_here_is_never_returned_even_if_it_is_the_best(self):
        for _ in range(3):      # the ranking is stable, so this is not luck
            point = cs.allocate(fake_db(CORPUS), (cs.LINE_PC,),
                                used_here={"kinepolis"})
            assert point["customer"] != "Kinepolis"

    def test_an_empty_slot_beats_a_duplicate_but_not_a_weaker_study(self):
        """Within one document the fallback is silence; across documents it is
        the best study again. Both are checked here so the two paths cannot be
        collapsed back into one by a later edit."""
        assert cs.allocate(fake_db(CORPUS), (cs.LINE_SECURITY,),
                           used_here={"city of bonn"}) is None
        assert cs.allocate(fake_db(CORPUS), (cs.LINE_SECURITY,),
                           taken={"city of bonn"})["customer"] == "City of Bonn"
