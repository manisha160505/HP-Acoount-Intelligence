# Filings: what the client told us, what we hold, and how to get the documents

**Date:** 25 September 2026 · **Status:** internal plan, nothing here is client-approved beyond the quoted answers.
**Sources:** the HP 220 Gmail thread (messages of 15, 17, 18, 23, 24 and 25 Sep), `00_INDEX/DECISION_LOG.md` (DEC-025, DEC-026, DEC-054f), `05_Questions_and_Clarifications/Answered/ANSWERED_QUESTIONS.md` (D11–D15), `04_Data_and_Source_Definitions/Filings/`, `filings 1.csv`, the PredictLeads `sec_filings` sheet, the current split (`220 account split csv/`), and a code trace of `hp-backend/src/app/services/retrieval/{corpus,pdf,financials}.py`.

---

## 1. What the client has already decided (verbatim)

| Date | Who | Instruction | Where recorded |
|---|---|---|---|
| 15 Sep | Dhruvi (minutes) | "Pritesh → crawl stock-exchange filings for the last 12 months (latest four quarters) from IR sites and national exchanges" | EMAIL_TIMELINE l.39 |
| 17 Sep 17:29 UTC | Dhruvi | "Account Filings Data - We have 184 of the 220 APAC accounts (83.6%), with the file including the status, source page url, document url wherever applicable and documented reasons for the remaining 35 accounts." Attachment: `filings 1.csv` | Gmail |
| 18 Sep 05:51 UTC | Dhruvi | "Sharing the completed data files available as of now: https://drive.google.com/drive/folders/1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25" | Gmail (not in the docs) |
| 18 Sep 07:28 UTC | Dhruvi | "Please use document_url where available and source_page_url as the fallback. Do not use local_path. Where both source URLs are blank, please exclude that record for now." | DEC-025 |
| 23 Sep 05:53 UTC | Dhruvi | "From the newly shared PredictLeads data, please use the SEC Filings data. This can be used together with the separate SEC/filings data already being used wherever applicable. You can ignore others which you asked." | DEC-026 |
| 24 Sep 14:43 UTC | Dhruvi (opens_2) | Item 11: "RESOLVED: use filings 1.csv plus PredictLeads SEC Filings, merged on domain but where the domain is same … pls use company name and country … and yes pls consider 'the file shows 186 unique company names'" plus the 31-account no-public-filings list. Item 12: "wherever it is not downloaded, or links fail: we skip that particular file, not the whole company"; documents are in Drive folder `1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP`. Item 13: "resolved: last 12 months". | DEC-025, D11–D13 |
| 25 Sep 05:50 UTC | Dhruvi (OPEN_v2) | C4: Fletcher → fletcherbuilding.com; Fonterra → fonterra.com; Astra/United Tractors row: "leave that row if it is not matching to astra". C5: Jabil Inc. 10-Q on both Jabil accounts "yes you can for now"; Hyundai DART rows → "HKMC GROUP(HYUNDAI AUTOEVER) – KR", hyundai-autoever.com. | DEC-054f |
| 25 Sep 12:02 UTC | Dhruvi | "Attached are the answers to your opens: clarifying_opens_3_UNRESOLVED_v2 and clarifying_opens_3_CLARIFICATIONS_v2." **These carry the answers to C1 (Agribank, VPBank, count reconciliation) and C5. The attachments are not on this machine yet.** | Gmail only |

The 31-account no-public-filings list (opens_2 item 11): Healthscope; Kementerian Pertahanan RI, PT Bank Central Asia, Yayasan Bina Nusantara, PT Tiara Marga Trakindo, Sinar Mas Group; Ministry of National Defense, National Intelligence Service (KR); Infineon Technologies (M), Ministry of Defence (MY); Beca, PwC (NZ); Department of Education, Department of National Defense, Ernst & Young, Philippine National Police, Supreme Court (PH); ITE, GovTech, Ministry of Defence, Education, Health, Home Affairs, Mediacorp, NTUC, OCBC (SG); Bank of Tokyo-Mitsubishi Bangkok Branch, Ministry of Defense (TH); Ministry of Defence, Finance, Public Security (VN).

---

## 2. What we hold today

**`filings 1.csv` (17 Sep).** 505 rows, 187 company names. 475 rows carry a `document_url`; 30 rows carry neither URL (15 companies: ASC, Bank Mandiri, PNM, Kuok, StarHub, Viettel, Agribank, VietinBank, VPBank, CIMB Group, Maybank, Public Bank, RHB, NCS, Danamon, Foodstuffs) and are excluded by the 18 Sep rule. Their `notes` column is empty, so the "documented reasons" of the 17 Sep mail are not in the file. `sha256` and `file_size` are present for the 474 downloaded rows, which lets us verify anything we obtain against Pritesh's copies. Country mix: JP 180, TH 65, KR 48, AU 43, MY 34, PH 34, ID 29, NZ 28, SG 25, VN 19.

**PredictLeads `sec_filings` (23 Sep workbook).** 121 rows for 12 accounts (10 each: Accenture, BHP, Concentrix, EXL, Jabil, Keysight Malaysia, KT Corp, MUFG, ORIX, SMFG, Sony, Westpac; MUFG's 11 rows fall on the shared mufg.jp domain). Form types 6-K 69, 8-K 37, 10-Q 13, 20-F 2; filed 3 Nov 2025 to 10 Sep 2026, so all inside a 12-month window. Every `source_url` is on sec.gov. **The `document` column holds the filing text itself**, capped by Excel at 32,767 characters (80 rows exceed 5,000 characters; the long 10-Q and 20-F texts are truncated). Six of the twelve accounts also appear among the index's 31 sec.gov rows (Accenture, Concentrix, EXL, Jabil, Keysight, KT), so the same filing can arrive twice.

**PDFs.** None on this machine. They exist in the client's Drive folders and on Pritesh's machine (`local_path` = `/Users/priteshhome/220-account/filings/<CC>/<company>/…pdf`, which the client told us never to use as a path). The Drive connector available here has no scope for either folder; both must be opened by hand.

**Split state (25 Sep 13:57 IST).** `compliance_filings/_filings_index.csv` written for 181 accounts (476 rows). Twelve rows sit in the wrong folder because the index's territory column is wrong: Fletcher's 4 under Sunway, Fonterra's 3 under UOB Malaysia, Astra's 3 dividend notices duplicated into Federal International Finance, VPBank's 2 under Vietnam Post. 29 rows unassigned. The client's re-keys are not applied yet.

**Pipeline.** No feature extractor reads filings. PDFs are read only by the retrieval layer for the Executive Dashboard index (`corpus._filing_documents` → `pdf.read_pdf` → `financials.document_claims` → strategic priorities and reported figures). The reader takes PDFs only, has no OCR, and binds a figure only when it recognises unit and currency words in English or Indonesian. Uploading a PDF also regenerates five extractors that ignore it.

---

## 3. Coverage reconciliation

| | count |
|---|---:|
| Client: accounts with filings | 184 |
| Split: accounts with an attached index row | 181 |
| Split: accounts with none | 39 |
| …of which on the client's 31-name list | 31 (Bank of Tokyo-Mitsubishi Bangkok included) |
| …explained by mis-keying or name variants, recoverable | 5: Fletcher, Fonterra (misfiled); Bank Mandiri, BRI, UOB Singapore (unassigned rows under variant names) |
| …genuinely absent from both the file and the list | 3: ANZ Holdings NZ, CIMB Group Holdings, CIMB Niaga (plus Agribank and VPBank, already asked as C1) |

After the re-keys and aliases below, 186 accounts will hold at least one indexed document, which matches the client's "186 unique company names".

---

## 4. How to get the documents — three routes, run in this order

**Route A — the client's Drive folders (complete set, preferred).** Open `https://drive.google.com/drive/folders/1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP` (named for the filings in opens_2 item 12) and `…/folders/1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25` (the 18 Sep data drop) in a browser, download as a zip, unpack into `project-documentation/04_Data_and_Source_Definitions/Filings/pdfs/`. A small script then places each PDF into the right account's `compliance_filings/` by matching its sha256 against the index (474 rows have one), and reports any file that matches no row. This is the only route that yields the 125 documents Pritesh converted from EDGAR HTML, DART and PSE viewer pages, and from the hosts that block bots.

**Route B — self-download from `document_url` (fallback, partial).** Tested one URL per host on 25 Sep: 350 of the 475 URL rows are direct PDFs on hosts that answer (EDINET links carry tokens valid to 2036). 125 rows are not fetchable as PDFs: sec.gov serves HTML (31), DART and PSE Edge serve viewer pages (43), OpenDART serves JSON statements (14), nine hosts return 403 to scripts (BHP, IAG, Sony, ASB, NZX, SA Education, Bursa, IDX, KWSP; 27 rows), and Qantas, Bangkok Bank and Singapore Airlines fail (5). Script rules: identify with a contact user-agent, one request per second per host, verify sha256 against the index, record every failure per file, never fail the company (DEC-025).

**Route C — the PredictLeads SEC filing text (immediate, 12 accounts).** The 121 rows already contain the filing text. Two ways to use them: render each row's text to a PDF and upload it under `compliance_filings` (works with today's reader, no code change), or extend `_filing_documents` to accept `.txt` (cleaner, small change). Either way, dedupe against the index by the EDGAR accession number embedded in both URLs (e.g. `000162828026046138`) so a 10-Q is not indexed twice. Where a text is truncated at 32,767 characters, prefer the PDF from Route A or B when it exists.

---

## 5. Keying rules to implement in the split

| rule | source | action in `assign_filings()` |
|---|---|---|
| Fletcher Building rows → FLETCHER_BUILDING_HOLDINGS_LIMITED (fletcherbuilding.com) | DEC-054f | explicit re-key table keyed on `company` + `sales_territory_name` |
| Fonterra rows → FONTERRA_CO_OPERATIVE_GROUP_LIMITED (fonterra.com) | DEC-054f | same |
| Astra rows under fifgroup.co.id → PT_ASTRA_INTERNATIONAL_TBK; drop the duplicates already on Astra; exclude the United Tractors row | DEC-054f | same, with a "excluded" reason written to `_unassigned_filings.csv` |
| VPBank rows under "VIETNAM POST CORPORATION" → VIETNAM_PROSPERITY_JOINT_STOCK_COMMERCIAL_BANK | pending C1 answer (in the 12:02 attachment) | same, once confirmed |
| Jabil Inc. 10-Q rows on both Jabil accounts; Hyundai DART rows on HKMC Group | DEC-054f | already the case; add a test so it stays so |
| Name variants: "BDO Unibank, Inc." → BANCO_DE_ORO_UNIBANK_INC_BDO; "United Overseas Bank Limited - SG" → UNITED_OVERSEAS_BANK_LIMITED_UOB; "Singapore Airlines Limited" → SINGAPORE_AIRLINES; "Spark New Zealand Limited" → SPARK_NEW_ZEALAND; "Bank Rakyat Indonesia (BRI)" → PT_BANK_RAKYAT_INDONESIA_PERSERO; "NIPPON EXPRESS HOLDINGS, INC." → NIPPON_EXPRESS_CO_LTD; "Bank Mandiri" (blank territory) → PT_BANK_MANDIRI_PERSERO | our proposal, needs Yogesh's approval | alias table |
| "PT Bank Mandiri (Persero) Tbk" rows carrying a Bank Central Asia territory | client, 26 Sep (DEC-058e) | **done:** filed under PT_BANK_MANDIRI_PERSERO via FILINGS_CLIENT_RULINGS |
| Group-level entries (Mitsubishi keiretsu, Astra International Group, UOB Group, CIMB Group, Aboitiz, Universal Robina) | no matching account | stay unassigned, listed in `_unassigned_filings.csv` |
| Shared domains (jabil.com, mufg.jp) | DEC-025 "where the domain is same … use company name and country" | territory name decides; already implemented |
| PredictLeads `sec_filings` | DEC-025/026 | attach by domain, then name + country for jabil.com and mufg.jp; give it a dataset slot (`sec_filings_text`) or fold into `compliance_filings` after Route C |

---

## 6. Window and document selection

The client's rule is "last 12 months". The index has `period_end` on only 223 rows, `publication_date` on 474 and `fiscal_year` on 474. Proposed order of precedence: `period_end` ≥ 2025-09-25; else `publication_date` ≥ 2025-09-25; else `fiscal_year` ≥ 2025. That keeps about 394 of the 475 URL rows for 157 accounts and drops the 2021–2024 statements. Document types stay as delivered (interim, annual, quarterly, statutory); the reader takes its period from the tables inside each document, not from the filename. All 121 PredictLeads filings fall inside the window.

---

## 7. Constraints in the pipeline to respect

- **Only the Executive Dashboard index consumes filings.** Set the upload not to regenerate the five extractors that declare `compliance_filings` (they never read it); let the index job run.
- **Reader limits.** PDF only, no OCR (image-only pages are excluded), figures bound only with English or Indonesian unit and currency words. 312 of the 505 index rows are Japanese, Thai, Korean or Vietnamese documents, so expect narrative pages but few reported figures for those accounts. Test one EDINET, one SET and one scanned PSE document before bulk ingestion.
- **Size.** 1.5 GB in total, seven files over 20 MB, largest 146 MB. Local upload is fine; Cloud Run caps requests at 32 MB, so those seven need a different path later.
- **Cost.** Astra's index alone holds about a thousand cached LLM responses. Load five accounts first, measure, then set a per-account document cap.

---

## 8. Still open with the client

1. **C1 — Agribank and VPBank**, and the 184 / 186 / 192 count reconciliation: answered in the 25 Sep 12:02 UTC attachments, which must be downloaded from Gmail and read.
2. ~~ANZ Holdings NZ, CIMB Group Holdings, CIMB Niaga~~ — **answered 26 Sep 03:26 UTC** with six URLs, now `Filings/filings_client_supplement_2026-09-26.csv` (DEC-058d). All six placed (CIMB Niaga downloaded by hand, via Filings/pdfs/_manual/).
3. ~~Bank Mandiri vs Bank Central Asia~~ — **answered 26 Sep**: Bank Mandiri (DEC-058e); applied as FILINGS_CLIENT_RULINGS in the split. Both PDFs downloaded by hand and placed; sha256 matches the index.
4. **Products sheet feature list** exists only in the 23 Sep screenshot (attached again on 25 Sep as `Screenshot 2026-09-23 at 5.23.22 PM.png`): download and transcribe.

---

## 9. Action list

| # | action | owner | depends on |
|---|---|---|---|
| 1 | Download the two 25 Sep attachments (`clarifying_opens_3_CLARIFICATIONS.docx`, `clarifying_opens_3_UNRESOLVED_v2.docx`) and the 23 Sep screenshot from Gmail; file under `01_Client_Provided/Client_Answers/`; ingest answers into the decision log | Yogesh | — |
| 2 | Open both Drive folders, download the filings as a zip into `04_Data_and_Source_Definitions/Filings/pdfs/` | Yogesh | Drive access in a browser |
| 3 | Write `scripts/place_filings.py`: match PDFs to index rows by sha256, copy into `<account>/compliance_filings/`, write a placement report | Claude | 2 |
| 4 | Write `scripts/fetch_filings.py` for Route B with sha256 verification and per-file failure log (fallback if 2 stalls) | Claude | — |
| 5 | Add the re-key table and alias table to `assign_filings()`, plus a test that Jabil and HKMC stay as decided; re-run the split | Claude | approval of the aliases; C1 answer for VPBank |
| 6 | Render or ingest the 121 PredictLeads filing texts; dedupe by accession number | Claude | decision: render to PDF vs `.txt` reader |
| 7 | Implement the 12-month selection in the upload plan (`--filings-window`) | Claude | agreement on the precedence in §6 |
| 8 | Stop filings uploads from regenerating the five extractors; keep the index job | Claude | — |
| 9 | Reader test on one EDINET, one SET, one scanned PSE document; record what text and claims come out | Claude | 2 or 4 |
| 10 | Load five accounts with filings, measure index cost and time, set the document cap | Claude + Manisha | 3–9 |
