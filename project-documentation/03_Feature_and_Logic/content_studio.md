# Content Studio (`content_studio`)

Requirements section: Feature 7 — Content Studio (ABX v3 L98–107). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
prospect_contacts (named persona) or job_openings (role proxy), firmographics; Rulebook facts; case-study proof points per asset.

## Decision / logic documents (read these before changing the feature)
- C01 ABX F7: Email ≤110 words; LinkedIn 2–3 variants × 150–200 words; One-Pager ≤400 words in four sections; low-confidence facts only if the user opts in with a qualifier.
- DEC-004 **human-in-the-loop / co-creation**: brief → suggested options → user selects/adjusts → generation (24 Aug email). DEC-004 HP deck rules for product facts (C02).
- v4 has no row (D44 default: Proof Points section per asset).

## Supporting reference
- 02_Decision_Maker/HP_220_Account_Platform_additional data (1).docx (deck rules + guardrails)
- _extraction_notes/A_client_requirements.md §2.7, §3

## Open questions
- D44
- D8 contacts (persona)
- QA16-10 regeneration cost after prompt changes

## Known data gaps
- Contacts 0/220 → role-proxy persona only
- Job openings missing for 45 accounts (proxy persona)

## Code touched
- `hp-backend/src/app/services/extractors/content_studio.py (generate_content_asset, suggest_content_angles)`
- `widgets: content_persona_context, content_generated_assets, content_angle_options`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
