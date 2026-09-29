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

import contextlib
import contextvars
import threading
import time
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
    # Every request that reached the provider - retrieval extraction included,
    # which never goes through note_llm - and the tokens they used. What an
    # admin reads to see what a run cost.
    api_calls: int = 0
    tokens: int = 0
    embedding_calls: int = 0
    embedded_texts: int = 0
    # Set by the engine: called with (done, total, label) as a producer works
    # through batches or documents, so the admin page can show a bar.
    on_progress: object = None


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


def note_api_call(tokens: int = 0) -> None:
    """One request that reached the model provider. A no-op outside a run."""
    ctx = _current.get()
    if ctx is None:
        return
    ctx.api_calls += 1
    ctx.tokens += int(tokens or 0)


def note_embedding(texts: int) -> None:
    ctx = _current.get()
    if ctx is None:
        return
    ctx.embedding_calls += 1
    ctx.embedded_texts += int(texts or 0)


def progress(done: int, total: int, label: str = "") -> None:
    """Report how far a producer has got. Never raises into the producer."""
    ctx = _current.get()
    if ctx is None or ctx.on_progress is None:
        return
    with contextlib.suppress(Exception):
        ctx.on_progress(int(done), int(total), str(label)[:80])


# Process-wide, not per run: a quota answer is about the key, not the job, and
# retrieval builds call the model from threads a context variable may not
# reach. The engine compares this with when a job started.
_quota_lock = threading.Lock()
_quota_exhausted_at = 0.0


def note_quota_exhausted() -> None:
    """The provider kept refusing for quota after every wait. Called by the
    model and embedding clients just before they give up."""
    global _quota_exhausted_at
    with _quota_lock:
        _quota_exhausted_at = time.time()


def quota_exhausted_since(started: float) -> bool:
    return _quota_exhausted_at >= started
