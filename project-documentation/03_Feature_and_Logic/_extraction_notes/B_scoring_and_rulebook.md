> GENERATED EXTRACTION NOTES — produced 25 Sep 2026 by an automated read of the plain-text conversions of the source documents. INTERNAL. Not client text. Verify any number, rule id or quote against the original document in 01_Client_Provided/ or 02_Decision_Maker/ before relying on it. Line numbers refer to the text conversions, not to Word pages.

# B. Scoring and Rulebook documents: index and rules register

Source folder: `/private/tmp/claude-501/-Users-yogeshyadav-Desktop-HP/68b93453-1a17-46aa-af1d-f4f252bca985/scratchpad/text/`
All quotes are from the plain-text extractions. Where an extraction looks damaged, this report says so. The report does not resolve any disagreement.

Doc keys used in this report:

| Key | File | Author / sent | Status |
|---|---|---|---|
| D1 | HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook.txt | Client (Dhruvi), 17 Sep 2026 | A later "_FINAL_" version was sent 23 Sep 2026. It is **not available locally**, so this report may be out of date for D1. |
| D2 | HP_Recommendation_Tuning_Logic_FINAL_v4.txt | Client (Dhruvi), 23 Sep 2026 | Replaces "HP_220_Account_Recommendation_Logic(1).pptx" (15 Sep). That deck is not available locally. |
| D3 | HP_Urgency_Score_Updated_Final.txt | Client (Dhruvi), 16 Sep 2026 | |
| D4 | HP_Live_Signal_Scoring_Logic.txt | Client (Dhruvi), 17 Sep 2026 | |
| D5 | HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.txt | Client (Dhruvi), 18 Sep 2026 | Replaces the non-FINAL version from 17 Sep. That version is not available locally. |
| D6 | HP-Account-Intelligence-Rules_1_.txt | **Internal delivery team (Manisha Parwani)**. Sent to the client on 10 Sep 2026. The client has not replied. | This file is byte-identical to `HP-Account-Intelligence-Rules.txt`. |
| R* | Reference files (Care Pack, Q426, Lifecycle, new_file_explanation, HP IQ, Wolf) | Client, 17-18 Sep 2026 | See §1.7 |

---

## 1. Per document

### 1.1 D1: Combined Product, Services and Solutions Rulebook
- **Title inside:** "HP 220 Account Rulebook", with the subtitle "Product, services and solutions rules for RAG recommendations".
- **Version and date markers inside the doc:**
  - The doc has no version number of its own.
  - The source-status table gives these source versions: "HP Care Pack Services Definitions — February 2026 Revision 4"; "HP Q426 Services and Solutions final workbook — Catalogue of 2,186 populated service rows and 287 expanded service descriptions"; "HP IQ for Enterprise — Version 1.0"; "HP Wolf Security Portfolio — February 2026 portfolio and comparison slides"; "HP WXP and DEX ROI Calculator pages — Official HP web content".
  - Guardrail 10 says embargo dates "are already past as of 24 Aug 2026".
- **Sections:**
  - How to use this rulebook
  - Rulebook structure
  - **Part A, Hardware product rules:** Rules 1-18
  - **Part B, Services and solutions rules:**
    - Source status and Opportunity routing
    - WXP 01-13 and CARE 01-20
    - LIFE 01, 02, 03, 05. LIFE 04 is absent from the extraction.
    - DEPLOY 01-15, POLY 01-05, PRINT 01-03, SCAN 01-03
    - IQ 01-12 and the HP IQ compatibility table
    - WOLF 01-20 and the Wolf selection matrix
  - **Part C, Common and specific guardrails:**
    - C 01-10
    - Product-specific guardrails numbered 2, 3, 4, 5, 7, 10, 15 and 16. Numbers 1, 6, 8, 9 and 11-14 are absent.
    - Service guardrails G 06-15, 17 and 18. G 01-05 and G 16 are absent.
    - Exact country restriction lists
- **Purpose:** This is the runtime source of HP facts for RAG recommendations. It says "All runtime product and service facts must come from this rulebook; the original HP files are provenance and review records only."
- **Features it governs:** every feature that names an HP product, service or solution: Executive Dashboard, Live Signals, Intent & Demand, Stakeholder Map, Opportunity Map, Technographic Map / Tech Landscape, and Content Messaging. new_file_explanation (R5) also lists "Objecti…" (Objection Playbook, cut off in the extraction) and Strategy Chat. D5 uses it to validate Driver 1, and D3 refers to it for Depth evidence.

### 1.2 D2: Recommendation Tuning Logic FINAL v4
- **Title inside:** "HP Account Intelligence -Recommendation Tuning Logic", with the subtitle "Feature-specific recommendation logic with seller-facing examples".
- **Version and date markers inside the doc:** there is no version string in the text; "FINAL_v4" appears only in the filename. The doc calls itself "the finalized recommendation logic". The examples mention "ingested in September 2026", BHP news from "Jul 2026", and Astra "In 2025".
- **Sections:**
  - "Implementation Additions for Recommendation Engine":
    - A. Shared Input Contract
    - B. Shared Evidence-Processing Layer
    - C. Evidence-Strength Tiers and Permitted Language
    - D. Thin-Account Path
    - E. Data As-of-Date Control
    - F. Internal Output Schema
    - G. Feature-Specific Output and Formatting Constraints
  - The Recommendation Logic Table, one row per feature, preceded by a "Shared Rulebook + Case Study Rule". The Intent & Demand and Technographic Map rows have duplicated or shifted cells in the extraction.
  - H. Case Study / Proof Library Rules
  - I. HP Claim Sourcing Rule
  - J. Lifecycle
  - K. Banned-Output Examples / Negative Tests (4 cases)
  - "BHP - North Star Examples" (7 features)
  - "3)Rules" (14 principles). The heading "3)" suggests the original has sections "1)" and "2)", but they are not labelled that way in the extraction.
- **Purpose:** defines the shared recommendation engine: inputs, evidence processing, evidence-strength tiers, as-of date, output schema and word limits. It also defines what each feature generates.
- **Features it governs:** Executive Dashboard, Live Signals, Intent & Demand, Stakeholder Map, Opportunity Map, Technographic Map and Content Messaging. These cover the recommendation and prose layer only; D2 contains no numeric scores.

### 1.3 D3: Urgency Score
- **Title inside:** "HP Account Urgency Score Final Logic", with the subtitle "Scoring rules for the 220-account intelligence platform, with a worked Astra example".
- **Version markers inside the doc:**
  - "Final" appears in the title.
  - The doc records a change: "The former standalone Hiring and Workforce Demand driver has been removed … The 30% weight preserves the previous combined 15% Hiring + 15% Growth weighting."
  - Dated example values: 31 July 2025 and 30 June 2026 associated_members; "2026 news".
- **Sections:**
  - Overall scoring model
  - 1. Workplace Technology and OS Opportunity (A Account scale, B OS environment, C Workplace technology footprint)
  - 2. AI and Workstation Opportunity (A AI/ML Breadth + Depth, B Workstation intent, C Recent AI initiatives)
  - 3. Growth and Expansion Signals (A Workforce growth proxy, B Recent hiring volume, C Verified Growth and Expansion Events)
  - 4. HP Solution Intent (A Category intent strength, B Trend, C Buying stage, D Research volume)
  - Astra worked result
- **Purpose:** produces an account-level urgency score from 0 to 100.
- **Features it governs:** the account urgency score. The doc does not name a page, but the score is used for account prioritisation on the Executive Dashboard or account list.

### 1.4 D4: Live Signal Scoring Logic
- **Title inside:** "HP Live Signal Scoring Logic", with the subtitle "Final Scoring Framework".
- **Date markers inside the doc:** the Astra example uses "Scoring date: 17 September 2026" and "Publication date: 23 April 2026".
- **Sections:**
  1. Purpose
  2. Final Live Signal Formula
  3. Driver 1, Recency
  4. Driver 2, Signal Relevance & Impact (includes the No-inference rule)
  5. Driver 3, Source Reliability
  6. Final Worked Astra Example
  7. Final Processing Rule
- **Purpose:** gives each unique underlying event a score out of 10.
- **Features it governs:** Live Signals.

### 1.5 D5: Tech Landscape Confidence Scoring Logic FINAL
- **Title inside:** "Tech Landscape Confidence Score".
- **Version markers inside the doc:** there is no date or version inside. "FINAL" appears only in the filename. The doc refers to an "Example from current UI".
- **Sections:**
  - What the confidence on each Tech Landscape card means
  - 1. Final scoring structure
  - 2. Driver 1, HP-Relevant Technology Evidence (with the Astra example)
  - 3. Driver 2, HP-Category Intent Support (with the Astra example)
  - 4. How to calculate the final card confidence
- **Purpose:** produces a confidence percentage for each Tech Landscape card (technology, position and HP recommendation).
- **Features it governs:** Tech Landscape / Technographic Map.

### 1.6 D6: Delivery team's Rules doc (internal)
- **Title inside:** "HP Account Intelligence — Rules, Guardrails & Logic".
- **Version and date markers inside the doc:** none. It cites code line references such as `grounding.py:19`, `:119` and `scripts/audit_grounding.py`.
- **Sections:**
  1. Engine-wide rules
  2. Shared grounding layer
  3. Scoring & prioritisation (Stakeholder composite, Priority Contact threshold, Influence cascade, Live Signals confidence, Opportunity Map has no numeric score)
  4. Signal -> HP opportunity (Steps 1-4 and the Overclaim guard)
  5. Recommendation logic (Who to approach, Influence-bounded wording, Resources and proof points)
  6. Live Signals gates (Gate 0, Deduplication, Sales-angle guards, Rationale grounding)
  7. Objection Playbook rules
- **Purpose:** describes what the delivery team built. Scoring, gates, grounding and wording guards are implemented in code. It predates D2, D3, D4 and D5.
- **Features it governs:** Stakeholder Map, Live Signals, Opportunity Map, Objection Playbook, and grounding across all features.

### 1.7 Reference materials (R1-R6)
- **R1 HP_Care_Pack_Services_Definitions.txt** (253 lines):
  - An HP glossary of Care Pack terms, headed "HP Care Pack Service Definitions". It opens with "Consult the applicable service datasheet for complete details and terms".
  - Terms covered include the warranty indicators 1/1/0, 3/3/0, 1/1/1 and 3/3/3; "2-hour SW phone-in response"; 24x7; 9x5; 4-hour response; NBD; NBD Exchange ("before 2:00 p.m."); Priority Services ("over 60 countries"); Peripheral Care Pack ("up to six peripherals … maximum of 2 displays"); Travel Support ("80 covered countries"); Customer Assurance Manager; PDA; Out-of-Band Remediation (vPro only); and more.
  - Footer: "4AA5-4980ENW, Feb 2026, Rev 4" and "© 2017, 2025". This matches D1's source status.
- **R2 HP_Q426_Services_and_solutions_final.txt** (62 lines, **truncated**):
  - A single-sheet extraction, "Sheet1 (max_row 2187 max_col 7)", with the columns SKU, Service Description, Remarks, Remarks2-4 and Expanded Service Description.
  - Only about 60 Care Pack SKU rows are present, for example "UG4V7E / HP 3y ONS PDA PA NB / Premium+". The file ends with "... (truncated)".
  - 2,186 data rows is consistent with D1's "2,186 populated service rows".
- **R3 Copy_of_HP_Lifecycle_as_of_June_2026_Filtered.txt:** **empty or failed extraction.** The file contains only "ERROR File is not a zip file". Its content cannot be described.
- **R4 new_file_explanation_220_acc.txt:** a 12-row map from file to feature. Cell text is **truncated at about 120 characters**. Key points:
  - filings 1.csv feeds the Executive Dashboard, Live Signals, Opportunity Map, Content Messaging and Strategy Chat.
  - The Care Pack, Q426, HP IQ and Wolf files are "Not used separately - included in Combined HP Rulebook".
  - The Rulebook and hp_case_studies_final.csv feed most features.
  - The tech landscape and live signal logic docs map to their pages.
  - "HP Lifecycle June 2026 — Not used as of now … Not being used in the platform currently".
  - "HP 220 account recommendation logic(1) — Not used as of now. Some changes need to be made after discussing them with Sahaj…"
- **R5 HP_IQ_for_Enterprise.txt:** **empty or failed extraction** ("ERROR File is not a zip file"). The HP IQ content is available only through D1 (IQ 01-12).
- **R6 Wolf_Security_Portfolio.txt:** **empty or failed extraction** ("ERROR File is not a zip file"). The Wolf content is available only through D1 (WOLF 01-20 and the matrix).

---

## 2. Rules register

**Type key:** formula / threshold / precedence / guardrail / mapping / fallback / UI.

### 2.1 D1 Rulebook: usage and Part A (hardware)

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D1 | How to use | "Find the verified account need. Do not start with an HP product, service, or solution name." | All recommendation features | precedence |
| D1 | How to use | Opportunity types: "hardware, workforce experience, security, support, lifecycle, deployment, Poly, print and scan, enterprise AI, or a valid combination." | All | mapping |
| D1 | How to use | "If a required condition is missing, don't use that fact. Do not invent a fact or force a recommendation." | All | fallback |
| D1 | Part A intro | "The account signal alone is not enough; the user type, scale, device type, and exact configuration must also fit." | All hardware recs | guardrail |
| D1 | A Rule 1 | Enterprise AI → "HP EliteBook 8 G2 Series … up to 50 TOPS NPU … up to 64GB memory where supported … Do not choose it from an AI signal alone" | Opp Map, Exec Dash, Content, Tech Map | mapping / guardrail |
| D1 | A Rule 2 | Enterprise AI at scale → "EliteBook 6 G2 … up to 50 TOPS on Next Gen variants; up to 64GB memory" "when the account needs enterprise AI across a large, repeatable fleet" | same | mapping |
| D1 | A Rule 3 | SMB AI refresh → "ProBook 4 G2 … 13/14/16-inch … up to 50 TOPS NPU; up to 68Wh battery" | same | mapping |
| D1 | A Rule 4 | Executive → "EliteBook Ultra G1i … up to 48 TOPS NPU … 9MP + IR camera … under 1.2kg … 3K OLED … 180-degree panel" | same | mapping |
| D1 | A Rule 5 | ARM → "EliteBook Ultra G1q / G1q8 … 45 TOPS NPU; G1q 12-core vs G1q8 8-core … up to 50% in 30 minutes … 14.4mm max height; 14-inch 2.2K" "only when ARM/Snapdragon fits … Do not replace Intel/AMD recommendations without a reason." | same | mapping / guardrail |
| D1 | A Rule 6 | Security → "Never copy a security feature from one model to another model." "quantum-resistant firmware claims only where allowed" | same | guardrail |
| D1 | A Rule 7 | Hybrid work → "exact 5MP/9MP camera spec for the selected model … First choose the right product family … Then use only the collaboration features from that exact product." | same | precedence |
| D1 | A Rule 8 | Lenovo X1 Carbon Gen 13 → "up to 85% higher CPU performance … Cinebench … up to 61% better office productivity … Procyon … 44% less keycap wobble … Keep the benchmark setup, date, and disclaimer" "only when the exact Lenovo competitor matches" | Tech Map, Objection Playbook, Opp Map | mapping / guardrail |
| D1 | A Rule 9 | Edu/Gov/RFP → "HP 200 G2 … dTPM 2.0 … up to 68Wh battery; 14/16-inch … subject to tender and country requirements" | same as Rule 1 | mapping |
| D1 | A Rule 10 | Expandable desktop → "EliteDesk 8 Tower G1i … Up to Intel Core Ultra 9; 13 TOPS NPU … 4 PCIe slots; up to 128GB DDR5; up to 11 native USB ports; up to 8 displays" | same | mapping |
| D1 | A Rule 11 | Compact / branch → "EliteDesk 8 Mini G1i / ProDesk 4 Mini G1i … 13 TOPS NPU … EliteDesk up to 7 displays … up to 10 USB ports" "Elite is the stronger enterprise option; Pro is the more value-focused option." | same | mapping / precedence |
| D1 | A Rule 12 | Integrated display → "EliteStudio 8 AiO G1i / ProStudio 4 AiO G1i … 27/23.8-inch … 5MP camera … optional RTX 5050" | same | mapping |
| D1 | A Rule 13 | Smaller-footprint desktop → "EliteDesk 8 SFF G1i … 13 TOPS NPU … 3x M.2 SSD up to 6TB … up to 128GB DDR5; up to 8 displays; up to 11 native USB ports" "when Mini is too limited but Tower is larger than needed" | same | mapping |
| D1 | A Rule 14 | ESG → "Do not choose a product only because of sustainability. Choose the product from the business need first" "Keep country/status limits and source date." | same | precedence / guardrail |
| D1 | A Rule 15 | Serviceability → "Do not turn this into an AI story unless there is also AI evidence." | same | guardrail |
| D1 | A Rule 16 | 5G / mobile → "Use Ultra/Elite for mobile executives and EliteBook/ProBook for broader mobile workforces … Do not treat HP Go as available everywhere." | same | mapping / guardrail |
| D1 | A Rule 17 | Persona routing → "BPS Portfolio Sell-In Deck FY26 … Leadership, Frontline, Specialist, Generalist … Elite = premium … Pro = SMB/mid-market … Chrome = speed/simplicity; Thin Client = cloud-first/virtualized; Fortis = education." "Use this deck first to choose the HP family." | All hardware recs | precedence / mapping |
| D1 | A Rule 18 | Why AI PCs now → "Do not use HP messaging as proof that the account is adopting AI." | Exec Dash, Content, Opp Map | guardrail |

### 2.2 D1 Rulebook: Part B (services and solutions)

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D1 | B Opportunity routing | Workforce experience → WXP; Security → Wolf; Support → Care; Lifecycle; Deployment; Poly support; Print and scan; "Enterprise AI — AI-PC rollout plus a specific employee workflow and compatible managed environment → HP IQ rules" | All rec features | mapping |
| D1 | WXP 01 | Employee tech complaints / downtime / DEX initiative → "Recommend WXP as a workforce enablement platform" | Opp Map, Tech Map, Content | mapping |
| D1 | WXP 02 | "Do not name a Standard, Professional, or Elite tier for a capability" | same | guardrail |
| D1 | WXP 03 | Large/distributed fleet, limited visibility → WXP telemetry and fleet analytics | same | mapping |
| D1 | WXP 04 | "Verified Windows, macOS, or Android estate, multiple manufacturers, or fragmented endpoint environment" → WXP multi-vendor. "Do not say that every device, operating-system version, agent, or integration is supported." | same; used by D5 Driver 1 | mapping / guardrail |
| D1 | WXP 05 | Sentiment / engagement → pulse surveys and self-help. "Do not assign these capabilities to a named WXP tier" | same | mapping / guardrail |
| D1 | WXP 06 | Identify issues before users report them → predictive analytics | same | mapping |
| D1 | WXP 07 | "ServiceNow, Microsoft Intune, Power BI, Power Automate, Tableau, and Microsoft Entra ID as integration routes. Mention only the integration that matches … Existing use shows possible fit, not buying intent." | same; D3 Workplace tech; D5 Driver 1 | mapping / guardrail |
| D1 | WXP 08 | "Treat WXP Collaboration as a separate licence; do not present it as included in every WXP licence." | same | guardrail |
| D1 | WXP 09 | DEX ROI Calculator: "only as an estimate calculated from the customer inputs … not as a guaranteed saving" | same | guardrail |
| D1 | WXP 10 | Device refresh + DEX: "Recommend the HP device and WXP as separate components … do not state that the customer needs an all-HP fleet." | same | guardrail |
| D1 | WXP 11 | "Standard, Professional, and Elite, with licence-and-support terms from one to five years … must not choose a tier automatically … label tier selection as pending HP input." | same | guardrail / fallback |
| D1 | WXP 12 | Enhanced Onboarding Service: "Recommend only the named onboarding service and do not add any deliverables." | same | guardrail |
| D1 | WXP 13 | "WXP Premium Support is available for one, two, three, four, and five years … do not promise a response time" | same | guardrail |
| D1 | CARE 01 | Response types: onsite, NBD, "four-hour … within four hours after receiving and acknowledging", "third-day … on the third coverage day", Standard Response. "it does not mean the issue is resolved. Service level and response time vary by geography." | Opp Map, Content | mapping / guardrail |
| D1 | CARE 02 | Accidental Damage Protection: "optional add-on … Do not describe intentional damage, loss, theft, or every type of damage as covered." | same | guardrail |
| D1 | CARE 03 | Travel Support: "hardware support across 80 covered countries … Do not promise the same response time … in every country." | same | mapping / guardrail |
| D1 | CARE 04 | Exchange types kept separate. NBD Exchange: "requests received before 2:00 p.m. on a business day are shipped for next-business-day delivery" | same | mapping |
| D1 | CARE 05 | Defective Media Retention: "Do not describe this as data recovery or data backup." | same | guardrail |
| D1 | CARE 06 | Computer Tracing: "Do not state that the device will always be found, recovered, or successfully erased." | same | guardrail |
| D1 | CARE 07 | Data Recovery: "Do not guarantee full recovery." | same | guardrail |
| D1 | CARE 08 | Predictive Detection and Alerts: "anticipate potential PC hardware issues and notify … before the issues occur" | same | mapping |
| D1 | CARE 09 | Priority Services: "more than 60 countries and more than 20 languages" | same | mapping |
| D1 | CARE 10 | Out-of-Band Remediation: "only for commercial PCs with Intel vPro processors" | same | guardrail |
| D1 | CARE 11 | In-Warranty applies "while the device is covered by the base HP Limited Warranty"; Post Warranty applies "after the base warranty has expired" | same | mapping |
| D1 | CARE 12 | Pickup and Return / Return to Depot: "Do not describe either service as onsite." | same | guardrail |
| D1 | CARE 13 | Peripheral Care Pack: "up to six peripherals, including no more than two displays" | same | threshold |
| D1 | CARE 14 | Software Support: "only for HP software and selected third-party products supported by HP" | same | guardrail |
| D1 | CARE 15 | Installation service for HP PCs or printers | same | mapping |
| D1 | CARE 16 | "three-, four-, and five-year support combinations … Do not choose a combination unless the product type, term, response type, and included add-ons match" | same | guardrail |
| D1 | CARE 17 | Premium / Premium Plus: "only when every included component is supported by separate verified account evidence. Do not recommend a bundle only because it exists in the catalogue." | same | guardrail |
| D1 | CARE 18 | "Priority Access only for a personal-computer estate of at least 250 seats. Available terms are one, three, four, or five years." | same | threshold |
| D1 | CARE 19 | "Priority Access Plus only for … at least 1,000 seats." Terms 1, 3, 4 or 5 years | same | threshold |
| D1 | CARE 20 | "Priority Management only for … at least 5,000 seats." Terms 1, 3, 4 or 5 years | same | threshold |
| D1 | LIFE 01 | Device Life Extension: "HP collects the existing PCs and professionally optimizes them" | same | mapping |
| D1 | LIFE 02 | Carbon Emissions Sync: "estimates and offsets carbon emissions" | same | mapping |
| D1 | LIFE 03 | To The Door / To The Door Usage: "Select only the route matching the device category" | same | mapping |
| D1 | LIFE 05 | "Preventive Maintenance is for printers only … includes no parts." Maintenance Kit Replacement includes parts | same | mapping / guardrail |
| D1 | DEPLOY 01 | Imaging Service: "unlimited required drivers, up to three applications, and up to three operating-system setting additions … GHO, WIM, SWM, FFU, and ZIP for Clonezilla" | same | threshold / mapping |
| D1 | DEPLOY 02 | Advanced Imaging: "one image for multiple PC platforms … unlimited application installs … PPKG injection requires HP Application and Package Installation Service … customer must review and approve" | same | mapping / guardrail |
| D1 | DEPLOY 03 | App/Package Install: "EXE, MSI … no single file may exceed 15 GB … must not reboot … only PPKG and VMware/WICD packages" | same | threshold |
| D1 | DEPLOY 04 | OS Version Control: "only for an HP OEM Corporate-Ready image … N, N-1, and N-2 … Windows 11 21H2 and Windows 10 21H2, 21H1, and 20H2 … Do not present the listed Windows versions as current" | same | guardrail |
| D1 | DEPLOY 05 | Provisioning Connect: "SCCM task sequences … global coverage except Brazil and Argentina" | same | guardrail (country) |
| D1 | DEPLOY 06 | Device Registration vs Standalone Device Registration: "Keep the two services separate." | same | guardrail |
| D1 | DEPLOY 07 | Hardware Hash / PKID reporting: "Do not claim any other report format or delivery method." | same | guardrail |
| D1 | DEPLOY 08 | Standard BIOS Settings; linked to Sure Admin and Tamper Lock. "Do not apply these features to an unsupported platform." | same | guardrail |
| D1 | DEPLOY 09 | BIOS Revision Control: "customer must specify the required BIOS revision" | same | mapping |
| D1 | DEPLOY 10 | Custom-Logo BIOS: "logo in the HP-defined format and size" | same | mapping |
| D1 | DEPLOY 11 | Sure Recover Custom Restore: "HP Pro, HP EliteBook, and HP ZBook devices" | same | mapping |
| D1 | DEPLOY 12 | Hardware Integration: requires "technical feasibility … procurement validation … forecasts" | same | guardrail |
| D1 | DEPLOY 13 | Asset tagging: "integrated reporting three business days after shipment" (Standard and Customer-Supplied) | same | mapping |
| D1 | DEPLOY 14 | Custom Security Tagging / StopTrack: "Do not describe the label as active device tracking or guarantee recovery." | same | guardrail |
| D1 | DEPLOY 15 | Drop-in packaging: "HP must first confirm that the items fit" | same | guardrail |
| D1 | POLY 01 | Poly Plus vs Partner Poly: "one- or three-year terms … do not combine them." | same | guardrail |
| D1 | POLY 02 | "do not attach onsite support to an entry that is not labelled with Onsite Support" | same | guardrail |
| D1 | POLY 03 | Poly Elite: "one- or three-year terms … do not add [further service-level benefits]" | same | guardrail |
| D1 | POLY 04 | Enterprise: "one-year … group: A, B, C, D, or E … Do not use a New entry for a renewal" | same | guardrail |
| D1 | POLY 05 | Reactivation Fee: "less-than-one and greater-than-one bands. Keep reactivation separate" | same | threshold / guardrail |
| D1 | PRINT 01-03 | Direct Print & Insights Cloud; Secure Print Enterprise Package Cloud; Secure Release & Insights Cloud: "electronic licences for one, three, four, and five years … Recommend only the named licence and term" | same | guardrail |
| D1 | SCAN 01 | "10,000, 50,000, 500,000, 1 million, 2 million, and 4 million credits. Choose the smallest listed bundle that meets the verified credit requirement" | same | threshold / precedence |
| D1 | SCAN 02 | Scan AI Basic Low / Basic High / Advanced: "must not choose among the three routes until HP supplies the missing threshold or scope." | same | fallback (pending) |
| D1 | SCAN 03 | Incremental Professional Hours: "do not invent an hour quantity" | same | guardrail |
| D1 | IQ 01 | HP IQ v1.0: "begins in the United States and in English, requires a PC with an NPU, and provides a limited experience on devices with 16 GB RAM or less." Requires "an employee workflow covered by IQ 02 to IQ 11" | same | guardrail / threshold |
| D1 | IQ 02-06 | Ask IQ; Analyze ("PDF, TXT, DOC, and PPT" only); Knowledge; Meeting Agent; Performance Optimization ("Do not promise a particular speed, battery … improvement") | same | mapping / guardrail |
| D1 | IQ 07 | Single Click Join: "Require supported Poly X32, X52, or X72 environment, shared tenancy, authorization, and IT-managed setup." | same | guardrail |
| D1 | IQ 08 | NearSense Share: "Require NearSense-enabled devices." | same | guardrail |
| D1 | IQ 09 | HP Product Help: "Do not describe it as a Care Pack, warranty service…" | same | guardrail |
| D1 | IQ 10 | Manageability: Intune, WXP opt-in, Entra ID, telemetry, NearSense and feedback controls | same | mapping |
| D1 | IQ 11 | "Daniel example … do not claim that every HP IQ feature works offline." | same | guardrail |
| D1 | IQ 12 | "Recommend the device and HP IQ separately." | same | guardrail |
| D1 | IQ compat | Notebooks: "EliteBook X, EliteBook 8, EliteBook 6, ProBook 4, ZBook X, and ZBook 8". Desktops: "EliteBoard, EliteDesk 8, and select workstations". Poly X32/X52/X72 | same | mapping |
| D1 | Wolf intro | "Use the generic security signal only as a starting point." | same | precedence |
| D1 | WOLF 01 | "Do not recommend a generic Wolf Security bundle." | same | guardrail |
| D1 | WOLF 02 | Wolf Security for Business: "Do not use for non-HP PCs." | same | guardrail |
| D1 | WOLF 03 | Wolf Pro Security Edition: "Licence is attached to hardware and non-transferable." Micro/SMB | same | mapping |
| D1 | WOLF 04 | Wolf Pro Security: "HP and non-HP Windows 10 or Windows 11 PCs … can transfer … cloud management" | same | mapping |
| D1 | WOLF 05 | Sure Click Enterprise: mid-market/enterprise. "Antivirus and malware-prevention components marked customer choice are not included by default." | same | mapping / guardrail |
| D1 | WOLF 06 | Credential protection: "Wolf Security for Business does not show this feature" | same | guardrail |
| D1 | WOLF 07 | "Do not imply that all four offerings protect the same file types…" | same | guardrail |
| D1 | WOLF 08 | Wolf Security Controller only with an eligible tier. SIEM via "syslog, STIX, or TAXII" | same | guardrail |
| D1 | WOLF 09 | Primary AV: "WPS Malware Prevention is the documented antivirus-replacement route. Do not apply this claim to another Wolf offering." | same | guardrail |
| D1 | WOLF 10 | Fileless attacks → Wolf Pro Security only | same | guardrail |
| D1 | WOLF 11 | Sure Access Enterprise for privileged remote access | same | mapping |
| D1 | WOLF 12 | Protect and Trace WiFi / with Wolf Connect: "offline or powered-down capability only for Protect and Trace with Wolf Connect" | same | guardrail |
| D1 | WOLF 13-16 | Sure Start/Sure Admin; Enterprise Security Edition (tampering/supply chain); Sure Recover / Flash ("Do not say that recovery restores customer data"); embedded features: "Do not copy an embedded feature from one HP model to another." | same | mapping / guardrail |
| D1 | WOLF 17 | "Recommend hardware and security separately." | same | guardrail |
| D1 | WOLF 18 | "Do not attach paid management features to Wolf Security for Business." | same | guardrail |
| D1 | WOLF 19 | "Sure Click Enterprise licence and support only for 500 to 999 seats. Available terms are one, two, three, four, and five years." | same | threshold |
| D1 | WOLF 20 | SCE professional services: "44-hour prepaid deployment … one-hour hourly resource … one-year full-time onsite engineer" | same | mapping |
| D1 | Wolf matrix | 4 offerings × segment / device support / licence (for example, WSfB "Free on eligible HP commercial PCs; perpetual") | same | mapping |

### 2.3 D1 Rulebook: Part C (guardrails)

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D1 | C 01 | "HP materials cannot prove that the account has a problem, initiative, technology, competitor, or buying intent." | All | guardrail |
| D1 | C 02 | "Source names are provenance only; the engine must not reopen the original HP files during recommendation generation." | All | guardrail |
| D1 | C 03 | "Do not copy facts between offerings." | All | guardrail |
| D1 | C 04 | "Keep every country, device, operating-system, configuration, benchmark, licence, term, seat-count, warranty, registration, and availability condition" | All | guardrail |
| D1 | C 05 | "Do not present an optional, add-on, customer-choice, separately activated, or configuration-dependent feature as standard." | All | guardrail |
| D1 | C 06 | "Give one main recommendation. Add another product or service only when separate verified evidence supports it." | All | precedence |
| D1 | C 07 | "leave out the recommendation or label the missing condition clearly. Do not send the engine back to the original HP material." | All | fallback |
| D1 | C 08 | "When this rulebook is updated from a newer approved HP source … replace the older fact and keep the new source date and version" | All | precedence |
| D1 | C 09 | "If a source says planned, expected, future … keep that wording until a newer approved source confirms availability." | All | guardrail |
| D1 | C 10 | "Keep HP Confidential, internal-only, encrypted, or HP/partner-only content within its stated audience." | All | guardrail |
| D1 | Product guardrail 2 | Block restricted superlative claims in "Romania, Slovakia, Turkey, UAE, Russia, Armenia, Belarus, Kazakhstan, Kyrgyzstan, Moldova, Tajikistan, Turkmenistan, Ukraine, China, Vietnam, Indonesia, Malaysia, Brazil, or Mexico" (19 countries). "The product can still be recommended" | All hardware recs | guardrail (country) |
| D1 | Product guardrail 3 | Block Lenovo comparison claims in the Competitive restriction list | Tech Map, Objection, Opp Map | guardrail (country) |
| D1 | Product guardrail 4 | "only when the account evidence or user question identifies Lenovo ThinkPad X1 Carbon Gen 13" | same | guardrail |
| D1 | Product guardrail 5 | "85% … Cinebench 2024 … 61% … Procyon Office Productivity … battery-life claims = HP internal video-playback testing; trackpad claim = HP 85 mm x 120 mm vs Lenovo 56.2 mm x 120 mm … Do not turn the percentages into generic HP facts." | same | guardrail |
| D1 | Product guardrail 7 | "HP Go … US subscription service … 5G: … module is configured at the factory, and carrier service is available … Wi-Fi 7: … separately purchased Wi-Fi 7 router … If these conditions are not known … leave the feature out" | All hardware recs | guardrail / fallback |
| D1 | Product guardrail 10 | "Store embargo dates as metadata and block the affected product/processor claim before the embargo date … 20 Mar 2026, 24–25 Mar 2026, and 31 Mar–3 Apr 2026 … already past as of 24 Aug 2026." | All hardware recs | guardrail (date) |
| D1 | Product guardrail 15 | "Next Gen AI PC = 40–60 TOPS NPU; AI PC = below 40 TOPS NPU; non-AI PC = no NPU." | All hardware recs | threshold / mapping |
| D1 | Product guardrail 16 | "Keep G1, G2, G1i, G1a, G1q, G1q8, Flip, Notebook, Mini, SFF, Tower, and AiO records separate." | All hardware recs | guardrail |
| D1 | G 06 | "must not tell the user or itself to check the Care Pack PDF or service datasheet" | Care recs | guardrail |
| D1 | G 07-12 | Location varies service (G 07); "Response does not mean resolution" (G 08); keep service types separate (G 09); Data Recovery "where possible" (G 10); third-party software limit (G 11); vPro check (G 12) | Care recs | guardrail |
| D1 | G 13-15 | HP IQ: device families listed, "NPU is required … limited on devices with 16 GB RAM or less" (G 13); "US and English launch … shared tenancy and authorization created by IT" (G 14); Analyze file types (G 15) | HP IQ recs | guardrail |
| D1 | G 17-18 | Keep Wolf offerings separate; Wolf Connect offline statement only for Protect and Trace with Wolf Connect | Wolf recs | guardrail |
| D1 | Country lists | "These lists apply only to the affected claim or slide. They do not block the product itself." The Lenovo list covers about 90 countries and territories. "Also block in any CIS country covered by the playbook restriction. Store the CIS-country restriction as a market-level block in the rules table, not as a free-text note." | Hardware / competitive | guardrail (country) |

### 2.4 D2 Recommendation Tuning Logic

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D2 | A Input contract | Intent: "hp_intent_results 2(3).xlsx / Intent Data (Wide) … Domain (primary); Company (fallback) … Every 6 months … 0 / No Signal is an explicit signal state; N/A, dash or blank means field unavailable and must not be inferred" | All 7 | mapping / fallback |
| D2 | A | Firmographics: "1_Firmographics … Annually … Blank cell / absent value means unavailable" | All | mapping / fallback |
| D2 | A | Technographics: "4_Technographics … Every 6 months … Blank category / no detected technology means no returned evidence; do not interpret as confirmed absence" | All | fallback |
| D2 | A | PredictLeads Hiring: "job_openings … Every 6 months … No returned job rows or blank field means no available hiring evidence" | All | fallback |
| D2 | A | Google News RSS and Exa: "Weekly … not proof the event did not occur" | All | fallback |
| D2 | A | Filings: "filings 1.csv … Every 6 months … non-success validation/download status means the claim cannot be treated as verified filing evidence" | All | guardrail |
| D2 | A | Contacts: "Apollo_All_Contacts(1).xlsx … Every 6 months … Pending/Review status means do not infer the missing role, authority or contact detail" | Stakeholder Map | guardrail |
| D2 | A | Case studies: "Not an account join … unvalidated record, or unresolved/manual-review item should not be used as seller-facing proof until approved" | All proof | guardrail |
| D2 | A | As-of date for every stream: "Record the date when the dataset is loaded into the recommendation engine." | All | UI |
| D2 | B | "prefer the canonical domain … company name as a fallback. Do not combine evidence from a parent, subsidiary, business unit or geography unless the mapping explicitly supports it." | All | precedence / guardrail |
| D2 | B | Dedup: "same underlying event … Google News RSS, Exa and/or a filing, treat it as one event. Keep the strongest/most direct source … do not count them as independent corroboration." | All; Live Signals | precedence |
| D2 | B | Ranking factors: "direct/verified account evidence, relevance to the active opportunity, source quality, timing … independent corroboration" | All | precedence |
| D2 | B | "pass only the most relevant evidence for the recommendation theme to the LLM" | All | guardrail |
| D2 | C Tier: Opportunity | "At least 2 logically related independent data pipelines supporting the same HP-addressable opportunity in the current loaded account-data snapshot. Duplicate coverage … counts as one pipeline" | All | threshold |
| D2 | C Tier: Conversation Starter | "1 strong, directly relevant signal … without a second independent pipeline". Language: "creates a relevant conversation" / "may warrant discussion" | All | threshold / UI |
| D2 | C Tier: Context Only | "weak/ambiguous, older based on its own event/source date, or does not establish an HP-addressable opportunity … Do not create an HP opportunity or product recommendation." | All | threshold |
| D2 | C | Thresholds are labelled "Initial build threshold" | All | threshold |
| D2 | D Thin account | "If one strong signal exists, return a Conversation Starter … If no HP-addressable evidence exists, return No supported HP play at this time … missing data must reduce recommendation strength, not increase model creativity." | All | fallback / UI |
| D2 | E As-of date | "data_as_of_date is the date the dataset was ingested … not the date the seller happens to open the dashboard … If all data pipelines are ingested together, use one shared as-of date" | All | UI |
| D2 | E | "When a new account-data snapshot is ingested, update the shared data_as_of_date and regenerate the feature outputs" | All | precedence |
| D2 | F Schema | Required: feature, account_id, as_of_date, recommendation_text, claim_ids[], evidence_ids[], confidence_tier. "When used": hp_offering_ids[], proof_ids[] | All | mapping |
| D2 | G | Executive Dashboard "Minimum 100 words; maximum 120 words." | Exec Dash | UI |
| D2 | G | Live Signals "Minimum 70 words; maximum 100 words." | Live Signals | UI |
| D2 | G | Intent & Demand "Minimum 80 words; maximum 90 words." | Intent | UI |
| D2 | G | Stakeholder Map "Minimum 40 words; maximum 100 words." | Stakeholder | UI |
| D2 | G | Opportunity Map "Minimum 80 words; maximum 160 words." | Opp Map | UI |
| D2 | G | Technographic Map "Minimum 70 words; maximum 100 words." | Tech Map | UI |
| D2 | G | Content Messaging "Minimum 90 words; maximum 150 words per pillar." | Content | UI |
| D2 | Shared rule | Rulebook and case studies "must not create the account need. If no relevant Rulebook offering or case study matches … retain the evidence-led recommendation without forcing" | All | precedence / fallback |
| D2 | Table: Exec Dash | Generates "Catalyst Explanation / Implication for HP" from Tech, Intent, Hiring, News, Filings, Firmographics and Contacts | Exec Dash | mapping |
| D2 | Table: Live Signals | "Start with the specific news event … If related signals are not present, surface the event as useful seller context rather than creating an unrelated opportunity." | Live Signals | fallback |
| D2 | Table: Intent | "Group related Intent topics into meaningful themes using scores, volume, trend, stage and researched topics" then corroborate | Intent | mapping |
| D2 | Table: Stakeholder | Generates "How to Open and HP Play Focus" from Contacts plus signals plus qualified Opp Map findings | Stakeholder | mapping |
| D2 | Table: Opp Map | "should be customized to the specific account evidence rather than generated from a single signal" | Opp Map | guardrail |
| D2 | Table: Tech Map | Motions: "displacement, attach, upgrade, coexistence or whitespace" | Tech Map | mapping |
| D2 | Table: Content | Each pillar gets "its own Challenge and HP Benefit" | Content | mapping |
| D2 | H Proof | Keep the "customer name exactly as HP publishes it … source URL and publication date … prefer APJ/APAC proof for APJ accounts" | All proof | precedence |
| D2 | I Claims | "Any HP number, statistic or quantified benefit … must have a verified HP source. If the number cannot be verified, remove only that number/claim — not the whole recommendation." | All | guardrail / fallback |
| D2 | I | "HP IQ for Enterprise and HP Wolf Security decks are HP-internal reference sources … should remain traceable to the relevant source." | All | guardrail |
| D2 | J Lifecycle | "If listed and its applicable PE/EM or lifecycle end date has passed, do not recommend it. If it is approaching lifecycle end, recommend it but also flag it in the backend … not listed … does not block" | All rec features | guardrail / fallback |
| D2 | K1 | "Poly Intent = 0 / No Signal. BANNED: Recommend an active HP Poly motion solely because Cisco WebEx, TelePresence … are detected." | Tech Map, Opp Map, Content | guardrail |
| D2 | K2 | "BANNED: Count the same underlying event from Google News RSS, Exa and/or a filing as multiple independent corroborating signals." | All | guardrail |
| D2 | K3 | "BANNED: State that the account has WXP buying intent because Microsoft Intune or ServiceNow is detected. ALLOWED: … only when a separate account signal establishes a relevant endpoint-experience or fleet-management need." | Tech Map, Opp Map | guardrail |
| D2 | K4 | Lifecycle check applies only to offerings listed in the Lifecycle file | All | guardrail |
| D2 | BHP examples | Case study pairing: "NASA for AI/data-science compute, University of Kansas Health System for WXP/endpoint experience, and Aereco for industrial 3D" — "A case study is supporting proof, not evidence that BHP has the need." | All | mapping |
| D2 | 3) Rules | 14 principles: start from evidence; corroborate; do not hallucinate facts or meaning ("Intent Trend = Increasing means research activity is increasing; it does not mean purchases are increasing"); separate fact from interpretation; match strength to evidence; do not force; do not expand into multiple plays ("should not automatically become a PC refresh + WXP + Wolf Security + Poly + Care Pack"); "Absence of evidence does not mean 'No.'"; account-specific; "Do not expose internal rule IDs … 'Rule WXP07 says..'"; no double-counting; do not invent displacement ("Detection of Dell, Lenovo, Cisco … does not automatically mean the account is dissatisfied"); actionable | All | guardrail / UI |

### 2.5 D3 Urgency Score

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D3 | Overall | "Urgency Score = (Workplace Technology and OS × 20%) + (AI and Workstation × 25%) + (Growth and Expansion × 30%) + (HP Solution Intent × 25%)"; "Each driver is scored out of 100" | Urgency | formula |
| D3 | Overall | "Missing inputs contribute 0 points only to the affected component. The remaining available components are still calculated." | Urgency | fallback |
| D3 | Overall | "For job records, only records dated within the latest 12 months are eligible … both blank-status and closed-status job records are included in the hiring-volume count." | Urgency | threshold |
| D3 | 1A Scale (30 pts) | "50,000 or more 30 / 10,001-49,999 25 / 5,001-10,000 20 / 1,001-5,000 15 / 251-1,000 10 / Below 250 5 / Unavailable 0" | Urgency | threshold |
| D3 | 1B OS (40 pts) | "Linux + Windows 40 / Linux + Apple 35 / Linux + another recognised OS 35 / Windows + Apple 30 / Windows + another 30 / Apple + another 20 / Linux only 30 / Windows only 25 / Apple only 15 / Another recognised OS only 10 / No OS detected 0" | Urgency | threshold |
| D3 | 1B | "Another recognised OS may include ChromeOS, Unix or Android. Where multiple rules apply, use the highest applicable score. The component is capped at 40 points." "Apple iOS is treated as an Apple OS family, not as macOS." | Urgency | precedence / mapping |
| D3 | 1C Workplace tech (30 pts) | Qualifies "only where there is a documented connection to an HP workplace solution, such as HP Workforce Experience Platform (WXP) or HP Anyware" | Urgency | mapping |
| D3 | 1C | Examples: Intune; Entra ID / Azure AD; ServiceNow; Power BI and Tableau; Power Automate; "Microsoft Teams, where supported by approved HP material"; "VMware vSphere / ESXi and VMware Horizon, where the detected environment is relevant to HP Anyware". M365, Google Workspace, SharePoint, Zoom, Webex and Splunk qualify "only where approved HP material establishes a direct HP … relationship" | Urgency | mapping |
| D3 | 1C | "5 or more 30 / 3-4 20 / 1-2 10 / None 0 … capped at 30 points … 12 qualifying technologies still receives 30/30, not 12 × 5 = 60" | Urgency | threshold |
| D3 | 1 Astra | "25 + 40 + 10 = 75/100 … 75 × 20% = 15.00/20". Teams and VMware counted → "2 qualifying … 10/30" | Urgency | formula (example) |
| D3 | 2A AI/ML (70 pts) | "Breadth = 35 points and Depth = 35 points". Breadth source: "Source A, 11_intent_score". Depth: 11_intent_score + 4_Technographics Full Tech Stack | Urgency | formula |
| D3 | 2A Breadth | "4 35 / 3 28 / 2 21 / 1 14 / None 0". Families: "(1) AI / Artificial Intelligence, (2) ML / Machine Learning, (3) Generative AI / GenAI, and (4) LLM / Large Language Models / VLLM … counted once" | Urgency | threshold / mapping |
| D3 | 2A | "Generic analytics, software or technology topics are not counted unless they clearly relate to AI or ML." | Urgency | guardrail |
| D3 | 2A Depth | "20 or more 35 / 15-19 28 / 10-14 21 / 5-9 14 / 1-4 7 / None 0". Each distinct intent signal and each distinct AI/ML technology counted once (for example, PyTorch, TensorFlow, Keras, scikit-learn, Spark MLlib) | Urgency | threshold |
| D3 | 2A | "Depth evidence can indicate potential HP opportunities, but the actual HP recommendation must still satisfy the relevant conditions in the HP product, services and solutions rulebook." | Urgency / recs | precedence |
| D3 | 2A Astra | Breadth "3 core families -> 28/35". Depth "16 detailed AI/ML intent signals … 4 qualifying AI/ML technologies … 20 … -> 35/35". "28 + 35 = 63/70" | Urgency | example |
| D3 | 2B Workstation intent (15 pts) | "Workstation intent points = Workstation intent score / 100 x 15". Astra "2 -> 0.3/15" | Urgency | formula |
| D3 | 2C AI initiatives (15 pts) | "5 points per unique verified AI event within the last 12 months, capped at 15 points." Qualifying events: "AI, machine learning, generative AI, large language models, an AI centre of excellence, AI infrastructure, or an AI partnership or investment. General technology announcements do not qualify. Duplicate reports … counted once." | Urgency | threshold / guardrail |
| D3 | 2 Astra | "63 + 0.3 + 0 = 63.3/100 … 63.3 x 25% = 15.83/25" | Urgency | example |
| D3 | 3A Workforce growth (25 pts) | Source: "Source B, extended_company, social_stats … associated_members … a LinkedIn workforce proxy, not verified employee headcount". "Growth % = (latest associated members - earliest comparable associated members) / earliest comparable associated members x 100" | Urgency | formula |
| D3 | 3A | "20% or more 25 / 10-19.99% 20 / 5-9.99% 15 / 1-4.99% 7.5 / 0% or negative 0 / Comparable history unavailable 0" | Urgency | threshold |
| D3 | 3A Astra | "14,217 … 31 July 2025 and 16,781 on 30 June 2026 … 18.0% -> 20/25" | Urgency | example |
| D3 | 3B Hiring volume (50 pts) | "posted_at date falls within the latest 12 months. If posted_at is blank, use first_seen_at … Records older than 12 months are excluded. No separate HP-relevant-job-share score is used." | Urgency | threshold / fallback |
| D3 | 3B | "200 or more 50 / 100-199 40 / 50-99 30 / 20-49 20 / 5-19 10 / Below 5 0". Astra "100 … 60 have status closed and 40 have blank status … 40/50" | Urgency | threshold |
| D3 | 3C Growth events (25 pts) | "10 points per unique verified growth or expansion event within the last 12 months, capped at 25 points." | Urgency | threshold |
| D3 | 3C | Qualifying: new office, HQ, facility, plant, data centre or site; capacity expansion; new country or market; "capex or major investment supporting business, operational or capacity growth"; M&A or JV; workforce expansion; new BU. Exclusions: "ordinary product launches, routine earnings announcements, general partnerships, awards, residential developments, generic capex or investment with no identified growth purpose, or duplicate reports" | Urgency | mapping / guardrail |
| D3 | 3C Astra | "approximately IDR 36 trillion in planned capex … treated as a verified capital-backed growth/expansion event … 10/25". Raw "20 + 40 + 10 = 70/100 … 21.00/30" | Urgency | example |
| D3 | 4 HP Solution Intent | "Source: hp_intent_results. Use the fields belonging to the highest-scoring HP category." | Urgency | precedence |
| D3 | 4A (60 pts) | "highest HP-category intent score / 100 x 60". Astra "3D Printers at 34 -> 20.4/60" | Urgency | formula |
| D3 | 4B Trend (10 pts) | "Increasing 10 / Stable 5 / Decreasing 0 / Unavailable 0" | Urgency | threshold |
| D3 | 4C Stage (15 pts) | "Decision or Purchase 15 / Consideration 10 / Awareness 5 / No Signal 0 / Unavailable 0" | Urgency | threshold |
| D3 | 4D Volume (15 pts) | "High 15 / Medium 10 / Low 5 / Unavailable 0" | Urgency | threshold |
| D3 | 4 Astra | "20.4 + 10 + 5 + 15 = 50.4/100". The next line reads "Weighted contribution = 49.3 x 25% = 12.33/25", but the results table shows "12.60/25" | Urgency | example (inconsistent) |
| D3 | Result | "Final Urgency Score … 64.43/100", then "Rounded Astra Urgency Score: 61/100" | Urgency | example (inconsistent) |
| D3 | Scope | "does not assume access to PC brands, printer brands, device age, Windows version, warranty data or other unavailable account fields" | Urgency | guardrail |

### 2.6 D4 Live Signal Scoring

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D4 | 1 Purpose | Pipes: "Explorium, PredictLeads, Google News RSS and Exa.ai" | Live Signals | mapping |
| D4 | 1 | "Each unique underlying event is scored separately … Each receives its own Live Signal Score /10." | Live Signals | precedence |
| D4 | 1 | "If multiple sources report the same underlying event, they should be consolidated into one Live Signal, with all supporting sources retained as evidence." | Live Signals | precedence |
| D4 | 2 Formula | "Live Signal Score = (Recency x 0.30) + (Signal Relevance & Impact x 0.50) + (Source Reliability x 0.20)"; each raw 0-10; "maximum final score is 10/10" | Live Signals | formula |
| D4 | 3 Recency fields | Explorium "12_Hiring_Events -> event_time"; PredictLeads News "news_events -> effective_date"; PL Hiring "job_openings -> posted_at"; RSS "event_date"; Exa "event_date" | Live Signals | mapping |
| D4 | 3 | "Use the actual event date where available. Otherwise, use the publication date. Do not use the date on which the platform retrieved or crawled the record if a usable event/publication date exists." | Live Signals | precedence / fallback |
| D4 | 3 bands | "0-7 days 10/10 / 8-30 days 8/10 / 31-90 days 6/10 / 91-180 days 4/10 / 181-365 days 2/10 / More than 365 days 0/10 / No usable date 0/10" | Live Signals | threshold |
| D4 | 3 Astra | "Publication date: 23 April 2026. Scoring date: 17 September 2026. Age: approximately 147 days … 4/10 … 1.20/3.00" | Live Signals | example |
| D4 | 3 | "These scores are not added or averaged." | Live Signals | guardrail |
| D4 | 4 Relevance fields | Explorium 12_Hiring_Events (event_name, event_time, event_id, data); PL news_events (event, category, summary, article_sentence, product, product_data, product_tags, job_title, job_title_tags); PL job_openings (title, normalized_title, seniority, posted_at); RSS (event_headline + news_announcements + event_type; event_url); Exa (+ signal_categories, matched_keywords, event_summary) | Live Signals | mapping |
| D4 | 4 bands | "10/10 Direct HP-addressable need … explicitly stated" / "8/10 HP-relevant technology or workplace initiative" / "6/10 Major business change that could create HP demand" / "3/10 General account signal with weak HP connection" / "0/10 No meaningful HP connection" (qualifying examples "taken from HP provided deck") | Live Signals | threshold / mapping |
| D4 | 4 No-inference | "The system must not increase the score because of a need that might logically follow from the event." | Live Signals | guardrail |
| D4 | 4 | "The levels are not additive … assign the highest Relevance & Impact level directly supported by that event … All matched evidence/categories should still be retained as tags." (New factory + AI initiative = 8) | Live Signals | precedence |
| D4 | 4 Astra | Capex → "6/10 … 3.00/5.00" | Live Signals | example |
| D4 | 5 Reliability by pipe | Explorium/PredictLeads: score the underlying source if available, otherwise "usable … structured event → 6/10"; RSS: "Resolve event_url to the underlying article/source"; Exa: "If source_publisher is blank, identify the source from event_url" | Live Signals | fallback |
| D4 | 5 | "The underlying source is scored, not simply the pipe that found it." | Live Signals | precedence |
| D4 | 5 bands | "10/10 First-party or authoritative … 8/10 Established independent reporting … 6/10 Structured third-party evidence … 3/10 Weak secondary evidence … 0/10 Unverifiable" | Live Signals | threshold |
| D4 | 5 | Same event from several sources: "Do not add 8 + 6 + 10 and do not average them. Use the strongest verified source that directly confirms the same event." | Live Signals | precedence |
| D4 | 5 Astra | Google News RSS → IDNFinancials → "8/10 … 1.60/2.00" | Live Signals | example |
| D4 | 6 Final | "(4 x 0.30) + (6 x 0.50) + (8 x 0.20) = 1.20 + 3.00 + 1.60 = 5.80/10 … Individual Live Signal Scores are not added together" | Live Signals | formula (example) |
| D4 | 7 Processing | Steps: ingest → "Deduplicate records that describe the same underlying event" → one Live Signal per event → score 3 drivers → weighted /10 → repeat | Live Signals | precedence |

### 2.7 D5 Tech Landscape Confidence

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D5 | Intro | Confidence measures "how well the available evidence supports what the whole card is saying - not just whether the vendor name was found." | Tech Landscape | UI |
| D5 | Harness rule | "Explorium technographics … does not by itself prove that the vendor represents a specific HP business opportunity … Use the HP Rulebook to validate that interpretation." | Tech Landscape | precedence |
| D5 | 1 Structure | Driver 1 "HP-Relevant Technology Evidence 70%" (4_Technographics + 5_Tech_Breakdown + HP rulebook); Driver 2 "HP-Category Intent Support 30%" (hp_intent_results) | Tech Landscape | formula |
| D5 | 1 Formula | "Tech Landscape Confidence % = [(Driver 1 x 0.70) + (Driver 2 x 0.30)] x 10" | Tech Landscape | formula |
| D5 | 1 Guardrail | "Mandatory guardrail: If Driver 1 = 0, do not create the Tech Landscape card … intent alone cannot prove that a technology is present." | Tech Landscape | guardrail |
| D5 | 2 Fields | 4_Technographics category columns (20 listed: Testing And Qa … Sales). "Full Tech Stack may be used as a consolidated reference, but it should not be treated as a separate independent source." 5_Tech_Breakdown columns (19 listed: Copyright … Javascript) | Tech Landscape | mapping |
| D5 | 2 | "Use only technologies … explicitly present in these two sources; do not infer … If the same technology appears in both sheets, treat it as the same evidence and do not double-count it." | Tech Landscape | guardrail |
| D5 | 2 Driver 1 bands | "10 = directly supported technology fit; 5 = related technology fit; 0 = no supported fit." 10 means "the HP Rulebook explicitly recognizes"; 5 means "clearly related … but … not explicitly mapped" | Tech Landscape | threshold |
| D5 | 2 examples | Intune → WXP = 10; Azure → WXP = 5 ("WXP rule specifically names … Intune, Microsoft Entra ID, Power BI and Power Automate - not Microsoft Azure"); VMware → 3D Printing = 0, "No Tech Landscape card is created" | Tech Landscape | mapping |
| D5 | 2 Astra | Microsoft Windows detected → "WXP 04 … Driver 1 = 10/10". Card: "Consider HP Workforce Experience Platform (WXP) for multi-vendor endpoint visibility…" | Tech Landscape | example |
| D5 | 3 Driver 2 | Categories: "PC, Workstation, Poly/Collaboration, Print, and 3D". "Do not interpret intent topics and do not create a Topic-to-HP-category mapping … Retrieve only that category's Intent Score" | Tech Landscape | mapping / guardrail |
| D5 | 3 bands | "50-100 → 10/10; 25-49 → 5/10; 0-24 or missing → 0/10" | Tech Landscape | threshold |
| D5 | 3 | "Do not use another category's score." Astra 3D = 34 → 5/10; "If the Tech Landscape card is Workstation, use Astra's Workstation Intent Score" | Tech Landscape | guardrail |
| D5 | 4 | "Driver 1 = 10 and Driver 2 = 5 -> … 85%" | Tech Landscape | formula (example) |
| D5 | 4 Note | "If none of the five available intent categories is relevant to the HP opportunity, Driver 2 = 0/10; do not force an unrelated intent category" | Tech Landscape | fallback |
| D5 | Derived | The formula can only produce 0, 15, 30, 35, 50, 65, 70, 85 or 100%. Because a card is not created when Driver 1 = 0, a card can only show 35, 50, 65, 70, 85 or 100%. This is arithmetic from D5's bands, not text in the doc. | Tech Landscape | threshold (derived) |

### 2.8 D6 Delivery team's Rules doc (internal)

| Doc | Section | Rule (short exact quote) | Feature(s) affected | Type |
|---|---|---|---|---|
| D6 | 1 | "Scores, tiers, priority, influence type, gates, dates, URLs, contact facts, dedupe and ordering are all computed in Python. The model writes prose and nothing else." | All | guardrail |
| D6 | 1 | "One exception: in Live Signals the model supplies five 1-10 dimension judgments, Python still computes the composite and assigns the tier." | Live Signals | precedence |
| D6 | 1 | "Quoted evidence … is re-verified against the originating cell. The model is never permitted to rewrite it." | All | guardrail |
| D6 | 1 | "No account name, vendor, contact or count appears in code." | All | guardrail |
| D6 | 1 | "Upload and delete re-run the dependent features. A page view serves storage and never regenerates." | All | precedence |
| D6 | 2 Grounding | "Numbers … Must exist as an exact token in the uploads. Numbers under two digits are ignored" | All | guardrail |
| D6 | 2 | "Percentages … '47%' passes only if '47%' itself appears" | All | guardrail |
| D6 | 2 | "URLs … Must appear verbatim in the data. Unsourced links are stripped" | All | guardrail |
| D6 | 2 | "HP products … Resolved through a six-line allow-list … Anything naming no HP line is dropped." | All | mapping / guardrail |
| D6 | 3 Stakeholder | "Seniority 25% … C-Suite 100 / VP 75 / Director 50 / Manager 25 / IC 10. 'Head of...' bands as Director." | Stakeholder | formula / threshold |
| D6 | 3 | "HP relevance 25% … Tiers 100 / 70 / 40. Department alone caps at 70 — only a TITLE keyword reaches 100. Floor 20, +10 for HP-adjacent skills." | Stakeholder | threshold |
| D6 | 3 | "Influence 20% … Decision Maker 100 / Budget Holder 85 / Technical Evaluator 60 / Influencer 50." | Stakeholder | threshold |
| D6 | 3 | "Data completeness 15% … Email, email status, phone and LinkedIn presence." "Priority 15% … Supplied priority band." | Stakeholder | formula |
| D6 | 3 Priority Contact | "Composite >= 60 AND HP relevance band is not 'low'. One override: if no Budget Holder clears the bar but one exists on the roster, the highest-scoring is promoted" | Stakeholder | threshold / fallback |
| D6 | 3 Influence cascade | Order: "Procurement / purchasing / sourcing title -> Budget Holder; C-Suite band -> Decision Maker; Technical title -> Technical Evaluator; VP or Director in IT or Engineering … -> Decision Maker; 'Business decision maker' persona -> Influencer; 'Decision maker' persona INSIDE IT / Engineering / Executive … -> Decision Maker … outside … -> Influencer; Otherwise -> Influencer" | Stakeholder | precedence |
| D6 | 3 | "Technical title is tested BEFORE seniority deliberately"; the deciding branch is stored in influence_source | Stakeholder | precedence |
| D6 | 3 | Persona column gated ("18 of 23 rows on the reference account carry a Decision-Maker label"); "Champion and Blocker are never assigned" | Stakeholder | guardrail |
| D6 | 3 Live Signals | "Recency 25% / HP relevance 30% / Strategic impact 20% / Actionability 15% / Source reliability 10%". Tiers "S >= 8.0 / A >= 6.0 / B >= 4.0 / C >= 2.0 / not published < 2.0" | Live Signals | formula / threshold |
| D6 | 3 Opp Map | "The Opportunity Map has no numeric score … Plays are ordered by how many of three checks they meet." | Opp Map | precedence |
| D6 | 4 Step 1 | "Intent topics (top 10 by score) and news events (top 10) are kind='trigger'. Business description, employee and revenue bands, and tech-stack entries are kind='context'. Context alone never establishes timing." | Opp Map (and other plays) | threshold / mapping |
| D6 | 4 Step 2 | "Five families : workstation, poly, pc, print, daas." Signal and exclusion tokens (for example, 'fleet', 'asset', 'hardware'; "'cloud' was removed from the DaaS vocabulary") | Opp Map | mapping / guardrail |
| D6 | 4 Step 3 | verified_evidence: "bidirectional, six-character floor, word boundary, longest match wins"; timing_trigger: "At least one cited quote is kind='trigger'"; hp_fit: "At least one cited, non-excluded quote is topically about this play" | Opp Map | threshold |
| D6 | 4 Step 3 | "A trigger is only DEMANDED when this play's own evidence actually contains one." | Opp Map | fallback |
| D6 | 4 Step 4 | "No verifiable evidence -> DROPPED"; "No timing trigger -> DEMOTED"; "Fails hp_fit -> DISCOVERY … retitled 'no supporting evidence in this account's data' … sales narrative stripped"; "Prose fault -> PUBLISHED … Two rewrites, then published anyway" | Opp Map | fallback / UI |
| D6 | 4 Overclaim | "ALWAYS banned: perfect time, perfect fit, the right time to, is ready to, guarantees, ensures, fully compatible, must have, ideal time." "ACCOUNT-PREDICATED ONLY: require, requires, needs, will need" | All prose | guardrail |
| D6 | 5 Who to approach | "Contacts are matched from this account's REAL ROSTER … A title match ranks 2, a department match 1; ties break on stakeholder score; the top two are returned … If nobody matches, the play names the owning function" | Opp Map, Stakeholder | precedence / fallback |
| D6 | 5 Wording | "Technical Evaluator — NEVER described as a decision owner; Influencer — NEVER implied to hold purchasing authority" | Stakeholder, Opp Map | guardrail |
| D6 | 5 Pain points | "must hedge ('may', 'could', 'likely'), frame pressure on the FUNCTION … run at least 12 words, and are rejected if they merely echo a supplied intent topic or headline." | Opp Map | guardrail / UI |
| D6 | 5 Resources | "HP resource links come from a fixed per-play URL table and are never generated." Proof: "'No supporting HP proof point available' , no HP proof corpus is connected" | Opp Map | fallback / UI |
| D6 | 6 Gate 0 | "excluded when it has no headline AND no evidence sentence, an unparseable date, a date in the future, or an event older than 365 days." | Live Signals | guardrail / threshold |
| D6 | 6 Dedup | "merge when EITHER canonical headline similarity is >= 0.85, OR the evidence sentence and the event date are both identical … Merged rows keep every URL, publisher and date" | Live Signals | threshold |
| D6 | 6 Sales-angle | Banned: "ideal time, perfect time, right time to, now is the time, generic 'monitor for...'", or "sharing an opening or closing five-word stem". "ONE prose-only retry" | Live Signals | guardrail |
| D6 | 6 Rationale | "An unsourced rationale is withheld … while its SCORE STILL STANDS" | Live Signals | fallback |
| D6 | 7 Objection | "Client Devices, Collaboration, Print / MPS, Endpoint Security, Device Management". PRIMARY versus CONTEXT technologies | Objection Playbook | mapping |
| D6 | 7 | "The field is named not_in_technographics, never no_incumbent … The counter question must FIND OUT who owns the decision" | Objection Playbook | guardrail / UI |
| D6 | 7 | "Only a STRONG title token names a person; a weak match falls back to the owning function, and the UI says 'Could be raised by'." | Objection Playbook | fallback / UI |
| D6 | 7 | "Sector words are rejected as justification." "Near-duplicate objections merge at ratio 0.85" | Objection Playbook | guardrail / threshold |
| D6 | 7 | "Objections are HYPOTHETICAL buyer pushback, never reported speech" | Objection Playbook | guardrail |

---

## 3. Cross-document conflicts

Each entry below is only recorded, not resolved.

1. **Live Signals scoring model**
   - **Conflict:** the number of drivers, their weights and who judges them differ.
   - **D4 says:** there are 3 drivers, "Recency x 0.30 … Relevance & Impact x 0.50 … Source Reliability x 0.20", each with deterministic bands, producing a score /10.
   - **D6 says:** there are 5 dimensions, "Recency 25% / HP relevance 30% / Strategic impact 20% / Actionability 15% / Source reliability 10%", and "the model supplies five 1-10 dimension judgments".
   - **Needs confirmation:** YES.

2. **Live Signals tiers and publish cut-off**
   - **D4 says:** it gives a score /10 only. There are no tiers and no publish threshold.
   - **D6 says:** "S >= 8.0 / A >= 6.0 / B >= 4.0 / C >= 2.0 / not published < 2.0".
   - **Needs confirmation:** YES.

3. **Old or undated signals**
   - **D4 says:** "More than 365 days 0/10" and "No usable date 0/10". These are scored, not excluded.
   - **D6 says:** Gate 0 excludes "an unparseable date … or an event older than 365 days".
   - **Needs confirmation:** YES.

4. **Recency reference date**
   - **D4 says:** age is measured to a "Scoring date: 17 September 2026".
   - **D2 says:** outputs carry data_as_of_date = "the date the dataset was ingested … not the date the seller happens to open the dashboard".
   - **D3** uses "latest 12 months" without saying what the window is measured from.
   - **Needs confirmation:** YES. Is recency measured from the ingestion date or from the scoring or run date?

5. **Deduplication rule**
   - **D2 and D4 say:** merge on the "same underlying event", keeping the strongest source. D4: "Use the strongest verified source".
   - **D6 says:** a mechanical rule: "headline similarity is >= 0.85, OR the evidence sentence and the event date are both identical".
   - **Needs confirmation:** YES. The client has not seen or approved the 0.85 heuristic.

6. **Live Signals pipes and fields**
   - **D4 says:** it scores Explorium `12_Hiring_Events`, PredictLeads `news_events` and `job_openings`, Google News RSS and Exa. It lists Google News RSS "exact supplied fields" without event_summary, signal_categories or matched_keywords.
   - **D2 says:** its Input Contract has no Explorium 12_Hiring_Events or PredictLeads news_events stream. It lists event_summary, signal_categories and matched_keywords as Google News RSS fields.
   - **Needs confirmation:** YES.

7. **Opportunity strength model**
   - **D2 says:** the evidence tiers are Opportunity ("At least 2 logically related independent data pipelines"), Conversation Starter (1 strong signal) and Context Only, plus a required `confidence_tier` field.
   - **D6 says:** "The Opportunity Map has no numeric score … Plays are ordered by how many of three checks they meet" (verified_evidence, timing_trigger, hp_fit). The outcomes are DROPPED, DEMOTED, DISCOVERY or PUBLISHED. There is no pipeline count.
   - **Needs confirmation:** YES.

8. **What counts as corroborating evidence**
   - **D2 says:** Technographics and Firmographics count as pipelines. The BHP Opportunity Map example uses Intent + Tech + "Number Of Employees Range = 10,001+".
   - **D6 says:** tech-stack, employee and revenue bands are "kind='context'. Context alone never establishes timing". Only the top 10 intent topics and top 10 news events are triggers.
   - **Needs confirmation:** YES.

9. **Play and offering universe**
   - **D6 says:** there are "Five families : workstation, poly, pc, print, daas" and a "six-line allow-list" of HP products.
   - **D1 says:** it routes to hardware, WXP, Care Pack, lifecycle, deployment, Poly support, print/scan, HP IQ and Wolf.
   - **D2 says:** its examples recommend "HP 3D Printing", "Z by HP Workstations" and WXP.
   - **D5 says:** its intent categories are "PC, Workstation, Poly/Collaboration, Print, and 3D". This includes 3D and has no DaaS.
   - **Needs confirmation:** YES.

10. **Proof points and case studies**
    - **D6 says:** "no HP proof corpus is connected, so an unrelated case study is never substituted"; the fallback is "No supporting HP proof point available".
    - **D2 says:** `hp_case_studies_final.csv` is the proof library (section H, "prefer APJ/APAC proof for APJ accounts"). R4 lists it for most features.
    - **Needs confirmation:** YES. The corpus is now supplied.

11. **Empty-state wording**
    - **D2 says:** "No supported HP play at this time".
    - **D6 says:** "no supporting evidence in this account's data" (DISCOVERY) and "No supporting HP proof point available".
    - **D1 says:** C 07 "leave out the recommendation or label the missing condition clearly".
    - **Needs confirmation:** YES.

12. **Numeric claim grounding**
    - **D6 says:** numbers and percentages "Must exist as an exact token in the uploads".
    - **D2 says:** section I requires that "Any HP number … must have a verified HP source". D1 contains many HP numbers ("up to 50 TOPS", "80 covered countries", "85%").
    - **Needs confirmation:** YES. D6's rule passes D1 numbers only if the Rulebook is part of the grounding corpus. This is not stated anywhere.

13. **Lifecycle file**
    - **D2 says:** section J and K4 say to check the HP Lifecycle file before surfacing an offering; if it is past its PE/EM date, do not recommend it.
    - **R4 (client explanation file) says:** "HP Lifecycle June 2026 — Not used as of now … Not being used in the platform currently."
    - **D1 says:** C 02 "must not reopen the original HP files".
    - **Also:** the local lifecycle extraction (R3) failed.
    - **Needs confirmation:** YES.

14. **HP IQ / Wolf decks as runtime sources**
    - **D2 says:** section I: "If information from these decks is used, it should remain traceable to the relevant source."
    - **D1 and R4 say:** D1 C 02 makes source names "provenance only". R4 says "Not used separately - included in Combined HP Rulebook".
    - **Needs confirmation:** NO. They are compatible if traceability means provenance IDs, but the reader should be aware of it.

15. **Qualifying workplace technologies**
    - **D3 says:** it counts "Microsoft Teams … supported through HP Workforce Experience Platform integrations" and VMware "relevant to HP Anyware" as qualifying (Astra = 2 → 10/30).
    - **D1 says:** WXP 07 lists integrations as "ServiceNow, Microsoft Intune, Power BI, Power Automate, Tableau, and Microsoft Entra ID". Teams is not listed, and HP Anyware does not appear anywhere in D1.
    - **D5 says:** it treats Azure as only "related" (5/10) because it is not named in WXP 07.
    - **Needs confirmation:** YES.

16. **WXP card from technology detection alone**
    - **D5 says:** "Microsoft Windows detected" → WXP 04 → Driver 1 = 10/10, and a card saying "Consider HP Workforce Experience Platform (WXP)…". Intune alone gives 10/10 with the WXP recommendation.
    - **D2 says:** K3 is BANNED: "State that the account has WXP buying intent because Microsoft Intune or ServiceNow is detected. ALLOWED … only when a separate account signal establishes a relevant endpoint-experience or fleet-management need." D1 WXP 07: "Existing use shows possible fit, not buying intent."
    - **Needs confirmation:** YES. Does a Tech Landscape card count as a "recommendation" under D2 K3? Does "Windows detected" satisfy WXP 04's "Verified Windows … estate"?

17. **D5 Astra example mixes two cards**
    - **Driver 1 example:** a WXP card (Windows → 10).
    - **Driver 2 example:** "Opportunity being evaluated: 3D" (3D Printers 34 → 5). §4 then combines "Driver 1 = 10 and Driver 2 = 5 -> 85%". D5 also does not say which of the five intent categories a WXP card maps to.
    - **Needs confirmation:** YES. This is internal to D5.

18. **Astra capex figure and event**
    - **D3 says:** "approximately IDR 36 trillion in planned capex".
    - **D4 says:** "ASII sets IDR 36 trillion capex for 2026, up 10% year on year".
    - **D2 says:** its Live Signals example says "Astra's Rp16.9T capex announcement".
    - **Needs confirmation:** YES. This could be a different event or an error.

19. **Growth vs generic capex**
    - **D3 says:** it excludes "generic capex or investment with no identified growth purpose", yet counts the Astra capex "as this is treated as a verified capital-backed growth/expansion event under this scoring rule".
    - **D4 says:** it scores the same capex as a "Major business change" (6/10): "Investment: major capex or investment tied to growth/operations/capacity".
    - **Needs confirmation:** YES. The criterion for when capex counts as growth is not stated.

20. **AI partnership classification**
    - **D3 says:** AI events qualify if they concern "an AI partnership or investment" (5 pts each).
    - **D4 says:** "General strategic partnership … customer-facing AI/product launch, general cloud partnership" = 3/10. "enterprise AI/GenAI … AI compute" initiatives = 8/10.
    - **Needs confirmation:** YES. The same event could be treated differently across features.

21. **Hiring date fallback**
    - **D3 says:** "If posted_at is blank, use first_seen_at". Closed and blank-status jobs both count.
    - **D4 says:** PredictLeads Hiring recency uses "job_openings -> posted_at" with no first_seen_at fallback. Otherwise use the publication date.
    - **Needs confirmation:** YES. This is a minor point.

22. **Urgency arithmetic (internal to D3)**
    - **HP Solution Intent:** the raw score is "50.4/100", but the next line says "49.3 x 25% = 12.33/25". The results table says "12.60/25".
    - **Final score:** the total is "64.43/100", but the doc then says "Rounded Astra Urgency Score: 61/100".
    - **Needs confirmation:** YES.

23. **Urgency band gaps (internal to D3)**
    - The employee bands "251-1,000" and "Below 250" leave exactly 250 unassigned.
    - The growth bands "1-4.99%" and "0% or negative" leave 0.01-0.99% unassigned.
    - Explorium's "10,001+" range, used in the Astra example, spans both the "10,001-49,999" and "50,000 or more" bands.
    - **Needs confirmation:** YES.

24. **Intent source for urgency**
    - **D3 says:** Breadth and Depth use "Source A, 11_intent_score" (an Explorium sheet). HP category scores use hp_intent_results.
    - **D2 says:** its Input Contract names only "hp_intent_results 2(3).xlsx / Intent Data (Wide)" for Intent. It has no 11_intent_score stream and no PredictLeads `extended_company.social_stats`, which D3 §3A uses.
    - **Needs confirmation:** YES.

25. **Stakeholder scoring**
    - **D6 says:** it defines a composite (25/25/20/15/15), a Priority Contact threshold ">= 60" and an influence cascade.
    - **D2 says:** it defines only How to Open + HP Play Focus (40-100 words). It has no stakeholder score. Its Contacts contract has no "priority" or "phone" field, both of which D6 uses.
    - **Needs confirmation:** YES. D6 is still awaiting client review.

26. **Parent/subsidiary evidence**
    - **D2 says:** section B: "Do not combine evidence from a parent, subsidiary, business unit or geography unless the mapping explicitly supports it." Yet D2's own Executive Dashboard example opens "In 2025, ASTRA Infra is optimizing technology…".
    - **D3 and D4 say:** they use Astra / ASII group-level data.
    - **Needs confirmation:** YES. Is ASTRA Infra the mapped account or a subsidiary?

27. **One main recommendation vs multiple pillars**
    - **D1 says:** C 06: "Give one main recommendation. Add another … only when separate verified evidence supports it."
    - **D2 says:** Content Messaging has several pillars, and Intent & Demand treats themes "as separate seller conversations". Both are conditioned on separate evidence.
    - **Needs confirmation:** NO. They appear consistent.

28. **Rulebook version in use**
    - D1 local is the 17 Sep version. D2 (23 Sep) and D5 (18 Sep) cite Rulebook rules such as WXP 04 and WXP 07, and the 23 Sep "_FINAL_" Rulebook is not local.
    - **Needs confirmation:** YES. Rule IDs and text may have changed.

29. **Persona routing source**
    - **D1 says:** Rule 17: "Use this deck [BPS Portfolio Sell-In Deck FY26] first to choose the HP family", but C 02 says "the engine must not reopen the original HP files".
    - **Needs confirmation:** NO. This is internal wording. Rule 17 itself carries the persona facts.

30. **Coverage gaps in D6 (not contradictions)**
    - D6 has no Urgency score (D3) and no Tech Landscape confidence (D5). D6 predates both.
    - D6 has no word limits matching D2 §G. D6 has only "at least 12 words" for pain points.
    - **Needs confirmation:** NO, beyond items 1-25.

---

## 4. Data each document depends on

| Doc | Datasets / sheets / columns named |
|---|---|
| D1 | **HP sources, as provenance only:** Care Pack Definitions (Feb 2026 Rev 4); Q426 Services and Solutions workbook (2,186 rows / 287 expanded descriptions); HP IQ for Enterprise v1.0; Wolf Security Portfolio (Feb 2026); WXP and DEX ROI Calculator web pages; BPS Portfolio Sell-In Deck FY26; Competitive Playbook EliteBook X G1i vs Lenovo X1 Carbon; product decks (EliteBook 8 G2, 6 G2, ProBook 4 G2, Ultra G1i, Ultra G1q/G1q8, HP 200 G2, EliteDesk 8 Tower/Mini/SFF G1i, ProDesk 4 Mini, EliteStudio/ProStudio AiO). **Account-side inputs, named generically:** "verified account research", technographics, procurement data, device warranty status, seat counts (Priority Access 250 / 1,000 / 5,000; SCE 500-999), account country for the restriction lists. D1 does not name account datasets or columns. |
| D2 | **Intent:** `hp_intent_results 2(3).xlsx / Intent Data (Wide)`. Columns: Run Date, Top HP Category, Top Intent Score (/100), per-category Intent Score, Intent Trend, Buying Stage, Research Volume, Topics Researched, Keywords Matched, Related Technologies, First/Latest Intent Date, Geo Source. **Explorium:** `Company_explorium_data.xlsx / 1_Firmographics` (Company Name, Domain, Country, Region, City, Naics, Naics Description, Number Of Employees Range, Yearly Revenue Range, Linkedin Industry Category) and `4_Technographics` (Technology, Full Tech Stack, category columns). **PredictLeads:** `predictleads_combined_219_accounts(2).xlsx / job_openings` (id, title, normalized_title, categories, seniority, location, posted_at, first_seen_at, last_seen_at, status, tags, description, url, source_url, retrieved_at). **News:** `google_news_rss_data` and `exa_data` (event_headline, event_url, event_date, event_type, signal_categories, matched_keywords, event_summary, source_publisher, relevance_confidence). **Filings:** `filings 1.csv` (row_id, document_title, document_type, reporting_period, period_start/end, publication_date, source_type, source_page_url, document_url, validation_status, confidence, notes; merge_group_id). **Contacts:** `Apollo_All_Contacts(1).xlsx / Contacts` (Seed Id, Company Name, Requested/Matched Contact, Requested Role, Title, Match Status, Match Rate Per Requested Contact, Email Confidence, Seniority, Department, Linkedin Url, Apollo Id, Review Reason). **Case studies:** `hp_case_studies_final.csv` (case_study_id, title, hp_route, product_featured, customer, industry, use_case, outcome_claimed, outcome_metrics, account_signal_match, solution_categories, source_url, publish_date, source_tier, validated, needs_manual_review, confidence fields). **Also:** HP Lifecycle file (PE/EM dates) and the HP Rulebook. **Join keys:** Domain primary, Company Name fallback. **Refresh:** Intent, Tech, Hiring, Filings, Contacts and Case studies every 6 months; Firmographics annually; RSS and Exa weekly. |
| D3 | **"Source A" (Explorium):** `1_Firmographics.Number Of Employees Range`, `4_Technographics.Full Tech Stack`, `11_intent_score` (AI/ML topics). **"Source B" (PredictLeads):** `extended_company.social_stats` (dated associated_members) and `job_openings` (posted_at, first_seen_at, status). **hp_intent_results:** Workstations Intent Score; highest-category score, trend, buying stage, research volume. **"supplied news files"** for AI and growth events. HP web pages are cited for the OS rationale (hp.com/in-en laptops and data-science workstations). The doc states that PC brands, printer brands, device age, Windows version and warranty data are *not* available. |
| D4 | **Explorium** `12_Hiring_Events` (event_name, event_time, event_id, data). **PredictLeads** `news_events` (effective_date, event, category, summary, article_sentence, product, product_data, product_tags, job_title, job_title_tags) and `job_openings` (title, normalized_title, seniority, posted_at). **Google News RSS** (company_name, website_domain, company_linkedin_url, news_announcements, event_headline, event_url, event_date, event_type, source_publisher, relevance_confidence, coverage_depth_events_per_account_last_12mo). **Exa.ai** (event_headline, news_announcements, event_type, signal_categories, matched_keywords, event_summary, event_url, source_publisher, event_date). Resolving event_url to the underlying article is required for reliability scoring. |
| D5 | **Explorium `4_Technographics`**, 20 category columns: Testing And Qa; Prog Langs And Frameworks; It Security; It Management; Devops And Development; Bi And Analytics; Computer Networks; Collaboration; Platform And Storage; Marketing; Hr; Finance And Accounting; Ecommerce; Customer Management; Communications; Operations Software; Operations Management; Product And Design; Productivity And Operations; Sales. Full Tech Stack may be used as a consolidated reference. **Explorium `5_Tech_Breakdown`**, 19 columns: Copyright; Framework; Ads; Link; Ns; Ssl; Web Server; Cms; Mx; Server; Mobile; Cdn; Media; Hosting; Language; Analytics; Cdns; Widgets; Javascript. **`hp_intent_results`** category Intent Score (PC, Workstation, Poly/Collaboration, Print, 3D). **HP Rulebook** (D1) rule matches such as WXP 04 and WXP 07. |
| D6 | "Every non-empty cell of the datasets" forms the grounding corpus. It names no specific files. **Contacts:** seniority, title, department, persona column ("Decision maker" / "Business decision maker"), email, email status, phone, LinkedIn, "Supplied priority band", skills. **Intent topics:** top 10 by score. **News events:** top 10. **Context:** business description, employee and revenue bands, tech-stack entries. **Code artefacts:** a fixed per-play HP URL table; a six-line HP product allow-list; `grounding.py`; `scripts/audit_grounding.py`. The doc states "no HP proof corpus is connected". |
| R4 | filings 1.csv → Exec Dashboard, Live Signals, Opp Map, Content Messaging, Strategy Chat. The Rulebook and hp_case_studies_final.csv go to most features. Lifecycle is "Not used as of now". |

---

## 5. TBD and open items stated in the docs

**D1 Rulebook**
- WXP 11: "the engine must not choose a tier automatically … label tier selection as pending HP input."
- WXP 12 and 13: the doc says "This rulebook contains no deliverables, duration, response time, or service-level details" for Enhanced Onboarding and Premium Support.
- SCAN 02: "The engine must not choose among the three routes until HP supplies the missing threshold or scope."
- SCAN 03: the number of hours and the deliverables are not stated.
- PRINT 01-03: the doc says "It provides no additional capability description."
- POLY 03: "The catalogue does not state further service-level benefits."
- C 08 and C 09: facts are to be replaced when newer approved sources arrive; "planned, expected, future" wording is to be kept until confirmed.
- Country lists: "Also block in any CIS country covered by the playbook restriction". The CIS country list itself is not given.
- Guardrail 10: embargo dates must be checked automatically for "any new HP deck added later".
- Numbering gaps in the extraction: LIFE 04; product guardrails 1, 6, 8, 9 and 11-14; G 01-05 and G 16. These may be deliberate removals. Check against the 23 Sep "_FINAL_" version, which is not local.
- The 23 Sep "_FINAL_" Rulebook is not available locally.

**D2 Recommendation Logic**
- Section C thresholds are labelled "Initial build threshold", which suggests they may be tuned later.
- Contacts with "Pending/Review status" and case studies with "needs_manual_review" are not to be used "until approved".
- Proof is described as "where available" and "optional proof".
- Section J lifecycle check: "approaching lifecycle end … flag it in the backend".
- The Intent & Demand row's "HP Rulebook + Case Study use" cell is blank or shifted in the extraction. The Technographic Map row's "Recommendation tuning logic" cell is empty or shifted.
- The earlier deck, "HP_220_Account_Recommendation_Logic(1).pptx" (15 Sep), is not local. R4 says of it: "Some changes need to be made after discussing them with Sahaj."

**D3 Urgency**
- 1C: Teams qualifies "where supported by approved HP material". M365, Google Workspace, SharePoint, Zoom, Webex and Splunk qualify "only where approved HP material establishes a direct HP product, service or solution relationship". Which HP material counts as approved is not listed.
- "Per the agreed rule for this dataset": the blank and closed job-status inclusion is recorded as an agreed rule.
- There is no "Final" rounding rule. The worked example is internally inconsistent (see §3 item 22).

**D4 Live Signals**
- No items are explicitly marked TBD.
- The qualifying examples are "taken from HP provided deck", which is not named.
- In the same-event reliability table, the Exa row's "Supporting evidence" cell repeats the instruction text instead of a source classification, yet it is scored 10.

**D5 Tech Landscape**
- No items are explicitly marked TBD.
- The doc does not state how a card's HP category is assigned for solution cards such as WXP.
- "Note: If none of the five available intent categories is relevant … Driver 2 = 0/10".

**D6 Delivery team's Rules doc**
- The whole doc is pending client review. It was sent 10 Sep 2026 and no feedback has been received.
- Items stated inside D6: "no HP proof corpus is connected"; "Champion and Blocker are never assigned" ("no such evidence is held"); the Opportunity Map score is undefined ("The specification defines none").

**R files**
- R3 (Lifecycle), R5 (HP IQ) and R6 (Wolf) have failed extractions ("ERROR File is not a zip file").
- R2 (Q426) is truncated after about 60 of 2,186 rows.
- R4 cells are truncated at about 120 characters.
- R4 says Lifecycle is "Not used as of now".
