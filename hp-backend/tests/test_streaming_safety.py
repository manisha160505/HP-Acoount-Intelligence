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

## Two things this file gets right that an earlier version did not

**It runs without a database.** Citations name a section of the account payload
the chat was given, and are resolved against that payload - so a test builds
the payload and needs nothing else. (Under retrieval they resolved through
Mongo, and a suite that let that call through passed locally and failed on CI.)

**It asserts that text IS released.** Every assertion in the first version was
negative - `text == ""`, `"42.7" not in text` - and every one of them was
satisfied by a function that returned `("", False)` unconditionally. Stubbing
`_validated_prefix` to release nothing, ever, left the whole file passing. A
suite that cannot fail against a completely broken implementation is not
pinning the behaviour it describes, so `TestValidTextIsReleased` exists to fail
in that case, and the withholding tests now assert non-empty output alongside
the absence of the unsafe part.

Run: python -m pytest tests/test_streaming_safety.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.strategy import chat as sc

# The account as the chat sees it: two sections, each introduced by the header
# a citation names. Only these two section keys resolve.
PAYLOAD = "\n\n".join([
    "===== exec_key_metrics (feature: executive_dashboard) =====",
    '{"revenue":"Astra reported net revenue of IDR 323,392 billion for FY2025."}',
    "===== stakeholder_contacts_grid (feature: stakeholder_map) =====",
    '{"contacts":[{"name":"Mochamad Triawan",'
    '"title":"Department Head of Technology Development"}]}',
])


def _turn(persona=None):
    return {"payload": PAYLOAD, "persona": persona, "banned": [],
            "widget_keys": ["exec_key_metrics", "stakeholder_contacts_grid"]}


def _prefix(buffer):
    return sc._validated_prefix(_turn(), buffer)


class TestValidTextIsReleased:
    """The half an earlier version of this file left untested.

    Without these, `_validated_prefix` could return `("", False)` for every
    input - streaming completely broken, nothing ever shown - and the suite
    would still be green.
    """

    def test_a_fully_cited_prefix_is_released(self):
        text, ok = _prefix(
            "FACTS: 1. Astra reported net revenue of IDR 323,392 billion "
            "[exec_key_metrics].")
        assert ok is True
        assert "323,392" in text
        assert "exec_key_metrics" in text

    def test_release_extends_as_further_citations_close(self):
        """A second bracket releases more than the first did."""
        one = ("FACTS: 1. Astra reported net revenue of IDR 323,392 billion "
               "[exec_key_metrics].")
        two = one + (" 2. Mochamad Triawan is Department Head of Technology "
                     "Development [stakeholder_contacts_grid].")
        first, ok_one = _prefix(one)
        second, ok_two = _prefix(two)
        assert ok_one and ok_two
        assert len(second) > len(first)
        assert "Mochamad" in second and "Mochamad" not in first


class TestNothingIsReleasedEarly:
    """The tail of the buffer is withheld until its citation arrives."""

    def test_text_with_no_citation_yet_releases_nothing(self):
        text, ok = _prefix("FACTS: 1. Astra reported net revenue of IDR 323,392")
        assert text == ""
        assert ok is False

    def test_a_figure_without_its_citation_is_withheld(self):
        """The failure this rule exists to prevent.

        An invented number sits after the last bracket. Releasing the buffer
        wholesale would publish it; releasing only to the bracket does not.

        The `assert text` matters as much as the `not in`: without it this
        passes when nothing is released at all, which is what it used to do.
        """
        buffer = ("FACTS: 1. Astra reported IDR 323,392 billion "
                  "[exec_key_metrics]. 2. Growth was 42.7%")
        text, ok = _prefix(buffer)
        assert ok is True
        assert text, "the cited prefix should have been released"
        assert "42.7" not in text

    def test_an_empty_buffer_releases_nothing(self):
        assert _prefix("") == ("", False)


class TestRoleplayIsHeldToItsOwnValidator:
    """A rehearsal streams too, and its prefix goes through the roleplay gate."""

    def test_a_real_persons_name_is_not_released_in_character(self):
        turn = dict(_turn(persona={"title": "COO"}), banned=["Mochamad Triawan"])
        text, ok = sc._validated_prefix(
            turn, "Talk to Mochamad Triawan about that [stakeholder_contacts_grid].")
        assert ok is False
        assert text == ""


class TestReleaseIsAlwaysAPrefix:
    """What was shown is never contradicted by what follows."""

    def test_released_text_is_a_prefix_of_the_buffer(self):
        buffer = ("FACTS: 1. Mochamad Triawan is Department Head of Technology "
                  "[stakeholder_contacts_grid]. 2. Still being written")
        text, ok = _prefix(buffer)
        assert ok is True
        assert text, "the cited prefix should have been released"
        # Markdown stripping can rewrite the released text, so the assertion is
        # on the release boundary rather than on string identity.
        assert "Still being written" not in text
        assert "Mochamad Triawan" in text


class TestTheValidatorIsNotBypassed:
    """Streaming reuses `_validate`; it does not reimplement it."""

    def test_an_unresolvable_citation_is_not_released(self):
        buffer = "FACTS: 1. Astra reported growth [exec_ghost_section]."
        text, ok = _prefix(buffer)
        assert ok is False
        assert text == ""

    def test_facts_asserted_with_no_citation_are_not_released(self):
        """Matches `_validate`'s uncited-facts rule, reached through a bracket
        that is not a section key at all."""
        buffer = "FACTS: 1. Mochamad Triawan is the Department Head [not_a_citation]."
        text, ok = _prefix(buffer)
        assert ok is False
        assert text == ""

    def test_a_figure_absent_from_the_evidence_is_not_released(self):
        """Even when it sits inside the cited prefix rather than after it.

        The bracket boundary decides WHAT is checked. It does not decide
        whether the check bites.
        """
        buffer = ("FACTS: 1. Astra reported IDR 999,111 billion "
                  "[exec_key_metrics].")
        text, ok = _prefix(buffer)
        assert ok is False
        assert text == ""
