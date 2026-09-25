# HP 220: open decisions and data questions before the 220-account run

Status as of 25 September 2026, after BridgeAI's written replies: "clarifying
opens_1" (the ten data questions), "clarifying opens_2" (this list), Dhruvi's
annotated reply to our 24 Sep email (09:30) and her 14:43 forward of six items
to Sahaj. Each
line keeps the question, our default and what it affects, and now carries a
**Status** line with the decision as it stands. Items marked NOT YET ASKED were
added on 24 Sep after the list went out and are put to BridgeAI in
`220-Open-Items-and-Clarifications.md`, which also holds the clarifications for
every item marked CLARIFICATION SENT.

Status vocabulary: RESOLVED (rule in force), OPEN (needs BridgeAI), OURS (we
owe BridgeAI), CLARIFICATION SENT, NOT YET ASKED.

## A. Account list and identity

1. **Canonical account list.** 220 Explorium workbooks resolve to 217 unique domains and identity is blank on 209 of 219 rows. Question: please confirm the master list of 220 accounts with one authoritative domain each. Default: the domains in our _RUN_SUMMARY (account_domains) are used. Affects: every join, every feature.
   **Status: RESOLVED (25 Sep discussion).** No separate master list is needed. An account is identified by Company Name + Country, with the PredictLeads canonical domain (item 5 overrides applied) alongside. The Name + Country columns BridgeAI is adding to every sheet (item 3) are that identifier; their delivery is the only open part, tracked under item 3.
2. **Entity scope: global parent or APAC entity?** The vendor logged 141 field conflicts and kept the global HQ value each time (e.g. Jabil recorded as Waltham, MA, not Shatin, HK). Question: which entity does each account represent, and how does it reconcile with the parent/child mapping? Default: APAC entity as named in the account list; firmographics shown as delivered. Affects: firmographics, hierarchy, Executive Dashboard.
   **Status: RESOLVED** (BridgeAI: "resolved", no choice named; default recorded). APAC entity as named; firmographics as delivered, global HQ values included.
3. **Shared domains: jabil.com and mufg.jp.** Two companies each. Question: which entity owns the rows, or treat each pair as one account? Default: Jabil Malaysia and MUFG Japan keep the rows; Jabil Singapore and the Bangkok branch stay near-empty. Affects: jobs, tech detections, news, connections for those four accounts.
   **Status: RESOLVED rule, OPEN delivery.** Keep as separate accounts. Key = domain + Company Name + Country. BridgeAI will populate `input_company_name` / `input_country_code` on every row of the PredictLeads sheets (today 2.6% of job rows, secondary entities only). Interim rule stands until the columns arrive.
4. **Blank domains.** Public Bank and Westpac have no Company Domain. Question: confirm publicbankgroup.com and westpac.com.au. Default: use those. Affects: all datasets for those two accounts.
   **Status: Westpac RESOLVED** (`westpac.com.au`; NZ account keeps `westpac.co.nz`). **Public Bank OPEN:** BridgeAI says `pbebank.com`, but item 6 says those rows are Public Bank Lao. Domain held until the corrected Public Bank Berhad rows arrive.
5. **Vendor domain mismatches.** Posco, Pilipinas Shell, Shiseido, Stanley Electric use different domains across Explorium and PredictLeads/news. Question: confirm the four aliases; is there a stable account ID we can join on instead? Default: our four aliases stay; any others we have not found stay silently unmatched. Affects: hiring, news, tech detections for those accounts.
   **Status: RESOLVED.** Canonical domains: Posco `posco.com`, Pilipinas Shell `shell.com.ph`, Shiseido `corp.shiseido.com`, Stanley Electric `stanley.co.jp`. Rule: PredictLeads domain is canonical; fallback Company Name + Country. Neither vendor is fetched by domain (Explorium: name + country + business ID; PredictLeads: name + country; news uses the PredictLeads domain), so a differing domain does not mean a wrong company. No stable ID exists; master list follows (item 1).
6. **pbebank.com.** Named Public Bank Bhd by Exa and Public Bank Lao by PredictLeads. Question: which company? Default: Public Bank Bhd; the PredictLeads rows are withheld. Affects: one account.
   **Status: OPEN.** Public Bank Lao is a wholly-owned subsidiary of Public Bank Berhad, hence the shared domain. BridgeAI will try to supply Public Bank Berhad rows for the PredictLeads file. PredictLeads rows withheld until then; Exa rows (which name Public Bank Bhd) attached.
7. **Hierarchy.** Company Hierarchy sheet present for 165 of 220. Confirmed on 23 Sep: use Explorium hierarchy; blank parent = ignore. Question: for the 55 accounts with no sheet, show "no hierarchy data" or leave the section out? Default: show "no hierarchy data". Affects: firmographics, Executive Dashboard.
   **Status: RESOLVED, default overturned.** Say nothing: the section is left out and no "no hierarchy data" text appears. Used as the precedent for item 39. Ultimate parent (25 Sep discussion): where the Explorium hierarchy sheet carries `Ultimate Parent Name` (filled on all 165 accounts that have the sheet) it is used; for the 55 accounts with no sheet, the account is its own ultimate parent.

## B. Contacts (blocks five features)

8. **Contact file.** Contacts sheet is empty in all 220 Explorium workbooks (0/220). The Apollo_All_Contacts file listed in v4 has not been received. Question: when does it arrive, and keyed on what (domain, company name, or seed ID)? Default: none; Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio and Message Evaluator do not run until it arrives and is checked.
   **Status: OPEN.** BridgeAI: contacts cannot be fetched for every account; some accounts get names and details, the rest names or roles only; prompts and supporting material to follow. Key will be domain + Company Name + Country. Waiting on the file, the split of real-contact vs role-only accounts, and the prompts.
9. **Role coverage.** 15 Sep minutes: ~30 buying-committee roles, with 5 to 8 more in a second round. Question: is the first file the ~30 roles only, and does a second file follow? Default: we build on whatever arrives first and regenerate once when the second round lands. Affects: the same five features, twice.
   **Status: OPEN.** Not answered; asked again.
10. **Empty-state rule.** Question: for an account with zero matched contacts, show an empty Stakeholder Map with a clear message, or hide the feature? Default: show the empty state with the message. Affects: UI for every account until contacts arrive.
    **Status: OPEN.** Proposed to BridgeAI: follow item 7 and leave the section out, no message; absent datasets listed in the run report instead.

## C. Compliance and filings

11. **Which filings source is authoritative.** We have filings 1.csv (your email says 184 of 220 accounts; the file shows 186 unique company names; our earlier count was 192 rows-based) and, from 23 Sep, the PredictLeads SEC Filings sheet to be used alongside it. In our per-account split, compliance_filings is currently 0/220 because neither is mapped yet. Question: confirm the count and send the list of accounts without filings and why. Default: filings 1.csv plus PredictLeads SEC Filings, merged on domain, document_url first, source_page_url as fallback, records with neither excluded (as you confirmed on 18 Sep). Affects: Executive Dashboard financials and priorities, Strategy Chat.
    **Status: RESOLVED.** `filings 1.csv` plus PredictLeads `sec_filings`, joined to accounts on Company Name + Country (the account identity, item 1), domain only as a tie-break. `document_url` first, `source_page_url` fallback; records with neither excluded (no public filings: paid or authenticated registries, family-owned, merged or privatised). 186 unique company names confirmed. Verified against the file: 186 with filings + 31 without = 217. Merged coverage today: 144 of 218 accounts. Measured 25 Sep: 173 of 187 filings companies join exactly on Name + Country, including 55 of the 60 with a bare-country-code, exchange-portal or blank domain, so those rows need no domain. Name variants that map to exactly one account are aliased by us and logged in the corrections report (ANZ Group, IAG Group AU/NZ, BDO Unibank Inc., UOB Group, Westpac Group AU/NZ, Fletcher Building Holdings NZ, Astra International Group); keiretsu-labelled rows are split by domain to the member accounts (Mitsubishi: Electric, Motors, MHI, Chemical, MUFG; Sumitomo: Electric, Corporation, SMFG); Aboitiz, Universal Robina, Singapore Airlines, Spark NZ and Bank Negara Indonesia are ignored as out of scope. Two entity questions remain open with BridgeAI, not blocking: "Jabil Inc." SEC filings to Jabil Singapore only or both Jabil accounts (default: Singapore); "Hyundai Motor Group" DART reports keyed on hyundai-autoever.com, Autoever's own or Hyundai Motor Company's (default: HKMC Group / Hyundai Autoever as keyed).
    The 31 accounts BridgeAI lists with no filings: Healthscope (AU); Kementerian Pertahanan Republik Indonesia, PT Bank Central Asia, Yayasan Bina Nusantara, PT Tiara Marga Trakindo, Sinar Mas Group (ID); Ministry of National Defense, National Intelligence Service (KR); Infineon Technologies (M), Ministry of Defence (MY); Beca Carter Hollings & Ferner, PricewaterhouseCoopers (NZ); Department of Education, Department of National Defense, Ernst & Young, Philippine National Police, Supreme Court of the Philippines (PH); Institute of Technical Education, Government Technology Agency, Ministry of Defence, Ministry of Education, Ministry of Health, Ministry of Home Affairs, Mediacorp, National Trades Union Congress, Oversea-Chinese Banking Corporation (SG); Bank of Tokyo-Mitsubishi Bangkok Branch, Ministry of Defense (TH); Ministry of Defence, Ministry of Finance, Ministry of Public Security (VN). None of them appears in `filings 1.csv`.
12. **Documents, not just links.** The filings file gives URLs. To extract financial figures and strategic priorities we need the documents themselves ingested. Question: do you expect financial figures and priorities for all ~184 accounts from these documents, and if so, are the URLs directly downloadable, or will you provide the files? Default: we ingest what is downloadable from the URLs; accounts whose links fail show "no filing data". Affects: Executive Dashboard, and ingestion time before the run.
    **Status: RESOLVED.** Documents are in BridgeAI's shared Google Drive folder (link in their reply); `local_path` is populated on 504 of 505 rows. Where a file is not downloaded or a link fails, skip that file, not the company.
13. **Window.** 15 Sep minutes: last 12 months, latest four quarters. Question: confirm 12 months; older filings are dropped at ingestion. Default: 12 months. Affects: Executive Dashboard.
    **Status: RESOLVED.** Last 12 months.
14. **Two NZ accounts linked to Malaysian parents** in the filings file, and one account whose filing links point at a different company. Question: we will send the three names today; please correct the mapping. Default: those records are excluded until corrected.
    **Status: OURS, sent.** Fletcher Building Holdings NZ (4 rows on `sunway.com.my`, parent Sunway Holdings); Fonterra Co-operative Group (3 rows on `uob.com.my`, parent UOB Group); PT Astra International (3 rows on `fifgroup.co.id`, Federal International Finance's domain, plus 1 blank-domain row whose document is PT United Tractors'). Under the Name + Country identity the ten Fletcher, Fonterra and Astra rows land correctly; the wrong domain and parent values are still to be corrected so the domain tie-break cannot misfire. Only the United Tractors row is excluded.
15. **Stock Exchange data.** Named in Konika's 3 Sep email but never attached. Question: is it superseded by filings 1.csv? Default: yes, superseded.
    **Status: RESOLVED.** Superseded; the PDFs Konika shared are the stock-exchange documents, and `filings 1.csv` plus `sec_filings` is the source of record.

## D. News (Google News RSS and Exa)

16. **Precedence.** Both feeds have the same schema; your 18 Sep email says together they cover all 220. We merged and removed 356 duplicates. Question: when both carry the same event with different details, which wins? Default: Exa row kept, RSS row kept as a supporting reference. Affects: Live Signals.
    **Status: RESOLVED rule, OPEN confirmation (with Sahaj since 24 Sep 14:43).** Per opens_1 Q6: merge both; where they disagree on the same event, skip that news item, never the company. BridgeAI marked this line "open" in opens_2 and Dhruvi forwarded it to Sahaj, so one-line confirmation requested, together with our definition of "same event" (same account, same event date, matching normalised headline).
17. **Undated rows.** 5,120 of 9,221 Exa rows have no event date; 3 RSS rows carry 1970-01-01. Question: can Exa be re-exported with ISO dates, and can the epoch dates be returned blank? Default: undated rows are shown as context only and never scored for recency; epoch dates treated as blank. Affects: Live Signals, urgency, every time-based signal.
    **Status: RESOLVED rule, OPEN delivery.** BridgeAI will crawl the URLs for dates. Rows still undated are skipped (not shown as context); the three epoch rows are skipped. Waiting on the re-export and its recovery count.
18. **Exa dataset key.** Exa is not an accepted dataset key in the input contract, so today it is filed under Google News and labelled as such on screen. Question: add a dedicated Exa key, or accept the label? Default: add the key and label the source correctly. Affects: source labels on every news card.
    **Status: RESOLVED by default.** BridgeAI's answer ("domain + company name + country") addressed mapping, not labelling. We add an `exa` key; cards show the publisher name per item 40. Clarification sent; stands unless they object.
19. **12-month window and 20-signal cap.** Anything older than 12 months is discarded at ingestion; about half of all news supplied never reaches the product (14,289 rows to 7,614; RSS 7,913 to 2,893; Exa 9,221 to 2,491). Question: keep the 12-month window and the 20-signals-per-account cap? Default: keep both. Affects: Live Signals volume.
    **Status: RESOLVED, default changed.** Keep the 12-month window; **remove the 20-signal cap.**
20. **Low-confidence news.** Both feeds carry a relevance rating (RSS: 4,049 Low vs 1,771 High) that nothing reads today. Question: exclude Low, down-weight it, or leave as is? Default: down-weight Low, never let it outrank High. Affects: Live Signals ranking.
    **Status: RESOLVED, default changed.** Do not use the Low/High columns from either feed at all.
21. **Corrupted text and HTML.** 28 cells with replacement characters (mostly Thai), 73 files with raw HTML. Question: re-export Exa as UTF-8, or accept loss? Default: HTML stripped on ingest; corrupted cells shown as delivered. Affects: news cards for Thai accounts.
    **Status: RESOLVED.** Exa text is as the tool returns it, no re-export; HTML stripped on ingest; corrupted cells shown as delivered.

## E. Intent, hiring, technographics coverage

22. **Coverage gaps.** Intent scores 173/220, job openings 175/220, technographics 207/220, PredictLeads news events 213/220, tech detections 216/220. Question: genuine no-data or partial pulls that can be re-run? Default: treated as source limits; the widget shows an empty state naming the missing dataset. Affects: Intent & Demand, hiring signals, Technographic Map for those accounts.
    **Status: RESOLVED, with one OPEN delivery.** Genuine no-data. Hierarchy: Explorium only. Intent: use `hp_intent_results` (Topics Researched, Keywords Matched, Related Technologies). Technographics: also Explorium `WebStack` and `Tech_Breakdown`; `Related Technologies` from the intent file as a fallback, surfaced as "researched technology" and kept separate from detected technology (confirmation requested). Job openings: absent from PredictLeads for 45 accounts; BridgeAI will supply them from another tool in the same format. Empty-state display governed by item 39.
23. **219 vs 220.** The PredictLeads file is named 219 accounts against 220 workbooks. Question: which account is absent and why? Default: the account shows empty PredictLeads datasets.
    **Status: RESOLVED.** The absent account is PT Astra International; its PredictLeads data was provided separately at the start. We use that file; confirmation of format/version requested.
24. **Duplicate record IDs inside PredictLeads.** technology_detections 715, news_events 68, subpages 10, job_openings 2. Question: genuine duplicates to remove at source, or distinct records? Default: de-duplicated on ID on ingest, first row kept. Affects: technology counts, news counts.
    **Status: RESOLVED, default changed.** Do not rely on IDs. Rows map to accounts on domain + Company Name + Country; a row is removed only when identical to another in every column; distinct records sharing an ID are both kept.
25. **Vendor-flagged bad rows.** PredictLeads review_records name rows it was not confident about (e.g. a court job wrongly attributed, "MISO" read as a framework). Question: drop flagged IDs before import? Default: dropped. Affects: hiring and technographic signals.
    **Status: CLARIFICATION SENT.** 9 flagged rows: 1 Supreme Court job (Regional Trial Court), 3 NSW Education jobs (Early Learning Commission), 1 "miso" technology, 4 duplicate provider profiles. Default: drop the 5, merge the 4.
26. **490 logged corrections** (283 technology detections, 186 job openings, mostly dates recovered from Excel serials). Question: is the delivered file post-correction, or is the log a to-do list? Default: assumed post-correction. Affects: dates on hiring and tech signals.
    **Status: CLARIFICATION SENT.** Sampled job_openings records already carry the "after" values; file treated as post-correction, nothing re-applied. Confirmation requested.
27. **Job status.** Confirmed 16 Sep: include blank and closed status within 12 months for the Urgency Score. Question: for hiring widgets, label as "postings seen" with open count beside it? Default: yes. Affects: hiring widgets.
    **Status: CLARIFICATION SENT.** Data: blank 54.5%, closed 44.9%, 28 rows positively open. Asked whether blank means open or not reported. Default: headline "Postings seen (last 12 months)"; blank shown as "status not reported", not counted as open; Urgency unchanged.
28. **Datasets with no consumer.** Twelve PredictLeads keys upload but produce nothing (subpages 15,163 rows, connections 19,583, social 7,668, products 2,246, similar companies 1,010, and others). On 23 Sep you said: use SEC Filings and the Products sheet; ignore the rest. Question: confirm the Products sheet is for recommendations only and the others can be removed from the upload contract so nothing silently does nothing. Default: Products consumed by recommendations; the rest removed from the contract.
    **Status: RESOLVED.** Yes: Products for recommendations; `sec_filings` per item 11; the other keys removed from the upload contract.

## F. Recommendation logic and rules

29. **Relevance threshold.** RESOLVED by Dhruvi (24 Sep, WhatsApp): use-case/opportunity fit, not exact-name matching. Ladder: technology or integration-route match alone = possible fit, not recommended; plus related evidence from another pipeline = "may be relevant / explore fit"; combined evidence satisfies the applicable Rulebook conditions = "relevant". Case study is relevant when it supports the same use case/opportunity already established. Seller-facing wording must reflect the certainty. Three small confirmations remain (29a to 29c).
    **Status: RESOLVED** (BridgeAI: "explained in the email"). 29a–29c below are NOT YET ASKED.
29a. **"Possible fit" on screen?** When only the integration route is detected, show it as a context line ("Intune detected; possible WXP integration route, no need evidenced") or not at all? Default: context line, never in the recommendation.
    **Status: NOT YET ASKED.**
29b. **Conditions the data cannot evaluate** (seat counts for Care Pack, WXP tier, print volumes). Treat as unmet, so the offering can reach "may be relevant" but never "relevant"? Default: yes.
    **Status: NOT YET ASKED.** Note item 38: employee range now stands in for seat count, so Care Pack conditions become evaluable on the proxy.
29c. **Use-case vocabulary for case studies.** Matching by use case needs a table from Rulebook opportunity type to case-study solution area and tags. We will write it and send it for approval. Default: our table until you change it.
    **Status: NOT YET ASKED.**

30. **Where the Rulebook and case studies appear.** RESOLVED by Dhruvi's 18 Sep file explanation: both are available to all 11 features and "do not need to be available for every recommendation", i.e. used only where a relevant signal exists. No decision needed; item 29 (what counts as a relevant match) is the only open part.
    **Status: RESOLVED.** As built, **plus the Stakeholder Map** (BridgeAI, opens_2). Timing of proof on the four additional surfaces is item 45.

31. **Case-study cleaning.** 384 rows reduced to 89 distinct studies; the file marks every row validated, including broken ones, publication date is empty on all rows, and some outcome figures are corrupted. Question: confirm our cleaned set of 89 is acceptable as the proof-point corpus. Default: the 89 are used; corrupted figures never shown.
    **Status: RESOLVED.** The 89 are the corpus; corrupted figures never shown.
32. **"Recommendation for HP" on the Technographic Map.** Maps to two categories with the Rulebook as it stands; extending to every section or merging graph-based recommendations is a much heavier pipeline. Question: keep as is for the 25th and extend after? Default: keep as is.
    **Status: RESOLVED, default overturned.** Dhruvi's annotated email of 24 Sep (09:30, section 5.3): "DROP IT for now". The card is removed from the Technographic Map for this delivery. If revived later, it follows the item-33 principle (evidence first, Rulebook attached only on a match).
33. **3D printing route.** The logic deck makes 3D the lead in its own Astra example and half the case studies are 3D, but the Rulebook has no 3D rules and no workstation rules. Question: do we build a 3D route, and from what rules? Default: 3D intent is scored but produces no product recommendation until rules exist.
    **Status: RESOLVED, default overturned.** The Rulebook and case studies are supporting inputs, not gates. Where intent, technographics, hiring, news or other signals collectively support a 3D or additive-manufacturing opportunity, the recommendation is generated at the supported opportunity level; a Rulebook offering or case study is attached only where one matches; no match is forced, and the evidence-based recommendation is never suppressed. Not every recommendation needs a Rulebook entry or case study.
34. **One recommendation or five routes.** The Rulebook says one main recommendation; the deck wants all five routes kept with a verdict each. Question: one primary plus secondaries? Default: one primary, others listed as secondary.
    **Status: CLARIFICATION SENT** (BridgeAI asked "which five routes?"). The routes came from the 15 Sep recommendation-logic document, which the 18 Sep sheet marks "not used as of now". Default: Rulebook guardrail C 06 governs; one primary, secondaries only with separate verified evidence, no verdicts for routes without evidence.
35. **Confidence tiers T0 to T3.** Required on every signal, never defined. Question: what does each tier mean, and is the case-study file's T0/T2 the same scale? Default: mapped to our existing High/Medium/Low.
    **Status: CLARIFICATION SENT** (BridgeAI asked "which feature?"). Default changed: `confidence_tier` on every output record = v4 section C labels (Opportunity / Conversation Starter / Context Only). Case-study `source_tier` T0 = HP first-party (378 rows), T2 = third-party (6 rows); T0 preferred, T2 only when no T0 fits.
36. **Live Signal tiers and minimum score.** The new scoring defines neither S/A/B/C tiers nor a minimum publish score; without them every signal shows, including undated ones. Question: keep our tiers and cut-off? Default: keep both.
    **Status: RESOLVED, default changed.** Use the Live Signal scoring logic as given: a numeric score, no S/A/B/C tier labels (as in the Sea Limited reference application). No minimum publish score, consistent with item 19; the 12-month window and the skip-undated rule (item 17) are the only filters.
37. **Technographic Map risk labels.** You asked on 23 Sep what logic assigns Low/Medium/High Risk. We owe you that; it will be in the decision list. Default: current logic stays until you change it.
    **Status: OURS, sent; with Sahaj since 24 Sep 14:43** (Dhruvi forwarded a screenshot of the logic and asked him whether it is good to go). Deterministic, from the HP relationship in the category: Compete = High risk; Open opportunity (whitespace) = Medium risk; Complement = Low risk; Contextual = no label. Not based on technology age, end-of-life or confidence. BridgeAI asked to keep, rename ("Competitive position") or drop.
38. **Services rules that need inputs the data does not have.** Care Pack rules select on PC seat count (250 / 1,000 / 5,000); we hold only an employee range. WXP tier mapping, print licences, scan credits and Poly premium tier are marked "pending HP input" in the Rulebook. Question: seat count entered by the seller? (Lifecycle file: confirmed 18 Sep as not used, so no question.) Default: seat-count rules do not fire; the pending items show as pending, not guessed.
    **Status: seat count RESOLVED, default changed; lifecycle CLARIFICATION SENT.** No seller entry. Employee range is the proxy: lower bound 501+ Priority Access, 1,001+ Priority Access Plus, 5,001+ Priority Management, labelled "based on employee range". "Pending HP input" items are recommended at family level with tiers and terms listed, no tier chosen, no "pending" label. Lifecycle: BridgeAI asked which columns; answered (six columns, 146 rows, 84 multi-date cells, NewDocs copy password-protected). Default: 18 Sep stands, file not used.

## F2. Case-study and Rulebook placement per feature (from comparing v4 with the build)

44. **Four features have no row in the v4 logic table:** Objection Playbook, Content Studio, Strategy Chat, Message Evaluator. The 18 Sep sheet lists both files against them but gives no method. Today: Objection Playbook attaches one case study per area card, Content Studio fills the "Proof Points" section of each asset, Strategy Chat cites the proof points already attached to plays and objection cards, Message Evaluator uses Rulebook facts only. Question: confirm these four methods, or supply rows for them. Default: as built.
    **Status: NOT YET ASKED.**
45. **Four features where v4 asks for case-study proof and the build has none:** Live Signals (Implication for HP), Intent & Demand (So What by theme), Stakeholder Map (HP Play Focus), Technographic Map (What It Means for HP; the BHP example attaches Kansas to the WXP motion and NASA to the engineering motion). Question: add proof to these four for the 25th, or after? Default: after, on the same deterministic matcher.
    **Status: NOT YET ASKED.** Item 30 now includes the Stakeholder Map, so the only open part is timing.
46. **Opportunity Map service plays.** Today proof is attached to hardware play cards only; service plays (WXP, Care, Poly, Print) get none, although the BHP example is a WXP opportunity with a case study. Question: attach proof to service plays too? Default: yes.
    **Status: NOT YET ASKED.**
47. **Evidence-tier gate.** v4: Rulebook and case studies only after the account evidence establishes an Opportunity (two independent pipelines); never at Conversation Starter or Context Only. Today the matcher gates on the HP line named in the text, and the Objection Playbook attaches one study per fixed area regardless of account evidence. Question: apply the tier gate to proof everywhere, which will remove proof from most objection cards on thin accounts? Default: apply it.
    **Status: NOT YET ASKED.**
48. **Region preference.** v4 section H: prefer APJ/APAC proof for APJ accounts where comparable proof exists. Today: industry preference only. Question: add region as the second sort key? Default: yes.
    **Status: NOT YET ASKED.**
49. **Lifecycle file: contradiction.** The 18 Sep sheet says "not used as of now"; v4 section J says check the Lifecycle file before surfacing any offering listed in it and block it after its end date. Question: which applies for the 25th? Default: 18 Sep (not used) until the date cells (two to six unlabelled dates per cell) are clarified.
    **Status: CLARIFICATION SENT** under item 38. Default: not used.
50. **Product-line mapping for matching.** Today a study is mapped to an HP line by a keyword table marked provisional in code, not by the Rulebook's offering IDs. Question: accept for the 25th and switch to Rulebook IDs after? Default: yes.
    **Status: NOT YET ASKED.**

## G. Product behaviour

39. **Empty-state behaviour.** For any dataset missing for an account (items 7, 10, 22, 23), show the widget with a "no data from source" message, or hide it? Default: show with the message, so nobody reads absence as a bug.
    **Status: OPEN, with Sahaj since 24 Sep 14:43.** Proposed: follow item 7, leave the section out with no message, and list absent datasets per account in the run report.
40. **Source labels.** Raw file names on the UI create a negative impression (23 Sep call). Question: agree the replacement label set (e.g. "Firmographics", "Hiring", "News", "Filings", "Intent"). Default: those five plus "HP Rulebook" and "HP case study".
    **Status: OPEN, with Sahaj since 24 Sep 14:43.** Proposed set: Firmographics, Technographics, Hiring, News, Intent, Filings, HP Rulebook, HP case study; news cards show the publisher, never the feed or vendor.
41. **Data as-of date.** v4 asks for one shared data_as_of_date per snapshot. Question: the date of the 23 Sep drop, or the date of the final consolidated drop? Default: the date of the final consolidated drop.
    **Status: OPEN, with Sahaj since 24 Sep 14:43.** Proposed: final consolidated drop; per-dataset retrieval dates kept in the backend record.

## H. Environment

42. **GCP.** Access not granted as of this morning. Once granted: a few hours to redeploy and load. Question: which project ID, and is the Cloud Run region fixed? Default: as in the attached access request.
    **Status: OPEN, with Sahaj since 24 Sep 14:43.** Dhruvi's email reply: "already followed up with Sahaj"; access still marked open.
43. **Inspection window.** When the contact file and the remaining data arrive, we need time to check them against this list before they enter the pipeline. Question: agree that a late-night drop is checked the next working morning, not run overnight. Default: yes.
    **Status: RESOLVED.** Agreed.

## I. From the 24 Sep email thread (not in the list sent)

51. **Realistic delivery date.** Email section 7.4: a date that starts from the day the data and GCP access are in our hands.
    **Status: OPEN.** Not answered.
52. **JEV.** Email section 5.4: proposed to scope after the 220 delivery.
    **Status: RESOLVED.** "Drop it for now."
53. **Consolidated drop with a contents list, and an inspection window.** Email section 3 and closing paragraph.
    **Status: inspection window RESOLVED (item 43); consolidated drop OPEN,** noted by Dhruvi, no commitment given.

## Summary

| Status | Items |
| --- | --- |
| RESOLVED | 1, 2, 5, 7, 11, 12, 13, 15, 18, 19, 20, 21, 23, 24, 28, 29, 30, 31, 32 (dropped), 33, 36, 43, 52; rule only: 3, 16, 17, 22; seat count in 38; Westpac in 4 |
| OPEN (BridgeAI) | 6, 8, 9, 10, 51, 53; Public Bank in 4; deliveries under 3, 17, 22 |
| OPEN (with Sahaj since 24 Sep) | 16 (confirmation), 37 (sign-off), 39, 40, 41, 42 |
| OURS, sent | 14, 37 |
| CLARIFICATION SENT | 25, 26, 27, 34, 35, 38 (lifecycle), 49 |
| NOT YET ASKED | 29a, 29b, 29c, 44, 45, 46, 47, 48, 50 |

Critical path unchanged: contact data, Name + Country on every row, the
corrected Public Bank rows, the Exa dates, the job openings for 45 accounts,
and GCP access. Plus, from the email thread: a delivery date.
