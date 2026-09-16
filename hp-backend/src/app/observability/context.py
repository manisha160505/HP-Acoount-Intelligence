"""Request-scoped context shared by the logging and tracing layers.

A ContextVar rather than a middleware attribute on `request.state`: the log
records that most need the request id are emitted deep inside the extractors
and the retrieval layer, which never receive the Request object. A ContextVar
set once by the middleware is visible to every `logger.*` call made while
handling that request, including from a thread pool via `run_in_threadpool`,
without threading an argument through forty call sites.
"""

from contextvars import ContextVar

# Empty string rather than None so the log formatter can emit the field
# unconditionally. Work that runs outside a request - the seeder, the retrieval
# worker - legitimately has no id, and a missing key in a JSON log is harder to
# query for than a present-but-empty one.
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """The id of the in-flight request, or "" outside of one."""
    return request_id_var.get()
