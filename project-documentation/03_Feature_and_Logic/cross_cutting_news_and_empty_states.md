# Cross-cutting: news feeds, empty states, labels, as-of date

**News (CLIENT DECISIONS):** two feeds merged (RSS + Exa), identical 14-column schema; disagreeing same-event rows skipped, never the company; undated and 1970-01-01 rows skipped pending the client's re-crawl; 12-month window; no 20-signal cap; the feeds' Low/High relevance columns are not used; HTML stripped on ingest; corrupted cells shown as delivered; score /10 per the Live Signal logic, no tiers, no minimum. (DEC-020 … DEC-024, DEC-032)

**News (INTERNAL, unconfirmed):** "same event" = same account (domain + name + country) + same event date + normalised-headline match (356 duplicates removed); disagreement = same event with different amount / counterparty / date. Rules-doc heuristic (≥ 0.85 similarity) is older and unreviewed. (X-02, D16)

**Empty states:** only client rule is hierarchy → say nothing (DEC-018). General rule OPEN (D39); Stakeholder Map with no contacts OPEN (D10). Two internal documents propose opposite defaults (I-01); the sent round-3 default is "show with a message".

**Source labels:** OPEN (D40). Proposed: Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study; publisher name on news cards; no vendor names. Exa vs Google News label UNRESOLVED (D18).

**As-of date:** OPEN (D41). v4 says ingestion date; proposal = date of the final consolidated drop, once per account; per-dataset retrieval dates kept in the record. Recency anchor conflict C-02.
