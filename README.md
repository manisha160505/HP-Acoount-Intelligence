# HP Account Intelligence

An account-based marketing platform for HP sellers. An admin uploads CSV exports
for a target account; the backend extracts them into per-feature widgets that the
dashboard renders. Eleven features are in scope — four have both a deterministic
and an AI-inferred layer in production, the rest are deterministic-only.

The conventions this code enforces are in [`docs/engineering/`](docs/engineering/README.md):
the response envelope, the error contract, linting, observability and branch
protection.

Everything else — client requirements, logic documents, the decision log,
question trackers, data definitions, delivery planning — is client material and
is **not committed**. It lives locally under `project-documentation/`, indexed
from `project-documentation/README.md`, and git ignores that folder. Two
documents there are worth reading before changing an extractor:
`07_Internal_Generated/Rules_and_Handover/HP-Account-Intelligence-Handover.docx`
(feature status and the dataset → feature mapping) and
`02_Decision_Maker/HP-Account-Intelligence-Rules.docx` (every rule, guardrail
and scoring decision, anchored to the line of code that implements it). Ask a
teammate for the folder if you do not have it.

---

## Setup

### 1. Environment

```bash
cp .env.example .env          # repo root, used by docker compose
cp .env.example hp-backend/.env
```

Then fill in `hp-backend/.env`:

| Variable | Notes |
|---|---|
| `MONGODB_URI` | The shared Atlas cluster. Ask the team for the connection string. |
| `OPENAI_API_KEY` | Azure OpenAI key. Only needed if you intend to **generate**; see below. |

Two things that will silently cost you an afternoon:

- **`.env` is read relative to the working directory.** Start the backend from
  `hp-backend/` (see below) or the file is not found and every AI layer stays
  empty. `--app-dir src` sets the import path, *not* the working directory.
- **Atlas requires your IP to be allowlisted.** Without it the app fails at
  startup with a message naming the URI. That is deliberate — it used to start
  fine and render blank.

### 2. MongoDB

Using the shared Atlas cluster, you need nothing locally.

Running against a local database instead:

```bash
docker compose up mongodb          # or install MongoDB and start it
```

Then set `MONGODB_URI=mongodb://localhost:27017`.

### 3. Run

```bash
# backend — from hp-backend/, not from hp-backend/src/
cd hp-backend
pip install -r requirements.txt
uvicorn app.main:app --app-dir src --reload --port 8000

# frontend
cd hp-frontend
npm install
npm run dev
```

Sign in with `admin@hp.com` / `AdminPassword123!` (admin, can upload) or
`user@hp.com` / `UserPassword123!`.

---

## What happens on first start

`seed_database_if_empty()` runs on every startup and is idempotent:

1. Seeds the two users.
2. Creates the benchmark account (PT Astra International Tbk) if absent.
3. Copies the 11 CSVs from `hp-backend/seed_data/astra/` into
   `hp-backend/data/accounts/<account_id>/` and registers them.
4. Runs every extractor in `FEATURE_EXTRACTORS`.

The startup log ends with a readiness line naming the account, dataset count and
widget count, and warns if `OPENAI_API_KEY` is missing or still the placeholder.
**If a feature is blank, read that line first.**

### Files are local; the database may be shared

Only metadata is in MongoDB. The CSV bytes live on disk, and
`account_data_files` stores a *path*. On a shared cluster that means rows can
point at files that exist only on the machine that uploaded them.

This is handled rather than ignored: `requires_local_datasets` aborts an
extractor whose source files are absent from this machine and logs which ones,
**leaving the stored widgets untouched** instead of overwriting them with empty
data. So a teammate without the files sees the existing content, not blanks.

The 11 seeded Astra datasets are in the repository and therefore always
available. Anything uploaded through the admin UI afterwards is not.

To move an existing local database into the shared cluster:

```bash
cd hp-backend
python scripts/migrate_to_atlas.py --target "mongodb+srv://..."           # dry run
python scripts/migrate_to_atlas.py --target "mongodb+srv://..." --apply
```

---

## Regeneration

Nothing expensive runs on its own. Changes only mark outputs **stale**;
regeneration happens when an admin submits it:

| Event | Regenerates? |
|---|---|
| Upload, replace or delete a dataset | No — the affected sections become stale |
| Edit account instructions or guardrails | No — the Opportunity Map becomes stale |
| Deploy / restart, prompt, rule or model change | No — affected sections become stale; startup logs how many accounts need a run |
| Open a feature in the dashboard | No — stored widgets are served; nothing is queued |
| **Submit** on the admin account page (Pipeline tab) | Yes — every stale, failed, degraded or never-run section of that account, once, in dependency order |
| `POST /api/v1/regeneration` | Yes — exactly what the request asks for |

`POST /api/v1/regeneration` takes `accounts` (ids, exact names or `"all"`),
`features` (ids or `"all"`), optional `nodes` (single sections), `force`
(default `false`: current sections are skipped) and `include_downstream`.
`POST /api/v1/regeneration/preview` returns the same plan without running
anything or calling a model. `GET /api/v1/regeneration/{run_id}` shows a run's
progress, errors and model usage; `GET /api/v1/accounts/{id}/pipeline` shows
every section of an account grouped by status, with why each one is stale
(data file, upstream section, code, prompt, rules, model or instructions).

A section is never re-queued or restarted on its own. Whatever stops it - its
own error, a model error that outlasts the short in-call waits, the quota
running out, its data files missing on the server, the worker dying, or a
restart/deploy - it goes straight to **Failed** with that reason on the
Pipeline tab, keeps its previous output, and runs again only on the next
Submit. A quota failure also pauses the queue, so the sections still waiting do
not each fail on it; an admin presses Resume. Work done before the failure is
kept and reused on the re-run: an index build continues from the documents it
finished, and Live Signals from the batches it scored.

AI output is cached on a SHA-256 fingerprint of the inputs plus a prompt
version, so identical data costs zero model calls. Bump the module's
`*_PROMPT_VERSION` to mark the section stale.

Without an LLM API key, deterministic widgets populate normally and inferred
widgets are stored as `pending` with a notice explaining why — shown in the UI.
Nothing is fabricated to fill the gap.

---

## Guardrails

Every generated string is checked against a corpus built from the account's own
uploaded cells. Numbers must appear as exact tokens, percentages verbatim, URLs
verbatim, and product names must resolve to an approved HP line.

```bash
cd hp-backend
python scripts/audit_grounding.py     # exits non-zero if anything is unsourced
```

Run it after touching any extractor. The full rule set is in
`HP-Account-Intelligence-Rules.docx`.

---

## Layout

```
hp-backend/
  src/app/
    api/v1/            routes, widget registry, feature→dataset mapping
    core/              seeder, LLM client, security
    database/          Mongo connection
    services/extractors/
      datasets.py      shared dataset reader + the missing-file guard
      grounding.py     shared grounding enforcement
      <feature>.py     one module per feature
  scripts/             audit_grounding.py, migrate_to_atlas.py
  seed_data/astra/     the 11 benchmark CSVs (committed)
  data/accounts/       uploaded files (gitignored, machine-local)
hp-frontend/src/app/dashboard/    the dashboard
```
