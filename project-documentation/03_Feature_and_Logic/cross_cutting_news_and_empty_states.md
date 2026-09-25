# Cross-cutting: news feeds, empty states, labels, as-of date

**News (CLIENT DECISIONS):** two feeds merged (RSS + Exa), identical 14-column schema; when the two disagree on the same event **keep the Exa row** (25 Sep, DEC-054a — replaces the 24 Sep "skip the item"); never skip the company; undated and 1970-01-01 rows skipped pending the client's re-crawl; 12-month window; no 20-signal cap; the feeds' Low/High relevance columns are not used; HTML stripped on ingest; corrupted cells shown as delivered; score /10 per the Live Signal logic, no tiers, no minimum. (DEC-020 … DEC-024, DEC-032)

**News (INTERNAL, unconfirmed):** "same event" = same account (domain + name + country) + same event date + normalised-headline match (356 duplicates removed); disagreement = same event with different amount / counterparty / date. Rules-doc heuristic (≥ 0.85 similarity) is older and unreviewed. (X-02, D16)

**Empty states (RESOLVED 25 Sep, provisional):** leave the section out and write nothing — for any missing dataset (G1) and for the Stakeholder Map with no contacts (B4); escalated to Sahaj, may be tweaked later (DEC-054b). The absent-dataset list per account goes into the run report.

**Source labels (RESOLVED 25 Sep, provisional):** our set applies — Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study; publisher name on news cards; no vendor names (DEC-054c). Exa origin kept in the record via an exa key.

**As-of date (RESOLVED 25 Sep):** show each dataset's own retrieval/ingestion date (DEC-054d); recency anchor = ingestion date (C-02 closed).
