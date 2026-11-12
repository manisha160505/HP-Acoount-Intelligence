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


# --- The facts a figure is checked against are Content Studio's ---------------

ACCOUNT = "6abfaa0357bc331e377c07c5"


@pytest.fixture
def fake_db():
    from regen_fakes import FakeDb
    return FakeDb()


def _evidence(**over):
    base = {"firmographics": [{"Company Name": "AEON CO., LTD.", "Employees": "155,000"}],
            "prospect_contacts": [], "job_openings": [],
            "company_name": "AEON CO., LTD.",
            "items": [("Technology estate", "412 technologies in the detected estate"),
                      ("Open hiring", "37 job postings in the last 12 months")]}
    return {**base, **over}


def test_a_figure_content_studio_wrote_from_is_supported(fake_db, monkeypatch):
    from app.services.evaluator import sources as SRC
    monkeypatch.setattr(CS, "account_evidence", lambda _db, _a: _evidence())
    sources = SRC.build(fake_db, ACCOUNT, {}, "draft")
    for claim in ("AEON runs 412 technologies across its estate.",
                  "AEON has 37 open job postings this year.",
                  "With 155,000 employees, AEON's device fleet is large."):
        assert sources.verify_claim(claim)["verdict"] == "supported", claim


def test_without_it_the_same_figure_was_unsupported(fake_db, monkeypatch):
    """The gap this closes: the Evaluator's own widgets do not hold it."""
    from app.services.evaluator import sources as SRC
    monkeypatch.setattr(CS, "account_evidence", lambda _db, _a: _evidence(items=[]))
    sources = SRC.build(fake_db, ACCOUNT, {}, "draft")
    assert sources.verify_claim("AEON runs 412 technologies.")["verdict"] == "unsupported"


def test_a_failed_read_still_evaluates(fake_db, monkeypatch):
    from app.services.evaluator import sources as SRC

    def boom(_db, _a):
        raise RuntimeError("dataset unreadable")

    monkeypatch.setattr(CS, "account_evidence", boom)
    sources = SRC.build(fake_db, ACCOUNT, {}, "draft")
    assert sources.verify_claim("AEON runs 412 technologies.")["verdict"] == "unsupported"


def test_content_studio_writes_from_the_same_function():
    """One function for both, so the facts cannot drift apart."""
    import inspect
    assert "account_evidence(db, account_id)" in inspect.getsource(CS._build_generation_context)


# --- The case study a message cites is checked against that study ---------------

STUDY = {"_id": "s1", "customer": "Ulster University", "product_featured": "Poly Studio",
         "headline": "Ulster University equipped 120 hybrid classrooms with Poly video",
         "outcome": "and cut set-up time by 40%."}


def test_a_cited_study_is_found_by_customer_or_headline(fake_db):
    from app.services.hp import case_studies as cstudies
    fake_db[cstudies.COLLECTION].insert_one(dict(STUDY))
    assert [s["customer"] for s in cstudies.named_in(fake_db, "As at Ulster University, ...")] \
        == ["Ulster University"]
    quoted = "PROOF POINTS\nUlster University equipped 120 hybrid classrooms with Poly video"
    assert cstudies.named_in(fake_db, quoted.replace("Ulster University", "One customer")) == []
    assert len(cstudies.named_in(fake_db, quoted)) == 1
    assert cstudies.named_in(fake_db, "Nothing cited here.") == []


def test_its_figures_are_supported(fake_db, monkeypatch):
    from app.services.evaluator import evaluate as E, sources as SRC
    from app.services.hp import case_studies as cstudies
    fake_db[cstudies.COLLECTION].insert_one(dict(STUDY))
    monkeypatch.setattr(CS, "account_evidence", lambda _db, _a: _evidence(items=[]))
    text = ("PROOF POINTS\nUlster University equipped 120 hybrid classrooms with Poly video "
            "and cut set-up time by 40%.")
    sources = SRC.build(fake_db, ACCOUNT, {}, text)
    claim = "Ulster University cut set-up time by 40% across 120 hybrid classrooms."
    assert sources.verify_claim(claim)["verdict"] == "unsupported"
    proof = E._proof_available(fake_db, [], "", text)
    assert [p["customer"] for p in proof] == ["Ulster University"]
    sources.offer(proof)
    assert sources.verify_claim(claim)["verdict"] == "supported"


# --- Content Studio's layout is not marked down ---------------------------------

@pytest.mark.parametrize(("fmt", "shown"), [("email", True), ("linkedin_message", True),
                                            ("one_pager", False)])
def test_the_house_layout_is_explained_where_it_applies(fake_db, monkeypatch, fmt, shown):
    from app.services.evaluator import evaluate as E, sources as SRC
    monkeypatch.setattr(CS, "account_evidence", lambda _db, _a: _evidence())
    text = _copied(fmt)
    prompt = E._user_prompt(text, {}, "awareness", fmt, E.MODE_LITE,
                            SRC.build(fake_db, ACCOUNT, {}, text), F.structure_checks(text, fmt))
    assert (E.HOUSE_LAYOUT in prompt) is shown
    assert "Sincerely, The HP Inc. Team" in E.HOUSE_LAYOUT and "'Re: '" in E.HOUSE_LAYOUT


def test_the_house_layout_is_what_content_studio_writes():
    text = _copied("email")
    assert text.startswith("Subject: Re: ")
    from app.services.evaluator import evaluate as E
    assert CS.EMAIL_SIGNOFF.replace("\n\n", " ") in E.HOUSE_LAYOUT


# --- The ask is the closing paragraph, as Content Studio's cta is ---------------

def test_a_question_in_the_body_is_not_the_ask():
    from app.services.evaluator import evaluate as E
    text = ("Subject: Re: Your store refresh\n\nDear [CFO Name],\n\n"
            "What would pricing for 500 devices mean for your budget? Many retailers ask.\n\n"
            "I'd welcome a 20-minute call next week.\n\nSincerely,\n\nThe HP Inc. Team")
    assert E._ask_sentence(text) == "I'd welcome a 20-minute call next week."
    assert E._severe_failures(text, "cfo") == []


def test_a_closing_question_is_still_the_ask():
    from app.services.evaluator import evaluate as E
    text = "Your estate is ageing.\n\nShall I send pricing for the fleet?\n\nBest regards,\nAnna"
    assert E._ask_sentence(text) == "Shall I send pricing for the fleet?"
    assert E._severe_failures(text, "cfo")


@pytest.mark.parametrize("content_type", ["email", "linkedin_message", "one_pager"])
def test_the_ask_of_a_content_studio_message_is_its_cta(content_type):
    from app.services.evaluator import evaluate as E
    assert E._ask_sentence(_copied(content_type)) == CTA
