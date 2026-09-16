"""OpenTelemetry metrics, exported to Google Cloud Monitoring.

Three instruments, chosen to be the minimum that supports the alerts worth
having on this service:

    http.server.requests        count, by method/route/status - error rate
    http.server.duration        histogram, ms - latency percentiles
    app.errors                  count, by type - unhandled failures

Metrics are recorded by the middleware on every request. As with tracing, all
OpenTelemetry imports are deferred so the app runs without the extras.
"""

import logging

logger = logging.getLogger(__name__)

_meter = None
_request_counter = None
_duration_histogram = None
_error_counter = None
_enabled = False


def configure_metrics(
    service_name: str,
    service_version: str = "1.0.0",
    environment: str = "development",
    project_id: str = "",
    otlp_endpoint: str = "",
    export_interval_ms: int = 60000,
) -> bool:
    """Set up the meter provider and create the instruments."""
    global _meter, _request_counter, _duration_histogram, _error_counter, _enabled

    if _enabled:
        return True

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
    except ImportError:
        logger.warning("OpenTelemetry is not installed - metrics are off.")
        return False

    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    })

    readers = []

    if project_id:
        try:
            from opentelemetry.exporter.cloud_monitoring import (
                CloudMonitoringMetricsExporter,
            )
            # 60s is Cloud Monitoring's own floor for a custom metric; a
            # shorter interval is rejected server-side rather than honoured.
            readers.append(PeriodicExportingMetricReader(
                CloudMonitoringMetricsExporter(project_id=project_id),
                export_interval_millis=max(export_interval_ms, 60000),
            ))
        except ImportError:
            logger.warning("Cloud Monitoring exporter is not installed - skipping it.")
        except Exception:
            logger.exception("Cloud Monitoring exporter failed to initialise.")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            readers.append(PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_endpoint),
                export_interval_millis=export_interval_ms,
            ))
        except ImportError:
            logger.warning("OTLP metric exporter is not installed - skipping it.")
        except Exception:
            logger.exception("OTLP metric exporter failed to initialise.")

    if not readers:
        # Unlike a trace, a metric with no exporter is pure overhead - there is
        # no equivalent of the trace id that makes it useful locally.
        logger.info("No metrics exporter configured - metrics stay off.")
        return False

    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))
    _meter = metrics.get_meter(service_name)

    _request_counter = _meter.create_counter(
        "http.server.requests",
        unit="1",
        description="HTTP requests served, by method, route and status.",
    )
    _duration_histogram = _meter.create_histogram(
        "http.server.duration",
        unit="ms",
        description="Wall-clock time to serve an HTTP request.",
    )
    _error_counter = _meter.create_counter(
        "app.errors",
        unit="1",
        description="Unhandled exceptions escaping a route handler.",
    )

    _enabled = True
    return True


def record_request(method: str, route: str, status_code: int, duration_ms: float) -> None:
    """Record one served request. A no-op when metrics are off.

    Labelled by route template rather than by concrete path: Cloud Monitoring
    bills and limits by cardinality, and one time series per account id would
    exhaust that quota quickly.
    """
    if not _enabled:
        return
    attrs = {
        "http.method": method,
        "http.route": route,
        "http.status_code": status_code,
        # Pre-bucketed so an alert can filter on the class without a regex on
        # the numeric code.
        "status_class": f"{status_code // 100}xx",
    }
    try:
        _request_counter.add(1, attrs)
        _duration_histogram.record(duration_ms, attrs)
    except Exception:
        # Never let telemetry break a request that has already succeeded.
        logger.debug("Failed to record request metrics.", exc_info=True)


def record_error(error_type: str, route: str = "") -> None:
    """Record one unhandled exception. A no-op when metrics are off."""
    if not _enabled:
        return
    try:
        _error_counter.add(1, {"error.type": error_type, "http.route": route})
    except Exception:
        logger.debug("Failed to record error metric.", exc_info=True)


def shutdown_metrics() -> None:
    """Flush pending metrics before exit.

    The reader exports on an interval, so without this the final window's data
    is lost - including the spike that may have caused the shutdown.
    """
    if not _enabled:
        return
    try:
        from opentelemetry import metrics
        provider = metrics.get_meter_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except Exception:
        logger.exception("Metrics did not shut down cleanly.")
