#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Rebuild `app/services/hp/buyer_personas.py`'s PERSONAS from the build spec.

    python scripts/regenerate_persona_pack.py

Reads Section 5 of HP220_Content_Studio_Message_Evaluator_Build_Spec_BridgeAI
_30Sept2026.docx out of `project-documentation/` and writes the eight cards
into the pack, verbatim.

Why this exists rather than an editor. The cards were transcribed by hand the
first time and the transcription lost every statistic: Section 5 carries
seventy percentage figures and a hundred-odd [E#] source references, and the
pack carried none of them. Some of that was a decision - a footnote marker in
the middle of a pain point renders to a seller as a defect - and the rest was
drift nobody wrote down. Deriving the text removes the question.

Run it when HP revises the specification. Then read the diff: a card whose
wording HP changed should show as changed text, and a field count that moves
means the document's shape changed and the parser needs looking at, not that
the pack should quietly carry fewer goals than the document lists.

Three fields survive a regeneration because they do not come from Section 5:
`fast_track_trigger` and `key_blocker` (Section 4.9's entry-state table) and
`confidence_explanation` (ours - the specification grades each card's evidence
but does not write the sentence saying what the grade rests on).

After running: bump `PERSONA_PACK_VERSION`, run the tests, and read the diff
before committing anything.
"""
import glob
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from html import unescape

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOCX_GLOB = os.path.join(ROOT, "project-documentation",
                         "*Content_Studio_Message_Evaluator_Build_Spec*.docx")


def spec_text() -> str:
    """The build specification as plain text, paragraphs preserved."""
    matches = sorted(glob.glob(DOCX_GLOB))
    if not matches:
        sys.exit("no build specification found at %s" % DOCX_GLOB)
    if len(matches) > 1:
        print("note: %d specifications present, using the last by name:\n  %s"
              % (len(matches), matches[-1]))
    with zipfile.ZipFile(matches[-1]) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    return unescape(re.sub(r"<[^>]+>", "", xml))


def section_five(text: str) -> str:
    lines = text.split("\n")
    try:
        start = next(i for i, line in enumerate(lines)
                     if line.startswith("5. Persona pack"))
        end = next(i for i, line in enumerate(lines)
                   if line.startswith("6. Guardrails"))
    except StopIteration:
        sys.exit("could not find Section 5 - has the specification been "
                 "restructured? The parser keys off the headings "
                 "'5. Persona pack' and '6. Guardrails'.")
    return "\n".join(lines[start:end])


def main() -> None:
    work = tempfile.mkdtemp(prefix="persona-pack-")
    sec5 = os.path.join(work, "section5.txt")
    cards = os.path.join(work, "cards.json")
    with open(sec5, "w", encoding="utf-8") as handle:
        handle.write(section_five(spec_text()))

    for script, args in ((os.path.join(HERE, "_persona_pack_parse.py"), [sec5, cards]),
                         (os.path.join(HERE, "_persona_pack_write.py"), [cards])):
        result = subprocess.run([sys.executable, script, *args], cwd=ROOT, check=False)
        if result.returncode:
            sys.exit("%s failed" % os.path.basename(script))

    print("\nNow: bump PERSONA_PACK_VERSION, run `python -m pytest hp-backend -q`, "
          "and read the diff.")


if __name__ == "__main__":
    main()
