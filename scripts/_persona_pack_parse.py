# -*- coding: utf-8 -*-
"""Parse spec Section 5 into structured cards, verbatim.

The point is that the pack's text becomes DERIVED from the document rather
than transcribed from it: re-running this against a revised spec regenerates
the cards, and a field count that moves is a parse failure rather than a
silent drift.
"""
import io
import json
import re
import sys

SRC = sys.argv[1]
OUT = sys.argv[2]

DASHES = {"—": " - ", "–": "-", "‘": "'", "’": "'",
          "“": '"', "”": '"', "…": "...", " ": " "}


def clean(text):
    for bad, good in DASHES.items():
        text = text.replace(bad, good)
    return " ".join(text.split())


def strip_marks(text):
    """Remove [E#] refs and [inference] marks; return (text, refs, inferred)."""
    refs = re.findall(r"\[E(\d+)\]", text)
    inferred = "[inference" in text
    text = re.sub(r"\s*\[E\d+\]", "", text)
    text = re.sub(r"\s*\[inference[^\]]*\]", "", text)
    text = re.sub(r"\s+([.;,])", r"\1", text)
    text = text.strip()
    # A bullet reduced to "Foo ." by a trailing ref.
    text = re.sub(r"\s+\.$", ".", text)
    return text, ["E" + r for r in refs], inferred


def bullets(block, start, end):
    pattern = re.escape(start) + r"\n(.*?)(?=\n" + re.escape(end) + r")"
    match = re.search(pattern, block, re.S)
    if not match:
        return None
    return [line.strip() for line in match.group(1).split("\n") if line.strip()]


def dotted(block, label):
    """A '· a · b · c' line."""
    match = re.search(re.escape(label) + r"[^\n]*", block)
    if not match:
        return None
    line = match.group(0)
    line = line.split(label, 1)[1]
    parts = []
    for raw in line.split("·"):
        # The "[inference]" marker sits before the first separator and leaves an
        # empty leading part; a dotted list also ends with a full stop the other
        # items do not carry.
        value = strip_marks(raw)[0].strip().rstrip(".")
        if value:
            parts.append(value)
    return parts


def main():
    text = io.open(SRC, encoding="utf-8").read()
    blocks = re.split(r"\n(?=5\.\d+ `)", text)[1:]
    cards = []
    for block in blocks:
        head = block.split("\n")[0]
        pid = re.search(r"`([a-z-]+)`", head).group(1)
        title = clean(head.split("`")[-1]).lstrip("- ").strip()

        meta = block.split("\n")[1]
        department = clean(re.search(r"Department (.*?)·", meta).group(1))
        angle = clean(re.search(r"Committee angle (.*?)·", meta).group(1))
        grade = clean(re.search(r"Evidence grade (.*)$", meta).group(1))

        remit = clean(re.search(r"^Remit (.*)$", block, re.M).group(1))

        card = {"persona_id": pid, "title": title, "department": department,
                "committee_angle": angle, "evidence_grade": grade,
                "remit": strip_marks(remit)[0]}

        refs, inferred_fields = set(), []
        spans = [
            ("goals", "Goals", "Pain points"),
            ("pain_points", "Pain points", "Value drivers"),
            ("value_drivers", "Value drivers", "Decision criteria"),
            ("decision_criteria", "Decision criteria - the questions they ask",
             "Typical objections"),
        ]
        block_c = clean_lines(block)
        for key, start, end in spans:
            raw = bullets(block_c, start, end)
            assert raw is not None, "%s: %s not found" % (pid, key)
            items, field_inferred = [], False
            for line in raw:
                value, r, inf = strip_marks(clean(line))
                # Decision criteria are quoted in the document; the quotes are
                # its formatting, not part of the question.
                items.append(value.strip('"'))
                refs.update(r)
                field_inferred = field_inferred or inf
            card[key] = items
            if field_inferred:
                inferred_fields.append(key)

        # Typical objections: a labelled block of quoted lines.
        raw = bullets(block_c, "Typical objections [inference]", "What resonates")
        if raw is None:
            raw = bullets(block_c, "Typical objections", "What resonates")
        assert raw is not None, "%s: objections" % pid
        card["typical_objections"] = [strip_marks(clean(x))[0].strip('"') for x in raw]
        inferred_fields.append("typical_objections")

        for key, label in (("resonates", "What resonates"),
                           ("does_not_resonate", "What does not resonate")):
            parts = dotted(block_c, label)
            assert parts, "%s: %s" % (pid, key)
            card[key] = [clean(p) for p in parts]
            inferred_fields.append(key)

        tone = clean(re.search(r"^Tone (.*)$", block_c, re.M).group(1))
        fmt = clean(re.search(r"^Format (.*)$", block_c, re.M).group(1))
        metrics = re.search(r"^Key metrics (.*)$", block_c, re.M).group(1)
        card["content_preferences"] = {
            "tone": strip_marks(tone)[0],
            "format": strip_marks(fmt)[0],
            "key_metrics": [strip_marks(clean(m))[0].rstrip(".")
                            for m in metrics.split("·") if m.strip()],
        }
        inferred_fields.append("content_preferences")

        opp = clean(re.search(r"^HP opportunity (.*)$", block_c, re.M).group(1))
        card["hp_opportunity"] = strip_marks(opp)[0]

        state_line = clean(re.search(r"^Behavioural state (.*)$", block_c, re.M).group(1))
        card["behavioural_state"] = re.match(r"([A-Z_]+)", state_line).group(1)
        card["behavioural_state_note"] = strip_marks(state_line)[0]
        inferred_fields.append("behavioural_state")

        card["evidence_refs"] = sorted(refs, key=lambda r: int(r[1:]))
        card["inference_fields"] = sorted(set(inferred_fields))
        cards.append(card)

    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(cards, indent=1, ensure_ascii=False))
    for c in cards:
        print("%-26s goals=%d pain=%d value=%d crit=%d obj=%d res=%d not=%d metrics=%d refs=%d"
              % (c["persona_id"], len(c["goals"]), len(c["pain_points"]),
                 len(c["value_drivers"]), len(c["decision_criteria"]),
                 len(c["typical_objections"]), len(c["resonates"]),
                 len(c["does_not_resonate"]),
                 len(c["content_preferences"]["key_metrics"]),
                 len(c["evidence_refs"])))


def clean_lines(block):
    out = []
    for line in block.split("\n"):
        for bad, good in DASHES.items():
            line = line.replace(bad, good)
        out.append(" ".join(line.split()))
    return "\n".join(out)


main()
