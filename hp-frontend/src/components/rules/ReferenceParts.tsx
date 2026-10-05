'use client';

/**
 * The "Rule books" pane of the admin Rules page: one fixed rule set - the HP
 * sales rulebook, the product lifecycle, the topic dictionary - listed entry by
 * entry, searchable, with the rulebook's rules filterable by family.
 */

import React, { useMemo, useState } from 'react';
import { BookMarked, ChevronRight, Search, X } from 'lucide-react';
import type { ReferenceEntry, ReferenceSection, ReferenceSet } from '@/types/rules';
import { featureLabel } from '@/lib/features';

const matches = (q: string, ...parts: (string | string[])[]) =>
  !q || parts.some(p => (Array.isArray(p) ? p.join(' ') : p).toLowerCase().includes(q));

function SearchBox({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder: string }) {
  return (
    <label className="flex items-center gap-2 rounded-lg bg-white ring-1 ring-gray-200 focus-within:ring-2 focus-within:ring-hp-navy px-2.5 py-1.5 w-full sm:w-72 transition-shadow">
      <Search className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        className="min-w-0 flex-1 bg-transparent text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none" />
      {value && (
        <button type="button" onClick={() => onChange('')} aria-label="Clear search" className="text-gray-400 hover:text-gray-700">
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </label>
  );
}

function EntryRow({ entry, open, onToggle, index }: { entry: ReferenceEntry; open: boolean; onToggle: () => void; index: number }) {
  const lead = entry.fields.find(f => f.label.startsWith('Use when'));
  return (
    <div style={{ ['--as-i' as string]: Math.min(index, 12) } as React.CSSProperties}
      className={`as-tile rounded-xl ring-1 transition-[box-shadow,background-color] duration-200 ${open ? 'bg-white ring-sky-200 shadow-md' : 'bg-white/80 ring-gray-200 hover:bg-white hover:shadow-sm'}`}>
      <button type="button" onClick={onToggle} aria-expanded={open}
        className="w-full flex items-start gap-3 px-4 py-3 text-left rounded-xl focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy">
        <ChevronRight className={`w-4 h-4 mt-0.5 flex-shrink-0 text-hp-navy transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            {entry.label && <span className="rounded-md bg-hp-dark text-white px-1.5 py-0.5 text-[10px] font-bold tabular-nums">{entry.label}</span>}
            <span className="text-[13px] font-bold text-gray-900">{entry.title}</span>
            {entry.badges.map(b => (
              <span key={b} className="rounded-full bg-amber-50 text-amber-800 ring-1 ring-inset ring-amber-200 px-2 py-0.5 text-[10px] font-bold">{b}</span>
            ))}
          </span>
          {!open && lead && typeof lead.value === 'string' && (
            <span className="mt-0.5 block text-xs text-gray-600 line-clamp-1">{lead.value}</span>
          )}
        </span>
        <span className="hidden sm:block flex-shrink-0 text-[10px] font-semibold text-gray-400">{entry.group}</span>
      </button>
      <div className={`grid transition-[grid-template-rows] duration-300 ease-out ${open ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}>
        <div className="overflow-hidden">
          {open && (
            <dl className="as-fade px-4 sm:pl-11 pb-4 space-y-3">
              {entry.fields.map(f => (
                <div key={f.label} className="grid grid-cols-1 sm:grid-cols-[11rem_1fr] gap-1 sm:gap-4">
                  <dt className="text-[10px] font-bold uppercase tracking-wider text-gray-500 pt-0.5">{f.label}</dt>
                  <dd className="text-[13px] leading-relaxed text-gray-800 min-w-0">
                    {Array.isArray(f.value) ? (
                      <ul className="space-y-1">
                        {f.value.map((v, i) => (
                          <li key={i} className="flex gap-2"><span className="mt-2 h-1 w-1 rounded-full bg-hp-navy flex-shrink-0" /><span>{v}</span></li>
                        ))}
                      </ul>
                    ) : f.value}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </div>
    </div>
  );
}

function EntriesSection({ section, query }: { section: Extract<ReferenceSection, { kind: 'entries' }>; query: string }) {
  const [group, setGroup] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const q = query.trim().toLowerCase();
  const shown = section.entries.filter(e => (!group || e.group === group)
    && matches(q, e.label, e.title, ...e.fields.map(f => f.value)));
  const counts = useMemo(() => {
    const c = new Map<string, number>();
    section.entries.forEach(e => c.set(e.group, (c.get(e.group) ?? 0) + 1));
    return c;
  }, [section]);
  const toggle = (id: string) => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });

  return (
    <div>
      <div className="flex flex-wrap gap-1.5">
        {[null, ...section.groups].map(g => {
          const active = group === g;
          return (
            <button key={g ?? 'all'} type="button" onClick={() => setGroup(g)}
              className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset transition-colors ${
                active ? 'bg-hp-dark text-white ring-hp-dark' : 'bg-white text-gray-700 ring-gray-200 hover:ring-hp-navy hover:text-hp-blue'}`}>
              {g ?? 'All'} <span className={active ? 'text-sky-200' : 'text-gray-400'}>{g ? counts.get(g) : section.entries.length}</span>
            </button>
          );
        })}
      </div>
      <p className="mt-3 text-[11px] text-gray-500">{shown.length} of {section.entries.length} rules. Select a rule to read it in full.</p>
      <div className="mt-2 space-y-2">
        {shown.map((e, i) => <EntryRow key={e.id} entry={e} index={i} open={open.has(e.id)} onToggle={() => toggle(e.id)} />)}
        {!shown.length && <p className="rounded-xl bg-white/80 ring-1 ring-gray-200 p-4 text-xs text-gray-500">No rule matches.</p>}
      </div>
    </div>
  );
}

function TableSection({ section, query }: { section: Extract<ReferenceSection, { kind: 'table' }>; query: string }) {
  const q = query.trim().toLowerCase();
  const rows = section.rows.filter(r => matches(q, ...r));
  return (
    <div>
      <p className="text-[11px] text-gray-500">{rows.length} of {section.rows.length} rows.</p>
      <div className="mt-2 max-h-[70vh] overflow-auto rounded-xl ring-1 ring-gray-200 bg-white">
        <table className="w-full text-[12px]">
          <thead className="sticky top-0 z-10 bg-gray-50 text-[10px] uppercase tracking-wider text-gray-500 shadow-[0_1px_0_rgb(229_231_235)]">
            <tr>{section.columns.map(c => <th key={c} className="px-3 py-2 text-left font-bold whitespace-nowrap">{c}</th>)}</tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row, i) => (
              <tr key={i} className="align-top hover:bg-sky-50/40">
                {row.map((cell, j) => (
                  <td key={j} className={`px-3 py-2 leading-relaxed ${j === 0 ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>{cell || '—'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        {!rows.length && <p className="p-4 text-xs text-gray-500">No row matches.</p>}
      </div>
    </div>
  );
}

export function ReferenceView({ data, onOpenFeature }: { data: ReferenceSet; onOpenFeature: (key: string) => void }) {
  const [sectionId, setSectionId] = useState(data.sections[0]?.id);
  const [query, setQuery] = useState('');
  const section = data.sections.find(s => s.id === sectionId) ?? data.sections[0];

  return (
    <div className="space-y-5">
      <div className="as-rise as-glass-strong rounded-2xl p-5 sm:p-6">
        <div className="flex items-start gap-3.5">
          <span className="flex-shrink-0 rounded-xl bg-hp-dark text-white p-2.5 shadow-md"><BookMarked className="w-5 h-5" /></span>
          <div className="min-w-0">
            <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">{data.title}</h2>
            <p className="mt-1 text-[13px] leading-relaxed text-gray-600">{data.summary}</p>
            <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px]">
              <span className="font-bold uppercase tracking-wider text-[10px] text-gray-500 mr-1">Used by</span>
              {data.used_by.map(k => (
                <button key={k} type="button" onClick={() => onOpenFeature(k)}
                  className="rounded-full bg-white ring-1 ring-gray-200 px-2.5 py-0.5 font-semibold text-gray-700 hover:ring-hp-navy hover:text-hp-blue transition-colors">
                  {featureLabel(k)}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {data.sections.length > 1 && (
        <div className="as-rise flex flex-wrap gap-1.5" role="tablist" style={{ ['--as-delay' as string]: '50ms' }}>
          {data.sections.map(s => {
            const active = s.id === section?.id;
            const n = s.kind === 'entries' ? s.entries.length : s.rows.length;
            return (
              <button key={s.id} type="button" role="tab" aria-selected={active} onClick={() => setSectionId(s.id)}
                className={`rounded-xl px-3.5 py-2 text-xs font-bold transition-[background-color,box-shadow,color] ${
                  active ? 'bg-hp-dark text-white shadow-md' : 'as-glass text-gray-700 hover:text-hp-blue'}`}>
                {s.title} <span className={active ? 'text-sky-200' : 'text-gray-400'}>{n}</span>
              </button>
            );
          })}
        </div>
      )}

      {section && (
        <section key={section.id} className="as-rise as-glass-strong rounded-2xl p-5 sm:p-6" style={{ ['--as-delay' as string]: '90ms' }}>
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
            <div className="min-w-0">
              <h3 className="text-sm font-extrabold text-gray-900">{section.title}</h3>
              <p className="mt-0.5 text-xs leading-relaxed text-gray-600 max-w-2xl">{section.description}</p>
            </div>
            <SearchBox value={query} onChange={setQuery} placeholder={`Search ${section.title.toLowerCase()}`} />
          </div>
          <div className="mt-4">
            {section.kind === 'entries'
              ? <EntriesSection section={section} query={query} />
              : <TableSection section={section} query={query} />}
          </div>
        </section>
      )}
    </div>
  );
}
