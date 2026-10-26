"""A C-Suite tag is honoured only when the title names an executive role
(stakeholder_map.seniority_band, rule c_suite_corroboration).

Client, 26 Oct: Sumitomo's Toshikazu Nambu, tagged c_suite, has the corrected
title "Director Vice chairman". A chairman is a board executive, so he stays
C-Suite rather than dropping to Manager.

Run: python -m pytest tests/test_seniority_band.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.stakeholder_map import seniority_band


@pytest.mark.parametrize("title", [
    "Director Vice chairman",
    "Chairman",
    "Vice Chairman and Representative Director",
    "Chairwoman of the Board",
    "Chairperson",
    "Chief Technology Officer",
    "CEO",
    "President",
    "Managing Director",
])
def test_an_executive_title_keeps_c_suite(title):
    assert seniority_band("c_suite", title) == ("C-Suite", False)


@pytest.mark.parametrize("title", [
    "CIO Office",                       # a department, not the person
    "Chairman's Office Manager",        # likewise
    "Analyst",
    "Head of Chair Manufacturing",      # "chair" alone is not "chairman"
])
def test_a_title_that_does_not_confirm_it_is_banded_manager(title):
    assert seniority_band("c_suite", title) == ("Manager", True)


@pytest.mark.parametrize("level, band", [
    ("staff", "Individual Contributor"),
    ("manager", "Manager"),
    ("head", "Director"),
])
def test_the_26_oct_corrected_levels(level, band):
    assert seniority_band(level, "Anything")[0] == band
