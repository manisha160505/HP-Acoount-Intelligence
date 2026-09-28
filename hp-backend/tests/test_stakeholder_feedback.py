"""The 27 September client feedback on the Stakeholder Map.

Four items, §4.1-4.4:

  4.1  "please remove 'Intent = 0' ... we are not sharing Intent at contact
       level" - the line was a contact count under the wrong word, and the
       count that fed it is gone from the payload
  4.2  "let's drop the 3 ... filters - Influence, Priority and HP Relevance as
       these are hard to defend" - taken through the whole module: the
       department roster is no longer split by HP relevance, and the roster is
       ordered by seniority rather than by the composite score
  4.3  "let's replace it to Explorium + Contacts Waterfall Tools" - one source
       label on every contact, with the internal provenance key untouched
  4.4  "let's drop the entire Entry Path tab altogether" - including the
       sentence the RAG corpus used to write from it

The line this file exists to hold: the scores stop being SHOWN, they do not
stop being COMPUTED. Content Studio still decides who may be named in copy
from `hp_relevance_band`, `source` and `is_priority_contact`, and the talking
points still bound a contact's claimed authority by `influence_type`. Every
one of those is asserted below, so a later tidy-up cannot quietly take them.

Run: python -m pytest tests/test_stakeholder_feedback.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from app.services.extractors import stakeholder_map as sm

ACCOUNT_ID = "6ab7ef16dc090e37050c56dd"


def _row(name, title, dept, level, **extra):
    row = {
        "Prospect full_name": name,
        "Prospect job_title": title,
        "Prospect job_department_main": dept,
        "Prospect job_level_main": level,
        "Contact professions_email": "%s@example.com" % name.split()[0].lower(),
        "Prospect prospect_id": name.replace(" ", "_").lower(),
    }
    row.update(extra)
    return row


ROWS = [
    _row("Zoe Abbott", "Chief Information Officer", "IT", "cxo",
         apollo_matched_contact="Zoe Abbott"),          # Apollo row, C-Suite
    _row("Adam Best", "Chief Financial Officer", "Finance", "cxo"),  # Source A
    _row("Cara Doyle", "VP Engineering", "Engineering", "vp"),
    _row("Ben Ellis", "IT Procurement Manager", "IT", "manager"),
    _row("Dana Frost", "Software Engineer", "Engineering", "individual"),
]


class _Collection:
    def __init__(self, db, name):
        self.db, self.name = db, name

    def find_one(self, query, *_a, **_k):
        if self.name == "accounts":
            return {"name": "Test Co"}
        return None                      # no registered files, no cached widget

    def update_one(self, _filter, update, upsert=False):
        payload = update["$set"]
        self.db.written[payload["widget_key"]] = payload


class _DB:
    """Just enough Mongo to run the extractor."""

    def __init__(self):
        self.written = {}

    def __getitem__(self, name):
        return _Collection(self, name)


@pytest.fixture
def widgets(monkeypatch):
    db = _DB()
    monkeypatch.setattr(sm, "get_db", lambda: db)
    monkeypatch.setattr("app.services.extractors.datasets.get_db", lambda: db)
    monkeypatch.setattr(sm, "_read_dataset_records",
                        lambda _aid, key, **_k: ROWS if key == "prospect_contacts" else [])
    monkeypatch.setattr(sm.personas, "read_roles", lambda _aid: [])
    monkeypatch.setattr(sm, "generate_stakeholder_talking_points",
                        lambda _aid, _c, _n: {"widget_key": "stakeholder_talking_points",
                                              "status": "empty", "data": {}})
    sm.extract_stakeholder_map(ACCOUNT_ID)
    return db.written


@pytest.fixture
def contacts(widgets):
    return widgets["stakeholder_contacts_grid"]["data"]["contacts"]


@pytest.fixture
def influence(widgets):
    return widgets["stakeholder_influence_map"]["data"]


# --------------------------------------------------------------- 4.1
class TestTheIntentLineIsGone:

    def test_the_contacts_grid_no_longer_counts_contacts_by_source(self, widgets):
        """It was rendered as "Intent: 0 - Contacts: 22".

        Neither number was an intent score; both were provenance counts, and
        the first was printed under the word Intent.
        """
        assert "source_breakdown" not in widgets["stakeholder_contacts_grid"]["data"]

    def test_the_roster_itself_is_unaffected(self, contacts):
        assert len(contacts) == len(ROWS)


# --------------------------------------------------------------- 4.2
class TestTheScoresStillExist:
    """Dropped from the interface, not from the record.

    Content Studio reads three of these to decide who may be named in copy and
    in what order; the talking-points prompt reads influence_type to bound what
    it may claim about a contact's authority.
    """

    @pytest.mark.parametrize("field", ["influence_type", "priority",
                                       "hp_relevance_band", "stakeholder_score",
                                       "is_priority_contact", "score_components"])
    def test_the_field_is_still_on_every_contact(self, contacts, field):
        assert all(field in c for c in contacts)

    def test_content_studio_can_still_tell_the_two_sources_apart(self, contacts):
        by_name = {c["full_name"]: c for c in contacts}
        assert by_name["Zoe Abbott"]["source"] == "Apollo"
        assert by_name["Adam Best"]["source"] == "Source A"


class TestTheRosterIsOrderedBySeniority:

    def test_the_grid_leads_with_the_c_suite(self, contacts):
        assert [c["full_name"] for c in contacts] == [
            "Adam Best", "Zoe Abbott",      # C-Suite, then by name
            "Cara Doyle",                   # VP
            "Ben Ellis",                    # Manager
            "Dana Frost",                   # Individual Contributor
        ]

    def test_every_department_carries_its_whole_roster(self, influence, contacts):
        seen = [cid for g in influence["department_groups"] for cid in g["contact_ids"]]
        assert sorted(seen) == sorted(c["contact_id"] for c in contacts)

    def test_a_department_lists_its_members_most_senior_first(self, influence):
        groups = {g["department"]: g for g in influence["department_groups"]}
        it = groups["Information Technology"]["contact_ids"]
        assert it == ["zoe_abbott", "ben_ellis"]

    def test_departments_are_ordered_by_headcount(self, influence):
        counts = [g["total_count"] for g in influence["department_groups"]]
        assert counts == sorted(counts, reverse=True)

    def test_an_unknown_seniority_band_sorts_last(self):
        assert sm.seniority_rank("C-Suite") < sm.seniority_rank("Manager")
        assert sm.seniority_rank("Something Else") == len(sm.SENIORITY_ORDER)


# --------------------------------------------------------------- 4.3
class TestTheSourceLabel:

    def test_every_contact_reads_the_same_label(self, contacts):
        assert {c["source_label"] for c in contacts} == {
            "Explorium + Contacts Waterfall Tools"}

    def test_an_apollo_row_and_a_source_a_row_read_alike(self, contacts):
        by_name = {c["full_name"]: c for c in contacts}
        assert (by_name["Zoe Abbott"]["source_label"]
                == by_name["Adam Best"]["source_label"])

    def test_the_word_apollo_is_not_shown_anywhere(self, contacts):
        assert all("Apollo" not in c["source_label"] for c in contacts)


# --------------------------------------------------------------- 4.4
class TestEntryPathIsGone:

    def test_no_ranking_is_published(self, influence):
        assert "ranked_entry_path" not in influence

    def test_the_weights_behind_it_are_kept(self, influence, contacts):
        """The composite still runs; it just no longer faces a reader."""
        assert influence["score_weights"] == sm.COMPOSITE_WEIGHTS
        assert all(isinstance(c["stakeholder_score"], int) for c in contacts)


class TestTheCorpusDoesNotRecycleWhatWasDropped:
    """Deleting a panel is not enough if the index still narrates it."""

    def _source(self):
        import inspect

        from app.services.retrieval import corpus
        return inspect.getsource(corpus)

    def test_the_entry_path_sentence_is_not_written(self):
        assert "Recommended entry path by department" not in self._source()

    def test_the_stakeholder_documents_do_not_report_hp_relevant_counts(self):
        src = self._source()
        assert "HP-relevant." not in src
        assert "hp_relevant_count" not in src

    def test_the_influence_tag_is_not_counted_back_at_the_reader(self):
        """The tag left the cards and the filters; a chat answer built from
        this index must not go on reporting "Budget Holder 4"."""
        src = self._source()
        assert "Stakeholders by influence type" not in src
        assert "influence_breakdown" not in src
        assert "buying_group_coverage" not in src

    def test_seniority_is_kept(self):
        """It is read off the title in the file, and it orders the roster."""
        assert "seniority_breakdown" in self._source()
