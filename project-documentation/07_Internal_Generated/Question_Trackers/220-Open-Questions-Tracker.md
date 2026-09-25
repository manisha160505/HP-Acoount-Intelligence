# HP 220 Account Data — Open Questions Tracker

Status as of 25 September 2026, after the client's written answers.

Each item records: what we asked, what they answered, what we are still waiting
on, and what it blocks. An item stays OPEN until the promised data actually
arrives and is checked against the files.

---

## 1. Contact Data — OPEN

**What we asked.** Contact / person data for all 220 accounts.

**What they answered.** Open on their side. Contact data cannot be fetched for
every account. For some accounts they will supply names and available details;
for the rest we will largely be representing roles and names only. They will
also provide prompts and supporting material so the affected features can still
be built.

**Still waiting on.**
- The contact file itself, and the key it joins on (domain, company name, or
  seed ID).
- The prompts and supporting material for the features that depend on it.
- Confirmation of which accounts have real contacts and which will carry names
  or roles only.

**Blocks.** Stakeholder Map, Opportunity Map, Objection Playbook, Content
Studio, Message Evaluator — five features.

**Note.** The contacts sheet is present but empty in all 220 Explorium
workbooks (0 rows), and nothing in the PredictLeads file replaces it. This is
the single largest dependency in the list.

---

## 2. Shared Domains — Jabil and MUFG — OPEN

**What we asked.** Two companies share `jabil.com` and two share `mufg.jp`.
Which entity owns which rows?

**What they answered.** Keep them as separate accounts. Use **Company Name +
Country** alongside the domain as the unique identifier for an account. They
will provide additional Company Name + Country columns in the mentioned sheets
of the PredictLeads data (job openings and the other listed sheets).

**Still waiting on.** The delivery of those populated columns.

**What to confirm when it arrives.** The columns `input_company_name` and
`input_country_code` already exist in these sheets but are populated on only
about 2.6% of rows, and only for the secondary entity (Jabil Singapore, the
Bangkok branch). The primary entities — Jabil Malaysia and MUFG Japan — are
blank. The new delivery needs these fields **populated on every row**, not
merely present, or the four accounts still cannot be separated.

**Blocks.** Job openings, technology detections, news events and connections
for the four affected accounts.

---

## 3. Missing Domains — Public Bank and Westpac — OPEN

**What we asked.** Company Domain is blank for both in Explorium. Please
confirm `publicbankgroup.com` and `westpac.com.au`.

**What they answered.** Use these two domains:
- `pbebank.com`
- `westpac.com.au`

**Westpac — resolved.** `westpac.com.au` is correct for the Australian account.
The New Zealand account is separate and keeps `westpac.co.nz`; their answer
covers AU only, and NZ needs no change.

**Public Bank — still open, and it conflicts with their own answer to item 5.**
Here they tell us to use `pbebank.com`. In item 5 they state that `pbebank.com`
returns **Public Bank Lao Limited**, a subsidiary, and that they will try to
supply the correct "Public Bank Bhd" data. Our account is Public Bank Berhad
(Malaysia).

If we adopt `pbebank.com` now, the Lao subsidiary's hiring and technology data
is attributed to the Malaysian parent account. The Name + Country fallback
cannot resolve it either — both fields are blank on that row.

**Still waiting on.** The corrected Public Bank Berhad data promised in item 5.
Until it arrives we hold the domain rather than adopt the Lao one.

---

## 4. Different Domains Across Vendors — OPEN

**What we asked.** Can a single canonical domain per account be agreed across
vendors, or a stable account ID added to every file? Is there a master account
list?

**What they answered.** For almost every account the domain is the same across
vendors; only a handful differ. There is no master account list yet, but one
can be made once the four accounts below are incorporated.

**Canonical domains to use for mapping:**

| Account | Canonical domain |
| --- | --- |
| Posco Group | `posco.com` |
| Pilipinas Shell | `shell.com.ph` |
| Shiseido | `corp.shiseido.com` |
| Stanley Electric | `stanley.co.jp` |

**How the data was fetched — their clarification.** Neither vendor is queried by
domain:
- **Explorium** is fetched using Company Name + Country plus Explorium's
  business ID; the domain is returned as part of the result.
- **PredictLeads** is fetched using Company Name + Country; the domain comes
  from the resulting company data.
- **News data, including Exa.ai**, uses the domain obtained from PredictLeads.

Therefore a different domain across datasets does not by itself mean the wrong
company was fetched.

**Rule for the final mapping.** Use the canonical domains from the PredictLeads
data, with the four above applied as named. Where domain matching is ambiguous,
fall back to Company Name + Country.

**Still waiting on.** The Company Name + Country columns from item 2. Since 25
Sep, Company Name + Country is the account identity itself, with the canonical
domain alongside, so no separate master account list is needed; this item
closes when the columns land.

---

## 5. Public Bank Entity Mapping — OPEN

**What we asked.** Which company does `pbebank.com` belong to? Exa names it
Public Bank Bhd; PredictLeads names it Public Bank Lao.

**What they answered.** Public Bank Lao Limited is a wholly-owned subsidiary of
Public Bank Berhad, which is why both entities share the domain. They will try
to supply the exact "Public Bank Bhd" data for
`predictleads_combined_219_accounts.xlsx`.

**Still waiting on.** The corrected Public Bank Berhad records.

**Linked to.** Item 3 — that item stays open until this data arrives.

---

## 6. News Sources — Exa and Google News RSS — CLOSED

**What we asked.** Is `exa_data.xlsx` a replacement, a supplement, or a trial?
Should one be authoritative? Which wins on a disagreement?

**What they answered.** Exa is not a replacement. **Merge both feeds.** Most
companies carry roughly 10–15 news articles, so genuine disagreement between
the two sources on the same event should be rare. Where it does happen, **skip
that individual news item — do not skip the company.**

**No further input needed.** This is implementable as written.

---

## 7. Event Dates — OPEN

**What we asked.** Can `event_date` be populated for Exa rows? Can the three
epoch dates (`1970-01-01`) be returned blank?

**What they answered.** They will provide the date wherever possible by
crawling the URLs. Where a date still cannot be recovered, **skip that news row
— do not skip the whole company or account.** The three epoch-dated rows are to
be skipped for now.

**Still waiting on.** The re-crawled event dates.

**Worth requesting alongside the delivery.** The recovery rate. At present
5,120 of 9,221 Exa rows carry no usable date. If the crawl recovers most of
them Exa becomes our strongest news source; if it recovers few, the skip rule
quietly discards more than half of the Exa feed. Knowing which before the run
tells us what news coverage to expect.

---

## 8. Compliance Filings — RESOLVED, with one data correction outstanding

**What we asked.** Which filings source is authoritative? Confirm the account
count and send the list of accounts without filings.

**What they answered (25 Sep).** Use `filings 1.csv` **plus** the PredictLeads
`sec_filings` sheet, merged on domain. Where the domain is the same, use
Company Name + Country to pick the correct rows for the correct company. Use
`document_url` first with `source_page_url` as fallback; exclude records with
neither, because for those accounts no public filings are available (paid or
authenticated registries, family-owned companies, merged or privatised
entities). They confirmed **186 unique company names** and supplied a list of
**31 accounts with no filings**.

They also resolved the documents question: the files themselves are available
at the shared Google Drive folder, and where a file is not downloaded or a link
fails, **skip that file, not the whole company**.

**Verified against the files — their answer holds.**

| Check | Result |
| --- | --- |
| Unique company names | 187 raw, of which one is a duplicate spelling of Singtel → **186 real companies**, as they state |
| 31 no-filings accounts | **None appear in `filings 1.csv`** — the list is consistent |
| Arithmetic | 186 with filings + 31 without = 217, matching our 217 unique accounts |
| Rows with a usable URL | 475 of 505; only **30 rows** excluded under the "neither URL" rule |
| Documents held | `local_path` populated on **504 of 505 rows** — they hold essentially every document |

Of the 31 no-filings accounts, 20 are ministries, defence bodies, police,
courts and government agencies, which genuinely do not file. The stated reasons
match the profile.

**Coverage.** `filings 1.csv` covers 144 of 218 accounts; PredictLeads
`sec_filings` covers 12 (US-listed only: 6-K, 8-K, 10-Q, 20-F), all of which
already appear in `filings 1.csv`. Merged coverage is **144 of 218**.

**Outstanding correction — shared domains are wider than stated.** Their answer
describes the shared-domain case as affecting 2 companies. In the file there
are **5 shared domains covering 21 companies**:

| Domain | Companies | Nature |
| --- | --- | --- |
| `jp` | 10 | Bare country code — Canon, Suzuki, Konica Minolta, Toray, Marubeni, Kawasaki, Nidec, Nippon Express, AEON, Mitsubishi Group |
| `pse.com.ph` | 4 | Exchange portal — San Miguel, Universal Robina, Aboitiz, BDO Unibank |
| `idx.co.id` | 3 | Exchange portal — Bank Rakyat Indonesia, CIMB Group, PLN |
| `singtel.com` | 2 | Genuine company domain, same company spelled two ways |
| `th` | 2 | Bare country code — Bangkok Bank, Bank for Agriculture |

Only `singtel.com` is the case their rule was written for. For the other four,
the `domain` value is not a company domain at all.

**Their Name + Country rule resolves most of this** (re-measured 25 Sep, after
Company Name + Country was agreed as the account identity). Joining the
filings file to the 220 accounts on name + country matches 173 of 187
companies exactly, including 55 of the 60 companies whose `domain` is a bare
country code, an exchange portal or blank. Those rows do not need a domain.

**Handled on our side, logged in the corrections report.** Name variants that
map to exactly one account are aliased: ANZ Group, IAG Group (AU and NZ), BDO
Unibank Inc., UOB Group, Westpac Group (AU and NZ), Fletcher Building Holdings
NZ, Astra International Group. "Mitsubishi Group (keiretsu)" and "Sumitomo
Group (keiretsu)" rows are split by domain to the member accounts. Five
companies not in the 220 are ignored: Aboitiz Equity Ventures, Universal
Robina, Singapore Airlines, Spark New Zealand, PT Bank Negara Indonesia. The
United Tractors document under Astra is excluded.

**Still to ask (not blocking).**
1. "Jabil Inc." SEC filings, keyed SG: Jabil Singapore only, or both Jabil
   accounts? Default: Singapore only.
2. "Hyundai Motor Group" DART reports keyed on `hyundai-autoever.com`:
   Hyundai Autoever's own reports, or Hyundai Motor Company's? Default: HKMC
   Group (Hyundai Autoever), as keyed.
3. Corrected `domain` and `global_parent` on the Fletcher, Fonterra and Astra
   rows in the next drop; they join correctly on name + country today.

**Net position.** Compliance filings moves from blocked to buildable on the
name + country join. Aligning the names above adds filings for up to 14
further accounts. Not blocking.


## 9. Dataset Fallbacks and Coverage Gaps — CLOSED

**What we asked.** Are the coverage gaps genuine no-data cases or partial pulls
that can be re-run?

**What they answered**, dataset by dataset:

**Company Hierarchy** — missing from Explorium only. Use what Explorium
provides.

**Intent Data** — use the separate `hp_intent_results` file already shared. The
columns `Topics Researched`, `Keywords Matched` and `Related Technologies` are
available there.

**Job Openings** — genuinely absent from PredictLeads for **45 accounts**; the
PredictLeads `company` sheet contains all accounts, but the `job_openings`
sheet does not. They will aggregate this data from another tool and deliver it
in the same format. **This part remains OPEN pending that delivery.**

**Technographics** — use the `WebStack` and `Tech_Breakdown` sheets in
Explorium, which also carry technographic data. As a further fallback, the
`Related Technologies` column in `hp_intent_results` may be used.

**Note on the technology fallback.** `Related Technologies` in the intent file
is derived from intent keyword research, not from detecting technology in use
at the company. It should be surfaced as a supporting "researched technology"
signal and kept separate from the detected-technology list, so a company that
read about a technology is never recorded as using it. Worth one line of
confirmation with them.

---

## 10. Duplicate IDs — CLOSED

**What we asked.** Are the duplicate record IDs inside PredictLeads genuine
duplicates or distinct records?

**What they answered.** Do not rely on IDs. Use **Domain + Company Name** for
mapping.

**No further input needed.** This matches how we already key accounts.

---

## Summary

| # | Item | Status | Waiting on |
| --- | --- | --- | --- |
| 1 | Contact data | **OPEN** | Contact file, join key, prompts and supporting material |
| 2 | Shared domains (Jabil, MUFG) | **OPEN** | Company Name + Country populated on every row |
| 3 | Missing domains (Public Bank, Westpac) | **OPEN** | Westpac resolved; Public Bank pending item 5 |
| 4 | Different domains across vendors | **OPEN** | Name + Country columns; master account list |
| 5 | Public Bank entity mapping | **OPEN** | Corrected Public Bank Berhad records |
| 6 | News sources (merge Exa + RSS) | CLOSED | — |
| 7 | Event dates | **OPEN** | Re-crawled dates; recovery rate |
| 8 | Compliance filings | RESOLVED | Jabil and Hyundai entity questions (not blocking) |
| 9 | Dataset fallbacks and gaps | CLOSED | Job openings for 45 accounts still to arrive |
| 10 | Duplicate IDs | CLOSED | — |

**Five open, five resolved.** Items 3 and 4 both depend on deliveries promised
under items 2 and 5, so the critical path is: contact data, the Name + Country
columns, the corrected Public Bank records, the re-crawled event dates, and the
job-openings data for the 45 accounts.

**Smaller items to raise alongside the next delivery**
- The Jabil and Hyundai entity questions on the filings file (item 8).
- Confirmation that `Related Technologies` is a supporting signal, not merged
  into detected technographics (item 9).
- The date-recovery rate from the Exa re-crawl (item 7).
- Name + Country populated on every row, not just present (item 2).
