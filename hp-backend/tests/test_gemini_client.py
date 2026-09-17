"""The Gemini client, against a stubbed API - no network, no key needed.

Strategy Chat is the only feature on Gemini, and three of its failure modes are
invisible from the outside:

**A truncated answer looks like a grounding failure.** Nothing else in this
codebase caps output tokens, because gpt-4o's default is generous; Gemini's is
not. An answer cut at the limit loses the citation tag closing its last
sentence, fails deterministic validation, burns all three retries and reaches
the seller as "the evidence does not support this". So `max_output_tokens` is
asserted to be sent on every call, and `MAX_TOKENS` is asserted to raise as
itself.

**A bad key retried three times is three times the latency and the same
failure.** Transient (429/500/503) and fatal (400/401/403) must be told apart by
status code, not by string matching.

**A malformed history must not become a way to write the prompt.** Anything
that is not a clean user or assistant turn is dropped rather than forwarded.

Run: python -m pytest tests/test_gemini_client.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from google.genai import errors

from app.core import gemini

FENCE = "```"


class _Reason:
    """Stands in for the FinishReason enum, which is read via `.name`."""

    def __init__(self, name):
        self.name = name


class _Response:
    def __init__(self, text="an answer", finish_reason="STOP"):
        self.text = text
        self.candidates = [
            type("C", (), {"finish_reason": _Reason(finish_reason)})()]


class _Models:
    """Replays a scripted sequence of outcomes and records every call."""

    def __init__(self, script):
        self._script = list(script)
        self.calls = []

    def generate_content(self, *, model, contents, config):
        self.calls.append({"model": model, "contents": contents,
                           "config": config})
        outcome = self._script.pop(0) if self._script else _Response()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class _Client:
    def __init__(self, script):
        self.models = _Models(script)


@pytest.fixture
def no_sleep(monkeypatch):
    """Retries are tested for their shape, not their wall-clock cost."""
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)


def _install(monkeypatch, script):
    client = _Client(script)
    monkeypatch.setattr(gemini, "_client", lambda: client)
    return client


def _busy(status=503):
    return errors.APIError(status, {"error": {"message": "overloaded"}})


# --- the message adapter -------------------------------------------------

def test_assistant_becomes_model_and_system_is_not_sent_in_band():
    contents = gemini.to_contents([
        {"role": "system", "content": "you are a system prompt"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ])
    assert [c.role for c in contents] == ["user", "model"]
    assert [c.parts[0].text for c in contents] == ["hello", "hi"]


def test_malformed_turns_are_dropped_not_forwarded():
    contents = gemini.to_contents([
        "not a dict",
        {"role": "user"},                       # no content
        {"role": "user", "content": "   "},     # whitespace only
        {"role": "tool", "content": "output"},  # not a conversational turn
        {"content": "no role"},
        {"role": "USER", "content": "kept"},    # case normalised, not rejected
    ])
    assert len(contents) == 1
    assert contents[0].parts[0].text == "kept"


# --- the output limit ----------------------------------------------------

def test_max_output_tokens_is_always_sent(monkeypatch):
    client = _install(monkeypatch, [_Response()])
    gemini.generate("system", [{"role": "user", "content": "q"}])
    config = client.models.calls[0]["config"]
    assert config.max_output_tokens == gemini.settings.GEMINI_MAX_OUTPUT_TOKENS
    assert config.max_output_tokens >= 8192
    assert config.system_instruction == "system"


def test_an_explicit_limit_overrides_the_setting(monkeypatch):
    client = _install(monkeypatch, [_Response()])
    gemini.generate("system", [{"role": "user", "content": "q"}],
                    max_output_tokens=256)
    assert client.models.calls[0]["config"].max_output_tokens == 256


def test_hitting_the_limit_raises_as_itself_not_as_an_empty_answer(monkeypatch):
    _install(monkeypatch,
             [_Response(text="cut off mid-", finish_reason="MAX_TOKENS")])
    with pytest.raises(gemini.GeminiTruncated) as caught:
        gemini.generate("system", [{"role": "user", "content": "q"}])
    assert "output limit" in str(caught.value)


def test_a_safety_block_is_reported_as_a_refusal(monkeypatch):
    _install(monkeypatch, [_Response(text="", finish_reason="SAFETY")])
    with pytest.raises(gemini.GeminiUnavailable) as caught:
        gemini.generate("system", [{"role": "user", "content": "q"}])
    assert "declined" in str(caught.value)


# --- transient vs fatal --------------------------------------------------

@pytest.mark.parametrize("status", sorted(gemini.RETRYABLE_STATUS))
def test_saturation_is_retried_and_then_succeeds(monkeypatch, no_sleep, status):
    client = _install(monkeypatch,
                      [_busy(status), _Response(text="second attempt")])
    answer = gemini.generate("s", [{"role": "user", "content": "q"}])
    assert answer == "second attempt"
    assert len(client.models.calls) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_a_fatal_status_is_not_retried(monkeypatch, no_sleep, status):
    client = _install(monkeypatch, [_busy(status)])
    with pytest.raises(gemini.GeminiUnavailable):
        gemini.generate("s", [{"role": "user", "content": "q"}])
    assert len(client.models.calls) == 1, "a fatal error was retried"


def test_the_fallback_model_is_a_second_capacity_pool(monkeypatch, no_sleep):
    script = [_busy() for _ in range(gemini.MAX_ATTEMPTS)]
    script.append(_Response(text="from the fallback"))
    client = _install(monkeypatch, script)

    answer = gemini.generate("s", [{"role": "user", "content": "q"}])

    assert answer == "from the fallback"
    models = [c["model"] for c in client.models.calls]
    primary = gemini.settings.GEMINI_MODEL_NAME
    assert models[:gemini.MAX_ATTEMPTS] == [primary] * gemini.MAX_ATTEMPTS
    assert models[-1] == gemini.settings.GEMINI_FALLBACK_MODEL


def test_exhausting_both_models_raises_rather_than_returning_none(
        monkeypatch, no_sleep):
    _install(monkeypatch, [_busy(429) for _ in range(gemini.MAX_ATTEMPTS * 2)])
    with pytest.raises(gemini.GeminiUnavailable):
        gemini.generate("s", [{"role": "user", "content": "q"}])


# --- configuration -------------------------------------------------------

def test_an_unconfigured_deployment_declines_rather_than_improvising(
        monkeypatch):
    monkeypatch.setattr(gemini.settings, "GEMINI_API_KEY", "")
    with pytest.raises(gemini.GeminiUnavailable) as caught:
        gemini.generate("s", [{"role": "user", "content": "q"}])
    assert "not configured" in str(caught.value)


def test_an_empty_question_is_refused_before_the_api_is_called(monkeypatch):
    client = _install(monkeypatch, [_Response()])
    with pytest.raises(gemini.GeminiUnavailable):
        gemini.generate("s", [{"role": "system", "content": "only a system turn"}])
    assert client.models.calls == []


# --- JSON ----------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ('{"a": 1}', {"a": 1}),
    (FENCE + 'json\n{"a": 1}\n' + FENCE, {"a": 1}),
    (FENCE + '\n{"a": 1}\n' + FENCE, {"a": 1}),
    ("not json at all", None),
    ("", None),
    (None, None),
    ("[1, 2, 3]", None),  # a list is not the object shape every caller expects
])
def test_json_survives_a_markdown_fence(raw, expected):
    assert gemini.parse_json(raw) == expected
