# Cross-cutting: entity and domain matching

**CLIENT DECISIONS** (DEC-013, DEC-014, DEC-015, DEC-016, DEC-018)
- Vendors fetch by Company Name + Country (Explorium business id; PredictLeads); the domain is a *result*, not the key. Differing domains across vendors do not mean a wrong company.
- Final account-level mapping: PredictLeads domains are canonical; four overrides (Posco → posco.com, Pilipinas Shell → shell.com.ph, Shiseido → corp.shiseido.com, Stanley Electric → stanley.co.jp); fallback Company Name + Country where the domain is ambiguous.
- Never key on vendor record ids.
- Shared domains: Jabil MY/SG and MUFG JP/Bangkok stay separate accounts; disambiguate with Company Name + Country — columns to be populated by the client (OPEN).
- Blank domains: Westpac = westpac.com.au; Public Bank = pbebank.com (UNRESOLVED — see 06/04).
- Hierarchy: Explorium Company Hierarchy sheet; blank parent ignored; nothing shown when absent.

**INTERNAL ASSUMPTIONS in the 25 Sep split** (`07_Internal_Generated/Derived_Data/_CORRECTIONS.txt`): Public Bank derived as publicbankgroup.com (conflicts with "held"); two aliases rewritten toward Explorium domains (direction conflicts with "PredictLeads canonical"); Jabil SG / MUFG Bangkok get no domain-keyed rows; Astra datasets incl. contacts filled from the seed. See CONFLICT_REGISTER I-02, I-03, I-09.

**OPEN:** one authoritative domain per account (D1); Name + Country columns (D3); Public Bank rows (D4/D6).
