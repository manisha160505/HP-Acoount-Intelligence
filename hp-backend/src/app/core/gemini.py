"""Gemini, for Strategy Chat and nothing else.

Every other feature talks to Azure-hosted OpenAI through `llm.py`. This module
exists for one reason: Strategy Chat answers over the finished output of eight
features at once - about 113,000 tokens of widget JSON - and that does not fit
gpt-4o's 128K window with room left for the conversation. Rather than retrieve
fragments of the account, the feature reads all of it in one pass from a model
with a 1M window.

Three things here are load-bearing.

**`max_output_tokens` is always sent.** Nothing else in this codebase caps
output, because gpt-4o's default is generous; Gemini's is not. An answer cut
short loses the citation tag that ends its last sentence, fails validation,
burns every retry, and reaches the seller as "the evidence does not support
this" - a failure that looks like anything except a token limit. Truncation is
therefore detected explicitly, via `finish_reason`, and reported as itself.

**Transient and fatal are told apart.** The flash models return 429 and 503
whenever Google's capacity is saturated. Retrying those is right; retrying a bad
key or a malformed request is pure latency. The split is by exception class and
status code, not by string matching.

**The fallback is a different capacity pool, not a cheaper tier.** When the
primary is saturated, asking it again usually fails again, so the retry ladder
ends by moving to a second model rather than by waiting longer.

Model ids are not guesses: they were verified against the live API for this
project's key. `gemini-2.5-flash-lite` and `gemini-2.0-flash` 404 on it.
"""

import json
import logging
import random
import time

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Google's own guidance, and what the reference implementation retries on: 429
# is rate limiting, 500 an internal error, 503 "model is currently experiencing
# high demand". Everything else - a bad key, a malformed request, a safety
# block - fails the same way on the second attempt as on the first.
RETRYABLE_STATUS = frozenset({429, 500, 503})
MAX_ATTEMPTS = 3
BASE_DELAY_SECONDS = 0.5


class GeminiUnavailable(Exception):
    """Gemini could not answer, with a reason worth showing or logging."""


class GeminiTruncated(GeminiUnavailable):
    """The model stopped because it hit the output limit.

    Its own exception because the symptom is so misleading otherwise: the answer
    looks complete-ish, its last citation is missing, and the grounding
    validator rejects it. Raised here, the cause is in the message.
    """


def _client():
    """A client, or None when Gemini is not configured.

    None rather than a raise: the caller turns it into "Strategy Chat is not
    configured", which is a truthful answer. A feature that cannot be grounded
    should decline rather than improvise.
    """
    api_key = (settings.GEMINI_API_KEY or "").strip()
    if not api_key:
        logger.warning("GEMINI_API_KEY is not set - Strategy Chat cannot answer.")
        return None
    from google import genai

    return genai.Client(api_key=api_key)


def to_contents(messages: list) -> list:
    """OpenAI-shaped history -> Gemini `contents`.

    Two differences that are not optional. Gemini calls the assistant `model`,
    and it takes no system turn at all - the system prompt is hoisted to
    `system_instruction`, a sibling of `contents`.

    Anything that is not a clean user/assistant turn is dropped rather than
    sent, exactly as `llm.generate_chat_completion` does: a malformed history
    arriving from a client must not become a way to write the prompt.
    """
    from google.genai import types

    out = []
    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue
        out.append(types.Content(
            role="model" if role == "assistant" else "user",
            parts=[types.Part(text=content)]))
    return out


def _is_retryable(exc) -> bool:
    code = getattr(exc, "code", None)
    return isinstance(code, int) and code in RETRYABLE_STATUS


def _record_usage(response) -> None:
    """Report what this call cost, to whatever step timer is in scope.

    Token counts are the half of the story latency does not tell. A turn that
    served 139,222 of its 142,116 input tokens from cache and one that cached
    nothing take indistinguishable amounts of time and differ several-fold in
    price, and nothing outside this function can see which happened - the SDK
    hands usage back on the response and `generate` returns only the text.

    Silent when nothing is measuring, and never raises: the usage block is
    optional in the SDK's own typing, and a missing counter must not turn a good
    answer into an error.
    """
    from app.observability import steps

    usage = getattr(response, "usage_metadata", None)
    if usage is None or steps.current() is None:
        return
    steps.count("input_tokens", getattr(usage, "prompt_token_count", 0) or 0)
    steps.count("cached_tokens",
                getattr(usage, "cached_content_token_count", 0) or 0)
    steps.count("output_tokens", getattr(usage, "candidates_token_count", 0) or 0)
    steps.count("thinking_tokens", getattr(usage, "thoughts_token_count", 0) or 0)


def _finish_reason(response) -> str:
    for candidate in (getattr(response, "candidates", None) or []):
        reason = getattr(candidate, "finish_reason", None)
        if reason is not None:
            return getattr(reason, "name", str(reason))
    return ""


def generate(system_prompt: str, messages: list, *,
             max_output_tokens: int | None = None,
             temperature: float | None = None,
             model: str | None = None) -> str:
    """One grounded answer from the whole account payload.

    Raises `GeminiUnavailable` rather than returning None: the caller has a
    refusal path that tells the seller why, and a silent None there would render
    as an empty chat bubble.
    """
    client = _client()
    if client is None:
        raise GeminiUnavailable("Gemini is not configured for this deployment.")

    contents = to_contents(messages)
    if not contents:
        raise GeminiUnavailable("no question was asked")

    from google.genai import errors, types

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        # Always set. See the module docstring - omitting this is the failure
        # that does not look like itself.
        max_output_tokens=(settings.GEMINI_MAX_OUTPUT_TOKENS
                           if max_output_tokens is None else max_output_tokens),
        temperature=(settings.GEMINI_TEMPERATURE
                     if temperature is None else temperature),
    )

    ladder = [model or settings.GEMINI_MODEL_NAME]
    fallback = (settings.GEMINI_FALLBACK_MODEL or "").strip()
    if fallback and fallback not in ladder:
        ladder.append(fallback)

    last = None
    for name in ladder:
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = client.models.generate_content(
                    model=name, contents=contents, config=config)
            except errors.APIError as exc:
                last = exc
                if not _is_retryable(exc):
                    # A bad key or a malformed request fails identically on the
                    # next attempt; spending two more is only latency.
                    logger.error("gemini: %s failed with %s - not retrying: %s",
                                 name, getattr(exc, "code", "?"), exc)
                    raise GeminiUnavailable(
                        "the model rejected the request (%s)"
                        % getattr(exc, "code", "error")) from exc
                # Jittered backoff, so several in-flight questions do not all
                # come back at the same instant and saturate it again.
                delay = BASE_DELAY_SECONDS * (2 ** attempt) + random.uniform(0, 0.2)
                logger.warning("gemini: %s returned %s (attempt %d/%d), retrying "
                               "in %.1fs", name, getattr(exc, "code", "?"),
                               attempt + 1, MAX_ATTEMPTS, delay)
                time.sleep(delay)
                continue

            _record_usage(response)

            reason = _finish_reason(response)
            if reason == "MAX_TOKENS":
                # Named, not swallowed. Left to the validator this reads as a
                # grounding failure three retries later.
                raise GeminiTruncated(
                    "the answer hit the %d-token output limit and was cut off"
                    % config.max_output_tokens)
            if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
                raise GeminiUnavailable(
                    "the model declined to answer (%s)" % reason.lower())

            text = (getattr(response, "text", None) or "").strip()
            if text:
                return text
            last = GeminiUnavailable("the model returned nothing (%s)"
                                     % (reason or "no finish reason"))
        logger.warning("gemini: %s exhausted its retries - trying %s",
                       name, ladder[-1] if name != ladder[-1] else "nothing else")

    raise GeminiUnavailable(
        "Gemini did not answer after %d attempt(s) on %s: %s"
        % (MAX_ATTEMPTS * len(ladder), ", ".join(ladder), last))


def generate_json(system_prompt: str, user_prompt: str, *,
                  max_output_tokens: int | None = None) -> dict | None:
    """A JSON answer, or None when it cannot be parsed.

    `response_mime_type` asks for JSON and mostly gets it, but Gemini still
    fences the object in a markdown code block often enough that the reference
    implementation strips them unconditionally. So does this.

    None on a parse failure rather than a raise: every caller of the equivalent
    OpenAI helper already degrades gracefully, and a rewrite that fails should
    leave the original question standing rather than end the turn.
    """
    client = _client()
    if client is None:
        return None

    from google.genai import errors, types

    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL_NAME,
            contents=[types.Content(role="user",
                                    parts=[types.Part(text=user_prompt)])],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                max_output_tokens=(settings.GEMINI_MAX_OUTPUT_TOKENS
                                   if max_output_tokens is None
                                   else max_output_tokens),
                temperature=0.2,
            ))
    except errors.APIError as exc:
        logger.error("gemini: JSON completion failed: %s", exc)
        return None

    return parse_json(getattr(response, "text", None))


def parse_json(text) -> dict | None:
    """Parse a JSON object that may arrive wrapped in a markdown fence."""
    body = str(text or "").strip()
    if not body:
        return None
    if body.startswith("```"):
        body = body.split("\n", 1)[-1] if "\n" in body else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[:-3]
    try:
        parsed = json.loads(body.strip())
    except (ValueError, TypeError):
        logger.warning("gemini: response was not JSON: %s", body[:120])
        return None
    return parsed if isinstance(parsed, dict) else None
