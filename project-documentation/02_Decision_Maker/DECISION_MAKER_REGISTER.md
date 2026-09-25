# Decision-Maker Register

The documents in this folder are the ones that decide what the product outputs: business rules, formulas, thresholds, precedence, matching rules, scope. Only **current** versions are copied here; superseded versions stay in `01_Client_Provided/…/_SUPERSEDED/` and are listed at the bottom. Every row cites the provenance id in `00_INDEX/PROVENANCE_REGISTER.md`.

Reading order for a developer: 1 → 2 → 7 → 8 → 3–6 → 9–10 → 11.

| # | File in this folder | Original filename | Source | Date received | Version | Replaced? | Current version | Approval state | Governs |
|---|---|---|---|---|---|---|---|---|---|
| 1 | HP_ABX_v3_final.docx | same | Client email, Dhruvi, 22 Aug 2026 (C01) | 22 Aug | v3 final | No | This one | **CLIENT — FINAL.** The requirements baseline; later client docs refine specific formulas (urgency, live signal, tech confidence, recommendations) and override some UI rules (Opportunity Map tags). | All 11 features: data, rules, guardrails, fallbacks, outputs |
| 2 | HP_220_Account_Platform_additional data (1).docx | HP_220_Account_Platform_additional data.docx | Client email, Dhruvi, 24 Aug 2026 (C02) | 24 Aug | 1 | No | This one | **CLIENT — FINAL** | HP deck RAG rules (18 signal→deck rules, 17 guardrails, country blocks); Reporting & Usage Analytics module |
| 3 | HP_Urgency_Score_Updated_Final.docx | same | Client email, Dhruvi, 16 Sep 2026 (C09) | 16 Sep | Updated Final | Replaced the delivery team's 16 Sep proposal | This one | **CLIENT — FINAL** (email adds: 60% coverage minimum; job-status rule; score scales; applies to all 220). Internal arithmetic inconsistencies noted in CONFLICT_REGISTER C-07/C-08. | Executive Dashboard urgency score |
| 4 | HP_Live_Signal_Scoring_Logic.docx | same | Client email, Dhruvi, 17 Sep 2026 (C18) | 17 Sep | 1 ("Final Scoring Framework" inside) | No | This one | **CLIENT — CONFIRMED** 24 Sep (opens_2 #36: score, no tiers) | Live Signals score /10 |
| 5 | HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx | same | Client email, Dhruvi, 18 Sep 2026 (C21) | 18 Sep | FINAL | Replaced the 17 Sep version (C17, not local) | This one | **CLIENT — FINAL** | Technographic Map card confidence |
| 6 | HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook.docx | same | Client email, Dhruvi, 17 Sep 2026 (C15) | 17 Sep | v1 | **YES — by the FINAL of 23 Sep (C29), which is NOT on this machine** | C29 (missing) | **CLIENT — SUPERSEDED but only local copy.** Use for non-Print rules; Print rules are only in FINAL. Retrieve C29 before changing rulebook.py. | HP product / services / solutions facts and routing for every recommendation |
| 7 | HP_Recommendation_Tuning_Logic_FINAL_v4.docx | same | Client email, Dhruvi, 23 Sep 2026 (C28) | 23 Sep | FINAL v4 | Replaced the 15 Sep pptx (C08, not local, "not used") | This one | **CLIENT — FINAL**, with the relevance threshold clarified by Dhruvi's 24 Sep annotation (DEC-040) | Recommendation engine: inputs, evidence tiers, permitted language, as-of date, output schema, word limits, banned outputs, proof library |
| 8 | new file explanation 220 acc.xlsx | same | Client email, Dhruvi, 18 Sep 2026 (C26) | 18 Sep | 1 | No | This one | **CLIENT — FINAL**; extended 24 Sep (opens_2 #30: Stakeholder Map added) | Which file feeds which feature; Lifecycle and the 15 Sep deck "not used" |
| 9 | clarifying opens_1  Dhruvi.docx | clarifying opens_1.docx (re-send of 24 Sep 14:43 UTC) | Client email, Dhruvi (C35) | 24 Sep | re-send (adds the "Sec filings" line) | Replaced the 09:30 UTC send (C34) | This one | **CLIENT — ANSWERS** to the 10 data questions; items marked "open" inside are still open | Identity/domain rules, news merge, undated rows, coverage gaps, filings source |
| 10 | clarifying opens_2.docx | same | Client email, Dhruvi (C36) | 24 Sep | 1 | No | This one; round 3 (I14) is awaiting answers | **CLIENT — ANSWERS** to the 43 decisions. "->RESOLVED" against an item with a stated default = default accepted (recorded as PARTIALLY RESOLVED where the answer is a bare "RESOLVED"). | Every decision in DECISION_LOG sections 2–5 |
| 11 | APAC_Account_Parent_Child_Mapping.xlsx | same | Client email, Dhruvi, 22 Aug 2026 (C03) | 22 Aug | 1 | No | This one | **CLIENT — FINAL** for the account names; **one domain per account still owed** (DEC-002) | Scope: the 220 accounts, parent/child groups, recommended merges |
| 12 | HP-Account-Intelligence-Rules.docx | same | **Delivery team** (Manisha) → client, 10 Sep 2026 (I01) | 10 Sep | 1 | Partly overtaken by 3–7 above | This one (no v2 issued) | **INTERNAL — UNDER CLIENT REVIEW, no feedback received.** Not approved. Sections on Live Signal tiers, opportunity ordering, stakeholder score and proof corpus conflict with later client documents (CONFLICT_REGISTER X-01…X-06). | Grounding, gates, scoring and wording guards as built on 10 Sep |

## Decision content that lives only in email (no file)
These are binding client statements with no document of their own; they are recorded in `00_INDEX/DECISION_LOG.md` with the message date:
- 16 Sep 13:35 UTC — urgency clarifications (60% coverage, 4 drivers, job status, score scales).
- 18 Sep 07:28 UTC — Fleet Refresh excluded; filings URL precedence.
- 18 Sep 13:32 UTC — Rulebook / case-study usage principle and the two worked examples.
- 23 Sep 12:33 UTC — hierarchy rule; Opportunity Map tags; Tech Map risk labels; PredictLeads sheets to use.
- 24 Sep 09:30 UTC — relevance threshold (use-case fit, graded wording); drop the extra Tech Map card; drop JEV.

## Superseded decision documents (kept, not here)
| Id | File | Superseded by | Where |
|---|---|---|---|
| C08 | HP_220_Account_Recommendation_Logic(1).pptx (15 Sep) | C28 v4 | not on this machine — placeholder in `01_Client_Provided/Logic_and_Scoring/_SUPERSEDED/` |
| C17 | HP_Tech_Landscape_Confidence_Scoring_Logic.docx (17 Sep) | C21 FINAL | not on this machine — placeholder in the same folder |
| C34 | clarifying opens_1.docx (09:30 UTC send) | C35 | `01_Client_Provided/Client_Answers/_SUPERSEDED/` |
| — | Delivery team's five-driver urgency proposal (email 16 Sep 02:34 UTC) | C09 | text in `00_INDEX/EMAIL_TIMELINE.md` / thread |
| I14 | clarifying_opens_3_OPEN.docx and _UNRESOLVED.docx (non-v2) | the _v2 files that were sent | `07_Internal_Generated/Client_Facing_Round3/` |

## Not decision-makers (deliberately excluded)
HP Care Pack / Q426 / Wolf / HP IQ / Lifecycle / Print PDFs / product decks — the client states their content is folded into the Rulebook or not used ("Not used separately"); they are in `08_Reference_Material/`. Internal analyses, QA outputs and trackers are in `07_Internal_Generated/` and change nothing on their own.
