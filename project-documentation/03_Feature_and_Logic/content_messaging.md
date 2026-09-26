# Content Messaging (`content_messaging`)

Requirements section: Feature 15 — Content Messaging (ABX v3 L186–195). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
firmographics, technographics, intent_score, google_news + news_events; filings (18 Sep mapping); Rulebook + case studies (proof points).

## Decision / logic documents (read these before changing the feature)
- C01 ABX F15: 3–5 messaging pillars (challenge, benefit, proof point).
- C28 v4 Content Messaging row: several pillars, each conditioned on separate evidence; word limits.
- Rulebook C 06 one main recommendation (consistent, CONFLICT C-27 = NO).
- Internal (16 Sep): unsourced proof points are deleted; badge shows "n/m sourced".

## Supporting reference
- _extraction_notes/A_client_requirements.md §2.10

## Open questions
- QA16-4 CM-15 check
- D29 relevance rule

## Known data gaps
- Filings PDFs not ingested

## Code touched
- `hp-backend/src/app/services/extractors/content_messaging.py`
- `hp-backend/src/app/services/messaging/pillars.py generate_messaging_pillars()`
- `widgets: messaging_context_card, messaging_pillars_output`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
