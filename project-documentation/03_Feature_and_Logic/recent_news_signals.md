# Live Signals (`recent_news_signals`)

Requirements section: Feature 2 — Recent News Signals (ABX v3 L43–52). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
google_news (Google News RSS + Exa merged; 14 identical columns) and news_events (PredictLeads). 12-month window. Filings per the 18 Sep mapping.

## Decision / logic documents (read these before changing the feature)
- C18 HP_Live_Signal_Scoring_Logic: **3 drivers Recency 0.30 / Relevance & Impact 0.50 / Source Reliability 0.20, score /10**; no-inference rule; strongest verified source on duplicates (DEC-032).
- DEC-020 merge both feeds; disagreeing same-event items skipped (opens_1 answer 6). DEC-021 undated / epoch rows skipped. DEC-023 12-month window, **no 20-signal cap**. DEC-024 do not use Low/High relevance columns. DEC-032 **no S/A/B/C tiers, no minimum score**.
- C01 ABX F2: 12–20 items, relevance 25/30/20/15/10, tie → newer (superseded by C18 for scoring; count rule overtaken by "no cap").
- C28 v4 Live Signals row: "Use relevant Rulebook offerings and case-study proof where they directly support the HP opportunity made timely by the news event" (relevance per DEC-040).

## Supporting reference
- _extraction_notes/B_scoring_and_rulebook.md §2.6
- CONFLICT_REGISTER C-01, C-02, C-11, C-12, X-01, X-02

## Open questions
- D16 same-event definition / precedence (with Sahaj)
- D17 Exa dates re-crawl (56% undated)
- D18 Exa label (unresolved)
- X-01 old events: show at 0/10 or exclude
- D45 case-study proof on this feature now or later

## Known data gaps
- Exa is the only source for ~119 accounts; 5,120 of 9,221 Exa rows undated
- Google News RSS covers 99 accounts only
- 28 corrupted (Thai) cells; 73 files with raw HTML (stripped on ingest)
- PredictLeads news_events: 38 unclaimed rows in the split

## Code touched
- `hp-backend/src/app/services/extractors/recent_news_signals.py (merge + de-dup)`
- `hp-backend/src/app/services/extractors/signal_scoring.py compute_relevance_score()`
- `widgets: news_signals_feed, news_relevance_summary`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
