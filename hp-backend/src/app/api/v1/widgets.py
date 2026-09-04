from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from bson import ObjectId
from app.database.mongodb import get_db
from app.core.deps import require_user_role, require_admin_role
from app.schemas.widget import WidgetContract, WidgetResponse
from app.services.extractors.executive_dashboard import extract_executive_dashboard
from app.services.extractors.recent_news_signals import extract_recent_news_signals
from app.services.extractors.intent_demand_signals import extract_intent_demand_signals
from app.services.extractors.solution_narrative_opportunity_map import extract_solution_narrative_opportunity_map
from app.services.extractors.stakeholder_map import extract_stakeholder_map
from app.services.extractors.tech_landscape import extract_tech_landscape

router = APIRouter(tags=["Widget Contracts & Dashboard Shell"])

WIDGET_REGISTRY = {
    "executive_dashboard": [
        {
            "widget_key": "exec_summary_card",
            "widget_name": "Executive Summary",
            "feature_key": "executive_dashboard",
            "description": "Company identity, domain, business description, industry classification, HQ location, and corporate hierarchy (Parent & Ultimate Parent)",
            "widget_type": "summary_card",
            "data_classification": "deterministic",
            "source_datasets": ["firmographics", "company_hierarchy"],
            "source_fields": ["company_name", "domain", "business_description", "industry_classification", "hq_location", "company_hierarchy"],
            "display_order": 1
        },
        {
            "widget_key": "exec_key_metrics",
            "widget_name": "Financial & Workforce Key Metrics",
            "feature_key": "executive_dashboard",
            "description": "Employee count range and yearly revenue metrics",
            "widget_type": "metric_grid",
            "data_classification": "deterministic",
            "source_datasets": ["firmographics"],
            "source_fields": ["employee_count", "revenue"],
            "display_order": 2
        },
        {
            "widget_key": "exec_hiring_velocity",
            "widget_name": "Hiring Velocity Signal",
            "feature_key": "executive_dashboard",
            "description": "Open job postings volume as role-proxy and urgency indicator",
            "widget_type": "metric_card",
            "data_classification": "deterministic",
            "source_datasets": ["job_openings"],
            "source_fields": ["hiring_velocity"],
            "display_order": 3
        },
        {
            "widget_key": "exec_urgency_score",
            "widget_name": "Urgency & Opportunity Score",
            "feature_key": "executive_dashboard",
            "description": "Derived composite account urgency score contract. Calculation logic and driver weights are TBD for future runtime calculation. Zero fabricated values.",
            "widget_type": "urgency_meter",
            "data_classification": "derived",
            "source_datasets": ["job_openings", "intent_score", "google_news"],
            "source_fields": ["hiring_velocity", "composite_score", "event_type"],
            "display_order": 4
        },
        {
            "widget_key": "exec_strategic_priorities",
            "widget_name": "Strategic Priorities & Catalysts",
            "feature_key": "executive_dashboard",
            "description": "Inferred account strategic priorities contract. AI inference model inputs and prompt execution are TBD for future generation. Zero fabricated priorities.",
            "widget_type": "priority_list",
            "data_classification": "inferred",
            "source_datasets": ["firmographics", "google_news"],
            "source_fields": ["business_description", "event_headline"],
            "display_order": 5
        }
    ],
    "recent_news_signals": [
        {
            "widget_key": "news_signals_feed",
            "widget_name": "Live Event Signals Feed",
            "feature_key": "recent_news_signals",
            "description": "Real-time press releases, leadership changes, M&A, and expansion events timeline",
            "widget_type": "timeline_feed",
            "data_classification": "deterministic",
            "source_datasets": ["google_news", "news_events"],
            "source_fields": ["event_headline", "event_date", "event_type", "source_url"],
            "display_order": 1
        },
        {
            "widget_key": "news_relevance_summary",
            "widget_name": "Event Relevance & Sales Angles",
            "feature_key": "recent_news_signals",
            "description": "Inferred event relevance score and sales angle contract. AI inference model inputs and prompt execution are TBD for future generation.",
            "widget_type": "summary_list",
            "data_classification": "inferred",
            "source_datasets": ["google_news", "news_events"],
            "source_fields": ["event_headline", "event_type"],
            "display_order": 2
        }
    ],
    "stakeholder_map": [
        {
            "widget_key": "stakeholder_contacts_grid",
            "widget_name": "Prospect Contacts & Org Directory",
            "feature_key": "stakeholder_map",
            "description": "Verified IT decision makers, titles, departments, email contacts, and phone numbers",
            "widget_type": "contact_grid",
            "data_classification": "deterministic",
            "source_datasets": ["prospect_contacts"],
            "source_fields": ["full_name", "title", "department", "seniority", "email", "phone", "linkedin_url"],
            "display_order": 1
        },
        {
            "widget_key": "stakeholder_influence_map",
            "widget_name": "Buying Center & Influence Grouping",
            "feature_key": "stakeholder_map",
            "description": "Derived departmental influence classification contract. Grouping algorithms are TBD for future runtime calculation.",
            "widget_type": "hierarchy_chart",
            "data_classification": "derived",
            "source_datasets": ["prospect_contacts"],
            "source_fields": ["department", "seniority"],
            "display_order": 2
        }
    ],
    "solution_narrative_opportunity_map": [
        {
            "widget_key": "opportunity_context_card",
            "widget_name": "Opportunity Account Context",
            "feature_key": "solution_narrative_opportunity_map",
            "description": "Core business model, technology stack, and intent context driving opportunity relevance",
            "widget_type": "context_card",
            "data_classification": "deterministic",
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "source_fields": ["narrative_context", "technology_stack", "intent_topic"],
            "display_order": 1
        },
        {
            "widget_key": "opportunity_trigger_signals",
            "widget_name": "Opportunity Trigger Signals",
            "feature_key": "solution_narrative_opportunity_map",
            "description": "Live news events and expansion triggers enabling HP solution plays",
            "widget_type": "signal_list",
            "data_classification": "deterministic",
            "source_datasets": ["google_news", "news_events"],
            "source_fields": ["trigger_signal"],
            "display_order": 2
        },
        {
            "widget_key": "opportunity_narrative_plays",
            "widget_name": "HP Opportunity Plays & Impact",
            "feature_key": "solution_narrative_opportunity_map",
            "description": "Inferred HP solution plays contract. Business outcome synthesis and product matching logic are TBD for future AI generation.",
            "widget_type": "play_cards",
            "data_classification": "inferred",
            "source_datasets": ["firmographics", "technographics", "google_news"],
            "source_fields": ["business_description", "technology_stack", "trigger_signal"],
            "display_order": 3
        }
    ],
    "tech_landscape": [
        {
            "widget_key": "technographic_map",
            "widget_name": "Technographic Map",
            "feature_key": "tech_landscape",
            "description": "Detected technologies across IT categories mapped to HP product lines, displacement opportunities, and sales plays",
            "widget_type": "technographic_map",
            "data_classification": "deterministic",
            "source_datasets": ["technographics", "technology_detections", "webstack"],
            "source_fields": ["technology_category", "vendor_product", "hp_product_line"],
            "display_order": 1
        },
        {
            "widget_key": "tech_stack_matrix",
            "widget_name": "Technology Stack Matrix",
            "feature_key": "tech_landscape",
            "description": "Installed software, hardware, cloud, security, and CRM vendors by category",
            "widget_type": "matrix_table",
            "data_classification": "deterministic",
            "source_datasets": ["technographics"],
            "source_fields": ["technology_category", "vendor_product"],
            "display_order": 2
        },
        {
            "widget_key": "tech_detections_reference",
            "widget_name": "Digital Technology Detections",
            "feature_key": "tech_landscape",
            "description": "Automated tech detection signals, confidence scores, and first/last seen timestamps",
            "widget_type": "detection_list",
            "data_classification": "deterministic",
            "source_datasets": ["technology_detections"],
            "source_fields": ["detection_confidence", "first_last_seen"],
            "display_order": 3
        },
        {
            "widget_key": "webstack_breakdown",
            "widget_name": "Web & Digital Infrastructure Stack",
            "feature_key": "tech_landscape",
            "description": "CMS, SSL, Web Server, Hosting, CDN, and Analytics technologies",
            "widget_type": "breakdown_grid",
            "data_classification": "deterministic",
            "source_datasets": ["webstack"],
            "source_fields": ["website_tech"],
            "display_order": 4
        }
    ],
    "objection_playbook": [
        {
            "widget_key": "objection_incumbent_context",
            "widget_name": "Incumbent Technology Context",
            "feature_key": "objection_playbook",
            "description": "Competitor technologies in place for weakness framing and displacement strategy",
            "widget_type": "context_card",
            "data_classification": "deterministic",
            "source_datasets": ["technographics", "firmographics"],
            "source_fields": ["incumbent_technology", "company_description"],
            "display_order": 1
        },
        {
            "widget_key": "objection_reframe_cards",
            "widget_name": "Competitor Reframes & Proof Points",
            "feature_key": "objection_playbook",
            "description": "Inferred objection reframes contract. Competitive reframe synthesis and counter-question generation are TBD for future AI generation.",
            "widget_type": "card_list",
            "data_classification": "inferred",
            "source_datasets": ["technographics", "firmographics"],
            "source_fields": ["incumbent_technology"],
            "display_order": 2
        }
    ],
    "content_studio": [
        {
            "widget_key": "content_persona_context",
            "widget_name": "Target Persona & Company Context",
            "feature_key": "content_studio",
            "description": "Persona profile from contacts or open hiring proxy roles plus account context",
            "widget_type": "context_card",
            "data_classification": "deterministic",
            "source_datasets": ["prospect_contacts", "job_openings", "firmographics"],
            "source_fields": ["named_persona", "role_type_proxy", "company_context"],
            "display_order": 1
        },
        {
            "widget_key": "content_generated_assets",
            "widget_name": "Tailored Content Asset Generator",
            "feature_key": "content_studio",
            "description": "Inferred content generation contract. Executive briefing deck and pitch generation prompts are TBD for future AI generation.",
            "widget_type": "asset_generator",
            "data_classification": "inferred",
            "source_datasets": ["prospect_contacts", "job_openings"],
            "source_fields": ["named_persona", "role_type_proxy"],
            "display_order": 2
        }
    ],
    "strategy_chat": [
        {
            "widget_key": "strategy_snapshot_context",
            "widget_name": "Account Snapshot Grounding Context",
            "feature_key": "strategy_chat",
            "description": "Full cached account snapshot used as grounding context for strategy chat",
            "widget_type": "snapshot_badge",
            "data_classification": "deterministic",
            "source_datasets": ["firmographics", "company_hierarchy", "technographics", "webstack", "job_openings", "google_news", "news_events", "intent_score", "technology_detections"],
            "source_fields": ["firmographics_context", "tech_context", "hiring_context", "event_context", "intent_context"],
            "display_order": 1
        },
        {
            "widget_key": "strategy_chat_interface",
            "widget_name": "Account Strategy Assistant",
            "feature_key": "strategy_chat",
            "description": "Inferred strategy assistant contract. Conversational RAG grounding and response generation are TBD for future AI generation.",
            "widget_type": "chat_interface",
            "data_classification": "inferred",
            "source_datasets": ["firmographics", "technographics", "google_news"],
            "source_fields": ["chat_response"],
            "display_order": 2
        }
    ],
    "message_evaluator": [
        {
            "widget_key": "evaluator_persona_context",
            "widget_name": "Target Persona Context",
            "feature_key": "message_evaluator",
            "description": "Persona title and seniority requirements for message evaluation",
            "widget_type": "context_card",
            "data_classification": "deterministic",
            "source_datasets": ["prospect_contacts", "job_openings"],
            "source_fields": ["named_persona", "role_type_proxy"],
            "display_order": 1
        },
        {
            "widget_key": "evaluator_feedback_score",
            "widget_name": "Message Scoring & Guardrails Tool",
            "feature_key": "message_evaluator",
            "description": "Inferred message evaluator contract. Message effectiveness scoring and guardrails analysis are TBD for future AI generation.",
            "widget_type": "evaluator_form",
            "data_classification": "inferred",
            "source_datasets": ["prospect_contacts", "job_openings"],
            "source_fields": ["named_persona"],
            "display_order": 2
        }
    ],
    "content_messaging": [
        {
            "widget_key": "messaging_context_card",
            "widget_name": "Messaging Input Context",
            "feature_key": "content_messaging",
            "description": "Business description, tech stack, intent surge, and live event proof points",
            "widget_type": "context_card",
            "data_classification": "deterministic",
            "source_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
            "source_fields": ["business_description", "technology_stack", "intent_topic", "news_event_proof"],
            "display_order": 1
        },
        {
            "widget_key": "messaging_pillars_output",
            "widget_name": "Core Messaging Pillars",
            "feature_key": "content_messaging",
            "description": "Inferred messaging pillars contract. Challenge, benefit, and proof point pillar synthesis are TBD for future AI generation.",
            "widget_type": "pillar_cards",
            "data_classification": "inferred",
            "source_datasets": ["firmographics", "technographics", "intent_score"],
            "source_fields": ["business_description", "technology_stack"],
            "display_order": 2
        }
    ],
    "intent_demand_signals": [
        {
            "widget_key": "intent_topics_table",
            "widget_name": "Bombora Intent Research Topics",
            "feature_key": "intent_demand_signals",
            "description": "IT research topics, composite surge scores, and intent category tiers",
            "widget_type": "topic_table",
            "data_classification": "deterministic",
            "source_datasets": ["intent_score", "intent_topics"],
            "source_fields": ["topic_name", "composite_score", "intent_level"],
            "display_order": 1
        },
        {
            "widget_key": "intent_hiring_demand",
            "widget_name": "Hiring-Linked Demand Signals",
            "feature_key": "intent_demand_signals",
            "description": "Job-posting volume and seniority mix as hiring-linked intent demand signal",
            "widget_type": "signal_card",
            "data_classification": "deterministic",
            "source_datasets": ["job_openings"],
            "source_fields": ["hiring_linked_demand"],
            "display_order": 2
        }
    ]
}

@router.get("/widgets", response_model=list[WidgetContract])
def list_all_widgets(current_user: dict = Depends(require_user_role)):
    all_widgets = []
    for feature_key, widgets in WIDGET_REGISTRY.items():
        all_widgets.extend(widgets)
    return all_widgets

@router.get("/widgets/{feature_key}", response_model=list[WidgetContract])
def get_feature_widgets(feature_key: str, current_user: dict = Depends(require_user_role)):
    key_clean = feature_key.strip().lower()
    if key_clean not in WIDGET_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_key}' not found in widget registry."
        )
    return WIDGET_REGISTRY[key_clean]

@router.get("/accounts/{account_id}/widgets/{feature_key}", response_model=list[WidgetResponse])
def get_account_feature_widgets(
    account_id: str,
    feature_key: str,
    current_user: dict = Depends(require_user_role)
):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid account ID format")

    db = get_db()
    account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company account not found")

    key_clean = feature_key.strip().lower()
    if key_clean not in WIDGET_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_key}' not found in widget registry."
        )

    widget_contracts = WIDGET_REGISTRY[key_clean]
    
    # Execute deterministic extractors
    extracted_widgets_map = {}
    if key_clean == "executive_dashboard":
        extracted_list = extract_executive_dashboard(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w
    elif key_clean == "recent_news_signals":
        extracted_list = extract_recent_news_signals(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w
    elif key_clean == "intent_demand_signals":
        extracted_list = extract_intent_demand_signals(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w
    elif key_clean == "solution_narrative_opportunity_map":
        extracted_list = extract_solution_narrative_opportunity_map(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w
    elif key_clean == "stakeholder_map":
        extracted_list = extract_stakeholder_map(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w
    elif key_clean == "tech_landscape":
        extracted_list = extract_tech_landscape(account_id)
        for w in extracted_list:
            extracted_widgets_map[w["widget_key"]] = w

    responses = []
    
    for contract in widget_contracts:
        w_key = contract["widget_key"]
        if w_key in extracted_widgets_map:
            ext_doc = extracted_widgets_map[w_key]
            updated_at_val = ext_doc.get("updated_at")
            updated_at_str = updated_at_val.isoformat() if isinstance(updated_at_val, datetime) else str(updated_at_val or "")
            
            responses.append({
                "account_id": account_id,
                "feature_key": key_clean,
                "widget_key": contract["widget_key"],
                "widget_name": contract["widget_name"],
                "description": contract["description"],
                "widget_type": contract["widget_type"],
                "data_classification": contract["data_classification"],
                "status": ext_doc.get("status", "empty"),
                "data": ext_doc.get("data", {}),
                "source_datasets": contract["source_datasets"],
                "source_fields": contract["source_fields"],
                "display_order": contract["display_order"],
                "updated_at": updated_at_str
            })
        else:
            responses.append({
                "account_id": account_id,
                "feature_key": key_clean,
                "widget_key": contract["widget_key"],
                "widget_name": contract["widget_name"],
                "description": contract["description"],
                "widget_type": contract["widget_type"],
                "data_classification": contract["data_classification"],
                "status": "empty",
                "data": {},
                "source_datasets": contract["source_datasets"],
                "source_fields": contract["source_fields"],
                "display_order": contract["display_order"],
                "updated_at": None
            })

    return responses
