# Conflict Register

Places where two sources disagree. Nothing here is resolved by judgement; each entry records what each document says, the latest known source, the interpretation the build currently follows, and whether confirmation is needed. Three families:

- **C-xx** client document vs client document
- **X-xx** client document vs the delivery team's rules / build
- **I-xx** internal document vs internal document (or vs the split output)
- **S-xx** sourcing reference (31 Aug) vs master requirements (22 Aug)

Numbers and quotes come from the plain-text extractions of the documents; the detailed rule-by-rule register is in `03_Feature_and_Logic/_extraction_notes/B_scoring_and_rulebook.md` (generated, verify before relying on a number).

---

## C. Client document vs client document

### C-01 · Live Signals: which datasets feed the score
- **Doc A (HP_Live_Signal_Scoring_Logic, 17 Sep) says:** scores Explorium `12_Hiring_Events`, PredictLeads `news_events` and `job_openings`, Google News RSS and Exa.
- **Doc B (Recommendation Tuning Logic v4, 23 Sep) says:** the Input Contract has no `12_Hiring_Events` or PredictLeads `news_events` stream; RSS fields include event_summary / signal_categories / matched_keywords, which Doc A omits.
- **Latest known source:** v4 (23 Sep). · **Current interpretation:** Live Signals reads google_news (RSS + Exa) and news_events (PredictLeads) per FEATURE_MAPPINGS. · **Needs confirmation:** YES.

### C-02 · Recency reference date
- **A (Live Signal Logic):** age measured to a "Scoring date: 17 September 2026". · **B (v4 §E):** every output carries `data_as_of_date` = "the date the dataset was ingested … not the date the seller happens to open the dashboard". · **C (Urgency):** "latest 12 months" with no anchor.
- **Latest:** v4. · **Interpretation:** ingestion date; the as-of date itself is OPEN (DEC-048). · **Needs confirmation:** YES.

### C-03 · WXP from a technology detection alone
- **A (Tech Landscape Confidence FINAL, 18 Sep):** "Microsoft Windows detected" → WXP 04 → Driver 1 = 10/10 with a card "Consider HP Workforce Experience Platform (WXP)"; Intune alone also 10/10.
- **B (v4 §K3 banned output, 23 Sep):** "State that the account has WXP buying intent because Microsoft Intune or ServiceNow is detected" is BANNED; allowed "only when a separate account signal establishes a relevant endpoint-experience or fleet-management need." Dhruvi 24 Sep: "Intune/ServiceNow detected alone -> possible WXP fit, but not enough to recommend WXP."
- **Latest:** 24 Sep relevance rule. · **Interpretation:** a Tech Landscape confidence card is not a recommendation; the recommendation layer applies the 24 Sep rule. Whether the card wording "Consider WXP" itself violates K3 is unanswered. · **Needs confirmation:** YES.

### C-04 · Qualifying workplace technologies for the Urgency Score
- **A (Urgency §1C):** counts Microsoft Teams ("supported through HP Workforce Experience Platform integrations") and VMware ("relevant to HP Anyware"). · **B (Rulebook WXP 07):** integrations are "ServiceNow, Microsoft Intune, Power BI, Power Automate, Tableau, and Microsoft Entra ID"; Teams is not listed and HP Anyware does not appear in the Rulebook. Tech Landscape logic treats Azure as only "related" because it is not in WXP 07.
- **Latest:** Rulebook FINAL 23 Sep (not local). · **Interpretation:** urgency follows its own document. · **Needs confirmation:** YES.

### C-05 · Lifecycle file: used or not
- **A (new file explanation, 18 Sep; Dhruvi 18 Sep email):** "HP Lifecycle June 2026 — Not used as of now"; Fleet Refresh excluded. · **B (v4 §J and §K4):** check the Lifecycle file before surfacing an offering; a product past PE/EM must not be recommended. · **C (opens_2 item 38):** "lifecycle date, which columns to look into? -> clarifications needed".
- **Latest:** v4 (23 Sep) then item 38 (24 Sep). · **Interpretation:** a product is treated as sellable while any of its dates is in the future (R3 F6 cautious reading); the readable file (C23) is not on this machine. · **Needs confirmation:** YES.

### C-06 · Astra capex figure
- **A (Urgency, Live Signal):** "IDR 36 trillion" capex for 2026. · **B (v4 Live Signals example):** "Astra's Rp16.9T capex announcement".
- **Interpretation:** different events or an error; only affects the worked examples. · **Needs confirmation:** NO (examples), but do not copy either number into a rule.

### C-07 · Urgency worked example arithmetic (internal to one client doc)
- HP Solution Intent raw "50.4/100" then "49.3 x 25% = 12.33/25", table says "12.60/25"; total "64.43/100" then "Rounded Astra Urgency Score: 61/100".
- **Interpretation:** implement the stated weights and bands, not the example. · **Needs confirmation:** YES (which rounding, if any).

### C-08 · Urgency band gaps
- Employee bands "251-1,000" and "Below 250" leave exactly 250 unassigned; growth bands "1-4.99%" and "0% or negative" leave 0.01–0.99% unassigned; Explorium's "10,001+" spans two bands.
- **Needs confirmation:** YES.

### C-09 · Opportunity ordering: ABX three checks vs SEA Limited priority tags
- **A (HP_ABX_v3_final F4):** plays ordered by Verified Evidence / Timing Trigger / HP Fit; "no numeric opportunity score is defined". · **B (Dhruvi 23 Sep):** drop the three check tags; keep Priority Critical/High/Medium/Low "as seen in sea limited". · **C (v4 §C):** evidence tiers Opportunity / Conversation Starter / Context Only with a `confidence_tier` field.
- **Latest:** v4 + 23 Sep. · **Interpretation:** tags dropped from the UI; what drives the Priority label is not documented by the client. · **Needs confirmation:** YES.

### C-10 · Rulebook version
- Every later logic document cites Rulebook rule ids (WXP 04, WXP 07 …) but the FINAL Rulebook (23 Sep) is not local; the local v1 (17 Sep) has numbering gaps (LIFE 04; product guardrails 1, 6, 8, 9, 11–14; G 01–05, G 16) that may be extraction artefacts or removals.
- **Needs confirmation:** YES — retrieve C29 first.

### C-11 · Hiring recency date fallback
- **A (Urgency):** "If posted_at is blank, use first_seen_at". · **B (Live Signal):** uses `posted_at` only.
- **Needs confirmation:** YES (minor).

### C-12 · Growth vs generic capex; AI partnership weight
- Urgency excludes "generic capex or investment with no identified growth purpose" yet counts the Astra capex; Live Signal scores the same capex as a "Major business change" 6/10. Urgency gives AI partnerships 5 pts; Live Signal gives general partnerships 3/10 and enterprise AI initiatives 8/10.
- **Needs confirmation:** YES (the same event can be treated differently across features).

### C-13 · Parent/subsidiary evidence
- **v4 §B:** "Do not combine evidence from a parent, subsidiary, business unit or geography unless the mapping explicitly supports it" — yet v4's own Executive Dashboard example opens with "ASTRA Infra", and Urgency / Live Signal use ASII group data. Hierarchy rule (DEC-018) says blank parent = ignore.
- **Needs confirmation:** YES.

### C-14 · Google News relevance column
- **16 Sep email:** "Google News relevance: retain as High/Medium/Low" (as a scale). · **opens_2 item 20:** "pls do not use low/high confidence columns from those feeds".
- **Latest:** 24 Sep. · **Interpretation:** the column is not used for ranking or scoring. · **Needs confirmation:** NO.

---

## X. Client document vs delivery-team rules / build

### X-01 · Live Signals scoring model
- **Client (Live Signal Logic):** 3 drivers, Recency 0.30 / Relevance & Impact 0.50 / Source Reliability 0.20, deterministic bands, score /10, no tiers. · **Internal (HP-Account-Intelligence-Rules, 10 Sep):** 5 dimensions 25/30/20/15/10 judged by the model; S ≥ 8 / A ≥ 6 / B ≥ 4 / C ≥ 2 / not published < 2; Gate 0 excludes undated or > 365-day events.
- **Latest:** client, confirmed opens_2 item 36 (no tiers). · **Interpretation:** client model; the Rules doc section is stale. Note the client scores old/undated events 0/10 (shown), the Rules doc excludes them; with "no cap" and "skip undated rows" (DEC-021/023) undated rows are skipped, old ones shown at 0. · **Needs confirmation:** YES (old events: show at 0 or exclude).

### X-02 · News de-duplication rule
- **Client:** "same underlying event", keep the strongest source (v4, Live Signal); "skip the item if the two feeds disagree" (opens_1 answer 6). · **Internal:** similarity ≥ 0.85 OR identical sentence + date (Rules doc); same account + date + normalised headline (split).
- **Needs confirmation:** YES (R3 D1 asks for it).

### X-03 · Proof corpus
- **Internal Rules doc:** "no HP proof corpus is connected, so an unrelated case study is never substituted". · **Client v4 §H:** hp_case_studies_final.csv is the proof library; opens_2 item 31 accepts the 89. · **Interpretation:** Rules doc is stale; corpus is in use. · **Needs confirmation:** NO.

### X-04 · Opportunity strength model
- **Internal:** three checks, DROPPED/DEMOTED/DISCOVERY/PUBLISHED, context (tech stack, size bands) never establishes timing. · **Client v4:** ≥ 2 independent pipelines = Opportunity; technographics and firmographics count as pipelines (BHP example uses Intent + Tech + employee range).
- **Needs confirmation:** YES.

### X-05 · Stakeholder scoring and fields
- **Internal:** composite 25/25/20/15/15, Priority Contact ≥ 60, uses "priority" and "phone" columns. · **Client v4:** no stakeholder score; the Apollo_All_Contacts contract has no priority or phone field; ABX F3 gives the same weights but no input scales.
- **Needs confirmation:** YES (and the contact file has not arrived).

### X-06 · Numeric-claim grounding vs Rulebook numbers
- **Internal:** a number must exist as an exact token in the uploads. · **Client:** Rulebook carries HP numbers ("up to 50 TOPS", "80 covered countries") and v4 §I says any HP number must have a verified HP source.
- **Interpretation:** passes only if the Rulebook is part of the grounding corpus; not stated anywhere. · **Needs confirmation:** YES.

### X-07 · Empty-state wording
- **Client v4:** "No supported HP play at this time". · **Rulebook C 07:** "leave out the recommendation or label the missing condition clearly". · **Internal:** "no supporting evidence in this account's data"; "No supporting HP proof point available". · **Hierarchy rule:** say nothing.
- **Needs confirmation:** YES (DEC-046).

### X-08 · Product / play universe
- **Internal:** five families (workstation, poly, pc, print, daas) and a six-line allow-list. · **Client:** Rulebook routes to hardware, WXP, Care Pack, lifecycle, deployment, Poly support, print/scan, HP IQ, Wolf; Tech Landscape logic has 3D and no DaaS; v4 examples recommend 3D printing, Z workstations, WXP.
- **Needs confirmation:** YES.

### X-09 · Relevance rule as built vs as decided
- **Client (24 Sep):** use-case/opportunity fit; graded "relevant" / "may be relevant / explore fit". · **Build as described in R3 F1 (25 Sep):** "exact or known-alias matches only, category-level matches listed as possible".
- **Needs confirmation:** the client rule is clear; the build has to change or the description was stale. Flagged for the engineering owner.

### X-10 · Tech Landscape "Contextual — no direct HP line" tag and confidence as a percentage
- Client ABX gives status words (Confirmed / Likely / Conflicting / Unknown); the QA validator demanded a percentage; the client's FINAL confidence logic produces a percentage per card. The "Contextual" tag is not in any client document; the 23 Sep question about it went unanswered.
- **Needs confirmation:** YES for the tag; percentage now has a client basis.

---

## I. Internal vs internal

### I-01 · Empty-state default
- 220-Open-Decisions-List (25 Sep working copy) and 220-Open-Items-and-Clarifications: leave the section out. · clarifying_opens_3_OPEN_v2 B4/G1 (sent): "Our default is to show it with the message". · Manisha's non-v2 OPEN: show with message.
- **Latest sent:** OPEN_v2 (show with message). · **Needs confirmation:** YES (client).

### I-02 · Public Bank domain
- Decisions List / Open-Items / UNRESOLVED_v2 A4: domain **held**. · `_CORRECTIONS.txt` (split, 25 Sep 05:16 UTC): "derived: publicbankgroup.com" from the Website column. · Client: pbebank.com.
- **Needs confirmation:** YES; the split must not run with the derived value.

### I-03 · Alias direction
- Decisions List D5: "PredictLeads domain is canonical" (posco.com, shell.com.ph …). · Split: rewrites posco.com → posco-inc.com and shell.com.ph → pilipinas.shell.com.ph, labelled "explicit approved alias" (toward Explorium).
- **Needs confirmation:** YES (engineering).

### I-04 · Jabil Inc. SEC 10-Q rows
- Decisions List / Open-Items / Tracker: Singapore only. · OPEN_v2 C5 (sent): attach to **both** Jabil accounts as keyed, labelled as the parent's filings, if no answer.
- **Latest sent:** OPEN_v2. · **Needs confirmation:** YES (client).

### I-05 · Master account list
- Decisions List D1: "RESOLVED (25 Sep discussion). No separate master list is needed." · OPEN_v2 A1 (sent): "Please send the master list of 220 accounts with one domain each." · Client: "OPEN: WILL GIVE THAT".
- **Needs confirmation:** the client already agreed to send it; treat as OPEN delivery.

### I-06 · Items 26 and 34 status
- Decisions List: "CLARIFICATION SENT". · CLARIFICATIONS (sent): "now cleared" (corrections already applied; one primary + secondary routes).
- **Interpretation:** cleared on our side, silence-default to the client.

### I-07 · Noisy-keyword rule for intent
- Session memory (11 Sep): a category whose score rests on a noisy keyword ("SLA", "identified as competitor of") keeps its score but is never primary. · HP-Input-Data-Contract.md: the noisy-keyword list is "empty by client instruction (Sep 2026)" and "the highest-scoring category is always the primary one". · Remediation checklist #8–9 (15 Sep) lists "noisy-keyword rule not enforced" as a defect.
- **Needs confirmation:** YES — no client email states either rule; find the instruction or treat the empty list as an INTERNAL ASSUMPTION.

### I-08 · Seat-count proxy
- Decisions List D38: "RESOLVED, default changed". · Open-Items C6 / CLARIFICATIONS_v2 F6: employee-range thresholds 501 / 1,001 / 5,001 still awaiting a yes.
- **Needs confirmation:** YES (client).

### I-09 · Astra seed fill
- Split fills four Astra datasets, including prospect_contacts, from `hp-backend/seed_data/astra`, citing the client's item-23 answer, which covers PredictLeads data only.
- **Needs confirmation:** YES (contacts are not covered by that answer).

### I-10 · Handover status snapshot vs progress mails
- Handover docx: 4 complete / 7 deterministic-only. · 14 Sep mail: all complete except Strategy Chat and the dashboard score.
- **Interpretation:** Handover is a 10–14 Sep snapshot; do not use it for status.

---

## S. Sourcing reference (31 Aug) vs master requirements (22 Aug)

| Id | Topic | HP_ABX_v3_final says | 11-Features sourcing reference says | Latest known source | Needs confirmation |
|---|---|---|---|---|---|
| S-01 | Stakeholder Map source | Apollo primary, FullEnrich / Prospeo / SignalHire, PDL, Coresignal verification | "Source A only" from 14_Prospect_Contacts, "empty in every verified test" | v4 (23 Sep) names Apollo_All_Contacts; file not received | YES (data) |
| S-02 | Tech Landscape source | Coresignal / TheirStack primary, then HG Insights / PredictLeads / BuiltWith | Source A (Explorium) major priority; Source B reference only | opens_1 answer 10: Explorium WebStack + Tech_Breakdown, Related Technologies fallback | NO |
| S-03 | News source | "Exa and Google News RSS" primary | Google News RSS primary + Source B add-on; Exa not mentioned | 18/24 Sep: RSS + Exa merged | NO |
| S-04 | Event-type taxonomy | 11 categories (Financial … Regulatory, Other) | 5 (Hiring, Financial, Technology, Strategic, Competitive) | Live Signal Logic (17 Sep) has its own bands | YES |
| S-05 | Executive Dashboard financials | "3-5 years of financial metrics … revenue, revenue growth, net income, headcount growth" | Only range fields (Yearly Revenue Range, Number Of Employees Range) | Filings (DEC-025) are the intended source; extraction not yet built (compliance_filings 0/220) | YES |
| S-06 | Intent source | Bombora composite scores | Source A 11_intent_score (Bombora composites) + hp_intent_results category scores (3 Sep) | DEC-012 | NO |
