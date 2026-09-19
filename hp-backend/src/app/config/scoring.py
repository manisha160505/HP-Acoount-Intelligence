"""Scoring weights and bands, loaded from `config/scoring.yaml`.

Every number a client document fixes - a driver weight, a band boundary, a
points allocation, a cap - lives in that YAML file rather than in the module
that uses it, so it can be changed without editing Python.

## What belongs here, and what does not

Only **client-specified scoring** moves into the config: the weights and bands
that a supplied document defines and that a client could reasonably want to
retune. Chunk sizes, `top_k`, HTTP timeouts, retry counts and max-item limits
stay in their own modules. They are operational, and putting them in a file
called "scoring" invites someone to tune a retrieval parameter believing it is a
weight.

## Why each section carries its authority

A weight with no source is a number somebody guessed. Every section names the
document it came from, and that string is published in the widget payload, so a
reader who doubts a score can find the page it was decided on. Moving the
numbers out of the code must not lose that - it is the difference between a
configurable score and an arbitrary one.

## Validation runs at import, and is meant to be loud

`_validate` rejects a weights block that does not sum to 1.0 and a band table
that is not in descending order. Both are silent failures otherwise: weights
summing to 0.9 produce scores about 10% low across every account, and a band
table out of order returns the first row that matches rather than the right one.
Neither raises, neither logs, and both look exactly like a working system. The
whole point of making these editable is that someone will edit them, so a
mistake has to stop the process rather than quietly change every number on every
dashboard.

## Versioning: how a change reaches the screen

`version(section)` is a hash of that section's loaded values. A scored widget
records the hash that produced it, and a startup sweep regenerates the widgets
whose stamp no longer matches - per section, so retuning an urgency band does
not rebuild the Tech Landscape.

This is not theoretical tidiness. The urgency formula was rewritten in code and
the dashboard kept serving the retired five-driver model for days, because
nothing anywhere compared what a stored widget was computed with against what
the code now does. Making the weights easier to change makes that failure easier
to trigger, so the detection has to ship with it.
"""

import hashlib
import json
import logging
import os

import yaml

logger = logging.getLogger(__name__)

# config/scoring.yaml sits at the backend root, beside the .env files, so it is
# visible as configuration rather than buried in the package. Anchored to this
# file rather than the working directory - settings.py documents what happened
# when a path was resolved against the CWD instead.
_CONFIG_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.abspath(os.path.join(_CONFIG_DIR, "..", "..", ".."))
CONFIG_PATH = os.path.join(_BACKEND_ROOT, "config", "scoring.yaml")

# Tolerance for a weights block summing to 1.0. Floats do not add exactly -
# 0.20 + 0.25 + 0.30 + 0.25 is not 1.0 in binary - so an exact test would reject
# a correct config.
_WEIGHT_SUM_TOLERANCE = 1e-9


class ScoringConfigError(RuntimeError):
    """Raised at import when the config cannot be trusted.

    Deliberately fatal. A scoring config that is wrong but loadable produces
    plausible numbers on every dashboard, and nothing downstream can tell.
    """


def _fail(message: str) -> None:
    raise ScoringConfigError("%s (in %s)" % (message, CONFIG_PATH))


def _validate_weights(name: str, weights: dict) -> None:
    if not weights:
        _fail("section '%s' has an empty weights block" % name)
    for key, value in weights.items():
        if not isinstance(value, (int, float)):
            _fail("weight '%s.%s' is %r, which is not a number" % (name, key, value))
        if value < 0:
            _fail("weight '%s.%s' is negative" % (name, key))
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        _fail("weights in '%s' sum to %g, not 1.0 - every score in this feature "
              "would be off by %g%%" % (name, total, abs(1.0 - total) * 100))


def _validate_bands(name: str, key: str, bands) -> None:
    """A band table is read first-match-wins, so its order carries meaning.

    There are two shapes in use and both are correct:

      lower-bound, descending - `if value >= bound`, as in the urgency employee
          and hiring ladders, where 50,000+ must be tested before 10,001+
      upper-bound, ascending  - `if value <= bound`, as in the live-signal
          recency bands, where 0-7 days must be tested before 0-30

    So the rule is not a direction, it is **monotonicity**: the bounds must run
    one way without reversing. A single row out of place is the failure this
    catches, and it is silent otherwise - the table keeps returning a row, just
    the wrong one, with every score still inside its normal range.

    A table whose bounds are LABELS rather than numbers is skipped, and that is
    correct rather than an oversight. `urgency.employee_bands` is keyed on band
    strings like "10001-49999" and is read by exact match, not by threshold -
    `_employee_band_points` compares normalised labels and the input contract
    says these are "passed through verbatim; NEVER parsed numerically". Its
    order carries no meaning, so there is nothing to validate.
    """
    bounds = []
    for row in bands:
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            _fail("band '%s.%s' has a row that is not a [threshold, points] "
                  "pair: %r" % (name, key, row))
        bound, points = row
        if not isinstance(points, (int, float)):
            _fail("band '%s.%s' has non-numeric points %r" % (name, key, points))
        if isinstance(bound, (int, float)):
            bounds.append(float(bound))

    if len(bounds) < 2:
        return
    ascending = bounds == sorted(bounds)
    descending = bounds == sorted(bounds, reverse=True)
    if not (ascending or descending):
        _fail("band '%s.%s' is not monotonic - it is read first-match-wins, so "
              "a row out of order silently returns the wrong band: %s"
              % (name, key, bounds))


def _validate(config: dict) -> None:
    for name, section in config.items():
        if not isinstance(section, dict):
            _fail("section '%s' is not a mapping" % name)
        if not section.get("authority"):
            _fail("section '%s' names no authority - every scoring number must "
                  "cite the document that fixed it" % name)
        if "weights" in section:
            _validate_weights(name, section["weights"])
        for key, value in section.items():
            if key.endswith("_bands") and isinstance(value, list):
                _validate_bands(name, key, value)


def _load() -> dict:
    if not os.path.exists(CONFIG_PATH):
        _fail("scoring config not found")
    with open(CONFIG_PATH, encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    if not isinstance(config, dict):
        _fail("scoring config is not a mapping")
    _validate(config)
    logger.info("scoring config loaded: %d section(s) from %s",
                len(config), CONFIG_PATH)
    return config


CONFIG = _load()


def section(name: str) -> dict:
    """One scorer's block. Missing is fatal - a scorer with no config cannot
    fall back to a default without inventing the numbers it exists to apply."""
    if name not in CONFIG:
        _fail("no scoring section named '%s'" % name)
    return CONFIG[name]


def bands(name: str, key: str) -> tuple:
    """A band table as tuples, in the shape the scorers already expect."""
    return tuple(tuple(row) for row in section(name).get(key) or ())


def weights(name: str) -> dict:
    return dict(section(name).get("weights") or {})


def version(name: str) -> str:
    """A short hash of one section's values.

    Stamped onto every widget the section scores, so a config change is
    detectable rather than silent. Excludes `authority`, which is prose: fixing
    a typo in a citation should not invalidate a year of stored scores.
    """
    payload = {k: v for k, v in section(name).items() if k != "authority"}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()[:12]
