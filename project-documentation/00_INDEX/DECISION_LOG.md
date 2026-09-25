# Decision Log — HP 220-Account Intelligence

Every decision that changes what the product does, with its source. Built 25 Sep 2026 from the Gmail threads, the client's clarifying-opens answer documents and the client logic documents. **Nothing here is inferred**: if a decision is not supported by a quoted source it is not in this log; if a client answer is ambiguous it is recorded as PARTIALLY RESOLVED or OPEN and cross-referenced to `06_Unresolved_and_Open/`.

Classification used on every entry:

| Label | Meaning |
|---|---|
| **CLIENT DECISION** | BridgeAI stated it in writing (email or answer document). Binding until they change it. |
| **CLIENT DATA / CLIENT REFERENCE** | A fact about the data or material the client supplied. |
| **INTERNAL IMPLEMENTATION DECISION** | The delivery team decided it; the client has seen it (sent) but not explicitly approved it. |
| **INTERNAL ASSUMPTION** | The delivery team is working on it; the client has not seen it or has not answered. |
| **OPEN QUESTION** | Asked, not answered, or answered in a way that does not settle it. |

Source abbreviations: **MAIN** = Gmail thread 1a082bca2581fea0; **opens_1** = clarifying opens_1.docx (24 Sep, C35); **opens_2** = clarifying opens_2.docx (24 Sep, C36; item numbers are the 43 items of 220-Open-Decisions-List.md); **DL** = 220-Open-Decisions-List.md; **R3** = round-3 docs sent 25 Sep (I14). Provenance ids (C01, I10 …) refer to `PROVENANCE_REGISTER.md`.

---

## 1. Scope and process

### DEC-001 · Eleven features are in scope — CLIENT DECISION
- **Question:** Which of the ~20 features in HP_ABX_v3_final are to be built?
- **Answer:** "please focus on the following 11 in-scope features: Executive Dashboard, Recent News Signals, Stakeholder Map, Solution Narrative / Opportunity Map, Tech Landscape, Objection Playbook, Content Studio, Strategy Chat, Message Evaluator, Content Messaging, Intent & Demand Signals."
- **Decision date:** 22 Aug 2026 · **Who decided:** Dhruvi Patel (BridgeAI) · **Source:** MAIN, 22 Aug 14:53 IST (quoted in the 9 Sep forward); C01
- **Current status:** CURRENT · **Impact:** whole product; the nine other ABX features (Narrative Engine, Competitive Displacement, Peer Benchmarking, Source Trail Explorer, Outreach Sequences, ABM Toolkit, Sales Simulator, Deal Qualification, KPI Framework) are out of scope.

### DEC-002 · The 220 accounts are Master List column B — CLIENT DECISION
- **Question:** Which accounts?
- **Answer:** APAC_Account_Parent_Child_Mapping.xlsx, "Sheet: Master List, Column B: Sales Territory Name. These are the 220 accounts".
- **Decision date:** 22 Aug 2026 · **Who:** Dhruvi · **Source:** MAIN 22 Aug; C03
- **Status:** CURRENT; the authoritative domain per account was sent on 25 Sep as PredictLeads_219_Account_Domain_Audit.xlsx (DEC-052, C43) — not yet downloaded. · **Impact:** every join, every per-account run, the 220-account split.

### DEC-003 · Reference implementations — CLIENT REFERENCE
- **Answer:** HP Sea Limited POC (hp-sea-abm.vercel.app + codebase zip) is the HP-specific reference; Palo Alto Caterpillar POC (paloalto-abm.vercel.app) is the reference for Executive Dashboard, Stakeholder Map, Solution Narrative and Tech Landscape. "These steps are not intended to restrict the technical approach."
- **Date:** 22 Aug 2026 · **Who:** Dhruvi · **Source:** MAIN 22 Aug; C05
- **Status:** CURRENT. The client repeatedly uses "as seen in SEA Limited" as the tie-breaker (23 Sep: Opportunity Map tags, Tech Map risk labels, Live Signal tiers). · **Impact:** UI parity decisions.

### DEC-004 · Additional modules: HP deck RAG rules, Reporting & Usage Analytics, human-in-the-loop — CLIENT DECISION
- **Answer:** (1) "when an account signal or use case matches one of the defined rules, the relevant HP deck can be used as the preferred source for HP product information. If no rule matches, the platform should … continue with the normal approved external research or retrieval flow." (2) "add a Reporting & Usage Analytics module … track usage across users, features, accounts, queries, sessions and time … capture the required usage events from the beginning". (3) "human in the loop / co-creation, rather than the system directly producing one final output" for brief-driven features such as Content Studio.
- **Date:** 24 Aug 2026 · **Who:** Dhruvi · **Source:** MAIN 24 Aug; C02 (points 1–2 are in the docx; point 3 is **only in the email body**)
- **Status:** CURRENT. Reporting & Usage Analytics is not one of the 11 features and its build status is not recorded in any later document (Sahaj re-raised "an analytics component" on 15 Sep). · **Impact:** Content Studio flow; a 12th module; logging from day one.

### DEC-005 · All communication and data in one thread; NDA — CLIENT DECISION
- **Answer:** "please use this email thread for future conversations"; "Please use this email thread to share the data for 220 accounts project"; "The material, code, data and POC references shared here are within the scope of our signed NDA."
- **Date:** 22 and 31 Aug 2026 · **Who:** Dhruvi · **Source:** MAIN
- **Status:** CURRENT (in practice the 3 Sep drop went to SharePoint and the 18 Sep drop to Drive). · **Impact:** provenance; where to look for files.

### DEC-006 · Rules document is under client review — OPEN QUESTION (process)
- **Question:** Sahaj: "Can you please drop all the rules, guardrails and logic being used across modules."
- **Answer:** Sent 10 Sep (HP-Account-Intelligence-Rules.docx). Dhruvi: "We'll review the rules, guardrails and logic at our end and share our feedback with the team."
- **Date:** 10 Sep 2026 · **Source:** thread 1a08a8571d30e41e; I01
- **Status:** **OPEN — no feedback received as of 25 Sep.** The document is therefore INTERNAL, not client-approved, and several of its rules are now contradicted by later client logic (see `CONFLICT_REGISTER.md` items X-01 to X-06). · **Impact:** Live Signals tiers, stakeholder scoring, opportunity ordering, de-dup heuristic, proof-point fallback.

### DEC-007 · 15 Sep action items — CLIENT DECISION (process)
- **Answer:** Sahaj → add Yogesh to GCP; Dhruvi → share recommendation logic + updated product rules, review remaining features, review Konika's sample output; Manil → project plan; Yogesh → compile all remaining scoring questions in one go, review sample output; Pritesh → crawl stock-exchange filings for the last 12 months (latest four quarters) from IR sites and national exchanges, crawl HP case studies; Konika → 220-account data + contacts for ~30 buying-committee roles, then 5–8 more roles after Services & Solutions data. Sahaj: analytics component to be added.
- **Date:** 15 Sep 2026 · **Who:** Dhruvi (minutes) · **Source:** thread 1a0911ab27454237, 15 Sep 12:11 UTC
- **Status:** GCP access and contacts still OPEN on 25 Sep. · **Impact:** filings window (12 months), contact role coverage, environment.

### DEC-008 · Inspection window for late data drops — CLIENT DECISION
- **Question (DL 43):** "agree that a late-night drop is checked the next working morning, not run overnight."
- **Answer:** "resolved: yes"
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_2 item 43
- **Status:** CURRENT · **Impact:** delivery planning.

### DEC-009 · Option A vs Option B (who owns the approach) — OPEN QUESTION
- **Question:** Delivery team proposed Option A (we document every output-changing decision and BridgeAI approves the list) or Option B (BridgeAI supplies a fully unambiguous approach).
- **Answer:** Dhruvi: "->OPEN … Just to confirm my understanding: based on Option A, you have already documented the open items and implementation decisions … Is that correct?"
- **Date:** 24 Sep 2026 · **Source:** MAIN 24 Sep 04:52 UTC (Yogesh) and 09:30 UTC (Dhruvi)
- **Status:** OPEN. The 220-Open-Decisions-List + opens_2 exchange is *de facto* Option A. · **Impact:** governance of every INTERNAL ASSUMPTION in this log.

### DEC-010 · JEV and the extra "Recommendation for HP" Tech Map card are dropped for now — CLIENT DECISION
- **Answer:** "5.3 … RESOLVED : DROP IT for now"; "5.4 JEV … RESOLVED : DROP IT for now".
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 24 Sep 09:30 UTC annotations
- **Status:** CURRENT · **Impact:** Tech Landscape (no per-section recommendation card beyond the two categories it maps today); no JEV integration in this delivery.

---

## 2. Data sourcing and identity

### DEC-011 · Sourcing hierarchy: Source A default, Source B for hiring, Google News RSS for news — CLIENT DECISION (sent for review)
- **Answer:** "Source A → Primary source for most company, technology, and general intent data. Source B → Primarily for hiring/job-related signals … Google News RSS → Primary source for news and event-related signals, with Source B's news data as an additional layer." Asked for review: "let us know if anything needs to be adjusted".
- **Date:** 31 Aug 2026 · **Who:** Konika Thakur · **Source:** mails (1).txt paste; C04
- **Status:** PARTIALLY SUPERSEDED — Exa was added as a second news feed (DEC-020) and the vendors are now named (Source A = Explorium, Source B = PredictLeads, per the 24 Sep opens_1 answer 4). No "aligned" reply is on record. · **Impact:** dataset registry; Live Signals sources.

### DEC-012 · Category-specific HP intent score is the primary intent signal — CLIENT DECISION
- **Answer:** "The proposed approach is to use the category-specific intent score as the primary signal. For example, if a company has a high Workstation Intent, we can then look at the relevant supporting intent topics available in the source A file—such as AI/ML, AI chips, data analytics, vector databases".
- **Date:** 3 Sep 2026 · **Who:** Konika · **Source:** MAIN 3 Sep (quoted 8 Sep); reaffirmed opens_1 answer 10 ("please look at the separate intent data … hp_intent_results")
- **Status:** CURRENT. Note HP_ABX_v3_final names Bombora composite scores as the intent source; the four-step flow in code (category score primary, Bombora supporting, technology confirms) is an INTERNAL IMPLEMENTATION DECISION consistent with this answer. · **Impact:** Intent & Demand Signals, Urgency driver 4.

### DEC-013 · Vendors are fetched by Company Name + Country, not by domain; PredictLeads domains are canonical; four overrides — CLIENT DECISION
- **Answer:** "For Explorium, we do not fetch the company using the domain. We fetch using Company Name + Country and explorium's business id … Similarly, for PredictLeads … For the news data, including Exa.ai, we use the domain obtained from PredictLeads. … For the final account-level mapping, please use the canonical domains listed in predictleads data and for 4 companies … Posco Group → posco.com, Pilipinas Shell → shell.com.ph, Shiseido → corp.shiseido.com, Stanley Electric → stanley.co.jp. Also where domain matching is ambiguous, use Company Name + Country as the fallback logic."
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1 answer 4; opens_2 item 5 "ALREADY RESOLVED"
- **Status:** SUPERSEDED on 25 Sep by DEC-052: the domain-audit sheet now gives the canonical domain per account (the four overrides should be checked against it). The split's alias rewrites (CONFLICT I-03) are moot once the sheet is used. · **Impact:** every domain join.

### DEC-014 · Use Domain + Company Name (+ Country) for matching, never vendor record ids — CLIENT DECISION
- **Answer:** "Why are we using IDs? We should use Domain + Company name for mapping." (answer 8); "Why are we using ids, already mentioned that pls use domain, company name and country" (opens_2 item 24); "Resolved: pls use domain + company name + country" (item 18).
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1; opens_2 items 18, 24
- **Status:** CURRENT · **Impact:** de-duplication of PredictLeads rows (the internal "de-dup on id, first row kept" default was answered with this instruction, so duplicate-id handling by id is NOT approved); news row attribution; Exa key.

### DEC-015 · Shared domains (jabil.com, mufg.jp): keep the entities separate; disambiguate with Company Name + Country; client to add the columns — CLIENT DECISION, delivery OPEN
- **Answer:** "Should the two Jabil entities and the two MUFG entities be treated as one account each? -no"; "Please take Company Name + Country into consideration along with the domain … Open: We will provide additional columns Company Name + Country in the mentioned sheets."
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1 answer 2; opens_2 item 3
- **Status:** rule CURRENT, **data OPEN** (R3 A3: columns exist but populated on 384 of 14,965 job rows). Interim INTERNAL ASSUMPTION in the split: Jabil Malaysia and MUFG Japan keep the domain-keyed rows; Jabil Singapore and the Bangkok branch stay near-empty. · **Impact:** hiring, tech detections, news, connections for four accounts. See `06_Unresolved_and_Open/03_shared_domains_name_country_columns.md`.

### DEC-016 · Blank domains: Westpac = westpac.com.au; Public Bank = pbebank.com — CLIENT DECISION, Public Bank PARTIALLY RESOLVED
- **Answer:** "pls look at below two domains: pbebank.com, westpac.com.au"; and on pbebank.com: "Public Bank Lao Limited is a wholly-owned subsidiary of Public Bank Berhad, which is why the same domain is associated with both entities … We will try and give you exact name 'public bank bhd' data".
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1 answers 3 and 5; opens_2 items 4, 6
- **Status:** RESOLVED 25 Sep by the audit sheet (DEC-055): Public Bank = pbebank.com and the "Public Bank Lao Limited" PredictLeads row is accepted as the account ("domain is matching irrespective of their names"). Our A4 concern is on record; the split's publicbankgroup.com must change. · **Impact:** one account's PredictLeads data.

### DEC-017 · Entity scope: APAC entity as named; firmographics as delivered — PARTIALLY RESOLVED
- **Question (DL 2):** "which entity does each account represent … Default: APAC entity as named in the account list; firmographics shown as delivered."
- **Answer:** "->RESOLVED" (no further words).
- **Date:** 24 Sep 2026 · **Source:** opens_2 item 2
- **Status:** PARTIALLY RESOLVED — the client wrote RESOLVED against a question that offered a default, so the default is taken as accepted; R3 (CLARIFICATIONS_v2 A2) asks for explicit confirmation. · **Impact:** firmographics, hierarchy, Executive Dashboard header.

### DEC-018 · Hierarchy: use the Explorium Company Hierarchy sheet; blank parent = ignore; no "no hierarchy data" text — CLIENT DECISION
- **Answer:** "If a Parent Name is provided there, we should use that parent relationship. If the Parent Name is blank, the parent relationship can be ignored for now" (23 Sep). "Resolved: nothing to mention, do not write 'no hierarchy data'" (opens_2 item 7).
- **Date:** 23–24 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 23 Sep 12:33 UTC; opens_2 item 7
- **Status:** CURRENT. Note: this is the only client rule on empty states, and it says *say nothing*; the general empty-state rule is still OPEN (DEC-046). · **Impact:** Executive Dashboard, firmographics; PT Astra shows itself as its own parent.

### DEC-019 · Coverage gaps are genuine no-data cases; where each dataset comes from — CLIENT DECISION, one delivery OPEN
- **Answer:** "no data cases. … Company Hierarchy: This is missing from Explorium only. Intent Data: … look at the separate intent data (hp_intent_results excel file). Columns: Topics Researched, Keywords Matched, Related Technologies are available there as well. Job Openings: This data is not available in PredictLeads itself for some accounts, we will aggregate it from other tools and give you in same format. Technographics: Please look at the WebStack and Tech_Breakdown sheets in Explorium … fallback data for technology … Related Technologies column [of hp_intent_results]."
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1 answer 10; opens_2 items 22–23
- **Status:** rule CURRENT; **job openings for 45 accounts OPEN** (R3 E1). INTERNAL point pending confirmation: "Related Technologies" is *researched*, not *detected*, technology and is to be shown as such. · **Impact:** Intent & Demand, hiring widgets, Urgency driver 3, Technographic Map for the affected accounts.

### DEC-020 · Two news feeds, merged; disagreeing items skipped — CLIENT DECISION, "same event" definition OPEN
- **Answer:** "no it is not a replacement … merging both … Please merge both. For most companies, you are getting around 10-15 news articles, so it might be rare for the two sources to disagree on the same event. However, in the rare case that this happens, please skip that particular news item. Do not skip the company directly." Earlier: "For the news data, the Google News RSS and Exa files together cover all 220 APAC accounts" (18 Sep).
- **Date:** 18 and 24 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 18 Sep 05:51 UTC; opens_1 answer 6
- **Status:** SUPERSEDED on the disagreement rule by DEC-054a (25 Sep): keep the Exa row instead of skipping the item. Merge rule and "never skip the company" still stand. Same-event definition remains INTERNAL. · **Impact:** Live Signals feed content.

### DEC-021 · Undated news rows are skipped; epoch dates skipped; client to re-crawl dates — CLIENT DECISION, delivery OPEN
- **Answer:** "We will provide the date wherever possible by crawling the URLs. For any rows where the date will still not available, please skip that news row for now, do not skip whole company/account"; "skip these three news items as of now".
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** opens_1 answer 7; opens_2 item 17
- **Status:** rule CURRENT; **re-export OPEN** (R3 D2: 5,120 of 9,221 Exa rows undated; Exa is the only news source for ~119 accounts). · **Impact:** Live Signals volume, urgency AI/growth events.

### DEC-022 · Exa text: as delivered (UTF-8 issues not fixable at source); HTML stripped on ingest by us — CLIENT DECISION
- **Answer:** "This is the data which we get from tool itself"; "If you could help strip it on ingest, it would be appreciated".
- **Date:** 24 Sep 2026 · **Source:** opens_1 answer 9; opens_2 item 21
- **Status:** CURRENT · **Impact:** news cards for Thai accounts show corrupted characters as delivered.

### DEC-023 · News window 12 months; NO 20-signal cap — CLIENT DECISION
- **Answer:** "Resolved: we should not keep the cap, pls use 12 month window".
- **Date:** 24 Sep 2026 · **Source:** opens_2 item 19
- **Status:** CURRENT (overturned the internal default "keep both"). · **Impact:** Live Signals shows every scored signal in the window; input contract still documents the cap (stale).

### DEC-024 · Do not use the feeds' Low/High relevance_confidence columns — CLIENT DECISION
- **Answer:** "Already Resolved: mentioned in yesterday's meeting, pls do not use low/high confidence columns from those feeds".
- **Date:** 24 Sep 2026 (meeting 23 Sep) · **Source:** opens_2 item 20
- **Status:** CURRENT. Note the 16 Sep urgency email said "Google News relevance: retain as High/Medium/Low" as a *scale*; this later instruction says not to *use* the column for ranking. · **Impact:** Live Signals ranking.

### DEC-025 · Filings: filings 1.csv + PredictLeads sec_filings; document_url first, source_page_url fallback, never local_path; exclude records with neither; 12-month window; skip failing files not companies — CLIENT DECISION
- **Answer:** "Please use document_url where available and source_page_url as the fallback. Do not use local_path. Where both source URLs are blank, please exclude that record" (18 Sep). "RESOLVED: use filings 1.csv plus PredictLeads SEC Filings, merged on domain but where the domain is same … pls use company name and country … and yes pls consider 'the file shows 186 unique company names'" + list of 31 accounts with no public filings (opens_2 item 11). "wherever it is not downloaded, or links fail: we skip that particular file, not the whole company" (item 12). "resolved: last 12 months" (item 13). Stock Exchange data of 3 Sep: "already resolved: she shared with you different pdfs" (item 15).
- **Date:** 18, 23, 24 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 18 Sep 07:28 UTC, 23 Sep 12:33 UTC; opens_2 items 11–13, 15
- **Status:** rule CURRENT; **three data issues OPEN** (mis-mapped Fletcher/Fonterra/Astra rows; Agribank and VPBank absent from both file and exclusion list; Jabil Inc. 10-Q rows keyed SG+MY and Hyundai DART rows — R3 C1, C4, C5). · **Impact:** Executive Dashboard financials and priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals (per the 18 Sep mapping).

### DEC-026 · New PredictLeads sheets: use sec_filings and products; ignore the rest — CLIENT DECISION
- **Answer:** "please use the SEC Filings data … Please also use the Products sheet (mainly for recommendation purposes) for the following features: [screenshot]. You can ignore others" (23 Sep); "Resolved: yes" to removing the twelve unused keys from the upload contract (opens_2 item 28).
- **Date:** 23–24 Sep 2026 · **Source:** MAIN 23 Sep 12:33 UTC; opens_2 item 28
- **Status:** CURRENT. **Gap:** the feature list for the Products sheet exists only in a screenshot that is not on this machine (see MISSING_FILES.md). · **Impact:** upload contract; recommendations.

### DEC-027 · Vendor-flagged rows and the 490-correction log — PARTIALLY RESOLVED / INTERNAL
- **Question:** drop the 9 vendor-flagged PredictLeads rows? Is the delivered file post-correction?
- **Answer:** "clarifications needed" to both (opens_2 items 25–26).
- **Status:** item 26 cleared internally by inspection (332 corrected values present, none old) — INTERNAL FINDING, stated to the client in R3 E5; item 25 OPEN with default "drop the 9 rows" (R3 E4). · **Impact:** hiring and technographic signals for a handful of rows.

### DEC-028 · Job status: blank and closed postings within 12 months count — CLIENT DECISION; label wording OPEN
- **Answer:** "please include both blank and closed job statuses for eligible records within the latest 12 months" (16 Sep, for the Urgency Score).
- **Date:** 16 Sep 2026 · **Source:** MAIN 16 Sep 13:35 UTC; opens_2 item 27 "clarifications needed"
- **Status:** scoring rule CURRENT; **hiring-widget label ("postings seen" + open count) and whether blank means open or unknown OPEN** (R3 E6). · **Impact:** Urgency driver 3; exec_hiring_velocity and intent_hiring_demand labels.

### DEC-029 · Related HP intent, hierarchy and technographic fallbacks (see DEC-019); Astra PredictLeads data is the 219th/220th account — CLIENT DATA
- **Answer:** "Astra: already provided initially and part of this predictleads data related questions ALREADY RESOLVED IN CLARIFYING_OPENS_1 DOC" (opens_2 item 23).
- **Status:** PARTIALLY RESOLVED — R3 E2 asks whether the seed extract is the same format/version. INTERNAL ASSUMPTION in the split: Astra's PredictLeads *and prospect_contacts* datasets are filled from `hp-backend/seed_data/astra` (the client answer covers PredictLeads data only).

---

## 3. Scoring logic

### DEC-030 · Urgency Score = client document with 4 drivers; delivery formulas replaced — CLIENT DECISION
- **Question:** Delivery team proposed five driver formulas (Fleet Refresh 20 / AI-Workstation 25 / Hiring 15 / Expansion 15 / Intent 25) and asked for sign-off.
- **Answer:** "please use the latest shared logic document as the basis for implementation rather than the proposed formulas … The latest logic has 4 drivers, not 5: Workplace Technology & OS (20%), AI & Workstation (25%), Growth & Expansion (30%), and HP Solution Intent (25%). Hiring is now incorporated within Growth & Expansion. … The overall Urgency Score should only be calculated where at least 60% of the weighted driver coverage is available … We are no longer scoring 'Fleet Refresh' … Bombora: use directly as 0-100; Detection score: 0-1 → multiply by 100; News confidence: 0-1 → multiply by 100; Google News relevance: retain as High/Medium/Low … The thresholds in the latest document should be applied consistently across all 220 accounts; Astra is only the worked example."
- **Date:** 16 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 16 Sep 13:35 UTC; C09
- **Status:** CURRENT; implemented 17 Sep ("we have updated the formula"). Known internal inconsistencies inside the client document (Astra example 12.33 vs 12.60; 64.43 "rounded" to 61; band gaps at exactly 250 employees and 0–1% growth) are recorded in CONFLICT_REGISTER.md C-07/C-08 — not resolved. · **Impact:** exec_urgency_score.

### DEC-031 · Fleet Refresh excluded; Lifecycle/EOL file not used for urgency — CLIENT DECISION
- **Answer:** "Fleet Refresh should remain excluded for now. The Lifecycle/EOL file tells us when specific HP products will reach EOL, but we don't have data showing which HP device models each account currently uses."; file explanation: "HP Lifecycle June 2026 — Not used as of now".
- **Date:** 18 Sep 2026 · **Source:** MAIN 18 Sep 07:28 UTC; C26
- **Status:** CURRENT for urgency. **Conflict:** Recommendation Tuning Logic v4 §J asks to check the Lifecycle file before surfacing an offering (CONFLICT C-05); R3 F6 asks which columns to read. · **Impact:** urgency; recommendation lifecycle check.

### DEC-032 · Live Signals: client scoring logic (3 drivers, score /10); no S/A/B/C tiers, no minimum publish score — CLIENT DECISION
- **Answer:** "I don't see the S/A/B/C tiering defined in the HP SEA limited poc" (18 Sep); "Resolved: use live signal scoring logic as given as I can see in sea limited, there is a score instead of tiers" (opens_2 item 36).
- **Date:** 18 and 24 Sep 2026 · **Source:** MAIN 18 Sep 07:28 UTC; opens_2 item 36; C18
- **Status:** CURRENT; overturns the internal tiers and the ≥2.0 cut-off in HP-Account-Intelligence-Rules.docx. Combined with DEC-023 (no cap) every signal in the 12-month window is published with its score. · **Impact:** news_signals_feed, signal_scoring.py.

### DEC-033 · Tech Landscape confidence = the FINAL document (18 Sep) — CLIENT DECISION
- **Answer:** "Please use the latest document I'm sharing here for technological confidence score and disregard the version I shared yesterday night."
- **Date:** 18 Sep 2026 · **Source:** MAIN 18 Sep 04:08 UTC; C21
- **Status:** CURRENT (Driver 1 HP-relevant technology evidence + Driver 2 HP-category intent support; 70/30 per the Gap Analysis reading). · **Impact:** technographic_map card confidence (percent), tech_confidence.py.

### DEC-034 · Opportunity Map: drop the Verified Evidence / Timing Trigger / HP Fit tags; keep Priority Critical/High/Medium/Low — CLIENT DECISION
- **Answer:** "Since I am not seeing the Verified Evidence, Timing Trigger, and HP Fit check tags in the SEA Limited reference application, we can drop these for now. Please retain only the Priority tags -Critical, High, Medium, Low as seen in sea limited".
- **Date:** 23 Sep 2026 · **Source:** MAIN 23 Sep 12:33 UTC
- **Status:** CURRENT. Note HP_ABX_v3_final defines the three checks as the ordering rule; the client chose UI parity with SEA Limited over the ABX text. · **Impact:** opportunity_narrative_plays.

### DEC-035 · Technographic Map keeps Low/Medium/High Risk labels; the risk logic is ours and awaits client sign-off — CLIENT DECISION + INTERNAL IMPLEMENTATION DECISION
- **Answer:** "Please retain the Low Risk / Medium Risk / High Risk labels, as these are also present in the SEA Limited reference application. Could you please let me know what logic is currently being used to assign these risk tags?" Logic sent 23 Sep (screenshot) and in words in R3 F7: High = competing vendor confirmed in a category HP sells into; Medium = need supported, no vendor confirmed; Low = HP can work alongside; no label where HP has no line; HP's own absence row always Medium. Forwarded to Sahaj 24 Sep ("Could you please have a look … good to go from your end").
- **Date:** 23–25 Sep 2026 · **Source:** MAIN 23 Sep 12:33 UTC, 24 Sep 14:43 UTC; R3 OPEN_v2 F7
- **Status:** labels CURRENT; logic = INTERNAL IMPLEMENTATION DECISION, **approval OPEN**. · **Impact:** technographic_map.

### DEC-036 · "Contextual — no direct HP line" relationship tag — INTERNAL IMPLEMENTATION DECISION
- **Question (23 Sep):** the tag is not in HP_ABX_v3_final; should it remain?
- **Answer:** Dhruvi answered the risk-label half of the question only.
- **Status:** OPEN by omission; the tag stays as built. · **Impact:** technographic_map rows without an HP category.

---

## 4. Recommendations, Rulebook and case studies

### DEC-037 · The Rulebook is the consolidated source of HP product/service/solution facts — CLIENT DECISION
- **Answer:** "HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook is the consolidated rulebook. It includes the rules we have created based on the product information as well as the Services & Solutions materials provided by the client." Supporting files "Not used separately - included in Combined HP Rulebook". FINAL (23 Sep) adds the Print rules "highlighted in yellow".
- **Date:** 17 and 23 Sep 2026 · **Source:** MAIN 17 Sep 08:47 UTC, 23 Sep 05:53 UTC; C15, C26, C29
- **Status:** CURRENT, **but the FINAL file is not on this machine** — only the 17 Sep v1 is. · **Impact:** rulebook.py, every feature that names an HP offering.

### DEC-038 · Recommendation Tuning Logic FINAL v4 is the recommendation logic; the 15 Sep deck is not used — CLIENT DECISION
- **Answer:** "HP_Recommendation_Tuning_Logic_FINAL_v4 - Sharing the recommendation logic for this project" (23 Sep). File explanation: "HP 220 account recommendation logic(1) — Not used as of now. Some changes need to be made after discussing them with Sahaj."
- **Date:** 18 and 23 Sep 2026 · **Source:** MAIN 23 Sep 05:53 UTC; C26, C28
- **Status:** CURRENT. v4 defines evidence tiers (Opportunity = ≥2 logically related independent pipelines; Conversation Starter = 1 strong signal; Context Only), permitted language, thin-account path, data_as_of_date = ingestion date, output schema, word limits, banned outputs. · **Impact:** recommendations.py and the prose layer of Executive Dashboard, Live Signals, Intent & Demand, Stakeholder Map, Opportunity Map, Technographic Map, Content Messaging.

### DEC-039 · Rulebook and case studies strengthen recommendations; never force a match; general LLM recommendation allowed without one — CLIENT DECISION
- **Answer:** "the Rulebook and Case Studies can help strengthen recommendations with relevant HP Product, Service and Solution information, add relevant real HP customer examples … Where there is no clear relationship … we should not force a match. The platform can still provide a general LLM-generated recommendation based on the available account evidence" (18 Sep, with the Intune→WXP and Mitsubishi Electric→Aereco examples). Reaffirmed opens_2 item 33: "the absence of a matching 3D or Workstation rule in the Rulebook should not block an otherwise supported recommendation … Not every recommendation is expected to have a matching Rulebook entry or case study."
- **Date:** 18 and 24 Sep 2026 · **Source:** MAIN 18 Sep 13:32 UTC; opens_2 item 33
- **Status:** CURRENT. Overturns the internal default "3D intent is scored but produces no product recommendation until rules exist". · **Impact:** all recommendation text; 3D and Workstation routes are evidence-led.

### DEC-040 · Relevance threshold: use-case/opportunity fit, not exact-name matching; graded wording — CLIENT DECISION (restatement requested)
- **Answer:** "A Rulebook offering should be considered when the account evidence establishes HP-addressable use case/opportunity and the Rulebook shows that the HP offering supports that use case … Where the … fit [is] clear, well-supported … the offering can be stated as relevant. Where the fit is conditional or there is still uncertainty, position it as 'may be relevant' / 'explore fit' … A technology or integration-route match alone is not sufficient to recommend the offering. … Intune/ServiceNow detected alone -> possible WXP fit, but not enough to recommend WXP. Intune/ServiceNow + related endpoint/fleet-management evidence -> WXP may be relevant; explore the fit. Where the combined evidence clearly satisfies the applicable Rulebook conditions → WXP can be stated as relevant. … For case studies, 'relevant' means that the case study supports the same use case/opportunity already established … The case study supports the opportunity; it does not create the account need."
- **Date:** 24 Sep 2026 · **Who:** Dhruvi · **Source:** MAIN 24 Sep 09:30 UTC annotation of §5.1; opens_2 item 29 "Already resolved: Explained in the email"
- **Status:** CURRENT. **Watch:** R3 CLARIFICATIONS F1 says "We are currently using exact or known-alias matches only, and listing category-level matches as possible" — i.e. the build as described on 25 Sep does not yet implement this rule (CONFLICT I-06). Sub-questions 29a–c (integration route shown as a context line; unevaluable conditions treated as unmet; a use-case vocabulary table) are INTERNAL ASSUMPTIONS not yet answered. · **Impact:** every recommendation across all features.

### DEC-041 · Where the Rulebook and case studies appear: as mapped on 18 Sep, plus the Stakeholder Map — CLIENT DECISION
- **Answer:** "resolved: pls include stakeholder map as well" (opens_2 item 30); "ALREADY RESOLVED … my 18 September email … Excel file with the feature-level mapping" (24 Sep annotation of the 21 Sep question).
- **Date:** 24 Sep 2026 · **Source:** opens_2 item 30; C26
- **Status:** AMENDED 25 Sep (DEC-054k): Stakeholder Map is **not** to carry case-study proof for now; signal features carry it only in the named slots; four-feature method confirmed as built (DEC-054j); proof on service plays yes (DEC-054l); no mapping table (DEC-054i). Still open: evidence-tier gate (F11) and APJ preference (F12). · **Impact:** proof-point placement.

### DEC-042 · 89 cleaned case studies are the proof corpus; corrupted figures never shown — CLIENT DECISION
- **Answer:** "resolved: yes" (opens_2 item 31). Client dataset: hp_case_studies_final.csv (17 Sep; 384 rows).
- **Date:** 24 Sep 2026 · **Source:** opens_2 item 31; C20
- **Status:** CURRENT. The reduction 384 → 89 is an INTERNAL cleaning decision that the client accepted. · **Impact:** proof library.

### DEC-043 · One primary recommendation with weaker routes as secondary hypotheses — INTERNAL IMPLEMENTATION DECISION (client asked "which five routes?")
- **Answer:** opens_2 item 34: "clarification needed, which five routes?" R3 F4 answers (3D Printing, Workstations, PC/Devices, Print, Poly, from slide 5 of the 15 Sep deck) and states the build: "the strongest route as the recommendation and keep the weaker ones as secondary hypotheses, per your slide 3."
- **Status:** PARTIALLY RESOLVED — consistent with Rulebook C 06 ("Give one main recommendation") but not yet confirmed. · **Impact:** Opportunity Map ordering.

### DEC-044 · Confidence tiers T0–T3 — OPEN QUESTION
- **Answer:** "clarification needed, which feature?" (opens_2 item 35). R3 F5 restates: v4 requires a `confidence_tier` on every signal; the case-study file carries T0/T2; the build maps to High/Medium/Low.
- **Status:** OPEN; INTERNAL ASSUMPTION (mapping to High/Medium/Low) applies. · **Impact:** every signal's confidence field.

### DEC-045 · Services rules with missing inputs: ignore "pending HP input" items; use the employee range instead of a seat count; no seller-entered seats — CLIENT DECISION; lifecycle columns OPEN
- **Answer:** "pls ignore that pending HP input, and use whose data we fully have, no as of now we might not ask seller to enter seats, so hold employee range. lifecycle date, which columns to look into? -> clarifications needed"
- **Date:** 24 Sep 2026 · **Source:** opens_2 item 38
- **Status:** PARTIALLY RESOLVED — the employee-range thresholds used as the seat proxy (501 / 1,001 / 5,001) are an INTERNAL ASSUMPTION still awaiting a yes (R3 F6); which Lifecycle column to read (PE vs EM, stacked dates) is OPEN. · **Impact:** Care Pack / WXP tier / Poly rules in rulebook.py; lifecycle check.

### DEC-052 · The PredictLeads domain-audit file is the canonical domain list; Column B is the display name — CLIENT DECISION (file not yet on this machine)
- **Question:** D1 canonical account list with one domain each; how to treat vendor name variations for one domain.
- **Answer:** "The file contains the correct domain to be used for each account. Therefore, please use the domain as the primary reference for data mapping, along with company name keeping caveat mentioned in Column H where applicable. For the company/account name displayed on the dashboard, please use the account name provided in Column B of this file, rather than the company name returned by the individual data sources." Clarification: "Please refer only to the sheet: 219_Account_Domain_Audit and ignore the other sheets … Column H: 'OK' means the company names are similar … 'Consider both names same' means different tools have returned very different company names for the same domain, but they should be treated as the same account … if you see: domain is matching irrespective of their names."
- **Decision date:** 25 Sep 2026 · **Who:** Dhruvi Patel · **Source:** MAIN 25 Sep 05:50 and 06:24 UTC; C43, C45
- **Current status:** CURRENT; file received 25 Sep 12:30 IST (see DEC-055 for what it settles). Supersedes the interim "PredictLeads domain canonical + four overrides" reading of DEC-013 and every domain the split derived (Public Bank, aliases). · **Impact:** every join; the split's `_ACCOUNTS.csv` must be rebuilt from this sheet; dashboard account names come from Column B, not vendor names.

### DEC-053 · Relevance direction: account evidence first, then the Rulebook; wording by evidence; conflicting signals count; never force an offering — CLIENT DECISION
- **Question:** D29 / round-3 F1 restatement of the relevance rule.
- **Answer (seven pointers, quoted short):** "Start with the account evidence first … Do not start with an HP offering from rulebook and then try to find evidence to support it." "Then check the Rulebook for an offering that supports the same opportunity." "Technology presence alone is not enough to recommend an offering." Wording: Intune/ServiceNow only → "Possible WXP fit internally, but do not recommend WXP yet"; + related fleet-management evidence → "HP WXP may be relevant to this opportunity"; + applicable Rulebook conditions supported → "HP WXP is relevant to this opportunity." "Consider conflicting evidence as well … BHP has Cisco WebEx and Cisco TelePresence detected, but Poly Intent = 0 / No Signal. Therefore, the collaboration technologies alone should not create an active Poly recommendation." "Case studies should be matched to the same use case/opportunity … not … only because it contains the same product name or comes from the same industry." "If no suitable HP offering is supported, do not force one" — show the evidenced opportunity/conversation instead (print example).
- **Decision date:** 25 Sep 2026 · **Who:** Dhruvi Patel · **Source:** MAIN 25 Sep 05:50 UTC; C45
- **Current status:** CURRENT; confirms and extends DEC-040. Sub-items 29a–c answered the same day (DEC-054g/h/i). · **Impact:** recommendations.py relevance logic (build must move from exact/alias matching to use-case fit, CONFLICT X-09); a new negative rule: a technology signal contradicted by zero intent in the matching category must not produce a recommendation.

### DEC-054 · Round-3 answers of 25 Sep (client-annotated OPEN_v2) — CLIENT DECISIONS
Source for all sub-items: `01_Client_Provided/Client_Answers/clarifying_opens_3_OPEN_v2_provided.docx` (C44), Dhruvi Patel, 25 Sep 2026 05:50 UTC. Quotes are the highlighted answers.
- **DEC-054a · News precedence:** "Resolved: to disagreement; consider exa news." When Exa and Google News RSS carry the same event with different details, **keep the Exa row**. This **replaces** the 24 Sep opens_1 answer 6 ("skip that particular news item"). Same-event definition (same account + date + normalised headline) not commented on — remains INTERNAL. Impact: Live Signals merge.
- **DEC-054b · Empty state:** "leave it out, do not write anything as of now" (G1) and, for the Stakeholder Map with no contacts, "do not write anything, leave that space empty" (B4). Provisional: "already escalated to sahaj … can we pls be flexible". Overturns our default (show with a message). Impact: every widget on accounts with gaps.
- **DEC-054c · Source labels:** "Right now go ahead with your labels" — Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study; publisher name on news cards; no vendor names. Provisional pending Sahaj. Impact: every source chip; Exa label question closed in practice.
- **DEC-054d · As-of date:** "let us show dataset's own retrieval date: meaning if we ingested the data for eg on 20th sept, keep that." Per-dataset ingestion date, not one drop date. Overturns our default; matches v4 §E. Impact: as-of line; recency anchor (closes CONFLICT C-02).
- **DEC-054e · Contacts:** one file only — "as of now we go with whatever we have, you will get one file" (B3); delivery still open ("will give that", B2). Impact: the five contact features are built once.
- **DEC-054f · Filings re-keying:** Fletcher Building Holdings NZ → fletcherbuilding.com; Fonterra → fonterra.com; the blank-domain Astra row holding United Tractors statements → "leave that row if it is not matching to astra" (exclude). Jabil Inc. 10-Q rows → attach to both Jabil accounts "for now". Hyundai DART rows → the account is "HKMC GROUP(HYUNDAI AUTOEVER) – KR", domain hyundai-autoever.com; the reports are Hyundai Autoever Corp.'s. Impact: filings index mapping; no corrected file is coming — we re-key.
- **DEC-054g · Integration-route context line:** "'Intune detected; possible WXP integration route' (do not mention no evidence)". Impact: wording of the context line (drop "no need evidenced").
- **DEC-054h · Unevaluable conditions:** treated as unmet → offering can reach "may be relevant" but never "relevant" — "yes". Impact: seat count / WXP tier / print-volume rules.
- **DEC-054i · No Rulebook-to-case-study mapping table:** "We do not want a fixed Rulebook-to-case-study mapping table. Both should be checked independently against the account evidence/use case." Four cases: offering + similar case study → use both; offering, no case study → offering only; case study, no supported offering → case study as supporting proof, do not force an offering; neither → use neither. Also answers F13 (no keyword/Rulebook-id table). Overturns our F1c and F13 defaults. Impact: case-study matcher decoupled from the Rulebook router.
- **DEC-054j · Proof method for the four features without a v4 row:** "yes" (as built), under the same four-case rule. Impact: Objection Playbook, Content Studio, Strategy Chat, Message Evaluator.
- **DEC-054k · Case-study proof on signal features — now, in named slots only:** Live Signals "Implication for HP"; Intent & Demand "So what for HP"; Technographic Map "what it means for HP"; **Stakeholder Map: not right now** ("Sahaj mentioned not right now in yesterday's meeting" — reverses opens_2 #30); "nowhere else"; optional ("we are not trying to compulsorily include it … if we can use, it would be appreciated"). Impact: proof placement.
- **DEC-054l · Proof on service plays:** "keep default" (yes). Impact: Opportunity Map service plays carry proof.
- **DEC-054m · Delivery dates and drops:** dates and timelines go to the WhatsApp group, "sahaj is the one deciding that"; consolidated drop request "noted". Process only.
- **Still open after this round:** A3 Name + Country columns ("will give that"), B2 contacts ("will give that"), D2 Exa dates ("we will send shortly"), E1 job rows for 45 accounts ("we will send shortly"), F7 risk-label logic and H1 GCP (both "escalated to Sahaj"), F11 evidence-tier gate and F12 APJ preference ("clarification needed pls" — re-ask in plain words). The CLARIFICATIONS (7) and UNRESOLVED_v2 (2) documents were not answered.

### DEC-055 · Domain audit sheet received: what it settles — CLIENT DATA (C43)
- Sheet "219 Account Audit" (the email's "219_Account_Domain_Audit"): 219 rows = the 220 accounts minus PT Astra International (its data is the separate seed delivery). Domain Check = MATCH on every row; Column H = "OK" ×204, "consider both names same, we get different name from diff tools" ×13 (Binus, ANA Holdings, Seiko Epson, Sony, CJ Group, KT Corp, Posco Group, NZ Defence Force, PwC NZ, Pilipinas Shell, Optum PH, Sagility PH, Siam Commercial Bank), blank ×2 (Stanley Electric, Shiseido — the two former domain mismatches, now resolved to stanley.co.jp and corp.shiseido.com).
- Confirms: Posco = posco.com; Pilipinas Shell = shell.com.ph; Shiseido = corp.shiseido.com; Stanley = stanley.co.jp; Westpac AU = westpac.com.au; Westpac NZ = westpac.co.nz; Pioneer = global.pioneer (kept); Jabil MY and SG both jabil.com; MUFG JP and the Bangkok branch both mufg.jp; **Public Bank = pbebank.com with the PredictLeads "Public Bank Lao Limited" row marked OK** — the client thereby closes our UNRESOLVED A4 (we had flagged that those rows are the Lao subsidiary's).
- Versus the 25 Sep split: three domains must change (Posco posco-inc.com → posco.com; Pilipinas Shell pilipinas.shell.com.ph → shell.com.ph; Public Bank publicbankgroup.com → pbebank.com). The split's `_ACCOUNTS.csv` should be rebuilt from this sheet, and Column B "Master Company" (e.g. "AUSTRALIA POST - AU") is the dashboard display name.

---

## 5. Product behaviour (UI)

### DEC-046 · Empty-state behaviour for a missing dataset — OPEN QUESTION
- **Question:** show the widget with a "no data from source" message, or hide it? Default offered: show with the message.
- **Answer:** "-> open" (opens_2 item 39; forwarded to Sahaj). Only precedent: hierarchy → say nothing (DEC-018).
- **Status:** RESOLVED 25 Sep (DEC-054b): leave the section out, write nothing; provisional pending Sahaj. Closes CONFLICT I-01. · **Impact:** every widget on accounts with gaps; Stakeholder Map on all accounts until contacts arrive.

### DEC-047 · Source labels on screen — OPEN QUESTION
- **Question:** replace raw file names with Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study; publisher name on news cards; no vendor names.
- **Answer:** "-> open" (opens_2 item 40; forwarded to Sahaj). Exa-vs-Google-News label unresolved (R3 UNRESOLVED D3).
- **Status:** RESOLVED 25 Sep (DEC-054c): our label set applies for now; provisional pending Sahaj. · **Impact:** every source chip.

### DEC-048 · Data as-of date — OPEN QUESTION
- **Question:** date of the 23 Sep drop or of the final consolidated drop? v4 says data_as_of_date = ingestion date.
- **Answer:** "-> open" (opens_2 item 41).
- **Status:** OPEN; default = final consolidated drop (INTERNAL ASSUMPTION). · **Impact:** the as-of line on every screen; recency calculations (CONFLICT C-03).

### DEC-049 · Objection Playbook says "Could be raised by" / "Topic owner", not "Likely raised by" — INTERNAL IMPLEMENTATION DECISION (put to the client 16 Sep)
- **Source:** QA-Discussion-Points_2026-09-16 §A.1; no client answer on record.
- **Status:** as built; OPEN for the client. · **Impact:** objection_reframe_cards wording; QA checks OP-03/OP-07.

### DEC-050 · Contacts: 0 of 220; five features cannot run until the contact file arrives — CLIENT DATA, OPEN
- **Answer:** "Ans 1) Contact Data open" (opens_1); section B "->OPEN" (opens_2 items 8–10). Client has since said (per R3 B2) that some accounts will get names and details, the rest names or roles only, with prompts and supporting material to follow.
- **Status:** OPEN — the single biggest blocker; 25 Sep: "will give that", one file only (DEC-054e). · **Impact:** Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio, Message Evaluator for all accounts.

### DEC-051 · GCP environment — OPEN
- **Answer:** "-> open" (opens_2 item 42); "RESOLVED: Already followed up with sahaj" on the 24 Sep timeline item, but access itself "->OPEN".
- **Status:** OPEN; "escalated to sahaj" (25 Sep); project id and region unknown. · **Impact:** 220-account deployment.

---

## 6. Internal implementation decisions and assumptions not covered above (all INTERNAL, none client-approved)

| Id | Decision / assumption | Where it lives | Client visibility |
|---|---|---|---|
| INT-01 | Intent four-step flow: hp_intent category score primary; Bombora `11_intent_score` supporting; Explorium sheets 4–5 confirm; a category whose score rests on a noisy keyword keeps its score but is never primary (memory of 11 Sep). **Note:** HP-Input-Data-Contract.md says the noisy-keyword list is "empty by client instruction (Sep 2026)" — the two records disagree (CONFLICT I-07). | intent_demand_signals.py, intent_topic_map.py | Described in HP-Account-Intelligence-Rules.docx (10 Sep), under review |
| INT-02 | News de-duplication heuristic: headline similarity ≥ 0.85 OR identical evidence sentence + date (Rules doc); split uses same account + same date + normalised headline. | recent_news_signals.py; split_account_data.py | Rules doc (unreviewed); R3 D1 asks for a yes/no |
| INT-03 | Stakeholder composite 25/25/20/15/15 and Priority Contact ≥ 60 (from ABX F3 weights; input scales are ours). | stakeholder_map.py | Rules doc; v4 has no stakeholder score (CONFLICT X-05) |
| INT-04 | Opportunity plays ordered by three checks, outcomes DROPPED/DEMOTED/DISCOVERY/PUBLISHED (Rules doc) — the check *tags* were dropped from the UI on 23 Sep; the ordering logic status is not recorded. | solution_narrative_opportunity_map.py | Rules doc; v4 evidence tiers differ (CONFLICT X-04) |
| INT-05 | Grounding: numbers must exist as exact tokens in the uploads; unsourced proof points and quantified impacts are deleted rather than labelled. | grounding.py | Rules doc; QA-Discussion-Points §A.3–4 |
| INT-06 | 220-account split corrections: Public Bank → publicbankgroup.com and Westpac → westpac.com.au derived from the Website column; three Ministries of Defence and two Westpacs disambiguated by country suffix; four alias rewrites; Jabil SG / MUFG Bangkok get no domain-keyed rows; Astra datasets filled from the seed. | `220 account split csv/_CORRECTIONS.txt` | Not sent as such; conflicts with DEC-013/016 (CONFLICT I-02/I-03) |
| INT-07 | Filings name-variant mapping (ANZ Group, IAG, BDO, UOB, Westpac, Fletcher, Astra; keiretsu rows split by domain); five non-220 companies ignored; the United Tractors row excluded. | split corrections report; R3 C5 | Stated to client in R3 C5 with silence defaults |
| INT-08 | Tech Map header "N found, M map to HP categories"; ~200 unmapped technologies not browsable. | tech_landscape.py | QA-Discussion-Points §C.11, unanswered |
| INT-09 | Strategy Chat answers/citations deferred to "Step 8 RAG"; source_links / uncertainty_state stay pending. | strategy_chat.py | QA-Discussion-Points §C.9, unanswered |
| INT-10 | Case-study cleaning 384 → 89; publication dates empty; corrupted outcome figures suppressed; keyword table for product-line mapping now, Rulebook ids later. | case-study matcher | Accepted (DEC-042); F13 default pending |
