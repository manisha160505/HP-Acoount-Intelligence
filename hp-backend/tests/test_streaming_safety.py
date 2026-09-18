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

**It runs without a database.** `_validated_prefix` resolves citation ids
through `evidence.resolve`, which opens a Mongo connection. The first version
let that call through to a real database, so the suite passed on a developer's
machine and failed on CI with `localhost:27017: Connection refused` - which is
how `main` went red. `ev.resolve` is stubbed here, which is also the only way
to control WHICH ids resolve and therefore the only way to test the boundary at
all.

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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.strategy import chat as sc

ACCOUNT = "000000000000000000000000"
PASSAGES = [
    "Astra reported net revenue of IDR 323,392 billion for FY2025. "
    "Mochamad Triawan is Department Head of Technology Development."
]

# The ids that resolve for this account, and the source line behind each. A
# real `ev.resolve` reads these from Mongo scoped by account; stubbing it keeps
# the suite hermetic AND makes "this id resolves, that one does not" a property
# of the test rather than of whatever happens to be in a developer's database.
EVIDENCE = {
    "a_reported_financials#c1":
        "Astra reported net revenue of IDR 323,392 billion for FY2025.",
    "a_contact_mochamad#c1":
        "Mochamad Triawan is Department Head of Technology Development.",
}


@pytest.fixture(autouse=True)
def resolver(monkeypatch):
    """`evidence.resolve`, without a database.

    Autouse because every test in this file goes through `_validated_prefix`,
    and one that forgot the fixture would reach for Mongo and fail on CI only -
    the exact failure this fixture exists to end.
    """
    def fake_resolve(_account_id, _index, ids):
        resolved, invalid = [], []
        for eid in ids:
            if eid in EVIDENCE:
                resolved.append({"evidence_id": eid, "source_text": EVIDENCE[eid],
                                 "dataset": "compliance_filings"})
            else:
                invalid.append(eid)
        return resolved, invalid

    monkeypatch.setattr(sc.ev, "resolve", fake_resolve)


class TestValidTextIsReleased:
    """The half an earlier version of this file left untested.

    Without these, `_validated_prefix` could return `("", False)` for every
    input - streaming completely broken, nothing ever shown - and the suite
    would still be green.
    """

    def test_a_fully_cited_prefix_is_released(self):
        text, ok = sc._validated_prefix(
            ACCOUNT,
            "FACTS: 1. Astra reported net revenue of IDR 323,392 billion "
            "[a_reported_financials#c1].",
            PASSAGES)
        assert ok is True
        assert "323,392" in text
        assert "a_reported_financials#c1" in text

    def test_release_extends_as_further_citations_close(self):
        """A second bracket releases more than the first did."""
        one = ("FACTS: 1. Astra reported net revenue of IDR 323,392 billion "
               "[a_reported_financials#c1].")
        two = one + (" 2. Mochamad Triawan is Department Head of Technology "
                     "Development [a_contact_mochamad#c1].")
        first, ok_one = sc._validated_prefix(ACCOUNT, one, PASSAGES)
        second, ok_two = sc._validated_prefix(ACCOUNT, two, PASSAGES)
        assert ok_one and ok_two
        assert len(second) > len(first)
        assert "Mochamad" in second and "Mochamad" not in first


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

        The `assert text` matters as much as the `not in`: without it this
        passes when nothing is released at all, which is what it used to do.
        """
        buffer = ("FACTS: 1. Astra reported IDR 323,392 billion "
                  "[a_reported_financials#c1]. 2. Growth was 42.7%")
        text, ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert ok is True
        assert text, "the cited prefix should have been released"
        assert "42.7" not in text

    def test_an_empty_buffer_releases_nothing(self):
        assert sc._validated_prefix(ACCOUNT, "", PASSAGES) == ("", False)


class TestReleaseIsAlwaysAPrefix:
    """What was shown is never contradicted by what follows."""

    def test_released_text_is_a_prefix_of_the_buffer(self):
        buffer = ("FACTS: 1. Mochamad Triawan is Department Head of Technology "
                  "[a_contact_mochamad#c1]. 2. Still being written")
        text, ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert ok is True
        assert text, "the cited prefix should have been released"
        # Markdown stripping can rewrite the released text, so the assertion is
        # on the release boundary rather than on string identity.
        assert "Still being written" not in text
        assert "Mochamad Triawan" in text


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

    def test_a_figure_absent_from_the_evidence_is_not_released(self):
        """Even when it sits inside the cited prefix rather than after it.

        The bracket boundary decides WHAT is checked. It does not decide
        whether the check bites.
        """
        buffer = ("FACTS: 1. Astra reported IDR 999,111 billion "
                  "[a_reported_financials#c1].")
        text, ok = sc._validated_prefix(ACCOUNT, buffer, PASSAGES)
        assert ok is False
        assert text == ""
