'use client';

/**
 * Pieces shared by the admin Analytics page and the seller's My Activity
 * panel, so both draw the same numbers the same way.
 *
 * Charts are single-series (one hue, no legend; the title names the measure),
 * every bar carries its value as text so colour is never the only signal, and
 * zero is drawn as an empty track rather than left out.
 */

import React, { useEffect } from 'react';
import { ChevronRight, X } from 'lucide-react';

// Dates are UTC calendar days, inclusive at both ends - the API's contract.
export function utcDay(offsetDays = 0): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export const PRESETS = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
];

export function formatDateTime(value: string | null, withYear = false): string {
  if (!value) return '—';
  // Timestamps are UTC; a naive one from the API is UTC too.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, {
    ...(withYear ? { year: 'numeric' } : {}), month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/**
 * 0 -> "0m", 30 -> "30s", 90 -> "1m 30s", 1500 -> "25m", 3900 -> "1h 05m".
 * Seconds are shown under ten minutes so a total and its parts add up
 * (time arrives in 30-second steps); above that they are noise.
 */
export function formatDuration(seconds: number): string {
  if (!seconds) return '0m';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 600) {
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return s ? `${m}m ${s}s` : `${m}m`;
  }
  const m = Math.round(seconds / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${String(m % 60).padStart(2, '0')}m`;
}

/** A headline number. With `onClick` the whole tile opens the list behind it. */
export function StatTile({ label, value, hint, Icon, onClick }: {
  label: string; value: React.ReactNode; hint?: string; Icon: React.FC<{ className?: string }>;
  onClick?: () => void;
}) {
  const body = (
    <>
      <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-gray-500">
        <Icon className="w-4 h-4 text-hp-navy" />
        <span>{label}</span>
        {onClick && <ChevronRight className="w-3.5 h-3.5 ml-auto text-gray-300 group-hover:text-hp-navy transition-colors" />}
      </div>
      <div className="mt-2 text-3xl font-extrabold text-gray-900 tabular-nums truncate group-hover:text-hp-blue transition-colors">{value}</div>
      {hint && <div className="mt-1 text-[11px] text-gray-500 truncate">{hint}</div>}
    </>
  );
  if (!onClick) {
    return <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">{body}</div>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title="See the users behind this number"
      className="group text-left bg-white rounded-2xl border border-gray-200 shadow-sm p-5 hover:border-hp-navy/50 hover:shadow-md focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy transition"
    >
      {body}
    </button>
  );
}

export function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <h2 className="text-sm font-bold text-gray-900">{title}</h2>
      {subtitle && <p className="text-[11px] text-gray-500 mt-0.5">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

export interface BarRow {
  key: string;
  label: string;
  value: number;
  /** What the right-hand column prints; defaults to the value. */
  display?: string;
  /** Hover text with the detail behind the bar. */
  title?: string;
  /** Opens the detail behind the bar. Only offered when there is something to show. */
  onClick?: () => void;
}

/** Horizontal bars, every row shown - zero included, as an empty track. */
export function HorizontalBars({ rows }: { rows: BarRow[] }) {
  const max = Math.max(1, ...rows.map(r => r.value));
  return (
    <div className="space-y-2" role="list">
      {rows.map(r => {
        const clickable = !!r.onClick && r.value > 0;
        const cells = (
          <>
            <span className="text-xs font-semibold text-gray-700 truncate">{r.label}</span>
            <div className="h-3.5 bg-gray-100 rounded-sm">
              {r.value > 0 && (
                <div
                  className="h-full bg-hp-blue rounded-r group-hover:bg-hp-dark transition-colors"
                  style={{ width: `${(r.value / max) * 100}%` }}
                />
              )}
            </div>
            <span className={`text-xs tabular-nums text-right ${r.value ? 'font-bold text-gray-900' : 'text-gray-400'} ${clickable ? 'group-hover:text-hp-blue group-hover:underline' : ''}`}>
              {r.display ?? r.value}
            </span>
          </>
        );
        const grid = 'group grid grid-cols-[minmax(0,11rem)_1fr_3.5rem] items-center gap-3 rounded-md px-1 py-0.5 hover:bg-gray-50 w-full text-left';
        return clickable ? (
          <button key={r.key} type="button" role="listitem" onClick={r.onClick} title={r.title}
            className={`${grid} cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy`}>
            {cells}
          </button>
        ) : (
          <div key={r.key} role="listitem" title={r.title} className={grid}>{cells}</div>
        );
      })}
    </div>
  );
}

/** One column per day. Hover gives the number; the peak is labelled. */
export function DailyColumns({ points, format = String, unit, onPointClick }: {
  points: { date: string; value: number }[];
  format?: (n: number) => string;
  unit: string;
  /** Opens the detail behind a day. Only days with a value are clickable. */
  onPointClick?: (date: string) => void;
}) {
  const max = Math.max(1, ...points.map(p => p.value));
  const peak = points.reduce((a, p) => (p.value > a.value ? p : a), points[0] ?? { date: '', value: 0 });
  return (
    <div>
      <div className="flex items-end gap-[2px] h-32 border-b border-gray-200">
        {points.map(p => (
          <div
            key={p.date}
            className={`group relative flex-1 h-full flex items-end ${onPointClick && p.value ? 'cursor-pointer' : ''}`}
            title={`${p.date}: ${format(p.value)} ${unit}${onPointClick && p.value ? ' - click to see who' : ''}`}
            onClick={onPointClick && p.value ? () => onPointClick(p.date) : undefined}
            role={onPointClick && p.value ? 'button' : undefined}
            tabIndex={onPointClick && p.value ? 0 : undefined}
            onKeyDown={onPointClick && p.value ? e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onPointClick(p.date); } } : undefined}
          >
            <div
              className="w-full bg-hp-blue group-hover:bg-hp-dark rounded-t transition-colors"
              style={{ height: p.value ? `${Math.max(3, (p.value / max) * 100)}%` : '0' }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-1.5 text-[10px] text-gray-500 tabular-nums">
        <span>{points[0]?.date}</span>
        {peak.value > 0 && <span>Peak {format(peak.value)} on {peak.date}</span>}
        <span>{points[points.length - 1]?.date}</span>
      </div>
    </div>
  );
}

/** Preset buttons plus from/to date inputs. */
export function RangePicker({ from, to, onChange, compact = false }: {
  from: string; to: string; onChange: (from: string, to: string) => void; compact?: boolean;
}) {
  const activePreset = to === utcDay(0) ? PRESETS.find(p => from === utcDay(-(p.days - 1)))?.days : undefined;
  const input = 'px-2 py-1.5 border border-gray-300 rounded-lg text-xs bg-gray-50 focus:outline-none focus:ring-2 focus:ring-hp-navy';
  return (
    <div className="flex flex-wrap items-center gap-2">
      {PRESETS.map(p => (
        <button
          key={p.days}
          type="button"
          onClick={() => onChange(utcDay(-(p.days - 1)), utcDay(0))}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
            activePreset === p.days ? 'bg-hp-navy text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
          }`}
        >
          {p.label}
        </button>
      ))}
      {!compact && <span className="w-px h-6 bg-gray-200 mx-1" />}
      <label className="text-[11px] font-bold text-gray-500 uppercase">From</label>
      <input type="date" value={from} max={to} onChange={e => onChange(e.target.value, to)} className={input} />
      <label className="text-[11px] font-bold text-gray-500 uppercase">To</label>
      <input type="date" value={to} min={from} onChange={e => onChange(from, e.target.value)} className={input} />
    </div>
  );
}

/** A small segmented control for switching what a chart measures. */
export function Toggle<T extends string>({ value, options, onChange }: {
  value: T; options: { key: T; label: string }[]; onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex rounded-lg bg-gray-100 p-0.5">
      {options.map(o => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          className={`px-2.5 py-1 rounded-md text-[11px] font-bold transition ${
            value === o.key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-800'
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export interface UserListRow {
  user_id: string;
  name: string;
  email: string;
  is_active: boolean;
  /** The number this list explains, for this user (e.g. "12 views"). */
  value?: string;
  /** Secondary detail under the value (e.g. "last login 1 Oct"). */
  detail?: string;
}

/**
 * The people behind a number on the Analytics page. Rows arrive already
 * sorted by the caller; the count in the header always equals the number
 * that was clicked.
 */
export function UserListDialog({ title, subtitle, rows, onClose }: {
  title: string; subtitle?: string; rows: UserListRow[]; onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Close" onClick={onClose}
        className="absolute inset-0 bg-slate-900/50 backdrop-blur-[1px] cursor-default" />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col border border-gray-200 animate-fade-in">
        <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-gray-200">
          <div className="min-w-0">
            <h3 className="text-base font-bold text-gray-900">{title}</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">
              {rows.length} user{rows.length === 1 ? '' : 's'}{subtitle ? ` · ${subtitle}` : ''}
            </p>
          </div>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-700 rounded-lg p-1" title="Close (Esc)">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto">
          {rows.length === 0 ? (
            <p className="px-6 py-10 text-center text-xs text-gray-500">Nobody in this range.</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {rows.map(r => (
                <li key={r.user_id} className="px-6 py-3 flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <div className="text-sm font-bold text-gray-900 truncate">
                      {r.name || r.email}
                      {!r.is_active && (
                        <span className="ml-2 align-middle inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-600">Deactivated</span>
                      )}
                    </div>
                    <div className="text-[11px] text-gray-500 truncate">{r.email}</div>
                  </div>
                  {(r.value || r.detail) && (
                    <div className="text-right shrink-0">
                      {r.value && <div className="text-xs font-bold text-gray-900 tabular-nums">{r.value}</div>}
                      {r.detail && <div className="text-[11px] text-gray-500 tabular-nums">{r.detail}</div>}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
