import contextlib
import logging
from datetime import UTC, datetime

from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    account_display_name,
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

def _resolve_parent(hier_row: dict | None) -> str:
    """The parent to display: the Company Hierarchy sheet's Parent Company Name.

    Client ruling (Sep 2026): a populated Parent Company Name is the parent and
    is used as supplied. A blank one means the parent relationship is ignored
    for now - nothing is shown and nothing is flagged, and no parent is looked
    for anywhere else (Ultimate Parent Name, or a "subsidiary of" clause in the
    Business Description).
    """
    if not hier_row:
        return ""
    return (hier_row.get("Parent Company Name")
            or hier_row.get("parent_company_name") or "").strip()


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

        # Blank unless the hierarchy sheet names a parent - see _resolve_parent.
        parent_company = _resolve_parent(hier_rows[0] if hier_rows else None)

        summary_data = {
            # DEC-052: the audit sheet's name, held on the account record,
            # not the vendor's name for the domain.
            "company_name": account_display_name(account_id, row),
            "domain": (row.get("Company Domain") or row.get("Website") or "").strip(),
            "business_description": business_description,
            "industry_classification": industry_classification,
            "hq_location": hq_location,
            "parent_company": parent_company,
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
