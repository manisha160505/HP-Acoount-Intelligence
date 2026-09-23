"""The client's priority table for the Opportunity Map (Sep 2026).

The SEA Limited reference application shows only Critical/High/Medium/Low, so
the three per-check tags are no longer published. These pin the table itself,
and that the four tags are the only ones a play can carry.
"""
import pytest

from app.services.extractors.solution_narrative_opportunity_map import (
    PRIORITY_ORDER,
    _priority_for,
)


@pytest.mark.parametrize("initiative,supporting,any_signal,expected", [
    # A specific initiative plus an independent supporting signal.
    (True, True, True, "Critical"),
    # The initiative, but nothing independent supports it.
    (True, False, True, "High"),
    # No confirmed initiative, but signals indicate potential.
    (False, True, True, "Medium"),
    (False, False, True, "Medium"),
    # Contextual or indirect only - nothing attaches to this play.
    (False, False, False, "Low"),
])
def test_priority_table(initiative, supporting, any_signal, expected):
    assert _priority_for(initiative, supporting, any_signal) == expected


def test_supporting_signal_alone_never_reaches_high():
    """High requires the initiative, not merely a second signal.

    A timing trigger without directly evidenced activity is the Medium row of
    the table - "relevant signals indicate a potential opportunity" - and
    must not be promoted just because a trigger exists.
    """
    assert _priority_for(False, True, True) == "Medium"


def test_initiative_alone_is_high_not_critical():
    """Critical needs the second independent signal."""
    assert _priority_for(True, False, True) == "High"


def test_only_the_four_client_tags_exist():
    assert PRIORITY_ORDER == ("Critical", "High", "Medium", "Low")


def test_order_runs_highest_first():
    """PRIORITY_ORDER is used as a sort key, so the order is load-bearing."""
    assert PRIORITY_ORDER.index("Critical") < PRIORITY_ORDER.index("High")
    assert PRIORITY_ORDER.index("High") < PRIORITY_ORDER.index("Medium")
    assert PRIORITY_ORDER.index("Medium") < PRIORITY_ORDER.index("Low")
