# Points We Need To Discuss With QA

**About this list:** these are only the open items. Anything we have already fixed is
left out. Every point below is something where we did **not** change the code, because
we think the check may need changing, the data does not exist, or we need your decision
first.

Each point says what the check asks for, why we could not simply do it, and a real
example from our system.

---

## A. Checks we think are asking for the wrong thing

We did not change the code for these. We would rather agree the check is wrong than
make our product less honest just to turn a box green.

### 1. Objection Playbook — the line naming who might raise the objection

*Where to look: Objection Playbook, the grey line under each quoted objection, and the
footer inside the expanded card. (QA checklist: OP-03 and OP-07)*

- **The check wants:** the card to say *"Likely raised by: [role]"*.
- **Our card says:** *"Could be raised by: [role]"*, and in the footer *"Topic owner"*.
- **Why we did not change it:** we have no data telling us any specific person will
  actually raise an objection. We only know who owns that subject area. Saying
  "likely" would be us predicting the behaviour of a real named person with nothing
  to back it up.
- **Example:** the card for *"We already use ManageEngine for device management"* shows
  "Could be raised by: Head of Information Technology project procurement". That person
  has never said this. They simply own that topic. Our card even states in plain words:
  *"They have not raised this objection."*
- **What we would like from QA:** can the check accept "Could be raised by"? If the
  intention really is to predict who will object, that is a bigger product change and we
  should talk about what evidence would support it.

### 2. Objection Playbook — the "Counter Question" box is marked missing, but it is there

*Where to look: Objection Playbook, click any objection to expand it. The purple box.
(QA checklist: OP-06)*

- **The check wants:** a COUNTER QUESTION box on the card.
- **The box is already there.** It is on screen, in purple, with the question in it.
- **Why the check fails anyway:** in our code the label is written as `Counter Question`
  and the styling makes it appear in capitals. On screen the seller reads
  **"COUNTER QUESTION"**. The check seems to be reading our code text instead of the
  actual screen.
- **What we would like from QA:** can this check look at the rendered page, or ignore
  upper/lower case? This is likely the single easiest fix on the list.

### 3. Opportunity Map — asked to label "HP's own numbers" and "unsourced" claims

*Where to look: Opportunity Map, the "Quantified Impact" box on each opportunity card.
(QA checklist: OM-10 and OM-13)*

- **The checks want:** a label saying *"HP-modeled / internal projection"* on HP's own
  numbers, and an amber *"Unsourced — HP analysis only"* state.
- **Why we did not add them:** our Opportunity Map never creates either of these. There
  is no HP calculation or projection in it at all. Every number shown is copied from the
  account's own uploaded data, and we check it again before showing it.
- **Example:** if the model tries to use a real number from the account's data but that
  number came from unrelated evidence (say a dividend figure used on a laptop
  opportunity), we **delete it** rather than show it with a warning label.
- **The awkward part:** to pass OM-13 we would first have to start producing unsourced
  claims, then label them. That is the opposite of what the guardrail is trying to
  achieve.
- **What we would like from QA:** should these checks be retired, or reworded to
  "confirm the feature produces no unsourced numbers"?

### 4. Content Messaging — asked to label proof points that have no source

*Where to look: Content Messaging, expand any pillar row, the "Proof points" list.
(QA checklist: CM-15)*

- **The check wants:** unsourced proof points labelled *"HP analysis"*.
- **What we do:** if a proof point cannot be traced back to real evidence, we **throw it
  away**. It never reaches the screen. So there is nothing left to label.
- **Example:** if the model writes 5 proof points for a pillar and 2 of them point at
  evidence that does not exist, only 3 are published. (We have now also changed the badge
  to show "3/5 sourced" so you can see that 2 were dropped.)
- **What we would like from QA:** same as OM-13 — deleting is stricter than labelling, so
  can the check accept that?

### 5. Tech Landscape — asked for a confidence percentage on each technology

*Where to look: Tech Landscape, the small grey text at the bottom of each vendor card.
(QA checklist: TM-11)*

- **The check wants:** a confidence **percentage** on each vendor card.
- **What we show:** the words `Confirmed`, `Likely`, or `Unknown`.
- **Why we did not change it:** we would have to invent the percentage. Our data tells us
  whether a technology was found in the export, not how confident we are as a number.
  Writing "85%" would look precise while meaning nothing.
- **Example:** if a rule matched a vendor but did not record which entry it matched, we
  mark it `Likely` instead of `Confirmed`. A made-up percentage would hide that
  difference.
- **What we would like from QA:** can words be accepted instead of a percentage? If a
  number is genuinely needed, we need to agree where that number would come from.

### 6. Stakeholder Map — the contact photo/avatar is marked missing

*Where to look: Stakeholder Map, the circle at the left of each contact card.
(QA checklist: SM-10)*

- **The check wants:** an avatar and LinkedIn icon on every person.
- **Both are already there.** The LinkedIn icon links out, and the avatar shows the
  person's initials in a circle.
- **Why no photo:** our contact data has no photo link in it at all. We show initials
  instead.
- **What we would like from QA:** can an initials avatar count as an avatar?

### 7. Stakeholder Map and Recent News — source links reported as broken

*Where to look: the LinkedIn links on contact cards, and the source chips on news cards.
(QA checklist: the Step 3 "Evidence Check" section)*

- **The check wants:** every source link to open and support the claim beside it.
- **Why they fail — LinkedIn:** LinkedIn returns error 999 to any automated tool. That is
  LinkedIn blocking robots, not a dead link. The same links open normally in a browser.
- **Why they fail — Apollo-style links:** 8 of our 23 contacts have LinkedIn links that
  look like `linkedin.com/in/ACoAABO8P9EB...`. These work, but they contain no readable
  name, so a tool that searches the page for the person's name will never find it.
- **Why they fail — Google News:** those are redirect links. They pass you on to the real
  article, so the tool only sees an empty page.
- **What we would like from QA:** mark these as "cannot be checked automatically" rather
  than failures, so they stop appearing as broken every run.

---

## B. Things we cannot do because the data does not exist

### 8. Stakeholder Map — asked to confirm only current employees are shown

*Where to look: Stakeholder Map, the header area above the contact list.
(QA checklist: SM-07 and SM-26)*

- **The check wants:** a label confirming only current employees are shown, and former
  employees marked as former.
- **The problem:** our contact file has **no column telling us if someone still works
  there**. We checked every column in the file. There is nothing about employment status,
  start date, or end date.
- **Why we did not just add the label:** putting "active employees only" on screen would
  be a promise about all 23 contacts that we cannot keep. If one of them left last month,
  we would be telling the seller something untrue.
- **Example:** a seller sees the label, emails a contact who left six months ago, and
  gets a bounce-back — and the platform told them that person was active.
- **What we would like from QA:** either (a) accept a dated note such as *"Contact list as
  captured on 9 Sep 2026 — employment not re-checked"*, or (b) help us get a data source
  that includes employment status. Right now this check cannot be passed honestly.

---

## C. Waiting on a decision from your side

### 9. Strategy Chat — source links and an "information not available" state

*Where to look: Strategy Chat. The feature is not built yet.
(QA checklist: source_links and uncertainty_state)*

- **Status:** open, and we think it should stay open for now.
- **Why:** Strategy Chat does not generate answers yet. It is waiting on the Step 8 RAG
  work. A feature that produces no answers cannot show sources for them, or say when the
  evidence is missing.
- **What we do not want to do:** add fake citations to answers that do not exist yet just
  to pass the check.
- **What we need:** confirmation that these two stay open until Step 8 is built.

### 10. Cost of re-generating cached content

- **What happened:** two of our fixes (the news event status, and the Content Studio word
  limits) change the instructions we send to the AI. That means all previously generated
  content becomes out of date and will be regenerated.
- **Why it matters:** this costs money and takes time across all accounts. It is not a
  problem, but it should be scheduled rather than happening by surprise.
- **What we need:** agreement on when to let that run.

### 11. The ~200 technologies that do not map to HP categories

- **What we fixed:** the header used to say "220 detected technologies" while the cards
  below only covered about 20. We now say clearly: *220 found, 20 map to HP categories*.
- **What is still open:** the other ~200 technologies are now honestly counted, but a
  seller cannot browse them anywhere.
- **Example:** things like ARCore, ASP.NET and Adobe Illustrator are in the account's
  technology list, but they do not belong to any HP category, so they are not shown.
- **What we need:** do you want a separate "Other technologies" view for these, or is the
  honest count enough?

### 12. The repeated "Step 4" data suggestions

- **What they are:** every feature in the QA report suggests adding the same extra data —
  the Excel files, the PDF annual reports, the monthly car sales data, the FY2025
  financials, and the stock exchange data.
- **Status:** none of these have been started. They are new features, not fixes.
- **What we need:** if these are wanted, they should be scoped and prioritised as their
  own piece of work rather than sitting inside a QA report.

---

## One thing worth flagging back

In the Strategy Chat section of the QA report (page 21) there is an *"Independent Groq
evaluation"*. That block contains figures that do not exist in our data — a CIO score of
92/100, an FY24 revenue of $12.4B, and "HP ProLiant servers", which is not even one of
the HP product lines in this platform.

We think that block is AI-generated content that was not checked. We have not acted on
any of it. Please do not treat those as real findings, and it may be worth reviewing how
that section is produced.
