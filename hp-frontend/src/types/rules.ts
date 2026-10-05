/** GET /admin/rules and /admin/rules/{feature_key}: the rules as a business
 *  reader needs them. Numbers arrive already filled in from live settings. */

export interface FeatureRulesSummary {
  feature_key: string;
  purpose: string;
  rule_count: number;
  top_level_rules: string[];
}

export interface RulesIndexResponse {
  features: FeatureRulesSummary[];
  /** WIDGET_REGISTRY features with no rule book yet. */
  missing: string[];
}

export interface RuleConstant {
  label: string;
  value: string;
}

export interface RuleExample {
  scenario?: string;
  steps?: string[];
  result?: string;
  /** The example's result is checked against the live calculation. */
  verified?: boolean;
}

export type RuleKind = 'score' | 'selection' | 'filter' | 'guardrail' | 'model' | 'display' | 'source';

export interface Rule {
  id: string;
  parent?: string | null;
  name: string;
  kind?: RuleKind;
  summary?: string;
  purpose?: string;
  inputs?: string[];
  logic?: string;
  formula?: string | null;
  conditions?: string[];
  table?: { columns: string[]; rows: (string | number)[][] } | null;
  constants?: RuleConstant[];
  example?: RuleExample | null;
  output?: string;
  /** Keys of the rule books (reference sets) this rule applies. */
  uses?: string[];
}

export interface FeatureRules {
  feature_key: string;
  purpose: string;
  final_output: string;
  how_it_combines?: string | null;
  rules: Rule[];
}

/** GET /admin/rules/reference: the fixed rule sets the features apply. */
export interface ReferenceSetSummary {
  key: string;
  title: string;
  summary: string;
  used_by: string[];
  count: number;
}

export interface ReferenceEntry {
  id: string;
  label: string;
  title: string;
  group: string;
  badges: string[];
  fields: { label: string; value: string | string[] }[];
}

export type ReferenceSection =
  | { id: string; title: string; description: string; kind: 'entries'; groups: string[]; entries: ReferenceEntry[] }
  | { id: string; title: string; description: string; kind: 'table'; columns: string[]; rows: string[][] };

export interface ReferenceSet extends ReferenceSetSummary {
  sections: ReferenceSection[];
}
