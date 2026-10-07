"""The client's extra sources (Dhruvi, 27 Sep; opens_1 answer 10), kept in the
files the application already defines.

Filings = filings 1.csv + PredictLeads sec_filings, one list
(`_filings_index.csv`, uploaded under compliance_filings) with the 18 Sep link
rule (document_url, else source_page_url, never local_path, drop when both
blank) and the 12-month window. Tech_Breakdown is its own dataset
(tech_breakdown.csv); the Website stack card groups it by the vendor's columns.

Run: python -m pytest tests/test_filings_and_tech_breakdown.py -v
"""

import csv
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard import filings_register as fr
from app.services.extractors.tech_landscape import _parse_tech_breakdown

AS_OF = date(2026, 9, 28)


def _reg(**kw):
    row = {"document_title": "Annual Report 2025", "document_type": "ANNUAL_REPORT",
           "reporting_period": "2025-FY", "publication_date": "2026-03-31T00:00:00Z",
           "document_url": "https://example.com/ar2025.pdf",
           "source_page_url": "https://example.com/investors",
           "local_path": "/Users/someone/filings/ar2025.pdf",
           "crawl_route": "ROUTE_D_UNLISTED_DIRECT",
           "download_status": "DOWNLOADED"}
    row.update(kw)
    return row


def _pl(**kw):
    """A PredictLeads row as the split writes it into the filings list."""
    row = {"document_title": "EXL Form 10-Q filed 2026-07-28",
           "document_type": "SEC_FORM_10-Q", "publication_date": "2026-07-28",
           "document_url": "https://www.sec.gov/Archives/x/q2.htm",
           "source_page_url": "https://www.sec.gov/Archives/x/q2.htm",
           "local_path": "predictleads_sec_10-q_2026-07-28.pdf",
           "crawl_route": fr.PREDICTLEADS_CRAWL_ROUTE,
           "download_status": "GENERATED_FROM_TEXT"}
    row.update(kw)
    return row


def test_document_url_wins_and_local_path_is_never_used():
    out = fr.register([_reg()], as_of=AS_OF)
    assert out["filings"][0]["url"] == "https://example.com/ar2025.pdf"
    assert out["filings"][0]["url_field"] == "document_url"
    assert "someone" not in str(out)


def test_source_page_url_is_the_fallback():
    out = fr.register([_reg(document_url="")], as_of=AS_OF)
    assert out["filings"][0]["url"] == "https://example.com/investors"
    assert out["filings"][0]["url_field"] == "source_page_url"


def test_both_urls_blank_excludes_the_record():
    out = fr.register([_reg(document_url="", source_page_url="")], as_of=AS_OF)
    assert out["filings"] == []
    assert out["excluded"]["no_url"] == 1


def test_24_month_window_and_counts():
    rows = [_reg(), _reg(publication_date="2024-06-30", document_url="https://e.com/old.pdf")]
    out = fr.register(rows, as_of=AS_OF)
    assert out["in_window"] == 1
    assert out["excluded"]["outside_window"] == 1
    assert out["total_on_record"] == 2


def test_a_filing_13_to_24_months_old_is_now_listed():
    """Client, 6 Oct: filings 24 months (was 12)."""
    older_than_a_year = AS_OF.replace(year=AS_OF.year - 1) - __import__("datetime").timedelta(days=60)
    rows = [_reg(publication_date=older_than_a_year.isoformat(), document_url="https://e.com/fy.pdf")]
    out = fr.register(rows, as_of=AS_OF)
    assert out["in_window"] == 1 and out["window"]["rule"] == "last 24 months (client, 6 Oct)"


def test_undated_is_left_out_and_counted():
    out = fr.register([_reg(publication_date="", period_end="")], as_of=AS_OF)
    assert out["filings"] == [] and out["excluded"]["undated"] == 1


def test_predictleads_rows_are_labelled_by_source():
    out = fr.register([_reg(), _pl()], as_of=AS_OF)
    assert out["in_window"] == 2
    newest = out["filings"][0]
    assert newest["source"] == fr.SOURCE_PREDICTLEADS
    assert newest["document_on_file"] is True
    assert out["sources"] == sorted([fr.SOURCE_REGISTER, fr.SOURCE_PREDICTLEADS])


def test_same_url_from_both_sources_is_listed_once():
    same = "https://www.sec.gov/Archives/x/q2.htm"
    out = fr.register([_reg(document_url=same, publication_date="2026-07-28"), _pl()],
                      as_of=AS_OF)
    assert out["in_window"] == 1 and out["excluded"]["duplicate"] == 1


def test_every_date_format_the_filings_crawl_wrote():
    assert fr._date("2026-03-31T00:00:00Z") == date(2026, 3, 31)
    assert fr._date("2026-03-31T00:00:00+07:00") == date(2026, 3, 31)
    assert fr._date("2026/03/31") == date(2026, 3, 31)
    assert fr._date("26/08/2026") == date(2026, 8, 26)
    assert fr._date("11/02/2026") == date(2026, 2, 11)      # day first
    assert fr._date("1774207812.0") == date(2026, 3, 22)
    assert fr._date("May 12, 2026 10:00 AM") == date(2026, 5, 12)
    assert fr._date("") is None and fr._date("FY2025") is None


def test_index_rows_come_only_from_the_csv_in_the_filing_set(tmp_path):
    index = tmp_path / "_filings_index.csv"
    with open(index, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(_reg()))
        w.writeheader()
        w.writerow(_reg())
    pdf = tmp_path / "annual.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    rows = fr.index_rows_from_files([("_filings_index.csv", str(index)),
                                     ("annual.pdf", str(pdf))])
    assert len(rows) == 1 and rows[0]["document_title"] == "Annual Report 2025"


def test_predictleads_pdfs_are_recognised_by_name():
    assert fr.is_predictleads_file("predictleads_sec_6-k_2026-09-01.pdf")
    assert not fr.is_predictleads_file("sony_2026-FY_annual_report.pdf")


def test_tech_breakdown_groups_are_kept_as_delivered():
    out = _parse_tech_breakdown([{
        "Cms": "Enterprise: Adobe Experience Manager | Other: WordPress 5.3, Adobe Experience Manager",
        "Seo Title": "Other: SEO_TITLE", "Hosting": "", "Mx": "\u2014",
        "Business Id": "abc", "Parked": "No"}])
    # Identifier and status columns are never read as categories.
    assert [c["category"] for c in out] == ["Cms", "Seo Title"]
    cms = out[0]
    assert cms["groups"][0] == {"group": "Enterprise",
                                "technologies": ["Adobe Experience Manager"]}
    assert cms["technologies"] == ["Adobe Experience Manager", "WordPress 5.3"]
    assert cms["page_metadata"] is False and out[1]["page_metadata"] is True


def test_tech_breakdown_empty():
    assert _parse_tech_breakdown([]) == []
