"""A filing's evidence carries the filing's own link - or none at all.

The client, 6 Oct: *"Make evidence sources clickable"*. The example they gave
was a catalyst whose evidence read `australia_post_2024-FY_annual_report.pdf
p.11` and stopped there. The filing's URL was in the account's own
`_filings_index.csv` the whole time and never reached the evidence row, so a
seller could read the claim and not open the document behind it.

The half of this that matters more is the other half: a filing with no URL on
record must stay plain text. `filings_register` already states the rule -
*"use document_url where available and source_page_url as the fallback. Do not
use local_path. Where both source URLs are blank, please exclude that record."*
- and a link invented for a document nobody can open is worse than no link.

Run: python -m pytest tests/test_filing_evidence_links.py -v
"""

import csv
import importlib.util
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval import corpus

AR = "australia_post_2024-FY_annual_report.pdf"
DOC_URL = "https://auspost.com.au/content/annual-report-2024.pdf"
PAGE_URL = "https://auspost.com.au/about-us/investor-centre"

COLUMNS = ["company", "reporting_period", "fiscal_year", "document_title",
           "document_url", "source_page_url", "local_path", "crawl_route",
           "download_status"]


def _index(tmp_path: Path, rows: list) -> list:
    """A compliance_filings file set: the list CSV plus the PDFs beside it.

    Shaped exactly like `dataset_file_paths` returns it - [(original_name,
    path)] - including the one CSV, because that CSV is where the links live
    and the caller filters it out before reading the PDFs.
    """
    index = tmp_path / "_filings_index.csv"
    with open(index, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in COLUMNS})
    files = [("_filings_index.csv", str(index))]
    for row in rows:
        name = row.get("_pdf")
        if name:
            pdf = tmp_path / name
            pdf.write_bytes(b"%PDF-1.4 test")
            files.append((name, str(pdf)))
    return files


class TestTheLinkIsTakenFromTheFilingsList:

    def test_document_url_reaches_the_pdf_it_names(self, tmp_path):
        files = _index(tmp_path, [{
            "company": "AUSTRALIA POST", "reporting_period": "2024-FY",
            "document_url": DOC_URL,
            "local_path": "/Users/crawler/filings/australia_post_2024-FY_annual_report.pdf",
            "_pdf": AR,
        }])
        assert corpus._filing_urls(files) == {AR: DOC_URL}

    def test_source_page_url_is_the_fallback(self, tmp_path):
        files = _index(tmp_path, [{
            "company": "AUSTRALIA POST", "reporting_period": "2024-FY",
            "source_page_url": PAGE_URL,
            "local_path": "C:\\crawl\\australia_post_2024-FY_annual_report.pdf",
            "_pdf": AR,
        }])
        assert corpus._filing_urls(files) == {AR: PAGE_URL}

    def test_document_url_wins_over_source_page_url(self, tmp_path):
        files = _index(tmp_path, [{
            "document_url": DOC_URL, "source_page_url": PAGE_URL,
            "local_path": AR, "_pdf": AR,
        }])
        assert corpus._filing_urls(files)[AR] == DOC_URL

    def test_a_collision_suffixed_filename_still_joins(self, tmp_path):
        """`fetch_filings.place` appends `__row<n>` when two different documents
        would land on one name. The index row knows nothing of that suffix."""
        name = "australia_post_2024-FY_annual_report__row41.pdf"
        files = _index(tmp_path, [{
            "document_url": DOC_URL, "local_path": AR, "_pdf": name,
        }])
        assert corpus._filing_urls(files) == {name: DOC_URL}

    def test_a_blank_local_path_joins_on_company_and_period(self, tmp_path):
        """The crawler falls back to `{company}_{period}_row{src_row}` and the
        index does not carry `src_row`, so the exact name cannot be rebuilt."""
        name = "anz_holdings_new_zealand_limited_2025-fy_row507.pdf"
        files = _index(tmp_path, [{
            "company": "ANZ HOLDINGS (NEW ZEALAND) LIMITED",
            "reporting_period": "2025-FY", "document_url": DOC_URL,
            "local_path": "", "_pdf": name,
        }])
        assert corpus._filing_urls(files) == {name: DOC_URL}


class TestNothingIsInvented:
    """Each of these must come back with no entry for the PDF. An absent key is
    what keeps the evidence row's `source_url` None and the chip flat."""

    def test_a_row_with_neither_url_contributes_nothing(self, tmp_path):
        files = _index(tmp_path, [{
            "company": "AUSTRALIA POST", "reporting_period": "2024-FY",
            "local_path": AR, "_pdf": AR,
        }])
        assert corpus._filing_urls(files) == {}

    def test_local_path_is_never_used_as_the_link(self, tmp_path):
        """The client's rule, 18 Sep. It names a folder on the crawler's
        machine, so it is a join key here and nothing else."""
        local = "/Users/crawler/filings/australia_post_2024-FY_annual_report.pdf"
        files = _index(tmp_path, [{"local_path": local, "_pdf": AR}])
        urls = corpus._filing_urls(files)
        assert urls == {}
        assert local not in urls.values()

    def test_a_non_http_url_is_not_a_link(self, tmp_path):
        files = _index(tmp_path, [{
            "document_url": "file:///C:/crawl/ar.pdf", "local_path": AR, "_pdf": AR,
        }])
        assert corpus._filing_urls(files) == {}

    def test_two_filings_for_one_period_are_ambiguous_and_stay_unlinked(self, tmp_path):
        """One bank filed two documents for 2025-FY. Both PDFs fall back to the
        company-and-period name, so neither can be told from the other - and a
        guessed link is worse than none."""
        a = "cimb_group_holdings_berhad_2025-fy_row509.pdf"
        b = "cimb_group_holdings_berhad_2025-fy_row510.pdf"
        files = _index(tmp_path, [
            {"company": "CIMB GROUP HOLDINGS BERHAD", "reporting_period": "2025-FY",
             "document_url": "https://cimb.com/a.pdf", "local_path": "", "_pdf": a},
            {"company": "CIMB GROUP HOLDINGS BERHAD", "reporting_period": "2025-FY",
             "document_url": "https://cimb.com/b.pdf", "local_path": "", "_pdf": b},
        ])
        assert corpus._filing_urls(files) == {}

    def test_a_filing_with_no_row_at_all_stays_unlinked(self, tmp_path):
        files = _index(tmp_path, [{"document_url": DOC_URL,
                                   "local_path": "some_other_report.pdf"}])
        files.append(("orphan.pdf", str(tmp_path / "orphan.pdf")))
        (tmp_path / "orphan.pdf").write_bytes(b"%PDF-1.4")
        assert "orphan.pdf" not in corpus._filing_urls(files)

    def test_no_filings_list_at_all_is_not_an_error(self, tmp_path):
        pdf = tmp_path / AR
        pdf.write_bytes(b"%PDF-1.4")
        assert corpus._filing_urls([(AR, str(pdf))]) == {}


class TestTheFilenameRuleMatchesTheCrawlerThatWroteTheFiles:
    """`_clean_filing_name` is a copy of `fetch_filings._clean_name`, which is
    in `scripts/` and outside the application package. The copy is what the
    join depends on, so the two are compared rather than assumed equal: a
    change to one that is not mirrored here would silently unlink every
    filing on every account."""

    @staticmethod
    def _crawler():
        path = (Path(__file__).resolve().parents[2] / "scripts" / "fetch_filings.py")
        if not path.exists():
            pytest.skip("scripts/fetch_filings.py is not in this checkout")
        spec = importlib.util.spec_from_file_location("_fetch_filings", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    @pytest.mark.parametrize("raw", [
        "australia_post_2024-FY_annual_report",
        "ANZ Bank NZ Ltd DS Mar26",
        "report (final) v2",
        "pt_bank_cimb_niaga_tbk_2025-fy",
        "a//b\\c:d*e?f",
        "  leading and trailing  ",
        "x" * 200,
        "日本語_report",
    ])
    def test_the_two_cleaners_agree(self, raw):
        assert corpus._clean_filing_name(raw) == self._crawler()._clean_name(raw)
