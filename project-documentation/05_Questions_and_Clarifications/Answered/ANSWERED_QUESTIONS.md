# Answered questions (34)

> Status values: RESOLVED = client answer settles it. PARTIALLY RESOLVED = answered, but a delivery, confirmation or sub-question is still outstanding (each has a file in `06_Unresolved_and_Open/`). OPEN = no answer. UNRESOLVED = answered, but the answer does not settle the point.
> IDs: D1–D43 = the 43 items of 220-Open-Decisions-List.md as numbered in clarifying opens_2.docx; D44–D53 = items added 24 Sep after the list went out; E18-x / E23-x = email Q&A of 18 and 23 Sep; QA16-x = the 16 Sep QA discussion points.

## Summary

| Id | Question | Feature | Status | Answered | Fully resolved? |
|---|---|---|---|---|---|
| D2 | Entity scope: APAC entity or global parent | Firmographics, hierarchy, Executive Dashboard | PARTIALLY RESOLVED | 2026-09-24 | Partly — a bare "RESOLVED" against a question that offered a default; taken as default acc… |
| D3 | Shared domains jabil.com and mufg.jp: which entity owns the rows | Hiring, tech detections, news, connections for 4 accounts | PARTIALLY RESOLVED | 2026-09-24 | Rule yes, data no. Round 3 A3: the columns exist but are populated on 384 of 14,965 job ro… |
| D4 | Blank domains: Public Bank and Westpac | All datasets for two accounts | PARTIALLY RESOLVED | 2026-09-24 | Westpac yes. Public Bank no — see D6; the two answers pull against each other (round 3 UNR… |
| D5 | Vendor domain mismatches (Posco, Pilipinas Shell, Shiseido, Stanley Electric) | Hiring, news, tech detections for 4 accounts | RESOLVED | 2026-09-24 | Yes. Note the split rewrites two aliases toward the Explorium domains (internal conflict I… |
| D7 | Hierarchy: 55 accounts without a sheet; blank parent | Executive Dashboard, firmographics | RESOLVED | 2026-09-23 | Yes. |
| D11 | Which filings source is authoritative; count; accounts without filings | Executive Dashboard financials/priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals | PARTIALLY RESOLVED | 2026-09-24 | Method yes. Reconciliation no: 31 excluded + 187 covered = 218, so Agribank and VPBank are… |
| D12 | Filing documents, not just links | Executive Dashboard, ingestion time | RESOLVED | 2026-09-24 | Yes as a rule; the Drive folder is not reachable from this machine (see MISSING_FILES.md C… |
| D13 | Filings window | Executive Dashboard | RESOLVED | 2026-09-24 | Yes. |
| D15 | Stock Exchange data of 3 Sep superseded? | Filings | RESOLVED | 2026-09-24 | Yes (filings 1.csv + PDFs replace it). |
| D16 | News precedence when Exa and Google News RSS disagree | Live Signals | PARTIALLY RESOLVED | 2026-09-24 | The skip rule is written; the client then re-marked the item open, and the "same event" de… |
| D17 | Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows | Live Signals, urgency, every time-based signal | PARTIALLY RESOLVED | 2026-09-24 | Rule yes; re-crawl not received. Exa is the only source for ~119 accounts, so they lose ov… |
| D19 | 12-month news window and 20-signal cap | Live Signals volume | RESOLVED | 2026-09-24 | Yes — default overturned: no cap. |
| D20 | Low-confidence news rows | Live Signals ranking | RESOLVED | 2026-09-24 | Yes. |
| D21 | Corrupted Thai text and raw HTML in Exa | News cards | RESOLVED | 2026-09-24 | Yes (HTML stripped by us; corrupted cells shown as delivered). |
| D22 | Coverage gaps: intent 173/220, jobs 175/220, technographics 207/220 | Intent & Demand, hiring, Technographic Map, urgency | PARTIALLY RESOLVED | 2026-09-24 | Rule yes; the job rows for the 45 accounts have not arrived; and "Related Technologies" is… |
| D23 | 219 vs 220: which account is absent from PredictLeads | PredictLeads | PARTIALLY RESOLVED | 2026-09-24 | Mostly; round 3 CLARIFICATIONS_v2 E2 asks whether the 31 Aug seed extract is the same form… |
| D24 | Duplicate record ids inside PredictLeads | Technology counts, news counts | RESOLVED | 2026-09-24 | Yes as an instruction (do not key on ids); round 3 E3 records duplicates as cleared. |
| D26 | 490 logged corrections: applied or to-do? | Hiring and tech dates | RESOLVED | 2026-09-24 | Yes, by inspection (internal finding stated to the client). |
| D27 | Job status: label wording and whether blank means open | exec_hiring_velocity, intent_hiring_demand, urgency driver 3 | PARTIALLY RESOLVED | 2026-09-24 | Scoring rule yes; label wording and the meaning of a blank status no. |
| D28 | Twelve PredictLeads keys with no consumer | Upload contract | RESOLVED | 2026-09-24 | Yes. The feature list for the Products sheet is only in a 23 Sep screenshot not on this ma… |
| D29 | Relevance threshold for Rulebook offerings and case studies | Every recommendation | PARTIALLY RESOLVED | 2026-09-24 | The rule is stated. Round 3 F1 asks for a one-line restatement and describes the build as … |
| D30 | Where the Rulebook and case studies appear | All features | RESOLVED | 2026-09-24 | Yes: as built (Objection Playbook, Opportunity Map, Content Messaging, Content Studio, Str… |
| D31 | 89 cleaned case studies as the corpus | Proof library | RESOLVED | 2026-09-24 | Yes. |
| D32 | "Recommendation for HP" on every Technographic Map section | Technographic Map | RESOLVED | 2026-09-24 | Yes. |
| D33 | 3D printing route without Rulebook rules | Recommendations | RESOLVED | 2026-09-24 | Yes — default overturned; evidence-led. |
| D34 | One recommendation or five routes | Opportunity Map ordering | PARTIALLY RESOLVED | 2026-09-24 | Cleared on our side; silence default; not confirmed. |
| D36 | Live Signal S/A/B/C tiers and minimum publish score | Live Signals | RESOLVED | 2026-09-24 | Yes — no tiers, no minimum; score /10 shown. |
| D38 | Service rules that need inputs the data lacks (seat count, WXP tier, print volumes, lifecycle dates) | Care Pack / WXP / Poly / Print rules; lifecycle check | PARTIALLY RESOLVED | 2026-09-24 | Pending items skipped and employee range used — yes. The specific employee-range threshold… |
| D43 | Inspection window for late-night drops | Process | RESOLVED | 2026-09-24 | Yes. |
| D52 | JEV (decision model) inside this delivery? | Scope | RESOLVED | 2026-09-24 | Yes. |
| E18-1 | Unencrypted copies of Lifecycle / Wolf / HP IQ | Reference | RESOLVED | 2026-09-18 | Yes by the client; the three files never reached this machine (MISSING_FILES.md). |
| E18-2 | Lifecycle/EOL for Fleet Refresh? | Urgency | RESOLVED | 2026-09-18 | Yes. |
| E23-2 | Opportunity Map three checks (Verified Evidence / Timing Trigger / HP Fit) | Opportunity Map | RESOLVED | 2026-09-23 | For the UI yes; what computes the Priority label is not stated by the client (CONFLICT C-0… |
| E23-4 | Which new PredictLeads sheets to use | Upload contract | PARTIALLY RESOLVED | 2026-09-23 | Yes, except the feature list for Products exists only in a screenshot not on this machine. |

## Detail

### D2 · Entity scope: APAC entity or global parent

- **Feature / topic:** Firmographics, hierarchy, Executive Dashboard
- **Original question:** Item 2. Vendor logged 141 field conflicts and kept the global HQ value each time (Jabil = Waltham MA, not Shatin HK). Default: APAC entity as named; firmographics as delivered.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "->RESOLVED" with no further words.
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Partly — a bare "RESOLVED" against a question that offered a default; taken as default accepted. Round 3 CLARIFICATIONS_v2 A2 asks for explicit confirmation.
- **Implementation impact:** Executive Dashboard header, firmographics, hierarchy for ~141 conflicted fields.
- **Unresolved-issue file:** `06_Unresolved_and_Open/02_entity_scope_resolved_ambiguously.md`

### D3 · Shared domains jabil.com and mufg.jp: which entity owns the rows

- **Feature / topic:** Hiring, tech detections, news, connections for 4 accounts
- **Original question:** Data question 2 (23 Sep) and item 3. Can vendors supply a per-entity id? Treat the pairs as one account? Which entity owns the rows?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 2: id "not possible currently"; one account each "no"; "Please take Company Name + Country into consideration along with the domain … Open: We will provide additional columns Company Name + Country in the mentioned sheets." opens_2 item 3: "ALREADY RESOLVED IN CLARIFYING_OPENS_1 DOC".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Rule yes, data no. Round 3 A3: the columns exist but are populated on 384 of 14,965 job rows, only for the secondary entities.
- **Implementation impact:** Jabil Malaysia / Singapore and MUFG Japan / Bangkok branch cannot be separated in hiring, technology, news, connections.
- **Unresolved-issue file:** `06_Unresolved_and_Open/03_shared_domains_name_country_columns.md`

### D4 · Blank domains: Public Bank and Westpac

- **Feature / topic:** All datasets for two accounts
- **Original question:** Data question 3 and item 4. Confirm publicbankgroup.com and westpac.com.au (we were deriving them).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 3: "pls look at below two domains: pbebank.com, westpac.com.au"; "Please populate Company Domain in the next delivery -> noted".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Westpac yes. Public Bank no — see D6; the two answers pull against each other (round 3 UNRESOLVED A4).
- **Implementation impact:** Public Bank: all PredictLeads data held; the 25 Sep split nevertheless derived publicbankgroup.com (internal conflict I-02).
- **Unresolved-issue file:** `06_Unresolved_and_Open/04_public_bank_domain_and_pbebank_rows.md`

### D5 · Vendor domain mismatches (Posco, Pilipinas Shell, Shiseido, Stanley Electric)

- **Feature / topic:** Hiring, news, tech detections for 4 accounts
- **Original question:** Data question 4 and item 5. Confirm the four aliases; is there a stable id?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 4: canonical domains are the PredictLeads ones; four overrides: Posco Group → posco.com, Pilipinas Shell → shell.com.ph, Shiseido → corp.shiseido.com, Stanley Electric → stanley.co.jp; vendors are fetched by Company Name + Country, so differing domains do not mean a wrong company; "where domain matching is ambiguous, use Company Name + Country as the fallback".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. Note the split rewrites two aliases toward the Explorium domains (internal conflict I-03) — engineering must align with the client direction.
- **Implementation impact:** Domain joins for those accounts; the alias table.

### D7 · Hierarchy: 55 accounts without a sheet; blank parent

- **Feature / topic:** Executive Dashboard, firmographics
- **Original question:** 23 Sep question 1 (PT Astra lists itself as its own parent) and item 7 (show "no hierarchy data" or leave the section out?).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 23 Sep: "If a Parent Name is provided there, we should use that parent relationship. If the Parent Name is blank, the parent relationship can be ignored for now." opens_2 item 7: "Resolved: nothing to mention, do not write 'no hierarchy data'."
- **Date answered:** 2026-09-23
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Hierarchy widget; the only client rule on empty states so far (say nothing).

### D11 · Which filings source is authoritative; count; accounts without filings

- **Feature / topic:** Executive Dashboard financials/priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals
- **Original question:** 18 Sep question 3, data question 10, item 11, round 3 C1/C5. 184 vs 186 vs 192 counts; document_url vs local_path; two NZ accounts linked to Malaysian parents.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 18 Sep: "Please use document_url where available and source_page_url as the fallback. Do not use local_path. Where both source URLs are blank, please exclude that record." opens_2 item 11: "RESOLVED: use filings 1.csv plus PredictLeads SEC Filings, merged on domain but where the domain is same … pls use company name and country … and yes pls consider 'the file shows 186 unique company names'" + list of 31 accounts with no public filings. opens_1 answer 10: "Sec filings: pls use from filings.csv + predictleads data->sec_filings".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Method yes. Reconciliation no: 31 excluded + 187 covered = 218, so Agribank and VPBank are on neither list (round 3 C1); Jabil Inc. 10-Q rows keyed SG and MY and Hyundai DART rows cannot be placed (round 3 C5); VPBank documents sit under "VIETNAM POST CORPORATION".
- **Implementation impact:** Financial figures and strategic priorities on the Executive Dashboard for those accounts.
- **Unresolved-issue file:** `06_Unresolved_and_Open/07_filings_reconciliation.md`

### D12 · Filing documents, not just links

- **Feature / topic:** Executive Dashboard, ingestion time
- **Original question:** Item 12. Are the URLs downloadable or will files be provided?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "RESOLVED: you can verify it with https://drive.google.com/drive/folders/1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP … wherever it is not downloaded, or links fail: we skip that particular file, not the whole company".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes as a rule; the Drive folder is not reachable from this machine (see MISSING_FILES.md C38).
- **Implementation impact:** compliance_filings ingestion.

### D13 · Filings window

- **Feature / topic:** Executive Dashboard
- **Original question:** Item 13. Confirm 12 months.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: last 12 months"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Older filings dropped at ingestion.

### D15 · Stock Exchange data of 3 Sep superseded?

- **Feature / topic:** Filings
- **Original question:** Item 15.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "already resolved: she shared with you different pdfs"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes (filings 1.csv + PDFs replace it).
- **Implementation impact:** None.

### D16 · News precedence when Exa and Google News RSS disagree

- **Feature / topic:** Live Signals
- **Original question:** Data question 6, item 16, round 3 D1. Exa replacement or supplement? Merge? Which wins?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 6: "no it is not a replacement … merging both … in the rare case that this happens, please skip that particular news item. Do not skip the company directly." opens_2 item 16: "->open" and forwarded to Sahaj on 24 Sep 14:43 UTC.
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** The skip rule is written; the client then re-marked the item open, and the "same event" definition (same account + same date + normalised headline; 356 duplicates removed) is ours and unconfirmed.
- **Implementation impact:** Which rows appear in Live Signals; 356 rows already removed as duplicates.
- **Unresolved-issue file:** `06_Unresolved_and_Open/08_news_precedence_and_same_event.md`

### D17 · Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows

- **Feature / topic:** Live Signals, urgency, every time-based signal
- **Original question:** Data question 7, item 17, round 3 D2.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 7: "We will provide the date wherever possible by crawling the URLs. For any rows where the date will still not available, please skip that news row for now, do not skip whole company/account"; epoch rows: "skip these three news items as of now".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Rule yes; re-crawl not received. Exa is the only source for ~119 accounts, so they lose over half their news until then.
- **Implementation impact:** Live Signals volume; AI/growth events in the urgency score.
- **Unresolved-issue file:** `06_Unresolved_and_Open/09_exa_event_dates.md`

### D19 · 12-month news window and 20-signal cap

- **Feature / topic:** Live Signals volume
- **Original question:** Item 19. Keep both?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Resolved: we should not keep the cap, pls use 12 month window"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned: no cap.
- **Implementation impact:** All scored signals in the window are shown; HP-Input-Data-Contract.md still documents the cap (stale).

### D20 · Low-confidence news rows

- **Feature / topic:** Live Signals ranking
- **Original question:** Item 20. Exclude Low, down-weight, or leave?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Already Resolved: mentioned in yesterday's meeting, pls do not use low/high confidence columns from those feeds"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** relevance_confidence column ignored.

### D21 · Corrupted Thai text and raw HTML in Exa

- **Feature / topic:** News cards
- **Original question:** Data question 9 and item 21.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 9: "This is the data which we get from tool itself"; "If you could help strip it on ingest, it would be appreciated".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes (HTML stripped by us; corrupted cells shown as delivered).
- **Implementation impact:** 28 cells for Thai accounts.

### D22 · Coverage gaps: intent 173/220, jobs 175/220, technographics 207/220

- **Feature / topic:** Intent & Demand, hiring, Technographic Map, urgency
- **Original question:** Data question 10, item 22, round 3 E1.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 10: "no data cases … Job Openings: … we will aggregate it from other tools and give you in same format … Technographics: Please look at the WebStack and Tech_Breakdown sheets … fallback … Related Technologies column".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Rule yes; the job rows for the 45 accounts have not arrived; and "Related Technologies" is researched, not detected, technology — round 3 E1 asks for one line confirming it is shown as such.
- **Implementation impact:** 45 accounts have no hiring widgets and no hiring driver in the Urgency Score.
- **Unresolved-issue file:** `06_Unresolved_and_Open/11_job_openings_45_accounts_and_related_technologies.md`

### D23 · 219 vs 220: which account is absent from PredictLeads

- **Feature / topic:** PredictLeads
- **Original question:** Item 23.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Astra: already provided initially … ALREADY RESOLVED IN CLARIFYING_OPENS_1 DOC"
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Mostly; round 3 CLARIFICATIONS_v2 E2 asks whether the 31 Aug seed extract is the same format and version as the 219-account file.
- **Implementation impact:** Astra hiring/tech/news come from the seed.
- **Unresolved-issue file:** `06_Unresolved_and_Open/12_astra_seed_extract_version.md`

### D24 · Duplicate record ids inside PredictLeads

- **Feature / topic:** Technology counts, news counts
- **Original question:** Data question 8 and item 24. De-dup on id, first row kept?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 8: "Why are we using IDs? We should use Domain + Company name for mapping." opens_2: "Why are we using ids, already mentioned that pls use domain, company name and country".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes as an instruction (do not key on ids); round 3 E3 records duplicates as cleared.
- **Implementation impact:** De-duplication keyed on domain + name + country + content, not vendor id.

### D26 · 490 logged corrections: applied or to-do?

- **Feature / topic:** Hiring and tech dates
- **Original question:** Item 26 and round 3 E5.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "clarifications needed"; cleared by our own inspection: 332 corrected values present, none old — the delivered file is post-correction.
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes, by inspection (internal finding stated to the client).
- **Implementation impact:** None; the log is not re-applied.

### D27 · Job status: label wording and whether blank means open

- **Feature / topic:** exec_hiring_velocity, intent_hiring_demand, urgency driver 3
- **Original question:** Input-contract 5.1 (16 Sep), item 27, round 3 E6. Blank and closed count for urgency (confirmed 16 Sep); label hiring widgets "postings seen" with the open count beside it?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 16 Sep: "please include both blank and closed job statuses for eligible records within the latest 12 months." opens_2 item 27: "clarifications needed".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Scoring rule yes; label wording and the meaning of a blank status no.
- **Implementation impact:** Label only for the widgets; the Hiring driver may be overstated if blank means unknown.
- **Unresolved-issue file:** `06_Unresolved_and_Open/14_job_status_label.md`

### D28 · Twelve PredictLeads keys with no consumer

- **Feature / topic:** Upload contract
- **Original question:** Item 28. Products for recommendations only; remove the rest?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Resolved: yes" (and 23 Sep: use sec_filings and products, ignore the others).
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. The feature list for the Products sheet is only in a 23 Sep screenshot not on this machine.
- **Implementation impact:** Upload contract; recommendations.

### D29 · Relevance threshold for Rulebook offerings and case studies

- **Feature / topic:** Every recommendation
- **Original question:** 21 Sep (email), 24 Sep email §5.1, item 29, round 3 F1. Exact/alias match only, or category-level match too?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Dhruvi 24 Sep 09:30 UTC: use-case/opportunity fit; "relevant" when clearly supported, "may be relevant / explore fit" when conditional; a technology or integration-route match alone is not sufficient (BHP Intune/ServiceNow example); case studies support an established opportunity, they do not create it. opens_2 item 29: "Already resolved: Explained in the email".
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** The rule is stated. Round 3 F1 asks for a one-line restatement and describes the build as "exact or known-alias matches only" — the build and the rule differ (CONFLICT X-09). Sub-items 29a-c not yet answered.
- **Implementation impact:** Every recommendation across all features.
- **Unresolved-issue file:** `06_Unresolved_and_Open/15_relevance_rule_implementation.md`

### D30 · Where the Rulebook and case studies appear

- **Feature / topic:** All features
- **Original question:** 21 Sep email, item 30.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: pls include stakeholder map as well"; 24 Sep annotation: already resolved by the 18 Sep mapping file.
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes: as built (Objection Playbook, Opportunity Map, Content Messaging, Content Studio, Strategy Chat, plus recommendation text in Executive Dashboard, Live Signals, Intent & Demand, Technographic Map) plus Stakeholder Map. Follow-ups F8-F13 have stated defaults.
- **Implementation impact:** Proof-point placement.

### D31 · 89 cleaned case studies as the corpus

- **Feature / topic:** Proof library
- **Original question:** Item 31.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: yes"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** hp_case_studies_final.csv 384 rows → 89 distinct studies; corrupted figures never shown.

### D32 · "Recommendation for HP" on every Technographic Map section

- **Feature / topic:** Technographic Map
- **Original question:** 24 Sep email §5.3, item 32.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "RESOLVED : DROP IT for now"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Card stays limited to the two categories it maps today (or is dropped).

### D33 · 3D printing route without Rulebook rules

- **Feature / topic:** Recommendations
- **Original question:** Item 33. Default: 3D intent scored but no product recommendation until rules exist.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "the absence of a matching 3D or Workstation rule in the Rulebook should not block an otherwise supported recommendation … Not every recommendation is expected to have a matching Rulebook entry or case study."
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned; evidence-led.
- **Implementation impact:** 3D and Workstation routes generate recommendations at the supported-opportunity level.

### D34 · One recommendation or five routes

- **Feature / topic:** Opportunity Map ordering
- **Original question:** Item 34 and round 3 F4.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "clarification needed, which five routes?" — round 3 F4 names them (3D Printing, Workstations, PC/Devices, Print, Poly, slide 5 of the 15 Sep deck) and states the build: strongest route as the recommendation, weaker ones as secondary hypotheses, per slide 3.
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Cleared on our side; silence default; not confirmed.
- **Implementation impact:** Opportunity Map ordering.
- **Unresolved-issue file:** `06_Unresolved_and_Open/16_one_primary_recommendation.md`

### D36 · Live Signal S/A/B/C tiers and minimum publish score

- **Feature / topic:** Live Signals
- **Original question:** 18 Sep question 4 and item 36.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 18 Sep: "I don't see the S/A/B/C tiering defined in the HP SEA limited poc … Could you please confirm where the current S/A/B/C classification in the UI is coming from"; opens_2: "Resolved: use live signal scoring logic as given as I can see in sea limited, there is a score instead of tiers".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — no tiers, no minimum; score /10 shown.
- **Implementation impact:** news_signals_feed; HP-Account-Intelligence-Rules.docx section is stale.

### D38 · Service rules that need inputs the data lacks (seat count, WXP tier, print volumes, lifecycle dates)

- **Feature / topic:** Care Pack / WXP / Poly / Print rules; lifecycle check
- **Original question:** Item 38 and round 3 F6.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved/clarification needed: pls ignore that pending HP input, and use whose data we fully have, no as of now we might not ask seller to enter seats, so hold employee range. lifecycle date, which columns to look into? -> clarifications needed"
- **Date answered:** 2026-09-24
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Pending items skipped and employee range used — yes. The specific employee-range thresholds (501 / 1,001 / 5,001) are ours and unconfirmed; which Lifecycle column (PE vs EM, duplicated PE heading, stacked dates in one cell) is unanswered; the readable Lifecycle file is not on this machine.
- **Implementation impact:** Which service rules fire; lifecycle gate in v4 §J.
- **Unresolved-issue file:** `06_Unresolved_and_Open/19_seat_proxy_and_lifecycle_columns.md`

### D43 · Inspection window for late-night drops

- **Feature / topic:** Process
- **Original question:** Item 43.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: yes"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Delivery planning.

### D52 · JEV (decision model) inside this delivery?

- **Feature / topic:** Scope
- **Original question:** 24 Sep email §5.4.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "RESOLVED : DROP IT for now"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Out of this delivery.

### E18-1 · Unencrypted copies of Lifecycle / Wolf / HP IQ

- **Feature / topic:** Reference
- **Original question:** 18 Sep question 1.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 18 Sep 07:28 UTC: "PFA the files" — Hp lifecycle june 2026.xlsx, Wolf_Security_Portfolio_Recreated.pptx, HP_IQ_for_Enterprise_Recreated.pptx.
- **Date answered:** 2026-09-18
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes by the client; the three files never reached this machine (MISSING_FILES.md).
- **Implementation impact:** Reference only (content folded into the Rulebook).

### E18-2 · Lifecycle/EOL for Fleet Refresh?

- **Feature / topic:** Urgency
- **Original question:** 18 Sep question 2.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Fleet Refresh should remain excluded for now … we don't have data showing which HP device models each account currently uses."
- **Date answered:** 2026-09-18
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Urgency has no Fleet Refresh driver.

### E23-2 · Opportunity Map three checks (Verified Evidence / Timing Trigger / HP Fit)

- **Feature / topic:** Opportunity Map
- **Original question:** 23 Sep question 2.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "we can drop these for now. Please retain only the Priority tags -Critical, High, Medium, Low as seen in sea limited".
- **Date answered:** 2026-09-23
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** For the UI yes; what computes the Priority label is not stated by the client (CONFLICT C-09).
- **Implementation impact:** opportunity_narrative_plays tags.

### E23-4 · Which new PredictLeads sheets to use

- **Feature / topic:** Upload contract
- **Original question:** 23 Sep question 4.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "please use the SEC Filings data … Please also use the Products sheet (mainly for recommendation purposes) for the following features: [screenshot]. You can ignore others".
- **Date answered:** 2026-09-23
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Yes, except the feature list for Products exists only in a screenshot not on this machine.
- **Implementation impact:** Products consumption.
- **Unresolved-issue file:** `06_Unresolved_and_Open/23_products_sheet_feature_list.md`
