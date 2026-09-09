from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import require_admin_role
from app.schemas.account_data import DATASET_REGISTRY
from app.schemas.feature_mapping import (
    MappedField,
    FeatureMappingResponse,
    ReverseDependencyResponse
)

router = APIRouter(prefix="/features", tags=["Feature & Sourcing Mapping (Admin Only)"])

FEATURE_MAPPINGS = {
    "executive_dashboard": {
        "feature_key": "executive_dashboard",
        "display_name": "Executive Dashboard",
        "purpose": "Executive summary of target company identity, size, financial health, corporate hierarchy, and hiring velocity",
        "dependent_datasets": ["firmographics", "company_hierarchy", "job_openings"],
        "mapped_fields": [
            {
                "field_key": "company_name",
                "display_name": "Company Name",
                "purpose": "Account identity (AccountData.identity.name)",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Company Name",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "domain",
                "display_name": "Company Domain / Website",
                "purpose": "Domain and web address",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Company Domain, Website",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "business_description",
                "display_name": "Business Description",
                "purpose": "Primary business summary",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Business Description",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "industry_classification",
                "display_name": "Industry Classification",
                "purpose": "NAICS, SIC, and LinkedIn industry tags",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Naics, Naics Description, Sic Code, Sic Code Description, Linkedin Industry Category",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hq_location",
                "display_name": "HQ Location",
                "purpose": "Registered country, region, city, street, and zip code",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Country Name, Region Name, City Name, Street, Zip Code",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "employee_count",
                "display_name": "Employee Count",
                "purpose": "Total workforce range",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Number Of Employees Range",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "revenue",
                "display_name": "Revenue Range",
                "purpose": "Yearly revenue range",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Yearly Revenue Range",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "company_hierarchy",
                "display_name": "Company Hierarchy",
                "purpose": "Parent and ultimate parent corporate structure",
                "dataset_key": "company_hierarchy",
                "source_sheet": "2_Company_Hierarchy",
                "source_column": "Parent Company Name, Ultimate Parent Name",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hiring_velocity",
                "display_name": "Hiring Velocity / Urgency Signal",
                "purpose": "Open job postings count as role-proxy/urgency signal",
                "dataset_key": "job_openings",
                "source_sheet": "job_openings",
                "source_column": "job_openings record count",
                "data_type": "DETERMINISTIC"
            }
        ]
    },
    "recent_news_signals": {
        "feature_key": "recent_news_signals",
        "display_name": "Recent News Signals",
        "purpose": "Live event signals, leadership changes, M&A, financing, and recent expansion events",
        "dependent_datasets": ["google_news", "news_events"],
        "mapped_fields": [
            {
                "field_key": "event_headline",
                "display_name": "Event Headline (LiveSignal.title)",
                "purpose": "Article headline or event title",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "title, summary, article_sentence",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "event_date",
                "display_name": "Event Date (LiveSignal.date)",
                "purpose": "Publication date or effective event date",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "pubDate, effective_date, found_at",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "event_type",
                "display_name": "Event Type (LiveSignal.type)",
                "purpose": "Event category tag (Hiring, Financial, Technology, Strategic, Competitive)",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "category, event, financing_type",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "source_url",
                "display_name": "Source URL (LiveSignal.sourceUrl)",
                "purpose": "Link to original news source",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "link, source_url",
                "data_type": "DETERMINISTIC"
            }
        ]
    },
    "stakeholder_map": {
        "feature_key": "stakeholder_map",
        "display_name": "Stakeholder Map",
        "purpose": "Org chart mapping, key IT decision makers, contacts, and influence levels",
        "dependent_datasets": ["prospect_contacts"],
        "mapped_fields": [
            {
                "field_key": "full_name",
                "display_name": "Full Name (ExtendedStakeholder.name)",
                "purpose": "Contact full name",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Full Name",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "title",
                "display_name": "Title (ExtendedStakeholder.title)",
                "purpose": "Job title / role",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Title",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "department",
                "display_name": "Department (ExtendedStakeholder.department)",
                "purpose": "Organizational department",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Department",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "seniority",
                "display_name": "Seniority (ExtendedStakeholder.seniority)",
                "purpose": "Seniority level (C-Level, VP, Director, Manager)",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Seniority",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "email",
                "display_name": "Email & Status (ExtendedStakeholder.email)",
                "purpose": "Verified email address and verification status",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Email, Email Status",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "phone",
                "display_name": "Phone (ExtendedStakeholder.phone)",
                "purpose": "Contact phone number",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Phone",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "linkedin_url",
                "display_name": "LinkedIn URL (ExtendedStakeholder.linkedinUrl)",
                "purpose": "LinkedIn profile link",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Linkedin Url",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "buying_committee_persona",
                "display_name": "Buying Committee Persona",
                "purpose": "Uploaded buying-committee classification; primary input to influence type",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect buying_committee_personas",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "seniority_band",
                "display_name": "Seniority Band (derived)",
                "purpose": "Job level normalised to C-Suite / VP / Director / Manager / Individual Contributor; scored 100/75/50/25/10",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect job_level_main",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "normalized_department",
                "display_name": "Normalised Department (derived)",
                "purpose": "Source A labels and Apollo slugs mapped onto one department set",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect job_department_main",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "influence_type",
                "display_name": "Influence Type (derived)",
                "purpose": "Decision Maker / Budget Holder / Technical Evaluator / Influencer. Buying-committee persona leads; procurement and technical title terms override. Scored 100/85/60/50",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect buying_committee_personas, Prospect job_title",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hp_relevance_band",
                "display_name": "HP Relevance (derived)",
                "purpose": "Title, department and skills matched against HP product lines; 100/70/40/20 tiers, banded High >=70, Medium 40-69, Lower <40",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect job_title, Prospect job_department_main, Prospect skills",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "data_completeness",
                "display_name": "Data Completeness (derived)",
                "purpose": "Which contact fields are populated: base 20, LinkedIn +15, email +20, verified email +10, phone +20, profile data +15",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Email, Email Status, Contact mobile_phone, Prospect linkedin, Prospect skills, Prospect experience",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "priority",
                "display_name": "Priority (derived)",
                "purpose": "High for C-Suite/VP in a high-priority department, Medium for other bands there, otherwise Low. Scored 100/50/10",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Prospect job_department_main, Prospect job_level_main",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "stakeholder_score",
                "display_name": "Stakeholder Score (derived)",
                "purpose": "25% seniority + 25% HP relevance + 20% influence + 15% data completeness + 15% priority. Drives Priority Contact selection and the entry-path ranking",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "All fields above",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "how_to_open",
                "display_name": "Opening Angle, HP Play Focus, Decision Power, Pain Points",
                "purpose": "Synthesized per-contact opener and role-based authority note, grounded in the contact's own record plus account-level evidence. Omitted where evidence does not support the claim",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "solution_narrative_opportunity_map": {
        "feature_key": "solution_narrative_opportunity_map",
        "display_name": "Solution Narrative / Opportunity Map",
        "purpose": "Maps customer triggers and tech environment to HP business outcomes and product opportunities",
        "dependent_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
        "mapped_fields": [
            {
                "field_key": "narrative_context",
                "display_name": "Business Outcome Context",
                "purpose": "Company context for outcome framing",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Business Description",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "technology_stack",
                "display_name": "Technology Stack Context",
                "purpose": "Current technology stack for solution framing",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics",
                "source_column": "Full Tech Stack",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "intent_topic",
                "display_name": "Intent Topic Relevance",
                "purpose": "Research topics for opportunity alignment",
                "dataset_key": "intent_score",
                "source_sheet": "11_intent_score",
                "source_column": "Topic, Composite Score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "trigger_signal",
                "display_name": "Trigger Signal (OpportunityPlay.triggerSignal)",
                "purpose": "Live event trigger driving the opportunity",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "title, summary",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "business_outcome",
                "display_name": "Quantified Business Outcome & Products",
                "purpose": "Synthesized HP value proposition and recommended product portfolio",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "tech_landscape": {
        "feature_key": "tech_landscape",
        "display_name": "Technographic Map",
        "purpose": "Comprehensive mapping of installed hardware, software, cloud, security, and web technologies",
        "dependent_datasets": ["technographics", "technology_detections", "webstack"],
        "mapped_fields": [
            {
                "field_key": "technology_category",
                "display_name": "Technology Category (DeviceEstateEntry.category)",
                "purpose": "Software/hardware domain category",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics (Primary) / technology_detections (Ref)",
                "source_column": "Category, department_onet_codes",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "vendor_product",
                "display_name": "Vendor / Product (DeviceEstateEntry.vendor, product)",
                "purpose": "Installed vendor name and product",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics (Primary) / technology_detections (Ref)",
                "source_column": "Full Tech Stack, vendor",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "detection_confidence",
                "display_name": "Detection Confidence (TechStackEntry.confidence)",
                "purpose": "Confidence score of detection",
                "dataset_key": "technology_detections",
                "source_sheet": "technology_detections",
                "source_column": "score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "first_last_seen",
                "display_name": "First / Last Seen Date",
                "purpose": "Recency dates for technology detection",
                "dataset_key": "technology_detections",
                "source_sheet": "technology_detections",
                "source_column": "first_seen_at, last_seen_at",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "website_tech",
                "display_name": "Website Tech Stack",
                "purpose": "CMS, SSL, Web Server, Hosting, CDN, Framework, Analytics",
                "dataset_key": "webstack",
                "source_sheet": "5_Tech_Breakdown",
                "source_column": "Cms, Ssl, Web Server, Hosting, Cdn, Framework, Analytics",
                "data_type": "DETERMINISTIC"
            }
        ]
    },
    "objection_playbook": {
        "feature_key": "objection_playbook",
        "display_name": "Objection Playbook",
        "purpose": "Anticipated competitor objections, reframes, proof points, and counter-questions",
        "dependent_datasets": ["technographics", "firmographics"],
        "mapped_fields": [
            {
                "field_key": "incumbent_technology",
                "display_name": "Incumbent Technology Context",
                "purpose": "Competitor technologies in place for weakness framing",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics",
                "source_column": "Full Tech Stack, category columns",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "company_description",
                "display_name": "Company Description Context",
                "purpose": "Account business model for objection context",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Business Description",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "objection_synthesis",
                "display_name": "Objection Reframe & Proof Points",
                "purpose": "Synthesized counter-arguments and competitive reframes",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "content_studio": {
        "feature_key": "content_studio",
        "display_name": "Content Studio",
        "purpose": "Generates personalized sales collateral, emails, and pitch decks tailored to target personas",
        "dependent_datasets": ["prospect_contacts", "job_openings", "firmographics"],
        "mapped_fields": [
            {
                "field_key": "named_persona",
                "display_name": "Named Persona Contact",
                "purpose": "Target contact title and department",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Title, Department",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "role_type_proxy",
                "display_name": "Role-Type Persona Proxy",
                "purpose": "Fallback persona constructed from open hiring roles",
                "dataset_key": "job_openings",
                "source_sheet": "job_openings",
                "source_column": "title, normalized_title, seniority",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "company_context",
                "display_name": "Company Context for Personalization",
                "purpose": "Industry and business description context",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Business Description, industry fields",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "generated_content",
                "display_name": "Generated Content Collateral",
                "purpose": "Synthesized personalized sales messaging and assets",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "strategy_chat": {
        "feature_key": "strategy_chat",
        "display_name": "Strategy Chat",
        "purpose": "Interactive account strategy Q&A grounded in full cached account snapshot",
        "dependent_datasets": ["firmographics", "company_hierarchy", "technographics", "webstack", "job_openings", "google_news", "news_events", "intent_score", "technology_detections"],
        "mapped_fields": [
            {
                "field_key": "firmographics_context",
                "display_name": "Firmographics Context",
                "purpose": "Company identity, size, revenue, location",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "All firmographic fields",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hierarchy_context",
                "display_name": "Hierarchy Context",
                "purpose": "Corporate structure",
                "dataset_key": "company_hierarchy",
                "source_sheet": "2_Company_Hierarchy",
                "source_column": "Parent Company Name, Ultimate Parent Name",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "tech_context",
                "display_name": "Technographics Context",
                "purpose": "Full tech stack",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics",
                "source_column": "Full Tech Stack",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "webstack_context",
                "display_name": "Webstack Context",
                "purpose": "Web infrastructure stack",
                "dataset_key": "webstack",
                "source_sheet": "5_Tech_Breakdown",
                "source_column": "Cms, Ssl, Web Server, Hosting, Cdn, Framework, Analytics",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hiring_context",
                "display_name": "Hiring & Job Openings Context",
                "purpose": "Open roles and hiring priorities",
                "dataset_key": "job_openings",
                "source_sheet": "job_openings",
                "source_column": "title, normalized_title, seniority",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "event_context",
                "display_name": "News & Events Context",
                "purpose": "Recent news and company events",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "title, summary, pubDate",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "intent_context",
                "display_name": "Intent Context",
                "purpose": "Intent research scores",
                "dataset_key": "intent_score",
                "source_sheet": "11_intent_score",
                "source_column": "Topic, Composite Score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "tech_detections_ref",
                "display_name": "Technology Detections Reference",
                "purpose": "Detected tech signals",
                "dataset_key": "technology_detections",
                "source_sheet": "technology_detections",
                "source_column": "vendor, score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "chat_response",
                "display_name": "Synthesized Strategy Answer",
                "purpose": "LLM response grounded in account snapshot",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "message_evaluator": {
        "feature_key": "message_evaluator",
        "display_name": "Message Evaluator",
        "purpose": "Evaluates sales outreach messages against target persona requirements and guardrails",
        "dependent_datasets": ["prospect_contacts", "job_openings"],
        "mapped_fields": [
            {
                "field_key": "named_persona",
                "display_name": "Named Persona Target",
                "purpose": "Target contact title, department, and seniority",
                "dataset_key": "prospect_contacts",
                "source_sheet": "14_Prospect_Contacts",
                "source_column": "Title, Department, Seniority",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "role_type_proxy",
                "display_name": "Role-Type Persona Proxy",
                "purpose": "Fallback persona constructed from open hiring roles",
                "dataset_key": "job_openings",
                "source_sheet": "job_openings",
                "source_column": "title, normalized_title, seniority",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "evaluation_score",
                "display_name": "Evaluated Messaging Score & Feedback",
                "purpose": "Synthesized message effectiveness score and guardrail check",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "content_messaging": {
        "feature_key": "content_messaging",
        "display_name": "Content Messaging",
        "purpose": "Constructs core messaging pillars (challenge, benefit, proof points) tailored to the account",
        "dependent_datasets": ["firmographics", "technographics", "intent_score", "google_news", "news_events"],
        "mapped_fields": [
            {
                "field_key": "business_description",
                "display_name": "Business Description Context",
                "purpose": "Pillar framing context",
                "dataset_key": "firmographics",
                "source_sheet": "1_Firmographics",
                "source_column": "Business Description",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "technology_stack",
                "display_name": "Technology Stack Context",
                "purpose": "Challenge and benefit framing context",
                "dataset_key": "technographics",
                "source_sheet": "4_Technographics",
                "source_column": "Full Tech Stack",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "intent_topic",
                "display_name": "Intent Topic Relevance",
                "purpose": "Proof point relevance context",
                "dataset_key": "intent_score",
                "source_sheet": "11_intent_score",
                "source_column": "Topic, Composite Score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "news_event_proof",
                "display_name": "News Event Proof Points",
                "purpose": "Live event evidence for messaging proof points",
                "dataset_key": "google_news",
                "source_sheet": "google_news_rss_data (Primary) / news_events (Add-on)",
                "source_column": "title, summary",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "generated_pillars",
                "display_name": "Generated Messaging Pillars",
                "purpose": "Synthesized value propositions and proof point pillars",
                "dataset_key": None,
                "source_sheet": None,
                "source_column": None,
                "data_type": "INFERRED / SYNTHESIZED"
            }
        ]
    },
    "intent_demand_signals": {
        "feature_key": "intent_demand_signals",
        "display_name": "Intent & Demand Signals",
        "purpose": "Aggregates Bombora intent research topics, composite scores, and hiring-linked demand surges",
        "dependent_datasets": ["intent_score", "intent_topics", "job_openings"],
        "mapped_fields": [
            {
                "field_key": "topic_name",
                "display_name": "Topic Name (IntentTopic.topic)",
                "purpose": "Research topic name",
                "dataset_key": "intent_score",
                "source_sheet": "11_intent_score",
                "source_column": "Topic",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "composite_score",
                "display_name": "Composite Intent Score (IntentTopic.compositeScore)",
                "purpose": "Composite research surge score",
                "dataset_key": "intent_score",
                "source_sheet": "11_intent_score",
                "source_column": "Composite Score",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "intent_level",
                "display_name": "Level of Intent / Category Tier",
                "purpose": "Intent category tier",
                "dataset_key": "intent_topics",
                "source_sheet": "10_Intent_Topics",
                "source_column": "Level Of Intent",
                "data_type": "DETERMINISTIC"
            },
            {
                "field_key": "hiring_linked_demand",
                "display_name": "Hiring-Linked Intent Category",
                "purpose": "Job-posting volume and seniority mix as hiring-linked intent signal",
                "dataset_key": "job_openings",
                "source_sheet": "job_openings",
                "source_column": "job_openings volume and seniority mix",
                "data_type": "DETERMINISTIC"
            }
        ]
    }
}

@router.get("", response_model=list[FeatureMappingResponse])
def list_features_mapping(current_user: dict = Depends(require_admin_role)):
    return list(FEATURE_MAPPINGS.values())

@router.get("/dependencies/reverse", response_model=list[ReverseDependencyResponse])
def list_reverse_dependencies(current_user: dict = Depends(require_admin_role)):
    result = []
    for key, info in DATASET_REGISTRY.items():
        mapped_feats = []
        for feat_key, feat_info in FEATURE_MAPPINGS.items():
            if key in feat_info["dependent_datasets"]:
                mapped_feats.append(feat_key)
        
        result.append({
            "dataset_key": key,
            "display_name": info["display_name"],
            "mapped_features": mapped_feats,
            "is_mapped": len(mapped_feats) > 0
        })
    return result

@router.get("/{feature_key}", response_model=FeatureMappingResponse)
def get_feature_mapping(feature_key: str, current_user: dict = Depends(require_admin_role)):
    key_clean = feature_key.strip().lower()
    if key_clean not in FEATURE_MAPPINGS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_key}' not found in registry."
        )
    return FEATURE_MAPPINGS[key_clean]
