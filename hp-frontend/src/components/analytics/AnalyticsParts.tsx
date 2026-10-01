'use client';

/**
 * Pieces shared by the admin Analytics page and the seller's My Activity
 * panel, so both draw the same numbers the same way.
 *
 * Charts are single-series (one hue, no legend; the title names the measure),
 * every bar carries its value as text so colour is never the only signal, and
 * zero is drawn as an empty track rather than left out.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronRight, X } from 'lucide-react';
import { CountUp, CountUpText, Reveal, SlidingSegments, growDelay, prefersReducedMotion } from '@/components/common/motion';

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

/** A headline number. With `onClick` the whole tile opens the list behind it.
 *  A numeric value counts up to itself; `index` staggers a row of tiles. */
export function StatTile({ label, value, hint, Icon, onClick, index = 0 }: {
  label: string; value: React.ReactNode; hint?: string; Icon: React.FC<{ className?: string }>;
  onClick?: () => void; index?: number;
}) {
  const stagger = { ['--as-i' as string]: index } as React.CSSProperties;
  const body = (
    <>
      <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-gray-500">
        <Icon className="w-4 h-4 text-hp-navy" />
        <span>{label}</span>
        {onClick && <ChevronRight className="w-3.5 h-3.5 ml-auto text-gray-300 group-hover:text-hp-navy transition-colors" />}
      </div>
      <div className="mt-2 text-3xl font-extrabold text-gray-900 tabular-nums truncate group-hover:text-hp-blue transition-colors">
        {typeof value === 'number' ? <CountUp value={value} delay={index * 55} />
          : typeof value === 'string' ? <CountUpText text={value} first delay={index * 55} /> : value}
      </div>
      {hint && <div className="mt-1 text-[11px] text-gray-500 truncate">{hint}</div>}
    </>
  );
  if (!onClick) {
    return <div className="as-tile as-glass rounded-2xl p-5" style={stagger}>{body}</div>;
  }
  return (
    <button
      type="button"
      onClick={onClick}
      title="See what is behind this number"
      style={stagger}
      className="as-tile as-tile-btn as-glass group text-left rounded-2xl p-5 hover:border-hp-navy/40 focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy"
    >
      {body}
    </button>
  );
}

export function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Reveal className="as-glass-strong rounded-2xl p-6">
      <h2 key={title} className="as-swap text-sm font-bold text-gray-900">{title}</h2>
      {subtitle && <p className="text-[11px] text-gray-500 mt-0.5">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </Reveal>
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
      {rows.map((r, i) => {
        const clickable = !!r.onClick && r.value > 0;
        const delay = growDelay(i);
        const cells = (
          <>
            <span className="text-xs font-semibold text-gray-700 truncate">{r.label}</span>
            <div className="h-3.5 bg-gray-100 rounded-sm overflow-hidden">
              {/* Always rendered, scaled to the value, so a new measure or
                  range glides from the old length instead of jumping. */}
              <div
                className="as-bar-x h-full bg-hp-blue rounded-sm group-hover:bg-hp-dark"
                style={{ transform: `scaleX(${r.value / max})`, ['--as-d' as string]: `${delay}ms` }}
              />
            </div>
            <span className={`text-xs tabular-nums text-right ${r.value ? 'font-bold text-gray-900' : 'text-gray-400'} ${clickable ? 'group-hover:text-hp-blue group-hover:underline' : ''}`}>
              <CountUpText text={r.display ?? r.value} first delay={delay} />
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
        {points.map((p, i) => (
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
              className="as-bar-y w-full h-full bg-hp-blue group-hover:bg-hp-dark rounded-t"
              style={{
                transform: `scaleY(${p.value ? Math.max(0.03, p.value / max) : 0})`,
                ['--as-d' as string]: `${growDelay(i, 80, 12, 40)}ms`,
              }}
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
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-colors duration-200 active:scale-95 ${
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
    <SlidingSegments
      size="sm"
      ariaLabel="Measure"
      value={value}
      onChange={onChange}
      options={options.map(o => ({ value: o.key, label: o.label }))}
    />
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

export interface DetailRow {
  key: string;
  primary: React.ReactNode;
  secondary?: React.ReactNode;
  /** The number this row contributes (e.g. "12 views"). */
  value?: string;
  /** Secondary detail under the value. */
  detail?: string;
}

/**
 * The list behind a clicked number. Rows arrive already sorted by the caller;
 * `count` names how many there are, so it can match the number clicked.
 */
export function DetailDialog({ title, count, subtitle, rows, emptyText = 'Nothing in this range.', onClose }: {
  title: string; count: string; subtitle?: string; rows: DetailRow[]; emptyText?: string; onClose: () => void;
}) {
  // The parent unmounts the dialog on close, so the exit plays here first.
  const [closing, setClosing] = useState(false);
  const timer = useRef<number>();
  const close = useCallback(() => {
    if (prefersReducedMotion()) { onClose(); return; }
    setClosing(true);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(onClose, 180);
  }, [onClose]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') close(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [close]);
  const state = closing ? ' is-closing' : '';

  return (
    // Above the My Activity slide-over, which is itself z-50.
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" aria-label="Close" onClick={close}
        className={`as-backdrop${state} absolute inset-0 bg-slate-900/40 backdrop-blur-md cursor-default`} />
      <div className={`as-dialog${state} as-glass-strong relative rounded-2xl w-full max-w-lg max-h-[80vh] flex flex-col`}>
        <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-slate-200/70">
          <div className="min-w-0">
            <h3 className="text-base font-bold text-gray-900">{title}</h3>
            <p className="text-[11px] text-gray-500 mt-0.5">{count}{subtitle ? ` · ${subtitle}` : ''}</p>
          </div>
          <button type="button" onClick={close} className="text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg p-1 transition-colors" title="Close (Esc)">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto">
          {rows.length === 0 ? (
            <p className="px-6 py-10 text-center text-xs text-gray-500">{emptyText}</p>
          ) : (
            <ul className="divide-y divide-gray-100">
              {rows.map((r, i) => (
                <li key={r.key} className="as-row px-6 py-3 flex items-center justify-between gap-4"
                  style={{ ['--as-i' as string]: Math.min(i, 10) }}>
                  <div className="min-w-0">
                    <div className="text-sm font-bold text-gray-900 truncate">{r.primary}</div>
                    {r.secondary && <div className="text-[11px] text-gray-500 truncate">{r.secondary}</div>}
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

/** The people behind a number on the Analytics page. */
export function UserListDialog({ title, subtitle, rows, onClose }: {
  title: string; subtitle?: string; rows: UserListRow[]; onClose: () => void;
}) {
  return (
    <DetailDialog
      title={title}
      subtitle={subtitle}
      count={`${rows.length} user${rows.length === 1 ? '' : 's'}`}
      emptyText="Nobody in this range."
      onClose={onClose}
      rows={rows.map(r => ({
        key: r.user_id,
        primary: (
          <>
            {r.name || r.email}
            {!r.is_active && (
              <span className="ml-2 align-middle inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold bg-gray-100 text-gray-600">Deactivated</span>
            )}
          </>
        ),
        secondary: r.email,
        value: r.value,
        detail: r.detail,
      }))}
    />
  );
}
