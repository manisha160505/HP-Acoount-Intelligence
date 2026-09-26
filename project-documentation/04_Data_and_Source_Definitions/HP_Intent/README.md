# HP category intent (hp_intent_results)

| Field | Value |
|---|---|
| What it contains | `hp_intent_results 2.xlsx`: sheet "Intent Data (Wide)" (two header rows; per account: Run Date, Top HP Category, Top Intent Score, then for each of PCs / Workstations / Poly / Printers / 3D Printers: Intent Score /100, Intent Trend, Buying Stage, Research Volume, Topics Researched, Keywords Matched, Related Technologies, First/Latest Intent Date, Geo Source) and sheet "API Report" (tool metadata). Seed export of 3 Sep: `seed_3Sep/hp_intent_results(Intent Data (Wide)).csv` + PDF print. |
| Who provided it | Konika Thakur / Dhruvi Patel (BridgeAI). Derived by the client from job-posting and news keyword matches (hence low scores for some accounts). |
| Where it came from | SharePoint (3 Sep, Astra); Drive folder 1eZvNHHKo… (18 Sep, 220 accounts). NSW Education intent added to Drive 23 Sep: `NSW_Education_Public_Intent.xlsx` (C33, copied here; also in `220 account data /`). |
| Accounts covered | 173 of 220 populated (client: genuine no-data). |
| Features using it | Intent & Demand Signals (primary score per category — DEC-012), urgency driver 4 (HP Solution Intent), Technographic Map Driver 2 (category intent support), Related Technologies as technographic fallback (researched, not detected — D22). |
| Known gaps | 47 accounts without scores; NSW Education now supplied by C33 as public-source estimates (not measured intent); the split uses it in place of the main file's "Unavailable" row. |
| Data-quality issues | Windows-1252 encoding, two header rows (contract note); scores rest on keyword matches, some noisy ("SLA", "identified as competitor of") — the noisy-keyword rule is INTERNAL and its provenance disputed (CONFLICT I-07). |
| Authoritative or supporting | **Authoritative** for the HP category score (primary intent signal). Explorium 11_intent_score (Bombora) is the supporting-topic layer. |
