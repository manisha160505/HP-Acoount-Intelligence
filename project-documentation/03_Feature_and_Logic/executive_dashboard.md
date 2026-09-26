# Executive Dashboard (`executive_dashboard`)

Requirements section: Feature 1 — Executive Dashboard (ABX v3 L32–41). UI label from NORTHSTAR_SIDEBAR_GROUPS; feature key from WIDGET_REGISTRY.

## Required data
Firmographics + hierarchy (Explorium 1_Firmographics, 2_Company_Hierarchy); filings 1.csv + PredictLeads sec_filings (financials, strategic priorities); job_openings (hiring velocity); contacts (top stakeholders); technographics + intent (reused from Tech Landscape and Intent & Demand); Google News RSS + Exa (top signals).

## Decision / logic documents (read these before changing the feature)
- C01 HP_ABX_v3_final F1: company profile; "3-5 years of financial metrics"; "3-5 strategic priorities" with evidence score 40/25/20/15; urgency with "five named drivers" (superseded).
- C09 HP_Urgency_Score_Updated_Final + 16 Sep email: **4 drivers 20/25/30/25; 60% weighted-coverage minimum; blank+closed jobs within 12 months count; score scales** (DEC-030). Fleet Refresh excluded (DEC-031).
- C28 Recommendation Tuning Logic v4: Executive Dashboard row (recommendation prose, word limit); data_as_of_date.
- DEC-018 hierarchy (Explorium sheet; blank parent ignored; say nothing when absent). DEC-017 entity scope (APAC entity, partially resolved). DEC-025 filings method and 12-month window.
- C26 file explanation: filings 1.csv, Rulebook and case studies feed this feature.

## Supporting reference
- 08_Reference_Material/Astra_Seed_Account (annual reports) as the worked example
- _extraction_notes/B_scoring_and_rulebook.md §2.5 (urgency rule register)

## Open questions
- D2 entity scope (bare RESOLVED)
- D11/D14 filings reconciliation (Agribank, VPBank, Fletcher, Fonterra, Astra/FIF, Jabil Inc., Hyundai DART)
- D27 blank job status meaning (drives 30% weight)
- D41 as-of date
- C-07/C-08 urgency arithmetic and band gaps
- S-05 3-5 years of financials come only from filings — extraction of figures from PDFs not yet built (PDFs placed for 137 accounts by fetch_filings.py on 26 Sep; not yet ingested)

## Known data gaps
- compliance_filings: index only; PDFs not local; 31 accounts have no public filings
- Hierarchy sheet present for 165/220
- Contacts 192/220 (Apollo, 26 Sep; 28 accounts none) (top-stakeholder tile)
- Job openings missing for 45 accounts (hiring velocity; urgency driver 3)
- One firmographics row per account → no growth comparison (Expansion proxy)

## Code touched
- `hp-backend/src/app/services/extractors/executive_dashboard.py`
- `hp-backend/src/app/services/dashboard/urgency.py compute_urgency_score()`
- `hp-backend/src/app/services/dashboard/priorities.py`
- `widgets: exec_summary_card, exec_key_metrics, exec_hiring_velocity, exec_urgency_score, exec_strategic_priorities`

Classification key: statements prefixed with a C-id or DEC-id are CLIENT DECISIONS / CLIENT DATA; "internal" or INT-id = INTERNAL IMPLEMENTATION DECISION; D-ids and X-/C-/I- ids are OPEN QUESTIONS or CONFLICTS in `00_INDEX/`. Full decision text: `00_INDEX/DECISION_LOG.md`.
