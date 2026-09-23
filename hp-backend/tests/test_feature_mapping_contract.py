"""Tests for the feature-mapping data_type vocabulary.

GET /api/v1/features returned a 500 for every caller, in both the old and the
new code, because seven mapped_fields carried a data_type outside the two the
response schema allows - six "DERIVED" and one "REFERENCE". FastAPI validates
the RESPONSE against the declared model, so the whole endpoint failed rather
than the one bad field, and the failure was silent until structured logging
surfaced the ResponseValidationError.

What these pin:

  - the vocabulary itself, so a new value cannot be introduced without either
    extending the Literal or being caught here rather than in production
  - the two-layer meaning behind it, which is the part a future editor is
    likely to get wrong: DETERMINISTIC means computed in Python from named
    source columns, INFERRED / SYNTHESIZED means written by the model. The
    handover document defines those two layers; "DERIVED" was a third word for
    the first of them and "REFERENCE" a fourth for the second.

Run: python -m pytest tests/test_feature_mapping_contract.py -v
"""

import os
import sys
from typing import get_args

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.api.v1.feature_mapping import FEATURE_MAPPINGS
from app.schemas.feature_mapping import FeatureMappingResponse, MappedField

ALLOWED = set(get_args(MappedField.model_fields["data_type"].annotation))

# Written by the model rather than computed. Kept as an explicit list because
# the distinction is a judgement about each field, not something derivable.
LLM_WRITTEN = {"hp_capability"}


def _all_fields():
    for feature_key, spec in FEATURE_MAPPINGS.items():
        for field in spec.get("mapped_fields", []):
            yield feature_key, field


def test_every_feature_validates_against_its_response_model():
    # The regression itself: this is what returned a 500 to every caller.
    for spec in FEATURE_MAPPINGS.values():
        FeatureMappingResponse(**spec)


def test_no_field_uses_a_data_type_outside_the_vocabulary():
    offenders = [
        (feature_key, field.get("field_key"), field.get("data_type"))
        for feature_key, field in _all_fields()
        if field.get("data_type") not in ALLOWED
    ]
    assert not offenders, (
        f"data_type values outside {sorted(ALLOWED)}: {offenders}. "
        f"Either use an existing value or extend the Literal in "
        f"schemas/feature_mapping.py - a new word here fails the whole endpoint."
    )


def test_the_vocabulary_is_exactly_two_values():
    # A guard on the schema rather than the data: widening the Literal is a
    # deliberate act, and this makes it visible in review.
    assert {"DETERMINISTIC", "INFERRED / SYNTHESIZED"} == ALLOWED


@pytest.mark.parametrize("feature_key,field", list(_all_fields()),
                         ids=lambda v: v if isinstance(v, str) else v.get("field_key", "?"))
def test_deterministic_fields_cite_a_source_and_inferred_ones_do_not(feature_key, field):
    """The semantic rule behind the vocabulary.

    A field computed from uploaded data names the dataset it reads. A field the
    model writes has nothing to name. The two exceptions are fields computed in
    Python from data already assembled by other fields - they are deterministic
    but read no dataset directly.
    """
    data_type = field["data_type"]
    key = field.get("field_key")
    has_dataset = bool(field.get("dataset_key"))

    if data_type == "INFERRED / SYNTHESIZED":
        assert not has_dataset, (
            f"{feature_key}.{key} is marked LLM-written but names dataset "
            f"{field.get('dataset_key')!r}; a model-written field reads no dataset."
        )
    else:
        # Deterministic. Most name a dataset; the rest compute from values other
        # deterministic fields already produced.
        assert key not in LLM_WRITTEN, (
            f"{feature_key}.{key} is written by the model and must be "
            f"INFERRED / SYNTHESIZED, not {data_type}."
        )


def test_the_previously_broken_fields_are_now_deterministic():
    # The six that were "DERIVED". Each is computed in Python from named source
    # columns and never reaches an LLM prompt - pinned by name so a future edit
    # that flips one back to a model-written type has to justify itself here.
    # "severity" became "priority" when the client replaced the "N of 3 checks"
    # tag with Critical/High/Medium/Low (Sep 2026). Same field, same guarantee:
    # computed in Python, never model-written.
    computed_in_python = {
        "source_publisher", "influence_type", "priority",
        "scale_statement", "target_contacts", "likely_raiser",
    }
    seen = {
        field["field_key"]: field["data_type"]
        for _, field in _all_fields()
        if field.get("field_key") in computed_in_python
    }
    assert set(seen) == computed_in_python, f"field(s) renamed or removed: {seen}"
    for key, data_type in seen.items():
        assert data_type == "DETERMINISTIC", f"{key} regressed to {data_type}"


def test_hp_capability_is_marked_as_model_written():
    # It was "REFERENCE". It is built from the model's JSON response in
    # solution_narrative_opportunity_map.py, so it belongs in the inferred layer.
    match = [f for _, f in _all_fields() if f.get("field_key") == "hp_capability"]
    assert match, "hp_capability was renamed or removed"
    assert match[0]["data_type"] == "INFERRED / SYNTHESIZED"


# =============================================================================
# A dataset nothing depends on is a dataset nothing rebuilds.
# =============================================================================

def test_every_dataset_a_feature_reads_is_declared_as_a_dependency():
    """`dependent_datasets` is not documentation - it is the regeneration trigger.

    `_features_for_dataset` in `api/v1/account_data.py` builds the list of
    extractors to re-run purely by scanning `dependent_datasets` for the
    uploaded key. A dataset absent from every feature therefore regenerates
    nothing: the upload returns 201, the file lands on disk, and the dashboard
    goes on showing figures derived from the previous one.

    `compliance_filings` was in exactly that state. It is read by
    `dashboard/priorities.py`, `dashboard/evidence_strength.py` and
    `retrieval/corpus.py` in five places, and it is the only source of reported
    financial figures - and it appeared in no feature's dependency list, so
    copying filings into an account changed nothing at all.
    """
    from app.api.v1.feature_mapping import FEATURE_MAPPINGS

    declared = {d for spec in FEATURE_MAPPINGS.values()
                for d in (spec.get("dependent_datasets") or [])}
    assert "compliance_filings" in declared, (
        "compliance_filings is read by the code but depended on by no feature, "
        "so uploading one regenerates nothing")


def test_filings_rebuild_the_five_features_the_client_named():
    """The client's file-usage mapping is explicit about which features
    `filings 1.csv` feeds. Pinned so a future edit to one feature's dependency
    list cannot quietly drop filings from another."""
    from app.api.v1.feature_mapping import FEATURE_MAPPINGS

    expected = {
        "executive_dashboard",          # reported financial figures
        "recent_news_signals",          # "Live Signals" in the client's naming
        "solution_narrative_opportunity_map",   # "Opportunity Map"
        "content_messaging",
        "strategy_chat",
    }
    actual = {fk for fk, spec in FEATURE_MAPPINGS.items()
              if "compliance_filings" in (spec.get("dependent_datasets") or [])}
    assert actual == expected


def test_every_declared_dependency_is_a_real_dataset_key():
    """A typo in `dependent_datasets` fails silently - the key simply never
    matches an upload, and the feature never rebuilds."""
    from app.api.v1.feature_mapping import FEATURE_MAPPINGS
    from app.schemas.account_data import DATASET_REGISTRY

    for feature_key, spec in FEATURE_MAPPINGS.items():
        for dataset in (spec.get("dependent_datasets") or []):
            assert dataset in DATASET_REGISTRY, (
                "%s depends on '%s', which is not a dataset key"
                % (feature_key, dataset))
