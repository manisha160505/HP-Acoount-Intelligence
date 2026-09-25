# Exa.ai news feed

| Field | Value |
|---|---|
| What it contains | `exa_data.xlsx`, one sheet, 9,221 rows × 14 columns: company_name, website_domain, company_linkedin_url, news_announcements, event_headline, event_url, event_date, event_type, signal_categories, matched_keywords, event_summary, source_publisher, relevance_confidence, coverage_depth_events_per_account_last_12mo. Same schema as Google News RSS. |
| Who provided it | Dhruvi Patel (BridgeAI). Vendor: Exa.ai (fetched on the PredictLeads domain). |
| Where it came from | Drive folder 1eZvNHHKo… (18 Sep 2026). Local: `220 account data /exa_data.xlsx` (30 MB, linked not copied). |
| Accounts covered | 215 of 220; the only news source for ~119 accounts. |
| Features using it | Live Signals (merged with RSS), Opportunity Map triggers, Content Messaging, urgency AI / growth events. |
| Known gaps | **5,120 of 9,221 rows have no event_date** → skipped until the client's re-crawl (D17). Not a replacement for RSS (DEC-020). |
| Data-quality issues | 28 cells with replacement characters (Thai); 73 files with raw HTML (stripped on ingest); UTF-8 cannot be fixed at source (D21). |
| Authoritative or supporting | **Authoritative, jointly with Google News RSS**; on a same-event disagreement both rows are skipped (DEC-020). On-screen label unresolved (D18). |
