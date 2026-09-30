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
    is published.** There is no partial-weight fallback and no renormalising
    over whichever dimensions happened to arrive, because either would quietly
    produce a plausible number from incomplete input. What the 30 Sep build
    specification adds (T21) is a stated, visible substitute: a dimension still
    missing after the correction round trip is padded to 50, the pad is
    recorded on the evaluation, and the seller is told which number was not the
    model's. A recorded pad is not a renormalisation - the formula is
    unchanged - and it is the difference between an evaluation that says so and
    one that looks complete.

All seven dimensions are always scored and always shown. The weights decide
what reaches the composite; a dimension weighted 0 for this objective is still
a number the seller sees, which is the point of showing all seven.
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

# The names the build specification uses for the same seven (Section 4.5 and
# the 4.10 contract). Two differ from our display labels, and the prompt is
# written in the specification's spellings so an HP reader comparing the two
# documents sees the same words. `_match_dimension` reads all of them back.
SPEC_DIMENSION_NAMES = {
    RELEVANCE: "Relevance", IMPACT: "Impact", BRAND_RECALL: "Brand_Recall",
    CLARITY: "Clarity", CREATIVITY: "Creativity", EMOTIONAL: "Emotional",
    NEXT_STEP: "CTA",
}

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

# Spec Section 4.5. Six bands, read from the top down; the previous table had
# five and started "Strong" at 80, so a 76 read as "Good" where the
# specification calls it Strong.
SCORE_BANDS = (
    (90, "Exceptional"),
    (75, "Strong"),
    (60, "Good"),
    (40, "Average"),
    (20, "Weak"),
    (0, "Poor"),
)

# T21: what a dimension the model never returned is worth. Not 0 - that would
# read as a judgement the model did not make - and not the mean of the others,
# which would be an invention dressed as arithmetic. 50 is the midpoint of the
# scale, and it is recorded so nobody mistakes it for a score.
PAD_SCORE = 50.0

# The one problem `pad_missing` may substitute for. Named rather than spelled
# twice, because the pad is keyed off this exact string.
MISSING_DETAIL = "missing"


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


def required_dimensions(_objective: str = "") -> list:
    """All seven. Spec Section 4.5: "Seven. Always."

    This used to return the weighted dimensions for the objective, which meant
    Awareness never asked for Emotional or CTA and the seller saw five bars.
    The objective still decides the composite - see `weighted_dimensions` - but
    it no longer decides what gets scored.

    The argument is kept and ignored so every existing call site still reads
    correctly; the answer does not depend on it.
    """
    return list(ALL_DIMENSIONS)


def weighted_dimensions(objective: str) -> list:
    """The dimensions this objective's formula actually multiplies.

    The rest are scored and displayed at weight 0. Use this only where the
    composite is concerned - never to decide what to ask the model for.
    """
    return sorted(formula_for(objective))


def weight_of(objective: str, dimension: str) -> float:
    """This dimension's weight, 0.0 when the formula does not reference it."""
    return formula_for(objective).get(dimension, 0.0)


def pad_missing(valid: dict, problems: list) -> tuple[dict, list, list]:
    """T21: pad a dimension the model never gave us, and say which.

    Called after the correction round trip, not instead of it. Returns
    (dimensions, padded, remaining_problems) - `padded` names every dimension
    that now holds `PAD_SCORE` rather than a score, and `remaining_problems`
    keeps anything padding cannot fix, so a caller can still refuse to publish.
    """
    dimensions = dict(valid or {})
    padded, remaining = [], []
    for problem in (problems or []):
        # `validate_dimensions` formats every problem as "<dimension>: <detail>",
        # and only one detail means the model did not answer: "missing". A
        # dimension it returned as "excellent", or as 400, is a different
        # failure and stays a problem - padding it would replace a wrong answer
        # with a plausible one, which is the thing this module exists to refuse.
        dimension, _, detail = str(problem).partition(": ")
        if (detail == MISSING_DETAIL and dimension in ALL_DIMENSIONS
                and dimension not in dimensions):
            dimensions[dimension] = PAD_SCORE
            padded.append(dimension)
        else:
            remaining.append(problem)
    return dimensions, padded, remaining


def split_dimension_payload(raw):
    """(scores, rationales) from either shape the model may return.

    Spec Section 4.10 asks for an array - `[{"dimension": "Creativity",
    "score": 82, "rationale": "..."}, ...]` - and the build has always asked
    for an object keyed by dimension. Both are read here rather than in the
    caller, so the rest of the pipeline sees one shape and an evaluation stored
    under the older contract still loads.

    Dimension names are matched case-insensitively and against the display
    label as well as the key, because the specification writes them as
    "Brand_Recall" and "CTA" where this module's keys are `brand_recall` and
    `next_step_strength`.
    """
    scores, rationales = {}, {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            dimension = _match_dimension(key)
            if dimension is None:
                continue
            if isinstance(value, dict):
                # {"clarity": {"score": 70, "rationale": "..."}}
                scores[dimension] = value.get("score")
                if str(value.get("rationale") or "").strip():
                    rationales[dimension] = str(value["rationale"]).strip()
            else:
                scores[dimension] = value
        return scores, rationales

    for entry in (raw or []):
        if not isinstance(entry, dict):
            continue
        dimension = _match_dimension(entry.get("dimension") or entry.get("name"))
        if dimension is None:
            # "Extra/unrecognised dimension: drop it" - Section 4.10.
            continue
        scores[dimension] = entry.get("score")
        if str(entry.get("rationale") or "").strip():
            rationales[dimension] = str(entry["rationale"]).strip()
    return scores, rationales


_DIMENSION_ALIASES = {}
for _dim in ALL_DIMENSIONS:
    _DIMENSION_ALIASES[_dim.lower()] = _dim
    _DIMENSION_ALIASES[DIMENSION_LABELS[_dim].lower()] = _dim
    _DIMENSION_ALIASES[DIMENSION_LABELS[_dim].replace(" ", "_").lower()] = _dim
# The specification's own spellings for the two that differ from ours.
_DIMENSION_ALIASES["cta"] = NEXT_STEP
_DIMENSION_ALIASES["call to action"] = NEXT_STEP
_DIMENSION_ALIASES["emotional"] = EMOTIONAL


def _match_dimension(name):
    return _DIMENSION_ALIASES.get(str(name or "").strip().lower())


def validate_dimensions(raw: dict, objective: str):
    """(valid, problems). A dimension is valid only if numeric and 0-100.

    Returns every problem found rather than the first, so one correction round
    trip can fix them all.
    """
    valid, problems = {}, []
    needed = required_dimensions(objective)

    for dimension in needed:
        if dimension not in (raw or {}):
            problems.append("%s: %s" % (dimension, MISSING_DETAIL))
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
    """The qualitative band shown under the number (spec Section 4.5)."""
    if value is None:
        return "Unavailable"
    for floor, label in SCORE_BANDS:
        if value >= floor:
            return label
    return "Poor"
