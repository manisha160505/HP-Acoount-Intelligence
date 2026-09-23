import contextlib
import logging
from datetime import UTC, datetime

from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path,
    read_dataset_records,
    requires_local_datasets,
)

logger = logging.getLogger(__name__)


def _find_file_path(rel_path: str) -> str | None:
    """Shared implementation - see datasets.py."""
    return find_file_path(rel_path)

def _read_dataset_csv(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

def _resolve_ultimate_parent(hier_row: dict | None, business_description: str = "") -> tuple[str, dict | None]:
    """The ultimate parent to display, and a review flag when it cannot be trusted.

    Returns ("", flag) rather than a name whenever the hierarchy row fails to
    establish one. The field is suppressed instead of guessed: the frontend
    hides it on an empty value, and a blank is honest where a wrong parent is
    not.

    Client ruling (Sep 2026), which takes precedence over the checks below:
    the Company Hierarchy sheet's Parent Company Name is the parent when it is
    populated. A populated Parent Company Name is used as supplied, without
    being second-guessed against the description. When it is blank the parent
    relationship is ignored for now - blank means "not established", never a
    reason to go looking for one elsewhere.

    Below that rule, an Ultimate Parent Name is still only displayed when the
    row actually establishes one. Two things make it untrustworthy:

    1. It is self-referential - Ultimate Parent Id equals Business Id. A company
       is not its own ultimate parent; this is how the vendor encodes "no
       hierarchy known", and taking the name at face value asserts independence
       the file never claimed. Astra ships exactly this: both ids are
       8fe936f4..., Parent Company Name is empty, and Ultimate Parent Name is
       the company itself.

    2. It contradicts the description - the same vendor's Business Description
       ends "operates as a subsidiary of Jardine Cycle & Carriage Limited", and
       news_events independently says "controlled by Jardine Cycle & Carriage
       Limited". Two datasets against one.

    The contradicting name is deliberately NOT written into the field. It is
    reported on the flag for a human to confirm, because promoting prose parsed
    out of a description to ground truth is the silent swap this codebase avoids
    - the description is unstructured text, and "subsidiary of" there may mean a
    minority stake rather than an ultimate parent.
    """
    if not hier_row:
        return "", None

    def field(*names):
        for n in names:
            v = (hier_row.get(n) or "").strip()
            if v:
                return v
        return ""

    # Client ruling: a populated Parent Company Name settles the relationship.
    # It is taken as supplied - no self-reference or description check runs,
    # because those exist to stop an unestablished parent being displayed, and
    # this one is established by the sheet itself.
    parent_company_name = field("Parent Company Name", "parent_company_name")
    if parent_company_name:
        return parent_company_name, None

    ultimate_parent = field("Ultimate Parent Name", "ultimate_parent_name")
    if not ultimate_parent:
        return "", None

    business_id = field("Business Id", "business_id")
    ultimate_parent_id = field("Ultimate Parent Id", "ultimate_parent_id")

    self_referential = bool(business_id) and business_id == ultimate_parent_id
    stated = _subsidiary_of(business_description)
    contradicted = bool(stated) and _norm_company(stated) != _norm_company(ultimate_parent)

    if not (self_referential or contradicted):
        return ultimate_parent, None

    reasons = []
    if self_referential:
        reasons.append(
            "company_hierarchy is self-referential (Ultimate Parent Id equals "
            "Business Id), so it establishes no parent"
        )
    if contradicted:
        reasons.append(
            f"firmographics Business Description states the company is a "
            f"subsidiary of {stated!r}, which contradicts {ultimate_parent!r}"
        )

    return "", {
        "field": "ultimate_parent",
        "status": "needs_review",
        "suppressed_value": ultimate_parent,
        "stated_parent": stated or None,
        "reason": "; ".join(reasons),
    }


def _norm_company(name: str) -> str:
    """Company name reduced for comparison only - never for display."""
    out = (name or "").lower()
    for token in (" limited", " ltd", " tbk", " plc", " inc", " corporation",
                  " corp", " company", " co", "pt ", ".", ","):
        out = out.replace(token, " ")
    return " ".join(out.split())


def _subsidiary_of(description: str) -> str:
    """The parent named by a "subsidiary of X" clause, or "".

    Deliberately narrow: it matches the one phrasing this vendor uses to close a
    description and stops at the sentence end. It feeds a review flag, not a
    displayed value, so a miss costs a flag rather than a wrong parent on screen.
    """
    if not description:
        return ""
    lowered = description.lower()
    marker = "subsidiary of "
    idx = lowered.rfind(marker)
    if idx == -1:
        return ""
    tail = description[idx + len(marker):].strip()
    for stop in (".", ";", "\n"):
        cut = tail.find(stop)
        if cut != -1:
            tail = tail[:cut]
    return tail.strip()


def _cross_feature_counts(db, account_id: str) -> dict:
    """Counts owned by other features, for the dashboard's Quick Stats.

    Only a key that genuinely resolves is returned. A count that is missing stays
    missing, so the card renders a dash - a wrong number here reads as though it
    had been checked, which is exactly how "100 active urgent signals" (really
    100 job postings, against 8 real signals) survived on the dashboard.
    """
    def widget(key):
        found = db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": key})
        if not found or found.get("status") != "available":
            return None
        return found.get("data") or {}

    out = {}

    plays = widget("opportunity_narrative_plays")
    if plays is not None and isinstance(plays.get("opportunity_plays"), list):
        out["solution_narratives_count"] = len(plays["opportunity_plays"])

    signals = widget("news_signals_feed")
    if signals is not None and signals.get("total_signals_count") is not None:
        with contextlib.suppress(TypeError, ValueError):
            out["recent_signals_count"] = int(signals["total_signals_count"])

    return out


@requires_local_datasets(
    "company_hierarchy", "firmographics", "job_openings", "prospect_contacts",
)
def extract_executive_dashboard(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    firmo_rows = _read_dataset_csv(account_id, "firmographics")
    hier_rows = _read_dataset_csv(account_id, "company_hierarchy")
    job_rows = _read_dataset_csv(account_id, "job_openings")
    contact_rows = _read_dataset_csv(account_id, "prospect_contacts")

    results = []

    # 1. exec_summary_card
    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]

        # Extract location string
        city = (row.get("City Name") or row.get("city_name") or "").strip()
        region = (row.get("Region Name") or row.get("region_name") or "").strip()
        country = (row.get("Country Name") or row.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_location = ", ".join(loc_parts) if loc_parts else "N/A"

        # Extract industry
        naics = (row.get("Naics Description") or row.get("naics_description") or "").strip()
        sic = (row.get("Sic Code Description") or row.get("sic_code_description") or "").strip()
        linkedin_ind = (row.get("Linkedin Industry Category") or row.get("linkedin_industry_category") or "").strip()
        ind_parts = [p for p in [linkedin_ind, naics, sic] if p]
        industry_classification = " / ".join(list(dict.fromkeys(ind_parts))) if ind_parts else "N/A"

        business_description = (row.get("Business Description") or "").strip()

        # Hierarchy fields
        parent_company = ""
        h_row = hier_rows[0] if hier_rows else None
        if h_row:
            parent_company = (h_row.get("Parent Company Name") or h_row.get("parent_company_name") or "").strip()

        # Suppressed rather than guessed when the hierarchy row cannot establish
        # a parent - see _resolve_ultimate_parent.
        ultimate_parent, parent_review_flag = _resolve_ultimate_parent(
            h_row, business_description)

        summary_data = {
            "company_name": (row.get("Company Name") or row.get("Name") or "").strip(),
            "domain": (row.get("Company Domain") or row.get("Website") or "").strip(),
            "business_description": business_description,
            "industry_classification": industry_classification,
            "hq_location": hq_location,
            "parent_company": parent_company,
            "ultimate_parent": ultimate_parent,
            "stakeholders_mapped_count": len(contact_rows),
            # Counts the dashboard's Quick Stats shows that belong to other
            # features. They are resolved here, server-side, because the
            # frontend loads widgets one feature at a time - asking it for
            # another feature's widget returns nothing, which is how these two
            # came to be a hardcoded 5 and a mislabelled job-postings count.
            #
            # Read from the owning widget rather than recomputed: both are
            # derived outputs, and the signal count in particular is the result
            # of a gate (55 raw, 45 rejected, deduped to 8). Recounting the CSV
            # here would quietly disagree with the feature that owns it.
            #
            # Absent when that feature has not run yet, and the card shows a
            # dash rather than a number.
            **_cross_feature_counts(db, account_id),
        }

        # Present only when something was actually suppressed, so a clean
        # account's payload keeps the shape it had before this existed.
        if parent_review_flag:
            summary_data["review_flags"] = [parent_review_flag]

        summary_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_summary_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": summary_data,
            "source_datasets": ["firmographics", "company_hierarchy", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        summary_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_summary_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "company_hierarchy"],
            "extracted_at": now,
            "updated_at": now
        }

    # Upsert exec_summary_card in MongoDB account_widgets
    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"},
        {"$set": summary_payload},
        upsert=True
    )
    results.append(summary_payload)

    # 2. exec_key_metrics
    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]
        emp_count = (row.get("Number Of Employees Range") or row.get("number_of_employees_range") or "").strip()
        revenue = (row.get("Yearly Revenue Range") or row.get("yearly_revenue_range") or "").strip()

        metrics_data = {
            "employee_count": emp_count if emp_count else "N/A",
            "revenue": revenue if revenue else "N/A"
        }

        metrics_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_key_metrics",
            "data_classification": "deterministic",
            "status": "available",
            "data": metrics_data,
            "source_datasets": ["firmographics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        metrics_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_key_metrics",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_key_metrics"},
        {"$set": metrics_payload},
        upsert=True
    )
    results.append(metrics_payload)

    # 3. exec_hiring_velocity
    if job_rows and len(job_rows) > 0:
        sample_roles = []
        for r in job_rows[:5]:
            t = (r.get("title") or r.get("normalized_title") or "").strip()
            if t and t not in sample_roles:
                sample_roles.append(t)

        hiring_data = {
            "open_job_count": len(job_rows),
            "sample_roles": sample_roles
        }

        hiring_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_hiring_velocity",
            "data_classification": "deterministic",
            "status": "available",
            "data": hiring_data,
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        hiring_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_hiring_velocity",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["job_openings"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "exec_hiring_velocity"},
        {"$set": hiring_payload},
        upsert=True
    )
    results.append(hiring_payload)

    # The urgency score. `build_urgency_score` computes and persists
    # `exec_urgency_score` itself, reading the datasets directly - it needs no
    # retrieval and no index. It was complete but unreferenced: nothing called
    # it, so the widget was never written and the card rendered empty.
    #
    # Wired here rather than left to be run by hand so it refreshes with the
    # rest of the feature whenever its datasets change.
    #
    # Never fatal. An account missing a driver's dataset gets an unavailable
    # driver and no composite, which is ABX's own missing-input rule; an
    # unexpected failure costs the account its urgency card, not its dashboard.
    try:
        from app.services.dashboard.urgency import build_urgency_score
        results.append(build_urgency_score(account_id))
    except Exception:
        logger.exception("executive_dashboard: urgency score failed for %s",
                         account_id)

    return results
