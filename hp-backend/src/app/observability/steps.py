"""Where a request's time actually went, step by step.

The middleware already records how long a request took, and that is the wrong
granularity for the only question anyone asks about Strategy Chat: a question
took nineteen seconds - doing what? Answering it has meant writing a throwaway
profiling script every time, which is how the N+1 in the graph reads survived as
long as it did. It was invisible because `query.ask` was one opaque block.

So each step names itself and reports its own cost, and the breakdown travels
three ways: a structured log line carrying the request id, an OpenTelemetry span
per step, and the answer payload itself under `generation.timings`, which is the
form that is actually useful while debugging because it needs no server access.

**The OpenTelemetry half is free when it is absent.** `tracing.get_tracer`
returns a no-op tracer when the extras are not installed, so `step()` costs a
`perf_counter` call on a laptop and produces a real span in Cloud Trace in
production, with no branch here.

**Repeated calls accumulate rather than overwrite.** Retrieval makes several
embedding calls and several LLM calls per question; what matters is "4 embedding
calls, 2.1s total", not the duration of the last one.

## Crossing the thread boundary

A ContextVar is how the request id reaches code that never sees the Request
object, and it is the natural mechanism here too - but it does not reach the
retrieval layer on its own. `client.run_on_query_loop` submits work with
`asyncio.run_coroutine_threadsafe` to a long-lived loop on ANOTHER THREAD, and a
ContextVar set while handling the request is not visible there.

That is worth stating plainly because the failure is silent: the embedding and
LLM timings would simply come back empty, and empty reads as "retrieval made no
calls" rather than as "the recorder never arrived". So the timer is handed
across that one boundary as an argument, and `retrieve` installs it on the query
loop with `use()`. Within the loop, ContextVars behave normally again - the
tasks LightRAG spawns inherit it - so nothing below that point needs a
parameter.
"""

import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar

from app.observability.tracing import get_tracer

# Looked up once per process, not once per step.
#
# `get_tracer` runs `try: from opentelemetry import trace / except ImportError`
# on every call, and when the extras are absent that failed import costs about
# 1.5ms - measured. Ten steps a question turned 20 microseconds of real work
# into 15 milliseconds of raising and catching the same ImportError. Still
# nothing against a ten-second question, but it is a silly thing to pay for
# instrumentation that is meant to be free when switched off.
_TRACER = None


def _tracer():
    global _TRACER
    if _TRACER is None:
        _TRACER = get_tracer("app.observability.steps")
    return _TRACER

# The timer for the work in flight, or None when nothing is being measured.
# None rather than a null object so that `current()` returning nothing is
# obviously "not measuring" at every call site.
_current_timer: ContextVar = ContextVar("step_timer", default=None)


class StepTimer:
    """Named steps and what each one cost, for one unit of work."""

    def __init__(self):
        # Insertion-ordered, so the breakdown reads in the order the work
        # happened rather than alphabetically or by cost.
        self.steps: dict = {}

    def record(self, name: str, ms: float, calls: int = 1) -> None:
        """Add to a step's running total. Safe to call repeatedly."""
        entry = self.steps.setdefault(name, {"ms": 0.0, "calls": 0})
        entry["ms"] = round(entry["ms"] + ms, 1)
        entry["calls"] += calls

    @contextmanager
    def step(self, name: str, **attributes):
        """Time a block, and open a span for it.

        The span is the same name, so a local log line and a production trace
        describe the work identically.
        """
        started = time.perf_counter()
        tracer = _tracer()
        with tracer.start_as_current_span(name) as span:
            for key, value in attributes.items():
                # A no-op span, or an attribute type the exporter rejects.
                # Timing must never fail the work it is measuring.
                with suppress(Exception):
                    span.set_attribute(key, value)
            try:
                yield
            finally:
                self.record(name, (time.perf_counter() - started) * 1000)

    def total_ms(self) -> float:
        # Steps nest, so this is deliberately NOT the sum: it is the widest
        # step, which is the closest thing to wall-clock this structure knows.
        return round(max((s["ms"] for s in self.steps.values()), default=0.0), 1)

    def as_dict(self) -> dict:
        """The breakdown, ordered slowest first - which is what gets read."""
        return {name: dict(entry) for name, entry in
                sorted(self.steps.items(), key=lambda kv: -kv[1]["ms"])}

    def summary(self) -> str:
        """One line: `retrieval 18420ms/1, generation 2110ms/2`."""
        return ", ".join("%s %.0fms/%d" % (name, entry["ms"], entry["calls"])
                         for name, entry in self.as_dict().items())


def current() -> StepTimer | None:
    """The timer in scope, or None. Callers must tolerate None."""
    return _current_timer.get()


@contextmanager
def use(timer: StepTimer):
    """Make `timer` the one `current()` returns for the duration of this block.

    Also how the timer crosses onto the retrieval loop - see the module note.
    """
    token = _current_timer.set(timer)
    try:
        yield timer
    finally:
        _current_timer.reset(token)


@contextmanager
def measure(name: str, **attributes):
    """Time a block against whatever timer is in scope, if any.

    For code that should report its cost when someone is measuring and cost
    nothing when nobody is - the embedding and LLM wrappers, which run on every
    index build as well as every question.
    """
    timer = current()
    if timer is None:
        yield
        return
    with timer.step(name, **attributes):
        yield
