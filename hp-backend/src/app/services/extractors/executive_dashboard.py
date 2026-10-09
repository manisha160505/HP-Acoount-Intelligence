import hashlib
import logging
import re
from datetime import UTC, datetime

from app.config import account_overrides
from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.observability import pipeline
from app.services.dashboard import filings_financials, filings_register
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
from app.services.hp import company_relationships, translate
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

# Words that do not tell one company from another, dropped before a parent's
# name is compared with the account's own.
_LEGAL_WORDS = {
    "pt", "tbk", "inc", "ltd", "limited", "co", "corporation", "corp", "company",
    "group", "groups", "holdings", "holding", "plc", "public", "persero", "the",
    "pte", "sdn", "bhd", "kk", "kabushiki", "kaisha",
}


def _account_key(name: str) -> str:
    """The account's name without its ' - XX' country suffix, lowercased."""
    name = " ".join(str(name or "").lower().split())
    head, sep, tail = name.rpartition(" - ")
    return head if sep and len(tail) == 2 else name


def _name_words(name: str) -> list[str]:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in _account_key(name))
    return [w for w in cleaned.split() if w not in _LEGAL_WORDS]


def _is_own_name(candidate: str, account_name: str, exact: bool = False) -> bool:
    """True when `candidate` is the account itself: 'canon' for 'CANON INC. -
    JP'. Unless `exact`, a name the account's own name starts with also counts
    ('mitsubishi' for MITSUBISHI MOTORS) - right for a parent, wrong for a
    subsidiary ('toyota motor' is Toyota Group's subsidiary, not Toyota)."""
    a, b = _name_words(candidate), _name_words(account_name)
    if not a or not b:
        return False
    return a == b if exact else (len(a) <= len(b) and b[:len(a)] == a)


def _resolve_parent(hier_row: dict | None, account_name: str = "") -> tuple[str, str | None]:
    """(parent to display, the column it came from) from the Company Hierarchy
    sheet.

    Client, 5 Oct (issue list v3): the parent is column E, Ultimate Parent
    Name. It is shown as supplied unless it is the account itself - Ultimate
    Parent Id equal to Business Id, or the account's own name ('canon' for
    Canon Inc.). Where column E gives no other company, column C (Parent
    Company Name, the September rule) is used under the same test, so a parent
    the sheet does name is not lost. Nothing else is read: no 'subsidiary of'
    clause in the Business Description.

    Explorium only. `_parents` decides what is shown: the client's 7 Oct
    mapping replaces this for the accounts it covers. An account flagged
    `hide_parent_company` in config/account_overrides.yaml (client, 8 Oct
    mechanism) shows no parent at all, whatever any source says.
    """
    if not hier_row or account_overrides.hides_parent(account_name):
        return "", None
    bid = str(hier_row.get("Business Id") or "").strip()
    upid = str(hier_row.get("Ultimate Parent Id") or "").strip()
    candidates = (
        (hier_row.get("Ultimate Parent Name") or hier_row.get("ultimate_parent_name"),
         "Ultimate Parent Name", bool(bid) and upid == bid),
        (hier_row.get("Parent Company Name") or hier_row.get("parent_company_name"),
         "Parent Company Name", False),
    )
    for value, column, is_self in candidates:
        value = " ".join(str(value or "").split())
        if (not value or is_self
                or (account_name and _is_own_name(value, account_name))):
            continue
        return value, column
    return "", None


MAPPING_SOURCE = "Client parent-company mapping (7 Oct)"
MERGED_SOURCE = "Merged company hierarchy (7 Oct)"


def _parents(hier_row: dict | None, account_name: str = "") -> tuple[list[str], list[str]]:
    """(parents to display, where they came from), in display order.

    Client, 7 Oct. For the 11 accounts in the client's parent-company mapping,
    the mapping is the answer, Explorium is not read, and "no parent" means
    nothing is shown. Its names are shown as written - 'BHP Group Limited' for
    BHP Billiton, which the own-name rule would otherwise hide - unless one is
    exactly the account itself.

    An account flagged `hide_parent_company` in config/account_overrides.yaml
    shows none at all; that is checked first and overrides every source.

    For every other account: Explorium's parent (`_resolve_parent`), then any
    parent the merged hierarchy sheet adds. A company can have two - a direct
    parent and an ultimate one - and both are shown. The sheet's rows were
    reviewed for self-references when the file was built, so they are only
    dropped here when they repeat a parent already listed or are exactly the
    account's own name ('Kuok Group' stays for Kuok (Singapore)).
    """
    if account_overrides.hides_parent(account_name):
        return [], []
    rel = company_relationships.for_account(account_name)
    if rel["override"] is not None:
        parents = [p for p in rel["override"]
                   if p and not (account_name and _is_own_name(p, account_name, exact=True))]
        return parents, [MAPPING_SOURCE] if parents else []

    parents, sources = [], []
    explorium, column = _resolve_parent(hier_row, account_name)
    if explorium:
        parents.append(explorium)
        sources.append("Company Hierarchy - " + column)
    seen = {p.lower() for p in parents}
    for p in rel["parents"]:
        if (not p or p.lower() in seen
                or (account_name and _is_own_name(p, account_name, exact=True))):
            continue
        seen.add(p.lower())
        parents.append(p)
        if MERGED_SOURCE not in sources:
            sources.append(MERGED_SOURCE)
    return parents, sources


def _in_english(db, names: list[str]) -> tuple[list[str], dict]:
    """(names in English, {English: as supplied}) - order kept, and a name
    that becomes a repeat of one already listed is dropped. The mapping is
    empty when nothing needed translating."""
    english = translate.to_english(names, db, "company")
    if not english:
        return list(names), {}
    out, original, seen = [], {}, set()
    for name in names:
        shown = english.get(" ".join(name.split()), name)
        if shown.lower() in seen:
            continue
        seen.add(shown.lower())
        out.append(shown)
        if shown != name:
            original[shown] = name
    return out, original


def _filings_in_english(db, filings: list, reported: list, chief: dict | None) -> None:
    """Filing titles, figure labels and the CEO in English, in place (client,
    9 Oct). Japanese filings are titled "有価証券報告書 ..." and print their tables
    in Japanese. The original stays beside each value for the hover; a figure's
    `quote` is the row as printed and is never rewritten - `quote_en` is added.
    """
    def apply(items, field, kind, keep_as=None):
        english = translate.to_english([i.get(field) for i in items], db, kind)
        for item in items:
            value = " ".join(str(item.get(field) or "").split())
            if value in english:
                if keep_as:
                    item[keep_as] = english[value]
                else:
                    item[field + "_original"] = item[field]
                    item[field] = english[value]

    filings, reported = filings or [], reported or []
    chief_list = [chief] if chief else []
    apply(filings, "title", "document")
    apply(reported, "filing_label", "document")
    apply(reported, "quote", "table_row", keep_as="quote_en")
    apply(chief_list, "filing_label", "document")
    apply(chief_list, "name", "person")
    apply(chief_list, "title", "job_title")


_GOVERNMENT = re.compile(r"\bgovernment\b")


def _subsidiaries(rows: list[dict], account_name: str, parent) -> list[str]:
    """Column A of the Subsidiaries sheet (Subsidiary Name), as supplied, in
    file order, then the merged hierarchy sheet's subsidiaries for the account
    (client, 7 Oct): blanks and repeats dropped, and the account and its
    parents left out, since none of them is a subsidiary of the account.
    `parent` is one name or a list of them.

    A government is never a subsidiary: Explorium lists "japan the government of
    japan" - a shareholder - as a subsidiary of eight Japanese accounts
    (Advantest, IHI, JAL, Konica Minolta, Marubeni, Nissan, Shiseido...), and
    "queensland government" under Coles. Only the word "government" is matched;
    "commonwealth superannuation" and "daikin czech republic" are real
    subsidiaries."""
    parents = [parent] if isinstance(parent, str) else list(parent or [])
    excluded = {p.lower() for p in parents if p}
    merged = [{"Subsidiary Name": s}
              for s in company_relationships.for_account(account_name)["subsidiaries"]]
    out, seen = [], set()
    for row in list(rows or []) + merged:
        value = row.get("Subsidiary Name")
        if value is None and row:
            value = next(iter(row.values()))  # column A
        value = " ".join(str(value or "").split())
        key = value.lower()
        if (not value or key in seen or key in excluded
                or _GOVERNMENT.search(key)
                or (account_name and _is_own_name(value, account_name, exact=True))):
            continue
        seen.add(key)
        out.append(value)
    return out


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
    "company_hierarchy", "firmographics", "job_openings", "subsidiaries",
)
@pipeline.feature("executive_dashboard")
def extract_executive_dashboard(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    firmo_rows = _read_dataset_csv(account_id, "firmographics")
    hier_rows = _read_dataset_csv(account_id, "company_hierarchy")
    subsidiary_rows = _read_dataset_csv(account_id, "subsidiaries")
    # The filings list: the CSV uploaded with the PDFs under compliance_filings.
    try:
        filing_files = dataset_file_paths(account_id, "compliance_filings", strict=False)
    except DatasetFileMissing:
        filing_files = []
    index_rows = filings_register.index_rows_from_files(filing_files)

    pipeline.step("datasets", "", firmographics=len(firmo_rows),
                  hierarchy=len(hier_rows), subsidiaries=len(subsidiary_rows),
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

        # Blank unless the hierarchy sheet names another company - see
        # _resolve_parent. Subsidiaries are column A of the Subsidiaries sheet.
        company_name = account_display_name(account_id, row)
        parents, parent_sources = _parents(
            hier_rows[0] if hier_rows else None, company_name)
        subsidiaries = _subsidiaries(subsidiary_rows, company_name, parents)
        # In English for the card (client, 9 Oct), translated only now so the
        # own-name and parent exclusions above compared the names as supplied.
        parents, parents_original = _in_english(db, parents)
        subsidiaries, subsidiaries_original = _in_english(db, subsidiaries)

        summary_data = {
            # DEC-052: the audit sheet's name, held on the account record,
            # not the vendor's name for the domain.
            "company_name": company_name,
            "domain": (row.get("Company Domain") or row.get("Website") or "").strip(),
            "business_description": business_description,
            "industry_classification": industry_classification,
            "hq_location": hq_location,
            # One string for every reader that predates two parents (Strategy
            # Chat's corpus, older screens); the list is what the card shows.
            "parent_company": " · ".join(parents),
            "parent_companies": parents,
            "parent_company_source": "; ".join(parent_sources) or None,
            "subsidiaries": subsidiaries,
            "subsidiaries_count": len(subsidiaries),
            # The names as supplied, beside the English, for the hover. Only
            # present when something was translated.
            **({"parent_companies_original": parents_original} if parents_original else {}),
            **({"subsidiaries_original": subsidiaries_original}
               if subsidiaries_original else {}),
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
            "source_datasets": ["firmographics", "company_hierarchy", "subsidiaries"],
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
            "source_datasets": ["firmographics", "company_hierarchy", "subsidiaries"],
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
    financial_rows = _read_dataset_csv(account_id, "filings_financials")
    reported = filings_financials.reported_metrics(financial_rows)
    chief_executive = filings_financials.ceo(financial_rows)
    _filings_in_english(db, filings, reported, chief_executive)
    if reported or chief_executive:
        filings_sources.append(filings_financials.SOURCE)

    if firmo_rows and len(firmo_rows) > 0:
        row = firmo_rows[0]
        emp_count = (row.get("Number Of Employees Range") or row.get("number_of_employees_range") or "").strip()
        revenue = (row.get("Yearly Revenue Range") or row.get("yearly_revenue_range") or "").strip()

        metrics_data = {
            "employee_count": emp_count if emp_count else "N/A",
            "revenue": revenue if revenue else "N/A",
            "filings_on_record": filings,
        }
        # Filed figures from the filings index (scripts/filings_to_csv.py), one
        # value per metric chosen across every filing. Only set when the file
        # is uploaded and shows something: otherwise the card keeps reading
        # the figures on exec_strategic_priorities, as before.
        if reported:
            metrics_data["reported_metrics"] = reported
            metrics_data["reported_metric_count"] = len(reported)
            metrics_data["reported_source"] = filings_financials.SOURCE
        # The header's CEO (Feature 1), from the newest filing naming one.
        if chief_executive:
            metrics_data["ceo"] = chief_executive

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

    # The job postings tile reads `hiring_postings_summary`, the one hiring
    # output (extractors/hiring_signals.py). This feature computes no job count.

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
