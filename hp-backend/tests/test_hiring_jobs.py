"""Which job openings count for an account (Hiring_Signals_Rule_Set_Final.docx).

The Executive Dashboard's job postings tile and the Hiring Signals page both
count this selection, so these rules are pinned once here:

  - country check on column M against the account's code in column E; blank
    kept; a location naming no country kept (client answer, 1 Oct)
  - two-code rows ("MY; SG") go to whichever account the location names
  - last 12 months on first_seen_at, counted back from the PredictLeads pull
    date; no first_seen_at is dropped
  - open and closed both count

Run: python -m pytest tests/test_hiring_jobs.py -v
"""

from datetime import date

from app.services.hp import hiring_jobs
from app.services.hp.hiring_jobs import (
    account_country_code,
    location_in_country,
    select_jobs,
    window_start,
)

RECENT = "2026-09-10T02:00:00Z"


def job(location="", code="AU", name="AUSTRALIA POST - AU", seen=RECENT,
        title="Manager Programs", status="closed"):
    return {"location": location, "account_country_code": code,
            "company_name": name, "first_seen_at": seen, "title": title,
            "status": status}


# -- country check ------------------------------------------------------------

def test_own_country_is_kept():
    assert location_in_country("Cremorne, Victoria, Australia", "AU")


def test_other_country_is_dropped():
    assert not location_in_country("Austin, Texas, United States", "AU")


def test_blank_location_is_kept():
    assert location_in_country("", "AU")
    assert location_in_country(None, "AU")


def test_location_naming_no_country_is_kept():
    """Client answer 1 Oct: treated as the account's own country."""
    for loc in ("Columbus, OH", "Europe", "Americas", "Perth, WA",
                "Hanoi Capital Region"):
        assert location_in_country(loc, "AU"), loc


def test_longest_name_wins():
    """'Papua New Guinea' is not 'Guinea', 'North Korea' is not 'Korea'."""
    assert not location_in_country("Pyongyang, North Korea", "KR")
    assert location_in_country("Seoul, South Korea", "KR")
    assert location_in_country("Seoul, Korea", "KR")


def test_vietnam_alias():
    assert location_in_country("Hanoi, Viet Nam", "VN")


def test_country_inside_a_word_is_not_matched():
    """'Indiana' is not India, 'New South Wales' names no country."""
    assert location_in_country("Indianapolis, Indiana", "AU")
    assert location_in_country("Sydney, New South Wales", "AU")


# -- the account's own code ---------------------------------------------------

def test_two_code_rows_resolve_by_account_name():
    rows = [job(code="MY; SG",
                name="JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG")]
    assert account_country_code("JABIL CIRCUIT SDN BHD - MY", rows) == "MY"
    assert account_country_code("JABIL CIRCUIT (SINGAPORE) PTE LTD - SG", rows) == "SG"


def test_name_without_suffix_falls_back_to_the_rows_code():
    rows = [job(code="AU", name="BUNNINGS GROUP LIMITED")]
    assert account_country_code("BUNNINGS GROUP LIMITED", rows) == "AU"


def test_two_code_rows_split_between_the_two_accounts():
    shared = "JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG"
    rows = [job("Penang, Malaysia", "MY; SG", shared, title="A"),
            job("Singapore, Singapore", "MY; SG", shared, title="B"),
            job("", "MY; SG", shared, title="C"),
            job("Austin, Texas, United States", "MY; SG", shared, title="D")]
    my = select_jobs("JABIL CIRCUIT SDN BHD - MY", rows)
    sg = select_jobs("JABIL CIRCUIT (SINGAPORE) PTE LTD - SG", rows)
    assert [r["title"] for r in my.jobs] == ["A", "C"]
    assert [r["title"] for r in sg.jobs] == ["B", "C"]
    assert my.dropped_other_country == 2


def test_no_code_skips_the_country_check_and_says_so():
    rows = [{"location": "Austin, Texas, United States", "first_seen_at": RECENT}]
    out = select_jobs("Astra", rows)
    assert len(out.jobs) == 1
    assert out.country_code == ""
    assert out.notes


# -- 12-month window ----------------------------------------------------------

def test_window_ends_at_the_pull_date_not_today():
    assert date(2026, 9, 18) == hiring_jobs.PREDICTLEADS_PULL_DATE
    assert window_start() == date(2025, 9, 18)


def test_window_start_clamps_month_end():
    assert window_start(date(2024, 2, 29)) == date(2023, 2, 28)


def test_older_and_undated_jobs_are_dropped():
    rows = [job(seen="2025-09-18T00:00:00Z", title="edge"),
            job(seen="2025-09-17T23:00:00Z", title="old"),
            job(seen="", title="undated"),
            job(seen=RECENT, title="recent")]
    out = select_jobs("AUSTRALIA POST - AU", rows)
    assert [r["title"] for r in out.jobs] == ["edge", "recent"]
    assert (out.dropped_older, out.dropped_undated) == (1, 1)


def test_open_and_closed_both_count():
    rows = [job(status="closed"), job(status=""), job(status="open")]
    assert len(select_jobs("AUSTRALIA POST - AU", rows).jobs) == 3


def test_basis_records_what_was_dropped():
    rows = [job("Tokyo, Japan"), job(seen="2015-03-21T00:00:00Z"), job()]
    basis = select_jobs("AUSTRALIA POST - AU", rows).basis()
    assert basis["account_country_code"] == "AU"
    assert basis["window_start"] == "2025-09-18"
    assert basis["window_end"] == "2026-09-18"
    assert basis["dropped_other_country"] == 1
    assert basis["dropped_older_than_window"] == 1


# -- one selection for every reader -------------------------------------------

def test_every_dropped_row_is_kept_with_its_reason():
    rows = [job("Tokyo, Japan", title="abroad"), job(seen="2015-03-21T00:00:00Z", title="old"),
            job(seen="", title="undated"), job(title="kept")]
    out = select_jobs("AUSTRALIA POST - AU", rows)
    assert [r["title"] for r in out.jobs] == ["kept"]
    assert [(r["title"], why) for r, why in out.excluded] == [
        ("abroad", "location outside AU"),
        ("old", "first seen before 2025-09-18"),
        ("undated", "no first_seen_at")]


def test_selection_is_idempotent_on_its_own_output():
    """The split script writes the selected rows; the app selects them again."""
    rows = [job("Tokyo, Japan"), job(seen="2015-03-21T00:00:00Z"), job(), job("Sydney, Australia")]
    once = select_jobs("AUSTRALIA POST - AU", rows).jobs
    assert select_jobs("AUSTRALIA POST - AU", once).jobs == once


def test_account_jobs_reads_the_dataset_and_selects(monkeypatch):
    from app.services.extractors import datasets
    rows = [job("Tokyo, Japan"), job(title="kept")]
    monkeypatch.setattr(datasets, "read_dataset_records",
                        lambda _account_id, key, **_: rows if key == "job_openings" else [])
    monkeypatch.setattr(datasets, "account_display_name",
                        lambda *_: "AUSTRALIA POST - AU")
    out = hiring_jobs.account_jobs("acc-1")
    assert [r["title"] for r in out.jobs] == ["kept"]
    assert out.dropped_other_country == 1


def test_postings_summary_carries_the_sample_roles():
    from app.services.extractors.hiring_signals import postings_summary
    jobs = [job(title=t) for t in ("A", "B", "A", "C", "D", "E", "F")]
    assert postings_summary(jobs)["sample_roles"] == ["A", "B", "C", "D", "E"]
