# -*- coding: utf-8 -*-
"""Rewrite the PERSONAS literal from the specification's own text.

Why this is a generator and not an edit. The cards were transcribed by hand the
first time and the statistics did not survive the transcription: Section 5
carries 70 percentage figures and 116 [E#] source references, and the pack
carried none of them. Some of that was deliberate - a footnote marker renders to
a seller - and the rest was drift nobody recorded.

Deriving the text from the document removes the question. `pack_extract.py`
parses Section 5, this writes the literal, and a field count that moves is a
parse failure rather than a silent change.

What is NOT doc-derived and is preserved from the existing pack:

  * `fast_track_trigger` and `key_blocker`, which come from Section 4.9's
    entry-state table rather than from the card
  * `confidence_explanation`, which is ours - the specification gives an
    evidence GRADE per card but no sentence saying what the grade rests on
"""
import io
import json
import re
import sys

sys.path.insert(0, "hp-backend/src")
from app.services.hp import buyer_personas as bp  # noqa: E402

CARDS = json.load(io.open(sys.argv[1], encoding="utf-8"))
P = "hp-backend/src/app/services/hp/buyer_personas.py"

# Fields whose text now comes from the document.
DOC_FIELDS = ("title", "department", "committee_angle", "evidence_grade", "remit",
              "goals", "pain_points", "value_drivers", "decision_criteria",
              "typical_objections", "resonates", "does_not_resonate",
              "content_preferences", "hp_opportunity", "behavioural_state")
# Fields kept from the existing pack.
KEPT = ("fast_track_trigger", "key_blocker", "confidence_explanation")


def q(text):
    """A Python string literal, wrapped at a readable width."""
    text = str(text)
    if len(text) <= 62:
        return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')
    words, lines, current = text.split(" "), [], ""
    for word in words:
        if len(current) + len(word) + 1 > 62 and current:
            lines.append(current)
            current = word
        else:
            current = (current + " " + word).strip()
    if current:
        lines.append(current)
    out = []
    for i, line in enumerate(lines):
        body = line.replace("\\", "\\\\").replace('"', '\\"')
        out.append('"%s%s"' % (body, "" if i == len(lines) - 1 else " "))
    return "\n".join(out)


def render_list(items, indent):
    pad = " " * indent
    out = ["("]
    for item in items:
        literal = q(item)
        parts = literal.split("\n")
        out.append(pad + parts[0] + ("," if len(parts) == 1 else ""))
        for extra in parts[1:]:
            out.append(pad + " " + extra + ("," if extra is parts[-1] else ""))
        if len(parts) > 1:
            out[-1] = out[-1].rstrip(",") + ","
    out.append(" " * (indent - 4) + ")")
    return "\n".join(out)


def render_card(doc, kept):
    lines = ['    "%s": {' % doc["persona_id"]]
    lines.append('        "persona_id": "%s",' % doc["persona_id"])
    for key in ("title", "department", "committee_angle"):
        lines.append('        "%s": %s,' % (key, {
            "committee_angle": "ANGLE_" + {
                "Economic Buyer": "ECONOMIC", "Technical Buyer": "TECHNICAL",
                "Finance - Budget Owner": "FINANCE",
                "Gatekeeper - Procurement & Legal": "GATEKEEPER",
            }[doc["committee_angle"].split(" (")[0]],
        }.get(key, q(doc[key]))))
    lines.append('        "evidence_grade": %s,' % q(kept.get("evidence_grade")
                                                     or doc["evidence_grade"]))
    lines.append('        "confidence_explanation": (')
    lines.append("            " + q(kept["confidence_explanation"]).replace("\n", "\n            "))
    lines.append("        ),")
    lines.append('        "remit": (')
    lines.append("            " + q(doc["remit"]).replace("\n", "\n            "))
    lines.append("        ),")
    for key in ("goals", "pain_points", "value_drivers", "decision_criteria",
                "typical_objections", "resonates", "does_not_resonate"):
        lines.append('        "%s": %s,' % (key, render_list(doc[key], 12)))
    prefs = doc["content_preferences"]
    lines.append('        "content_preferences": {')
    lines.append('            "tone": %s,' % q(prefs["tone"]).replace("\n", "\n                     "))
    lines.append('            "format": (')
    lines.append("                " + q(prefs["format"]).replace("\n", "\n                "))
    lines.append("            ),")
    lines.append('            "key_metrics": %s,' % render_list(prefs["key_metrics"], 16))
    lines.append("        },")
    lines.append('        "hp_opportunity": (')
    lines.append("            " + q(doc["hp_opportunity"]).replace("\n", "\n            "))
    lines.append("        ),")
    lines.append('        "behavioural_state": "%s",' % doc["behavioural_state"])
    for key in ("fast_track_trigger", "key_blocker"):
        lines.append('        "%s": (' % key)
        lines.append("            " + q(kept[key]).replace("\n", "\n            "))
        lines.append("        ),")
    lines.append('        "evidence_refs": (%s),'
                 % ", ".join('"%s"' % r for r in doc["evidence_refs"]))
    lines.append('        "inference_fields": (')
    lines.append("            " + ", ".join('"%s"' % f for f in doc["inference_fields"]) + ",")
    lines.append("        ),")
    lines.append("    },")
    return "\n".join(lines)


def main():
    source = io.open(P, encoding="utf-8").read()
    start = source.index("PERSONAS = {")
    end = source.index("\nPERSONA_IDS")

    body = ["PERSONAS = {"]
    for doc in CARDS:
        kept = bp.PERSONAS[doc["persona_id"]]
        # Every doc-derived field must already exist on the card, or the two
        # have diverged in shape rather than in wording.
        for field in DOC_FIELDS:
            assert field in kept, "%s missing %s" % (doc["persona_id"], field)
        for field in KEPT:
            assert field in kept, "%s missing %s" % (doc["persona_id"], field)
        body.append(render_card(doc, kept))
    body.append("}")

    new = source[:start] + "\n".join(body) + source[end:]
    io.open(P, "w", encoding="utf-8", newline="").write(new)
    print("PERSONAS rewritten from the specification: %d cards" % len(CARDS))


main()
