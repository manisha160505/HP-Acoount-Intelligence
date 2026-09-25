# Which filings source is authoritative; count; accounts without filings

**Issue ids:** D11, D14 · **Status:** OPEN / PARTIALLY RESOLVED · **Affects:** Executive Dashboard financials/priorities, Strategy Chat, Opportunity Map, Content Messaging, Live Signals

## Issue
Which filings source is authoritative; count; accounts without filings.

## What we asked
- (D11) 18 Sep question 3, data question 10, item 11, round 3 C1/C5. 184 vs 186 vs 192 counts; document_url vs local_path; two NZ accounts linked to Malaysian parents.
- (D14) 18 Sep question 3 and item 14; names sent in round 3 C4: Fletcher Building (rows carry sunway.com.my), Fonterra (uob.com.my), Astra (fifgroup.co.id; plus a blank-domain row holding United Tractors statements).

## What they answered
- (D11) 18 Sep: "Please use document_url where available and source_page_url as the fallback. Do not use local_path. Where both source URLs are blank, please exclude that record." opens_2 item 11: "RESOLVED: use filings 1.csv plus PredictLeads SEC Filings, merged on domain but where the domain is same … pls use company name and country … and yes pls consider 'the file shows 186 unique company names'" + list of 31 accounts with no public filings. opens_1 answer 10: "Sec filings: pls use from filings.csv + predictleads data->sec_filings".
- (D14) opens_2: "open: pls send, noted!" — names sent 25 Sep; no correction received.

## What is still unclear
Whether Agribank/VPBank have filings; whether parent (Jabil Inc.) filings attach to both APAC entities; whose reports the DART rows are.

## Why it matters
Filings feed five features; one company's filings must not appear on another's page.

## What we need from the client
Yes/no on Agribank and VPBank; yes/no on Jabil (both/neither); Hyundai Autoever vs Hyundai Motor for the DART rows; re-key VPBank out of Vietnam Post.

## Current status
OPEN / PARTIALLY RESOLVED. Last movement: 2026-09-24. Tracked in `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` and, where already sent, in `07_Internal_Generated/Client_Facing_Round3/`.
