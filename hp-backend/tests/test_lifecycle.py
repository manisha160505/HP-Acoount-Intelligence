"""Section J: not recommending a product HP has stopped making.

The document's own closing sentence sets the safety direction:

    "If the Product, Service or Solution is not listed in the Lifecycle file,
    the absence of a lifecycle record does not block the recommendation."

So every uncertainty here resolves towards recommending. The failure this file
mostly guards is the opposite one - blocking a live product because the file
lists its PREDECESSOR, which is what a lifecycle file is full of.

Run: python -m pytest tests/test_lifecycle.py -v
"""

import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import lifecycle as lc

TODAY = date(2026, 9, 23)


def row(product, first, last, **over):
    base = {
        "product": product,
        "family": "Notebooks 800 Series",
        "generations": sorted(lc._generations(product)),
        "identity": sorted(lc._identity(product)),
        "first_end": first,
        "last_end": last,
        "end_dates": [d for d in (first, last) if d],
        "source": "HP lifecycle file",
    }
    base.update(over)
    return base


ROWS = [
    row("HP EliteBook 8 G1i Flip", "2025-09-30", "2027-06-30"),
    row("HP EliteBook Ultra G1i", "2024-01-31", "2026-03-31"),
    row("HP EliteDesk 8 G1i Tower", "2027-01-31", "2028-06-30"),
]


class TestTheFileMustNotBlockASuccessorProduct:
    """The rulebook sells "HP EliteBook 8 G2 Series"; the lifecycle file lists
    "HP EliteBook 8 G1i Flip". Same family, different product, and treating
    them as one would withdraw a live recommendation because the generation
    before it is being retired."""

    def test_a_g2_offering_does_not_match_a_g1i_row(self):
        out = lc.status_for("HP EliteBook 8 G2 Series", TODAY, ROWS)
        assert out["status"] == lc.NOT_LISTED
        assert out["recommendable"] is True

    def test_g1q_and_g1i_are_different_products(self):
        assert lc.status_for("HP EliteBook Ultra G1q / G1q8",
                             TODAY, ROWS)["status"] == lc.NOT_LISTED

    def test_an_offering_with_no_generation_matches_nothing(self):
        """"Mapped EliteBook / EliteDesk / ProBook deck" names a family and no
        product. It must never be blocked on one."""
        assert lc.status_for("Mapped EliteBook / EliteDesk / ProBook deck",
                             TODAY, ROWS)["status"] == lc.NOT_LISTED

    def test_the_family_alone_is_not_enough(self):
        assert lc.status_for("HP EliteBook", TODAY, ROWS)["status"] == lc.NOT_LISTED


class TestTheStatesSectionJDefines:
    def test_a_product_past_every_end_date_is_refused(self):
        out = lc.status_for("HP EliteBook Ultra G1i", TODAY, ROWS)
        assert out["status"] == lc.PAST_END
        assert out["recommendable"] is False
        assert "2026-03-31" in out["basis"]

    def test_a_product_with_one_date_passed_is_approaching_and_still_offered(self):
        """"If it is approaching lifecycle end, recommend it but also flag it."
        The 2025 date has gone; the 2027 one has not, so HP is still shipping
        it somewhere."""
        out = lc.status_for("HP EliteBook 8 G1i Flip", TODAY, ROWS)
        assert out["status"] == lc.APPROACHING
        assert out["recommendable"] is True
        assert out["flag"] == "approaching lifecycle end"

    def test_a_product_whose_dates_are_all_ahead_is_unflagged(self):
        out = lc.status_for("HP EliteDesk 8 G1i Tower", TODAY, ROWS)
        assert out["status"] == lc.LISTED_FUTURE
        assert out["recommendable"] is True
        assert "flag" not in out

    def test_an_unreadable_file_recommends_rather_than_withholds(self):
        out = lc.status_for("HP EliteBook 8 G1i Flip", TODAY, [])
        assert out["status"] == lc.NOT_LISTED
        assert out["recommendable"] is True


class TestTheLatestDateDecidesWhetherItIsGone:
    """84 of the 146 rows carry several dates in one cell with nothing saying
    which market each belongs to. Blocking on the earliest would withdraw a
    product HP is still selling."""

    def test_the_earliest_passing_does_not_refuse_it(self):
        rows = [row("HP Test G1i Box", "2020-01-01", "2030-01-01")]
        assert lc.status_for("HP Test G1i Box", TODAY, rows)["recommendable"] is True

    def test_the_latest_passing_does(self):
        rows = [row("HP Test G1i Box", "2020-01-01", "2021-01-01")]
        assert lc.status_for("HP Test G1i Box", TODAY, rows)["recommendable"] is False
