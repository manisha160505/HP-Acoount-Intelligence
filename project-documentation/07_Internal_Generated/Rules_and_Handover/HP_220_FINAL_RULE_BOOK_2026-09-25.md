# HP 220-Account Intelligence: Final Rule Book

**As of:** 25 Sep 2026, after the client's round-3 answers (annotated OPEN_v2), the 25 Sep relevance-direction email and the domain-audit sheet.
**Audience:** the delivery team first. Once agreed, the "Final rule" column can go to BridgeAI as the single statement of how the product works.
**How it was built:** every client rule comes from `00_INDEX/DECISION_LOG.md`, the client logic documents in `02_Decision_Maker/` and the 25 Sep answers. Every "Build today" statement was read from the backend code on 25 Sep (file references are in §5). Nothing here is new policy. Where the documents disagree or say nothing, the row is marked OPEN.

### Status key

| Mark | Meaning |
|---|---|
| ✅ ALIGNED | The build already follows the final rule. |
| 🔧 CHANGE | The client rule is settled and the build does something different. This is engineering work. |
| ❓ OPEN | The client has not settled it. The interim rule in the table applies until they do. |
| 🟡 INTERNAL | Our own rule. The client has seen it or can see it but has not approved it. It stays until they object. |

### Which source wins
1. Client answers of 24–25 Sep (opens_1, opens_2, annotated OPEN_v2, the 25 Sep emails) and other dated client emails.
2. Client logic documents: Recommendation Tuning Logic v4 (23 Sep), Urgency Score Updated Final (16 Sep), Live Signal Scoring Logic (17 Sep), Tech Landscape Confidence FINAL (18 Sep), Combined Rulebook (v1 17 Sep is on this machine; the FINAL of 23 Sep is not).
3. HP_ABX_v3_final (22 Aug requirements).
4. Our HP-Account-Intelligence-Rules.docx (10 Sep). It is internal and was never approved. Where it disagrees with 1–3, it loses.

---

## 1. Rules that apply to every feature

### 1.1 Accounts, domains and names

| Rule | Final rule | Build today | Status |
|---|---|---|---|
| Account list | 220 accounts = Master List column B. The domain for 219 of them comes from `219 Account Audit` (PredictLeads_219_Account_Domain_Audit.xlsx). Astra comes from the separate seed delivery. (DEC-002, DEC-052, DEC-055) | The split reads the audit sheet; 219/219 domains match. | ✅ |
| Join key | Domain first, then Company Name + Country. Never vendor record IDs. Column H "Consider both names same" means one account whatever the vendor names. (DEC-013/014/052) | Split follows this. | ✅ |
| Shared domains (jabil.com, mufg.jp) | Four separate accounts. Rows are split by Company Name + Country once the client adds those columns. (DEC-015) | Interim: Jabil MY and MUFG JP get the domain-keyed rows; Jabil SG and MUFG Bangkok are near-empty. | ❓ client owes the columns |
| Name shown on screen | Audit sheet Column B ("Master Company"), never a vendor's company name. (DEC-052) | Features read the firmographics `Company Name`, then the account record, then "Target Account". | 🔧 read `audit_master_company` |
| Hierarchy | Use Explorium Company Hierarchy. A blank parent is ignored and nothing is written. (DEC-018) | As specified. | ✅ |
| Entity scope | The APAC entity as named; firmographics as delivered. (DEC-017: bare "RESOLVED") | As specified. | ❓ confirmation requested |
| Parent/subsidiary evidence | Do not combine a parent's, subsidiary's or other geography's evidence unless the mapping supports it (v4 §B). | Not enforced beyond the domain join. | ❓ v4's own Astra example uses "ASTRA Infra" (C-13) |

### 1.2 Data sources

| Stream | Final rule | Build today | Status |
|---|---|---|---|
| Firmographics / technographics / intent topics | Explorium (1_Firmographics, 4_Technographics, 5_Tech_Breakdown / WebStack, 11_intent_score). (DEC-011, DEC-019) | As specified. | ✅ |
| HP category intent | hp_intent_results is the **primary** intent signal. Bombora topics support it. (DEC-012) | As specified. | ✅ |
| Hiring | PredictLeads job_openings. Blank and closed postings within 12 months both count for urgency. (DEC-028) | As specified. | ✅ rule / ❓ 45 accounts' rows owed |
| News | Google News RSS + Exa, merged; PredictLeads news_events as an extra layer. (DEC-020) | google_news + news_events are read. | ✅ |
| Filings | filings 1.csv + PredictLeads sec_filings. Use document_url, else source_page_url, never local_path. Drop rows with neither. 12 months. A failing file is skipped, not the company. Re-key Fletcher, Fonterra and Hyundai; exclude the United Tractors row; Jabil 10-Q goes on both Jabil accounts. (DEC-025, DEC-054f) | The index is keyed; figures from the PDFs are not extracted (0/220). | 🔧 figures not extracted; ❓ Agribank/VPBank |
| PredictLeads extra sheets | Use sec_filings and products (products "mainly for recommendations"). Ignore the rest. (DEC-026) | products is not wired into recommendations. The list of features it should feed exists only in a screenshot we do not have. | ❓ need the feature list |
| Contacts | One Apollo file, still to come. Rows marked Pending/Review must not be used to infer a role or authority (v4 §A). (DEC-054e) | 0/220 accounts. The code reads `prospect_contacts` and does not filter on Pending/Review. | 🔧 add the status filter · ❓ file owed |
| Lifecycle file | v4 §J: a product past its PE/EM date is not recommended; one approaching end is recommended and flagged in the backend. The client's file note says "Not used as of now". (C-05) | lifecycle.py implements the check (last end date passed → blocked; within 180 days → flagged). The readable file is not on this machine. | ❓ which column, and is it in use |
| Feed relevance columns | Do not use the feeds' Low/High relevance_confidence. (DEC-024) | The value is passed into the Live Signals scoring prompt as `source_confidence`. | 🔧 remove it from the prompt |

### 1.3 Dates, windows, empty states, labels

| Rule | Final rule | Build today | Status |
|---|---|---|---|
| As-of date | Each dataset shows its own ingestion date. The recency anchor is that date, not the day the seller opens the page. (DEC-054d, v4 §E) | Widgets carry `extracted_at` (generation time). News recency is measured from `now()`. | 🔧 store an ingestion date per dataset; score recency from it |
| Look-back window | 12 months for news, hiring and filings. (DEC-023, DEC-025, DEC-028) | 365 days everywhere. | ✅ |
| Missing dataset | Leave the section out and write nothing. The same applies to the Stakeholder Map with no contacts. Provisional pending Sahaj. (DEC-054b) | Mixed. Some widgets return empty. Others show text such as "Intent unavailable: no Bombora intent topics on file", "No matching technology in Explorium sheets 4–5", "No supporting HP proof point available", "No matching contact identified in supplied data." | 🔧 hide the section; list the absent datasets in the run report |
| Source labels | Firmographics, Technographics, Hiring, News, Filings, Intent, HP Rulebook, HP case study. News cards show the publisher's name. No vendor names. Provisional pending Sahaj. (DEC-054c) | The UI still shows "Source A", "Source B", "Explorium sheets 4–5" and "Job Openings (Source B)". | 🔧 relabel in the frontend |
| Blank ≠ zero | "0 / No Signal" is a real signal state. A blank or dash means "unavailable" and must not be inferred. Blank technographics does not mean the technology is absent. (v4 §A) | Intent treats "No Signal" as an explicit state and blank as unavailable. | ✅ |

### 1.4 How a recommendation is reached (applies to every feature that names an HP offering)

**Relevance ladder** (DEC-040, DEC-053, 25 Sep email):
1. Start from the account evidence across all streams (firmographics, technographics, intent, news, hiring, filings) and say what opportunity it shows. Never start from an HP offering and look for evidence to fit it.
2. Only then check the Rulebook for an offering that supports **the same** use case.
3. Word the result by the strength of the evidence:
   - Technology only (for example Intune/ServiceNow): an internal "possible fit" only, **not recommended**. The context line reads "Intune detected; possible WXP integration route". Do not add "no evidence". (DEC-054g)
   - Technology plus related account evidence: "HP WXP **may be relevant** to this opportunity."
   - A clear opportunity plus the Rulebook's conditions supported: "HP WXP **is relevant** to this opportunity."
4. Conflicting evidence counts against the offering. Example: WebEx or TelePresence detected but Poly intent = 0 / No Signal means no active Poly recommendation.
5. A Rulebook condition that cannot be evaluated counts as unmet. The offering can reach "may be relevant" but never "is relevant". (DEC-054h)
6. If no offering fits, do not force one. Describe the evidenced opportunity without naming an HP solution (the print example in the 25 Sep email). (DEC-039)
7. Rulebook and case studies strengthen a recommendation; they never create the account's need. A general recommendation without a Rulebook match is allowed. A missing 3D or Workstation rule does not block a route. (DEC-039)

**Evidence tiers** (v4 §C, "initial build threshold"):

| Tier | Threshold | Permitted language |
|---|---|---|
| Opportunity | ≥ 2 logically related, independent streams support the same HP-addressable opportunity. The same event from RSS, Exa and a filing counts once. | May say the evidence supports an HP-addressable opportunity and recommend a seller focus. |
| Conversation Starter | 1 strong, directly relevant signal. | "creates a relevant conversation" / "may warrant discussion". No confirmed need or project. |
| Context Only | Weak, ambiguous or old evidence, or nothing HP-addressable. | Seller context only. No HP opportunity or product. |

If the account has one strong signal, return a Conversation Starter. If it has nothing, return nothing (see 1.3: the section is left out). Missing data lowers the strength of a recommendation; it must never make the model more creative.

| Item | Build today | Status |
|---|---|---|
| Evidence tiers | Implemented in evidence_tier.py. RSS + Exa + news_events count as one News stream. | ✅ |
| Which streams count | Build: firmographics and contacts are context only and cannot corroborate. v4's BHP example counts the employee range (firmographics) as a stream. | ❓ confirm (X-04) |
| Conflicting-evidence rule | Evidence tier: when the offering's own intent category is No Signal, detected technology stops counting as corroboration. Tech Map cards and Opportunity Map plays do not apply this. | 🔧 apply it on those two surfaces as well |
| Relevance ladder and graded wording | Nowhere implemented. Matching is on exact or alias technology names; the Opportunity Map is "fit / no fit"; the Tech Map uses a confidence % only. | 🔧 **largest change** (X-09) |
| Technology-only guard | Intune, Windows or Entra detected alone produces a WXP card at 70–100 % confidence. | 🔧 show it as a context line, not a recommendation (C-03, v4 K3) |
| Unevaluable = unmet | Rulebook conditions: country, management environment and OS are tested. Anything untested is flagged but the rule still fires. There is no "may be relevant" cap. | 🔧 |
| Seat count | Use the employee range as a proxy; do not ask sellers for seat counts; ignore "pending HP input" items. (DEC-045) | Employee range is used for a scale sentence only. The proxy thresholds (501 / 1,001 / 5,001) are not in the code. | 🔧 add them · ❓ thresholds await a yes |
| One main recommendation | Rulebook C 06: one main recommendation, plus another only when separate evidence supports it. Weaker routes are secondary hypotheses. (DEC-043, partly resolved) | Service plays: one primary, plus secondaries on separate evidence. Hardware plays: up to 5, ordered, with no "secondary" label. | ❓ client asked "which five routes?" |
| Confidence tier field | v4 requires `confidence_tier` on every output. T0–T3 are undefined. (DEC-044) | The tier name (Opportunity / Conversation Starter / Context Only) is stored. | ❓ |

### 1.5 Case studies (proof)

| Rule | Final rule | Build today | Status |
|---|---|---|---|
| Corpus | The 89 cleaned case studies. Corrupted figures are never shown. (DEC-042) | Corpus loaded. | ✅ |
| How a study is matched | Matched to the same **use case** as the account opportunity, never only on product name or industry. There is no Rulebook-to-case-study table; each is checked against the account on its own. (DEC-053, DEC-054i) | The study is chosen through the play's HP product line (`lines_for_hp_line`), with industry as a tie-break. | 🔧 match on use case |
| Four cases | Offering + study → use both. Offering only → offering only. Study only → study as supporting proof, no offering forced. Neither → nothing. (DEC-054i) | Case 3 (study without an offering) cannot happen, because a study is picked only from an offering's line. | 🔧 |
| Where studies appear | Opportunity Map (hardware and service plays), Objection Playbook, Content Studio, Content Messaging, and optionally Live Signals "Implication for HP", Intent "So what for HP" and Technographic Map "What it means for HP". **Not** on the Stakeholder Map for now. Nowhere else. (DEC-054j/k/l) | Studies attach on Opportunity hardware plays, Objection cards, Content Studio, Content Messaging and exec priorities. None on service plays, Live Signals, Intent or the Tech Map. | 🔧 add to service plays; optional on the three signal slots; check the exec-priority surface is allowed |
| No repeats | The same customer is not cited twice on one account. | A cross-feature "already cited" check exists. | ✅ 🟡 |
| Only at Opportunity tier? | Not answered: the client asked for the question again in plain words. (F11/D47) | Proof is attached to any play that passed the fit check, whatever its tier. | ❓ |
| APJ preference | v4 §H says "prefer APJ/APAC proof for APJ accounts". Whether this is the second sort key is unanswered. (F12/D48) | Not implemented. | ❓ (v4 text supports doing it) |
| Unvalidated studies | Studies missing source_url, unvalidated, or marked needs_manual_review are not shown to sellers. (v4 §A) | The 89 are pre-cleaned. | ✅ confirm the filter stays in code |

### 1.6 HP facts, grounding and banned output

| Rule | Final rule | Build today | Status |
|---|---|---|---|
| HP facts source | The Rulebook is the only runtime source of HP facts. The original HP decks are provenance only. (DEC-037, Rulebook C 02) | rulebook.py loads the **v1** Rulebook. The FINAL (23 Sep, with Print rules) is not on this machine. | 🔧 get and load the FINAL |
| Rulebook guardrails | C 01–C 10, product guardrails (country superlative blocks, Lenovo comparison block, AI-PC classes by TOPS, optional-feature labels, embargo dates, no mixing generations), service guardrails (WXP tier never auto-chosen, Care Pack seat thresholds 250/1,000/5,000, Wolf SCE 500–999 seats, HP IQ US/English only, and so on). | guardrails.py covers country blocks, the AI-PC classes, optional-feature qualifiers and planned-vs-available. | ✅ recheck once the FINAL arrives |
| HP numbers | Any HP number must have a verified HP source. Remove only that number, not the whole recommendation. (v4 §I) | Account prose: a number must appear as an exact token in the uploaded data. Case-study figures are verified against their own source. Rulebook facts are passed through as approved text. | 🟡 X-06: confirm the Rulebook counts as a verified source |
| Rule IDs | Never expose rule IDs such as "Rule WXP07 says…" to sellers. (v4 Rules) | Rule labels are sent to the prompt, not to the output. | ✅ |
| Banned outputs (v4 §K) | K1: no Poly from collaboration tech when Poly intent = 0. K2: one event is never counted as several corroborations. K3: no WXP buying intent from Intune/ServiceNow alone. K4: the lifecycle check applies only to products in the lifecycle file. | K1 partly (evidence tier only), K2 yes, K3 no, K4 yes. | 🔧 K1 on every surface, K3 |
| Overclaim words | Not client text. | Always banned: perfect time, perfect fit, the right time to, is ready to, guarantees, ensures, fully compatible, must have, ideal time. "require/needs/will need" only in sentences about the account. | 🟡 |
| Intent wording | Intent means research activity, not buying. "Increasing" means research is rising, not purchases. (ABX F10, v4 Rules) | In the prompts. | ✅ |

---

## 2. Feature by feature

Word limits are from v4 §G. "Build" is the code as of 25 Sep.

### F1 · Executive Dashboard (`executive_dashboard`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **exec_summary_card** | Name from audit Column B; HQ, industry, description; parent from the hierarchy sheet (blank parent → nothing shown). | Firmographics name; hierarchy rule as specified. | 🔧 name source · ✅ hierarchy |
| **exec_key_metrics** | ABX: 3–5 years of financials from filings (revenue, growth, net income, headcount growth), each with its period and currency. Until then, Explorium's ranges. | Employee range and revenue range as delivered; "N/A" when blank. | 🔧 financials from filings not built (S-05) |
| **exec_hiring_velocity** | Postings within 12 months. Label "Postings seen", with the open count beside it. (Our proposal, not yet approved.) | Counts **all** job rows as `open_job_count`, with no 12-month filter; 5 sample roles. | 🔧 relabel, apply the window, stop calling every row "open" · ❓ is blank = open? |
| **exec_urgency_score**: formula | 20 % Workplace Tech & OS + 25 % AI & Workstation + 30 % Growth & Expansion + 25 % HP Solution Intent. Each driver out of 100. (DEC-030) | As specified. | ✅ |
| – 60 % coverage rule | "The overall Urgency Score should only be calculated where at least 60 % of the weighted driver coverage is available." (16 Sep email) | Not implemented. A missing component scores 0 and the total always publishes. | 🔧 add the gate; below 60 %, leave the score out (per 1.3) |
| – Driver 1 Workplace Tech & OS | Scale 30 (≥50k=30, 10,001–49,999=25, 5,001–10k=20, 1,001–5k=15, 251–1k=10, <250=5) + OS mix 40 (highest rule wins) + workplace tech 30 (5+=30, 3–4=20, 1–2=10). | As specified. "10,001+" is scored 25. A bare "250" does not match any band. | ✅ · ❓ band gaps at exactly 250 and 0–1 % growth (C-08) |
| – which workplace tech counts | The Urgency doc counts Teams and VMware. The Rulebook's WXP 07 list does not include them. (C-04) | Published list in urgency.py. | ❓ |
| – Driver 2 AI & Workstation | Breadth 35 (4 families) + Depth 35 (signals + AI technologies) + Workstation intent/100×15 + AI events 5 each, max 15, within 12 months. | As specified. | ✅ |
| – Driver 3 Growth & Expansion | LinkedIn members growth 25 + hiring volume 50 (blank + closed, posted_at else first_seen_at, 12 months) + growth events 10 each, max 25. | As specified. | ✅ · ❓ which capex counts as "growth" (C-12) |
| – Driver 4 HP Solution Intent | Highest category: score/100×60 + trend 10 + stage 15 + volume 15. | As specified. The noisy-keyword gate is empty. | ✅ |
| – Rounding | Not defined. The worked example is inconsistent (64.43 "rounded" to 61). (C-07) | Each driver's contribution is rounded to 2 decimals; the headline is rounded half-up. | ❓ |
| **exec_strategic_priorities** | ABX: evidence score 40 % frequency + 25 % sections + 20 % recency + 15 % independent support; shown only with a supporting source sentence. v4: "Catalyst Explanation / Implication for HP + seller focus", 100–120 words, following the relevance ladder. | Our evidence-strength score (5 per filing up to 25 + recency up to 25 + 10 per source type up to 50); ordered by support count, then sections, then recency. 100–120-word description. At least one source sentence. | 🟡 our formula replaces ABX's (tell the client) · 🔧 description must follow the relevance ladder · 🔧 depends on filings figures |

### F2 · Live Signals (`recent_news_signals`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **news_signals_feed**: inputs | RSS + Exa merged, plus PredictLeads news_events. (The Live Signal doc also lists Explorium hiring events and job openings; v4 does not; C-01.) | google_news + news_events. | ✅ · ❓ hiring as a signal |
| – undated rows | Skip undated and 1970 rows; never skip the company. (DEC-021) | Unparseable dates are rejected; the company stays. | ✅ · ❓ client re-crawling Exa dates |
| – old rows | The client logic scores anything older than 365 days as 0/10. With the 12-month window they fall outside. | Rows older than 365 days are excluded. | ✅ (X-01 closed in practice by the window) |
| – duplicates | One event = one signal; keep the strongest source and retain every source as evidence. When Exa and RSS disagree, **keep the Exa row**. (DEC-054a) | Merge on headline similarity ≥ 0.85, or identical sentence + date. Every URL is kept. No Exa preference when the details differ. | 🔧 add the Exa rule · 🟡 same-event definition |
| – count and cut-off | **No 20-signal cap. No S/A/B/C tiers. No minimum score.** Every scored signal in the window is shown. (DEC-023, DEC-032) | **Cap 20, floor 2.0, S/A/B/C tiers still rendered** (scoring.yaml). | 🔧 remove all three |
| – order | By score, newer first on ties. (ABX) | As specified. | ✅ |
| **news_relevance_summary**: score | (Recency × 0.30) + (Relevance & Impact × 0.50) + (Source reliability × 0.20), out of 10. | As specified. | ✅ |
| – Recency | 0–7 d = 10 · 8–30 = 8 · 31–90 = 6 · 91–180 = 4 · 181–365 = 2 · older or undated = 0. Use the event date, else the publication date, never the crawl date. Age is measured to the ingestion date. | Bands correct. Age is measured to `now()`. | 🔧 measure to the ingestion date |
| – Relevance & Impact | 10 direct HP need / 8 HP-relevant tech or workplace initiative / 6 major business change / 3 weak / 0 none. Take the highest level, never add. Do not score a need that "might follow". | The model picks from {10, 8, 6, 3, 0} under these rules. | ✅ |
| – Source reliability | Score the underlying source, not the pipe: 10 first-party / 8 established reporting / 6 structured provider / 3 weak secondary / 0 unverifiable. | Python, with Google News URLs unwrapped. | ✅ |
| – "Implication for HP" | 70–100 words, following the relevance ladder. If nothing corroborates the event, present it as seller context and create no opportunity. Optional case study. | 70–100 words, grounded; banned phrases. Reads Opportunity Map, intent and tech context. No case study. | 🔧 ladder · 🔧 optional proof |

### F3 · Stakeholder Map (`stakeholder_map`), blocked until contacts arrive

| Component | Final rule | Build today | Status |
|---|---|---|---|
| Data | One Apollo contacts file (owed). Pending/Review rows are not used to infer anything. With no contacts, leave the space empty. | prospect_contacts; no status filter; empty widget when no rows. | ❓ file · 🔧 status filter · ✅ empty |
| **stakeholder_contacts_grid** | ABX: 20–30 people; composite 25 % seniority + 25 % HP relevance + 20 % influence + 15 % completeness + 15 % priority. v4 has **no** stakeholder score, and its contact file has no priority or phone field. | Composite as ABX, with our input scales. Priority contact ≥ 60 and not low relevance. Priority and phone are read. | 🟡 X-05: scales are ours; priority and phone will be empty in the Apollo file, so re-weight or drop them |
| **stakeholder_influence_map** | Decision Maker / Budget Holder / Technical Evaluator / Influencer. Champion and Blocker only on evidence. | Cascade as the Rules doc; Champion and Blocker never assigned. | 🟡 |
| **stakeholder_talking_points** | v4: "How to Open + HP Play Focus", **40–100 words**, from role + corroborated signals + qualified Opportunity Map plays. **No case study for now.** (DEC-054k) | 40–**90** words; no case study. | 🔧 limit to 100 · ✅ no proof |
| Other | Initials vs photo, LinkedIn/Apollo link format, "active employee" label. | — | ❓ QA16-6/7/8 unanswered |

### F4 · Opportunity Map (`solution_narrative_opportunity_map`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **opportunity_context_card** | Account context. | Description, ranges, top 10 intent topics, 40 tech items. | ✅ |
| **opportunity_trigger_signals** | Triggers from news, deduplicated. | 10 newest, deduplicated on headline. | ✅ |
| **opportunity_narrative_plays**: what it says | v4: "Why the opportunity exists + How HP enables + HP product/service/solution + proof where supported", **80–160 words**, built from several streams, not one signal. About 3–5 tiles (ABX). | Up to 5 hardware plays plus Rulebook service plays. **No word limit.** | 🔧 80–160 words · 🔧 relevance ladder |
| – Priority label | Keep Critical / High / Medium / Low; drop the three check tags. (DEC-034) Nothing in the client's text says what sets the label. | Tags hidden. Label = Critical (directly evidenced + second signal) / High (evidenced only) / Medium (some signal) / Low. Ordered by label, then checks met, then recency. | ✅ tags · ❓ C-09: tell the client our rule and ask them to confirm |
| – play families | Rulebook routes: hardware, WXP, Care Pack, lifecycle, deployment, Poly support, print/scan, HP IQ, Wolf; v4 examples also use 3D and Z workstations. (X-08) | Hardware: workstation, poly, pc, print, daas. Services: 8 Rulebook opportunity types. **No 3D play.** | 🔧 add a 3D route (DEC-039: evidence-led, no Rulebook rule needed) |
| – no-fit plays | Do not force an offering. With no offering, show the evidenced opportunity without an HP name. With nothing at all, leave the section out. | Plays that fail the fit check become "discovery areas" titled "… no supporting evidence in this account's data". The empty state says "No opportunity play met the evidence threshold…". | 🔧 rewrite per 1.3 and 1.4 step 6 |
| – proof | One use-case-matched case study per play, on **service plays too**. (DEC-054l) | Hardware plays: yes, matched by product line. Service plays: none. Without a study: "No supporting HP proof point available". | 🔧 service plays · 🔧 use-case match · 🔧 hide the "no proof" text |
| – Rulebook service plays | One primary, plus secondaries on separate evidence; max 3 rules per family; untested conditions flagged; market blocks (HP IQ US only). | As specified. | ✅ · 🔧 unmet/untested → "may be relevant" |
| – who to approach | Matched from the real contact list; otherwise name the owning function. | As specified (blocked by contacts). | 🟡 |

### F5 · Technographic Map (`tech_landscape`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **technographic_map**: confidence | % = [(Driver 1 × 0.70) + (Driver 2 × 0.30)] × 10. Driver 1: 10 = Rulebook names the technology for this route, 5 = related, 0 = none → **no card**. Driver 2: **only the card's own category** intent (50–100 = 10, 25–49 = 5, 0–24 or missing = 0). (DEC-033) | As specified; possible values 35/50/65/70/85/100 %. | ✅ |
| – what the card may claim | The confidence says how well the evidence supports the card. It is not a recommendation. Technology alone is a "possible integration route" (1.4). | A Windows or Intune detection gives a WXP card at 70–100 %, and the card's `hp_play` reads as a recommendation. | 🔧 C-03 / K3 |
| – risk labels | Keep Low / Medium / High Risk (SEA Limited parity). (DEC-035) Our logic: High = a competing vendor confirmed in a category HP sells into; Medium = need supported, no vendor, and always on HP's own absence row; Low = HP can sit alongside; no label where HP has no line. | As specified. | ✅ labels · ❓ logic awaiting Sahaj |
| – "Contextual — no direct HP line" tag | Not in any client document. | Shown for client OS and UEM/MDM. | ❓ E23-3 unanswered |
| – status words | ABX: Confirmed / Likely / Conflicting / Unknown. Web tags cannot prove a hardware fleet. | Confirmed / Likely / Unknown. | ✅ |
| – header | — | "N found, M map to HP categories". About 200 unmapped technologies cannot be browsed. | 🟡 QA16-11 |
| – "What it means for HP" | 70–100 words: a displacement, attach, upgrade, coexistence or whitespace motion, corroborated by intent, hiring, news or filings. Optional case study. | 70–100 words (map_narrative). No case study. | ✅ length · 🔧 ladder · 🔧 optional proof |
| **tech_stack_matrix / tech_detections_reference / webstack_breakdown** | Raw evidence views. | Raw columns as delivered. | ✅ |
| **technographic_hp_recommendations** | Extra "Recommendation for HP" card per section: **drop for now**. (DEC-010) | The widget is still generated (Part A and Part B rules with evidence tiers). | 🔧 hide it or confirm that it is the card the client dropped |
| Related Technologies | hp_intent "Related Technologies" is a fallback for technographics and is **researched**, not detected. (DEC-019) | Shown in the Intent summary, not presented as confirmed. Not used as a Tech Map fallback. | 🟡 D22 · 🔧 fallback for the 13 accounts without technographics |

### F6 · Intent & Demand Signals (`intent_demand_signals`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **intent_category_summary** | Category score from hp_intent_results is primary (PC, Workstation, Poly, Print, 3D), shown as received. Bombora topics support it with their exact scores. Technographics/WebStack confirm. (DEC-012) | As specified; highest category is primary. | ✅ |
| – noisy keywords | Our earlier rule ("SLA", "identified as competitor of" never primary) vs the input contract's "empty by client instruction". No client email found either way. (I-07) | List is empty. | ❓ confirm, then close |
| – "So what for HP" | 80–90 words per prioritised theme, worded by evidence tier, following the ladder. Optional case study. | 80–90 words, worded by tier. No case study. | ✅ length · 🔧 ladder · 🔧 optional proof |
| **intent_topics_table** | Raw Bombora topics → theme → HP category (conservative; ambiguous topics flagged, never forced). Max / Average / Trend only within one provider. | As specified. When topics are missing it shows "Intent unavailable…". | ✅ · 🔧 hide instead of the message |
| **intent_hiring_demand** | "Postings seen" + open count. Whether blank = open is unanswered. (D27) | "Postings seen" + "open postings" (blank counted as open). | 🟡 ❓ |
| Coverage | Intent exists for 173/220; the rest are genuine no-data cases → section left out. NSW Education intent file is not on this machine. | — | ❓ NSW file |

### F7 · Objection Playbook (`objection_playbook`)

v4 has no row for this feature. The client accepted our method under the four-case rule (DEC-054j).

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **objection_incumbent_context** | Incumbents per area from technographics; "not in technographics" never means "no incumbent". | 5 areas: Client Devices, Collaboration, Print/MPS, Endpoint Security, Device Management; field named `not_in_technographics`. | ✅ 🟡 |
| **objection_reframe_cards** | ABX: typically 5–10; evidenced objections first, then weaker, then generic; merge near-duplicates; neutral discovery question; no factual comparison without approved competitive evidence. | Up to 10; merged at 0.85 similarity; 3 Rulebook rules per area; sector words rejected as justification; internal vocabulary banned. | ✅ 🟡 |
| – who raises it | "Could be raised by" / "Topic owner". Never "Likely raised by", because no data shows who will raise it. (DEC-049) | As specified. | 🟡 QA16-1 awaits the client |
| – proof | One use-case-matched case study per area card. If none, show nothing (1.3). | One per area, matched by product line; "No supporting HP proof point available" when none. | 🔧 use-case match · 🔧 hide the text · ❓ Opportunity-tier gate (F11) |
| – Counter Question | — | Rendered in capitals; the QA check said it was missing. | 🟡 QA16-2 |

### F8 · Content Studio (`content_studio`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **content_persona_context** | Persona from contacts; otherwise from hiring roles. Never name a person who is not in the data. | 8 named (from the Stakeholder Map), else 5 hiring-role proxies, else 7 fixed archetypes. | ✅ 🟡 archetypes are ours |
| **content_angle_options** | Human in the loop: brief → options → user picks → generate. (DEC-004) | 3 angles, each on different evidence; user picks. | ✅ |
| **content_generated_assets** | Email ≤ 110 words, subject "Re: …", low-friction next step; LinkedIn 2–3 variants × 150–200 words; One-Pager ≤ 400 words in the order Account Challenge / How HP Helps / Proof Points / Next Step. HP facts from the Rulebook only. No private attributes. A deterministic template if the model fails. | As specified, plus 4 more formats (Executive Brief, Follow-up, Branded Emailer, Landing Page); at most one HP line, and only if earned; proof chosen after generation by product line. | ✅ 🟡 extra formats · 🔧 use-case match for proof |

### F9 · Strategy Chat (`strategy_chat`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **strategy_snapshot_context** | Answers only from the account's finished data; no web research by default. | Counts from finished widgets; 6 starter questions. | ✅ |
| **strategy_chat_interface** | Every factual sentence cites retrieved evidence; order current-verified → older → inferred; say "not available" when it is not; no numeric evidence score; one account only. | chat.py answers with bracketed evidence citations and checks figures against the retrieved passages. Whether the "information not available / uncertainty" state works end to end was not re-verified today. | ✅ 🟡 QA16-9 · test before sign-off |
| Data | Filings, Rulebook and case studies feed it (18 Sep file note). | Rulebook and filings go through the retrieval index; filings figures are not extracted. | 🔧 depends on filings |

### F10 · Message Evaluator (`message_evaluator`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **evaluator_persona_context** | Persona from contacts, else from hiring roles; persona reaction is labelled as a simulation. | 8 named, else 8 hiring-role clusters. | ✅ |
| **evaluator_feedback_score** | Awareness 30/20/20/15/15 · Engagement 50/10/20/10/10 · Consideration 40/10/10/10/30 · Conversion 15/15/25/10/5/30; each dimension 0–100; no overall score if any dimension is invalid. | As specified, plus an **Advocacy** objective taken from the reference app (not in the spec) and bands (Strong ≥ 80 … Poor < 20). | ✅ 🟡 Advocacy and bands are ours |

### F11 · Content Messaging (`content_messaging`)

| Component | Final rule | Build today | Status |
|---|---|---|---|
| **messaging_context_card** | Context from firmographics, tech, intent and news. | As specified. | ✅ |
| **messaging_pillars_output** | 3–5 pillars, each with its own evidence: Challenge → HP Benefit → HP Solutions → Proof; **90–150 words per pillar**; umbrella message adds no new facts; merge repeated pillars; no duplicate proof; drop weak pillars. | 90–150 words; merge; proof deduplicated. Unsourced proof is **deleted** rather than labelled "HP account analysis". | ✅ · 🟡 QA16-4 · 🔧 ladder and use-case proof |

### Module 12 · Reporting & Usage Analytics (not one of the 11)
Requested 24 Aug (DEC-004): log user, timestamp, account, feature, action, query text, query topic and session from day one; a reporting dashboard plus "Ask Reporting" computed from the logs, never estimated by the model. **Status: no build or plan recorded anywhere.** ❓ Ask Sahaj whether it is in this delivery.

---

## 3. Build changes, in order

Settled client rules that the build does not follow yet:

1. **Relevance ladder and graded wording** across the Opportunity Map, Tech Map, Live Signals, Intent, Exec priorities and Content Messaging. This includes "technology only" as a context line (K3), conflicting-evidence blocks on every surface (K1), and unevaluable conditions capped at "may be relevant".
2. **Case studies matched on use case, not product line.** Add the four-case rule, proof on service plays, and optional proof on the three signal slots. Keep proof off the Stakeholder Map.
3. **Live Signals:** remove the 20 cap, the 2.0 floor and the S/A/B/C tiers; keep the Exa row when the feeds disagree; stop sending relevance_confidence to the model; measure recency to the ingestion date.
4. **Empty states:** hide the section instead of showing "unavailable / no proof / no contact / no supporting evidence" text; list the absent datasets in the run report.
5. **Source labels:** replace "Source A/B" and "Explorium sheets 4–5" with the agreed labels; show publisher names on news cards.
6. **As-of date** per dataset, taken from the ingestion date.
7. **Display name** from audit Column B.
8. **Urgency:** add the 60 % weighted-coverage gate.
9. **Exec hiring velocity:** 12-month window, and label "Postings seen", not "open".
10. **Word limits:** Opportunity Map 80–160; Stakeholder "How to open" up to 100.
11. **3D play** on the Opportunity Map.
12. **Hide `technographic_hp_recommendations`**, if it is the card the client dropped (DEC-010).
13. **Contacts:** filter Pending/Review rows when the Apollo file lands; re-weight the stakeholder score for the missing priority and phone fields.
14. **Seat proxy** from the employee range (501 / 1,001 / 5,001) once the thresholds are approved.
15. **Filings:** extract financial figures for key metrics and priorities.
16. **Load the FINAL Rulebook** (23 Sep, with Print rules) once we have the file.

## 4. Still open with the client

| # | Question | Owner | Interim rule |
|---|---|---|---|
| 1 | Contacts file (the one file) | Client | Stakeholder Map left out; four features run on hiring-role personas |
| 2 | Company Name + Country columns for jabil.com / mufg.jp rows | Client | Jabil MY and MUFG JP hold the rows |
| 3 | Exa dates re-crawl; job rows for 45 accounts | Client | Undated rows skipped; hiring left out |
| 4 | Tech Map risk-label logic; GCP access | Sahaj | Our lookup; current environment |
| 5 | Proof only at Opportunity tier? (F11) · APJ proof first? (F12) | Client (re-ask plainly) | No gate · APJ first (v4 §H) |
| 6 | One main route vs five routes (D34) | Client | One primary + secondary hypotheses |
| 7 | T0–T3 confidence tiers (D35) | Client | Store the evidence-tier name |
| 8 | Employee-range thresholds for seats; which Lifecycle column, and is the file in use | Client | Thresholds not applied; lifecycle check on, with no file loaded |
| 9 | What sets the Opportunity Priority label (C-09) | Client | Our rule (§F4) |
| 10 | "Contextual — no direct HP line" tag (E23-3) | Client | Keep |
| 11 | Urgency: rounding, band gaps (exactly 250, 0–1 %), Teams/VMware as qualifying tech, capex-as-growth | Client | As built |
| 12 | Parent/subsidiary evidence (C-13); entity scope confirmation (D2) | Client | APAC entity as named |
| 13 | Blank job status = open or unknown (D27) | Client | Counted as open |
| 14 | Which streams count toward the Opportunity tier: firmographics? (X-04) | Client | Firmographics and contacts are context only |
| 15 | Same-event definition for news (X-02) | Client (silence = yes) | Headline similarity ≥ 0.85 or same sentence + date |
| 16 | Products sheet feature list (screenshot) | Client | Not used |
| 17 | 16 Sep QA points (QA16-1…12), the 22 Sep UI test doc, feedback on our Rules doc | Client | As built |
| 18 | Vendor-flagged rows (9) (D25) | Client | Drop them |
| 19 | Agribank / VPBank filings (R3 C1) | Client | None shown |
| 20 | Reporting & Usage Analytics module in scope? | Sahaj | Not built |
| 21 | Files we still need: FINAL Rulebook, readable Lifecycle, NSW intent, filings PDFs | Client | v1 Rulebook |

## 5. Where each "Build today" statement comes from (code, 25 Sep)
- Urgency: `hp-backend/src/app/services/dashboard/urgency.py`, `config/scoring.yaml` (driver bands; no coverage gate).
- Live Signals: `extractors/recent_news_signals.py` (Gate 0, dedup 0.85, `[:MAX_SIGNALS]` at l.1024, floor at l.1017, `source_confidence` in the prompt at l.604), `extractors/signal_scoring.py` (weights, bands, tiers), `config/scoring.yaml` l.113–145 (tiers, floor and cap annotated as "delivery decisions, not in the client document").
- Evidence tiers and K1: `hp/evidence_tier.py` l.140–180.
- Tech confidence and risk labels: `hp/tech_confidence.py`, `extractors/tech_landscape.py` l.64–81; narrative length in `hp/map_narrative.py` l.45–46.
- Opportunity Map priority, proof and caps: `extractors/solution_narrative_opportunity_map.py` (MAX_PLAYS l.90, NO_PROOF_POINT l.138, proof by product line l.1550–1585).
- Case-study surfaces: `hp/case_studies.py` l.390–402 (objections, opportunities, messaging, content, exec priorities only).
- Intent: `extractors/intent_demand_signals.py`, `hp/intent_topic_map.py` l.361–375 (noisy list empty).
- Stakeholder: `extractors/stakeholder_map.py` (weights, ≥ 60, opener 40–90).
- Labels: `hp-frontend/src/app/dashboard/page.tsx` l.1076, 2617, 2689; `hp-frontend/src/types/widget.ts` l.40.
- Pillars: `messaging/pillars.py` l.62–63.
