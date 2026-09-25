> GENERATED EXTRACTION NOTES — produced 25 Sep 2026 by an automated read of the plain-text conversions of the source documents. INTERNAL. Not client text. Verify any number, rule id or quote against the original document in 01_Client_Provided/ or 02_Decision_Maker/ before relying on it. Line numbers refer to the text conversions, not to Word pages.

# A — Client requirements: HP_ABX_v3_final, additional-data addendum, 11-Features sourcing reference

Source files (plain-text extractions, scratchpad/text/):
- `HP_ABX_v3_final.txt` (273 lines, ~136 KB). Each table row is one long line, so the line numbers below refer to the .txt extraction, not to Word pages.
- `HP_220_Account_Platform_additional_data_1_.txt` (140 lines)
- `11-Features-Sourcing-Reference-Anonymized_1_.txt` (110 lines). It is byte-identical to `11-Features-Sourcing-Reference-Anonymized.txt`.

Conventions: "quoted text" is copied word for word from the source. **[note]** marks my own observation; it is not client text. The master doc tags steps with two labels, `[Deterministic/Derived]` and `[VLLM]`. `[VLLM]` is the doc's own label and apparently means an LLM (Gemini) step. **The master doc contains no "RAG" label anywhere.** RAG appears only in the additional-data doc.

---

## 1. Document structure

### 1.1 HP_ABX_v3_final ("master requirements / implementation guide")
- **Title/author/date stated inside:** none. The text starts with "How to use this document". Nothing in the text names Dhruvi Patel, BridgeAI or 22 Aug 2026; that attribution comes from outside the doc.
- **Purpose (L2):** "For every platform feature, the same build path is shown: what the feature needs, which sources/APIs feed it, how the data is cleaned, how facts are verified, what rules or AI create the intelligence, what happens when a step fails, what is saved/audited, and the exact seller-facing output that is accepted." It calls the field list "a parity contract": any tile/label/score component/etc. visible in the referenced POC or repo "must retain it unless it is a true duplicate of another field." The goal is "one repeatable automated harness across the full HP account list."
- **Sections:**
  - L3–30 Feature classification:
    - **Static / Pre-built:** Executive Dashboard, Stakeholder Map, Solution Narrative / Opportunity Map, Tech Landscape, Objection Playbook, Intent & Demand Signals, Competitive Displacement, Peer Benchmarking, Source Trail Explorer, Content Messaging, Opportunity / Account Planning, Account / Seller Briefing, Account Intelligence / Supporting View. The doc says these are "refreshed when their underlying data changes … Recent News is refreshed on a defined cadence, while Source Trail is updated when upstream claims change".
    - **Live / Seller-Triggered:** Content Studio, Strategy Chat, Message Evaluator, ABM Toolkit / Asset Generation, Sales Simulator.
    - **Hybrid:** (1) Recent News Signals, with Live = searches "on the defined refresh schedule" and Static = saved verified signals "displayed from storage until the next refresh"; (2) Narrative Engine, with Dynamic regeneration and Static saved five-section narrative.
  - L32–250: Feature 1 to Feature 20. Every feature uses the same template: "What are we trying to build?"; "POC to study"; "1. What data this feature needs"; "2. Where the data comes from"; "3. Clean and prepare the data"; "4. Rules + guardrails"; "5. How to build this feature"; "6. Fallback handling"; "Required output". Cross-references treat these rows as "Stages" (for example "Feature 1, Stage 5, Step 5").
  - L251–266 "How the POC modules connect in the automated build": FOUNDATION (Master List column B Sales Territory Name → account record → common evidence/source-details layer) → PRIMARY ACCOUNT INTELLIGENCE (Recent News + Stakeholder Map + Tech Landscape + Intent + Competitive Displacement + Peer Benchmarking + Source trail) → DERIVED SALES INTELLIGENCE (Solution Narrative/Opportunity Map → Objection Playbook → Content Messaging → Outreach Sequences) → EXECUTIVE EXPERIENCE (Executive Dashboard + Narrative Engine + KPI Framework) → LIVE / ACTION TOOLS (Content Studio + Strategy Chat + Message Evaluator + Sales Simulator + Deal Qualification + ABM Toolkit).
  - L267–273 "Recommended implementation order": Phase 1 account list from Master List column B; Phase 2 data acquisition + normalized evidence/source-details model; Phase 3 Recent News + Stakeholders + Tech Landscape + Intent + Source trail; Phase 4 Solution/Opportunity Map + Competitive Displacement + Objection Playbook + Content Messaging + Peer Benchmarking; Phase 5 Executive Dashboard + Narrative Engine + KPI Framework. **[note]** The list stops at Phase 5. No phase covers the Live tools.
- **POC references used throughout:** `paloalto-abm.vercel.app → Caterpillar` (primary for Exec Dashboard, Stakeholder Map, Solution Narrative, Tech Landscape) and `hp-sea-abm.vercel.app → Sea Limited` (HP-native reference for all features).

### 1.2 HP_220_Account_Platform_additional_data ("addendum")
- **Title stated inside:** "HP 220-Account Platform" / "HP-Provided Knowledge Rules for RAG Recommendations". No author. The only date reference is inside Guardrail 10: "these dates are already past as of 24 Aug 2026".
- **Purpose (L3):** "when to use the HP Notebook/Desktop decks, which deck to use, and which exact HP facts can be used. These decks are only for the situations listed below."
- **Sections:** L5 How to Use These Rules · L13 Recommendation Flow · L22 HP Deck Usage Rules (18-row table) · L43 Mandatory RAG Guardrails (17 rows) · L64 Exact Country Restriction Lists from the Reviewed HP Decks · L70 Implementation note · L71 How the Team Should Implement This · L73 Additional Module – Reporting & Usage Analytics (L75 What should be tracked; L85 Natural-Language Reporting Questions; L105 Expected Reporting Module; L117 Important Implementation Point; L123 Required Usage Logging).
- **[note] Human-in-the-loop:** the extraction has **no human-in-the-loop section** and no HITL wording. The only "human" hit is "Human Presence Detection", a product feature in deck rule 12. Either the HITL content is not in this .docx or it did not survive extraction. It should be checked against the original Word file.

### 1.3 11-Features-Sourcing-Reference-Anonymized
- **Title stated inside:** "11 In-Scope Features — Data Sourcing Reference (Revised)". Subtitle: "Field names aligned to the live tool's AccountData model (app/src/data/types.ts)". No author or date inside.
- **Anonymized:** providers appear only as "Source A" and "Source B", plus "Google News RSS" by name. **[note]** Source A sheet names (1_Firmographics, 2_Company_Hierarchy, 4_Technographics, 5_Tech_Breakdown, 10_Intent_Topics, 11_intent_score, 13_News_Events, 14_Prospect_Contacts) and Source B endpoints (job_openings, news_events, technology_detections) are consistent with Explorium (A) and PredictLeads (B). **The doc does not name either provider.**
- **Sections:** L4 Sourcing Rule · L11 Field-by-Field Sourcing, with sub-sections "## 1." to "## 11." (L12, 26, 35, 47, 56, 66, 73, 81, 87, 94, 103).
- **Purpose:** field-by-field decision on which source feeds each AccountData field for the 11 in-scope features.

---

## 2. Per-feature extraction from HP_ABX_v3_final (11 in-scope features)

### 2.1 Executive Dashboard — "Feature 1 — Executive Dashboard", L32–41
- **POC:** paloalto-abm → Caterpillar (primary); hp-sea-abm → Sea Limited (HP version).
- **Data required:**
  - Company profile: "Sales Territory Name (from Master List column B), domain, Headquarters (HQ), country/market, industry, Chief Executive Officer (CEO) and employee count".
  - "3-5 years of financial metrics where available: revenue, revenue growth, net income, headcount growth".
  - "3-5 strategic priorities with evidence for why each priority matters now".
  - Top recent signals, top stakeholders, technology/installed-base signals, intent signals and HP-relevant opportunities.
  - "An urgency score with the five named drivers used in the Sea Limited POC".
- **Sources:**
  - Primary: regulatory filings / annual reports / IR pages; Apollo (company + contact); Coresignal (company/workforce, technology-use); Exa and Google News RSS (news/trigger); Bombora (intent "where available").
  - Secondary: People Data Labs, InfobelPRO, Techsalerator (profile); FullEnrich, Prospeo, SignalHire (contacts); Tavily, PredictLeads (news/events); TheirStack, HG Insights, PredictLeads, BuiltWith (technology); Intentsify (alternative intent).
  - Verification/fallback: company website, LinkedIn company page, leadership pages, newsroom, IR, filings.
  - "For technology and intent shown on the dashboard, reuse the cleaned outputs from Tech Landscape and Intent & Demand Signals rather than sourcing the same data again."
- **Rules / thresholds / formulas / precedence:**
  - Identity: match "the company name and official website returned by sources such as Apollo or Coresignal to the Sales Territory Name in the HP Master List"; keep old names, parents and subsidiaries.
  - Financial normalisation: keep original currency/value, converted value, financial period, and whether the figure is full year, quarter or LTM. "do not compare total-company revenue for financial year 2025 with one business unit's quarterly revenue for financial year 2026".
  - **Precedence:** "When data sources disagree, prefer the most recent value reported by the company or in a regulatory filing and keep the external data-source estimate as secondary evidence rather than overwriting it."
  - Priority taxonomy: "(AI, workforce productivity, hybrid work, expansion, security, fleet refresh, print/workflow, sustainability, cost optimisation)", while "retaining the original supporting sentence".
  - Dedup: the same real-world event in News/Tech/Intent is stored once; "Do not count the same event twice when building dashboard tiles or the urgency score."
  - Urgency driver scale: "The dashboard accepts five urgency driver values on a 0-100 scale. The current POC does not define a reusable raw-data-to-driver formula for all accounts. Do not invent one inside the dashboard. Store the driver value, the evidence used and the driver calculation used by the upstream data process".
  - Financial check: "correct company/business unit, correct metric, correct reporting period, and correct unit/currency". Subsidiary/segment data must be labelled; "do not show it as total-company data".
  - **FORMULA:** "Strategic-priority evidence score = 40% support frequency + 25% supporting document sections + 20% recency + 15% independent external-source support." Step 3 adds: "Sort priorities from highest to lowest score."
  - "Show a strategic priority only when at least one saved source sentence supports it. Do not create a priority from a general industry assumption."
  - **FORMULA:** "Urgency score = 20% Fleet Refresh + 25% AI/Workstation + 15% Hiring + 15% Expansion/Print + 25% Intent. Each of the five inputs must already be stored as a 0%-100% value with its evidence and calculation method."
  - "Do not count the same evidence twice inside the same urgency driver. If one evidence item genuinely supports two different drivers, link the same evidence ID to both drivers so the reuse is visible."
  - **Missing-input rule:** "if any of the five urgency inputs is unavailable, keep that input unavailable and do not calculate the overall urgency score. Do not change a missing value to 0%."
  - Exec summary "may use only saved account facts. Every named person, date, percentage, company fact and HP product statement must be traceable to the saved evidence or official HP content."
  - "If a card has no valid data, use the same empty/missing state used by the POC instead of creating a value."
- **Step labels:** Steps 1–6 are all `[Deterministic/Derived]`, including Step 6 "create the short executive summary". In fallback, three bullets are `[Deterministic/Derived]` and one is `[VLLM]` (the summary fallback).
- **Fallback:**
  - Name/domain mismatch across major sources: "do not show the dashboard". Put the account into "an account-name review list", keep raw records, fix mapping, and rebuild only after the match is resolved.
  - Financial metric fails period/whole-company check: remove it; "Show the last verified period with its date if one exists; otherwise show the metric as unavailable."
  - Urgency driver lacks evidence: keep it unavailable and "do not calculate the overall urgency score until all five driver scores are available. Do not replace the missing driver with 0%."
  - [VLLM] Summary contains an unsupported fact: "do not show that version. Use a simple summary built from the strongest verified priority, trigger and stakeholder instead."
- **Required output:**
  - Account header: name, logo/domain, industry, HQ/market, CEO, employee count, revenue, financial trend cards.
  - "Executive summary / account story with 2-4 grounded sentences".
  - Strategic-priority tiles: title, description, criticality/importance, why-now, reference sentence, source link, source/date, confidence and verification.
  - Recent-signal tiles: signal/event, category, date, urgency/relevance, what happened, why HP should care, HP category/play, source link, confidence.
  - Stakeholder summary/entry point: contact/persona, role, influence/priority, rationale, link to full map.
  - Technology and intent summaries: status, confidence, HP opportunity.
  - "Urgency score out of 100 with Fleet Refresh, AI/Workstation, Hiring, Expansion/Print and Intent component scores, weights, evidence used and any unavailable component clearly marked".
  - All material claims keep source/reference access; POC filters/links/actions remain.

### 2.2 Recent News Signals — "Feature 2 — Recent News Signals", L43–52
- **Refresh:** "The scope calls for a monthly refresh." The classification section describes this feature as Hybrid.
- **POC:** hp-sea-abm → Sea Limited → Recent News / Live Signals.
- **Data required:** "12-20 recent news/events per account: headline, description, source, link, publication date and event date"; account mentioned, geography, people mentioned; event type; "A short field describing why the event matters to HP."
- **Sources:**
  - Primary: "Exa and Google News RSS". "Company newsroom, investor-relations pages and regulatory filings should be treated as the strongest evidence when the company itself has announced the event."
  - Secondary: Tavily, PredictLeads.
  - Tertiary/fallback: NewsAPI.org, GDELT, "when the primary and secondary sources do not return enough relevant results".
  - Approach: combine feeds, dedupe, classify, keep one clean signal.
- **Rules / thresholds / formulas / precedence:**
  - Identity at article level: check name plus website, stock ticker, subsidiary, executive name, country. "If the company name is common and the other clues do not match, do not use that article". "the selected account must be a subject of the event, not merely mentioned in a list or unrelated market roundup."
  - Normalise URLs (strip tracking parameters) before dedup.
  - **Dates:** publication date is separate from event date. Store both "and use the event date for trigger timing" (example: published 10 Aug, completed 2 Aug).
  - **Dedup precedence:** "Use the original company announcement or the most direct reliable report as the main source, and keep other independent links as supporting sources." Dedup is validated at event level: "multiple articles about one office opening must result in one signal card … not multiple urgency boosts."
  - **Category list (exactly one per story):** "Financial, Leadership, Hiring, Expansion, AI/Transformation, Security, Procurement, Partnership, Product/Business Expansion, Regulatory, or Other."
  - Evidence: extract exact evidence sentence(s) and keep them separate from the HP implication. Verify against the body, not only the headline. If the body does not support the headline, "do not create a signal … retain it only in the audit log if needed."
  - Company announcements: "prefer the original announcement for dates, amounts and executive names."
  - Chronology: "future plans, announced plans, completed actions and rumours must carry different statuses".
  - **FORMULA:** "News relevance score = 25% Recency + 30% HP relevance + 20% Strategic impact + 15% Actionability + 10% Source reliability. Store all five inputs used for the score." Step 5 adds: "Keep each input on a 0-100 scale."
  - "Why HP should care" "must be an implication, not a new fact" (example: "do not state 'the company will buy 5,000 PCs' unless a source directly supports that number").
  - **Sort / tie-break:** "Sort from highest to lowest News relevance score. If two items have the same score, show the newer event first." Step 7: "Show 12-20 items only when that many verified items exist."
  - Search keys (Step 1): "HP Sales Territory Name, official website, important subsidiaries and known executives."
- **Step labels:** Steps 1–7 `[Deterministic/Derived]`; Step 8 `[VLLM]` ("write the short HP implication from the verified event only"). All fallbacks are `[Deterministic/Derived]`.
- **Fallback:**
  - "Do not publish signals with a missing/invalid link, impossible date, wrong-account match, duplicate event ID or no usable evidence sentence. Keep them in a review list".
  - Sources disagree on date/value: "show the strongest-source value and retain a note that the sources disagree; do not silently average or merge".
  - Secondary reporting only: "retain the signal with a lower confidence".
  - HP implication cannot be grounded: "display the factual event without an HP implication".
  - "If fewer than 12 verified signals remain, show the smaller verified set. Do not add weaker or unrelated stories only to reach the 12-20 target".
- **Required output:**
  - Signal cards: headline, category, publication date, event date where different, urgency/relevance level and score.
  - "What happened" plus exact supporting sentence; entities mentioned.
  - "Why HP should care" kept separate; related HP category/play; recommended seller action.
  - Publisher, link, source type/reliability, confidence/verification, count and links of independent supporting sources.
  - "Filters by category/date, plus the current vs out-of-date behavior described in Feature 2, Stages 7 and 8."
  - "No duplicate cards for the same underlying event."

### 2.3 Stakeholder Map — "Feature 3 — Stakeholder Map", L54–63
- **POC:** paloalto-abm → Caterpillar (primary); hp-sea-abm → Sea Limited (HP data shape).
- **Target:** "the 20-30 people who are most relevant to an HP sale, instead of a long contact dump."
- **Data required:**
  - Name, title, department/function, seniority, location; company; LinkedIn.
  - "Email/phone where the subscribed source permits it"; reporting line "where available".
  - For priority contacts, "optional account-based talking points … These are not personal facts about the individual."
- **Sources:**
  - Primary: Apollo (base list, titles, seniority, email/phone).
  - Secondary: FullEnrich, Prospeo, SignalHire ("where Apollo is missing verified contact details or APAC coverage").
  - Tertiary: People Data Labs.
  - Verification/org context: LinkedIn, company leadership pages, Coresignal.
- **Rules / thresholds / formulas / precedence:**
  - **Person-match precedence:** "LinkedIn link first, then verified email, then name + company + title/location". Similar-name matching is "only as a secondary rule".
  - Merge field-by-field with field-level source details.
  - Keep the original title. Map separately to function and seniority (example: "'Senior Vice President, Global Workplace Technology' -> Executive / IT-Workplace").
  - Departments: "Information Technology (IT), Engineering, Operations, Finance, Procurement, Human Resources (HR), Executive, etc."
  - Former-employee detection: "never merge a former role into the current-role record without status". Active-map eligibility requires current affiliation "supported by a current data-source record, LinkedIn/company source or another recent verification signal". Former employees are marked Former/Out-of-date or excluded.
  - **Seniority mapping:** "Chief-level executive = Chief-level; Vice President = Vice President; Director = Director; Manager = Manager; all other non-manager roles = Individual Contributor. If the mapped seniority does not fit the original title, keep the original title and send only the mapped field for review."
  - Contacts: "Validate email/phone only from licensed sources … never infer an email pattern and label it verified"; "prevent unlicensed fields from entering the seller view".
  - Buying role is interpretation: a CIO may be "Decision Maker / High influence" but "must not state that the person owns the exact HP budget unless evidence says so".
  - Reporting lines are shown only when source-supported: "title hierarchy alone cannot be converted into a factual reporting line."
  - Talking points: "Do not claim to know the individual's private concerns, budget, motivation or opinion."
  - Dedup QA: one real person produces one active card.
  - Pre-ranking exclusion: records "missing both a reliable match to the correct company and a stable person identifier".
  - **Coverage check:** the top list must not be "20 people from one function when the buying committee requires IT, procurement, finance and business/operations coverage."
  - **Influence rules (Step 4):** "C-suite and senior IT/Engineering leaders = Decision Maker; Procurement roles = Budget Holder; technical IT/infrastructure/collaboration/engineering roles = Technical Evaluator; a known internal supporter = Champion; other relevant roles = Influencer. Use Blocker only when there is evidence that the person can stop or delay the purchase."
  - **FORMULA (Step 5):** "Stakeholder score = 25% seniority + 25% HP solution relevance + 20% influence + 15% data completeness + 15% priority."
  - Step 6: "sort contacts by Stakeholder score, then check buying-group coverage so the final 20-30 contacts cover the roles needed".
- **Step labels:** Steps 1–6 `[Deterministic/Derived]`; Step 7 (talking points) `[VLLM]`. All fallbacks are `[Deterministic/Derived]`.
- **Fallback:**
  - Conflicting current titles: "retain the newest/highest-confidence title but surface the conflict/last-verified date; do not silently concatenate titles."
  - No contact details: keep the person, "mark contact details unavailable rather than dropping the person".
  - "If the target 20-30 cannot be reached without low-confidence or out-of-date people, return the verified subset and show coverage by function/seniority so the gap is visible."
- **Required output:**
  - Ranked list "(target 20-30 where evidence supports that many)".
  - Name, original title, standardized function, seniority, location, company; LinkedIn, licensed email/phone with status.
  - "Influence type: Decision Maker / Budget Holder / Technical Evaluator / Champion / Influencer, plus High / Medium / Low priority and the rule/evidence basis". **[note]** Blocker appears in the Step 4 rules but not in this output list.
  - Reporting line "where known; unknown stays unknown".
  - Optional talking points, approach/entry point, linked priority/HP solution.
  - Source(s), last verified date, confidence, last-checked date, current/former.
  - Filters by function, seniority, influence, priority.

### 2.4 Solution Narrative / Opportunity Map — "Feature 4 — Solution Narrative / Opportunity Map", L65–74
- **POC:** paloalto-abm → Caterpillar → Solution Narrative / Solution Mapping; hp-sea-abm → Sea Limited → Opportunity Map / HP Plays.
- **Data required:** each strategic priority from Exec Dashboard; supporting evidence and trigger; tech gap/current vendor; stakeholder/persona; "HP product catalogue, value propositions and official HP proof points/case studies"; "Numeric impact only where evidence supports it."
- **Sources:**
  - Reuses Exec Dashboard priorities, Recent News, Tech Landscape, Stakeholder Map, and Intent (Intent "only as supporting evidence … Intent can strengthen the story but cannot create the opportunity by itself").
  - HP content: "only official HP product information, value messages, case studies, proof points and competitive guidance that match the verified need."
  - **Build rule:** "normally do not call Apollo, Exa, Coresignal, Bombora or another account-data provider again for this feature."
- **Rules / formulas / precedence:**
  - Controlled business theme, keeping the original wording and source sentence. Link each narrative to one or more concrete triggers and dedupe the triggers.
  - Tech states: "current vendor / confirmed HP footprint / likely gap / unknown; do not convert 'unknown' into whitespace."
  - HP products standardized to a catalogue ID/category.
  - **Numeric impact object:** "metric, baseline, assumption(s), formula, result, unit, source and confidence". Example: headcount growth supports a device estimate "only if the formula and assumption are visible".
  - Separate factual fields from derived fields (risk, opportunity, likely need, HP fit, recommendation).
  - "Rank narratives using evidence strength, timing/criticality and HP fit, not prose quality."
  - "do not create an account-specific narrative from generic industry trends alone. Keep the opportunity empty until account evidence supports it."
  - Example: "'office expansion' can support workplace-device/collaboration need; it does not automatically prove a printer refresh."
  - "Criticality/why-now labels must have an explicit basis such as recency, strategic importance, scale or deadline".
  - "A product cannot be recommended just because it belongs to HP's portfolio."
  - "Numeric impact must recalculate from stored inputs/formula … If a number cannot be reproduced … remove the number and keep the impact qualitative."
  - "do not invent a named buyer when only a persona is supported"; "likely/inferred gaps cannot be rewritten as confirmed problems."
  - Step 3: tech status (confirmed, likely, conflicting or unknown) drives "whether HP would expand, complement or compete".
  - **ORDERING (Step 7):** "no numeric opportunity score is defined. Order opportunities using three checks: (1) verified account evidence exists, (2) a current timing trigger exists, and (3) the HP product/play directly fits the need. Opportunities meeting all three checks come first; those missing one check come after them." Story shape: "account change -> likely need -> HP response -> proof -> stakeholder -> next action".
- **Step labels:** Steps 1–6 `[Deterministic/Derived]`; Step 7 `[VLLM]`. All 6 fallbacks are `[Deterministic/Derived]`.
- **Fallback:**
  - Do not publish a tile without a verified priority/trigger, defensible HP fit or traceable evidence chain. Keep it as draft. "A partial tile may be retained only if missing fields are explicitly marked."
  - Risk supported but no credible HP solution: keep the insight "without forcing a product recommendation".
  - Numeric impact fails: descriptive outcome instead.
  - No HP proof: "leave that proof section empty or show 'No supporting HP proof point available'. Do not insert an unrelated case study".
  - "combine two tiles that use the same trigger, need and HP solution unless they genuinely address different stakeholders/outcomes."
  - Acceptance requires "evidence/reference link, risk explanation, calculation basis for any numeric impact, target stakeholder and next action".
- **Required output:**
  - "Approximately 3-5 prioritized narrative/opportunity tiles where evidence supports them."
  - Per tile: priority/change, criticality, why-now trigger and date, reference sentence, source name/link/date, confidence and verification.
  - Tech/vendor/HP footprint/gap with confirmed/inferred/unknown; risk/opportunity plus explanation; need and HP solution/product.
  - Outcome, with numeric impact only "with baseline/inputs, assumptions, formula/method and 'how calculated' explanation visible".
  - Target stakeholder/persona, HP proof with link, next step.

### 2.5 Tech Landscape — "Feature 5 — Tech Landscape (Device Estate + Technology-use Map)", L76–85
- **POC:** paloalto-abm → Caterpillar → Tech Landscape; hp-sea-abm → Sea Limited → Technology-use Map / Device Estate.
- **Data required:** current vendor/product by category: "PCs/endpoints, operating systems, endpoint management, collaboration/Unified Communications (UC), meeting-room technology, security, print/Managed Print Services (MPS), cloud/productivity and other relevant categories"; detection source, date, confidence; confirmed/inferred/unknown.
- **Sources:**
  - Primary: Coresignal (technology-use/workforce) and TheirStack (job-posting inference).
  - Secondary: HG Insights (IT spend/install base), PredictLeads ("jobs, scripts and Domain Name System (DNS)").
  - Tertiary: BuiltWith.
  - Additional POC inputs: "Bombora technology-uses and internal technology-stack fields".
  - Build rule: multiple sources where possible. "A website technology finding should not be treated as proof of an internal hardware fleet."
- **Rules / thresholds / precedence:**
  - Normalise vendor names (for example "Microsoft 365 variants -> Microsoft 365") and keep the original text.
  - Categories: "PCs/endpoints, OS, endpoint management, collaboration/UC, meeting rooms, security, print/MPS, cloud/productivity, etc."
  - **Evidence types (separate from category):** "direct company statement, install-base provider, job-posting inference, web-tag technology finding, procurement reference, employee profile, other."
  - Merge the same vendor/product/category into one record with multiple evidence items.
  - **Conflict precedence:** "Resolve conflicts using evidence strength and recency, not provider count alone. Example: a current procurement document can override an older job-posting inference." "Never map 'not detected' to 'competitor absent'."
  - Derive the HP relationship "only after status is determined".
  - **Hardware rule:** "Hardware/device-estate claims require hardware/install-base/direct evidence; website tags or software job descriptions cannot by themselves confirm a physical PC, printer or room-device fleet." Step 4 repeats: "A web tag can support web software; it cannot by itself prove a PC, printer or meeting-room hardware fleet."
  - **STATUS RULE (stated 4 times):** "Confirmed = one direct company/procurement/install-base source, or at least two independent strong sources that agree. Likely/Inferred = one indirect source such as a job posting or website signal. Conflicting = reliable sources disagree. Unknown = no usable evidence."
  - **HP RELATIONSHIP RULE:** "HP already present = existing HP footprint; Compete = another vendor is confirmed in an HP-relevant category; Complement = HP can work alongside the confirmed technology; Possible open opportunity = the category need is supported but no vendor is confirmed."
  - Account attribution: product must belong to the account, "not a customer, supplier or technology mentioned in an article/job description."
  - Multi-vendor: "Mark conflict only when the sources claim mutually exclusive 'primary/standard' positions."
  - "HP whitespace is allowed only when the account need/category is supported and no current vendor is confirmed; label it a candidate, not a fact."
  - Opportunity notes claiming near-term displacement/expansion need "both the technology status and a timing/business trigger". Step 6: "raise priority only when a separate timing trigger exists, such as office expansion, refresh activity, hiring or another relevant change."
  - "Source link/date and evidence type must be present for every Confirmed or Likely finding shown to sellers."
  - One vendor may appear in multiple categories without duplicate rows in the same category.
  - "Unknown must remain Unknown."
- **Step labels:** all Steps 1–6 `[Deterministic/Derived]`; all fallbacks `[Deterministic/Derived]`. No LLM step.
- **Fallback:**
  - Unmapped/wrong-account/unsupported-category findings stay out of the seller view "rather than forcing them into 'Other' if that would mislead".
  - Conflicts: "display both findings with status/evidence until the conflict is resolved; do not choose whichever vendor is more favorable to HP."
  - No evidence: "show Unknown/No verified technology finding, not an empty card or 'No current vendor'."
  - Newer contradicting evidence: "mark the older finding Out-of-date before it can feed Competitive Displacement or Solution Narrative. Do not expire a finding only because of age unless that source has an explicit refresh interval in source configuration."
- **Required output:**
  - View grouped by category. Per finding: category, vendor, product, original text, evidence type, date found, source link.
  - "Confirmed / Likely-Inferred / Conflicting / Unknown with the evidence basis".
  - HP relationship: "existing HP footprint / compete / complement / whitespace candidate". **[note]** The output uses "whitespace candidate" while the rule uses "Possible open opportunity".
  - Opportunity/risk note with trigger; corroborating/conflicting sources retained; filters/expanders.

### 2.6 Objection Playbook — "Feature 6 — Objection Playbook", L87–96
- **POC:** hp-sea-abm → Sea Limited → Objection Playbook.
- **Data required:** current vendors/technologies from Tech Landscape; likely objections; account priorities and personas; "HP competitive messaging, official HP proof points and case studies."
- **Sources:**
  - Primary: cleaned Tech Landscape output plus priorities, recent signals and stakeholder context.
  - HP references: "official HP competitive battlecards, product collateral, case studies and proof points".
  - Secondary: "internal account claims or scoring outputs".
  - "No separate external provider pull is required".
- **Rules / precedence:**
  - Each objection starts from "a specific account evidence object: confirmed current vendor, strategic priority, procurement condition, timing signal, cost pressure or other verified situation."
  - **Entry schema:** "expected objection -> why likely -> response/reframe -> proof point -> counter-question -> source(s)". Step 4 gives the variant "objection -> HP reframe -> proof -> discovery question -> next action".
  - "An objection can be labelled account-specific only if the account evidence supports the premise. A generic 'too expensive' objection without account cost/procurement context should be labelled generic/persona guidance".
  - "a likely/unknown current vendor cannot be described as definitely deployed."
  - "Approved battlecard language or sourced competitive facts are required for factual comparisons"; "negative competitor claims require approved competitive evidence."
  - The proof must support the exact claim and be checked against the source link and HP content version.
  - Counter-question: "If a question assumes an unverified problem is already true, rewrite it as a neutral discovery question".
  - Persona mapping must be sensible and linked to Stakeholder Map roles; "use a named stakeholder only when the role is verified."
  - "covers the highest-value confirmed situations first rather than filling a fixed count with generic objections."
  - **ORDERING (Step 6):** "no numeric objection score is defined. Show objections with direct current account evidence first, then account-specific objections with weaker evidence, then generic persona guidance. Merge near-duplicate objections instead of filling a fixed count."
- **Step labels:** Steps 1–3 and 5–6 `[Deterministic/Derived]`; Step 4 (response creation) `[VLLM]`. Fallback: 3 `[Deterministic/Derived]` and the last one `[VLLM]`.
- **Fallback:**
  - Remove entries whose evidence has expired or been contradicted.
  - No approved competitive proof: "keep a neutral capability-based reframe and omit the comparative claim".
  - Merge wording-only duplicates, keeping persona variants.
  - [VLLM] "Do not publish an objection entry if a factual claim has no source/proof reference or if the counter-question contains an unsupported assumption."
- **Required output:**
  - "Prioritized objection cards/entries, typically 5-10 when evidence supports that many."
  - Per entry: objection, category, why expected, triggering evidence + source link/date/confidence, vendor/situation, target persona, HP reframe + category/product, HP proof with link/status, counter-question, next step.
  - "Clear distinction between sourced competitor fact, HP analysis and generic persona guidance."

### 2.7 Content Studio — "Feature 7 — Content Studio", L98–107
- **POC:** hp-sea-abm → Sea Limited → Content Studio (live AI).
- **Data required:** "No new external account research is required at click time". Uses built data (stakeholder/persona, priorities, narratives, signals, technology, HP proof points, seller objective). User inputs: "target persona, objective/topic and content format".
- **Sources:** finished account intelligence; official HP product/proof/content library; "Live AI layer: Gemini generates the content at click time". "No new Apollo, Exa, Coresignal, Bombora or other provider call should normally be needed".
- **Rules / thresholds:**
  - "retrieve the smallest relevant evidence set instead of the whole account record".
  - Rank facts "by relevance, recency and confidence; exclude low-confidence facts unless the user explicitly chooses to use them with a qualifier."
  - Standardize names before prompt assembly; dedupe proof.
  - Prompt slots: "trigger, account priority, persona context, HP value proposition, proof, next-step request".
  - Remove private/unlicensed contact data from model context.
  - Validation: "fail the output if a factual sentence has no matching evidence item"; persona belongs to the account; no other account/person from cached context.
  - **FORMAT RULES:**
    - "Email = maximum 110 words, one specific account fact or strategic priority, subject format 'Re: [specific initiative or challenge]', and a low-friction next step."
    - "LinkedIn Post = 2-3 variants, each 150-200 words, account/industry hook, HP insight, and a question or next step."
    - "One-Pager = maximum 400 words with Account Challenge, How HP Helps, Proof Points, and Next Step in that order."
    - "Do not show a result that breaks the selected format." Step 3 adds for Email: "end with a low-friction next step such as a briefing, workshop or assessment".
  - HP claims must match official HP content; remove any invented "capability, guarantee, Return on Investment (ROI) figure or customer result" and regenerate.
  - "do not infer private attributes, motivations or personal events"; the next-step request "cannot claim an existing meeting/project unless that is in the supplied context."
  - Step 4: "Do not send the full account dataset just because it is available."
- **Step labels:** Steps 1–3 `[Deterministic/Derived]`; Step 4 (send to Gemini) `[VLLM]`; Step 5 (sentence validation) `[Deterministic/Derived]`; Step 6 (regenerate/remove or fixed template) `[VLLM]`. Fallback: `[VLLM]`, `[D/D]`, `[D/D]`, `[VLLM]`, `[D/D]`.
- **Fallback:**
  - Unsupported facts: "strip/regenerate only the affected sentences using the same verified packet".
  - Thin persona context: "generate a role-based version and label the personalization basis".
  - No HP proof: "produce the content without proof or use an approved general HP capability statement; never substitute an unrelated customer story."
  - Wrong format: "re-run with constrained schema/formatting".
  - Live AI unavailable: "deterministic template populated with the verified trigger, persona, HP play and next-step request fields."
- **Required output:**
  - Generation controls (account, persona/contact, objective/topic, format).
  - "email, LinkedIn message and one-pager (plus any repo-supported format retained in the build)".
  - Copy with trigger, HP play, HP proof, next step; "used inputs" view.
  - "Regenerate, edit, copy and export/download actions"; validation/unsupported-claim state; safe fallback template.

### 2.8 Strategy Chat — "Feature 8 — Strategy Chat", L109–118
- **POC:** hp-sea-abm → Sea Limited → Strategy Chat (live AI).
- **Data required:** "No new external raw data at question time." Uses finished intelligence (facts, priorities, stakeholders, technology, signals, narratives, objections, intent, HP recommendations).
- **Sources:** the selected account's finished evidence layer; Gemini ("should not perform fresh open-web research by default"); show source links where available.
- **Rules / precedence:**
  - Classify question intent "(stakeholder, priority, technology, objection, opportunity, evidence, etc.)" and retrieve only matching fields.
  - **EVIDENCE ORDER:** "current verified evidence first; older verified evidence second; inferred/likely evidence last. When two items have the same status, use the newer source date first. Do not create a numeric evidence score unless a formula is added to this feature."
  - Merge duplicate evidence and keep the strongest plus independent support. Standardize names before the model call.
  - Compact context "with claim IDs/source links".
  - History is "scoped to the same account and reset/retrieve again when the selected account changes."
  - "Every factual answer sentence must map to retrieved evidence … cannot come from model memory."
  - Account isolation is validated before and after generation: "all retrieved claim IDs must belong to the selected account ID."
  - Fact vs recommendation separation ("'X is CIO' … 'X may be a strong entry point'").
  - Absent info: "answer that it is unavailable and optionally identify the closest available evidence; do not fill from open-web/model knowledge by default."
  - Links must correspond "to the exact claims cited". Conflicting evidence must be surfaced.
- **Step labels:** Steps 1–3 `[Deterministic/Derived]`; Step 4 (Gemini writes answer) `[VLLM]`; Steps 5–6 `[Deterministic/Derived]`. Fallback: `[VLLM]`, `[VLLM]`, `[D/D]`, `[VLLM]`.
- **Fallback:**
  - No relevant evidence: "skip generation and return an evidence-not-available state plus suggested in-platform modules".
  - Ungrounded name/number/product: do not show; regenerate. "if the problem remains, show the available evidence without a generated answer."
  - Broken links/stale claim IDs: answer from the remaining evidence and "flag the missing citation".
  - Model/API fails: "return the ranked retrieved evidence/cards".
- **Required output:** Q&A scoped to one account; answer followed by rationale; relevant stakeholders/priorities/tech/risks/HP play; evidence sentences and links; "Visible uncertainty/conflict or 'information not available' state"; account-safe follow-ups.

### 2.9 Message Evaluator — "Feature 9 — Message Evaluator", L120–129
- **POC:** hp-sea-abm → Sea Limited → Message Evaluator (live AI).
- **Data required:** pasted draft; target account and persona/contact; persona role, priorities, pain points and account context; message objective and format.
- **Sources:** seller draft; Stakeholder Map and account intelligence; Gemini for review and rewrite. "No new external data-provider pull is required at evaluation time".
- **Rules / thresholds / formulas:**
  - Preserve the original unchanged.
  - Dimension scores must be "numeric 0-100 … If a score is below 0, above 100 or not numeric, do not use it; ask the model for a corrected score and keep the original model output in the audit log."
  - Phrase feedback maps "to exact text spans". Factual-grounding issues are separate from style ("a polished unsupported claim must still be flagged as a factual problem").
  - Persona must belong to the account, with no other-account data.
  - Objective switch changes formula.
  - Persona reaction is "framed as a simulation … not as a factual statement".
  - Rewrites "preserve all verified facts … remove/qualify unsupported claims rather than making them stronger"; only the seller-selected changes are applied.
  - **FORMULAS (Step 4):**
    - "Awareness = 30% Relevance + 20% Impact + 20% Brand Recall + 15% Clarity + 15% Creativity"
    - "Engagement = 50% Relevance + 10% Impact + 20% Clarity + 10% Creativity + 10% Emotional Connection"
    - "Consideration = 40% Relevance + 10% Brand Recall + 10% Clarity + 10% Emotional Connection + 30% next-step strength"
    - "Conversion = 15% Relevance + 15% Impact + 25% Brand Recall + 10% Clarity + 5% Emotional Connection + 30% next-step strength"
- **Step labels:** Steps 1–2 `[D/D]`; Step 3 (Gemini dimensions + Keep/Improve/Change + persona reaction) `[VLLM]`; Steps 4–5 `[D/D]` (validate and weighted calc; span mapping); Step 6 (selective rewrite) `[VLLM]`. Fallback: `[VLLM]`, `[D/D]`, `[VLLM]`, `[D/D]`.
- **Fallback:**
  - Incomplete/missing dimensions, repeated phrase marker, or "overall score that does not match the weighted calculation": don't show; regenerate. "if it still fails, show only the checks that can be calculated without the model."
  - No persona grounding: "run a generic message-quality review only and label it accordingly".
  - AI scoring fails: "do not create dimension scores. Keep only checks that are explicitly coded in this feature, such as message length or whether a next-step request is present; mark the AI-scored dimensions unavailable."
  - Compare original vs rewrite for lost or invented facts.
- **Required output:**
  - Seller inputs (account, persona, objective, message).
  - "Overall score out of 100 with the objective/weighting profile used".
  - Dimension scores: Relevance, Impact, Brand Recall, Clarity, Creativity, Emotional Connection, next-step strength.
  - Keep/Improve/Change highlights with explanations; persona reaction "clearly labelled as simulation".
  - Improvements and rewrite using only selected recommendations; original vs revised; retry/edit/copy; validation/unavailable state.

### 2.10 Content Messaging — "Feature 15 — Content Messaging", L186–195
- **POC:** hp-sea-abm → Sea Limited → Content Messaging; repo `data/content-messaging/sea-content-messaging.ts`, `content-messaging.tsx`.
- **Purpose:** the account-specific "message house": main HP message plus messaging pillars.
- **Data required:** top priorities/challenges, HP solutions, competitive/technology context, verified proof points, official HP capability statements.
- **Sources:** already-built priorities, signals, tech/competitive findings, HP plays; official HP product resources/case studies. The doc says "The POC proof points use real source links where available; unsupported external facts are instead phrased as 'HP account analysis' or product capability statements."
- **Rules:**
  - "group it into 3-5 coherent messaging pillars".
  - **Pillar structure:** "Challenge -> HP Benefit -> HP Solutions -> Proof Points".
  - Dedupe proof across pillars "unless each use is clearly different".
  - Separate account facts, HP interpretation and official HP capability statements.
  - "Map each proof point to its exact source link and the claim it supports; do not attach one generic source to an entire pillar."
  - "Keep the umbrella message derived from the highest-priority pillars".
  - "The Challenge must be supported by account evidence and cannot be generic industry pain presented as an account fact."
  - HP Benefit is supported by official HP content. Product names are "current approved catalogue names".
  - External proof is verified against the link or revised/removed.
  - "Internal interpretations are labelled HP account analysis and are not given external-source styling."
  - "If two pillars repeat the same challenge and solution, merge them into one pillar".
  - The umbrella must add no new facts. The message house keeps "the same fields/order/actions as the referenced Content Messaging component".
  - Step 2: "store the account challenge and source before writing any HP benefit."
  - Step 6: "add target role/message angle/next-step request only where supported".
- **Step labels:** Steps 1–4 and 6 `[Deterministic/Derived]`; Step 5 (umbrella message) `[VLLM]`. All fallbacks are `[Deterministic/Derived]`.
- **Fallback:**
  - "Drop a pillar when its account challenge or proof base is too weak rather than filling the message house with generic copy."
  - Broken proof: keep the pillar only if challenge and benefit are still supported, and replace the proof with an approved one.
  - Consolidate repeated products/proof.
- **Required output:** "One account-specific umbrella message"; "3-5 messaging pillars when supported"; per pillar: title, Challenge + evidence, HP Benefit, HP Solutions, Proof Points with exact link/date/confidence, "internal interpretation clearly labelled HP account analysis"; trigger/priority and persona where represented; expand/copy/use-in-content actions.

### 2.11 Intent & Demand Signals — "Feature 10 — Intent & Demand Signals", L131–140
- **POC:** hp-sea-abm → Sea Limited → Intent & Demand Signals. The doc says "The attached build-story document treats this as the 10th in-scope feature and notes that it was built specifically for HP."
- **Data required:** "Raw topic-level intent scores"; "HP-category intent scores for categories such as PC, Workstation, Poly/Collaboration, Print and 3D where available"; source, date/time window, account/domain match.
- **Sources:**
  - Primary: "Bombora Company Surge".
  - Secondary: Intentsify.
  - Supporting: "internal HP-category intent mappings and, where available, PredictLeads / TheirStack-style enrichment".
  - "Keep the raw vendor intent signal separate from the HP-category mapping."
- **Rules / formulas / precedence:**
  - Preserve raw topic text, raw score, domain match, observation window and timestamp before mapping.
  - Topic dictionary normalisation "without changing the external source score".
  - **TOPIC → THEME:** "generative AI / ChatGPT / machine learning / Graphics Processing Unit (GPU) / AI compute -> AI & Compute; PC / laptop / endpoint / workstation hardware -> Devices & Endpoints; meeting room / video collaboration / unified communications / hybrid work -> Collaboration & Workplace; printer / print / managed print -> Print; 3D printing / additive manufacturing -> 3D; unclear topics -> Other / Unmapped."
  - **THEME → HP CATEGORY:** "Devices & Endpoints -> PC or Workstation only when the topic identifies which one; Collaboration & Workplace -> Poly/Collaboration; Print -> Print; 3D -> 3D; AI & Compute stays broad unless another account signal supports a specific HP category."
  - Dedupe within provider/time window; "distinguish multiple data sources rather than averaging them blindly."
  - Keep provider-supplied HP-category scores separate from internally mapped summaries.
  - Domain match must be validated.
  - **Cross-provider:** "Do not compare or average scores from different providers unless a provider-to-provider conversion formula is explicitly added … No such cross-provider conversion formula is defined in this document."
  - Mapping is versioned; flag unmapped/ambiguous topics "for review".
  - **Language guardrail:** "Intent is evidence of research activity only. Do not say the account is 'buying', 'in market' or has an approved project unless another source confirms it."
  - Aggregates recalculate exactly from included raw topics; "excluded/noisy topics cannot silently affect the aggregate."
  - "Trend labels require comparable prior windows from the same scoring definition/provider."
  - **FORMULAS (Step 5):** "Maximum = highest source score in the theme. Average = sum of source scores in the theme / number of included topics. Trend is valid only when the current and previous periods come from the same provider and scoring definition."
  - Step 7: "use intent only to strengthen an opportunity already supported by other account evidence. Never turn a strong research score into a confirmed buying project."
- **Step labels:** all Steps 1–7 `[Deterministic/Derived]`; all fallbacks `[Deterministic/Derived]`. No LLM step. **[note]** No step generates the "what this may mean for HP" explanation that the Required output asks for.
- **Fallback:**
  - No account match: "show Intent Unavailable/No matched signal rather than generating a zero score."
  - Ambiguous topic: "keep it broad/unmapped until a rule resolves it; do not force it into the category that creates the best sales story."
  - Scoring definitions changed: "break/flag the trend comparison".
  - Providers disagree: keep them separate and do not average.
- **Required output:**
  - Raw topic view (topic, score/intensity, provider, domain match, window).
  - Theme per topic (mapping repeated). HP-category view "clearly distinguishing provider-supplied vs internally mapped scores".
  - Max/average/trend; strength indicator and "short 'what this may mean for HP' explanation with related HP play/product".
  - "Confidence/source/refresh date and an explicit statement that intent indicates research activity, not confirmed purchase intent."

### 2.12 Cross-feature numeric summary (in-scope only)
| Item | Exact wording | Where |
|---|---|---|
| Strategic-priority evidence score | "40% support frequency + 25% supporting document sections + 20% recency + 15% independent external-source support" | F1 L39–40 (repeated in F11 Narrative Engine L147) |
| Urgency score | "20% Fleet Refresh + 25% AI/Workstation + 15% Hiring + 15% Expansion/Print + 25% Intent"; inputs 0–100; no score if any input missing; never 0% | F1 L37–40 |
| News relevance score | "25% Recency + 30% HP relevance + 20% Strategic impact + 15% Actionability + 10% Source reliability"; inputs 0–100; tie → newer event | F2 L48–50 |
| News count | "12-20 recent news/events per account"; show fewer if fewer verified | F2 L45, 50–51 |
| Stakeholder score | "25% seniority + 25% HP solution relevance + 20% influence + 15% data completeness + 15% priority" | F3 L60 |
| Stakeholder count | "20-30" | F3 L54, 60–63 |
| Opportunity tiles | "Approximately 3-5"; three-check ordering, no numeric score | F4 L72–74 |
| Tech status | Confirmed = 1 direct or ≥2 independent strong agreeing; Likely = 1 indirect; Conflicting; Unknown | F5 L82–83 |
| Objections | "typically 5-10"; 3-tier ordering, no numeric score | F6 L94–96 |
| Content formats | Email ≤110 words; LinkedIn 2–3 variants × 150–200 words; One-Pager ≤400 words, 4 fixed sections | F7 L103–104 |
| Message Evaluator | Four objective formulas (see 2.9); dimension scores 0–100 | F9 L127 |
| Intent summaries | Max / Average (sum ÷ n included) / Trend same-provider-only; no cross-provider formula | F10 L138 |
| Messaging pillars | "3-5" | F15 L192–195 |

### 2.13 Out-of-scope features covered in HP_ABX_v3_final (names only)
- With full sections: Feature 11 Narrative Engine; Feature 12 Competitive Displacement; Feature 13 Peer Benchmarking; Feature 14 Source Trail Explorer; Feature 16 Outreach Sequences; Feature 17 Account-Based Marketing (ABM) Toolkit; Feature 18 Sales Simulator; Feature 19 Deal Qualification (MEDDPICC); Feature 20 KPI Framework.
- Named in the classification list only, with no section: Opportunity / Account Planning; Account / Seller Briefing; Account Intelligence / Supporting View.

**[note] Out-of-scope rules that in-scope features depend on:** Source Trail Explorer (F14, L175–184) defines the verification statuses "Verified / Needs Review / Broken / Unsourced / Out-of-date". It also says "A calculated claim is Verified only when its input claims are Verified and the calculation/method is stored" and "an undated page should not inherit the crawl date as the publication date". All in-scope features rely on this claim/source layer. For reference only, the other numeric rules in out-of-scope sections are:
- Competitive threat rule: "if any validated competitor page is High, overall threat = High; otherwise if any page is Medium … Medium; otherwise … Low" (L159).
- Peer % difference: "(account value - peer value) / peer value × 100" (L171).
- Sales Simulator: overall = average of 4 categories. Difficulty: "C-suite = Advanced; Vice President = Advanced when … Decision Maker or Budget Holder, otherwise Intermediate; Director = Intermediate; Manager / Individual Contributor = Beginner" (L225).
- Deal Qualification bands: "0%-30% = Weak / Major Gaps; above 30%-60% = Developing / Needs Work; above 60%-80% = Strong / Good Position; above 80%-100% = Highest qualification band" (L236).
- KPI % change: "(target - baseline) / baseline × 100" (L247).

---

## 3. Rules from the additional-data doc (HP_220_Account_Platform_additional_data)

### 3.1 Scope and how to use (L3–21, L71–72)
- The decks "are only for the situations listed below. If a question or opportunity is not covered here, use the normal approved external research/retrieval flow and Gemini/LLM."
- "When both are needed, external sources explain what is happening at the account and the HP deck provides the HP product facts."
- If a rule matches: "use the mapped HP deck first, apply the guardrails, then let Gemini/LLM generate the answer." Worked example: ANZ Group AI adoption + device modernization → "Enterprise AI rule -> retrieve the mapped EliteBook 8 G2 deck -> use the exact allowed EliteBook 8 G2 product facts -> Gemini/LLM generates the recommendation."
- **Recommendation Flow (6 steps):**
  1. "Find the account need" (AI adoption, device refresh, security, competitor, mobility, expansion, hybrid work, desktop need).
  2. "Understand the users - Leadership / Specialist / Generalist / Frontline; enterprise vs SMB; mobile vs desk-based; premium vs value-focused."
  3. "Choose the device type - Notebook / Mini / SFF / Tower / AiO."
  4. "Choose the HP family - Elite / Pro / 200 / other suitable HP portfolio."
  5. "Retrieve the exact HP product facts - only from the deck mapped to the selected product. Keep product, country, configuration, and claim restrictions in place."
  6. "Generate the recommendation - combine the verified account need with the exact HP facts. The model should not invent either side."
- "Important: This is not the complete recommendation system. … Do not choose a product only because a vector search says it is similar."
- L72: "If yes, use the mapped HP deck as the preferred source for the HP product facts. If no, continue with normal approved research/retrieval. If both are needed, combine verified account evidence with the exact HP facts."

### 3.2 HP Deck Usage Rules (signal → deck), L23–40
| # | Signal / condition | Deck | Key usage constraint (quoted) |
|---|---|---|---|
| 1 | Enterprise AI / local AI: "AI adoption, GenAI programs, AI hiring, Copilot rollout, local AI workloads, AI-PC refresh, or knowledge-worker AI use" | HP EliteBook 8 G2 Series | "Do not choose it from an AI signal alone; the user type, scale, and device type must also fit." Facts include "up to 50 TOPS NPU", "5MP HDR IR camera", "up to 64GB memory where supported" |
| 2 | Enterprise AI at scale / standard fleet: "Large workforce, standard endpoint rollout, IT manageability, long lifecycle, global SKU, or cost control" | HP EliteBook 6 G2 Series | "Use EliteBook 6 G2 when the account needs enterprise AI across a large, repeatable fleet instead of the most premium device." |
| 3 | SMB / growing-business AI refresh | HP ProBook 4 G2 Series | "for growing businesses that need practical AI capability, hybrid-work features, and good value"; "sustainability facts only where the deck supports them" |
| 4 | Executive / senior leader | HP EliteBook Ultra G1i Customer Presentation | "senior, highly mobile executive who needs premium AI productivity"; facts incl. "up to 48 TOPS NPU", "9MP + IR camera", "under 1.2kg stated weight" |
| 5 | ARM / Snapdragon mobile AI | HP EliteBook Ultra G1q / G1q8 | "Use this route only when ARM/Snapdragon fits the account need. Do not replace Intel/AMD recommendations without a reason." Facts incl. "45 TOPS NPU", "Fast Charge up to 50% in 30 minutes under stated conditions" |
| 6 | Security / cyber risk | Mapped EliteBook / EliteDesk / ProBook deck | "Only security features supported by the selected model"; "quantum-resistant firmware claims only where allowed"; "Never copy a security feature from one model to another model." |
| 7 | Hybrid work / video meetings | Mapped EliteBook / ProBook / AiO deck | "First choose the right product family from the user type and scale. Then use only the collaboration features from that exact product." |
| 8 | Lenovo ThinkPad X1 Carbon Gen 13 found (technographics, procurement data or competitor research shows "this exact Lenovo model") | Competitive Playbook - EliteBook X G1i vs Lenovo ThinkPad X1 Carbon | Claims: "up to 85% higher CPU performance on the cited Cinebench test; up to 61% better office productivity on the cited Procyon test; cited battery differences; 44% less keycap wobble; …" "Keep the benchmark setup, date, and disclaimer with each claim." "Do not reuse these claims against Dell, Apple, another Lenovo model, or an unknown competitor." |
| 9 | Education / government / RFP notebook | HP 200 G2 Series | "consider HP 200 G2 subject to tender and country requirements." |
| 10 | Fixed-office AI / expandable desktop | HP EliteDesk 8 Tower G1i / G1i E | "desk-based power users who need expansion, multiple displays, and higher local compute"; facts incl. "13 TOPS NPU", "up to 8 displays with the required graphics/flex-I/O setup" |
| 11 | Compact desktop / branch / call center | HP EliteDesk 8 Mini G1i / HP ProDesk 4 Mini G1i | "Elite is the stronger enterprise option; Pro is the more value-focused option." |
| 12 | Integrated display / front desk / shared workspace | HP EliteStudio 8 AiO G1i / HP ProStudio 4 AiO G1i | "EliteStudio is higher-end; ProStudio is mainstream." |
| 13 | Desktop performance with smaller footprint | HP EliteDesk 8 SFF G1i | "Use SFF when Mini is too limited but Tower is larger than needed." |
| 14 | Sustainability / ESG | "Product deck for the product already selected" | "Do not choose a product only because of sustainability. Choose the product from the business need first, then add the supported ESG facts." "Keep country/status limits and source date." |
| 15 | Fleet serviceability / IT operations | EliteBook 8 / EliteDesk / mapped product deck | "Do not turn this into an AI story unless there is also AI evidence." |
| 16 | 5G / highly mobile workforce | Mapped notebook deck that supports 5G / HP Go | "Use Ultra/Elite for mobile executives and EliteBook/ProBook for broader mobile workforces … Do not treat HP Go as available everywhere." |
| 17 | User/persona routing before product selection | BPS Portfolio Sell-In Deck FY26 | "Use this deck first to choose the HP family. Then use the product-specific deck after the user type, scale, and device type are clear." Portfolio: "Elite = premium/high-value work …; Pro = SMB/mid-market, reliable and scalable; Chrome = speed/simplicity; Thin Client = cloud-first/virtualized; Fortis = education." |
| 18 | Why AI PCs now: "The account already has verified AI initiatives, but the device-refresh reason is not yet clear." | BPS Portfolio Sell-In Deck FY26 | "Use this to explain why AI-PC modernization may matter after AI adoption is already proven. Do not use HP messaging as proof that the account is adopting AI." |

### 3.3 Mandatory RAG Guardrails (L43–61)
Preamble: "These rules must be followed. If the system cannot verify a required condition, it should leave that claim out."
1. **Exact product binding:** "Use a product fact only for the exact product/model/variant named in the HP Deck Usage Rules." Example: the 9MP camera fact from Ultra G1i must not be used for other models.
2. **Superlative country block:** Romania, Slovakia, Turkey, UAE, Russia, Armenia, Belarus, Kazakhstan, Kyrgyzstan, Moldova, Tajikistan, Turkmenistan, Ukraine, China, Vietnam, Indonesia, Malaysia, Brazil, Mexico: "do not use the restricted superlative claims … The product can still be recommended using other allowed facts."
3. **Lenovo comparison block** in the markets on the competitive restriction list: "do not surface the Lenovo comparison percentages, superiority wording, or competitor-name claims".
4. **Exact competitor match:** only "when the account evidence or user question identifies Lenovo ThinkPad X1 Carbon Gen 13."
5. **Benchmark context:** "up to 85% higher CPU performance = Cinebench 2024 comparison; up to 61% better office productivity = Procyon Office Productivity comparison; battery-life claims = HP internal video-playback testing; trackpad claim = HP 85 mm x 120 mm vs Lenovo 56.2 mm x 120 mm". Keep the tested configurations and test date. "Do not turn the percentages into generic HP facts."
6. **Optional/config labels:** "Do not write an optional feature as standard." Examples: "5G modules must be configured at the factory; HP Go requires a supported 5G configuration and is described … as a US subscription service; Sure View is optional; OLED/touch/display upgrades are optional where listed; discrete graphics such as RTX 5050/A1000/A400/RX6300 are configuration-dependent; multi-display limits depend on the stated graphics/flex-I/O configuration; fingerprint readers, pens, KVM/Device Switch, and some cameras are optional".
7. **Connectivity:** "HP Go: use only for supported models/configurations and treat it as a US subscription service". "5G: use only when the selected product supports an optional 5G module, the module is configured at the factory, and carrier service is available in the account country." "Wi‑Fi 7: use only for a compatible Windows 11 system/processor with a separately purchased Wi‑Fi 7 router, and only in countries where Wi‑Fi 7 is supported. If these conditions are not known for the account, leave the feature out of the recommendation."
8. **Keep limitations:** "'up to' performance/TOPS/battery figures stay as 'up to'", and so on.
9. **Planned/future:** keep the wording. "Do not state that it is available now unless the RAG index contains a newer approved HP source confirming current availability."
10. **Embargo:** "Store embargo dates as metadata and block the affected product/processor claim before the embargo date." Dates given: "20 Mar 2026, 24–25 Mar 2026, and 31 Mar–3 Apr 2026 … already past as of 24 Aug 2026. The same automatic check must be applied to any new HP deck added later."
11. **Newest wins:** "For the same exact product/model, use the newest approved HP source date/version in the index. Do not combine an older generation or older specification with a newer product record."
12. **Confidentiality:** material marked "HP Confidential" / "For use by HP or Partner with Customers under HP CDA only": "Use this material only inside the agreed HP/partner access boundary."
13. **Decks cannot create account evidence:** "Do not use HP product decks to claim that an account is adopting AI, refreshing devices, using Lenovo, expanding offices, or facing a security problem."
14. **No forced deck:** "Do not choose an HP deck only because it contains similar words."
15. **AI-PC classes:** "Next Gen AI PC = 40–60 TOPS NPU; AI PC = below 40 TOPS NPU; non-AI PC = no NPU. Do not label a below-40-TOPS product as a Next Gen AI PC."
16. **No mixing generations/variants/form factors:** "G1, G2, G1i, G1a, G1q, G1q8, Flip, Notebook, Mini, SFF, Tower, and AiO records separate."
17. **Unverifiable → omit:** if the system cannot verify "exact product, country eligibility, configuration, competitor/model, benchmark context, source date/version, or availability condition", "do not generate that claim."

- **Country lists (L64–69):** "These lists apply only to the claims/slides that carry the stated restriction. They are not a ban on recommending the product itself." The Lenovo/competitor list is long: Middle East, most of Africa, French territories, China, Vietnam, Indonesia, Malaysia, Brazil, Mexico, and more. It adds "Also block in any CIS country covered by the playbook restriction. Store the CIS-country restriction as a market-level block in the rules table, not as a free-text note."
- **Implementation note (L70):** "Store these restrictions at claim level, not only at document level. Different slides in the same deck can have different restrictions."

### 3.4 Reporting & Usage Analytics module (L73–140)
- **Purpose:** "track how the HP Account Intelligence platform is being used and allow authorized users to ask questions about platform usage in natural language."
- **Track:**
  - Users (who/when); platform usage ("number of unique users, sessions, and activities over a selected period").
  - Feature usage per user; feature usage count.
  - Account usage ("which of the 220 accounts users viewed or worked on, and how often").
  - Queries ("questions submitted through Strategy Chat or other query-based features").
  - Query topic/category ("Tech Landscape, Stakeholders, News, Opportunities, HP Products, Competitors, etc.").
  - User-level activity; time ("filtered by day, week, month, or a custom date range").
- **Example NL questions (18, verbatim list L87–104):**
  - "How many users have used the platform this month?"
  - "How many active users did we have last week?"
  - "How many queries were asked about Tech Landscape this month?"
  - "Which feature is used the most?"
  - "Which features are used the least?"
  - "How many times was Recent News Signals viewed this month?"
  - "Which features did [User X] use?"
  - "How many times did [User X] use Tech Landscape?"
  - "How many different features did [User X] access?"
  - "Which accounts did [User X] view?"
  - "How many users viewed the ANZ Group account?"
  - "Which accounts are viewed most frequently?"
  - "How many questions were asked about ANZ Group?"
  - "What are the most common query topics across the platform?"
  - "Which users are using Strategy Chat most frequently?"
  - "How has platform usage changed from last month to this month?"
  - "Show me feature usage by user for the last 30 days."
  - "Show me the top 10 most-used features this month."
- **Expected module:**
  1. "Reporting Dashboard": total users and active users; total queries; feature usage; most/least-used features; account usage; query-topic distribution; usage trends over time.
  2. "Ask Reporting": NL interface "calculated from the platform's stored usage/activity data".
- **Binding implementation point:** "The reporting answers must come from captured platform usage/activity data. The LLM should not estimate or generate usage numbers from general knowledge." "For counts, rankings, totals, and trends, the calculation should be done from the structured reporting data. Gemini/LLM should mainly be used to understand the user's reporting question and present the result clearly." Example flow: "Stored usage/query logs → filter records for August → filter/classify Tech Landscape queries → calculate the count → Gemini/LLM presents the result".
- **Required logging:** "Usage events should be captured from the beginning so historical reporting can be produced later."
  - At minimum: `user_id`, `timestamp`, `account_id`, `feature`, `action`, `query_text` (when applicable), `query_topic`, `session_id`.
  - Example actions: "login", "account viewed", "feature opened", "query submitted", "content generated", "report viewed".

### 3.5 Human-in-the-loop
- **Not present in this extraction** (see 1.2). The nearest review behaviours are in the master doc:
  - F1 "account-name review list".
  - F2 "Keep them in a review list so the source or account match can be corrected and checked again".
  - F3 "send only the mapped field for review".
  - F10 "flag unmapped/ambiguous topics for review".
  - F14 "Needs Review" status and "Do not manually raise confidence or source reliability. If confidence changes, save the new evidence/reason and record the change in the audit history".
  - F4 draft status for incomplete tiles.
  - F19 "Seller Confirmed" status, and "seller confirmation wins over generated suggestions".
- None of these defines a reviewer role, queue owner or SLA.

---

## 4. Sourcing reference (11-Features-Sourcing-Reference-Anonymized)

### 4.1 Global sourcing rule (L4–10, quoted)
- "Default: Source A, for every field not covered by an exception below." The Source B column is "left blank (—) … it is not filled with 'not available'".
- "Hiring fields → Source B is major priority. Source A's contact/prospect sheet (14_Prospect_Contacts) was empty in every verified test; Source B's job_openings (title, normalized_title, seniority) is used wherever a hiring or role-proxy signal is needed."
- "Event fields → Google News RSS is primary, Source B's news_events is the add-on. Source A's News_Events sheet is not used (0 rows in every verified test)."
- "Technographic fields → Source A is major priority. Source B's technology_detections is shown for reference only alongside it, not as a replacement."
- "Contact-level fields (Stakeholder Map) → Source A only. No Source B column … since Source B has no contact/stakeholder endpoint in the verified export."
- "Intent fields → Source A for all general topics. One specific category — hiring-linked intent/demand — uses Source B (job_openings volume) … IntentTopic.source is explicitly typed as 'Source A' | 'Source B'."

### 4.2 Feature → source table
| # | Feature (doc heading) | Stated primary source | Field → Source A (sheet/column) / Source B | Notes as stated |
|---|---|---|---|---|
| 1 | Executive Dashboard | Source A | Company name → Company Name (1_Firmographics); Domain → Company Domain, Website; Business description; Industry → Naics, Naics Description, Sic Code, Sic Code Description, Linkedin Industry Category; HQ → Country/Region/City/Street/Zip; Employee count → "Number Of Employees Range"; Revenue → "Yearly Revenue Range"; Hierarchy → Parent Company Name, Ultimate Parent Name (2_Company_Hierarchy). Source B: — for all except hiring velocity | "Hiring velocity / urgency signal (UrgencyScore.breakdown.securityHiring-equivalent)": Source A "Not directly available (workforce % only)"; Source B "job_openings record count (Source B major priority -- hiring field)" |
| 2 | Recent News Signals | "Google News RSS (primary) + Source B (add-on)" | Headline, date, event type, source URL: Source A "Not used"; Google News RSS (primary) + news_events (summary, article_sentence; effective_date, found_at; category, event, financing_type; source fields) | Maps to LiveSignal[] (date, type, title, detail, sourceUrl, relevanceScore, salesAngle). Event type "includes 'Hiring', 'Financial', 'Technology', 'Strategic', 'Competitive'". "13_News_Events returned 0 rows in every verified test" |
| 3 | Stakeholder Map | Source A only | name, title, department, seniority, email + status, phone, LinkedIn URL → 14_Prospect_Contacts | "(empty in every verified test -- requires a live fetch-prospects + enrich-prospects call)"; no Source B column |
| 4 | Solution Narrative / Opportunity Map | Source A (narrative) + Google News RSS / Source B (trigger only) | Business outcome → Business Description (1_Firmographics); Tech stack → Full Tech Stack (4_Technographics) ("'howPaloAltoEnables'-equivalent framing"); Intent → Topic, Composite Score (11_intent_score); Trigger signal → Google News RSS + news_events | Maps to OutcomeMapping[] / OpportunityPlay[] (businessOutcome, quantifiedImpact, products, triggerSignal) |
| 5 | Tech Landscape | Source A (major priority) | Category → 4_Technographics category columns ("Testing And Qa, It Security, Devops And Development, Bi And Analytics, Computer Networks, Collaboration, Platform And Storage, and 13 more") vs department_onet_codes (reference only); Vendor/product → Full Tech Stack vs technology_detections rows (reference); Confidence → "Not a distinct confidence field in this export" vs score (reference); detectedVia/first-last seen → "Not present in this export" vs first_seen_at, last_seen_at (reference); Website tech → Cms, Ssl, Web Server, Hosting, Cdn, Framework, Analytics (5_Tech_Breakdown) vs "Not available in Source B export" | Maps to TechStackEntry[] / DeviceEstateEntry[]; "Source B is shown for reference only" |
| 6 | Objection Playbook | Source A | Incumbent technology → Full Tech Stack, category columns (4_Technographics); Company description → Business Description | Maps to Objection[] (objection, reframe, proofPoint, counterQuestion, likelyRaiser); "Synthesized from Tech Landscape fields" |
| 7 | Content Studio | Source A (named persona) / Source B (hiring-driven persona proxy) | Named persona → 14_Prospect_Contacts (empty); Role-type persona proxy → Source B job_openings (title, normalized_title, seniority); Company context → Business Description, industry fields | Persona built from Stakeholder Map + company context |
| 8 | Strategy Chat | Source A (primary), per-field rule for hiring/event/tech | Full account snapshot → "All Source A fields listed in Sections 1, 4, 5, 6" + job_openings + Google News RSS/news_events + technology_detections (reference only) | "Grounded in the full cached account snapshot. No new fields of its own" |
| 9 | Message Evaluator | Source A (named persona) / Source B (hiring proxy) | Same as Content Studio (named persona → 14_Prospect_Contacts; proxy → job_openings) | "persona defaults to Source A (Stakeholder Map), falls back to the Source B hiring field when no named contact exists" |
| 10 | Content Messaging | Source A + Google News RSS / Source B (event add-on for proof points) | Business Description; Full Tech Stack; Topic, Composite Score (11_intent_score); News event → Google News RSS + news_events | "Messaging pillars (challenge, benefit, proof point) draw from Source A fields by default" |
| 11 | Intent & Demand Signals | Source A (general topics) / Source B (hiring-linked only) | Topic → Topic (11_intent_score); Composite score → Composite Score; Level → "Level Of Intent (10_Intent_Topics)"; Hiring-linked category → Source A staffing-topic rows "remain Source A-sourced by default" + Source B "job_openings volume and seniority mix" | "General topic-level intent (Bombora composite scores) uses Source A for every topic". **[note]** This is the only place the doc links Source A to a named vendor (Bombora composite scores) |

### 4.3 [note] Where the sourcing reference conflicts with the master doc (not client text; flagged for the decision log)
- **Stakeholder Map:** master says primary is "Apollo", with FullEnrich/Prospeo/SignalHire, PDL, and Coresignal verification. Sourcing says "Source A only" from 14_Prospect_Contacts, which is "empty in every verified test".
- **Tech Landscape:** master names Coresignal/TheirStack primary and HG Insights/PredictLeads/BuiltWith after them. Sourcing says Source A is major priority and Source B is reference only.
- **Recent News:** master names "Exa and Google News RSS" as primary. Sourcing names Google News RSS primary + Source B add-on and does not mention Exa.
- **Event-type taxonomy:** master has 11 categories (Financial, Leadership, Hiring, Expansion, AI/Transformation, Security, Procurement, Partnership, Product/Business Expansion, Regulatory, Other). Sourcing's LiveSignal.type "includes 'Hiring', 'Financial', 'Technology', 'Strategic', 'Competitive'".
- **Exec Dashboard financials:** master wants "3-5 years of financial metrics … revenue, revenue growth, net income, headcount growth" from filings/IR. Sourcing maps revenue and employees to *range* fields only ("Yearly Revenue Range", "Number Of Employees Range").
- **Urgency Hiring driver:** sourcing labels it "UrgencyScore.breakdown.securityHiring-equivalent". The master formula's driver is "Hiring".

---

## 5. Open questions / TBDs / optional items stated inside the docs

**Explicitly undefined or left to upstream (master doc):**
1. Urgency drivers: "The current POC does not define a reusable raw-data-to-driver formula for all accounts. Do not invent one inside the dashboard." The driver calculation belongs to "the upstream data process", which is unspecified (F1 L37).
2. Opportunity ranking: "no numeric opportunity score is defined" (F4 L72).
3. Objection ranking: "no numeric objection score is defined" (F6 L94).
4. Strategy Chat: "Do not create a numeric evidence score unless a formula is added to this feature" (F8 L113).
5. Intent cross-provider: "No such cross-provider conversion formula is defined in this document" (F10 L137, L139).
6. The five inputs to the News relevance score (Recency, HP relevance, Strategic impact, Actionability, Source reliability) and the Stakeholder-score inputs (seniority, HP solution relevance, influence, data completeness, priority) must be on 0–100, but the doc gives **no input-level scoring scales**. The same applies to the Strategic-priority evidence score inputs (support frequency, document sections, recency, external support). **[note]** This is an observation; the doc does not flag it.
7. Out of scope: "there is no separate numeric page-level threat formula" (F12); "no automatic peer score" (F13).

**Refresh cadence:**

8. Recent News: "The scope calls for a monthly refresh". The classification section says only "a defined cadence" / "defined refresh schedule". Tech findings expire only if "that source has an explicit refresh interval in source configuration". No such configuration is given.

**Dangling references / inconsistencies in the master doc (observations):**

9. F2 Required output cites "the current vs out-of-date behavior described in Feature 2, Stages 7 and 8". **No Stage 7 or 8 exists**: every feature has Stages 1–6 plus Required output.
10. F3 Step 4 defines a "Blocker" influence type, but the Required output lists only "Decision Maker / Budget Holder / Technical Evaluator / Champion / Influencer".
11. F5 HP-relationship label is "Possible open opportunity" in the rules and "whitespace candidate" in the output.
12. F10 Required output asks for a "'what this may mean for HP' explanation", but no build step (all Deterministic) produces it.
13. F7 Required output says "LinkedIn message", while format rules say "LinkedIn Post"; "plus any repo-supported format retained in the build" is open-ended.
14. Classification lists three features with no section ("Opportunity / Account Planning", "Account / Seller Briefing", "Account Intelligence / Supporting View"). Implementation order ends at Phase 5, with no phase for the Live/Action tools.
15. Intent POC note refers to "The attached build-story document". That document is not among these three.
16. F1 Step 6 (executive summary generation) is labelled `[Deterministic/Derived]`, although its fallback treats it as a generated (`[VLLM]`) summary.

**Optional / conditional items (master doc):**

17. Talking points in Stakeholder Map are "optional". Email/phone appear "where the subscribed source permits it". Reporting lines appear "where available".
18. Bombora for dashboard intent "where available". HP-category intent scores "where available". PredictLeads/TheirStack enrichment for intent "where available". Bombora technology-uses in Tech Landscape "where available".
19. "Secondary sources to try" and "Tertiary / fallback" lists are framed as trials, not commitments. Examples: People Data Labs, InfobelPRO, Techsalerator, FullEnrich, Prospeo, SignalHire, Tavily, PredictLeads, TheirStack, HG Insights, BuiltWith, Intentsify, NewsAPI.org, GDELT.
20. Solution Narrative "normally" does not re-call providers. Content Studio: "No new … provider call should normally be needed".
21. Content Studio may use low-confidence facts only "if the user explicitly chooses to use them with a qualifier".
22. Out of scope: live competitor scan "if live scanning is enabled"; Gamma "only when the Gamma option is enabled"; ElevenLabs "only when voice mode is enabled".

**Additional-data doc:**

23. HP Go is described as a US subscription service "in the reviewed decks". Wi‑Fi 7 and 5G availability depend on account-country conditions: "If these conditions are not known for the account, leave the feature out". The doc gives no source for per-country carrier/Wi‑Fi 7 availability.
24. CIS countries: "Also block in any CIS country covered by the playbook restriction". The CIS country set is not enumerated.
25. Embargo dates are given as examples ("dates such as …"). The full embargo metadata must come from the decks.
26. Guardrail 12 gives the "agreed HP/partner access boundary" but does not define who is inside it.
27. "This is not the complete recommendation system": everything outside the 18 rules goes to "normal approved external research/retrieval". That flow is not defined in this doc.
28. Human-in-the-loop: the brief expects it in this doc, but it is absent from the extraction (see 1.2/3.5).

**Sourcing doc:**

29. Stakeholder Map depends on 14_Prospect_Contacts, which is "empty in every verified test -- requires a live fetch-prospects + enrich-prospects call". The contact source is therefore unresolved in practice.
30. Tech Landscape confidence: "Not a distinct confidence field in this export". detectedVia/first-last seen: "Not present in this export" in Source A.
31. Hiring-linked intent category: staffing topics "remain Source A-sourced by default", while job_openings drives "the hiring-linked intent category". The boundary between the two is not specified.
