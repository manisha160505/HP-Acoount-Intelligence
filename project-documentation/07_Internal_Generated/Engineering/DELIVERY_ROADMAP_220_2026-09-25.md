# HP 220-Account Delivery Roadmap

**Status as of:** Fri 25 Sep 2026, 13:00 IST · **Owner:** Yogesh (delivery lead) · **Co-owner:** Manisha
**Built from:** the repository state, `220 account split csv/`, `project-documentation/`, the local and shared databases, and the 25 Sep client answers. Every claim below was checked against the source today; nothing is assumed from the doc filenames.

---

## 0. Where we actually are (verified today)

### Data

| Item | State |
|---|---|
| Per-account split | 220 folders under `220 account split csv/`, built 25 Sep 10:53 IST. 25 dataset slots each, plus `reference/` (13 tables no feature reads yet) and `compliance_filings/` (index only, 0 PDFs). |
| Split validator | `scripts/validate_split_data.py` run today: **0 FAIL, 22 WARN**, exit 0. Every warning is a vendor-side property (duplicate ids, blank Exa dates, HTML fragments). Transformation is sound. |
| Coverage (accounts with rows / 220) | firmographics 220 · webstack 219 · technology_detections 217 · google_news 218 · hp_category_intent 218 · news_events 214 · technographics 207 · job_openings 176 · intent_score + intent_topics 173 · company_hierarchy 165 · **prospect_contacts 1** (Astra seed) · **compliance_filings 0** |
| Feature readiness | Technographic Map complete on 205; Intent & Demand complete on 141. Every other feature is "partial" on all 220 because contacts and filings PDFs are source-wide gaps, not account-specific ones. Message Evaluator has nothing to read on 44 accounts (no jobs and no contacts). |
| Domain audit vs split | The audit sheet arrived at 12:30 IST, after the split was built. Reconciled today: all 219 Column B names equal the split's `name_for_upload` exactly. **3 domains differ:** Posco (`posco-inc.com` → `posco.com`), Pilipinas Shell (`pilipinas.shell.com.ph` → `shell.com.ph`), Public Bank (`publicbankgroup.com` → `pbebank.com`). Astra is not in the sheet (separate seed delivery), which is expected. **Only Public Bank changes data:** it holds 0 PredictLeads rows today and gains 268 under pbebank.com (1 company, 47 tech detections, 38 news, 100 connections, 82 subpages), which are exactly the split's current "unclaimed" rows. Posco and Shell already carry their rows through the alias; only their recorded domain changes. **Applied 25 Sep:** split rerun, 219/219 domains equal the sheet, unclaimed PredictLeads rows 274 → 0, validator 0 FAIL. |
| News precedence | The split's `google_news()` concatenates RSS first, then Exa, then `drop_duplicates` on domain + headline + date. **It keeps the RSS row and drops the Exa row.** The client decided the opposite on 25 Sep (DEC-054a). One-line fix plus rerun. |
| Filings re-keys | DEC-054f (Fletcher → fletcherbuilding.com, Fonterra → fonterra.com, Hyundai DART rows → HKMC GROUP, Jabil 10-Q on both Jabil accounts, United Tractors row excluded) is not yet applied in the split. |

### Platform

| Item | State |
|---|---|
| Accounts loaded | **0 of 220** anywhere. Local Docker Mongo holds only the Astra seed (1 account, 13 files). Backend not running; only the frontend dev server is. |
| Which database the backend uses | `hp-backend/.env` points at the **shared Atlas cluster**, the same database the Render site reads (Astra and Astra_Step73 live there, 20 files each). The reference collections exist **only** there: `hp_rulebook` 234 docs (extractor v5, parsed from the 23 Sep FINAL Rulebook), `hp_case_studies` 90, `hp_product_knowledge` 381, `hp_lifecycle` 145. The local Docker Mongo has none of them. |
| Rulebook FINAL | The docx is not on this machine, but its parsed rules are in `hp_rulebook` (v5 adds the INK family, print 3 → 39, scan 3 → 10, six guardrails). This is a documentation gap, not a code gap. |
| Ingestion path | HTTP only: `POST /accounts` (name, unique) then one `POST /accounts/{id}/data` per dataset file. **Every upload synchronously reruns every feature that reads that dataset; there is no bypass.** With ~21 files per account that is ~43 extractor runs, ~17 of them LLM features. |
| Two-pass load without new code | With `OPENAI_API_KEY` unset, the 7 deterministic features populate and the 4 LLM features are stored `pending`. `scripts/regenerate_features.py --include-llm` then reruns the 4 LLM features once per account. |
| Retrieval layer | The Strategy Chat / Executive Dashboard / Content Messaging retrieval indexes are queued on upload and also need the key (`services/retrieval/client.py`). Astra's index on the shared cluster is ~176 text chunks, ~2,150 entity chunks and ~1,000 cached LLM responses. At that size, 220 accounts means on the order of 200,000 LLM calls for the index alone. This is the expensive part of pass 2 and must be measured on wave 1 before committing to all 220. |

### Code vs the 24–25 Sep client decisions

| Decision | In code today? | Where it bites |
|---|---|---|
| Display name = audit Column B (DEC-052) | **No.** Executive Dashboard header shows firmographics "Company Name" first, `accounts.name` only as fallback. | Every account would show the vendor's name (e.g. "Epson America Inc." for SEIKO EPSON CORPORATION - JP). |
| Keep the Exa row on duplicate news (DEC-054a) | **No** (split keeps RSS). | Live Signals content. |
| Empty sections left out, no message (DEC-054b) | **No.** Dashboard renders "unavailable" / "No supporting…" text. | With 0 contacts, every account shows empty-state text on five features. |
| Our source labels, no vendor names (DEC-054c) | **Partly.** "Bombora" and "Explorium" strings render in `dashboard/page.tsx`. | Intent and Tech widgets. |
| Per-dataset as-of date (DEC-054d) | Yes (`uploaded_at` per dataset). | — |
| Relevance wording tiers "is relevant" / "may be relevant"; technology alone ≤ "may"; zero intent in the matching category blocks the offering (DEC-053, DEC-054g/h) | **No.** Bands are Confirmed / Likely / Discovery; zero intent demotes topics to "context" but does not block. | Opportunity Map (LLM), Content Messaging, Objection Playbook. |
| No Rulebook↔case-study table, four-case rule (DEC-054i/j) | Yes (keyword matcher, independent of the router). | — |
| Stakeholder Map carries no proof (DEC-054k) | Yes. | — |
| Unevaluable numeric conditions treated as unmet (DEC-054h) | Nothing to do: no numeric thresholds exist in code. | — |

---

## 1. Immediate priority order

**Answer to the main question:** option 4, in parallel, with one strict order inside the data lane. The "latest PredictLeads update" is the domain-audit sheet, and incorporating it is a two-hour split fix, not a workstream. Documentation is not allowed to hold up ingestion: the must-do set is about two hours of work and runs beside it.

### FIRST, today, sequential (Yogesh, ~3–4 h)

1. **Correct the split** (audit domains, Exa-first dedup, DEC-054f filings re-keys). Rerun split, validator, and an audit reconciliation check. This closes CP2, CP3 and CP4 in one pass.
2. **Fix the local environment** (CP0): run against the local Docker Mongo, clone the four reference collections from Atlas into it, start the backend with the key unset.
3. **Write the loader with a ledger** and load wave 1 (5 accounts). Measure seconds per account and extractor failures (CP5).

### IN PARALLEL from today (Manisha)

- One client follow-up email with nine items and stated defaults (contacts ETA, GCP project/region, Rulebook FINAL docx, Products feature list, jobs for 45 accounts, Name + Country columns, Exa dates, vendor-flagged rows default, F11/F12 re-asked in one line each).
- Frontend conformance: display name from `accounts.name`, vendor labels out, empty sections hidden.
- The one-page run contract and three decision-log entries.
- Filings PDFs from Pritesh's machine.

### THEN (Yogesh)

4. Pass 1 (deterministic) across all 220 in batches with stop-on-fail.
5. Relevance wording tiers and the zero-intent negative rule in `recommendations.py`.
6. Pass 2 (LLM regeneration and retrieval index) once, across all 220.

### NOT a priority now

Perfecting documentation; retrieving the superseded files in `MISSING_FILES.md` §B; Products / sec_filings feature work (needs the client's screenshot list first); Strategy Chat "Step 8" RAG; QA-validator false-failure fixes; anything on Render; Astra_Step73.

### The four questions

| Question | Answer |
|---|---|
| What blocks the 220 run today? | Nothing hard for pass 1. Pass 2 should wait for the relevance change, or the Opportunity Map is paid for twice. |
| What can proceed with the data we have? | All 220 accounts through the 7 deterministic features. Technographic Map is final on 205 accounts and Intent & Demand on 141 today. |
| What waits for GCP? | Only the copy (database plus the `data/accounts/` tree). Everything else, including the go-live checklist, is prepared locally. |
| What waits for client data? | Contacts (five features on 219 accounts), job rows for 45 accounts, Name + Country columns (Jabil SG, MUFG Bangkok), Exa dates, filings PDFs (unless Pritesh's copy arrives first), the Products feature list. Each is a targeted rerun of the affected features, not a restart. |

---

## 2. Workstreams

The split minimises dependency: Yogesh owns everything that touches data and the backend run; Manisha owns everything that faces the client, the UI conformance items (frontend only), documentation upkeep and QA. The only hand-offs are M2 → CP8 (UI fixes must be in before the client sees output) and Y6 → M6 (rules doc follows the code).

### Yogesh

#### Y1 · Correct the split for the 25 Sep decisions
- **Why it matters:** three accounts carry the wrong canonical domain; Live Signals would show the RSS version of every duplicated story; five accounts' filings are keyed wrongly.
- **Input:** `PredictLeads_219_Account_Domain_Audit.xlsx` sheet "219 Account Audit" (col D = domain, col B = name); DEC-054a; DEC-054f.
- **Expected output:** `split_account_data.py` reads the audit sheet as the domain source (delete the posco/shell aliases, add `pbebank.com`), lists Exa before RSS in `google_news()`, applies the five filings re-keys; split rerun; `validate_split_data.py` 0 FAIL; `_CORRECTIONS.txt` regenerated; a new reconciliation output: 219/219 domains and names equal the audit sheet.
- **Dependency:** none.
- **Progress (25 Sep):** domain part DONE: the split reads the audit sheet, aliases point toward it, Public Bank = pbebank.com, 219/219 domains reconciled, unclaimed PredictLeads rows 0. Still to do: Exa before RSS in `google_news()`, the five filings re-keys.
- **Definition of Done:** validator 0 FAIL; reconciliation 219/219; `_RUN_SUMMARY.json` shows Exa rows retained on duplicates (dedup count recorded); unclaimed PredictLeads rows drop to 0 for company, extended_company and tech detections, because Public Bank now claims them; the five re-keyed filings rows appear in the right `_filings_index.csv`.

#### Y2 · Local environment for the run (CP0)
- **Why it matters:** the backend currently writes to the shared Atlas cluster that Render reads. Loading 220 accounts there would list them on the live site with files that exist only on this machine. The local Mongo lacks the rulebook and case studies, so recommendations would run on nothing.
- **Input:** `hp-backend/.env`; Atlas collections `hp_rulebook`, `hp_case_studies`, `hp_product_knowledge`, `hp_lifecycle`.
- **Expected output:** `MONGODB_URI=mongodb://localhost:27017` for the run; a 20-line copy script (pymongo) that clones the four collections and their version docs into local `hp_account_db`; backend started from `hp-backend/` with `OPENAI_API_KEY` blank; readiness line confirms Astra, dataset and widget counts; a note on what `retrieval_jobs` does without a key.
- **Dependency:** none.
- **Definition of Done:** local `hp_rulebook` count = 234 and version doc `extractor_version` = 5; `hp_case_studies` = 90; backend health endpoint answers; `rulebook.load(db)` against the local database returns non-empty rules and routing; an Astra regenerate completes with LLM widgets stored `pending`, not `failed`.

#### Y3 · Loader and run ledger
- **Why it matters:** there is no bulk endpoint. Manual upload of ~4,600 files is not an option, and without a ledger a failure on account 137 is invisible.
- **Input:** each folder's `_account.json` (`name_for_upload`), `_MISSING.txt` / `--print-upload-plan` (rows-only files), the upload API, `regenerate_features.py` for auth pattern.
- **Expected output:** `scripts/load_accounts.py` that, per account: runs the pre-ingestion checklist (§4), creates the account named `name_for_upload`, uploads only files with rows in a fixed order (firmographics first, `google_news` last), records one ledger row (`_RUN_LEDGER.csv`: slug, name, account_id, files uploaded, files skipped, features ok / empty / failed, seconds, pass-2 status, LLM calls, QA sample, notes), and is idempotent (skips accounts already `ok`). Flags: `--accounts`, `--batch-file`, `--stop-on-fail`, `--dry-run`.
- **Dependency:** Y1, Y2.
- **Definition of Done:** wave 1 (five accounts) loads end to end from one command; the ledger shows 11 stored widgets per account, none `failed`; rerunning the command changes nothing.

#### Y4 · Wave 1 and measurement (CP5)
- **Why it matters:** sets the batch size, time budget and LLM cost for the other 215.
- **Input:** five deliberately different accounts: BHP BILLITON - AU (the client's worked example), SEIKO EPSON CORPORATION - JP (Column H name mismatch), PUBLIC BANK BHD - MY (domain changed today), JABIL CIRCUIT (SINGAPORE) PTE LTD - SG (shared domain, sparse), MINISTRY OF DEFENCE - SG (government, thin data).
- **Expected output:** seconds per account for pass 1; the post-processing checklist (§4) passed on all five; `audit_grounding.py` exit 0; a screenshot set for Manisha's QA.
- **Dependency:** Y3.
- **Definition of Done:** all five accounts open in the dashboard with the right header name and no extractor failure in the backend log; timings written into the run contract.

#### Y5 · Pass 1 across all 220
- **Why it matters:** this is the deliverable's deterministic body; it does not depend on any open client item.
- **Input:** batch files in alphabetical order (20 accounts, then 50s), the ledger.
- **Expected output:** 220 ledger rows `pass1 = ok`; `_READINESS.csv` cross-checked against stored widget status (a feature "complete" in readiness must not be `empty` in storage).
- **Dependency:** Y4 timings.
- **Definition of Done:** 220/220 ok; zero `failed` features; grounding audit exit 0 on a 10 % sample; the readiness cross-check shows no contradictions.

#### Y6 · Relevance wording tiers and the zero-intent rule
- **Why it matters:** DEC-053 changes the final output of every recommendation. Running pass 2 before it means paying for the Opportunity Map twice.
- **Input:** `services/hp/recommendations.py`, `rulebook.py`, `solution_narrative_opportunity_map.py`; DEC-053, DEC-054g/h; the client's BHP examples (Intune + ServiceNow only → no WXP recommendation; plus fleet-management intent → "may be relevant"; plus Rulebook conditions → "is relevant"; WebEx + TelePresence with Poly intent 0 → no Poly).
- **Expected output:** a `relevance` field per offering with values `relevant` / `may_be_relevant` / `not_recommended`; technology-only evidence caps at `may_be_relevant`; zero intent in the matching category yields `not_recommended`; unevaluable conditions count as unmet; the context line reads "Intune detected; possible WXP integration route". Unit tests for the four BHP cases.
- **Dependency:** none (can run in parallel with Y5).
- **Definition of Done:** tests green; Astra and BHP regenerated locally show the new wording; `HP-Account-Intelligence-Rules.docx` v2 entry handed to Manisha (M6).

#### Y7 · Pass 2: LLM features and retrieval index, once
- **Why it matters:** the four LLM features and Strategy Chat need it; it is the only step that costs money.
- **Input:** `OPENAI_API_KEY` set; `regenerate_features.py --include-llm`; `rebuild_index.py`.
- **Expected output:** per-account LLM call count and cost measured on wave 1 first, then a go / scope decision (retrieval index on all 220, or on demand via the first-view bootstrap); then all 220.
- **Dependency:** Y5, Y6.
- **Definition of Done:** no `pending` LLM widgets on any account; retrieval index state per account recorded; ledger pass-2 column complete; grounding audit exit 0 on a 10 % sample.

#### Y8 · GCP: prepare now, execute on access
- **Why it matters:** Render has no persistent disk, so the 220 uploads cannot live there. The cut-over must be one copy, not a re-run.
- **Input:** `migrate_to_atlas.py` (works for any target URI), `migrate_shared_vdb.py`, the `data/accounts/` tree, `.env`, Dockerfile.
- **Expected output (now):** a go-live checklist; a sha256 manifest of `data/accounts/`; storage decision (persistent disk mounted at the same relative path, since `account_data_files.file_path` is relative); the env var list; the order of operations (restore database **before** first backend start, so the seeder does not create a second Astra). **On access:** execute and smoke-test five accounts.
- **Dependency:** Sahaj's project id and region (open item D42).
- **Definition of Done:** manifest verified on the target; 220 accounts served from GCP with the same widget counts as local; frontend pointed at the GCP API.

### Manisha

#### M1 · Client follow-up, one email, nine items with defaults
- **Why it matters:** every item has been asked before; the client answers whichever default is stated. Defaults let us proceed without waiting.
- **Input:** `06_Unresolved_and_Open/README.md`; round-3 files in `07_Internal_Generated/Client_Facing_Round3/`.
- **Expected output:** email in thread `1a082bca2581fea0` covering: contacts ETA and key columns; GCP project id / region (Sahaj); Rulebook FINAL docx re-send; the Products screenshot list as text; job rows for the 45 accounts; Name + Country columns on PredictLeads rows; Exa dates; the nine vendor-flagged rows (default: drop); F11 / F12 re-asked as one-line examples.
- **Dependency:** none.
- **Definition of Done:** sent today; each item logged in `build_questions.py` with its default and date.

#### M2 · Frontend conformance to DEC-052 / 054b / 054c
- **Why it matters:** three visible violations would appear on every one of the 220 accounts the moment the client opens them.
- **Input:** `hp-frontend/src/app/dashboard/page.tsx`; `executive_dashboard.py` header source; DEC-052, DEC-054b, DEC-054c.
- **Expected output:** header shows `accounts.name` (Column B) everywhere the account is named; "Bombora" / "Explorium" strings replaced by Intent / Technographics labels; a widget or section with `status: empty` renders nothing (no "unavailable" text), across all 11 features.
- **Dependency:** none for the change; Y4 screenshots to verify.
- **Definition of Done:** wave-1 accounts show the master name; grep for vendor names in rendered strings returns nothing; the Stakeholder Map on a no-contacts account is absent, not a message.

#### M3 · Run contract and decision-log entries
- **Why it matters:** this is the document that answers "which rule, dataset or decision caused this" during the run.
- **Input:** this roadmap; `_DATASET_USAGE.md`; `DECISION_LOG.md`; `00_INDEX/_build/`.
- **Expected output:** `07_Internal_Generated/Engineering/RUN_CONTRACT_220.md` (one page: identity rule, upload rule, pass 1 / pass 2, ledger location, stop rules, who to call); DEC-056 two-pass load, DEC-057 local database for the run, DEC-058 account name = territory name = Column B; a code-gap register (the table in §0) as `DECISION_TO_CODE_GAPS.md`.
- **Dependency:** none.
- **Definition of Done:** all three files committed; `build_docs.py` and `build_questions.py` rerun cleanly.

#### M4 · Filings PDFs from Pritesh
- **Why it matters:** filings feed five features and the financials evidence on the Executive Dashboard; 0 of 220 are local; 474 already exist on Pritesh's machine.
- **Input:** `filings 1.csv` (`local_path`, `sha256`), Pritesh.
- **Expected output:** a zip of `/Users/priteshhome/220-account/filings/`; sha256 verified against the index; PDFs dropped into each account's `compliance_filings/` folder via a small script keyed on the index; a list of index rows whose file is missing.
- **Dependency:** Pritesh's availability; Y1's re-keyed index.
- **Definition of Done:** count of PDFs placed = count of index rows with SUCCESS minus the missing list; the loader picks them up on the next run of the affected accounts.

#### M5 · QA protocol and per-batch spot check
- **Why it matters:** the validator proves the CSVs; nothing yet proves the output. A 10 % sample per batch catches systematic errors before 220 are done.
- **Input:** wave-1 screenshots; feature logic docs in `03_Feature_and_Logic/`; the post-processing checklist (§4).
- **Expected output:** a one-page checklist per feature (5–8 checks each, tied to the governing doc); a QA column in the ledger; findings filed as issues with the rule id they violate.
- **Dependency:** Y4 (first sample).
- **Definition of Done:** every batch has its sample checked before the next batch starts; findings triaged as data / code / decision.

#### M6 · Rules doc v2 and handover refresh
- **Why it matters:** the client is reviewing the 10 Sep rules doc; any rule changed by Y6 that is not in it reads as undisclosed behaviour.
- **Input:** Y6 output; `HP-Account-Intelligence-Rules.docx`; `HP-Account-Intelligence-Handover.docx`.
- **Expected output:** v2 of the rules doc with the relevance tiers, the zero-intent rule, empty-state and label rules; handover doc updated at CP10.
- **Dependency:** Y6.
- **Definition of Done:** v2 sent to the client; both docs re-indexed by `build_docs.py`.

#### M7 · Retrieve the missing decision documents (low priority)
- **Why it matters:** the Rulebook FINAL docx, `tests on current HP 220.docx` and `HP_220_Refinements_Updated.docx` are cited by the registers but not on disk. Needed for the record, not for the run.
- **Input:** Gmail thread attachments (manual download).
- **Expected output:** files dropped into the folders named in `MISSING_FILES.md` §A; placeholders deleted; provenance rebuilt.
- **Dependency:** none.
- **Definition of Done:** `MISSING_FILES.md` §A empty except the client-owed items.

---

## 3. Delivery checkpoints

Targets assume wave-1 timings are reasonable; adjust after CP5. "Evidence" is what must exist on disk or in the database, not a verbal report.

| CP | What must be true | Owner | Evidence | Blocks next | Target |
|---|---|---|---|---|---|
| **0 · Environment ready** | Backend runs against the local Docker Mongo with the four reference collections cloned; key unset for pass 1; frontend points at local API. | Yogesh | Local `hp_rulebook` = 234 (v5), `hp_case_studies` = 90; readiness log line; Astra Opportunity Map regenerate returns candidates. | Everything | 25 Sep |
| **1 · Source of truth ready enough** | Run contract exists; DEC-056/057/058 logged; code-gap register exists; `_DATASET_USAGE.md` and `_CORRECTIONS.txt` regenerated by Y1. | Manisha (docs), Yogesh (split outputs) | The three files in `07_Internal_Generated/Engineering/`; `DECISION_LOG.md` diff. | CP5 (the run must be describable before it starts) | 25 Sep |
| **2 · Account data validated** | Validator 0 FAIL after Y1; warnings triaged into the run contract. | Yogesh | Validator log saved beside the ledger. | CP3 | 25 Sep |
| **3 · 220 split validated** | Split rerun with audit domains, Exa-first, filings re-keys; reconciliation 219/219. | Yogesh | New `_RUN_SUMMARY.json`; reconciliation output. | CP5 | 25 Sep |
| **4 · Latest PredictLeads data incorporated** | Same rerun as CP3: the audit sheet is the only new PredictLeads item. Products and sec_filings stay in `reference/` until the feature list arrives. | Yogesh | Three `_account.json` domains changed; Public Bank folder has PredictLeads rows. | CP5 | 25 Sep |
| **5 · First accounts end to end** | Wave 1 (five accounts) loaded by the loader; 11 stored widgets each; post-processing checklist passed; timings known. | Yogesh; Manisha QA | Ledger rows; backend log; grounding audit exit 0; screenshots. | CP6 | 26 Sep |
| **6 · Pipeline fixes and stable reruns** | Every extractor failure from wave 1 fixed; M2 UI fixes merged; Y6 relevance change merged with tests; a wave-1 account deleted and reloaded gives identical widget counts. | Yogesh (backend), Manisha (frontend) | Green tests; ledger rerun rows; diff of widget payloads before/after reload. | CP7 pass 2 | 29 Sep |
| **7 · All 220 processed** | Pass 1 on 220 (can complete before CP6's Y6); pass 2 on 220 after CP6. | Yogesh | 220 ledger rows `pass1 = ok`, `pass2 = ok`; no `pending` LLM widgets; index state recorded. | CP8 | pass 1: 29 Sep · pass 2: 1 Oct |
| **8 · Final validation** | 10 % QA sample per batch passed; grounding audit exit 0 on the sample; readiness vs storage cross-check clean; no vendor names, right header name, no empty-state text on any sampled account. | Manisha (QA), Yogesh (audits) | QA sheet; audit logs; cross-check output. | CP9 | 2 Oct |
| **9 · GCP deployment** | Database restored, `data/accounts/` copied and sha256-verified, backend up, five accounts smoke-tested, frontend pointed at GCP. | Yogesh | Manifest verification log; widget-count parity local vs GCP. | CP10 | access + 1 day |
| **10 · Handover** | Contacts loaded when they arrive and the five contact features rerun; rules doc v2 and handover doc refreshed; missing-files list reduced to client-owed items; client walkthrough done. | Manisha (docs, client), Yogesh (reruns) | `MISSING_FILES.md`; ledger rerun rows; sent email. | — | contacts + 2 days |

CP2, CP3 and CP4 are one action (the split rerun) and are listed separately only so that each has its own evidence.

---

## 4. The 220-account split process

### What each account folder must hold before ingestion

Every folder already has the same 25 slots; the question is which must carry rows.

| Tier | Datasets | Rule |
|---|---|---|
| **A · Required** | `firmographics` (Company Name and Company Domain populated; domain = audit sheet col D); `_account.json` with `name_for_upload` = audit col B | The account does not enter the pipeline without these. Extractors take the account's identity from firmographics, not from the account record. |
| **B · Expected** | `technographics` or `webstack` or `technology_detections`; `google_news` or `news_events`; `hp_category_intent`; `job_openings`; `intent_score` + `intent_topics`; `company_hierarchy` | Load without them, but the ledger marks the account "thin" and names what is absent. Each absence degrades a known feature (table below). |
| **C · Optional** | `subsidiaries`, `funding`, `workforce_trends`, `company_ratings`, `website_traffic`, `social_media`, `company`, `extended_company`, `news_events_additional`, `connections`, `subpages`, `similar_companies` | No feature declares them, so uploading triggers no regeneration. Upload when they have rows (cheap, keeps the account complete for later features); skip when empty. |
| **D · Source-wide gaps** | `prospect_contacts`, `compliance_filings` | Never upload a header-only file: a registered empty dataset makes the extractor work from nothing, whereas an unregistered one degrades cleanly. Fill later and rerun the dependent features only. |

### What a missing dataset does

| Missing | Accounts | Effect |
|---|---|---|
| `prospect_contacts` | 219 | Stakeholder Map empty; Objection Playbook falls back to function names; Content Studio and Message Evaluator use job-title proxies; Executive Dashboard has no contact count. |
| `compliance_filings` | 220 | No filings-sourced financials on the Executive Dashboard; no filings evidence in Live Signals, Opportunity Map, Strategy Chat, Content Messaging. |
| `job_openings` | 44 | Hiring velocity and urgency driver 3 are zero; Intent & Demand loses hiring demand; Message Evaluator has no persona at all when contacts are also missing (44 accounts). |
| `intent_score` / `intent_topics` | 47 | Intent & Demand shows the category score only, no supporting signals; Stakeholder and Opportunity lose the intent input. |
| `hp_category_intent` | 2 | No category score; Intent & Demand cannot pick a primary category. |
| `technographics` | 13 | Technographic Map runs on webstack + tech detections only (client-approved fallback). |
| `company_hierarchy` | 55 | No parent shown (client: show nothing when absent). |

### Pre-ingestion checklist for one account (the loader runs it and refuses on any failure)

1. `_account.json.name_for_upload` equals the audit sheet Column B for this domain (Astra: exempt).
2. `firmographics.csv` has one data row; Company Name and Company Domain non-blank; domain equals audit Column D.
3. The upload plan lists only files with ≥ 1 data row (`--print-upload-plan`); no header-only file is in it.
4. Every file in the plan has the row count `_manifest.json` recorded for it.
5. Every file opens with `utf-8-sig`; `hp_category_intent.csv` keeps its two header rows.
6. No dataset file in this folder carries rows keyed to another account's domain (shared-domain accounts Jabil SG and MUFG Bangkok are expected to be sparse, not to carry the other entity's rows).
7. The account name does not already exist in the target database (or the ledger says it is a deliberate reload after `delete_account.py`).
8. The split-level validator run that produced this folder had 0 FAIL.

### Post-processing checklist for one account

1. `accounts` has the record; `account_data_files` active count equals the upload plan count.
2. Every one of the 11 features has a stored widget record; status is `ok`, `empty` or `pending`, never `failed`; the backend log has no extractor traceback for this account id.
3. Executive Dashboard header name equals `name_for_upload`.
4. Intent & Demand primary category equals the highest category-file score that does not rest on a noisy keyword (the 11 Sep rule).
5. Tech Map header reads "N found, M map to HP categories" and M equals the number of vendors on the category cards.
6. Live Signals cards carry a date and a publisher; no 1970-01-01 dates.
7. No seed numbers leaked (Strategy Chat "Grounded in" line shows `unavailable_counts`, not 10 / 23 / 149 / 220).
8. `audit_grounding.py` exits 0 for the sample accounts; no vendor names in rendered strings.

### How this scales to 220 without discovering a problem on account 200

- **The loader enforces the pre-checks**, so bad folders never reach the API.
- **Waves:** 1 account → 5 accounts (the diverse set in Y4) → one batch of 20 → batches of 50. Each wave passes the post-processing checklist and a 10 % QA sample before the next starts.
- **Stop-on-fail:** any `failed` feature or pre-check failure halts the batch; the ledger says exactly where.
- **Fixed, alphabetical batch order and idempotent runs**, so a restart continues rather than duplicates.
- **Two passes:** pass 1 deterministic on all 220 first (cheap, fast, catches data problems); pass 2 LLM only after Y6 and after the wave-1 cost measurement.
- **One rerun path:** `delete_account.py` then reload from the folder. Never patch a stored widget by hand.

---

## 5. The latest PredictLeads update

**What it actually is.** The 25 Sep item is `PredictLeads_219_Account_Domain_Audit.xlsx`, a reconciliation sheet, not a new data workbook. The PredictLeads data itself (`predictleads_combined_219_accounts.xlsx`, hiring added 18 Sep) is unchanged and is already what the split reads.

| Question | Finding |
|---|---|
| What is new | Sheet "219 Account Audit" only (per Dhruvi's second email): 219 rows, Domain Check = MATCH on all 219, Column H "OK" ×204, "consider both names same" ×13, blank ×2. Column B is the dashboard display name. |
| Relevant sheets | "219 Account Audit". Ignore "Problems Only" and "Summary" (client instruction). In the data workbook, keep using company, extended_company, job_openings, technology_detections, news_events, connections, subpages, similar_companies; sec_filings and products stay in `reference/` until the client's Products feature list arrives; dataset_status, review_records, quality_changes, differences, comparison are QA records, never loaded (client answer E5). |
| Features that use it | Everything, indirectly: the domain is the join key for every dataset and every account. Column B drives the header on all 11 features. |
| What must be replaced | Three split domains (Posco, Pilipinas Shell, Public Bank). Public Bank gains 268 PredictLeads rows it has none of today (the "Public Bank Lao Limited" row is accepted by the client). Posco and Shell keep the rows they already have. The interim alias table in the split is retired; the sheet is the domain source. |
| What must be merged | Nothing new. The 13 "consider both names same" rows need no data change (we key on domain); they matter only so the validator's cross-source name check does not flag them. |
| What to ignore | The two other sheets; vendor company names as display names. |
| Does it change the split structure | No. Folder names, slugs and `name_for_upload` are unchanged (all 219 names already match). Only three `_account.json` domains, `_ACCOUNTS.csv` and the three folders' domain-keyed datasets change. |
| Before or in parallel | Before ingestion for the three affected accounts; for the other 217 nothing changes, so ingestion can start the moment the rerun finishes (about an hour). |
| Regenerate existing accounts | No account of the 220 has been processed anywhere, so nothing to regenerate. The live Astra is unaffected (not in the sheet). Astra_Step73 is out of scope. |

**Not automatically authoritative, checked:** the sheet agrees with the master list on all 219 names, agrees with the split on 216 of 219 accounts' domains, and the three differences are exactly the ones the client had already answered in writing (DEC-055). It is safe to adopt as the domain source. One caveat stays open: Jabil SG and MUFG Bangkok still share a domain with their siblings, and the sheet does not solve that; only the promised Name + Country columns do.

---

## 6. Documentation priority

### MUST DO NOW (about two hours, in parallel with the split rerun)

1. **Run contract** (one page): identity rule, upload rule, pass 1 / pass 2, ledger, stop rules.
2. **Three decision-log entries** for the choices this plan makes: two-pass load, local database for the run, account name = territory name = Column B. Via `build_docs.py`, not by hand.
3. **Code-gap register**: the table in §0, so that a wrong output can be traced to "decided, not yet in code" in one lookup.
4. `_DATASET_USAGE.md`, `_CORRECTIONS.txt`, `_READINESS.csv`: regenerated automatically by the split rerun; nothing to write.

### DO IN PARALLEL (Manisha, ongoing, never blocking a batch)

- Log each client answer the day it arrives (`build_questions.py`), including defaults we stated.
- Per-feature QA checklists (M5), written from `03_Feature_and_Logic/`.
- Rules doc v2 after Y6.
- Filings and contacts source READMEs updated when those files land.

### CAN WAIT UNTIL AFTER THE 220 ARE PROCESSED

- Retrieving superseded and reference files (`MISSING_FILES.md` §B).
- Email archive polish, `MASTER_DOCUMENT_INDEX.md` cosmetics, extraction notes.
- Handover docx refresh (CP10).
- Wiki or GitBook publication.

### Minimum source of truth while processing

1. `02_Decision_Maker/DECISION_MAKER_REGISTER.md` and the 15 documents it lists (what the client decided).
2. `00_INDEX/DECISION_LOG.md` (why the code does what it does).
3. `220 account split csv/_DATASET_USAGE.md`, `_CORRECTIONS.txt`, `_READINESS.csv` (what data each account has and where it feeds).
4. `04_Data_and_Source_Definitions/*/README.md` (what each source is and its known defects).
5. `06_Unresolved_and_Open/README.md` (what is still open and which feature it affects).
6. The run contract and the run ledger (what happened to each account).

Anything not in this list is not needed to diagnose a failed account.

---

## 7. Blockers

### HARD BLOCKERS (the final deliverable cannot be complete without them)

| Blocker | Why it is hard | What it blocks | Owner |
|---|---|---|---|
| Contact file (Apollo, one file) | 0 of 220 accounts have contacts; five features have no primary input. No substitute exists in any source we hold. | Stakeholder Map, Opportunity Map contacts, Objection Playbook topic owners, Content Studio and Message Evaluator personas, on 219 accounts. | Client (Konika); Manisha chases |
| GCP access, project id, region | Render has no persistent disk; the 220 uploads cannot be hosted there. There is no other target. | CP9, CP10. | Sahaj; Manisha chases |
| Relevance change (Y6) before pass 2 | Self-imposed but real: running the Opportunity Map LLM pass before DEC-053 lands means paying for 220 regenerations twice. | Pass 2 only. Pass 1 is unaffected. | Yogesh |

### SOFT BLOCKERS (risk or degraded output; processing continues)

| Item | Effect if unresolved | Default we proceed with |
|---|---|---|
| Split keeps RSS over Exa on duplicates | Live Signals shows the RSS variant (DEC-054a violated). | Fix in Y1 today. |
| Display name, vendor labels, empty-state text in the UI | Every account visibly violates DEC-052 / 054b / 054c. | Fix in M2 before CP8; does not block loading. |
| Filings PDFs 0 / 220 | Financials evidence absent from the Executive Dashboard; filings evidence absent from four features. | Get Pritesh's 474 files (M4); rerun the five dependent features on affected accounts. |
| Job rows for 45 accounts | Urgency driver 3 = 0; Message Evaluator has nothing on 44 accounts. | Load as is; rerun on arrival. |
| Name + Country columns on PredictLeads rows | Jabil SG and MUFG Bangkok get almost no domain-keyed data. | Load sparse; rerun on arrival. |
| Exa event dates blank on 29 % of rows, three 1970-01-01 | Undated stories cannot be scored for recency. | Treat blank and epoch as absent; rerun on re-crawl. |
| Products and sec_filings sheets not consumed | Recommendations miss the client's "mainly for recommendation purposes" input. | Feature increment after the client sends the list (M1). |
| Nine vendor-flagged rows | Four wrong-employer postings become hiring signals. | Drop them (stated default in M1). |
| Retrieval index cost per account unknown | Pass 2 budget unknown. | Measure on wave 1 before deciding scope. |
| Rulebook FINAL docx not on disk | Documentation only; the parsed rules (v5) are in the database. | M7, low priority. |

### NOT BLOCKING

MISSING_FILES §B (superseded files); QA validator false failures; Astra_Step73; Render deployment; case-study depth constants; the 22 Sep client UI test observations (fold into CP8 QA); Strategy Chat Step 8 RAG; HP-Account-Intelligence-Rules.docx feedback (we update it after Y6 regardless).

---

## 8. Local-first strategy, made concrete

```
Local (this machine)
  Docker Mongo (hp_account_db) + cloned reference collections   ← Y2
  backend from hp-backend/ with OPENAI_API_KEY blank            ← pass 1
  ↓
Split corrected and validated (Y1)                              ← CP2–4
  ↓
Loader: pre-checks → create account → upload rows-only files → ledger (Y3)
  wave 1 (5) → 20 → 50 → 50 → 50 → 45                            ← CP5, CP7 pass 1
  ↓
Fix extractor failures; merge M2 UI fixes and Y6 relevance      ← CP6
  ↓
Pass 2 with the key: regenerate 4 LLM features once; rebuild retrieval index (Y7)
  ↓
Validate outputs: QA sample, grounding audit, readiness cross-check   ← CP8
  ↓
GCP access arrives
  ↓
Restore database (migrate_to_atlas.py --target <gcp>) BEFORE first backend start
Copy data/accounts/ to a persistent disk at the same relative path; verify sha256 manifest
Start backend; smoke-test 5 accounts; point frontend at GCP       ← CP9
  ↓
Contacts arrive → rerun the 5 contact features only → handover   ← CP10
```

**Why local Mongo, not the shared cluster:** the shared cluster is what the Render site reads. Loading 220 accounts into it would list them on the live site with files that exist only on this machine, and every mistake during the run would be visible there. The four reference collections are a one-time copy.

**What moves to GCP:** the `hp_account_db` database (accounts, files, widgets, retrieval collections, reference collections); the `hp-backend/data/accounts/` tree at the same relative path (file paths in the database are relative and resolved through `find_file_path`); the `.env`; the vector collections. Nothing is regenerated on GCP; it serves what local produced.

**What can be prepared before access:** the checklist, the manifest script, the storage decision, the env list, a local Docker build of the backend image. The only inputs from Sahaj are the project id, the region, and who provisions Mongo.

---

## Decisions this plan takes, for the record

- **DEC-056 (proposed):** two-pass load; pass 1 deterministic with the key unset, pass 2 LLM and retrieval once per account after the relevance change.
- **DEC-057 (proposed):** the 220 run uses the local Docker Mongo with the four reference collections cloned from the shared cluster; the shared cluster is not touched until GCP.
- **DEC-058 (proposed):** account name in the platform = Sales Territory Name = audit sheet Column B; the dashboard header reads it from the account record, not from firmographics.
- **Assumption to confirm with Manisha:** she owns the frontend conformance changes (M2). If not, M2 moves to Yogesh after Y5 and CP8 slips by a day.
