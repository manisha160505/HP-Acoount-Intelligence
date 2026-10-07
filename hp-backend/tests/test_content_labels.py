"""Evidence tags never reach the seller's clipboard.

The client, 6 Oct: in Content Studio, or anywhere we generate seller-facing
content, `[P1]` and `[P2]` must not appear inside the content - the seller
copies the email and pastes it. The Evidence section underneath stays.

It already behaved this way, but only because prompt rule 6 asks for evidence
named "by its content, not by its label". That is a rule the model may follow,
which is the exact distinction `content_gates` exists to draw:

    The prompt rules are instructions the model may follow. These are checks
    the code enforces.

So these tests pin the check, not the instruction.

Run: python -m pytest tests/test_content_labels.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import content_gates as cg

TAG = "[A1]"


class TestTheTagPattern:

    @pytest.mark.parametrize("text,want", [
        ("As the VP, you own the roadmap. [P4]", "As the VP, you own the roadmap."),
        ("Research activity [A1, A2] is high.", "Research activity is high."),
        ("Two sources [P1][P4] agree.", "Two sources agree."),
        ("The 12 roles [A3] suggest demand.", "The 12 roles suggest demand."),
        ("A two-digit label [P12] counts.", "A two-digit label counts."),
        ("Nothing to strip here.", "Nothing to strip here."),
    ])
    def test_tags_go_and_the_gap_closes(self, text, want):
        assert cg.strip_evidence_tags(text) == want

    @pytest.mark.parametrize("placeholder", [
        "Dear [VP Name],",
        "Hello [First Name], a quick note.",
        "Contact [Name] when ready.",
        "Reach out to [Job Title] about the refresh.",
    ])
    def test_a_seller_placeholder_is_not_a_tag(self, placeholder):
        """The failure a loose `\\[[^\\]]+\\]` would cause: "Dear [VP Name],"
        becomes "Dear ," and the seller mails it. Worse than the bug being
        fixed, so it is pinned."""
        assert cg.strip_evidence_tags(placeholder) == placeholder

    def test_an_evidence_label_list_is_left_alone(self):
        """Bare labels are G2's business and live in `evidence_used`. This
        strip only takes the bracketed form out of prose."""
        assert cg.strip_evidence_tags("A1") == "A1"


class TestEveryContentTypeIsCovered:
    """Three live formats - email, linkedin_message, one_pager - and their
    prose fields differ, so each is checked on its own shape."""

    def test_email(self):
        asset = {
            "subject_line": "Re: the refresh %s" % TAG,
            "opening": "You own the roadmap %s." % TAG,
            "body_sections": [{"heading": "Why now %s" % TAG,
                               "text": "The 12 roles %s suggest demand." % TAG}],
            "cta": "Worth a short call %s?" % TAG,
            "evidence_used": ["A1", "P4"],
        }
        cg.strip_evidence_labels(asset)
        assert TAG not in cg.asset_blob(asset)
        assert asset["evidence_used"] == ["A1", "P4"]

    def test_linkedin_message(self):
        asset = {
            "opening": "Your team is hiring %s." % TAG,
            "body_sections": ["One short paragraph %s." % TAG],
            "cta": "Open to a chat %s?" % TAG,
            "evidence_used": ["A3"],
        }
        cg.strip_evidence_labels(asset)
        assert TAG not in cg.asset_blob(asset)
        assert asset["body_sections"] == ["One short paragraph."]
        assert asset["evidence_used"] == ["A3"]

    def test_one_pager_keeps_its_per_pillar_evidence(self):
        """The 1-Pager cites per pillar. The prose goes, the citation stays -
        that is what builds the Evidence section the client asked to keep."""
        asset = {
            "headline": "Australia Post %s" % TAG,
            "subtitle": "For the IT committee %s" % TAG,
            "why_now": "Capex was announced %s." % TAG,
            "hp_play": "Z by HP Workstations %s" % TAG,
            "cta": "A 30-minute review %s." % TAG,
            "pillars": [{"heading": "Engineering load %s" % TAG,
                         "challenge": "AutoCAD is in use %s." % TAG,
                         "hp_response": "Z workstations %s." % TAG,
                         "evidence_used": ["A2"]}],
            "evidence_used": ["A1", "A2"],
        }
        cg.strip_evidence_labels(asset)
        assert TAG not in cg.asset_blob(asset)
        assert asset["pillars"][0]["evidence_used"] == ["A2"]
        assert asset["evidence_used"] == ["A1", "A2"]
        assert asset["pillars"][0]["challenge"] == "AutoCAD is in use."


class TestItCannotDriftFromTheReader:
    """`strip_evidence_labels` is the writing counterpart to `asset_texts`.
    If a prose field is added to one and not the other, a tag escapes - so the
    parity is asserted rather than trusted to a comment."""

    def test_every_key_the_reader_walks_is_also_stripped(self):
        asset = dict.fromkeys(cg._TEXT_KEYS, "text %s" % TAG)
        asset["body_sections"] = [{"heading": "h %s" % TAG, "text": "t %s" % TAG}]
        asset["pillars"] = [{"heading": "h %s" % TAG, "challenge": "c %s" % TAG,
                             "hp_response": "r %s" % TAG}]
        cg.strip_evidence_labels(asset)
        leaked = [t for t in cg.asset_texts(asset) if "[" in t]
        assert not leaked, "tags survived in: %s" % leaked

    def test_machine_fields_are_never_touched(self):
        asset = {"opening": "x %s" % TAG, "evidence_used": ["A1"],
                 "hp_products": ["Z by HP Workstations"]}
        cg.strip_evidence_labels(asset)
        assert asset["evidence_used"] == ["A1"]
        assert asset["hp_products"] == ["Z by HP Workstations"]

    def test_an_empty_or_missing_asset_does_not_raise(self):
        assert cg.strip_evidence_labels({}) == {}
        assert cg.strip_evidence_labels(None) == {}
class TestTheProofPointCannotCarryATagEither:
    """The one escape path the rest of this file missed.

    `_attach_proof_point` runs AFTER `_validate_asset` has stripped the model's
    prose and AFTER the gates, so nothing downstream re-checks it and no gate in
    `run()` looks for a bracketed tag - that call is the only enforcement on this
    path. It used to strip only `hp_proof_point`, which `asset_texts` does not
    read, while `proof_point` and the appended Proof Points section - the two the
    seller actually copies - were written raw.

    The text comes from the vetted case-study corpus and cannot carry a tag
    today, which is exactly why nothing caught it. These tests make the ordering
    hold on its own rather than on that happening to stay true.
    """

    PROOF = "HP secured 40,000 endpoints for a global manufacturer. %s" % TAG

    def _one_pager(self):
        return {
            "headline": "Australia Post",
            "subtitle": "For the IT committee",
            "why_now": "Capex was announced.",
            "hp_play": "Z by HP Workstations",
            "cta": "A 30-minute review.",
            "body_sections": [],
            "pillars": [{"heading": "Load", "challenge": "AutoCAD is in use.",
                         "hp_response": "Z workstations.", "evidence_used": ["A2"]}],
            "evidence_used": ["A1"],
        }

    def test_every_field_the_seller_copies_is_clean(self):
        from app.services.extractors import content_studio as cstudio
        asset = self._one_pager()
        cstudio._attach_proof_point(
            asset, {"text": self.PROOF},
            cstudio.CONTENT_TYPE_CONTRACTS["one_pager"])

        assert TAG not in asset["proof_point"]
        assert TAG not in asset["hp_proof_point"]
        assert TAG not in asset["body_sections"][-1]["text"]
        assert asset["body_sections"][-1]["heading"] == cstudio.PROOF_POINTS_HEADING
        # `asset_texts` is the authoritative traversal, so this is the catch-all.
        assert not [t for t in cg.asset_texts(asset) if TAG in t]

    def test_the_detail_the_ui_renders_is_clean_too(self):
        """`hp_proof_point_detail.text` is shown beside the copy in the UI and is
        not part of `asset_texts`, so the blob assertion above cannot see it."""
        from app.services.extractors import content_studio as cstudio
        asset = self._one_pager()
        cstudio._attach_proof_point(
            asset, {"text": self.PROOF, "customer": "A manufacturer"},
            cstudio.CONTENT_TYPE_CONTRACTS["one_pager"])
        assert TAG not in asset["hp_proof_point_detail"]["text"]
        assert asset["hp_proof_point_detail"]["customer"] == "A manufacturer"

    def test_the_callers_own_dict_is_not_mutated(self):
        """The caller keeps using `proof` for allocation bookkeeping, so the
        strip must not reach back into it."""
        from app.services.extractors import content_studio as cstudio
        proof = {"text": self.PROOF, "study_id": "cs-1"}
        cstudio._attach_proof_point(
            self._one_pager(), proof,
            cstudio.CONTENT_TYPE_CONTRACTS["one_pager"])
        assert proof["text"] == self.PROOF

    def test_no_field_of_the_asset_carries_a_tag(self):
        """A sweep over every value, not only the ones `asset_texts` walks.

        The other tests in this file use `asset_blob` as their oracle, which by
        construction cannot see a field the reader does not read - the same blind
        spot the fix itself had. This looks at everything.
        """
        import json

        from app.services.extractors import content_studio as cstudio
        asset = self._one_pager()
        cstudio._attach_proof_point(
            asset, {"text": self.PROOF},
            cstudio.CONTENT_TYPE_CONTRACTS["one_pager"])
        prose = {k: v for k, v in asset.items() if k != "evidence_used"}
        assert TAG not in json.dumps(prose, default=str)
