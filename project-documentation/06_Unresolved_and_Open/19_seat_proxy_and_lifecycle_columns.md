# Service rules that need inputs the data lacks (seat count, WXP tier, print volumes, lifecycle dates)

**Issue ids:** D38 · **Status:** PARTIALLY RESOLVED · **Affects:** Care Pack / WXP / Poly / Print rules; lifecycle check

## Issue
Service rules that need inputs the data lacks (seat count, WXP tier, print volumes, lifecycle dates).

## What we asked
- (D38) Item 38 and round 3 F6.

## What they answered
- (D38) "resolved/clarification needed: pls ignore that pending HP input, and use whose data we fully have, no as of now we might not ask seller to enter seats, so hold employee range. lifecycle date, which columns to look into? -> clarifications needed"

## What is still unclear
Threshold approval; lifecycle column semantics; whether Lifecycle is in use at all (client file explanation says "Not used").

## Why it matters
Rules silently never fire or fire on a wrong proxy.

## What we need from the client
(a) yes to the employee-range thresholds or alternatives; (b) which Lifecycle column and what stacked dates mean; (c) an unencrypted Lifecycle copy.

## Current status
PARTIALLY RESOLVED. Last movement: 2026-09-24. Tracked in `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` and, where already sent, in `07_Internal_Generated/Client_Facing_Round3/`.
