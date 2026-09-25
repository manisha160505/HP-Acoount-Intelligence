# Opportunity Map (`solution_narrative_opportunity_map`)

Requirements section: Feature 4 — Solution Narrative / Opportunity Map (ABX v3 L65–74). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
firmographics (business outcome), technographics, intent_score, google_news + news_events (trigger), prospect_contacts, compliance_filings; Rulebook + case studies; PredictLeads products (per 23 Sep screenshot).

## Decision / logic documents (read these before changing the feature)
- C01 ABX F4: 3–5 tiles; ordered by three checks; "no numeric opportunity score is defined".
- DEC-034 (23 Sep): **drop the Verified Evidence / Timing Trigger / HP Fit tags; keep Priority Critical/High/Medium/Low** as in SEA Limited.
- C28 v4: evidence tiers — Opportunity (≥2 logically related independent pipelines), Conversation Starter (1 strong signal), Context Only; confidence_tier field; thin-account path; word limits.
- DEC-039/040 Rulebook and case studies strengthen an established opportunity; use-case fit; graded wording. DEC-043 one primary route, others secondary (partially resolved). DEC-033 3D route evidence-led.

## Supporting reference
- 02_Decision_Maker/HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook.docx (v1; FINAL missing)
- _extraction_notes/B_scoring_and_rulebook.md §2.1–2.4
- CONFLICT_REGISTER C-09, X-04, X-07, X-08

## Open questions
- D29 relevance rule vs build (X-09)
- D34 one vs five routes
- D35 T0–T3 tiers
- D46 proof on service plays
- D47 evidence-tier gate on proof
- QA16-3 OM-10/OM-13 checks
- C-09 what computes the Priority label

## Known data gaps
- Contacts 0/220 (persona side)
- Filings PDFs not ingested
- Rulebook FINAL (Print rules) not on this machine

## Code touched
- `hp-backend/src/app/services/extractors/solution_narrative_opportunity_map.py`
- `hp-backend/src/app/services/hp/rulebook.py (Critical/High/Medium/Low)`
- `hp-backend/src/app/services/hp/recommendations.py`
- `widgets: opportunity_context_card, opportunity_trigger_signals, opportunity_narrative_plays`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
