"""Step timings, and the one way they fail silently.

A question that took nineteen seconds is not diagnosable from the request log,
which records only that it took nineteen seconds. These timings name the step,
and the reason they are worth testing is that the interesting failure produces
no error at all: an empty breakdown reads as "that step did no work" rather than
as "nothing was measuring".

The specific trap is the retrieval loop. `client.run_on_query_loop` submits work
with `asyncio.run_coroutine_threadsafe` to a long-lived loop on another thread,
and a ContextVar set while handling the request is not visible there. So the
timer is handed across that boundary as an argument and re-installed on the far
side. `test_a_timer_does_not_cross_a_thread_by_itself` exists to keep the reason
for that visible, because the obvious "simplification" is to drop the parameter
and rely on the ContextVar - which would compile, run, pass every other test,
and quietly report nothing.

Run: python -m pytest tests/test_step_timings.py -v
"""

import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.observability import steps


def test_a_step_records_what_it_cost():
    timer = steps.StepTimer()
    with timer.step("work"):
        time.sleep(0.02)
    assert timer.steps["work"]["calls"] == 1
    assert timer.steps["work"]["ms"] >= 15


def test_repeated_calls_accumulate_rather_than_overwrite():
    """Retrieval makes several embedding calls; the total is what matters."""
    timer = steps.StepTimer()
    for _ in range(3):
        with timer.step("retrieval.embedding"):
            time.sleep(0.01)
    assert timer.steps["retrieval.embedding"]["calls"] == 3
    assert timer.steps["retrieval.embedding"]["ms"] >= 25


def test_a_step_is_recorded_even_when_the_work_raises():
    """A failed question is the one you most want the breakdown for."""
    timer = steps.StepTimer()
    try:
        with timer.step("generation"):
            raise RuntimeError("the model refused")
    except RuntimeError:
        pass
    assert "generation" in timer.steps


def test_the_breakdown_is_ordered_slowest_first():
    timer = steps.StepTimer()
    timer.record("fast", 5)
    timer.record("slow", 500)
    timer.record("middling", 50)
    assert list(timer.as_dict()) == ["slow", "middling", "fast"]


def test_measuring_without_a_timer_is_free_and_silent():
    """`_embedding_func` runs on index builds too, where nobody is measuring."""
    assert steps.current() is None
    with steps.measure("retrieval.embedding"):
        pass  # must not raise


def test_measure_records_against_whatever_timer_is_in_scope():
    timer = steps.StepTimer()
    with steps.use(timer), steps.measure("retrieval.llm"):
        time.sleep(0.01)
    assert timer.steps["retrieval.llm"]["calls"] == 1
    # And the scope closes behind it.
    assert steps.current() is None


def test_a_timer_does_not_cross_a_thread_by_itself():
    """Why `retrieve` takes the timer as an argument.

    This is the behaviour that makes the parameter necessary, asserted rather
    than described - so that removing the parameter as redundant fails here
    instead of silently reporting an empty retrieval breakdown.
    """
    timer = steps.StepTimer()
    seen = {}

    def on_another_thread():
        # A fresh thread starts with an empty context, exactly as the query
        # loop's thread does.
        seen["timer"] = steps.current()

    with steps.use(timer):
        assert steps.current() is timer
        worker = threading.Thread(target=on_another_thread)
        worker.start()
        worker.join()

    assert seen["timer"] is None, (
        "a ContextVar reached another thread - if this ever becomes true, the "
        "timer parameter on `retrieve` can go, but not before")


def test_handing_the_timer_across_restores_the_measurement():
    """And why re-installing it on the far side is enough.

    Mirrors what `retrieve` does: the timer travels as a value, `use()` puts it
    back in context, and everything spawned below it records normally again.
    """
    timer = steps.StepTimer()

    async def deep_work():
        # A task spawned inside the loop, as LightRAG spawns its own.
        async def inner():
            with steps.measure("retrieval.embedding"):
                await asyncio.sleep(0.01)
        await asyncio.gather(inner(), inner())

    async def entry(handed):
        with steps.use(handed):
            await deep_work()

    def run_on_another_loop():
        asyncio.run(entry(timer))

    worker = threading.Thread(target=run_on_another_loop)
    worker.start()
    worker.join()

    assert timer.steps["retrieval.embedding"]["calls"] == 2, (
        "work on the far side of the boundary went unmeasured")


def test_the_summary_line_is_readable():
    timer = steps.StepTimer()
    timer.record("retrieval", 18420.4, calls=1)
    timer.record("generation", 2110.2, calls=2)
    assert timer.summary() == "retrieval 18420ms/1, generation 2110ms/2"


def test_total_is_the_widest_step_not_the_sum():
    """Steps nest - `retrieval.embedding` happens inside `retrieval`.

    Summing them would double-count and report a total larger than the request
    took, which is worse than no total at all.
    """
    timer = steps.StepTimer()
    timer.record("retrieval", 12000)
    timer.record("retrieval.embedding", 3000)
    timer.record("generation", 5000)
    assert timer.total_ms() == 12000
