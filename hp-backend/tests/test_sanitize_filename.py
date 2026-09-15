"""Regression tests for the stored-filename sanitizer.

The character class in `sanitize_filename` once read `[^a border-zA-Z0-9_\\.-]`.
The stray "border-" parsed as the literals a/space/b/o/r/d/e plus the range r-z,
so the twelve lowercase letters outside that range (c f g h i j k l m n p q) were
each replaced with an underscore while spaces were let through:

    "My Report 2026.csv"  ->  "My Re_ort 2026._sv"

Nothing broke visibly, because the extension is appended separately by the caller
and `original_filename` is kept in the metadata - which is exactly why it went
unnoticed. These tests pin the two properties that matter: ordinary names survive
intact, and nothing that could escape the dataset directory survives at all.

Only the multi-file datasets reach this function; single-file datasets are stored
under a canonical filename and never consult it.

Run: python -m pytest tests/test_sanitize_filename.py -v
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.account_data import sanitize_filename  # noqa: E402


# ---------------------------------------------------------------------------
# The letters the old class silently ate. This is the actual bug.
# ---------------------------------------------------------------------------

def test_every_ascii_letter_and_digit_survives():
    """The regression itself: no alphanumeric may be replaced."""
    name = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    assert sanitize_filename(name) == name


@pytest.mark.parametrize("letter", list("cfghijklmnpq"))
def test_letters_outside_the_old_broken_range(letter):
    """c f g h i j k l m n p q were each turned into an underscore before."""
    assert sanitize_filename(letter) == letter


def test_real_world_names_keep_their_words():
    assert sanitize_filename("My Report 2026") == "My_Report_2026"
    assert sanitize_filename("google news") == "google_news"
    assert sanitize_filename("Car Market Apr26 - Wholesales") == "Car_Market_Apr26_-_Wholesales"
    assert sanitize_filename("news_events 2026-08") == "news_events_2026-08"


# ---------------------------------------------------------------------------
# Characters that must not reach the filesystem
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("a/b", "a_b"),          # path separator
    ("a\\b", "a_b"),         # windows separator
    ("a b", "a_b"),          # space - the old class let these through
    ("données", "donn_es"),  # non-ASCII
    ("ab#c!d", "ab_c_d"),
    ("q3 (final)", "q3__final_"),
])
def test_unsafe_characters_become_underscores(raw, expected):
    assert sanitize_filename(raw) == expected


def test_no_path_separator_ever_survives():
    assert "/" not in sanitize_filename("../../etc/passwd")
    assert "\\" not in sanitize_filename("..\\..\\windows\\system32")


def test_dot_and_dash_and_underscore_are_kept():
    """Needed so a real extension and a date range stay readable."""
    assert sanitize_filename("report.v2-final_draft") == "report.v2-final_draft"


# ---------------------------------------------------------------------------
# Degenerate input
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["", None])
def test_empty_basename_falls_back(raw):
    """An upload named ".csv" has an empty basename; it still needs a filename."""
    assert sanitize_filename(raw or "") == "dataset_file"


def test_all_unsafe_input_does_not_fall_back():
    """"#@!" sanitizes to "___", which is truthy, so the fallback must not fire."""
    assert sanitize_filename("#@!") == "___"


def test_output_is_always_a_bare_filename():
    """Whatever goes in, the result is safe to join onto the dataset directory."""
    for raw in ["../../etc/passwd", "a/b\\c", "  ", "données.csv", "#@!"]:
        out = sanitize_filename(raw)
        assert out == os.path.basename(out)
        assert not out.startswith(os.sep)


# ---------------------------------------------------------------------------
# The caller's contract: extension is appended separately, so it is never lost
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("original", [
    "My Report 2026.csv",
    "google news données.csv",
    "Q3 wholesales (final).xlsx",
    "Astra Annual Report.pdf",
])
def test_stored_filename_preserves_extension(original):
    """Mirrors how upload_account_data builds stored_filename."""
    base, ext = os.path.splitext(original)
    stored = f"google_news_1757000000_{sanitize_filename(base)}{ext}"

    assert stored.endswith(ext)
    assert " " not in stored
    assert "/" not in stored and "\\" not in stored
    assert re.fullmatch(r"[A-Za-z0-9_.-]+", stored)
