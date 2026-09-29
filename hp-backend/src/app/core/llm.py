import json
import logging
import time

from openai import APIStatusError, OpenAI, RateLimitError

from app.config.settings import settings
from app.observability import pipeline
from app.services.regen import context as run_context

logger = logging.getLogger(__name__)

def get_openai_client() -> OpenAI | None:
    """The client for the configured LLM provider (settings.LLM_PROVIDER).

    Gemini is reached through its OpenAI-compatible endpoint, so the same SDK and
    the same request shapes serve both providers."""
    api_key = settings.llm_api_key
    if not api_key:
        logger.warning("%s is not set in environment or settings.", settings.llm_api_key_name)
        return None
    return OpenAI(**settings.llm_client_kwargs)


# Waits before each retry of a 429 or 5xx, after the SDK's own quick retries.
# Vertex's shared quota answered 429 for minutes at a time during a full
# regeneration (28 Sep); the SDK's retries give up within ~2 s, which turned a
# busy minute into a DEGRADED widget.
RATE_LIMIT_WAITS = (5, 15, 30, 60)


def _retryable(exc) -> bool:
    return isinstance(exc, RateLimitError) or (
        isinstance(exc, APIStatusError) and exc.status_code >= 500)


def create_completion(client, **kwargs):
    """The SDK's chat completion call with the provider's request options and
    rate-limit waits. Every model call goes through here, so this is also where
    a regeneration run counts its requests and tokens.

    The waits are inside ONE call - a busy few seconds at the provider - not a
    retry of a failed pipeline. When the provider is still refusing for quota
    after all of them, the quota signal is raised before giving up: the engine
    then pauses the whole queue instead of failing job after job.
    """
    kwargs = {**settings.llm_request_extra, **kwargs}
    for wait in (*RATE_LIMIT_WAITS, None):
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not _retryable(exc):
                raise
            if wait is None:
                if isinstance(exc, RateLimitError):
                    run_context.note_quota_exhausted()
                raise
            logger.info("LLM answered %s - retrying in %ds",
                        getattr(exc, "status_code", "error"), wait)
            time.sleep(wait)
            continue
        if not kwargs.get("stream"):
            usage = getattr(response, "usage", None)
            run_context.note_api_call(getattr(usage, "total_tokens", 0) or 0)
        else:
            run_context.note_api_call(0)
        return response
    raise AssertionError("unreachable")


def _parse_json(content: str) -> dict | None:
    """The model's JSON answer. Gemini sometimes wraps it in a ```json fence even
    in JSON mode; the fence is removed rather than the answer thrown away."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    if not text:
        return None
    parsed = json.loads(text)
    return parsed if isinstance(parsed, dict) else None

def generate_chat_completion(system_prompt: str, messages: list,
                             temperature: float = 0.3) -> str | None:
    """A multi-turn text completion. Returns prose, not JSON.

    Strategy Chat needs the conversation itself in the request - a seller asks
    "how does that compare to last year" and the model has to see what "that"
    referred to. Flattening the history into one user string loses the turn
    boundaries the model uses to do that.

    `messages` is [{"role": "user"|"assistant", "content": str}]; anything else
    is dropped rather than sent, so a malformed history cannot become a prompt
    injection vector. The system prompt is always first and always ours.

    Runs on the chat model (settings.chat_model), not the retrieval model: index
    building stays on the slower model, but answering happens while a seller waits.

    The model writes the prose and has no authority over any fact in it -
    everything it says is validated against retrieved evidence afterwards.
    """
    client = get_openai_client()
    if not client:
        logger.warning("Cannot generate completion: LLM client is uninitialized.")
        run_context.note_llm(failed=True)
        return None

    turns = [{"role": "system", "content": system_prompt}]
    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content})

    if len(turns) == 1:
        logger.warning("Cannot generate completion: no usable messages supplied.")
        return None

    model_name = settings.chat_model
    try:
        response = create_completion(
            client, model=model_name, messages=turns, temperature=temperature)
        text = (response.choices[0].message.content or "").strip() or None
        run_context.note_llm(failed=text is None)
        return text
    except Exception as exc:
        logger.error("Error calling chat completion: %s", exc)
        run_context.note_llm(failed=True)
        return None


def stream_chat_completion(system_prompt: str, messages: list,
                           temperature: float = 0.3):
    """`generate_chat_completion`, yielding text as the model writes it.

    Same request, same model, same validation downstream - the only difference
    is that the caller sees the answer being written instead of waiting for the
    whole of it. Generation is not faster; a seller waits about twelve seconds
    either way. What changes is that the first words arrive in about three.

    Yields str deltas. A failure yields nothing, which the caller reads as an
    empty answer exactly as it reads a `None` from the non-streaming call.
    """
    client = get_openai_client()
    if not client:
        logger.warning("Cannot stream completion: LLM client is uninitialized.")
        return

    turns = [{"role": "system", "content": system_prompt}]
    for message in (messages or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower()
        content = str(message.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            turns.append({"role": role, "content": content})

    if len(turns) == 1:
        logger.warning("Cannot stream completion: no usable messages supplied.")
        return

    model_name = settings.chat_model
    try:
        stream = create_completion(
            client, model=model_name, messages=turns, temperature=temperature,
            stream=True)
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except Exception as exc:
        logger.error("Error streaming chat completion: %s", exc)


def generate_gpt4o_json_completion(system_prompt: str, user_prompt: str) -> dict | None:
    client = get_openai_client()
    if not client:
        logger.warning("Cannot generate completion: LLM client is uninitialized.")
        # Counted as a failure: a run with no model configured falls back
        # everywhere, and the engine must know its output is degraded.
        run_context.note_llm(failed=True)
        return None

    model_name = settings.chat_model
    started = time.monotonic()
    try:
        response = create_completion(
            client,
            model=model_name,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2
        )
        # Counted per feature rather than printed per call: an account makes
        # dozens of these, and a line each would bury the pipeline's own
        # output. `pipeline.llm_done` rolls them into one line on the feature's
        # DONE banner - which is what makes "this feature called the model six
        # times" checkable during a supervised run.
        usage = getattr(response, "usage", None)
        pipeline.llm_call(model_name, time.monotonic() - started,
                          getattr(usage, "total_tokens", 0) or 0)
        content = response.choices[0].message.content
        parsed = _parse_json(content) if content else None
        if parsed is not None:
            run_context.note_llm(failed=False)
            return parsed
        # An empty response is a failure to the caller exactly as an exception
        # is: it gets None either way and falls back.
        run_context.note_llm(failed=True)
        return None
    except Exception as e:
        pipeline.llm_call(model_name, time.monotonic() - started, 0, failed=True)
        logger.error("Error calling %s JSON completion: %s", model_name, e)
        run_context.note_llm(failed=True)
        return None
