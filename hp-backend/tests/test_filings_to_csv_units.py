"""scripts/filings_to_csv.parse_unit: which currency a filing's figure is in.

Each case is a caption the 11 Oct filings actually printed.
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "scripts" / "filings_to_csv.py"
_spec = importlib.util.spec_from_file_location("filings_to_csv", _PATH)
ftc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ftc)


def currency(unit, page="", hint="", country=""):
    return ftc.parse_unit(unit, page, hint, country, False)[0]


def test_us_dollars_are_not_read_as_singapore_dollars():
    # BHP's annual report: "US$M".
    assert currency("US$M 58,760", country="AU") == "USD"


def test_singapore_dollars_still_read():
    assert currency("S$ million", country="SG") == "SGD"
    assert currency("SGD million") == "SGD"


def test_sec_table_with_a_bare_dollar_takes_the_currency_the_model_named():
    page = "(in millions, except per share amounts) Net revenues $ 34,534 $ 30,268"
    assert currency("in millions 34,534", page, hint="USD", country="KR") == "USD"


def test_a_bare_dollar_does_not_override_another_named_dollar():
    page = "NZ$ millions ... $ 1,760"
    assert currency("in millions 1,760", page, hint="USD", country="NZ") == ""


def test_no_dollar_on_the_page_stays_unresolved():
    assert currency("in millions 34,534", "Net revenues 34,534", hint="USD") == ""


def test_the_word_dollars_is_the_country_dollar_like_a_bare_dollar_sign():
    # BNZ's disclosure statement: "Dollars in Millions".
    assert currency("Dollars in Millions 3,484", country="NZ") == "NZD"
    assert currency("Dollars in Millions 3,484", country="KR") == ""


def test_philippine_peso_sign_printed_as_p_equals():
    assert currency("P= 368,532,088,776", country="PH") == "PHP"
