from datetime import datetime
from pydantic import BaseModel
from typing import Literal

DATASET_REGISTRY = {
    "firmographics": {
        "display_name": "Firmographics",
        "type": "single_file_csv",
        "canonical_filename": "firmographics.csv",
        "allowed_extensions": [".csv"]
    },
    "company_hierarchy": {
        "display_name": "Company Hierarchy",
        "type": "single_file_csv",
        "canonical_filename": "company_hierarchy.csv",
        "allowed_extensions": [".csv"]
    },
    "subsidiaries": {
        "display_name": "Subsidiaries",
        "type": "single_file_csv",
        "canonical_filename": "subsidiaries.csv",
        "allowed_extensions": [".csv"]
    },
    "funding": {
        "display_name": "Funding",
        "type": "single_file_csv",
        "canonical_filename": "funding.csv",
        "allowed_extensions": [".csv"]
    },
    "technographics": {
        "display_name": "Technographics",
        "type": "single_file_csv",
        "canonical_filename": "technographics.csv",
        "allowed_extensions": [".csv"]
    },
    "webstack": {
        "display_name": "Webstack",
        "type": "single_file_csv",
        "canonical_filename": "webstack.csv",
        "allowed_extensions": [".csv"]
    },
    "workforce_trends": {
        "display_name": "Workforce Trends",
        "type": "single_file_csv",
        "canonical_filename": "workforce_trends.csv",
        "allowed_extensions": [".csv"]
    },
    "company_ratings": {
        "display_name": "Company Ratings",
        "type": "single_file_csv",
        "canonical_filename": "company_ratings.csv",
        "allowed_extensions": [".csv"]
    },
    "website_traffic": {
        "display_name": "Website Traffic",
        "type": "single_file_csv",
        "canonical_filename": "website_traffic.csv",
        "allowed_extensions": [".csv"]
    },
    "social_media": {
        "display_name": "Social Media",
        "type": "single_file_csv",
        "canonical_filename": "social_media.csv",
        "allowed_extensions": [".csv"]
    },
    "intent_topics": {
        "display_name": "Intent Topics",
        "type": "single_file_csv",
        "canonical_filename": "intent_topics.csv",
        "allowed_extensions": [".csv"]
    },
    "intent_score": {
        "display_name": "Intent Score",
        "type": "single_file_csv",
        "canonical_filename": "intent_score.csv",
        "allowed_extensions": [".csv"]
    },
    "news_events": {
        "display_name": "News & Events",
        "type": "multi_file",
        "allowed_extensions": [".csv"]
    },
    "prospect_contacts": {
        "display_name": "Prospect Contacts",
        "type": "single_file_csv",
        "canonical_filename": "prospect_contacts.csv",
        "allowed_extensions": [".csv"]
    },
    "company": {
        "display_name": "Company",
        "type": "single_file_csv",
        "canonical_filename": "company.csv",
        "allowed_extensions": [".csv"]
    },
    "extended_company": {
        "display_name": "Extended Company",
        "type": "single_file_csv",
        "canonical_filename": "extended_company.csv",
        "allowed_extensions": [".csv"]
    },
    "job_openings": {
        "display_name": "Job Openings",
        "type": "single_file_csv",
        "canonical_filename": "job_openings.csv",
        "allowed_extensions": [".csv"]
    },
    "technology_detections": {
        "display_name": "Technology Detections",
        "type": "single_file_csv",
        "canonical_filename": "technology_detections.csv",
        "allowed_extensions": [".csv"]
    },
    "news_events_additional": {
        "display_name": "News & Events (Additional)",
        "type": "multi_file",
        "allowed_extensions": [".csv"]
    },
    "connections": {
        "display_name": "Connections",
        "type": "single_file_csv",
        "canonical_filename": "connections.csv",
        "allowed_extensions": [".csv"]
    },
    "subpages": {
        "display_name": "Subpages",
        "type": "single_file_csv",
        "canonical_filename": "subpages.csv",
        "allowed_extensions": [".csv"]
    },
    "similar_companies": {
        "display_name": "Similar Companies",
        "type": "single_file_csv",
        "canonical_filename": "similar_companies.csv",
        "allowed_extensions": [".csv"]
    },
    "google_news": {
        "display_name": "Google News",
        "type": "multi_file",
        "allowed_extensions": [".xlsx", ".xls", ".csv"]
    }
}

class AccountDataFileResponse(BaseModel):
    id: str
    account_id: str
    dataset_key: str
    display_name: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size: int
    row_count: int
    status: Literal['active', 'replaced', 'archived', 'deleted']
    uploaded_at: str
    updated_at: str
