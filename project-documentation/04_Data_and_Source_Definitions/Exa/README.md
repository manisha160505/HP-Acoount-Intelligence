# Exa.ai news feed

| Field | Value |
|---|---|
| What it contains | **Current (C46):** `exa_data (3)_2025-2026.xlsx`, one sheet, 3,726 rows × 14 columns, every row dated (2025-01-01 to 2026-10-19). Superseded (C22c, `_SUPERSEDED/`): `exa_data.xlsx`, 9,221 rows. Columns: company_name, website_domain, company_linkedin_url, news_announcements, event_headline, event_url, event_date, event_type, signal_categories, matched_keywords, event_summary, source_publisher, relevance_confidence, coverage_depth_events_per_account_last_12mo. Same schema as Google News RSS. |
| Who provided it | Dhruvi Patel (BridgeAI). Vendor: Exa.ai (fetched on the PredictLeads domain). |
| Where it came from | Drive folder 1eZvNHHKo…, re-dropped 25 Sep 2026 12:34 UTC ("use only this file going forward"). Local: `220 account data /exa_data (3)_2025-2026.xlsx` (10.8 MB, linked not copied). The 18 Sep file is in `220 account data /_superseded_2026-09-25/`. |
| Accounts covered | 215 of 220, all with at least one row in the 12 months to 25 Sep 2026 (2,929 rows). |
| Features using it | Live Signals (merged with RSS), Opportunity Map triggers, Content Messaging, urgency AI / growth events. |
| Known gaps | Re-crawl delivered 25 Sep (D17): every row now carries an event_date; undatable rows were left out of the file. **Last 12 months only** (client): 796 rows older than 25 Sep 2025 and 1 future-dated row (2026-10-19) must be filtered on ingest. Not a replacement for RSS (DEC-020). |
| Data-quality issues | 28 cells with replacement characters (Thai); 73 files with raw HTML (stripped on ingest); UTF-8 cannot be fixed at source (D21). |
| Authoritative or supporting | **Authoritative, jointly with Google News RSS**; on a same-event disagreement both rows are skipped (DEC-020). On-screen label unresolved (D18). |
