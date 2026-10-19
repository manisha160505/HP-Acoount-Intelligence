"""The 19 Oct shipping list -> prospect_contacts rows (scripts/upload_shipping_list_contacts.py).

The client's rules: an email tag only beside an email, catch_all and CATCH_ALL
as one tag, "unknown" and blank left blank; a phone only when there is a
number, with its line type as the tag. A number Excel stored in scientific
notation has lost its digits and is never shown.

Run: python -m pytest tests/test_shipping_list_contacts.py -v
"""

import importlib.util
import os
import sys

import pytest

pytest.importorskip("pandas")    # the scripts it imports need it; the backend does not

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")


@pytest.fixture(scope="module")
def loader():
    sys.path.insert(0, SCRIPTS)
    spec = importlib.util.spec_from_file_location(
        "upload_shipping_list_contacts", os.path.join(SCRIPTS, "upload_shipping_list_contacts.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCOUNT = {"vendor_company_name": "EXAMPLE HOLDINGS CO., LTD.", "domain": "example.com"}


def _row(**over):
    row = {"account_name": "EXAMPLE HOLDINGS CO., LTD.", "account_country": "JP",
           "full_name": "Aiko Tanaka", "job_title": "CIO", "role_department": "IT & Technology",
           "seniority": "c_suite", "person_country": "Japan", "person_city": "Tokyo",
           "email": "someone@example.com", "email_status": "valid",
           "phone": "81300000000", "phone_line_type": "LANDLINE",
           "linkedin_url": "http://www.linkedin.com/in/example",
           "committee_angle": "Economic Buyer"}
    row.update(over)
    return row


def test_a_full_row_keeps_every_column_we_load(loader):
    out, damaged = loader.convert(_row(), ACCOUNT)
    assert not damaged
    assert out["Prospect full_name"] == "Aiko Tanaka"
    assert out["Prospect job_department_main"] == "master_information_technology"
    assert out["Prospect job_level_main"] == "c_suite"
    assert out["Email"] == "someone@example.com" and out["Email Status"] == "valid"
    assert out["Mobile Phone"] == "81300000000" and out["Phone Line Type"] == "LANDLINE"
    assert out["Prospect linkedin"].endswith("/example")
    # Personas come from the title, as for every account: no committee column.
    assert "Economic Buyer" not in out.values()


@pytest.mark.parametrize("status, tag", [
    ("catch_all", "CATCH_ALL"), ("CATCH_ALL", "CATCH_ALL"), ("VERIFIED", "VERIFIED"),
    ("VALID_RISKY", "VALID_RISKY"), ("valid", "valid"),
    ("unknown", ""), ("UNKNOWN", ""), (None, ""), ("", ""),
])
def test_email_tags_as_provided_except_blank_and_unknown(loader, status, tag):
    assert loader.convert(_row(email_status=status), ACCOUNT)[0]["Email Status"] == tag


def test_no_email_means_no_email_tag(loader):
    out, _ = loader.convert(_row(email=None, email_status="unavailable"), ACCOUNT)
    assert out["Email"] == "" and out["Email Status"] == ""


def test_no_phone_means_no_phone_tag(loader):
    out, damaged = loader.convert(_row(phone=None, phone_line_type="MOBILE"), ACCOUNT)
    assert out["Mobile Phone"] == "" and out["Phone Line Type"] == "" and not damaged


def test_a_phone_without_a_line_type_shows_without_a_tag(loader):
    out, _ = loader.convert(_row(phone_line_type=None), ACCOUNT)
    assert out["Mobile Phone"] == "81300000000" and out["Phone Line Type"] == ""


def test_a_number_excel_stored_in_scientific_notation_is_dropped(loader):
    out, damaged = loader.convert(_row(phone="8.17048E+11", phone_line_type="MOBILE"), ACCOUNT)
    assert damaged
    assert out["Mobile Phone"] == "" and out["Phone Line Type"] == ""


@pytest.mark.parametrize("raw, level", [
    ("head; director", "director"), ("senior; c_suite", "c_suite"),
    ("Director", "director"), ("Manager", "manager"), ("entry", "entry"), (None, ""),
])
def test_seniority_bands_on_the_most_senior_value(loader, raw, level):
    assert loader.convert(_row(seniority=raw), ACCOUNT)[0]["Prospect job_level_main"] == level


def test_rows_carry_the_same_marker_as_every_other_account(loader):
    out, _ = loader.convert(_row(), ACCOUNT)
    assert out["apollo_matched_contact"] == "Aiko Tanaka"
    assert out["apollo_match_status"] == "Shipping list"


def test_an_account_matches_by_name_or_name_and_country(loader):
    folders = {"advantest corporation - jp": ("dir", {}), "bunnings group limited": ("dir2", {})}
    assert loader.match("ADVANTEST  CORPORATION", "JP", folders) == ("dir", {})
    assert loader.match("BUNNINGS GROUP LIMITED", "AU", folders) == ("dir2", {})
    assert loader.match("UNKNOWN CO", "JP", folders) is None
