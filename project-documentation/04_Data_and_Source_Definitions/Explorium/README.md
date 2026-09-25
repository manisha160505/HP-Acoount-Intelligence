# Explorium (Source A)

| Field | Value |
|---|---|
| What it contains | One workbook per account (`<NAME>_explorium_data.xlsx`, 220 files in `explorium_clean_220`), same 18-sheet layout as the Astra seed `Source A.xlsx`: 1_Firmographics, 2_Company_Hierarchy, 2_Subsidiaries, 3_Funding_Overview / Rounds / Advisors / Investors, 4_Technographics (20 category columns + Full Tech Stack), 5_Webstack, 5_Tech_Breakdown, 6_Workforce_Trends, 7_Company_Ratings, 8_Website_Traffic, 9_Social_Media, 10_Intent_Topics, 11_intent_score (Bombora composite topics), 12_Hiring_Events, 13_News_Events (empty), 14_Prospect_Contacts (**empty in all 220**). |
| Who provided it | Konika Thakur / Dhruvi Patel (BridgeAI). Vendor: Explorium. |
| Where it came from | Google Drive folder 1eZvNHHKo_WZyoYWJbPB_FHZl04vLiw25 (18 Sep 2026); seed from Konika's 31 Aug mail. Local: `220 account data /explorium_clean_220(.zip)`; seed `Explorium/seed_Astra/Source A.xlsx`. |
| Accounts covered | 220 workbooks (all matched to the master list). Hierarchy 165/220; technographics 207/220; intent score 173/220 (per the 24 Sep review). Fetched by Company Name + Country + business id; the domain is returned by Explorium (DEC-013). |
| Features using it | Executive Dashboard (firmographics, hierarchy), Technographic Map (4/5 sheets), Intent & Demand (10/11), Stakeholder Map (14, empty), Objection Playbook, Content Messaging, Strategy Chat, urgency (employees range, tech stack, 11_intent_score). |
| Known gaps | Contacts sheet empty everywhere; 13_News_Events empty; identity blank on 209/219 rows; Level Of Intent column empty; no detectedVia / first-seen for technologies; 141 field conflicts resolved by the vendor toward the global HQ (D2). |
| Data-quality issues | Blank domains for Public Bank and Westpac; global.pioneer is not a working domain; two accounts share domains (Jabil, MUFG); duplicate company names (3 Ministries of Defence, 2 Westpacs) disambiguated by country suffix in the split. |
| Authoritative or supporting | **Authoritative** for firmographics, hierarchy, technographics (client: "WebStack and Tech_Breakdown sheets … also related to technographic data"), Bombora topic intent. Contacts: not a source (empty). |

Copies here: `seed_Astra/Source A.xlsx`, `seed_Astra/firmographics.csv`. The 220 workbooks are linked, not copied (`explorium_clean_220.zip.LINK.md`).
