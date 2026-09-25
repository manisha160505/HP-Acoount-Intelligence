To: Dhruvi Patel, Konika Thakur, Sahaj Khunteta
Cc: Manil Tongya, Palash Chatterjee, Manisha Parwani, Anvesha Mittal, Pritesh Virat
Subject: HP 220: status against 25 Sep, what is still pending from BridgeAI, and what we need today
Attachments: 220-Account-Data-Questions-For-Client (sent last night), GCP_Access_Request_for_Manager.docx

Hi Dhruvi, Konika, Sahaj,

**This email is not about blame and it is not about passing the ball between our teams. It is about delivering the HP 220 platform complete and correct, and putting the whole picture in one place so we can fix what is broken.** I am writing on behalf of our team, with Manil's full knowledge and backing, so please read it as the team's position. Everything below is from our email threads, the notes of yesterday's call, and my messages with Sahaj.

Let me start with my own side. Until last night I was working on the assumption that the complete data would be with us by then, and that I would have GCP access. I also assumed the dataset we received was close to final and could be used as it was. When I started splitting and filtering it, that turned out not to be the case, and I raised the issues as I found them. If I should have checked those assumptions earlier, that is on me. But I was also under the assumption that these dependencies were being conveyed to you, Sahaj, and from yesterday's conversations it is clear they were not. So part of this is broken on your side as well, and we need to fix both.

**1. Where we stand today**

- Every rule and logic change received so far is implemented, up to and including the Recommendation Tuning Logic v4 and the updated Rulebook with the Print additions, which reached us yesterday, 23 September, at 11:24 AM. One open interpretation in v4 (what counts as "relevant") is in section 5 for your approval.
- With the data we have today, and our own judgement where the instructions are open, the product remains dependent on incomplete data and on assumptions you have not approved. That is not the complete product we committed to, and it is not what should be delivered as final. We cannot create the missing data ourselves.
- Six of the eleven features do not depend on contact data and can run for all accounts once the environment is in place. The other five cannot run for any account until the contact file arrives and has been checked.
- **We are humans.** However much AI is in the pipeline, every output still has to be verified by a person before it goes out. That takes time, and it has to be in the plan.

**2. How we got here**

**10 Sep** — At Sahaj's request, we sent the full rules, guardrails and logic document for BridgeAI's review.
↓
**14 Sep** — All in-scope features complete on our side except Strategy Chat and the Executive Dashboard score, which was waiting on scoring logic from BridgeAI.
↓
**15 Sep** — Call. Dhruvi's minutes: Sahaj to add Yogesh to the GCP account; Dhruvi to share the recommendation logic and updated rules; Konika to provide the 220-account data with contact data for about 30 buying-committee roles. First recommendation logic shared that evening.
↓
**16 Sep** — Urgency Score logic replaced (4 drivers instead of 5). Case-study dataset shared.
↓
**17 Sep** — Rulebook v1 and services materials (Print "still pending from the client"). Tech Landscape and Live Signal scoring logic. Filings. "Konika will share the 220-account dataset shortly."
↓
**18 Sep** — 9:38 AM: Tech Landscape logic replaced by a FINAL version. 11:21 AM: first data drop, "the completed data files available as of now", with hiring and contact data to follow "shortly". 7:02 PM: hiring data added. Contacts did not arrive.
↓
**21 Sep** — We confirmed the case-study file was integrated (384 rows cleaned to 89 distinct HP customer case studies, used in five features) and asked, in writing: the file explanation maps the Rulebook and the case studies against all 11 in-scope features. Are they expected in all 11, or are we to decide where they appear? Deciding that is a solution-level decision about which HP-provided data is surfaced in the final product, not a technical one. Still open.
↓
**22 Sep** — Dhruvi's UI test observations received.
↓
**23 Sep, 11:24 AM** — "Pending data/updates from our side": Recommendation Tuning Logic v4, updated Rulebook with Print, intent data for one account. The most recent data we have received.
↓
**23 Sep, 3:51 PM** — Call. We said the current environment cannot hold the 220-account volume. Dhruvi confirmed GCP access was in process and took the action to follow up with Sahaj.
↓
**23 Sep, 4:06 PM** — Our four clarification questions sent; Dhruvi answered by 6:03 PM.
↓
**23 Sep, 6:31 PM and 7:11 PM** — GCP role list, then the formal access request document, sent to Sahaj on WhatsApp; call at 7:26 PM.
↓
**24 Sep, 12:26 AM** — Our full review of the 220-account dataset sent (220-Account Data Questions, attached again). Open.
↓
**24 Sep, today** — Contact data still missing for all 220 accounts. GCP access still not granted. Delivery due tomorrow.

**3. The data has still not been fully provided**

Until now the complete data has not been provided. On that basis, a full delivery tomorrow is not possible, and I want to be direct about that rather than let it surface on the 25th.

Sahaj, please check this directly with your team, because the full data has not been shared, whatever you may have been told. This is the exact position as of this morning.

**Which datasets are still pending, where are they used, and what cannot be built without them?**

- **Contact data for the 220 accounts?** Konika's action item on 15 September, "shortly" in Dhruvi's email of 18 September. Still 0 of 220: the contacts sheet in every Explorium workbook is empty, and the Apollo_All_Contacts file that v4 lists as a required input has not been received. **Used by:** Stakeholder Map, Opportunity Map, Objection Playbook, Content Studio, Message Evaluator. **Without it:** none of the five can be generated for any account. Built later, all five have to be regenerated and re-tested.
- **Confirmation of the account identity conflicts?** Two pairs of companies share one domain (jabil.com, mufg.jp), two accounts have a blank domain (Public Bank, Westpac), four accounts use different domains across vendors, and pbebank.com is labelled as two different banks. **Used by:** every dataset joined on domain. **Without it:** either one company's data on another company's page, or, with our interim rules, Jabil Singapore and the MUFG Bangkok branch stay near-empty. This needs your decision, not our guess.
- **Which news feed wins when the two disagree, and can Exa be re-exported with dates?** Dhruvi's 18 September email said the Google News RSS and Exa files together cover all 220 accounts, and we merged them on that basis. But 5,120 of the 9,221 Exa rows (56%) have no event date. **Used by:** Live Signals and every signal that depends on when an event happened. **Without it:** more than half the Exa feed cannot be used.
- **Are these coverage gaps expected, or partial pulls?** Intent scores present for 173 of 220 accounts, job openings for 175, company hierarchy for 165, and 219 accounts in the PredictLeads file against 220 workbooks. **Used by:** Intent & Demand, hiring signals, hierarchy. **Without it:** empty widgets for those accounts, with no way to tell a source limit from a failed pull.

**When did we receive the final data?** Yesterday, 23 September, at 11:24 AM, shortly before our call, and that was itself a partial update. The data has come in pieces on 16, 17, 18 and 23 September, and each piece means we repeat the same review, mapping and verification. We have to go through the data each time to identify what is missing, where there are gaps, which files should be used, and where we need clarification or further information from your side. This is how the empty contact sheets and the domain conflicts were found. Please send the remaining data consolidated, in one drop, with a list of what it contains.

On the questions: we asked on 18 September and Dhruvi answered within two hours. We asked again on 23 September and Dhruvi answered the same evening. The third set, the full data review sent at 12:26 AM last night, is the one that decides what we can build, and we need written answers to it today. I have seen Dhruvi's Teams invite for today; if we go through items 1 to 6 on that call and confirm the answers in writing afterwards, that closes the data side.

So these items will remain open on 25 September regardless of what we do on our side.

**4. GCP access**

Sahaj, I am sorry, but I was under the impression that Dhruvi was directly in the loop with you on this. On yesterday's call Dhruvi confirmed the access request was already in process and took the action to follow up with you on it; my action from the same call was to send the access requirements, which I did that evening. My understanding from that call was that Dhruvi would take the provisioning forward with you directly. I have raised the need for GCP access several times since it was recorded as your action item in the minutes of 15 September, and Manil has raised it as well.

I understand you told Manil this morning that I had sent the GCP details only 20 minutes earlier. That was the plain role list I sent at 8:19 AM, a few minutes after you asked for it without the logic. The full request had reached you the evening before. For the record:

- **23 Sep, 6:31 PM:** I sent you the list of roles required, with the purpose of each.
- **23 Sep, 7:11 PM:** I sent you the formal access request document (attached again here), and we spoke at 7:26 PM. We spoke three or four times yesterday in total.
- **24 Sep, 8:15 AM:** you asked for the list without the logic, and I sent it within minutes.

This dependency has been open for nine days after it was minuted, and it should have taken a day. If a specific format was required, we should have been told that at step one, and we would have provided it right then. I am not raising this as the biggest blocker, the data is, but the current environment cannot hold 220 accounts, and once access lands the redeployment and data load still take a few hours. Please close it today.

**5. The points we raised with you earlier this week, still open**

**5.1 What counts as "relevant" is not defined.** We first raised this on Monday, 21 September: the file explanation maps the Rulebook and the case studies against all 11 features, and we asked whether they are expected in all 11 or whether we are to decide where they appear, which is a solution-level decision. That question is still open, and v4 now repeats the same gap. The Recommendation Tuning Logic says, for Live Signals: *"Use relevant Rulebook offerings and case-study proof where they directly support the HP opportunity made timely by the news event."* The same word carries the instruction for Intent & Demand, Stakeholder Map and the Executive Dashboard, and the data lists ("relevant Intent", "relevant Explorium Technographics"). Dhruvi's 18 September email gave two worked examples and the rule not to force a match, and we have built to that. What is still undefined is the threshold: does a Rulebook offering count as relevant only on an exact product or technology-name match, or also on a category-level match (for example, any endpoint-management tool → WXP)? Whoever decides that is making a product decision that changes the final output. We need it approved in writing, not decided silently on our side.

**5.2 Building a partial dashboard on incomplete data.** We were asked to proceed on the data available. Every contact-dependent feature we build now has to be built and tested again when the contact file arrives.

**5.3 "Recommendation for HP" on every section of the Technographic Map.** This card was our own addition beyond the reference application. With the Rulebook as it stands it maps to two categories today, as Manisha explained on yesterday's call. Extending it to every section, or merging in graph-based recommendations as Dhruvi suggested, means many more AI calls per account and a much heavier pipeline. Even then, some sections do not carry enough signal for a meaningful recommendation, and we would rather show none than a weak one. We can take this on after the 25th if you want it; please confirm.

**5.4 JEV.** We understand this was raised as a possible addition. It is very new, it is a decision model rather than a language model, and we have not yet identified a meaningful role for it in the current architecture. Fitting it in would need a proper assessment and possibly architectural changes. We propose to scope it after the 220 delivery rather than inside it.

**5.5 Data readiness against 25 September.** The first version of the logic came on 15 September and each revision since has changed it (Urgency drivers on the 16th, Tech Landscape replaced on the 18th, v4 on the 23rd); each was implemented on receipt. The build that includes v4 and the Print Rulebook has not yet been reviewed by BridgeAI, because it only became possible yesterday. Two days, and now effectively one, is not a realistic window to integrate, run, test and validate 220 accounts. We will push as hard as we can towards the 25th, but that time was lost waiting for inputs, and we cannot get it back by cutting our testing short.

**6. Why this matters: one owner for the approach**

The instructions we have are open in exactly the places that decide the output. That leaves two workable options, and we are fine with either:

- **Option A:** we take charge of the approach. We document every decision that changes output (the relevance threshold, news precedence, domain ownership for the two shared-domain pairs, the pbebank.com identity, coverage-gap handling) and BridgeAI approves the list before we run 220 accounts.
- **Option B:** BridgeAI gives us a fully detailed, unambiguous approach with those definitions filled in, and we implement exactly that.

What does not work is the current split, where some of these decisions are made on our side and some on yours without a record. If something is wrong in the final output, there is no clear owner. That is not fair to either team. Our recommendation is Option A.

**7. What we are asking for today**

1. GCP access.
2. The contact data, plus written answers to the data questions sent last night.
3. A decision on Option A or Option B.
4. Dhruvi, Konika and Sahaj to align internally on the above and come back with a realistic delivery date, one that starts from the day the data and access are in our hands. Once they are, we will commit to a date within hours.

One more point, and I am saying it plainly because it matters: if data arrives at midnight or 1 AM, we cannot have a validated output by 5 AM. When the contact file arrives we need an inspection window before it enters the pipeline; that is the same check that found the empty contact sheets, the shared domains and the corrupted text in the current drop. Checking the data is our responsibility, and any problem we do not catch at that stage goes straight into the output. That review time has to be part of the plan.

Sahaj, I have always tried to be accommodating and keep things moving. But being accommodating cannot mean that every delay on the input side is simply absorbed by our team, with our build and testing window compressed each time. This is a serious concern I am raising on behalf of the team, not a small one, and we need to work through it properly and put a clear system in place: one owner for the approach, complete data drops with a list of contents, and review time built into every drop. It is also very solvable. If we are aligned on that and the data is complete, we will deliver, and quickly.

Best regards,
Yogesh
