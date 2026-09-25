# Intent & Demand Signals (`intent_demand_signals`)

Requirements section: Feature 10 — Intent & Demand Signals (ABX v3 L131–140). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
hp_category_intent (hp_intent_results 2.xlsx, Intent Data (Wide): PCs, Workstations, Poly, Printers, 3D Printers; Topics Researched, Keywords Matched, Related Technologies); Explorium 11_intent_score (Bombora topics) and 10_Intent_Topics; job_openings (hiring-linked demand); technographics + webstack (confirmation).

## Decision / logic documents (read these before changing the feature)
- DEC-012 (3 Sep, Konika): **category-specific HP intent score is the primary signal**; Source A topics are supporting signals. Reaffirmed opens_1 answer 10.
- C01 ABX F10: Max / Average / Trend per provider; no cross-provider formula; topic → theme → HP category mapping.
- C28 v4 Intent & Demand row (themes as separate seller conversations); C26 mapping (Rulebook + case studies feed it).
- INT-01 four-step flow and noisy-keyword rule (internal; CONFLICT I-07 on whether the client said the list is empty).

## Supporting reference
- 04_Data_and_Source_Definitions/HP_Intent/README.md
- _extraction_notes/A_client_requirements.md §2.11

## Open questions
- I-07 noisy-keyword rule provenance
- D22 Related Technologies as researched
- D45 case-study proof now or later
- C-01/S-06 which intent streams v4 recognises

## Known data gaps
- Intent present for 173/220 (client: genuine no-data)
- NSW Education intent file not on this machine
- Level Of Intent column empty in Source A (input contract 5.4)

## Code touched
- `hp-backend/src/app/services/extractors/intent_demand_signals.py`
- `hp-backend/src/app/services/hp/intent_topic_map.py`
- `widgets: intent_topics_table, intent_category_summary, intent_hiring_demand`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
