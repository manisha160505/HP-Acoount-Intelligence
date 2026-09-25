# Files that could not be retrieved

Every file the email record proves exists but that has no copy anywhere on this machine (searched: the project folders, `~/Downloads`, the whole home directory by filename). The Gmail connector used to build this index can read messages but **cannot download attachments**; the Google Drive connector has **no scope** ("Insufficient scope" on every call); SharePoint has no connector at all. Each item therefore has to be downloaded by hand and dropped into the folder named in the last column, then its `.MISSING.md` placeholder deleted and `PROVENANCE_REGISTER.md` updated.

## A. Current decision documents that are missing (highest priority)

| Id | File | Sent by / when | Why it matters | Drop into |
|---|---|---|---|---|
| C44 | clarifying_opens_3_OPEN_v2.docx (client-annotated) | Dhruvi, 25 Sep 2026 05:50 UTC, message 1a0d71dc51f96712 | **The client's answers to all 25 open round-3 items.** Nothing in `05_Questions_and_Clarifications/Open/` can be closed until this is read. | `01_Client_Provided/Client_Answers/` (also `02_Decision_Maker/`) |
| C43 | PredictLeads_219_Account_Domain_Audit.xlsx | Dhruvi, 25 Sep 2026 05:50 UTC, same message | **The canonical domain per account** (sheet 219_Account_Domain_Audit; Column H same-account markers; Column B display name). Replaces every derived domain in the split. | `04_Data_and_Source_Definitions/Account_List/` (also `02_Decision_Maker/`) |
| C29 | HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook_FINAL_.docx | Dhruvi, 23 Sep 2026 05:53 UTC, thread 1a082bca2581fea0 | **The current Rulebook.** Adds the Print rules (highlighted yellow). The only local Rulebook is the 17 Sep v1; every later logic doc cites Rulebook rule ids that may have changed. | `01_Client_Provided/Logic_and_Scoring/` and `02_Decision_Maker/` |
| C27 | tests on current HP 220.docx | Dhruvi, 22 Sep 11:58 UTC | Client UI test observations and questions on the current build; never answered in writing. | `01_Client_Provided/Client_Reviews/` |
| C37 | HP_220_Refinements_Updated.docx | Dhruvi, 12 Sep 11:26 UTC, thread 1a0911ab27454237 | Client's screenshot review vs HP SEA Limited; the basis of the 16 Sep QA response. | `01_Client_Provided/Client_Reviews/` |
| C33 | NSW_Education_Public_intent (Drive folder 1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25) | Dhruvi, 23 Sep | Intent data for DEPARTMENT OF EDUCATION - NSW, AU; missing from hp_intent_results 2.xlsx. | `04_Data_and_Source_Definitions/HP_Intent/` |
| C38 | Filings PDFs (Drive folder 1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP) | Dhruvi, 24 Sep (opens_2 item 12) | The filing documents themselves; only the index (filings 1.csv) is local. ~1.5 GB, also on Pritesh's machine. | `04_Data_and_Source_Definitions/Filings/` (or keep external and record the path) |
| — | Apollo_All_Contacts (220-account contact file) | Never sent (Konika's 15 Sep action; "shortly" on 18 Sep; still open 25 Sep) | Blocks Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio, Message Evaluator for all 220 accounts. | `04_Data_and_Source_Definitions/Contacts_Apollo/` |

## B. Superseded or reference files that are missing (retrieve for completeness)

| Id | File | Sent by / when | Status |
|---|---|---|---|
| C08 | HP_220_Account_Recommendation_Logic(1).pptx | Dhruvi, 15 Sep 13:02 UTC | SUPERSEDED by v4 (23 Sep). Still referenced: round-3 item F4 relies on "slide 3" and "slide 5" of this deck. |
| C17 | HP_Tech_Landscape_Confidence_Scoring_Logic.docx (17 Sep) | Dhruvi, 17 Sep 17:29 UTC | SUPERSEDED by FINAL (18 Sep). |
| C10 | hp_case_studies_full.csv | Dhruvi, 16 Sep 13:39 UTC | SUPERSEDED by hp_case_studies_final.csv. |
| C23 | Hp lifecycle june 2026.xlsx | Dhruvi, 18 Sep 07:28 UTC | Unencrypted replacement for the encrypted Lifecycle file. Client says not used in the platform, but v4 section J and round-3 item F6 depend on reading its columns. |
| C24 | Wolf_Security_Portfolio_Recreated.pptx | Dhruvi, 18 Sep 07:28 UTC | Readable replacement for the encrypted deck. Content is folded into the Rulebook. |
| C25 | HP_IQ_for_Enterprise_Recreated.pptx | Dhruvi, 18 Sep 07:28 UTC | Readable replacement for the encrypted deck. Content is folded into the Rulebook. |
| C30–C32 | Original HP Ink Portfolio.pdf, HP Managed Print Portfolio 1.pdf, HP Document and Workflow Solutions Brochure.pdf | Dhruvi, 23 Sep 05:53 UTC | Print reference; content folded into Rulebook FINAL. |
| C05 | hp-sea-abm-dev-main.zip (Drive file 16WsfrKkdd6ITk3UCfVFcA-lQz0URXdHM) | Dhruvi, 22 Aug | HP Sea Limited POC codebase. Live POC still reachable at https://hp-sea-abm.vercel.app/. |
| C06/C07 | Any further decks in the Drive "Notebook" (1gbneD6Rri5ae2ml9Lq09PtM32Ba-z9jO) and "Desktop" (1BzoQcTnvu2kinEqnZWXcmVw9Hc7sHTEr) folders | Dhruvi, 24 Aug | 10 Notebook decks + 1 Desktop deck are local (downloaded 12 Sep). Whether the folders hold more is unknown. |
| C39a/c | hp_intent_results.xlsx and apollo_data.xlsx (3 Sep SharePoint) | Konika, 3 Sep | Only a CSV of one sheet / a PDF print exist locally. Superseded for intent; apollo_data is the Astra seed only. |
| C42a/b | Source B.xlsx, google_news_rss_data.xlsx (31 Aug) | Konika, 31 Aug (mail not in this mailbox) | Astra seed; superseded by the 220-account files. |
| — | Screenshots in the 23 Sep 12:33 message (Opportunity Map priority tags; PredictLeads Products feature list) and image.png of 24 Sep 14:43 (risk-label logic) | Dhruvi | The 23 Sep Products screenshot **defines which features consume the Products sheet** — that list is not written anywhere else. |
| — | NotebookLM notebooks "Account Intelligence Meeting 31-8-2026" and "Hp Harness" | Palash, 8 Sep | Delivery-side notes of the 31 Aug meeting; not exportable. |

## C. Files the client owes (not yet produced by anyone)
Contact file; Company Name + Country columns populated on every PredictLeads row; Public Bank Bhd rows for PredictLeads; re-crawled Exa event dates; job openings for the 45 accounts without them; corrected filings rows for Fletcher / Fonterra / Astra (FIF); filings for Agribank and VPBank (or confirmation they belong on the exclusion list); GCP project id / region; written feedback on HP-Account-Intelligence-Rules.docx (promised 10 Sep). See `06_Unresolved_and_Open/`.
