"""A 400 that means "not right now" is retried; one that means "not ever" is not.

Measured on production, 7 Oct: a 307,661-token Strategy Chat request came back

    400 INVALID_ARGUMENT: The input token count (307661) exceeds the maximum
    number of tokens allowed (131072)

The cause is now known, and it is the REGION. Probed from the VM against all 24
configured regions with one 232,986-token prompt, seconds apart: 22 accepted it;
`asia-northeast3` and `europe-west9` refused with that 131,072 cap. `global` and
`asia-south1` then accepted 963,786 tokens.

So the model's window really is 1,048,576, and those two regions serve 131,072.
Not load, not the project's quota (none holds that value), not the model - which
reports itself as `gemini-2.5-flash` on every successful call. Rotating over 24
regions put ~8% of calls on one of the two, which is what made Strategy Chat fail
on some turns and not others.

Excluding them by prompt size is the fix; the retry below is the backstop, because
the exclusion works off an estimate and the set of regions can change.

Because it arrives as a 400 it was treated as a permanent bad request: not
retried, no second region, straight to a refusal the seller reads as "the model
did not answer" on a question that works a minute later.

The distinction is the whole point of these tests. Retrying a genuinely malformed
request across 24 regions and 110s of waits would be a worse bug than the one
being fixed, so the match is on the provider's message rather than on the status
code.

Run: python -m pytest tests/test_capacity_refusal.py -v
"""

import os
import sys

import httpx
import pytest
from openai import APIStatusError, RateLimitError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.core import gemini, llm

CAPACITY = ("Error code: 400 - [{'error': {'code': 400, 'message': 'The input "
            "token count (307661) exceeds the maximum number of tokens allowed "
            "(131072).', 'status': 'INVALID_ARGUMENT'}}]")


def _status_error(status: int, message: str):
    request = httpx.Request("POST", "http://vertex.invalid")
    response = httpx.Response(status, request=request)
    if status == 429:
        return RateLimitError(message, response=response, body=None)
    return APIStatusError(message, response=response, body=None)


class TestWhichFailuresAreTransient:

    def test_the_capacity_400_is_retryable(self):
        assert llm._retryable(_status_error(400, CAPACITY))

    def test_a_429_is_still_retryable(self):
        assert llm._retryable(_status_error(429, "RESOURCE_EXHAUSTED"))

    def test_a_5xx_is_still_retryable(self):
        assert llm._retryable(_status_error(503, "backend unavailable"))

    @pytest.mark.parametrize("message", [
        "Invalid JSON payload received. Unknown name 'messagez'",
        "Please use a valid role: user, model.",
        "Publisher Model `publishers/google/models/nope` not found.",
        "The model is not supported for generateContent.",
    ])
    def test_an_ordinary_400_is_not_retryable(self, message):
        """The failure mode this must not cause: a malformed request sent 24
        times across every region and then waited on for 110 seconds."""
        assert not llm._retryable(_status_error(400, message))

    def test_the_match_is_on_the_message_not_the_status(self):
        assert llm._is_capacity_refusal(_status_error(400, CAPACITY))
        assert not llm._is_capacity_refusal(_status_error(400, "bad request"))
        # Same words, wrong status: a 429 is already handled as a 429.
        assert not llm._is_capacity_refusal(_status_error(429, CAPACITY))

    def test_a_non_api_exception_is_not_mistaken_for_one(self):
        assert not llm._is_capacity_refusal(ValueError("maximum number of tokens allowed"))
        assert not llm._retryable(ValueError("boom"))


class TestItMovesRegionAndThenWaits:

    @pytest.fixture
    def three_regions(self, monkeypatch):
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
        monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                            property(lambda _self: ["global", "asia-south1", "us-central1"]))
        monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "proj")
        monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0))

    def _client(self, outcomes):
        """A client where each call pops the next scripted outcome."""
        sent = []

        class _Completions:
            def create(self, **kw):
                sent.append(kw)
                outcome = outcomes.pop(0) if outcomes else type("R", (), {"usage": None})()
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome

        class _Client:
            chat = type("C", (), {"completions": _Completions()})()

            def with_options(self, **_kw):
                return self

        return _Client(), sent

    def test_a_capacity_400_tries_the_next_region(self, three_regions):
        """It used to give up on the first one."""
        ok = type("R", (), {"usage": None})()
        client, sent = self._client([_status_error(400, CAPACITY), ok])
        llm.create_completion(client, model="m", messages=[])
        assert len(sent) == 2

    def test_a_capacity_400_everywhere_fails_without_the_waits(self, three_regions):
        """A region's window does not change by waiting, so the 5/15/30/60s
        ladder would only delay the same refusal by ~110s."""
        ok = type("R", (), {"usage": None})()
        outcomes = [_status_error(400, CAPACITY)] * 3 + [ok]
        client, sent = self._client(outcomes)
        with pytest.raises(APIStatusError):
            llm.create_completion(client, model="m", messages=[])
        assert len(sent) == 3, "one walk over the regions, then no re-send"

    def test_a_429_everywhere_still_falls_into_the_waits(self, three_regions):
        ok = type("R", (), {"usage": None})()
        outcomes = [_status_error(429, "RESOURCE_EXHAUSTED")] * 3 + [ok]
        client, sent = self._client(outcomes)
        llm.create_completion(client, model="m", messages=[])
        assert len(sent) == 4

    def test_an_ordinary_400_still_fails_on_the_first_region(self, three_regions):
        client, sent = self._client([_status_error(400, "Invalid JSON payload")])
        with pytest.raises(APIStatusError):
            llm.create_completion(client, model="m", messages=[])
        assert len(sent) == 1, "a malformed request must not be re-sent"


class TestTheInputWindowIsStatedAndChecked:
    """The window is 1,048,576 tokens and that is now written down and enforced
    before the call, so an oversized prompt names itself instead of arriving as a
    provider error that sounds like the capacity refusal above."""

    def test_the_budget_is_the_models_own_window(self):
        assert llm.settings.GEMINI_MAX_INPUT_TOKENS == 1_048_576

    def test_the_estimate_errs_high(self):
        """Fewer chars per token means more tokens per char, so the guard trips
        early rather than late. The corpus measures 3.68; the setting is below it
        on purpose."""
        assert gemini.settings.TOKEN_ESTIMATE_CHARS < 3.68

    def test_a_real_sized_account_is_nowhere_near_the_window(self, monkeypatch):
        """The largest measured payload is 1,226,071 chars. It must pass - the
        guard is a runaway detector, not a limiter on normal work."""
        monkeypatch.setattr(gemini.llm, "get_openai_client", object)
        _client, request = gemini._request("x" * 1_226_071,
                                          [{"role": "user", "content": "q"}],
                                          None, None)
        assert request["messages"][0]["content"].startswith("x")

    def test_a_prompt_over_the_window_is_refused_before_it_is_sent(self, monkeypatch):
        sent = []
        monkeypatch.setattr(gemini.llm, "get_openai_client", object)
        monkeypatch.setattr(gemini.llm, "create_completion",
                            lambda *_a, **kw: sent.append(kw))
        huge = "x" * (1_048_577 * 3 + 10)
        with pytest.raises(gemini.GeminiPromptTooLarge, match="input window"):
            gemini.generate(huge, [{"role": "user", "content": "q"}])
        assert sent == [], "nothing should reach the provider"

    def test_it_is_not_confused_with_a_capacity_refusal(self):
        """Similar-sounding, opposite meaning: one is worth retrying, the other
        never is. Separate exception so the two cannot be handled together."""
        assert issubclass(gemini.GeminiPromptTooLarge, gemini.GeminiUnavailable)
        assert not llm._is_capacity_refusal(
            gemini.GeminiPromptTooLarge("over the input window"))
SECRET_KEY = "AIzaSyTOTALLY-SECRET-KEY-VALUE-0001"
BODY = ('{"error": {"code": 400, "message": "The input token count (307661) '
        'exceeds the maximum number of tokens allowed (131072).", '
        '"status": "INVALID_ARGUMENT"}}')


def _detailed_error():
    """A 400 shaped like the real one: a URL naming its region, response headers
    carrying the provider's request id, and the key in the REQUEST headers."""
    request = httpx.Request(
        "POST",
        "https://asia-south1-aiplatform.googleapis.com/v1/projects/81911779229"
        "/locations/asia-south1/endpoints/openapi/chat/completions",
        headers={"x-goog-api-key": SECRET_KEY},
    )
    response = httpx.Response(
        400, request=request, text=BODY,
        headers={"x-request-id": "req-abc123", "x-goog-request-id": "goog-def456"},
    )
    return APIStatusError(CAPACITY, response=response, body=None)


class TestTheNextOccurrenceWillBeExplainable:
    """The refusal measured so far said the maximum allowed was 131,072 - not this
    model's window (1,048,576) and not any quota on the project - and ~30 probes
    since, up to 316,794 tokens on this exact path, were all accepted. It has not
    been reproducible, and the message string alone teaches nothing new. So the
    endpoint that served it and the provider's own request id are recorded."""

    def test_it_records_the_endpoint_request_id_and_body(self):
        detail = llm._refusal_detail(_detailed_error())
        assert detail["status"] == 400
        assert detail["endpoint"] == "asia-south1"
        assert detail["x-request-id"] == "req-abc123"
        assert detail["x-goog-request-id"] == "goog-def456"
        assert "131072" in detail["body"]

    def test_the_api_key_never_reaches_the_log(self):
        """The key travels in the REQUEST headers of the very call that failed, so
        only the response side is read and only an allowlist of names. A diagnostic
        that leaks the credential would be worse than no diagnostic."""
        detail = llm._refusal_detail(_detailed_error())
        assert SECRET_KEY not in repr(detail)
        assert not any("api-key" in k.lower() for k in detail)
        assert not any("authorization" in k.lower() for k in detail)

    def test_it_survives_an_exception_with_no_response(self):
        """Telemetry must never turn a handled failure into an unhandled one."""
        detail = llm._refusal_detail(_status_error(400, CAPACITY))
        assert detail["status"] == 400
        assert detail["body"]

    def test_it_is_logged_once_per_walk_at_warning(self, caplog, monkeypatch):
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
        monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                            property(lambda _self: ["global", "asia-south1",
                                                    "us-central1"]))
        monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "proj")
        monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0,))

        class _Completions:
            def create(self, **_kw):
                raise _detailed_error()

        class _Client:
            chat = type("C", (), {"completions": _Completions()})()

            def with_options(self, **_kw):
                return self

        with caplog.at_level("WARNING", logger="app.core.llm"),                 pytest.raises(APIStatusError):
            llm.create_completion(_Client(), model="m", messages=[])

        said = [r for r in caplog.records if "token capacity" in r.getMessage()]
        # One walk over three regions - no wait follows a capacity refusal -
        # and one line for it, because the other two regions say the same thing.
        assert len(said) == 1, [r.getMessage()[:60] for r in said]
        assert all(r.levelname == "WARNING" for r in said)
        assert SECRET_KEY not in caplog.text

    def test_an_ordinary_400_logs_no_capacity_line(self, caplog, monkeypatch):
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "openai")

        class _Completions:
            def create(self, **_kw):
                raise _status_error(400, "Invalid JSON payload")

        class _Client:
            chat = type("C", (), {"completions": _Completions()})()

        with caplog.at_level("WARNING", logger="app.core.llm"),                 pytest.raises(APIStatusError):
            llm.create_completion(_Client(), model="m", messages=[])
        assert "token capacity" not in caplog.text
SMALL_WINDOW = ("asia-northeast3", "europe-west9")


class TestSmallWindowRegionsAreKeptAwayFromBigPrompts:
    """MEASURED, 7 Oct, from the VM against all 24 configured regions with one
    232,986-token prompt: 22 accepted, and `asia-northeast3` and `europe-west9`
    refused with a 131,072 cap. `global` and `asia-south1` then took 963,786
    tokens, so the window really is ~1M and those two regions are the exception.

    Rotating over all 24 put ~8% of calls on one of them, and a ~300k-token chat
    prompt sent there is refused outright - which is what made Strategy Chat fail
    on some turns and not others."""

    @pytest.fixture
    def all_regions(self, monkeypatch):
        regions = ["global", "asia-south1", "asia-northeast3", "us-central1",
                   "europe-west9", "europe-west1"]
        monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
        monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                            property(lambda _self: list(regions)))
        monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "proj")
        return regions

    def _regions_for(self, estimated):
        class _C:
            def with_options(self, base_url=None, **_kw):
                copy = _C()
                copy.base_url = base_url
                return copy
        out = llm._regional_clients(_C(), "", estimated)
        return [u.base_url.split("/locations/")[1].split("/")[0] for u in out]

    def test_a_big_prompt_never_goes_to_a_small_window_region(self, all_regions):
        chosen = self._regions_for(300_000)
        for region in SMALL_WINDOW:
            assert region not in chosen, region

    def test_a_small_prompt_may_still_use_every_region(self, all_regions):
        """They serve 131,072 fine. Excluding them for everything would throw away
        two regions of quota spread that regeneration's small calls can use."""
        chosen = self._regions_for(50_000)
        assert set(chosen) == set(all_regions)

    def test_the_boundary_is_the_small_window_itself(self, all_regions):
        at = llm.settings.VERTEX_SMALL_WINDOW_TOKENS
        assert set(self._regions_for(at)) == set(all_regions)
        assert not set(self._regions_for(at + 1)) & set(SMALL_WINDOW)

    def test_affinity_also_never_pins_an_account_to_one(self, all_regions):
        """The hazard this closes. Hashing an account over all 24 regions would pin
        roughly one account in twelve to a small-window region, turning a failure
        that happened on ~8% of calls into one that happened on every call."""
        class _C:
            def with_options(self, base_url=None, **_kw):
                copy = _C()
                copy.base_url = base_url
                return copy
        for n in range(60):
            out = llm._regional_clients(_C(), "account-%d" % n, 300_000)
            first = out[0].base_url.split("/locations/")[1].split("/")[0]
            assert first not in SMALL_WINDOW, (n, first)

    def test_the_estimate_is_taken_from_the_request(self):
        """It reads the messages it is about to send, so no caller has to remember
        to declare a size."""
        big = {"messages": [{"role": "system", "content": "x" * 900_000},
                            {"role": "user", "content": "q"}]}
        assert llm._prompt_tokens_estimate(big) > llm.settings.VERTEX_SMALL_WINDOW_TOKENS
        assert llm._prompt_tokens_estimate({"messages": []}) == 0
        assert llm._prompt_tokens_estimate({}) == 0

    def test_excluding_everything_falls_back_rather_than_sending_nowhere(
            self, monkeypatch):
        """If every configured region were small-window, returning an empty list
        would make the call impossible. The provider's own answer is better than
        a silent nothing."""
        monkeypatch.setattr(type(llm.settings), "vertex_chat_locations",
                            property(lambda _self: list(SMALL_WINDOW)))
        assert llm.settings.vertex_chat_locations_for(300_000) == list(SMALL_WINDOW)
