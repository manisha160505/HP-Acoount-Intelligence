"""One entry point that turns the observability settings into a live setup."""

import logging

from app.config.settings import settings
from app.observability.logging import configure_logging
from app.observability.metrics import configure_metrics, shutdown_metrics
from app.observability.tracing import configure_tracing, shutdown_tracing

logger = logging.getLogger(__name__)


def setup_observability() -> None:
    """Configure logging, then tracing, then metrics.

    Order matters: logging goes first so that a failure in either of the other
    two is itself reported through the configured formatter rather than lost.
    """
    configure_logging(
        level=settings.LOG_LEVEL,
        log_format=settings.LOG_FORMAT,
        service=settings.SERVICE_NAME,
        environment=settings.ENVIRONMENT,
        project_id=settings.GCP_PROJECT_ID,
    )

    if not settings.OTEL_ENABLED:
        logger.info(
            "Observability: logs only (format=%s, level=%s). Tracing and metrics "
            "are disabled by OTEL_ENABLED.",
            settings.LOG_FORMAT, settings.LOG_LEVEL,
        )
        return

    tracing_on = configure_tracing(
        service_name=settings.SERVICE_NAME,
        service_version=settings.SERVICE_VERSION,
        environment=settings.ENVIRONMENT,
        project_id=settings.GCP_PROJECT_ID,
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        sample_ratio=settings.OTEL_TRACE_SAMPLE_RATIO,
    )

    metrics_on = configure_metrics(
        service_name=settings.SERVICE_NAME,
        service_version=settings.SERVICE_VERSION,
        environment=settings.ENVIRONMENT,
        project_id=settings.GCP_PROJECT_ID,
        otlp_endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        export_interval_ms=settings.OTEL_METRIC_EXPORT_INTERVAL_MS,
    )

    # Named explicitly rather than left implicit: "tracing is on" and "tracing
    # is on and reaching Cloud Trace" are different states, and the difference
    # is invisible until someone goes looking for a trace that was never
    # exported.
    logger.info(
        "Observability ready: logs=%s level=%s tracing=%s metrics=%s "
        "project=%s otlp=%s",
        settings.LOG_FORMAT,
        settings.LOG_LEVEL,
        "on" if tracing_on else "off",
        "on" if metrics_on else "off",
        settings.GCP_PROJECT_ID or "-",
        settings.OTEL_EXPORTER_OTLP_ENDPOINT or "-",
    )


def shutdown_observability() -> None:
    """Flush buffered spans and metrics on the way out."""
    if not settings.OTEL_ENABLED:
        return
    shutdown_tracing()
    shutdown_metrics()
