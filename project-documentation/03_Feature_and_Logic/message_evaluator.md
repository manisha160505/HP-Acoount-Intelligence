# Message Evaluator (`message_evaluator`)

Requirements section: Feature 9 — Message Evaluator (ABX v3 L120–129). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
prospect_contacts (named persona) or job_openings (proxy); the seller's draft message.

## Decision / logic documents (read these before changing the feature)
- C01 ABX F9: four objective formulas, dimension scores 0–100.
- v4 has no row (D44 default: citations of already-attached proof).

## Supporting reference
- _extraction_notes/A_client_requirements.md §2.9

## Open questions
- D44
- D8 contacts

## Known data gaps
- Contacts 0/220; readiness "none" for 44 accounts in the split (no job rows either)

## Code touched
- `hp-backend/src/app/services/extractors/message_evaluator.py`
- `hp-backend/src/app/services/evaluator/scoring.py catalogue()`
- `widgets: evaluator_persona_context, evaluator_feedback_score`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
