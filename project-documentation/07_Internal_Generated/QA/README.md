# QA documents (internal)

| File | What | Author |
|---|---|---|
| `validator_run_2026-09-15/QA-Report.md`, `pipeline-results.json`, `HP_Sea_Limited_QA_Report_2026-09-15_0513 (1).docx` | 4-step feature evaluation of the **deployed** site (hp-frontend-e56t.onrender.com, account "HP Sea Limited"), run 2026-09-15T05:13Z | Automated QA validator; its source code is not on this machine. Who ran it cannot be determined from the content. |
| `QA-Report-Response_2026-09-16.md/.pdf` | Item-by-item response (fixed / not fixed and why) — sent to the client 16 Sep | Delivery team |
| `QA-Discussion-Points_2026-09-16.md/.pdf` | The 12 unfixed items needing a client decision — sent 16 Sep, **never answered** | Delivery team |
| `HP_Account_Intelligence_FINAL_Remediation_Checklist.pdf` | 51-item code-audit fix list (security, storage, async, contract, intent, fallbacks, tests) | Generated with ChatGPT from an internal engineering review; no item statuses tracked; items 8–9 contradicted by later intent instruction |

Known **false failures** of the validator (verified against source on 16 Sep; keep in mind when reading QA-Report.md):
- "contract tbd" placeholder — lived only in `page.tsx.bak*` files, now untracked; live page contains it only in a comment.
- OP-03 / OP-06 / OP-07 — elements render; checks match source text, not rendered UI (Counter Question is CSS-uppercased; "Could be raised by" is deliberate).
- SM-03 / SM-10 — contact count and initials avatar render; no photo URL exists in the data.
- LinkedIn link checks — status 999 is LinkedIn's bot block; Apollo URNs carry no name text; Google News links are redirects.
- OM-10 / OM-13 — the Opportunity Map never emits an unsourced number, so the states cannot occur.
- TM-11 — words (Confirmed/Likely/Unknown) were correct for install-base detections; the client's 18 Sep confidence logic now supplies a percentage.
- Strategy Chat source_links / uncertainty_state — deliberately pending until Step 8 RAG; the report's "Independent Groq evaluation" block is hallucinated (CIO 92/100, FY24 revenue $12.4B, "HP ProLiant") and must not be actioned.

Real findings it caught (fixed): LS-13 news sort tie-break; LS-16 event-status field; TM-12 header count; strategy_chat.py seed-number fallback leaking into other accounts.
Unfixable as written: SM-07 / SM-26 (active-employee label) — no employment-status column exists.
