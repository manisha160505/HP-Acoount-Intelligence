"""Loading the client's user sheet: matching, the plan, credentials and apply.

Run: python -m pytest tests/test_user_import.py -v
"""

import openpyxl
import pytest

from app.core.security import verify_password
from app.services import user_import
from regen_fakes import FakeDb


def _sheet(tmp_path, sales, admins):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Country", "Sales Territory ID", "Sales Territory Name", "EAM", "IAM"])
    for row in sales:
        ws.append(row)
    adm = wb.create_sheet("Admin")
    for email in admins:          # no header row, as in the client's file
        adm.append([email])
    path = tmp_path / "sheet.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def db():
    d = FakeDb()
    for name in ("MALAYAN BANKING BHD - MY", "PUBLIC BANK BHD - MY", "BUNNINGS GROUP LIMITED",
                 "AUSTRALIAN SUBMARINE CORPORATION [ASC] - AU"):
        d["accounts"].insert_one({"name": name, "status": "active"})
    return d


@pytest.fixture
def sheet(tmp_path):
    return user_import.read_sheet(_sheet(tmp_path, [
        ("MY", 169890, "MALAYAN BANKING BHD - MY", "Seller.One@Example.com", "seller.two@example.com"),
        ("MY", 184582, "PUBLIC BANK BHD  -  MY", "seller.three@example.com", "seller.two@example.com"),
        ("AU", 216239, "BUNNINGS GROUP LIMITED- AU", "seller.four@example.com", "-"),
        ("AU", 217303, "WESTPAC BANKING CORPORATION - AU", "-", "seller.five@example.com"),
        ("PH", 1, "BROKEN ROW - PH", "not an email", None),
    ], ["admin.one@example.com", "admin.two@example.com", "admin.one@example.com"]))


def _accounts(db):
    return [{"id": str(a["_id"]), "name": a["name"]} for a in db["accounts"].find({})]


def _plan(db, sheet, existing=None):
    return user_import.build_plan(sheet, _accounts(db), existing or {})


def _by_email(plan):
    return {p.email: p for p in plan.people}


def test_the_sheet_reads_both_tabs_and_skips_dashes_and_junk(sheet):
    assert sheet.admins == ["admin.one@example.com", "admin.two@example.com"]
    assert sheet.rows[0].emails == ["seller.one@example.com", "seller.two@example.com"]
    assert sheet.rows[2].emails == ["seller.four@example.com"]
    assert sheet.invalid == ["BROKEN ROW - PH: 'not an email'"]


def test_matching_is_exact_or_through_the_reviewed_aliases_only(db, sheet):
    plan = _plan(db, sheet)
    how = {s: h for s, _, h in plan.matched}
    assert how["MALAYAN BANKING BHD - MY"] == "exact"
    assert how["PUBLIC BANK BHD  -  MY"] == "exact"       # spacing only
    assert how["BUNNINGS GROUP LIMITED- AU"] == "alias"
    assert plan.unmatched == ["WESTPAC BANKING CORPORATION - AU", "BROKEN ROW - PH"]
    assert plan.accounts_not_in_sheet == ["AUSTRALIAN SUBMARINE CORPORATION [ASC] - AU"]


def test_one_seller_collects_every_account_they_are_named_on(db, sheet):
    people = _by_email(_plan(db, sheet))
    kalyn = people["seller.two@example.com"]
    assert kalyn.role == "user"
    assert kalyn.account_names == ["MALAYAN BANKING BHD - MY", "PUBLIC BANK BHD - MY"]
    assert len(kalyn.account_ids) == 2
    # Named only on an unmatched row: created, with nothing assigned.
    assert people["seller.five@example.com"].account_ids == []
    assert people["admin.one@example.com"].role == "admin"


def test_existing_users_are_marked_and_a_role_clash_is_reported(db, sheet):
    plan = _plan(db, sheet, {"seller.two@example.com": {"role": "user"},
                             "admin.two@example.com": {"role": "user"}})
    people = _by_email(plan)
    assert people["seller.two@example.com"].status == "exists"
    assert people["admin.two@example.com"].status == "role_differs"
    assert people["seller.one@example.com"].status == "new"


def test_passwords_are_generated_once_and_kept_across_runs(db, sheet, tmp_path):
    cred = tmp_path / "creds.xlsx"
    plan = _plan(db, sheet)
    pw = user_import.load_credentials(cred)
    added = user_import.fill_passwords(plan, pw)
    assert len(added) == len(plan.people) and all(len(v) == 12 for v in pw.values())
    user_import.write_credentials(cred, plan, pw)

    again = user_import.load_credentials(cred)
    assert again == pw
    assert user_import.fill_passwords(_plan(db, sheet), again) == []
    assert len(set(pw.values())) == len(pw)


def test_apply_creates_everyone_with_the_files_passwords(db, sheet, tmp_path):
    plan = _plan(db, sheet)
    pw = {}
    user_import.fill_passwords(plan, pw)
    counts = user_import.apply(db, plan, pw, super_admin_email="bridge@gmail.com",
                               super_admin_password="bridge-pass-1")
    assert counts == {"created": len(plan.people), "accounts_synced": 0, "super_admin_created": 1}
    rachel = db["users"].find_one({"email": "seller.one@example.com"})
    assert verify_password(pw["seller.one@example.com"], rachel["password_hash"])
    assert rachel["must_change_password"] is True and rachel["role"] == "user"
    boss = db["users"].find_one({"email": "bridge@gmail.com"})
    assert boss["role"] == "super_admin" and boss["must_change_password"] is False
    assert db["user_audit"].count_documents({"action": "user.created"}) == len(plan.people) + 1


def test_apply_twice_creates_nothing_and_touches_no_password(db, sheet):
    plan = _plan(db, sheet)
    pw = {}
    user_import.fill_passwords(plan, pw)
    user_import.apply(db, plan, pw, super_admin_email="bridge@gmail.com", super_admin_password="x")
    before = {u["email"]: u["password_hash"] for u in db["users"].find({})}
    existing = {u["email"]: u for u in db["users"].find({})}
    plan2 = user_import.build_plan(sheet, _accounts(db), existing)
    counts = user_import.apply(db, plan2, pw, super_admin_email="bridge@gmail.com",
                               super_admin_password=None)
    assert counts["created"] == 0 and counts["super_admin_created"] == 0
    assert {u["email"]: u["password_hash"] for u in db["users"].find({})} == before


def test_sync_accounts_sets_existing_sellers_to_the_sheet(db, sheet):
    db["users"].insert_one({"email": "seller.two@example.com", "role": "user", "account_ids": []})
    existing = {u["email"]: u for u in db["users"].find({})}
    plan = _plan(db, sheet, existing)
    pw = {}
    user_import.fill_passwords(plan, pw)
    assert "seller.two@example.com" not in pw
    counts = user_import.apply(db, plan, pw, super_admin_email="bridge@gmail.com",
                               super_admin_password="x", sync_accounts=True)
    assert counts["accounts_synced"] == 1
    assert len(db["users"].find_one({"email": "seller.two@example.com"})["account_ids"]) == 2


def test_apply_refuses_without_every_password(db, sheet):
    plan = _plan(db, sheet)
    with pytest.raises(ValueError, match="no password"):
        user_import.apply(db, plan, {}, super_admin_email="bridge@gmail.com",
                          super_admin_password="x")
    assert db["users"].count_documents({}) == 0


def test_apply_refuses_to_promote_an_existing_non_super_admin(db, sheet):
    db["users"].insert_one({"email": "bridge@gmail.com", "role": "user"})
    plan = _plan(db, sheet, {"bridge@gmail.com": {"role": "user"}})
    pw = {}
    user_import.fill_passwords(plan, pw)
    with pytest.raises(ValueError, match="refusing to promote"):
        user_import.apply(db, plan, pw, super_admin_email="bridge@gmail.com",
                          super_admin_password="x")


def test_apply_needs_the_super_admin_password_the_first_time(db, sheet):
    plan = _plan(db, sheet)
    pw = {}
    user_import.fill_passwords(plan, pw)
    with pytest.raises(ValueError, match="SUPER_ADMIN_PASSWORD"):
        user_import.apply(db, plan, pw, super_admin_email="bridge@gmail.com",
                          super_admin_password=None)
