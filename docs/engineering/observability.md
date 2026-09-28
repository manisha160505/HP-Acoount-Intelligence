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

## Watching a pipeline run

The fields above are for reading logs after the fact, in Cloud Logging. A
supervised run - the two or three account wave that opens a 220-account build -
is the opposite case: someone is watching a terminal while it happens, and what
they need is to see each feature take the right datasets, match the right rules,
call the model the expected number of times, drop what the guardrails should
drop, and write the widgets it should write.

`app/observability/pipeline.py` owns that shape, so eleven extractors do not
each invent their own:

```
INFO [Astra] === START  (account_id=6a997c3bd0dfef61be9ff142)
INFO [Astra] executive_dashboard START
INFO [Astra] executive_dashboard     datasets      firmographics=1 hierarchy=1 jobs=100 contacts=23
INFO [Astra] executive_dashboard     urgency       62/100  coverage 92.5% (minimum 60.0%)
INFO [Astra] executive_dashboard     widget        exec_summary_card        available
INFO [Astra] executive_dashboard DONE 3 widgets 2s
INFO [Astra] tech_landscape          guardrail     1 dropped (no rulebook rule supports the detected technology)
INFO [Astra] tech_landscape          llm           gpt-4o x7  36.1s  9209 tokens
INFO [Astra] tech_landscape          proof         5 of 5 slot(s) filled  City of Bonn, NASA, STERNAUTO, ...
INFO [Astra] objection_playbook      cache         objection_reframe_cards  UNCHANGED - fingerprint unchanged
INFO [Astra] === DONE  11 features, 28 widgets (6 cached), 0 failed, 175s
```

| Helper | Emits |
|---|---|
| `account_scope(account_id, label)` | the `=== START` / `=== DONE` banner and the run totals |
| `feature_scope(feature_key)` | `START`, `DONE n widgets Ns`, or `FAILED` with the exception - and re-raises |
| `step(kind, message, **fields)` | one stage: datasets read, rules matched, gate results |
| `widget(key, status)` | one widget written, counted once |
| `cache_hit(key, reason)` | a widget served from cache, or kept because this run produced nothing |
| `llm_call(model, seconds, tokens)` | accumulated per feature, printed once on `DONE` |
| `guardrail(dropped, reason)` | silence here means nothing was dropped |
| `proof_allocated(customer)` | tallied inside `hp/case_studies.allocate`, so all nine call sites are covered |

The `[account] feature` prefix comes from two ContextVars in
`observability/context.py`, set by the scopes and read by `PlainFormatter`. A
220-account build is driven from a script, so there is no request id to
correlate on; the account and the feature are what a reader needs on every line.

**The cache line is not optional.** An extractor whose fingerprint has not moved
returns the stored widget and used to log nothing, so the run reported "OK 2s"
and looked like success - four times in one afternoon, each needing a manual
database query to notice the widget was stale. A run that is fast because
nothing changed must not look identical to a run that is fast because nothing
ran.

All of it is INFO. It is written to be read during a supervised run, not kept
behind DEBUG - a flag nobody remembers to set shows nobody anything.

### Reading it in a terminal

```bash
LOG_FORMAT=plain LOG_LEVEL=INFO
```

`PlainFormatter` then prints `LEVEL [account] feature message` instead of JSON,
and `quieten_noisy_loggers()` holds pymongo, httpx and LightRAG at WARNING.
LightRAG installs its own handler when a handle opens, long after startup, so
the retrieval layer calls that helper again once a handle is up - without it a
single index build buries the output under several hundred "Upserting relation
VDB" lines.

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
