# Build scripts (documentation tooling, not product code)

- `build_docs.py` — the provenance manifest (one `add(...)` per document: source path, destination, sender, channel, date, version, status, supersedes/superseded-by, used-for). Running it copies files ≤ 6 MB, writes `*.LINK.md` pointers for larger ones and `*.MISSING.md` placeholders for files not on this machine, and regenerates `00_INDEX/PROVENANCE_REGISTER.md` and `provenance_manifest.json`. Idempotent.
- `build_questions.py` — the question register (one `q(...)` per question) that generates `05_Questions_and_Clarifications/Answered/ANSWERED_QUESTIONS.md`, `Open/OPEN_QUESTIONS.md`, the per-issue files in `06_Unresolved_and_Open/` and both folder READMEs.

To record a newly retrieved file (e.g. the Rulebook FINAL): set its `src=` in `build_docs.py`, delete the `.MISSING.md` placeholder, run `python3 build_docs.py` from the repo root, then regenerate `MASTER_DOCUMENT_INDEX.md` (its generator snippet is in the session transcript; it reads `provenance_manifest.json`).

To record a client answer: edit the matching `q(...)` (answer, date, status, resolves) and run `python3 build_questions.py`.
