# Filings (stock-exchange / annual-report index)

| Field | Value |
|---|---|
| What it contains | `filings 1.csv`: 505 rows, 187 unique company names; columns include row_id, company, country, domain, global_parent, document_title, document_type, reporting_period, publication_date, source_type, source_page_url, document_url, local_path, validation_status, confidence, notes. Plus PredictLeads `sec_filings` (121 rows). The documents themselves are in a Drive folder (1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP) and on Pritesh's machine — **not local**. |
| Who provided it | Dhruvi Patel; crawled by Pritesh (BridgeAI) per the 15 Sep action (last 12 months / four quarters, IR sites + national exchanges). |
| Where it came from | Email 17 Sep 17:29 UTC (C19). Local: `NewDocs/filings 1.csv`. |
| Accounts covered | Client: 184 of 220 (83.6%); file: 186/187 unique names; 31 accounts listed by the client as having no public filings; Agribank and VPBank on neither list (D11). |
| Features using it | Executive Dashboard (financials, strategic priorities), Live Signals, Opportunity Map, Content Messaging, Strategy Chat (client mapping 18 Sep). |
| Known gaps | compliance_filings is 0/220 in the split (PDFs not ingested; 29 index rows unassigned, 2 conflicts). |
| Data-quality issues | Fletcher (NZ) rows carry sunway.com.my; Fonterra (NZ) rows carry uob.com.my; Astra rows carry fifgroup.co.id plus a blank-domain row holding PT United Tractors statements; VPBank documents filed under "VIETNAM POST CORPORATION"; Jabil Inc. 10-Q rows keyed both SG and MY; Hyundai DART rows keyed hyundai-autoever.com; five non-220 companies present (ignored). |
| Rules | document_url first, source_page_url fallback, never local_path; exclude records with neither; merge with sec_filings on domain, name + country where the domain is shared; last 12 months; skip a failing file, not the company (DEC-025). |
| Authoritative or supporting | **Authoritative** for reported financial figures and strategic priorities. Supersedes the "Stock Exchange data" of 3 Sep. |
