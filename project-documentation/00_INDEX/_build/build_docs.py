#!/usr/bin/env python3
"""Build project-documentation/ from a provenance manifest. Idempotent: re-run to refresh."""
import hashlib, json, os, shutil, sys, datetime
from pathlib import Path

ROOT = Path('/Users/yogeshyadav/Desktop/HP')
OUT = ROOT / 'project-documentation'
HOME = Path.home()
DL = HOME / 'Downloads'
COPY_LIMIT = 6 * 1024 * 1024   # files above this are linked, not copied

MAIN = 'Gmail thread "HP Account Based Intelligence (220 accounts)" (id 1a082bca2581fea0)'
SKIP = 'Gmail thread "Request to Skip Today\'s Meeting" (id 1a08a8571d30e41e)'
PROG = 'Gmail thread "Project Progress Update" (id 1a0911ab27454237)'
SP = "SharePoint (bridgeaipte-my.sharepoint.com, Konika Thakur's OneDrive) links in Konika's 3 Sep 2026 mail, quoted in " + MAIN
DRIVE_DATA = 'Google Drive folder 1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25 (Dhruvi, 18 Sep 2026 05:51 UTC, ' + MAIN + ')'

# Each entry: id, name (original filename), src (absolute path or None), dest (folder under OUT),
# origin, sender, channel, date, version, status, supersedes, superseded_by, used_for, notes, also (extra dest folders)
M = []
def add(**k):
    k.setdefault('src', None); k.setdefault('supersedes', ''); k.setdefault('superseded_by', '')
    k.setdefault('notes', ''); k.setdefault('also', []); k.setdefault('version', '')
    M.append(k)

# ---------------- CLIENT: requirements ----------------
add(id='C01', name='HP_ABX_v3_final.docx', src=ROOT/'docs/HP_ABX_v3_final.docx', dest='01_Client_Provided/Requirements',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 22 Aug 2026 14:53 IST (forwarded to Manisha 22 Aug, re-forwarded into thread 9 Sep 2026)',
    date='2026-08-22', version='v3 final', status='CURRENT',
    used_for='Master requirements and implementation guide for all 11 in-scope features: data required, sources, cleaning, rules and guardrails, build steps (Deterministic / Derived / LLM / RAG), fallbacks, required outputs.',
    also=['02_Decision_Maker'])
add(id='C02', name='HP_220_Account_Platform_additional data.docx', src=ROOT/'docs/HP_220_Account_Platform_additional data (1).docx', dest='01_Client_Provided/Requirements',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 24 Aug 2026 14:33 IST (forwarded into thread 9 Sep 2026)',
    date='2026-08-24', version='1', status='CURRENT',
    used_for='HP product-deck usage / RAG rules, Reporting & Usage Analytics module requirements, human-in-the-loop / co-creation rule.',
    notes='Local copy carries a "(1)" suffix from download; content is the emailed file.', also=['02_Decision_Maker'])
add(id='C03', name='APAC_Account_Parent_Child_Mapping.xlsx', src=ROOT/'docs/APAC_Account_Parent_Child_Mapping.xlsx', dest='01_Client_Provided/Requirements',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 22 Aug 2026 (forwarded into thread 9 Sep 2026)',
    date='2026-08-22', version='1', status='CURRENT',
    used_for='Scope: the 220 accounts (sheet "Master List", column B "Sales Territory Name"), parent/child groups and recommended merges. Used by the 220-account split and every per-account run.',
    also=['02_Decision_Maker','04_Data_and_Source_Definitions/Account_List'])
add(id='C04', name='11-Features-Sourcing-Reference-Anonymized.docx', src=ROOT/'docs/11-Features-Sourcing-Reference-Anonymized (1).docx', dest='01_Client_Provided/Requirements',
    origin='CLIENT', sender='Konika Thakur (BridgeAI)', channel="Konika Thakur's mail of 31 Aug 2026 23:41 IST to Manil/Palash/Sahaj/Dhruvi (not in this mailbox; text preserved in 07_Internal_Generated/Email_Archive/mails (1).txt; attachments: 11-Features-Sourcing-Reference-Anonymized.docx, Source A.xlsx, Source B.xlsx, google_news_rss_data.xlsx)",
    date='2026-08-31', version='anonymized', status='REFERENCE',
    used_for='Which vendor/source feeds each of the 11 features (Explorium, PredictLeads, Bombora, Apollo, Exa, Google News RSS...).',
    notes='Provenance confirmed from the pasted mail text in 07_Internal_Generated/Email_Archive/mails (1).txt. Explicitly a REVIEW draft: "Could you both please review it and let us know if anything needs to be adjusted? Once aligned, we can use this as the reference going forward." No alignment reply is on record.')

add(id='C42a', name='Source B.xlsx (31 Aug, Astra seed - PredictLeads export)', src=None, dest='04_Data_and_Source_Definitions/PredictLeads/seed_Astra', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)',
    channel="Konika's 31 Aug 2026 mail (not in this mailbox; see 07_Internal_Generated/Email_Archive/mails (1).txt)", date='2026-08-31', status='SUPERSEDED - NOT ON THIS MACHINE', superseded_by='C22b predictleads_combined_219_accounts.xlsx',
    used_for='Hiring / job-openings + news_events + technology_detections seed for Astra. Only job_openings.csv (now 04_Data_and_Source_Definitions/PredictLeads/seed_Astra/) survives locally.', notes='Never reached this machine; .gitignore names it.')
add(id='C42b', name='google_news_rss_data.xlsx (31 Aug, Astra seed)', src=None, dest='04_Data_and_Source_Definitions/Google_News_RSS', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)',
    channel="Konika's 31 Aug 2026 mail (not in this mailbox; see 07_Internal_Generated/Email_Archive/mails (1).txt)", date='2026-08-31', status='SUPERSEDED - NOT ON THIS MACHINE', superseded_by='C22d google_news_rss_data 1.xlsx (220 accounts, 18 Sep)',
    used_for='Google News RSS seed for Astra.', notes='Never reached this machine; .gitignore names it.')

# ---------------- CLIENT: logic and scoring ----------------
add(id='C08', name='HP_220_Account_Recommendation_Logic(1).pptx', src=None, dest='01_Client_Provided/Logic_and_Scoring/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 15 Sep 2026 13:02 UTC', date='2026-09-15', version='draft (Astra worked example)',
    status='SUPERSEDED', superseded_by='C28 HP_Recommendation_Tuning_Logic_FINAL_v4.docx (23 Sep 2026)',
    used_for='First draft of the recommendation logic. Client\'s own file explanation (18 Sep) says "Not used as of now. Some changes need to be made after discussing them with Sahaj."',
    notes='NOT ON THIS MACHINE - attachment never downloaded. Gmail connector cannot fetch attachments.')
add(id='C09', name='HP_Urgency_Score_Updated_Final.docx', src=DL/'HP_Urgency_Score_Updated_Final.docx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 16 Sep 2026 13:35 UTC', date='2026-09-16', version='Updated Final',
    status='CURRENT', supersedes="Delivery team's five-driver proposal (Yogesh, 16 Sep 02:34 UTC) - explicitly replaced by this document",
    used_for='Executive Dashboard Urgency Score: 4 drivers (Workplace Technology & OS 20%, AI & Workstation 25%, Growth & Expansion 30%, HP Solution Intent 25%), 60% weighted-coverage minimum, job-status rule, score-scale conversions (email of 16 Sep).',
    notes='Was only in ~/Downloads, not in the project folders, before this exercise. Fleet Refresh explicitly excluded (Dhruvi, 18 Sep).', also=['02_Decision_Maker'])
add(id='C15', name='HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook.docx', src=ROOT/'NewDocs/HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook.docx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17', version='v1 (17 Sep)',
    status='SUPERSEDED (replacement not on file)', superseded_by='C29 ..._Rulebook_FINAL_.docx (23 Sep 2026, adds Print sections highlighted yellow) - NOT ON THIS MACHINE',
    used_for='HP product / services / solutions rules used to strengthen recommendations across features (client mapping of 18 Sep: all features except Content Studio? see new file explanation). Only local copy of the Rulebook; use for non-Print rules until FINAL is retrieved.',
    also=['02_Decision_Maker'])
add(id='C17', name='HP_Tech_Landscape_Confidence_Scoring_Logic.docx', src=None, dest='01_Client_Provided/Logic_and_Scoring/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 17:29 UTC', date='2026-09-17', version='v1',
    status='SUPERSEDED', superseded_by='C21 ..._FINAL.docx (18 Sep 2026 04:08 UTC): "please use the latest document ... and disregard the version I shared yesterday night"',
    used_for='Tech Landscape confidence scoring (first version).', notes='NOT ON THIS MACHINE.')
add(id='C18', name='HP_Live_Signal_Scoring_Logic.docx', src=ROOT/'NewDocs/HP_Live_Signal_Scoring_Logic.docx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 17:29 UTC', date='2026-09-17', version='1',
    status='CURRENT', used_for='Live Signals scoring (3 drivers, score out of 10). Client confirmed 24 Sep (clarifying opens_2 item 36): "use live signal scoring logic as given ... there is a score instead of tiers".',
    also=['02_Decision_Maker'])
add(id='C21', name='HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx', src=ROOT/'NewDocs/HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 18 Sep 2026 04:08 UTC', date='2026-09-18', version='FINAL',
    status='CURRENT', supersedes='C17 (17 Sep version)', used_for='Technographic Map confidence score per card (Confirmed / Likely / Unknown bands etc.).',
    also=['02_Decision_Maker'])
add(id='C26', name='new file explanation 220 acc.xlsx', src=ROOT/'NewDocs/new file explanation 220 acc.xlsx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 18 Sep 2026 13:32 UTC', date='2026-09-18', version='1',
    status='CURRENT', used_for='Client mapping of each new file (filings, Rulebook, case studies, scoring docs, lifecycle, recommendation deck) to the in-scope features that may use it, plus two worked examples in the covering email (Intune -> WXP; Mitsubishi Electric 3D -> Aereco case study).',
    also=['02_Decision_Maker'])
add(id='C28', name='HP_Recommendation_Tuning_Logic_FINAL_v4.docx', src=DL/'HP_Recommendation_Tuning_Logic_FINAL_v4.docx', dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 23 Sep 2026 05:53 UTC', date='2026-09-23', version='FINAL v4',
    status='CURRENT', supersedes='C08 recommendation deck (15 Sep)', used_for='Recommendation logic for every feature (which evidence feeds recommendations, use of Rulebook and case studies, data_as_of_date, Apollo contacts as required input). Relevance threshold clarified by Dhruvi 24 Sep 09:30 UTC (use-case/opportunity fit, "relevant" vs "may be relevant / explore fit").',
    notes='Was only in ~/Downloads before this exercise.', also=['02_Decision_Maker'])
add(id='C29', name='HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook_FINAL_.docx', src=None, dest='01_Client_Provided/Logic_and_Scoring',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 23 Sep 2026 05:53 UTC', date='2026-09-23', version='FINAL (Print additions in yellow)',
    status='CURRENT - NOT ON THIS MACHINE', supersedes='C15 Rulebook v1 (17 Sep)',
    used_for='The current HP Rulebook incl. Print (Ink, Managed Print, Document & Workflow) rules.', notes='MUST BE DOWNLOADED from the 23 Sep 05:53 UTC message. Until then C15 is the only local Rulebook.')

# ---------------- CLIENT: answers ----------------
add(id='C34', name='clarifying opens_1.docx (first send, 09:30 UTC)', src=DL/'clarifying opens_1.docx', dest='01_Client_Provided/Client_Answers/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 24 Sep 2026 09:30 UTC', date='2026-09-24', version='as sent 09:30 UTC',
    status='SUPERSEDED', superseded_by='C35 (same file re-sent 14:43 UTC with one extra line: "Sec filings : pls use from filings.csv + predictleads data->sec_filings")',
    used_for='Client answers (yellow) to 220-Account-Data-Questions-For-Client.md (10 items).',
    notes='Version mapping inferred from download timestamps (local 17:27 IST vs 21:41 IST) and a one-line diff. Needs confirmation: LOW risk.')
add(id='C35', name='clarifying opens_1.docx (re-sent 14:43 UTC)', src=ROOT/'NewDocs/clarifying opens_1  Dhruvi.docx', dest='01_Client_Provided/Client_Answers',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 24 Sep 2026 14:43 UTC (attached again alongside opens_2)', date='2026-09-24', version='re-send 14:43 UTC',
    status='CURRENT', supersedes='C34', used_for='Client answers to the 10 data questions of 23 Sep: shared domains (Company Name + Country), canonical domains for Posco/Pilipinas Shell/Shiseido/Stanley, pbebank.com, news merge rule, undated/epoch rows, IDs vs domain, UTF-8/HTML, coverage gaps, filings source.',
    notes='Saved locally as "clarifying opens_1  Dhruvi.docx".', also=['02_Decision_Maker','05_Questions_and_Clarifications/Source_Documents'])
add(id='C36', name='clarifying opens_2.docx', src=ROOT/'NewDocs/clarifying opens_2.docx', dest='01_Client_Provided/Client_Answers',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 24 Sep 2026 14:43 UTC', date='2026-09-24', version='1',
    status='CURRENT', used_for='Client answers (inline "->") to the 43-item 220-Open-Decisions-List.md sent 24 Sep 07:35 UTC. Source for most decisions in DECISION_LOG.md.',
    also=['02_Decision_Maker','05_Questions_and_Clarifications/Source_Documents'])

# ---------------- CLIENT: reviews / tests ----------------
add(id='C37', name='HP_220_Refinements_Updated.docx', src=None, dest='01_Client_Provided/Client_Reviews',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=PROG+', 12 Sep 2026 11:26 UTC', date='2026-09-12', version='Updated',
    status='REFERENCE - NOT ON THIS MACHINE', used_for='Client review of the live build vs the HP SEA Limited POC (screenshots of six features). Basis for the 16 Sep QA discussion.',
    notes='Attachment never downloaded.')
add(id='C27', name='tests on current HP 220.docx', src=None, dest='01_Client_Provided/Client_Reviews',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 22 Sep 2026 11:58 UTC', date='2026-09-22', version='1',
    status='OPEN - NOT ON THIS MACHINE', used_for="Client's UI test observations and questions on the current HP 220 build.", notes='Attachment never downloaded.')

# ---------------- CLIENT: HP reference material (folded into Rulebook) ----------------
add(id='C11', name='HP Care Pack Services Definitions.pdf', src=ROOT/'NewDocs/HP Care Pack Services Definitions.pdf', dest='08_Reference_Material/HP_Services_and_Solutions',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI) - "original supporting materials received from the client [HP]"', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17',
    status='REFERENCE', used_for='HP Care Pack definitions. Client: "Not used separately - included in Combined HP Rulebook".')
add(id='C12', name='HP Q426 Services and solutions final.xlsx', src=ROOT/'NewDocs/HP Q426 Services and solutions final.xlsx', dest='08_Reference_Material/HP_Services_and_Solutions',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17',
    status='REFERENCE', used_for='HP services SKU list (2,186 rows). Client: "Not used separately - included in Combined HP Rulebook".')
add(id='C13', name='Wolf Security Portfolio.pptx', src=ROOT/'NewDocs/Wolf Security Portfolio.pptx', dest='08_Reference_Material/HP_Services_and_Solutions/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17',
    status='SUPERSEDED (encrypted, unreadable)', superseded_by='C24 Wolf_Security_Portfolio_Recreated.pptx (18 Sep 2026 07:28 UTC) - NOT ON THIS MACHINE',
    used_for='HP Wolf Security offerings. Client: folded into the Rulebook.', notes='File is password-protected (CDFV2 Encrypted); cannot be opened.')
add(id='C14', name='HP IQ for Enterprise.pptx', src=ROOT/'NewDocs/HP IQ for Enterprise.pptx', dest='08_Reference_Material/HP_Services_and_Solutions/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17',
    status='SUPERSEDED (encrypted, unreadable)', superseded_by='C25 HP_IQ_for_Enterprise_Recreated.pptx (18 Sep 2026 07:28 UTC) - NOT ON THIS MACHINE',
    used_for='HP IQ for Enterprise capabilities. Client: folded into the Rulebook.', notes='Password-protected; cannot be opened.')
add(id='C16', name='Copy of HP Lifecycle as of June 2026_Filtered.xlsx', src=ROOT/'NewDocs/Copy of HP Lifecycle as of June 2026_Filtered.xlsx', dest='08_Reference_Material/HP_Services_and_Solutions/_SUPERSEDED',
    origin='CLIENT', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 08:47 UTC', date='2026-09-17',
    status='SUPERSEDED (encrypted, unreadable)', superseded_by='C23 Hp lifecycle june 2026.xlsx (18 Sep 2026 07:28 UTC) - NOT ON THIS MACHINE',
    used_for='HP product EOL / sell-through dates. Client 18 Sep: NOT used for Fleet Refresh; file explanation: "Not used as of now".', notes='Password-protected; cannot be opened.')
add(id='C23', name='Hp lifecycle june 2026.xlsx', src=None, dest='08_Reference_Material/HP_Services_and_Solutions', origin='CLIENT', sender='Dhruvi Patel (BridgeAI)',
    channel=MAIN+', 18 Sep 2026 07:28 UTC', date='2026-09-18', status='REFERENCE - NOT ON THIS MACHINE', supersedes='C16',
    used_for='Unencrypted lifecycle file. Not used in the platform per client.', notes='Attachment never downloaded.')
add(id='C24', name='Wolf_Security_Portfolio_Recreated.pptx', src=None, dest='08_Reference_Material/HP_Services_and_Solutions', origin='CLIENT', sender='Dhruvi Patel (BridgeAI)',
    channel=MAIN+', 18 Sep 2026 07:28 UTC', date='2026-09-18', status='REFERENCE - NOT ON THIS MACHINE', supersedes='C13', used_for='Readable Wolf Security deck.', notes='Attachment never downloaded.')
add(id='C25', name='HP_IQ_for_Enterprise_Recreated.pptx', src=None, dest='08_Reference_Material/HP_Services_and_Solutions', origin='CLIENT', sender='Dhruvi Patel (BridgeAI)',
    channel=MAIN+', 18 Sep 2026 07:28 UTC', date='2026-09-18', status='REFERENCE - NOT ON THIS MACHINE', supersedes='C14', used_for='Readable HP IQ deck.', notes='Attachment never downloaded.')
for i,(nm) in enumerate(['Original HP Ink Portfolio.pdf','HP Managed Print Portfolio 1.pdf','HP Document and Workflow Solutions Brochure.pdf']):
    add(id=f'C3{i}', name=nm, src=None, dest='08_Reference_Material/HP_Services_and_Solutions', origin='CLIENT', sender='Dhruvi Patel (BridgeAI) - received from HP',
        channel=MAIN+', 23 Sep 2026 05:53 UTC', date='2026-09-23', status='REFERENCE - NOT ON THIS MACHINE',
        used_for='Print portfolio reference; client says relevant content already incorporated into the Rulebook FINAL (C29).', notes='Attachment never downloaded.')

# ---------------- CLIENT: data (3 Sep SharePoint drop, Astra seed) ----------------
add(id='C39a', name='hp_intent_results.xlsx (3 Sep, Astra seed)', src=ROOT/'docs/hp_intent_results(Intent Data (Wide)).csv', dest='04_Data_and_Source_Definitions/HP_Intent/seed_3Sep',
    origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)', channel=SP, date='2026-09-03', version='3 Sep export (single account)',
    status='SUPERSEDED', superseded_by='C22 hp_intent_results 2.xlsx (220 accounts, Drive drop 18 Sep)', used_for='Intent & Demand Signals seed for Astra. Only the "Intent Data (Wide)" sheet was exported to CSV locally; hp_intent_results.pdf is a print of the same.',
    notes='Full workbook lives on SharePoint; not reachable from this machine.')
add(id='C39b', name='hp_intent_results.pdf', src=ROOT/'docs/hp_intent_results.pdf', dest='04_Data_and_Source_Definitions/HP_Intent/seed_3Sep', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)', channel=SP,
    date='2026-09-03', status='SUPERSEDED', superseded_by='C22', used_for='PDF print of the 3 Sep intent workbook (Astra).')
add(id='C39c', name='apollo_data.xlsx (3 Sep)', src=ROOT/'docs/apollo_data.pdf', dest='04_Data_and_Source_Definitions/Contacts_Apollo', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)', channel=SP,
    date='2026-09-03', status='REFERENCE (Astra seed only)', used_for='Contacts + phone numbers for the Astra seed account. Only a PDF print exists locally; the xlsx is on SharePoint. The 220-account contact file (Apollo_All_Contacts) has NOT been received as of 25 Sep.',
    notes='Local file is apollo_data.pdf.')
for nm in ['2025-Astra-Annual-Report.pdf','Astra-Annual-Report-2024.pdf']:
    add(id='C39d', name=nm, src=ROOT/'docs'/nm, dest='08_Reference_Material/Astra_Seed_Account', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)', channel=SP, date='2026-09-03',
        status='REFERENCE', used_for='Astra annual reports (compliance_filings seed for the reference account).')
for nm in ["Car Market Jan'26 - Wholesales.pdf","Car Market Feb'26 - Wholesales.pdf","Car Market Mar'26 - Wholesales.pdf","Car Market Apr'26 - Wholesales.pdf","Car Market May'26 - Wholesales.pdf","Car Market Jun'26 - Wholesales.pdf","Car Market Jul'26 - Wholesales.pdf"]:
    add(id='C39e', name=nm, src=ROOT/'docs'/nm, dest='08_Reference_Material/Astra_Seed_Account', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)', channel=SP, date='2026-09-03',
        status='REFERENCE', used_for='Monthly Indonesian car-market wholesale reports (Astra seed context).')
add(id='C40', name='Source A.xlsx', src=ROOT/'docs/Source A.xlsx', dest='04_Data_and_Source_Definitions/Explorium/seed_Astra', origin='CLIENT DATA', sender='Konika Thakur (BridgeAI)',
    channel="Konika's 31 Aug 2026 mail (not in this mailbox) - see 07_Internal_Generated/Email_Archive/mails (1).txt paste", date='2026-08-31', version='Astra single-account Explorium export',
    status='SUPERSEDED (as production input)', superseded_by='C22 explorium_clean_220 (220 workbooks, same sheet layout)', used_for='Explorium export for the Astra seed: 1_Firmographics ... 14_Prospect_Contacts (18 sheets). Defines the Explorium sheet layout the input contract was built on.',
    notes='Still the Astra seed used by the local backend.')
add(id='C41a', name='firmographics.csv', src=ROOT/'docs/firmographics.csv', dest='04_Data_and_Source_Definitions/Explorium/seed_Astra', origin='CLIENT DATA (derived)', sender='Konika Thakur (BridgeAI) / extracted by delivery team',
    channel='Sheet 1_Firmographics of Source A.xlsx exported to CSV', date='2026-09-03', status='REFERENCE (Astra seed)', used_for='Upload-ready firmographics for Astra.')
add(id='C41b', name='job_openings.csv', src=ROOT/'docs/job_openings.csv', dest='04_Data_and_Source_Definitions/PredictLeads/seed_Astra', origin='CLIENT DATA (derived)', sender='Konika Thakur (BridgeAI) / extracted by delivery team',
    channel="PredictLeads job_openings export for Astra (from Konika's 31 Aug 'Source B' set; original xlsx not on this machine)", date='2026-09-03', status='REFERENCE (Astra seed)', used_for='Hiring signals seed for Astra (100 postings: 60 closed, 40 blank status).')

# ---------------- CLIENT: 220-account data drop ----------------
add(id='C22a', name='explorium_clean_220.zip (+ extracted folder, 220 workbooks)', src=ROOT/'220 account data /explorium_clean_220.zip', dest='04_Data_and_Source_Definitions/Explorium', origin='CLIENT DATA', sender='Konika Thakur / Dhruvi Patel (BridgeAI)',
    channel=DRIVE_DATA, date='2026-09-18', version='clean_220', status='CURRENT', used_for='Per-account Explorium workbooks (firmographics, hierarchy, technographics, webstack, tech breakdown, workforce, ratings, traffic, social, intent topics, intent score, news events, contacts [empty]).',
    notes='Local copy in "220 account data /". 220 workbooks; Contacts sheet empty in all; hierarchy present for 165.')
add(id='C22b', name='predictleads_combined_219_accounts.xlsx', src=ROOT/'220 account data /predictleads_combined_219_accounts.xlsx', dest='04_Data_and_Source_Definitions/PredictLeads', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)',
    channel=DRIVE_DATA+' - hiring data added 18 Sep 13:32 UTC', date='2026-09-18', status='CURRENT', used_for='company, extended_company, job_openings, technology_detections, news_events, financing_events, connections, subpages, products, similar_companies, sec_filings + QA sheets. Client 23 Sep: use sec_filings and products; ignore the rest of the new sheets.')
add(id='C22c', name='exa_data.xlsx', src=ROOT/'220 account data /exa_data.xlsx', dest='04_Data_and_Source_Definitions/Exa', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=DRIVE_DATA, date='2026-09-18',
    status='CURRENT', used_for='Exa.ai news feed (9,221 rows, 14 cols, same schema as Google News RSS). Merged with RSS for Live Signals.')
add(id='C22d', name='google_news_rss_data 1.xlsx', src=ROOT/'220 account data /google_news_rss_data 1.xlsx', dest='04_Data_and_Source_Definitions/Google_News_RSS', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=DRIVE_DATA, date='2026-09-18',
    status='CURRENT', supersedes='google_news_rss_data.xlsx (31 Aug, Astra only - not on this machine)', used_for='Google News RSS feed (7,913 rows). Merged with Exa for Live Signals.')
add(id='C22e', name='hp_intent_results 2.xlsx', src=ROOT/'220 account data /hp_intent_results 2.xlsx', dest='04_Data_and_Source_Definitions/HP_Intent', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=DRIVE_DATA, date='2026-09-18',
    status='CURRENT', supersedes='C39a (3 Sep Astra-only export)', used_for='HP category intent (PCs, Workstations, Poly, Printers, 3D Printers) per account; primary intent signal per Konika 3 Sep. 173 of 220 populated.')
add(id='C33', name='NSW_Education_Public_intent (Drive)', src=None, dest='04_Data_and_Source_Definitions/HP_Intent', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=DRIVE_DATA+' - added 23 Sep 2026 05:53 UTC', date='2026-09-23',
    status='CURRENT - NOT ON THIS MACHINE', used_for='Intent data for DEPARTMENT OF EDUCATION - NSW, AU (education.nsw.gov.au), missing from the 18 Sep intent file.', notes='Drive connector has no scope; download by hand.')
add(id='C19', name='filings 1.csv', src=ROOT/'NewDocs/filings 1.csv', dest='04_Data_and_Source_Definitions/Filings', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI) (crawl by Pritesh)', channel=MAIN+', 17 Sep 2026 17:29 UTC', date='2026-09-17',
    status='CURRENT', supersedes='"Stock Exchange data" named in Konika\'s 3 Sep mail (never attached) - client 24 Sep: "already resolved: she shared with you different pdfs"',
    used_for='Index of stock-exchange / annual-report filings per account (505 rows, 186 unique company names; client says 184 of 220 accounts). document_url first, source_page_url fallback, exclude records with neither (Dhruvi 18 Sep). Merge with PredictLeads sec_filings on domain + Company Name + Country (opens_2 #11).')
add(id='C38', name='Filings PDFs (Drive folder 1FAMRDkL7Y0E8LSzEYu7FmmVA0VVAgCgP)', src=None, dest='04_Data_and_Source_Definitions/Filings', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel='clarifying opens_2 item 12, 24 Sep 2026', date='2026-09-24',
    status='CURRENT - NOT ON THIS MACHINE', used_for='The downloaded filing documents themselves (~1.5 GB on Pritesh\'s machine per memory note). Client: where a link fails, skip that file, not the company.')
add(id='C10', name='hp_case_studies_full.csv', src=None, dest='04_Data_and_Source_Definitions/Case_Studies/_SUPERSEDED', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 16 Sep 2026 13:39 UTC', date='2026-09-16',
    status='SUPERSEDED', superseded_by='C20 hp_case_studies_final.csv (17 Sep)', used_for='First case-study dataset ("277 HP case studies").', notes='Attachment never downloaded.')
add(id='C20', name='hp_case_studies_final.csv', src=ROOT/'NewDocs/hp_case_studies_final.csv', dest='04_Data_and_Source_Definitions/Case_Studies', origin='CLIENT DATA', sender='Dhruvi Patel (BridgeAI)', channel=MAIN+', 17 Sep 2026 17:29 UTC', date='2026-09-17',
    status='CURRENT', supersedes='C10', used_for='HP customer case studies as proof points (384 rows -> 89 distinct studies after delivery-team cleaning; client accepted the 89 on 24 Sep, opens_2 #31).')

# ---------------- CLIENT: HP product decks (Drive) ----------------
DECKS = ROOT/'docs/drive-download-20260912T033240Z-1-001'
if not DECKS.exists(): DECKS = OUT/'08_Reference_Material/HP_Product_Decks'
for p in sorted(DECKS.glob('*.pptx')):
    if p.name.startswith('HP EliteDesk 8'): continue  # Desktop deck, listed separately as C07
    add(id='C06', name=p.name, src=p, dest='08_Reference_Material/HP_Product_Decks', origin='CLIENT REFERENCE (HP via BridgeAI)', sender='Dhruvi Patel (BridgeAI)',
        channel='Google Drive "Notebook" folder 1gbneD6Rri5ae2ml9Lq09PtM32Ba-z9jO (24 Aug 2026 mail); downloaded 12 Sep 2026 as drive-download-20260912T033240Z-1-001.zip', date='2026-08-24',
        status='REFERENCE', used_for='HP Notebook product decks for RAG / recommendations per the additional-data doc rules (C02). Preferred HP product source when a deck rule matches.')
add(id='C07', name='HP EliteDesk 8 and ProDesk 4 Mini G1i Desktop AI PC Full Customer Presentation.pptx', src=ROOT/'docs/HP EliteDesk 8 and ProDesk 4 Mini G1i Desktop AI PC Full Customer Presentation.pptx', dest='08_Reference_Material/HP_Product_Decks',
    origin='CLIENT REFERENCE (HP via BridgeAI)', sender='Dhruvi Patel (BridgeAI)', channel='Google Drive "Desktop" folder 1BzoQcTnvu2kinEqnZWXcmVw9Hc7sHTEr (24 Aug 2026 mail); downloaded 12 Sep 2026', date='2026-08-24',
    status='REFERENCE', used_for='HP Desktop product deck for RAG / recommendations.', notes='Whether the Desktop folder holds more decks than this one is unknown (Drive not reachable).')
add(id='C05', name='hp-sea-abm-dev-main.zip (HP Sea Limited ABM POC codebase)', src=None, dest='08_Reference_Material/POC_References', origin='CLIENT REFERENCE', sender='Dhruvi Patel (BridgeAI)',
    channel='Google Drive file 16WsfrKkdd6ITk3UCfVFcA-lQz0URXdHM (22 Aug 2026 mail)', date='2026-08-22', status='REFERENCE - NOT ON THIS MACHINE',
    used_for='Starting point / reference implementation for the 11 features. Live POC: https://hp-sea-abm.vercel.app/ ; Palo Alto Caterpillar POC: https://paloalto-abm.vercel.app/', notes='Drive connector lacks scope.')

# ---------------- INTERNAL ----------------
add(id='I01', name='HP-Account-Intelligence-Rules.docx', src=DL/'HP-Account-Intelligence-Rules.docx', dest='02_Decision_Maker', origin='INTERNAL (delivery team)', sender='Manisha Parwani -> client', channel=SKIP+', 10 Sep 2026 11:16 UTC (requested by Sahaj; Dhruvi: "we\'ll review ... and share our feedback")',
    date='2026-09-10', version='1', status='INTERNAL - UNDER CLIENT REVIEW (no feedback received as of 25 Sep)', used_for='Every rule, guardrail and scoring decision the four then-complete features enforce, anchored to code. Any rule not in here is undisclosed to the client.',
    notes='The docs/ copy "HP-Account-Intelligence-Rules (1).docx" was byte-identical.', also=['07_Internal_Generated/Rules_and_Handover'])
add(id='I02', name='HP-Account-Intelligence-Handover.docx', src=ROOT/'docs/HP-Account-Intelligence-Handover.docx', dest='07_Internal_Generated/Rules_and_Handover', origin='INTERNAL (delivery team)', sender='delivery team', channel='local (formerly docs/), referenced by repo README', date='2026-09-14',
    status='INTERNAL', used_for='Feature status (4 complete / 7 deterministic-only at the time) and dataset -> feature map. Reference account Astra.', notes='Status is a snapshot; superseded by later progress mails (all features complete except Strategy Chat by 14 Sep).')
add(id='I03', name='Evidence-Score-Data-Availability-Answers.md', src=ROOT/'docs/Evidence-Score-Data-Availability-Answers.md', dest='07_Internal_Generated/Analysis', origin='INTERNAL', sender='delivery team', channel='git (first commit 2026-09-15)', date='2026-09-15', status='INTERNAL', used_for='Answers on what data exists for evidence scoring.')
add(id='I04a', name='HP-Input-Data-Contract.md', src=ROOT/'docs/HP-Input-Data-Contract.md', dest='07_Internal_Generated/Analysis', origin='INTERNAL', sender='delivery team', channel='git (2026-09-16, last 2026-09-24)', date='2026-09-24', status='INTERNAL (living spec)', used_for='Input contract: every dataset key, columns, transforms, known defects, which widget each column becomes.')
add(id='I04b', name='hp-input-contract.json', src=ROOT/'docs/hp-input-contract.json', dest='07_Internal_Generated/Analysis', origin='INTERNAL', sender='delivery team', channel='git (2026-09-16, last 2026-09-23)', date='2026-09-23', status='INTERNAL (living spec)', used_for='Machine-readable column-level lineage (columns -> widget fields).')
add(id='I04c', name='hp-file-to-json-map.json', src=ROOT/'docs/hp-file-to-json-map.json', dest='07_Internal_Generated/Analysis', origin='INTERNAL', sender='delivery team', channel='git (2026-09-16, last 2026-09-23)', date='2026-09-23', status='INTERNAL (living spec)', used_for='File-level companion of the input contract.')
add(id='I05', name='2026-09-14-feature-walkthrough.md', src=ROOT/'docs/meeting-notes/2026-09-14-feature-walkthrough.md', dest='07_Internal_Generated/Meeting_Notes', origin='INTERNAL', sender='delivery team', channel='git (2026-09-14)', date='2026-09-14', status='INTERNAL', used_for='Notes of the 14 Sep internal feature walkthrough.')
for nm in ['QA-Report-Response_2026-09-16.md','QA-Report-Response_2026-09-16.pdf','QA-Discussion-Points_2026-09-16.md','QA-Discussion-Points_2026-09-16.pdf']:
    add(id='I06', name=nm, src=ROOT/'docs/qa'/nm, dest='07_Internal_Generated/QA', origin='INTERNAL', sender='Yogesh Yadav -> client (PDFs attached 16 Sep 19:14 UTC)', channel=MAIN+', 16 Sep 2026 19:14 UTC', date='2026-09-16',
        status='INTERNAL - SENT TO CLIENT', used_for='Response to the client\'s 12 Sep refinements doc (resolved items) and the open QA questions needing a client classification/decision.',
        also=['05_Questions_and_Clarifications/Source_Documents'] if nm.endswith('.md') else [])
for nm in ['api-envelope.md','api-errors.md','linting.md','observability.md','observability-backlog.md','branch-protection.md']:
    add(id='I07', name=nm, src=ROOT/'docs'/nm, dest='07_Internal_Generated/Engineering', origin='INTERNAL', sender='delivery team', channel='git (2026-09-16)', date='2026-09-16', status='INTERNAL (engineering)', used_for='Engineering conventions; no business-rule content.')
add(id='I08', name='mails (1).txt', src=ROOT/'07_Internal_Generated/Email_Archive/mails (1).txt', dest='07_Internal_Generated/Email_Archive', origin='INTERNAL (paste of client mails)', sender='Palash Chatterjee (pasted from his mailbox)', channel='local paste, ~3 Sep 2026 ("12 days ago" relative to 22 Aug)', date='2026-09-03',
    status='REFERENCE', used_for='Plain-text copy of the 22 Aug - 3 Sep client mails (Dhruvi 22 Aug, 24 Aug, 31 Aug; Konika 3 Sep). Only local record of the pre-9 Sep thread.')
add(id='I09', name='220-Account-Data-Questions-For-Client.md', src=ROOT/'NewDocs/220-Account-Data-Questions-For-Client.md', dest='07_Internal_Generated/Question_Trackers', origin='INTERNAL', sender='Yogesh Yadav -> client', channel=MAIN+', 23 Sep 2026 18:56 UTC', date='2026-09-23',
    status='INTERNAL - SENT TO CLIENT (answered by C35)', used_for='10 data discrepancies found in the 220-account drop.', also=['05_Questions_and_Clarifications/Source_Documents'])
add(id='I10', name='220-Open-Decisions-List.md', src=ROOT/'NewDocs/220-Open-Decisions-List.md', dest='07_Internal_Generated/Question_Trackers', origin='INTERNAL', sender='Yogesh Yadav -> client', channel=MAIN+', 24 Sep 2026 07:35 UTC', date='2026-09-24',
    status='INTERNAL - SENT TO CLIENT (answered by C36)', used_for='43 open decisions and data questions before the 220-account run, each with a proposed default.', also=['05_Questions_and_Clarifications/Source_Documents'])
add(id='I11', name='220-Open-Items-and-Clarifications.md', src=ROOT/'NewDocs/220-Open-Items-and-Clarifications.md', dest='07_Internal_Generated/Question_Trackers', origin='INTERNAL', sender='Yogesh Yadav', channel='local (NewDocs), 25 Sep 2026', date='2026-09-25',
    status='INTERNAL (merged into clarifying_opens_3 *_v2)', used_for='Our round-3 points after reading opens_2; merged into the v2 docx files.')
add(id='I12', name='220-Open-Questions-Tracker.md', src=ROOT/'NewDocs/220-Open-Questions-Tracker.md', dest='07_Internal_Generated/Question_Trackers', origin='INTERNAL', sender='delivery team', channel='local (NewDocs), 25 Sep 2026', date='2026-09-25', status='INTERNAL', used_for='Running tracker of questions and their status.')
add(id='I13', name='BridgeAI-email-draft-2026-09-24.md', src=ROOT/'NewDocs/BridgeAI-email-draft-2026-09-24.md', dest='07_Internal_Generated/Email_Drafts', origin='INTERNAL', sender='Yogesh Yadav', channel='local draft of the 24 Sep 04:52 UTC team-position email', date='2026-09-24', status='INTERNAL (sent version is in the thread)', used_for='Draft of the team-position email.')
R3 = {'clarifying_opens_3_CLARIFICATIONS.docx': ('SENT 25 Sep 02:35 UTC - CURRENT', ''), 'clarifying_opens_3_CLARIFICATIONS_v2.docx': ('INTERNAL - NOT SENT (merged draft with our extra points)', ''),
      'clarifying_opens_3_OPEN.docx': ('SUPERSEDED (not sent)', 'clarifying_opens_3_OPEN_v2.docx'), 'clarifying_opens_3_OPEN_v2.docx': ('SENT 25 Sep 02:35 UTC - CURRENT (awaiting client answers)', ''),
      'clarifying_opens_3_UNRESOLVED.docx': ('SUPERSEDED (not sent)', 'clarifying_opens_3_UNRESOLVED_v2.docx'), 'clarifying_opens_3_UNRESOLVED_v2.docx': ('SENT 25 Sep 02:35 UTC - CURRENT (awaiting client answers)', '')}
for nm,(st,sb) in R3.items():
    add(id='I14', name=nm, src=ROOT/'NewDocs'/nm, dest='07_Internal_Generated/Client_Facing_Round3', origin='INTERNAL', sender='Manisha Parwani (originals) / Yogesh Yadav (v2 merges) -> client', channel=MAIN+', 25 Sep 2026 02:35 UTC' if 'SENT' in st else 'local (NewDocs), 25 Sep 2026',
        date='2026-09-25', status=st, superseded_by=sb, used_for='Round-3 clarification pack to BridgeAI: what we mean (CLARIFICATIONS), what we still need answered (OPEN), what is still broken after their answers (UNRESOLVED).',
        also=['05_Questions_and_Clarifications/Source_Documents'] if 'SENT' in st else [])
add(id='I15', name='HP-220-Account-Data-Review-Agenda.docx', src=ROOT/'NewDocs/HP-220-Account-Data-Review-Agenda.docx', dest='07_Internal_Generated/Meeting_Notes', origin='INTERNAL', sender='delivery team', channel='local (NewDocs), 23 Sep 2026', date='2026-09-23', status='INTERNAL', used_for='Agenda for the 23 Sep data-review call with BridgeAI.')
add(id='I16', name='GCP_Access_Request_for_Manager.docx', src=DL/'GCP_Access_Request_for_Manager.docx', dest='07_Internal_Generated/Access_Requests', origin='INTERNAL', sender='Yogesh Yadav -> Sahaj (WhatsApp, 23 Sep 19:11 IST)', channel='WhatsApp (not retrievable); local copy in ~/Downloads', date='2026-09-23', status='INTERNAL - SENT (access still open 25 Sep)', used_for='GCP roles / project requirements for the 220-account deployment.')
add(id='I17a', name='QA-Report.md (widget QA validator, HP Sea Limited, 15 Sep)', src=DL/'reports/QA-Report.md', dest='07_Internal_Generated/QA/validator_run_2026-09-15', origin='GENERATED (internal QA tool)', sender='QA validator (source not on this machine)', channel='local ~/Downloads/reports', date='2026-09-15', status='INTERNAL - GENERATED', used_for='4-step feature evaluation of the deployed site vs the SEA Limited reference. Known false failures are recorded in 07_Internal_Generated/QA/README.md.')
add(id='I17b', name='pipeline-results.json', src=DL/'reports/pipeline-results.json', dest='07_Internal_Generated/QA/validator_run_2026-09-15', origin='GENERATED (internal QA tool)', sender='QA validator', channel='local ~/Downloads/reports', date='2026-09-15', status='INTERNAL - GENERATED', used_for='Machine output of the same run.')
add(id='I18', name='hp-project-flow.html', src=ROOT/'hp-project-flow.html', dest='07_Internal_Generated/Engineering', origin='INTERNAL', sender='delivery team', channel='local (repo root)', date='2026-09-14', status='INTERNAL', used_for='End-to-end flow diagram of the application (login -> upload -> extract -> widgets).')
add(id='I19', name='vercel app/ (Data Lineage Portal)', src=ROOT/'vercel app/README.md', dest='07_Internal_Generated/Engineering', origin='INTERNAL', sender='delivery team', channel='local (repo root "vercel app/"), 21 Sep 2026', date='2026-09-21', status='INTERNAL', used_for='Static site: 11 features, 32 widgets, 191 lineage records (what is shown -> where from -> how derived). Only the README is copied; the site lives in "vercel app/".')
add(id='I20a', name='_RUN_SUMMARY.json (220-account split)', src=ROOT/'220 account split csv/_RUN_SUMMARY.json', dest='07_Internal_Generated/Derived_Data', origin='GENERATED (scripts/split_account_data.py)', sender='delivery team', channel='local, generated 25 Sep 2026 05:16 UTC', date='2026-09-25', status='INTERNAL - GENERATED', used_for='Row counts, unclaimed rows, news de-dup count, corrections applied when splitting the vendor files into 220 per-account folders.')
add(id='I20b', name='_CORRECTIONS.txt (220-account split)', src=ROOT/'220 account split csv/_CORRECTIONS.txt', dest='07_Internal_Generated/Derived_Data', origin='GENERATED', sender='delivery team', channel='local, generated 25 Sep 2026', date='2026-09-25', status='INTERNAL - GENERATED', used_for='Every value the split derived instead of copying (blank domains, duplicate-name folders). INTERNAL ASSUMPTIONS live here.')
add(id='I20c', name='split_baseline.json', src=ROOT/'scripts/split_baseline.json', dest='07_Internal_Generated/Derived_Data', origin='GENERATED', sender='delivery team', channel='local (scripts/)', date='2026-09-23', status='INTERNAL - GENERATED', used_for='Baseline counts for validate_split_data.py.')
add(id='I21', name='README.md (repository)', src=ROOT/'README.md', dest='07_Internal_Generated/Engineering', origin='INTERNAL', sender='delivery team', channel='git', date='2026-09-11', status='INTERNAL', used_for='Setup and run instructions for hp-backend / hp-frontend.')
# Downloads-only docs whose authorship agent C verifies (defaults set here, adjusted after)
add(id='I22', name='HP_Platform_Gap_Analysis.docx', src=DL/'HP_Platform_Gap_Analysis.docx', dest='07_Internal_Generated/Analysis', origin='INTERNAL (delivery team)', sender='delivery team (received on this machine via WhatsApp)', channel='WhatsApp / local ~/Downloads, 18 Sep 2026', date='2026-09-18', status='INTERNAL - ANALYSIS ONLY', used_for='Gap analysis of the platform against the 11 client documents of 17-18 Sep: built / must change / must add. Origin of decision-list items 33-36, 38, 49. Evidence of authorship: "The client sent 11 new documents", "No code has been changed. This document is analysis only." Several of its recommendations were later overturned by the client (keep S/A/B/C tiers; seller-entered seat count).')
add(id='I23', name='HP_Account_Intelligence_FINAL_Remediation_Checklist.pdf', src=DL/'HP_Account_Intelligence_FINAL_Remediation_Checklist.pdf', dest='07_Internal_Generated/QA', origin='GENERATED (ChatGPT, from an internal engineering review)', sender='delivery team (downloaded from chatgpt.com)', channel='local ~/Downloads, 15 Sep 2026', date='2026-09-15', status='INTERNAL - GENERATED, UNTRACKED', used_for='51-item code-audit fix list (security, storage, async extraction, contract, intent correctness, silent fallbacks, tests). No item statuses are tracked; items 8-9 are contradicted by later client instruction on the intent hierarchy / noisy keywords. Not a client document.')
add(id='I24', name='HP_Sea_Limited_QA_Report_2026-09-15_0513 (1).docx', src=DL/'HP_Sea_Limited_QA_Report_2026-09-15_0513 (1).docx', dest='07_Internal_Generated/QA/validator_run_2026-09-15', origin='GENERATED (internal QA tool)', sender='QA validator', channel='local ~/Downloads, 15 Sep 2026', date='2026-09-15', status='INTERNAL - GENERATED', used_for='Word/PDF rendering of the 15 Sep validator run (same run as QA-Report.md).')

def md5(p, limit=None):
    h=hashlib.md5()
    with open(p,'rb') as f:
        for chunk in iter(lambda: f.read(1<<20), b''): h.update(chunk)
    return h.hexdigest()

def main():
    OUT.mkdir(exist_ok=True)
    rows=[]
    for e in M:
        dests=[e['dest']]+e['also']
        info={'size':None,'md5':None,'mtime':None,'copied':[], 'local_path':None}
        src=e['src']
        # docs/ and NewDocs/ were deleted on 25 Sep 2026 (user request) after every file was
        # verified as copied or moved into this tree; fall back to the in-tree copy.
        if src and not Path(src).exists():
            for d in dests:
                cand=OUT/d/Path(src).name
                if cand.exists(): src=cand; break
        if src and Path(src).exists():
            src=Path(src); st=src.stat(); info['size']=st.st_size; info['mtime']=datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M'); info['local_path']=str(src)
            if src.is_file(): info['md5']=md5(src)
            for d in dests:
                dd=OUT/d; dd.mkdir(parents=True, exist_ok=True)
                target=dd/src.name
                if src.is_file() and target.exists() and src.resolve()==target.resolve():
                    info['copied'].append(str(target.relative_to(OUT))); continue
                if src.is_file() and st.st_size<=COPY_LIMIT:
                    if not target.exists() or target.stat().st_size!=st.st_size: shutil.copy2(src, target)
                    info['copied'].append(str(target.relative_to(OUT)))
                else:
                    ptr=dd/(src.name+'.LINK.md')
                    ptr.write_text(f"# {src.name}\n\nNot copied ({'folder' if src.is_dir() else f'{st.st_size/1e6:.1f} MB'} > copy limit). Original is at:\n\n    {src}\n\nmd5: {info['md5'] or 'n/a (folder)'}\n\nProvenance: {e['channel']} — status {e['status']}. See 00_INDEX/PROVENANCE_REGISTER.md entry {e['id']}.\n")
                    info['copied'].append(str(ptr.relative_to(OUT)))
        else:
            for d in dests:
                dd=OUT/d; dd.mkdir(parents=True, exist_ok=True)
                ptr=dd/(e['name'].split(' (')[0]+'.MISSING.md')
                ptr.write_text(f"# {e['name']}\n\n**NOT ON THIS MACHINE.**\n\n- Sender: {e['sender']}\n- Where it was sent: {e['channel']}\n- Date: {e['date']}\n- Status: {e['status']}\n- Supersedes: {e['supersedes'] or '-'}\n- Superseded by: {e['superseded_by'] or '-'}\n- Used for: {e['used_for']}\n- Notes: {e['notes']}\n\nHow to retrieve: open the message above in Gmail (the connector used for this index cannot download attachments) or the Drive/SharePoint link, download by hand, drop the file into this folder and update 00_INDEX/PROVENANCE_REGISTER.md.\n")
                info['copied'].append(str(ptr.relative_to(OUT)))
        rows.append({**{k:(str(v) if isinstance(v,Path) else v) for k,v in e.items()}, **info})
    (OUT/'00_INDEX').mkdir(exist_ok=True)
    json.dump(rows, open(OUT/'00_INDEX/provenance_manifest.json','w'), indent=1)
    # PROVENANCE_REGISTER.md
    L=['# Provenance Register', '', '**Consolidation note (25 Sep 2026):** after every file was verified as copied (md5-identical) or moved into this tree, the original `docs/` and `NewDocs/` folders were deleted at the user\'s request. "Original local path" therefore names the file\'s location inside this tree for anything that used to live there; files under `220 account data /` and `~/Downloads` were left in place.', '', 'One block per important file: where it came from, where it lives now, which version it is, and what replaced it. Generated by the documentation build on 2026-09-25 from the Gmail threads, the local folders and ~/Downloads. IDs are stable and are referenced from MASTER_DOCUMENT_INDEX.md and DECISION_LOG.md.', '',
       '- **CLIENT** = authored/sent by BridgeAI (Dhruvi Patel, Konika Thakur, Sahaj Khunteta). **CLIENT DATA** = vendor exports the client delivered. **INTERNAL** = written by the delivery team. **GENERATED** = produced by a tool.',
       '- "NOT ON THIS MACHINE" = the email/Drive record proves the file exists but no local copy was found anywhere under the home directory; a `.MISSING.md` placeholder sits where the file should go.', '']
    for r in rows:
        L.append(f"## {r['id']} — {r['name']}")
        L.append('')
        L.append(f"| Field | Value |\n|---|---|")
        L.append(f"| Origin | {r['origin']} |")
        L.append(f"| Received from | {r['sender']} |")
        L.append(f"| Email / channel | {r['channel']} |")
        L.append(f"| Date | {r['date']} |")
        L.append(f"| Version | {r['version'] or '-'} |")
        L.append(f"| Status | **{r['status']}** |")
        L.append(f"| Supersedes | {r['supersedes'] or '-'} |")
        L.append(f"| Superseded by | {r['superseded_by'] or '-'} |")
        L.append(f"| Original local path | {r['local_path'] or 'none found'} |")
        L.append(f"| In this structure | {', '.join('`'+c+'`' for c in r['copied'])} |")
        L.append(f"| Size / md5 | {('%.1f KB' % (r['size']/1024)) if r['size'] else '-'} / {r['md5'] or '-'} |")
        L.append(f"| Used for | {r['used_for']} |")
        if r['notes']: L.append(f"| Notes | {r['notes']} |")
        L.append('')
    (OUT/'00_INDEX/PROVENANCE_REGISTER.md').write_text('\n'.join(L))
    print('entries', len(rows), 'copied', sum(1 for r in rows if r['local_path'] and any(not c.endswith('.LINK.md') for c in r['copied'])), 'linked', sum(1 for r in rows if any(c.endswith('.LINK.md') for c in r['copied'])), 'missing', sum(1 for r in rows if not r['local_path']))
if __name__=='__main__': main()
