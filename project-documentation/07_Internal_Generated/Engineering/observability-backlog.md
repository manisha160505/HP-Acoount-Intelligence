# Remaining observability and quality work

Deferred by agreement — recorded here so none of it is lost. Ordered by value
against effort, not by when it came up.

## 1. Migrate the remaining 71 `raise HTTPException` sites

**Status:** 8 of 79 migrated (the ones leaking internals). The other 71 work
correctly through the compatibility handler and return the envelope already —
they simply carry a generic code (`RESOURCE_NOT_FOUND` rather than
`ACCOUNT_NOT_FOUND`) and inherit whatever status was hardcoded.

Worth doing per-file when touching a file anyway, not as one sweep. The value
is a precise code the frontend can branch on; the risk of a big-bang rewrite
is changing a status a screen depends on.

Concentration: `widgets.py` (30 left), `account_data.py` (18), `deps.py` (10),
`accounts.py` (9), `account_config.py` (9).

## 2. RESOLVED - `GET /api/v1/features` returned 500 to every caller

Seven `mapped_fields` in `api/v1/feature_mapping.py` carried a `data_type`
outside the two values the response schema allows, so FastAPI's response
validation failed the whole endpoint. It failed in the pre-existing code too;
structured logging is what surfaced it, as a `ResponseValidationError`.

The vocabulary comes from the handover document's two-layer model: a
**deterministic** layer (facts read from uploaded files plus scores computed in
Python) and an **LLM-inferred** layer. `DERIVED` and `REFERENCE` were third and
fourth words for those same two layers.

- Six fields marked `DERIVED` -> `DETERMINISTIC`. Each is computed in Python
  from named source columns (`source_publisher`, `influence_type`, `severity`,
  `scale_statement`, `target_contacts`, `likely_raiser`); none appears in any
  LLM prompt.
- `hp_capability`, marked `REFERENCE` -> `INFERRED / SYNTHESIZED`. It is read
  out of the model's JSON response in
  `solution_narrative_opportunity_map.py:1038`, so it belongs to the inferred
  layer despite naming no dataset.

Pinned by `tests/test_feature_mapping_contract.py`.

## 3. Two real bugs the linter found, left for a behaviour decision

Both are marked with `noqa` and a reason, so the rules stay live for new code.

- **Late-binding closure** — `services/retrieval/pdf.py:344`. The nested `fix()`
  captures `years` by reference, so every closure sees the final value rather
  than the one from its own iteration. The mechanical fix is
  `def fix(match, years=years)`, but whether any current output depends on the
  present behaviour needs checking first.
- **Two dead assignments** — `solution_narrative_opportunity_map.py:588, 968`.
  `has_any_trigger_available` and `cited_intent` are computed and never read.
  Either the logic that should consume them is missing, or the computation is
  dead and should go.

A third was fixed rather than deferred, because it could not be left marked:
line 1166 of the same file read `{...} | {...discovery_areas} if False else {...}`.
The `if False` made the first arm unreachable, which is the only reason the
**undefined name** `discovery_areas` never raised. Collapsed to the arm that
executes; behaviour unchanged.

## 4. Frontend linting

Out of scope by choice — backend-only was requested. `tsc --noEmit` runs in CI
and catches the same class of error. If it is wanted later: ESLint with
`next/core-web-vitals`, and `npx next lint` will offer to scaffold it.

## 5. Client-side log forwarding

`hp-frontend/src/lib/logger.ts` emits JSON to the console in production, in the
same shape the backend uses, but nothing collects it. To close the loop, add a
`POST /api/v1/client-logs` endpoint that accepts a batch and re-emits each
entry through the backend logger — the `request_id` correlation already works,
so a browser error would land in Cloud Logging beside the server-side line for
the same call.

Rate-limit it and cap the body size: it is an unauthenticated write path.

## 6. Alert policies in Cloud Monitoring

The metrics are exported; the policies are not created — that is console or
Terraform work rather than code. The three to start with are specified in
[observability.md](observability.md#alerts-worth-creating): 5xx rate, p95
latency, and an uptime check on `/health`.

## 7. Trace sampling before traffic grows

`OTEL_TRACE_SAMPLE_RATIO` is 1.0 — every request is traced. Correct at current
volume and while the system is new. Revisit when request volume or the trace
bill makes it worth lowering; the setting is already there.

## 8. Ratchet the lint thresholds down

`max-statements = 120` is far above the conventional 50 because 85 existing
functions exceed that. As the long extractors get split, lower it. The dials
and the measured distribution are in [linting.md](linting.md#the-dials).

## 9. Formatting

`ruff format` is deliberately not gated: it would rewrite 73 of 82 files and
bury every real change behind one reformat commit. If the team wants formatting
enforced, do it as a single dedicated commit that touches nothing else, then
turn the gate on.
