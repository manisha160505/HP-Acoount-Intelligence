# The response envelope

One shape for every response, success or failure — the Python equivalent of
Go's `Response[T any]`.

```json
{
  "success": true,
  "data":    { "id": "68f1a2b3", "name": "PT Astra International Tbk" },
  "error":   null,
  "meta":    { "request_id": "3f9ac1b2...", "timestamp": "2026-09-16T08:00:00Z" }
}
```

```json
{
  "success": false,
  "data":    null,
  "error":   { "code": "ACCOUNT_NOT_FOUND", "message": "That account could not be found." },
  "meta":    { "request_id": "3f9ac1b2...", "timestamp": "2026-09-16T08:00:00Z" },
  "detail":  "That account could not be found."
}
```

## Does the frontend accept it?

Yes, and **no call site needed changing**. The axios interceptor in
[api.ts](../hp-frontend/src/services/api.ts) unwraps `data` on success, so
`response.data` is still the payload at all 33 read sites:

```ts
if (isEnvelope(response.data)) response.data = response.data.data;
```

That is the whole compatibility mechanism. `api.get<Account[]>(url)` gives
`response.data` typed as `Account[]`, exactly as before, and
`response.data.length`, `response.data[0].id` and destructuring all still work.

Errors are read from the **raw** envelope, because the success interceptor
never runs on a rejection — which is why `detail` is kept as a top-level alias
of `error.message`. The 16 sites doing `err.response.data.detail` are untouched.

## The generic

```python
from app.schemas.envelope import Response

Response[Account]           # data is an Account
Response[list[Widget]]      # data is a list of Widget
Response[None]              # a delete, data is null
```

`Response[Account]` and `Response[list[Account]]` generate **different** OpenAPI
schemas, so generated clients stay precisely typed rather than collapsing to
`Any`.

## How wrapping happens

[ResponseEnvelopeMiddleware](../hp-backend/src/app/observability/envelope_middleware.py)
wraps successful JSON centrally. Handlers are unchanged — a route still
declares `response_model=Account` and returns an `Account`, and the middleware
puts it in `data`.

This was deliberate over rewriting 25 endpoints to return `Response[Account]`
by hand: that would have meant touching every handler, restating every type,
and losing the per-payload OpenAPI schema.

**Not wrapped**, each for a reason:

| What | Why |
|---|---|
| `/health`, `/docs`, `/openapi.json` | read by the container platform and the schema UI, which do not know the envelope |
| File downloads (CSV, PDF) | wrapping a download in JSON corrupts the file |
| `204` / `304` | must not gain a body |
| 4xx / 5xx | already enveloped by the error handlers; re-wrapping would nest |
| Already-enveloped bodies | idempotent by design |

## `meta.request_id` on successes

A failure being traceable is the obvious case. The reason it is on **successes**
too: a user reporting "this number looks wrong" is reporting a 200, and without
an id on that response there is nothing to search the logs for.

It matches the `X-Request-ID` header and the `request_id` on the backend log
entry, so one id ties the browser console line, the API log line and the trace
together.

## A bug this found

The first implementation returned the original response object on its
early-exit paths — after `_read_body` had already consumed the body iterator.
That sent a **200 with an empty body** for any already-enveloped response. Both
paths now reconstruct the response; `test_wrapping_is_idempotent` pins it.

Tests: `python -m pytest tests/test_envelope.py -v`
