"""Objective-weighted scoring for the Message Evaluator.

HP_ABX_v3_final Feature 9, Stage 5 Step 4 fixes four weighting formulas. The
model supplies dimension scores; everything below - which formula applies,
whether the scores are usable, and the composite itself - is decided in Python.

Two rules are load-bearing and easy to get wrong:

  * **Only the objective selects the formula.** Not the mode, not the format,
    not the persona. Mode changes how deep the analysis goes and format changes
    the prompt context; neither touches a weight. The UI prints the formula next
    to the score, so a mismatch here would be visible and wrong.

  * **Every dimension a formula references must be valid before any composite
    is published.** Five for Awareness, Engagement and Consideration; six for
    Conversion. A missing, non-numeric or out-of-range dimension invalidates the
    whole composite - there is no partial-weight fallback and no renormalising
    over whichever dimensions happened to arrive, because either of those would
    quietly produce a plausible number from incomplete input.
"""

RELEVANCE = "relevance"
IMPACT = "impact"
BRAND_RECALL = "brand_recall"
CLARITY = "clarity"
CREATIVITY = "creativity"
EMOTIONAL = "emotional_connection"
NEXT_STEP = "next_step_strength"

ALL_DIMENSIONS = [RELEVANCE, IMPACT, BRAND_RECALL, CLARITY, CREATIVITY,
                  EMOTIONAL, NEXT_STEP]

# Verbatim from the specification. The reference application displays the
# Awareness row as "Relevance*0.3 + Impact*0.2 + Brand_Recall*0.2 +
# Clarity*0.15 + Creativity*0.15", which matches.
OBJECTIVE_FORMULAS = {
    "awareness": {
        RELEVANCE: 0.30, IMPACT: 0.20, BRAND_RECALL: 0.20,
        CLARITY: 0.15, CREATIVITY: 0.15,
    },
    "engagement": {
        RELEVANCE: 0.50, IMPACT: 0.10, CLARITY: 0.20,
        CREATIVITY: 0.10, EMOTIONAL: 0.10,
    },
    "consideration": {
        RELEVANCE: 0.40, BRAND_RECALL: 0.10, CLARITY: 0.10,
        EMOTIONAL: 0.10, NEXT_STEP: 0.30,
    },
    "conversion": {
        RELEVANCE: 0.15, IMPACT: 0.15, BRAND_RECALL: 0.25, CLARITY: 0.10,
        EMOTIONAL: 0.05, NEXT_STEP: 0.30,
    },
    # Advocacy is NOT in HP_ABX_v3_final, which stops at Conversion. It is the
    # fifth objective in the reference application's dropdown, and its weights
    # are that application's: Relevance .15, Brand_Recall .30, Clarity .15,
    # Creativity .10, Emotional .30. Carried here so the seller sees the same
    # five funnel stages, with the source of the weights recorded on the
    # evaluation rather than implied to be the specification.
    "advocacy": {
        RELEVANCE: 0.15, BRAND_RECALL: 0.30, CLARITY: 0.15,
        CREATIVITY: 0.10, EMOTIONAL: 0.30,
    },
}

# Where each formula comes from, stored on every evaluation.
FORMULA_SOURCE = {
    "awareness": "HP_ABX_v3_final Feature 9 Step 4",
    "engagement": "HP_ABX_v3_final Feature 9 Step 4",
    "consideration": "HP_ABX_v3_final Feature 9 Step 4",
    "conversion": "HP_ABX_v3_final Feature 9 Step 4",
    "advocacy": "reference application (not in HP_ABX_v3_final)",
}

# Funnel order, not alphabetical - these are stages, and a dropdown that runs
# Advocacy, Awareness, Consideration, Conversion, Engagement is nonsense.
OBJECTIVES = ["awareness", "engagement", "consideration", "conversion", "advocacy"]

OBJECTIVE_LABELS = {k: k.capitalize() for k in OBJECTIVES}

DIMENSION_LABELS = {
    RELEVANCE: "Relevance", IMPACT: "Impact", BRAND_RECALL: "Brand Recall",
    CLARITY: "Clarity", CREATIVITY: "Creativity",
    EMOTIONAL: "Emotional Connection", NEXT_STEP: "Next-step Strength",
}

for _obj, _w in OBJECTIVE_FORMULAS.items():
    assert abs(sum(_w.values()) - 1.0) < 1e-9,         "%s weights sum to %g, not 1.0" % (_obj, sum(_w.values()))
assert set(OBJECTIVES) == set(OBJECTIVE_FORMULAS) == set(FORMULA_SOURCE)

SCORE_MIN = 0
SCORE_MAX = 100


class ScoringError(Exception):
    """The composite cannot be computed from what the model returned."""


def normalize_objective(objective: str) -> str:
    value = str(objective or "").strip().lower()
    if value not in OBJECTIVE_FORMULAS:
        raise ScoringError(
            "unknown objective %r - expected one of %s"
            % (objective, ", ".join(OBJECTIVES)))
    return value


def formula_source(objective: str) -> str:
    """Which document fixes these weights."""
    return FORMULA_SOURCE[normalize_objective(objective)]


def catalogue() -> list:
    """Objectives for the UI dropdown, in funnel order."""
    return [{"id": k, "label": OBJECTIVE_LABELS[k],
             "formula": formula_expression(k), "source": FORMULA_SOURCE[k]}
            for k in OBJECTIVES]


def formula_for(objective: str) -> dict:
    """The weights for this objective. Nothing else is consulted."""
    return dict(OBJECTIVE_FORMULAS[normalize_objective(objective)])


def formula_expression(objective: str) -> str:
    """Human-readable formula, for display beside the score."""
    weights = formula_for(objective)
    return " + ".join(
        "%s*%g" % (DIMENSION_LABELS[dim], weight)
        for dim, weight in weights.items())


def required_dimensions(objective: str) -> list:
    return sorted(formula_for(objective))


def validate_dimensions(raw: dict, objective: str):
    """(valid, problems). A dimension is valid only if numeric and 0-100.

    Returns every problem found rather than the first, so one correction round
    trip can fix them all.
    """
    valid, problems = {}, []
    needed = required_dimensions(objective)

    for dimension in needed:
        if dimension not in (raw or {}):
            problems.append("%s: missing" % dimension)
            continue
        value = (raw or {})[dimension]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            try:
                value = float(str(value).strip())
            except (TypeError, ValueError):
                problems.append("%s: not numeric (%r)" % (dimension, value))
                continue
        if value < SCORE_MIN or value > SCORE_MAX:
            problems.append("%s: %g outside %d-%d"
                            % (dimension, value, SCORE_MIN, SCORE_MAX))
            continue
        valid[dimension] = float(value)

    return valid, problems


def composite(dimensions: dict, objective: str) -> float:
    """The weighted total. Raises unless every required dimension is valid.

    Deliberately strict: publishing a composite from a subset would give a
    number that looks like the others and means something different.
    """
    weights = formula_for(objective)
    missing = [d for d in weights if d not in (dimensions or {})]
    if missing:
        raise ScoringError(
            "cannot compute a %s composite - missing %s"
            % (objective, ", ".join(sorted(missing))))

    total = sum(dimensions[dim] * weight for dim, weight in weights.items())
    return round(total, 1)


def score_band(value) -> str:
    """The qualitative band shown under the number."""
    if value is None:
        return "Unavailable"
    if value >= 80:
        return "Strong"
    if value >= 60:
        return "Good"
    if value >= 40:
        return "Fair"
    if value >= 20:
        return "Weak"
    return "Poor"
