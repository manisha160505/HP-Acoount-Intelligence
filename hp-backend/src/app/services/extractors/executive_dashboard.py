import hashlib
import logging
from datetime import UTC, datetime

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.observability import pipeline
from app.services.dashboard import filings_register
from app.services.extractors.datasets import (
    DatasetFileMissing,
    account_display_name,
    dataset_file_paths,
    find_file_path,
    read_dataset_records,
    requires_local_datasets,
)
from app.services.extractors.grounding import (
    GroundingReport,
    build_corpus,
    check_text,
)
from app.services.regen import store as widget_store

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


# --------------------------------------------------------------------------
# The company profile, as bullets
# --------------------------------------------------------------------------
# The client, 27 Sep: "Need to break the below write up in bullets, right now is
# coming across as a dump of information and hard to read."
#
# The write-up is one vendor paragraph - Accenture's runs to 300 words in a
# single sentence-stack - and no upstream field carries it as parts. So it is
# reorganised here, once, at extraction: the bullets are stored on the widget
# and cached on a fingerprint, the same way every other generated field in this
# codebase is, rather than being made afresh on every page view where nothing
# would check them before a reader saw them.
#
# The model may ONLY reorganise. The paragraph is the sole source, the output is
# checked against it for invented figures, and a failed check publishes the
# paragraph rather than a bullet nobody can stand behind.
SUMMARY_PROMPT_VERSION = 1

DESCRIPTION_POINTS_MIN = 3
DESCRIPTION_POINTS_MAX = 5
# Below this there is nothing to break up, and a two-line description reads
# worse as a bullet than as a sentence.
DESCRIPTION_POINTS_MIN_WORDS = 40

POINTS_SYSTEM = """You reorganise one paragraph about a company into bullets for a sales reader.

You are NOT writing anything new. Every fact in your bullets must be in the paragraph you are given.

Rules:
- Between 3 and 5 bullets. Each one a complete sentence, at most 25 words.
- Lead each bullet with the specific thing - the business line, the market, the capability - not with the company name.
- Group related items from the paragraph into one bullet rather than listing everything twice.
- Copy every number, percentage and date exactly as written. Never add one, and never round.
- Never add a judgement, an implication for HP, or anything the paragraph does not say.
- Plain hyphens only. Do not use em dashes.
- Write in English even when the paragraph is not.

Return JSON only: {"points": ["...", "..."]}"""


def _description_fingerprint(description: str) -> str:
    return hashlib.sha256(
        ("%s|%s" % (SUMMARY_PROMPT_VERSION, description)).encode("utf-8")
    ).hexdigest()


def _description_points(db, account_id: str, description: str,
                        firmo_row: dict) -> tuple[list, str]:
    """(bullets, why it is what it is). Cached on the paragraph's fingerprint."""
    words = len(description.split())
    if words < DESCRIPTION_POINTS_MIN_WORDS:
        return [], ("the description is %d words - short enough to read as it is"
                    % words)

    fingerprint = _description_fingerprint(description)
    existing = widget_store.get(account_id, "exec_summary_card", db=db) or {}
    stored = existing.get("data") or {}
    if (stored.get("business_description_fingerprint") == fingerprint
            and stored.get("business_description_points")):
        pipeline.cache_hit("exec_summary_card business bullets")
        return (stored["business_description_points"],
                stored.get("business_description_points_basis") or "")

    result = generate_gpt4o_json_completion(
        POINTS_SYSTEM,
        "Paragraph:\n%s\n\nReturn JSON only." % description)
    raw = (result or {}).get("points") or []
    points = [" ".join(str(p).split()) for p in raw if str(p).strip()]
    points = points[:DESCRIPTION_POINTS_MAX]
    if len(points) < DESCRIPTION_POINTS_MIN:
        return [], "the model returned %d bullet(s); the paragraph is shown instead" % len(points)

    # The paragraph is the only source. A figure that is not in it was invented.
    ground = build_corpus({"firmographics": [firmo_row]})
    report = GroundingReport(ground, ["business_description_points"])
    bad_numbers, _bad_urls = check_text(ground, report, "business_description_points",
                                        *points)
    if bad_numbers:
        pipeline.guardrail(len(bad_numbers), "bullet quotes an unsourced figure",
                           figures=", ".join(bad_numbers[:3]))
        return [], ("bullets held back - they quoted %s, which the description "
                    "does not carry" % ", ".join(bad_numbers[:3]))

    return points, "reorganised from the description; no fact added"


@requires_local_datasets(
    "company_hierarchy", "firmographics", "job_openings",
)
@pipeline.feature("executive_dashboard")
def extract_executive_dashboard(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    firmo_rows = _read_dataset_csv(account_id, "firmographics")
    hier_rows = _read_dataset_csv(account_id, "company_hierarchy")
    job_rows = _read_dataset_csv(account_id, "job_openings")
    # The filings list: the CSV uploaded with the PDFs under compliance_filings.
    try:
        filing_files = dataset_file_paths(account_id, "compliance_filings", strict=False)
    except DatasetFileMissing:
        filing_files = []
    index_rows = filings_register.index_rows_from_files(filing_files)

    pipeline.step("datasets", "", firmographics=len(firmo_rows),
                  hierarchy=len(hier_rows), jobs=len(job_rows),
                  filings_list=len(index_rows))

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
        points, points_basis = _description_points(
            db, account_id, business_description, row)
        pipeline.step("summary", "%d bullet(s) - %s" % (len(points), points_basis))

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
            # The company profile, as bullets. See _description_points.
            "business_description_points": points,
            "business_description_points_basis": points_basis,
            "business_description_fingerprint":
                _description_fingerprint(business_description),
        }

        summary_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_summary_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": summary_data,
            "source_datasets": ["firmographics", "company_hierarchy"],
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
    widget_store.put(account_id, "exec_summary_card", summary_payload, db=db)
    results.append(summary_payload)

    # 2. exec_key_metrics
    # Filings on record: filings 1.csv + PredictLeads sec_filings, the client's
    # definition (opens_1 answer 10), inside the 12-month window. Listed beside
    # the bands, never in place of them - the reported figures themselves come
    # from reading the documents (exec_strategic_priorities), not from here.
    filings = filings_register.register(index_rows)
    filings_sources = ["compliance_filings"] if index_rows else []

    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]
        emp_count = (row.get("Number Of Employees Range") or row.get("number_of_employees_range") or "").strip()
        revenue = (row.get("Yearly Revenue Range") or row.get("yearly_revenue_range") or "").strip()

        metrics_data = {
            "employee_count": emp_count if emp_count else "N/A",
            "revenue": revenue if revenue else "N/A",
            "filings_on_record": filings,
        }

        metrics_payload = {
            "account_id": account_id,
            "feature_key": "executive_dashboard",
            "widget_key": "exec_key_metrics",
            "data_classification": "deterministic",
            "status": "available",
            "data": metrics_data,
            "source_datasets": ["firmographics", *filings_sources],
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

    widget_store.put(account_id, "exec_key_metrics", metrics_payload, db=db)
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

    widget_store.put(account_id, "exec_hiring_velocity", hiring_payload, db=db)
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
