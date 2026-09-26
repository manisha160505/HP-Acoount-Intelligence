"""Watchable pipeline logging: one shape for every step of a build.

A 220-account build starts with a two or three account wave, and the point of
that wave is to WATCH - to see each feature take the right datasets, match the
right rules, call the model the expected number of times, drop what the
guardrails should drop, and write the widgets it should write.

Before this, a successful run printed almost nothing: five `logger.info` calls
across all eleven feature extractors, seven of which had none at all. What it
did print came from LightRAG, several hundred lines per index build.

The shape, so eleven extractors do not each invent their own:

    [astra] executive_dashboard  START
        datasets      firmographics=1 filings=476 jobs=100
        llm           describe x6  12.4s
        guardrail     1 paragraph dropped (unsourced figure)
        widget        exec_urgency_score     partial (92.5% coverage)
    [astra] executive_dashboard  DONE 5 widgets 79s

## Why the cache line is not optional

`cache_hit` exists because of a specific, repeated failure. An extractor whose
fingerprint has not moved returns the stored widget and logs nothing, so the
run reports "OK 2s" and looks like success. That happened four separate times
in one afternoon, and each time it took a manual database query to notice the
widget was stale. A run that is fast because nothing changed must not look
identical to a run that is fast because nothing ran.

## Levels

All of this is INFO. It is written to be read during a supervised run, not
kept behind DEBUG - a flag nobody remembers to set shows nobody anything.
Failures are ERROR and carry the exception.

Every helper is safe to call outside a scope: the context vars default to empty
and the line still prints, so a script that calls an extractor directly gets
the same output as the pipeline does.
"""

import functools
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar

from app.observability.context import account_var, feature_var

logger = logging.getLogger(__name__)

# The counters for the feature in flight. A ContextVar rather than an argument
# because the things that need to count - a cache hit deep inside a helper, a
# widget written by a sub-module - are nowhere near the scope that opened them.
_state_var: ContextVar[dict] = ContextVar("pipeline_state", default=None)

# The account-level counters, found the same way. Without this the decorator
# could not roll a feature's totals up into the account summary - it opens the
# feature scope itself and never sees the caller's run dict.
_run_var: ContextVar[dict] = ContextVar("pipeline_run", default=None)


def _state():
    """The in-flight feature's counters, or None outside a feature."""
    return _state_var.get()

# Indent for the step lines under a feature banner. One place, so the columns
# line up however many call sites there are.
_STEP = "    %-13s %s"


def _fields(pairs: dict) -> str:
    """`a=1 b=2`, for the tail of a step line. Empty values are dropped."""
    return " ".join("%s=%s" % (k, v) for k, v in (pairs or {}).items()
                    if v not in (None, "", [], {}))


@contextmanager
def account_scope(account_id: str, label: str = ""):
    """One account's whole run: banner, totals, elapsed.

    `label` is what a reader recognises - the account's name. The id is logged
    once on the banner so a line can still be traced back to a record, and then
    stays out of the way.
    """
    shown = label or str(account_id)
    token = account_var.set(shown)
    state = {"features": 0, "widgets": 0, "cached": 0, "failed": 0}
    run_token = _run_var.set(state)
    started = time.monotonic()
    logger.info("=== START  (account_id=%s)", account_id)
    try:
        yield state
    finally:
        logger.info(
            "=== DONE  %d feature%s, %d widget%s (%d cached), %d failed, %.0fs",
            state["features"], "" if state["features"] == 1 else "s",
            state["widgets"], "" if state["widgets"] == 1 else "s",
            state["cached"], state["failed"], time.monotonic() - started)
        _run_var.reset(run_token)
        account_var.reset(token)


@contextmanager
def feature_scope(feature_key: str, run=None):
    """One feature: START, DONE with its widget count, or FAILED with why.

    The exception is logged and re-raised. The caller decides whether one
    feature failing stops the account - this only makes sure the failure is
    visible in the same stream as everything else, rather than surfacing later
    in a caller's handler with no indication of where it came from.
    """
    run = run if run is not None else _run_var.get()
    token = feature_var.set(feature_key)
    started = time.monotonic()
    logger.info("START")
    state = {"widgets": 0, "cached": 0, "seen": set()}
    state_token = _state_var.set(state)
    try:
        yield state
    except Exception as exc:
        logger.exception("FAILED after %.0fs - %s",
                         time.monotonic() - started, exc)
        if run is not None:
            run["failed"] = run.get("failed", 0) + 1
            run["features"] = run.get("features", 0) + 1
        raise
    else:
        if state.get("llm_calls"):
            failed = state.get("llm_failed") or 0
            step("llm", "%s x%d  %.1fs%s%s" % (
                state.get("llm_model") or "model", state["llm_calls"],
                state.get("llm_seconds") or 0.0,
                "  %d tokens" % state["llm_tokens"] if state.get("llm_tokens") else "",
                "  %d FAILED" % failed if failed else ""))
        if state.get("proof_asked"):
            seen = state.get("proof_customers") or []
            step("proof", "%d of %d slot(s) filled%s" % (
                state.get("proof_filled", 0), state["proof_asked"],
                "  %s" % ", ".join(sorted(set(seen))) if seen else ""))
        cached = (" (%d cached)" % state["cached"]) if state["cached"] else ""
        logger.info("DONE %d widget%s%s %.0fs",
                    state["widgets"], "" if state["widgets"] == 1 else "s",
                    cached, time.monotonic() - started)
        if run is not None:
            run["features"] = run.get("features", 0) + 1
            run["widgets"] = run.get("widgets", 0) + state["widgets"]
            run["cached"] = run.get("cached", 0) + state["cached"]
    finally:
        _state_var.reset(state_token)
        feature_var.reset(token)


def step(kind: str, message: str = "", **fields) -> None:
    """One stage inside a feature: `    datasets  firmographics=1 jobs=100`."""
    tail = _fields(fields)
    logger.info(_STEP, kind, " ".join(p for p in (message, tail) if p))


def widget(key: str, status: str = "available", state=None, **fields) -> None:
    """A widget this feature wrote. Counted once, however often it is reported."""
    state = state if state is not None else _state()
    if state is not None and key in state.setdefault("seen", set()):
        return
    step("widget", "%-34s %s" % (key, status), **fields)
    if state is not None:
        state.setdefault("seen", set()).add(key)
        state["widgets"] = state.get("widgets", 0) + 1


def cache_hit(key: str, reason: str = "fingerprint unchanged", state=None) -> None:
    """A widget served from cache rather than rebuilt.

    Always logged. See the module docstring: a silent cache hit is
    indistinguishable from work, and that has cost real time.
    """
    state = state if state is not None else _state()
    step("cache", "%-34s UNCHANGED - %s" % (key, reason))
    if state is not None:
        state.setdefault("seen", set()).add(key)
        state["cached"] = state.get("cached", 0) + 1
        state["widgets"] = state.get("widgets", 0) + 1


def feature(feature_key: str):
    """Wrap an extractor entry point so its whole run is reported.

    Applied to the eleven `extract_*` functions. They already return the widget
    payloads they wrote, so the widget lines and the DONE count come from the
    return value rather than from eleven hand-maintained counters.
    """
    def outer(fn):
        @functools.wraps(fn)
        def inner(account_id, *args, **kwargs):
            with feature_scope(feature_key) as state:
                result = fn(account_id, *args, **kwargs)
                for item in (result if isinstance(result, list) else []):
                    if isinstance(item, dict) and item.get("widget_key"):
                        widget(item["widget_key"],
                               item.get("status") or "available", state)
                return result
        return inner
    return outer


def llm_call(model: str, seconds: float, tokens: int = 0,
             failed: bool = False) -> None:
    """Record one model call against the feature in flight.

    Nothing is printed here. An account makes dozens of calls and a line each
    would bury everything else; the total is printed once on the feature's DONE
    banner instead, which is what makes "this feature called the model six
    times" checkable during a supervised run.
    """
    state = _state()
    if state is None:
        return
    state["llm_calls"] = state.get("llm_calls", 0) + 1
    state["llm_seconds"] = state.get("llm_seconds", 0.0) + max(0.0, seconds)
    state["llm_tokens"] = state.get("llm_tokens", 0) + max(0, tokens)
    state["llm_model"] = model
    if failed:
        state["llm_failed"] = state.get("llm_failed", 0) + 1


def proof_allocated(study: str = "", customer: str = "") -> None:
    """One case-study slot filled. Tallied, printed once on the feature's DONE.

    A slot left empty is the interesting case - it means the corpus reached
    nothing the card could honestly cite - so both halves are counted and the
    ratio is what gets printed.
    """
    state = _state()
    if state is None:
        return
    state["proof_asked"] = state.get("proof_asked", 0) + 1
    if study or customer:
        state["proof_filled"] = state.get("proof_filled", 0) + 1
        state.setdefault("proof_customers", []).append(customer or study)


def llm(purpose: str, calls: int = 1, seconds: float = 0.0, **fields) -> None:
    """Model work, printed explicitly. Most callers want `llm_call` instead."""
    step("llm", "%s x%d  %.1fs" % (purpose, calls, seconds), **fields)


def guardrail(dropped: int, reason: str = "", **fields) -> None:
    """What the guardrails withheld. Silence here means nothing was dropped."""
    if not dropped:
        return
    step("guardrail", "%d dropped%s" % (dropped, " (%s)" % reason if reason else ""),
         **fields)
