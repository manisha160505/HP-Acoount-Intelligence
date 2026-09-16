"""Logging, tracing and metrics for the backend.

`setup_observability` is the single entry point: main.py calls it once, before
anything else runs, and gets logging configured plus tracing and metrics
enabled to whatever degree the environment supports.
"""

from app.observability.context import get_request_id, request_id_var
from app.observability.logging import configure_logging
from app.observability.metrics import record_error, record_request
from app.observability.setup import setup_observability, shutdown_observability
from app.observability.tracing import get_tracer

__all__ = [
    "configure_logging",
    "get_request_id",
    "get_tracer",
    "record_error",
    "record_request",
    "request_id_var",
    "setup_observability",
    "shutdown_observability",
]
