'use client';

/**
 * The pieces of the admin Rules page: the feature sidebar with each feature's
 * rule tree and the rule detail pane. Every rule renders the same sections in
 * the same order (Purpose, Inputs, How it works, Values, Table, Conditions,
 * Example, Result) and skips the ones it does not have, so a reader learns the
 * layout once. The page explains rules only - no code or document references.
 */

import React from 'react';
import {
  BookOpen, Calculator, CheckCircle2, ChevronRight, Cpu,
  Filter, Layers, LayoutDashboard, Lightbulb, ListChecks, Loader2, MessageSquare, Newspaper,
  ShieldAlert, ShieldCheck, Sparkles, Target, TrendingUp, Users, CheckSquare, FileText, Database, Eye,
} from 'lucide-react';
import type { Rule, RuleKind } from '@/types/rules';

export const FEATURE_ICONS: Record<string, React.FC<{ className?: string }>> = {
  LayoutDashboard, Newspaper, TrendingUp, Users, Lightbulb, Cpu, ShieldAlert, FileText, MessageSquare, CheckSquare,
};

export function featureIcon(iconName?: string): React.FC<{ className?: string }> {
  return (iconName && FEATURE_ICONS[iconName]) || BookOpen;
}

const KIND: Record<RuleKind, { label: string; Icon: React.FC<{ className?: string }>; tone: string; dot: string }> = {
  score:     { label: 'Score',       Icon: Calculator,  tone: 'bg-sky-50 text-sky-700 ring-sky-200',             dot: 'bg-sky-500' },
  selection: { label: 'Selection',   Icon: Target,      tone: 'bg-indigo-50 text-indigo-700 ring-indigo-200',    dot: 'bg-indigo-500' },
  filter:    { label: 'Filter',      Icon: Filter,      tone: 'bg-slate-100 text-slate-700 ring-slate-200',      dot: 'bg-slate-400' },
  guardrail: { label: 'Guardrail',   Icon: ShieldCheck, tone: 'bg-emerald-50 text-emerald-700 ring-emerald-200', dot: 'bg-emerald-500' },
  model:     { label: 'AI step',     Icon: Sparkles,    tone: 'bg-violet-50 text-violet-700 ring-violet-200',    dot: 'bg-violet-500' },
  display:   { label: 'Display',     Icon: Eye,         tone: 'bg-gray-100 text-gray-700 ring-gray-200',         dot: 'bg-gray-400' },
  source:    { label: 'Data source', Icon: Database,    tone: 'bg-amber-50 text-amber-800 ring-amber-200',       dot: 'bg-amber-500' },
};

export function KindBadge({ kind }: { kind?: RuleKind }) {
  const k = kind && KIND[kind];
  if (!k) return null;
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold ring-1 ring-inset ${k.tone}`}>
      <k.Icon className="w-3 h-3" />{k.label}
    </span>
  );
}

export function RuleBadges({ rule }: { rule: Rule }) {
  return <KindBadge kind={rule.kind} />;
}

// --------------------------------------------------------------------- sidebar

/** A feature's rules as a tree: id -> children, plus the roots, in catalog order. */
export interface RuleIndex {
  roots: Rule[];
  children: Map<string, Rule[]>;
  byId: Map<string, Rule>;
  /** Depth-first order, for previous / next. */
  order: Rule[];
}

export function indexRules(rules: Rule[]): RuleIndex {
  const ids = new Set(rules.map(r => r.id));
  const children = new Map<string, Rule[]>();
  const roots: Rule[] = [];
  for (const r of rules) {
    if (r.parent && ids.has(r.parent)) children.set(r.parent, [...(children.get(r.parent) ?? []), r]);
    else roots.push(r);
  }
  const order: Rule[] = [];
  const walk = (r: Rule) => { order.push(r); (children.get(r.id) ?? []).forEach(walk); };
  roots.forEach(walk);
  return { roots, children, byId: new Map(rules.map(r => [r.id, r])), order };
}

export function ancestors(index: RuleIndex, id: string): Rule[] {
  const out: Rule[] = [];
  for (let r = index.byId.get(index.byId.get(id)?.parent ?? ''); r; r = r.parent ? index.byId.get(r.parent) : undefined) out.unshift(r);
  return out;
}

export function FeatureNavItem({ label, iconName, ruleCount, active, expanded, loading, onSelect, children }: {
  label: string; iconName?: string; ruleCount: number;
  active: boolean; expanded: boolean; loading: boolean; onSelect: () => void; children?: React.ReactNode;
}) {
  const Icon = featureIcon(iconName);
  return (
    <li>
      <button type="button" onClick={onSelect} aria-expanded={expanded}
        className={`group w-full flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy ${
          active ? 'bg-hp-dark text-white shadow-md' : 'text-gray-800 hover:bg-white/80'}`}>
        <span className={`flex-shrink-0 rounded-lg p-1.5 transition-colors ${active ? 'bg-white/15 text-white' : 'bg-hp-dark/[0.06] text-hp-dark group-hover:bg-hp-blue group-hover:text-white'}`}>
          <Icon className="w-4 h-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-bold">{label}</span>
          <span className={`block text-[10px] font-semibold ${active ? 'text-sky-200' : 'text-gray-500'}`}>
            {ruleCount} rules
          </span>
        </span>
        {loading ? <Loader2 className="w-3.5 h-3.5 animate-spin flex-shrink-0" /> : (
          <ChevronRight className={`w-3.5 h-3.5 flex-shrink-0 transition-transform duration-200 ${expanded ? 'rotate-90' : ''} ${active ? 'text-sky-200' : 'text-gray-400'}`} />
        )}
      </button>
      <div className={`grid transition-[grid-template-rows] duration-300 ease-out ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden">{expanded && children}</div>
      </div>
    </li>
  );
}

/**
 * One feature's rules as a tree of rows. A row with parts has a chevron that
 * opens it in place; clicking the name selects the rule for the right pane.
 * While searching, every branch that leads to a match is shown open.
 */
export function RuleTreeNav({ index, selectedId, openIds, onToggle, onSelect, query }: {
  index: RuleIndex; selectedId: string | null; openIds: Set<string>;
  onToggle: (id: string) => void; onSelect: (id: string) => void; query: string;
}) {
  const q = query.trim().toLowerCase();
  const hits = React.useMemo(() => {
    if (!q) return null;
    const keep = new Set<string>();
    for (const r of index.order) {
      if (`${r.name} ${r.summary ?? ''}`.toLowerCase().includes(q)) {
        keep.add(r.id);
        for (let p = r.parent ? index.byId.get(r.parent) : undefined; p; p = p.parent ? index.byId.get(p.parent) : undefined) keep.add(p.id);
      }
    }
    return keep;
  }, [q, index]);

  const render = (r: Rule, depth: number): React.ReactNode => {
    if (hits && !hits.has(r.id)) return null;
    const kids = index.children.get(r.id) ?? [];
    const open = hits ? true : openIds.has(r.id);
    const selected = r.id === selectedId;
    const dot = (r.kind && KIND[r.kind]?.dot) || 'bg-gray-300';
    return (
      <li key={r.id} className="relative">
        <div className={`group relative flex items-start rounded-lg transition-colors ${selected ? 'bg-hp-blue/10' : 'hover:bg-white/80'}`}
          style={{ paddingLeft: depth * 14 }}>
          {selected && <span className="absolute top-1.5 bottom-1.5 w-[3px] rounded-full bg-hp-blue" style={{ left: depth * 14 - 2 }} aria-hidden />}
          {kids.length ? (
            <button type="button" onClick={() => onToggle(r.id)} aria-label={open ? `Collapse ${r.name}` : `Expand ${r.name}`}
              className="mt-[5px] ml-1 p-0.5 rounded text-gray-400 hover:text-hp-blue hover:bg-white transition-colors">
              <ChevronRight className={`w-3 h-3 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
            </button>
          ) : (
            <span className="mt-[11px] ml-[9px] mr-[5px] h-1.5 w-1.5 rounded-full flex-shrink-0" aria-hidden>
              <span className={`block h-1.5 w-1.5 rounded-full ${dot}`} />
            </span>
          )}
          <button type="button" onClick={() => onSelect(r.id)} aria-current={selected ? 'true' : undefined}
            className={`min-w-0 flex-1 text-left px-1.5 py-1.5 text-[12px] leading-snug rounded-lg focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy ${
              selected ? 'font-bold text-hp-dark' : depth === 0 ? 'font-semibold text-gray-800 group-hover:text-hp-blue' : 'text-gray-600 group-hover:text-hp-blue'}`}>
            <span className="line-clamp-2">{r.name}</span>
          </button>
          {!!kids.length && <span className="mt-1.5 mr-1.5 text-[10px] font-semibold text-gray-400 tabular-nums">{kids.length}</span>}
        </div>
        {!!kids.length && (
          <div className={`grid transition-[grid-template-rows] duration-200 ease-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
            <div className="overflow-hidden relative">
              {/* The guide line runs down from the parent's chevron. */}
              <span className="absolute top-0 bottom-1 w-px bg-sky-200/80" style={{ left: depth * 14 + 11 }} aria-hidden />
              <ul className="space-y-px">{kids.map(c => render(c, depth + 1))}</ul>
            </div>
          </div>
        )}
      </li>
    );
  };

  const rows = index.roots.map(r => render(r, 0)).filter(Boolean);
  return (
    <div className="pl-2 pr-1 pt-1.5 pb-2">
      {rows.length ? <ul className="space-y-px">{rows}</ul> : <p className="px-3 py-2 text-[11px] text-gray-500">No rule matches “{query}”.</p>}
    </div>
  );
}

// ------------------------------------------------------------------ rule detail

function Section({ title, Icon, children }: { title: string; Icon: React.FC<{ className?: string }>; children: React.ReactNode }) {
  return (
    <section className="grid grid-cols-1 sm:grid-cols-[9rem_1fr] gap-1 sm:gap-4 py-3.5 border-t border-gray-100 first:border-t-0">
      <h4 className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-gray-500 pt-0.5">
        <Icon className="w-3.5 h-3.5 text-hp-navy" />{title}
      </h4>
      <div className="text-[13px] leading-relaxed text-gray-800 min-w-0">{children}</div>
    </section>
  );
}

function Bullets({ items }: { items: string[] }) {
  return (
    <ul className="space-y-1">
      {items.map((s, i) => (
        <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 rounded-full bg-hp-navy flex-shrink-0" /><span>{s}</span></li>
      ))}
    </ul>
  );
}

function VerifiedBadge() {
  return (
    <div className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 ring-1 ring-emerald-200 px-2.5 py-1 text-[11px] font-semibold text-emerald-800">
      <CheckCircle2 className="w-3.5 h-3.5" />Verified: the live calculation gives this result
    </div>
  );
}

export function RuleBody({ rule }: { rule: Rule }) {
  const ex = rule.example;
  return (
    <div>
      {rule.purpose && <Section title="Purpose" Icon={Target}>{rule.purpose}</Section>}
      {!!rule.inputs?.length && <Section title="Inputs" Icon={Database}><Bullets items={rule.inputs} /></Section>}
      {(rule.logic || rule.formula) && (
        <Section title="How it works" Icon={Calculator}>
          {rule.logic && <p className="whitespace-pre-line">{rule.logic}</p>}
          {rule.formula && (
            <pre className="mt-2 overflow-x-auto rounded-lg bg-hp-dark text-sky-100 px-3.5 py-2.5 text-[12px] leading-relaxed font-mono whitespace-pre-wrap shadow-inner">{rule.formula}</pre>
          )}
        </Section>
      )}
      {!!rule.constants?.length && (
        <Section title="Values in use" Icon={ListChecks}>
          <div className="flex flex-wrap gap-1.5">
            {rule.constants.map((c, i) => (
              <span key={i} className="inline-flex max-w-full items-stretch rounded-lg ring-1 ring-inset ring-sky-200 text-[11px] overflow-hidden">
                <span className="bg-white px-2 py-1 text-gray-600">{c.label}</span>
                <span className="px-2 py-1 font-bold tabular-nums break-words min-w-0 bg-sky-50 text-sky-800">{c.value}</span>
              </span>
            ))}
          </div>
        </Section>
      )}
      {rule.table && rule.table.rows.length > 0 && (
        <Section title="Table" Icon={Layers}>
          <div className="overflow-x-auto rounded-lg ring-1 ring-gray-200">
            <table className="w-full text-[12px]">
              <thead className="bg-gray-50 text-[10px] uppercase tracking-wider text-gray-500">
                <tr>{rule.table.columns.map(c => <th key={c} className="px-3 py-2 text-left font-bold">{c}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-gray-100 bg-white">
                {rule.table.rows.map((row, i) => (
                  <tr key={i}>{row.map((cell, j) => <td key={j} className={`px-3 py-1.5 ${j === 0 ? 'font-semibold text-gray-900' : 'text-gray-700'} tabular-nums`}>{cell}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
      {!!rule.conditions?.length && <Section title="Conditions" Icon={Filter}><Bullets items={rule.conditions} /></Section>}
      {ex && (ex.scenario || ex.steps?.length || ex.result) && (
        <Section title="Example" Icon={Lightbulb}>
          <div className="rounded-xl bg-gradient-to-br from-sky-50 to-white ring-1 ring-sky-100 p-3.5">
            {ex.scenario && <p className="text-gray-700">{ex.scenario}</p>}
            {!!ex.steps?.length && (
              <ol className="mt-2 space-y-1 text-[13px] text-gray-800">
                {ex.steps.map((s, i) => (
                  <li key={i} className="flex gap-2"><span className="text-sky-500 tabular-nums">{i + 1}.</span><span className="whitespace-pre-wrap">{s}</span></li>
                ))}
              </ol>
            )}
            {ex.result && (
              <p className="mt-2.5 pt-2.5 border-t border-sky-100 font-semibold text-gray-900">
                <span className="text-[10px] uppercase tracking-wider text-sky-700 mr-2">Result</span>{ex.result}
              </p>
            )}
            {ex.verified && <VerifiedBadge />}
          </div>
        </Section>
      )}
      {rule.output && <Section title="Produces" Icon={CheckCircle2}>{rule.output}</Section>}
    </div>
  );
}

/** A clickable row for a rule: used for a rule's parts and a feature's top-level rules. */
export function RuleRow({ rule, partCount, onSelect, index = 0 }: {
  rule: Rule; partCount: number; onSelect: () => void; index?: number;
}) {
  return (
    <button type="button" onClick={onSelect} style={{ ['--as-i' as string]: index } as React.CSSProperties}
      className="as-tile group w-full flex items-start gap-3 rounded-xl bg-white/80 ring-1 ring-gray-200 px-4 py-3 text-left transition-[box-shadow,transform,background-color] duration-200 hover:bg-white hover:shadow-md hover:-translate-y-px focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[13px] font-bold text-gray-900 group-hover:text-hp-blue transition-colors">{rule.name}</span>
          <KindBadge kind={rule.kind} />
          {partCount > 0 && <span className="text-[10px] font-semibold text-gray-400">{partCount} part{partCount === 1 ? '' : 's'}</span>}
        </div>
        {rule.summary && <p className="mt-0.5 text-xs text-gray-600 leading-relaxed">{rule.summary}</p>}
      </div>
      <ChevronRight className="w-4 h-4 mt-0.5 flex-shrink-0 text-gray-300 group-hover:text-hp-blue group-hover:translate-x-0.5 transition" />
    </button>
  );
}
