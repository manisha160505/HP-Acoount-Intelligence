# Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows

**Issue ids:** D17 · **Status:** PARTIALLY RESOLVED · **Affects:** Live Signals, urgency, every time-based signal

## Issue
Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows.

## What we asked
- (D17) Data question 7, item 17, round 3 D2.

## What they answered
- (D17) opens_1 answer 7: "We will provide the date wherever possible by crawling the URLs. For any rows where the date will still not available, please skip that news row for now, do not skip whole company/account"; epoch rows: "skip these three news items as of now".

## What is still unclear
Nothing; awaiting the re-export and its recovery count.

## Why it matters
Without dates most Exa rows are dropped under the skip rule.

## What we need from the client
Re-exported Exa file with ISO dates and a count of how many of the 5,120 received a date.

## Current status
PARTIALLY RESOLVED. Last movement: 2026-09-25. Tracked in `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` and, where already sent, in `07_Internal_Generated/Client_Facing_Round3/`.
