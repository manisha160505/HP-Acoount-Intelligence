import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    find_file_path, read_dataset_records, requires_local_datasets,
)

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

# Titles that carry no useful remit for message targeting.
_UNUSABLE_TITLE = ("unknown", "n/a", "-", "")


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _personas_from_contacts(db, account_id: str, contacts_records: list) -> list:
    """Named personas, from this account's roster.

    The Stakeholder Map has already scored these people - seniority band,
    influence type, normalised department, HP relevance - so that work is
    reused rather than repeated here. Every field is labelled with where it
    came from, so the UI can show provenance the way the reference app does
    instead of implying everything is account intelligence.
    """
    grid = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "stakeholder_contacts_grid"}) or {}
    scored = {str(c.get("contact_id")): c
              for c in ((grid.get("data") or {}).get("contacts") or [])}

    talking = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "stakeholder_talking_points"}) or {}
    talking_points = (talking.get("data") or {}).get("talking_points") or {}

    personas, seen = [], set()
    for row in contacts_records:
        name = _clean(row.get("Prospect full_name") or row.get("full_name"))
        title = _clean(row.get("Prospect job_title") or row.get("title"))
        if not name or not title or title.lower() in _UNUSABLE_TITLE:
            continue

        key = (name.lower(), title.lower())
        if key in seen:
            continue
        seen.add(key)

        contact_id = str(row.get("contact_id") or row.get("Prospect id") or "").strip()
        enriched = scored.get(contact_id) or next(
            (c for c in scored.values()
             if _clean(c.get("full_name")).lower() == name.lower()), {})
        points = talking_points.get(str(enriched.get("contact_id") or contact_id)) or {}

        department = _clean(row.get("Prospect job_department") or row.get("department"))
        department_column = "Prospect job_department" if department else None
        if not department:
            department = _clean(row.get("Prospect job_department_main"))
            department_column = "Prospect job_department_main" if department else None

        personas.append({
            "persona_id": "contact::%s" % (enriched.get("contact_id") or contact_id or name),
            "is_named_person": True,
            "name": name,
            "title": title,
            # The raw department column, never a tidied-up invention. The
            # Stakeholder Map's normalised value is carried alongside it.
            #
            # `job_department` is populated for only some of the roster, while
            # `job_department_main` is populated for nearly all of it, so the
            # second is used when the first is blank. Both are the account's own
            # columns - this picks a fuller one, it does not fill a gap in.
            "department": department,
            "department_column": department_column,
            "normalized_department": enriched.get("normalized_department"),
            "seniority_band": enriched.get("seniority_band"),
            "influence_type": enriched.get("influence_type"),
            "hp_relevance_band": enriched.get("hp_relevance_band"),
            "opening_angle": points.get("how_to_open"),
            "pain_points": points.get("pain_points") or [],
            "sources": {
                "name": "account_contact",
                "title": "account_contact",
                "department": "account_contact" if department else "not_available",
                "seniority_band": "account_contact" if enriched.get("seniority_band") else "not_available",
                "influence_type": "account_contact" if enriched.get("influence_type") else "not_available",
                "opening_angle": "account_evidence" if points.get("how_to_open") else "not_available",
                "pain_points": "account_evidence" if points.get("pain_points") else "not_available",
            },
        })
    return personas


def _personas_from_hiring(job_records: list) -> list:
    """Role personas, from open postings. No person is named.

    The fallback the 11-Features reference specifies for accounts whose
    prospect-contacts export is empty - which it notes was the case "in every
    verified test". The persona is a role backed by a posting count, so a
    seller can see exactly how thin the evidence is.
    """
    counts, seniority = {}, {}
    for row in job_records:
        title = _clean(row.get("normalized_title") or row.get("title"))
        if not title or title.lower() in _UNUSABLE_TITLE:
            continue
        counts[title] = counts.get(title, 0) + 1
        level = _clean(row.get("seniority"))
        if level and title not in seniority:
            seniority[title] = level

    personas = []
    for title, count in sorted(counts.items(), key=lambda kv: -kv[1])[:8]:
        personas.append({
            "persona_id": "role::%s" % title.lower().replace(" ", "_"),
            "is_named_person": False,
            "name": None,
            "title": title,
            "department": None,
            "normalized_department": None,
            "seniority_band": seniority.get(title),
            "influence_type": None,
            "hp_relevance_band": None,
            "opening_angle": None,
            "pain_points": [],
            "evidence_note": "role inferred from %d open posting%s; no named contact "
                             "exists for this account" % (count, "" if count == 1 else "s"),
            "posting_count": count,
            "sources": {
                "title": "hiring_role_proxy",
                "seniority_band": "hiring_role_proxy" if seniority.get(title) else "not_available",
                "name": "not_available",
                "department": "not_available",
                "influence_type": "not_available",
                "opening_angle": "not_available",
                "pain_points": "not_available",
            },
        })
    return personas


@requires_local_datasets(
    "firmographics", "job_openings", "prospect_contacts",
)
def extract_message_evaluator(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    contacts_records = _read_dataset_records(account_id, "prospect_contacts")
    
    results = []

    # Get dynamic company name
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"
    
    if firmo_records and len(firmo_records) > 0:
        f_name = str(firmo_records[0].get("Company Name") or firmo_records[0].get("company_name") or "").strip()
        if f_name:
            company_name = f_name

    # 1. Personas - every one of them from this account's own data.
    #
    # This used to start from five hardcoded "base personas" that named two real
    # Astra contacts ("Stephen Dharma", "Mochamad (ivan) Triawan") and attached
    # departments to them - IT Procurement, Technology Development, IT
    # Operations, Risk Advisory, Data Enablement - that appear nowhere in the
    # account. Real people, invented roles, and Astra's names would have been
    # offered on every other account too.
    #
    # The 11-Features sourcing reference defines the correct behaviour:
    # "persona defaults to Source A (Stakeholder Map), falls back to the
    # Source B hiring field when no named contact exists". So there are two
    # paths and neither invents a person.
    personas = _personas_from_contacts(db, account_id, contacts_records)
    persona_source = "prospect_contacts"

    if not personas:
        # No named contact in this account - build ROLE personas from open
        # postings. A role, never a name.
        personas = _personas_from_hiring(_read_dataset_records(account_id, "job_openings"))
        persona_source = "job_openings"

    persona_archetypes = personas

    # 2. Business Context
    business_context = {}
    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]
        
        c_name = str(f.get("Company Name") or f.get("company_name") or f.get("Name") or "").strip()
        domain_val = str(f.get("Company Domain") or f.get("company_domain") or f.get("Domain") or f.get("Website") or f.get("website") or "").strip()

        city = str(f.get("City Name") or f.get("city_name") or "").strip()
        region = str(f.get("Region Name") or f.get("region_name") or "").strip()
        country = str(f.get("Country Name") or f.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_loc_val = ", ".join(loc_parts) if loc_parts else str(f.get("HQ Location") or f.get("hq_location") or "").strip()

        linkedin_ind = str(f.get("Linkedin Industry Category") or f.get("linkedin_industry_category") or "").strip()
        naics = str(f.get("Naics Description") or f.get("naics_description") or "").strip()
        sic = str(f.get("Sic Code Description") or f.get("sic_code_description") or "").strip()
        ind_parts = [p for p in [linkedin_ind, naics, sic] if p]
        ind_val = " / ".join(list(dict.fromkeys(ind_parts))) if ind_parts else str(f.get("Industry Classification") or f.get("industry") or "").strip()

        emp_val = str(f.get("Number Of Employees Range") or f.get("employee_count_range") or f.get("Employee Count") or f.get("employee_count") or "").strip()
        rev_val = str(f.get("Yearly Revenue Range") or f.get("yearly_revenue_range") or f.get("Yearly Revenue") or f.get("revenue") or "").strip()

        business_context = {
            "company_name": c_name,
            "domain": domain_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

    # Widget 1: evaluator_persona_context (Deterministic)
    persona_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_persona_context",
        "data_classification": "deterministic",
        "status": "available",
        "data": {
            "company_name": company_name,
            "persona_archetypes": persona_archetypes,
            "persona_source": persona_source,
            "persona_count": len(persona_archetypes),
            "business_context": business_context
        },
        "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_persona_context"},
        {"$set": persona_payload},
        upsert=True
    )
    results.append(persona_payload)

    # Widget 2: evaluator_feedback_score (Inferred - Left as Pending / TBD)
    score_payload = {
        "account_id": account_id,
        "feature_key": "message_evaluator",
        "widget_key": "evaluator_feedback_score",
        "data_classification": "inferred",
        "status": "pending",
        "data": {
            "feedback_score": "Inferred TBD",
            "notice": "Message effectiveness scoring, guardrail rules evaluation, and rewrite recommendations using LLM prompts are TBD for Step 8 AI model execution."
        },
        "source_datasets": ["prospect_contacts", "job_openings"],
        "extracted_at": now,
        "updated_at": now
    }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "evaluator_feedback_score"},
        {"$set": score_payload},
        upsert=True
    )
    results.append(score_payload)

    return results
