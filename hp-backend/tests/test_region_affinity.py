"""One conversation, one Vertex region - so a prompt cache can be reused.

Strategy Chat sends the same ~400,000-token prefix again on every turn and again
on every validation retry. That prefix is byte-identical for the life of a
conversation and is exactly what a prompt cache is for. A cache is per region,
and `_regional_clients` advanced a module-global counter on EVERY call, so with
24 regions configured in production consecutive turns of one conversation landed
on different regions and the cache was never reused - `cached_tokens` came back 0.

So chat pins its starting region to the account, and regeneration keeps rotating:
many accounts, no shared prefix, spread the quota.

Two properties matter and both are easy to break by accident:

  * the region must be the same for one account ACROSS PROCESSES - `hash()` on a
    str is salted per process, so it would differ per worker and after every
    restart, which is the exact behaviour this replaces;
  * affinity must decide where a call STARTS, never where it may go - a 429 still
    has to reach every other region.

Run: python -m pytest tests/test_region_affinity.py -v
"""

import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core import llm

REGIONS = ["global", "asia-south1", "asia-southeast1", "asia-northeast1",
           "asia-northeast3", "australia-southeast1", "us-central1", "us-east1"]

ACCOUNT_A = "68d9f1c2a4b5c6d7e8f90123"
ACCOUNT_B = "68d9f1c2a4b5c6d7e8f90456"


@pytest.fixture
def vertex(monkeypatch):
    """A Vertex deployment with several chat regions."""
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                        property(lambda _self: list(REGIONS)))
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "proj")


class _Client:
    """Records the base_url of each regional copy it is asked for."""

    def __init__(self):
        self.base_url = "https://aiplatform.googleapis.com/original"

    def with_options(self, base_url=None, **_kw):
        copy = _Client()
        copy.base_url = base_url
        return copy


def _order(client, affinity=""):
    return [c.base_url for c in llm._regional_clients(client, affinity)]


class TestOneAccountAlwaysStartsInTheSameRegion:

    def test_repeated_calls_for_one_account_start_in_one_place(self, vertex):
        client = _Client()
        first = _order(client, ACCOUNT_A)
        for _ in range(12):
            assert _order(client, ACCOUNT_A)[0] == first[0]

    def test_the_rotating_counter_does_not_drag_it_along(self, vertex):
        """The bug in one assertion: rotation between two turns of the same
        conversation is what moved the cache out from under it."""
        client = _Client()
        pinned = _order(client, ACCOUNT_A)[0]
        for _ in range(5):
            _order(client)          # other work, rotating as before
        assert _order(client, ACCOUNT_A)[0] == pinned

    def test_different_accounts_do_not_all_land_together(self, vertex):
        client = _Client()
        starts = {_order(client, "acct-%d" % i)[0] for i in range(40)}
        # Spread, not a single hot region. Exact distribution is the hash's
        # business; what matters is that pinning did not serialise everything
        # onto one endpoint.
        assert len(starts) > len(REGIONS) // 2


class TestItIsStableAcrossProcesses:

    def test_a_fresh_interpreter_picks_the_same_region(self):
        """`hash()` on a str is salted per process. A worker restart, or a second
        uvicorn worker, would then pick a different region for the same account
        and the cache would miss - so a stable digest is the whole point."""
        code = (
            "import sys; sys.path.insert(0, %r);"
            "from app.core import llm;"
            "print(llm._affinity_start(%r, 8))"
            % (os.path.join(os.path.dirname(__file__), "..", "src"), ACCOUNT_A)
        )
        runs = set()
        for seed in ("0", "1", "random"):
            env = {**os.environ, "PYTHONHASHSEED": seed}
            out = subprocess.run([sys.executable, "-c", code], check=True,
                                 capture_output=True, text=True, env=env)
            runs.add(out.stdout.strip())
        assert len(runs) == 1, runs
        assert runs == {str(llm._affinity_start(ACCOUNT_A, 8))}


class TestAffinityOnlyChoosesWhereToStart:

    def test_every_region_is_still_reachable(self, vertex):
        """A 429 must still fall through to all the others, so pinning costs no
        resilience - it reorders the list, it does not shorten it."""
        order = _order(_Client(), ACCOUNT_A)
        assert len(order) == len(REGIONS)
        assert len({*order}) == len(REGIONS)
        for region in REGIONS:
            assert any(region in url for url in order)

    def test_the_order_is_a_rotation_of_the_configured_list(self, vertex):
        order = _order(_Client(), ACCOUNT_B)
        names = [u.split("/locations/")[1].split("/")[0] for u in order]
        start = REGIONS.index(names[0])
        assert names == REGIONS[start:] + REGIONS[:start]


class TestWhatIsLeftAlone:

    def test_without_an_affinity_the_regions_still_rotate(self, vertex):
        """Regeneration's behaviour, unchanged: many accounts, no shared prefix,
        spread the quota. Asserted as "advances by one each call" rather than
        "differs", so a change that rotated erratically would still fail."""
        client = _Client()

        def start(affinity=""):
            url = _order(client, affinity)[0]
            return REGIONS.index(url.split("/locations/")[1].split("/")[0])

        first = start()
        for step in range(1, 5):
            assert start() == (first + step) % len(REGIONS)

    def test_a_single_region_deployment_is_the_client_untouched(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
        monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                            property(lambda _self: ["global"]))
        client = _Client()
        assert llm._regional_clients(client, ACCOUNT_A) == [client]

    def test_another_provider_is_the_client_untouched(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "openai")
        client = _Client()
        assert llm._regional_clients(client, ACCOUNT_A) == [client]


class TestItReachesTheCallThroughCreateCompletion:

    def test_the_affinity_is_not_forwarded_to_the_provider(self, vertex):
        """It selects an endpoint; it is not part of the request body. Sending it
        on would be an unknown field in the completion call."""
        sent = []

        class _Completions:
            def create(self, **kw):
                sent.append(kw)
                return type("R", (), {"usage": None})()

        class _Regional(_Client):
            chat = type("C", (), {"completions": _Completions()})()

            def with_options(self, base_url=None, **_kw):
                return self

        llm.create_completion(_Regional(), affinity=ACCOUNT_A,
                              model="m", messages=[])
        assert sent and "affinity" not in sent[0]
        assert sent[0]["model"] == "m"
