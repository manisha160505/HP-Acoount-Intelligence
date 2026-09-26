# 220-Account Source Data: Questions for the Data Provider

Findings from splitting the four source workbooks into per-account datasets and
validating the result. Every item below was verified against the source files,
not inferred.

Counts refer to: `explorium_clean_220/` (220 workbooks),
`predictleads_combined_219_accounts.xlsx`, `google_news_rss_data 1.xlsx`,
`exa_data.xlsx`.

**Priority:** items 1–4 block or distort delivery. Items 5–9 are quality issues
we can work around but should be fixed at source. Item 10 is a clarification.

---

## 1. Prospect contacts are missing entirely — 0 of 220 accounts

**BLOCKER.**

Sheet `14_Prospect_Contacts` is present in all 220 Explorium workbooks and
contains no rows in any of them. Every file returns the placeholder header
`No data available`.

```
Explorium workbooks with contact rows:  0 / 220
```

Five product features depend on contacts: Stakeholder Map, Solution Narrative
& Opportunity Map, Objection Playbook, Content Studio and Message Evaluator.
Without this dataset those features cannot be generated for any account.

**Questions**

- Is contact data expected in the Explorium export, or is it delivered
  separately (e.g. the Apollo extract)?
- If separate: when can we expect it, and keyed on what — domain or company ID?
- Was the export run with contacts excluded by licence or by filter?

---

## 2. Two different companies share one domain — data would be misattributed

**BLOCKER.** Two pairs of distinct companies carry an identical
`Company Domain`, and all three vendors key their rows on that domain:

| Domain        | Company                                               | Country   |
| ------------- | ----------------------------------------------------- | --------- |
| `jabil.com` | JABIL CIRCUIT SDN BHD                                 | Malaysia  |
| `jabil.com` | JABIL CIRCUIT (SINGAPORE) PTE LTD                     | Singapore |
| `mufg.jp`   | MITSUBISHI UFJ FINANCIAL GROUP, INC.                  | Japan     |
| `mufg.jp`   | THE BANK OF TOKYO-MITSUBISHI LIMITED (BANGKOK BRANCH) | Thailand  |

Filtering by domain returns the same rows for both companies in each pair. Left
unhandled this puts Malaysia's job openings on Singapore's account page, and
Japan's technology stack on the Bangkok branch's, as fact.

Measured duplication when filtering purely on domain:

```
job_openings            +314 rows
technology_detections   +204 rows
connections             +202 rows
news_events             +201 rows
subpages                +197 rows
```

Nothing in either vendor's schema distinguishes the two entities, so we cannot
split the rows ourselves. **Interim handling:** all rows go to one account per
pair (Jabil Malaysia, MUFG Japan) and the other gets none — an account with no
data is safer than an account with another company's data. This means Jabil
Singapore and the Bangkok branch are currently near-empty.

**Questions**

- Can the vendors supply a per-entity identifier (registration number, LinkedIn
  company ID, or a site-specific domain) so the rows can be separated?
- Should the two Jabil entities and the two MUFG entities be treated as one
  account each instead of two?
- If they stay separate, which entity should own the shared-domain rows?

---

## 3. Company Domain is blank for two accounts

**BLOCKER for those accounts.** `Company Domain` is empty in
`1_Firmographics`, though `Website` is populated:

| Workbook                           | Company Domain | Website                             | Country   |
| ---------------------------------- | -------------- | ----------------------------------- | --------- |
| `PUBLIC_BANK_BHD_MY`             | *(blank)*    | `https://www.publicbankgroup.com` | Malaysia  |
| `WESTPAC_BANKING_CORPORATION_AU` | *(blank)*    | `https://www.westpac.com.au`      | Australia |

Because every other dataset joins on domain, a blank value means the account
receives nothing from the other three workbooks. Westpac AU went from 2 to 23
of 25 datasets once the domain was recovered from `Website`.

**Questions**

- Please populate `Company Domain` in the next delivery.
- Can you confirm `publicbankgroup.com` and `westpac.com.au` are the correct
  values? We are currently deriving them and would rather not guess.

---

## 4. Vendors disagree about which domain represents a company

**BLOCKER — silent data loss.** For four accounts, Explorium and
PredictLeads/News use different domains for the same company. A domain join
therefore returns nothing, and the account looks like a coverage gap rather
than a mismatch:

| Company          | Explorium                  | PredictLeads / News      |
| ---------------- | -------------------------- | ------------------------ |
| Posco Group      | `posco-inc.com`          | `posco.com`            |
| Pilipinas Shell  | `pilipinas.shell.com.ph` | `shell.com.ph`         |
| Shiseido         | `corp.shiseido.com`      | `shiseido.co.jp`       |
| Stanley Electric | `stanley.co.jp`          | `stanley-electric.com` |

We have mapped these four explicitly. The concern is the ones we have not
found: this only surfaced because rows in the combined workbooks matched no
account at all.

**Questions**

- Can a single canonical domain per account be agreed across vendors, or a
  stable account ID be added to every file?
- Is there a master account list with the agreed domain for all 220?

---

## 5. `pbebank.com` is labelled as two different companies

The same domain is named differently by two vendors:

| Source                                      | Company name                |
| ------------------------------------------- | --------------------------- |
| `exa_data.xlsx`                           | `PUBLIC BANK BHD`         |
| `predictleads_combined_219_accounts.xlsx` | `Public Bank Lao Limited` |

Public Bank Bhd (Malaysia) and Public Bank Lao are different entities. We are
currently attaching the 43 news rows (which name Public Bank Bhd) and
withholding the PredictLeads rows (which name Public Bank Lao).

**Question**

- Which company does `pbebank.com` belong to? This is a one-line fix once
  confirmed — we just will not guess between two banks.

---

## 6. Two news feeds with very different coverage, and no stated relationship

`exa_data.xlsx` and `google_news_rss_data 1.xlsx` have **identical column
schemas** but different coverage:

| File                            | Rows  | Distinct domains |
| ------------------------------- | ----- | ---------------- |
| `exa_data.xlsx`               | 9,221 | 215              |
| `google_news_rss_data 1.xlsx` | 7,913 | 99               |

Neither is a superset. We have merged both and de-duplicated on
domain + headline + date (356 duplicate rows removed), which took news coverage
from 103 to 220 accounts. Had we used only the RSS file — the one that looks
canonical by name — 119 accounts would have had no news at all.

**Questions**

- Is `exa_data.xlsx` a replacement for the RSS file, a supplement, or a trial
  export?
- Is merging both correct, or should one be authoritative?
- Which should win when the two disagree on the same event?

---

## 7. 56% of Exa news rows have no event date

```
exa_data.xlsx rows with blank event_date:  5,120 / 9,221  (56%)
google_news_rss_data blank event_date:         0 / 7,913  (0%)
```

Undated news cannot be placed on a timeline, aged out, or used for recency
scoring, so more than half the Exa feed is unusable for any time-based signal.

Separately, 3 rows in the RSS feed carry `1970-01-01` — the Unix epoch, which
is a missing timestamp rendered as a date rather than left blank:

```
TDK CORPORATION                 The Future of AI: How Will ChatGPT Change ...
ERNST&YOUNG                     How an AI application can help auditors ...
GOVERNMENT TECHNOLOGY AGENCY    International collaboration - tech.gov.sg
```

These will sort as each account's oldest news item.

**Questions**

- Can `event_date` be populated for the Exa rows, or is publication date
  genuinely unavailable from that source?
- Can the three epoch dates be returned as blank rather than `1970-01-01`?

---

## 8. Duplicate record IDs inside PredictLeads' own tables

`id` is expected to be unique per record but is not:

| Sheet                     | Duplicate IDs | Total rows |
| ------------------------- | ------------- | ---------- |
| `technology_detections` | 715           | 17,799     |
| `news_events`           | 68            | 14,289     |
| `subpages`              | 10            | 15,163     |
| `job_openings`          | 2             | 14,965     |

These are duplicated in the delivered file, before any processing on our side.
Counting detected technologies or news events will over-count unless we
de-duplicate — and doing that ourselves risks dropping legitimately distinct
records that happen to share an ID.

**Questions**

- Are these genuine duplicates to be removed, or distinct records with a
  reused ID?
- If duplicates: can they be removed at source, or is there a field that
  distinguishes them?

---

## 9. Corrupted non-Latin text in the Exa export

28 cells contain U+FFFD replacement characters — text that was decoded with the
wrong encoding somewhere upstream. The original characters are unrecoverable
from the delivered file.

Mostly Thai, in `event_summary` (26 cells), `news_announcements` and
`event_headline`. Example, domain `gsb.or.th`:

```
การรายงานตามหลััักการ ธนาคารที่่่�� รัับผิิิดชอบ ประจำำ ปีี 2566
```

Note also the doubled vowel marks, which suggests a normalisation problem in
addition to the replacement characters.

Separately, 73 output files carry raw HTML fragments (`<br>`, `&nbsp;`) inside
text fields, which will render literally unless stripped.

**Questions**

- Can the Exa export be re-run with UTF-8 throughout?
- Should HTML be stripped at source, or should we strip it on ingest?

---

## 10. Coverage gaps — please confirm these are expected

Datasets missing for a material number of accounts. We are treating these as
source-coverage facts rather than errors, but want that confirmed:

| Dataset                        | Accounts with data | Missing          |
| ------------------------------ | ------------------ | ---------------- |
| `company_hierarchy`          | 165 / 220          | 55               |
| `intent_score`               | 173 / 220          | 47               |
| `intent_topics`              | 173 / 220          | 47               |
| `job_openings`               | 175 / 220          | 45               |
| `technographics`             | 207 / 220          | 13               |
| `news_events` (PredictLeads) | 213 / 220          | 7                |
| `technology_detections`      | 216 / 220          | 4                |
| `prospect_contacts`          | **0 / 220**  | 220 (see item 1) |
| `compliance_filings`         | **0 / 220**  | 220 (no feed)    |

Also note the file is named `predictleads_combined_219_accounts` while
Explorium supplies 220 workbooks.

**Questions**

- Which account is absent from the PredictLeads set, and why?
- Are the gaps above genuine no-data cases, or partial extractions that could
  be re-run?
- Is `compliance_filings` (annual reports, exchange filings) in scope? Five
  features depend on it and no feed exists today. Reported financial figures
  come from this dataset.

---

## Summary

| #  | Issue                                | Severity | Blocks                |
| -- | ------------------------------------ | -------- | --------------------- |
| 1  | Prospect contacts empty (0/220)      | Blocker  | 5 features            |
| 2  | Two companies share one domain       | Blocker  | 2 account pairs       |
| 3  | Blank Company Domain                 | Blocker  | 2 accounts            |
| 4  | Vendor domain mismatches             | Blocker  | 4 accounts confirmed  |
| 5  | `pbebank.com` identity conflict    | High     | 1 account             |
| 6  | Two news feeds, unclear relationship | High     | news for 119 accounts |
| 7  | 56% undated news + epoch dates       | High     | time-based signals    |
| 8  | Duplicate IDs in source              | Medium   | counts over-report    |
| 9  | Corrupted text and HTML              | Medium   | 28 cells, 73 files    |
| 10 | Coverage gaps                        | Confirm  | varies                |

Items 2, 3, 4 and 6 are currently handled with explicit, documented rules on our
side, all recorded in the run's corrections report. Items 1 and 10 cannot be
worked around — the data either arrives or those features do not ship.
