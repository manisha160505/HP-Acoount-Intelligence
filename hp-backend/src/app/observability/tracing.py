"""OpenTelemetry tracing.

Instruments FastAPI, PyMongo and outbound HTTP so a single trace shows the
request, the queries it ran and the model calls it made. Exports to Google
Cloud Trace when a project is configured, and to an OTLP collector when one is
pointed at - both, neither or either.

Every import of an OpenTelemetry package is deferred into the function body.
The dependency is optional: a developer who has not installed the extras gets
an app that starts and logs normally, with tracing off and one line saying so,
rather than an ImportError at startup.
"""

import logging

logger = logging.getLogger(__name__)

_instrumented = False


def configure_tracing(
    service_name: str,
    service_version: str = "1.0.0",
    environment: str = "development",
    project_id: str = "",
    otlp_endpoint: str = "",
    sample_ratio: float = 1.0,
) -> bool:
    """Set up the tracer provider and the auto-instrumentors.

    Returns whether tracing was actually enabled, so the caller can say so at
    startup instead of leaving it ambiguous.
    """
    global _instrumented
    if _instrumented:
        return True

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
    except ImportError:
        logger.warning(
            "OpenTelemetry is not installed - tracing is off. "
            "Install the observability extras to enable it."
        )
        return False

    # The identity every span is tagged with, and what Cloud Trace groups by.
    # The keys are the OTel semantic conventions rather than names of our own
    # choosing, so the backends recognise them without mapping.
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    })

    # ParentBased so a sampling decision made upstream is honoured: sampling a
    # child independently of its parent produces broken traces where the
    # request span is missing and only a query span survives.
    provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(root=TraceIdRatioBased(sample_ratio)),
    )

    exporters = 0

    if project_id:
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
            provider.add_span_processor(
                BatchSpanProcessor(CloudTraceSpanExporter(project_id=project_id))
            )
            exporters += 1
        except ImportError:
            logger.warning("Cloud Trace exporter is not installed - skipping it.")
        except Exception:
            logger.exception("Cloud Trace exporter failed to initialise.")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            exporters += 1
        except ImportError:
            logger.warning("OTLP exporter is not installed - skipping it.")
        except Exception:
            logger.exception("OTLP exporter failed to initialise.")

    if not exporters:
        # A provider with no exporter still creates spans, and those spans
        # still carry the trace id that the log formatter stamps onto every
        # record. Log correlation therefore works even with nothing collecting
        # the spans themselves - worth keeping rather than bailing out.
        logger.info("Tracing is on with no exporter configured; spans stay local "
                    "and only serve to correlate logs.")

    trace.set_tracer_provider(provider)
    _instrumented = True
    return True


def instrument_app(app) -> None:
    """Attach the auto-instrumentors to the app and its clients.

    Each is wrapped separately: a version mismatch in one instrumentor should
    cost that one signal, not the whole app's startup.
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        # The health endpoint is polled constantly and its span says nothing.
        FastAPIInstrumentor.instrument_app(
            app, excluded_urls="health,metrics,favicon.ico"
        )
    except ImportError:
        pass
    except Exception:
        logger.exception("FastAPI instrumentation failed; tracing may be partial.")

    try:
        from opentelemetry.instrumentation.pymongo import PymongoInstrumentor
        PymongoInstrumentor().instrument()
    except ImportError:
        pass
    except Exception:
        logger.exception("PyMongo instrumentation failed; queries will not appear "
                         "in traces.")

    # Covers the Azure OpenAI and LightRAG calls, which are the slowest thing
    # in most requests and the most useful span to have.
    #
    # The instrumentor logs a DependencyConflict at ERROR when the library it
    # targets is absent - which is not an error here, since httpx and requests
    # are both optional transitive dependencies. Its logger is quietened for
    # the duration so a clean install does not start with a red herring.
    instrumentor_log = logging.getLogger("opentelemetry.instrumentation.instrumentor")
    previous_level = instrumentor_log.level
    instrumentor_log.setLevel(logging.CRITICAL)
    try:
        for module, attr in (
            ("opentelemetry.instrumentation.httpx", "HTTPXClientInstrumentor"),
            ("opentelemetry.instrumentation.requests", "RequestsInstrumentor"),
        ):
            try:
                mod = __import__(module, fromlist=[attr])
                getattr(mod, attr)().instrument()
            except ImportError:
                pass
            except Exception:
                logger.debug("%s did not instrument; outbound HTTP calls will "
                             "not appear as spans.", attr, exc_info=True)
    finally:
        instrumentor_log.setLevel(previous_level)


def shutdown_tracing() -> None:
    """Flush buffered spans before the process exits.

    BatchSpanProcessor holds spans in memory; without this the spans for the
    final requests before a shutdown or a redeploy are dropped - exactly the
    ones worth having when a deploy goes wrong.
    """
    try:
        from opentelemetry import trace
        provider = trace.get_tracer_provider()
        if hasattr(provider, "shutdown"):
            provider.shutdown()
    except Exception:
        logger.exception("Tracing did not shut down cleanly.")


def get_tracer(name: str):
    """A tracer for manual spans, or a no-op stand-in when OTel is absent.

    Lets feature code call `with get_tracer(__name__).start_as_current_span(...)`
    unconditionally, with no import guard at the call site.
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoopTracer()


class _NoopTracer:
    def start_as_current_span(self, *args, **kwargs):
        from contextlib import nullcontext
        return nullcontext(_NoopSpan())


class _NoopSpan:
    def set_attribute(self, *args, **kwargs) -> None: ...
    def record_exception(self, *args, **kwargs) -> None: ...
    def set_status(self, *args, **kwargs) -> None: ...
