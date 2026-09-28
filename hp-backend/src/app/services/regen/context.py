"""The state of one producer run, visible to the code the producer calls.

A run needs three things from code it does not own:

  * the dataset loader must read the file rows pinned when the run started, not
    whatever is active by the time it gets there;
  * `widget_store` must answer upstream reads from the generations pinned at
    the start, and a producer's reads of its own widgets from what it staged;
  * `core/llm.py` must report every call and every failure, so a run that fell
    back after a model outage is known to be degraded.

Threading that through every extractor signature would touch hundreds of call
sites. A context variable reaches them without that, and outside a run it is
simply absent, so every caller keeps its existing behaviour.

Deliberately free of app imports: `core/llm.py` and the dataset loader import
this module, and anything it imported back would close a cycle.
"""

import contextvars
from dataclasses import dataclass, field

_current: contextvars.ContextVar = contextvars.ContextVar("regen_run", default=None)


@dataclass
class RunContext:
    account_id: str
    node_id: str
    # dataset_key -> [file row dicts], captured when the run started.
    pinned_rows: dict = field(default_factory=dict)
    # widget_key -> the committed widget document of an upstream node.
    pinned_widgets: dict = field(default_factory=dict)
    # widget_key -> payload this run has published so far.
    staged: dict = field(default_factory=dict)
    # Keys this node owns; a put outside them fails the run.
    owned: frozenset = frozenset()
    force: bool = False
    # The manifest the run is being built from; `manifest.cache_suffix` reads it
    # so a producer's own LLM cache cannot outlive a config or model change.
    manifest: dict = field(default_factory=dict)
    widget_reads: set = field(default_factory=set)
    soft_reads: dict = field(default_factory=dict)
    dataset_reads: set = field(default_factory=set)
    llm_calls: int = 0
    llm_failures: int = 0
    foreign_puts: list = field(default_factory=list)


def current() -> RunContext | None:
    return _current.get()


class active:
    """`with active(ctx):` - make `ctx` the current run for this thread/task."""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self._token = None

    def __enter__(self):
        self._token = _current.set(self.ctx)
        return self.ctx

    def __exit__(self, *exc):
        _current.reset(self._token)
        return False


def note_llm(failed: bool) -> None:
    """Called by `core/llm.py` for every model call. A no-op outside a run."""
    ctx = _current.get()
    if ctx is None:
        return
    ctx.llm_calls += 1
    if failed:
        ctx.llm_failures += 1


def note_dataset_read(dataset_key: str) -> None:
    ctx = _current.get()
    if ctx is not None and dataset_key:
        ctx.dataset_reads.add(dataset_key)
