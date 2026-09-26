# Objection Playbook (`objection_playbook`)

Requirements section: Feature 6 — Objection Playbook (ABX v3 L87–96). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
technographics (incumbents), firmographics, prospect_contacts (raiser / topic owner), Rulebook + case studies (proof per area card).

## Decision / logic documents (read these before changing the feature)
- C01 ABX F6: 5–10 objections; three-tier ordering; "no numeric objection score".
- DEC-041 Rulebook/case studies used here (as built). DEC-049 "Could be raised by" / "Topic owner" wording (internal, disclosed 16 Sep).
- v4 has **no row** for this feature (D44 / round 3 F8: one case study per area card as the default).

## Supporting reference
- 02_Decision_Maker/HP-Account-Intelligence-Rules.docx §7 (internal, under review)
- _extraction_notes/A_client_requirements.md §2.6

## Open questions
- D44 proof method (no v4 row)
- QA16-1/2 wording and Counter Question checks
- D47 evidence-tier gate removes proof from most objection cards on thin accounts

## Known data gaps
- Contacts 192/220 (Apollo, 26 Sep; 28 accounts none) (topic owner)
- Rulebook FINAL missing

## Code touched
- `hp-backend/src/app/services/extractors/objection_playbook.py (_resolve_likely_raiser)`
- `widgets: objection_incumbent_context, objection_reframe_cards`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
