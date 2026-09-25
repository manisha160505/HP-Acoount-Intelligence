# Feature and logic

One file per in-scope feature, plus three cross-cutting files. Each feature file answers "which documents do I need to read before changing this feature?" and separates CLIENT DECISIONS from INTERNAL decisions and OPEN questions. The compact tree view of the same information is `00_INDEX/FEATURE_DOCUMENT_MAPPING.md`.

| Feature key | UI label | File |
|---|---|---|
| executive_dashboard | Executive Dashboard | executive_dashboard.md |
| recent_news_signals | Live Signals | recent_news_signals.md |
| stakeholder_map | Stakeholder Map | stakeholder_map.md |
| solution_narrative_opportunity_map | Opportunity Map | solution_narrative_opportunity_map.md |
| tech_landscape | Technographic Map | tech_landscape.md |
| objection_playbook | Objection Playbook | objection_playbook.md |
| content_studio | Content Studio | content_studio.md |
| strategy_chat | Strategy Chat | strategy_chat.md |
| message_evaluator | Message Evaluator | message_evaluator.md |
| content_messaging | Content Messaging | content_messaging.md |
| intent_demand_signals | Intent & Demand Signals | intent_demand_signals.md |

Cross-cutting: `cross_cutting_entity_matching.md`, `cross_cutting_recommendations_rulebook_case_studies.md`, `cross_cutting_news_and_empty_states.md`.

`_extraction_notes/` holds three GENERATED, unverified rule registers: A (per-feature extraction of HP_ABX_v3_final + addendum + sourcing reference), B (rule-by-rule register of the five client logic docs and the internal rules doc, ~250 rows, plus 30 recorded conflicts), D (feature → code map). They are internal working aids; the source documents win.

Also relevant: the 12th module, Reporting & Usage Analytics (DEC-004), has no feature key in the registry and no status in any later document.
