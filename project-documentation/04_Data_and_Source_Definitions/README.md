# Data and source definitions

One folder per source. Each README states what the dataset contains, who provided it, where it came from, which accounts it covers, which features use it, known gaps, data-quality issues and whether it is authoritative or supporting. Small files are copied here; files above 6 MB are linked (`*.LINK.md` gives the local path and md5) — the originals of the linked files stay in `220 account data /`; everything that was in `docs/` and `NewDocs/` now lives only here.

| Folder | Source | Role |
|---|---|---|
| `Explorium/` | Explorium (Source A) — 220 workbooks + Astra seed | Authoritative: firmographics, hierarchy, technographics, Bombora topics |
| `PredictLeads/` | PredictLeads (Source B) — combined workbook + Astra seed | Authoritative: hiring, sec_filings; supporting: tech detections, news_events, products |
| `Exa/` | Exa.ai news | Authoritative (with RSS) |
| `Google_News_RSS/` | Google News RSS | Authoritative (with Exa) |
| `HP_Intent/` | hp_intent_results (HP category intent) | Authoritative: primary intent signal |
| `Filings/` | filings 1.csv (+ PredictLeads sec_filings; PDFs on Drive) | Authoritative: financials, priorities |
| `Case_Studies/` | hp_case_studies_final.csv | Supporting: proof points |
| `Contacts_Apollo/` | Apollo contacts — **not delivered for 220** | Would be authoritative for stakeholders |
| `Account_List/` | APAC_Account_Parent_Child_Mapping.xlsx | Authoritative: scope |
| `Rulebook_and_HP_Services/` | pointer to the Rulebook (02) and HP materials (08) | Authoritative for HP facts |
| `Derived_Split/` | the per-account split (internal, generated) | Working data; assumptions logged |
| `Other/` | seed PDFs, decks, POC links | Reference |

Column-level lineage (which column becomes which widget field) is in `07_Internal_Generated/Analysis/HP-Input-Data-Contract.md` and `hp-input-contract.json` (internal, living spec — note it is stale on the 20-signal cap and the removed dataset keys).
