"""Section F: the structured record behind every seller-facing output.

    "Generate a structured internal object first; then render the approved
    seller-facing fields in the UI. Each important claim must be traceable to
    its evidence IDs."
        - HP Recommendation Tuning Logic FINAL v4, section F

    feature              the feature generating the recommendation
    account_id           canonical account identifier
    as_of_date           the account-data snapshot the output was built from
    recommendation_text  the seller-facing conclusion
    claim_ids[]          stable ids for the material claims in that text
    evidence_ids[]       source record ids supporting each claim
    hp_offering_ids[]    rulebook offering ids actually cited
    proof_ids[]          case-study ids actually cited
    confidence_tier      the evidence-strength label

Ids are **derived, not allocated**. A claim id is a hash of what the claim says
and where it sits, so the same sentence regenerated from the same evidence keeps
the same id and a changed sentence gets a new one. That is what makes the record
auditable across rebuilds: nothing has to be stored to be able to say "this is
the claim that was on the card yesterday".

The features differ in what they can supply. Anything genuinely absent is
published as an empty list rather than omitted - section F marks
`hp_offering_ids` and `proof_ids` "When used", and an empty list says the
question was asked and the answer was none, where a missing key cannot.
"""

import hashlib
import logging

logger = logging.getLogger(__name__)

# Long enough that a collision is not a practical concern, short enough to read
# in a payload and quote in a bug report.
ID_LENGTH = 12


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _digest(*parts) -> str:
    joined = "|".join(_text(p).lower() for p in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:ID_LENGTH]


def claim_id(feature: str, account_id: str, scope: str, field: str, text) -> str:
    """A stable id for one material claim.

    Derived from the claim itself, so it survives a regeneration that did not
    change the sentence and changes when the sentence does. `scope` is whatever
    the feature uses to identify the thing the claim is about - a rule label, a
    play key, a category key.
    """
    return "claim_%s" % _digest(feature, account_id, scope, field, text)


def evidence_id(row) -> str | None:
    """A stable id for one evidence row, or None when the row says nothing.

    The retrieval registry already mints ids for the features it indexes. The
    rulebook matchers do not go through it - they read dataset cells directly -
    so their evidence needs an id of the same shape, derived the same way.
    """
    if not isinstance(row, dict):
        return None
    text = _text(row.get("text") or row.get("source_text") or row.get("quote"))
    if not text:
        return None
    existing = _text(row.get("evidence_id"))
    if existing:
        return existing
    return "ev_%s" % _digest(row.get("dataset"), row.get("field"), text)


def record(  # noqa: PLR0913, PLR0917 - section F names nine fields; this builds them
    feature: str,
    account_id: str,
    as_of_date: str | None,
    recommendation_text,
    claims=None,
    evidence_rows=None,
    evidence_ids=None,
    hp_offering_ids=None,
    proof_ids=None,
    confidence_tier: str | None = None,
    scope: str = "",
) -> dict:
    """The nine-field record for one output.

    `claims` is `{field: text}` - the material claims this output makes, each
    getting its own id. `recommendation_text` is the seller-facing conclusion;
    pass the same text as a claim when it is itself the claim.

    Evidence arrives either way round. A caller holding the rows passes
    `evidence_rows` and the ids are derived here; one that derived them earlier,
    from rows it did not keep or kept only truncated for display, passes
    `evidence_ids`. Both may be given, and the union is what the record carries.
    """
    claims = {k: v for k, v in (claims or {}).items() if _text(v)}
    ids = {evidence_id(row) for row in (evidence_rows or [])}
    ids |= {_text(i) or None for i in (evidence_ids or [])}
    ids = sorted(ids - {None})

    return {
        "feature": feature,
        "account_id": str(account_id or ""),
        "as_of_date": as_of_date,
        "recommendation_text": _text(recommendation_text) or None,
        "claim_ids": [claim_id(feature, account_id, scope, field, text)
                      for field, text in sorted(claims.items())],
        "claims": {claim_id(feature, account_id, scope, field, text): field
                   for field, text in sorted(claims.items())},
        "evidence_ids": ids,
        # "When used" in section F. An empty list is the honest answer to a
        # question that was asked; a missing key would not distinguish "none
        # cited" from "never checked".
        "hp_offering_ids": sorted({_text(x) for x in (hp_offering_ids or []) if _text(x)}),
        "proof_ids": sorted({_text(x) for x in (proof_ids or []) if _text(x)}),
        "confidence_tier": confidence_tier,
    }
