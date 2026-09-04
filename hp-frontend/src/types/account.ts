export type AccountStatus = 'active' | 'hidden';

export interface CompanyAccount {
  id: string;
  name: string;
  status: AccountStatus;
  created_at: string;
  updated_at: string;
}

export type DatasetKey = 
  | 'firmographics'
  | 'company_hierarchy'
  | 'subsidiaries'
  | 'funding'
  | 'technographics'
  | 'webstack'
  | 'workforce_trends'
  | 'company_ratings'
  | 'website_traffic'
  | 'social_media'
  | 'intent_topics'
  | 'intent_score'
  | 'news_events'
  | 'prospect_contacts'
  | 'company'
  | 'extended_company'
  | 'job_openings'
  | 'technology_detections'
  | 'news_events_additional'
  | 'connections'
  | 'subpages'
  | 'similar_companies'
  | 'google_news';

export interface AccountDataFile {
  id: string;
  account_id: string;
  dataset_key: DatasetKey;
  category?: string;
  display_name: string;
  original_filename: string;
  stored_filename: string;
  file_path: string;
  file_size: number;
  row_count: number;
  status: 'active' | 'replaced' | 'archived' | 'deleted';
  uploaded_at: string;
  updated_at: string;
}

export interface DatasetRegistryItem {
  key: DatasetKey;
  display_name: string;
  canonical_filename?: string;
  type: 'single_file_csv' | 'multi_file';
  group: string;
  description: string;
  allowed_extensions: string[];
}

export const DATASET_REGISTRY_LIST: DatasetRegistryItem[] = [
  // 1. Company & Structure
  { key: 'firmographics', display_name: 'Firmographics', canonical_filename: 'firmographics.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Basic company information, registered address, shareholders, employee count', allowed_extensions: ['.csv'] },
  { key: 'company_hierarchy', display_name: 'Company Hierarchy', canonical_filename: 'company_hierarchy.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Corporate hierarchy, ultimate parent, and branch structures', allowed_extensions: ['.csv'] },
  { key: 'subsidiaries', display_name: 'Subsidiaries', canonical_filename: 'subsidiaries.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Subsidiary companies, operating units, and international entities', allowed_extensions: ['.csv'] },
  { key: 'company', display_name: 'Company', canonical_filename: 'company.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Core company profile and primary entity details', allowed_extensions: ['.csv'] },
  { key: 'extended_company', display_name: 'Extended Company', canonical_filename: 'extended_company.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Extended firmographic attributes and extended corporate metadata', allowed_extensions: ['.csv'] },
  { key: 'similar_companies', display_name: 'Similar Companies', canonical_filename: 'similar_companies.csv', type: 'single_file_csv', group: 'Company & Structure', description: 'Peer group companies, competitors, and market lookalikes', allowed_extensions: ['.csv'] },

  // 2. Financial & Funding
  { key: 'funding', display_name: 'Funding', canonical_filename: 'funding.csv', type: 'single_file_csv', group: 'Financial & Funding', description: 'Venture funding rounds, investors, capital raised, and valuation history', allowed_extensions: ['.csv'] },

  // 3. Technology & Stack
  { key: 'technographics', display_name: 'Technographics', canonical_filename: 'technographics.csv', type: 'single_file_csv', group: 'Technology & Stack', description: 'Installed hardware, software, cloud providers, CRM, and collaboration tools', allowed_extensions: ['.csv'] },
  { key: 'webstack', display_name: 'Webstack', canonical_filename: 'webstack.csv', type: 'single_file_csv', group: 'Technology & Stack', description: 'Web servers, frameworks, analytics scripts, and frontend stacks', allowed_extensions: ['.csv'] },
  { key: 'technology_detections', display_name: 'Technology Detections', canonical_filename: 'technology_detections.csv', type: 'single_file_csv', group: 'Technology & Stack', description: 'Automated digital technology detection signals and active vendor tags', allowed_extensions: ['.csv'] },

  // 4. Workforce & Ratings
  { key: 'workforce_trends', display_name: 'Workforce Trends', canonical_filename: 'workforce_trends.csv', type: 'single_file_csv', group: 'Workforce & Ratings', description: 'Headcount growth trends, departmental distribution, and turnover rates', allowed_extensions: ['.csv'] },
  { key: 'company_ratings', display_name: 'Company Ratings', canonical_filename: 'company_ratings.csv', type: 'single_file_csv', group: 'Workforce & Ratings', description: 'Employee ratings, Glassdoor feedback, and workplace sentiment scores', allowed_extensions: ['.csv'] },
  { key: 'job_openings', display_name: 'Job Openings', canonical_filename: 'job_openings.csv', type: 'single_file_csv', group: 'Workforce & Ratings', description: 'Active job postings, hiring velocity, and required technical skills', allowed_extensions: ['.csv'] },
  { key: 'prospect_contacts', display_name: 'Prospect Contacts', canonical_filename: 'prospect_contacts.csv', type: 'single_file_csv', group: 'Workforce & Ratings', description: 'Key IT decision makers, verified email contacts, and phone numbers', allowed_extensions: ['.csv'] },

  // 5. Traffic & Intent
  { key: 'website_traffic', display_name: 'Website Traffic', canonical_filename: 'website_traffic.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Monthly web visitors, domain authority, and referral sources', allowed_extensions: ['.csv'] },
  { key: 'social_media', display_name: 'Social Media', canonical_filename: 'social_media.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Social profiles, LinkedIn followers, and engagement metrics', allowed_extensions: ['.csv'] },
  { key: 'intent_topics', display_name: 'Intent Topics', canonical_filename: 'intent_topics.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Active IT research topics, content consumption, and Bombora interest signals', allowed_extensions: ['.csv'] },
  { key: 'intent_score', display_name: 'Intent Score', canonical_filename: 'intent_score.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Buying intent surge scores, urgency indices, and topic intensity', allowed_extensions: ['.csv'] },
  { key: 'connections', display_name: 'Connections', canonical_filename: 'connections.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Partner connections, vendor relationships, and ecosystem links', allowed_extensions: ['.csv'] },
  { key: 'subpages', display_name: 'Subpages', canonical_filename: 'subpages.csv', type: 'single_file_csv', group: 'Traffic & Intent', description: 'Key domain subpages, product landing pages, and career portals', allowed_extensions: ['.csv'] },

  // 6. News & Live Signals (Multi-File)
  { key: 'news_events', display_name: 'News & Events', type: 'multi_file', group: 'News & Live Signals', description: 'Primary news articles, PR releases, leadership changes, and expansion announcements (Multi-file CSV)', allowed_extensions: ['.csv'] },
  { key: 'news_events_additional', display_name: 'News & Events (Additional)', type: 'multi_file', group: 'News & Live Signals', description: 'Supplemental news feeds, market updates, and additional press coverage (Multi-file CSV)', allowed_extensions: ['.csv'] },
  { key: 'google_news', display_name: 'Google News', type: 'multi_file', group: 'News & Live Signals', description: 'Google News RSS feeds and search results (Multi-file Excel .xlsx / .csv)', allowed_extensions: ['.xlsx', '.xls', '.csv'] }
];

export interface AccountInstructions {
  account_id: string;
  instructions_text: string;
  updated_at: string;
}

export interface AccountGuardrails {
  account_id: string;
  enabled: boolean;
  guardrails_text: string;
  updated_at: string;
}
