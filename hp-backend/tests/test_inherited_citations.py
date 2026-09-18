"""A citation must not survive being copied into another index.

Strategy Chat builds its corpus from other features' finished widget text, and
that text arrives with the issuing feature's citation tags written into the
sentence. The tags are valid where they came from and unciteable anywhere else:
`resolve` scopes every lookup to one index, so a tag inherited from
`content_messaging` cannot resolve against `strategy`.

Measured on the Astra account, that cost a whole generation. The model read
`[a6a997c3b_opportunity_plays#c9]` sitting in the text it was handed, cited it
as any honest reader would, and validation correctly rejected the answer - 11.7
seconds paid for and binned, with the retry writing the same answer from the
same text. A question whose evidence is mostly inherited can burn all three
attempts and return "information not available" for content the platform holds.

So the tag is removed where the sentence is reused, not caught downstream. The
reusing index registers its own id for that sentence; nothing is lost.

Run: python -m pytest tests/test_inherited_citations.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.retrieval.evidence import (
    EVIDENCE_ID_RE,
    strip_citations,
)


class TestStripsInheritedCitations:
    """What must be removed."""

    def test_removes_a_single_inherited_tag(self):
        assert strip_citations(
            "Capex is IDR 36 trillion. [a6a997c3b_opportunity_plays#c9]"
        ) == "Capex is IDR 36 trillion."

    def test_removes_a_comma_separated_list(self):
        """The observed shape - one sentence carrying four inherited ids."""
        assert strip_citations(
            "Robust computing is needed. [a6a997c3b_opportunity_plays#c9, "
            "a6a997c3b_opportunity_plays#c10, a6a997c3b_news_signals#c2]"
        ) == "Robust computing is needed."

    def test_removes_a_tag_mid_sentence(self):
        assert strip_citations(
            "The plan [a_x#c1] continues."
        ) == "The plan continues."

    def test_handles_empty_and_none(self):
        assert strip_citations("") == ""
        assert strip_citations(None) == ""


class TestLeavesEverythingElseAlone:
    """What must survive - stripping too much would delete real prose."""

    def test_keeps_text_with_no_citation(self):
        text = "Astra allocated IDR 36 trillion capex for 2026."
        assert strip_citations(text) == text

    def test_keeps_an_ordinary_bracketed_aside(self):
        text = "Revenue rose [see note] this year."
        assert strip_citations(text) == text

    def test_keeps_a_bracketed_number(self):
        """`[12]` is not a citation and must not be mistaken for one."""
        text = "Growth was [12] percent."
        assert strip_citations(text) == text


class TestAgreesWithTheResolver:
    """The stripper and the validator must recognise the same shape.

    If they drift, either a real citation is deleted from the corpus or an
    inherited one survives to be rejected again.
    """

    def test_every_stripped_id_is_one_resolve_would_have_parsed(self):
        for eid in ("a6a997c3b_opportunity_plays#c9", "a_x#c1", "doc_2#c123"):
            assert EVIDENCE_ID_RE.match(eid), eid
            assert strip_citations("Sentence. [%s]" % eid) == "Sentence."
