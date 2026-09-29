"""Where a question's time actually went, step by step - and what it cost.

The middleware already records how long a request took, and that is the wrong
granularity for the only question anyone asks about Strategy Chat: a question
took nineteen seconds - doing what? Answering it has meant writing a throwaway
profiling script every time, which is how "Gemini is slow" survived as a theory
long after raw generation had been measured at three seconds.

So each step names itself and reports its own cost, and the breakdown travels
three ways: a structured log line carrying the request id, an OpenTelemetry span
per step, and the answer payload itself under `generation.timings`, which is the
form that is actually useful while debugging because it needs no server access.

**Counters sit alongside timings.** Latency is not the only thing worth seeing
per question: `prompt_token_count` and `cached_content_token_count` decide the
bill, and whether the cache engaged is invisible from the outside. A turn that
reports 142,116 input tokens of which 139,222 were cached is doing something
very different from an identical-looking turn that cached nothing, and the only
difference on the clock is noise.

**The OpenTelemetry half is free when it is absent.** `tracing.get_tracer`
returns a no-op tracer when the extras are not installed, so `step()` costs a
`perf_counter` call on a laptop and produces a real span in Cloud Trace in
production, with no branch here. The tracer is looked up once per process: that
function runs a `try: import / except ImportError` on every call, and when the
extras are absent the failed import costs about 1.5ms - measured - which turned
ten steps a question into 15ms of raising and catching the same error.

**Repeated calls accumulate rather than overwrite.** A question that fails
validation twice makes three generation calls, and what matters is
"generation 22400ms/3", not the duration of the last one. That 3 is usually the
answer to "why did that turn take so long".
"""

import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar

from app.observability.tracing import get_tracer

# Looked up once per process, not once per step - see the module note.
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
    """Named steps, what each cost, and the counters worth seeing beside them."""

    def __init__(self):
        # Insertion-ordered, so the breakdown reads in the order the work
        # happened rather than alphabetically or by cost.
        self.steps: dict = {}
        self.counters: dict = {}

    def record(self, name: str, ms: float, calls: int = 1) -> None:
        """Add to a step's running total. Safe to call repeatedly."""
        entry = self.steps.setdefault(name, {"ms": 0.0, "calls": 0})
        entry["ms"] = round(entry["ms"] + ms, 1)
        entry["calls"] += calls

    def count(self, name: str, value: int = 1) -> None:
        """Add to a counter - tokens, cache hits, anything not a duration."""
        self.counters[name] = self.counters.get(name, 0) + int(value or 0)

    @contextmanager
    def step(self, name: str, **attributes):
        """Time a block, and open a span for it.

        The span carries the same name, so a local log line and a production
        trace describe the work identically.
        """
        started = time.perf_counter()
        with _tracer().start_as_current_span(name) as span:
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

    def cache_summary(self) -> str:
        """How much of the input was served from cache, in words.

        Worth its own line because it is the one number that explains the bill
        and is invisible in the latency: a cached turn and an uncached turn look
        identical on the clock.
        """
        total = self.counters.get("input_tokens", 0)
        cached = self.counters.get("cached_tokens", 0)
        if not total:
            return ""
        return "cache %s/%s input tokens (%d%%)" % (
            format(cached, ","), format(total, ","), round(cached * 100 / total))

    def summary(self) -> str:
        """One line: `generation 18420ms/2, validation 46ms/1`."""
        return ", ".join("%s %.0fms/%d" % (name, entry["ms"], entry["calls"])
                         for name, entry in self.as_dict().items())


def current() -> StepTimer | None:
    """The timer in scope, or None. Callers must tolerate None."""
    return _current_timer.get()


@contextmanager
def use(timer: StepTimer):
    """Make `timer` the one `current()` returns for the duration of this block."""
    token = _current_timer.set(timer)
    try:
        yield timer
    finally:
        _current_timer.reset(token)


@contextmanager
def measure(name: str, **attributes):
    """Time a block against whatever timer is in scope, if any.

    For code that should report its cost when someone is measuring and cost
    nothing when nobody is.
    """
    timer = current()
    if timer is None:
        yield
        return
    with timer.step(name, **attributes):
        yield


def count(name: str, value: int = 1) -> None:
    """Add to a counter on the timer in scope, if there is one."""
    timer = current()
    if timer is not None:
        timer.count(name, value)
