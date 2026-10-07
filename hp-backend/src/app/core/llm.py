import hashlib
import json
import logging
import re
import threading
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


# Waits inside ONE model call before sending it again, when the provider
# answers 429 or 5xx for a moment. Not a retry of a failed pipeline: a section
# that still fails after these fails with its reason and is never re-queued
# (29 Sep). The SDK adds its own two quick retries before these.
RATE_LIMIT_WAITS = (5, 15, 30, 60)


# The 400 that says a prompt is too big - and why it is retried rather than fatal.
#
# MEASURED, 7 Oct, from the VM against all 24 configured regions with one
# 232,986-token prompt, seconds apart: 22 accepted it and TWO refused with
# `400 INVALID_ARGUMENT ... maximum number of tokens allowed (131072)`.
# `global` and `asia-south1` then accepted 963,786 tokens. So the model's window
# really is ~1,048,576, and `asia-northeast3` and `europe-west9` simply serve a
# 131,072 one. It is a property of the region - not load, not the project's quota
# (no quota holds that value), and not the model, which reports itself as
# `gemini-2.5-flash` on every successful call.
#
# That is what made Strategy Chat fail on some turns and not others: rotating over
# 24 regions put ~8% of calls on one of the two, and a ~300k-token chat prompt sent
# there is refused outright. The regions are now excluded by prompt size before a
# region is chosen (settings.vertex_chat_locations_for), which is the actual fix.
#
# This retry stays as the backstop, for three reasons: the exclusion works off an
# ESTIMATE, the set of small-window regions can change under us, and a 400 that
# means "not right now" should never be treated as "not ever" whatever its cause.
# Matched on the message rather than the status, so a genuinely malformed request
# is still refused once instead of being sent 24 times.
_CAPACITY_400 = "maximum number of tokens allowed"


def _is_capacity_refusal(exc) -> bool:
    """True for a 400 that means the provider is out of room, not that we asked
    for something impossible."""
    if not isinstance(exc, APIStatusError) or exc.status_code != 400:
        return False
    text = "%s %s" % (getattr(exc, "message", "") or "", exc)
    return _CAPACITY_400 in text.lower()


def _retryable(exc) -> bool:
    return (isinstance(exc, RateLimitError)
            or _is_capacity_refusal(exc)
            or (isinstance(exc, APIStatusError) and exc.status_code >= 500))


# Response headers worth keeping when a capacity refusal happens. An allowlist,
# not everything: the REQUEST headers carry `x-goog-api-key` and must never be
# logged, so only the response side is read, and only these names.
_TRACE_HEADERS = ("x-request-id", "x-goog-request-id", "x-goog-api-version",
                  "x-guploader-uploadid", "server-timing", "retry-after")


def _refusal_detail(exc) -> dict:
    """Which endpoint refused, and the provider's own request id.

    The known cause is a small-window region (see the note above), and `endpoint`
    is what proves it - the region is in the URL path. If this ever fires for a
    region NOT in `VERTEX_SMALL_WINDOW_LOCATIONS`, that list is out of date and
    this line is how anyone would know.

    The request id is kept so a refusal nobody can explain is still a question
    Google can answer.
    """
    detail = {"status": getattr(exc, "status_code", None)}
    response = getattr(exc, "response", None)
    request = getattr(response, "request", None)
    url = str(getattr(request, "url", "") or "")
    if url:
        # The region is in the path; the key is in a header, so the URL is safe.
        match = re.search(r"/locations/([^/]+)/", url)
        detail["endpoint"] = match.group(1) if match else url[:80]
    headers = getattr(response, "headers", None)
    if headers is not None:
        for name in _TRACE_HEADERS:
            value = headers.get(name)
            if value:
                detail[name] = str(value)[:120]
    body = ""
    try:
        body = response.text or ""
    except Exception:
        body = ""
    detail["body"] = (body or str(exc))[:900]
    return detail


_chat_lock = threading.Lock()
_chat_turn = 0


def _affinity_start(affinity: str, count: int) -> int:
    """Which region a given key always starts at.

    A stable digest, not `hash()`: Python randomises string hashing per process,
    so `hash()` would pick a different region after every restart and a different
    one per worker - which is the behaviour this function exists to remove.
    """
    digest = hashlib.blake2b(affinity.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % count


def _prompt_tokens_estimate(kwargs) -> int:
    """Roughly how large this request's prompt is, for choosing a region.

    Deliberately crude and deliberately high: `settings.TOKEN_ESTIMATE_CHARS` is
    below the ratio the corpus measures at, so a prompt near the boundary is
    treated as the larger case and keeps away from the small-window regions.
    """
    total = 0
    for message in (kwargs.get("messages") or []):
        if isinstance(message, dict):
            total += len(str(message.get("content") or ""))
    return int(total / max(settings.TOKEN_ESTIMATE_CHARS, 1.0))


def _regional_clients(client, affinity: str = "", estimated_tokens: int = 0) -> list:
    """The client once per Vertex chat region, in the order they should be tried.

    Without an `affinity` the list starts one further along on each call, so
    concurrent sections spread over the regions - which is what regeneration
    wants: many accounts, no shared prefix, spread the quota.

    **With an `affinity` the starting region is fixed for that key.** Strategy
    Chat sends the same ~400k-token prefix again on every turn and on every
    validation retry, and a prompt cache is per region. Under the rotation,
    consecutive turns of one conversation landed on different regions - 24 of
    them in production - so the cache was never reused and `cached_tokens` came
    back 0. Keying on the account keeps one conversation on one region while
    different accounts still spread across all of them.

    A 429 still falls through to the next region, so this costs no resilience:
    affinity decides where to START, not where it is allowed to go.

    **The candidate list is filtered by prompt size first.** Two of the 24 regions
    serve a 131,072-token window rather than 1,048,576 (measured - see
    `VERTEX_SMALL_WINDOW_LOCATIONS`), and a ~300k-token chat prompt sent there is
    refused outright. Filtering before the affinity hash matters as much as the
    hash: pinning an account to a small-window region would turn a failure that
    happened on ~8% of calls into one that happened on every single one.

    The copies skip the SDK's own retries: a 429 should move on at once. One
    region (or another provider) is just the client as it was.
    """
    global _chat_turn
    locations = settings.vertex_chat_locations_for(estimated_tokens)
    if settings.llm_provider != "vertex" or len(locations) == 1:
        return [client]
    if affinity:
        start = _affinity_start(affinity, len(locations))
    else:
        with _chat_lock:
            start = _chat_turn % len(locations)
            _chat_turn += 1
    return [client.with_options(base_url=settings.vertex_chat_endpoint(loc),
                                max_retries=0)
            for loc in locations[start:] + locations[:start]]


def _create_in_some_region(client, kwargs, affinity=""):
    """One chat call, moving to the next region on a 429; the last region's
    429 is raised so the waits in create_completion take over."""
    clients = _regional_clients(client, affinity,
                               _prompt_tokens_estimate(kwargs))
    reported = False
    for i, regional in enumerate(clients):
        try:
            return regional.chat.completions.create(**kwargs)
        except Exception as exc:
            # A capacity refusal moves on like a 429 does. It is a property of
            # the REGION (see VERTEX_SMALL_WINDOW_LOCATIONS), so the next region
            # will normally take the same prompt - and the hop costs one fast
            # failure, not a wait.
            if not (isinstance(exc, RateLimitError) or _is_capacity_refusal(exc)):
                raise
            if _is_capacity_refusal(exc) and not reported:
                # Once per walk, not once per region: the other 23 say the same
                # thing. WARNING because the retry usually recovers it, so an
                # ERROR would cry wolf - but it must stay visible, since this is
                # the only record of a failure nobody has been able to reproduce.
                reported = True
                logger.warning("LLM refused a request on token capacity - "
                               "retrying. %s", _refusal_detail(exc))
            if i == len(clients) - 1:
                raise
    raise AssertionError("unreachable")


def create_completion(client, affinity: str = "", **kwargs):
    """The SDK's chat completion call with the provider's request options and
    the short in-call waits above. Every model call goes through here, so this
    is also where a regeneration run counts its requests and tokens.

    When the provider is still refusing for quota after every wait, the quota
    signal is raised before giving up: the engine then fails the section as
    QUOTA_EXHAUSTED and pauses the queue.

    `affinity` pins which region this call starts at - pass it when the same
    large prefix will be sent again, so a prompt cache can be reused. Strategy
    Chat passes the account id. Left empty, the regions rotate as before, which
    is what regeneration wants. See `_regional_clients`.
    """
    kwargs = {**settings.llm_request_extra, **kwargs}
    for wait in (*RATE_LIMIT_WAITS, None):
        try:
            response = _create_in_some_region(client, kwargs, affinity)
        except Exception as exc:
            if not _retryable(exc):
                raise
            # Every region refused on size. Waiting changes nothing about a
            # region's input window, so the 5/15/30/60s ladder would only make
            # the seller wait ~110s for the same answer - fail now instead.
            if _is_capacity_refusal(exc):
                raise
            if wait is None:
                if isinstance(exc, RateLimitError):
                    run_context.note_quota_exhausted()
                raise
            logger.info("LLM answered %s (%d region(s) tried) - waiting %ds before "
                        "sending it again", getattr(exc, "status_code", "error"),
                        len(settings.vertex_chat_locations), wait)
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
