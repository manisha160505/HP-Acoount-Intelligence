# Strategy Chat (`strategy_chat`)

Requirements section: Feature 8 — Strategy Chat (ABX v3 L109–118). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
Full cached account snapshot: firmographics, hierarchy, technographics, webstack, job_openings, google_news, news_events, intent_score, technology_detections; filings (per 18 Sep mapping); Rulebook.

## Decision / logic documents (read these before changing the feature)
- C01 ABX F8: grounded in the snapshot; evidence order current-verified → older-verified → inferred; "Do not create a numeric evidence score".
- C26 file explanation: filings, Rulebook, case studies feed this feature. v4 has no row (D44).
- 14 Sep: "Strategy Chat – currently under development"; QA16-9 citations deferred to Step 8 RAG (internal).

## Supporting reference
- _extraction_notes/A_client_requirements.md §2.8

## Open questions
- D44
- QA16-9 source links / uncertainty state
- Filings ingestion (D11/D12)

## Known data gaps
- Feature not producing answers yet (strategy_chat_interface pending)
- Filings PDFs not ingested

## Code touched
- `hp-backend/src/app/services/extractors/strategy_chat.py`
- `widgets: strategy_snapshot_context, strategy_chat_interface`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
