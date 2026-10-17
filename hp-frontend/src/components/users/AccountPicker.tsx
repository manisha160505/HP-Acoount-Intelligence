'use client';

import React, { useMemo, useState } from 'react';
import { Search } from 'lucide-react';

export interface PickableAccount { id: string; name: string; status?: string }

/**
 * Tick the accounts a seller may open. Search narrows the list; "Select shown"
 * and "Clear" act on what is visible, so a filtered list can be ticked at once.
 */
export function AccountPicker({ accounts, selected, onChange }: {
  accounts: PickableAccount[];
  selected: Set<string>;
  onChange: (next: Set<string>) => void;
}) {
  const [query, setQuery] = useState('');
  const [onlySelected, setOnlySelected] = useState(false);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return accounts
      .filter((a) => !q || a.name.toLowerCase().includes(q))
      .filter((a) => !onlySelected || selected.has(a.id));
  }, [accounts, query, onlySelected, selected]);

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    onChange(next);
  };
  const selectShown = () => onChange(new Set(Array.from(selected).concat(shown.map((a) => a.id))));
  const clearShown = () => {
    const ids = new Set(shown.map((a) => a.id));
    onChange(new Set(Array.from(selected).filter((id) => !ids.has(id))));
  };

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <div className="p-2.5 bg-gray-50 border-b border-gray-200 space-y-2">
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search accounts"
            aria-label="Search accounts"
            className="w-full pl-8 pr-3 py-2 text-xs border border-gray-300 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-hp-navy"
          />
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="font-bold text-gray-700">{selected.size} selected</span>
          <div className="flex items-center gap-3">
            <label className="inline-flex items-center gap-1.5 text-gray-600 cursor-pointer">
              <input type="checkbox" checked={onlySelected} onChange={(e) => setOnlySelected(e.target.checked)} />
              Only selected
            </label>
            <button type="button" onClick={selectShown} className="font-bold text-hp-navy hover:underline">Select shown</button>
            <button type="button" onClick={clearShown} className="font-bold text-gray-500 hover:underline">Clear shown</button>
          </div>
        </div>
      </div>
      <ul className="max-h-64 overflow-y-auto divide-y divide-gray-100">
        {shown.length === 0 ? (
          <li className="px-3 py-6 text-center text-xs text-gray-500">No accounts match.</li>
        ) : shown.map((a) => (
          <li key={a.id}>
            <label className="flex items-center gap-2.5 px-3 py-2 text-xs hover:bg-slate-50 cursor-pointer">
              <input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} />
              <span className="flex-1 text-gray-800">{a.name}</span>
              {a.status && a.status !== 'active' && (
                <span className="text-[10px] font-bold uppercase text-gray-400">{a.status}</span>
              )}
            </label>
          </li>
        ))}
      </ul>
    </div>
  );
}
