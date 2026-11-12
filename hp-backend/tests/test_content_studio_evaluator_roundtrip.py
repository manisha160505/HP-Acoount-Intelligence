"""Content Studio's copy text passes the Message Evaluator's checks, as it is.

AEON, 12 Nov: a one-pager copied from Content Studio scored "0 heading-like
line(s)" in the Evaluator, a full-length email "183 words (guide up to 180)",
and a LinkedIn message "no salutation found". The two features are one
workflow - write in Content Studio, check in the Evaluator - so each format is
written here at the TOP of Content Studio's own word budget and must pass every
coded check there. The Evaluator's own rewrites are held to the same.

If either side changes its layout, budget or checks, this fails.

Run: python -m pytest tests/test_content_studio_evaluator_roundtrip.py -v
"""

import pytest

from app.services.evaluator import formats as F
from app.services.extractors import content_studio as CS
from app.services.hp import content_gates

PERSONA = {"kind": "archetype", "title": "Section Head IT Infrastructure"}
CTA = "Would you be open to a 20-minute call next week?"


def _words(n: int, word: str = "device") -> str:
    return " ".join([word] * (n - 1)) + " estate."


def _fill(generated: dict, target: int) -> dict:
    """Pad the opening until the asset is exactly `target` words by Content
    Studio's own count."""
    short = target - content_gates.asset_word_count(generated)
    assert short >= 0, "the fixed parts are already over the budget"
    generated["opening"] = (generated.get("opening", "") + " " + " ".join(["fleet"] * short)).strip()
    assert content_gates.asset_word_count(generated) == target
    return generated


def _generated(content_type: str) -> dict:
    if content_type == "email":
        g = {"subject_line": "Re: Lower device TCO across AEON's store estate",
             "opening": "Your remit covers the hardware roadmap.",
             "body_sections": [{"heading": None, "text": _words(50)},
                               {"heading": None, "text": _words(50)}],
             "cta": CTA}
    elif content_type == "linkedin_message":
        g = {"opening": "Your remit covers the hardware roadmap.",
             "body_sections": [{"heading": None, "text": _words(40)}],
             "cta": CTA}
    else:
        # The structured one-pager, as `_validate_asset` projects it: pillars,
        # the HP play and the attached Proof Points as headed sections.
        g = {"headline": "AEON: Streamlining Device Lifecycle Across the Store Estate",
             "opening": "AEON is refreshing its store hardware.",
             "body_sections": [
                 {"heading": "Inventory Visibility Gaps", "text": _words(90)},
                 {"heading": "Lifecycle Cost Pressure", "text": _words(90)},
                 {"heading": CS.HP_PLAY_HEADING, "text": _words(80)},
                 {"heading": CS.PROOF_POINTS_HEADING, "text": _words(60)}],
             "cta": CTA}
    _lo, high = content_gates.WORD_BUDGETS[content_type]
    return _fill(g, high)


def _copied(content_type: str) -> str:
    """What the seller copies from Content Studio, composed by its own code."""
    contract = CS.CONTENT_TYPE_CONTRACTS[content_type]
    record = {"generated": _generated(content_type),
              "greeting": CS._record_greeting(PERSONA, contract)}
    return CS._compose_plain_text(record, contract)


def _failed(text: str, fmt: str) -> list:
    return [(c["check"], c["detail"]) for c in F.structure_checks(text, fmt)["checks"]
            if not c["passed"]]


@pytest.mark.parametrize("content_type", ["email", "linkedin_message", "one_pager"])
def test_content_studio_copy_passes_every_evaluator_check(content_type):
    text = _copied(content_type)
    assert _failed(text, content_type) == [], text


def test_every_content_studio_format_is_an_evaluator_format():
    assert set(CS.CONTENT_TYPE_CONTRACTS) <= set(F.OFFERED_FORMATS)


def test_a_linkedin_message_opens_with_a_composed_hi():
    contract = CS.CONTENT_TYPE_CONTRACTS["linkedin_message"]
    assert CS._record_greeting(PERSONA, contract) == "Hi [Section Head IT Infrastructure Name],"
    assert _copied("linkedin_message").startswith("Hi [")
    # The one-pager is a document, not a letter.
    assert CS._record_greeting(PERSONA, CS.CONTENT_TYPE_CONTRACTS["one_pager"]) is None


def test_an_email_greeting_still_says_dear():
    assert CS._record_greeting(PERSONA, CS.CONTENT_TYPE_CONTRACTS["email"]).startswith("Dear ")


# --- The Evaluator's own rewrites, at the top of their caps ------------------

def _rewrite(fmt: str) -> dict:
    if fmt == "email":
        body = {"subject_line": "Lower device TCO for AEON",
                "opening": "Your remit covers the hardware roadmap.",
                "body_sections": [{"text": _words(60)}], "cta": CTA}
    elif fmt == "linkedin_message":
        body = {"opening": "Your remit covers the hardware roadmap.",
                "body_sections": [{"text": _words(40)}], "cta": CTA}
    else:
        body = {"headline": "AEON device brief", "opening": "AEON is refreshing its stores.",
                "body_sections": [{"heading": h, "text": _words(80)} for h in
                                  ("Account Challenge", "How HP Helps", "Proof Points",
                                   "Next Step")],
                "cta": CTA}
    cap = F.FORMATS[fmt]["rewrite"]["max_words"]
    counted = sum(len(str(v).split()) for k, v in body.items()
                  if k not in ("subject_line", "body_sections"))
    counted += sum(len(s["text"].split()) + len(s.get("heading", "").split())
                   for s in body["body_sections"])
    body["opening"] += " " + " ".join(["fleet"] * (cap - counted))
    return body


@pytest.mark.parametrize("fmt", ["email", "linkedin_message", "one_pager"])
def test_a_rewrite_at_its_cap_passes_and_passes_its_own_checks(fmt):
    rewrite, faults = F.validate_rewrite({"rewrite": _rewrite(fmt)}, fmt, (), PERSONA, "")
    assert faults == [] and rewrite
    assert F.counted_length(rewrite["plain_text"], "words") == F.FORMATS[fmt]["rewrite"]["max_words"]
    assert _failed(rewrite["plain_text"], fmt) == [], rewrite["plain_text"]


def test_a_rewrite_one_word_over_its_cap_is_refused():
    body = _rewrite("linkedin_message")
    body["cta"] += " Thanks"
    _rewrite_out, faults = F.validate_rewrite({"rewrite": body}, "linkedin_message", (), PERSONA, "")
    assert faults == ["rewrite is 111 words; LinkedIn Message allows 110"]


# --- What reads as a heading -------------------------------------------------

@pytest.mark.parametrize("line", [
    "# Account Challenge",                                           # Markdown
    "## How HP Helps",
    "Account Challenge:",                                            # ends in a colon
    "ACCOUNT CHALLENGE",                                             # capitals (Content Studio)
    "HOW HP HELPS",
    "Account Challenge: Streamlining Device Inventory and Lifecycle.",  # label: title (AEON)
    "How HP Helps: Enhanced Fleet Management and Cost Control",
    "How HP Helps",                                                  # Title Case
    "Proof Points",
    "Next Step",
    "Why Now for AEON",
])
def test_these_are_headings(line):
    assert F.heading_lines(line) == [line]


@pytest.mark.parametrize("line", [
    "We help retailers modernise their device estate.",
    "AEON is refreshing the hardware in its stores across Japan this year.",
    "Would you be open to a call next week?",
    "Dear Ms Tan,",
    "Hi [CFO Name],",
    "Best regards,",
    "Sincerely,",
    "[Your Name]",
    "Subject: Lower TCO for AEON",
    "Account Challenge Streamlining Device Inventory And Lifecycle Across Every Store In Japan Today",
    "",
])
def test_these_are_not(line):
    assert F.heading_lines(line) == []


def test_the_aeon_one_pager_has_its_headings_found():
    text = ("AEON Device Lifecycle Brief\n\n"
            "AEON runs one of the largest retail estates in Asia.\n\n"
            "Account Challenge: Streamlining Device Inventory and Lifecycle.\n"
            "Store devices are tracked by hand across regions.\n\n"
            "How HP Helps: Enhanced Fleet Management and Cost Control\n"
            "HP manages the fleet as a service.\n\n"
            "Would you be open to a 30-minute workshop?")
    checks = {c["check"]: c for c in F.structure_checks(text, "one_pager")["checks"]}
    assert checks["scannable_structure"]["passed"], checks["scannable_structure"]["detail"]
    assert F.heading_lines(text)[1:] == [
        "Account Challenge: Streamlining Device Inventory and Lifecycle.",
        "How HP Helps: Enhanced Fleet Management and Cost Control"]


def test_a_one_pager_of_plain_paragraphs_still_fails():
    text = ("AEON runs one of the largest retail estates in Asia.\n\n"
            "Store devices are tracked by hand across regions, which costs time.\n\n"
            "Would you be open to a 30-minute workshop?")
    checks = {c["check"]: c for c in F.structure_checks(text, "one_pager")["checks"]}
    assert not checks["scannable_structure"]["passed"]
