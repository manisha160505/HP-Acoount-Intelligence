"""The persona pack must still say what the build specification says.

The cards were transcribed by hand once and the transcription lost every
statistic - Section 5 carries seventy percentage figures and the pack carried
none. Nobody noticed for a fortnight, because a card full of confident prose
reads exactly like a card full of sourced prose.

So the pack is now generated from the document
(`scripts/regenerate_persona_pack.py`) and this reads the document back and
checks it. It is the only test in the suite that opens a .docx, and it skips
rather than fails when the file is absent, because the specification is HP
Confidential and is not in every checkout.
"""

import os
import re
import sys
import zipfile
from html import unescape
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.hp import buyer_personas as bp

_DOCS = Path(__file__).resolve().parents[2] / "project-documentation"
_PATTERN = "*Content_Studio_Message_Evaluator_Build_Spec*.docx"


def _section_five():
    matches = sorted(_DOCS.glob(_PATTERN))
    if not matches:
        pytest.skip("the build specification is not in this checkout")
    with zipfile.ZipFile(matches[-1]) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    text = unescape(re.sub(r"<[^>]+>", "", re.sub(r"</w:p>", "\n", xml)))
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.startswith("5. Persona pack"))
    end = next(i for i, line in enumerate(lines) if line.startswith("6. Guardrails"))
    return "\n".join(lines[start:end])


@pytest.fixture(scope="module")
def spec():
    return _section_five()


def _normalise(text):
    """The document as the generator sees it.

    The [E#] and [inference] markers are stripped here as well as in the
    generator: they sit mid-sentence, so a card's bullet is the document's
    sentence WITHOUT them and a comparison against the raw text would never
    match.
    """
    for bad, good in (("—", " - "), ("–", "-"), ("‘", "'"),
                      ("’", "'"), ("“", '"'), ("”", '"'),
                      ("…", "...")):
        text = text.replace(bad, good)
    text = re.sub(r"\s*\[E\d+\]", "", text)
    text = re.sub(r"\s*\[inference[^\]]*\]", "", text)
    text = re.sub(r"\s+([.;,])", r"\1", text)
    return " ".join(text.split())


class TestTheCardsAreTheDocument:

    def test_all_eight_personas_are_present(self, spec):
        found = re.findall(r"5\.\d+ `([a-z-]+)`", spec)
        assert found == list(bp.PERSONA_IDS)

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_every_bullet_appears_in_the_document(self, spec, persona_id):
        """Verbatim, not paraphrased.

        Checked against the whole of Section 5 rather than against this
        persona's block, because a bullet moving between cards is HP's edit to
        make and the parser would carry it; a bullet that appears in NEITHER
        card is a rewrite, which is the failure this guards.
        """
        body = _normalise(spec)
        card = bp.card(persona_id)
        for field in ("goals", "pain_points", "value_drivers",
                      "decision_criteria", "typical_objections"):
            for item in card[field]:
                # The document quotes decision criteria and objections; the
                # quotes are its formatting and are stripped in the pack.
                needle = _normalise(item).rstrip(".")
                assert needle in body, "%s.%s: %r is not in the document" % (
                    persona_id, field, needle[:70])

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_remit_and_hp_opportunity_are_the_document_s(self, spec, persona_id):
        body = _normalise(spec)
        card = bp.card(persona_id)
        assert _normalise(card["remit"]).rstrip(".") in body
        assert _normalise(card["hp_opportunity"]).rstrip(".") in body

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_the_grade_angle_and_entry_state_match(self, spec, persona_id):
        block = re.search(r"5\.\d+ `%s`.*?(?=\n5\.\d+ `|\Z)" % persona_id,
                          spec, re.S).group(0)
        block = _normalise(block)
        card = bp.card(persona_id)
        # The document writes one grade in capitals ("THIN - SIGN-OFF
        # REQUIRED"); the pack title-cases it so the eight read consistently.
        assert ("evidence grade %s" % card["evidence_grade"].split(" - ")[0].lower()
                in block.lower())
        assert card["committee_angle"] in block
        assert "Behavioural state %s" % card["behavioural_state"] in block


class TestTheFiguresSurvived:
    """The regression this file exists for."""

    def test_the_pack_carries_the_document_s_statistics(self, spec):
        in_spec = set(re.findall(r"\d+%", spec))
        in_pack = set()
        for persona_id in bp.PERSONA_IDS:
            card = bp.card(persona_id)
            for field in ("goals", "pain_points", "value_drivers",
                          "decision_criteria", "remit", "hp_opportunity"):
                value = card[field]
                text = value if isinstance(value, str) else " ".join(value)
                in_pack |= set(re.findall(r"\d+%", text))
        missing = in_spec - in_pack
        assert not missing, (
            "figures in Section 5 that no card carries: %s. The pack is "
            "generated - run scripts/regenerate_persona_pack.py rather than "
            "editing the cards by hand." % sorted(missing))

    def test_no_footnote_marker_renders_to_a_seller(self):
        """The refs belong in `evidence_refs`, not in the middle of a sentence."""
        for persona_id in bp.PERSONA_IDS:
            card = bp.evaluator_card(persona_id)
            blob = str(card)
            assert not re.search(r"\[E\d+\]", blob), persona_id
            assert "[inference]" not in blob, persona_id

    @pytest.mark.parametrize("persona_id", bp.PERSONA_IDS)
    def test_every_card_records_where_it_came_from(self, persona_id):
        card = bp.card(persona_id)
        assert card["evidence_refs"], "no source register entries"
        assert all(re.fullmatch(r"E\d+", r) for r in card["evidence_refs"])
        assert card["inference_fields"], "no field marked as reasoned"

    def test_the_union_of_inference_fields_is_wider_than_the_old_constant(self):
        """The hand-written list named five fields. The document also marks
        individual goals, pain points, value drivers and decision criteria."""
        assert set(bp.INFERENCE_HEAVY_FIELDS) >= {
            "typical_objections", "resonates", "does_not_resonate",
            "content_preferences", "behavioural_state", "goals"}
