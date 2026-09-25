# Data Readiness Audit — HP 220-Account Intelligence

**Date:** 25 September 2026 · **Scope:** the 220 account folders in `220 account split csv/` as regenerated 25 Sep 13:57 IST (run summary generated 08:27 UTC), the 11 feature extractors in `hp-backend/src/app/services/extractors/`, and the decision/issue registers in `project-documentation/`.
**Method:** every CSV in every folder was read and profiled column by column (blank rate, all-blank accounts, ISO dates, epoch and future dates, duplicate ids, replacement characters, HTML). Feature dependencies come from a code trace of each extractor, not from the declared list alone. Where a statement rests on code reading rather than a run, it says so.
**Companion file:** `DATA_READINESS_MATRIX_220_2026-09-25.csv` (same folder) — one row per account, every dataset status, every feature status, quality flags. The same table is reproduced in section 3.

**Internal document. Nothing here is client-approved.**

---

## 0. Headline

| | |
|---|---|
| Accounts with a folder and a valid identity (master list + audit sheet) | 220 / 220 |
| Accounts ready for the deterministic features today | 202 |
| Accounts to hold for a data-quality reason before loading | 18 |
| Accounts where every feature that does not need contacts can run with full inputs | 132 |
| Datasets no account has from the 220-account sources | contacts (219 empty), filings PDFs (220 empty) |
| Features blocked on all 219 non-Astra accounts | Stakeholder Map (fatal without contacts) |
| Features that will publish misleading output on some accounts unless fixed first | Technographic Map (13), Intent & Demand (17), Objection Playbook (13) |

The single largest finding is not a missing file. It is that five features declare `compliance_filings` as an input and **no extractor reads it**; Content Messaging reads the PredictLeads news table with the wrong column names and gets nothing from it; and the intent extractor will silently drop every Bombora topic for 15 accounts because the vendor wrote a variant website. Those are implementation gaps, listed in section 5, and they change what "ready" means more than any client delivery does.

---

## 1. Dataset inventory across the 220 folders

Every folder holds all 25 registry files (empty ones are header-only placeholders, excluded from upload by design), so "file missing" is 0 everywhere. The columns that matter are "accounts with usable rows" and the field-level gaps.

### 1a. Datasets the extractors consume

| dataset_key | accounts with rows | empty | rows | fields that are empty or thin (rows blank %, accounts entirely blank) | invalid / inconsistent values |
|---|---:|---:|---:|---|---|
| firmographics | 220 | 0 | 220 | Business Description blank in 6 accounts (2.7%); Company Domain blank in 2 (Public Bank, Westpac AU — recovered from Website); City blank in 25 (11%) | Domain in file ≠ audit canonical domain for Posco and Pilipinas Shell (see §5) |
| company_hierarchy | 165 | 55 | 165 | Parent Company Name blank 83% (137 of 165 accounts); Ultimate Parent Name always present | — |
| technographics | 207 | 13 | 207 | Full Tech Stack blank in 5 more accounts (BNZ, Honda, Krung Thai, OCBC, Toppan) → 202 usable; column "Technology" 100% blank; category columns 1–47% blank | — |
| webstack | 219 | 1 | 219 | Technologies Used By Company Website blank in 5 | Cms/Ssl/Hosting columns named in FEATURE_MAPPINGS do not exist in this sheet (they are in Explorium 5_Tech_Breakdown, now in `reference/`); the extractor does not read them either, so this is stale documentation, not a data gap |
| intent_topics | 173 | 47 | 173 | **Level Of Intent and Topic Count blank in 100% of rows, all 173 accounts** (the contract marks Level Of Intent required) | Date Stamp is `20260913` (not ISO); Company Website differs from the account domain in 15 accounts |
| intent_score | 173 | 47 | 116,076 | Topic and Composite Score fully populated | — |
| hp_category_intent | 218 | 2 | 220 | 4 accounts have Top HP Category "Unavailable" with every score blank (NSW Education, NSW Health, Shiseido, Supreme Court PH); First/Latest Intent Date blank ~50%; Geo Source blank 64% | Domain in file ≠ firmographics domain for Posco and Pilipinas Shell; two accounts (Jabil SG, MUFG Bangkok) have no row (shared domain) |
| prospect_contacts | 1 | 219 | 23 | Only the Astra seed. Within it: Email blank 35%, Mobile 70% | Seed schema (48 cols) — not the 220-account contact file, which has never arrived |
| job_openings | 176 | 44 | 15,065 | status blank 54.4% (8,198 rows), "closed" 45%, "open at retrieval" 28 rows; status blank on every row in 12 accounts; posted_at blank 36%; closed_at blank 99.9%; input_company_name / input_country_code blank 97.4% (169 accounts entirely) | 1 duplicate id; 12 cells with U+FFFD; 2 HTML fragments |
| technology_detections | 218 | 2 | 17,899 | **No technology name on 94.8% of rows** (`technology` / `technology_name` present only for the 3 official-source accounts); score blank 5.2% | 647 duplicate ids (vendor); usable columns are id, score, first/last_seen_at, department_onet_codes only |
| google_news | 218 | 2 | 16,778 | event_date blank 28.7% (4,815 rows, all from Exa); source_publisher blank 38.5%; signal_categories blank 30.7% | 3 rows dated 1970-01-01; 27 cells U+FFFD (mis-encoded Thai); 26 HTML fragments |
| news_events (PredictLeads) | 215 | 5 | 14,332 | effective_date blank 46.9% (found_at is 100% present as fallback); `event` blank 90% (summary present); location 55%, product 71%, amount 92% blank | **176 effective_date values in 2027 or later** — the extractor's date gate rejects future dates, so those rows are lost even though found_at is valid; 2 duplicate ids |
| compliance_filings | 0 | 220 | 0 PDFs | Crawl index attached for 181 accounts (476 documents with URLs); 39 accounts have no indexed filing | PDFs sit on the crawler's machine / Drive; 29 index rows unassigned (group-level entries and 2 conflicts) |

### 1b. Datasets the split produces that no extractor reads

| dataset_key | accounts with rows | note |
|---|---:|---|
| subsidiaries | 160 | 2,142 rows; not consumed |
| funding | 220 | not consumed; 4 columns >90% blank |
| workforce_trends | 215 | not consumed |
| company_ratings | 156 | not consumed |
| website_traffic | 216 | not consumed |
| social_media | 220 | 7,668 rows; not consumed |
| company / extended_company | 217 | 219 rows each, 2 duplicated domains; `extended_company` is read by the urgency score (undeclared) |
| connections | 217 | 19,583 rows; not consumed |
| subpages | 217 | 15,163 rows; 19 HTML cells, 8 duplicate ids; not consumed |
| similar_companies | 202 | not consumed |
| news_events_additional (Explorium 13_News_Events) | 168 | 819 real news events (partnerships, products, awards) with title, link and snippet — read by nothing |

### 1c. Reference tables (`reference/`, no dataset key, not uploadable)

explorium_hiring_events 194 accounts / 1,714 rows · explorium_tech_breakdown 214 · predictleads_products 128 / 2,246 · predictleads_financing_events 47 / 74 · predictleads_sec_filings 12 / 121 · explorium_funding_rounds 46 · explorium_advisors 56 · explorium_investors 39 · vendor QA sheets 2–5 accounts · predictleads_github_repositories 0.

### 1d. Global reference data (not per account)

`hp_case_studies_final.csv`: 384 rows (378 T0 first-party, 6 T2), hp_route blank on 78, publish_date empty on all; the team's cleaned set of 89 studies exists only in the shared Atlas cluster (`hp_case_studies`), alongside `hp_rulebook` (234), `hp_product_knowledge` (381) and `hp_lifecycle` (145). Local Mongo has none of these.

---

## 2. Feature → data → coverage

Classification comes from tracing each extractor: **FATAL** = the feature does not produce its main widgets; **CORE** = it publishes but the main widget is empty or a placeholder; **QUALITY** = a secondary field or count is affected; **UNUSED** = declared but never read.

| Feature | Required dataset (role) | Fields actually read | 220 coverage | Accounts lacking it | Can run without? | Blocking? |
|---|---|---|---|---:|---|---|
| Executive Dashboard | firmographics (CORE) | Company Name, Domain/Website, Business Description, Naics/Sic/LinkedIn industry, City/Region/Country, Employees Range, Revenue Range | 220 | 0 | No | Yes (none lack it) |
| | company_hierarchy (QUALITY) | Parent Company Name only | 28 with a parent name | 192 | Yes, parent shows blank | No |
| | job_openings (QUALITY) | title, normalized_title, row count | 176 | 44 | Yes, hiring velocity empty, urgency driver 0 | No |
| | prospect_contacts (QUALITY) | row count | 1 | 219 | Yes, but shows **0** not "not available" | No |
| | compliance_filings (UNUSED) | — | 0 | 220 | Extractor never reads it | No |
| | *undeclared:* technographics, webstack, hp_category_intent, extended_company, intent_score, google_news, news_events | read by the urgency score | — | — | Missing driver scores 0, card "partial" | No |
| Recent News Signals | google_news + news_events (FATAL only if both absent) | headline (event_headline→news_announcements→title; summary→article_sentence→event), date (event_date; effective_date→found_at), type/category, url, publisher, confidence | 218 / 215 | 2 have neither | No | Yes for 2 (Jabil SG, MUFG Bangkok) |
| | compliance_filings (UNUSED) | — | | | | |
| Intent & Demand Signals | hp_category_intent (CORE) | domain, top category, per-category score/trend/stage/volume/topics/keywords/technologies/dates | 214 usable (218 rows − 4 Unavailable) | 6 | Publishes topics only; primary scores None; So-What skipped | Partially |
| | intent_score (CORE) | Topic, Composite Score (exact names) | 173 | 47 | Topics table empty | Partially |
| | intent_topics (QUALITY, but FATAL when mismatched) | Company Website, Date Stamp, Level Of Intent, Topic Count | 173 | 47 | Absent → provenance null only. **Present with a different website → every topic dropped** (15 accounts) | Risk |
| | job_openings, technographics, webstack (QUALITY) | seniority/status/categories; Full Tech Stack; Technologies Used By Company Website | 176 / 202 / 214 | | Hiring-demand widget empty; no "confirmed" supporting signals | No |
| | *undeclared:* firmographics | Company Domain / Website as the account domain | 220 | 0 | Without a domain the category file never attaches | Yes in effect |
| Solution Narrative / Opportunity Map | google_news + news_events (CORE together) | headline, date, url | 218 / 215 | 2 | Trigger widget empty, plays demoted to exploratory | Partially |
| | firmographics, technographics, intent_score (QUALITY) | description/industry/size; Full Tech Stack; Topic/score | 220 / 202 / 173 | | Fewer plays eligible | No |
| | prospect_contacts (QUALITY, via the stakeholder grid widget) | — | 1 | 219 | target_buyers "no_match" | No |
| | compliance_filings (UNUSED); *undeclared:* hp_category_intent, intent_topics | | | | LLM is called with no empty-input guard | — |
| Stakeholder Map | prospect_contacts (**FATAL**) | full_name, job_title, department_main, level_main, email, phone, linkedin, personas, skills, experience, city, country | 1 | 219 | No — all three widgets empty, no LLM call | **Yes, 219 accounts** |
| | firmographics, technographics, intent_score, google_news, news_events (QUALITY) | LLM context only | | | | No |
| Technographic Map | technographics (CORE) | Full Tech Stack + 20 category columns | 202 usable | 18 | **Publishes "available" with 0 detected and still marks PC/Print cards as opportunities** | Risk, 13 accounts |
| | technology_detections (QUALITY) | id, score, first/last_seen_at, department_onet_codes — **no technology name exists** | 218 | 2 | Reference widget empty | No |
| | webstack (QUALITY) | Technologies Used By Company Website, premium count, spend, categories | 219 | 1 | Breakdown widget empty | No |
| | *undeclared:* firmographics, hp_category_intent | account name; confidence driver 2 | | | | |
| Objection Playbook | technographics (CORE) | Full Tech Stack, category and area columns | 207 | 13 | Cards "pending" with the wrong notice "requires OPENAI_API_KEY" | Yes, 13 |
| | firmographics (QUALITY); prospect_contacts (QUALITY) | context; job_title/department for the raiser | 220 / 1 | | Raiser falls back to the contest-area name (by design) | No |
| Content Messaging | firmographics, technographics, intent_score, google_news (QUALITY, any one suffices) | description; Full Tech Stack; Topic/score; headline/date/type/url | 220 | 0 | Context card empty only if all yield nothing | No |
| | news_events (**UNUSED — column mismatch**) | reads event_headline/title/event_date/source_url, which the PredictLeads table does not have | — | — | Contributes 0 triggers on every account | Implementation gap |
| | compliance_filings (UNUSED) | | | | Pillars come from the retrieval index | |
| Content Studio | job_openings (QUALITY) | normalized_title/title, seniority, categories | 176 | 44 | Role-proxy personas missing; falls back to generic archetypes | No |
| | prospect_contacts (QUALITY, via widget); firmographics (QUALITY) | | 1 / 220 | | Never empty | No |
| | *risk:* private CSV reader with a hard-coded `C:\hp-account...` path; reads nothing unless cwd is `hp-backend/` or `/app` | | | | | Implementation gap |
| Strategy Chat | none directly — reads 7 widgets; index requires exec_summary_card | | 220 | 0 | Counts show None when a dataset is absent | No |
| Message Evaluator | prospect_contacts (CORE) | full_name, job_title, department | 1 | 219 | Falls back to job-role personas | Partially |
| | job_openings (QUALITY) | normalized_title/title, seniority | 176 | 44 | **Both absent → "available" with 0 personas** | Yes, 44 accounts |

Per-account result (from the matrix):

| Feature | can run with full inputs | runs degraded | cannot run | runs but output is misleading |
|---|---:|---:|---:|---:|
| Executive Dashboard | 176 | 44 (no hiring) | 0 | 0 |
| Recent News Signals | 215 | 3 | 2 | 0 |
| Intent & Demand Signals | 157 | 46 | 0 | 17 (topic/domain mismatch) |
| Opportunity Map | 1 | 217 (no contacts) | 2 | 0 |
| Stakeholder Map | 1 | 0 | 219 | 0 |
| Technographic Map | 201 | 6 | 0 | 13 (no technographics) |
| Objection Playbook | 207 | 0 | 13 | 0 |
| Content Messaging | 206 | 14 | 0 | 0 |
| Content Studio | 176 | 44 | 0 | 0 |
| Strategy Chat | 220 | 0 | 0 | 0 |
| Message Evaluator | 1 | 175 | 44 | 0 |

---

## 3. Master readiness matrix (220 accounts)

Statuses: **COMPLETE** rows present and required fields populated · **PARTIAL** rows present but a required field ≥50% blank, or one dataset of the group missing · **EMPTY** the vendor has no rows for this account · **BLOCKED** no source exists for any account yet (contacts, filings PDFs) · **NOT REQUIRED** global reference, not per account.

Group definitions: Intent = hp_category_intent + intent_score (intent_topics is noted separately because its level and count are blank everywhere) · Technographics = technographics + webstack + technology_detections · News = google_news (RSS+Exa) + news_events (PredictLeads) · Hiring = job_openings · Other = the 12 unconsumed tables.

Feature codes: **OK** full inputs · **P** runs degraded · **NO** cannot run or nothing useful · **RISK** runs but may publish wrong output. Feature order: ED = Executive Dashboard, NS = News Signals, ID = Intent & Demand, OM = Opportunity Map, SM = Stakeholder Map, TM = Technographic Map, OP = Objection Playbook, CM = Content Messaging, CS = Content Studio, SC = Strategy Chat, ME = Message Evaluator.

Group counts: Firmographics 212 complete / 8 partial · Hierarchy 28 / 137 partial (no parent name) / 55 empty · Intent 168 / 52 partial · Technographics 201 / 19 partial · News 215 / 3 partial / 2 empty · Hiring 173 / 3 partial / 44 empty · Contacts 1 / 219 blocked · Filings 181 blocked with an index / 39 none found.

| # | Account (name for upload) | Firmo | Hierarchy | Intent | Techno | News | Hiring | Contacts | Filings | Other | ED | NS | ID | OM | SM | TM | OP | CM | CS | SC | ME | Verdict / flags |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ACCENTURE INC - PH | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 2 | ADVANTEST CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 3 | AEON CO., LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 12/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 4 | AGC INC - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 5 | AIR NEW ZEALAND LIMITED - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | READY — intent_topics website != account domain (topics dropped as mismatch) |
| 6 | ALPS ALPINE CO LTD - JP | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending; job status blank on every posting |
| 7 | ANA HOLDINGS INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 8 | ANZ HOLDINGS (NEW ZEALAND) LIMITED - NZ | PARTIAL | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 9/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — Business Description blank |
| 9 | ASAHI GROUP HOLDINGS,LTD. - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 10 | ASB HOLDINGS LIMITED - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 11 | ASIA COMMERCIAL JOINT STOCK BANK - VN | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 12 | AUSTRALIAN SUBMARINE CORPORATION [ASC] - AU | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 13 | AUSTRALIA AND NEW ZEALAND BANKING GROUP LTD - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 14 | AUSTRALIA POST - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 15 | BANCO DE ORO UNIBANK, INC. (BDO) - PH | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 16 | BANGKOK BANK PUBLIC CO LTD - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 17 | BANK FOR AGRICULTURE AND AGRICULTURAL COOPERATIVE - TH | COMPLETE | COMPLETE | PARTIAL | COMPLETE | PARTIAL | EMPTY | BLOCKED | BLOCKED 4 idx | 9/12 | P | P | P | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 18 | BANK FOR FOREIGN TRADE OF VIETNAM - VN | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 19 | BANK FOR INVESTMENT AND DEVELOPMENT OF VIETNAM - VN | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 20 | BANK ISLAM MALAYSIA BERHAD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 21 | BANK OF NEW ZEALAND - NZ | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | P | OK | OK | OK | OK | P | READY |
| 22 | BECA CARTER HOLLINGS & FERNER LTD - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 23 | BETAGRO AGRO GROUP PUBLIC COMPANY LIMITED - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 24 | BHP BILLITON - AU | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 25 | BUNNINGS GROUP LIMITED | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 26 | CANON INC. - JP | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 27 | CENTRAL JAPAN RAILWAY COMPANY - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 10/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY |
| 28 | CHAROEN POKPHAND GROUP CO LTD - TH | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 29 | CIMB GROUP HOLDINGS BERHAD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 30 | CJ GROUP - KR | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 31 | COLES GROUP - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 32 | COMMONWEALTH BANK OF AUSTRALIA - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 12/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 33 | CONCENTRIX SERVICES CORPORATION - PH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 34 | COUPANG KOREA - KR | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | P | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 35 | DAIKIN INDUSTRIES, LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 36 | DAIWA SECURITIES GROUP INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 12/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 37 | DEPARTMENT FOR EDUCATION SA - AU | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 38 | DEPARTMENT OF EDUCATION - PH | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 39 | DEPARTMENT OF EDUCATION - NSW - AU | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | PARTIAL | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 40 | DEPARTMENT OF HEALTH AND HUMAN SERVICES (VICTORIA) - AU | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 1 idx | 10/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 41 | DEPARTMENT OF NATIONAL DEFENSE - PH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 10/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 42 | DEPT OF DEFENCE - FED - AU | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 43 | DEPT OF HEALTH - NSW - AU | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | PARTIAL | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | READY — intent_topics website != account domain (topics dropped as mismatch) |
| 44 | DOWNER GROUP - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 45 | DRB-HICOM BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 46 | EAST JAPAN RAILWAY COMPANY - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 47 | ERNST&YOUNG - PH | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 48 | EXL SERVICE PHILIPPINES - PH | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 49 | FEDERAL INTERNATIONAL FINANCE, PT - ID | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 50 | FLETCHER BUILDING HOLDINGS LIMITED - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 51 | FONTERRA CO-OPERATIVE GROUP LIMITED - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 52 | FOODSTUFFS (AUCKLAND) LIMITED - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 53 | FUJIFILM HOLDINGS CORPORATION - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 54 | FUJITSU LIMITED - JP | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | RISK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — intent_topics website != account domain (topics dropped as mismatch); no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 55 | GOVERNMENT HOUSING BANK - TH | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 1 idx | 9/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 56 | GOVERNMENT SAVINGS BANK - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 1 idx | 11/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY |
| 57 | GOVERNMENT TECHNOLOGY AGENCY OF SINGAPORE - SG | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 58 | HANJIN GROUP - KR | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 4 idx | 10/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 59 | HANKOOK TIRE - KR | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 60 | HANWHA GROUP - KR | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 61 | HEALTHSCOPE - AU | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 62 | HITACHI, LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 63 | HKMC GROUP(HYUNDAI AUTOEVER) - KR | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 64 | HONDA MOTOR CO., LTD. - JP | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | P | OK | OK | OK | OK | P | READY |
| 65 | HYOSUNG GROUP - KR | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 66 | HYUNDAI HEAVY INDUSTRIES - KR | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 9/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 67 | IAG (NZ) HOLDINGS LIMITED - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 12/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 68 | IDEMITSU KOSAN CO.,LTD. - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 69 | IHI CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 70 | INDONESIA FINANCIAL GROUP - CATEGORY1 - PARTIAL - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 71 | INFINEON TECHNOLOGIES (M) SDN BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 72 | INSTITUTE OF TECHNICAL EDUCATION - SG | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 73 | INSURANCE AUSTRALIA GROUP LIMITED - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 74 | ISUZU MOTORS LIMITED - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 75 | ITOCHU CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 76 | JABIL CIRCUIT SDN BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 77 | JABIL CIRCUIT (SINGAPORE) PTE LTD - SG | COMPLETE | PARTIAL | PARTIAL | PARTIAL | EMPTY | EMPTY | BLOCKED | BLOCKED 3 idx | 7/12 | P | NO | P | NO | NO | P | OK | P | P | OK | NO | **HOLD** — shared-domain secondary: no PredictLeads/news/intent rows; Explorium hiring events available in reference/ |
| 78 | JAPAN AIRLINES CO.,LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 79 | JAPAN POST HOLDINGS CO.,LTD. - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 80 | JFE HOLDINGS, INC. - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 81 | JG SUMMIT HOLDINGS, INC. - PH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 82 | JOHOR CORPORATION - MY | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | P | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 83 | KALBE FARMA GROUP - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 84 | KANSAI ELECTRIC POWER COMPANY - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 9/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 85 | KAO CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 86 | KASIKORNBANK PUBLIC CO LTD - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 87 | KAWASAKI HEAVY INDUSTRIES LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 12/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 88 | KEMENTERIAN PERTAHANAN REPUBLIK INDONESIA - ID | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 9/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 89 | KEYSIGHT TECHNOLOGIES MALAYSIA SDN. BHD. - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 90 | KOBE STEEL, LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 91 | KONICA MINOLTA, INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 92 | KRUNG THAI BANK PUBLIC COMPANY LIMITED - TH | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 8 idx | 12/12 | OK | OK | OK | P | NO | P | OK | OK | OK | OK | P | READY |
| 93 | KT CORP. - KR | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | **HOLD** — PredictLeads identity = Keysight Technologies (wrong entity) |
| 94 | KUMPULAN WANG SIMPANAN PEKERJA - MY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 95 | KUOK (SINGAPORE) LIMITED - SG | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 96 | LEMBAGA HASIL DALAM NEGERI - MY | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 10/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY |
| 97 | LIXIL GROUP CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 98 | LOTTE GROUP - KR | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 4 idx | 9/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 99 | LOTUS S STORES THAILAND COMPANY LIMITED - TH | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 100 | MALAYAN BANKING BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 101 | MALAYSIA AIRPORTS HOLDINGS BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 102 | MARUBENI CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 103 | MAZDA MOTOR CORPORATION - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 104 | MEDIACORP PTE. LTD. - SG | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 12/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 105 | MEIJI HOLDINGS CO., LTD. - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 106 | METROPOLITAN BANK & TRUST COMY - PH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 107 | MILITARY BANK - VN | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 108 | MINISTRY OF DEFENCE - MY | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | EMPTY | BLOCKED | EMPTY | 10/12 | P | OK | P | P | NO | RISK | NO | P | P | OK | NO | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending; Explorium hiring events available in reference/ |
| 109 | MINISTRY OF DEFENCE - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 110 | MINISTRY OF DEFENCE - VN | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | EMPTY | BLOCKED | EMPTY | 9/12 | P | OK | P | P | NO | RISK | NO | P | P | OK | NO | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending; Explorium hiring events available in reference/ |
| 111 | MINISTRY OF DEFENSE - TH | PARTIAL | EMPTY | COMPLETE | COMPLETE | PARTIAL | EMPTY | BLOCKED | EMPTY | 8/12 | P | P | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Business Description blank |
| 112 | MINISTRY OF EDUCATION - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 113 | MINISTRY OF FINANCE - VN | PARTIAL | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 8/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Business Description blank |
| 114 | MINISTRY OF HEALTH - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 115 | MINISTRY OF HOME AFFAIRS - SG | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 116 | MINISTRY OF NATIONAL DEFENSE - KR | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | P | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 117 | MINISTRY OF PUBLIC SECURITY - VN | PARTIAL | EMPTY | PARTIAL | PARTIAL | COMPLETE | EMPTY | BLOCKED | EMPTY | 7/12 | P | OK | P | P | NO | RISK | NO | P | P | OK | NO | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending; Business Description blank |
| 118 | MINISTRY OF SOCIAL DEVELOPMENT - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 119 | MITRA ADHI PERKASA - ID | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 120 | MITSUBISHI CHEMICAL HOLDINGS CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 121 | MITSUBISHI ELECTRIC CORPORATION - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 122 | MITSUBISHI HEAVY INDUSTRIES, LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 123 | MITSUBISHI MOTORS CORPORATION - JP | COMPLETE | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 124 | MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP | COMPLETE | COMPLETE | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | RISK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — intent_topics website != account domain (topics dropped as mismatch); no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 125 | MURATA MANUFACTURING CO.,LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 126 | NATIONAL AUSTRALIA BANK - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 127 | NATIONAL INTELLIGENCE SERVICE - KR | COMPLETE | EMPTY | COMPLETE | COMPLETE | PARTIAL | EMPTY | BLOCKED | EMPTY | 9/12 | P | P | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 128 | NATIONAL TRADES UNION CONGRESS - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 11/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 129 | NCS PTE. LTD. - SG | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 130 | NEC CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 131 | NEW ZEALAND DEFENCE FORCE - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same); job status blank on every posting |
| 132 | NEW ZEALAND POLICE - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 133 | NIDEC CORPORATION - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 134 | NIKON CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 135 | NIPPON EXPRESS CO., LTD. - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 8/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 136 | NIPPON STEEL CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 137 | NISSAN MOTOR CO LTD - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 138 | NITTO DENKO CORPORATION - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 139 | NOMURA HOLDINGS, INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | READY — intent_topics website != account domain (topics dropped as mismatch) |
| 140 | NTT INC - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 141 | OLYMPUS CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 142 | OPTUM GLOBAL SOLUTIONS (PHILIPPINES), INC - PH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same); job status blank on every posting |
| 143 | ORICA AUSTRALIA - AU | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 144 | ORIX CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 145 | OVERSEA-CHINESE BANKING CORPORATION LIMITED - SG | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | P | OK | OK | OK | OK | P | READY |
| 146 | PANASONIC CORPORATION - JP | COMPLETE | COMPLETE | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 147 | PEMODALAN NASIONAL MADANI (PNM) - ID | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 148 | PERTAMINA (PERSERO), PT - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 149 | PETROLIAM NASIONAL BERHAD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 150 | PHILIPPINE NATIONAL POLICE - PH | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 10/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 151 | PILIPINAS SHELL PETROLEUM CORPORATION - PH | PARTIAL | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 8/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | **HOLD** — audit domain != firmographics domain (intent scores would be 'unverified'); PredictLeads returned a related/sub entity (client: treat as same); Business Description blank |
| 152 | PIONEER CORPORATION - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 4 idx | 9/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 153 | POSCO GROUP - KR | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 6 idx | 11/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | **HOLD** — audit domain != firmographics domain (intent scores would be 'unverified'); PredictLeads returned a related/sub entity (client: treat as same); Explorium hiring events available in reference/ |
| 154 | PRICEWATERHOUSECOOPERS - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 9/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 155 | PTT GLOBAL CHEMICAL PUBLIC COMPANY LIMITED - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 156 | PTT PUBLIC COMPANY LIMITED - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 6 idx | 12/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 157 | PT ASTRA INTERNATIONAL TBK - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED 3 idx | 6/12 | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | OK | **HOLD** — seed-filled datasets; live Astra account already exists |
| 158 | PT BANK CENTRAL ASIA TBK - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 159 | PT BANK CIMB NIAGA TBK - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 160 | PT BANK DANAMON INDONESIA TBK - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 161 | PT BANK MANDIRI (PERSERO) - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 162 | PT BANK RAKYAT INDONESIA (PERSERO) - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 163 | PT PERUSAHAAN LISTRIK NEGARA (PERSERO) - ID | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 164 | PT TIARA MARGA TRAKINDO - CATEGORY1 - PARTIAL - ID | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 165 | PUBLIC BANK BHD - MY | PARTIAL | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY — firmographics domain blank (recovered from Website); Explorium hiring events available in reference/ |
| 166 | QANTAS AIRWAYS - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 167 | RAMSAY HEALTH CARE - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 168 | RENESAS ELECTRONICS CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 169 | RHB CAPITAL BERHAD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 170 | RICOH COMPANY,LTD. - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 171 | SAGILITY PHILIPPINES B V BRANCH OFFICE - PH | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | RISK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — intent_topics website != account domain (topics dropped as mismatch); PredictLeads returned a related/sub entity (client: treat as same); no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 172 | SAN MIGUEL CORPORATION - PH | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 173 | SEATRIUM LIMITED - SG | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 174 | SECOM GROUP - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 175 | SEIKO EPSON CORPORATION - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 176 | SEVEN & I HOLDINGS CO., LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 177 | SHISEIDO COMPANY, LIMITED - JP | COMPLETE | COMPLETE | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 11/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 178 | SIAM COMMERCIAL BANK PUBLIC CO LTD - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 179 | SINAR MAS GROUP - ID | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 180 | SINGAPORE TECHNOLOGIES ELECTRONICS LIMITED - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 181 | SINGAPORE TELECOMMUNICATIONS LIMITED (SINGTEL) - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 182 | SOFTBANK GROUP CORP. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 183 | SONY CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 184 | STANDARD CHARTERED BANK - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — job status blank on every posting |
| 185 | STANLEY ELECTRIC CO.,LTD. - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 9/12 | P | OK | OK | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 186 | STARHUB LTD. - SG | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 187 | SUMITOMO CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 188 | SUMITOMO ELECTRIC INDUSTRIES, LTD. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 189 | SUMITOMO MITSUI FINANCIAL GROUP, INC. - JP | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 10/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | READY — intent_topics website != account domain (topics dropped as mismatch) |
| 190 | SUNWAY HOLDINGS INCORPORATED BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 191 | SUPREME COURT OF THE PHILIPPINES - PH | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | PARTIAL | BLOCKED | EMPTY | 10/12 | OK | OK | RISK | P | NO | OK | OK | OK | OK | OK | P | READY — intent_topics website != account domain (topics dropped as mismatch) |
| 192 | SUZUKI MOTOR CORPORATION - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 9/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 193 | TDK CORPORATION - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 194 | TELSTRA CORPORATION - AU | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 195 | TE WHATU ORA HEALTH NEW ZEALAND - NZ | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 1 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 196 | THE BANK OF TOKYO-MITSUBISHI LIMITED (BANGKOK BRANCH) - TH | COMPLETE | COMPLETE | PARTIAL | PARTIAL | EMPTY | EMPTY | BLOCKED | EMPTY | 6/12 | P | NO | RISK | NO | NO | RISK | NO | P | P | OK | NO | **HOLD** — shared-domain secondary: no PredictLeads/news/intent rows; intent_topics website != account domain (topics dropped as mismatch); no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending; Explorium hiring events available in reference/ |
| 197 | THE SIAM CEMENT PUBLIC CO LTD - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 10/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 198 | TMB BANK THANACHART PUBLIC COMPANY LIMITED - TH | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 199 | TOKIO MARINE HOLDINGS, INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 200 | TOKYO ELECTRON LIMITED - JP | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 201 | TOPPAN PRINTING CO., LTD. - JP | COMPLETE | PARTIAL | PARTIAL | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | P | P | NO | P | OK | OK | OK | OK | P | READY |
| 202 | TORAY INDUSTRIES,INC. - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 4 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 203 | TOSHIBA CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 204 | TOYOTA GROUP - JP | COMPLETE | PARTIAL | COMPLETE | PARTIAL | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | RISK | NO | P | OK | OK | P | **HOLD** — no technographics: Tech Map publishes 0 detected with whitespace 'opportunities'; Objection cards pending |
| 205 | TRUE CORPORATION PUBLIC COMPANY LIMITED - TH | COMPLETE | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 6 idx | 11/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY |
| 206 | T&D HOLDINGS, INC. - JP | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 3 idx | 9/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 207 | UNITED OVERSEAS BANK LIMITED (UOB) - SG | PARTIAL | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | EMPTY | 8/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY — Business Description blank |
| 208 | UNITED OVERSEAS BANK (MALAYSIA) BHD - MY | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 3 idx | 12/12 | P | OK | RISK | P | NO | OK | OK | OK | P | OK | NO | READY — intent_topics website != account domain (topics dropped as mismatch); Explorium hiring events available in reference/ |
| 209 | VIETNAM BANK FOR AGRICULTURE & RURAL DEVELOPMENT - VN | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 3 idx | 10/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 210 | VIETNAM JOINT STOCK COMMERCIAL BANK FOR INDUSTRY AND TRADE (VIETINBANK) - VN | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 211 | VIETNAM POST CORPORATION - VN | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 2 idx | 9/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY — Explorium hiring events available in reference/ |
| 212 | VIETNAM PROSPERITY JOINT STOCK COMMERCIAL BANK - VN | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 213 | VIETTEL CORPORATION - VN | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 214 | WESTPAC BANKING CORPORATION - AU | PARTIAL | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY — firmographics domain blank (recovered from Website) |
| 215 | WESTPAC BANKING CORPORATION - NZ | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 216 | WOOLWORTHS GROUP LIMITED - AU | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 217 | YAMAHA MOTOR CO., LTD. - JP | COMPLETE | EMPTY | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 3 idx | 11/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |
| 218 | YAMATO HOLDINGS CO.,LTD. - JP | COMPLETE | PARTIAL | PARTIAL | COMPLETE | COMPLETE | EMPTY | BLOCKED | BLOCKED 4 idx | 11/12 | P | OK | P | P | NO | OK | OK | OK | P | OK | NO | READY |
| 219 | YAYASAN BINA NUSANTARA - ID | COMPLETE | EMPTY | PARTIAL | COMPLETE | COMPLETE | COMPLETE | BLOCKED | EMPTY | 10/12 | OK | OK | P | P | NO | OK | OK | OK | OK | OK | P | READY — PredictLeads returned a related/sub entity (client: treat as same) |
| 220 | YKK CORPORATION - JP | COMPLETE | PARTIAL | COMPLETE | COMPLETE | COMPLETE | COMPLETE | BLOCKED | BLOCKED 2 idx | 12/12 | OK | OK | OK | P | NO | OK | OK | OK | OK | OK | P | READY |

---

## 4. Everything missing, grouped

### A. Missing for ALL 220 accounts
- **Contact data** — 219 of 220 have none; the one exception is the Astra POC seed (23 contacts), not the client file. Stakeholder Map cannot run; Opportunity Map target buyers, Objection Playbook raiser, Content Studio named personas and Message Evaluator personas all degrade.
- **Filings PDFs** — 0 of 220 folders hold a PDF. The crawl index lists 476 downloadable documents for 181 accounts. Note: no extractor reads PDFs; they feed only the Strategy Chat retrieval index.
- **Intent topic level and count** — `Level Of Intent` and `Topic Count` are blank in every one of the 173 intent_topics rows. The extractor reads them for provenance only, so this reduces traceability, not output.
- **Technology names in technology_detections** — 95% of rows carry an id, a score and a department code but no technology name. The vendor did not ship the technology object. The Tech Map's detections widget is therefore anonymous by design; vendor names come from Explorium's Full Tech Stack.
- **Name + Country columns on PredictLeads rows** — populated on 2.6% of job rows (secondary entities only); the client promised full population.

### B. Missing for SOME accounts
| gap | accounts | who fills it |
|---|---:|---|
| job_openings (PredictLeads) | 44 (45 before Astra's seed) | client, from another tool, same format |
| intent_score + intent_topics (Bombora) | 47 | vendor has no data; accepted as genuine no-data |
| hp_category_intent | 2 (Jabil SG, MUFG Bangkok) + 4 "Unavailable" | shared-domain rule; NSW intent file never downloaded (C33) |
| company_hierarchy | 55 (and 137 more with no parent name) | Explorium has none; nothing shown when absent (DEC-018) |
| technographics | 13; Full Tech Stack blank in 5 more | Explorium |
| news_events (PredictLeads) | 5 | vendor |
| google_news (RSS/Exa) | 2 | shared-domain rule |
| Filings index | 39 accounts with no indexed document | 31 listed by the client as no public filings; Agribank and VPBank unaccounted |
| Business Description | 6 | Explorium |
| company_ratings 64, subsidiaries 60, similar_companies 18, website_traffic 4, workforce_trends 5 | | not consumed by any feature |

### C. Available but partially populated
- job_openings: status blank on 54% of postings (12 accounts blank on every row), posted_at blank 36%, closed_at blank 99.9%. The agreed reading (E6 default) is "postings seen", never "open".
- google_news: 4,815 rows (29% after merge) have no event_date, all from Exa (56% of Exa rows); source_publisher blank 38%; signal_categories blank 31%. Undated rows are rejected by the news date gate.
- news_events: effective_date blank 47% (found_at covers it); `event` text blank 90% (summary covers it); location/product/amount mostly blank.
- hp_category_intent: first/latest intent dates blank ~50%, geo source 64%.
- company_hierarchy: parent name blank for 137 of 165; ultimate parent always present.
- Astra seed contacts: email blank 35%, mobile 70%.
- Case studies: hp_route blank on 78 of 384; publish_date empty on all.

### D. Available but invalid or problematic
| problem | where | size |
|---|---|---|
| Future dates rejected by the news gate | news_events.effective_date in 2027+ | 176 rows |
| Epoch dates | google_news.event_date = 1970-01-01 | 3 rows |
| Duplicate vendor ids | technology_detections 647, subpages 8, news_events 2, job_openings 1; company/extended_company 2 duplicated domains | vendor-side; never key on ids |
| Mis-encoded text (U+FFFD) | google_news 27 cells, job_openings 12, subpages 2, extended_company 1 | display as-is |
| HTML fragments in text fields | subpages 19, google_news 26, job_openings 2 (+ social_media, news_events_additional) | strip on ingest |
| Wrong entity from PredictLeads | KT Corp rows are Keysight Technologies (company profile, 41 jobs, 100 tech, 100 news, 100 connections) | 1 account — the audit sheet says "consider both names same"; this one is not a naming variant |
| Sub-/parent-entity from PredictLeads | Binus University International, All Nippon Airways, Epson America, Sony Electronics, CJ Cheiljedang, Posco International, NZDF Māori Cultural Group, PwC "New Zealand LP", Shell Group, Optum Inc, Sagility LLC, SCB Asset Management | 12 accounts — client accepted as the same |
| Shared domain, rows withheld | Jabil SG and MUFG Bangkok hold no PredictLeads, news or intent rows (jabil.com / mufg.jp go to the primary entity) | 2 accounts |
| Firmographics domain ≠ canonical domain | Posco (posco-inc.com vs posco.com), Pilipinas Shell (pilipinas.shell.com.ph vs shell.com.ph); Public Bank and Westpac AU blank in firmographics | 4 accounts |
| Intent-topics website ≠ account domain | 15 accounts (Air NZ, NSW Health, Fujitsu, IAG NZ, Kawasaki, MUFG ×2, NIS Korea, NTUC, Nomura, Sagility, Shiseido, SMFG, Supreme Court PH, UOB Malaysia) | all topics would be dropped as "mismatch" |
| Filings keyed to another company | The index carries the wrong territory name on these rows, so the split attached them to the wrong folder: Fletcher's 4 rows sit under Sunway Holdings (sunway.com.my), Fonterra's 3 under UOB Malaysia (uob.com.my), Astra's 3 dividend notices are duplicated into Federal International Finance (fifgroup.co.id), VPBank's 2 sit under Vietnam Post. Jabil 10-Q rows are already on both Jabil accounts and Hyundai DART rows already on HKMC Group, as the client answered. 2 Bank Mandiri rows carry a Bank Central Asia territory and are unassigned. | 12 rows in the wrong folder; client re-key answers (DEC-054f) received 25 Sep, not yet applied |
| Duplicate-story precedence | on the 356 RSS/Exa duplicates the split keeps the RSS row; DEC-054a says keep Exa | fix pending (list Exa first) |
| Explorium event log carries blank Company Domain | news_events_additional for MoD MY, MoD VN, Sagility, UOB MY | harmless (workbook-keyed) |

### E. Available and sufficient for ingestion now
firmographics (220), funding/social/website_traffic/workforce/company_ratings (unconsumed but clean), webstack (214 with website tech), technographics (202 with a tech stack), technology_detections (218, anonymous), intent_score (173), hp_category_intent (214 with scores), google_news (218), news_events (215), job_openings (176), company_hierarchy (165, ultimate parent), subsidiaries (160), PredictLeads company/extended_company/connections/subpages/similar_companies, the filings index (181), and the 13 reference tables. The pre-upload validator reports 0 transformation failures on the current split.

---

## 5. Data gaps vs logic gaps vs access gaps vs implementation gaps

### DATA GAPS (account data we do not have)
1. Contact file — all 220 (client: "will give that", no date).
2. Filings PDFs — all 220 (Drive folder / Pritesh's machine; index has URLs so we could self-download 476 files, ~1.5 GB).
3. Job openings — 44 accounts (client to aggregate from another tool).
4. Exa event dates — 5,120 undated rows (client re-crawl open).
5. Name + Country columns on every PredictLeads row (2.6% populated).
6. NSW Education intent file (C33) — one account's intent, on Drive only.
7. Technology names in technology_detections — vendor never shipped the technology object.
8. Bombora intent (intent_score/intent_topics) — 47 accounts; genuine no-data.
9. Explorium gaps — technographics 13, hierarchy 55, Business Description 6, firmographics domain 2.

### LOGIC GAPS (rules not final; not datasets)
Vendor-flagged rows default (issue 13) · job-status label wording (14) · one primary recommendation vs five routes (16) · confidence tiers T0–T3 (17) · Technographic Map risk labels (18, with Sahaj) · "Could be raised by" wording (24) · evidence-tier gate F11 and APJ region preference F12 (27) · entity scope APAC vs global (02) · filings reconciliation counts (07) · Exa label on screen (10) · seat proxy and lifecycle columns (19) · noisy-keyword rule provenance (CONFLICT I-07) · rules doc feedback pending since 10 Sep (25) · client UI observations of 22 Sep never received (26).

### ACCESS GAPS
GCP project id and Cloud Run region (issue 22, blocks deployment) · Drive folder with filings PDFs and NSW intent · SharePoint (apollo_data, full hp_intent workbook) · Gmail attachments not downloadable by tooling (Rulebook FINAL 23 Sep, HP_220_Refinements_Updated, tests on current HP 220.docx).

### IMPLEMENTATION GAPS (our code or pipeline; each verified by code trace, file:line in the extractor audit)
1. **compliance_filings is declared by five features and read by none.** Only `retrieval/corpus.py` reads PDFs, for the Strategy Chat index. Readiness reports and the regeneration trigger both mislead on this dataset.
2. **Content Messaging reads news_events with google_news column names** (`event_headline`, `event_date`, `source_url`), so 14,332 PredictLeads news rows contribute nothing to it. Content Studio has the same mismatch.
3. **Content Studio has its own CSV reader** with a hard-coded Windows path and path candidates that miss the backend root; unless the process runs from `hp-backend/` or `/app`, it silently reads every dataset as absent.
4. **Undeclared dependencies**: urgency score reads technographics, webstack, hp_category_intent, extended_company, intent_score, google_news, news_events; Intent reads firmographics for the domain; Tech Map reads firmographics and hp_category_intent; Opportunity Map reads hp_category_intent and intent_topics; Content Studio reads news_events, intent_score, google_news. Uploading one of these datasets does not regenerate those features.
5. **Intent topics mismatch rule** drops every topic when `Company Website` differs from the account domain — 15 accounts today, on vendor domain variants, not wrong companies.
6. **Runtime account domain comes from firmographics** (Explorium's), not from the audit's canonical domain, and the account record stores only a name. Posco and Pilipinas Shell will have their category file marked "unverified".
7. **Technographic Map without technographics** publishes "available" with 0 detected and still flags PC and Print whitespace as opportunities (13 accounts).
8. **Objection Playbook without technographics** shows "requires OPENAI_API_KEY" — a false diagnosis.
9. **Stale documents survive reloads**: Opportunity Map keeps previous plays when none are found; the news relevance summary is not rewritten when the feed is empty; Tech Map recommendations are not overwritten when there is no evidence.
10. **Inconsistent empty handling**: Executive Dashboard shows stakeholders 0, Strategy Chat shows None, Message Evaluator publishes "available" with 0 personas.
11. **News date gate** rejects future dates, so 176 news_events rows with a 2027+ effective_date are lost although found_at is valid; 4,815 undated google_news rows are rejected as agreed.
12. **Explorium hiring events (194 accounts) and Explorium news events (168) have no dataset key**, so they cannot be uploaded; the hiring events would cover 32 of the 44 accounts with no PredictLeads jobs.
13. **Split keeps RSS over Exa** on the 356 duplicate stories; DEC-054a says keep Exa.
14. **Filings re-keys (DEC-054f) not applied** in the split. Because the index's territory column is wrong on those rows, 12 documents currently sit in the wrong account folder (Fletcher under Sunway, Fonterra under UOB Malaysia, Astra's notices under Federal International Finance, VPBank under Vietnam Post); a further 29 rows are unassigned.
15. **FEATURE_MAPPINGS source columns are stale** (Cms/Ssl for webstack; "vendor" for technology_detections), so documentation overstates what is read.
16. **Every upload regenerates dependents synchronously** (about 41 feature runs per account if uploaded file by file); a regenerate-once path is needed before bulk loading (proposed DEC-056).
17. **PredictLeads products and sec_filings**, which DEC-026 says to use, have no dataset key and sit in `reference/`.

---

## 6. Latest PredictLeads data vs the split

The only PredictLeads artifact newer than the 23 Sep combined workbook on this machine is **`PredictLeads_219_Account_Domain_Audit.xlsx`** (received 25 Sep 12:30 IST, sheets "219 Account Audit", "Problems Only", "Summary"). It is a canonical-domain and display-name list, not new account data.

| question | answer |
|---|---|
| Already incorporated? | Yes. The split reads it (`DOMAIN_AUDIT_FILE`), matched all 219 rows, and was regenerated 25 Sep 13:57. Astra is absent from the audit by design. |
| Does it replace or supplement? | Supplements the master list: domains and display names only. |
| What changed in the data? | Public Bank: domain publicbankgroup.com → pbebank.com, gaining 274 previously unclaimed PredictLeads rows (38 news, 47 tech, 100 connections, 82 subpages, 5 similar, company, extended_company). Posco: posco-inc.com → posco.com. Pilipinas Shell: pilipinas.shell.com.ph → shell.com.ph. Stanley and Shiseido keep aliases. |
| What still needs doing? | The audit domain lives only in `_account.json`; firmographics.csv still carries the Explorium domain, so the extractor's runtime domain disagrees for Posco and Shell (gap 6). Store the canonical domain on the account record or rewrite the firmographics domain at split time. |
| Which accounts? | All 219; 13 flagged "consider both names same" (accepted by client); KT Corp's PredictLeads rows are Keysight's — not a naming variant. |
| Which features use it? | Everything keyed by domain: intent attach, news, hiring, tech detections. |
| Re-run needed? | The split is already re-run. Nothing has been loaded into any environment, so no account needs regenerating. If a newer combined workbook arrives (new hiring or contacts), the split must be re-run and every loaded account re-uploaded, because upload is the only trigger for regeneration. |

The remaining PredictLeads sheets (products 2,246 rows / 128 accounts, sec_filings 121 / 12, financing_events 74 / 47, github 0, and five vendor QA sheets) are split into `reference/` and are not consumable until a dataset key exists (gap 17).

---

## 7. Coverage by source (actual counts)

| source | file | rows | accounts covered | known quality |
|---|---|---:|---:|---|
| Explorium | 220 workbooks (18 sheets) | — | 220 | 14_Prospect_Contacts and 13_News_Events empty everywhere / 168 respectively; hierarchy 165; technographics 207; Bombora intent 173 |
| PredictLeads | predictleads_combined_219_accounts.xlsx (23 Sep) | job 14,965 · tech 17,799 · news 14,289 · connections 19,583 · subpages 15,163 | 217–219 | see §1a; Name+Country 2.6%; ids duplicated |
| Exa | exa_data.xlsx (18 Sep) | 9,221 | 217 (only source of news for 119) | 56% undated; 28 mis-encoded cells |
| Google News RSS | google_news_rss_data 1.xlsx | 7,913 | 101 | fully dated; 3 accounts RSS-only |
| HP Intent (category file) | hp_intent_results 2.xlsx | 220 | 218 attached, 214 with scores | 4 "Unavailable"; dates 50% blank |
| Case Studies | hp_case_studies_final.csv | 384 (89 cleaned in Atlas) | global | route blank 78; no publish dates |
| Filings | filings 1.csv index | 505 (476 with URL) | 181 | PDFs not local; 29 unassigned; re-keys pending |
| News (merged) | google_news dataset | 16,778 | 218 | 4,815 undated |
| Hiring | job_openings | 15,065 | 176 | status blank 54% |
| Contacts | prospect_contacts | 23 (seed) | 1 | file not received |
| Hierarchy | company_hierarchy | 165 | 165 | parent name 83% blank |
| Firmographics | firmographics | 220 | 220 | 6 without description, 2 without domain |
| Master list / audit | APAC_Account_Parent_Child_Mapping.xlsx; PredictLeads_219_Account_Domain_Audit.xlsx | 220 / 219 | 220 | all matched |

---

## 8. What can be processed right now

**Can process now (all required inputs present):** 132 accounts run every feature that does not need contacts with full inputs. By feature: Executive Dashboard 176, News Signals 215, Intent & Demand 157, Technographic Map 201, Objection Playbook 207, Content Messaging 206, Content Studio 176, Strategy Chat 220.

**Can process with partial output (missing data is allowed; section left out per DEC-054b):** Executive Dashboard on the 44 accounts without hiring; Intent on 46 with a category score but no Bombora topics (or the reverse); Opportunity Map on 217 without contacts (target buyers "no_match"); Message Evaluator on 175 using job-role personas; Content Studio on 44 with archetype personas only; News Signals on 3 single-feed accounts.

**Cannot process:** Stakeholder Map on 219 accounts (no contacts). Objection Playbook on 13 (no technographics). Message Evaluator on 44 (no contacts and no jobs). News Signals and Opportunity Map on Jabil SG and MUFG Bangkok (no news at all).

**Should NOT be processed yet (18 accounts, quality hold):**
- 13 without technographics — Tech Map would publish false whitespace opportunities and the Objection cards a false notice: Alps Alpine, Coupang, Fujitsu, Johor Corp, MoD MY, MoD VN, Ministry of National Defense, Ministry of Public Security, MUFG, Panasonic, Sagility PH, MUFG Bangkok, Toyota Group.
- Jabil SG and MUFG Bangkok — shared-domain secondaries with 11–13 tables and no news, hiring, tech detections or intent; a near-empty dashboard reads as fact.
- KT Corp — PredictLeads profile, jobs, tech and news belong to Keysight Technologies.
- Posco and Pilipinas Shell — canonical domain differs from the firmographics domain; the intent file will not attach.
- Astra — seed-filled datasets in an older schema, and a live Astra account already exists.

Also hold the 15 intent-topic mismatch accounts for Intent & Demand only, until gap 5 is fixed; the rest of their features can run.

**Everything that runs an LLM without an input guard (Opportunity Map, Tech Map narrative) will spend tokens on the hold accounts too**, which is another reason not to load them first.

---

## 9. Pre-ingestion checklist

Template (all answers derivable from `_account.json`, `_manifest.json`, `_READINESS.txt` and the matrix):

```text
Account identity valid?        _account.json.name_for_upload == audit sheet Column B; domain == audit Column D; not already in the target DB
Required datasets present?     firmographics rows ≥ 1; at least one of google_news / news_events; technographics rows ≥ 1 (else Tech Map + Objection hold)
Required fields populated?     Company Name, Company Domain (or Website), Business Description; Full Tech Stack non-blank; hp_category_intent Top Intent Score non-blank
Known domain conflict?         shared domain (jabil.com, mufg.jp)? firmographics domain == canonical domain? intent_topics Company Website == domain?
Known entity conflict?         audit sheet "Problems Only" row? (KT Corp = wrong entity; 12 others accepted)
Missing critical data?         prospect_contacts (219), job_openings (44), Bombora intent (47) — list, do not block
Data-quality issue?            job status all blank? U+FFFD / HTML cells? future or epoch dates? seed-filled?
Ready for ingestion?           validator 0 FAIL for the folder; no HOLD flag in the matrix; upload plan lists only files with rows; regenerate-once path in place
```

Worked example, ACCENTURE INC - PH:

```text
Account identity valid?        yes — "ACCENTURE INC - PH", accenture.com, audit row OK, not loaded anywhere
Required datasets present?     yes — firmographics 1 row; google_news 49 + news_events 100; technographics 1
Required fields populated?     yes — name/domain/description present; Full Tech Stack present; Top Intent Score 35 (3D Printers)
Known domain conflict?         none — firmographics, intent file and intent_topics all say accenture.com
Known entity conflict?         none — audit "OK"
Missing critical data?         prospect_contacts (none); company_hierarchy empty; subsidiaries empty; filings index 4 docs, no PDFs
Data-quality issue?            job status blank on all 100 postings (show as "postings seen"); no corrupted cells
Ready for ingestion?           YES for 8 features with full inputs; Stakeholder Map cannot run; Opportunity Map / Message Evaluator degrade; Executive Dashboard shows stakeholders 0 until gap 10 is fixed
```

---

## Sources
Split output `220 account split csv/` (run summary 2026-09-25T08:27 UTC; validator 0 FAIL / 22 WARN) · `scripts/split_account_data.py` (working tree) · extractor trace of `hp-backend/src/app/services/extractors/*.py`, `api/v1/feature_mapping.py`, `services/retrieval/registry.py`, `retrieval/corpus.py` · `07_Internal_Generated/Analysis/hp-input-contract.json` · `00_INDEX/DECISION_LOG.md` (DEC-013…DEC-055) · `06_Unresolved_and_Open/` (27 issues) · `04_Data_and_Source_Definitions/` READMEs · `PredictLeads_219_Account_Domain_Audit.xlsx` · `hp_case_studies_final.csv`.
