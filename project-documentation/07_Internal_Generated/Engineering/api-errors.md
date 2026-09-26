# API error contract

Every failure returns the same JSON shape, whatever raised it.

```json
{
  "detail": "That account could not be found.",
  "error": {
    "code": "ACCOUNT_NOT_FOUND",
    "message": "That account could not be found.",
    "request_id": "3f9ac1b2...",
    "fields": { "email": "Enter a valid address." }
  }
}
```

`fields` appears only on validation failures. `request_id` matches the
`X-Request-ID` response header and the backend log entry.

## Why `detail` is still a plain string

It is the compatibility hinge. Sixteen call sites in `hp-frontend` do:

```ts
const msg = err.response?.data?.detail || 'Failed to load.';
```

and render `msg` straight into the DOM. Making `detail` an object would print
`[object Object]` in all sixteen. Keeping it a string means the structured
`error` object is purely additive: existing screens were not touched, and new
code reads `error.code`.

This also **fixed a live bug**. FastAPI's own 422 puts an *array* of error
objects in `detail`, so every one of those sixteen sites already rendered
`[object Object]` whenever a form failed validation. Validation errors are now
normalised into the same envelope with a readable sentence.

## Raising an error

```python
from app.errors import APIError, ErrorCode

raise APIError(ErrorCode.ACCOUNT_NOT_FOUND)                      # default message
raise APIError(ErrorCode.INVALID_PARAMETER, "Quarter must be Q1-Q4.")
raise APIError(ErrorCode.NO_SOURCE_DATA,
               log_context={"account_id": aid})                  # logged, never sent
```

The **code determines the status**. A raise site names the condition rather
than picking a number, which is what stopped the same "not found" being a 400
in one handler and a 404 in another.

`log_context` is for developers. It reaches the log line and never the
response body — it is where a connection string or an internal id belongs.

## Status codes

| Code | Status | Meaning |
|---|---|---|
| `INVALID_ID_FORMAT`, `INVALID_PARAMETER` | 400 | the request is malformed |
| `UNAUTHENTICATED`, `INVALID_CREDENTIALS`, `TOKEN_EXPIRED` | 401 | sign in |
| `FORBIDDEN` | 403 | signed in, not allowed |
| `*_NOT_FOUND` | 404 | no such resource |
| `ALREADY_EXISTS`, `NO_SOURCE_DATA`, `INDEX_NOT_READY` | 409 | request fine, state not ready |
| `FILE_TOO_LARGE` | 413 | |
| `UNSUPPORTED_FILE_TYPE` | 415 | |
| `VALIDATION_ERROR`, `EXTRACTION_FAILED` | 422 | well-formed, unprocessable |
| `EXTRACTION_FAILED`, `DATABASE_ERROR`, `INTERNAL_ERROR` | 500 | server fault |
| `GENERATION_FAILED`, `UPSTREAM_ERROR` | 502 | upstream failed |
| `LLM_UNAVAILABLE`, `LLM_NOT_CONFIGURED` | 503 | try again later |

**409 vs 400 for `NO_SOURCE_DATA`** is the distinction that matters to a
seller: the call was correct and the data simply is not uploaded yet. A 400
would suggest they sent something wrong.

## Reading errors in the frontend

Existing screens need no change. New code can use the helper:

```ts
import { parseApiError, isMissingData, isRetryable } from '@/lib/apiError';

const e = parseApiError(err, 'Failed to load the dashboard.');
if (isMissingData(e)) showUploadPrompt();
else if (isRetryable(e)) showRetry(e.message);
else showError(e.message);
```

`parseApiError` handles a missing body, so a network failure or a gateway
error returns a sensible message rather than throwing.

## What never leaks

An unhandled exception returns a generic message plus the request id; the
exception text is withheld because it can carry a connection string, a key, or
customer data. Eight raise sites that did leak internals — `detail=str(exc)`
and `f"Regeneration failed: {type(exc).__name__}: {exc}"` — were migrated.
Where a domain exception's message was genuinely written for a user
(`EvaluationError`, `PillarError`), that wording was kept and only the status
and code corrected.

Tests: `python -m pytest tests/test_errors.py -v`
