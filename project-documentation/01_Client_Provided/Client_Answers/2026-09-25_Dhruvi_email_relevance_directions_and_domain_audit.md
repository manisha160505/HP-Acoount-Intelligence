# Client email (verbatim): relevance directions and the PredictLeads domain audit

> CLIENT DECISION text, copied word for word from two emails by Dhruvi Patel (BridgeAI) in Gmail thread 1a082bca2581fea0. Nothing edited. Attachments of the first message: `PredictLeads_219_Account_Domain_Audit.xlsx` and the client-annotated `clarifying_opens_3_OPEN_v2.docx` — see `00_INDEX/MISSING_FILES.md` until they are downloaded.

## Message 1 — 25 Sep 2026 05:50 UTC (11:20 IST), message id 1a0d71dc51f96712
From: dhruvi.p@bridgeaitech.com · To: yogesh23012001@gmail.com, manishaparwani1605@gmail.com · Attachments: PredictLeads_219_Account_Domain_Audit.xlsx, clarifying_opens_3_OPEN_v2.docx (+ the recurring screenshots)

Hi Yogesh ,

  1.
clarifying_opens_3_OPEN_v2 :Attached is the major part you asked for(open questions) (highlighted the answers to this particular doc only)

  1.
Below are the few pointers for Rulebook/case study relevance directions with example which might help you:

-Start with the account evidence first.
First accumulate what opportunity the account data(from all different data pipes firms,techno,intent,news,hiring) is showing. Do not start with an HP offering from rulebook and then try to find evidence to support it.

Example: BHP has increasing PC Intent around fleet management and IT infrastructure. This gives us an account-level endpoint/fleet-management opportunity. After identifying this opportunity we check which HP offering may support it.

-Then check the Rulebook for an offering that supports the same opportunity.
In the HP offering , we might see similar use case/opportunity which we found in the account evidence.

Example: BHP's evidence shows a fleet-management opportunity. The Rulebook shows that HP WXP supports endpoint experience and fleet-management use cases. Therefore, WXP can be considered for this opportunity.

-Technology presence alone is not enough to recommend an offering.
A detected technology can show compatibility or integration fit, but it does not show that the customer needs the HP offering.

Example:
Intune + ServiceNow detected -> WXP has a possible fit, but this alone is not enough to recommend WXP.

Intune + ServiceNow + increasing PC Intent around fleet management -> there is now account evidence supporting the same opportunity, so WXP may be relevant.

-Recommendation wording should depend on the evidence available.

Example using WXP:

Intune/ServiceNow only
→ Possible WXP fit internally, but do not recommend WXP yet.

Intune/ServiceNow + related fleet-management evidence
→ “HP WXP may be relevant to this opportunity.”

Clear fleet-management opportunity + Intune/ServiceNow + applicable Rulebook conditions supported
→ “HP WXP is relevant to this opportunity.”

-Consider conflicting evidence as well.
If another signal does not support the opportunity, do not ignore it.

Example: BHP has Cisco WebEx and Cisco TelePresence detected, but Poly Intent = 0 / No Signal. Therefore, the collaboration technologies alone should not create an active Poly recommendation.

-Case studies should be matched to the same use case/opportunity.
Do not select a case study only because it contains the same product name or comes from the same industry.

Example: BHP has an endpoint/fleet-management opportunity and WXP is relevant. The University of Kansas Health System - HP WXP case study can be used because it supports the same endpoint-experience/proactive-management use case.

- If no suitable HP offering is supported, do not force one.

Example: If Printer Intent is increasing around digitization and cost reduction, but there is not enough evidence to identify a specific print workflow or satisfy a Rulebook offering's conditions, show the print opportunity/conversation without forcing a specific HP print solution. Instead, keep the recommendation focused on the evidenced opportunity, maybe for example: "The increasing research around digitization and cost reduction indicates an opportunity to improve print and digital document workflows and reduce related operational costs."

  1. While reviewing the data across the different sources, you may notice that some company names differ slightly across tools even when the domain is the same. This is expected, as the different data providers do not necessarily follow the same company-name taxonomy and may return a parent company, subsidiary, regional entity, or a different naming convention for the same domain.

Where the domain is the same and the company-name variation can be considered the same account for our mapping purposes, I have already marked this in Column H of the file. Please consider these as the same account and continue using the data accordingly.

The file contains the correct domain to be used for each account. Therefore, please use the domain as the primary reference for data mapping, along with company name keeping caveat mentioned in Column H where applicable.

For the company/account name displayed on the dashboard, please use the account name provided in Column B of this file, rather than the company name returned by the individual data sources.

Best,
Dhruvi

## Message 2 — 25 Sep 2026 06:24 UTC (11:54 IST), message id 1a0d73ce30f04282
From: dhruvi.p@bridgeaitech.com

Hi Yogesh ,

Just one clarification to my previous email: Please refer only to the sheet : 219_Account_Domain_Audit and ignore the other sheets in excel PredictLeads_219_Account_Domain_Audit.
Column H:

  *
“OK” means the company names are similar, hence considered okay.
  *
“Consider both names same” means different tools have returned very different company names for the same domain, but they should be treated as the same account for our mapping.

All in all if you see: domain is matching irrespective of their names and I already mentioned the reason for different names in previous email.

Best,
Dhruvi
