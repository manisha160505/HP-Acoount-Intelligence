# PredictLeads (Source B)

| Field | Value |
|---|---|
| What it contains | `predictleads_combined_219_accounts.xlsx`: company (220 rows), extended_company, job_openings (14,965), technology_detections (17,799), news_events (14,289), financing_events (74), connections (19,583), subpages (15,163), products (2,246), similar_companies (1,010), sec_filings (121), accounts, github_repositories (empty), dataset_status, Data7/Data8 differences, quality_changes (490), review_records (9), comparison. |
| Who provided it | Dhruvi Patel (BridgeAI). Vendor: PredictLeads. |
| Where it came from | Google Drive folder 1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25, hiring data added 18 Sep 13:32 UTC. Local: `220 account data /predictleads_combined_219_accounts.xlsx`. Seed: `PredictLeads/seed_Astra/job_openings.csv` (Astra, from the 31 Aug "Source B.xlsx" not on this machine). |
| Accounts covered | 219 + Astra from the seed (D23). Job openings missing for **45 accounts** (client: genuine no-data; will be aggregated from another tool — OPEN D22). Tech detections 216/220; news events 213/220. |
| Features using it | job_openings → Executive Dashboard hiring velocity, urgency driver 3, Intent & Demand hiring demand, Content Studio / Message Evaluator role-proxy persona. technology_detections → Technographic Map (reference). news_events → Live Signals, Opportunity Map triggers, Content Messaging. sec_filings → filings (with filings 1.csv). products → recommendations (features per the 23 Sep screenshot, not on file). extended_company.social_stats → urgency workforce growth proxy. |
| Known gaps | Contacts: none (no endpoint). input_company_name / input_country_code populated on 384 of 14,965 job rows only (D3). |
| Data-quality issues | 9 vendor-flagged rows (review_records) — drop pending (D25). 490 corrections already applied (D26, verified). Duplicate ids (technology_detections 715, news_events 68 …) — do not key on ids (D24). Job status: blank or closed only in the seed (D27). |
| Authoritative or supporting | **Authoritative** for hiring; **supporting** for technographics ("shown for reference only"); news_events is the add-on layer to RSS + Exa; sec_filings authoritative alongside filings 1.csv. Twelve sheets have no consumer and are removed from the upload contract (DEC-026). |

Domain: the 25 Sep audit workbook `PredictLeads_219_Account_Domain_Audit.xlsx` (in `Account_List/`, not yet downloaded) is now the canonical domain source (DEC-052); the earlier rule "PredictLeads domain canonical + four overrides" (DEC-013) is the interim state until then.
