"""Server-sent events that stay open while a slow answer is being written.

A strategy chat answer can take minutes on a large account, and for most of
that time the generator yields nothing. A connection that carries no bytes for
that long is closed by the browser or something on the network between it and
the server (6 Oct: Australia Post, closed at 7m37s; the answer was ready 9s
later). `with_keepalive` sends an SSE comment line whenever the generator has
been silent for `interval` seconds. A comment carries no `data:` line, so every
SSE client - including services/api.ts `postStream` - ignores it.
"""

import contextvars
import queue
import threading
from collections.abc import Callable, Iterable, Iterator

KEEPALIVE = ": keep-alive\n\n"
_END = object()


def with_keepalive(make_events: Callable[[], Iterable[str]],
                   interval: float = 15.0) -> Iterator[str]:
    """Yield what `make_events()` yields, plus a keep-alive comment after every
    `interval` seconds of silence. The events are produced on a worker thread,
    in a copy of the caller's context so request ids still reach the logs."""
    q: queue.Queue = queue.Queue()
    ctx = contextvars.copy_context()

    def produce():
        try:
            for item in make_events():
                q.put(item)
        except BaseException as exc:  # handed to the consumer
            q.put(exc)
        finally:
            q.put(_END)

    threading.Thread(target=ctx.run, args=(produce,), daemon=True,
                     name="sse-producer").start()
    while True:
        try:
            item = q.get(timeout=interval)
        except queue.Empty:
            yield KEEPALIVE
            continue
        if item is _END:
            return
        if isinstance(item, BaseException):
            raise item
        yield item
