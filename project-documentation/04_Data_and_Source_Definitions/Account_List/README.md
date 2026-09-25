# Account list

| Field | Value |
|---|---|
| What it contains | `APAC_Account_Parent_Child_Mapping.xlsx`: Master List (226 rows = 220 accounts + legend; Cty, Sales Territory Name, Global Parent / Group, Account Type, Merge Group ID, Notes), Parent-Child Groups, Recommended Merges. |
| Who provided it | Dhruvi Patel (22 Aug 2026). |
| Rules | Column B "Sales Territory Name" defines the 220 accounts (DEC-002). Names carry a " - XX" country suffix that disambiguates duplicates (3 Ministries of Defence, 2 Westpacs). "never merge across countries" for sovereign entities. |
| Domains | **`PredictLeads_219_Account_Domain_Audit.xlsx`** (Dhruvi, 25 Sep 2026; C43), sheet **"219 Account Audit"** only (ignore "Problems Only" and "Summary"): columns # / Master Company (B = dashboard display name) / Country / **Master Domain (D = canonical domain)** / PredictLeads Company / PredictLeads Domain / Domain Check (MATCH ×219) / considerations to keep in mind (H: "OK" ×204, "consider both names same" ×13, blank ×2). 219 rows — PT Astra International is absent (its data is the separate seed delivery; domain astra.co.id). Shared domains kept: jabil.com ×2, mufg.jp ×2. Differences vs the 25 Sep split: Posco (posco.com), Pilipinas Shell (shell.com.ph), Public Bank (pbebank.com) — applied 25 Sep: `scripts/split_account_data.py` reads this sheet as its domain source and `_ACCOUNTS.csv` carries its columns as `audit_*`. |
| Authoritative or supporting | Authoritative for scope and names. |
