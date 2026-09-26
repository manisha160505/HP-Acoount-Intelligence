# Data Readiness Report: HP 220-Account Intelligence

| | |
|---|---|
| **Report date** | 26 September 2026 (supersedes the 25 Sep audit, which was this same file under the name `DATA_READINESS_AUDIT_220_2026-09-25.md` and is kept in git history) |
| **Data snapshot** | Split output `220 account split csv/`, run 26 Sep 04:42 UTC (`_RUN_SUMMARY.json`) · filings download 26 Sep 05:09 UTC (`_filings_download_summary.json`) · backend extractors at commit `83d14a9c` (no backend change since 25 Sep 18:18 IST) |
| **Source files in the snapshot** | Explorium `explorium_clean_220` (23 Sep) · PredictLeads `predictleads_combined_219_accounts_company_country.xlsm` (C46–C48, 25 Sep) · Exa `exa_data (3)_2025-2026.xlsx` and Google News RSS `google_news_rss_data 2 (2)_2025-2026.xlsx` (re-dated, last 12 months) · `hp_intent_results 2.xlsx` + `NSW_Education_Public_Intent.xlsx` · `Apollo_All_Contacts (1).xlsx` (C49, 26 Sep) · `filings 1.csv` + `filings_client_supplement_2026-09-26.csv` · `PredictLeads_219_Account_Domain_Audit.xlsx` (canonical domains) |
| **Total accounts** | **220** (all 220 matched to the master list; 219 to the domain audit, with Astra absent by design) |
| **Companion file** | `DATA_READINESS_MATRIX_220.csv` (same folder, gitignored): one row per account with its dataset counts and 11 feature statuses. The 25 Sep matrix `DATA_READINESS_MATRIX_220_2026-09-25.csv` is superseded. |

**Internal document. Nothing here is client-approved.**

---

## 0. Overall readiness

| Measure | 26 Sep | 25 Sep baseline |
|---|---:|---:|
| Feature × account cells **Ready** (11 × 220 = 2,420) | **1,927 (79.6%)** | 1,561 (64.5%) |
| Cells **Partially ready** (the feature runs; a section is left empty per DEC-054b) | 418 (17.3%) | 549 (22.7%) |
| Cells **Blocked** (no main output, or the output would be misleading) | **75 (3.1%)** | 310 (12.8%) |
| Accounts ready on all 11 features | **80** | 1 (Astra seed) |
| Accounts with no blocked feature | **182** | 1 |
| Accounts with at least one blocked feature | 38 | 219 |

**Verdict.** Every one of the 220 accounts has enough data to load. The remaining limits sit in three layers:

1. **Environment.** GCP access and the project id (D42) block loading all 220 at once. This applies to every account, whatever its data.
2. **Our own fixes**, to make before loading. There are 3 domain conflicts in the split and 4 extractor defects that publish misleading output (§4B).
3. **Data from the client.** Only the contacts for 28 accounts (Stakeholder Map) and job postings for 42 accounts are still expected. Every other gap is a genuine no-data case the vendors cannot fill.

Once the §4B fixes are in, the only blocked cells that are not honest empty states are 28 Stakeholder Map accounts waiting on the client's "few more details".

**What changed since 25 Sep:**
- **Apollo contacts arrived:** 192 accounts, up from 1.
- **Filing PDFs:** 344 PDFs in 139 accounts, up from 0.
- **News files re-dated:** the Exa and RSS files are dated and cut to 12 months, so no undated rows remain.
- **PredictLeads now carries company and country.** Jabil SG and MUFG Bangkok now get their own news, jobs and technology rows.
- **NSW Education intent file received.** Its category scores now attach.
- **Two split fixes:** Exa is kept over RSS on duplicate stories, and the filings re-keys are applied.

Counts are not all like-for-like with the baseline. Where the Ready rule was tightened because new data made it possible (contacts, PDFs), §2 says so.

---

## 1. How the numbers were produced

Every CSV in every folder was read, then each account was classified per feature. The rules come from the 25 Sep extractor trace; on 26 Sep the code was re-checked for the rules that decide the counts (the intent domain match, the news date gate, the contact fields, the Tech Map and Message Evaluator empty paths).

- **Ready**: every dataset the extractor reads for the feature's main and supporting widgets has usable rows, and no known defect distorts the output.
- **Partially ready**: the main widget is produced, but a supporting input is missing, so that section is left out (DEC-054b empty state) or falls back to a designed default.
- **Blocked**: the main widget cannot be produced, or the feature would publish something wrong for that account.

"Usable" applies the extractor's own filters:
- News rows must be dated and fall within the last 365 days, not in the future.
- The category-intent row must match the account's runtime domain, which is the firmographics Company Domain, falling back to Website.
- Technographics must have a non-blank Full Tech Stack.

---

## 2. Readiness by feature (220 accounts)

| # | Feature | Ready | Partially ready | Blocked | Required data (role) | Main missing / issue |
|---|---|---:|---:|---:|---|---|
| 1 | Executive Dashboard | **168** | 52 | 0 | firmographics (core); job_openings, prospect_contacts (supporting) | 42 accounts have no job postings and 28 no contacts (18 lack both). With no contacts the stakeholder count shows **0**, not "not available" (defect B6). |
| 2 | Recent News Signals | **205** | 15 | 0 | google_news (Exa + RSS) and news_events (PredictLeads); either one is enough to run | 14 accounts have only one feed within 12 months. KT Corp: all 100 PredictLeads summaries name "Keysight Technologies, Inc." although the events and jobs are KT's (e.g. "KT NPU LLM Station"), so it counts as Exa/RSS only. 299 PredictLeads rows with a future effective_date are rejected by the date gate. |
| 3 | Intent & Demand Signals | **157** | 60 | **3** | hp_category_intent (core), intent_score + intent_topics (Bombora), firmographics domain | Partial: 44 have a category score but no Bombora data (genuine no-data); 5 have Bombora but no category score (NSW Health, Shiseido, Supreme Court PH are "Unavailable"; Jabil SG and MUFG Bangkok have no row); 11 more lose every Bombora topic to the website-mismatch rule (B3). **Blocked: Posco, Pilipinas Shell, Public Bank.** The firmographics domain differs from the canonical domain, so the category row never attaches, and none of the three has Bombora data (B1). |
| 4 | Solution Narrative / Opportunity Map | **177** | 43 | 0 | news (core); prospect_contacts, technographics, intent (supporting) | 28 without contacts (target buyers show "no_match"), 18 without a tech stack, 3 without any intent (the three overlap). |
| 5 | Stakeholder Map | **176** | 16 | **28** | prospect_contacts (required) | **28 accounts have no contacts** (list in §4A). 16 are thin, with 1–2 contacts each. Apollo supplies no buying-committee persona, so influence is inferred from title. 745 of 2,306 contacts have no email. Astra counts as ready on its 23-contact pilot seed, pending decision INT-11. |
| 6 | Technographic Map | **201** | 6 | **13** | technographics Full Tech Stack (core); webstack, technology_detections (supporting) | **13 accounts have no technographics**, yet the map would publish "available" with 0 detected and still flag PC/Print whitespace as opportunities (B4). Partial: 5 have a blank Full Tech Stack (BNZ, Honda, Krung Thai, OCBC, Toppan) and Posco has no website technologies. 94.8% of technology_detections rows carry no technology name (vendor). |
| 7 | Objection Playbook | **183** | 24 | **13** | technographics (core); prospect_contacts (supporting, for "Could be raised by") | The same 13 no-technographics accounts; their cards show the false notice "requires OPENAI_API_KEY" (B5). Partial: 24 without contacts, where the raiser falls back to the contest-area name (by design). |
| 8 | Content Messaging | **161** | 59 | 0 | firmographics, technographics, intent_score, google_news (any one is enough to run) | 47 without Bombora, 18 without a tech stack, 2 without Exa/RSS. PredictLeads news_events contributes nothing on any account, because the extractor reads the wrong column names (B7). |
| 9 | Content Studio | **168** | 52 | 0 | job_openings, prospect_contacts, firmographics | Missing jobs means no role personas; missing contacts means no named personas. **All 220 are at risk from B8**: a hard-coded Windows path means every dataset reads as absent unless the process runs from `hp-backend/` or `/app`. |
| 10 | Strategy Chat | **139** | 81 | 0 | the 7 upstream widgets + filing PDFs (retrieval index) | 81 accounts have no PDF: 48 have indexed filings that could not be fetched by script, and 33 have no indexed filing at all. The chat still runs on widget data. |
| 11 | Message Evaluator | **192** | 10 | **18** | prospect_contacts (core); job_openings (fallback role personas) | Partial: 10 have no contacts but have jobs, so they get role personas. **Blocked: 18 have neither.** The extractor publishes "available" with 0 personas (B6). |
| | **Total cells** | **1,927** | **418** | **75** | | |

**Changes against the 25 Sep baseline, and why**

| Feature | 25 Sep R / P / B | 26 Sep R / P / B | Main reason |
|---|---|---|---|
| Executive Dashboard | 176 / 44 / 0 | 168 / 52 / 0 | Ready now also requires contacts; +2 accounts with jobs |
| Recent News Signals | 215 / 3 / 2 | 205 / 15 / 0 | Shared-domain accounts now have PredictLeads news; the 12-month window leaves 14 accounts with one feed; KT's naming defect |
| Intent & Demand | 157 / 46 / 0 (+17 misleading) | 157 / 60 / 3 | Topic-mismatch accounts are now counted as Partial (topics withheld, not misstated); NSW Education attached; Public Bank's domain now conflicts |
| Opportunity Map | 1 / 217 / 2 | 177 / 43 / 0 | Contacts |
| Stakeholder Map | 1 / 0 / 219 | 176 / 16 / 28 | Contacts |
| Technographic Map | 201 / 6 / 0 (+13 misleading) | 201 / 6 / 13 | No change in data; misleading output now counted as Blocked |
| Objection Playbook | 207 / 0 / 13 | 183 / 24 / 13 | Ready now also requires contacts (raiser) |
| Content Messaging | 206 / 14 / 0 | 161 / 59 / 0 | Ready now requires all four inputs, Bombora included (definition tightened) |
| Content Studio | 176 / 44 / 0 | 168 / 52 / 0 | Ready now also requires contacts |
| Strategy Chat | 220 / 0 / 0 | 139 / 81 / 0 | Ready now requires filing PDFs, which exist for the first time (definition tightened) |
| Message Evaluator | 1 / 175 / 44 | 192 / 10 / 18 | Contacts |

---

## 3. Readiness by dataset

| Dataset | Source | Accounts with data | Empty | Rows | Change since 25 Sep | Remaining issue | Gap type |
|---|---|---:|---:|---:|---|---|---|
| firmographics | Explorium | 220 | 0 | 220 | — | 6 without Business Description. **Domain ≠ canonical domain: Posco (posco-inc.com vs posco.com), Pilipinas Shell (pilipinas.shell.com.ph vs shell.com.ph), Public Bank (Website publicbankgroup.com vs pbebank.com; Company Domain blank)** | 6 accepted; 3 our fix (B1) |
| company_hierarchy | Explorium | 165 | 55 | 165 | — | Parent name present for only 28; ultimate parent always present | Accepted no-data (DEC-018) |
| technographics | Explorium | 207 (202 with a stack) | 13 | 207 | — | 5 with a blank Full Tech Stack | Accepted no-data, but needs the code guard B4/B5 |
| webstack | Explorium | 219 (214 with site technologies) | 1 | 219 | — | — | Accepted |
| technology_detections | PredictLeads | 219 | 1 | 17,903 | Country attribution applied | 94.8% of rows have no technology name (vendor never shipped the object) | Vendor; accepted |
| hp_category_intent | HP intent file + NSW Education file | 218 rows, **212 attach with scores** | 2 | 220 | **NSW Education now scored** | 3 "Unavailable" (NSW Health, Shiseido, Supreme Court PH); 3 do not attach (B1); Jabil SG and MUFG Bangkok have no row (shared domain) | 5 accepted; 3 our fix |
| intent_score (Bombora) | Explorium | 173 | 47 | 116,076 | — | — | Accepted no-data |
| intent_topics (Bombora) | Explorium | 173 | 47 | 173 | — | Level Of Intent and Topic Count blank in all rows; **15 accounts' Company Website differs from the account domain, so all their topics are dropped** | Vendor field gap accepted; mismatch is our fix (B3) |
| prospect_contacts | **Apollo (C49, 26 Sep)** + Astra seed | **192** | 28 | 2,306 | **New: was 1 account** | 745 contacts without an email (6 withheld because the email names someone else); 197 review flags (130 listed under a sister account, 54 off-domain emails, 5 phone, 1 team name, 1 unmatched); 16 accounts have 1–2 contacts; no persona column | 28 pending client ("few more details"); Astra pending INT-11 |
| job_openings | PredictLeads | 178 | 42 | 15,179 | +2 accounts (Jabil SG, MUFG Bangkok) | Status blank on 54.6% of postings (12 accounts entirely), shown as "postings seen" | 42 pending client/vendors (client counts 43); 27 of the 42 have Explorium hiring events in `reference/`, which has no dataset key (B10) |
| google_news (Exa + RSS) | Exa, Google News RSS | 218 | 2 | 5,756 | **Re-dated 12-month files; every row dated; Exa kept on duplicates** | Jabil SG and MUFG Bangkok have none (their news is PredictLeads) | Accepted |
| news_events | PredictLeads | 216 (208 inside the 12-month gate) | 4 | 14,333 (6,623 inside the gate) | Company and country on every row | 299 future-dated rows rejected (B9); **KT Corp's 100 summaries name Keysight** | Vendor; clarification C6 |
| compliance_filings (PDFs) | `filings 1.csv` + client supplement; self-downloaded | **139 (344 PDFs)**; 185 indexed | 81 without a PDF | 511 index rows | **New: was 0** | 116 fetches failed for structural reasons (sec.gov HTML, DART/PSE Edge viewer pages, bot-blocked IR sites) + 30 rows with no URL; 27 index rows unassigned; VPBank's 2 rows still held under Vietnam Post; **no extractor reads PDFs** (Strategy Chat retrieval only, B2) | Access (client Drive folder); VPBank ruling C4 |
| Case studies (global) | HP | global | — | 384 (89 cleaned, in Atlas only) | — | route blank on 78; no publish dates | Accepted |

Twelve other tables are produced by the split but read by no feature: subsidiaries, funding, workforce, ratings, traffic, social, company/extended_company, connections, subpages, similar companies, Explorium news events. The 13 reference tables have no dataset key. None of these affects readiness.

---

## 4. Remaining gaps: acceptable versus blocking

### A. Blocking, waiting on the client

| Gap | Accounts | Feature impact | Status |
|---|---:|---|---|
| Contacts | 28: Air NZ, ANZ NZ, Central Japan Railway, Coles, Coupang, Hanjin, IAG NZ, Japan Post, JFE, Kansai Electric, Kawasaki Heavy, Lotte, Mazda, Meiji, MoD MY, MoD VN, MoD TH, MoF VN, NIS Korea, Nippon Express, NTT, Pilipinas Shell, Pioneer, Public Bank, Toyota Group, T&D, Vietnam Post, Yamato | Stakeholder Map blocked on 28 (Message Evaluator on the 18 that also lack jobs) | Client (26 Sep): "will comeback with few more details". If they confirm there are none, these become acceptable no-data. |
| Job postings | 42 | Degrades the Executive Dashboard hiring view, Content Studio personas, Message Evaluator fallback, and Intent hiring demand | Client: "final hiring dataset for now"; vendors asked. Not blocking on its own. |

### B. Blocking, our fixes (make before loading)

| # | Defect | Accounts | Fix |
|---|---|---:|---|
| B1 | Runtime domain comes from firmographics, not the canonical domain | 3 (Posco, Pilipinas Shell, Public Bank) | Write the audit domain into `firmographics.Company Domain` at split time, or populate `accounts.domain` on load |
| B2 | `compliance_filings` is declared by 5 features but read by no extractor | 220 (reporting only) | Remove it from those features' FEATURE_MAPPINGS or read it; today the readiness files mislabel it as missing |
| B3 | The intent-topics mismatch rule drops every Bombora topic when `Company Website` is a vendor variant | 15 | Apply the split's domain aliases before comparing |
| B4 | Technographic Map with no technographics publishes "available" plus false whitespace opportunities | 13 | Publish the empty state when technographics has no rows |
| B5 | Objection Playbook with no technographics shows "requires OPENAI_API_KEY" | 13 | Correct the notice to "no technographic data" |
| B6 | Empty-state handling: Message Evaluator publishes "available" with 0 personas; the Executive Dashboard shows 0 stakeholders | 18 / 28 | Publish the empty state |
| B7 | Content Messaging and Content Studio read news_events with google_news column names | 220 | Map `summary`/`effective_date`/`found_at` |
| B8 | Content Studio's own CSV reader has a hard-coded Windows path | 220 | Use `datasets.read_dataset_records` |
| B9 | The news gate uses `effective_date` before `found_at`, so a future effective_date loses the row | 299 rows | Fall back to `found_at` when effective_date is in the future |
| B10 | Explorium hiring events and PredictLeads products/sec_filings have no dataset key | 27 of the 42 no-jobs accounts could be filled | Optional: add keys |
| B11 | Every upload regenerates dependents synchronously (about 41 runs per account) | 220 | Regenerate once per account before bulk load (DEC-056, proposed) |

B2 and B4–B9 were re-confirmed in the code on 26 Sep. B10 and B11 are carried from the 25 Sep trace; no backend change since. The 25 Sep items fixed since the baseline are: RSS kept over Exa (fixed, Exa now stacked first) and the filings re-keys for Fletcher, Fonterra, FIF and Mandiri (applied).

### C. Acceptable no-data (the feature degrades cleanly; nothing to chase)

| Gap | Accounts |
|---|---:|
| Bombora intent (intent_score + intent_topics) | 47 |
| Category intent "Unavailable" (3) or no row for a shared-domain secondary (2) | 5 |
| Technographics (after the B4/B5 guard) | 13 |
| Full Tech Stack blank | 5 |
| Company hierarchy / parent name | 55 / 192 |
| Business Description | 6 |
| Exa/RSS news for Jabil SG and MUFG Bangkok (they have PredictLeads news) | 2 |
| Technology names in technology_detections | 94.8% of rows |
| Level Of Intent / Topic Count | all 173 rows |
| Job status blank, shown as "postings seen" | 54.6% of postings |
| Filings with no indexed document | 33, but see C4 |
| Filings that scripts cannot fetch (sec.gov, DART, PSE Edge, 403) | 116 documents; only the client's Drive folder would fill these |

### Accounts to hold at load time (18)

| Accounts | Reason | Lifted by |
|---|---|---|
| Posco, Pilipinas Shell, Public Bank | Domain conflict | B1 |
| Alps Alpine, Coupang, Fujitsu, Johor Corp, MoD MY, MoD VN, MND Korea, MPS Vietnam, MUFG, Panasonic, Sagility PH, MUFG Bangkok, Toyota Group | No technographics | B4 + B5, or load with Tech Map and Objection suppressed |
| KT Corp | PredictLeads news text names Keysight | Suppress news_events for KT, or clarification C6 |
| PT Astra International | Seed-schema data; a live Astra account exists | Decision INT-11 (seed vs Apollo) |

Jabil SG, which was on the 25 Sep hold list, comes off: the country attribution now gives it its own news, jobs and technology rows.

---

## 5. Client clarifications still required

Data-affecting items come first. The UI and wording items are listed because they are still open, but they do not change readiness counts.

| # | Id | Question | Affects | Blocking? |
|---|---|---|---|---|
| C1 | D42 | GCP project id and region (the client has asked what we mean by "project ID") | Loading all 220 | **Yes: whole project** |
| C2 | D8 | Which of the 28 contact-less accounts the "few more details" will cover, and when | Stakeholder Map on 28 | Yes for those 28 |
| C3 | D22 | Which 43 accounts the job vendors are chasing (we count 42) | 5 features, degraded | No |
| C4 | D11 | Agribank and VPBank filings; re-key VPBank out of Vietnam Post. The listed firms BCA, BRI, OCBC, UOB SG and Sinar Mas have no indexed filing: are they index gaps, or on the client's no-filings list? | Strategy Chat | No |
| C5 | D3 | Shared domains: the vendor now attributes most rows to the second entity (Jabil SG 200 jobs vs Jabil MY 100; MUFG Bangkok 114 vs MUFG Japan 14). Confirm this is intended. | News, hiring, Tech Map for 4 accounts | No |
| C6 | new | KT Corp: PredictLeads news summaries say "Keysight Technologies, Inc." for KT's own events. Suppress, relabel, or have the vendor re-issue? | News for 1 account | No |
| C7 | D27 | Does a blank job status mean open or unknown, and what label? | Hiring views | No |
| C8 | D25 | 9 vendor-flagged doubtful rows: drop them? | 9 rows | No |
| C9 | D35 | Confidence tiers T0–T3 (client asked "which feature?") | Every signal | No |
| C10 | E23-3 | The "Contextual — no direct HP line" tag | Tech Map | No |
| C11 | E23-4 / D38 | Which features use the PredictLeads products sheet; seat-proxy thresholds and lifecycle columns | Opportunity Map, services rules | No |
| C12 | RULES, TESTS22, QA16-1…12 | Rules-doc feedback (pending since 10 Sep), the 22 Sep UI test notes, and 12 QA wording/UI points | Presentation | No |

Two internal actions sit alongside these: download the 25 Sep 12:02 UTC CLARIFICATIONS and UNRESOLVED_v2 attachments (which may already answer C4), and send the round-4 follow-up.

---

## 6. Pre-load checklist (per account)

```text
Identity       name_for_upload == audit sheet; firmographics domain == canonical domain (fails: Posco, Pilipinas Shell, Public Bank)
Hold list      not one of the 18 in section 4
Minimum data   firmographics ≥1 row; news inside 12 months ≥1 row (all 220 pass)
Upload set     only files with rows; empty placeholders are never uploaded
Validator      0 FAIL for the folder
Regeneration   regenerate-once path in place (B11) before bulk load
```

---

## Sources
- Split output `220 account split csv/` (`_RUN_SUMMARY.json` 26 Sep 04:42 UTC, `_filings_download_summary.json` 26 Sep 05:09 UTC, per-folder CSVs and `_account.json`)
- `scripts/split_account_data.py` and `scripts/fetch_filings.py` (working tree)
- `hp-backend/src/app/services/extractors/*.py` at `83d14a9c`
- `06_Unresolved_and_Open/` and `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` as of 26 Sep
- The 25 Sep audit (this file's previous version) for the extractor trace behind B10 and B11

To regenerate every count here, run `_readiness_scripts/readiness.py profile.csv` and then `_readiness_scripts/classify.py profile.csv matrix.csv`. Both need pandas, so use `hp-backend/.venv/bin/python`. The matrix CSV in this folder is the profile joined to the classification.
