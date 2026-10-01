'use client';

/**
 * "My Activity": a slide-over on the dashboard where a seller sees their own
 * usage - the same numbers an admin sees for them on Analytics, and nobody
 * else's. Opened from the dashboard header; the dashboard stays where it was
 * underneath, so closing it puts the seller straight back on their account.
 */

import React, { useCallback, useEffect, useState } from 'react';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { featureLabel } from '@/lib/features';
import { flush } from '@/lib/track';
import { MyActivityResponse } from '@/types/analytics';
import {
  Card, DailyColumns, HorizontalBars, RangePicker, StatTile, Toggle,
  formatDateTime, formatDuration, utcDay,
} from '@/components/analytics/AnalyticsParts';
import { Activity, AlertCircle, Clock, Eye, LogIn, Loader2, Star, X } from 'lucide-react';

type Measure = 'time' | 'views';

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

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const t = data?.totals;
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
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px] cursor-default" />

      <div className="relative h-full w-full max-w-2xl bg-gray-50 shadow-2xl flex flex-col animate-fade-in">
        <div className="px-6 py-4 bg-white border-b border-gray-200">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-extrabold text-gray-900 flex items-center gap-2">
                <Activity className="w-5 h-5 text-hp-navy" />
                <span>My Activity</span>
              </h2>
              <p className="text-[11px] text-gray-500 mt-0.5">
                {userName ? `${userName} · ` : ''}Only you and your admin can see this. Dates are UTC.
              </p>
            </div>
            <button type="button" onClick={onClose} className="text-gray-400 hover:text-gray-700 rounded-lg p-1" title="Close (Esc)">
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="mt-3">
            <RangePicker compact from={from} to={to} onChange={(f, t2) => { setFrom(f); setTo(t2); }} />
          </div>
        </div>

        <div className={`flex-1 overflow-y-auto p-6 space-y-5 transition-opacity ${isLoading && data ? 'opacity-60' : ''}`}>
          {error && (
            <div className="bg-red-50 border-l-4 border-red-500 p-3 rounded-r-lg flex items-center gap-2 text-red-800 text-xs font-semibold">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}
          {from > to && (
            <div className="bg-amber-50 border-l-4 border-amber-500 p-3 rounded-r-lg text-amber-800 text-xs font-semibold">
              Choose a start date on or before the end date.
            </div>
          )}

          {isLoading && !data ? (
            <div className="py-20 flex flex-col items-center gap-3">
              <Loader2 className="w-7 h-7 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500">Loading your activity...</p>
            </div>
          ) : data && t && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <StatTile label="Time spent" value={formatDuration(t.time_seconds)} hint="Active time on features" Icon={Clock} />
                <StatTile label="Feature views" value={t.feature_views} hint={`${t.features_used} of ${data.features.length} features used`} Icon={Eye} />
                <StatTile label="Logins" value={t.logins} hint={t.last_login_at ? `Last: ${formatDateTime(t.last_login_at)}` : undefined} Icon={LogIn} />
                <StatTile label="Most used" value={<span className="text-xl">{t.top_feature ? featureLabel(t.top_feature) : '—'}</span>} hint="By time, then views" Icon={Star} />
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
                      <li key={`${r.ts}-${i}`} className="py-2 flex items-center justify-between gap-3 text-xs">
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
    </div>
  );
}
