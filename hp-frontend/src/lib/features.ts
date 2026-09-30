/**
 * The features a seller sees, in sidebar order, with their user-facing labels.
 *
 * Lives here rather than in the dashboard page so the admin analytics page
 * labels features exactly as the sidebar does. The keys are the backend's
 * feature keys (WIDGET_REGISTRY in hp-backend/src/app/api/v1/widgets.py), which
 * is the authoritative list the analytics API reports against.
 */

export interface SidebarItem {
  key: string;
  label: string;
  subtitle: string;
  description: string;
  iconName: string;
}

export interface SidebarGroup {
  sectionTitle: string;
  items: SidebarItem[];
}

export const NORTHSTAR_SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    sectionTitle: "INTELLIGENCE",
    items: [
      { key: 'executive_dashboard', label: 'Executive Dashboard', subtitle: 'Account profile & key metrics', description: 'Account profile & key metrics', iconName: 'LayoutDashboard' },
      { key: 'recent_news_signals', label: 'Live Signals', subtitle: 'Real-time news & triggers', description: 'Real-time news & triggers', iconName: 'Newspaper' },
      { key: 'intent_demand_signals', label: 'Intent & Demand Signals', subtitle: 'HP-category & topic-level research intent', description: 'HP-category & topic-level research intent', iconName: 'TrendingUp' },
      { key: 'stakeholder_map', label: 'Stakeholder Map', subtitle: 'Contacts & influence map', description: 'Contacts & influence map', iconName: 'Users' },
      { key: 'solution_narrative_opportunity_map', label: 'Opportunity Map', subtitle: 'HP plays: outcome, impact & evidence', description: 'HP plays: outcome, impact & evidence', iconName: 'Lightbulb' },
      { key: 'tech_landscape', label: 'Technographic Map', subtitle: 'Tech stack by category & HP fit', description: 'Tech stack by category & HP fit', iconName: 'Cpu' },
      { key: 'objection_playbook', label: 'Objection Playbook', subtitle: 'Reframes & proof points', description: 'Reframes & proof points', iconName: 'ShieldAlert' }
    ]
  },
  {
    sectionTitle: "ACTION",
    items: [
      { key: 'content_studio', label: 'Content Studio', subtitle: 'Generate tailored content', description: 'Generate tailored content', iconName: 'FileText' },
      { key: 'strategy_chat', label: 'Strategy Chat', subtitle: 'AI strategy assistant', description: 'AI strategy assistant', iconName: 'MessageSquare' }
    ]
  },
  {
    sectionTitle: "SIMULATION & PLANNING",
    items: [
      { key: 'message_evaluator', label: 'Message Evaluator', subtitle: 'Test messages against personas', description: 'Test messages against personas', iconName: 'CheckSquare' }
    ]
  }
];

/** feature_key -> label, for anything that shows a backend feature key. */
export const FEATURE_LABELS: Record<string, string> = Object.fromEntries(
  NORTHSTAR_SIDEBAR_GROUPS.flatMap(g => g.items).map(i => [i.key, i.label]),
);

export function featureLabel(key: string): string {
  return FEATURE_LABELS[key] ?? key;
}
