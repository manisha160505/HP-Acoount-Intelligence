# Observability

Structured logs, traces and metrics for the HP Account Intelligence backend and
frontend. This document is the operational reference: what is emitted, how to
query it, and which alerts to create.

## What changed and why

The backend previously called `logging.basicConfig` with a plain text format and
had no request-level logging at all. Three things followed from that: an
unhandled exception returned a 500 with nothing identifying the call that caused
it, a slow endpoint was invisible, and the log level was fixed at INFO in source
so the `logger.debug` calls already in the extractors could never be turned on.

The frontend had no logging of any kind — a failed API call left nothing in the
console, so "the dashboard is blank" was indistinguishable from a feature
legitimately having no data.

## Design

**Optional dependencies.** Every OpenTelemetry import is deferred into a
function body and guarded. Without the packages installed the app starts, logs
in full, and reports `tracing=off metrics=off`. Structured JSON logging has no
third-party dependency and always works. This is deliberate: observability
should never be the reason a service fails to boot.

**Cloud Logging without a client library.** The formatter names its fields the
way Cloud Logging already understands — `severity` rather than `level`, and the
trace under `logging.googleapis.com/trace`. A JSON line on stdout is then parsed
into a structured entry by the platform's built-in agent on Cloud Run or GKE,
with no sidecar and no write path to fail.

**stdout, not stderr.** On Cloud Run and GKE, stderr is flagged as an error
regardless of the record's own severity, which would turn every INFO line into
an alert-worthy entry.

## The log contract

Every record is one JSON object on one line:

| Field | Always | Notes |
|---|---|---|
| `timestamp` | yes | UTC ISO-8601, `Z`-suffixed |
| `level` | yes | DEBUG…CRITICAL |
| `severity` | yes | Cloud Logging's spelling of the same |
| `service` | yes | `SERVICE_NAME` |
| `environment` | yes | dev / staging / production |
| `logger` | yes | Python logger name |
| `message` | yes | |
| `request_id` | request-scoped | **absent**, not empty, outside a request |
| `trace_id` / `span_id` | when tracing | correlates to Cloud Trace |
| `method` `path` `route` `status_code` `duration_ms` `client_ip` | request completion | `route` is the template |
| `error` | on exception | `{type, message, stack_trace}` |

`request_id` is absent rather than empty outside a request because the seeder
and the retrieval worker legitimately have none, and a present-but-empty field
makes `request_id != ""` the only way to find real request work.

`route` is the un-substituted template (`/api/v1/accounts/{account_id}`). Without
it every account id becomes its own value and a latency chart by path
degenerates into one series per account.

## Correlating a user report to a log line

1. The browser console shows the failure with a `request_id`, read off the
   response's `X-Request-ID` header.
2. A 500's JSON body carries the same id, so a user can quote it directly.
3. Both match the `request_id` on the backend log entry, and its `trace_id`
   opens the full trace.

## Cloud Logging queries

```
# One request end to end, across both services
jsonPayload.request_id = "abc123def456"

# Server-side failures only, newest first
jsonPayload.service = "hp-backend" AND severity >= ERROR

# Slow calls
jsonPayload.duration_ms > 2000

# Error rate for one endpoint
jsonPayload.route = "/api/v1/accounts/{account_id}" AND jsonPayload.status_code >= 500

# What actually failed, grouped
jsonPayload.error.type != "" 
```

## Metrics

Three instruments, exported to Cloud Monitoring as
`custom.googleapis.com/opentelemetry/*`:

| Metric | Type | Labels |
|---|---|---|
| `http.server.requests` | counter | `http.method`, `http.route`, `http.status_code`, `status_class` |
| `http.server.duration` | histogram (ms) | same |
| `app.errors` | counter | `error.type`, `http.route` |

Labelled by route template rather than concrete path: Cloud Monitoring bills and
limits by cardinality, and one time series per account id would exhaust that
quota quickly.

## Alerts worth creating

Start with these three; they cover the failure modes this service actually has.

**1. Elevated 5xx rate** — the service is broken.
- Metric `http.server.requests`, filter `status_class = "5xx"`
- Aligner: rate, 60s. Condition: > 0.05/s for 5 minutes.

**2. Latency regression** — the service is slow.
- Metric `http.server.duration`, aligner: 95th percentile, 5m
- Condition: > 3000 ms for 10 minutes.
- Tune per route: the retrieval endpoints are legitimately slow and will need
  their own policy or a higher threshold.

**3. Service down** — an uptime check on `/health`.
- Check every 60s from 3 regions; alert on 2 consecutive failures.
- `/health` is deliberately excluded from request logging but **not** from
  metrics, so a health check that starts failing still shows up.

A fourth worth adding once the app is in front of users: alert on
`app.errors` by `error.type` crossing a low absolute threshold, which catches a
new exception class appearing after a deploy before users report it.

## Running it

Local, human-readable, no telemetry:

```bash
LOG_FORMAT=plain LOG_LEVEL=DEBUG uvicorn app.main:app --reload
```

Against Google Cloud:

```bash
GCP_PROJECT_ID=your-project ENVIRONMENT=production uvicorn app.main:app
```

Against a local OTLP collector:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 uvicorn app.main:app
```

Tests: `python -m pytest tests/test_observability.py -v`

## Adding a field

Pass `extra=` at the call site; the formatter emits any non-reserved attribute
automatically, with no change needed here.

```python
logger.info("Extracted widget", extra={"account_id": aid, "widget": name})
```

Do not put a credential, a token or a full request body in `extra` — these
records leave the process.
