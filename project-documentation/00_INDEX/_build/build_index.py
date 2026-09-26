#!/usr/bin/env python3
"""Regenerate 00_INDEX/MASTER_DOCUMENT_INDEX.md from provenance_manifest.json (run build_docs.py first)."""
import json
from pathlib import Path
OUT=Path(__file__).resolve().parents[2]
rows=json.load(open(OUT/'00_INDEX/provenance_manifest.json'))
def cat(r):
    d=r['dest']
    if d.startswith('01_'): return 'Client provided'
    if d.startswith('04_'): return 'Client data' if 'CLIENT' in r['origin'] else 'Derived data'
    if d.startswith('08_'): return 'Reference'
    if d.startswith('02_'): return 'Decision maker'
    if d.startswith('07_'): return 'Internal'
    return d.split('/')[0]
def short(s,n=140): return s if len(s)<=n else s[:n-1]+'…'
T=['| Id | Document | Category | Source | Date | Version | Status | Replaced by | Used for | Location |','|---|---|---|---|---|---|---|---|---|---|']
for r in sorted(rows, key=lambda r:(r['dest'], r['date'], r['id'])):
    src=r['sender'].split(' (')[0].split(' -')[0]
    loc=('`'+r['copied'][0]+'`') if r['copied'] else '—'
    T.append(f"| {r['id']} | {r['name']} | {cat(r)} | {src} | {r['date']} | {r['version'] or '—'} | **{r['status']}** | {short(r['superseded_by'] or '—',90)} | {short(r['used_for'])} | {loc} |")
extra=[
 ('X01','MASTER_DOCUMENT_INDEX.md (this file)','Index','documentation build','2026-09-25','1','CURRENT','—','Single starting point.','`00_INDEX/MASTER_DOCUMENT_INDEX.md`'),
 ('X02','DECISION_LOG.md','Index','documentation build','2026-09-25','1','CURRENT','—','Every decision with source; classification labels.','`00_INDEX/DECISION_LOG.md`'),
 ('X03','FEATURE_DOCUMENT_MAPPING.md','Index','documentation build','2026-09-25','1','CURRENT','—','Feature → data → docs → questions → gaps → code.','`00_INDEX/FEATURE_DOCUMENT_MAPPING.md`'),
 ('X04','PROVENANCE_REGISTER.md + provenance_manifest.json','Index','documentation build','2026-09-25','1','CURRENT','—','File-level provenance, md5, versions.','`00_INDEX/PROVENANCE_REGISTER.md`'),
 ('X05','CONFLICT_REGISTER.md','Index','documentation build','2026-09-25','1','CURRENT','—','Where documents disagree; needs-confirmation flags.','`00_INDEX/CONFLICT_REGISTER.md`'),
 ('X06','EMAIL_TIMELINE.md','Index','documentation build','2026-09-25','1','CURRENT','—','Chronology of every message with attachments.','`00_INDEX/EMAIL_TIMELINE.md`'),
 ('X07','MISSING_FILES.md','Index','documentation build','2026-09-25','1','CURRENT','—','What could not be retrieved and how to get it.','`00_INDEX/MISSING_FILES.md`'),
 ('X08','DECISION_MAKER_REGISTER.md','Decision maker','documentation build','2026-09-25','1','CURRENT','—','Which decision doc is current / superseded / under review.','`02_Decision_Maker/DECISION_MAKER_REGISTER.md`'),
 ('X09','03_Feature_and_Logic/*.md (11 features + 3 cross-cutting)','Feature & logic','documentation build','2026-09-25','1','CURRENT','—','Per-feature approved logic vs internal vs open.','`03_Feature_and_Logic/`'),
 ('X10','_extraction_notes A / B / D','Internal (generated)','documentation build','2026-09-25','1','INTERNAL — GENERATED, unverified','—','Rule registers extracted from the client docs; feature→code map.','`03_Feature_and_Logic/_extraction_notes/`'),
 ('X11','04_Data_and_Source_Definitions/*/README.md (12)','Data definitions','documentation build','2026-09-25','1','CURRENT','—','Per-source definition, coverage, gaps, authority.','`04_Data_and_Source_Definitions/`'),
 ('X12','ANSWERED_QUESTIONS.md / OPEN_QUESTIONS.md','Questions','documentation build','2026-09-25','1','CURRENT','—','74 questions with status and impact.','`05_Questions_and_Clarifications/`'),
 ('X13','06_Unresolved_and_Open/*.md (26 issues)','Unresolved','documentation build','2026-09-25','1','OPEN','—','One page per unresolved issue.','`06_Unresolved_and_Open/`'),
 ('X14','_generated_catalogue_of_internal_docs.md','Internal (generated)','documentation build','2026-09-25','1','INTERNAL — GENERATED, unverified','—','Catalogue and question inventory of internal docs.','`07_Internal_Generated/Analysis/`'),
]
for e in extra: T.append('| '+' | '.join(e)+' |')
n=len(rows); client=sum(1 for r in rows if r['origin'].startswith('CLIENT')); internal=sum(1 for r in rows if r['origin'].startswith(('INTERNAL','GENERATED')))
missing=sum(1 for r in rows if not r['local_path']); sup=sum(1 for r in rows if 'SUPERSEDED' in r['status']); cur=sum(1 for r in rows if r['dest']=='02_Decision_Maker' or '02_Decision_Maker' in r['also'])
head=f"""# Master Document Index — HP 220-Account Intelligence

Built 25 Sep 2026. One row per document or dataset discovered in the project folders, `~/Downloads` and the Gmail threads, plus the index documents produced by this exercise. Ids are stable: C = client-provided, I = internal, X = index. Full provenance (email, md5, local path) per id: `PROVENANCE_REGISTER.md`. Decisions: `DECISION_LOG.md`. Disagreements: `CONFLICT_REGISTER.md`.

**Consolidation note:** the former `docs/` and `NewDocs/` folders were deleted on 25 Sep 2026 after every file in them was verified as copied or moved into this tree; this tree is now the only local home of those files.

**Status values:** CURRENT · APPROVED · SUPERSEDED · OPEN · UNRESOLVED · REFERENCE · INTERNAL · NOT ON THIS MACHINE (a proven-to-exist file with no local copy; see `MISSING_FILES.md`).

**Counts (source files, excluding the X index rows):** {n} entries · client-provided or client data {client} · internal or generated {internal} · superseded {sup} · not on this machine {missing} · copied into `02_Decision_Maker/` as current decision documents {cur} (one of them, the Rulebook v1, is the only local copy of a superseded version; one, the internal Rules doc, is under client review).

**How to read "Used for":** the feature, pipeline, dataset, inference or code behaviour that depends on the document. Feature-level view: `FEATURE_DOCUMENT_MAPPING.md`.

## A. Read first (the source of truth in precedence order)
1. Client answers of 24 Sep: C36 clarifying opens_2, C35 clarifying opens_1 (re-send), and the dated email decisions of 16 / 18 / 23 / 24 Sep (`DECISION_LOG.md`).
2. Client logic: C28 Recommendation Tuning Logic FINAL v4 · C09 Urgency Score Updated Final · C18 Live Signal Scoring Logic · C21 Tech Landscape Confidence FINAL · C29 Rulebook FINAL (**missing**; C15 v1 is local) · C26 new file explanation.
3. Requirements: C01 HP_ABX_v3_final · C02 additional data (deck rules, analytics module) · C03 account list.
4. Internal, under client review (not approved): I01 HP-Account-Intelligence-Rules.docx.
5. Awaiting client answers: I14 round-3 pack (25 Sep).

## B. All documents

"""
(OUT/'00_INDEX/MASTER_DOCUMENT_INDEX.md').write_text(head+'\n'.join(T)+'\n')
print('index rows', len(T)-2, 'entries', n, 'client', client, 'internal', internal, 'superseded', sup, 'missing', missing, 'decision-maker', cur)
