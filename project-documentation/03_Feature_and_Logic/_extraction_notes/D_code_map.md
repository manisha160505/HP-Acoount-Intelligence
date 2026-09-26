> GENERATED EXTRACTION NOTES — produced 25 Sep 2026 by an automated read of the plain-text conversions of the source documents. INTERNAL. Not client text. Verify any number, rule id or quote against the original document in 01_Client_Provided/ or 02_Decision_Maker/ before relying on it. Line numbers refer to the text conversions, not to Word pages.

# HP Features to Code Mapping

## Feature → Code Inventory (11 Features / 32 Widgets)

| Feature Key | Widgets (count) | Dataset Keys Consumed | Extractor File(s) | Scoring / Rule Modules |
|---|---|---|---|---|
| executive_dashboard | exec_summary_card, exec_key_metrics, exec_hiring_velocity, exec_urgency_score, exec_strategic_priorities (5) | firmographics, company_hierarchy, job_openings, prospect_contacts, compliance_filings | hp-backend/src/app/services/extractors/executive_dashboard.py | hp-backend/src/app/services/dashboard/urgency.py `compute_urgency_score()`, `dashboard/priorities.py` for strategic priorities |
| recent_news_signals | news_signals_feed, news_relevance_summary (2) | google_news, news_events | hp-backend/src/app/services/extractors/recent_news_signals.py | hp-backend/src/app/services/extractors/signal_scoring.py `compute_relevance_score()`, news dedup in recent_news_signals.py |
| stakeholder_map | stakeholder_contacts_grid, stakeholder_influence_map, stakeholder_talking_points (3) | prospect_contacts, firmographics, technographics, intent_score, google_news, news_events | hp-backend/src/app/services/extractors/stakeholder_map.py | hp-backend/src/app/services/extractors/stakeholder_map.py `compute_stakeholder_score()` (25% seniority + 25% HP relevance + 20% influence + 15% completeness + 15% priority) |
| solution_narrative_opportunity_map | opportunity_context_card, opportunity_trigger_signals, opportunity_narrative_plays (3) | firmographics, technographics, intent_score, google_news, news_events, prospect_contacts, compliance_filings | hp-backend/src/app/services/extractors/solution_narrative_opportunity_map.py | hp-backend/src/app/services/hp/rulebook.py for play prioritization (Critical/High/Medium/Low); hp-backend/src/app/services/hp/recommendations.py for opportunity relevance |
| tech_landscape | technographic_map, tech_stack_matrix, tech_detections_reference, webstack_breakdown, technographic_hp_recommendations (5) | technographics, technology_detections, webstack, intent_score, firmographics | hp-backend/src/app/services/extractors/tech_landscape.py | hp-backend/src/app/services/hp/tech_confidence.py `compute_confidence()` for HP product line recommendations; hp-backend/src/app/services/hp/recommendations.py for product confidence scoring |
| objection_playbook | objection_incumbent_context, objection_reframe_cards (2) | technographics, firmographics, prospect_contacts | hp-backend/src/app/services/extractors/objection_playbook.py | Not found (AI-generated synthesis only) |
| content_studio | content_persona_context, content_generated_assets, content_angle_options (3) | prospect_contacts, job_openings, firmographics | hp-backend/src/app/services/extractors/content_studio.py (with generate_content_asset, suggest_content_angles) | Not found (AI-generated collateral) |
| strategy_chat | strategy_snapshot_context, strategy_chat_interface (2) | firmographics, company_hierarchy, technographics, webstack, job_openings, google_news, news_events, intent_score, technology_detections | hp-backend/src/app/services/extractors/strategy_chat.py | Not found (RAG/LLM-based Q&A) |
| message_evaluator | evaluator_persona_context, evaluator_feedback_score (2) | prospect_contacts, job_openings | hp-backend/src/app/services/extractors/message_evaluator.py | hp-backend/src/app/services/evaluator/scoring.py `catalogue()`, multiple objective scoring functions |
| content_messaging | messaging_context_card, messaging_pillars_output (2) | firmographics, technographics, intent_score, google_news, news_events | hp-backend/src/app/services/extractors/content_messaging.py | hp-backend/src/app/services/messaging/pillars.py `generate_messaging_pillars()` (challenge, benefit, proof point synthesis) |
| intent_demand_signals | intent_topics_table, intent_category_summary, intent_hiring_demand (3) | hp_category_intent, intent_score, intent_topics, job_openings, technographics, webstack | hp-backend/src/app/services/extractors/intent_demand_signals.py | hp-backend/src/app/services/hp/intent_topic_map.py for theme/category mapping; hp-backend/src/app/services/extractors/intent_demand_signals.py for theme aggregation |

## Dataset Registry (source files)

| Dataset Key | Source File/Sheet (from registry.py or inferred) | Type | Format |
|---|---|---|---|
| firmographics | 1_Firmographics (primary reference in mappings) | single_file_csv | CSV |
| company_hierarchy | 2_Company_Hierarchy (primary reference) | single_file_csv | CSV |
| job_openings | job_openings (multi-file or flat table) | single_file_csv | CSV |
| prospect_contacts | 14_Prospect_Contacts (primary reference) | single_file_csv | CSV |
| technographics | 4_Technographics (primary reference) | single_file_csv | CSV |
| webstack | 5_Tech_Breakdown (primary reference) | single_file_csv | CSV |
| google_news | google_news_rss_data (primary reference) | multi_file | XLSX/CSV |
| news_events | news_events or news_events (secondary) | multi_file | CSV |
| intent_score | 11_intent_score (primary reference) | single_file_csv | CSV |
| intent_topics | 10_Intent_Topics (primary reference) | single_file_csv | CSV |
| hp_category_intent | Intent Data (Wide) (primary reference) | single_file_csv | CSV |
| technology_detections | technology_detections (single file) | single_file_csv | CSV |
| compliance_filings | Multi-file PDF directory (from registry) | multi_file | PDF |
| extended_company | extended_company.csv | single_file_csv | CSV |

## Features in WIDGET_REGISTRY but Missing from FEATURE_MAPPINGS

**None found.** All 11 feature keys in WIDGET_REGISTRY (executive_dashboard, recent_news_signals, stakeholder_map, solution_narrative_opportunity_map, tech_landscape, objection_playbook, content_studio, strategy_chat, message_evaluator, content_messaging, intent_demand_signals) are present in FEATURE_MAPPINGS.

---

**File Sources:**
- WIDGET_REGISTRY: hp-backend/src/app/api/v1/widgets.py:93–490
- FEATURE_MAPPINGS: hp-backend/src/app/api/v1/feature_mapping.py:12–965
- Extractors inventory: hp-backend/src/app/services/extractors/
- Scoring/Rules modules: hp-backend/src/app/services/dashboard/urgency.py, hp-backend/src/app/services/dashboard/priorities.py, hp-backend/src/app/services/hp/tech_confidence.py, hp-backend/src/app/services/hp/rulebook.py, hp-backend/src/app/services/hp/recommendations.py, hp-backend/src/app/services/evaluator/scoring.py, hp-backend/src/app/services/messaging/pillars.py
- Dataset registry: hp-backend/src/app/schemas/account_data.py:5–161
