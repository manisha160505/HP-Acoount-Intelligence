# Canonical account list with one domain each

**Issue ids:** D1 · **Status:** PARTIALLY RESOLVED · **Affects:** Identity / every join

## Issue
Canonical account list with one domain each.

## What we asked
- (D1) 220-Open-Decisions-List item 1 (24 Sep). 220 Explorium workbooks resolve to 217 unique domains; identity blank on 209 of 219 rows. Default offered: the domains in _RUN_SUMMARY.

## What they answered
- (D1) "OPEN: WILL GIVE THAT" (clarifying opens_2, 24 Sep). Round 3 A1 re-asked. 25 Sep 05:50 UTC: Dhruvi sent PredictLeads_219_Account_Domain_Audit.xlsx — "The file contains the correct domain to be used for each account … use the domain as the primary reference for data mapping" (sheet 219_Account_Domain_Audit only; Column H marks same-account name variants; Column B = dashboard display name).

## What is still unclear
Nothing in the rule. Pending on our side: download C43 from the 25 Sep 05:50 UTC message, rebuild _ACCOUNTS.csv from sheet 219_Account_Domain_Audit, check the four overrides and Public Bank against it.

## Why it matters
Wrong domain = one company's data on another company's page, or silently empty widgets.

## What we need from the client
Nothing more from the client for the domain list itself; the file is in the mailbox. (Whether it covers 219 or all 220 accounts is unknown until opened.)

## Current status
PARTIALLY RESOLVED. Last movement: 2026-09-25. Tracked in `05_Questions_and_Clarifications/Open/OPEN_QUESTIONS.md` and, where already sent, in `07_Internal_Generated/Client_Facing_Round3/`.
