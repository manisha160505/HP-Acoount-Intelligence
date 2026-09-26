# Answered questions (58)

> **26 Sep 03:26 UTC:** Dhruvi answered the six items of our 25 Sep 14:30 UTC email §5 inline: contact file delivered (D8, C49), ANZ Holdings NZ / CIMB / CIMB Niaga filing URLs (E25-4), Bank Mandiri rows belong to Mandiri (E25-5), risk logic approved (D37), GCP project ID to be explained (D42), hiring flexibility (D22). F12 was answered 25 Sep 09:36 UTC (D48) and F11 recorded as settled (D47).
> **25 Sep 05:50 UTC:** the client answered all 25 round-3 open items in the annotated `clarifying_opens_3_OPEN_v2_provided.docx` (C44). The CLARIFICATIONS (7) and UNRESOLVED_v2 (2) answers arrived 25 Sep 12:02 UTC as attachments that are not yet on this machine, so they are not ingested here.
> Status values: RESOLVED = client answer settles it. PARTIALLY RESOLVED = answered, but a delivery, confirmation or sub-question is still outstanding (each has a file in `06_Unresolved_and_Open/`). OPEN = no answer. UNRESOLVED = answered, but the answer does not settle the point.
> IDs: D1–D43 = the 43 items of 220-Open-Decisions-List.md as numbered in clarifying opens_2.docx; D44–D53 = items added 24 Sep after the list went out; E18-x / E23-x = email Q&A of 18 and 23 Sep; QA16-x = the 16 Sep QA discussion points.

## Summary

| Id | Question | Feature | Status | Answered | Fully resolved? |
|---|---|---|---|---|---|
| D1 | Canonical account list with one domain each | Identity / every join | RESOLVED | 2026-09-25 | Yes. The file (sheet "219 Account Audit", 219 rows, Astra absent because its data is the s… |
| D2 | Entity scope: APAC entity or global parent | Firmographics, hierarchy, Executive Dashboard | PARTIALLY RESOLVED | 2026-09-24 | Partly — a bare "RESOLVED" against a question that offered a default; taken as default acc… |
| D3 | Shared domains jabil.com and mufg.jp: which entity owns the rows | Hiring, tech detections, news, connections for 4 accounts | PARTIALLY RESOLVED | 2026-09-25 | Rule yes; data delivered 25 Sep 12:34 UTC (C48, predictleads_combined_219_accounts_company… |
| D4 | Blank domains: Public Bank and Westpac | All datasets for two accounts | RESOLVED | 2026-09-25 | Westpac AU = westpac.com.au, Westpac NZ = westpac.co.nz, Public Bank = pbebank.com per the… |
| D5 | Vendor domain mismatches (Posco, Pilipinas Shell, Shiseido, Stanley Electric) | Hiring, news, tech detections for 4 accounts | RESOLVED | 2026-09-24 | Yes. Note the split rewrites two aliases toward the Explorium domains (internal conflict I… |
| D6 | pbebank.com: Public Bank Bhd or Public Bank Lao? | One account | RESOLVED | 2026-09-25 | Yes, by the 25 Sep audit sheet: PUBLIC BANK BHD - MY = pbebank.com, PredictLeads "Public B… |
| D7 | Hierarchy: 55 accounts without a sheet; blank parent | Executive Dashboard, firmographics | RESOLVED | 2026-09-23 | Yes. |
| D8 | Contact file for the 220 accounts | Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio, Message Evaluator (BLOCKER) | PARTIALLY RESOLVED | 2026-09-26 | Delivered: Apollo_All_Contacts (1).xlsx (C49), 2,296 contacts for 192 of 220 accounts, key… |
| D9 | Role coverage: ~30 buying-committee roles, then 5-8 more | Contacts | RESOLVED | 2026-09-25 | Yes — one file, built once. |
| D10 | Stakeholder Map with zero contacts: message or hidden | UI for every account until contacts arrive | RESOLVED | 2026-09-25 | Yes — default overturned: leave the space empty, no message. |
| D11 | Which filings source is authoritative; count; accounts without filings | Executive Dashboard financials/priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals | PARTIALLY RESOLVED | 2026-09-25 | Method yes. Round 3 C5 (25 Sep) placed the two rows: Jabil Inc. 10-Q rows → "yes you can f… |
| D12 | Filing documents, not just links | Executive Dashboard, ingestion time | RESOLVED | 2026-09-24 | Yes as a rule; the Drive folder is not reachable from this machine (see MISSING_FILES.md C… |
| D13 | Filings window | Executive Dashboard | RESOLVED | 2026-09-24 | Yes. |
| D14 | Three accounts with a wrong filings mapping | Filings | RESOLVED | 2026-09-25 | Yes for the three accounts (we re-key the rows ourselves to those domains; no corrected fi… |
| D15 | Stock Exchange data of 3 Sep superseded? | Filings | RESOLVED | 2026-09-24 | Yes (filings 1.csv + PDFs replace it). |
| D16 | News precedence when Exa and Google News RSS disagree | Live Signals | RESOLVED | 2026-09-25 | Round 3 D1 (25 Sep): "Resolved: to disagreement; consider exa news" — when the two feeds d… |
| D17 | Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows | Live Signals, urgency, every time-based signal | PARTIALLY RESOLVED | 2026-09-25 | Delivered 25 Sep 12:34 UTC: exa_data (3)_2025-2026.xlsx (C46, 3,726 rows) and google_news_… |
| D18 | Exa as its own dataset key and on-screen label | Source labels on news cards | PARTIALLY RESOLVED | 2026-09-25 | In practice yes via G2 (publisher name on news cards, vendor names never shown; an exa key… |
| D19 | 12-month news window and 20-signal cap | Live Signals volume | RESOLVED | 2026-09-24 | Yes — default overturned: no cap. |
| D20 | Low-confidence news rows | Live Signals ranking | RESOLVED | 2026-09-24 | Yes. |
| D21 | Corrupted Thai text and raw HTML in Exa | News cards | RESOLVED | 2026-09-24 | Yes (HTML stripped by us; corrupted cells shown as delivered). |
| D22 | Coverage gaps: intent 173/220, jobs 175/220, technographics 207/220 | Intent & Demand, hiring, Technographic Map, urgency | PARTIALLY RESOLVED | 2026-09-25 | 25 Sep 12:34 UTC: "The job-opening data currently available in the PredictLeads file shoul… |
| D23 | 219 vs 220: which account is absent from PredictLeads | PredictLeads | PARTIALLY RESOLVED | 2026-09-24 | Mostly; round 3 CLARIFICATIONS_v2 E2 asks whether the 31 Aug seed extract is the same form… |
| D24 | Duplicate record ids inside PredictLeads | Technology counts, news counts | RESOLVED | 2026-09-24 | Yes as an instruction (do not key on ids); round 3 E3 records duplicates as cleared. |
| D26 | 490 logged corrections: applied or to-do? | Hiring and tech dates | RESOLVED | 2026-09-24 | Yes, by inspection (internal finding stated to the client). |
| D27 | Job status: label wording and whether blank means open | exec_hiring_velocity, intent_hiring_demand, urgency driver 3 | PARTIALLY RESOLVED | 2026-09-24 | Scoring rule yes; label wording and the meaning of a blank status no. |
| D28 | Twelve PredictLeads keys with no consumer | Upload contract | RESOLVED | 2026-09-24 | Yes. The feature list for the Products sheet is only in a 23 Sep screenshot not on this ma… |
| D29 | Relevance threshold for Rulebook offerings and case studies | Every recommendation | RESOLVED | 2026-09-25 | The rule is stated and was restated on 25 Sep with seven pointers (evidence first; Ruleboo… |
| D30 | Where the Rulebook and case studies appear | All features | RESOLVED | 2026-09-24 | Yes: as built (Objection Playbook, Opportunity Map, Content Messaging, Content Studio, Str… |
| D31 | 89 cleaned case studies as the corpus | Proof library | RESOLVED | 2026-09-24 | Yes. |
| D32 | "Recommendation for HP" on every Technographic Map section | Technographic Map | RESOLVED | 2026-09-24 | Yes. |
| D33 | 3D printing route without Rulebook rules | Recommendations | RESOLVED | 2026-09-24 | Yes — default overturned; evidence-led. |
| D34 | One recommendation or five routes | Opportunity Map ordering | PARTIALLY RESOLVED | 2026-09-24 | Cleared on our side; silence default; not confirmed. |
| D36 | Live Signal S/A/B/C tiers and minimum publish score | Live Signals | RESOLVED | 2026-09-24 | Yes — no tiers, no minimum; score /10 shown. |
| D37 | Technographic Map Low/Medium/High risk logic | Technographic Map | RESOLVED | 2026-09-26 | Yes. The logic we sent (round 3 F7) is approved - Dhruvi says so, citing her CLARIFICATION… |
| D38 | Service rules that need inputs the data lacks (seat count, WXP tier, print volumes, lifecycle dates) | Care Pack / WXP / Poly / Print rules; lifecycle check | PARTIALLY RESOLVED | 2026-09-24 | Pending items skipped and employee range used — yes. The specific employee-range threshold… |
| D39 | Empty-state behaviour for any missing dataset | Every widget | RESOLVED | 2026-09-25 | Yes for now — default overturned: leave the section out, nothing on screen; may be revisit… |
| D40 | Source label set on screen | Every source chip | RESOLVED | 2026-09-25 | Yes for now — our label set applies (publisher name on news cards, no vendor names); may b… |
| D41 | Data as-of date | As-of line on every screen; recency anchor | RESOLVED | 2026-09-25 | Yes — default overturned: show each dataset's own ingestion/retrieval date, not one drop d… |
| D43 | Inspection window for late-night drops | Process | RESOLVED | 2026-09-24 | Yes. |
| D44 | Proof method for the four features with no v4 row (Objection Playbook, Content Studio, Strategy Chat, Message Evaluator) | Proof placement | RESOLVED | 2026-09-25 | Yes, as built, under the four-case rule (which we should confirm back as our reading). |
| D45 | Case-study proof on the signal features (Live Signals, Intent & Demand, Stakeholder Map, Technographic Map): now or after? | Proof placement | RESOLVED | 2026-09-25 | Yes: include now, in exactly those slots; Stakeholder Map NOT for now (reverses opens_2 #3… |
| D46 | Proof on service plays in the Opportunity Map | Opportunity Map | RESOLVED | 2026-09-25 | Yes. |
| D47 | Evidence-tier gate on proof (only once an Opportunity is established by two pipelines) | Proof placement | RESOLVED | 2026-09-25 | Yes, as option A (the round-4 default): an HP offering is named and proof attached at the … |
| D48 | APJ region preference as the second sort key for proof | Proof ranking | RESOLVED | 2026-09-25 | Yes: use case → industry → APJ/APAC → stated outcome → T0 before T2; region inferred from … |
| D50 | Product-line mapping for case studies: keyword table now, Rulebook offering ids after | Proof matching | RESOLVED | 2026-09-25 | Yes — default overturned: no Rulebook-id mapping later either; use-case matching only. |
| D29a | Integration route detected on its own shown as a context line? | Recommendations | RESOLVED | 2026-09-25 | Yes, with a wording change: drop the phrase "no need evidenced". |
| D29b | Conditions the data cannot evaluate treated as unmet (offering reaches "may be relevant" but never "relevant") | Recommendations | RESOLVED | 2026-09-25 | Yes. |
| D29c | Use-case vocabulary table (Rulebook opportunity type → case-study solution area/tags) | Case studies | RESOLVED | 2026-09-25 | Yes — default overturned: NO mapping table; independent matching of each against the accou… |
| D51 | A realistic delivery date starting from the day data and GCP access are in hand | Process | RESOLVED | 2026-09-25 | Process answer: dates go through the WhatsApp group; Sahaj decides. No date given. |
| D53 | Remaining deliveries as one consolidated drop with a contents list | Process | RESOLVED | 2026-09-25 | Noted, not committed. |
| D52 | JEV (decision model) inside this delivery? | Scope | RESOLVED | 2026-09-24 | Yes. |
| E25-4 | Filings for ANZ Holdings NZ, CIMB Group Holdings and CIMB Niaga (absent from filings 1.csv and from the 31-account no-filings list) | Filings: Executive Dashboard financials/priorities | RESOLVED | 2026-09-26 | Yes. Rows added as Filings/filings_client_supplement_2026-09-26.csv (row_id S26-1..6) in f… |
| E25-5 | Bank Mandiri vs Bank Central Asia: two filings rows named Bank Mandiri carry BCA's territory | Filings | RESOLVED | 2026-09-26 | Yes. FILINGS_CLIENT_RULINGS in split_account_data.py files both rows under PT_BANK_MANDIRI… |
| E18-1 | Unencrypted copies of Lifecycle / Wolf / HP IQ | Reference | RESOLVED | 2026-09-18 | Yes by the client; the three files never reached this machine (MISSING_FILES.md). |
| E18-2 | Lifecycle/EOL for Fleet Refresh? | Urgency | RESOLVED | 2026-09-18 | Yes. |
| E23-2 | Opportunity Map three checks (Verified Evidence / Timing Trigger / HP Fit) | Opportunity Map | RESOLVED | 2026-09-23 | For the UI yes; what computes the Priority label is not stated by the client (CONFLICT C-0… |
| E23-4 | Which new PredictLeads sheets to use | Upload contract | PARTIALLY RESOLVED | 2026-09-23 | Yes, except the feature list for Products exists only in a screenshot not on this machine. |

## Detail

### D1 · Canonical account list with one domain each

- **Feature / topic:** Identity / every join
- **Original question:** 220-Open-Decisions-List item 1 (24 Sep). 220 Explorium workbooks resolve to 217 unique domains; identity blank on 209 of 219 rows. Default offered: the domains in _RUN_SUMMARY.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "OPEN: WILL GIVE THAT" (clarifying opens_2, 24 Sep). Round 3 A1 re-asked. 25 Sep 05:50 UTC: Dhruvi sent PredictLeads_219_Account_Domain_Audit.xlsx — "The file contains the correct domain to be used for each account … use the domain as the primary reference for data mapping" (sheet 219_Account_Domain_Audit only; Column H marks same-account name variants; Column B = dashboard display name).
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. The file (sheet "219 Account Audit", 219 rows, Astra absent because its data is the separate seed delivery) gives Master Domain per account; 13 rows are marked "consider both names same"; Column B "Master Company" is the dashboard name. Three domains differ from the 25 Sep split (Posco posco.com, Pilipinas Shell shell.com.ph, Public Bank pbebank.com) — the split must be rebuilt from this sheet.
- **Implementation impact:** Every join, the split, every per-account run. Three accounts appeared to have no intent data until alias domains were applied.

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
- **Date answered:** 2026-09-25
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Rule yes; data delivered 25 Sep 12:34 UTC (C48, predictleads_combined_219_accounts_company_country.xlsm): company_name and account_country_code on every row of every sheet. On jabil.com and mufg.jp, 270 of 1,313 rows name BOTH entities (e.g. "JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG", country "MY; SG"), 114 of them in job_openings (of 314).
- **Implementation impact:** Jabil Malaysia / Singapore and MUFG Japan / Bangkok branch can now be separated for single-entity rows; the dual-entity rows need a rule (attach to both, as for the Jabil 10-Q, or neither).
- **Unresolved-issue file:** `06_Unresolved_and_Open/03_shared_domains_name_country_columns.md`

### D4 · Blank domains: Public Bank and Westpac

- **Feature / topic:** All datasets for two accounts
- **Original question:** Data question 3 and item 4. Confirm publicbankgroup.com and westpac.com.au (we were deriving them).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 3: "pls look at below two domains: pbebank.com, westpac.com.au"; "Please populate Company Domain in the next delivery -> noted".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Westpac AU = westpac.com.au, Westpac NZ = westpac.co.nz, Public Bank = pbebank.com per the 25 Sep audit sheet, where the PredictLeads row "Public Bank Lao Limited" is marked "OK" and the email says "domain is matching irrespective of their names". This overrides our UNRESOLVED A4 concern (the client has decided the Lao rows belong to the account). Applied in the split on 25 Sep (pbebank.com).
- **Implementation impact:** Public Bank PredictLeads rows are used under pbebank.com.

### D5 · Vendor domain mismatches (Posco, Pilipinas Shell, Shiseido, Stanley Electric)

- **Feature / topic:** Hiring, news, tech detections for 4 accounts
- **Original question:** Data question 4 and item 5. Confirm the four aliases; is there a stable id?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 4: canonical domains are the PredictLeads ones; four overrides: Posco Group → posco.com, Pilipinas Shell → shell.com.ph, Shiseido → corp.shiseido.com, Stanley Electric → stanley.co.jp; vendors are fetched by Company Name + Country, so differing domains do not mean a wrong company; "where domain matching is ambiguous, use Company Name + Country as the fallback".
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. Note the split rewrites two aliases toward the Explorium domains (internal conflict I-03); aligned on 25 Sep, the aliases now point toward the audit sheet's domains.
- **Implementation impact:** Domain joins for those accounts; the alias table.

### D6 · pbebank.com: Public Bank Bhd or Public Bank Lao?

- **Feature / topic:** One account
- **Original question:** Data question 5 and item 6.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 5: "open: We will try and give you exact name 'public bank bhd' data for predictleads_combined_219_accounts.xlsx … Public Bank Lao Limited is a wholly-owned subsidiary of Public Bank Berhad, which is why the same domain is associated with both entities."
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes, by the 25 Sep audit sheet: PUBLIC BANK BHD - MY = pbebank.com, PredictLeads "Public Bank Lao Limited" marked OK ("domain is matching irrespective of their names"). No separate Public Bank Bhd rows are coming.
- **Implementation impact:** Public Bank PredictLeads data used.

### D7 · Hierarchy: 55 accounts without a sheet; blank parent

- **Feature / topic:** Executive Dashboard, firmographics
- **Original question:** 23 Sep question 1 (PT Astra lists itself as its own parent) and item 7 (show "no hierarchy data" or leave the section out?).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 23 Sep: "If a Parent Name is provided there, we should use that parent relationship. If the Parent Name is blank, the parent relationship can be ignored for now." opens_2 item 7: "Resolved: nothing to mention, do not write 'no hierarchy data'."
- **Date answered:** 2026-09-23
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Hierarchy widget; the only client rule on empty states so far (say nothing).

### D8 · Contact file for the 220 accounts

- **Feature / topic:** Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio, Message Evaluator (BLOCKER)
- **Original question:** Data question 1 (23 Sep), item 8, 24 Sep email §3, round 3 B2. Contacts sheet empty in all 220 workbooks; Apollo_All_Contacts named in v4 not received.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1: "Ans 1) Contact Data open". opens_2 section B: "->OPEN". Round 3 B2 (25 Sep): "-> open: will give that". Per B3 there will be ONE file: "as of now we go with whatever we have, you will get one file". 26 Sep 03:26 UTC (reply to our 25 Sep 14:30 email §5.1): "Resolved: Apollo_all_contacts(1) uploaded in the google drive folder; as sahaj mentioned , if we can pls be flexible on this ->we are pulling data and will comeback with few more details if we can".
- **Date answered:** 2026-09-26
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Delivered: Apollo_All_Contacts (1).xlsx (C49), 2,296 contacts for 192 of 220 accounts, keyed Company Name + Country Code + domain (all 2,296 rows matched an account). 28 accounts have no contacts (listed in 04_Data_and_Source_Definitions/Contacts_Apollo/README.md) and the client may send "few more details". Split into prospect_contacts on 26 Sep; Astra keeps its pilot seed pending an internal decision.
- **Implementation impact:** The five contact features can now be built for 192 accounts (Stakeholder Map left empty on the other 28, per D10). Contacts carry no persona and no verified email status; 6 emails that name a different person are withheld, 54 are flagged as a non-company domain, 130 rows are the same person under both sister entities (Jabil, MUFG, UOB).
- **Unresolved-issue file:** `06_Unresolved_and_Open/05_contact_file_partial_coverage.md`

### D9 · Role coverage: ~30 buying-committee roles, then 5-8 more

- **Feature / topic:** Contacts
- **Original question:** Item 9 and round 3 B3.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 B3 (25 Sep): "Resolved: this is already discussed in yesterday's meeting, as of now we go with whatever we have, you will get one file".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — one file, built once.
- **Implementation impact:** The five contact features are built once.

### D10 · Stakeholder Map with zero contacts: message or hidden

- **Feature / topic:** UI for every account until contacts arrive
- **Original question:** Item 10 and round 3 B4. Default: show the empty state with a message.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 B4 (25 Sep): "Resolved: do not write anything, leave that space empty".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned: leave the space empty, no message.
- **Implementation impact:** Stakeholder Map on accounts with no contacts shows nothing.

### D11 · Which filings source is authoritative; count; accounts without filings

- **Feature / topic:** Executive Dashboard financials/priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals
- **Original question:** 18 Sep question 3, data question 10, item 11, round 3 C1/C5. 184 vs 186 vs 192 counts; document_url vs local_path; two NZ accounts linked to Malaysian parents.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 18 Sep: "Please use document_url where available and source_page_url as the fallback. Do not use local_path. Where both source URLs are blank, please exclude that record." opens_2 item 11: "RESOLVED: use filings 1.csv plus PredictLeads SEC Filings, merged on domain but where the domain is same … pls use company name and country … and yes pls consider 'the file shows 186 unique company names'" + list of 31 accounts with no public filings. opens_1 answer 10: "Sec filings: pls use from filings.csv + predictleads data->sec_filings".
- **Date answered:** 2026-09-25
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Method yes. Round 3 C5 (25 Sep) placed the two rows: Jabil Inc. 10-Q rows → "yes you can for now" (attach to both Jabil accounts as keyed); Hyundai DART rows → the account is "HKMC GROUP(HYUNDAI AUTOEVER) – KR", domain hyundai-autoever.com, reports are Hyundai Autoever Corp.'s ("in explorium, predictleads everywhere it is this name"). Still open: Agribank and VPBank (round 3 CLARIFICATIONS C1, not answered) and VPBank documents keyed under "VIETNAM POST CORPORATION". 26 Sep 03:26 UTC settled two more (E25-4, E25-5): the client sent document URLs for ANZ Holdings NZ (3), CIMB Group Holdings (2) and CIMB Niaga (1), now in Filings/filings_client_supplement_2026-09-26.csv; and the two "PT Bank Mandiri" rows carrying BCA's territory belong to Bank Mandiri.
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

### D14 · Three accounts with a wrong filings mapping

- **Feature / topic:** Filings
- **Original question:** 18 Sep question 3 and item 14; names sent in round 3 C4: Fletcher Building (rows carry sunway.com.my), Fonterra (uob.com.my), Astra (fifgroup.co.id; plus a blank-domain row holding United Tractors statements).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 C4 (25 Sep): Fletcher Building Holdings NZ domain is fletcherbuilding.com; Fonterra domain is fonterra.com; Astra/United Tractors row: "resolved: leave that row if it is not matching to astra" (exclude it).
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes for the three accounts (we re-key the rows ourselves to those domains; no corrected file is coming). Federal International Finance still has no filings of its own — not addressed.
- **Implementation impact:** Fletcher and Fonterra rows re-keyed; the United Tractors row excluded; FIF empty.

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
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Round 3 D1 (25 Sep): "Resolved: to disagreement; consider exa news" — when the two feeds disagree on the same event, keep the Exa row (this REPLACES the 24 Sep "skip that news item" answer). The same-event definition was not commented on; our definition stands as the working rule (INTERNAL).
- **Implementation impact:** Disagreeing pairs now keep the Exa row instead of being dropped; 356 exact duplicates still merged.

### D17 · Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows

- **Feature / topic:** Live Signals, urgency, every time-based signal
- **Original question:** Data question 7, item 17, round 3 D2.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** opens_1 answer 7: "We will provide the date wherever possible by crawling the URLs. For any rows where the date will still not available, please skip that news row for now, do not skip whole company/account"; epoch rows: "skip these three news items as of now".
- **Date answered:** 2026-09-25
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** Delivered 25 Sep 12:34 UTC: exa_data (3)_2025-2026.xlsx (C46, 3,726 rows) and google_news_rss_data 2 (2)_2025-2026.xlsx (C47, 4,159 rows), every row dated; undatable rows left out of the files; "last 12 months only". Both files start at 2025-01-01, so the 12-month window is still applied on ingest (Exa 2,929 rows / 215 accounts in window; RSS 2,876 / 93).
- **Implementation impact:** Live Signals volume; AI/growth events in the urgency score.
- **Unresolved-issue file:** `06_Unresolved_and_Open/09_exa_event_dates.md`

### D18 · Exa as its own dataset key and on-screen label

- **Feature / topic:** Source labels on news cards
- **Original question:** Item 18 and round 3 UNRESOLVED D3. Add a dedicated Exa key, or accept the "Google News" label?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Resolved: pls use domain + company name + country" — answers matching, not labelling. UNRESOLVED_v2 D3 itself was not returned, but G2 (25 Sep) approved our label set, whose news-card rule is "publisher name, no feed name".
- **Date answered:** 2026-09-25
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** In practice yes via G2 (publisher name on news cards, vendor names never shown; an exa key keeps the origin in the record). D3 as such is unanswered.
- **Implementation impact:** News cards show the publisher; Exa origin retained in data.
- **Unresolved-issue file:** `06_Unresolved_and_Open/10_exa_source_label.md`

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
- **Client answer:** opens_1 answer 10: "no data cases … Job Openings: … we will aggregate it from other tools and give you in same format … Technographics: Please look at the WebStack and Tech_Breakdown sheets … fallback … Related Technologies column". 26 Sep 03:26 UTC, on our "Hiring data for the remaining accounts, whenever the vendors deliver it": "thank you for this flexibility".
- **Date answered:** 2026-09-25
- **Status:** **PARTIALLY RESOLVED**
- **Does the answer fully resolve it?** 25 Sep 12:34 UTC: "The job-opening data currently available in the PredictLeads file should be considered the final hiring dataset for now. We are reaching out to the vendors … for the remaining 43 accounts … I request if we can be flexible on this." Our split: 176 of 220 accounts have job rows (175 domains + the Astra seed), so 44 without. The Related-Technologies-as-researched line was not separately confirmed.
- **Implementation impact:** 44 accounts have no hiring widgets and no hiring driver in the Urgency Score until the vendors deliver.
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
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** The rule is stated and was restated on 25 Sep with seven pointers (evidence first; Rulebook second; technology alone insufficient; wording by evidence; conflicting evidence such as WebEx + Poly Intent 0 blocks a Poly recommendation; case studies by use case; never force). Sub-items 29a-c answered the same day (see D29a-c). The build described on 25 Sep still used exact/alias matching (CONFLICT X-09) — an engineering follow-up, not a client question.
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

### D37 · Technographic Map Low/Medium/High risk logic

- **Feature / topic:** Technographic Map
- **Original question:** 23 Sep (Dhruvi asked us); item 37; logic sent 23 Sep as a screenshot and in words in round 3 F7.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 23 Sep: "Please retain the Low Risk / Medium Risk / High Risk labels … what logic is currently being used"; opens_2: "open" and forwarded to Sahaj; round 3 F7 (25 Sep): "OPEN; already escalated to Sahaj". 26 Sep 03:26 UTC, on our "keep as shared, rename, or drop": "can you pls elaborate more on this, because in one of the opens I replied that you can use the risk logic which you shared, hence which are these labels ?"
- **Date answered:** 2026-09-26
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. The logic we sent (round 3 F7) is approved - Dhruvi says so, citing her CLARIFICATIONS/UNRESOLVED answers of 25 Sep 12:02 UTC (attachment not on this machine). The labels are the Low / Medium / High Risk she asked us to retain on 23 Sep, so our "rename or drop" offer was redundant; nothing changes in the product.
- **Implementation impact:** technographic_map risk column stays as built.
- **Unresolved-issue file:** `06_Unresolved_and_Open/18_tech_map_risk_labels.md`

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

### D39 · Empty-state behaviour for any missing dataset

- **Feature / topic:** Every widget
- **Original question:** Item 39, round 3 G1. Show with a "no data from source" message or hide?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 G1 (25 Sep): "Resolved: leave it out, do not write anything as of now; but pls keep in mind this is already escalated to sahaj; so later on if we have any tweak, can we pls be flexible, right now do not show anything".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes for now — default overturned: leave the section out, nothing on screen; may be revisited after Sahaj's review.
- **Implementation impact:** Contacts (all accounts), hiring (45 accounts), filings (31 accounts): sections omitted; the absent-dataset list goes to the run report.

### D40 · Source label set on screen

- **Feature / topic:** Every source chip
- **Original question:** Item 40, round 3 G2. Approve Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study; publisher name on news cards; no vendor names.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 G2 (25 Sep): "Right now go ahead with your labels: this is already escalated to sahaj; so later on if we have any tweak, can we pls be flexible".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes for now — our label set applies (publisher name on news cards, no vendor names); may be tweaked after Sahaj's review.
- **Implementation impact:** UI labels everywhere; closes the Exa label question in practice (D18).

### D41 · Data as-of date

- **Feature / topic:** As-of line on every screen; recency anchor
- **Original question:** Item 41, round 3 G3. Date of the 23 Sep drop or of the final consolidated drop?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Round 3 G3 (25 Sep): "Resolved so let us show dataset's own retrieval date: meaning if we ingested the data for eg on 20th sept, keep that".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned: show each dataset's own ingestion/retrieval date, not one drop date. Consistent with v4 §E.
- **Implementation impact:** As-of line per dataset; recency anchor = ingestion date (closes CONFLICT C-02).

### D43 · Inspection window for late-night drops

- **Feature / topic:** Process
- **Original question:** Item 43.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: yes"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Delivery planning.

### D44 · Proof method for the four features with no v4 row (Objection Playbook, Content Studio, Strategy Chat, Message Evaluator)

- **Feature / topic:** Proof placement
- **Original question:** Round 3 F8 (item 44). Default: as built (one case study per area card; a Proof Points section per asset; citations of attached proof; Rulebook facts only).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "yes, just clarifying you mean below things for the case study and rulebook facts part, correct?" followed by the four-case rule: Rulebook offering + similar case study → use both; Rulebook offering, no case study → Rulebook only; case study with similar use case but no supported offering → case study as supporting proof, do not force an offering; neither relevant → use neither.
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes, as built, under the four-case rule (which we should confirm back as our reading).
- **Implementation impact:** Proof slots in the four features.

### D45 · Case-study proof on the signal features (Live Signals, Intent & Demand, Stakeholder Map, Technographic Map): now or after?

- **Feature / topic:** Proof placement
- **Original question:** Round 3 F9 (item 45). Default: after, on the same matcher.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "we use this just to strengthen the recommendation, and it is there in recommendation logic v4 as well: Live Signals: if you can include just in 'Implication for HP'; Intent and Demand: in 'So what for HP'; stakeholder: correct (Sahaj mentioned not right now in yesterday's meeting); technographic: just in 'what it means for HP', nowhere else; we are not trying to compulsorily include it, but for recommendation purposes to strengthen what we already recommend … if we can use, it would be appreciated".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes: include now, in exactly those slots; Stakeholder Map NOT for now (reverses opens_2 #30); optional, never forced.
- **Implementation impact:** Live Signals "Implication for HP", Intent "So what for HP", Technographic Map "what it means for HP".

### D46 · Proof on service plays in the Opportunity Map

- **Feature / topic:** Opportunity Map
- **Original question:** Round 3 F10 (item 46). Default: yes.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "keep default"
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Proof attaches to WXP / Care / Poly / Print plays too.

### D47 · Evidence-tier gate on proof (only once an Opportunity is established by two pipelines)

- **Feature / topic:** Proof placement
- **Original question:** Round 3 F11 (item 47). Default: apply it.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "clarification needed pls" (OPEN_v2). Re-explained in clarifying_opens_4_OPEN_and_CLARIFICATIONS.docx (options A/B, default A). Yogesh 25 Sep 09:10 UTC: "F11. Evidence-tier gate on proof. is resolved"; our 25 Sep 14:30 UTC email lists F11 under "Settled by your answers today" with no objection in the 26 Sep reply.
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes, as option A (the round-4 default): an HP offering is named and proof attached at the Opportunity tier only, on every feature. The client's own words choosing A are not in the email thread; the resolution rests on our 09:10 and 14:30 emails, which she did not contest.
- **Implementation impact:** Thin accounts show no offering or case study on objection cards and Content Studio proof points until two pipelines agree.

### D48 · APJ region preference as the second sort key for proof

- **Feature / topic:** Proof ranking
- **Original question:** Round 3 F12 (item 48). Default: yes. Re-asked by Yogesh 25 Sep 09:10 UTC with three sub-questions.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Dhruvi 25 Sep 09:36 UTC: "This is correct :1. Same use case → 2. Same industry → 3. APJ/APAC region → 4. Stated outcome/metric → 5. HP.com (T0) before third-party (T2). Yes, industry first, followed by APJ/APAC region … Please infer the region from the case-study page/URL where possible … Yes, the same use case should always be the first priority. Region should not override the use-case match."
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes: use case → industry → APJ/APAC → stated outcome → T0 before T2; region inferred from the case-study page/URL; region never overrides use case. Engineering follow-up: our 14:30 email said region "cannot be inferred from the URLs", but seven pages carry an APJ locale (au-en, nz-en, sg-en, my-en, ph-en, in-en) and Mazenod College WA names its state, so step 3 should be applied from those.
- **Implementation impact:** Order of case studies when several match; APJ step currently not applied in the matcher.

### D50 · Product-line mapping for case studies: keyword table now, Rulebook offering ids after

- **Feature / topic:** Proof matching
- **Original question:** Round 3 F13 (item 50). Default: yes.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Resolved: already resolved this question above" — i.e. by F1c: no fixed mapping; match case studies to the account use case independently.
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned: no Rulebook-id mapping later either; use-case matching only.
- **Implementation impact:** Case-study matcher keys on use case, not product line.

### D29a · Integration route detected on its own shown as a context line?

- **Feature / topic:** Recommendations
- **Original question:** Round 3 F1a (item 29a). Default: shown as a context line "Intune detected; possible WXP integration route, no need evidenced", never inside the recommendation.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "resolved: 'Intune detected; possible WXP integration route' (do not mention no evidence)".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes, with a wording change: drop the phrase "no need evidenced".
- **Implementation impact:** Context line wording on Tech Map / recommendations.

### D29b · Conditions the data cannot evaluate treated as unmet (offering reaches "may be relevant" but never "relevant")

- **Feature / topic:** Recommendations
- **Original question:** Round 3 F1b (item 29b). Default: yes.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "-> yes"
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Seat counts, WXP tier, print volumes cap an offering at "may be relevant".

### D29c · Use-case vocabulary table (Rulebook opportunity type → case-study solution area/tags)

- **Feature / topic:** Case studies
- **Original question:** Round 3 F1c (item 29c). Default: our table applies until changed.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "yes pls don't try to match case studies and rulebook, I mentioned it so many times: We do not want a fixed Rulebook-to-case-study mapping table. Both should be checked independently against the account evidence/use case." + the four-case rule (both / Rulebook only / case study as proof only / neither).
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes — default overturned: NO mapping table; independent matching of each against the account evidence.
- **Implementation impact:** Case-study matcher and Rulebook router are decoupled.

### D51 · A realistic delivery date starting from the day data and GCP access are in hand

- **Feature / topic:** Process
- **Original question:** 24 Sep email §7.4; round 3 I1.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "Resolved: I already mentioned yesterday, pls write in whatsapp group about dates and timelines; sahaj is the one deciding that".
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Process answer: dates go through the WhatsApp group; Sahaj decides. No date given.
- **Implementation impact:** Planning.

### D53 · Remaining deliveries as one consolidated drop with a contents list

- **Feature / topic:** Process
- **Original question:** 24 Sep email §3; round 3 I2.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "-> noted"
- **Date answered:** 2026-09-25
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Noted, not committed.
- **Implementation impact:** Planning.

### D52 · JEV (decision model) inside this delivery?

- **Feature / topic:** Scope
- **Original question:** 24 Sep email §5.4.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "RESOLVED : DROP IT for now"
- **Date answered:** 2026-09-24
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes.
- **Implementation impact:** Out of this delivery.

### E25-4 · Filings for ANZ Holdings NZ, CIMB Group Holdings and CIMB Niaga (absent from filings 1.csv and from the 31-account no-filings list)

- **Feature / topic:** Filings: Executive Dashboard financials/priorities
- **Original question:** FILINGS_PLAN_2026-09-25 §8.2; 25 Sep 14:30 UTC email §5.4.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 26 Sep 03:26 UTC: six document URLs - ANZ Bank NZ disclosure statements Mar26, Sep25, Mar25; CIMB cimb-iar2025.pdf and cimb-fr-2025.pdf; CIMB Niaga AR-2025-ID.pdf.
- **Date answered:** 2026-09-26
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. Rows added as Filings/filings_client_supplement_2026-09-26.csv (row_id S26-1..6) in filings 1.csv's columns; periods read from each cover page (ANZ NZ: six months to 31 Mar 2026, year to 30 Sep 2025, six months to 31 Mar 2025). Five PDFs downloaded into the accounts' compliance_filings/. CIMB's integrated report is byte-identical (sha256) to the crawler's unassigned "CIMB Group" 2025-FY row. The CIMB Niaga URL sits behind an AWS WAF browser challenge; Yogesh downloaded it in a browser on 26 Sep (984 pages) and fetch_filings.py placed it from Filings/pdfs/_manual/.
- **Implementation impact:** ANZ Holdings NZ, CIMB Group Holdings and CIMB Niaga now have filings; the split counts 511 index rows.

### E25-5 · Bank Mandiri vs Bank Central Asia: two filings rows named Bank Mandiri carry BCA's territory

- **Feature / topic:** Filings
- **Original question:** FILINGS_PLAN_2026-09-25 §8.3; 25 Sep 14:30 UTC email §5.5.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** 26 Sep 03:26 UTC: "Resolved: When you look at the urls , those redirect to Bank Mandiri , hence consider Bank Mandiri".
- **Date answered:** 2026-09-26
- **Status:** **RESOLVED**
- **Does the answer fully resolve it?** Yes. FILINGS_CLIENT_RULINGS in split_account_data.py files both rows under PT_BANK_MANDIRI_PERSERO (matched_by "client_ruling"). bankmandiri.co.id does not answer scripted downloads, so Yogesh downloaded both in a browser on 26 Sep; their sha256 matches filings 1.csv, and fetch_filings.py placed them from Filings/pdfs/_manual/.
- **Implementation impact:** Bank Mandiri gets its 2025-FY and 2026-1H statements; BCA is unchanged.

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
