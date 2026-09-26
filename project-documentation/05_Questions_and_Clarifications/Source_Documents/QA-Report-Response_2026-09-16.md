# QA Report Response — HP 220-Account ABM Platform

**Responding to:** HP Sea Limited QA Report, run 2026-09-15T05:13:15Z
**Prepared:** 16 September 2026
**Scope:** All 11 features. Every item below was verified against source code, seed data, or the spec document before being assigned a status.

---

## How to read this

Each finding from the QA report is placed in one of four buckets:

| Status | Meaning |
|---|---|
| **FIXED** | Code changed this cycle. Verified by test, typecheck, or direct execution. |
| **ALREADY CORRECT** | The check failed but the code was right. Evidence given. The check needs changing, not the code. |
| **OPEN — NEEDS DECISION** | Real gap. Blocked on a product or client decision, not on engineering. |
| **BLOCKED ON DATA** | Cannot be satisfied without a data field that does not exist in any supplied source. |

**Important:** the QA run predates all fixes below and audits the deployed site
(`hp-frontend-e56t.onrender.com`), not the working tree. None of these changes appear
in a report until the next deploy.

---

## 1. The single biggest finding: the validator is scanning backup files

**"contract tbd" was reported on 10 of 11 features.** It is a false positive on every one.

The string lived in `page.tsx.bak4` and `page.tsx.bak6` — two of **seven** `.bak` files
that were committed to git. The live `page.tsx` contains the phrase only inside a code
comment recording that the placeholder had already been removed.

**Fixed:** all seven `.bak` files untracked (`git rm --cached`) and `*.bak*` added to
`.gitignore`. Their history is preserved in git; only the working copies are ignored.

**Action for the QA tool:** exclude `*.bak*`, `node_modules`, and `.next` from source
scanning. This one change should clear the finding from all 10 features at once.

---

## 2. Status by feature

### Executive Dashboard — 2/10, 2 red flags

| ID | Finding | Status |
|---|---|---|
| ED-14 | Ultimate Parent contradicts description (CRITICAL) | **FIXED** |
| ED-17 | Financial figures / fiscal year | **FIXED** |
| ED-13 | "Contract TBD" urgency placeholder | **FIXED** (see §1) |

The Ultimate Parent field now suppresses itself and raises a review flag rather than
displaying a name it cannot stand behind. Two independent triggers: a self-referential
hierarchy row (Ultimate Parent Id == Business Id, which is how the vendor encodes "no
hierarchy known") and a direct contradiction with the Business Description.

Notably, the contradicting name ("Jardine Cycle & Carriage") is deliberately **not**
written into the field. It is surfaced on the flag for a human to confirm, because
promoting prose parsed out of a description to structured ground truth would be the
same silent swap the platform avoids elsewhere.

---

### Recent News Signals — 7.4/10, 1 red flag

| ID | Finding | Status |
|---|---|---|
| LS-13 | Sorting: ties not broken by newest first | **FIXED** — was a real bug |
| LS-16 | Future/announced/rumoured/completed not distinguishable | **FIXED** |
| LS-10, LS-15 | Source citation / cited source supports claim | **ALREADY CORRECT** |
| LS-12 | Duplicate cards | **ALREADY CORRECT** |

**LS-13 was a genuine defect.** The code sorted twice; the second sort discarded the
tiebreak, and the first sorted `event_date` ascending — so equal-confidence signals
ranked **oldest-first**, the opposite of the requirement. Two further bugs were fixed in
passing: `event_date` is a string, so `"15/03/2026"` was being compared as text against
`"2026-01-01"`; and the parsed date was discarded before ranking ran.

**LS-16** added an `event_status` field (`completed | announced | planned | rumoured |
unknown`), enum-checked on parse so an invented value falls back to `unknown`, which
renders no badge. This bumped the scoring prompt version and will regenerate cached
scores on next run — a real LLM cost worth scheduling deliberately.

**LS-10 / LS-15 and the four "UNREADABLE" sources are not defects.** Those URLs are
Google News *redirect* links (`news.google.com/rss/articles/CBMi...`), which return a
JavaScript shell with no extractable text. The code explicitly refuses to fabricate a
URL for rows whose dataset carries none. The validator cannot follow these redirects;
that is a tool limitation.

---

### Stakeholder Map — 7.7/10, 0 red flags

| ID | Finding | Status |
|---|---|---|
| SM-03 | Total contact count not stated | **ALREADY CORRECT** |
| SM-10 | Avatar + LinkedIn per person | **ALREADY CORRECT** |
| SM-32 | Duplicate persons | **ALREADY CORRECT** |
| SM-07 / SM-26 | "Active employees only" | **BLOCKED ON DATA** |
| 8 LinkedIn links | Broken / not supported | **ALREADY CORRECT** |

SM-03 and SM-10 both render in the live UI — the contact count in the header, and
avatar plus LinkedIn icon on every card. SM-10 appears to require an `<img>` avatar
where the code renders initials, which is deliberate: the contact data carries no
photo URL.

**SM-07 / SM-26 cannot be honestly satisfied.** The contact source has **no
employment-status column at all** — verified directly against the CSV. Adding a
"Showing active employees only" label would assert a guarantee across all 23 contacts
that no supplied data supports. Recommend the check be reworded to accept dated
provenance ("contact list as captured <date>") or marked blocked-on-data.

**The 8 LinkedIn failures are tool limitations.** Status 999 is LinkedIn's standard
anti-bot response; the `ACoAA...` URLs are opaque Apollo member URNs (8 of 23 rows)
that resolve by redirect but expose no name text, so a term-match check can never pass.

---

### Solution Narrative / Opportunity Map — 6.1/10, 2 red flags

| ID | Finding | Status |
|---|---|---|
| OM-10 | "QUANTIFIED IMPACT" not labeled HP-MODELED | **ALREADY CORRECT** |
| OM-13 | Amber "Unsourced — HP analysis only" state | **ALREADY CORRECT** |
| OM-11 | Calculation basis expander | **ALREADY CORRECT** |
| 4 hp.com links | Not supported | **ALREADY CORRECT** |

**Both red flags are inverted.** They ask for labels on HP-modeled and unsourced
numbers. The Opportunity Map **never produces either** — there is no HP projection
formula, so there is no HP-modeled state to label, and every figure is re-verified
against the evidence that specific play cites. A genuinely real number sourced from
*unrelated* evidence is dropped rather than shown.

Satisfying OM-13 would require first creating unsourced claims. This widget scored
second-lowest precisely because it refuses to invent numbers.

The four hp.com URLs are labeled in the UI as "HP RESOURCE · HP product page" — a
resource chip, not a citation. Where no HP proof point exists the code says so
explicitly rather than substituting an unrelated one.

---

### Tech Landscape — 7.3/10, 1 red flag

| ID | Finding | Status |
|---|---|---|
| TM-12 | Category signal counts ≠ header total | **FIXED** — real bug |
| TM-11 | Provenance + confidence % per card | **OPEN — NEEDS DECISION** |

**TM-12 was real and severe.** The header counted the entire technographics export
(**220** entries) while the category cards counted only vendors matched into the 7 HP
categories (**~20**). An order-of-magnitude mismatch, and a seller reading "220 detected
technologies" would assume the cards below accounted for them.

Fixed by publishing a `mapped_signal_count` computed as the sum of the exact field the
cards render, and relabelling the header:

> `220 technologies detected in the technographics export · 20 map to the 7 HP categories below`

Per the standing preference, nothing was replaced — 220 remains, correctly labelled,
with a new metric beside it.

**Also fixed in passing:** the stat tiles fell back to hardcoded `21`, `5/7`, `4/7` when
data was missing — one account's figures that would render as another's real numbers.
Now `--`. The `||` was also changed to `??` so a legitimate zero is not swallowed.

**TM-11 is open.** The check wants a confidence percentage; the code emits
`Confirmed / Likely / Unknown`. For install-base detections a synthetic "85%" would be
invented precision. **Recommendation: change the check.** The code already grades
honestly — a vendor matched by a rule that did not record *what* it matched is
downgraded to `Likely` rather than claiming `Confirmed`.

---

### Objection Playbook — 4.3/10, 0 red flags

| ID | Finding | Status |
|---|---|---|
| OP-03 | "Likely raised by:" line | **ALREADY CORRECT** — do not change |
| OP-06 | COUNTER QUESTION box | **ALREADY CORRECT** |
| OP-07 | Footer "Likely Raiser:" | **ALREADY CORRECT** — do not change |

**All three render in the live UI.** OP-06 is the clearest error: the box exists,
styled and populated, labelled `Counter Question` in JSX with a CSS `uppercase` class —
so it displays as "COUNTER QUESTION". The validator is matching source text rather than
rendered output.

**OP-03 and OP-07 ask for wording that would be less honest than what ships.** The code
says "Could be raised by" and "Topic owner", and the card states outright: *"They have
not raised this objection."* The backend only names a person on a strong title match,
falling back to the function name otherwise, because *"a weak or department-only match
is the nearest technically adjacent person, not the owner of this subject. Naming them
would overstate."*

Adopting "Likely Raiser" would assert a prediction about a named real individual that
no data supports. **This wording is deliberate and should not be changed to turn the
check green.** OP-12 will also fail by design whenever the code correctly falls back to
a function name.

---

### Content Studio — 8.3/10, 0 red flags

| ID | Finding | Status |
|---|---|---|
| format_limits_respected | Email/LinkedIn/one-pager limits | **FIXED** |
| human_in_loop | Co-creation flow | **FIXED** |
| no_invented_roi, no_cross_account_bleed | | **ALREADY CORRECT** |

Checking the spec (`HP_ABX_v3_final.docx`, Feature 7) found the limits were stated in
the prompt but **never verified** — and that the code's numbers contradicted the spec.
Now enforced as hard faults feeding the existing retry loop:

| | Was | Now (per spec) |
|---|---|---|
| Email | 90–130 words | **≤110** |
| LinkedIn | 120–200, 1 post | **150–200, 2–3 variants** |
| One-pager | free-form sections | **≤400, 4 mandated headings in order** |

Reading the full spec section surfaced three further gaps the QA report did not raise:

- **`Re: [initiative]` subject format** — was missing entirely. Now enforced.
- **Deterministic fallback template** — was missing entirely. A failed generation
  previously returned nothing; the spec requires the safe template. Now composed in
  Python from verified fields (no model in that path, so it cannot hallucinate) and
  flagged "Safe template — not AI-generated".
- **Low-friction next step** — CTA must request a briefing/workshop/assessment and never
  claim an existing meeting.

**Co-creation** implements Dhruvi's email requirement (*"brief → suggested options →
user selects or adjusts → generation"*) as a cheap angles call, so the expensive
generate-and-retry loop runs once on the chosen angle. The selected angle is editable
before generating — that is the "or adjusts" half — and folded into the cache key.

---

### Strategy Chat — 6/10, 0 red flags — **THE ONE FEATURE NOT COVERED**

| ID | Finding | Status |
|---|---|---|
| source_links | Evidence + source links shown | **OPEN — blocked on Step 8 RAG** |
| uncertainty_state | "Information not available" state | **OPEN — blocked on Step 8 RAG** |
| Hardcoded count fallbacks | *(not raised by QA)* | **FIXED** |

The `strategy_chat_interface` widget is deliberately `status: "pending"` pending Step 8
RAG. A feature that generates no answers cannot cite sources or show a conflict state,
so both checks stay red until Step 8. **They should not be "fixed" by bolting on
citations to answers that do not exist yet.** The three ⚠️ guardrails were never
evaluated, not failed.

**A real bug was found here that QA did not flag:** the extractor fell back to
`10 / 23 / 149 / 220` and `solutions_count: 5` when a dataset was empty, and the
frontend re-defaulted at the render site. An account with no uploads published a seed
account's numbers as its own in the "Grounded in" line. Now `None` plus an
`unavailable_counts` list, rendering "not available".

> ⚠️ **On the "Independent Groq evaluation" in the QA report (p. 21):** that block is
> itself ungrounded. It invents a CIO score of 92/100, an FY24 revenue of $12.4B, HP
> ProLiant servers (not an HP line in this platform), and named stakeholders —
> attributing them to Source A sheets. Treat it as a hallucination sample, not as
> suggestions to implement. Verify before actioning any figure from it.

---

### Message Evaluator — 8.3/10, 0 red flags

| ID | Finding | Status |
|---|---|---|
| phrase_highlights | Keep/Improve/Change highlights | **FIXED** |

The `evaluator_feedback_score` placeholder widget was removed rather than left writing
"Inferred TBD".

---

### Intent & Demand Signals — 8.6/10, 0 red flags — strongest feature

| ID | Finding | Status |
|---|---|---|
| top_category_matches_gt | 3D Printers, 34/100 | **ALREADY CORRECT** |
| pc_score_not_hidden | PC score of 0 shown | **ALREADY CORRECT** |
| providers_not_averaged | Providers kept separate | **ALREADY CORRECT** |
| no_buying_claim | No "is buying" language | **ALREADY CORRECT** |

Verified against the real data: top category **3D Printers at 34/100**, PCs at **0** —
matching the stated ground truth exactly.

The PC-zero guardrail is worth noting, since `0` is falsy in both Python and JavaScript
and could easily have broken. It holds at three layers: the parser returns `0` for
`"0"` and `None` only for non-numeric; categories are built unconditionally from the
fixed HP taxonomy; the frontend sorts with `?? -1`, never `|| 0`. The opposite
precaution is also taken — an unparseable score is *excluded* rather than scored 0,
because a zero would read as measured absence of interest.

Provider separation is architectural: category-file scores and Bombora signals live in
separate fields, and *"supporting signals never change a category's score."*

---

### Content Messaging — 5.6/10, 1 red flag

| ID | Finding | Status |
|---|---|---|
| CM-11 | SOURCES footer | **FIXED** — the one real gap |
| CM-12 | Header fraction = sum of pillar fractions | **FIXED** |
| CM-15 | Unsourced proofs labeled "HP analysis" | **ALREADY CORRECT** |
| CM-04, CM-16 | Sub-bullets / no new facts in WHY HP | **ALREADY CORRECT** |

**CM-11 was real.** Sources rendered only inside expanded pillar rows, so a seller had
to open every pillar to see what backed the document. Added a deduped `Sources (N)`
footer built from the same data the rows render — so it cannot list a source that is
not actually used, satisfying CM-17 by construction.

**CM-12 exposed a subtler problem.** Because unsourced proofs are *dropped*, the badge
always read `3/3` and was structurally incapable of showing a gap. The denominator now
counts what the model **proposed**, so a pillar reads `3/5 sourced` when two claims
could not be stood behind.

**CM-15 is inverted, like OM-13.** It asks that unsourced proofs be labeled. The code
never publishes one — a proof whose evidence ID does not resolve is discarded. Dropping
is stricter than labeling. The "HP account analysis" label does exist, on the
interpretive `hp_benefit` field where it belongs.

---

## 3. Open points needing your decision

| # | Item | Decision needed |
|---|---|---|
| 1 | **TM-11 confidence %** | Keep `Confirmed/Likely/Unknown`, or emit percentages? Recommend keeping — percentages would be invented precision. |
| 2 | **SM-07 active employees** | Accept dated provenance wording, or source an employment-status field? |
| 3 | **Strategy Chat source_links / uncertainty_state** | Confirm these stay open until Step 8 RAG. |
| 4 | **LS-16 / Content Studio prompt-version bumps** | Both invalidate cached output and re-run generation across accounts. When should that cost land? |
| 5 | **Unmapped technologies** | The ~200 technologies outside HP categories are now *disclosed* but not *browsable*. Add an "Unmapped" view? |
| 6 | **Step 4 data suggestions** | The `.xlsx` / `.pdf` / `gaikindo` / `financials_fy.2025` / `stock_exchange` suggestions repeat across every feature. None are started. Worth scoping separately. |

---

## 4. Recommended changes to the QA tool itself

These would remove most of the noise from the next run:

1. **Exclude `*.bak*` from source scanning** — clears "contract tbd" from 10 features.
2. **Match rendered DOM, not source text** — OP-06 fails only because the label is
   lowercase in JSX with a CSS `uppercase` class.
3. **Drop the "Likely" wording requirement** (OP-03, OP-07, OP-12) — the shipped wording
   is deliberately more cautious.
4. **Retire OM-10, OM-13, CM-15 as written** — they fault features for *not* producing
   the unsourced states they are designed to never produce.
5. **Mark LinkedIn and Google News link checks not-machine-verifiable** — an
   unauthenticated fetcher cannot validate either.
6. **Accept an initials avatar** for SM-10.

---

## 5. Verification

All changes verified before this document was written:

- **360 backend tests pass** (up from 311; new evaluator and dashboard test files)
- **`ruff check src/` — all checks passed**
- **`tsc --noEmit` — exit 0**
- Sort ordering, word-limit enforcement, subject-prefix enforcement, fallback template,
  proof-fraction arithmetic and source dedupe each exercised directly against real
  functions or real seed data.

**All changes are uncommitted** and staged for review.

### Caveats worth stating

- Verification was by direct function execution and test suite, **not a live end-to-end
  run** against Mongo with an LLM key. The LinkedIn variant *distinctness* and the
  `event_status` tense judgment both depend on the model honoring its instruction —
  worth eyeballing the first real generation.
- OM-14 / OM-15 (does a cited source actually support its quote) still needs a human
  spot-check against the Astra annual reports. Code structure cannot answer that.
- The QA run predates every fix here. Re-running before a deploy will reproduce the
  same report.
