"""The client's buying committee for an account: the `company_personas` dataset.

Where it comes from
-------------------
The client sent a 32-role target list and, for every account, who fills each
role: a name, title, work email, phone and LinkedIn where the enrichment found
one, and an explicit "no suitable distinct candidate found" where it did not.
`scripts/split_account_data.py --refresh` writes that per account as
`company_personas.csv`.

Why it exists as its own dataset rather than more columns on prospect_contacts
------------------------------------------------------------------------------
Two thirds of the rows name nobody. They are the client stating a role they
want reached and that no contact for it was found - evidence of a gap, which a
contact file cannot carry because a contact file only holds people who exist.
Keeping them here is what lets the Stakeholder Map say "9 of 32 target roles
are covered" instead of silently showing the nine.

The rules that apply to it are the ones that apply everywhere else: an unfilled
role stays a role. Nothing here may turn one into a person, invent a contact
detail, or infer that someone holds a role because their title looks close -
the "matched alias" and "match basis" columns record the client's own matching,
and that is the only authority for the persona on a contact.
"""

from app.services.extractors.datasets import read_dataset_records

DATASET_KEY = "company_personas"

# The delivered column names. Listed once here so the three features that read
# this dataset cannot drift into reading it differently.
COL_PERSONA = "target_persona"
COL_DEPARTMENT = "department"
COL_ANGLE = "buying_committee_angle"
COL_NAME = "contact_name"
COL_TITLE = "actual_job_title"
COL_EMAIL = "work_email"
COL_PHONE = "phone_number"
COL_LINKEDIN = "linkedin_url"
COL_STATUS = "contact_status"
COL_SOURCE = "source"
COL_ALIAS = "matched_alias"


def _text(value) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in ("nan", "none", "null") else text


def read_roles(account_id: str) -> list[dict]:
    """The account's target roles, filled and unfilled, in delivered order.

    Returns [] when the dataset was never uploaded, which is the same thing the
    features see for any other missing dataset: they carry on without it.
    """
    roles = []
    for row in read_dataset_records(account_id, DATASET_KEY) or []:
        persona = _text(row.get(COL_PERSONA))
        if not persona:
            continue
        name = _text(row.get(COL_NAME))
        roles.append({
            "target_persona": persona,
            "department": _text(row.get(COL_DEPARTMENT)),
            "buying_committee_angle": _text(row.get(COL_ANGLE)),
            "contact_name": name,
            "actual_job_title": _text(row.get(COL_TITLE)),
            "work_email": _text(row.get(COL_EMAIL)),
            "phone_number": _text(row.get(COL_PHONE)),
            "linkedin_url": _text(row.get(COL_LINKEDIN)),
            "contact_status": _text(row.get(COL_STATUS)),
            "source": _text(row.get(COL_SOURCE)),
            "matched_alias": _text(row.get(COL_ALIAS)),
            "is_filled": bool(name),
        })
    return roles


def coverage(roles: list[dict]) -> dict:
    """How much of the client's buying committee this account actually has.

    The unfilled roles are returned in full, not just counted: "who are we
    still missing" is the question a seller asks of this, and a number alone
    cannot answer it.
    """
    filled = [r for r in roles if r["is_filled"]]
    unfilled = [r for r in roles if not r["is_filled"]]
    reachable = [r for r in filled if r["work_email"] or r["phone_number"]]
    return {
        "target_roles": len(roles),
        "filled_roles": len(filled),
        "unfilled_roles": len(unfilled),
        "roles_with_a_contact_detail": len(reachable),
        "coverage_percent": round(100.0 * len(filled) / len(roles), 1) if roles else None,
        "filled": [{"target_persona": r["target_persona"],
                    "buying_committee_angle": r["buying_committee_angle"],
                    "contact_name": r["contact_name"],
                    "actual_job_title": r["actual_job_title"],
                    "has_work_email": bool(r["work_email"]),
                    "has_phone": bool(r["phone_number"]),
                    "source": r["source"]} for r in filled],
        "not_covered": [{"target_persona": r["target_persona"],
                         "department": r["department"],
                         "buying_committee_angle": r["buying_committee_angle"],
                         "why": r["contact_status"] or "no contact found"}
                        for r in unfilled],
        "source_dataset": DATASET_KEY,
    }


def role_id(persona: str) -> str:
    """A stable id for a target role, for the two persona-driven features."""
    slug = "".join(c if c.isalnum() else "_" for c in persona.lower()).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return "role_%s" % slug
