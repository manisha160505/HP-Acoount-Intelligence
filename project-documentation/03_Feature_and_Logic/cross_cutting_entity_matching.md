# Cross-cutting: entity and domain matching

**CLIENT DECISIONS** (DEC-052 — newest, DEC-013, DEC-014, DEC-015, DEC-016, DEC-018)
- **25 Sep:** `PredictLeads_219_Account_Domain_Audit.xlsx`, sheet `219_Account_Domain_Audit` only, is the canonical domain per account: "use the domain as the primary reference for data mapping". Column H: "OK" = vendor names similar; "Consider both names same" = different vendor names, same account — treat as one account. Column B = the account name shown on the dashboard (never a vendor's company name). **File received 25 Sep 12:30 IST.** Sheet is actually named "219 Account Audit"; 219 rows (Astra absent = seed delivery); Public Bank = pbebank.com with the Lao-named PredictLeads row accepted; Westpac NZ = westpac.co.nz; Pioneer stays global.pioneer. Three split domains must change (Posco, Pilipinas Shell, Public Bank). Filings re-keying from the same round: Fletcher fletcherbuilding.com, Fonterra fonterra.com, Hyundai DART rows → "HKMC GROUP(HYUNDAI AUTOEVER) – KR" / hyundai-autoever.com, Jabil Inc. 10-Q rows on both Jabil accounts (DEC-054f).
- Vendors fetch by Company Name + Country (Explorium business id; PredictLeads); the domain is a *result*, not the key. Differing domains across vendors do not mean a wrong company.
- Final account-level mapping: PredictLeads domains are canonical; four overrides (Posco → posco.com, Pilipinas Shell → shell.com.ph, Shiseido → corp.shiseido.com, Stanley Electric → stanley.co.jp); fallback Company Name + Country where the domain is ambiguous.
- Never key on vendor record ids.
- Shared domains: Jabil MY/SG and MUFG JP/Bangkok stay separate accounts; disambiguate with Company Name + Country — columns to be populated by the client (OPEN).
- Blank domains: Westpac = westpac.com.au; Public Bank = pbebank.com (RESOLVED 25 Sep by the audit sheet).
- Hierarchy: Explorium Company Hierarchy sheet; blank parent ignored; nothing shown when absent.

**INTERNAL ASSUMPTIONS in the 25 Sep split** (`07_Internal_Generated/Derived_Data/_CORRECTIONS.txt`): Public Bank derived as publicbankgroup.com (conflicts with "held"); two aliases rewritten toward Explorium domains (direction conflicts with "PredictLeads canonical"); Jabil SG / MUFG Bangkok get no domain-keyed rows; Astra datasets incl. contacts filled from the seed. See CONFLICT_REGISTER I-02, I-03, I-09.

**OPEN:** Name + Country columns on every PredictLeads row (D3, "will give that"). Resolved 25 Sep: canonical domains (D1), Public Bank (D4/D6).
