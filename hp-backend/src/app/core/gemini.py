"""The whole-account call Strategy Chat makes.

Strategy Chat answers over the finished output of eight features at once -
about 113,000 tokens of widget JSON - in one pass, rather than retrieving
fragments of it. That needs a 1M context window, which the Gemini models this
platform runs on have.

It goes through the same client as every other model call (`core.llm`): the
same provider, key and endpoint (the Vertex express key travels in its header),
the same thinking budget, and the same short in-call waits on a 429/5xx. What
this module adds is what a long grounded answer needs on top of that.

**The output cap is always sent.** Gemini's default is small. An answer cut
short loses the citation tag that ends its last sentence, fails validation,
burns every attempt, and reaches the seller as "the evidence does not support
this" - a failure that looks like anything except a token limit. Truncation is
therefore detected from `finish_reason` and reported as itself.

**Failures are raised, not returned as None.** The chat has a refusal path that
tells the seller why, and a silent None there would render as an empty bubble.
"""

import logging

from app.config.settings import settings
from app.core import llm

logger = logging.getLogger(__name__)


class GeminiUnavailable(Exception):
    """The model could not answer, with a reason worth showing or logging."""


class GeminiTruncated(GeminiUnavailable):
    """The model stopped because it hit the output limit.

    Its own exception because the symptom is so misleading otherwise: the answer
    looks complete-ish, its last citation is missing, and the grounding
    validator rejects it. Raised here, the cause is in the message.
    """


def _turns(system_prompt: str, messages: list) -> list:
    """The system prompt, then the clean user/assistant turns.

    Anything that is not a clean user/assistant turn is dropped rather than
    sent: a malformed history arriving from a client must not become a way to
    write the prompt.
    """
    turns = [{"role": "system", "content": system_prompt}]
    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content})
    return turns


def _request(system_prompt, messages, max_output_tokens, temperature) -> tuple:
    client = llm.get_openai_client()
    if client is None:
        raise GeminiUnavailable("the model is not configured for this deployment")
    turns = _turns(system_prompt, messages)
    if len(turns) == 1:
        raise GeminiUnavailable("no question was asked")
    return client, {
        "model": settings.chat_model,
        "messages": turns,
        # Always set. See the module docstring - omitting this is the failure
        # that does not look like itself.
        "max_tokens": (settings.GEMINI_MAX_OUTPUT_TOKENS
                       if max_output_tokens is None else max_output_tokens),
        "temperature": (settings.GEMINI_TEMPERATURE
                        if temperature is None else temperature),
    }


def _record_usage(usage, timer=None) -> None:
    """Report what this call cost, to whatever step timer is in scope.

    Token counts are the half of the story latency does not tell. A turn that
    served most of its ~140k input tokens from cache and one that cached nothing
    take indistinguishable amounts of time and differ several-fold in price.

    `timer` is passed explicitly by the streaming path: a generator resumes in
    whatever context the server steps it from, so the one `steps.current()`
    returns there is not reliably the turn's own.

    Silent when nothing is measuring, and never raises: a missing counter must
    not turn a good answer into an error.
    """
    from app.observability import steps

    timer = timer or steps.current()
    if usage is None or timer is None:
        return
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    output_details = getattr(usage, "completion_tokens_details", None)
    timer.count("input_tokens", getattr(usage, "prompt_tokens", 0) or 0)
    timer.count("cached_tokens", getattr(prompt_details, "cached_tokens", 0) or 0)
    timer.count("output_tokens", getattr(usage, "completion_tokens", 0) or 0)
    timer.count("thinking_tokens",
                getattr(output_details, "reasoning_tokens", 0) or 0)


def _check_finish(reason, max_tokens) -> None:
    if reason == "length":
        # Named, not swallowed. Left to the validator this reads as a grounding
        # failure three attempts later.
        raise GeminiTruncated("the answer hit the %d-token output limit and was "
                              "cut off" % max_tokens)
    if reason == "content_filter":
        raise GeminiUnavailable("the model declined to answer (content filter)")


def _unavailable(exc) -> GeminiUnavailable:
    status = getattr(exc, "status_code", None)
    logger.error("strategy chat model call failed (%s): %s", status or "error", exc)
    return GeminiUnavailable("the model did not answer (%s)" % (status or "error"))


def generate(system_prompt: str, messages: list, *,
             max_output_tokens: int | None = None,
             temperature: float | None = None, timer=None,
             affinity: str = "") -> str:
    """One answer over the whole account payload.

    `timer` is passed explicitly for the same reason `generate_stream` takes one.
    The streamed endpoint cannot hold a context variable across a `yield`, so
    `answer_stream` only wraps setup in `steps.use` and generation runs with
    nothing current - which meant `steps.current()` was None here, `_record_usage`
    returned immediately, and every turn logged `"tokens": {}` and `cache n/a`.
    Timings survived because they use the timer object directly; the token and
    cache counters did not, which is why the cache rate has never been visible on
    the path the UI actually uses.

    `affinity` pins the Vertex region. The prefix here is the whole account and is
    byte-identical across the turns of a conversation, so it is exactly what a
    prompt cache is for - but a cache is per region, and the client rotated
    regions on every call. Passing the account id keeps one conversation on one
    region. See `llm._regional_clients`.
    """
    client, request = _request(system_prompt, messages, max_output_tokens,
                               temperature)
    try:
        response = llm.create_completion(client, affinity=affinity, **request)
    except Exception as exc:
        raise _unavailable(exc) from exc

    _record_usage(getattr(response, "usage", None), timer)
    choice = response.choices[0]
    _check_finish(choice.finish_reason, request["max_tokens"])
    text = (choice.message.content or "").strip()
    if not text:
        raise GeminiUnavailable("the model returned nothing (%s)"
                                % (choice.finish_reason or "no finish reason"))
    return text


def generate_stream(system_prompt: str, messages: list, *,
                    max_output_tokens: int | None = None,
                    temperature: float | None = None, timer=None,
                    affinity: str = ""):
    """`generate`, yielding text as the model writes it.

    Same request and same checks; the caller sees the answer being written
    instead of waiting for the whole of it. A truncated or refused answer raises
    after its last delta, exactly as `generate` would have raised.
    """
    client, request = _request(system_prompt, messages, max_output_tokens,
                               temperature)
    try:
        stream = llm.create_completion(
            client, affinity=affinity, stream=True,
            stream_options={"include_usage": True}, **request)
        finish = None
        for chunk in stream:
            if getattr(chunk, "usage", None):
                _record_usage(chunk.usage, timer)
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            finish = choice.finish_reason or finish
            delta = choice.delta
            if delta and delta.content:
                yield delta.content
    except GeminiUnavailable:
        raise
    except Exception as exc:
        raise _unavailable(exc) from exc
    _check_finish(finish, request["max_tokens"])
