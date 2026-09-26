# Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows

**Issue ids:** D17 · **Status:** PARTIALLY RESOLVED · **Affects:** Live Signals, urgency, every time-based signal

## Issue
Undated Exa rows (5,120 of 9,221) and three 1970-01-01 rows.

## What we asked
- (D17) Data question 7, item 17, round 3 D2.

## What they answered
- (D17) opens_1 answer 7: "We will provide the date wherever possible by crawling the URLs. For any rows where the date will still not available, please skip that news row for now, do not skip whole company/account"; epoch rows: "skip these three news items as of now".

## What is still unclear
One Exa row is dated 2026-10-19 (future); the recovery count against the 5,120 was not given.

## Why it matters
A future date would sort to the top of the feed.

## What we need from the client
Nothing blocking; we drop future-dated rows.

## Current status
PARTIALLY RESOLVED. Last movement: 2026-09-25. Tracked in `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` and, where already sent, in `07_Internal_Generated/Client_Facing_Round3/`.
