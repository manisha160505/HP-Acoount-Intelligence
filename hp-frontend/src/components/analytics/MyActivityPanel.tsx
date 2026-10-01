'use client';

/**
 * "My Activity": a slide-over on the dashboard where a seller sees their own
 * usage - the same numbers an admin sees for them on Analytics, and nobody
 * else's. Opened from the dashboard header; the dashboard stays where it was
 * underneath, so closing it puts the seller straight back on their account.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { featureLabel } from '@/lib/features';
import { flush } from '@/lib/track';
import { MyActivityResponse } from '@/types/analytics';
import {
  Card, DailyColumns, DetailDialog, DetailRow, HorizontalBars, RangePicker, StatTile, Toggle,
  formatDateTime, formatDuration, utcDay,
} from '@/components/analytics/AnalyticsParts';
import { ParallaxBand, usePresence } from '@/components/common/motion';
import { Activity, AlertCircle, Clock, Eye, LogIn, Loader2, Star, X } from 'lucide-react';

type Measure = 'time' | 'views';

interface Drill { title: string; count: string; subtitle?: string; rows: DetailRow[]; emptyText: string }

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * The list behind each tile, built from the same response the tile's number
 * came from, so a list's length or total matches what was clicked - the
 * seller's version of the admin drill-downs.
 */
function drills(data: MyActivityResponse) {
  const range = `${data.date_from} to ${data.date_to}`;
  const total = data.totals.time_seconds;
  const lastOpened = (iso: string | null) => (iso ? `last opened ${formatDateTime(iso)}` : 'not opened in this range');
  return {
    time: (): Drill => {
      const rows = data.per_feature.filter(f => f.time_seconds > 0).sort((a, b) => b.time_seconds - a.time_seconds);
      return {
        title: 'Where your time went', subtitle: range, count: plural(rows.length, 'feature'),
        emptyText: 'No time recorded in this range.',
        rows: rows.map(f => ({
          key: f.feature_key, primary: featureLabel(f.feature_key),
          secondary: `${plural(f.total_views, 'view')} · ${lastOpened(f.last_used_at)}`,
          value: formatDuration(f.time_seconds),
          detail: total ? `${Math.round((f.time_seconds / total) * 100)}% of your time` : undefined,
        })),
      };
    },
    views: (): Drill => {
      const rows = data.per_feature.filter(f => f.total_views > 0).sort((a, b) => b.total_views - a.total_views);
      return {
        title: 'Features you opened', subtitle: range, count: plural(rows.length, 'feature'),
        emptyText: 'No features opened in this range.',
        rows: rows.map(f => ({
          key: f.feature_key, primary: featureLabel(f.feature_key), secondary: lastOpened(f.last_used_at),
          value: plural(f.total_views, 'view'), detail: `${formatDuration(f.time_seconds)} spent`,
        })),
      };
    },
    logins: (): Drill => {
      const list = data.recent_logins ?? [];
      return {
        title: 'Your sign-ins', count: plural(data.totals.logins, 'login'),
        subtitle: list.length < data.totals.logins ? `latest ${list.length} shown · ${range}` : range,
        emptyText: 'No sign-ins in this range.',
        rows: list.map((ts, i) => ({
          key: `${ts}-${i}`, primary: formatDateTime(ts, true), secondary: timeAgo(ts),
        })),
      };
    },
    // Ranked by the rule that picks "Most used": time first, then views.
    mostUsed: (): Drill => {
      const rows = data.per_feature.filter(f => f.time_seconds > 0 || f.total_views > 0)
        .sort((a, b) => b.time_seconds - a.time_seconds || b.total_views - a.total_views);
      return {
        title: 'Your features, most used first', subtitle: 'by time, then views', count: plural(rows.length, 'feature'),
        emptyText: 'No features used in this range.',
        rows: rows.map((f, i) => ({
          key: f.feature_key,
          primary: (
            <>
              {featureLabel(f.feature_key)}
              {i === 0 && (
                <span className="ml-2 align-middle inline-flex px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-50 text-[#007DB8]">Most used</span>
              )}
            </>
          ),
          secondary: lastOpened(f.last_used_at),
          value: formatDuration(f.time_seconds), detail: plural(f.total_views, 'view'),
        })),
      };
    },
  };
}

function timeAgo(value: string): string {
  const t = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`).getTime();
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export function MyActivityPanel({ open, onClose, userName }: {
  open: boolean; onClose: () => void; userName?: string;
}) {
  const [from, setFrom] = useState(utcDay(-6));
  const [to, setTo] = useState(utcDay(0));
  const [data, setData] = useState<MyActivityResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [featureMeasure, setFeatureMeasure] = useState<Measure>('time');
  const [dailyMeasure, setDailyMeasure] = useState<Measure>('time');
  const [drill, setDrill] = useState<Drill | null>(null);
  const closeDrill = useCallback(() => setDrill(null), []);

  const load = useCallback(async (f: string, t: string) => {
    setIsLoading(true);
    setError(null);
    try {
      // Send anything still waiting in the tracking queue first, so the panel
      // includes what the seller did in the last few seconds. Never rejects.
      await flush();
      const res = await api.get<MyActivityResponse>('/me/activity', { params: { from: f, to: t } });
      setData(res.data);
    } catch (err) {
      setError(parseApiError(err, 'Could not load your activity.').message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Fetched on open (and on range change while open), so the numbers include
  // what the seller has just done.
  useEffect(() => {
    if (open && from && to && from <= to) load(from, to);
  }, [open, from, to, load]);

  // Esc closes an open breakdown first, not the whole panel.
  useEffect(() => {
    if (!open || drill) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose, drill]);
  useEffect(() => { if (!open) setDrill(null); }, [open]);

  // Stays mounted through the slide-out; the header band parallaxes with the
  // panel's own scroll, not the dashboard's behind it.
  const { mounted, closing } = usePresence(open, 240);
  const scrollRef = useRef<HTMLDivElement>(null);
  if (!mounted) return null;
  const state = closing ? ' is-closing' : '';

  const t = data?.totals;
  const d = data ? drills(data) : null;
  const noTimeYet = !!data && data.totals.time_seconds === 0;
  const featureRows = data ? data.per_feature.map(f => {
    const value = featureMeasure === 'time' ? f.time_seconds : f.total_views;
    return {
      key: f.feature_key,
      label: featureLabel(f.feature_key),
      value,
      display: featureMeasure === 'time' ? formatDuration(value) : String(value),
      title: `${featureLabel(f.feature_key)}: ${formatDuration(f.time_seconds)} spent, ${f.total_views} view(s), last opened ${formatDateTime(f.last_used_at)}`,
    };
  // Most-used first; unused features keep their sidebar order at the bottom.
  }).sort((a, b) => b.value - a.value) : [];

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="My activity">
      <button type="button" aria-label="Close" onClick={onClose}
        className={`as-backdrop${state} absolute inset-0 bg-slate-900/40 backdrop-blur-[2px] cursor-default`} />

      <div className={`as-sheet${state} as-page relative h-full w-full max-w-2xl shadow-2xl flex flex-col`}>
        <ParallaxBand scrollRef={scrollRef} fadeOnScroll={false}>
          <div className="px-6 pt-5 pb-5 flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-extrabold text-white flex items-center gap-2">
                <Activity className="w-5 h-5 text-[#7FD3FF]" />
                <span>My Activity</span>
              </h2>
              <p className="text-[11px] text-slate-300 mt-0.5">
                {userName ? `${userName} · ` : ''}Only you and your admin can see this. Dates are UTC.
              </p>
            </div>
            <button type="button" onClick={onClose} className="text-slate-300 hover:text-white hover:bg-white/10 rounded-lg p-1 transition-colors" title="Close (Esc)">
              <X className="w-5 h-5" />
            </button>
          </div>
        </ParallaxBand>
        <div className="px-6 py-3 bg-white/80 backdrop-blur-md border-b border-slate-200/70">
          <RangePicker compact from={from} to={to} onChange={(f, t2) => { setFrom(f); setTo(t2); }} />
        </div>

        <div ref={scrollRef} className={`flex-1 overflow-y-auto p-6 space-y-5 transition-opacity duration-300 ${isLoading && data ? 'opacity-60' : ''}`}>
          {error && (
            <div className="as-fade bg-red-50 border border-red-200 p-3 rounded-xl flex items-center gap-2 text-red-800 text-xs font-semibold">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {from > to && (
            <div className="as-fade bg-amber-50 border border-amber-200 p-3 rounded-xl text-amber-800 text-xs font-semibold">
              Choose a start date on or before the end date.
            </div>
          )}

          {isLoading && !data ? (
            <div className="as-fade py-20 flex flex-col items-center gap-3">
              <Loader2 className="w-7 h-7 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500">Loading your activity...</p>
            </div>
          ) : data && t && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatTile index={0} label="Time spent" value={formatDuration(t.time_seconds)} hint="Active time on features" Icon={Clock}
                  onClick={() => setDrill(d!.time())} />
                <StatTile index={1} label="Feature views" value={t.feature_views} hint={`${t.features_used} of ${data.features.length} features used`} Icon={Eye}
                  onClick={() => setDrill(d!.views())} />
                <StatTile index={2} label="Logins" value={t.logins} hint={t.last_login_at ? `Last: ${formatDateTime(t.last_login_at)}` : undefined} Icon={LogIn}
                  onClick={() => setDrill(d!.logins())} />
                <StatTile index={3} label="Most used" value={<span className="text-xl">{t.top_feature ? featureLabel(t.top_feature) : '—'}</span>} hint="By time, then views" Icon={Star}
                  onClick={() => setDrill(d!.mostUsed())} />
              </div>

              <Card title={featureMeasure === 'time' ? 'Time by feature' : 'Views by feature'} subtitle="All features, most used first.">
                <div className="mb-3">
                  <Toggle value={featureMeasure} onChange={setFeatureMeasure}
                    options={[{ key: 'time', label: 'Time' }, { key: 'views', label: 'Views' }]} />
                </div>
                <HorizontalBars rows={featureRows} />
              </Card>

              <Card title={dailyMeasure === 'time' ? 'Time per day' : 'Feature views per day'}>
                <div className="mb-3">
                  <Toggle value={dailyMeasure} onChange={setDailyMeasure}
                    options={[{ key: 'time', label: 'Time' }, { key: 'views', label: 'Views' }]} />
                </div>
                <DailyColumns
                  points={data.daily.map(d => ({ date: d.date, value: dailyMeasure === 'time' ? d.time_seconds : d.views }))}
                  format={dailyMeasure === 'time' ? formatDuration : String}
                  unit={dailyMeasure === 'time' ? '' : 'view(s)'}
                />
              </Card>

              <Card title="Recently opened" subtitle="Where you have been, newest first.">
                {data.recent.length === 0 ? (
                  <p className="text-xs text-gray-500">Nothing opened in this range yet.</p>
                ) : (
                  <ul className="divide-y divide-gray-100">
                    {data.recent.map((r, i) => (
                      <li key={`${r.ts}-${i}`} className="as-row py-2 flex items-center justify-between gap-3 text-xs"
                        style={{ ['--as-i' as string]: Math.min(i, 10) }}>
                        <div className="min-w-0">
                          <span className="font-bold text-gray-900">{featureLabel(r.feature_key)}</span>
                          {r.account_name && <span className="text-gray-500"> · {r.account_name}</span>}
                        </div>
                        <span className="text-gray-500 whitespace-nowrap tabular-nums" title={formatDateTime(r.ts, true)}>{timeAgo(r.ts)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>

              {data.top_accounts.length > 0 && (
                <Card title="Accounts you viewed most">
                  <ul className="divide-y divide-gray-100">
                    {data.top_accounts.map(a => (
                      <li key={a.account_id} className="py-1.5 flex justify-between text-xs">
                        <span className="font-semibold text-gray-800 truncate">{a.account_name || a.account_id}</span>
                        <span className="tabular-nums font-bold text-gray-900">{a.views} views</span>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              <p className="text-[11px] text-gray-500 leading-relaxed">
                Time counts while a feature is open in a visible tab and you have used the page in the last 5 minutes.
                {noTimeYet && ' Time tracking is new, so earlier days show views but no time.'}
              </p>
            </>
          )}
        </div>
      </div>
      {drill && (
        <DetailDialog title={drill.title} count={drill.count} subtitle={drill.subtitle}
          rows={drill.rows} emptyText={drill.emptyText} onClose={closeDrill} />
      )}
    </div>
  );
}
