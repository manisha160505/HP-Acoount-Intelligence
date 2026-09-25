# Stakeholder Map (`stakeholder_map`)

Requirements section: Feature 3 — Stakeholder Map (ABX v3 L54–63). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
prospect_contacts (**empty for all 220**; Apollo_All_Contacts per v4 not received); firmographics, technographics, intent_score, news for talking points; Rulebook + case studies (added by DEC-041).

## Decision / logic documents (read these before changing the feature)
- C01 ABX F3: 20–30 stakeholders; score 25/25/20/15/15 (no input scales given); influence types incl. "Blocker" in rules but not in output.
- C28 v4 Stakeholder Map row: How to Open + HP Play Focus, 40–100 words; contacts with Pending/Review status not used until approved; no numeric score.
- DEC-041 Rulebook and case studies included here (opens_2 #30). DEC-007 ~30 buying-committee roles, then 5–8 more.
- DEC-049 (internal, put to client 16 Sep): objection/talking-point wording never predicts a named person's behaviour.

## Supporting reference
- 04_Data_and_Source_Definitions/Contacts_Apollo/README.md
- _extraction_notes/B_scoring_and_rulebook.md §2.8 (internal composite)
- CONFLICT_REGISTER X-05

## Open questions
- D8 contact file (BLOCKER)
- D9 one file or two
- D10 empty state with no contacts
- QA16-6/7/8 avatar, LinkedIn links, active-employee label
- X-05 internal composite score vs v4 (no score)

## Known data gaps
- 0 of 220 accounts have contacts
- No employment-status column in any contact source
- 8 of 23 seed LinkedIn links are Apollo URNs

## Code touched
- `hp-backend/src/app/services/extractors/stakeholder_map.py compute_stakeholder_score()`
- `widgets: stakeholder_contacts_grid, stakeholder_influence_map, stakeholder_talking_points`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
