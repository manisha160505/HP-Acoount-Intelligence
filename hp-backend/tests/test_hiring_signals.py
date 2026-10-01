"""Hiring Signals page blocks (Hiring_Signals_Rule_Set_Final.docx).

The Australia Post worked example was checked against the real file when this
was built: 100 jobs, 60% hybrid, the same family bars, the same 30 tags in the
same order and the same seven cards with the same counts. These tests pin the
rules behind those numbers on small hand-made rows.

Run: python -m pytest tests/test_hiring_signals.py -v
"""

import json

from app.services.extractors.hiring_signals import (
    _own_name_keys,
    family_breakdown,
    postings_summary,
    tech_tags,
    theme_cards,
)
from app.services.hp.hiring_themes import THEMES, theme_for


def job(code="13-1111.00", family="Business and Financial Operations",
        title="Business Analyst", tags=(), contract=(), first="2026-09-01",
        last="2026-09-10"):
    return {"onet_data": json.dumps({"code": code, "family": family}) if code else "",
            "title": title, "tags": json.dumps(list(tags)),
            "contract_types": json.dumps(list(contract)),
            "first_seen_at": first + "T00:00:00Z", "last_seen_at": last + "T00:00:00Z"}


# -- theme table --------------------------------------------------------------

def test_first_matching_row_wins():
    """Exact codes above beat the broad 'all other' rows below them."""
    assert theme_for("15-1212.00").key == "security"
    assert theme_for("11-3021.00").key == "it_operations"     # not knowledge workers
    assert theme_for("15-1232.00").key == "it_operations"     # not technical
    assert theme_for("11-1011.00").key == "leadership"
    assert theme_for("15-2051.00").key == "technical"
    assert theme_for("11-9199.02").key == "knowledge_workers"


def test_minor_group_prefixes():
    assert theme_for("41-3091.00").key == "mobile_sales"
    assert theme_for("41-2031.00").key == "frontline"
    assert theme_for("23-2011.00").key == "office_support"
    assert theme_for("23-1011.00").key == "knowledge_workers"
    assert theme_for("25-1011.00").key == "education"
    assert theme_for("53-3032.00").key == "frontline"


def test_blank_code_has_no_theme():
    assert theme_for("") is None
    assert theme_for(None) is None


def test_nine_themes_with_the_example_name():
    assert len(THEMES) == 9
    assert theme_for("15-2051.00").name == "Technical, engineering & design experts"


# -- tiles --------------------------------------------------------------------

def test_hybrid_counts_hybrid_remote_and_work_from_home():
    jobs = [job(contract=["hybrid"]), job(contract=["Remote"]),
            job(contract=["all levels", "work from home"]), job(contract=["full time"])]
    s = postings_summary(jobs)
    assert (s["job_postings"], s["hybrid_count"], s["hybrid_pct"]) == (4, 3, 75)
    assert s["window_label"] == "Last 12 months"


def test_seen_range_is_earliest_first_to_latest_last():
    s = postings_summary([job(first="2026-08-05", last="2026-08-20"),
                          job(first="2026-09-01", last="2026-09-17")])
    assert (s["seen_from"], s["seen_to"]) == ("2026-08-05", "2026-09-17")


# -- families -----------------------------------------------------------------

def test_six_largest_families_then_other_including_unclassified():
    jobs = []
    for i, n in enumerate((7, 6, 5, 4, 3, 2, 1)):
        jobs += [job(family="F%d" % i)] * n
    jobs.append(job(code="", family=""))
    out = family_breakdown(jobs)
    assert [b["family"] for b in out["bars"]] == ["F0", "F1", "F2", "F3", "F4", "F5", "Other"]
    assert out["bars"][-1]["count"] == 2          # F6 + the job with no family
    assert sum(b["count"] for b in out["bars"]) == out["total"] == 29


# -- tech tags ----------------------------------------------------------------

def test_tags_count_jobs_and_drop_own_name_and_non_tech():
    jobs = [job(tags=["Australia Post", "SAP", "SAP", "Contractor"]),
            job(tags=["SAP", "Power BI", "Social Media"]),
            job(tags=["Power BI", "Auspost"])]
    own = _own_name_keys("AUSTRALIA POST - AU", "auspost.com.au")
    out = tech_tags(jobs, own)
    assert out["tags"] == [{"tag": "SAP", "jobs": 2}, {"tag": "Power BI", "jobs": 2}]
    assert set(out["removed"]) == {"Australia Post", "Contractor", "Social Media", "Auspost"}


def test_tag_that_starts_the_company_name_is_its_own_name():
    own = _own_name_keys("TOYOTA GROUP - JP", "toyota-global.com")
    out = tech_tags([job(tags=["Toyota", "SAP"])], own)
    assert [t["tag"] for t in out["tags"]] == ["SAP"]


def test_at_most_thirty_tags():
    out = tech_tags([job(tags=["T%d" % i for i in range(40)])], set())
    assert len(out["tags"]) == 30


# -- cards --------------------------------------------------------------------

def test_card_titles_most_frequent_first_and_more_jobs():
    jobs = ([job(title="Duty Manager")] * 2 + [job(title="Analyst A")] * 3
            + [job(title=t) for t in ("B", "C", "D", "E", "F")])
    card = theme_cards(jobs)["cards"][0]
    assert card["theme"] == "Office knowledge workers"
    assert card["job_count"] == 10
    assert card["titles"][:2] == [{"title": "Analyst A", "posted": 3},
                                  {"title": "Duty Manager", "posted": 2}]
    assert len(card["titles"]) == 5
    assert card["more_jobs"] == 10 - (3 + 2 + 1 + 1 + 1)
    assert card["hp_product"] == "HP EliteBook 6 G2 Series"


def test_cards_largest_first_ties_in_rule_set_order():
    jobs = ([job(code="41-3091.00")] * 4 + [job(code="15-1212.00")] * 4
            + [job(code="13-1111.00")] * 9 + [job(code="")])
    out = theme_cards(jobs)
    assert [c["theme_key"] for c in out["cards"]] == [
        "knowledge_workers", "security", "mobile_sales"]
    assert out["unthemed_jobs"] == 1


def test_only_themes_with_jobs_get_a_card():
    assert len(theme_cards([job(code="25-1011.00")])["cards"]) == 1
