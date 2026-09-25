"""v4 section A: a contact the vendor has not finished matching is not evidence.

    "Blank contact fields or Pending/Review status means do not infer the
    missing role, authority or contact detail."

The contact file for the 220 accounts has not arrived - `prospect_contacts` is
empty on all 220 - so this is tested against synthetic rows in the two shapes
that have actually been delivered: the pilot CSV's `apollo_match_status` and the
Apollo workbook's `match_status`.

Run: python -m pytest tests/test_contact_match_status.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.stakeholder_map import _drop_unmatched_contacts


class TestUnmatchedContactsAreWithheld:

    def test_a_pending_row_is_withheld(self):
        rows = [{"Prospect full_name": "A", "apollo_match_status": "Pending"}]
        kept, withheld = _drop_unmatched_contacts(rows)
        assert kept == []
        assert withheld == 1

    def test_a_needs_review_row_is_withheld(self):
        rows = [{"Prospect full_name": "A", "match_status": "Needs Review"}]
        kept, withheld = _drop_unmatched_contacts(rows)
        assert kept == []
        assert withheld == 1

    def test_a_matched_row_is_kept(self):
        rows = [{"Prospect full_name": "A", "apollo_match_status": "Matched"}]
        kept, withheld = _drop_unmatched_contacts(rows)
        assert len(kept) == 1
        assert withheld == 0

    def test_a_blank_status_is_kept(self):
        """Blank is not Pending.

        On the pilot account 8 of 23 rows carry no status at all and are good
        contacts. Reading blank as unmatched would discard a third of them.
        """
        rows = [{"Prospect full_name": "A", "apollo_match_status": ""},
                {"Prospect full_name": "B"}]
        kept, withheld = _drop_unmatched_contacts(rows)
        assert len(kept) == 2
        assert withheld == 0

    def test_both_delivered_column_names_are_read(self):
        rows = [{"apollo_match_status": "pending"},      # pilot CSV
                {"match_status": "PENDING"},             # Apollo workbook
                {"Match Status": "Review"},              # the input contract
                {"apollo_match_status": "Matched"}]
        kept, withheld = _drop_unmatched_contacts(rows)
        assert withheld == 3
        assert len(kept) == 1

    def test_no_rows_is_not_an_error(self):
        assert _drop_unmatched_contacts([]) == ([], 0)
        assert _drop_unmatched_contacts(None) == ([], 0)
