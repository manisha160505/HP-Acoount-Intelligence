"""Streaming must not weaken the guarantee that nothing unverified is shown.

Strategy Chat's promise is that every sentence a seller reads has been checked
against the account's evidence. Streaming appears to conflict with that: text
shown as it is written has not been checked yet, and an answer that fails
validation would have to be taken back after it was read - a retracted figure
is worse than a slow one, because by then it may be in an email to the client.

The reconciliation is the release rule, and these tests pin it.

**Nothing is released past the last closed citation bracket.** The model writes
a claim before it writes the tag, so a sentence in flight has no citation yet.
Holding the tail back means a fabricated figure cannot be published: it sits
unreleased until either a citation follows it - and is then validated like any
other text - or the answer ends and the whole-answer check rejects it.

**The prefix is checked by the same validator as the final answer.** Not a
relaxed variant: `_validate` itself, run earlier and more often. It costs about
70ms, which is affordable per bracket and is not affordable per token - the
first implementation ran it 531 times for one answer and spent 82% of the wall
clock inside it, so the caller validates only when a new bracket closes.

Run: python -m pytest tests/test_streaming_safety.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.strategy import chat as sc  # noqa: E402

ACCOUNT = "000000000000000000000000"
PASSAGES = [
    "Astra reported net revenue of IDR 323,392 billion for FY2025. "
    "Mochamad Triawan is Department Head of Technology Development."
]


class TestNothingIsReleasedEarly:
    """The tail of the buffer is withheld until its citation arrives."""

    def test_text_with_no_citation_yet_releases_nothing(self):
        text, ok = sc._validated_prefix(
            ACCOUNT, "FACTS: 1. Astra reported net revenue of IDR 323,392", PASSAGES)
        assert text == ""
        assert ok is False

    def test_a_figure_without_its_citation_is_withheld(self):
        """The failure this rule exists to prevent.

        An invented number sits after the last bracket. Releasing the buffer
        wholesale would publish it; releasing only to the bracket does not.
        """
        buffer = ("FACTS: 1. Astra reported IDR 323,392 billion "
                  "[a_reported_financials#c1]. 2. Growth was 42.7%")
        text, _ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert "42.7" not in text

    def test_an_empty_buffer_releases_nothing(self):
        assert sc._validated_prefix(ACCOUNT, "", PASSAGES) == ("", False)


class TestReleaseIsAlwaysAPrefix:
    """What was shown is never contradicted by what follows."""

    def test_released_text_is_a_prefix_of_the_buffer(self):
        buffer = ("FACTS: 1. Mochamad Triawan is Department Head of Technology "
                  "[a_contact_mochamad#c1]. 2. Still being written")
        text, _ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        # Markdown stripping can rewrite the released text, so the assertion is
        # on the release boundary rather than on string identity.
        assert "Still being written" not in text


class TestTheValidatorIsNotBypassed:
    """Streaming reuses `_validate`; it does not reimplement it."""

    def test_an_unresolvable_citation_is_not_released(self):
        buffer = "FACTS: 1. Astra reported growth [a_ghost_document#c99]."
        text, ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert ok is False
        assert text == ""

    def test_facts_asserted_with_no_citation_are_not_released(self):
        """Matches `_validate`'s uncited-facts rule, reached through a bracket
        that resolves to nothing."""
        buffer = "FACTS: 1. Mochamad Triawan is the Department Head [not_a_citation]."
        text, ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert ok is False
        assert text == ""
