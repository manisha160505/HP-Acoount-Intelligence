# Backend linting

Ruff, gated on push. Frontend linting was deliberately left out of scope;
`tsc --noEmit` covers the frontend in CI.

## Setup, once per clone

```bash
cd hp-backend && pip install -r requirements-dev.txt
cd .. && ./scripts/install-hooks.sh
```

The installer points `core.hooksPath` at `scripts/git-hooks/`, so hooks are
version-controlled and a change reaches everyone on the next pull. The existing
code-review-graph `pre-commit` hook is carried across, not replaced.

## Daily use

```bash
ruff check hp-backend            # what would block a push
ruff check hp-backend --fix      # fix what is mechanical
ruff format hp-backend           # format (by choice, not gated - see below)
```

A push runs `ruff check` and fails if anything is reported. In a genuine
emergency, `git push --no-verify`. CI re-runs the same check, so a bypassed
push still fails on the remote — which is the point: the hook is a fast local
signal, CI is the gate that actually holds.

## The dials

All in `hp-backend/pyproject.toml`. These are the values you asked to be able
to tune:

| Setting | Value | What it limits |
|---|---|---|
| `line-length` | 100 | characters per line |
| `max-statements` | 120 | statements in one function |
| `max-branches` | 40 | if/elif/for/while paths in one function |
| `max-args` | 8 | parameters |
| `max-returns` | 12 | return statements |
| `max-locals` | 40 | local variables |
| `max-complexity` | 25 | cyclomatic complexity |
| `max-public-methods` | 25 | methods on one class |

### Why these numbers

They were measured from the code, not taken from defaults. Over the 600
functions in `src/` at the time of writing: median 14 lines, p90 70, max 810.
85 functions are over 50 lines and 42 are over 80.

`max-statements = 120` is far above the conventional 50 on purpose. Set to 50,
it would have failed 85 existing functions on the first run, and a gate that
fails everything on day one gets switched off within a week. At 120 it catches
the genuine outliers — the 810-line and 688-line extractors — and, more
importantly, stops anything **new** from reaching that size.

**The intended direction is to ratchet these down** as the long extractors get
split, not to raise them when something new trips a limit. If a new function
hits the ceiling, that is the rule doing its job.

### Formatting is not gated

`ruff format` would rewrite 73 of the 82 files, because this codebase is
hand-wrapped to keep long comment blocks and scoring tables readable and the
formatter cannot know that. Gating it would produce one enormous reformat
commit burying every real change behind it. Run it by choice on a file you are
already rewriting.

## What was fixed getting to zero

836 violations initially, now zero. 301 were auto-fixed (unused imports, import
ordering, trailing whitespace), 31 more with scoped `--unsafe-fixes`
(`Optional` typing, comprehension simplifications). Hand-fixed:

- **10 `raise ... from err`** in the API layer — without `from`, the original
  exception is dropped from the chain and the traceback stops at the re-raise.
- **4 f-strings in logging calls** — these interpolate eagerly and bypass the
  structured-field path, so `logger.error(f"...{e}")` became
  `logger.error("...%s", e)`.
- **One dead branch** in `solution_narrative_opportunity_map.py` — see below.

## Rules that are off, and why

Each is a deliberate decision about this codebase, not a blanket silencing:

- `UP031` (296 hits) — `"%s" % x` is ordinary formatting here, and the lazy
  `logger.info("...%s", x)` form is correct practice.
- `PLC0415` (83) — function-level imports break circular dependencies between
  extractors and keep optional packages out of import time, which is exactly
  what makes the observability layer degrade gracefully.
- `BLE001` (17) — `except Exception` is the deliberate design: one failing
  feature degrades to an empty widget rather than taking the request down, and
  every handler logs first.
- `E402`, `ARG001/2`, `PLW0603`, `PLW2901`, `RUF001-3`, most `PTH*` — noise
  against this codebase's established and consistent patterns.

## Known debt, marked with `noqa`

23 findings were grandfathered rather than fixed, each with a `noqa` naming the
reason. The rules stay enabled, so new code cannot add to these. Two are real
latent bugs left for a behaviour decision rather than fixed silently:

- **`B023`** in `services/retrieval/pdf.py:344` — a closure captures the loop
  variable `years` by reference, so all closures see its final value. A classic
  late-binding bug. The fix is `def fix(match, years=years)`, but whether the
  current behaviour is load-bearing needs checking first.
- **`F841`** in `solution_narrative_opportunity_map.py:588,968` — two computed
  values are never read. Either the logic that should consume them is missing,
  or the computation is dead.

One was fixed because it could not be marked: `solution_narrative_opportunity_map.py:1166`
read `{...} | {... discovery_areas} if False else {...}`. The `if False` made
the first arm unreachable, which is the only reason the **undefined name**
`discovery_areas` never raised. It is collapsed to the arm that actually runs —
behaviour unchanged — with a comment saying what to do if the union was the real
intent.
