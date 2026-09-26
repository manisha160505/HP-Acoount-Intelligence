# Evidence Score — Data Availability: Answers from the Corpus

**Status:** answers verified against the code and the live Astra corpus on `feat/Executive-dashboard`, 15 Sep 2026.
Every claim below is traceable to a file path or a line of code. Where the answer is a product decision rather than a
fact, it is marked **DECISION NEEDED** and not guessed at.

**Corpus inspected:** `hp-backend/data/accounts/6aa147b63c29c55e5ed97867/` (Astra), 12 datasets.

---

## The three findings that change the design

Read these before the per-question answers — each invalidates a premise in the proposal.

### Finding 1 — `google_news.event_url` is never a publisher URL

All 12 of 12 rows in the Astra corpus point at `news.google.com`:

```
https://news.google.com/rss/articles/CBMizgFBVV95cUxPT0NPZHEyTHlDdU4xQzR5clZNOTVvOElTMHNPX2xI...?oc=5
```

Domain distribution, whole corpus: `news.google.com` ×12. Nothing else.

These are Google News RSS redirect tokens — an opaque base64 payload, not a redirect to a readable URL. **Domain-based
source classification cannot work on this data.** The controlled `reuters.com → Independent Media` mapping proposed in
Q6 has nothing to bind to.

Equally, `source_publisher` is the literal constant `"Google News RSS"` in all 12 rows — it is the *feed* name, not the
outlet.

### Finding 2 — the publisher that scoring would actually see is derived from the headline suffix

`recent_news_signals.py:144` recovers the outlet structurally from the trailing `" - Publisher"` of a Google News
headline, and that derived value **takes precedence** over the column (`recent_news_signals.py:190`).

Running that exact function over the real corpus:

| event_date | derived publisher | column |
| --- | --- | --- |
| 2026-02-26 | `PT Astra International Tbk` | `Google News RSS` |
| 2025-07-17 | `PT Astra International Tbk` | `Google News RSS` |
| 2025-10-31 | `PT Astra International Tbk` | `Google News RSS` |
| 2023-04-10 | `PT Astra International Tbk` | `Google News RSS` |
| 2024-02-27 | `PT Astra International Tbk` | `Google News RSS` |
| 2021-04-20 | `PT Astra International Tbk` | `Google News RSS` |
| 2022-02-24 | `PT Astra International Tbk` | `Google News RSS` |
| 2026-04-23 | `IDNFinancials` | `Google News RSS` |
| 2026-04-23 | `IDNFinancials` | `Google News RSS` |
| 2026-04-23 | `Tempo.co English` | `Google News RSS` |
| 2023-07-28 | `Halodoc` | `Google News RSS` |
| 2017-04-27 | `Gaadiwaadi.com` | `Google News RSS` |

Note what this means: **7 of 12 "news" rows are Astra's own press releases**, and the derived publisher is the company
itself. Treating those as Independent Media would be wrong. The derived publisher is a *name string with no allowlist
behind it* — `_split_headline_publisher` explicitly claims no outlet vocabulary — so it is a display label, not a
classification key.

### Finding 3 — the evidence pool is already filtered before any scoring runs

Two gates in `recent_news_signals.py` reshape the pool:

- `GATE_MAX_AGE_DAYS = 365` (line 107) — anything older than a year is dropped outright
- `DEDUP_SIMILARITY = 0.85` (line 108) — near-identical headlines merge

Applying the 365-day gate to the real corpus as of today (2026-09-15): **5 of 12 google_news rows survive.** Seven are
already gone before scoring sees them.

This has a direct consequence for the Recency component: **recency is largely pre-decided.** Every row that reaches the
scorer is by construction ≤365 days old. A 25-point recency scale spread over a range the gate has already truncated
will compress into a narrow band. Also note the corpus is capped at `MAX_SIGNALS = 20` per account.

---

## 1. Source URL availability

**Answer: partly available, and one of your assumptions is wrong in our favour.**

| Dataset | URL present? | Evidence |
| --- | --- | --- |
| `compliance_filings` | **No, and none exists upstream** | These are *uploaded PDF files*, not fetched documents. `account_data.py:156` — `allowed_extensions: [".pdf"]`. There is no origin URL because the file arrives as a file. |
| `google_news` | Yes, but useless for sourcing | `news.google.com` redirect tokens only (Finding 1) |
| `news_events` | **No, by design** | `corpus.py` / `recent_news_signals.py:232` — `"source_url": ""` with the comment *"news_events carries no URL column - never fabricate one"* |
| `job_openings` | **Yes — real, usable URLs** | See below |

**`job_openings` does have URLs, contrary to the "No?" in your table.** All 100 rows populated:

```
career.astra.co.id   71
www.linkedin.com     29
```

Example: `https://career.astra.co.id/lowongan/lowongan-detail-page/14787/Engineering%20Manager%20-%20ADMO`

This is the one dataset in the corpus with a genuine, classifiable source domain.

**Is metadata being dropped at ingestion?** No — see §42.

---

## 2. Datasets and their source metadata

Full inventory of the Astra corpus. "Rows" is the real count on disk.

| Dataset | Rows | URL | Publisher | Provider | Document/Record ID | Date field |
| --- | --- | --- | --- | --- | --- | --- |
| `compliance_filings` | PDFs (pages, not rows) | No | No | No | `filing_label` = **filename** | `filing_period` (derived, see §19) |
| `google_news` | 12 | Redirect only | Constant `"Google News RSS"` | No | No | `event_date` (`YYYY-MM-DD`) |
| `news_events` | 43 | **No** | **No** | No | **Yes — `id` (UUID), 43/43 unique** | `effective_date` (22/43), `found_at` (43/43) |
| `job_openings` | 100 | **Yes (100/100)** | Implied by domain | No | `id` (100/100 unique) | `first_seen_at` (100/100), `posted_at` (**0/100 populated**) |
| `firmographics` | 1 | `Website` col | n/a | n/a | `Company ID`, `Business Id` | No |
| `technology_detections` | 100 | No | No | No | `id` | `first_seen_at`, `last_seen_at` |
| `intent_score` | 149 | No | No | No | No (`Topic` only) | No |
| `intent_topics` | 1 | No | No | No | `Business Id` | `Date Stamp` |
| `hp_category_intent` | 2 | No | No | No | No | `Run Date` |
| `technographics` | 1 | No | No | No | No | No |
| `webstack` | 1 | No | No | No | `Business Id` | `Earliest Record`, `Latest Update` |
| `company_hierarchy` | 1 | No | No | No | `Business Id` | No |
| `prospect_contacts` | 23 | LinkedIn URL | n/a | `data_source` | `Prospect prospect_id` | No |

**Unused metadata worth noting:** `news_events.id` is a clean UUID, unique across all 43 rows, and is currently not used
for anything. It is the right deduplication key (§37). `job_openings.url` is likewise unused for sourcing.

---

## 3. Is `google_news.event_url` the original publisher URL?

**Answer: option 3, and worse — it is *always* an aggregator redirect.** 12/12 rows are `news.google.com/rss/articles/...`.

Not "sometimes". Always, in this corpus. Plan for the redirect case as the default, not the exception.

---

## 4. Is `publisher` reliable?

**Answer: no, in both of its forms.**

- The **column** `source_publisher` is the constant `"Google News RSS"` — zero information.
- The **derived** publisher (headline suffix) is a free-text name with no allowlist (`recent_news_signals.py:146`
  states this explicitly). It returns the company's own name for 7/12 rows.

`news_events` has no publisher field at all — `recent_news_signals.py:233` sets `"source_publisher": ""`.

So: publisher cannot be the source identity, and the URL domain cannot either. **Neither proposed mechanism for source
classification is available on the news datasets.** See §9–§11 for what we can do instead.

---

## 5. Publisher vs URL — which is authoritative?

**The conflict you describe cannot occur in this corpus,** because the URL is always `news.google.com` and the column
publisher is always `"Google News RSS"`. There is no disagreement to arbitrate — there is simply no signal.

The existing code already has a precedence rule for the *label*: derived publisher wins over column publisher
(`recent_news_signals.py:190`). If we later ingest a feed with real URLs, I recommend the same shape — **URL domain
wins for classification, publisher string is display only** — because a domain is verifiable and a name is not. But
this is **DECISION NEEDED** and should not be built until a feed with real URLs exists.

---

## 6. Unique publisher domains

Complete list for the current corpus:

**`google_news.event_url`:**
```
news.google.com          (12 of 12 — the entire dataset)
```

**`job_openings.url`:**
```
career.astra.co.id        71
www.linkedin.com          29
```

That is the whole real-domain inventory. The illustrative list in the question (`reuters.com`, `bloomberg.com`,
`idx.co.id`, `bps.go.id` …) **does not correspond to anything in the corpus.** Building a five-category domain map
against it would be mapping imagined data.

---

## 7. Domain normalization

**Answer: no rule exists today, and there is currently nothing to normalize** — two of the three real domains are
already bare, and `www.linkedin.com` is a single fixed form.

If we add classification later, the standard treatment is correct: lowercase, strip `www.`/`m.`/`mobile.`, keep the
registrable domain plus any meaningful subdomain we deliberately want to distinguish (e.g. keep `career.astra.co.id`
separate from `astra.co.id` only if we want careers-vs-corporate to differ; otherwise fold both to `astra.co.id`).

**DECISION NEEDED:** whether `investor.astra.co.id`-style subdomains should collapse into the parent company domain.
My recommendation: collapse for *ownership* (is this the company talking about itself?), which is the question that
actually matters for evidence independence.

---

## 8. Redirects and shortened URLs

**Yes — and it is the norm, not the edge case.** Every `google_news` URL is a Google News redirect carrying an `?oc=5`
tracking parameter.

There is **no canonicalization process today.** Resolving these would require an outbound HTTP fetch per URL to follow
the redirect, which is a real design decision (latency, rate limits, and the fact that Google actively discourages it),
not a parsing change. **DECISION NEEDED** — but note that until it is resolved, no amount of parsing recovers the
publisher from these URLs.

---

## 9. Confirm the source-category list

**Cannot confirm as proposed.** The five categories are reasonable as a taxonomy, but the corpus cannot populate them:

| Proposed category | Can the corpus fill it? |
| --- | --- |
| Regulatory Filings | Partly — `compliance_filings`, but these are annual reports, which are corporate disclosure |
| Official Company Sources | Yes — `job_openings` (`career.astra.co.id`), and the 7 Astra press releases in `google_news` |
| Investor Materials | **No dataset maps to this** |
| Government / Regulator Sources | **No dataset maps to this** — nothing from `idx.co.id` or `bps.go.id` is in the corpus |
| Independent Media | Partly — 4 rows (`IDNFinancials`, `Tempo.co English`, `Halodoc`, `Gaadiwaadi.com`), of which 3 fall outside the 365-day gate |

**Consequence for scoring: a 5×10 = 50-point scale is unreachable.** The realistic ceiling on today's data is 2–3
categories, so every account would score 20–30/50 on Source Diversity regardless of how good its evidence is. The
component would not discriminate between accounts, which defeats its purpose.

**Recommendation:** either reduce to the categories the corpus can actually evidence (Company / Filings / Media = 3),
or re-weight so the achievable range spans the full scale. **DECISION NEEDED.**

---

## 10. Can categories be assigned from the dataset itself?

**Yes — and given Findings 1–2, this is the only mechanism that actually works.** Dataset identity is reliable;
URL and publisher are not.

There is precedent in the codebase: `priorities.py:126` already maps dataset → human label.

```python
DATASET_LABELS = {
    "compliance_filings": "Company filing",
    "google_news":        "News",
    "news_events":        "News",
    "job_openings":       "Job postings",
    ...
}
```

Your proposed mapping is directionally right, with one correction:

- `compliance_filings → Regulatory Filings` — **approximately.** The corpus holds annual reports
  (`2025-Astra-Annual-Report.pdf`, `Astra-Annual-Report-2024.pdf`) and monthly market reports. An annual report is
  corporate disclosure, not a regulator filing. Existing code labels it **"Company filing"**, which is more honest.
- `job_openings → Official Company Sources` — **confirmed**, and now URL-verifiable (71/100 on `career.astra.co.id`).
  Note the LinkedIn 29 are a third-party board, so strictly they are not first-party company sources.

---

## 11. Datasets that don't identify a category (`news_events`)

**Answer: `Unknown` is correct, and you are right not to guess.**

`news_events` has no URL, no publisher, and no provider field. The code is emphatic about not inventing one
(`recent_news_signals.py:232`, comment: *"news_events carries no URL column - never fabricate one"*).

This matches the standing project rule on conservative signals: relabel and flag rather than silently substitute.
`news_events` should contribute to evidence *volume* and *recency* (it has dates) but **must not contribute to Source
Diversity**, because its source is genuinely unknown.

That is 43 of the corpus's ~155 evidence-bearing rows contributing nothing to a 50-point component. Worth weighing when
setting the weights.

---

## 12. Can one source belong to multiple categories?

**Confirmed: exactly one category per source.** Your recommendation is right. Multi-category membership would let a
single source inflate diversity, which is precisely what the component is meant to measure against.

---

## 13. Source category precedence

**DECISION NEEDED**, but it is currently moot — no Investor Materials source exists in the corpus, so the
Official-vs-Investor conflict you describe has no instance today.

If it arises, recommended precedence: **most specific wins** — Investor Materials over Official Company Sources, because
a company's IR output is a narrower, more evidentially meaningful class than its general web presence.

---

## 14. Is `news_events` having no URL permanent?

**Confirmed intentional. Whether it is permanent is a question for the upstream provider, not for us** — the code
choice reflects the data, not the other way round.

Two independent confirmations that it is deliberate:
- `HP-Input-Data-Contract.md:287` — *"`news_events` has no URL column and the code will never fabricate one, so
  `news_events` signals are unlinkable. Only `google_news` carries `event_url`."*
- `recent_news_signals.py:232` — the empty-string assignment with its explanatory comment.

Proceed on the basis that `news_events` source category is unavailable.

---

## 15. Another way to identify the source of `news_events`?

**No join key to a publisher exists.** I checked every column for population across all 43 rows:

Fields that are **always empty** (0/43): `award`, `contact`, `division`, `financing_type`, `financing_type_normalized`,
`financing_type_tags`, `headcount`, `job_title`, `planning`, `recognition`, `vulnerability`.

There is no `source_id`, `publisher_id`, `article_id`, `provider`, or `external_id`. The `id` field is a standalone
UUID (`6b29fed0-aff7-44d5-8ac5-61ff3a549b92`) with no corresponding lookup table in the corpus.

The proposed `news_events.publisher_id → publishers.id → publishers.domain` chain **has no basis in the data.**

---

## 16. Is `filing_label` a true document identifier?

**No — it is the PDF's filename, assigned at upload.**

`corpus.py:782` — `filing_label=file_name`, where `file_name` is the basename of the uploaded file.

So `COUNT(DISTINCT filing_label)` counts *distinct uploaded files*, not distinct documents. Those coincide only if
nobody uploads the same document twice under two names.

---

## 17. Is there a stable filing/document ID?

**No.** I searched the whole of `src/` for `filing_id`, `document_id`, `document_uuid`, `external_id`, and `fiscal` —
**none exist.**

What does exist:
- `filing_label` — the filename
- `page` — the page number within that PDF
- `record_id` — constructed as `"%s#p%s" % (file_name, page)` (`corpus.py:780`), i.e. still filename-derived
- `evidence_id` — format `doc_id#cN`, assigned by the evidence builder (`evidence.py`), stable within an index build
  but not a document identity

**There is no safer identifier than the filename.** If document identity matters for scoring, it needs to be added at
upload — that is a real change, not a field we are failing to read.

---

## 18. Can the same filing have multiple labels?

**Yes — nothing prevents it.** Since the label is the uploaded filename, `2025-Astra-Annual-Report.pdf` and
`Astra_2025_AR.pdf` are two distinct labels for one document, and would count as two filings.

`compliance_filings` is a `multi_file` dataset (`account_data.py:156`), so multiple active files legitimately coexist
and replacement is explicit via `file_id_to_replace` — there is no content-level dedup.

**You are right to flag this.** With a 5-filing cap worth 25 points, a duplicate upload is worth 5 free points. Given
the Astra corpus has only 2 filings (§35), that is a 20% swing on the component from an operator mistake.

---

## 19. Filing date vs filing period

**We have neither a filing date nor a publication date. `filing_period` is reverse-derived from inside the document.**

`corpus.py:783` attaches `filing_period=period`, where `period` comes from `_reporting_periods()` — which maps a
filename to **the highest period found in that document's own financial tables**.

So for `2025-Astra-Annual-Report.pdf`, `filing_period` is something like `FY2025` — recovered by reading the table
column headers, not from any metadata.

`priorities.py:195` documents the intent precisely:

> *"a reported figure knows its own reporting period, a narrative paragraph inherits the period its filing reports, and
> a news row carries a publication date. **Nothing is guessed from a document's name.**"*

**There is no `2026-03-15`-style actual filing date available.** Recency for filings can only use the reporting period.

---

## 20. Fiscal-year-end information

**Not available.** `grep -rn "fiscal" src/` returns nothing. `firmographics.csv` (the company-level dataset) has 21
columns — name, domain, IDs, address, NAICS/SIC, ticker, employee and revenue bands, LinkedIn — and **no fiscal-year
field**.

So converting `FY2025` to a company-specific year-end is not possible from the corpus. It would require either a
per-account fiscal-calendar input or a hardcoded assumption. **DECISION NEEDED** (see §25).

---

## 21. What does `period` mean per dataset?

| Dataset | Field | Semantics |
| --- | --- | --- |
| `compliance_filings` | `period` | **Reporting period of the figure** — the table column header (`FY2025`, `2026-Jul`). Not a date of publication. |
| `compliance_filings` | `filing_period` | The highest reporting period in the source document (§19) |
| `google_news` | `event_date` | Ambiguous — see below |
| `news_events` | `effective_date` | **When the event happened** (22/43 populated) |
| `news_events` | `found_at` | **When the feed discovered it** (43/43 populated) |

On `google_news.event_date`: the contract lists its accepted aliases as `pubDate` and `found_at`
(`HP-Input-Data-Contract.md`, §3.11) — i.e. the field may carry a *publication* date or a *discovery* date depending on
the feed. It is **not** reliably an event-occurrence date. Treat it as "publication date, approximately".

`news_events` is the only dataset that genuinely separates event date from discovery date, and it does so in exactly the
way you describe.

---

## 22. What date should recency use?

Recommended canonical date per evidence type, following the precedence the code already uses
(`recent_news_signals.py:213`: `_parse_date(effective) or _parse_date(found)`):

| Evidence type | Use | Fallback |
| --- | --- | --- |
| `news_events` | `effective_date` (event date) | `found_at` — needed for 21 of 43 rows |
| `google_news` | `event_date` | none |
| `compliance_filings` | `period` / `filing_period` (reporting period) | none — no filing date exists (§19) |
| `job_openings` | `first_seen_at` | **not** `posted_at` — it is 0/100 populated |

Note `posted_at` is empty in all 100 rows of the live corpus (the contract says ~71% empty generally). Do not build on it.

**On event-vs-publication:** prefer the event date where both exist, because the score measures how recent the
*underlying development* is, not how recently someone wrote about it. This matches the existing precedence.

---

## 23. Supported date formats

The parser (`recent_news_signals.py:126`) accepts exactly five, in this order:

1. ISO-8601 (with `Z`)
2. `YYYY-MM-DD`
3. `DD/MM/YYYY`
4. `MM/DD/YYYY`
5. `YYYY/MM/DD`

**Anything else returns `None` and the row is silently dropped.** So of the formats in your question:
`July 2026`, `Jul-2026`, `15-Jul-2026`, `Q2 2026`, `2026-Q2` would all **fail to parse and drop the row**.

⚠️ **`DD/MM/YYYY` is tried before `MM/DD/YYYY`** — so `03/04/2025` reads as **4 March**, not 3 April. Any US-format
feed will be silently misread, not rejected. Worth raising with the provider independently of this work.

Separately, the *financial* period strings inside filings (`FY2025`, `2026-Jul`) are a different vocabulary handled by
`financials.py`, not by this date parser. Don't conflate the two.

Live corpus: all 12 `google_news.event_date` values are clean `YYYY-MM-DD`; all `found_at` are ISO-8601 with `Z`.

---

## 24. What should `2026-Jul` mean?

**DECISION NEEDED** — no normalization rule exists today.

Recommendation: **month-end (`2026-07-31`)** for recency purposes, because a period label denotes the period's coverage,
and the evidence is only complete as of its end. Using month-start would overstate the age of every monthly figure by
up to 30 days.

---

## 25. What should `FY2025` mean?

**DECISION NEEDED**, and blocked on §20 — fiscal-year-end is not available per company.

Options:
1. Assume calendar year-end (`2025-12-31`). Correct for Astra; wrong for any March/June year-end company.
2. Add a per-account fiscal-year-end input to `firmographics`. Correct, but needs an upstream change.
3. Treat `FY` periods as year-granularity only and score recency in years rather than days for filings.

My recommendation is **(3) for now, (2) eventually** — it avoids encoding a silently wrong assumption for non-calendar
companies, which is exactly the failure mode that is hard to notice later.

---

## 26. What happens when a date cannot be determined?

**Important: the row never reaches you.** `_apply_gate` (`recent_news_signals.py:245`) drops rows with an unparseable
date *before* scoring, alongside future-dated and >365-day-old rows.

So for news, `period = NULL` is not a scoring case — it is an upstream drop. For filings and other datasets, the
recommendation is **exclude from the recency calculation rather than score 0**, and surface the exclusion count.
Scoring a missing date as 0 conflates "we know this is old" with "we don't know" — the distinction the project's
conservative-signals rule exists to preserve.

**DECISION NEEDED** on whether an account with no datable evidence shows Recency as `0/25` or `unavailable`.

---

## 27–28. Current time vs frozen `scored_at`

**Recommendation: freeze `scored_at`, and note that the 365-day gate makes this more urgent than it looks.**

With a live clock, evidence silently falls out of the gate as days pass. A row 364 days old is scored today and
*vanishes entirely* tomorrow — so the score changes without the evidence changing, which is the reproducibility problem
you are worried about, in its sharpest form.

There is precedent for freezing in the codebase: `_signals_fingerprint` (`recent_news_signals.py:321`) already exists to
make a signal set identifiable.

**DECISION NEEDED**, but I'd record `scored_at` on the score document and compute all ages against it.

---

## 29. How categories translate into points

The arithmetic is right (1→10, 2→20 … 5→50), but **see §9: the 5-category ceiling is unreachable on this corpus.**
Confirming the formula without re-weighting would ship a component whose real range is 20–30 out of 50.

---

## 30. Do duplicate sources count once?

**Confirmed — yes, and your worked example is right: 20/50, not 40/50.** Category diversity means distinct categories,
so three Reuters articles are one category.

Note the corpus applies its own dedup first (≥85% fuzzy headline match, `recent_news_signals.py:286`), which already
collapses near-identical stories. That dedup is documented as *"lossless on sources"* (line 273) — it keeps each merged
row's URL, publisher and date as a supporting source — so the merged record still carries every contributing source if
we want to count them.

---

## 31. Do multiple publishers in one category increase diversity?

**Confirmed — no. Three independent outlets = 1 category = 10 points.** That follows from the component measuring
category diversity, as you say.

Worth flagging as a product question, though: Reuters + Bloomberg + CNBC is genuinely stronger evidence than one blog,
and this design scores them identically. If that matters, it belongs in a separate corroboration measure rather than
bent into diversity.

---

## 32–33. What makes a filing "relevant", and how is relevance determined?

**There is no filing-level relevance mechanism today.** Relevance is not keyword matching, not manual tagging, and not
a per-filing LLM judgement.

What actually exists is **retrieval-based**: `priorities.py` runs `query.retrieve(account_id, INDEX, PRIORITY_QUESTION,
top_k=60)` over a LightRAG index, and evidence rows come back ranked by semantic relevance to the question. Filings
enter that index as two kinds of chunk (`corpus.py`):

- **financial claims** — one per bound figure, carrying `value`, `unit`, `period`, `page`, `filing_label`
- **narrative sentences** — `field="filing_narrative"`, carrying `page`, `filing_label`, `filing_period`

So "relevant filings" would mean *filings that contributed at least one retrieved evidence row to this catalyst* —
which is a property of the retrieval result, not of the filing.

That is a workable definition and needs no new machinery. **DECISION NEEDED** on whether that is what you intend, because
it makes the count sensitive to `top_k` and to retrieval ranking.

One constraint worth knowing: Indonesian-language and interleaved bilingual passages are indexed but **never given a
citable evidence id** (`HP-Input-Data-Contract.md` §3.13). Only English narrative becomes quotable, which shrinks what a
bilingual filing can contribute.

---

## 34–35. Filing scoring formula and cap

The 5-point-per-filing formula is arithmetically fine. **The cap is the problem.**

**The Astra corpus contains 2 filings** (`2025-Astra-Annual-Report.pdf`, `Astra-Annual-Report-2024.pdf`, plus 7 monthly
car-market PDFs in `docs/` that are market reports rather than company filings).

Under the proposed scale, the flagship account scores **10/25** on Relevant Filings — and no realistic amount of new
data moves it, because a company files one annual report a year. A 5-filing threshold implicitly asks for five years of
history to score full marks on a component meant to measure evidence quality *now*.

**Recommendation: cap at 3 filings = 25 points**, or reallocate as you suggest. Against the real distribution, a 3-cap
discriminates between accounts; a 5-cap mostly reports "not enough filings" for everyone. **DECISION NEEDED.**

---

## 36. Are duplicate evidence rows possible?

**Yes, at two levels:**

- *Within news* — handled. The ≥85% fuzzy dedup merges near-identical headlines, and the contract notes this is
  "expected, not a bug".
- *Within filings* — **not handled.** Re-uploading a document under a different filename produces a second set of
  evidence rows with a different `filing_label` (§18).

The corpus itself is clean on IDs: `news_events` 43/43 unique, `job_openings` 100/100 unique.

---

## 37. Is there a stable evidence ID?

**Yes for news_events; partly for the rest.**

| Level | Identifier | Stability |
| --- | --- | --- |
| Source row | `news_events.id` (UUID), `job_openings.id`, `technology_detections.id` | **Stable and unique — use these** |
| Evidence chunk | `evidence_id` = `doc_id#cN` (`evidence.py`) | Stable within an index build; regenerated on rebuild |
| Filing page | `record_id` = `filename#pN` | Only as stable as the filename |
| `google_news` | **no id column** | — |

**Recommendation: dedupe on the source row `id` where it exists** (as you suggest), falling back to canonicalized
headline for `google_news`, which has no id.

---

## 38. Can different datasets describe the same underlying event?

**Yes, and it demonstrably happens in this corpus.** `google_news` row 3 is *"Astra Financial Report for the Third
Quarter of 2025"*; `news_events` contains `has_earnings` rows for Astra's H1 2026 and 2025 results; the annual report
PDFs contain the same reported figures.

The existing dedup **will not catch this** — it matches headlines within the merged news stream, so a filing and a news
story about that filing survive as two rows, and their text is nothing alike.

**This is a real over-counting risk for both Source Diversity and Relevant Filings,** and it is the one in your list I'd
treat as highest priority. Three representations of one earnings announcement would currently read as evidence from
three categories.

**DECISION NEEDED.** Cross-dataset event resolution is genuinely hard (it needs entity+date+event-type matching) and I
would not build it into v1 — but the scoring should not claim "3 independent sources" when it cannot tell.

---

## 39. How should source independence be handled?

Given Findings 1–2, **we cannot detect syndication at all** — no publisher identity, no resolvable URL, no article body
to compare.

The honest rule for v1 is the simpler one you propose: **different category = different evidence**, with no claim of
independence beyond that. Anything stronger would be asserting a property we have no data to verify.

---

## 40. Can source metadata change after ingestion?

**Yes, and there is no versioning of field values.**

- Files carry a lifecycle status — `active` / `replaced` / `archived` / `deleted` — with `uploaded_at` and `updated_at`
  (`account_data.py`), so *file* replacement is tracked.
- Individual field corrections within a re-uploaded file are **not** diffed or versioned. A changed publisher string
  just becomes the new value on the next ingest.
- Evidence ids are regenerated on index rebuild, so they do not pin a value either.

**For reproducibility, the score document should store the evidence it used** (ids + the field values it scored),
not just the resulting number. Combined with a frozen `scored_at` (§27–28), that makes a score explainable after the
fact even if the corpus moves.

---

## 41. Real sample records

Live rows from the Astra corpus, abridged to the relevant fields.

**`google_news`** (12 rows, columns: `company_name`, `website_domain`, `company_linkedin_url`, `news_announcements`,
`event_headline`, `event_url`, `event_date`, `event_type`, `source_publisher`, `relevance_confidence`,
`coverage_depth_events_per_account_last_12mo`):

```
event_headline   Astra Financial Report for the Third Quarter of 2025 - PT Astra International Tbk
event_url        https://news.google.com/rss/articles/CBMimAFBVV95cUxPS3FyOEk1eGRUSC1oRjFYeGNYTWtNRGFuQTZKRnZ3dzd2ODd4...?oc=5
event_date       2025-10-31
event_type       other
source_publisher Google News RSS
relevance_confidence  High
coverage_depth   12
```

```
event_headline   Astra Women Community: Strong Roles in the Workplace - PT Astra International Tbk
event_url        https://news.google.com/rss/articles/CBMibkFVX3lxTE1vZWdmNVUwanVnU1BGZE1EOWpzYmhOeVFhQUZqSDZ6eTVZ...?oc=5
event_date       2025-07-17        ← 425 days old, DROPPED by the 365-day gate
event_type       other
source_publisher Google News RSS
```

**`news_events`** (43 rows, 30 columns):

```
id               6b29fed0-aff7-44d5-8ac5-61ff3a549b92
category         partners_with
company_domain   astra.co.id
confidence       0.6216
effective_date   2026-08-09
found_at         2026-08-12T00:55:43Z
summary          Astra International partnered with Universitas Gadjah Mada on Aug 9th '26.
article_sentence The ecotourism area is the result of a collaboration between the Astra Honda Motor
                 Foundation, Universitas Gadjah Mada (UGM), and the Klaten Regency Government...
location         Central, Louisiana, United States, Northern America, Americas   ← note: geocoding error
(no url, no publisher — 0/43 rows)
```

```
id               40f3c6df-c967-4663-b462-a75ffb0985ca
category         has_earnings
confidence       0.8504
effective_date   2026-04-01
found_at         2026-07-31T02:10:00Z
amount           IDR 12.53 trillion
amount_normalized 697000000.0
summary          Astra International had earnings of $697M on Apr 1st '26.
```

One with no effective_date (21 of 43 are like this — recency must fall back to `found_at`):
```
effective_date   (empty)
found_at         2026-04-06T06:00:43Z
```

**`job_openings`** (100 rows, 24 columns):

```
id               (unique, 100/100)
title            Engineering Manager - ADMO
url              https://career.astra.co.id/lowongan/lowongan-detail-page/14787/Engineering%20Manager%20-%20ADMO
company_domain   astra.co.id
categories       ["information_technology", "management"]
contract_types   ["full_time"]
first_seen_at    2026-08-27T19:05:13Z
posted_at        (empty — 0/100 populated)
```

**`compliance_filings`** — not rows. Two PDFs; evidence is generated per figure and per narrative sentence:

```
# financial claim chunk
dataset        compliance_filings
field          <metric name>
source_text    "Net revenue for FY2025: 323,392 IDR billion"
value / unit / period   323392 / IDR billion / FY2025
page           14
filing_label   2025-Astra-Annual-Report.pdf
record_id      <table_id>

# narrative chunk
field          filing_narrative
page           27
filing_label   2025-Astra-Annual-Report.pdf
filing_period  FY2025          ← derived from the document's own table headers, not metadata
```

---

## 42. Are we losing metadata during ingestion?

**No. The corpus is not lossier than the source files.** I compared the delivered CSVs against what the code reads, and
the ingestion carries fields through verbatim — `_normalize_signals` is documented as *"Evidence and every source field
are carried through verbatim - nothing here rewrites source text"* (`recent_news_signals.py:168`).

Specifically:

- `news_events` — the source CSV has **30 columns and none of them is a URL, publisher, or provider.** Nothing is being
  dropped; it was never there. (11 of the 30 columns are empty in all 43 rows, which is a separate data-quality point.)
- `google_news` — the CSV's `event_url` *is* the Google News redirect. The aggregator URL is what the provider sends;
  ingestion is not degrading a better URL.
- `compliance_filings` — these are **uploaded PDF files**. There is no upstream record with `document_id` /
  `source_url` / `filing_date` to lose; the file is the whole input.

**Two things are genuinely available and currently unused**, which is the closest thing to your hypothesis:

1. **`job_openings.url`** — 100/100 populated, real domains, not used for source classification anywhere.
2. **`news_events.id`** — a clean unique UUID, ideal as a dedup key, currently unused.

So the answer to your headline question is: **design the scoring around what we have.** The metadata you were hoping to
recover does not exist upstream — with the two exceptions above, which we can start using immediately.

---

## Summary of decisions needed from the product/data owner

These are the ones that block implementation. Everything else above is answered by evidence.

| # | Decision | Why it blocks |
| --- | --- | --- |
| §9 | Final source-category list, given that only 2–3 of the 5 are reachable | 50-point scale doesn't discriminate otherwise |
| §35 | Filing cap: 5 or 3 | Astra has 2 filings; a 5-cap scores every account "insufficient" |
| §25 | `FY2025` → date, without fiscal-year-end data | Recency for all filing evidence depends on it |
| §27 | Frozen `scored_at` vs live clock | 365-day gate makes scores change with no data change |
| §33 | Is "relevant filing" = "contributed a retrieved evidence row"? | No other relevance mechanism exists |
| §38 | Accept cross-dataset over-counting in v1, or defer the component | One earnings announcement can read as 3 categories |
| §26 | Missing date → `0` or `unavailable` | Affects whether the score is comparable across accounts |
| §8 | Resolve Google News redirects (outbound fetch) or accept no publisher | Determines whether §9 is ever reachable |

## Recommended next step

The proposed Source Diversity component is the one that does not survive contact with the corpus — it depends on a
publisher identity that does not exist in either of the news datasets. Before building, I'd suggest either:

- **re-weighting** toward what the data supports (dataset-implied categories per §10, evidence volume, and the filing
  and recency components, which are sound), or
- **going back to the news provider** for a feed with resolved publisher URLs, which would make the original design
  viable as written.

Worth deciding which before the scoring logic gets written, since the two lead to different implementations.
