# Open and unresolved questions (18)

> **26 Sep 03:26 UTC:** Dhruvi answered the six items of our 25 Sep 14:30 UTC email §5 inline: contact file delivered (D8, C49), ANZ Holdings NZ / CIMB / CIMB Niaga filing URLs (E25-4), Bank Mandiri rows belong to Mandiri (E25-5), risk logic approved (D37), GCP project ID to be explained (D42), hiring flexibility (D22). F12 was answered 25 Sep 09:36 UTC (D48) and F11 recorded as settled (D47).
> **25 Sep 05:50 UTC:** the client answered all 25 round-3 open items in the annotated `clarifying_opens_3_OPEN_v2_provided.docx` (C44). The CLARIFICATIONS (7) and UNRESOLVED_v2 (2) answers arrived 25 Sep 12:02 UTC as attachments that are not yet on this machine, so they are not ingested here.
> Status values: RESOLVED = client answer settles it. PARTIALLY RESOLVED = answered, but a delivery, confirmation or sub-question is still outstanding (each has a file in `06_Unresolved_and_Open/`). OPEN = no answer. UNRESOLVED = answered, but the answer does not settle the point.
> IDs: D1–D43 = the 43 items of 220-Open-Decisions-List.md as numbered in clarifying opens_2.docx; D44–D53 = items added 24 Sep after the list went out; E18-x / E23-x = email Q&A of 18 and 23 Sep; QA16-x = the 16 Sep QA discussion points.

## Summary

| Id | Question | Feature | Status | Answered | Fully resolved? |
|---|---|---|---|---|---|
| D25 | Vendor-flagged doubtful rows (9) | Hiring and technographic signals | OPEN | 2026-09-24 | No. |
| D35 | Confidence tiers T0-T3 | Every signal; case-study file | OPEN | 2026-09-24 | No. |
| D42 | GCP access, project id, region | Environment | OPEN | 2026-09-26 | No. The client asks what we mean by project ID. She says the region was "already solved in… |
| E23-3 | "Contextual — no direct HP line" relationship tag | Technographic Map | OPEN | 2026-09-23 | No (by omission). |
| QA16-1 | Objection Playbook wording "Could be raised by" vs QA check "Likely raised by" (OP-03/OP-07) | Objection Playbook | OPEN | 2026-09-16 | No. |
| QA16-2 | "Counter Question" box reported missing (OP-06) — rendered in capitals | Objection Playbook | OPEN | 2026-09-16 | No. |
| QA16-3 | Opportunity Map HP-modeled / unsourced labels (OM-10/OM-13) — feature never emits unsourced numbers | Opportunity Map | OPEN | 2026-09-16 | No. |
| QA16-4 | Content Messaging unsourced proof points labelled "HP analysis" (CM-15) — we delete instead | Content Messaging | OPEN | 2026-09-16 | No. |
| QA16-5 | Tech Landscape confidence percentage (TM-11) vs Confirmed/Likely/Unknown words | Tech Landscape | OPEN | 2026-09-16 | No. |
| QA16-6 | Stakeholder avatar: initials vs photo (SM-10) | Stakeholder Map | OPEN | 2026-09-16 | No. |
| QA16-7 | LinkedIn 999 / Apollo URN / Google redirect links reported broken | Stakeholder Map, Live Signals | OPEN | 2026-09-16 | No. |
| QA16-8 | Active-employee label (SM-07/SM-26) — no employment-status column exists | Stakeholder Map | OPEN | 2026-09-16 | No. |
| QA16-9 | Strategy Chat source links / uncertainty state stay open until Step 8 RAG | Strategy Chat | OPEN | 2026-09-16 | No. |
| QA16-10 | Cost/scheduling of regenerating cached content after prompt changes | All | OPEN | 2026-09-16 | No. |
| QA16-11 | ~200 technologies that map to no HP category: separate view or count only? | Tech Landscape | OPEN | 2026-09-16 | No. |
| QA16-12 | Repeated "Step 4" data suggestions (xlsx, PDFs, car-market data) are new features, not fixes | All | OPEN | 2026-09-16 | No. |
| RULES | Client feedback on HP-Account-Intelligence-Rules.docx | All rules | OPEN | 2026-09-10 | No. |
| TESTS22 | Client UI test observations of 22 Sep (tests on current HP 220.docx) | UI | OPEN | 2026-09-22 | No. |

## Detail

### D25 · Vendor-flagged doubtful rows (9)

- **Feature / topic:** Hiring and technographic signals
- **Original question:** Item 25 and round 3 E4: 4 job postings attributed to the wrong employer, 1 MISO misreading, 4 duplicate company profiles. Drop them?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "clarifications needed"
- **Date answered:** 2026-09-24
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** 9 rows.
- **Unresolved-issue file:** `06_Unresolved_and_Open/13_vendor_flagged_rows.md`

### D35 · Confidence tiers T0-T3

- **Feature / topic:** Every signal; case-study file
- **Original question:** Item 35 and round 3 F5. What does each tier mean; is the case-study T0/T2 the same scale?
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "clarification needed, which feature?"
- **Date answered:** 2026-09-24
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** confidence_tier field required by v4 on every signal; build maps to High/Medium/Low.
- **Unresolved-issue file:** `06_Unresolved_and_Open/17_confidence_tiers_T0_T3.md`

### D42 · GCP access, project id, region

- **Feature / topic:** Environment
- **Original question:** 15 Sep action item; 24 Sep email §4; item 42; round 3 H1; access request doc sent 23 Sep via WhatsApp.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** "-> open"; "RESOLVED: Already followed up with sahaj" (on the follow-up action only); round 3 H1 (25 Sep): "Open: escalated to sahaj". 26 Sep 03:26 UTC: "can you please elaborate on project ID and region? I think region part is already solved in one of the opens which I shared yesterday."
- **Date answered:** 2026-09-26
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No. The client asks what we mean by project ID. She says the region was "already solved in one of the opens", but no readable document answers the GCP region (OPEN_v2 H1: "Open: escalated to sahaj"); she may mean the F12 APJ/APAC case-study region answered on 25 Sep. Unread candidate: the 25 Sep 12:02 UTC attachments.
- **Implementation impact:** The current environment cannot hold 220 accounts; a few hours of redeploy/load once granted.
- **Unresolved-issue file:** `06_Unresolved_and_Open/22_gcp_access.md`

### E23-3 · "Contextual — no direct HP line" relationship tag

- **Feature / topic:** Technographic Map
- **Original question:** 23 Sep question 3 (with the risk labels).
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Only the risk-label half was answered.
- **Date answered:** 2026-09-23
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No (by omission).
- **Implementation impact:** Rows with no HP category.
- **Unresolved-issue file:** `06_Unresolved_and_Open/18_tech_map_risk_labels.md`

### QA16-1 · Objection Playbook wording "Could be raised by" vs QA check "Likely raised by" (OP-03/OP-07)

- **Feature / topic:** Objection Playbook
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Objection Playbook
- **Unresolved-issue file:** `06_Unresolved_and_Open/24_qa_discussion_points_unanswered.md`

### QA16-2 · "Counter Question" box reported missing (OP-06) — rendered in capitals

- **Feature / topic:** Objection Playbook
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Objection Playbook

### QA16-3 · Opportunity Map HP-modeled / unsourced labels (OM-10/OM-13) — feature never emits unsourced numbers

- **Feature / topic:** Opportunity Map
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Opportunity Map

### QA16-4 · Content Messaging unsourced proof points labelled "HP analysis" (CM-15) — we delete instead

- **Feature / topic:** Content Messaging
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Content Messaging

### QA16-5 · Tech Landscape confidence percentage (TM-11) vs Confirmed/Likely/Unknown words

- **Feature / topic:** Tech Landscape
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Tech Landscape

### QA16-6 · Stakeholder avatar: initials vs photo (SM-10)

- **Feature / topic:** Stakeholder Map
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Stakeholder Map

### QA16-7 · LinkedIn 999 / Apollo URN / Google redirect links reported broken

- **Feature / topic:** Stakeholder Map, Live Signals
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Stakeholder Map, Live Signals

### QA16-8 · Active-employee label (SM-07/SM-26) — no employment-status column exists

- **Feature / topic:** Stakeholder Map
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Stakeholder Map

### QA16-9 · Strategy Chat source links / uncertainty state stay open until Step 8 RAG

- **Feature / topic:** Strategy Chat
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Strategy Chat

### QA16-10 · Cost/scheduling of regenerating cached content after prompt changes

- **Feature / topic:** All
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** All

### QA16-11 · ~200 technologies that map to no HP category: separate view or count only?

- **Feature / topic:** Tech Landscape
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Tech Landscape

### QA16-12 · Repeated "Step 4" data suggestions (xlsx, PDFs, car-market data) are new features, not fixes

- **Feature / topic:** All
- **Original question:** QA-Discussion-Points_2026-09-16 (sent 16 Sep 19:14 UTC as PDF), asking for a classification/decision per item.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** No written answer on record. TM-11 is overtaken by the client's 18 Sep confidence logic (a percentage now has a client basis); the Opportunity Map tags question was overtaken on 23 Sep.
- **Date answered:** 2026-09-16
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** All

### RULES · Client feedback on HP-Account-Intelligence-Rules.docx

- **Feature / topic:** All rules
- **Original question:** Sahaj 10 Sep asked for the rules; sent 10 Sep 11:16 UTC.
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Dhruvi 10 Sep: "We'll review the rules, guardrails and logic at our end and share our feedback." No feedback received.
- **Date answered:** 2026-09-10
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Every rule in that doc is unapproved; several are now contradicted by client logic.
- **Unresolved-issue file:** `06_Unresolved_and_Open/25_rules_doc_feedback_pending.md`

### TESTS22 · Client UI test observations of 22 Sep (tests on current HP 220.docx)

- **Feature / topic:** UI
- **Original question:** Dhruvi 22 Sep: "I tested the current HP 220 UI and have highlighted a few observations and questions".
- **Original source:** see `00_INDEX/EMAIL_TIMELINE.md`; documents in `05_Questions_and_Clarifications/Source_Documents/`
- **Client answer:** Yogesh 22 Sep: "Ok, I'll take a look." No written response on record; the document is not on this machine.
- **Date answered:** 2026-09-22
- **Status:** **OPEN**
- **Does the answer fully resolve it?** No.
- **Implementation impact:** Unknown until the file is retrieved.
- **Unresolved-issue file:** `06_Unresolved_and_Open/26_client_ui_test_observations_22sep.md`
