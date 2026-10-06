"""The strategy chat stream stays open while a slow answer is written.

Run: python -m pytest tests/test_sse_keepalive.py -v
"""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core.sse import KEEPALIVE, with_keepalive


def test_events_pass_through_in_order():
    assert list(with_keepalive(lambda: iter(["a", "b"]), interval=1)) == ["a", "b"]


def test_a_silent_producer_gets_keepalives():
    def slow():
        time.sleep(0.35)
        yield "done"
    out = list(with_keepalive(slow, interval=0.1))
    assert out[-1] == "done" and out.count(KEEPALIVE) >= 2


def test_a_keepalive_is_an_sse_comment_clients_ignore():
    assert KEEPALIVE.startswith(":") and "data:" not in KEEPALIVE and KEEPALIVE.endswith("\n\n")


def test_a_producer_error_reaches_the_response():
    def broken():
        yield "a"
        raise RuntimeError("boom")
    gen = with_keepalive(broken, interval=1)
    assert next(gen) == "a"
    with pytest.raises(RuntimeError):
        next(gen)
