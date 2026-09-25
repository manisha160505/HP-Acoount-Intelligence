# HP 220-Account Intelligence — project documentation

Single starting point for every document, decision, question and data definition on the project. Built 25 Sep 2026 from the local folders (the former `docs/` and `NewDocs/`, now deleted after consolidation here; `220 account data /`; `~/Downloads`), the Gmail threads with BridgeAI, and the Drive/SharePoint links in those threads. Originals were copied, never edited; nothing was deleted.

```
Start here:
→ 00_INDEX/MASTER_DOCUMENT_INDEX.md      every document, its status, what replaced it, what it is used for
→ 00_INDEX/DECISION_LOG.md               every decision with question, answer, date, who, source, impact
→ 00_INDEX/EMAIL_TIMELINE.md             what was sent when (the version chronology)

Need current business logic?            → 02_Decision_Maker/  (DECISION_MAKER_REGISTER.md first)
Need the logic for one feature?          → 03_Feature_and_Logic/<feature>.md  or  00_INDEX/FEATURE_DOCUMENT_MAPPING.md
Need client questions and answers?       → 05_Questions_and_Clarifications/  (Answered/ and Open/)
Need unresolved issues?                  → 06_Unresolved_and_Open/  (one page per issue)
Need our own analysis, QA, trackers?     → 07_Internal_Generated/
Need dataset definitions?                → 04_Data_and_Source_Definitions/
Need where a file came from?             → 00_INDEX/PROVENANCE_REGISTER.md
Need what could not be retrieved?        → 00_INDEX/MISSING_FILES.md
Where two documents disagree?            → 00_INDEX/CONFLICT_REGISTER.md
Background material (decks, PDFs, POCs)? → 08_Reference_Material/
```

## Status values
CURRENT · APPROVED · SUPERSEDED · OPEN · UNRESOLVED · PARTIALLY RESOLVED · REFERENCE · INTERNAL · NOT ON THIS MACHINE (listed in MISSING_FILES.md, with a `.MISSING.md` placeholder in the folder where the file belongs).

## Classification of statements
CLIENT DECISION · CLIENT DATA · CLIENT REFERENCE · INTERNAL IMPLEMENTATION DECISION · INTERNAL ASSUMPTION · OPEN QUESTION. Internal assumptions are never presented as client rules; where the two disagree the conflict register records both.

## The source of truth going forward
1. **Client answers** (`02_Decision_Maker/clarifying opens_2.docx`, `clarifying opens_1  Dhruvi.docx`) and the dated email decisions in `DECISION_LOG.md` override the older client documents on the same point.
2. **Client logic documents** — Recommendation Tuning Logic FINAL v4, Urgency Score Updated Final, Live Signal Scoring Logic, Tech Landscape Confidence FINAL, the Rulebook (FINAL 23 Sep — not yet on this machine; v1 17 Sep is the local copy).
3. **HP_ABX_v3_final** for everything the above do not cover.
4. **HP-Account-Intelligence-Rules.docx** is INTERNAL and under client review; it does not outrank any of the above.

## Housekeeping
- Files bigger than 6 MB and whole data folders are linked (`*.LINK.md`), not copied.
- The repository's `.gitignore` ignores `*.docx *.xlsx *.pptx *.pdf *.csv` everywhere, so the client files in this tree stay uncommitted; the Markdown indexes are committable.
- To refresh the provenance register or the question registers after a new file or a client answer, edit and re-run the scripts in `00_INDEX/_build/` (see its README).
- The Zscaler "ABM project call" thread and the Micron POC mail in the same mailbox are different engagements and are excluded.
