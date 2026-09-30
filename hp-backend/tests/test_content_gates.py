"""The fourteen gates, and the acceptance tests the client will ask for by name.

Spec Section 6 draws the line this file is about:

    The prompt rules are instructions the model may follow. These are checks
    the code enforces.

So every test here is about what happens to output the model already produced,
never about what the prompt asked for.

Two properties matter as much as the individual gates:

**Each gate carries its own consequence.** Some regenerate once and then
reject; some reject outright and are never retried. A suite that only asserted
"a finding was raised" would let those collapse into each other, and G4 - the
gate with no regeneration allowance - is precisely the one that must not.

**An empty result is a pass.** `test_a_clean_asset_raises_nothing` is what
stops this file being satisfied by a gate suite that flags everything.

Acceptance tests from spec Section 7 are named T1, T2, T10 ... in their
docstrings, because that is how the client refers to them.

Run: python -m pytest tests/test_content_gates.py -v
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.services.extractors.grounding import corpus_from_texts
from app.services.hp import content_gates as cg

# An account whose evidence carries one figure and nothing else numeric.
EVIDENCE = ("Advantest runs a mixed estate of 220 technologies across its "
            "engineering sites. The IT team reported 220 devices due for "
            "refresh.")
CORPUS = corpus_from_texts([EVIDENCE])
LABELS = {"A1": EVIDENCE, "P3": "Buying-committee angle: Finance - Budget Owner"}


def _asset(**over) -> dict:
    """A clean email to a CFO: one allowed line, an in-angle ask, cited."""
    base = {
        "subject_line": "Re: the refresh calendar and what it costs to hold",
        "opening": "Your team reported devices due for refresh across the "
                   "engineering sites.",
        "body_sections": [{"text": "At HP, we can set the lifecycle economics "
                                   "against a fixed multi-year cost so the "
                                   "comparison is like for like."}],
        "cta": "Worth walking through an extend-versus-replace comparison?",
        "hp_products": ["HP Care Pack Services"],
        "evidence_used": ["A1"],
    }
    base.update(over)
    return base


def _run(asset, persona_id="cfo", content_type="", filled=False, **kw):
    return cg.run(asset, persona_id=persona_id, content_type=content_type,
                  filled=filled, corpus=CORPUS, supplied_labels=("A1", "P3"),
                  label_texts=LABELS, **kw)


def _gates(findings):
    return {f["gate"] for f in findings}


# ---------------------------------------------------------------------------
# The baseline
# ---------------------------------------------------------------------------

def test_a_clean_asset_raises_nothing():
    """The test that stops a gate suite passing by flagging everything."""
    assert _run(_asset()) == []


# ---------------------------------------------------------------------------
# G4 - the gate the specification says pays for the table
# ---------------------------------------------------------------------------

def test_t1_a_video_bar_pitched_to_a_cfo_is_rejected():
    """Acceptance test T1, and the failure this whole module exists for.

    Spec Section 2.3: "a perfectly fluent, perfectly grounded email that
    pitches a Poly video bar to a CFO ... passes every check currently in
    place, and it is the one output that makes a seller stop trusting the
    tool."
    """
    findings = _run(_asset(hp_products=["Poly Studio"]))
    g4 = [f for f in findings if f["gate"] == "G4"]
    assert g4, "a denied line reached a CFO unflagged"
    assert g4[0]["action"] == cg.ACTION_REJECT
    assert g4[0]["denied_line_named"] == "Poly Studio"
    assert g4[0]["where_found"] == "hp_products"


def test_g4_catches_a_denied_line_in_prose_not_just_the_field():
    """The damage is done by the sentence a seller reads, not by the machine
    field beside it."""
    findings = _run(_asset(
        hp_products=[],
        body_sections=[{"text": "Poly Studio would transform your meeting rooms."}]))
    g4 = [f for f in findings if f["gate"] == "G4"]
    assert g4 and g4[0]["where_found"] == "prose"
    assert g4[0]["action"] == cg.ACTION_REJECT


def test_t10_a_denied_print_line_for_the_standards_owner():
    """Acceptance test T10."""
    findings = _run(_asset(hp_products=["HP Enterprise Print / MPS"],
                           cta="Shall we review the print fleet?"),
                    persona_id="pc-fleet-standards-owner")
    assert "G4" in _gates(findings)


def test_g4_never_offers_to_regenerate():
    """Spec Section 6: "Reject - no silent pass." Every other gate may retry;
    this one may not, and that distinction is the point of the action field."""
    findings = _run(_asset(hp_products=["Poly Studio"]))
    assert all(f["action"] == cg.ACTION_REJECT
               for f in findings if f["gate"] == "G4")


def test_the_allowed_line_for_the_right_persona_passes():
    findings = _run(_asset(hp_products=["Poly Studio"],
                           cta="Would a pilot in one room be worth trying?"),
                    persona_id="av-collaboration-manager")
    assert "G4" not in _gates(findings)


# ---------------------------------------------------------------------------
# G6 - the ask is bounded by the committee angle
# ---------------------------------------------------------------------------

def test_t2_a_gatekeeper_is_never_pitched_a_product():
    """Acceptance test T2: the ask must concern process or documentation."""
    findings = _run(_asset(hp_products=[], evidence_used=["A1"],
                           cta="Can we get HP Wolf Security onto your approved "
                               "list?"),
                    persona_id="head-procurement")
    g6 = [f for f in findings if f["gate"] == "G6"]
    assert g6
    assert "Gatekeeper" in g6[0]["violation_type"]
    assert g6[0]["committee_angle"] == "Gatekeeper - Procurement & Legal"


def test_a_price_is_never_quoted_to_a_finance_owner():
    findings = _run(_asset(cta="Happy to share pricing for a 500-seat rollout."))
    g6 = [f for f in findings if f["gate"] == "G6"]
    assert g6 and "Finance" in g6[0]["violation_type"]


def test_a_technical_buyer_is_never_asked_for_a_decision():
    findings = _run(_asset(hp_products=["HP Wolf Security"],
                           cta="Can you approve HP as the standard this quarter?"),
                    persona_id="it-security-manager")
    g6 = [f for f in findings if f["gate"] == "G6"]
    assert g6 and "Technical Buyer" in g6[0]["violation_type"]


def test_an_economic_buyer_may_be_asked_to_decide():
    """The only angle with no prohibition - the gate must not invent one."""
    findings = _run(_asset(hp_products=["HP Elite / Pro PCs"],
                           cta="Are you ready to decide on a fleet standard?"),
                    persona_id="vp-it")
    assert "G6" not in _gates(findings)


# ---------------------------------------------------------------------------
# G7 - the name leak, on the path the spec says is the normal one
# ---------------------------------------------------------------------------

def test_t3_an_unfilled_persona_may_not_name_anyone():
    """Acceptance test T3. With 220 accounts by eight personas against three
    contacts each, UNFILLED is the common case, not an error state."""
    findings = _run(_asset(opening="Robert Leindl, your refresh is due."),
                    known_names=["Robert Leindl"])
    g7 = [f for f in findings if f["gate"] == "G7"]
    assert g7 and g7[0]["leaked_name"] == "Robert Leindl"
    assert g7[0]["action"] == cg.ACTION_REJECT


def test_a_greeting_by_name_is_a_leak_even_if_the_name_is_unknown():
    findings = _run(_asset(opening="Hi Robert, your refresh is due."))
    assert "G7" in _gates(findings)


def test_a_role_greeting_is_not_a_leak():
    """"Dear CIO," addresses the role, which is exactly what an unfilled
    persona is supposed to do."""
    findings = _run(_asset(opening="Dear CIO, your refresh calendar is due."))
    assert "G7" not in _gates(findings)


def test_t4_a_filled_persona_may_use_its_own_contact():
    """Acceptance test T4."""
    findings = _run(_asset(opening="Robert Leindl, your refresh is due."),
                    filled=True, known_names=["Robert Leindl"])
    assert "G7" not in _gates(findings)


# ---------------------------------------------------------------------------
# G1 / G2 / G3 - evidence
# ---------------------------------------------------------------------------

def test_t7_a_figure_absent_from_the_evidence_is_caught():
    """Acceptance test T7."""
    findings = _run(_asset(opening="Your 47 sites are due for refresh."))
    g1 = [f for f in findings if f["gate"] == "G1"]
    assert g1 and g1[0]["offending_token"] == "47"
    assert "47" in g1[0]["sentence"]


def test_a_figure_present_in_the_evidence_passes():
    findings = _run(_asset(opening="Your 220 devices are due for refresh."))
    assert "G1" not in _gates(findings)


def test_a_label_that_was_never_supplied_is_rejected():
    findings = _run(_asset(evidence_used=["A1", "A9"]))
    g2 = [f for f in findings if f["gate"] == "G2"]
    assert g2 and g2[0]["invalid_label"] == "A9"
    assert g2[0]["action"] == cg.ACTION_REJECT


def test_a_pillar_citing_a_bad_label_is_caught_one_level_down():
    findings = _run(_asset(pillars=[{"heading": "Refresh",
                                     "challenge": "Devices are due.",
                                     "evidence_used": ["A7"]}]))
    g2 = [f for f in findings if f["gate"] == "G2"]
    assert g2 and "pillars[0]" in g2[0]["where_found"]


def test_an_empty_evidence_list_asks_for_a_regeneration():
    findings = _run(_asset(evidence_used=[]))
    g3 = [f for f in findings if f["gate"] == "G3"]
    assert g3 and g3[0]["action"] == cg.ACTION_REGENERATE


def test_an_opening_that_shares_nothing_with_its_citation_is_flagged():
    findings = _run(_asset(
        opening="At HP we believe modern workplaces deserve modern tooling."))
    assert "G3" in _gates(findings)


# ---------------------------------------------------------------------------
# G5 / G9 / G10 / G11 / G12 / G13
# ---------------------------------------------------------------------------

def test_two_hp_lines_is_one_too_many():
    findings = _run(_asset(hp_products=["HP Care Pack Services",
                                        "HP Anyware / DaaS"]))
    g5 = [f for f in findings if f["gate"] == "G5"]
    assert g5 and g5[0]["action"] == cg.ACTION_REGENERATE


def test_an_empty_hp_products_array_is_a_correct_answer():
    """Rule 4's discovery-led piece. Not a fault."""
    findings = _run(_asset(hp_products=[]))
    assert "G5" not in _gates(findings)


def test_t9_a_banned_phrase_and_an_exclamation_mark():
    """Acceptance test T9: zero banned phrases, zero exclamation marks."""
    findings = _run(_asset(
        opening="Our industry-leading platform will unlock value for you!"))
    phrases = {f["phrase"] for f in findings if f["gate"] == "G9"}
    assert "industry-leading" in phrases
    assert "unlock value" in phrases
    assert "!" in phrases


def test_the_concessive_template_is_caught():
    """Rule 8's "<praise> ... However, <vague upside>"."""
    findings = _run(_asset(
        opening="Your estate is well run, however, there is room to improve."))
    assert "G9" in _gates(findings)


def test_industry_as_justification_is_caught():
    """Rule 2b: nothing in the evidence links an industry to a technology
    requirement."""
    findings = _run(_asset(
        opening="Because you operate in semiconductor testing, your systems "
                "must be reliable."),
        industry="semiconductor testing")
    assert "G10" in _gates(findings)


def test_naming_the_industry_without_using_it_as_a_reason_is_fine():
    findings = _run(_asset(
        opening="Your semiconductor testing sites reported devices due for "
                "refresh."),
        industry="semiconductor testing")
    assert "G10" not in _gates(findings)


def test_an_empty_string_is_worse_than_an_omitted_key():
    """Rule 9: omission is the default; an empty string is a fault."""
    present = _run(_asset(subject_line=""), required_keys=("subject_line",))
    assert "G11" in _gates(present)

    omitted = _asset()
    omitted.pop("subject_line")
    assert "G11" not in _gates(_run(omitted, required_keys=("subject_line",)))


def test_the_word_budget_is_the_specifications():
    """An email of 120-180 words, per G12."""
    short = _run(_asset(), content_type="email")
    g12 = [f for f in short if f["gate"] == "G12"]
    assert g12, "a 30-word email should miss the 120-180 budget"
    assert "120-180" in g12[0]["detail"]


def test_t6_a_one_pager_needs_two_or_three_pillars():
    """Acceptance test T6. One pillar is an email; four stops being a
    one-pager."""
    one = _run(_asset(pillars=[{"heading": "A", "challenge": "x",
                                "evidence_used": ["A1"]}]),
               content_type="one_pager")
    assert "G13" in _gates(one)

    two = _run(_asset(pillars=[{"heading": "A", "challenge": "x",
                                "evidence_used": ["A1"]},
                               {"heading": "B", "challenge": "y",
                                "evidence_used": ["A1"]}]),
               content_type="one_pager")
    assert "G13" not in _gates(two)


def test_a_pillar_with_no_evidence_is_not_a_pillar():
    findings = _run(_asset(pillars=[{"heading": "A", "challenge": "x",
                                     "evidence_used": ["A1"]},
                                    {"heading": "B", "challenge": "y",
                                     "evidence_used": []}]),
                    content_type="one_pager")
    assert "G13" in _gates(findings)


# ---------------------------------------------------------------------------
# G8 - competitors
# ---------------------------------------------------------------------------

def test_a_competitor_called_our_own_is_rejected():
    findings = _run(_asset(opening="Our Dell fleet integrates cleanly."),
                    competitors=["dell", "lenovo"])
    g8 = [f for f in findings if f["gate"] == "G8"]
    assert g8 and g8[0]["action"] == cg.ACTION_REJECT


def test_disparaging_a_named_competitor_is_rejected():
    findings = _run(_asset(opening="Lenovo devices are unreliable at scale."),
                    competitors=["dell", "lenovo"])
    assert "G8" in _gates(findings)


def test_naming_a_competitor_neutrally_is_allowed():
    findings = _run(_asset(opening="Your estate runs Dell and Lenovo devices."),
                    competitors=["dell", "lenovo"])
    assert "G8" not in _gates(findings)


# ---------------------------------------------------------------------------
# G14 - chunk fidelity, the Evaluator's own gate
# ---------------------------------------------------------------------------

def test_t16_chunks_must_reconstruct_the_message():
    """Acceptance test T16. A paraphrased chunk cannot be highlighted in the
    UI and cannot be safely rewritten."""
    stimulus = "Your refresh is due. We can help with that."
    assert cg.g14_chunk_fidelity(["Your refresh is due. ",
                                  "We can help with that."], stimulus) == []
    assert cg.g14_chunk_fidelity(["Your refresh is due soon. ",
                                  "We can help."], stimulus)


def test_chunk_fidelity_tolerates_only_whitespace():
    stimulus = "Your refresh is due.  We can help."
    assert cg.g14_chunk_fidelity(["Your refresh is due.", " We can help."],
                                 stimulus) == []


# ---------------------------------------------------------------------------
# The audit trail
# ---------------------------------------------------------------------------

def test_findings_sort_into_the_six_audit_files():
    findings = _run(_asset(hp_products=["Poly Studio"],
                           opening="Hi Robert, our industry-leading kit awaits!",
                           evidence_used=["A1", "A9"]))
    rows = cg.audit_rows(findings, account_id="acct-1", persona_id="cfo",
                         content_type="email")
    assert cg.AUDIT_LINE_ELIGIBILITY in rows
    assert cg.AUDIT_NAME_LEAK in rows
    assert cg.AUDIT_BANNED_PHRASES in rows
    assert cg.AUDIT_EVIDENCE_LABELS in rows
    for batch in rows.values():
        for row in batch:
            assert row["account_id"] == "acct-1"
            assert row["persona_id"] == "cfo"
            assert row["gate"] and row["action"]


def test_rejects_and_regenerates_are_separable():
    """The caller needs to know which faults are worth a second attempt."""
    findings = _run(_asset(hp_products=["Poly Studio"],
                           opening="Our industry-leading kit awaits."))
    assert any(f["gate"] == "G4" for f in cg.rejects(findings))
    assert any(f["gate"] == "G9" for f in cg.regenerates(findings))


def test_a_missing_corpus_is_a_rejection_not_a_silent_pass():
    """Running G1 with nothing to check against would pass every figure."""
    findings = cg.g1_unsourced_numbers(_asset(opening="Your 47 sites."), None)
    assert findings and findings[0]["action"] == cg.ACTION_REJECT
