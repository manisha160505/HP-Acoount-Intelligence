# Technographic Map (`tech_landscape`)

Requirements section: Feature 5 — Tech Landscape (ABX v3 L76–85). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
Explorium 4_Technographics (20 category columns + Full Tech Stack), 5_Tech_Breakdown / WebStack, PredictLeads technology_detections (reference), hp_intent category scores (Driver 2), Rulebook rule matches (WXP 04/07 …); Related Technologies from hp_intent as fallback (researched, not detected).

## Decision / logic documents (read these before changing the feature)
- C21 HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL: **Driver 1 HP-relevant technology evidence + Driver 2 HP-category intent support → card confidence %** (DEC-033).
- C01 ABX F5: status Confirmed (1 direct or ≥2 independent strong) / Likely / Conflicting / Unknown; HP-relationship labels.
- DEC-035 keep Low/Medium/High **Risk** labels (SEA Limited parity); our lookup logic awaits Sahaj. DEC-010/032 extra "Recommendation for HP" card dropped for now. DEC-019 WebStack + Tech_Breakdown are technographic sources.
- C28 v4 Technographic Map row; K3 banned output (WXP intent from Intune/ServiceNow alone).

## Supporting reference
- _extraction_notes/B_scoring_and_rulebook.md §2.7
- CONFLICT_REGISTER C-03, C-04, X-10

## Open questions
- D37 risk-label logic approval
- E23-3 "Contextual — no direct HP line" tag
- C-03 does the confidence card wording "Consider WXP" breach v4 K3
- QA16-11 ~200 unmapped technologies
- D22 Related Technologies shown as researched

## Known data gaps
- Technographics present for 207/220; tech detections 216/220; 47 unclaimed detection rows
- No detectedVia / first-seen in Explorium
- Rulebook FINAL missing (rule ids may have changed)

## Code touched
- `hp-backend/src/app/services/extractors/tech_landscape.py`
- `hp-backend/src/app/services/hp/tech_confidence.py compute_confidence()`
- `hp-backend/src/app/services/hp/recommendations.py`
- `widgets: technographic_map, tech_stack_matrix, tech_detections_reference, webstack_breakdown, technographic_hp_recommendations`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
