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
from datetime import datetime, timezone

from app.core.llm import generate_gpt4o_json_completion
from app.services.evaluator import formats as F
from app.services.evaluator import scoring as S
from app.services.evaluator import sources as SRC
from app.services.evaluator import storage, verify

logger = logging.getLogger(__name__)

PROMPT_VERSION = 2

MODE_LITE = "LITE"
MODE_DEEP = "DEEP"
MODES = (MODE_LITE, MODE_DEEP)

# LITE is a cheaper pass, not a different rubric: same formula, same dimensions,
# fewer phrase chunks and no simulated reaction.
LITE_MAX_CHUNKS = 5
DEEP_MAX_CHUNKS = 12


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
    needed = S.required_dimensions(objective)
    lines = []
    for dim in needed:
        lines.append('    "%s": <0-100>' % dim)
    return "{\n" + ",\n".join(lines) + "\n  }"


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


def _user_prompt(message, persona, objective, fmt, mode, sources, checks):
    spec = F.FORMATS[fmt]
    want_reaction = mode == MODE_DEEP
    max_chunks = LITE_MAX_CHUNKS if mode == MODE_LITE else DEEP_MAX_CHUNKS

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
        _context_block(sources),
        "",
        "CODED CHECKS ALREADY RUN (do not repeat these, build on them):",
        coded,
        "",
        "THE MESSAGE TO EVALUATE (verbatim, between the markers):",
        "<<<MESSAGE",
        str(message),
        "MESSAGE>>>",
        "",
        "Return JSON exactly in this shape:",
        "{",
        '  "dimensions": %s,' % _dimension_block(objective),
        '  "phrases": [',
        '    {"chunk": "<EXACT quotation from the message>",',
        '     "verdict": "Keep" | "Improve" | "Change",',
        '     "comment": "<why, one sentence>",',
        '     "suggestion": "<a concrete replacement, or empty>"}',
        "  ],   // at most %d, in the order they appear" % max_chunks,
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
    fmt = F.normalize_format(fmt)
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

    audit = []
    raw = _ask(SYSTEM_PROMPT, _user_prompt(text, persona, objective, fmt, mode,
                                           sources, checks))
    dimensions, problems = S.validate_dimensions(raw.get("dimensions") or {}, objective)

    # One correction round trip, with the problems named. The original response
    # is kept whatever happens next.
    if problems:
        audit.append({"stage": "dimensions", "problems": problems,
                      "raw": raw.get("dimensions")})
        logger.warning("evaluator: dimension problems, retrying once: %s", problems)
        retry = _ask(SYSTEM_PROMPT,
                     _user_prompt(text, persona, objective, fmt, mode, sources, checks)
                     + "\n\nYour previous answer was rejected:\n"
                     + "\n".join("  - %s" % p for p in problems)
                     + "\nReturn every dimension as a number from 0 to 100.")
        if retry:
            dimensions, problems = S.validate_dimensions(
                retry.get("dimensions") or {}, objective)
            if not problems:
                raw = retry
            else:
                audit.append({"stage": "dimensions_retry", "problems": problems,
                              "raw": retry.get("dimensions")})

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
    if dropped:
        audit.append({"stage": "phrases", "dropped": dropped})

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
        "composite": composite,
        "composite_available": composite is not None,
        "score_band": S.score_band(composite),
        "formula_used": S.formula_expression(objective),
        "formula_source": S.formula_source(objective),
        "structure_checks": checks,
        "phrases": phrases,
        "phrases_dropped": len(dropped),
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

    raw = _ask(REWRITE_SYSTEM, prompt)
    banned = sources.contact_names()
    rewrite, faults = F.validate_rewrite(raw, fmt, banned, persona, original)

    if faults:
        logger.warning("evaluator: rewrite rejected (%s), retrying once",
                       "; ".join(faults))
        retry = _ask(REWRITE_SYSTEM, prompt + "\n\nYour previous answer was rejected:\n"
                     + "\n".join("  - %s" % f for f in faults))
        rewrite, faults = F.validate_rewrite(retry, fmt, banned, persona, original)

    if not rewrite:
        # The seller keeps their original rather than receiving a malformed one.
        db[storage.COLLECTION].update_one(
            {"account_id": account_id, "fingerprint": fingerprint},
            {"$set": {"rewrite": None,
                      "rewrite_faults": faults,
                      "rewrite_attempted_at": datetime.now(timezone.utc)}})
        raise EvaluationError("the rewrite did not meet the %s format contract: %s"
                              % (evaluation["format_label"], "; ".join(faults)))

    diff, diff_faults = verify.diff_rewrite(original, rewrite["plain_text"],
                                            sources, selected)
    if diff_faults:
        db[storage.COLLECTION].update_one(
            {"account_id": account_id, "fingerprint": fingerprint},
            {"$set": {"rewrite": None, "rewrite_faults": diff_faults,
                      "rewrite_diff": diff,
                      "rewrite_attempted_at": datetime.now(timezone.utc)}})
        raise EvaluationError("the rewrite introduced claims the sources do not "
                              "support: %s" % "; ".join(diff_faults))

    rewrite["diff"] = diff
    db[storage.COLLECTION].update_one(
        {"account_id": account_id, "fingerprint": fingerprint},
        {"$set": {"rewrite": rewrite, "rewrite_faults": [],
                  "rewrite_applied": selected,
                  "rewrite_attempted_at": datetime.now(timezone.utc)}})
    return storage.find_existing(account_id, fingerprint)
