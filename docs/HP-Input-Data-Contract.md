# HP Account Intelligence — Input Data Contract

**Audience:** Data team producing the per-account file set
**Status:** Describes what the system accepts **today** (as built), not a wish list
**Scope:** Every file that can be uploaded, its accepted name/format, the columns the code actually reads, and the value formats it assumes

**Companion:** [`hp-input-contract.json`](hp-input-contract.json) — the same contract machine-readable, plus what each file becomes as JSON (the 31 widget payloads), the shared envelope, and 17 numbered edge cases. Use it for validators, codegen and CI checks.

---

## 0. Summary

The API accepts **25 dataset keys**. Of those:

- **14 are actually consumed** by the product — these are the ones that matter (§3, Groups A/B/D). Thirteen are CSV tables; one (`compliance_filings`) is PDF and is the sole source of reported financial figures.
- **12 are accepted but read by nothing** — uploading them does nothing today (§3, Group C)

**The five rules that cause the most breakage:**

1. **Column names are matched exactly** — case-sensitive, whitespace-sensitive. No normalization anywhere (one narrow exception, §4).
2. **No validation at upload.** A file with wrong headers returns HTTP 201 and then produces empty widgets with no error.
3. **The domain is the join key** and must be identical across every file for an account. Three of the six silent failure modes are domain mismatches (§7).
4. **Dates must be ISO-8601.** Dates are string-sorted, and ambiguous `03/04/2025` is read as 4 March.
5. **Delimiters differ per file** — comma, semicolon, pipe, and JSON array all appear (§1.2a).

**Fastest path to a working account:** `firmographics`, `technographics`, `prospect_contacts`, `intent_score`, `google_news`, `news_events`, `job_openings` (§6).

Nine open questions/defects needing a data-team decision are collected in §5.

---

## 1. How upload works today (read this first)

Files are uploaded per account through `POST /api/v1/accounts/{account_id}/data` with two form fields:

| Form field | Value |
| --- | --- |
| `dataset_key` | One of the 25 keys in §3. Lower-cased and trimmed before matching. |
| `file` | The file itself |
| `file_id_to_replace` | Optional, multi-file datasets only |

**What the upload endpoint validates:**

1. `dataset_key` is a known key
2. File extension is in that dataset's allowed list
3. File is not 0 bytes
4. File parses — CSV via `csv.reader`, Excel via `pandas.read_excel`, PDF via PyMuPDF (page count > 0)

**What it does NOT validate — important:**

- ❌ **No column/header checking.** A CSV with completely wrong headers uploads successfully with HTTP 201.
- ❌ **No type, range, or enum checking.**
- ❌ **No required-column checking.**

A file with wrong headers is accepted at upload and then produces **empty or missing widgets** later, with no error pointing back at the file. This is why the column names below must be treated as a hard contract rather than a guideline.

### 1.1 Column matching is exact and case-sensitive

Nearly all datasets are read with `csv.DictReader` (`services/extractors/datasets.py`), which matches header strings **byte-for-byte**. Therefore:

- `Company Name` ✅ — `company name` ❌ — `Company_Name` ❌ — `Company Name ` (trailing space) ❌
- Title Case with single spaces, exactly as printed in §3.
- Where a snake_case fallback exists it is listed explicitly as an alias. **Do not assume one exists.**

**The one exception:** `hp_category_intent` field names are lower-cased before matching, so that file's field row is case-insensitive.

### 1.2 Encoding and file mechanics

| Rule | Requirement |
| --- | --- |
| Encoding | UTF-8. A BOM is fine (read with `utf-8-sig`). `hp_category_intent` alone falls back to Windows-1252. |
| Header | Exactly one header row — **except** `hp_category_intent`, which has two (§4). |
| Quoting | Standard RFC 4180. Fields containing commas/newlines must be double-quoted. |
| Booleans | Not normalized. `webstack` uses `Yes`/`No`; `technology_detections` uses `True`/`False`. Keep each file's existing convention. |
| Empty | Send a genuinely empty field. The literal strings `none`, `null`, `nan`, `[]` are treated as empty by the contacts/news resolvers — never emit them as text. |
| Dates | **ISO-8601.** Most dates are compared/sorted as *strings*, so any other format sorts wrong and silently produces wrong "latest" values. |
| Row count | `firmographics`, `company_hierarchy`, `technographics`, `webstack` are **row-0 only** — extra rows are silently ignored. One account per file. |

### 1.2a Three different multi-value delimiters

This is a frequent source of error. The delimiter depends on the file:

| File | Delimiter |
| --- | --- |
| `technographics`, `webstack` | **comma** `,` (inside a quoted field) |
| `prospect_contacts` departments | **semicolon** `;` (commas are converted to `;` first, so both work) |
| `hp_category_intent` list fields | **pipe** `\|` |
| `job_openings.categories`, `contract_types`, `tags`; `technology_detections.department_onet_codes` | **JSON array string** — `["full_time"]`, double quotes |

### 1.3 The join key is the domain

Accounts are matched across files by **bare lower-case host**: `https://www.Astra.co.id/about` → `astra.co.id` (scheme, `www.`, path, port and trailing dot stripped).

Every file that carries a domain must carry it in the **same normalized form** for the same account. `firmographics.Company Domain` is the anchor — if `hp_category_intent` has no row whose domain matches it, that file's scores are silently dropped with "no row for this account", even when the scores are present and correct.

---

## 2. File-level contract

Two structural types:

| Type | Behaviour | Datasets |
| --- | --- | --- |
| `single_file_csv` | One active file. Re-upload **replaces** it (stored under a canonical filename; previous marked `replaced`). | 22 datasets |
| `multi_file` | Many active files coexist. Replacing one needs `file_id_to_replace`. | `news_events`, `news_events_additional`, `google_news`, `compliance_filings` |

Uploaded filenames do not need to match the canonical name — the system renames on store. Canonical names in §3 are given so your exports are self-describing.

---

## 3. The 25 accepted datasets

Columns marked **[R]** are required for the feature to produce output; **[O]** optional. "Read by code" = the exact string the code looks up.

### Group A — Source A / Explorium sheets

#### 3.1 `firmographics` — `firmographics.csv` — `.csv` — sheet `1_Firmographics`
The anchor file. Feeds 9 of 11 features.

| Column | Req | Notes |
| --- | --- | --- |
| `Company Name` | **[R]** | Aliases: `company_name`, `Name` |
| `Company Domain` | **[R]** | Aliases: `company_domain`, `Domain`, `Website`, `website`. The join key (§1.3) |
| `Business Description` | **[R]** | Free text; drives narrative + messaging features. **No alias in 2 of the readers — send this exact name** |
| `Number Of Employees Range` | [O] | Aliases: `number_of_employees_range`, `employee_count_range`, `Employee Count`, `employee_count`. A **band** e.g. `1001-5000`, never parsed as a number |
| `Yearly Revenue Range` | [O] | Aliases: `yearly_revenue_range`, `Yearly Revenue`, `revenue`. A band, never parsed as a number |
| `Naics`, `Naics Description`, `Sic Code`, `Sic Code Description`, `Linkedin Industry Category` | [O] | Industry. Composed as `LinkedIn / NAICS / SIC`, de-duplicated. Aliases: snake_case of each; last-resort `Industry Classification`, `industry` |
| `Country Name`, `Region Name`, `City Name`, `Street`, `Zip Code` | [O] | HQ. Composed as `City, Region, Country`, blanks skipped, `N/A` if all blank. Aliases: snake_case of each; fallback `HQ Location` / `hq_location` |
| `Company ID`, `Business Id`, `Ticker`, `Linkedin Profile` | [O] | Identifiers |

Full header as received:
```
Company Name,Company Domain,Company ID,Business Id,Name,Business Description,Website,Country Name,Region Name,City Name,Street,Zip Code,Naics,Naics Description,Sic Code,Sic Code Description,Ticker,Number Of Employees Range,Yearly Revenue Range,Linkedin Industry Category,Linkedin Profile
```

> **Note:** revenue and employees arrive as *bands*. No reported revenue figure exists in this file — reported financials come only from `compliance_filings` (§3.13).

#### 3.2 `company_hierarchy` — `company_hierarchy.csv` — sheet `2_Company_Hierarchy`

| Column | Req | Notes |
| --- | --- | --- |
| `Parent Company Name` | **[R]** | Alias: `parent_company_name`. Empty = company is its own parent |
| `Ultimate Parent Name` | **[R]** | |
| `Business Id`, `Parent Company Id`, `Ultimate Parent Id` | [O] | |

#### 3.3 `technographics` — `technographics.csv` — sheet `4_Technographics`

| Column | Req | Notes |
| --- | --- | --- |
| `Full Tech Stack` | **[R]** | Comma-separated technology names inside one quoted field |
| 20 category columns | [O] | See exact strings below |

**The 20 category columns — note the unusual casing, which must be matched exactly:**
```
Testing And Qa, Sales, Prog Langs And Frameworks, Productivity And Operations,
Product And Design, Platform And Storage, Operations Software, Operations Management,
Marketing, It Security, It Management, Hr, Finance And Accounting, Ecommerce,
Devops And Development, Customer Management, Computer Networks, Communications,
Collaboration, Bi And Analytics, Technology
```

⚠️ `Testing And Qa` (**not** "QA"), `Hr` (**not** "HR"), `It Security` / `It Management` (**not** "IT"). These are the strings the code looks up — the natural capitalisation will not match.

A technology is credited to its **specific category column** when present; `Full Tech Stack` is read last as the catch-all. So the category columns are what give a technology its provenance on screen — worth populating, not just the full stack. Vendor matching is case-insensitive on whole words, and underscores are treated as spaces.

⚠️ **Action required — truncated cells.** The current file contains 9 cells ending in `(+11 more)`, `(+15 more)`, etc. Nothing in the code strips these, so `(+15 more)` is ingested as a **literal technology name**. Please export full lists with no truncation marker.

#### 3.4 `webstack` — `webstack.csv` — sheet `5_Webstack` / `5_Tech_Breakdown`

| Column | Req | Notes |
| --- | --- | --- |
| `Technologies Used By Company Website` | **[R]** | Comma-separated, underscore-joined names (`ASP.NET_Core`) |
| `Technologies Categories`, `Technologies Sub Categories` | [O] | Mixed case in source (`Server, Web_Master, ads, analytics`) |
| `Cms`, `Ssl`, `Web Server`, `Hosting`, `Cdn`, `Framework`, `Analytics` | [O] | Named in the feature map as `5_Tech_Breakdown` fields. **Not present in the current `webstack.csv`** — confirm which sheet supplies them |
| `Status`, `Umbrella`, `Db Indexed`, `Live Techs`, `Ecommerce`, `Established`, `Parked`, `Affiliate Links`, `Payment Options`, `Money Spend On Website Technologies`, `Spend`, `Number Of Premium Technologies`, `Number Of Pages On Sitemap`, `Number Of Social Networks`, `Product Count`, `Premium Techs`, `Q Rank`, `Earliest Record`, `Latest Update`, `Company Vertical`, `Shopify Apps In Use`, `Payment Technologies In Use`, `Business Id` | [O] | `Yes`/`No` booleans. ⚠️ `Earliest Record` is `2002-01-22T23:00:00` — no `Z`; please emit full ISO-8601 with timezone |

#### 3.5 `intent_topics` — `intent_topics.csv` — sheet `10_Intent_Topics`

| Column | Req | Notes |
| --- | --- | --- |
| `Company Website` | **[R]** | ⚠️ **The single most load-bearing column in the whole contract.** If it does not normalize-match the account domain, **every Bombora topic is discarded** and the intent widget reports "No matched signal" |
| `Date Stamp` | **[R]** | `YYYYMMDD` (e.g. `20260830`). `YYYY-MM-DD` also accepted; anything else kept raw, not guessed. If the file carries **more than one distinct Date Stamp, no time window is shown at all** — one run per file |
| `Level Of Intent` | **[R]** | ⚠️ **Empty in the current file.** Needs a defined value set |
| `Business Id`, `Company Name`, `Topic Count` | [O] | ⚠️ `Topic Count` also empty currently |

#### 3.6 `intent_score` — `intent_score.csv` — sheet `11_intent_score`
Bombora topic scores — the supporting-signal source.

| Column | Req | Notes |
| --- | --- | --- |
| `Topic` | **[R]** | Convention `family: detail`, lower-case — e.g. `business solutions: data insights`. The `family:` prefix is used for grouping; keep it. **Blank ⇒ row skipped** |
| `Composite Score` | **[R]** | Numeric **0–100**. Observed range 60–100 (surge threshold) |

149 rows in the reference file; one row per topic, no domain column (the whole file belongs to the account).

**Two behaviours worth knowing:**

- **A non-numeric score is not treated as zero.** The topic is kept and marked excluded with the reason `Composite Score '<raw>' is not a number`. So a formatting error is visible rather than silently scoring 0 — but the topic contributes nothing.
- **Duplicate topics: first row wins.** Matching is case-insensitive and repeats are reported as removed, **never averaged**. If you send the same topic twice with different scores, the second is discarded. Please de-duplicate upstream.

#### 3.7 `prospect_contacts` — `prospect_contacts.csv` — sheet `14_Prospect_Contacts`

⚠️ **The feature-map documentation is stale for this file.** It lists `Full Name`, `Title`, `Department`, `Seniority`, `Linkedin Url` — **none of those columns exist** in the real file and none are read. The code reads the `Prospect *` names below. **Use these:**

| Read by code (in fallback order) | Req | Notes |
| --- | --- | --- |
| `Prospect full_name` → else `Prospect first_name` + `Prospect last_name` | **[R]** | Falls back to `"Unknown Contact"` |
| `Prospect job_title` → `apollo_title` | **[R]** | |
| `Prospect job_department_main` → `apollo_department` | **[R]** | e.g. `It` |
| `Prospect job_level_main` → `apollo_seniority` | **[R]** | e.g. `director`, `head` (lower-case) |
| `Contact professions_email` → `Email` → `apollo_verified_work_email` | [O] | |
| `Contact professional_email_status` → `Email Status` → `apollo_zerobounce_email_status` | [O] | e.g. `valid` |
| `Contact mobile_phone` → `Mobile Phone` → `apollo_direct_mobile_phone` | [O] | Normalized by code |
| `Prospect linkedin` → `Prospect linkedin_url_array` → `apollo_linkedin_url` | [O] | |
| `Prospect buying_committee_personas` | [O] | **JSON array string**: `["IT Decision Maker"]` |
| `Prospect prospect_id` | [O] | Falls back to positional `contact_N` — supply it for stable IDs |
| `Prospect skills`, `Prospect experience`, `Prospect city`, `Prospect country_name` | [O] | |
| `apollo_requested_contact` / `apollo_matched_contact` | [O] | Presence flags the row as Apollo-sourced |

**Null sentinels:** `none`, `null`, `nan`, `[]` are treated as empty (case-insensitive).

#### Controlled vocabularies (these are real enums — unmatched values degrade silently)

**`Prospect job_level_main`** — anything not in this list becomes `"Individual Contributor"`, which lowers the contact's score and can drop them out of the priority list:
```
c_suite, c-suite, cxo, vp, vice_president, director, head, manager, owner
```
Wrapping is tolerated (`["c_suite"]` works — brackets/quotes are stripped).

**`Prospect job_department_main`** — unmatched values are Title-Cased and passed through, so they still display but never match HP relevance rules:
```
master_information_technology, master_engineering_technical, master_operations,
master_finance, master_legal, master_marketing, master_sales, master_human_resources,
product_management, consulting, c_suite, it, data, engineering, operations,
finance, legal, marketing, sales, human resources
```

**`Email Status` / `Contact professional_email_status`** — only the exact value `valid` (case-insensitive) earns the data-completeness credit. Other values are kept but score nothing.

**Phone format** — a trailing `.0` (Excel float coercion) is stripped, then non-digits removed. A `+` prefix is emitted when the value started with `+` or has 10–15 digits. Please send E.164 (`+6281...`) and keep the column formatted as **text**, not number, in any Excel step.

> **Contacts are scored, not filtered.** No row is dropped. Each gets a 0–100 score: 25% seniority + 25% HP relevance + 20% influence + 15% data completeness + 15% priority. A contact needs ≥60 to be a priority contact — so missing email/phone/LinkedIn directly removes people from the priority list.

#### 3.8 `news_events` (multi-file) — `.csv` — sheet `13_News_Events`

| Column | Req | Notes |
| --- | --- | --- |
| `article_sentence` | **[R]** | Headline/summary text. Alias: `news_announcements` |
| `found_at` | **[R]** | Full ISO-8601 with `Z`: `2022-11-28T11:01:00Z` |
| `category` | **[R]** | snake_case verbs: `partners_with`, `launches`, `acquires`, `is_developing`, `has_earnings`, `sells_assets_to`, `identified_as_competitor_of` |
| `company_domain` | **[R]** | Join key |
| `confidence` | [O] | **Float 0–1** (e.g. `0.9159`) — see §5.2 |
| `effective_date` | [O] | `YYYY-MM-DD`. ~49% empty currently |
| `event` | [O] | ~98% empty currently |
| `summary`, `amount`, `amount_normalized`, `assets`, `assets_tags`, `award`, `contact`, `division`, `financing_type`, `financing_type_normalized`, `financing_type_tags`, `headcount`, `id`, `job_title`, `job_title_tags`, `location`, `location_data`, `planning`, `product`, `product_data`, `product_tags`, `recognition`, `vulnerability` | [O] | `*_data` fields are JSON strings |

> ℹ️ `identified_as_competitor_of` is a news relationship rather than a buying signal. It **was** excluded from becoming a primary signal; that gate is empty by client instruction (Sep 2026), so the value is now used as supplied. See section 4.

---

### 3.8a Shared rules for BOTH news files (`google_news` + `news_events`)

These two feed one widget through one normalizer, so the rules below apply to both.

**Accepted date formats, tried in this order:**
1. Full ISO-8601 (`Z` accepted) ← **use this**
2. `YYYY-MM-DD`
3. `DD/MM/YYYY`
4. `MM/DD/YYYY`
5. `YYYY/MM/DD`

⚠️ **`DD/MM/YYYY` is tried before `MM/DD/YYYY`.** So `03/04/2025` is read as **4 March**, not 3 April. If any upstream feed emits US-format dates they will be silently misread. **Send ISO-8601 only.** Naive timestamps are assumed UTC.

**Rows are silently dropped when:**

| Gate | Rule |
| --- | --- |
| No text | Neither headline nor evidence sentence present |
| Unparseable date | Date does not match any format above |
| Future date | Date is after today |
| **Too old** | **Older than 365 days** |

That last one matters for delivery planning: a back-catalogue of older news is accepted at upload and then discarded. Only the trailing 12 months reach the product. At most **20 signals** are published per account.

**De-duplication:** headlines are matched case-insensitively with punctuation stripped, and also merged at **≥85% fuzzy similarity**. Near-identical headlines from multiple publishers collapse into one signal — expected, not a bug.

**`news_events` has no URL column** and the code will never fabricate one, so `news_events` signals are unlinkable. Only `google_news` carries `event_url`.

**Accepted `event_type` / `category` values** (anything unrecognised becomes `"Strategic"`):

- `google_news.event_type`: `funding`, `earnings`, `m&a`, `acquisition`, `leadership`, `launch`, `product`, `partnership`, `hiring`, `security`, `other`
- `news_events.category`: `has_earnings`, `invests_into`, `invests_into_assets`, `receives_financing`, `launches`, `is_developing`, `partners_with`, `acquires`, `sells_assets_to`, `expands_to`, `identified_as_competitor_of`, `hires`, `increases_headcount_by`, `is_vulnerable_to`

---

### Group B — Explorium / other feeds

#### 3.9 `job_openings` — `job_openings.csv` — `.csv`

| Column | Req | Notes |
| --- | --- | --- |
| `status` | **[R]** | ⚠️ **See §5.1 — this is the most important open question.** Empty is currently counted as *open* |
| `title` | **[R]** | |
| `normalized_title` | [O] | |
| `seniority` | [O] | snake_case: `junior`, `mid_senior`, `manager` |
| `first_seen_at`, `last_seen_at` | **[R]** | ISO-8601 with `Z`. Sorted as strings |
| `posted_at` | [O] | ⚠️ 71% empty currently |
| `categories`, `contract_types`, `tags` | [O] | **JSON array strings**: `["full_time"]` |
| `company_domain`, `_related_company_domain` | **[R]** | Join key |
| `description`, `id`, `language`, `location`, `location_data`, `onet_data`, `recruiter_data`, `salary`, `salary_data`, `translated_title`, `url`, `last_processed_at` | [O] | `language` is ISO-639-1 (`id`, `en`) |

#### 3.10 `technology_detections` — `technology_detections.csv` — `.csv`

| Column | Req | Notes |
| --- | --- | --- |
| `score` | **[R]** | ⚠️ **Float 0–1** — a different scale from every other score (§5.2) |
| `first_seen_at`, `last_seen_at` | **[R]** | ISO-8601 with `Z` |
| `id` | **[R]** | Detection id |
| `department_onet_codes` | [O] | **JSON array** of O*NET codes: `["15-2051.01"]` |
| `behind_firewall` | [O] | `True`/`False` (Python style) |
| `company_domain`, `_related_company_domain`, `location_data`, `source_count` | [O] | |

⚠️ **Gap:** the feature map documents a `vendor` column for this dataset. **It does not exist in the file and nothing reads it.** As delivered, each row is a score and a date with **no technology name attached**, which makes the detections un-interpretable on screen. Please either add the technology/vendor name column or confirm this dataset is reference-only.

#### 3.11 `google_news` (multi-file) — `.xlsx`, `.xls`, `.csv`
The **primary** news source (`news_events` is the add-on).

| Column | Req | Notes |
| --- | --- | --- |
| `event_headline` | **[R]** | Aliases: `title`, `summary` |
| `event_date` | **[R]** | `YYYY-MM-DD`. Aliases: `pubDate`, `found_at` |
| `event_type` | **[R]** | ⚠️ Mixed casing in source: `launch`, `other`, `leadership`, `funding` but `M&A`. **Pick one casing convention** |
| `event_url` | **[R]** | |
| `relevance_confidence` | [O] | ⚠️ **Text** `High`/`Medium`/`Low` — inconsistent with `news_events.confidence` (§5.2) |
| `source_publisher` | [O] | Used as fallback when headline has no trailing suffix |
| `coverage_depth_events_per_account_last_12mo` | [O] | Integer |
| `company_name`, `website_domain`, `company_linkedin_url`, `news_announcements` | [O] | `website_domain` is the join key |

#### 3.12 `hp_category_intent` — `hp_category_intent.csv` — `.csv`
**Non-standard two-row header — see §4.** This is the primary intent signal.

---

### Group C — Accepted by the API but NOT consumed ⚠️

**Do not spend effort on these 12 yet.** They are valid `dataset_key` values, so uploads succeed with HTTP 201 — but **no code reads a single column from any of them.** Uploading them produces no widget and changes nothing on screen.

All are `single_file_csv`, `.csv`, canonical name `<key>.csv` (except `news_events_additional`, multi-file).

| Key | Source A sheet | Note |
| --- | --- | --- |
| `subsidiaries` | `2_Subsidiaries` | Not consumed |
| `funding` | `3_Funding_Overview` / `3_Funding_Rounds` / `3_Advisors` / `3_Investors` | Not consumed |
| `workforce_trends` | `6_Workforce_Trends` | Deliberately excluded — holds role shares, not technologies |
| `company_ratings` | `7_Company_Ratings` | Not consumed |
| `website_traffic` | `8_Website_Traffic` | Not consumed |
| `social_media` | `9_Social_Media` | Not consumed |
| `company` | — | Not consumed |
| `extended_company` | — | Not consumed |
| `connections` | — | Not consumed |
| `subpages` | — | Not consumed |
| `similar_companies` | — | Not consumed |
| `news_events_additional` | — | Not consumed under this key. Files filed under `category: news_events` **are** picked up |

**Decision needed:** either we build consumers for these (tell us which have business value and we will spec columns), or we remove them from the API so an upload cannot silently do nothing. Please confirm which of these you actually intend to deliver before building exports for them.

---

### Group D — Filings

#### 3.13 `compliance_filings` (multi-file) — `.pdf` **only**

The only non-tabular dataset, and the **only source of reported financial figures** (every other file carries a band or a category). Annual reports, exchange filings, monthly market reports.

| Requirement | Detail |
| --- | --- |
| Format | `.pdf` only. Measured in **pages**, not rows |
| **Text layer required** | Pages are parsed from word coordinates. A page with **no text layer (a scanned image) is dropped.** Scanned/photocopied PDFs will not produce evidence — send digitally generated PDFs |
| Multi-file | A filing history is several documents; replacing one must not disturb the others |
| Layout | Two-column and bilingual layouts are handled (split at the vertical gutter); comparative tables are reconstructed with their header row |
| Page count | Must be > 0 or upload is rejected |

#### How a financial figure becomes usable

A number is registered **only when metric + period + value + unit are all recovered together from the same page.** Anything else is skipped and counted as an unbound row. Three rules follow:

1. **The unit must be printed on the page.** A scale word (trillion/triliun, billion/miliar/milyar, million/juta, thousand/ribu) and a currency (`IDR`/`Rupiah`/`Rp`, `USD`, `SGD`, `EUR`, `JPY`) must appear **within 60 characters of each other**. A page that states no unit yields **zero** monetary claims — by design, because an unlabelled number cannot be cited. The standard "expressed in billions of Rupiah" header sentence satisfies this; keep it on every page of tables, not only the first.
2. **Table columns must be year- or month-headed.** Either ≥2 four-digit years (1980–2049), or 1 year plus ≥3 month names. A `Total` column is recognised.
3. **Figures bind by position, never by proximity.** The count of figures in a row must match the number of period columns. Merged cells, footnote markers glued to numbers, or a stray figure will unbind the whole row.

Accepted number formats: comma thousands separators (`323,392`), parenthesised negatives (`(1,234)`), trailing `%`.

> Indonesian-language and interleaved bilingual passages are indexed but never given a citable evidence id — English narrative is what becomes quotable.

---

## 4. `hp_category_intent` — the wide-format exception

This file does not follow the one-header-row rule and needs its own spec. It drives the **primary** intent score.

**Row 1** — category group names, each appearing once above the 10 columns it spans, remaining 10 cells blank:
```
Company,Domain,Run Date,Top HP Category,Top Intent Score (/100),PCs  (Score /100),,,,,,,,,,Workstations  (Score /100),,,,,,,,,,Poly  (Score /100),,,,,,,,,,Printers  (Score /100),,,,,,,,,,3D Printers  (Score /100),,,,,,,,,
```

**Row 2** — field names, repeated per category block:
```
Company,Domain,Run Date,Top HP Category,Top Intent Score (/100),Intent Score (/100),Intent Trend,Buying Stage,Research Volume,Topics Researched,Keywords Matched,Related Technologies,First Intent Date,Latest Intent Date,Geo Source,[...repeats per category...]
```

**Row 3+** — one row per company per run.

### Rules

| Rule | Detail |
| --- | --- |
| Leading columns | `Company`, `Domain`, `Run Date`, `Top HP Category`, `Top Intent Score (/100)` |
| Category blocks | Exactly **5**, in order: PCs, Workstations, Poly, Printers, 3D Printers |
| Block width | Exactly **10** fields, in the order shown |
| Field names | Matched **case-insensitively** (unlike every other file) |
| Accepted category names | `pc`/`pcs`, `workstation`/`workstations`, `poly`/`poly/collaboration`, `print`/`printer`/`printers`, `3d`/`3d printer`/`3d printers` |
| `Intent Score (/100)` | Numeric **0–100** |
| `Buying Stage` | `no signal` (or empty) means no signal; any other value with a score counts as a signal |
| List fields | `Topics Researched`, `Keywords Matched`, `Related Technologies`, `Geo Source` are **pipe-delimited** (`\|`) — *not* comma |
| Empty markers | `` (empty), `-`, `–`, `—`, `n/a`, `na`, `none` all mean empty |
| Encoding | UTF-8 preferred; falls back to Windows-1252 (its em dash `0x97` marks an empty cell) |
| Multiple runs | Several rows per domain is fine — the row with the **greatest `Run Date`** wins. Keep `Run Date` sortable as a string (ISO) |
| Domain match | **Must match `firmographics.Company Domain`** after normalization, or the whole file is ignored for that account |

### Two behaviours to be aware of

1. **`Intent Trend` is not used as a trend.** The file states `Increasing`/`Stable`/`Decreasing`, but with one run and no prior score there is nothing to verify it against. It is kept as the file's own words and never drawn as a direction. Sending a prior-window score would let it become a real trend.
2. **`Top HP Category` is re-checked, not trusted.** The system recomputes the highest-scoring category and reports whether your stated top matches. Inconsistencies surface on screen.
3. **Keyword noise is no longer gated.** The file is the source of truth: its scores and fields are shown and scored exactly as supplied, and the highest-scoring category is always the primary one. A keyword blocklist (`NOISY_CATEGORY_TERMS`) still exists but is **empty by client instruction (Sep 2026)**, so nothing is flagged or barred. Previously `sla` and `identified as competitor of` were flagged; re-adding a term there restores that behaviour for every feature at once.

---

## 5. Open questions for the data team

These are real ambiguities in the current data, in priority order.

### 5.1 `job_openings.status` — empty means "open" ⚠️ highest priority

In the reference file `status` only ever holds `closed` (60%) or **empty** (40%). Code treats `""`, `open`, `active` as open:

```python
OPEN_STATUSES = {"", "open", "active"}
```

So **40% of rows count as open postings** purely because the field is blank — and that number drives hiring-velocity and urgency signals on the Executive Dashboard.

**Please confirm one:** (a) blank genuinely means open → emit `open` explicitly; or (b) blank means unknown → we must stop counting blanks as open.

### 5.2 Three different score scales

| Field | Scale |
| --- | --- |
| `intent_score.Composite Score` | 0–100 |
| `hp_category_intent.Intent Score (/100)` | 0–100 |
| `technology_detections.score` | **0–1** |
| `news_events.confidence` | **0–1 float** |
| `google_news.relevance_confidence` | **Text** High/Medium/Low |

The last two are the same concept (confidence in a news item) on two incompatible scales, and both feed the same news widget. Please either align them or confirm the mapping you intend (e.g. High ≥ 0.8).

### 5.3 Truncated technology lists
`technographics` contains 9 `(+N more)` markers that become literal technology names. Export untruncated.

### 5.4 Empty-but-required fields
`intent_topics.Level Of Intent` and `intent_topics.Topic Count` are empty throughout the reference file, and `Level Of Intent` is a required input. Please supply values and the allowed value set.

### 5.5 Missing `vendor` on `technology_detections`
See §3.10 — detections currently have no technology name.

### 5.6 `5_Tech_Breakdown` columns
`Cms`, `Ssl`, `Web Server`, `Hosting`, `Cdn`, `Framework`, `Analytics` are documented against `webstack` but absent from `webstack.csv`. Which file carries them?

### 5.7 Enum casing
`google_news.event_type` mixes `launch`/`other`/`leadership` with `M&A`. Pick one convention (lower snake_case preferred, matching `news_events.category`).

### 5.8 Twelve datasets accepted but not consumed
See Group C. Confirm which you intend to deliver so we either build consumers or close the keys.

### 5.9 News older than 12 months is discarded
The 365-day gate drops older signals after a successful upload. Confirm this is the intended window before you build a historical back-fill — currently it would be wasted effort.

---

## 6. Which files each feature needs

A feature **produces nothing at all** if any of its listed datasets is registered but unreadable. Use this to prioritise.

| Feature | Required datasets |
| --- | --- |
| Executive Dashboard | `company_hierarchy`, `firmographics`, `job_openings`, `prospect_contacts` |
| Intent & Demand Signals | `intent_score`, `intent_topics`, `job_openings`, `hp_category_intent`, `technographics`, `webstack` |
| Stakeholder Map | `firmographics`, `google_news`, `intent_score`, `news_events`, `prospect_contacts`, `technographics` |
| Technographic Map | `technographics`, `technology_detections`, `webstack` |
| Recent News Signals | `google_news`, `news_events` |
| Content Messaging | `firmographics`, `google_news`, `intent_score`, `news_events`, `technographics` |
| Solution Narrative / Opportunity Map | `firmographics`, `google_news`, `intent_score`, `news_events`, `prospect_contacts`, `technographics` |
| Objection Playbook | `firmographics`, `prospect_contacts`, `technographics` |
| Content Studio | `prospect_contacts`, `job_openings`, `firmographics` |
| Message Evaluator | `firmographics`, `job_openings`, `prospect_contacts` |
| Strategy Chat | All 10: `company_hierarchy`, `firmographics`, `google_news`, `intent_score`, `job_openings`, `news_events`, `prospect_contacts`, `technographics`, `technology_detections`, `webstack` |

**The minimum viable set** (unlocks the most features): `firmographics`, `technographics`, `prospect_contacts`, `intent_score`, `google_news`, `news_events`, `job_openings`.

`compliance_filings` additionally unlocks reported financial figures on the Executive Dashboard.

---

## 7. The six silent failure modes

None of these raises an error, appears in a log the data team sees, or blocks the upload. Each produces a screen that looks "empty" rather than "broken". These are the things worth double-checking before delivery.

| # | Cause | Visible effect |
| --- | --- | --- |
| 1 | Header case/whitespace drift on any column | Column reads as blank; widget shows `N/A` |
| 2 | `firmographics` domain missing or not normalized | **Both** intent widgets go `unverified` / `mismatch` |
| 3 | `intent_topics.Company Website` does not match | **All** Bombora topics discarded |
| 4 | `hp_category_intent` has no row matching the domain | **All** HP category scores discarded — the primary intent signal |
| 5 | Non-ISO dates in `job_openings` seen-at fields | Wrong first/last-seen dates, no error |
| 6 | `DD/MM` vs `MM/DD` ambiguity in news dates | Wrong dates, and the 365-day gate then silently drops the signal |

Failure modes 2, 3 and 4 are all the **same root cause — domain normalization** — and together they account for the entire intent feature. If you check one thing, check that `firmographics.Company Domain`, `intent_topics.Company Website` and `hp_category_intent.Domain` all resolve to the identical bare host.

---

## 8. Per-account delivery checklist

- [ ] All files UTF-8, one header row (except `hp_category_intent`: two)
- [ ] Headers match §3 **exactly** — Title Case, single spaces, no trailing whitespace
- [ ] Domain identical and normalized across every file, matching `firmographics.Company Domain`
- [ ] All dates ISO-8601; timestamps with `Z`
- [ ] `hp_category_intent`: 5 category blocks × 10 fields, pipe-delimited lists, a row whose domain matches firmographics
- [ ] `job_openings.status` explicit (§5.1)
- [ ] `technographics` has no `(+N more)` truncation
- [ ] JSON-array fields are valid JSON (`["full_time"]`, double quotes)
- [ ] `compliance_filings` PDFs have a real text layer (not scans)
