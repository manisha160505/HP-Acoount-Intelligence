"""A row's own label outranks the page's unit caption.

A financial-highlights page carries one caption fixing the unit for its money
columns - Astra's reads *"(dalam miliar Rupiah)"* - and `detect_unit` reads it
off the page. The bug this file pins is what happened to every row in that table
that is NOT money.

The parser applied the page unit to every non-percentage row, so the dashboard
published:

    Earnings per Share (Rp)          IDR 810 billion
    Net Asset Value per Share (Rp)   IDR 5,692 billion
    Current Ratio (x)                IDR 1.20 billion
    Outstanding Share (in millions)  IDR 40,214 billion

against filed figures of Rp 810 per share, Rp 5,692 per share, a ratio of 1.20,
and 40,214 million shares. The numbers were right; the units were wrong by about
a trillion. That is worse than publishing nothing - a seller quoting earnings per
share off that card repeats a figure the filing never stated, and every figure on
the card is labelled "Filed", which is exactly the claim that makes it credible.

Percentages were already handled, because the value's own notation settles them.
The gap was rows whose unit is declared by the label rather than by the value or
the page.

Run: python -m pytest tests/test_financial_units.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.dashboard.priorities import _format_value
from app.services.retrieval.financials import detect_label_unit

PAGE_UNIT = "IDR billion"          # what the Astra highlights page states


def rendered(label: str, value: float) -> str:
    """The figure as the dashboard would print it, page caption applied unless
    the label overrides it."""
    unit, _why = detect_label_unit(label)
    return _format_value(value, unit or PAGE_UNIT)


class TestRatiosAreNotMoney:
    """A label ending "(x)" states the figure is a ratio."""

    @pytest.mark.parametrize("label,value,expected", [
        ("Current Ratio (x)", 1.2, "1.20 x"),
        ("Liabilities to Assets Ratio (x)", 0.4, "0.40 x"),
        ("Liabilities to Equity Ratio (x)", 0.7, "0.70 x"),
    ])
    def test_a_ratio_row_is_not_priced_in_rupiah(self, label, value, expected):
        assert rendered(label, value) == expected

    def test_the_currency_is_gone_entirely(self):
        assert "IDR" not in rendered("Current Ratio (x)", 1.2)


class TestPerShareAmountsAreNotBillions:
    """A label ending "per Share (Rp)" states rupiah per share."""

    @pytest.mark.parametrize("label,value,expected", [
        ("Earnings per Share (Rp)", 810.0, "IDR 810 per share"),
        ("Net Asset Value per Share (Rp)", 5692.0, "IDR 5,692 per share"),
        ("Interim Dividend per Share (Rp)", 98.0, "IDR 98 per share"),
        ("Final Dividend per Share (Rp)", 2925.0, "IDR 2,925 per share"),
    ])
    def test_a_per_share_row_keeps_its_own_unit(self, label, value, expected):
        assert rendered(label, value) == expected

    def test_a_footnote_marker_glued_to_the_label_does_not_defeat_the_match(self):
        """The filing prints "4Earnings per Share (Rp)" - the footnote number
        runs into the label. The unit is decided by the label's END, so the
        prefix is harmless; this pins that rather than leaving it to luck."""
        assert rendered("4Earnings per Share (Rp)", 810.0) == "IDR 810 per share"

    def test_the_scale_word_is_gone(self):
        """"billion" on a per-share figure is the whole defect."""
        assert "billion" not in rendered("Earnings per Share (Rp)", 810.0)


class TestShareCountsAreNotCurrency:

    def test_a_share_count_in_millions_is_not_rupiah(self):
        assert (rendered("Outstanding Share (in millions)", 40214.0)
                == "40,214 million shares")


class TestMoneyRowsAreUntouched:
    """The fix must not reach rows the page caption correctly describes."""

    @pytest.mark.parametrize("label,value,expected", [
        ("Net Revenue", 323392.0, "IDR 323,392 billion"),
        ("Gross Profit", 71444.0, "IDR 71,444 billion"),
        ("Total Assets", 507366.0, "IDR 507,366 billion"),
        ("Total Equity", 290812.0, "IDR 290,812 billion"),
        ("Net Working Capital", 31168.0, "IDR 31,168 billion"),
    ])
    def test_a_money_row_still_takes_the_page_unit(self, label, value, expected):
        assert detect_label_unit(label) == (None, None)
        assert rendered(label, value) == expected

    def test_a_label_merely_containing_rp_is_not_matched(self):
        """The patterns anchor to the end of the label. A row that happens to
        mention a currency mid-label is not making a unit declaration."""
        assert detect_label_unit("Rp denominated borrowings") == (None, None)

    def test_an_x_inside_a_word_does_not_make_a_ratio(self):
        assert detect_label_unit("Capex") == (None, None)
        assert detect_label_unit("Tax Expense") == (None, None)


class TestTheBasisIsRecorded:
    """Every unit decision carries its reason, the way the page and title
    detectors already do - so a figure on screen can be traced to the statement
    that fixed its unit."""

    def test_the_quote_names_the_label_it_read(self):
        unit, why = detect_label_unit("Current Ratio (x)")
        assert unit == "x"
        assert "Current Ratio (x)" in why
        assert "ratio" in why.lower()

    def test_an_unmatched_label_claims_nothing(self):
        assert detect_label_unit("Net Revenue") == (None, None)
        assert detect_label_unit("") == (None, None)
        assert detect_label_unit(None) == (None, None)


class TestABareCurrencyStillLeadsItsAmount:
    """A figure in the currency's own units, with no scale word after it.

    Astra's dividend table states amounts in rupiah - "Total Dividend (Rp) 390"
    - which reconciles against its own rows: interim 98 + final 308 = 406, the
    prior year's total. Those are rupiah per share, and the page caption's
    "trillion" never applied to them.
    """

    def test_a_currency_with_no_scale_reads_as_currency_first(self):
        assert _format_value(390.0, "IDR") == "IDR 390"

    def test_the_dividend_rows_no_longer_read_as_trillions(self):
        unit, _why = detect_label_unit("Jumlah Dividen (Rp) | Total Dividend (Rp)")
        assert unit == "IDR"
        assert _format_value(390.0, unit) == "IDR 390"

    def test_a_scaled_currency_is_unchanged(self):
        assert _format_value(323392.0, "IDR billion") == "IDR 323,392 billion"

    def test_a_non_currency_unit_still_follows_its_amount(self):
        assert _format_value(40214.0, "million shares") == "40,214 million shares"
        assert _format_value(1.2, "x") == "1.20 x"
