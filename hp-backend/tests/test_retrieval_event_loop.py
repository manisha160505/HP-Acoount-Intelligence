"""One event loop owns every LightRAG handle. Nothing may open one elsewhere.

LightRAG's Mongo backend caches a single `AsyncMongoClient` in a class-level
dict (`lightrag/kg/mongo_impl.py`, `ClientManager`), and that client binds to
the event loop it was created on. So the first piece of code to open a handle
inside a throwaway `asyncio.run(...)` loop poisons the cache for the whole
process:

    RuntimeError: Cannot use AsyncMongoClient in different event loop.

That is not theoretical. Loading the first account through the API failed 11 of
15 index jobs this way: `dashboard/priorities.py` awaited `query.retrieve`
inside `asyncio.run(...)`, and after the Executive Dashboard regenerated, every
later index build in that process died - which left the message house pending
and Strategy Chat unanswerable on a fully loaded account.

`client.run_on_query_loop()` is the only way in. This test is a grep, because
the failure is a call-site mistake rather than a logic error, and the next one
will be written the same way.

Run: python -m pytest tests/test_retrieval_event_loop.py -v
"""

import os
import re
from pathlib import Path

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "app")

# Where retrieval is actually reached from. A new caller belongs on this list.
RETRIEVAL_CALLERS = [
    os.path.join(SRC, "services", "retrieval", "ingest.py"),
    os.path.join(SRC, "services", "retrieval", "query.py"),
    os.path.join(SRC, "services", "dashboard", "priorities.py"),
    os.path.join(SRC, "services", "messaging", "pillars.py"),
    os.path.join(SRC, "api", "v1", "widgets.py"),
]

_ASYNCIO_RUN = re.compile(r"^[^#\n]*\basyncio\.run\s*\(", re.M)


def _offending_lines(path: str) -> list[str]:
    if not Path(path).is_file():
        return []
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    # A backtick means the line is prose quoting the old call, not making it -
    # query.ask's docstring explains exactly why nobody should write it.
    return [line.strip() for line in text.splitlines()
            if _ASYNCIO_RUN.match(line) and "`" not in line]


class TestNobodyOpensTheirOwnLoop:

    def test_no_retrieval_caller_uses_asyncio_run(self):
        offenders = {path: lines for path in RETRIEVAL_CALLERS
                     if (lines := _offending_lines(path))}
        assert offenders == {}, (
            "asyncio.run() on a retrieval path binds LightRAG's cached Mongo "
            "client to a loop that is about to be closed. Use "
            "client.run_on_query_loop(...) instead: %s" % offenders)

    def test_the_shared_loop_helper_still_exists(self):
        """The test above is only meaningful while this is the way in."""
        path = os.path.join(SRC, "services", "retrieval", "client.py")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        assert "def run_on_query_loop(" in text
        assert "def _ensure_query_loop(" in text

    def test_builds_go_through_it_too(self):
        """A build creates its own handle - but on the same loop as everything
        else, which is what the class-level client cache requires."""
        path = os.path.join(SRC, "services", "retrieval", "ingest.py")
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        assert "client.run_on_query_loop(" in text
        assert "update_index(account_id, index, full=full)" in text
