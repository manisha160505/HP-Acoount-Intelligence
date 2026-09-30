"""Step F - one evaluation, start to finish.

The order matters and is the whole design:

    resolve persona (inside this account)     - refuses a persona from elsewhere
    build the four sources                     - Step D
    run the coded structure checks             - survive an AI failure
    ask the model for dimensions/phrases/reaction
    validate dimensions, retry once, composite in Python - Step C
    locate every phrase, guard the reaction    - Step E
    store

Everything the model returns passes through Python before it reaches a seller.
The model supplies dimension numbers and prose; it never decides the composite,
never decides where a phrase sits, and never gets to assert something about the
real contact.

When the model fails entirely the evaluation still publishes: the deterministic
structure checks are real results and do not depend on it. What is withheld in
that case is every dimension score and the composite, marked unavailable rather
than estimated.
"""

import logging
import re
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.services.evaluator import formats as F, scoring as S, sources as SRC, storage, verify
from app.services.extractors.grounding import corpus_from_texts
from app.services.hp import buyer_personas as bp, content_gates

logger = logging.getLogger(__name__)

PROMPT_VERSION = 4

MODE_LITE = "LITE"
MODE_DEEP = "DEEP"
MODES = (MODE_LITE, MODE_DEEP)

# LITE is a cheaper pass, not a different rubric: same formula, same dimensions,
# fewer phrase chunks and no simulated reaction.
#
# Spec Section 4.2 states DEEP as a RANGE - 10-15 chunks - where this was a
# ceiling of 12 with no floor, so a DEEP pass that returned three chunks was a
# DEEP pass. The floor is recorded rather than enforced: a two-sentence message
# cannot be cut into ten spans, and failing it for being short would be a worse
# answer than saying so.
LITE_MAX_CHUNKS = 5
DEEP_MIN_CHUNKS = 10
DEEP_MAX_CHUNKS = 15

# Spec Section 4.5, the two severe-failure rules. A denied HP line drives
# Relevance below 40; an out-of-angle ask drives CTA below 40. "Below 40" is
# taken as 39: at 40 the band is still Average, and the point of the rule is
# that the seller sees the message is not merely mediocre.
SEVERE_FLOOR = 39.0


class EvaluationError(Exception):
    """The request cannot be evaluated as submitted."""


SYSTEM_PROMPT = """You evaluate a B2B sales message for an HP seller.

You are scoring a DRAFT. The draft is not evidence: a claim is not true because
the seller wrote it. If the draft asserts something the supplied context does
not support, that is a finding, not a fact you may repeat.

You return dimension scores and prose. You do NOT compute the composite score -
that is calculated from your dimensions by a fixed formula you never see the
result of, so do not report, guess or mention an overall score.

RULES THAT ARE CHECKED IN CODE AFTER YOU ANSWER:
1. Every phrase you return must be quoted EXACTLY from the message, character
   for character. A phrase that cannot be found in the message is discarded.
2. The simulated reaction is written about a ROLE, never the individual. Do not
   use the contact's name. Do not write what the person thinks, believes, wants,
   feels, has decided or has said. Do not include a quotation. Write "someone in
   this role would ..." - never "<name> would ...".
3. Do not introduce a number, percentage, statistic or URL that is not in the
   supplied context. Anything you invent is stripped.
4. Do not claim an HP capability that is not in the approved HP facts below.

Score every dimension from 0 to 100. Return all of them; a missing dimension
invalidates the whole evaluation."""


def _dimension_block(objective):
    """All seven, always, each with a reason. Spec Section 4.10.

    The objective is not consulted. It decides the composite weights, which the
    model never sees - it is told it will not see the result, so telling it
    which dimensions carry weight would only invite it to optimise the ones
    that count.

    The array shape is the specification's. `scoring.split_dimension_payload`
    also reads the object shape this build used to ask for, so an evaluation
    stored under the old contract still loads.
    """
    del objective
    lines = ['    {"dimension": "%s", "score": <0-100>, "rationale": "<one sentence: '
             'what in the message earned this score>"}' % S.SPEC_DIMENSION_NAMES[dim]
             for dim in S.required_dimensions()]
    return "[\n" + ",\n".join(lines) + "\n  ]"


def _rubric_block():
    """Spec Section 4.5's rubric, so a 70 means the same thing to the model as
    it does to the band printed under the seller's score."""
    return "SCORING RUBRIC: " + " | ".join(
        "%d-%d %s" % (floor, ceiling, label)
        for (floor, label), ceiling in zip(
            S.SCORE_BANDS,
            [100] + [f - 1 for f, _ in S.SCORE_BANDS[:-1]], strict=True))


def _lines_block(card):
    """The eligibility matrix, in the words Section 4.10 uses.

    Python enforces this after the answer - see `_severe_failures` - so nothing
    here decides a score. What it decides is whether the summary and the
    persona reaction make sense next to the score, which is the part a seller
    reads.
    """
    if not card:
        return ""
    persona_id = card["persona_id"]
    return "\n".join([
        "HP LINES THIS PERSONA MAY BE OFFERED: %s"
        % ", ".join(bp.allowed_lines(persona_id)),
        "HP LINES THAT ARE WRONG FOR THIS PERSONA: %s"
        % ", ".join(bp.denied_lines(persona_id)),
        "If the message names a line from the second list, Relevance must score below 40 "
        "and the summary must say so explicitly. Pitching the wrong line to this role is "
        "the most damaging error in the message, whatever else it does well.",
    ])


def _card_for(persona, mode):
    """The hardcoded persona card, or None for a persona outside the eight.

    A stored evaluation can be replayed under an id from before the audience
    narrowed, and a rewrite resolves its persona again. None is the honest
    answer there - the severe-failure rules and the card simply do not apply -
    rather than raising on a request that used to work.
    """
    try:
        return bp.evaluator_card(str(persona.get("persona_id") or ""),
                                 deep=mode == MODE_DEEP)
    except bp.UnknownPersona:
        return None


def _card_block(card):
    """What the critic is given about the buyer. Spec Section 4.3.

    This is the asymmetry with Content Studio and it is deliberate: the
    generator is NOT shown the goals, pain points, value drivers or decision
    criteria, because a writer given a persona's pain points writes them back to
    the persona as though they were account facts. A critic needs exactly those
    things - they are what "relevant to this buyer" means.
    """
    if not card:
        return ""
    out = ["THE BUYER (a persona reference, not account intelligence - it is the "
           "same on every account):",
           "- Role: %s, %s" % (card["title"], card["department"]),
           "- Buying-committee angle: %s" % card["committee_angle"],
           "- What this role owns: %s" % card["remit"],
           "- Goals: %s" % "; ".join(card["goals"]),
           "- Pain points: %s" % "; ".join(card["pain_points"]),
           "- Value drivers: %s" % "; ".join(card["value_drivers"]),
           "- They decide by asking: %s" % "; ".join(card["decision_criteria"]),
           "- Measured on: %s" % ", ".join(card["content_preferences"]["key_metrics"]),
           "- Preferred tone: %s" % card["content_preferences"]["tone"],
           "- What does NOT land with them: %s" % "; ".join(card["does_not_resonate"]),
           "- Objections they raise: %s" % "; ".join(card["typical_objections"]),
           "- What HP can and cannot address here: %s" % card["hp_opportunity"]]
    state = card.get("behavioural_state")
    if state:
        # DEEP only. Section 4.9 is explicit that the entry state is a
        # hypothesis rather than observed behaviour, and that the value of
        # saying it out loud is that it becomes adjustable instead of buried in
        # tone - so the prompt says so too.
        out += ["",
                "ASSUMED ENTRY STATE (a default, not something observed about this "
                "reader - judge the message against it, do not assert it):",
                "- State: %s (trust %.1f, %s bias)"
                % (state["name"], state["trust_level"], state["response_bias"]),
                "- What works from this state: %s" % state["messaging_approach"],
                "- What would move them forward: %s" % state["fast_track_trigger"],
                "- What holds them back: %s" % state["key_blocker"]]
    return "\n".join(out)


def _ask_sentence(text):
    """The message's ask: its closing question, or its last sentence.

    A generated asset has an `ask` field. A pasted message does not, so the ask
    has to be located - and the committee-angle rule is about the ask
    specifically, not about the whole message. A question is the ask when there
    is one; otherwise the last sentence is, because that is where a message puts
    what it wants.
    """
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "")) if p.strip()]
    if not parts:
        return ""
    questions = [p for p in parts if p.endswith("?")]
    return questions[-1] if questions else parts[-1]


def _severe_failures(text, persona_id):
    """Spec Section 4.5's two severe-failure rules, decided in Python.

    Not asked of the model. A denied HP line and an out-of-angle ask are exactly
    the two judgements the rest of this build refuses to leave to a model, and
    leaving them here would mean a stimulus pitching a video bar to a CFO could
    score 80 on Relevance because it was well written.

    The findings come from the same two gates Content Studio is held to, so a
    draft that would have been rejected at generation is marked down here for
    the same reason and in the same words.
    """
    view = {"opening": str(text or ""), "cta": _ask_sentence(text)}
    out = []
    for finding in content_gates.g4_line_eligibility(view, persona_id):
        out.append({
            "dimension": S.RELEVANCE, "gate": "G4",
            "detail": "%s is a line this persona is never offered (found in %s)"
                      % (finding["denied_line_named"], finding["where_found"]),
            "quote": finding.get("sentence") or "",
        })
    for finding in content_gates.g6_ask_bound(view, persona_id):
        out.append({
            "dimension": S.NEXT_STEP, "gate": "G6",
            "detail": "the ask is outside this persona's committee angle (%s): %s"
                      % (finding["committee_angle"], finding["violation_type"]),
            "quote": finding.get("ask_text") or "",
        })
    return out


def _persona_block(persona):
    """Only what the persona context may establish - role facts."""
    lines = []
    title = persona.get("title")
    if title:
        lines.append("- Role: %s" % title)
    for key, label in (("department", "Department"),
                       ("normalized_department", "Department (normalised)"),
                       ("seniority_band", "Seniority"),
                       ("influence_type", "Influence")):
        if persona.get(key):
            lines.append("- %s: %s" % (label, persona[key]))
    if persona.get("is_named_person"):
        lines.append("- This is a real named individual at the account. You may "
                     "use their ROLE. You may not use their name, and you may "
                     "not state what they think or want.")
    else:
        lines.append("- This is a ROLE TYPE, not a person. %s"
                     % (persona.get("evidence_note") or ""))
    return "\n".join(lines)


def _rewrite_persona_block(persona):
    """The same role facts, minus the no-name rule.

    That rule exists to stop the simulated reaction speaking for a real person.
    A rewrite is the message being sent TO them, and there the instruction
    backfired: the model addressed the job title instead - "As the Head of
    Governance & Strategy in Risk Advisory, your role is pivotal". The
    salutation is composed in Python, so the model still never receives the
    contact's name; it is simply no longer told to avoid something it was never
    given.
    """
    lines = [line for line in _persona_block(persona).split("\n")
             if "You may not use their name" not in line]
    lines.append("- Write TO this person. The salutation and any sign-off are "
                 "added automatically - do not write one.")
    return "\n".join(lines)


def _context_block(sources, limit=18):
    account = [c for c in sources.account.cells if c][:limit]
    hp = [c for c in sources.hp.cells if c][:limit]
    out = ["ACCOUNT CONTEXT (facts about the account; says nothing about HP):"]
    out += ["  - %s" % str(c)[:240] for c in account] or ["  (none available)"]
    out.append("")
    out.append("APPROVED HP FACTS (HP capability only; says nothing about the account):")
    out += ["  - %s" % str(c)[:240] for c in hp] or ["  (none available)"]
    if sources.superlatives_blocked or sources.competitor_claims_blocked:
        out.append("")
        out.append("MARKET RESTRICTIONS for %s:" % (sources.country or "").title())
        if sources.superlatives_blocked:
            out.append("  - Superlative claims are not permitted. Flag any in the draft.")
        if sources.competitor_claims_blocked:
            out.append("  - Competitor comparison claims are not permitted. Flag any "
                       "naming of a competitor.")
    return "\n".join(out)


def _user_prompt(message, persona, objective, fmt, mode, sources, checks,  # noqa: PLR0913, PLR0917 - one argument per prompt section; a context object would hide what the prompt is built from
                 card=None, severe=()):
    spec = F.FORMATS[fmt]
    want_reaction = mode == MODE_DEEP

    failed = [c for c in checks["checks"] if not c["passed"]]
    coded = "\n".join("  - %s: %s" % (c["check"], c["detail"]) for c in failed) \
        or "  (all coded checks passed)"

    parts = [
        "OBJECTIVE (funnel stage): %s" % objective.capitalize(),
        "FORMAT: %s" % spec["label"],
        "FORMAT CRITERIA: %s" % spec["criteria"],
        "",
        "TARGET PERSONA:",
        _persona_block(persona),
        "",
        _card_block(card),
        "",
        _lines_block(card),
        "",
        _context_block(sources),
        "",
        "CODED CHECKS ALREADY RUN (do not repeat these, build on them):",
        coded,
        "",
        _severe_block(severe),
        "",
        "THE MESSAGE TO EVALUATE (verbatim, between the markers):",
        "<<<MESSAGE",
        str(message),
        "MESSAGE>>>",
        "",
        _rubric_block(),
        "",
        "Return JSON exactly in this shape:",
        "{",
        '  "dimensions": %s,' % _dimension_block(objective),
        '  "phrases": [',
        '    {"chunk": "<EXACT quotation from the message>",',
        '     "verdict": "Keep" | "Improve" | "Change",',
        '     "comment": "<why, one sentence>",',
        '     "suggestion": "<a concrete replacement, or empty>"}',
        "  ],   // %s" % _chunk_instruction(mode),
        '  "summary": "<3-4 sentences: what works, what to fix first>",',
        '  "strengths": ["<short>", "..."],',
        '  "weaknesses": ["<short>", "..."]',
    ]
    if want_reaction:
        parts.append(',  "reaction": "<2-4 sentences: how someone in this ROLE would '
                     'likely read this. Never the contact\'s name. Never what they '
                     'think, want or said.>"')
    parts.append("}")
    return "\n".join(parts)


def _chunk_instruction(mode):
    """What the model is told about chunking. Spec Section 4.6.

    The instruction that matters is not the count: it is that the chunks must
    TILE the message. Asked only for "at most N", a model returns the N spans it
    has something to say about and leaves the rest uncovered - which reads in
    the UI as text nobody objected to, and leaves Step R unable to touch it.
    """
    span = ("exactly %d chunks" % LITE_MAX_CHUNKS if mode == MODE_LITE
            else "between %d and %d chunks" % (DEEP_MIN_CHUNKS, DEEP_MAX_CHUNKS))
    return (span + ", in the order they appear. Together they must cover the WHOLE "
            "message with no gaps and no overlap - every sentence belongs to exactly "
            "one chunk, including the ones you would keep unchanged. This is checked "
            "in code.")


def _severe_block(severe):
    """Findings Python has already made, which the prose has to agree with.

    The scores for these are set in code afterwards whatever the model says, so
    the only thing at stake here is whether the summary explains a number the
    seller can see. A summary that praises the relevance of a message Python
    just floored to 39 is worse than no summary.
    """
    if not severe:
        return ""
    lines = ["SEVERE FAILURES ALREADY FOUND IN CODE. These are decided; do not "
             "dispute them. Score the dimension named at or below 39 and say why "
             "in the summary, naming the mismatch explicitly:"]
    lines += ["  - %s: %s" % (S.DIMENSION_LABELS[f["dimension"]], f["detail"])
              for f in severe]
    return "\n".join(lines)


def _ask(system, user):
    try:
        return generate_gpt4o_json_completion(system, user) or {}
    except Exception:
        logger.exception("evaluator: model call failed")
        return {}


def evaluate_message(account_id, persona_id, objective, fmt, message,
                     mode=MODE_DEEP, dataset_records=None):
    """Evaluate one draft. Returns the stored evaluation document."""
    from app.database.mongodb import get_db

    text = str(message or "").strip()
    if not text:
        raise EvaluationError("the message is empty")

    objective = S.normalize_objective(objective)
    # The narrow reader: only the three formats the seller can pick. A stored
    # evaluation under an older format still reads back through
    # `normalize_format`, but nothing new is scored against a rubric the
    # dropdown does not offer.
    fmt = F.normalize_offered_format(fmt)
    mode = (mode or MODE_DEEP).upper()
    if mode not in MODES:
        raise EvaluationError("unknown mode %r - expected LITE or DEEP" % mode)

    db = get_db()

    # Isolation first: a persona from another account is refused outright, not
    # quietly treated as missing context.
    persona = storage.resolve_persona(account_id, persona_id)
    if persona is None:
        raise EvaluationError(
            "persona %r does not belong to this account" % persona_id)

    fingerprint = storage.message_fingerprint(text, persona_id, objective, fmt, mode)
    cached = storage.find_existing(account_id, fingerprint)
    if cached:
        logger.info("evaluator: returning stored evaluation for %s", fingerprint[:12])
        return cached

    sources = SRC.build(db, account_id, persona, text, dataset_records)
    checks = F.structure_checks(text, fmt)

    # The card and the two severe-failure findings are both decided before any
    # model call: one is a constant, the other is Python reading the stimulus.
    card = _card_for(persona, mode)
    severe = _severe_failures(text, card["persona_id"]) if card else []

    audit = []
    prompt = _user_prompt(text, persona, objective, fmt, mode, sources, checks,
                          card=card, severe=severe)
    raw = _ask(SYSTEM_PROMPT, prompt)
    scores, rationales = S.split_dimension_payload(raw.get("dimensions"))
    dimensions, problems = S.validate_dimensions(scores, objective)

    # One correction round trip, with the problems named. The original response
    # is kept whatever happens next.
    if problems:
        audit.append({"stage": "dimensions", "problems": problems,
                      "raw": raw.get("dimensions")})
        logger.warning("evaluator: dimension problems, retrying once: %s", problems)
        retry = _ask(SYSTEM_PROMPT,
                     prompt
                     + "\n\nYour previous answer was rejected:\n"
                     + "\n".join("  - %s" % p for p in problems)
                     + "\nReturn every dimension as a number from 0 to 100.")
        if retry:
            retry_scores, retry_rationales = S.split_dimension_payload(
                retry.get("dimensions"))
            dimensions, problems = S.validate_dimensions(retry_scores, objective)
            if not problems:
                raw, rationales = retry, retry_rationales
            else:
                audit.append({"stage": "dimensions_retry", "problems": problems,
                              "raw": retry.get("dimensions")})

    # T21: a dimension still missing after the round trip is padded to 50 and
    # the pad is recorded, so the request succeeds and the seller can still see
    # which number was not the model's. Only a MISSING dimension is padded - a
    # dimension the model returned as "excellent" or as 400 is a different
    # failure and stays a problem.
    padded = []
    if problems and raw:
        dimensions, padded, problems = S.pad_missing(dimensions, problems)
        if padded:
            logger.warning("evaluator: padded %s to %g for account %s",
                           ", ".join(padded), S.PAD_SCORE, account_id)
            audit.append({"stage": "dimensions_padded", "padded": padded,
                          "pad_score": S.PAD_SCORE})

    # Spec Section 4.5: a denied HP line floors Relevance, an out-of-angle ask
    # floors CTA. Applied after the model, so no wording can talk its way past
    # it, and only ever downwards - a model that already scored it 20 keeps 20.
    for failure in severe:
        dimension = failure["dimension"]
        current = dimensions.get(dimension)
        if current is not None and current > SEVERE_FLOOR:
            failure["model_score"] = current
            dimensions[dimension] = SEVERE_FLOOR

    # No partial-weight fallback: either every required dimension is valid or no
    # composite publishes.
    composite = None
    if not problems:
        try:
            composite = S.composite(dimensions, objective)
        except S.ScoringError as exc:
            audit.append({"stage": "composite", "problems": [str(exc)]})

    max_chunks = LITE_MAX_CHUNKS if mode == MODE_LITE else DEEP_MAX_CHUNKS
    phrases, dropped = verify.verify_phrases(raw.get("phrases"), sources, max_chunks)

    # G14, spec Section 4.6: "if the concatenated chunks do not match the
    # stimulus, reject and retry once."
    fidelity = verify.chunk_fidelity(phrases, text) if raw else []
    if fidelity:
        audit.append({"stage": "chunks", "problems": fidelity})
        logger.warning("evaluator: chunk fidelity failed, retrying once: %s", fidelity)
        retry = _ask(SYSTEM_PROMPT, prompt
                     + "\n\nYour previous phrase chunks were rejected:\n"
                     + "\n".join("  - %s" % f for f in fidelity)
                     + "\nReturn chunks that tile the whole message end to end.")
        if retry:
            retry_phrases, retry_dropped = verify.verify_phrases(
                retry.get("phrases"), sources, max_chunks)
            retry_fidelity = verify.chunk_fidelity(retry_phrases, text)
            if not retry_fidelity:
                phrases, dropped, fidelity = retry_phrases, retry_dropped, []
            else:
                audit.append({"stage": "chunks_retry", "problems": retry_fidelity})
    if dropped:
        audit.append({"stage": "phrases", "dropped": dropped})
    if mode == MODE_DEEP and phrases and len(phrases) < DEEP_MIN_CHUNKS:
        # Recorded, not failed: a short message cannot be cut into ten spans.
        audit.append({"stage": "chunks", "problems": [
            "DEEP returned %d chunks; the range is %d-%d"
            % (len(phrases), DEEP_MIN_CHUNKS, DEEP_MAX_CHUNKS)]})

    reaction, reaction_faults = (None, [])
    if mode == MODE_DEEP:
        reaction, reaction_faults = verify.guard_reaction(raw.get("reaction"), sources)
        if reaction_faults:
            audit.append({"stage": "reaction", "withheld": reaction_faults})

    ai_failed = not raw
    evaluation = {
        "account_id": account_id,
        "persona_contact_id": persona_id,
        "version": storage.next_version(account_id, persona_id),
        "fingerprint": fingerprint,
        "prompt_version": PROMPT_VERSION,
        "objective": objective,
        "objective_label": S.OBJECTIVE_LABELS[objective],
        "format": fmt,
        "format_label": F.FORMATS[fmt]["label"],
        "mode": mode,
        "message_text": text,
        "persona": {k: persona.get(k) for k in
                    ("persona_id", "name", "title", "department", "seniority_band",
                     "influence_type", "is_named_person")},
        "dimensions": dimensions if not problems else {},
        "dimension_problems": problems,
        "dimensions_padded": padded,
        # Spec Section 4.10 and the tuning row: "Each scored 0-100 with a
        # rationale." A dimension the model scored but did not explain simply
        # has no entry - an invented reason would be worse than none.
        "dimension_rationales": {d: r for d, r in rationales.items()
                                 if d in dimensions},
        # Spec Section 4.5: "A dimension weighted 0 is still scored and
        # displayed - the seller sees all seven - but contributes nothing to
        # the composite. Show the formula under the composite so the number is
        # inspectable." The formula string alone cannot tell the UI WHICH of
        # the seven bars carries no weight, so the weights travel with it.
        "dimension_weights": {d: S.weight_of(objective, d)
                              for d in S.ALL_DIMENSIONS},
        "composite": composite,
        "composite_available": composite is not None,
        "score_band": S.score_band(composite),
        "formula_used": S.formula_expression(objective),
        "formula_source": S.formula_source(objective),
        "structure_checks": checks,
        "persona_card": card,
        "persona_card_source": (card or {}).get("card_source"),
        "severe_failures": severe,
        "phrases": phrases,
        "phrases_dropped": len(dropped),
        "chunk_fidelity_faults": fidelity,
        "reaction": reaction,
        "reaction_withheld": reaction_faults,
        "summary": verify._text(raw.get("summary")),
        "strengths": [verify._text(s) for s in (raw.get("strengths") or []) if verify._text(s)],
        "weaknesses": [verify._text(s) for s in (raw.get("weaknesses") or []) if verify._text(s)],
        "data_sources": sources.as_panel(),
        "ai_available": not ai_failed,
        "audit_log": audit,
        "rewrite": None,
    }

    # T17 and T18 require the summary to name the mismatch. The model was told
    # to, and the prompt is not a guarantee - so Python puts it at the front,
    # where the seller reads first and where it explains the floored number
    # beside it.
    if severe:
        lead = " ".join("%s scored down: %s." % (S.DIMENSION_LABELS[f["dimension"]],
                                                 f["detail"])
                        for f in severe)
        evaluation["summary"] = (lead + " " + (evaluation["summary"] or "")).strip()

    if ai_failed:
        # The coded checks are still a real result and still publish.
        evaluation["summary"] = ("AI scoring was unavailable. The checks below are "
                                 "computed in code and are unaffected.")
        logger.warning("evaluator: publishing coded checks only for account %s", account_id)

    return storage.save(evaluation)


# ---------------------------------------------------------------------------
# Rewrite - a separate call, made only when the seller selects recommendations
# ---------------------------------------------------------------------------

REWRITE_SYSTEM = """You rewrite a B2B sales message applying ONLY the changes the
seller selected. Everything else stays as the seller wrote it.

You may not introduce any number, percentage, statistic, URL or HP capability
claim that is not in the supplied context. A claim the original made without
support must NOT be carried over as though it were verified - drop it or soften
it to what the context supports.

Return a single JSON object in the exact structured shape requested. Do not
return a single block of prose, and do not wrap the JSON in markdown."""


def _rewrite_gate_faults(rewrite, card, persona, banned, sources, original, fmt):
    """The Section 6 gates, on the version the seller actually sends.

    Only the REJECT findings become faults. A regenerate-once finding - a filler
    phrase, a word budget - is not worth withholding a rewrite the seller asked
    for and can edit; a denied HP line, a leaked name on an unfilled role or an
    invented figure is.

    Returns [] for a persona outside the eight: there is no eligibility row to
    check against, and inventing one would be worse than checking nothing.
    """
    if not rewrite or not card:
        return []
    asset = {
        "headline": rewrite.get("headline") or "",
        "subject_line": rewrite.get("subject_line") or "",
        "opening": rewrite.get("opening") or "",
        "body_sections": rewrite.get("body_sections") or [],
        "cta": rewrite.get("cta") or "",
        "hp_products": rewrite.get("hp_products") or [],
        # The gates read `evidence_used` for G2 and G3, and a rewrite has no
        # evidence labels - it is not generated from a labelled block. Those two
        # gates are not applicable here, so nothing is passed and neither the
        # empty-citation finding nor a coverage finding is raised as a fault
        # below: only rejects are, and G3's action is regenerate.
    }
    # G1 needs a corpus and refuses to run without one - passing None makes it
    # reject everything, which is the right default for a generator and the
    # wrong one here. The corpus is this account's sources PLUS the seller's own
    # original: a figure the seller already wrote is not something the rewrite
    # invented, and whether it was ever supported is `diff_rewrite`'s question,
    # asked against the original a few lines later and asked more strictly.
    corpus = corpus_from_texts([*sources.account.cells, *sources.hp.cells,
                                str(original or "")])
    findings = content_gates.run(
        asset, persona_id=card["persona_id"], content_type=fmt,
        filled=bool(persona.get("is_named_person")), corpus=corpus,
        supplied_labels=(), label_texts={}, known_names=banned,
        competitors=(), industry="", required_keys=())
    return ["%s: %s" % (f["gate"], f.get("detail") or f.get("denied_line_named")
                        or f.get("leaked_name") or f["gate"])
            for f in content_gates.rejects(findings)]


def rewrite_message(account_id, fingerprint, selected_recommendations,
                    dataset_records=None):
    """Rewrite a stored evaluation's message, applying the selected changes."""
    from app.database.mongodb import get_db

    db = get_db()
    evaluation = storage.find_existing(account_id, fingerprint)
    if not evaluation:
        raise EvaluationError("no evaluation found for this account and message")

    fmt = evaluation["format"]
    original = evaluation["message_text"]
    persona = storage.resolve_persona(account_id, evaluation["persona_contact_id"]) or {}
    sources = SRC.build(db, account_id, persona, original, dataset_records)

    selected = [str(s) for s in (selected_recommendations or []) if str(s).strip()]
    if not selected:
        raise EvaluationError("select at least one recommendation to apply")

    prompt = "\n".join([
        "OBJECTIVE: %s" % evaluation["objective_label"],
        "FORMAT: %s" % evaluation["format_label"],
        "",
        "TARGET PERSONA:",
        _rewrite_persona_block(persona),
        "",
        _context_block(sources),
        "",
        "THE ORIGINAL MESSAGE:",
        "<<<MESSAGE", original, "MESSAGE>>>",
        "",
        "APPLY ONLY THESE CHANGES:",
        "\n".join("  %d. %s" % (i, s) for i, s in enumerate(selected, 1)),
        "",
        F.rewrite_instructions(fmt, persona, original),
    ])

    card = _card_for(persona, evaluation.get("mode") or MODE_DEEP)
    raw = _ask(REWRITE_SYSTEM, prompt)
    banned = sources.contact_names()
    rewrite, faults = F.validate_rewrite(raw, fmt, banned, persona, original)
    faults += _rewrite_gate_faults(rewrite, card, persona, banned, sources, original, fmt)

    if faults:
        logger.warning("evaluator: rewrite rejected (%s), retrying once",
                       "; ".join(faults))
        retry = _ask(REWRITE_SYSTEM, prompt + "\n\nYour previous answer was rejected:\n"
                     + "\n".join("  - %s" % f for f in faults))
        rewrite, faults = F.validate_rewrite(retry, fmt, banned, persona, original)
        faults += _rewrite_gate_faults(rewrite, card, persona, banned, sources, original, fmt)
        if faults:
            rewrite = None

    if not rewrite:
        # The seller keeps their original rather than receiving a malformed one.
        db[storage.COLLECTION].update_one(
            {"account_id": account_id, "fingerprint": fingerprint},
            {"$set": {"rewrite": None,
                      "rewrite_faults": faults,
                      "rewrite_attempted_at": datetime.now(UTC)}})
        raise EvaluationError("the rewrite did not meet the %s format contract: %s"
                              % (evaluation["format_label"], "; ".join(faults)))

    diff, diff_faults = verify.diff_rewrite(original, rewrite["plain_text"],
                                            sources, selected)
    if diff_faults:
        db[storage.COLLECTION].update_one(
            {"account_id": account_id, "fingerprint": fingerprint},
            {"$set": {"rewrite": None, "rewrite_faults": diff_faults,
                      "rewrite_diff": diff,
                      "rewrite_attempted_at": datetime.now(UTC)}})
        raise EvaluationError("the rewrite introduced claims the sources do not "
                              "support: %s" % "; ".join(diff_faults))

    rewrite["diff"] = diff
    db[storage.COLLECTION].update_one(
        {"account_id": account_id, "fingerprint": fingerprint},
        {"$set": {"rewrite": rewrite, "rewrite_faults": [],
                  "rewrite_applied": selected,
                  "rewrite_attempted_at": datetime.now(UTC)}})
    return storage.find_existing(account_id, fingerprint)
