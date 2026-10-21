"""Fault injection: the LLM client layer and the regeneration engine.

Part 1 drives `core/llm.py`, `core/gemini.py`, `services/hp/translate.py` and
the retrieval client's embedding POST with scripted provider failures - 429s,
5xx, timeouts, connection errors, empty/None/fenced/list/truncated answers,
missing `choices` and `usage` - and checks each entry point either returns its
documented failure value or raises its documented exception, and reports to
`run_context.note_llm` exactly once per logical call.

Part 2 drives the engine (in-memory Mongo fake, the synthetic graph of
test_regen_engine.py: A(d1) -> B(d2) -> C, D(d3)) through producer failures,
degraded output, partial runs and resubmits, a quota stop mid-run, a deleted
dataset, and the run document's status after its jobs have all finished.

Real defects are kept as `xfail(strict=True)` tests: they fail today and will
flip to XPASS (and so fail the suite) once fixed, so the marker gets removed.

No network: every client, POST and runner is a fake.
"""

import asyncio
import time
from types import SimpleNamespace as NS

import httpx
import openai
import pytest
from bson import ObjectId

from app.core import gemini, llm
from app.services.extractors.datasets import DatasetFileMissing
from app.services.hp import translate
from app.services.regen import context as run_context, jobs, planner, runs, state
from regen_fakes import FakeDb
from test_regen_engine import Harness

# ===========================================================================
# Part 1 - LLM client layer
# ===========================================================================

_REQ = httpx.Request("POST", "http://provider.invalid/v1/chat/completions")


def _status_error(cls, code, message="provider said no"):
    return cls(message, response=httpx.Response(code, request=_REQ), body=None)


def rate_limited():
    return _status_error(openai.RateLimitError, 429, "429 RESOURCE_EXHAUSTED")


def server_error():
    return _status_error(openai.InternalServerError, 503, "503 UNAVAILABLE")


def timed_out():
    return openai.APITimeoutError(request=_REQ)


def connection_reset():
    return openai.APIConnectionError(request=_REQ)


_UNSET = object()


def answer(content="{}", *, choices=_UNSET, usage=_UNSET, finish="stop"):
    """A chat completion as the SDK returns it. `usage=_UNSET` leaves it off."""
    if choices is _UNSET:
        choices = [NS(message=NS(content=content), finish_reason=finish)]
    resp = NS(choices=choices)
    if usage is not _UNSET:
        resp.usage = usage
    return resp


class FakeClient:
    """Answers `chat.completions.create` from a script; the last entry repeats.
    An exception in the script is raised. `with_options` (the per-region copy)
    returns the same client, so every region's call lands in `calls`."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []
        self.regions = []
        self.chat = NS(completions=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        item = self.script[min(len(self.calls), len(self.script)) - 1]
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return item()
        return item

    def with_options(self, **kw):
        self.regions.append(kw.get("base_url"))
        return self


@pytest.fixture
def one_region(monkeypatch):
    """A non-Vertex provider: one client, the SDK's own retries, four zero waits."""
    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0, 0, 0))
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", "")


@pytest.fixture
def ctx():
    c = run_context.RunContext(account_id="acct", node_id="node")
    with run_context.active(c):
        yield c


def _use(monkeypatch, client):
    monkeypatch.setattr(llm, "get_openai_client", lambda *_a, **_k: client)
    return client


# ------------------------------------------------------------ create_completion

def test_create_completion_429_then_success_returns_and_does_not_flag_quota(one_region, ctx):
    started = time.time()
    client = FakeClient(rate_limited(), rate_limited(), answer(usage=NS(total_tokens=7)))
    resp = llm.create_completion(client, model="m", messages=[])
    assert resp.choices and len(client.calls) == 3
    assert not run_context.quota_exhausted_since(started)
    assert ctx.api_calls == 1 and ctx.tokens == 7          # counted once, on success


def test_create_completion_429_forever_raises_and_flags_quota(one_region, ctx):
    started = time.time()
    client = FakeClient(rate_limited())
    with pytest.raises(openai.RateLimitError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == len(llm.RATE_LIMIT_WAITS) + 1
    assert run_context.quota_exhausted_since(started)
    assert ctx.api_calls == 0                              # nothing reached a model


def test_create_completion_5xx_forever_raises_without_flagging_quota(one_region):
    started = time.time()
    client = FakeClient(server_error())
    with pytest.raises(openai.InternalServerError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == len(llm.RATE_LIMIT_WAITS) + 1
    assert not run_context.quota_exhausted_since(started)


def test_create_completion_5xx_then_success_recovers(one_region):
    client = FakeClient(server_error(), answer())
    assert llm.create_completion(client, model="m", messages=[]).choices
    assert len(client.calls) == 2


@pytest.mark.parametrize("make", [timed_out, connection_reset], ids=["timeout", "conn"])
def test_create_completion_timeout_or_connection_error_is_waited_out(one_region, make):
    # With one region the SDK client also keeps its own retries for these (not
    # exercised by the fake); the wait ladder comes on top.
    client = FakeClient(make(), answer())
    assert llm.create_completion(client, model="m", messages=[]).choices
    assert len(client.calls) == 2


def test_create_completion_connection_error_forever_raises_without_flagging_quota(
        one_region):
    started = time.time()
    client = FakeClient(connection_reset())
    with pytest.raises(openai.APIConnectionError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == len(llm.RATE_LIMIT_WAITS) + 1
    assert not run_context.quota_exhausted_since(started)


def test_create_completion_timeout_forever_stops_at_the_timeout_cap(one_region):
    # A timeout costs the whole 300s request timeout, so it is not walked down
    # the full ladder: the 3rd timed-out attempt raises.
    started = time.time()
    client = FakeClient(timed_out())
    with pytest.raises(openai.APITimeoutError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == llm.MAX_TIMED_OUT_ATTEMPTS == 3
    assert not run_context.quota_exhausted_since(started)


def test_a_client_with_sdk_retries_counts_them_against_the_timeout_cap(one_region):
    # One region keeps the SDK's own retries (max_retries=2): its timeout means
    # the request may already have timed out three times inside the SDK.
    client = FakeClient(timed_out(), answer())
    client.max_retries = 2
    with pytest.raises(openai.APITimeoutError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == 1


@pytest.mark.parametrize("make", [
    lambda: _status_error(openai.BadRequestError, 400, "400 INVALID_ARGUMENT bad field"),
    lambda: _status_error(openai.PermissionDeniedError, 403, "403 denied"),
    lambda: _status_error(openai.NotFoundError, 404, "404 no such model"),
], ids=["400", "403", "404"])
def test_create_completion_other_4xx_is_not_retried(one_region, make):
    client = FakeClient(make(), answer())
    with pytest.raises(openai.APIStatusError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == 1


def test_create_completion_usage_missing_or_none_counts_zero_tokens(one_region, ctx):
    llm.create_completion(FakeClient(answer()), model="m", messages=[])
    llm.create_completion(FakeClient(answer(usage=None)), model="m", messages=[])
    llm.create_completion(FakeClient(answer(usage=NS(total_tokens=None))), model="m",
                          messages=[])
    assert ctx.api_calls == 3 and ctx.tokens == 0


def test_vertex_429_moves_to_the_next_region_before_any_wait(monkeypatch):
    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0,))
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "p")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", "r1,r2,r3")
    client = FakeClient(rate_limited(), rate_limited(), answer())
    assert llm.create_completion(client, model="m", messages=[]).choices
    assert len(client.calls) == 3 and len(client.regions) == 3


@pytest.fixture
def three_regions(monkeypatch):
    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0))
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "p")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", "r1,r2,r3")


@pytest.mark.parametrize("make", [connection_reset, server_error], ids=["conn", "5xx"])
def test_vertex_transient_error_moves_to_the_next_region(three_regions, make):
    client = FakeClient(make(), answer())
    assert llm.create_completion(client, model="m", messages=[]).choices
    assert len(client.calls) == 2 and len(client.regions) == 3   # one pass, 2nd region


@pytest.mark.parametrize("make", [connection_reset, server_error], ids=["conn", "5xx"])
def test_vertex_transient_error_everywhere_walks_every_region_per_wait(three_regions, make):
    started = time.time()
    client = FakeClient(make())
    with pytest.raises(openai.APIError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == 3 * (len(llm.RATE_LIMIT_WAITS) + 1)
    assert not run_context.quota_exhausted_since(started)


# ------------------------------------------------------------- the timeout cap

class RegionalClient:
    """A Vertex client whose per-region copies know their region, answering
    from one shared script (the last entry repeats)."""

    def __init__(self, *script, base_url="https://aiplatform.googleapis.com/root"):
        self.script, self.base_url = list(script), base_url
        self.calls = []                      # region of every attempt, in order
        self.chat = NS(completions=NS(create=self._create))
        self.max_retries = 2                 # the real SDK default

    def with_options(self, base_url=None, max_retries=None):
        copy = RegionalClient(base_url=base_url)
        copy.script, copy.calls, copy.max_retries = self.script, self.calls, max_retries
        return copy

    def _create(self, **_kw):
        self.calls.append(self.base_url.split("/locations/")[1].split("/")[0])
        item = self.script[min(len(self.calls), len(self.script)) - 1]
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture
def five_regions(monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (5, 15, 30, 60))
    monkeypatch.setattr(llm.time, "sleep", sleeps.append)
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "p")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", "r1,r2,r3,r4,r5")
    return sleeps


def test_the_third_timeout_raises_after_waits_each_in_another_region(five_regions):
    client = RegionalClient(timed_out())
    with pytest.raises(openai.APITimeoutError):
        llm.create_completion(client, affinity="acct", model="m", messages=[])
    assert len(client.calls) == 3 and len(set(client.calls)) == 3   # 3 regions
    assert five_regions == [5, 15]                       # a ladder wait between


def test_a_timeout_then_an_answer_goes_to_another_region(five_regions):
    client = RegionalClient(timed_out(), answer())
    assert llm.create_completion(client, affinity="acct", model="m", messages=[]).choices
    assert len(client.calls) == 2 and client.calls[0] != client.calls[1]
    assert five_regions == [5]


def test_a_connection_reset_still_hops_regions_without_a_wait(five_regions):
    client = RegionalClient(connection_reset(), connection_reset(), answer())
    assert llm.create_completion(client, affinity="acct", model="m", messages=[]).choices
    assert len(client.calls) == 3 and len(set(client.calls)) == 3
    assert five_regions == []                            # hops, no wait


def test_connection_resets_forever_keep_the_full_hop_and_ladder(five_regions):
    client = RegionalClient(connection_reset())
    with pytest.raises(openai.APIConnectionError):
        llm.create_completion(client, affinity="acct", model="m", messages=[])
    assert len(client.calls) == 5 * (len(llm.RATE_LIMIT_WAITS) + 1)
    assert five_regions == [5, 15, 30, 60]


@pytest.mark.parametrize("seed", range(40))
def test_timed_out_attempts_never_exceed_the_cap(five_regions, seed):
    import random

    rng = random.Random(seed)
    makers = [timed_out, connection_reset, rate_limited, server_error]
    script = [rng.choice(makers)() for _ in range(40)]
    client = RegionalClient(*script)
    with pytest.raises(openai.APIError):
        llm.create_completion(client, affinity="acct", model="m", messages=[])
    timed = [i for i, _ in enumerate(client.calls)
             if isinstance(script[min(i, len(script) - 1)], openai.APITimeoutError)]
    assert len(timed) <= llm.MAX_TIMED_OUT_ATTEMPTS
    regions = [client.calls[i] for i in timed]
    assert len(set(regions)) == len(regions)             # never the same region twice


def test_timeouts_in_a_single_region_reuse_it_up_to_the_cap(monkeypatch):
    monkeypatch.setattr(llm, "RATE_LIMIT_WAITS", (0, 0, 0, 0))
    monkeypatch.setattr(llm.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(llm.settings, "VERTEX_PROJECT", "p")
    monkeypatch.setattr(llm.settings, "VERTEX_LOCATIONS", "r1,r2")
    client = RegionalClient(timed_out())
    with pytest.raises(openai.APITimeoutError):
        llm.create_completion(client, affinity="acct", model="m", messages=[])
    # two regions: both time out, then the third attempt goes back to one of them
    assert len(client.calls) == 3 and len(set(client.calls)) == 2


def test_vertex_bad_request_is_not_sent_to_another_region(three_regions):
    client = FakeClient(_status_error(openai.BadRequestError, 400, "400 bad field"), answer())
    with pytest.raises(openai.BadRequestError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == 1


def test_vertex_capacity_refusal_everywhere_fails_at_once(three_regions):
    client = FakeClient(_status_error(
        openai.BadRequestError, 400, "maximum number of tokens allowed (131072)"))
    with pytest.raises(openai.BadRequestError):
        llm.create_completion(client, model="m", messages=[])
    assert len(client.calls) == 3                                 # no waits


# ---------------------------------------------- generate_gpt4o_json_completion

@pytest.mark.parametrize("script,expected,calls", [
    ([answer('```json\n{"a": 1}\n```')], {"a": 1}, 1),
    ([answer('{"a": 1}', usage=None)], {"a": 1}, 1),
    ([answer(None), answer('{"a": 2}')], {"a": 2}, 2),
    ([answer('{"a": [1, 2'), answer('{"a": 3}')], {"a": 3}, 2),        # truncated
    ([answer("[1, 2]"), answer('{"a": 4}')], {"a": 4}, 2),             # list
], ids=["fenced", "usage-none", "none-then-ok", "truncated-then-ok", "list-then-ok"])
def test_json_completion_recovers_and_notes_one_success(monkeypatch, ctx, one_region,
                                                        script, expected, calls):
    client = _use(monkeypatch, FakeClient(*script))
    assert llm.generate_gpt4o_json_completion("s", "u") == expected
    assert len(client.calls) == calls
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 0)
    assert ctx.api_calls == calls                         # every request is costed


@pytest.mark.parametrize("script,calls", [
    ([answer(None)], 2),
    ([answer("")], 2),
    ([answer("[1, 2]")], 2),
    ([answer('{"a": 1')], 2),
    ([answer("```json\n```")], 2),
    ([rate_limited()], len(llm.RATE_LIMIT_WAITS) + 1),
    ([server_error()], len(llm.RATE_LIMIT_WAITS) + 1),
    ([timed_out()], llm.MAX_TIMED_OUT_ATTEMPTS),
    ([connection_reset()], len(llm.RATE_LIMIT_WAITS) + 1),
    ([answer("not json"), rate_limited()], 1 + len(llm.RATE_LIMIT_WAITS) + 1),
    ([answer("{}")], 2),
    ([answer("```json {}```")], 2),
    ([answer(choices=[]), answer("{}")], 2),
], ids=["none", "empty", "list", "truncated", "empty-fence", "429-forever",
        "5xx-forever", "timeout", "conn", "bad-then-429", "empty-object",
        "fenced-empty-object", "no-choices-then-empty-object"])
def test_json_completion_failure_returns_none_and_notes_one_failure(
        monkeypatch, ctx, one_region, script, calls):
    client = _use(monkeypatch, FakeClient(*script))
    assert llm.generate_gpt4o_json_completion("s", "u") is None
    assert len(client.calls) == calls
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 1)


def test_json_completion_without_a_client_notes_one_failure(monkeypatch, ctx):
    _use(monkeypatch, None)
    assert llm.generate_gpt4o_json_completion("s", "u") is None
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 1)


@pytest.mark.parametrize("bad", [
    answer(choices=[]), answer(choices=None), answer(choices=[NS(message=None)]),
    NS(), answer(choices=[NS()])],
    ids=["choices-empty", "choices-none", "message-none", "no-choices-attr",
         "choice-without-message"])
def test_json_completion_with_no_choices_is_a_failure_not_a_crash(monkeypatch, ctx,
                                                                 one_region, bad):
    client = _use(monkeypatch, FakeClient(bad))
    assert llm.generate_gpt4o_json_completion("s", "u") is None
    assert len(client.calls) == 2                           # asked once more
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 1)


def test_json_completion_no_choices_then_a_good_answer_recovers(monkeypatch, ctx,
                                                                one_region):
    client = _use(monkeypatch, FakeClient(answer(choices=[]), answer('{"a": 5}')))
    assert llm.generate_gpt4o_json_completion("s", "u") == {"a": 5}
    assert len(client.calls) == 2
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 0)


@pytest.mark.parametrize("text", [
    '```json {"a": 1}```', '```{"a": 1}```', '```JSON\n{"a": 1}\n```',
    '```json\n{"a": 1}\n```\n', '```json {"a": 1}\n```'])
def test_one_line_fenced_json_is_read(monkeypatch, ctx, one_region, text):
    client = _use(monkeypatch, FakeClient(answer(text)))
    assert llm.generate_gpt4o_json_completion("s", "u") == {"a": 1}
    assert len(client.calls) == 1


# ----------------------------------------------------- generate_chat_completion

@pytest.mark.parametrize("script", [
    [answer(None)], [answer("   ")], [answer(choices=[])], [answer(choices=None)],
    [rate_limited()], [server_error()], [timed_out()], [connection_reset()],
], ids=["none", "blank", "choices-empty", "choices-none", "429", "5xx", "timeout",
        "conn"])
def test_chat_completion_failure_returns_none_and_notes_one_failure(
        monkeypatch, ctx, one_region, script):
    _use(monkeypatch, FakeClient(*script))
    assert llm.generate_chat_completion("s", [{"role": "user", "content": "hi"}]) is None
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 1)


def test_chat_completion_success_notes_one_success(monkeypatch, ctx, one_region):
    _use(monkeypatch, FakeClient(answer(" hello ")))
    assert llm.generate_chat_completion("s", [{"role": "user", "content": "hi"}]) == "hello"
    assert (ctx.llm_calls, ctx.llm_failures) == (1, 0)


def test_chat_completion_with_no_usable_turns_calls_nothing(monkeypatch, ctx):
    # Not a model call, so not counted (unlike the no-client path, which is).
    client = _use(monkeypatch, FakeClient(answer("x")))
    assert llm.generate_chat_completion("s", [{"role": "system", "content": "x"}]) is None
    assert client.calls == [] and ctx.llm_calls == 0


def test_stream_chat_completion_stops_quietly_on_a_mid_stream_error(monkeypatch, one_region):
    def stream():
        yield NS(choices=[])                                   # usage-only chunk
        yield NS(choices=[NS(delta=NS(content="par"))])
        yield NS(choices=[NS(delta=None)])
        raise connection_reset()

    _use(monkeypatch, FakeClient(stream))
    out = list(llm.stream_chat_completion("s", [{"role": "user", "content": "hi"}]))
    assert out == ["par"]                     # partial text, no exception


# ------------------------------------------------------------------- gemini.py

def _chat_messages():
    return [{"role": "user", "content": "q"}]


@pytest.mark.parametrize("script,exc", [
    ([answer(None)], gemini.GeminiUnavailable),
    ([answer("")], gemini.GeminiUnavailable),
    ([answer("cut", finish="length")], gemini.GeminiTruncated),
    ([answer("x", finish="content_filter")], gemini.GeminiUnavailable),
    ([rate_limited()], gemini.GeminiUnavailable),
    ([server_error()], gemini.GeminiUnavailable),
    ([timed_out()], gemini.GeminiUnavailable),
    ([connection_reset()], gemini.GeminiUnavailable),
], ids=["none", "empty", "length", "filter", "429", "5xx", "timeout", "conn"])
def test_gemini_generate_raises_its_own_exception(monkeypatch, one_region, script, exc):
    _use(monkeypatch, FakeClient(*script))
    with pytest.raises(exc):
        gemini.generate("s", _chat_messages())


@pytest.mark.parametrize("bad", [answer(choices=[]), answer(choices=None),
                                 answer(choices=[NS(message=None, finish_reason="stop")])],
                         ids=["choices-empty", "choices-none", "message-none"])
def test_gemini_generate_with_no_choices_is_unavailable(monkeypatch, one_region, bad):
    client = _use(monkeypatch, FakeClient(bad))
    with pytest.raises(gemini.GeminiUnavailable, match="no answer"):
        gemini.generate("s", _chat_messages())
    assert len(client.calls) == gemini.EMPTY_ANSWER_ATTEMPTS     # asked once more


@pytest.mark.parametrize("first", [answer(choices=[]), answer(None), answer("  ")],
                         ids=["no-choices", "none", "blank"])
def test_gemini_generate_empty_then_answer_recovers(monkeypatch, one_region, first):
    client = _use(monkeypatch, FakeClient(first, answer(" ok ")))
    assert gemini.generate("s", _chat_messages()) == "ok"
    assert len(client.calls) == 2


@pytest.mark.parametrize("script,exc", [
    ([answer("x", finish="content_filter"), answer("ok")], gemini.GeminiUnavailable),
    ([answer("cut", finish="length"), answer("ok")], gemini.GeminiTruncated),
], ids=["filter", "length"])
def test_gemini_generate_does_not_ask_again_after_a_filter_or_cut_off(
        monkeypatch, one_region, script, exc):
    client = _use(monkeypatch, FakeClient(*script))
    with pytest.raises(exc):
        gemini.generate("s", _chat_messages())
    assert len(client.calls) == 1


def test_gemini_stream_with_no_choice_in_any_chunk_is_unavailable(monkeypatch, one_region):
    def stream():
        yield NS(usage=None, choices=None)
        yield NS(usage=None, choices=[])

    _use(monkeypatch, FakeClient(stream))
    with pytest.raises(gemini.GeminiUnavailable, match="no answer"):
        list(gemini.generate_stream("s", _chat_messages()))


def test_gemini_stream_tolerates_a_choice_without_a_delta(monkeypatch, one_region):
    def stream():
        yield NS(usage=None, choices=[NS(finish_reason=None)])
        yield NS(usage=None, choices=[NS(delta=None, finish_reason=None)])
        yield NS(usage=None, choices=[NS(delta=NS(content="a"), finish_reason="stop")])

    _use(monkeypatch, FakeClient(stream))
    assert list(gemini.generate_stream("s", _chat_messages())) == ["a"]


def test_gemini_stream_error_mid_answer_is_unavailable(monkeypatch, one_region):
    def stream():
        yield NS(usage=None, choices=[NS(delta=NS(content="a"), finish_reason=None)])
        raise server_error()

    _use(monkeypatch, FakeClient(stream))
    got = []
    with pytest.raises(gemini.GeminiUnavailable):
        for piece in gemini.generate_stream("s", _chat_messages()):
            got.append(piece)
    assert got == ["a"]


def test_gemini_stream_cut_off_raises_truncated(monkeypatch, one_region):
    def stream():
        yield NS(usage=None, choices=[NS(delta=NS(content="a"), finish_reason="length")])

    _use(monkeypatch, FakeClient(stream))
    with pytest.raises(gemini.GeminiTruncated):
        list(gemini.generate_stream("s", _chat_messages()))


# ---------------------------------------------------------------- translate.py

@pytest.mark.parametrize("model_answer", [
    None, [], {"items": None}, {"items": "x"}, {"items": [None, 1, {"i": "x"}]},
    {"items": [{"i": 0, "english": ""}]},
    {"items": [{"i": 0, "english": "Results"}]},          # drops the "2026"
    {"items": [{"i": 9, "english": "2026 results"}]},     # index out of range
], ids=["none", "list", "items-none", "items-str", "junk-rows", "blank",
        "lost-number", "bad-index"])
def test_translate_keeps_the_original_on_any_bad_answer(monkeypatch, model_answer):
    monkeypatch.setattr(translate, "generate_gpt4o_json_completion",
                        lambda *_a: model_answer)
    assert translate.to_english(["2026年の決算"], None, "headline") == {}
    assert translate.one("2026年の決算", None, "headline") == "2026年の決算"


def test_translate_accepts_a_faithful_answer(monkeypatch):
    monkeypatch.setattr(translate, "generate_gpt4o_json_completion",
                        lambda *_a: {"items": [{"i": 0, "english": "2026 results"}]})
    assert translate.to_english(["2026年の決算"], None, "headline") == {
        "2026年の決算": "2026 results"}


# --------------------------------------------------------- retrieval embeddings

@pytest.fixture
def vertex_embed(monkeypatch):
    from app.services.retrieval import client
    monkeypatch.setattr(client.settings, "LLM_PROVIDER", "vertex")
    monkeypatch.setattr(client.settings, "GEMINI_API_KEY", "g-key")
    monkeypatch.setattr(client.settings, "VERTEX_EMBEDDING_LOCATIONS", "e1,e2")
    monkeypatch.setattr(client, "VERTEX_RETRY_WAITS", (0, 0))
    return client


def _fake_post(monkeypatch, codes):
    calls = []

    def post(url, headers=None, json=None, timeout=None, **_kw):
        calls.append(url)
        code = codes[min(len(calls), len(codes)) - 1]
        if isinstance(code, BaseException):
            raise code
        body = {"predictions": [{"embeddings": {"values": [0.5]}}
                                for _ in json["instances"]]}
        return httpx.Response(code, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)
    return calls


def test_embedding_429_in_every_region_forever_flags_quota_and_raises(monkeypatch,
                                                                      vertex_embed):
    started = time.time()
    calls = _fake_post(monkeypatch, [429])
    with pytest.raises(httpx.HTTPStatusError):
        vertex_embed._vertex_embed(["a"])
    assert len(calls) == (len(vertex_embed.VERTEX_RETRY_WAITS) + 1) * 2
    assert run_context.quota_exhausted_since(started)


def test_embedding_5xx_then_success_recovers(monkeypatch, vertex_embed):
    calls = _fake_post(monkeypatch, [503, 200])
    assert vertex_embed._vertex_embed(["a", "b"]) == [[0.5], [0.5]]
    assert len(calls) == 2


def test_embedding_connection_error_is_raised_at_once(monkeypatch, vertex_embed):
    # Documented current behaviour: no wait or region hop for a network error.
    calls = _fake_post(monkeypatch, [httpx.ConnectError("reset"), 200])
    with pytest.raises(httpx.ConnectError):
        vertex_embed._vertex_embed(["a"])
    assert len(calls) == 1


def test_retrieval_extraction_429_forever_flags_quota(monkeypatch, one_region):
    from app.services.retrieval import client as rclient
    started = time.time()
    fake = FakeClient(rate_limited())
    monkeypatch.setattr(rclient, "_openai_client", lambda: fake)
    with pytest.raises(openai.RateLimitError):
        asyncio.run(rclient._llm_model_func("p", system_prompt="s"))
    assert run_context.quota_exhausted_since(started)


# ===========================================================================
# Part 2 - regeneration engine
# ===========================================================================

@pytest.fixture
def h(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "GATE_RETRY_SECONDS", 0)
    db = FakeDb()
    from app.database import mongodb
    monkeypatch.setattr(mongodb.db_instance, "db", db)
    return Harness(db, tmp_path)


def _fresh(h):
    acct = h.account()
    h.add_file(acct, "d1", "x\n1\n")
    h.add_file(acct, "d2", "y\n2\n")
    h.add_file(acct, "d3", "z\n3\n")
    return acct


def _loaded(h):
    acct = _fresh(h)
    h.submit(acct)
    h.drain()
    h.log.clear()
    return acct


def _gens(h, acct, keys=("a", "b", "c", "dw")):
    return {k: h.widget(acct, k)["generation_id"] for k in keys}


def _by_node(run):
    return {j["node_id"]: j for j in run["jobs"]}


# ---------------------------------------------------------- producer failures

def test_a_producer_that_raises_keeps_output_and_skips_downstream(h):
    acct = _loaded(h)
    before = _gens(h, acct)
    h.fail["A"] = RuntimeError("model down")
    h.upload(acct, "d1", "x\n2\n")
    run = h.submit(acct)
    h.drain()                                   # no exception escapes the worker
    got = runs.get(h.db, run["_id"])
    rows = _by_node(got)
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert rows["A"]["status"] == jobs.FAILED
    assert rows["A"]["error"]["code"] == "ERROR"
    assert "RuntimeError: model down" in rows["A"]["error"]["message"]
    assert rows["B"]["status"] == jobs.SKIPPED and rows["B"]["blocked_by"] == ["A"]
    assert rows["C"]["status"] == jobs.SKIPPED and rows["C"]["blocked_by"] == ["B"]
    assert "D" not in rows                      # current, not planned
    assert h.ran(acct) == ["A"]
    assert _gens(h, acct) == before             # previous output kept everywhere
    assert h.live_jobs() == []


def test_a_degraded_result_keeps_output_and_skips_downstream(h):
    acct = _loaded(h)
    before = _gens(h, acct)
    h.degrade.add("A")
    h.upload(acct, "d1", "x\n3\n")
    run = h.submit(acct)
    h.drain()
    got = runs.get(h.db, run["_id"])
    rows = _by_node(got)
    assert rows["A"]["status"] == jobs.FAILED
    assert rows["A"]["error"]["code"] == "DEGRADED"
    assert "previous output is kept" in rows["A"]["error"]["message"]
    assert rows["B"]["status"] == rows["C"]["status"] == jobs.SKIPPED
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert _gens(h, acct) == before
    assert h.status(acct, "A") == planner.FAILED


def test_a_producer_whose_model_returns_no_choices_fails_the_section_not_the_worker(
        h, monkeypatch, one_region):
    """A model answer with no choices is a failed model call (None + one noted
    failure), so the section is DEGRADED and its previous output kept - not an
    IndexError out of the producer."""
    acct = _loaded(h)
    before = _gens(h, acct)
    _use(monkeypatch, FakeClient(answer(choices=[])))
    plain = h.runners["D"]

    def calls_the_model(account_id, **kw):
        llm.generate_gpt4o_json_completion("s", "u")
        return plain(account_id, **kw)

    h.engine.runners["D"] = calls_the_model
    h.upload(acct, "d3", "z\n4\n")
    run = h.submit(acct)
    h.drain()
    [job] = runs.get(h.db, run["_id"])["jobs"]
    assert job["status"] == jobs.FAILED and job["error"]["code"] == "DEGRADED"
    assert "IndexError" not in job["error"]["message"]
    assert _gens(h, acct) == before


def test_a_dataset_file_vanishing_mid_run_fails_files_missing_and_keeps_output(h):
    acct = _loaded(h)
    before = _gens(h, acct)
    h.fail["D"] = DatasetFileMissing("d3", "uploads/gone.csv")
    h.upload(acct, "d3", "z\n5\n")
    run = h.submit(acct)
    h.drain()
    [job] = runs.get(h.db, run["_id"])["jobs"]
    assert job["status"] == jobs.FAILED and job["error"]["code"] == "FILES_MISSING"
    assert _gens(h, acct) == before


def test_a_deleted_dataset_is_not_run_and_its_last_output_stays(h):
    """Observed behaviour (not asserted as right or wrong): after the only file a
    section reads is deleted, the section is NO_DATA, a Submit does not run it,
    and its last committed output - built from the deleted file - stays served."""
    acct = _loaded(h)
    before = _gens(h, acct)
    h.db["account_data_files"].update_many({"account_id": acct, "dataset_key": "d1"},
                                           {"$set": {"status": "deleted"}})
    assert h.status(acct, "A") == planner.NO_DATA
    run = h.submit(acct)
    items = {i["node_id"]: i["action"] for i in run["plan"]["accounts"][0]["items"]}
    assert items["A"] == planner.CANNOT_RUN
    h.drain()
    assert "A" not in h.ran(acct)
    assert h.widget(acct, "a")["generation_id"] == before["a"]


def test_a_successful_job_is_failed_if_the_quota_flag_trips_anywhere_meanwhile(h):
    """Design as documented in context.py (process-wide quota flag): a job whose
    own calls all succeeded is still failed QUOTA_EXHAUSTED, and its output
    discarded, when any thread flagged the quota while it ran. Pinned here
    because with REGEN_WORKERS > 1 it fails other accounts' good work."""
    acct = _loaded(h)
    before = _gens(h, acct)
    plain = h.runners["D"]

    def other_thread_hits_quota(account_id, **kw):
        plain(account_id, **kw)                      # publishes a good widget
        run_context.note_quota_exhausted()           # e.g. another account's 429

    h.engine.runners["D"] = other_thread_hits_quota
    h.upload(acct, "d3", "z\n6\n")
    run = h.submit(acct)
    h.drain()
    [job] = runs.get(h.db, run["_id"])["jobs"]
    assert job["status"] == jobs.FAILED and job["error"]["code"] == "QUOTA_EXHAUSTED"
    assert _gens(h, acct) == before
    jobs.resume(h.db, "test")


# ------------------------------------------------------------ partial runs

def _partial(h):
    """A failed, B and C skipped behind it, D current."""
    acct = _loaded(h)
    h.fail["A"] = RuntimeError("model down")
    h.upload(acct, "d1", "x\n7\n")
    h.submit(acct)
    h.drain()
    del h.fail["A"]
    h.log.clear()
    return acct


def _actions(run):
    return {i["node_id"]: i["action"] for i in run["plan"]["accounts"][0]["items"]}


def test_resubmitting_only_the_failed_node_runs_only_it(h):
    acct = _partial(h)
    run = h.submit(acct, nodes=["A"])
    assert _actions(run) == {"A": planner.RUN}
    assert run["plan"]["accounts"][0]["downstream_left_stale"] == ["B", "C"]
    h.drain()
    assert h.ran(acct) == ["A"]
    assert [h.status(acct, n) for n in "ABC"] == [planner.CURRENT, planner.STALE,
                                                  planner.STALE]


def test_resubmitting_the_failed_node_with_downstream_runs_failed_and_skipped(h):
    acct = _partial(h)
    run = h.submit(acct, nodes=["A"], include_downstream=True)
    assert _actions(run) == {"A": planner.RUN, "B": planner.RUN, "C": planner.RUN}
    h.drain()
    assert h.ran(acct) == ["A", "B", "C"]
    assert runs.get(h.db, run["_id"])["status"] == runs.SUCCEEDED


def test_resubmitting_the_whole_account_runs_failed_and_skipped_and_skips_current(h):
    acct = _partial(h)
    run = h.submit(acct)
    acts = _actions(run)
    assert [acts[n] for n in "ABC"] == [planner.RUN] * 3
    assert acts["D"] == planner.SKIP_CURRENT
    h.drain()
    assert h.ran(acct) == ["A", "B", "C"]


def test_resubmitting_a_skipped_node_pulls_in_its_failed_ancestor(h):
    acct = _partial(h)
    run = h.submit(acct, nodes=["C"])
    assert _actions(run) == {"A": planner.RUN, "B": planner.RUN, "C": planner.RUN}
    h.drain()
    assert [h.status(acct, n) for n in "ABC"] == [planner.CURRENT] * 3


# ------------------------------------------------------------ quota mid-run

def test_quota_mid_run_pauses_the_queue_and_waiting_sections_do_not_fail(h):
    acct = _loaded(h)

    def quota(account_id, **_kw):
        h.log.append((account_id, "A"))
        run_context.note_quota_exhausted()
        raise RuntimeError("429 RESOURCE_EXHAUSTED")

    h.engine.runners["A"] = quota
    h.upload(acct, "d1", "x\n8\n")
    run = h.submit(acct)
    out = h.drain()
    assert [o["outcome"] for o in out] == ["failed"]
    assert out[0]["error"]["code"] == "QUOTA_EXHAUSTED"
    qs = jobs.queue_state(h.db)
    assert qs["paused"] and qs["resume_after"] is not None      # lifts by itself
    waiting = {j["node_id"]: j["status"] for j in h.live_jobs(acct)}
    assert waiting == {"B": jobs.PENDING, "C": jobs.PENDING}    # not failed
    assert runs.get(h.db, run["_id"])["status"] == runs.RUNNING  # legitimately

    jobs.resume(h.db, "user:1")
    h.engine.runners["A"] = h._runner("A")
    h.drain()
    got = runs.get(h.db, run["_id"])
    rows = _by_node(got)
    assert rows["B"]["status"] == rows["C"]["status"] == jobs.SKIPPED
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert h.ran(acct) == ["A"]                                 # nothing re-ran A


# ------------------------------------------------- run status reaches terminal

@pytest.mark.parametrize("fail_a", [False, True], ids=["succeeded", "with-failures"])
def test_a_finished_run_is_listed_with_a_terminal_status(h, fail_a):
    acct = _fresh(h)
    if fail_a:
        h.fail["A"] = RuntimeError("model down")
    run = h.submit(acct)
    h.drain()
    assert all(j["status"] in jobs.TERMINAL
               for j in h.db[jobs.COLLECTION].find({"run_ids": run["_id"]}))
    [listed] = runs.recent(h.db, acct)
    assert listed["status"] in (runs.SUCCEEDED, runs.COMPLETED_WITH_FAILURES)


@pytest.mark.parametrize("fail_a", [False, True], ids=["succeeded", "with-failures"])
def test_the_run_status_is_stored_when_its_last_job_finishes(h, fail_a):
    """Without anyone reading the run: the job path settles it."""
    acct = _fresh(h)
    if fail_a:
        h.fail["A"] = RuntimeError("model down")
    run = h.submit(acct)
    stored = h.db[runs.COLLECTION].find_one({"_id": run["_id"]})
    assert stored["status"] == runs.RUNNING                  # jobs still queued
    h.drain()
    stored = h.db[runs.COLLECTION].find_one({"_id": run["_id"]})
    want = runs.COMPLETED_WITH_FAILURES if fail_a else runs.SUCCEEDED
    assert stored["status"] == want and stored.get("finished_at")
    assert runs.get(h.db, run["_id"])["status"] == want


def _make_stuck(h, run_id):
    """A run from before settling existed: jobs all finished, stored RUNNING."""
    h.db[runs.COLLECTION].update_one({"_id": run_id}, {"$set": {"status": runs.RUNNING},
                                                       "$unset": {"finished_at": ""}})


def test_an_old_stuck_run_is_listed_and_stored_with_its_real_status(h):
    acct = _fresh(h)
    run = h.submit(acct)
    h.drain()
    _make_stuck(h, run["_id"])
    assert [r["_id"] for r in runs.stuck(h.db)] == [run["_id"]]
    assert runs.stuck(h.db)[0]["would_be"] == runs.SUCCEEDED
    assert runs.recent(h.db, acct)[0]["status"] == runs.SUCCEEDED
    stored = h.db[runs.COLLECTION].find_one({"_id": run["_id"]})
    assert stored["status"] == runs.SUCCEEDED and stored.get("finished_at")
    assert runs.stuck(h.db) == []


def test_a_run_whose_jobs_finished_before_it_was_stored_is_settled_by_create(h,
                                                                           monkeypatch):
    acct = _fresh(h)
    real_insert = h.db[runs.COLLECTION].insert_one

    def insert_after_the_jobs_ran(doc):
        h.drain()                          # every job finishes before the insert
        return real_insert(doc)

    monkeypatch.setattr(h.db[runs.COLLECTION], "insert_one", insert_after_the_jobs_ran)
    run = h.submit(acct)
    assert run["status"] == runs.SUCCEEDED
    stored = h.db[runs.COLLECTION].find_one({"_id": run["_id"]})
    assert stored["status"] == runs.SUCCEEDED


def test_a_failing_settle_does_not_break_finishing_the_job(h, monkeypatch):
    acct = _fresh(h)
    run = h.submit(acct)

    def broken(*_a, **_k):
        raise RuntimeError("mongo blip")

    with monkeypatch.context() as m:
        m.setattr(runs, "settle", broken)
        h.drain()                                      # no exception escapes
    assert h.live_jobs() == []
    assert h.db[runs.COLLECTION].find_one({"_id": run["_id"]})["status"] == runs.RUNNING
    assert runs.recent(h.db, acct)[0]["status"] == runs.SUCCEEDED     # repaired


def test_a_stuck_running_run_blocks_neither_submits_nor_the_queue(h):
    acct = _loaded(h)
    _make_stuck(h, runs.recent(h.db, acct)[0]["_id"])
    h.upload(acct, "d3", "z\n9\n")
    run = h.submit(acct)
    assert run["status"] == runs.RUNNING and run["totals"]["queued"] == 1
    h.drain()
    assert h.ran(acct) == ["D"]
    assert runs.get(h.db, run["_id"])["status"] == runs.SUCCEEDED


@pytest.mark.parametrize("stuck", [False, True], ids=["settled", "stored-running"])
def test_cancelling_a_finished_run_does_not_rewrite_its_outcome(h, stuck):
    acct = _fresh(h)
    run = h.submit(acct)
    h.drain()
    if stuck:
        _make_stuck(h, run["_id"])
    out = runs.cancel(h.db, run["_id"], "user:1")
    assert out["cancelled"] == 0
    assert runs.get(h.db, run["_id"])["status"] == runs.SUCCEEDED
    assert "cancelled_by" not in h.db[runs.COLLECTION].find_one({"_id": run["_id"]})


@pytest.mark.xfail(strict=True, reason=(
    "DEFERRED: (race, low) when a node is planned RUN but its job is claimed before "
    "runs.create enqueues it, jobs.enqueue (jobs.py:131-143) records the run only "
    "in rerun_run_ids. runs.get queries run_ids, sees no jobs and PERSISTS "
    "SUCCEEDED while the work is still owed; if the running job is then failed "
    "by fail_owned/reclaim_expired (which never call _requeue_rerun) the rerun is "
    "dropped and the run stays SUCCEEDED with 0 jobs although nothing ran for it"))
def test_a_run_coalesced_into_a_running_job_is_not_reported_succeeded(h, monkeypatch):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n10\n")
    planned_before_claim = planner.plan(h.engine, accounts=[acct], nodes=["D"])
    h.submit(acct, nodes=["D"])
    running = jobs.claim(h.db, "w1")
    assert running["node_id"] == "D"
    # Run B was planned before the claim and enqueues after it.
    monkeypatch.setattr(planner, "plan", lambda *_a, **_k: planned_before_claim)
    run_b = runs.create(h.engine, accounts=[acct], nodes=["D"], actor="user:2")
    assert run_b["status"] == runs.RUNNING and run_b["totals"]["queued"] == 1
    # The worker running D dies; nothing re-queues D for run B.
    jobs.fail_owned(h.db, "w1")
    got = runs.get(h.db, run_b["_id"])
    assert got["status"] != runs.SUCCEEDED and got["progress"]["total"] == 1


def test_a_cancelled_run_with_a_still_running_job_finishes_as_cancelled(h):
    acct = _loaded(h)
    h.upload(acct, "d1", "x\n11\n")
    run = h.submit(acct)
    job = jobs.claim(h.db, "w1")                       # A runs
    out = runs.cancel(h.db, run["_id"], "user:1")
    assert out["cancelled"] == 2                       # B and C were waiting
    assert runs.get(h.db, run["_id"])["status"] == runs.RUNNING
    assert jobs.finish(h.db, job, jobs.SUCCEEDED)
    assert runs.get(h.db, run["_id"])["status"] == runs.CANCELLED


def test_an_engine_crash_mid_job_still_lets_the_run_finish(h, monkeypatch):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n12\n")
    run = h.submit(acct)

    def boom(_job):
        raise KeyError("engine bug")

    monkeypatch.setattr(h.engine, "run_job", boom)
    out = h.drain()
    assert [o["error"]["code"] for o in out] == ["ENGINE_ERROR"]
    got = runs.get(h.db, run["_id"])
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert got["jobs"][0]["error"]["code"] == "ENGINE_ERROR"


def test_a_worker_that_died_lets_the_run_finish_with_the_reason(h):
    acct = _loaded(h)
    h.upload(acct, "d3", "z\n13\n")
    run = h.submit(acct)
    jobs.claim(h.db, "dead-worker")
    h.db[jobs.COLLECTION].update_many(
        {"status": jobs.RUNNING},
        {"$set": {"lease_expires_at": state._now().replace(year=2000)}})
    assert h.engine.run_once() is None                 # reclaims, claims nothing
    got = runs.get(h.db, run["_id"])
    assert got["status"] == runs.COMPLETED_WITH_FAILURES
    assert got["jobs"][0]["error"]["code"] == jobs.WORKER_STOPPED


def test_a_job_for_a_node_removed_from_the_graph_does_not_hang_its_run(h):
    acct = _loaded(h)
    run_id = ObjectId()
    h.db[runs.COLLECTION].insert_one({"_id": run_id, "status": runs.RUNNING,
                                      "account_ids": [acct], "created_at": state._now()})
    jobs.enqueue(h.db, acct, "gone_node", jobs.trigger("manual"), run_id=run_id)
    out = h.drain()
    assert [o["outcome"] for o in out] == ["cancelled"]
    # Cancelled jobs count as finished, not failed.
    assert runs.get(h.db, run_id)["status"] == runs.SUCCEEDED
