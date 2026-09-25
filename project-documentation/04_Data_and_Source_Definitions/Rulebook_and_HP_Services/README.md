# Rulebook and HP services / solutions material

The Rulebook is a decision document, so it lives in `02_Decision_Maker/` (and `01_Client_Provided/Logic_and_Scoring/`). The HP source materials it was built from (Care Pack definitions, Q426 SKU list, Wolf Security deck, HP IQ deck, Lifecycle file, Print PDFs, DEX ROI / WXP web pages) are reference only — "Not used separately - included in Combined HP Rulebook" — and live in `08_Reference_Material/HP_Services_and_Solutions/`.

| Field | Value |
|---|---|
| Versions | v1 17 Sep (local); FINAL 23 Sep with Print rules highlighted yellow (**not on this machine**). |
| Structure (v1) | Part A hardware rules 1–18; Part B services & solutions (WXP 01–13, CARE 01–20, LIFE, DEPLOY 01–15, POLY 01–05, PRINT 01–03, SCAN 01–03, IQ 01–12, WOLF 01–20); Part C guardrails (C 01–10, product-specific, service G 06–18, country restriction lists). Numbering gaps in the local extraction: LIFE 04; product guardrails 1, 6, 8, 9, 11–14; G 01–05, G 16. |
| Rules that cannot fire on current data | Care Pack seat-count thresholds (250 / 1,000 / 5,000), WXP tier, print licences, scan credits, Poly premium tier — "pending HP input" items are to be ignored; employee range used as the proxy (DEC-045; thresholds unconfirmed). |
| Lifecycle | Client: not used; v4 §J: check PE/EM dates; columns unclear (C-05, D38). |
| Authoritative or supporting | **Authoritative for HP facts**; supporting for recommendations (never creates an account need). |
