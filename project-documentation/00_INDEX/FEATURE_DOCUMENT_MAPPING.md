# Feature → Document Mapping

For each of the 11 in-scope features: required data → decision/logic documents → supporting reference → open questions → known data gaps → potential code impact. Ids: C-xx / I-xx = `PROVENANCE_REGISTER.md`; DEC-xxx = `DECISION_LOG.md`; D-xx / QA16-x = `05_Questions_and_Clarifications/`; C-/X-/I-/S- = `CONFLICT_REGISTER.md`. Fuller narrative per feature: `03_Feature_and_Logic/<feature>.md`.

Documents every feature depends on (read once):
```
ALL FEATURES
├── C01 HP_ABX_v3_final.docx ........................ requirements baseline (per-feature sections)
├── C28 HP_Recommendation_Tuning_Logic_FINAL_v4.docx  recommendation engine, evidence tiers, as-of date, word limits
├── C15/C29 Rulebook (v1 local; FINAL 23 Sep MISSING)  HP facts and routing
├── C26 new file explanation 220 acc.xlsx ........... which file feeds which feature
├── C35/C36 clarifying opens_1 / opens_2 ............ client answers (identity, news, filings, UI)
├── DEC-013/014/015/016 entity & domain matching ..... 03_Feature_and_Logic/cross_cutting_entity_matching.md
├── DEC-039/040/041/042 Rulebook & case-study use .... 03_Feature_and_Logic/cross_cutting_recommendations_rulebook_case_studies.md
└── I01 HP-Account-Intelligence-Rules.docx .......... INTERNAL, under client review — not approved
```

```
Executive Dashboard  (executive_dashboard)
├── Required data ........ Explorium 1_Firmographics + 2_Company_Hierarchy; filings 1.csv + sec_filings; job_openings; contacts; tech + intent (reused); RSS + Exa
├── Decision / logic ..... C01 F1 · C09 Urgency (4 drivers 20/25/30/25, 60% coverage) + 16 Sep email · DEC-018 hierarchy · DEC-025 filings · C28 v4 row
├── Supporting reference . 08 Astra_Seed_Account (worked example) · _extraction_notes/B §2.5
├── Open questions ....... D2 entity scope · D11/D14 filings reconciliation · D27 blank job status · D41 as-of date · C-07/C-08 urgency arithmetic
├── Known data gaps ...... filings PDFs 0/220 (31 accounts have none) · hierarchy 165/220 · contacts 0/220 · jobs missing 45 · single firmographics row
└── Code impact .......... extractors/executive_dashboard.py · dashboard/urgency.py · dashboard/priorities.py · widgets exec_*
```
```
Live Signals  (recent_news_signals)
├── Required data ........ google_news (RSS + Exa merged, 14 cols) · news_events (PredictLeads) · filings (18 Sep mapping)
├── Decision / logic ..... C18 Live Signal Scoring (0.30/0.50/0.20, /10) · DEC-020 merge & skip · DEC-021 undated rows · DEC-023 12 months, no cap · DEC-024 no Low/High · DEC-032 no tiers
├── Supporting reference . _extraction_notes/B §2.6 · CONFLICT C-01, C-02, X-01, X-02
├── Open questions ....... D16 same-event definition · D17 Exa dates · D18 Exa label · X-01 old events at 0 or excluded · D45 proof timing
├── Known data gaps ...... 5,120/9,221 Exa rows undated · RSS covers 99 accounts · corrupted Thai cells
└── Code impact .......... extractors/recent_news_signals.py · extractors/signal_scoring.py · widgets news_signals_feed, news_relevance_summary
```
```
Stakeholder Map  (stakeholder_map)
├── Required data ........ prospect_contacts (EMPTY 0/220; Apollo_All_Contacts owed) · firmographics · technographics · intent · news · Rulebook + case studies (DEC-041)
├── Decision / logic ..... C01 F3 (20–30, score weights) · C28 v4 row (How to Open + HP Play Focus, 40–100 words, no score) · DEC-007 role coverage
├── Supporting reference . 04/Contacts_Apollo/README.md · CONFLICT X-05, S-01
├── Open questions ....... D8 contact file (BLOCKER) · D9 one file or two · D10 empty state · QA16-6/7/8
├── Known data gaps ...... contacts for 192/220 (Apollo, 26 Sep; 28 none) · no employment-status column anywhere
└── Code impact .......... extractors/stakeholder_map.py compute_stakeholder_score() · widgets stakeholder_*
```
```
Opportunity Map  (solution_narrative_opportunity_map)
├── Required data ........ firmographics · technographics · intent · news (trigger) · contacts · filings · Rulebook + case studies · PredictLeads products
├── Decision / logic ..... C01 F4 · DEC-034 drop 3 check tags, keep Priority C/H/M/L · C28 v4 evidence tiers · DEC-039/040 relevance · DEC-043 one primary route · DEC-033 3D route
├── Supporting reference . 02 Rulebook (v1) · _extraction_notes/B §2.1–2.4 · CONFLICT C-09, X-04, X-07, X-08
├── Open questions ....... D29/X-09 relevance build · D34 · D35 T0–T3 · D46 · D47 · QA16-3 · C-09 what computes Priority
├── Known data gaps ...... contacts 0/220 · filings PDFs · Rulebook FINAL missing
└── Code impact .......... extractors/solution_narrative_opportunity_map.py · hp/rulebook.py · hp/recommendations.py · widgets opportunity_*
```
```
Technographic Map  (tech_landscape)
├── Required data ........ Explorium 4_Technographics + 5_Tech_Breakdown/WebStack · PredictLeads technology_detections (ref) · hp_intent category scores · Rulebook matches · Related Technologies (fallback, researched)
├── Decision / logic ..... C21 Tech Landscape Confidence FINAL (Driver 1 + Driver 2 → %) · C01 F5 status words · DEC-035 keep Risk labels · DEC-010 extra card dropped · DEC-019 sources
├── Supporting reference . _extraction_notes/B §2.7 · CONFLICT C-03, C-04, X-10
├── Open questions ....... D37 risk logic approval · E23-3 "Contextual" tag · C-03 WXP card vs v4 K3 · QA16-11 unmapped technologies · D22 Related Technologies
├── Known data gaps ...... technographics 207/220 · 47 unclaimed detection rows · no detectedVia / first-seen
└── Code impact .......... extractors/tech_landscape.py · hp/tech_confidence.py · hp/recommendations.py · widgets technographic_map, tech_stack_matrix, tech_detections_reference, webstack_breakdown, technographic_hp_recommendations
```
```
Objection Playbook  (objection_playbook)
├── Required data ........ technographics (incumbents) · firmographics · contacts (topic owner) · Rulebook + case studies (proof per area card)
├── Decision / logic ..... C01 F6 (5–10, three-tier order, no score) · DEC-041 · DEC-049 "Could be raised by" wording (internal) · no v4 row → D44 default
├── Supporting reference . I01 Rules doc §7 (internal) · _extraction_notes/A §2.6
├── Open questions ....... D44 · QA16-1/2 · D47 tier gate on proof
├── Known data gaps ...... contacts 0/220 · Rulebook FINAL missing
└── Code impact .......... extractors/objection_playbook.py (_resolve_likely_raiser) · widgets objection_incumbent_context, objection_reframe_cards
```
```
Content Studio  (content_studio)
├── Required data ........ contacts (persona) or job_openings (role proxy) · firmographics · HP decks (C02 rules) · Rulebook · case-study proof per asset
├── Decision / logic ..... C01 F7 (formats & word limits) · DEC-004 human-in-the-loop co-creation + deck rules/guardrails (C02) · no v4 row → D44
├── Supporting reference . 02 HP_220_Account_Platform_additional data · 08 HP_Product_Decks · _extraction_notes/A §2.7, §3
├── Open questions ....... D44 · D8 · QA16-10 regeneration cost
├── Known data gaps ...... contacts 0/220 · jobs missing 45 · Desktop deck folder possibly incomplete
└── Code impact .......... extractors/content_studio.py (generate_content_asset, suggest_content_angles) · widgets content_*
```
```
Strategy Chat  (strategy_chat)
├── Required data ........ full account snapshot (9 dataset keys) · filings · Rulebook
├── Decision / logic ..... C01 F8 (evidence order, no numeric score) · C26 mapping · no v4 row → D44 · internal: answers deferred to Step 8 RAG
├── Supporting reference . _extraction_notes/A §2.8
├── Open questions ....... D44 · QA16-9 citations/uncertainty state · D11/D12 filings ingestion
├── Known data gaps ...... feature not answering yet · filings PDFs not ingested
└── Code impact .......... extractors/strategy_chat.py · widgets strategy_snapshot_context, strategy_chat_interface
```
```
Message Evaluator  (message_evaluator)
├── Required data ........ contacts (persona) or job_openings (proxy) · the draft message
├── Decision / logic ..... C01 F9 (four objective formulas, 0–100) · no v4 row → D44
├── Supporting reference . _extraction_notes/A §2.9
├── Open questions ....... D44 · D8
├── Known data gaps ...... contacts 0/220 · readiness "none" for 44 accounts
└── Code impact .......... extractors/message_evaluator.py · evaluator/scoring.py · widgets evaluator_*
```
```
Content Messaging  (content_messaging)
├── Required data ........ firmographics · technographics · intent · news · filings · Rulebook + case studies
├── Decision / logic ..... C01 F15 (3–5 pillars) · C28 v4 row (pillars on separate evidence, word limits) · Rulebook C 06 · internal: unsourced proof deleted, "n/m sourced" badge
├── Supporting reference . _extraction_notes/A §2.10
├── Open questions ....... QA16-4 CM-15 · D29 relevance
├── Known data gaps ...... filings PDFs
└── Code impact .......... extractors/content_messaging.py · messaging/pillars.py · widgets messaging_*
```
```
Intent & Demand Signals  (intent_demand_signals)
├── Required data ........ hp_category_intent (hp_intent_results 2.xlsx) · Explorium 11_intent_score + 10_Intent_Topics · job_openings · technographics + webstack
├── Decision / logic ..... DEC-012 category score primary (3 Sep) · C01 F10 (Max/Average/Trend, no cross-provider formula) · C28 v4 row · INT-01 four-step flow + noisy-keyword rule (internal)
├── Supporting reference . 04/HP_Intent/README.md · _extraction_notes/A §2.11
├── Open questions ....... I-07 noisy-keyword provenance · D22 Related Technologies · D45 · S-06/C-01 recognised streams
├── Known data gaps ...... intent 173/220 · NSW Education file missing · Level Of Intent empty
└── Code impact .......... extractors/intent_demand_signals.py · hp/intent_topic_map.py · widgets intent_*
```

Not a feature but in scope: **Reporting & Usage Analytics** (DEC-004, C02 §"Additional Module": events to log, 18 example questions, dashboard + "Ask Reporting") — no feature key, no status recorded anywhere after 24 Aug. Sahaj re-raised "an analytics component" on 15 Sep.
