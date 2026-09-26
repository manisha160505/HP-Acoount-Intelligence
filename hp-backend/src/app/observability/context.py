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

# The account and feature a pipeline run is currently inside.
#
# Same reasoning as the request id, for the case the request id cannot cover: a
# 220-account build is driven from a script, so there is no request and no id,
# and the thing a reader needs on every line is which account and which feature
# produced it. Set by `observability.pipeline`, read by the formatter.
account_var: ContextVar[str] = ContextVar("account", default="")
feature_var: ContextVar[str] = ContextVar("feature", default="")


def get_request_id() -> str:
    """The id of the in-flight request, or "" outside of one."""
    return request_id_var.get()


def get_account() -> str:
    """The account label of the run in flight, or "" outside one."""
    return account_var.get()


def get_feature() -> str:
    """The feature key in flight, or "" outside one."""
    return feature_var.get()
