# Derived: the 220-account split (INTERNAL, GENERATED)

Produced by `scripts/split_account_data.py` (validated by `scripts/validate_split_data.py`) from the vendor files above, on 25 Sep 2026 05:16 UTC, into `220 account split csv/` (gitignored). One folder per account with one CSV per dataset key (firmographics, company_hierarchy, technographics, webstack, intent_topics, intent_score, hp_category_intent, job_openings, technology_detections, news_events, news_events_additional, google_news, prospect_contacts, compliance_filings/_filings_index.csv …), a `reference/` folder for tables with no dataset key, `_READINESS.txt`, `_MISSING.txt`, `_manifest.json`, `_account.json`; plus `_RUN_SUMMARY.json`, `_CORRECTIONS.txt`, `_ACCOUNTS.csv`, `_READINESS.csv`, `_DATASET_USAGE.md` at the root.

- Row counts and unclaimed rows: see `07_Internal_Generated/Derived_Data/_RUN_SUMMARY.json`.
- **Every derived value** (blank domains, folder slugs, alias rewrites, seed fills) is listed in `_CORRECTIONS.txt` — these are INTERNAL ASSUMPTIONS, several of which conflict with the decision documents (CONFLICT I-02, I-03, I-09). Do not run the pipeline on the derived Public Bank domain.
- Readiness: tech_landscape complete for 205/220, intent_demand for 141; every other feature partial (contacts, filings); message_evaluator "none" for 44.
