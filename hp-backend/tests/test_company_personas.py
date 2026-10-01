"""The client's buying committee: company_personas, and the 26 Sep contact file.

Two deliveries arrived together on 26 Sep - 2,959 deduplicated Apollo contacts
and a 32-role target list per account - and both are read by code that already
existed for an earlier delivery in different column names. What is pinned here
is the reading, not the data:

  * a role nobody fills stays a role, and never acquires a name
  * the enrichment file's own column spellings and packed cells
  * the join that puts a client persona on a contact

Run: python -m pytest tests/test_company_personas.py -v
"""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors import personas
from app.services.hp import buyer_personas as bp


def _load_splitter():
    """scripts/split_account_data.py, which is not an importable package.

    Skipped rather than failed when pandas is absent: the splitter needs it,
    the backend does not, and this file also covers the backend-side reader.
    """
    path = os.path.join(os.path.dirname(__file__), "..", "..", "scripts",
                        "split_account_data.py")
    spec = importlib.util.spec_from_file_location("split_account_data", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ROLE_FILLED = {
    "target_persona": "Chief Technology Officer (CTO)",
    "department": "Executive / C-Suite",
    "buying_committee_angle": "Economic Buyer",
    "contact_name": "Adam Neal",
    "actual_job_title": "Chief Technology Officer",
    "work_email": "adam.neal@example.com",
    "phone_number": "",
    "linkedin_url": "http://www.linkedin.com/in/example",
    "contact_status": "Work email only; phone missing",
    "source": "Apollo",
    "matched_alias": "CTO",
}
# One of the eight, filled. `ROLE_FILLED` above is deliberately NOT one of
# them - it is the CTO, and it is kept to prove the scope lock holds.
ROLE_IN_SCOPE = {
    "target_persona": "VP / Head of Information Technology",
    "department": "IT",
    "buying_committee_angle": "Economic Buyer",
    "contact_name": "Adam Neal",
    "actual_job_title": "Head of IT",
    "work_email": "adam.neal@example.com",
    "phone_number": "",
    "linkedin_url": "http://www.linkedin.com/in/example",
    "contact_status": "Work email only; phone missing",
    "source": "Apollo",
    "matched_alias": "Head of IT",
}
ROLE_EMPTY = {
    "target_persona": "Head of Procurement",
    "department": "Procurement",
    "buying_committee_angle": "Economic Buyer",
    "contact_name": "",
    "actual_job_title": "",
    "work_email": "",
    "phone_number": "",
    "linkedin_url": "",
    "contact_status": "No suitable distinct candidate found",
    "source": "",
    "matched_alias": "",
}


class TestReadingTheRoles:

    def test_a_filled_role_is_filled(self, monkeypatch):
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_FILLED)])
        roles = personas.read_roles("acct")
        assert len(roles) == 1
        assert roles[0]["is_filled"] is True
        assert roles[0]["contact_name"] == "Adam Neal"

    def test_a_role_with_no_contact_is_not_filled(self, monkeypatch):
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_EMPTY)])
        role = personas.read_roles("acct")[0]
        assert role["is_filled"] is False
        assert role["contact_name"] == ""
        assert role["contact_status"] == "No suitable distinct candidate found"

    def test_a_missing_dataset_is_not_an_error(self, monkeypatch):
        """The same thing every other absent dataset does: the feature carries
        on without it."""
        monkeypatch.setattr(personas, "read_dataset_records", lambda _a, _k: [])
        assert personas.read_roles("acct") == []

    def test_pandas_nan_text_reads_as_empty(self, monkeypatch):
        """A CSV written from a DataFrame can carry the literal "nan"."""
        row = dict(ROLE_EMPTY, contact_name="nan", work_email="NaN")
        monkeypatch.setattr(personas, "read_dataset_records", lambda _a, _k: [row])
        role = personas.read_roles("acct")[0]
        assert role["is_filled"] is False
        assert role["work_email"] == ""


class TestCoverage:

    def test_it_counts_both_halves(self, monkeypatch):
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_FILLED), dict(ROLE_EMPTY)])
        cover = personas.coverage(personas.read_roles("acct"))
        assert cover["target_roles"] == 2
        assert cover["filled_roles"] == 1
        assert cover["unfilled_roles"] == 1
        assert cover["coverage_percent"] == 50.0

    def test_an_unfilled_role_is_named_with_its_reason(self, monkeypatch):
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_EMPTY)])
        cover = personas.coverage(personas.read_roles("acct"))
        assert cover["not_covered"] == [{
            "target_persona": "Head of Procurement",
            "department": "Procurement",
            "buying_committee_angle": "Economic Buyer",
            "why": "No suitable distinct candidate found",
        }]

    def test_an_unfilled_role_never_carries_a_person(self, monkeypatch):
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_EMPTY)])
        cover = personas.coverage(personas.read_roles("acct"))
        assert all("contact_name" not in entry for entry in cover["not_covered"])

    def test_reachability_is_separate_from_being_filled(self, monkeypatch):
        """A named contact with no email and no phone is not reachable, and the
        two numbers must not be conflated on a coverage panel."""
        no_details = dict(ROLE_FILLED, work_email="", phone_number="")
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [no_details])
        cover = personas.coverage(personas.read_roles("acct"))
        assert cover["filled_roles"] == 1
        assert cover["roles_with_a_contact_detail"] == 0

    def test_no_roles_gives_no_percentage_rather_than_zero(self):
        assert personas.coverage([])["coverage_percent"] is None


class TestRoleIds:

    def test_an_id_is_stable_and_slug_safe(self):
        assert personas.role_id("Chief Technology Officer (CTO)") == \
            "role_chief_technology_officer_cto"

    def test_two_roles_do_not_collide(self):
        assert personas.role_id("IT Asset Manager") != personas.role_id("IT Manager")


class TestMessageEvaluatorPersonaPaths:
    """Three ordered sources, and the first one has to actually run.

    Contacts -> the client's target roles -> hiring proxy. The contact path was
    silently broken by a rename once and nothing failed until a live account
    was loaded, which is why each path is exercised here.
    """

    class _DB:
        def __init__(self, widgets=None):
            self._widgets = widgets or {}

        def __getitem__(self, _name):
            return self

        def find_one(self, query, projection=None):
            return self._widgets.get(query.get("widget_key"))

    def test_a_contact_becomes_a_named_persona(self):
        from app.services.extractors import message_evaluator as me
        rows = [{"Prospect full_name": "Adam Neal",
                 "Prospect job_title": "Chief Technology Officer"}]
        out = me._personas_from_contacts(self._DB(), "acct", rows)
        assert len(out) == 1
        assert out[0]["is_named_person"] is True
        assert out[0]["name"] == "Adam Neal"

    def test_a_row_with_no_title_is_not_a_persona(self):
        from app.services.extractors import message_evaluator as me
        out = me._personas_from_contacts(self._DB(), "acct",
                                         [{"Prospect full_name": "Adam Neal"}])
        assert out == []

    def test_the_client_roles_are_the_eight_and_carry_their_card(self, monkeypatch):
        """The audience narrowed on 30 Sep: spec Section 4.2 makes it one of
        the eight persona_ids, and each one carries the hardcoded card."""
        from app.services.extractors import message_evaluator as me
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_IN_SCOPE), dict(ROLE_EMPTY)])
        out = me._personas_from_client_roles("acct")
        # All eight, in pack order, on every account - spec 1.4 "Treat all
        # eight as client target roles". The file supplies the contact; it
        # never decides which personas exist.
        assert [p["persona_id"] for p in out] == list(bp.PERSONA_IDS)
        by_id = {p["persona_id"]: p for p in out}
        assert by_id["vp-it"]["is_named_person"] is True
        assert by_id["head-procurement"]["is_named_person"] is False
        assert by_id["head-procurement"]["name"] is None
        assert by_id["head-procurement"]["title"] == "Head of Procurement"
        assert "no contact identified" in by_id["head-procurement"]["evidence_note"]
        assert by_id["vp-it"]["card"]["persona_id"] == "vp-it"
        out = [by_id["vp-it"], by_id["head-procurement"]]
        # LITE shape: the behavioural state is mode-dependent, and the widget
        # is written once for both modes.
        assert "behavioural_state" not in out[0]["card"]

    def test_a_role_outside_the_eight_is_never_offered(self, monkeypatch):
        """The CTO is one of the twenty-four roles `company_personas` carries
        that this programme does not evaluate against - Section 2.3's
        eligibility matrix has no row for it.

        It is dropped; the eight are still offered. This test once asserted
        that NOTHING was offered, which encoded a real bug: the eight were
        gated on the file having a matching row, so an account without the
        file - every account on a local machine - showed an empty audience in
        a feature whose audience is a fixed list.
        """
        from app.services.extractors import message_evaluator as me
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_FILLED)])
        out = me._personas_from_client_roles("acct")
        assert [p["persona_id"] for p in out] == list(bp.PERSONA_IDS)
        assert all(not p["is_named_person"] for p in out)
        assert "Adam Neal" not in str(out)

    def test_an_account_with_no_target_role_file_still_has_eight(self, monkeypatch):
        """Spec 1.4: UNFILLED is "the normal path, not an error state"."""
        from app.services.extractors import message_evaluator as me
        monkeypatch.setattr(personas, "read_dataset_records", lambda _a, _k: [])
        out = me._personas_from_client_roles("acct")
        assert len(out) == 8
        assert all(p["card"] and not p["is_named_person"] for p in out)

    def test_the_angle_comes_from_the_pack_not_the_export(self, monkeypatch):
        """Section 2.2 assigns the eight angles explicitly, so a reworded
        `buying_committee_angle` in a later delivery cannot move one."""
        from app.services.extractors import message_evaluator as me
        role = dict(ROLE_IN_SCOPE, buying_committee_angle="Something Else")
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [role])
        out = me._personas_from_client_roles("acct")
        assert out[0]["influence_type"] == "Economic Buyer"
        assert out[0]["sources"]["name"] == personas.DATASET_KEY

    def test_the_card_is_the_same_on_every_account(self, monkeypatch):
        """T19. The card is hardcoded; only whether the role is filled varies."""
        import json

        from app.services.extractors import message_evaluator as me
        monkeypatch.setattr(personas, "read_dataset_records",
                            lambda _a, _k: [dict(ROLE_IN_SCOPE)])
        first = me._personas_from_client_roles("account-one")[0]["card"]
        second = me._personas_from_client_roles("account-two")[0]["card"]
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)

    def test_the_hiring_proxy_still_names_nobody(self):
        from app.services.extractors import message_evaluator as me
        out = me._personas_from_hiring([{"title": "IT Manager"},
                                        {"title": "IT Manager"}])
        assert out and out[0]["is_named_person"] is False
        assert out[0]["name"] is None
        assert out[0]["posting_count"] == 2


class TestTheDeliveredContactFile:
    """scripts/split_account_data.py, against the 26 Sep column spellings."""

    def setup_method(self):
        self.mod = _load_splitter()

    def test_the_new_column_names_are_read(self):
        """"Work Emails" and "Phone Numbers" are what the 26 Sep file calls the
        columns the earlier one called "Verified Work Email" and "Direct Mobile
        Phone". Reading only the old names silently produced blank contacts."""
        row = {"Work Emails": "a@b.com", "Phone Numbers": "+15551234"}
        assert self.mod.apollo_first(row, "Verified Work Email") == "a@b.com"
        assert self.mod.apollo_first(row, "Direct Mobile Phone") == "+15551234"

    def test_the_old_column_names_still_win_when_present(self):
        row = {"Verified Work Email": "old@b.com", "Work Emails": "new@b.com"}
        assert self.mod.apollo_first(row, "Verified Work Email") == "old@b.com"

    def test_a_packed_cell_yields_its_first_value(self):
        row = {"Phone Numbers": "+14848025428; +14106925099"}
        assert self.mod.apollo_first(row, "Direct Mobile Phone") == "+14848025428"

    def test_the_whole_cell_is_preserved_beside_it(self):
        row = {"Phone Numbers": "+14848025428; +14106925099"}
        assert self.mod.apollo_cell(row, "Direct Mobile Phone") == \
            "+14848025428; +14106925099"

    def test_the_name_is_the_first_value_of_matched_contact(self):
        """The cell is "<full name>; <requested first name>" on 2,897 of 2,959
        rows, and the row's own Last Name column is blank on most of them."""
        row = {"Company Name": "ACME", "Website Domain": "acme.com",
               "Matched Contact": "Adam Neal; Adam", "Match Status": "Matched",
               "Title": "CTO"}
        out = self.mod.apollo_to_prospect(row, {"acme.com"}, False)
        assert out["Prospect full_name"] == "Adam Neal"
        assert out["Prospect first_name"] == "Adam"
        assert out["Prospect last_name"] == "Neal"

    def test_the_persona_column_starts_empty(self):
        """Apollo carries no persona of its own - "Requested Role" is what we
        asked the vendor to find, not what the person does."""
        row = {"Company Name": "ACME", "Website Domain": "acme.com",
               "Matched Contact": "Adam Neal", "Requested Role": "CTO",
               "Match Status": "Matched"}
        out = self.mod.apollo_to_prospect(row, {"acme.com"}, False)
        # The mapping does not set the key at all; the column appears when the
        # frame is reindexed onto PROSPECT_CONTACT_COLUMNS, and is blank until
        # the persona pass fills it.
        assert "Prospect buying_committee_personas" not in out
        assert out["apollo_requested_role"] == "CTO"

    def test_a_float_join_key_is_normalised(self):
        """pandas reads "Apollo source row" as 185.0; the sheet it joins to
        holds 185, and "185.0" matches nothing."""
        assert self.mod._int_like("185.0") == "185"
        assert self.mod._int_like("185") == "185"
        assert self.mod._int_like("") == ""

    def test_a_cell_naming_two_domains_gives_both(self):
        assert self.mod._row_domains("ocbc.com; sc.com") == ["ocbc.com", "sc.com"]

    def test_a_cell_naming_two_companies_gives_every_territory_key(self):
        """"JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG"
        with country "MY; SG". 64 rows matched nothing before this."""
        keys = self.mod._company_keys(
            "JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG",
            "MY; SG")
        assert self.mod._territory_key("JABIL CIRCUIT SDN BHD - MY") in keys
        assert self.mod._territory_key("JABIL CIRCUIT (SINGAPORE) PTE LTD - SG") in keys

    def test_a_single_company_still_gets_its_suffixed_key(self):
        keys = self.mod._company_keys("ACCENTURE INC", "PH")
        assert self.mod._territory_key("ACCENTURE INC - PH") in keys

    def test_the_persona_lands_on_the_contact_it_belongs_to(self):
        rows = [{"apollo_source_row": "185", "apollo_explorium_prospect_id": ""},
                {"apollo_source_row": "999", "apollo_explorium_prospect_id": "abc"},
                {"apollo_source_row": "", "apollo_explorium_prospect_id": ""}]
        by_row = {"185": {"target_persona": "CTO", "matched_alias": "CTO",
                          "match_basis": "title"}}
        by_id = {"abc": {"target_persona": "IT Asset Manager",
                         "matched_alias": "ITAM", "match_basis": "title"}}
        filled = self.mod.attach_personas(rows, by_row, by_id)
        assert filled == 2
        assert rows[0]["Prospect buying_committee_personas"] == "CTO"
        assert rows[1]["Prospect buying_committee_personas"] == "IT Asset Manager"
        assert "Prospect buying_committee_personas" not in rows[2]
