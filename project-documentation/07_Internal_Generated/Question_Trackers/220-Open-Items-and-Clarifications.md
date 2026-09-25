`# HP 220 — Open items and clarifications after your written answers

Date: 25 September 2026
Inputs: your replies to the ten data questions (clarifying opens_1) and to the
decisions list (clarifying opens_2). "Q" numbers refer to the data questions,
"D" numbers to the decisions list.

How to read this document:

- **Part 1** — what is still open, what we need from you, and why.
- **Part 2** — the items you marked "clarification needed": the question
  restated, what we meant, what the data shows, what we need, and what we do if
  we hear nothing.
- **Part 3** — the two items we owed you, answered here.
- **Part 4** — items that were not in the version of the list you answered.
- **Part 5** — every decision already resolved, for the record.

Every rule you gave has been adopted and recorded in the updated decisions
list; Part 5 lists them. Your annotated reply to our 24 Sep email (09:30) and
your 14:43 forward to Sahaj are also reflected here. The open items,
clarifications and Part 4 items are what still need your word. Silence on a
clarification means its stated default applies.

---

## Part 1 — Still open

### 1.1 Deliveries we are waiting on

**O1. Contact data (Q1, D8, D9)**

- Status: open on your side. You said contacts cannot be fetched for every
  account; some accounts get names and details, the rest names or roles only;
  prompts and supporting material will follow.
- What we need:
  1. The file, keyed on domain + company name + country (your own rule).
  2. Which accounts carry real contacts and which carry names or roles only.
  3. Role coverage: is the first file the ~30 buying-committee roles from the
     15 Sep minutes, and does a second round of 5–8 roles follow?
  4. The prompts and supporting material, with a note on which feature each
     one is for.
- Why: five features consume contacts. Without the file none of them runs for
  any account. If a second file follows, all five are regenerated and
  re-tested, so we need to know that before the first run.
- Blocks: Stakeholder Map, Opportunity Map, Objection Playbook, Content
  Studio, Message Evaluator.

**O2. Company Name + Country populated on every PredictLeads row (Q2, D3)**

- Status: you will add the columns.
- What we need: `input_company_name` and `input_country_code` populated on
  **every** row of `job_openings`, `technology_detections`, `news_events`,
  `connections`, `subpages` and `sec_filings`. The columns already exist but
  are populated on 384 of 14,965 job rows (2.6%), and only for the secondary
  entities (Jabil Singapore, the Bangkok branch). The Jabil Malaysia and MUFG
  Japan rows are blank.
- Why: it is the only way to separate the two Jabil and the two MUFG entities,
  and it is the fallback you named for ambiguous domains (Q4) and for shared
  domains in the filings file (D11). Populated on some rows only, the fallback
  fires on some rows only.
- Blocks: hiring, technology, news and connections for Jabil MY/SG and MUFG
  JP/Bangkok; the fallback rule everywhere else.

**O3. Public Bank Berhad records (Q3, Q5, D4, D6)**

- Status: you will try to supply "Public Bank Bhd" rows for the PredictLeads
  file.
- Where it stands: Q3 tells us to use `pbebank.com`; Q5 says the `pbebank.com`
  rows are Public Bank Lao Limited, a subsidiary. Adopting `pbebank.com` today
  would put the Lao subsidiary's hiring and technology on the Malaysian
  parent's page, and Name + Country cannot rescue it because both fields are
  blank on that row. We are holding the domain until the corrected rows arrive.
- What we need: the Public Bank Berhad (Malaysia) rows, and confirmation that
  `pbebank.com` is the key for Explorium, Exa and RSS for this account.
- Blocks: one account, all PredictLeads datasets.

**O4. Re-crawled Exa event dates (Q7, D17)**

- Status: you will crawl the URLs and add dates where possible. Rows still
  undated are skipped, as are the three `1970-01-01` rows.
- What we need: the re-export with dates, and the recovery count (how many of
  the 5,120 undated rows received a date).
- Why: Exa is the only news source for roughly 119 accounts. Under the skip
  rule every undated row disappears; with 56% undated today those accounts
  lose more than half their news. The recovery count tells us what coverage to
  expect before the run rather than after.
- Blocks: Live Signals coverage.

**O5. Job openings for the 45 accounts (Q10, D22)**

- Status: you will aggregate them from another tool in the same format.
- What we need: rows in the `job_openings` layout with company name + country
  on every row, a posted date and a status; and the name of the tool they came
  from, because source reliability differs by tool.
- Why: hiring signals and the hiring driver of the Urgency Score.
- Blocks: hiring widgets and the Urgency Score for those 45 accounts.

**O6. Filings file: two entity questions (D11 follow-up)** — not blocking.

Under the Company Name + Country identity the filings file joins cleanly: 173
of its 187 companies match their account exactly, including 55 of the 60 rows
whose `domain` is a bare country code, an exchange portal or blank. Where a
company name is a variant of one account's name we have mapped it ourselves;
the mapping is in Part 5 for the record. Two rows we cannot place without you:

1. **"Jabil Inc." (SEC filings, country SG).** These are the parent's
   filings. Attach them to Jabil Singapore only, as the row is keyed, or to
   both Jabil accounts? Default: Singapore only.
2. **"Hyundai Motor Group" (DART reports keyed on `hyundai-autoever.com`).**
   Are these Hyundai Autoever's own statutory reports, or Hyundai Motor
   Company's? Default: attached to HKMC Group (Hyundai Autoever), as keyed.

For the record, no answer needed: five companies in the file are not in the
220 and are ignored (Aboitiz Equity Ventures, Universal Robina, Singapore
Airlines, Spark New Zealand, PT Bank Negara Indonesia); the PT United Tractors
document filed under Astra is excluded; and the wrong `domain` and
`global_parent` values on the Fletcher, Fonterra and Astra rows (Part 3, P1)
would be good to correct in the next drop so the domain tie-break cannot
misfire.

### 1.2 Decisions still open on your side

**O7. News precedence when the two feeds disagree (D16).** You marked this
open and forwarded it to Sahaj on 24 Sep (14:43), although Q6 answers it: merge both; where they
disagree on the same event, skip that news item, not the company. We need one
line confirming Q6 stands, and a yes/no on our definition of "same event"
(Part 2, C8).

**O8. Empty-state rule (D39, D10).** Open, with Sahaj since 24 Sep. Your answer to D7 ("nothing to
mention, do not write no hierarchy data") is the only precedent. Proposal:
apply it everywhere. When a source has no data for an account, the section is
left out; no "no data" text appears on screen; the list of absent datasets per
account goes into the run report for QA. Same rule for the Stakeholder Map on
accounts with zero contacts. Need: yes, or a different rule.

**O9. Source labels (D40).** Open, with Sahaj since 24 Sep. Proposal: Firmographics, Technographics,
Hiring, News, Intent, Filings, HP Rulebook, HP case study. News cards show the
publisher name (for example "Nikkei Asia"), never the feed. Vendor names
(Explorium, PredictLeads, Exa, Google News RSS) do not appear on screen. Need:
approve or edit.

**O10. Data as-of date (D41).** Open, with Sahaj since 24 Sep. Proposal: the date of the final
consolidated drop, shown once per account; each dataset's own retrieval date
is kept in the backend record. Need: yes/no.

**O11. GCP (D42).** Open, with Sahaj since 24 Sep. Need: access granted, the project ID, and whether the
Cloud Run region is fixed. After access, a few hours to redeploy and load.

**O12. Items we owed you.** The three names for D14 and the risk-label logic
for D37 are in Part 3. D37 is also with Sahaj since 24 Sep.

### 1.3 Process items from the 24 Sep email thread

**O13. Realistic delivery date (email section 7, point 4).** Not answered.
Need: a date from Dhruvi, Konika and Sahaj that starts from the day the data
and GCP access are in our hands. We commit to a date within hours of that.

**O14. Consolidated drop with a contents list.** Requested in the email and
not answered. Need: the remaining deliveries (O1 to O6) in one drop, with a
list of what it contains and, per C2, whether any correction log is already
applied. The inspection window (D43) is agreed: a late-night drop is checked
the next working morning.

Two small confirmations to include in your next reply:

- `Related Technologies` in `hp_intent_results` is derived from intent
  keywords, not from detecting technology in use. We will surface it as
  "researched technology", separate from the detected-technology list, so a
  company that read about a technology is never recorded as using it. Confirm.
- The Name + Country columns (O2) populated on every row, not merely present.

---

## Part 2 — Clarifications

### C1. D25 — Vendor-flagged rows

**Question as asked.** PredictLeads `review_records` names rows it was not
confident about. Drop flagged IDs before import?

**What we meant.** Your PredictLeads file carries a sheet `review_records`
with 9 rows that your own QA flagged. We did not know whether the flag means
"exclude" or "look at this".

**What the data shows.**

| Rows | Reason, as written in the sheet | Affects |
| --- | --- | --- |
| 1 | Job "Court Decongestion Officer" recruits for Regional Trial Court Branch 70, Taguig; not a Supreme Court vacancy | Supreme Court of the Philippines, hiring |
| 3 | Job descriptions name the NSW Early Learning Commission as employer; not confirmed as Department of Education | Department of Education NSW, hiring |
| 1 | Technology "miso" (Frontend Framework): the job text expands MISO as Management Information Systems Office | Supreme Court of the Philippines, technographics |
| 4 | Duplicate provider profile for the same domain; conflicting source values retained | `company` / `extended_company` rows for `sc.judiciary.gov.ph` and `education.nsw.gov.au` |

**What we need.** Confirm we drop the 5 job and technology rows and merge the
4 duplicate profiles, keeping the master value the log names.

**If we hear nothing.** Dropped and merged, listed in the corrections report.

### C2. D26 — 490 logged corrections

**Question as asked.** Is the delivered file post-correction, or is the log a
to-do list?

**What we meant.** The sheet `quality_changes` lists 490 changes with before
and after values. If the data sheets already carry the "after" values we must
not apply them again (a date restored twice from an Excel serial goes wrong).
If they do not, we have to apply them.

**What the data shows.** 425 "restore date/time from Excel serial", 54 "remove
presentation markup", 4 duplicate-profile merges, 3 NSW employer corrections,
2 title corrections, 2 other. Targets: `technology_detections` 283,
`job_openings` 186, `company` 10, `extended_company` 10, `connections` 1. We
sampled corrected `job_openings` records: every one we could match already
carries the "after" value and none carries the "before". The file looks
post-correction.

**What we need.** One line confirming the sheets are post-correction. For every
future drop, a line in the cover note saying whether the logs are applied.

**If we hear nothing.** Treated as applied; nothing is re-applied.

### C3. D27 — Job status

**Question as asked.** For hiring widgets, label as "postings seen" with the
open count beside it?

**What we meant.** The 16 Sep confirmation covered the Urgency Score: blank and
closed status within 12 months count toward hiring volume. It did not cover
what the hiring widget calls these rows. We cannot call them "open roles"
because the data does not say so.

**What the data shows** (`job_openings`, 14,965 rows):

| Status value | Rows | Within last 12 months |
| --- | --- | --- |
| blank | 8,158 (54.5%) | 4,885 |
| closed | 6,725 (44.9%) | 4,173 |
| verification notes ("Open at retrieval" 28, "No provider closure; current status unverified" 41, and similar) | 82 | 51 |

Only 28 rows are positively marked open.

**What is not in the data.** Whether a blank status means "open" or "not
reported". PredictLeads does not say.

**What we need.** (a) Does blank mean open, or unknown? (b) Approve the widget
label: headline "Postings seen (last 12 months)" = all rows in the window;
beside it "still open" = rows with status open or active, plus blank if you
say blank means open.

**If we hear nothing.** Headline "postings seen"; blank shown as "status not
reported" and not counted as open; Urgency unchanged (blank + closed count, as
confirmed on 16 Sep).

### C4. D34 — "Which five routes?"

**Question as asked.** One recommendation, or five routes each with a verdict?

**What we meant.** The "routes" wording came from the first
recommendation-logic document shared on 15 Sep ("HP 220 account recommendation
logic"). It laid the recommendation out as parallel routes, each carrying its
own verdict, and led with 3D printing in its Astra example. Your 18 Sep file
sheet now marks that document "not used as of now". The case-study file uses a
similar split in its `hp_route` column (3D Printing, Workstations, Print,
PC-Notebook). The Rulebook, guardrail C 06, says the opposite: give one main
recommendation; add another product or service only when separate verified
evidence supports it.

**What we need.** Confirm that C 06 governs and the earlier routes document is
superseded. Then: one primary recommendation per account and feature;
additional ones only where separate verified evidence exists, shown as
secondary with their own evidence; routes with no evidence are not shown at
all (no "not recommended" verdicts on screen).

**If we hear nothing.** As above.

### C5. D35 — "T0 to T3: which feature?"

**Question as asked.** What does each tier mean, and is the case-study file's
T0/T2 the same scale?

**What we meant.** Not one feature; two places.

1. Tuning Logic v4 section F requires a `confidence_tier` on every output
   record, and section C defines three evidence tiers: Opportunity (two
   independent pipelines), Conversation Starter (one strong signal), Context
   Only. We have implemented those three. The T0–T3 numbering came from the
   earlier logic document.
2. The case-study file has a `source_tier` column: T0 on 378 rows, all on
   hp.com properties; T2 on 6 rows, four YouTube links and two on a third-party
   reseller site. There is no T1 or T3 anywhere.

**What we need.** (a) Confirm `confidence_tier` is the three section-C labels
and nothing else. (b) Confirm T0 = HP first-party source and T2 = third-party
source. (c) May T2 studies be cited as proof?

**If we hear nothing.** Section C labels. T0 studies preferred; a T2 study used
only when no T0 study fits the same use case, and labelled with its source.

### C6. D38 — Seat count and the Lifecycle file

**Seat count.** You resolved it: no seller entry; use the data we fully have;
ignore "pending HP input". What we will do: Care Pack rules CARE 18, 19 and 20
need PC seats of at least 250, 1,000 and 5,000. We hold Explorium's `Number Of
Employees Range`. Across the 220 accounts:

| Employee range | Accounts |
| --- | --- |
| 10001+ | 177 |
| 5001–10000 | 17 |
| 1001–5000 | 14 |
| 1000 or fewer | 12 |

Proposal: use the lower bound of the range as a conservative proxy. Lower bound
501 or more: Priority Access eligible. 1,001 or more: Priority Access Plus.
5,001 or more: Priority Management. The output says "based on employee range,
not a seat count", so nobody reads it as a fleet size. The "pending HP input"
items (WXP tier, print licences, scan credits, Poly premium tier) are
recommended at family level with the available tiers and terms listed and no
tier chosen; the word "pending" does not appear on screen.

Need: yes to the proxy, or different thresholds.

**Lifecycle file.** You asked which columns we mean.

The file "HP Lifecycle as of June 2026" has these columns: Platform Family;
Platform Description; Global Series Planned End (PE) Date; Global Series
Planned End (PE) Date / Global Account End of Manufacturing (EM) Date; WW End
of Mfg (EM) or Disco Date; Early Alert date to start transition (*PTT). It has
146 rows. 84 of them carry several dates in one cell, for example
"30/9/2025 / 31 October 2026 / 30 Nov 2026 / 30 June 2027", with nothing saying
which market each date applies to. The copy in the 18 Sep drop is also
password-protected.

What we meant: v4 section J says check the Lifecycle file before surfacing an
offering and do not recommend it after its PE/EM date. Your 18 Sep file sheet
says the Lifecycle file is "not used as of now". We need to know which applies,
and if section J applies, which date is "the applicable PE/EM date" when a
cell holds several.

What we need: (a) is the file in use for this delivery, yes or no; (b) if yes,
which column is the end date, and for multi-date cells which date applies (our
reading: a product is past its end only when its latest date has passed; once
its earliest date has passed it is "approaching"); (c) an unprotected copy.

If we hear nothing: the 18 Sep sheet stands, the file is not used, and no
offering is blocked on lifecycle.

### C7. D18 — Exa dataset key

Your answer ("use domain + company name + country") covered mapping. The
question was about labelling. Today Exa rows are filed under the Google News
key and the screen says "Google News RSS" for all of them. We will add an
`exa` key so each row keeps its origin, and on screen, per O9, news cards
show the publisher name, not the feed. Mapping stays domain + company name +
country as you said. Nothing needed unless you object.

### C8. D16 — What "the same event" means

Needed to apply your Q6 rule. Two rows are the same event when they belong to
the same account (domain + name + country), carry the same event date, and
their headlines match after normalisation. That is how 356 duplicates were
removed. "Disagree" means the same event with different details (amount,
counterparty, date). In that case both rows are skipped and the company keeps
its other news. Rows about the same story under different headlines are not
detected as one event and both appear. Need: yes/no.

### C9. D32 — "Recommendation for HP" on the Technographic Map

Your opens_2 reply pointed to opens_1, which does not cover this item, but your
annotated email of 24 Sep (09:30, section 5.3) answers it: **drop it for now.**
We are removing the card from the Technographic Map for this delivery. If it
is revived later, it will follow your D33 principle: evidence-based per
section, with a Rulebook offering or case study attached only where a match
exists. Nothing needed.

### C10. D23 — Astra

The account missing from the 219 is PT Astra International. Its PredictLeads
data was delivered separately at the start of the engagement and we use that
file. Need: confirm it is the same format and version as the 219 file, or send
the current extract.

### C11. D2 — Entity scope marked "RESOLVED"

Your reply says resolved without naming a choice, so we are recording the
default: each account is the APAC entity named in the account list, and
firmographics are shown as delivered. That means the 141 fields where the
vendor kept the global HQ value stay as delivered (for example Jabil HQ =
Waltham, MA). If you want APAC-entity values there, that is a separate
correction on your side.

### C12. D24 — Duplicate record IDs

Your answer (map on domain + company name + country, not on IDs) covers
mapping. On duplicate rows: a row is removed only when it is identical to
another in every column; two distinct records that happen to share an ID are
both kept. Counts therefore never drop a real record.

---

## Part 3 — Items we owed you

### P1. D14 — The three mis-mapped accounts in `filings 1.csv`

1. **Fletcher Building Holdings New Zealand Limited (NZ).** 4 rows carry
   domain `sunway.com.my` and global parent "SUNWAY HOLDINGS INCORPORATED
   BHD". The documents are Fletcher's own NZX announcements.
2. **Fonterra Co-operative Group Limited (NZ).** 3 rows carry domain
   `uob.com.my` and global parent "UOB Group". The documents are Fonterra's
   NZX announcements.
3. **PT Astra International (ID, labelled "Astra International Group").**
   3 rows carry domain `fifgroup.co.id`, which is Federal International
   Finance, a separate account in the 220, while the documents are Astra's own
   dividend notices. A fourth row has a blank domain and its document is PT
   United Tractors' audited financial statements, a different company.

Under the Company Name + Country identity the first ten rows land on the
right account, so the harm is contained. Please still correct the `domain` and
`global_parent` values so the domain fallback cannot misfire, and remove or
relabel the United Tractors row, which we exclude until then.

### P2. D37 — How the Technographic Map assigns Low, Medium and High Risk

The label is computed in code, not by the model, from the relationship between
what is detected in a category and HP's line in that category:

| Relationship | Meaning | Label |
| --- | --- | --- |
| Compete | another vendor is confirmed in an HP-relevant category | High risk |
| Open opportunity | category need supported, no vendor confirmed (HP whitespace) | Medium risk |
| Complement | HP can work alongside the confirmed technology | Low risk |
| Contextual | no direct HP line in this category | no label |

"Risk" here is the difficulty of HP's position in that category (an incumbent
to displace), not a risk to the customer. It does not use technology age,
end-of-life status or detection confidence.

You forwarded a screenshot of this logic to Sahaj on 24 Sep (14:43) asking
whether it is good to go. The table above is the written version of the same
logic. Ask: keep the labels as they are, rename them to "Competitive position"
(Incumbent / Open / Complementary), or drop them. Default: keep, until you say.

---

## Part 4 — Items not in the version you answered

These were added on 24 Sep after the list went out, so you have not seen them.
Please answer them with the above. Defaults apply if we hear nothing.

- **29a.** When only an integration route is detected (for example Intune),
  show it as a context line ("Intune detected; possible WXP integration route,
  no need evidenced") or not at all? Default: context line, never inside the
  recommendation.
- **29b.** Conditions the data cannot evaluate (seat counts, WXP tier, print
  volumes) are treated as unmet, so an offering can reach "may be relevant" but
  never "relevant". Default: yes.
- **29c.** Use-case vocabulary for case studies: a table from Rulebook
  opportunity type to case-study solution area and tags. We will write it and
  send it for approval. Default: our table until you change it.
- **44.** Four features have no row in the v4 table: Objection Playbook,
  Content Studio, Strategy Chat, Message Evaluator. Today: one case study per
  area card; "Proof Points" section per asset; citations of already-attached
  proof; Rulebook facts only. Default: as built.
- **45.** Case-study proof on Live Signals, Intent & Demand, Stakeholder Map
  (you asked for it in D30) and Technographic Map: for this delivery or after?
  Default: after, on the same matcher.
- **46.** Proof attached to service plays (WXP, Care, Poly, Print) in the
  Opportunity Map, not only hardware plays. Default: yes.
- **47.** Evidence-tier gate on proof everywhere: Rulebook and case studies
  only once an Opportunity is established by two independent pipelines. This
  removes proof from most objection cards on thin accounts. Default: apply it.
- **48.** Region preference: APJ proof for APJ accounts as the second sort key
  after industry. Default: yes.
- **49.** Lifecycle contradiction: see C6.
- **50.** Product-line mapping for case studies by keyword table now, Rulebook
  offering IDs after. Default: yes.

---

## Part 5 — Resolved and adopted, for the record

Everything below is in force as you answered it, listed so that one document
carries the whole picture.

| Ref | Decision as adopted |
| --- | --- |
| D1 | No separate master account list is needed. An account is identified by Company Name + Country, with the PredictLeads canonical domain alongside; the Name + Country columns you are adding to every sheet (O2) are that identifier. |
| Q4, D5 | Canonical domain = PredictLeads domain; overrides `posco.com`, `shell.com.ph`, `corp.shiseido.com`, `stanley.co.jp`; fallback Company Name + Country. A differing domain across vendors does not mean a wrong company. |
| Q2, D3 | Jabil and MUFG pairs stay separate accounts; key = domain + Company Name + Country (columns pending, O2). |
| Q3, D4 | Westpac AU = `westpac.com.au`; Westpac NZ keeps `westpac.co.nz`. |
| D2 | Each account is the APAC entity named in the list; firmographics shown as delivered (see C11). |
| D7 | Accounts without a hierarchy sheet (55): section left out, no "no hierarchy data" text. Ultimate parent: where the Explorium hierarchy sheet carries `Ultimate Parent Name` (165 accounts) it is used; where there is no sheet, the account is its own ultimate parent. |
| D11, D12, D13 | Filings = `filings 1.csv` + PredictLeads `sec_filings`, joined to accounts on Company Name + Country (the account identity), with the domain only as a tie-break; `document_url` first, `source_page_url` fallback, neither = excluded; 186 companies with filings, 31 without; documents from your Drive folder; failed file skipped, not the company; last 12 months. |
| D11 (applied by us) | Filings rows whose company name is a variant of one account's name are mapped to that account, by country: "ANZ Group" (AU) → Australia and New Zealand Banking Group; "IAG Group" (AU) → Insurance Australia Group, (NZ) → IAG NZ Holdings; "BDO Unibank, Inc." → Banco de Oro Unibank; "UOB Group" (MY) → United Overseas Bank (Malaysia); "Westpac Group" (AU) → Westpac Banking Corporation, (NZ) → Westpac NZ; "Fletcher Building Holdings New Zealand Limited" → Fletcher Building Holdings; "Astra International Group" → PT Astra International. Group-labelled rows are split by domain to the member account: "Mitsubishi Group (keiretsu)" → Mitsubishi Electric, Mitsubishi Motors, Mitsubishi Heavy Industries, Mitsubishi Chemical, MUFG; "Sumitomo Group (keiretsu)" → Sumitomo Electric, Sumitomo Corporation, SMFG. Every mapping is listed in the run's corrections report. |
| D15 | Stock-exchange data is the PDFs Konika shared; superseded by the filings sources above. |
| Q6 | Merge Exa and RSS; on a disagreement about the same event, skip the item, not the company (definition in C8). |
| Q7, D17 | Undated Exa rows skipped after the re-crawl; the three `1970-01-01` rows skipped. |
| D19 | 12-month news window kept; the 20-signals-per-account cap removed. |
| D20 | The Low/High relevance columns in both feeds are not used. |
| Q9, D21 | Exa text as the tool returns it; HTML stripped on ingest; corrupted cells shown as delivered. |
| Q10, D22 | Coverage gaps are genuine. Hierarchy: Explorium only. Intent: `hp_intent_results`. Technographics: Explorium plus `WebStack` and `Tech_Breakdown`; `Related Technologies` as a supporting signal. Job openings for 45 accounts to follow (O5). |
| D23 | The 220th account is PT Astra International, PredictLeads data supplied separately (C10). |
| Q8, D24 | Mapping on domain + Company Name + Country, never on record IDs. |
| D28 | PredictLeads `products` feeds recommendations; `sec_filings` per D11; the other unused keys leave the upload contract. |
| D29, email 5.1 | Relevance = use-case/opportunity fit, not name matching. Integration-route match alone = possible fit, not recommended; plus related evidence = "may be relevant / explore fit"; combined evidence meeting the Rulebook conditions = "relevant". A case study is relevant when it supports an opportunity already established; it never creates the need. |
| D30, 21 Sep question | Rulebook and case studies available to all 11 features per your 18 Sep mapping, used only where a relevant signal exists; Stakeholder Map included. |
| D31 | The 89 cleaned case studies are the proof corpus; corrupted figures never shown. |
| D32, email 5.3 | "Recommendation for HP" card on the Technographic Map: dropped for now. |
| D33 | Rulebook and case studies are supporting inputs, not gates. A 3D or workstation recommendation supported by account evidence is generated at the supported opportunity level; a match is attached where one exists, never forced, never suppressed. |
| D36 | Live Signals show the numeric score from the scoring logic; no S/A/B/C tier labels; no minimum score. |
| D38 (seat count) | No seller entry; employee range as the proxy (C6); "pending HP input" items recommended at family level with tiers and terms listed, no tier chosen. |
| D43 | Late-night drops are checked the next working morning. |
| Email 5.4 | JEV: dropped for now; to be scoped after the 220 delivery if at all. |
| Email 5.2, 5.5 | Partial build on incomplete data and the compressed test window: noted by you; no decision taken. |

---

## Summary

| # | Item | Waiting on | Blocks |
| --- | --- | --- | --- |
| O1 | Contact data, role coverage, prompts | BridgeAI delivery | 5 features |
| O2 | Name + Country on every PredictLeads row | BridgeAI delivery | Jabil, MUFG; fallback rule |
| O3 | Public Bank Berhad rows | BridgeAI delivery | 1 account |
| O4 | Exa dates + recovery count | BridgeAI delivery | Live Signals coverage |
| O5 | Job openings, 45 accounts | BridgeAI delivery | hiring, urgency for 45 |
| O6 | Filings: Jabil and Hyundai entity questions | BridgeAI yes/no | 2 accounts' filings (not blocking) |
| O7 | Same-event rule | Sahaj (forwarded 24 Sep) | Live Signals merge |
| O8 | Empty-state rule | Sahaj (forwarded 24 Sep) | UI on every account |
| O9 | Source labels | Sahaj (forwarded 24 Sep) | UI on every card |
| O10 | Data as-of date | Sahaj (forwarded 24 Sep) | snapshot stamp |
| O11 | GCP access, project, region | Sahaj | deployment |
| O12 | Three names and risk-label logic we owed you | answered in Part 3 | — |
| O13 | Delivery date | BridgeAI decision | planning |
| O14 | Consolidated drop with contents list | BridgeAI delivery | inspection window |
| C1–C12 | Clarifications | BridgeAI reply; defaults stated | see each item |
| P1, P2 | Three names; risk-label logic | answered here; P2 also with Sahaj | filings rows; label wording |
| Part 4 | 29a–c, 44–50 | first reply | recommendation surfaces |
`