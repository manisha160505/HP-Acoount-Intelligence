import os
import io
import csv
import pandas as pd
from datetime import datetime, timezone
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.recent_news_signals import extract_recent_news_signals

def _find_file_path(rel_path: str) -> str | None:
    if not rel_path:
        return None
    candidate_paths = [
        os.path.join(os.getcwd(), rel_path),
        os.path.join("/app", rel_path),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", rel_path)),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", rel_path)),
        os.path.join(r"C:\hp-account\HP-Acoount-Intelligence\hp-backend", rel_path)
    ]
    for cp in candidate_paths:
        if os.path.exists(cp):
            return cp
    return None

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    db = get_db()
    file_doc = db["account_data_files"].find_one({
        "account_id": account_id,
        "$or": [{"dataset_key": dataset_key}, {"category": dataset_key}],
        "status": "active"
    })
    
    if not file_doc:
        return []
    
    rel_path = file_doc.get("file_path", "")
    full_path = _find_file_path(rel_path)
    
    if not full_path or not os.path.exists(full_path):
        return []
    
    ext = os.path.splitext(full_path)[1].lower()
    try:
        if ext in [".xlsx", ".xls"]:
            df = pd.read_excel(full_path)
            df = df.fillna("")
            return df.to_dict(orient="records")
        else:
            with open(full_path, "r", encoding="utf-8-sig", errors="replace") as f:
                reader = csv.DictReader(f)
                return [row for row in reader]
    except Exception:
        return []

def generate_opportunity_map_plays_with_gpt4o(account_id: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)

    # 1. Load account-agnostic company identity
    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    # 2. Read ONLY the 5 approved datasets
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_records = _read_dataset_records(account_id, "intent_score")
    gnews_records = _read_dataset_records(account_id, "google_news")
    events_records = _read_dataset_records(account_id, "news_events")

    # 3. Read account-specific runtime instructions & guardrails
    inst_doc = db["account_instructions"].find_one({"account_id": account_id})
    guard_doc = db["account_guardrails"].find_one({"account_id": account_id})
    instructions_text = inst_doc.get("instructions_text", "").strip() if inst_doc else ""
    guardrails_text = guard_doc.get("guardrails_text", "").strip() if guard_doc else ""

    # Parse Firmographics
    domain_val = "N/A"
    industry_val = "N/A"
    hq_val = "N/A"
    revenue_val = "N/A"
    emp_val = "N/A"
    bus_desc = ""

    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]
        c_name = str(f.get("Company Name") or f.get("company_name") or f.get("Name") or "").strip()
        if c_name:
            company_name = c_name
        domain_val = str(f.get("Company Domain") or f.get("company_domain") or f.get("Domain") or f.get("Website") or "N/A").strip()
        bus_desc = str(f.get("Business Description") or f.get("business_description") or "").strip()
        
        city = str(f.get("City Name") or "").strip()
        country = str(f.get("Country Name") or "").strip()
        hq_val = f"{city}, {country}".strip(", ") if (city or country) else "N/A"
        
        linkedin_ind = str(f.get("Linkedin Industry Category") or "").strip()
        naics = str(f.get("Naics Description") or "").strip()
        industry_val = linkedin_ind or naics or "N/A"

        emp_val = str(f.get("Number Of Employees Range") or "N/A").strip()
        revenue_val = str(f.get("Yearly Revenue Range") or "N/A").strip()

    # Parse Technographics
    full_tech_stack = []
    if techno_records and len(techno_records) > 0:
        raw_stack = str(techno_records[0].get("Full Tech Stack") or "").strip()
        if raw_stack:
            full_tech_stack = [s.strip() for s in raw_stack.split(",") if s.strip()]

    # Parse Intent Topics
    intent_topics_str_list = []
    for r in intent_records[:10]:
        t_name = str(r.get("Topic") or r.get("topic_name") or "").strip()
        c_score = str(r.get("Composite Score") or r.get("composite_score") or "").strip()
        if t_name:
            intent_topics_str_list.append(f"- {t_name} (Composite Score: {c_score})")

    # Parse News & Trigger Events
    news_triggers = []
    seen_headlines = set()

    for row in gnews_records + events_records:
        headline = str(row.get("event_headline") or row.get("news_announcements") or row.get("title") or "").strip()
        e_date = str(row.get("event_date") or row.get("date") or "").strip()
        e_type = str(row.get("event_type") or "News Event").strip()
        s_url = str(row.get("event_url") or row.get("source_url") or "").strip()

        if headline and headline.lower() not in seen_headlines:
            seen_headlines.add(headline.lower())
            news_triggers.append({
                "headline": headline,
                "date": e_date,
                "type": e_type,
                "url": s_url
            })

    news_triggers_str_list = [f"- [{trig['type']}] {trig['headline']} ({trig['date']}) | URL: {trig['url'] if trig['url'] else 'None'}" for trig in news_triggers[:10]]

    # Build Prompt
    system_prompt = f"""You are an expert ABM strategist for HP Inc. ("HP"). You are helping the HP sales team identify strategic HP hardware and solution opportunity plays for {company_name}.

ACCOUNT OVERVIEW:
- Company: {company_name}
- Domain: {domain_val}
- Industry: {industry_val}
- HQ Location: {hq_val}
- Revenue Range: {revenue_val}
- Employee Count Range: {emp_val}
- Business Description: {bus_desc if bus_desc else 'N/A'}

INSTALLED TECHNOLOGY STACK ({len(full_tech_stack)} items):
{', '.join(full_tech_stack[:40]) if full_tech_stack else 'None detected in exports.'}

INTENT RESEARCH SURGES:
{chr(10).join(intent_topics_str_list) if intent_topics_str_list else 'None detected.'}

VERIFIED LIVE NEWS & TRIGGER EVENTS ({len(news_triggers)} events):
{chr(10).join(news_triggers_str_list) if news_triggers_str_list else 'None detected.'}

ACCOUNT-SPECIFIC CUSTOM INSTRUCTIONS:
{instructions_text if instructions_text else 'None provided.'}

ACCOUNT-SPECIFIC MANDATORY GUARDRAILS:
{guardrails_text if guardrails_text else 'None provided.'}

CRITICAL RULES:
1. You represent HP Inc. Never reference Dell, Lenovo, Huawei, Acer, or Zoom as "our" product.
2. Ground every recommendation in the specific account evidence above. Only use the provided data - never invent facts that are not in this context.
3. Reference specific HP products by name (Z Workstations, EliteBook/ProBook PCs, HP Wolf Security, Poly Studio, HP Enterprise Printing/MPS, HP DaaS, HP Anyware).
4. "summary": Provide a rich 2-3 sentence strategic summary narrative linking the account's operational context (automotive, heavy equipment, logistics, financial services, IT) to the HP hardware line.
5. "how_hp_enables": Provide a comprehensive 3-4 sentence paragraph detailing the exact team (e.g. CAD engineering, software developers, IT operations), software compatibility (AutoCAD, CATIA, SAP, Azure), product fit, and why the procurement window is open now.
6. "quantified_impact": MUST BE null UNLESS an exact numeric figure (e.g. "IDR 36 trillion capex", "10,000+ employees", "10% YoY increase") exists verbatim in the supplied evidence above. If no exact number exists, set "quantified_impact" to null.
7. "proof_point" and "source_url": MUST come EXCLUSIVELY from the provided VERIFIED LIVE NEWS & TRIGGER EVENTS list above. Copy the EXACT URL string from the list. Do NOT invent or alter URLs.
8. Output JSON format matching:
{{
  "opportunity_plays": [
    {{
      "play_key": "workstation | poly | pc | print | daas",
      "category_label": "WORKSTATION | POLY | PC | PRINT | DAAS",
      "title": "Z by HP Workstations | Poly collaboration hardware | HP Elite & Pro PCs | HP Enterprise Printing & MPS | HP DaaS",
      "severity": "Critical | High | Medium",
      "summary": "Rich 2-3 sentence strategic summary narrative linking the account's operational context to the HP hardware line.",
      "how_hp_enables": "Comprehensive 3-4 sentence paragraph explaining how HP hardware enables the outcome, referencing software stack and specific teams.",
      "hp_products": ["HP Product Tag 1", "HP Product Tag 2"],
      "hp_resource_url": "https://www.hp.com/us-en/workstations/workstation-solutions.html",
      "quantified_impact": "Exact numeric figure string or null",
      "quantified_impact_title": "Detailed headline title for HP-Modeled Quantified Impact box",
      "how_hp_calculated_this": "2-3 sentence explanation of how HP calculated this impact by cross-referencing account headcount, tech stack, and intent surges.",
      "proof_point": "Verbatim signal citation from the provided trigger events",
      "source_type": "SEC 20-F | Google News | News Event",
      "source_url": "Verbatim source URL from the provided trigger events or null",
      "entry_path": {{
        "timeline": "0-90 days | 90-180 days",
        "target_buyers": ["Infrastructure Strategy & Commercial team", "Regional IT Procurement Manager"],
        "recommended_cta": "Open a scoping conversation on Workstation with Infrastructure Strategy & Commercial team, Regional IT Procurement Manager."
      }}
    }}
  ]
}}
"""

    user_prompt = f"Analyze the account evidence for {company_name} and generate 5 detailed HP solution opportunity plays in JSON format matching the schema."

    # Call GPT-4o
    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)

    if llm_res and isinstance(llm_res, dict) and "opportunity_plays" in llm_res:
        plays = llm_res.get("opportunity_plays", [])
        cleaned_plays = []
        for p in plays:
            impact_val = p.get("quantified_impact")
            if impact_val and not any(char.isdigit() for char in str(impact_val)):
                impact_val = None

            entry_p = p.get("entry_path") or {}
            buyers = entry_p.get("target_buyers") if isinstance(entry_p.get("target_buyers"), list) else ["IT Procurement Manager", "Infrastructure Strategy Team"]

            pk = str(p.get("play_key") or "play").lower()
            if "workstation" in pk:
                res_url = "https://www.hp.com/us-en/workstations.html"
            elif "poly" in pk:
                res_url = "https://www.hp.com/us-en/poly.html"
            elif "pc" in pk:
                res_url = "https://www.hp.com/us-en/laptops.html"
            elif "print" in pk:
                res_url = "https://www.hp.com/us-en/services/workforce-solutions/document-printing/managed-print-services.html"
            elif "daas" in pk:
                res_url = "https://www.hp.com/us-en/services/workforce-solutions/workforce-computing/managed-device-services.html"
            elif "security" in pk or "wolf" in pk:
                res_url = "https://www.hpwolf.com/"
            else:
                res_url = "https://www.hp.com/us-en/services/workforce-solutions/learning-hub.html"

            cleaned_plays.append({
                "play_key": str(p.get("play_key") or "play"),
                "category_label": str(p.get("category_label") or p.get("play_key", "PLAY")).upper(),
                "title": str(p.get("title") or "HP Opportunity Play"),
                "severity": str(p.get("severity") or "High"),
                "summary": str(p.get("summary") or ""),
                "how_hp_enables": str(p.get("how_hp_enables") or ""),
                "hp_products": p.get("hp_products", []),
                "hp_resource_url": res_url,
                "quantified_impact": impact_val,
                "quantified_impact_title": str(p.get("quantified_impact_title") or p.get("title", "")),
                "how_hp_calculated_this": str(p.get("how_hp_calculated_this") or f"Derived from HP Scoring Engine account intelligence for {company_name}."),
                "proof_point": str(p.get("proof_point") or ""),
                "source_type": str(p.get("source_type") or "Google News"),
                "source_url": p.get("source_url"),
                "entry_path": {
                    "timeline": str(entry_p.get("timeline") or "0-90 days"),
                    "target_buyers": buyers,
                    "recommended_cta": str(entry_p.get("recommended_cta") or f"Open a scoping conversation with {', '.join(buyers)}.")
                }
            })

        plays_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_narrative_plays",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "total_plays_count": len(cleaned_plays),
                "opportunity_plays": cleaned_plays
            },
            "source_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        existing_doc = db["account_widgets"].find_one({
            "account_id": account_id,
            "widget_key": "opportunity_narrative_plays",
            "status": "available"
        })

        if existing_doc:
            return existing_doc

        plays_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_narrative_plays",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "total_plays_count": 0,
                "opportunity_plays": [],
                "notice": "Opportunity Map AI generation requires OPENAI_API_KEY. Click 'Generate Opportunity Map' when API key is configured."
            },
            "source_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_narrative_plays"},
        {"$set": plays_payload},
        upsert=True
    )
    return plays_payload

def extract_solution_narrative_opportunity_map(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)
    
    firmo_records = _read_dataset_records(account_id, "firmographics")
    techno_records = _read_dataset_records(account_id, "technographics")
    intent_records = _read_dataset_records(account_id, "intent_score")
    
    results = []

    # 1. Widget: opportunity_context_card
    bus_desc = ""
    if firmo_records and len(firmo_records) > 0:
        bus_desc = (str(firmo_records[0].get("Business Description") or "")).strip()

    tech_stack_items = []
    if techno_records and len(techno_records) > 0:
        raw_stack = (str(techno_records[0].get("Full Tech Stack") or "")).strip()
        if raw_stack:
            tech_stack_items = [s.strip() for s in raw_stack.split(",") if s.strip()]

    top_intent_topics = []
    for r in intent_records:
        t_name = (str(r.get("Topic") or "")).strip()
        c_score_raw = (str(r.get("Composite Score") or "0")).strip()
        try:
            c_score = int(float(c_score_raw))
        except (ValueError, TypeError):
            c_score = 0

        if t_name:
            top_intent_topics.append({
                "topic_name": t_name,
                "composite_score": c_score
            })

    top_intent_topics.sort(key=lambda x: x["composite_score"], reverse=True)

    has_context = bool(bus_desc or tech_stack_items or top_intent_topics)

    if has_context:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "business_description": bus_desc,
                "full_tech_stack_sample": tech_stack_items,
                "total_tech_items_count": len(tech_stack_items),
                "top_intent_topics": top_intent_topics[:10],
                "total_intent_topics_count": len(top_intent_topics)
            },
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        context_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_context_card",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_context_card"},
        {"$set": context_payload},
        upsert=True
    )
    results.append(context_payload)

    # 2. Widget: opportunity_trigger_signals
    news_res = extract_recent_news_signals(account_id)
    news_signals = news_res[0]["data"].get("signals", []) if (news_res and news_res[0]["status"] == "available") else []

    if news_signals:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_trigger_count": len(news_signals),
                "triggers": news_signals
            },
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        triggers_payload = {
            "account_id": account_id,
            "feature_key": "solution_narrative_opportunity_map",
            "widget_key": "opportunity_trigger_signals",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["google_news", "news_events"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "opportunity_trigger_signals"},
        {"$set": triggers_payload},
        upsert=True
    )
    results.append(triggers_payload)

    # 3. Widget: opportunity_narrative_plays
    existing_plays_doc = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "opportunity_narrative_plays"
    })

    if existing_plays_doc and existing_plays_doc.get("status") == "available":
        results.append(existing_plays_doc)
    else:
        gen_payload = generate_opportunity_map_plays_with_gpt4o(account_id)
        results.append(gen_payload)

    return results
