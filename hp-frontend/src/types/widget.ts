export type WidgetClassification = 'deterministic' | 'derived' | 'inferred';
export type WidgetStatus = 'available' | 'empty' | 'pending';

export interface WidgetContract {
  widget_key: string;
  widget_name: string;
  feature_key: string;
  description: string;
  widget_type: string;
  data_classification: WidgetClassification;
  source_datasets: string[];
  source_fields: string[];
  display_order: number;
}

export interface WidgetResponse extends WidgetContract {
  account_id: string;
  status: WidgetStatus;
  data: Record<string, any>;
  updated_at: string | null;
}

export interface FeatureTabDefinition {
  key: string;
  label: string;
  description: string;
  iconName: string;
}

export const FEATURE_TABS_LIST: FeatureTabDefinition[] = [
  { key: 'executive_dashboard', label: 'Executive Dashboard', description: 'Account profile, key metrics, hiring velocity & strategic catalysts', iconName: 'LayoutDashboard' },
  { key: 'recent_news_signals', label: 'Recent News Signals', description: 'Real-time press, M&A, leadership changes, and event triggers', iconName: 'Newspaper' },
  { key: 'stakeholder_map', label: 'Stakeholder Map', description: 'Contacts, decision makers, org directory & buying center mapping', iconName: 'Users' },
  { key: 'solution_narrative_opportunity_map', label: 'Solution Narrative / Opportunity Map', description: 'HP opportunity plays, trigger signals, and business outcome framing', iconName: 'Lightbulb' },
  { key: 'tech_landscape', label: 'Technographic Map', description: 'Installed software/hardware stack, tech detections & web infrastructure', iconName: 'Cpu' },
  { key: 'objection_playbook', label: 'Objection Playbook', description: 'Competitor reframes, incumbent weaknesses, and proof points', iconName: 'ShieldAlert' },
  { key: 'content_studio', label: 'Content Studio', description: 'Tailored executive briefings, email pitches, and persona battlecards', iconName: 'FileText' },
  { key: 'strategy_chat', label: 'Strategy Chat', description: 'Interactive account strategy assistant grounded in full snapshot', iconName: 'MessageSquare' },
  { key: 'message_evaluator', label: 'Message Evaluator', description: 'Sales message testing tool against persona requirements and guardrails', iconName: 'CheckSquare' },
  { key: 'content_messaging', label: 'Content Messaging', description: 'Core messaging pillars, challenges, benefits, and evidence proof points', iconName: 'Megaphone' },
  { key: 'intent_demand_signals', label: 'Intent & Demand Signals', description: 'Bombora topic research surges and hiring-linked demand signals', iconName: 'TrendingUp' }
];
