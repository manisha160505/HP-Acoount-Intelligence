> GENERATED CATALOGUE — produced 25 Sep 2026 by an automated read of the internal documents. INTERNAL working aid; verify quotes against the files in this folder before relying on them.

# C. Internally generated documents: catalogue and analysis

Project: HP 220-Account Intelligence. Client: BridgeAI Tech (Dhruvi Patel, Konika Thakur, Sahaj Khunteta). Delivery team: Yogesh Yadav, Manisha Parwani, Palash Chatterjee, Manil Tongya, Anvesha Mittal, Pritesh.
Prepared 25 Sep 2026. Every file listed was read in full. Nothing in /Users/yogeshyadav/Desktop/HP was modified.

Abbreviations used below:
- **DQ**: 220-Account-Data-Questions-For-Client (Q1 to Q10)
- **DL**: 220-Open-Decisions-List (D1 to D53)
- **OI**: 220-Open-Items-and-Clarifications (O1 to O14, C1 to C12, P1 and P2)
- **TR**: 220-Open-Questions-Tracker (T1 to T10, which follow Q1 to Q10)
- **AG**: HP-220-Account-Data-Review-Agenda (Ag1 to Ag11)
- **O3 / C3 / U3**: clarifying_opens_3 OPEN / CLARIFICATIONS / UNRESOLVED. A **v2** suffix means the merged version.
- **opens_1 / opens_2**: BridgeAI's written replies. They are Dhruvi's docx files (`clarifying opens_1  Dhruvi.docx`, `clarifying opens_2.docx`), whose docProps name "Dhruvi Nilam Patel" as author, edited 24 Sep. They are client documents and are not catalogued here.

Times are local (IST) unless marked Z (UTC).

---

## 1. Catalogue table

| # | File | Local path | Author (evidence) | Date | Purpose | Type | Sent to client? |
|---|---|---|---|---|---|---|---|
| 1 | 220-Account-Data-Questions-For-Client.md | /Users/yogeshyadav/Desktop/HP/NewDocs/ | Delivery team, Yogesh. The text reads "Findings from splitting the four source workbooks"; the email draft calls it "Our full review". | mtime 23 Sep 22:11 | Ten data-quality questions from splitting the 220-account drop | Question list | **Yes.** The email draft's timeline says: "24 Sep, 12:26 AM: Our full review of the 220-account dataset sent (220-Account Data Questions…)". The attachment line reads "(sent last night)". BridgeAI answered it as opens_1. The mtime is 23 Sep, but the send time was 00:26 on 24 Sep. |
| 2 | 220-Open-Decisions-List.md | /Users/yogeshyadav/Desktop/HP/NewDocs/ | Delivery team, Yogesh. Committed as `df4ca9b6` by Yogesh Yadav on 24 Sep 23:17. | Items 1 to 43 sent 24 Sep. The working copy has **uncommitted** "Status" edits (+90 lines), "Status as of 25 September", mtime 25 Sep 01:06. | Decision list (question, default, affects) that becomes the spec for the run. It now also serves as the status register. | Question list / tracker | **Yes for items 1 to 43.** BridgeAI answered them in opens_2 ("43 questions" per opens_3). Items 29a to 29c and 44 to 53 are marked "NOT YET ASKED" or come "From the 24 Sep email thread". Whether the 25 Sep status version was sent is unknown. |
| 3 | 220-Open-Items-and-Clarifications.md | /Users/yogeshyadav/Desktop/HP/NewDocs/ | Delivery team, written in the second person to BridgeAI ("your replies"). The file starts with a stray backtick. | "Date: 25 September 2026"; mtime 25 Sep 01:06 | Client-facing follow-up after opens_1 and opens_2, in five parts: open items, clarifications, items we owed, items not yet asked, resolved decisions | Q&A / clarification letter | **Unknown.** It is written to be sent. Project memory says Manisha's clarifying_opens_3 files are "the vehicle", and nearly all of this content was merged into the v2 files. No evidence that it was sent on its own. |
| 4 | 220-Open-Questions-Tracker.md | /Users/yogeshyadav/Desktop/HP/NewDocs/ | Delivery team, internal. It speaks of the client in the third person ("What they answered"). | "Status as of 25 September 2026" | Internal tracker of the answers to Q1 to Q10 (opens_1) | Tracker | **No.** It is an internal register. |
| 5 | BridgeAI-email-draft-2026-09-24.md | /Users/yogeshyadav/Desktop/HP/NewDocs/ | Delivery team, signed "Best regards, Yogesh". Addressed to Dhruvi, Konika and Sahaj, with the delivery team cc'd. | 24 Sep; mtime 24 Sep 10:15 | Escalation and status email: data still pending, GCP access, open logic points, Option A/B for approach ownership, asks | Draft email | **Yes, in some form.** DL, OI and O3 v2 cite "our 24 Sep email" and "Dhruvi's annotated reply to our 24 Sep email (09:30)", and quote its sections 5.1, 5.3, 5.4 and 7.4, which match this draft's numbering. The exact wording sent is not confirmed. |
| 6 | Evidence-Score-Data-Availability-Answers.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team. Heavy code citations (`recent_news_signals.py:144`). Committed as `8a8687e9` "Evidence Strength: a computed score for each catalyst" by Yogesh. | "15 Sep 2026" (header and commit) | Answers a questionnaire on an Evidence Score proposal (source diversity, filings, recency) against the Astra corpus | Q&A / analysis | **Unknown.** It answers "your proposal" / "your table" and ends with "decisions needed from the product/data owner". The recipient is not named. |
| 7 | HP-Input-Data-Contract.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team. "Audience: Data team producing the per-account file set". Committed by Yogesh on 16, 23 (twice) and 24 Sep. | Created 16 Sep; last committed 24 Sep 00:16 (`3d81b077`) | As-built input contract: 25 dataset keys, the columns read, formats, silent failure modes, open questions | Spec | **Unknown.** It is written for BridgeAI's data team, but no send is recorded. DL item 18 refers to "the input contract". |
| 8 | 2026-09-14-feature-walkthrough.md | /Users/yogeshyadav/Desktop/HP/docs/meeting-notes/ | Delivery team, internal. "internal walkthrough transcript… Palash presenting to Manisha, Anvesha and Yogesh". Committed as `e3103bcd` on 14 Sep. | 14 Sep | Notes and implementation plan per feature, plus the GraphRAG decision | Meeting notes | **No** (internal). |
| 9 | QA-Report-Response_2026-09-16.md | /Users/yogeshyadav/Desktop/HP/docs/qa/ | Delivery team. "Prepared: 16 September 2026". Commit `8437f68a`. A PDF export sits alongside it. | 16 Sep | Finding-by-finding response to the HP Sea Limited QA report (FIXED / ALREADY CORRECT / OPEN / BLOCKED ON DATA) | QA report (response) | **Unknown.** It is addressed to the QA owner ("Open points needing your decision"). A PDF export exists (docs/qa/…pdf), but no send is recorded. |
| 10 | QA-Discussion-Points_2026-09-16.md | /Users/yogeshyadav/Desktop/HP/docs/qa/ | Delivery team. "Points We Need To Discuss With QA". Committed on 18 Sep (`064043a8`). A PDF export exists. | Named 16 Sep; mtime 21 Sep | Plain-language list of the 12 QA items not fixed, with asks | Question list | **Unknown.** It is written to the QA party ("from your side"). A PDF exists. |
| 11 | api-envelope.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (Yogesh commit `8b3fde81`, 16 Sep) | 16 Sep | Defines the uniform `{success, data, error, meta}` response envelope. The frontend axios interceptor unwraps it, so no call site changed. | Engineering doc | No |
| 12 | api-errors.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (commit `8b3fde81`, 16 Sep) | 16 Sep | API error contract (`error.code`, `request_id`, `fields`). `detail` stays a plain string for 16 frontend call sites. | Engineering doc | No |
| 13 | linting.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (16 Sep) | 16 Sep | Backend Ruff lint gated on push through version-controlled git hooks. CI re-runs it. Frontend is covered by `tsc --noEmit`. | Engineering doc | No |
| 14 | observability.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (commit `75231a01`, 16 Sep) | 16 Sep | Structured JSON logs, optional OpenTelemetry traces and metrics, Cloud-Logging-compatible fields, and alerts to create | Engineering doc | No |
| 15 | observability-backlog.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (16 Sep) | 16 Sep | Deferred work, e.g. 71 of 79 `HTTPException` sites still to migrate. Records that the `GET /api/v1/features` 500 is resolved. | Engineering doc | No |
| 16 | branch-protection.md | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (commits on 16 Sep and 24 Sep) | 16 Sep, updated 24 Sep | `main` accepts PRs only: a local pre-push hook plus GitHub branch protection, which is the real control | Engineering doc | No |
| 17 | mails (1).txt | /Users/yogeshyadav/Desktop/HP/docs/ | Mixed, **mostly client-authored**: a pasted Gmail thread with Dhruvi (22 and 24 Aug), Konika (undated ~3 Sep, then 31 Aug) and Palash (26 Aug). The relative stamps ("12 days ago") suggest it was pasted around 3 Sep. | 22 Aug to ~3 Sep 2026 | Project kickoff thread. See the summary in section 2. | Mail dump | n/a (these are the emails themselves) |
| 18 | hp-input-contract.json | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (generated from code). `generated_at: 2026-09-15`. Commits on 16 and 23 Sep. **Uncommitted edits** in the working tree. | 15 Sep; mtime 23 Sep 16:47 | Machine-readable version of the input contract | Spec (JSON) | Unknown |
| 19 | hp-file-to-json-map.json | /Users/yogeshyadav/Desktop/HP/docs/ | Delivery team (generated). `generated_at: 2026-09-15`, "verified_against: ingestion source code and the reference account files". | 15 Sep | For each uploadable file: the JSON it produces, where that JSON is stored, and which features need it | Spec (JSON) | Unknown |
| 20 | HP-Account-Intelligence-Handover (.docx; text at scratchpad/text/HP-Account-Intelligence-Handover.txt) | /Users/yogeshyadav/Desktop/HP/docs/HP-Account-Intelligence-Handover.docx | Delivery team. python-docx generated; lastModifiedBy "KHUSHBOO PARWANI". The content describes the team's own code paths. | docx modified 10 Sep 06:53Z; file mtime 14 Sep | Handover: what the system is, the status of the 11 features, the dataset-to-feature map, and where code lives | Spec / handover | Unknown |
| 21 | HP-220-Account-Data-Review-Agenda (.docx; text at scratchpad/text/HP-220-Account-Data-Review-Agenda.txt) | /Users/yogeshyadav/Desktop/HP/NewDocs/HP-220-Account-Data-Review-Agenda.docx | Delivery team. Header "BridgeAI / Movozane"; "We have reviewed all 226 files in the new drop". | "23 September 2026"; docx created 23 Sep 05:35Z | Agenda of 11 items for the 23 Sep data-review call | Question list / agenda | **Likely, not confirmed.** It is an agenda for the 23 Sep BridgeAI call (email draft: "23 Sep, 3:51 PM: Call"). There is no explicit send record. |
| 22 | HP_Platform_Gap_Analysis (.docx from ~/Downloads; text at scratchpad/text/HP_Platform_Gap_Analysis.txt) | ~/Downloads/HP_Platform_Gap_Analysis.docx | **Delivery team.** The content reads "The client sent 11 new documents… what the platform already does today… Decisions for us rather than the client… No code has been changed". docProps show "python-docx". Spotlight WhereFrom is web.whatsapp.com, so it was received by WhatsApp, probably from a teammate. | "18 September 2026"; mtime 18 Sep 15:57 | Review of the client's 11 new documents: the Rulebook, logic deck, scoring docs, case studies, Q426, Care Pack, filings, Lifecycle, Wolf, HP IQ | Analysis | **Unknown.** It contains "Questions we need answered", but no send is recorded. Its questions reappear as D33 to D35 and D38 in DL. |
| 23 | HP_Account_Intelligence_FINAL_Remediation_Checklist (.pdf from ~/Downloads; text at scratchpad/text/…Remediation_Checklist.txt) | ~/Downloads/HP_Account_Intelligence_FINAL_Remediation_Checklist.pdf | **Generated with ChatGPT** (Spotlight WhereFrom `https://chatgpt.com/`) from an internal engineering review. The subtitle reads "Consolidated from the engineering review + modularity analysis". The content audits the delivery team's own repo: committed JWT secret, git stash, `.bak` files. The operator is most likely the delivery team, but that is not stated. | PDF created 15 Sep 07:34Z | 51-item fix list: 10 BLOCKER, 18 HIGH, 16 MEDIUM, 7 LOW (the header counts; items 45 to 51 are appended out of order) | Engineering review / checklist | **No evidence it was sent.** Internal. |
| 24 | HP_Sea_Limited_QA_Report_2026-09-15_0513_1_ (.docx from ~/Downloads; text at scratchpad/text/…) | ~/Downloads/HP_Sea_Limited_QA_Report_2026-09-15_0513 (1).docx (plus .pdf and "latest.pdf" copies) | **Generated tool output.** "4-Step Feature Evaluation Report", "Run at: 2026-09-15T05:13:15.164Z", and it includes an "Independent Groq evaluation". docProps author "Un-named". Received via WhatsApp. It audits the **deployed** site. Its Windows-style paths (`Stock exchange sample data\…`) show it ran on a Windows machine. Its checks refer to "Konika's news dataset" and "Dhruvi's follow-up email requirement". **Who ran the validator cannot be determined from the content.** Project memory says its source is not on this machine. | Run 15 Sep 05:13Z | Automated structural, deep, evidence and suggestion audit of all 11 features for account "HP Sea Limited" (Astra data) | QA report (generated) | n/a (received, not sent) |
| 25 | clarifying_opens_3_OPEN (.docx; text) | /Users/yogeshyadav/Desktop/HP/NewDocs/clarifying_opens_3_OPEN.docx | **Manisha Parwani** (python-docx; lastModifiedBy "Manisha Parwani") | Edited 24 Sep 18:40Z (25 Sep 00:10 IST); mtime 25 Sep 07:15 | The 11 of 43 opens_2 items still open | Question list | Unknown. It is addressed to BridgeAI and is the intended vehicle per memory. |
| 26 | clarifying_opens_3_CLARIFICATIONS (.docx; text) | same folder | Manisha (as above) | 24 Sep 19:51Z; mtime 25 Sep 07:15 | 7 items needing a short clarification | Question list | Unknown |
| 27 | clarifying_opens_3_UNRESOLVED (.docx; text) | same folder | Manisha (as above) | 24 Sep 19:10Z; mtime 25 Sep 07:15 | 1 item answered but unresolved | Question list | Unknown |
| 28 | clarifying_opens_3_OPEN_v2 (.docx; text) | same folder | Manisha's base doc **merged with Yogesh's points** (the docProps keep Manisha. Word lock file `~$arifying_opens_3_CLARIFICATIONS_v2.docx` names owner "Yogesh Yadav". The content pulls in OI and DL wording.) | mtime 25 Sep 07:28 | 26 items: 14 of 43 open, plus a filings follow-up, two email items and nine items added on 24 Sep | Question list | Unknown. It is the latest vehicle. |
| 29 | clarifying_opens_3_CLARIFICATIONS_v2 (.docx; text) | same folder | Manisha plus Yogesh (lock file owner "Yogesh Yadav"; the file was open in Word) | mtime 25 Sep 07:27 | 12 items: 7 clarifications and 5 recorded readings | Question list | Unknown |
| 30 | clarifying_opens_3_UNRESOLVED_v2 (.docx; text) | same folder | Manisha plus Yogesh | mtime 25 Sep 07:27 | 2 items answered but unresolved | Question list | Unknown |
| 31 | _RUN_SUMMARY.json and _CORRECTIONS.txt (plus _ACCOUNTS.csv, _READINESS.csv, _DATASET_USAGE.md, _unassigned_filings.csv) | /Users/yogeshyadav/Desktop/HP/220 account split csv/ | **Generated tool**: the delivery team's `scripts/split_account_data.py` (uncommitted changes in git status) | Generated 2026-09-25T05:23:33Z (10:53 IST) | Derived per-account dataset: 220 account folders | Derived dataset | No |

---

## 2. Per-document summary

### 2.1 220-Account-Data-Questions-For-Client.md (DQ, sent 24 Sep 00:26)
Ten findings from splitting the four source workbooks (Explorium ×220, PredictLeads combined 219, Google News RSS, Exa), each "verified against the source files, not inferred". They are prioritised in three bands: items 1 to 4 are blockers, items 5 to 9 are quality issues, and item 10 asks for confirmation.
- Q1: contacts are 0 of 220.
- Q2: jabil.com and mufg.jp are each shared by two companies. Measured duplication would be +314 job rows and similar.
- Q3: Public Bank and Westpac have a blank Company Domain.
- Q4: four vendor domain mismatches.
- Q5: pbebank.com is named as two different banks.
- Q6: Exa (9,221 rows, 215 domains) and RSS (7,913 rows, 99 domains) have no stated relationship.
- Q7: 56% of Exa rows are undated, and 3 rows carry the epoch date.
- Q8: duplicate PredictLeads IDs.
- Q9: 28 corrupted Thai cells and 73 files containing HTML.
- Q10: coverage gaps, including compliance_filings at 0 of 220.

A closing table gives the severity of each item.

**Internal assumptions / decisions stated:**
- "**Interim handling:** all rows go to one account per pair (Jabil Malaysia, MUFG Japan) and the other gets none — an account with no data is safer than an account with another company's data."
- "We are currently deriving them [publicbankgroup.com, westpac.com.au] and would rather not guess."
- "We have mapped these four explicitly." (the Q4 aliases)
- "We are currently attaching the 43 news rows (which name Public Bank Bhd) and withholding the PredictLeads rows."
- "We have merged both and de-duplicated on domain + headline + date (356 duplicate rows removed)."
- "We are treating these as source-coverage facts rather than errors."
- "Items 2, 3, 4 and 6 are currently handled with explicit, documented rules on our side."
- No claim of client approval.

### 2.2 220-Open-Decisions-List.md (DL)
The spine document. The committed version (24 Sep) opens: "Each line has the question, what we will do if you do not say otherwise (our default)… the approved list becomes the spec for the run." It holds 53 items in sections A to I:
- A: identity
- B: contacts
- C: filings
- D: news
- E: coverage
- F: recommendation logic
- F2: case-study placement
- G: product behaviour
- H: environment
- I: email-thread items

The uncommitted 25 Sep working copy adds a **Status** line to every item, using this vocabulary: RESOLVED, OPEN, OURS, CLARIFICATION SENT, NOT YET ASKED. It adds a summary table and states the critical path: contacts, Name + Country on every row, the Public Bank rows, the Exa dates, jobs for 45 accounts, GCP access, and a delivery date.

**Client approval claims (quoted):**
- "Status vocabulary: RESOLVED (rule in force)".
- D29: "RESOLVED by Dhruvi (24 Sep, WhatsApp)".
- D30: "RESOLVED by Dhruvi's 18 Sep file explanation".
- D32: "Dhruvi's annotated email of 24 Sep (09:30, section 5.3): 'DROP IT for now'".
- D52: "'Drop it for now.'"
- D1 and D7 (ultimate parent): "RESOLVED (25 Sep discussion)". The participants in that discussion are not named.
- D2: "RESOLVED (BridgeAI: 'resolved', no choice named; default recorded)". The default was recorded by us.

**Internal assumptions or implementation decisions made without a client answer:**
- D3: "Interim rule stands until the columns arrive."
- D4: "Domain held until the corrected Public Bank Berhad rows arrive."
- D11: "Name variants that map to exactly one account are aliased by us and logged in the corrections report (ANZ Group, IAG Group AU/NZ, BDO Unibank Inc., UOB Group, Westpac Group AU/NZ, Fletcher Building Holdings NZ, Astra International Group); keiretsu-labelled rows are split by domain to the member accounts… Aboitiz, Universal Robina, Singapore Airlines, Spark NZ and Bank Negara Indonesia are ignored as out of scope." Defaults: "Jabil Inc." to "Singapore"; Hyundai to "HKMC Group / Hyundai Autoever as keyed". **This conflicts with O3 v2 C5, where the default is both Jabil accounts.**
- D16: "our definition of 'same event' (same account, same event date, matching normalised headline)".
- D18: "**RESOLVED by default.**… We add an `exa` key; cards show the publisher name per item 40. Clarification sent; stands unless they object." BridgeAI never answered the labelling question (see U3 v2 D3).
- D22: `Related Technologies` "surfaced as 'researched technology' and kept separate from detected technology (confirmation requested)".
- D23: "We use that file" (the separate Astra PredictLeads file).
- D25 to D27 defaults: drop 5 rows and merge 4; the file is treated as post-correction; "Postings seen (last 12 months)" with blank shown as "status not reported".
- D34 default: "Rulebook guardrail C 06 governs; one primary, secondaries only with separate verified evidence, no verdicts for routes without evidence."
- D35: "Default changed: `confidence_tier`… = v4 section C labels (Opportunity / Conversation Starter / Context Only)… T0 preferred, T2 only when no T0 fits."
- D37: the risk-label logic is ours ("Compete = High risk; Open opportunity = Medium; Complement = Low; Contextual = no label").
- D38 is marked "**seat count RESOLVED, default changed**". The client said only "hold employee range". The thresholds are an internal proposal: "lower bound 501+ Priority Access, 1,001+ Priority Access Plus, 5,001+ Priority Management". OI C6 and C3 v2 F6 still ask "Need: yes to the proxy", so **RESOLVED overstates the approval.** Likewise "'Pending HP input' items are recommended at family level… no 'pending' label" is our interpretation of "pls ignore that pending HP input".
- D10 and D39: "Proposed: follow item 7 and leave the section out, no message." **This conflicts with O3 v2 G1 and B4, which state "Our default is to show it with the message."**
- 29a to 29c and 44 to 50: defaults "as built", "after", "yes" and "apply it". They are marked NOT YET ASKED.

### 2.3 220-Open-Items-and-Clarifications.md (OI, 25 Sep)
A client-facing letter in five parts:
- Part 1: 14 open items (O1 to O14).
- Part 2: 12 clarifications (C1 to C12), each with the question as asked, what we meant, what the data shows, what we need, and what we do "if we hear nothing".
- Part 3: two items we owed. P1 names the three mis-mapped filings accounts: Fletcher and Fonterra rows on Malaysian domains, and Astra rows on fifgroup.co.id. P2 gives the risk-label logic.
- Part 4: nine items not in the version answered (29a to 29c, 44 to 50).
- Part 5: every resolved decision "for the record".

**Approval claims:** "Every rule you gave has been adopted and recorded in the updated decisions list." "Silence on a clarification means its stated default applies." Part 5 heading: "Resolved and adopted, for the record… in force as you answered it".

**Internal assumptions or decisions:**
- C6 employee-range proxy: "Proposal: use the lower bound of the range as a conservative proxy… Need: yes to the proxy, or different thresholds."
- C6 lifecycle: "our reading: a product is past its end only when its latest date has passed; once its earliest date has passed it is 'approaching'".
- C8: our "same event" definition.
- C11: "we are recording the default: each account is the APAC entity".
- C12: "a row is removed only when it is identical to another in every column".
- Part 5 "D11 (applied by us)" lists the name-alias mapping. P2: "Default: keep, until you say."
- O8: "Proposal: apply it [the hierarchy rule] everywhere" (hide sections with no data).
- O9 label set: "Vendor names (Explorium, PredictLeads, Exa, Google News RSS) do not appear on screen."
- Part 5 includes "D38 (seat count) | No seller entry; employee range as the proxy (C6)". The table calls this adopted while C6 still asks for approval, which is an internal inconsistency.

### 2.4 220-Open-Questions-Tracker.md (TR, internal, 25 Sep)
An internal digest of BridgeAI's answers to Q1 to Q10, recording for each: what we asked, what they answered, what we are still waiting on, and what it blocks. Items that "stay OPEN until the promised data actually arrives and is checked".
- T1 to T5 and T7: OPEN.
- T6 (news merge) and T9 (fallbacks): CLOSED.
- T10 (duplicate IDs): CLOSED.
- T8 (filings): "RESOLVED, with one data correction outstanding".

T8 holds the verified filings arithmetic: 186 + 31 = 217; 475 of 505 rows have a usable URL; `local_path` is set on 504 of 505; there are 5 shared domains covering 21 companies; the Name + Country join matches 173 of 187; merged coverage is 144 of 218.

**Internal inconsistencies:**
- The summary line reads "Five open, five resolved", but the table shows six OPEN (1 to 5 and 7) and four CLOSED or RESOLVED.
- The summary row for item 4 still lists "master account list" as awaited, while the body says "no separate master account list is needed".

**Internal assumptions:**
- "Handled on our side, logged in the corrections report. Name variants… are aliased".
- "The United Tractors document under Astra is excluded."
- On `Related Technologies`: "It should be surfaced as a supporting 'researched technology' signal… Worth one line of confirmation with them."
- On the client's answer that filings are "merged on domain", the tracker re-frames it: "Their Name + Country rule resolves most of this".

### 2.5 BridgeAI-email-draft-2026-09-24.md (draft, 24 Sep)
Yogesh's escalation email, sent "with Manil's full knowledge and backing".
- Section 1: status. Every rule up to Tuning Logic v4 and the Print Rulebook (received 23 Sep 11:24) is implemented. 6 of 11 features can run without contacts.
- Section 2: a dated timeline from 10 Sep to 24 Sep.
- Section 3: pending data: contacts (0 of 220), identity conflicts, news precedence and Exa dates, coverage gaps.
- Section 4: the GCP access chronology.
- Section 5: open points. 5.1 the "relevant" threshold is undefined; 5.2 a partial build; 5.3 "Recommendation for HP" on the Technographic Map; 5.4 JEV; 5.5 readiness.
- Section 6: Option A (the delivery team owns the approach and documents every output-changing decision for approval) or Option B (BridgeAI gives a fully specified approach). It recommends Option A.
- Section 7: four asks: GCP, contacts plus answers, an A/B decision, and a realistic date. It also asks for an inspection window.

**Internal assumptions or decisions (quoted):**
- "Until last night I was working on the assumption that the complete data would be with us by then, and that I would have GCP access. I also assumed the dataset we received was close to final."
- "With the data we have today, and our own judgement where the instructions are open, the product remains dependent on incomplete data and on assumptions you have not approved."
- "we merged them on that basis" (the news feeds).
- "with our interim rules, Jabil Singapore and the MUFG Bangkok branch stay near-empty."
- "Dhruvi's 18 September email gave two worked examples and the rule not to force a match, and we have built to that."
- 5.3: "This card was our own addition beyond the reference application."
- 5.4: "We propose to scope it after the 220 delivery."

No approval claims. It explicitly asks for written approval: "We need it approved in writing, not decided silently on our side."

### 2.6 Evidence-Score-Data-Availability-Answers.md (15 Sep)
Answers roughly 42 numbered questions about a proposed Evidence Score (Source Diversity out of 50, Relevant Filings out of 25, Recency out of 25), verified against code and the live Astra corpus (12 datasets). It reports three design-changing findings:
1. Every `google_news.event_url` is a `news.google.com` redirect, and `source_publisher` is the constant "Google News RSS".
2. The publisher is derived from the headline suffix, and 7 of 12 rows name Astra itself.
3. The 365-day gate and the 20-signal cap pre-filter the pool, with 5 of 12 rows surviving.

Other findings: `news_events` has no URL or publisher; `filing_label` is the filename; there is no fiscal-year-end field; the date parser tries DD/MM before MM/DD; and cross-dataset over-counting of one event is possible. It closes with a table of 8 "DECISION NEEDED" items and a recommendation to re-weight or obtain a feed with resolved URLs.

**Internal recommendations. These are proposals, each marked "DECISION NEEDED", not decisions:**
- "URL domain wins for classification, publisher string is display only."
- "collapse [subdomains] for *ownership*"
- reduce the categories to 3 "(Company / Filings / Media)"
- "Investor Materials over Official Company Sources"
- "month-end (`2026-07-31`)" for `2026-Jul`
- "(3) for now, (2) eventually" for FY dates
- "exclude from the recency calculation rather than score 0"
- "freeze `scored_at`"
- "cap at 3 filings = 25 points"
- dedupe on the source-row `id`
- "different category = different evidence"
- A stated rule: "`news_events` should contribute to evidence *volume* and *recency*… but **must not contribute to Source Diversity**."

It cites "the standing project rule on conservative signals". No client-approval claims.

### 2.7 HP-Input-Data-Contract.md (16 to 24 Sep)
As-built contract for BridgeAI's data team:
- 25 dataset keys: 14 consumed, 12 accepted but unread. (The document says both "14" and "12", which sum to 26 against 25 keys. It is internally inconsistent.)
- Exact column names per dataset, with delimiters, the domain join key and date rules.
- The `hp_category_intent` two-row header spec.
- 9 open questions (§5).
- A feature-to-dataset matrix (§6).
- Six silent failure modes (§7).
- A delivery checklist.

**Statements attributing rules to the client (quoted):**
- `Parent Company Name`: "Empty = parent relationship ignored for now: nothing shown, nothing flagged (client instruction, Sep 2026)".
- `identified_as_competitor_of`: "that gate is empty by client instruction (Sep 2026)".
- `NOISY_CATEGORY_TERMS`: "**empty by client instruction (Sep 2026)**".

**Internal implementation decisions:**
- "Code treats `""`, `open`, `active` as open" (`OPEN_STATUSES`). This is raised as open question §5.1.
- "`DD/MM/YYYY` is tried before `MM/DD/YYYY`".
- "Naive timestamps are assumed UTC".
- "Duplicate topics: first row wins… **never averaged**".
- "A non-numeric score is not treated as zero".
- Contact scoring: "25% seniority + 25% HP relevance + 20% influence + 15% data completeness + 15% priority. A contact needs ≥60".
- "`Top HP Category` is re-checked, not trusted."
- "`Intent Trend` is not used as a trend."
- A 365-day gate and "At most **20 signals** are published per account".

**Staleness against DL (25 Sep):**
- The 20-signal cap was removed (D19).
- The `Ultimate Parent Name` column is "Not displayed", while D7 now uses Ultimate Parent Name.
- The Group C keys are to be removed (D28).
- Exa has no key (D18).

### 2.8 docs/meeting-notes/2026-09-14-feature-walkthrough.md (14 Sep, internal)
Notes of Palash's walkthrough for Manisha, Anvesha and Yogesh.

The headline decision is a **GraphRAG layer**. Plain RAG and "the existing Azure AI Search setup" were "explicitly rejected"; Neo4j was named as the reference. It plans per-account indexes for compliance, products, news, structured data and dashboard outputs, and makes PDF cleaning mandatory.

Per feature:
- Executive Dashboard: numbers from the compliance PDFs; news only as a fallback; hiring velocity stays deterministic.
- Intent & Demand: done, with a "BLOCKER: location tags do not exist". Provider runs disagree (41/37 against 12/34).
- Message Evaluator: honest scoring and a gap-driven rewrite.
- Content Messaging: challenge, HP solution, benefit, proof; "Recommend classes, never SKUs"; top 3 chosen by the LLM through GraphRAG.
- Strategy Chat: last; "inputs are widget outputs, not raw data". GraphRAG was preferred over the agentic tool-calling Yogesh proposed.

Build order: GraphRAG, then Executive Dashboard, then Content Messaging, then Message Evaluator, then Strategy Chat.

**Internal decisions made without the client:**
- the GraphRAG adoption and the rejection of Azure search
- "No new external raw data at question time"
- "Keep `exec_hiring_velocity` and `exec_key_metrics` exactly as they are"
- "Enforce the class-not-SKU rule in the prompt **and** validate it post-generation"
- "Do not synthesise or infer a location"

To raise with the client: the location tags and the 41/37 against 12/34 discrepancy. **No later document in this set records an answer to either.**

The later Remediation Checklist item 5 says per-account RAG workspaces block account #2 and asks to "evaluate which features need graph RAG".

### 2.9 QA-Report-Response_2026-09-16.md (16 Sep)
Buckets every finding of the 15 Sep QA report as FIXED, ALREADY CORRECT, OPEN or BLOCKED ON DATA. The biggest finding: "contract tbd" was a false positive from seven committed `.bak` files, which were untracked and gitignored.

Real fixes:
- ED-14: Ultimate Parent suppression with a review flag.
- LS-13: the sort tiebreak bug.
- LS-16: an `event_status` enum.
- TM-12: the header shows 220 detected against 20 mapped.
- Hardcoded Astra fallbacks removed.
- Content Studio format limits per `HP_ABX_v3_final.docx`, plus a `Re:` subject line, a deterministic fallback template and co-creation.
- Message Evaluator phrase highlights.
- CM-11 sources footer and CM-12 fraction.

It lists 6 open decisions and 6 recommended changes to the QA tool. Verification: "360 backend tests pass", ruff is clean, and tsc exits 0. "All changes are uncommitted". The report flags the Groq block as a "hallucination sample".

**Internal decisions:**
- The contradicting parent name "is deliberately **not** written into the field".
- "Per the standing preference, nothing was replaced — 220 remains, correctly labelled".
- TM-11: "Recommendation: change the check" (no percentages).
- OP-03 and OP-07: "This wording is deliberate and should not be changed to turn the check green."
- Strategy Chat checks "should not be 'fixed' by bolting on citations".
- The denominator "now counts what the model **proposed**".

**Client-alignment claim:** "Co-creation implements Dhruvi's email requirement (*'brief → suggested options → user selects or adjusts → generation'*)". This matches the 24 Aug email in mails (1).txt.

### 2.10 QA-Discussion-Points_2026-09-16.md
A plain-language rewrite of the unfixed QA items only, 12 points:
- A. Checks asking for the wrong thing: OP-03/07 wording, OP-06 box present, OM-10/13, CM-15, TM-11, SM-10 avatar, link checks.
- B. Data does not exist: SM-07 and SM-26, active employees.
- C. Needs a decision: Strategy Chat citations, the regeneration cost, about 200 unmapped technologies, the Step 4 data suggestions.

It also flags the Groq block.

**Internal positions:**
- "We did not change the code for these. We would rather agree the check is wrong than make our product less honest just to turn a box green."
- The proposed dated wording: "Contact list as captured on 9 Sep 2026 — employment not re-checked".

No approval claims. **No later document in this set records QA's answers.**

### 2.11 mails (1).txt (mail dump, 22 Aug to ~3 Sep 2026)
A pasted Gmail thread (Yogesh's view, with "me" in the recipients):
- **Dhruvi, 22 Aug**, the kickoff: the POC codebase `hp-sea-abm-dev-main.zip`, `HP_ABX_v3_final.docx` (about 20 features; the 11 in scope are listed), the account list `APAC_Account_Parent_Child_Mapping.xlsx` (Master List col B, 220 accounts), and the Palo Alto Caterpillar and HP Sea Limited POC URLs. Covered by NDA.
- **Dhruvi, 24 Aug**: HP Notebook and Desktop deck folders for RAG, a new Reporting & Usage Analytics module, and a human-in-the-loop co-creation requirement.
- **Konika, undated (~3 Sep, "38 minutes ago")**: intent, stock exchange and contact data (hp_intent_results.xlsx, the Astra annual reports, the Car Market PDFs, apollo_data.xlsx). It proposes the category intent score as the primary signal with Source A topics as support.
- **Palash, 26 Aug**: a request for one representative cleaned account dataset, a data contract and a feature mapping.
- **Dhruvi, 27 Aug**: promises it by Monday.
- **Konika, 31 Aug**: the Data Sourcing Reference document plus Source A, Source B and google_news_rss_data.

### 2.12 hp-input-contract.json and hp-file-to-json-map.json
- **hp-input-contract.json** (JSON Schema 2020-12, v1.0.0, `generated_at 2026-09-15`, 3,102 lines). Top-level keys: `$schema, title, description, version, generated_at, authority` (5 code pointers: `DATASET_REGISTRY`, the upload endpoint, `datasets.py`, `WIDGET_REGISTRY`, `FEATURE_MAPPINGS`), `pipeline` (3), `global_rules` (9), `dataset_types` (2), **`datasets` (25)**, `not_consumed_notice` (3), `output_json` (`widget_count` 31, `feature_count` 11, `widgets` 11 and `remaining_widgets` 11 groups, envelope, provenance block), `feature_dependencies` (11 features plus the minimum viable set), **`edge_cases` (17)**, **`open_questions` (9)**, `delivery_checklist` (13). It states: "Where this file and the code disagree, the code is authoritative." It has uncommitted edits in the working tree.
- **hp-file-to-json-map.json** (`generated_at 2026-09-15`, 764 lines). Keys: `title, purpose, how_to_read_an_entry` (6), `generated_at`, `verified_against` ("ingestion source code and the reference account files"), `quick_reference` (2), **`files` (13 entries**: firmographics, technographics, prospect_contacts, intent_score, google_news, news_events, job_openings, webstack, company_hierarchy, technology_detections, intent_topics, hp_category_intent, compliance_filings), `files_you_can_upload_but_that_do_nothing` (4), `features_and_the_files_they_need` (2), `how_to_check_your_upload_worked` (4), `the_six_things_that_fail_silently` (7), `companion_documents` (2).

### 2.13 HP-Account-Intelligence-Handover (docx, ~10 Sep)
A handover for the reference account (Astra). It describes a two-layer design, a deterministic layer and an LLM-inferred layer, and states that "the inferred layer is never allowed to introduce a fact the uploaded files do not contain".

Status of the features:
- Group 1, complete in both layers: Live Signals, Stakeholder Map, Opportunity Map, Objection Playbook.
- Group 2, deterministic layer only: Executive Dashboard, Content Messaging, Content Studio, Strategy Chat, Message Evaluator, Tech Landscape, Intent & Demand. The heading says "(5)" but the table lists 7.

It warns that the registry descriptions for 3 widgets are stale. It includes a dataset-to-feature map, the regeneration rules ("Opening a page never calls the model"; caching on an input fingerprint plus the prompt version) and the code locations.

**Internal design decisions:** the two-layer separation, the regeneration trigger table generated from `FEATURE_MAPPINGS.dependent_datasets`, and the caching policy. No client-approval claims.

### 2.14 HP-220-Account-Data-Review-Agenda (docx, 23 Sep)
Agenda for the "BridgeAI / Movozane" call. "We have reviewed all 226 files in the new drop." It has 11 items, each with evidence and the decision needed:
1. contacts (0 of 220)
2. entity scope (141 conflicts)
3. the 12-month news window and 20-signal cap
4. an Exa key ("Exa covers 215 of 217 accounts; Google News covers only 99")
5. Exa dates ("5,120 of 9,221 Exa rows unparseable; usable yield ~27%")
6. low-confidence news
7. vendor-flagged rows
8. the 490 corrections
9. the account list and domains (217 unique, identity blank on 209 of 219)
10. coverage gaps and empty state
11. about 48,000 rows the platform cannot read

**Internal assertions:**
- "Extraction of the per-account sheets is understood and needs no discussion."
- "we can build 6 of the 11 features across all 217 accounts today; resolving item 1 takes us to 11 of 11."
- Item 7 is framed as "Vendor-flagged bad rows should be excluded before import… Agree to drop flagged IDs pre-ingestion". That is a proposed decision.
- Note that Ag5 calls the rows "unparseable", while DQ and DL call them "no event date" or blank.

### 2.15 HP_Platform_Gap_Analysis (docx, 18 Sep): delivery team
A review of the client's 11 new documents: the Combined Rulebook (about 90 rules; Part A 18 hardware, Part B about 72 services, Part C guardrails), the Recommendation Logic deck, Live Signal Scoring, Tech Landscape Confidence Scoring, case studies (384 rows), Q426 (2,186 SKUs), Care Pack definitions, filings (505 rows and 187 companies), Lifecycle (146 rows), the Wolf deck and the HP IQ deck (picture-only rebuilds).

It sets out what is built (Part A and the hardware guardrails), what must change (live signal scoring from 5 drivers to 3; tech confidence at 70/30; the proof-point slot; 3D has no route), what must be added (a services catalogue, about 72 service rules, a router, a Wolf grid, an HP IQ eligibility check, vocabulary mapping), what must be built "deliberately incomplete", a document-to-feature table, data-quality notes and questions.

**Author: delivery team.** Evidence: "The client sent 11 new documents"; "what the platform already does today"; "Decisions for us rather than the client"; "No code has been changed. This document is analysis only."

**Internal assumptions or recommendations:**
- "dropping ours [S/A/B/C tiers, minimum score] would mean showing every signal… We recommend keeping both." BridgeAI later overturned this in D36.
- "Moving recency off the AI model… is a clear improvement."
- "seat count should be something the seller enters." BridgeAI later rejected this in D38: "we might not ask seller to enter seats".
- On the Lifecycle multi-date cells: "We think it is the last, but the file does not say so".
- On one route against five: "Our reading is that one is the primary and the rest are secondary".
- "Rename our evidence classification… Recommendation: leave it for now".
- "Fix the two product rules that refer to the stakeholder list… worth doing".
- "Filings: the covering email says 184 accounts of 220, but the file supports 175." Later documents say 186 or 187 companies.

Questions it raised that **do not reappear** in later lists: "The rulebook says the engine must not open the original HP files… Does that count as the rulebook or not?"; a request for the genuine Wolf and HP IQ decks; "Is there a table linking service SKUs to the products they attach to?"

### 2.16 HP_Account_Intelligence_FINAL_Remediation_Checklist (PDF, 15 Sep): generated with ChatGPT from an internal engineering review
A 51-item fix list with a recommended order: security, then durable storage, async extraction, identity/registry/column contract, intent correctness, removal of silent fallbacks, authorization, tests, and cleanup. The blockers:
- committed PII of 23 contacts in a public repo
- a committed production JWT secret
- public default admin credentials
- ephemeral Render disk storage
- RAG index caps blocking account #2
- synchronous extraction
- no account-level authorization
- the intent hierarchy not enforced
- the noisy-keyword rule not enforced
- Astra hardcoded into seeding (#46)

HIGH and MEDIUM items include closed jobs counted as open, Astra fallbacks leaking, fabricated X-Ray provenance, no header validation, no tests or CI, and grounding that accepts any number. #44: a git stash containing `.env`, an Azure key and a Chrome profile.

**Authorship:** Spotlight WhereFrom `https://chatgpt.com/`. The subtitle reads "Consolidated from the engineering review + modularity analysis". It is an internal code audit. **No item statuses are tracked.**

Some items are visibly addressed in later documents:
- #40 (`.bak` files): QA Response §1.
- #15 (Astra fallbacks): QA Response for Tech Landscape and Strategy Chat.
- #32 (tests and CI): linting.md and "360 backend tests".

Items #9 and #8 are contradicted by a later client instruction. The Input Contract says the noisy-keyword list is "empty by client instruction (Sep 2026)", and "the highest-scoring category is always the primary one".

Item #51 is self-labelled "not independently verified".

### 2.17 HP_Sea_Limited_QA_Report_2026-09-15_0513 (docx): generated validator output
"4-Step Feature Evaluation Report" for the account "HP Sea Limited" on `hp-frontend-e56t.onrender.com`, run at 2026-09-15T05:13:15Z. The four steps are structural, deep, evidence and suggestions.

Summary scores:
- Executive Dashboard: 2/10, with red flags ED-14 (Ultimate Parent contradiction) and ED-17
- Recent News: 7.4
- Stakeholder Map: 7.7
- Opportunity Map: 6.1 (OM-10, OM-13)
- Tech Landscape: 7.3 (TM-12)
- Objection Playbook: 4.3
- Content Studio: 8.3
- Strategy Chat: 6
- Message Evaluator: 8.3
- Intent & Demand: 8.6
- Content Messaging: 5.6 (CM-15)

Step 2 flags "contract tbd" on every feature. Step 3 marks LinkedIn links as 999 "broken" and Google News links as unreadable. Step 4 repeats data suggestions (the xlsx and pdf files, gaikindo, financials_fy.2025, stock_exchange, workforce_trends). The Strategy Chat section includes an "Independent Groq evaluation". The delivery team identified it as hallucinated (CIO score 92/100, FY24 revenue $12.4B, "HP ProLiant servers").

Its ground truth for Intent is "3D Printers, 34/100", which matches the 12/34 run cited in the meeting notes.

**Authorship:** generated tool output. Who ran it is not determinable from the content. Project memory says the validator's source is not on this machine.

### 2.18 clarifying_opens_3 (non-v2): Manisha, created 25 Sep 00:10 to 01:21 IST
BridgeAI's opens_2 answers to the 43 decision items, sorted into three documents. Each item is numbered by section letter and traceable to its opens_2 item, and carries: What we asked / Your answer / What we checked / What we need.

**OPEN (11 of 43)**

| ID | opens_2 item | Title | Status wording (answer as quoted) |
|---|---|---|---|
| A1 | 1 | Canonical account list | "OPEN: WILL GIVE THAT". We need: "Please send the master list of 220 accounts with one domain each." It also measures 218 domains, 216 unique, plus `global.pioneer`. |
| B2 | 8 | Contact file | "(no answer; section B is marked OPEN)". We need: "Please send the contact data." |
| B3 | 9 | Role coverage | "(no answer; section B is marked OPEN)" |
| B4 | 10 | What to show when an account has no contacts | "(no answer…)". "Our default is to show it with a message" |
| C4 | 14 | Three accounts with the wrong filings mapping, "the names, as promised" | "open: pls send , noted!". It names **SUNWAY HOLDINGS (MY) with an NZ country, UOB (MALAYSIA) with an NZ country, and FEDERAL INTERNATIONAL FINANCE (ID)**, saying "Our earlier description had the first two the wrong way round". |
| D1 | 16 | Which news feed wins | "open". We need: "keep the Exa row as the main one, and keep the Google News row beside it as a supporting source." |
| F7 | 37 | Technographic Map risk labels, "the logic, as promised" | "open". "This is our logic and it stays as described until you tell us otherwise." It adds an exception: HP's own absence row always reads Medium. |
| G1 | 39 | What to show when a dataset is missing | "open". The gaps cited include "hiring, missing for 15". "Our default is to show the section with the message." |
| G2 | 40 | Source labels on screen | "open". Five labels plus HP Rulebook and HP case study. |
| G3 | 41 | The data as-of date | "open". Default: the final consolidated drop. |
| H1 | 42 | GCP access | "open" |

**CLARIFICATIONS (7 of 43)**

| ID | opens_2 item | Title | Status wording |
|---|---|---|---|
| C1 | 11 | Two accounts missing from the filings list (Agribank, VPBank) | Answer "RESOLVED…". We need confirmation for the two. |
| E4 | 25 | Rows the vendor flagged as doubtful (9 rows) | "clarifications needed". "Please confirm we should drop those 9 rows." |
| E5 | 26 | The 490 logged corrections, "now cleared" | "332 of them hold the corrected value… We are treating the delivered file as final". We need: "Nothing." |
| E6 | 27 | How to label job postings | "clarifications needed". Confirm the "postings seen" wording. |
| F1 | 29 | When a Rulebook offering counts as relevant | "Already resolved: Explained in the email". "We are currently using exact or known-alias matches only, and listing category-level matches as possible". |
| F4 | 34 | One recommendation or several, "now cleared" | Routes per slide 5 (3D Printing, Workstations, PC/Devices, Print, Poly). "We will show the strongest route… keep the weaker ones as secondary hypotheses, per your slide 3." |
| F6 | 38 | Service rules that need data we do not have | Answer "resolved / clarification needed…". Asks which lifecycle column applies. "we treat a product as still sellable while any of its dates is still in the future". |

**UNRESOLVED (1 of 43)**

| ID | opens_2 item | Title | Status wording |
|---|---|---|---|
| D3 | 18 | Exa as its own source | Answer "Resolved: pls use domain + company name + country". "Why this does not settle it: That answers how to match rows…". Suggests "showing Exa by name". |

**Internal assumptions or decisions in the non-v2 set:**
- F7 says the logic is ours and "stays as described".
- E5 says "treating the delivered file as final".
- F1 says "using exact or known-alias matches only". This **predates, or ignores, Dhruvi's 24 Sep use-case-fit rule** recorded in DL D29.
- F4 is our reading of the client's slide 3.
- F6 applies a "cautious reading" of lifecycle dates.
- The B4 and G1 default is to show a message.
- The D1 proposal is "Exa row as main". This **contradicts the client's own opens_1 Q6 answer** (skip the disagreeing item).
- C4 re-identifies the three filings accounts, and v2 reverses that.

### 2.19 clarifying_opens_3 v2: Manisha's documents merged with Yogesh's points (25 Sep 07:27 to 07:28)

**OPEN_v2.** The header changes to "14 of the 43 questions are still open, either because no answer was given or because the answer promises a delivery that has not yet reached us… One follow-up on item 11, two process items from our 24 Sep email and nine items added on 24 Sep".

| ID | Source | Title | Status wording | v2 change |
|---|---|---|---|---|
| A1 | item 1 | Canonical account list | "OPEN: WILL GIVE THAT". We need the master list. | **Unchanged.** This conflicts with DL D1, "No separate master list is needed". |
| A3 | item 3 / opens_1 Q2 | Company Name + Country on every PredictLeads row | Open delivery. The columns are populated on 384 of 14,965 rows (2.6%). | **Added** (from OI O2) |
| B2 | item 8 | Contact file | "(no answer…)". It now includes BridgeAI's later statement (contacts not available for every account; roles or names only for some). | **Expanded**: key on domain + name + country; which accounts carry real contacts; prompts per feature |
| B3 | item 9 | Role coverage | unchanged | unchanged |
| B4 | item 10 | No-contacts display | Default "show it with a message" | **Added the alternative** of the item-7 hierarchy rule |
| C4 | item 14 | Three accounts with the wrong filings mapping | "Item 14 had them right the first time": **Fletcher (NZ) on sunway.com.my; Fonterra (NZ) on uob.com.my; Astra International Group on fifgroup.co.id; plus a United Tractors row** | **Rewritten.** Reverses the non-v2 identification (from OI P1). |
| C5 | item 11 follow-up | Two filings rows we cannot place without you | Yes/no each. It reports "Jabil Inc. – six SEC 10-Q rows, three keyed SG and three keyed MY". "If we hear nothing: the Jabil rows are attached to both Jabil accounts as keyed". | **Added** (from OI O6). **The default differs from DL, OI and TR ("Singapore only").** |
| D1 | item 16 | Which news feed wins | "open". Confirm the Q6 skip rule plus the same-event definition. "Exa row as main" is kept only as an alternative. | **Rewritten** (from OI O7/C8) |
| D2 | item 17 / opens_1 Q7 | Exa event dates: the re-crawl | Open delivery plus the recovery count | **Added** (O4) |
| E1 | item 22 / opens_1 Q10 | Job openings for the 45 accounts, plus a technographics confirmation | Open delivery plus a "researched technology" confirmation | **Added** (O5) |
| F7 | item 37 | Risk labels | "Nothing from you unless you want it changed". Options: keep, rename ("Competitive position"), or drop. Mentions the Sahaj screenshot. | **Expanded** (P2) |
| G1 | item 39 | Missing dataset display | "hiring, missing for 45 accounts" (the non-v2 said 15). Default "show it with the message" or the hierarchy rule. | **Expanded.** It still conflicts with the DL proposal to hide. |
| G2 | item 40 | Source labels | Adds **Technographics**, publisher name on news cards, and no vendor names | **Expanded** (O9) |
| G3 | item 41 | As-of date | "shown once per account; each dataset's own retrieval date is kept in the backend record" | **Expanded** (O10) |
| H1 | item 42 | GCP access | unchanged | unchanged |
| I1 | email §7.4 | A realistic delivery date | "(not answered in the annotated reply)" | **Added** (O13) |
| I2 | email | One consolidated drop with a contents list | Not answered. The inspection window is agreed. | **Added** (O14) |
| F1a | 29a | Integration routes detected on their own | "(not yet put to you)". Default: a context line. | **Added** |
| F1b | 29b | Conditions the data cannot evaluate | "(not yet put to you)". Default: yes. | **Added** |
| F1c | 29c | Use-case vocabulary for case studies | "(not yet put to you)". We write the table. | **Added** |
| F8 | 44 | Four features with no row in the v4 table | "(not yet put to you)". Default: as built. | **Added** |
| F9 | 45 | Case-study proof on the signal features | "(not yet put to you)". Default: after. | **Added** |
| F10 | 46 | Proof on service plays in the Opportunity Map | "(not yet put to you)". Default: yes. | **Added** |
| F11 | 47 | Evidence-tier gate on proof | "(not yet put to you)". Default: apply it. | **Added** |
| F12 | 48 | Region preference for proof | "(not yet put to you)". Default: yes. | **Added** |
| F13 | 50 | Product-line mapping for case studies | "(not yet put to you)". Default: yes. | **Added** |

**CLARIFICATIONS_v2.** The header changes to "12 of the 43 questions are here. Seven need a short clarification; five are answered, and we are recording the reading we have taken so you can correct it."

| ID | Item | Title | Status wording | v2 change |
|---|---|---|---|---|
| A2 | 2 | Entity scope: the reading we have recorded | "RESOLVED". We need: "Nothing, unless you want APAC-entity values in those 141 fields." | **Added** (OI C11) |
| C1 | 11 | Two accounts missing from the filings list | Adds that Agribank's 3 rows carry only name and document type; **VPBank's 2 documents sit under "VIETNAM POST CORPORATION"**; asks to re-key them | **Expanded with new measured facts** (not in OI or DL) |
| E2 | 23 | Astra: the file we are using | "Astra: already provided initially". Confirm format and version. | **Added** (OI C10) |
| E3 | 24 | Duplicate record IDs, "now cleared" | "Nothing. This is on record" | **Added** (OI C12) |
| E4 | 25 | Vendor-flagged rows | Confirm dropping 5 rows and merging 4. "If we hear nothing: dropped and merged" | **Expanded** (OI C1) |
| E5 | 26 | 490 corrections, "now cleared" | unchanged ("Nothing") | unchanged. It conflicts with DL D26 status "CLARIFICATION SENT" and OI C2, which still asks for one confirming line. |
| E6 | 27 | Job postings label | Adds the status breakdown (8,158 blank, 6,725 closed, 82 notes, 28 open), (a) blank = open?, (b) the wording, and the silence default | **Expanded** (OI C3) |
| F1 | 29 | When a Rulebook offering counts as relevant | Restates Dhruvi's 24 Sep §5.1 rule. "Please confirm that reading." | **Expanded.** It still says "It matches what we do today: exact or known-alias matches", which sits awkwardly with the use-case-fit rule it restates. |
| F3 | 32 | "Recommendation for HP" card, "now cleared" | "drop it for now". We need: "Nothing". | **Added** (OI C9) |
| F4 | 34 | One recommendation or several, "now cleared" | Adds the match with Rulebook C 06 and "Routes with no evidence are not shown at all" | **Expanded** (OI C4) |
| F5 | 35 | Confidence tiers T0 to T3: which feature | (a) section C labels, (b) T0 and T2 meaning, (c) may T2 be cited. Silence default. | **Added** (OI C5) |
| F6 | 38 | Service rules that need data we do not have | Adds the employee-range distribution (177, 17, 14, 12), the proxy thresholds, the Lifecycle columns (146 rows, 84 multi-date), password protection, the 18 Sep against v4 §J contradiction, and asks (a), (b), (c) | **Expanded** (OI C6) |

**UNRESOLVED_v2.** The header changes to "2 of the 43… or it conflicts with another answer".

| ID | Item | Title | Status wording | v2 change |
|---|---|---|---|---|
| A4 | 4 and 6 / opens_1 Q3 and Q5 | Public Bank: which rows belong to the Malaysian account | "The two answers pull against each other… we are holding the domain until the corrected rows arrive." | **Added** (OI O3) |
| D3 | 18 | Exa as its own source | Adds a third option, the publisher's name with no feed name, and "Whichever you pick, we are adding an exa key" | **Expanded** (OI C7) |

**Internal assumptions or decisions introduced in v2 (quoted):**
- C5: "If we hear nothing: the Jabil rows are attached to both Jabil accounts as keyed and labelled as the parent's filings".
- C1: "VPBank's two documents are held back rather than shown under the wrong bank".
- D3: "we are adding an exa key".
- F6: "Until you answer, we treat a product as still sellable while any of its dates is still in the future". **This differs from OI C6's reading** ("past its end only when its latest date has passed… 'approaching' once its earliest"). v2 F6 carries both sentences.
- F4: "Routes with no evidence are not shown at all".
- E4 and E6: silence defaults.

**Approval claims:** the headers "now cleared" (E3, E5, F3, F4) assert closure. E5 was cleared by our own data check, not by the client.

### 2.20 220-account split (_RUN_SUMMARY.json and _CORRECTIONS.txt), 25 Sep 05:23Z
In five lines:
1. It produced **220 account folders** (from 220 Explorium workbooks, all 220 matched to the master list, none unmatched), each with one CSV per `dataset_key`, plus `_ACCOUNTS.csv`, `_READINESS.csv` and `_DATASET_USAGE.md`.
2. Source rows sliced: news_events 14,289; job_openings 14,965; technology_detections 17,799; connections 19,583; subpages 15,163; google_news 17,134 (RSS + Exa, 356 dropped as duplicates). Unclaimed rows: tech 47, connections 100, subpages 82, news 38, similar 5, company 1.
3. `datasets_nobody_has`: compliance_filings and prospect_contacts (prospect_contacts rows exist only for Astra, 1 of 220, from the seed). The filings index has 505 rows: 437 by territory, 8 by domain, 31 by company name, **29 unassigned**, and 2 conflicts.
4. `_READINESS.csv`: tech_landscape is complete for 205 of 220 and intent_demand for 141; every other feature is "partial" for nearly all accounts; message_evaluator is "none" for 44 and recent_news "none" for 2.
5. `_CORRECTIONS.txt` records 17 derived values:
   - Public Bank derived to `publicbankgroup.com` and Westpac to `westpac.com.au`
   - folder slugs for 3 Ministries of Defence and 2 Westpacs
   - 4 "explicit approved alias" domain rewrites
   - Jabil SG and the MUFG Bangkok branch given no domain-keyed rows
   - 4 Astra datasets filled from `hp-backend/seed_data/astra`

**Internal assumptions or decisions, with conflicts against the 25 Sep decision documents:**
- Public Bank: "derived: publicbankgroup.com". DL D4, OI O3 and U3 v2 A4 say the domain is "held" pending BridgeAI; the client suggested `pbebank.com`.
- Aliases: "explicit approved alias", rewriting `posco.com` to `posco-inc.com` and `shell.com.ph` to `pilipinas.shell.com.ph`, i.e. **to the Explorium domain**. DL D5 records "Rule: PredictLeads domain is canonical" with Posco `posco.com` and Pilipinas Shell `shell.com.ph`. The resulting join may be equivalent, but the "canonical" direction differs.
- Shared domains: "jabil.com is shared with JABIL_CIRCUIT_SDN_BHD, which keeps the rows". This is the interim rule, still applied.
- Astra: "filled from the Astra benchmark seed; the client's E2 answer says Astra's PredictLeads data is a separate delivery, and the seed is that delivery". That is an internal assumption. It also covers **prospect_contacts**, which is not PredictLeads data, so the E2 answer does not cover that file.

---

## 3. Question inventory

Keyed on the Decisions List number, which is the common spine. The "Latest status" column quotes the clarifying_opens_3 v2 documents (25 Sep 07:27), which are the most recent. Where an item is not in opens_3, it quotes DL 25 Sep. Where documents disagree, the conflict is noted.

| IDs across documents | Question (short) | Feature / topic | Latest status, as stated | Carried in |
|---|---|---|---|---|
| D1 · Ag9 · (Q4) · T4 · O3 A1 | Canonical list of 220 accounts, one domain each | Identity | O3v2 A1: open. "Please send the master list of 220 accounts with one domain each." **Conflict:** DL D1: "RESOLVED (25 Sep discussion). No separate master list is needed." TR T4 body agrees with DL; the TR summary row still lists "master account list". | DL, AG, TR, OI Part 5, O3, O3v2 |
| D2 · Ag2 · OI C11 · C3v2 A2 | Entity scope: APAC entity or global parent (141 conflicts) | Identity, firmographics | C3v2 A2: answered ("RESOLVED"); default recorded. "Nothing, unless you want APAC-entity values." | DL, AG, OI, C3v2 |
| D3 · Q2 · T2 · OI O2 · O3v2 A3 | Jabil/MUFG shared domains; populate Name + Country on every PredictLeads row | Identity (4 accounts) | O3v2 A3: open delivery. "Please send the two columns populated on every row… not merely present." DL: "RESOLVED rule, OPEN delivery." | DQ, DL, TR, OI, O3v2 |
| D4 + D6 · Q3 + Q5 · T3 + T5 · OI O3 · U3v2 A4 | Public Bank domain / pbebank.com identity; Westpac | Identity (1 account) | U3v2 A4: unresolved. "The two answers pull against each other… holding the domain." Westpac: RESOLVED (DL D4). **The split output nevertheless derives `publicbankgroup.com`.** | DQ, DL, TR, OI, U3v2, _CORRECTIONS |
| D5 · Q4 · T4 | Vendor domain mismatches (Posco, Shell, Shiseido, Stanley) | Identity | DL: "RESOLVED." PredictLeads is canonical, with the four overrides. Not in opens_3. (The split rewrites toward the Explorium domains.) | DQ, DL, TR, OI Part 5 |
| D7 | Hierarchy: 55 accounts without a sheet; ultimate parent | Executive Dashboard | DL: "RESOLVED, default overturned. Say nothing." Ultimate parent is taken from the sheet, otherwise the account itself ("25 Sep discussion"). | DL, OI Part 5 |
| D8 · Q1 · Ag1 · T1 · OI O1 · O3v2 B2 | Contact file (0 of 220) | 5 features (blocker) | O3v2 B2: open. "Please send the contact data, keyed on domain + company name + country." | DQ, AG, DL, TR, OI, email §3, O3, O3v2 |
| D9 · OI O1 · O3v2 B3 | Role coverage (~30 roles, then 5 to 8 more) | Contacts | O3v2 B3: open. "(no answer; section B is marked OPEN)" | DL, OI, O3, O3v2 |
| D10 · OI O8 · O3v2 B4 | Stakeholder Map with no contacts: message or hidden | UI | O3v2 B4: open. Default "show it with a message", or the hierarchy rule. **Conflict:** DL proposes "leave the section out, no message". | DL, OI, O3, O3v2 |
| D11 · Q10 · T8 · OI O6 · C3v2 C1 · O3v2 C5 | Filings source and count; accounts without filings; Agribank and VPBank; Jabil Inc. and Hyundai DART rows | Executive Dashboard financials, Strategy Chat | C3v2 C1: clarification. Confirm Agribank; re-key the VPBank documents out of Vietnam Post. O3v2 C5: "A yes or no on each"; default Jabil to **both** accounts. **Conflict:** DL, OI and TR default is "Singapore only". DL: "RESOLVED" (method). | DQ, DL, TR, OI, C3/C3v2, O3v2 |
| D12 | Filing documents (Drive) | Filings | DL: "RESOLVED." Skip the failed file, not the company. | DL, TR T8, OI Part 5 |
| D13 | 12-month filings window | Filings | DL: "RESOLVED. Last 12 months." | DL, OI Part 5 |
| D14 · OI P1 · O3v2 C4 | Three mis-mapped filings accounts | Filings | O3v2 C4: "Please still correct the domain and global_parent values… remove or relabel the United Tractors row." DL: "OURS, sent." **Conflict:** the non-v2 C4 named Sunway, UOB MY and FIF instead. | DL, OI, O3, O3v2 |
| D15 | Stock Exchange data superseded? | Filings | DL: "RESOLVED. Superseded." | DL, OI Part 5 |
| D16 · Q6 · T6 · OI O7 + C8 · O3v2 D1 | News precedence when Exa and RSS disagree; "same event" definition | Live Signals | O3v2 D1: open. "Please confirm that your question 6 answer stands… yes or no on the same-event definition." DL: "RESOLVED rule, OPEN confirmation (with Sahaj since 24 Sep 14:43)". TR T6: "CLOSED". Non-v2 D1 proposed "Exa row as the main one". | DQ, DL, TR, OI, O3, O3v2 |
| D17 · Q7 · Ag5 · T7 · OI O4 · O3v2 D2 | Undated Exa rows (5,120 of 9,221); epoch dates | Live Signals | O3v2 D2: open delivery. "Please send the re-export with dates, and… the recovery count." | DQ, AG, DL, TR, OI, O3v2 |
| D18 · Ag4 · OI C7 · U3v2 D3 | Exa dataset key and on-screen label | News labels | U3v2 D3: unresolved. "should a news card sourced from Exa say 'Exa', or is 'Google News' acceptable…?" DL: "RESOLVED by default." | AG, DL, OI, U3, U3v2 |
| D19 · Ag3 | 12-month news window and 20-signal cap | Live Signals | DL: "RESOLVED, default changed… remove the 20-signal cap." | AG, DL, OI Part 5 |
| D20 · Ag6 | Low-confidence news rating | Live Signals | DL: "RESOLVED, default changed. Do not use the Low/High columns." | AG, DL, OI Part 5 |
| D21 · Q9 | Corrupted Thai text and HTML | News | DL: "RESOLVED." Text as returned; HTML stripped. | DQ, DL, OI Part 5 |
| D22 · Q10 · Ag10 · T9 · OI O5 · O3v2 E1 | Coverage gaps; job openings for 45 accounts; Related Technologies as "researched" | Hiring, Urgency, Tech Map | O3v2 E1: open delivery (job rows) plus a one-line confirmation. DL: "RESOLVED, with one OPEN delivery." (Non-v2 G1 said hiring was missing for 15; v2 says 45; the split shows job_openings for 176 of 220.) | DQ, AG, DL, TR, OI, O3v2 |
| D23 · Q10 · OI C10 · C3v2 E2 | 219 against 220: Astra | PredictLeads | C3v2 E2: "Please confirm it is the same format and version… or send the current extract." | DQ, DL, OI, C3v2 |
| D24 · Q8 · T10 · OI C12 · C3v2 E3 | Duplicate PredictLeads IDs | Counts | C3v2 E3: "now cleared… Nothing. This is on record". | DQ, DL, TR, OI, C3v2 |
| D25 · Ag7 · OI C1 · C3v2 E4 | Vendor-flagged rows (9) | Hiring, tech | C3v2 E4: "Please confirm we should drop those 9 rows… If we hear nothing: dropped and merged". DL: "CLARIFICATION SENT." | AG, DL, OI, C3, C3v2 |
| D26 · Ag8 · OI C2 · C3v2 E5 | 490 logged corrections applied? | Hiring and tech dates | C3v2 E5: "now cleared… We need: Nothing." **Conflict:** DL "CLARIFICATION SENT"; OI C2 still asks for one confirming line. | AG, DL, OI, C3, C3v2 |
| D27 · OI C3 · C3v2 E6 | Job status: "postings seen" label; does blank mean open? | Hiring widgets | C3v2 E6: "Two things. (a) Does a blank status mean open, or unknown? (b)… wording". | DL, OI, C3, C3v2 (also Input Contract §5.1, Remediation #11) |
| D28 · Ag11 | 12 PredictLeads keys with no consumer | Upload contract | DL: "RESOLVED." Products for recommendations; the rest removed. | AG, DL, OI Part 5 (Input Contract §5.8) |
| D29 · C3v2 F1 | Relevance threshold for Rulebook and case studies | Recommendations | C3v2 F1: "Please confirm that reading in a line here… or correct it." DL: "RESOLVED" (Dhruvi, 24 Sep). | email §5.1, DL, OI Part 5, C3, C3v2 |
| 29a · O3v2 F1a | Integration route alone as a context line? | Recommendations | "(not yet put to you)". Default: a context line. | DL, OI Part 4, O3v2 |
| 29b · O3v2 F1b | Unevaluable conditions treated as unmet? | Recommendations | "(not yet put to you)". Default: yes. | DL, OI Part 4, O3v2 |
| 29c · O3v2 F1c | Use-case vocabulary table (we write it) | Case studies | "(not yet put to you)". "Nothing yet." | DL, OI Part 4, O3v2 (Gap Analysis asked "Who writes the mapping") |
| D30 | Where Rulebook and case studies appear | All features | DL: "RESOLVED. As built, plus the Stakeholder Map." | email §2 (21 Sep), DL, OI Part 5 |
| D31 | 89 cleaned case studies as the corpus | Proof | DL: "RESOLVED." | DL, OI Part 5 |
| D32 · email §5.3 · OI C9 · C3v2 F3 | "Recommendation for HP" card on the Tech Map | Tech Map | C3v2 F3: "now cleared". Drop for now. "Nothing, unless you read your email differently." | email, DL, OI, C3v2 |
| D33 | 3D printing route | Recommendations | DL: "RESOLVED, default overturned." Evidence-led; Rulebook and case study not gates. | Gap Analysis, DL, OI Part 5 |
| D34 · OI C4 · C3v2 F4 | One recommendation or five routes | Recommendations | C3v2 F4: "now cleared… Nothing, unless you disagree." DL: "CLARIFICATION SENT." | Gap Analysis, DL, OI, C3, C3v2 |
| D35 · OI C5 · C3v2 F5 | Confidence tiers T0 to T3 | All signals, case studies | C3v2 F5: (a), (b), (c) confirmations; silence default. DL: "CLARIFICATION SENT." | Gap Analysis, DL, OI, C3v2 |
| D36 | Live Signal S/A/B/C tiers and minimum score | Live Signals | DL: "RESOLVED, default changed." Numeric score, no tiers, no minimum. | Gap Analysis, DL, OI Part 5 |
| D37 · OI P2 · O3v2 F7 | Tech Map Low/Medium/High risk logic | Tech Map | O3v2 F7: "Nothing from you unless you want it changed… keep… rename… or drop." DL: "OURS, sent; with Sahaj since 24 Sep 14:43." | DL, OI, O3, O3v2 |
| D38 + D49 · OI C6 · C3v2 F6 | Seat-count proxy (employee range thresholds); Lifecycle file columns and multi-date cells | Services rules, lifecycle | C3v2 F6: "Three things. (a) A yes to the employee-range proxy… (b) Is the Lifecycle file in use… (c) An unprotected copy." **Conflict:** DL marks the seat count "RESOLVED, default changed". | Gap Analysis, DL, OI, C3, C3v2 |
| D39 · Ag10 · OI O8 · O3v2 G1 | Empty-state behaviour for missing datasets | UI | O3v2 G1: open. "Please pick one… Our default is to show it with the message." **Conflict:** DL and OI propose leaving the section out. | AG, DL, OI, O3, O3v2 |
| D40 · OI O9 · O3v2 G2 | Source label set | UI | O3v2 G2: open. "Please approve this label set" (8 labels; publisher on news cards). | DL, OI, O3, O3v2 |
| D41 · OI O10 · O3v2 G3 | Data as-of date | UI | O3v2 G3: open. Default: the final consolidated drop. | DL, OI, O3, O3v2 |
| D42 · OI O11 · O3v2 H1 | GCP project ID and region; access | Environment | O3v2 H1: open. "Please confirm the project ID and whether the region is fixed." | email §4, DL, OI, O3, O3v2 |
| D43 | Inspection window for late drops | Process | DL: "RESOLVED. Agreed." | email §7, DL, OI Part 5 |
| D44 · O3v2 F8 | Proof method for 4 features with no v4 row | Proof placement | "(not yet put to you)". Default: as built. | DL, OI Part 4, O3v2 |
| D45 · O3v2 F9 | Case-study proof on Live Signals, Intent, Stakeholder Map, Tech Map | Proof placement | "(not yet put to you)". Default: after. | DL, OI Part 4, O3v2 |
| D46 · O3v2 F10 | Proof on service plays | Opportunity Map | "(not yet put to you)". Default: yes. | DL, OI Part 4, O3v2 |
| D47 · O3v2 F11 | Evidence-tier gate on proof | Proof placement | "(not yet put to you)". Default: apply it. | DL, OI Part 4, O3v2 |
| D48 · O3v2 F12 | APJ region preference | Proof ranking | "(not yet put to you)". Default: yes. | DL, OI Part 4, O3v2 |
| D50 · O3v2 F13 | Keyword table now, Rulebook IDs later | Proof matching | "(not yet put to you)". Default: yes. | DL, OI Part 4, O3v2 |
| D51 · OI O13 · O3v2 I1 | Realistic delivery date | Process | O3v2 I1: "(not answered in the annotated reply)" | email §7.4, DL, OI, O3v2 |
| D52 | JEV | Scope | DL: "RESOLVED. 'Drop it for now.'" | email §5.4, DL, OI Part 5 |
| D53 · OI O14 · O3v2 I2 | Consolidated drop with a contents list | Process | O3v2 I2: "(not answered…)" | email §3, DL, OI, O3v2 |

### 3a. Earlier question sets not carried into the 220 decision thread
No later status was found in any reviewed document for these, unless stated otherwise.

| Source | Question | Later status |
|---|---|---|
| Gap Analysis (18 Sep) | Does the rule "the engine must not open the original HP files" cover facts we extracted earlier? | Not carried forward |
| Gap Analysis | Genuine Wolf and HP IQ decks; a SKU-to-product table for Q426 | Not carried forward |
| Gap Analysis | Case-study publication dates, the wrong filing links, corrupted outcomes | Partly covered by D31 (the 89 are the corpus; corrupted figures hidden) and D14 |
| Meeting notes (14 Sep) | Intent location tags absent from Source A; the 41/37 against 12/34 category scores | Not carried forward (the QA report's ground truth uses 34/100) |
| Input Contract §5 (16 to 24 Sep) | 5.2 score scales; 5.3 truncated `(+N more)` tech lists; 5.4 empty `Level Of Intent`; 5.5 no `vendor` on technology_detections; 5.6 Tech_Breakdown columns; 5.7 enum casing | 5.1 maps to D27; 5.8 to D28; 5.9 to D19; 5.2 partly D20; 5.6 partly D22 (client: use WebStack and Tech_Breakdown). The others are not carried forward. |
| Evidence Score answers (15 Sep) | 8 "DECISION NEEDED" items (§8, §9, §25, §26, §27, §33, §35, §38) | Not carried forward |
| QA Response §3 / QA Discussion Points (16 Sep) | TM-11 %; SM-07 active employees; Strategy Chat citations; regeneration cost; about 200 unmapped technologies; Step 4 data suggestions; plus the validator-rule changes (OP-03/06/07, OM-10/13, CM-15, SM-10, link checks) | No answer recorded in the reviewed documents |

---

## 4. Overlap and duplication

**Lineage of the 220-account question thread:**
1. **AG (23 Sep morning).** Eleven items for the call. Nine are folded into DL almost verbatim: Ag1→D8, Ag2→D2, Ag3→D19, Ag4→D18, Ag5→D17, Ag6→D20, Ag7→D25, Ag8→D26, Ag9→D1. Ag10 splits into D22 and D39, and Ag11 becomes D28.
2. **DQ (sent 24 Sep 00:26).** Q1 to Q10. BridgeAI answered them as **opens_1**. Every Q is also restated in DL (Q1→D8, Q2→D3, Q3→D4, Q4→D5, Q5→D6, Q6→D16, Q7→D17, Q8→D24, Q9→D21, Q10→D22/D23/D11).
3. **TR (25 Sep).** An internal digest of the opens_1 answers to Q1 to Q10. It **duplicates** DL items 3, 4, 5, 6, 8, 11, 16, 17, 22 and 24, and the OI Part 1 deliveries. It adds only the filings verification detail, and it has internal inconsistencies ("Five open, five resolved" against six open; a stale "master account list").
4. **DL (items 1 to 43 sent 24 Sep; answered as opens_2).** The 25 Sep working copy adds Status lines and items 44 to 53. It is the **most complete register**: every item, resolved and open, with status and a summary.
5. **OI (25 Sep).** A client-facing restatement of DL's non-resolved items (Part 1 open, Part 2 clarifications, Part 3 owed, Part 4 not asked) plus DL's resolved items (Part 5). It is **almost fully duplicated** by DL (status) and by opens_3 v2 (open items and clarifications).
6. **clarifying_opens_3 non-v2 (Manisha, 25 Sep 00:10 to 01:21).** A parallel restructuring of the same 43 opens_2 items into three documents (OPEN 11, CLARIFICATIONS 7, UNRESOLVED 1), written without the OI content. It **conflicts** with DL and OI on:
   - the news precedence proposal ("Exa row as main" against the client's own skip rule)
   - the empty-state default (show a message against hide)
   - the Exa label (show "Exa" against publisher only)
   - the identity of the three mis-mapped filings accounts (Sunway, UOB and FIF against Fletcher, Fonterra and Astra)
   - the hiring gap (15 against 45)
   - the relevance rule (exact or alias matching against Dhruvi's use-case-fit rule)
7. **clarifying_opens_3 v2 (Yogesh merge, 25 Sep 07:27 to 07:28).** Manisha's format with nearly all OI content merged in:

   | OI item | v2 item |
   |---|---|
   | O2 | A3 |
   | O3 | A4 |
   | O4 | D2 |
   | O5 | E1 |
   | O6 | C5 |
   | O7 and C8 | D1 |
   | C1 | E4 |
   | C3 | E6 |
   | C4 | F4 |
   | C5 | F5 |
   | C6 | F6 |
   | C7 | D3 |
   | C9 | F3 |
   | C10 | E2 |
   | C11 | A2 |
   | C12 | E3 |
   | P1 | C4 |
   | P2 | F7 |
   | Part 4 | F1a to F1c, F8 to F13 |
   | O13 | I1 |
   | O14 | I2 |

   The Manisha errors are corrected: C4 is reversed ("Item 14 had them right the first time"), the hiring gap becomes 45, and D1 is reframed around the client's Q6 rule.

   It **adds new measured facts** found nowhere else:
   - VPBank's documents are filed under "VIETNAM POST CORPORATION"
   - Agribank's rows are empty
   - Jabil Inc. has "six SEC 10-Q rows, three keyed SG and three keyed MY"

   It **does not carry** OI Part 5 (the resolved-decisions table) or the DL resolved items.

**Which is the latest and most complete:**
- For **open questions and clarifications to BridgeAI**, the **clarifying_opens_3 v2 set** is the latest (07:27 to 07:28 on 25 Sep, after DL and OI at 01:06), and it is the most complete. It covers every open and clarification item in DL and OI, uses the numbering BridgeAI already works from (opens_2), and carries the newest data checks. Project memory also names it as the vehicle.
- For the **full decision record, including resolved rules**, the **DL working copy (25 Sep, uncommitted)** remains the only single place listing all 53 items with a status, and OI Part 5 is its client-facing twin. It is not the latest, though: several DL statuses and defaults are now contradicted by v2. v2 is newer, and in C5 it rests on newer data.

**Contradictions to reconcile before anything is sent or re-run:**
- The master list is not needed (DL D1) against "Please send the master list" (v2 A1).
- The Jabil Inc. default: Singapore only (DL, OI, TR) against both accounts as keyed (v2 C5).
- The empty-state default: hide (DL and OI) against "show it with the message" (v2 B4 and G1).
- D26 and D34: "CLARIFICATION SENT" (DL) against "now cleared" (v2 E5 and F4).
- Seat count: "RESOLVED" (DL D38) against "A yes to the employee-range proxy" still requested (v2 F6, OI C6).
- The v2 F1 wording "matches what we do today: exact or known-alias matches" sits awkwardly with the use-case-fit rule recorded as resolved in D29.
- The split output (10:53 IST, 25 Sep, the newest artifact) derives Public Bank as `publicbankgroup.com` and rewrites the aliases toward the Explorium domains, labelled "explicit approved alias". Both conflict with the DL D4 "held" status and the D5 "PredictLeads domain is canonical" rule.

**Other duplicates:**
- **QA-Discussion-Points** is a plain-language subset of **QA-Report-Response**: only the unfixed items, 12 points against 6 decisions plus 6 tool changes.
- **HP-Input-Data-Contract.md**, **hp-input-contract.json** and **hp-file-to-json-map.json** are the same contract in three forms. The md is the most current (last committed 24 Sep); the JSON files say 15 Sep. The **Handover** repeats the dataset-to-feature map.
- **The Gap Analysis** is the origin of DL D33 to D36, D38 and D49. Several of its recommendations were later overturned by BridgeAI: keep tiers (D36), and seller-entered seat count (D38).
- **The Remediation Checklist** overlaps the **QA Response** (`.bak` files and Astra fallbacks) and the Input Contract (header validation and silent failures).
