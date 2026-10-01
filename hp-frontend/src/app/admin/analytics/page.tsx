'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { featureLabel } from '@/lib/features';
import { AnalyticsResponse, UserUsage } from '@/types/analytics';
import {
  Card, DailyColumns, HorizontalBars, RangePicker, StatTile, Toggle, UserListDialog, UserListRow,
  formatDateTime, formatDuration, utcDay,
} from '@/components/analytics/AnalyticsParts';
import { BarChart3, Loader2, AlertCircle, RefreshCw, Users, Activity, LogIn, Eye, Clock } from 'lucide-react';

type FeatureMeasure = 'users' | 'views' | 'time';
type CellMeasure = 'views' | 'time';

interface Drill { title: string; subtitle?: string; rows: UserListRow[] }

const totalViews = (u: UserUsage) => Object.values(u.feature_views).reduce((a, b) => a + b, 0);
const lastLogin = (u: UserUsage) => (u.last_login_at ? `Last login ${formatDateTime(u.last_login_at)}` : 'Never logged in');
const toRow = (u: UserUsage, value?: string, detail?: string): UserListRow => ({
  user_id: u.user_id, name: u.full_name, email: u.email, is_active: u.is_active, value, detail,
});
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/**
 * The list behind each clickable number. Every list is built from the same
 * response the number came from, so its length matches what was clicked.
 */
function drills(data: AnalyticsResponse) {
  const byId = new Map(data.per_user.map(u => [u.user_id, u]));
  const pick = (ids: string[] = []) => ids.map(id => byId.get(id)).filter((u): u is UserUsage => !!u);
  const byName = (a: UserUsage, b: UserUsage) => (a.full_name || a.email).localeCompare(b.full_name || b.email);
  const range = `${data.date_from} to ${data.date_to}`;
  return {
    total: (): Drill => ({
      title: 'All users', subtitle: 'every non-admin user, active or not',
      rows: [...data.per_user].sort(byName).map(u => toRow(u, plural(u.features_used, 'feature'), lastLogin(u))),
    }),
    active7d: (): Drill => ({
      title: 'Active in the last 7 days', subtitle: 'signed in or opened a feature',
      rows: pick(data.totals.active_user_ids_7d).sort(byName).map(u => toRow(u, undefined, lastLogin(u))),
    }),
    logins: (): Drill => ({
      title: 'Who logged in', subtitle: range,
      rows: data.per_user.filter(u => u.logins > 0).sort((a, b) => b.logins - a.logins)
        .map(u => toRow(u, plural(u.logins, 'login'), lastLogin(u))),
    }),
    views: (): Drill => ({
      title: 'Who opened features', subtitle: range,
      rows: data.per_user.filter(u => totalViews(u) > 0).sort((a, b) => totalViews(b) - totalViews(a))
        .map(u => toRow(u, plural(totalViews(u), 'view'), plural(u.features_used, 'feature'))),
    }),
    time: (): Drill => ({
      title: 'Time spent by user', subtitle: range,
      rows: data.per_user.filter(u => u.time_seconds > 0).sort((a, b) => b.time_seconds - a.time_seconds)
        .map(u => toRow(u, formatDuration(u.time_seconds), u.top_feature ? `Mostly ${featureLabel(u.top_feature)}` : undefined)),
    }),
    // A bar counts users by views (Users, Views) or by time (Time); the list
    // uses the same rule so its length matches the bar.
    feature: (f: string, measure: FeatureMeasure): Drill => {
      const v = (u: UserUsage) => u.feature_views[f] ?? 0;
      const t = (u: UserUsage) => u.feature_seconds?.[f] ?? 0;
      const users = data.per_user.filter(u => (measure === 'time' ? t(u) : v(u)) > 0)
        .sort((a, b) => (measure === 'time' ? t(b) - t(a) : v(b) - v(a)));
      return {
        title: featureLabel(f), subtitle: range,
        rows: users.map(u => toRow(u, plural(v(u), 'view'), `${formatDuration(t(u))} spent`)),
      };
    },
    day: (date: string): Drill => ({
      title: `Active on ${date}`, subtitle: 'UTC day',
      rows: pick(data.daily_active_users.find(d => d.date === date)?.user_ids).sort(byName).map(u => toRow(u)),
    }),
    account: (accountId: string): Drill => {
      const a = data.top_accounts.find(x => x.account_id === accountId);
      return {
        title: a?.account_name || accountId, subtitle: `viewed by, ${range}`,
        rows: pick(a?.user_ids).sort(byName).map(u => toRow(u)),
      };
    },
  };
}

export default function AdminAnalyticsPage() {
  const [from, setFrom] = useState(utcDay(-29));
  const [to, setTo] = useState(utcDay(0));
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [featureMeasure, setFeatureMeasure] = useState<FeatureMeasure>('users');
  const [cellMeasure, setCellMeasure] = useState<CellMeasure>('views');
  const [drill, setDrill] = useState<Drill | null>(null);
  const closeDrill = useCallback(() => setDrill(null), []);

  const fetchAnalytics = useCallback(async (f: string, t: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await api.get<AnalyticsResponse>('/admin/analytics', { params: { from: f, to: t } });
      setData(res.data);
    } catch (err) {
      setError(parseApiError(err, 'Failed to load analytics.').message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (from && to && from <= to) fetchAnalytics(from, to);
  }, [from, to, fetchAnalytics]);

  const rangeInvalid = !from || !to || from > to;
  const hasActivity = !!data && (data.totals.feature_views > 0 || data.totals.logins > 0 || data.totals.time_seconds > 0);
  const d = data ? drills(data) : null;

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="max-w-7xl mx-auto py-8 px-4 sm:px-6 lg:px-8">

        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-extrabold text-gray-900 tracking-tight flex items-center gap-2">
              <BarChart3 className="w-7 h-7 text-hp-navy" />
              <span>Usage Analytics</span>
            </h1>
            <p className="text-xs text-gray-500 mt-1 font-medium">
              Which features sellers use. Admin activity is excluded. Dates are UTC and inclusive.
            </p>
          </div>

          <div className="bg-white p-3 rounded-2xl border border-gray-200 shadow-sm flex flex-wrap items-center gap-2">
            <RangePicker from={from} to={to} onChange={(f, t) => { setFrom(f); setTo(t); }} />
            <button type="button" onClick={() => !rangeInvalid && fetchAnalytics(from, to)} title="Refresh"
              className="p-2 text-gray-500 hover:text-hp-navy rounded-lg hover:bg-gray-100 transition">
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>

        {rangeInvalid && (
          <div className="mb-6 bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-lg text-amber-800 text-xs font-semibold">
            Choose a start date on or before the end date.
          </div>
        )}

        {error && (
          <div className="mb-6 bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center space-x-2 text-red-800 text-xs font-semibold shadow-sm">
            <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {isLoading && !data ? (
          <div className="p-16 flex flex-col items-center justify-center space-y-3">
            <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
            <p className="text-xs text-gray-500 font-medium">Loading analytics...</p>
          </div>
        ) : data && (
          <div className={`space-y-6 transition-opacity ${isLoading ? 'opacity-60' : ''}`}>
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
              <StatTile label="Total users" value={data.totals.total_users} hint="Non-admin users, active or not" Icon={Users}
                onClick={() => setDrill(d!.total())} />
              <StatTile label="Active, last 7 days" value={data.totals.active_users_7d} hint="Signed in or opened a feature" Icon={Activity}
                onClick={() => setDrill(d!.active7d())} />
              <StatTile label="Logins" value={data.totals.logins} hint={`${data.date_from} to ${data.date_to}`} Icon={LogIn}
                onClick={() => setDrill(d!.logins())} />
              <StatTile label="Feature views" value={data.totals.feature_views} hint={`${data.date_from} to ${data.date_to}`} Icon={Eye}
                onClick={() => setDrill(d!.views())} />
              <StatTile label="Time spent" value={formatDuration(data.totals.time_seconds)} hint="Active time on features" Icon={Clock}
                onClick={() => setDrill(d!.time())} />
            </div>

            {!hasActivity && (
              <div className="bg-white rounded-2xl border border-dashed border-gray-300 p-6 text-center text-xs text-gray-500">
                No seller activity between {data.date_from} and {data.date_to}. Every feature is listed below at zero.
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card
                title={featureMeasure === 'users' ? 'Unique users per feature' : featureMeasure === 'views' ? 'Views per feature' : 'Time spent per feature'}
                subtitle="Every feature is listed; a grey zero means nobody used it in this range. Click a bar to see who."
              >
                <div className="mb-3">
                  <Toggle value={featureMeasure} onChange={setFeatureMeasure}
                    options={[{ key: 'users', label: 'Users' }, { key: 'views', label: 'Views' }, { key: 'time', label: 'Time' }]} />
                </div>
                <HorizontalBars rows={data.per_feature.map(f => {
                  const value = featureMeasure === 'users' ? f.unique_users : featureMeasure === 'views' ? f.total_views : f.time_seconds;
                  return {
                    key: f.feature_key,
                    label: featureLabel(f.feature_key),
                    value,
                    display: featureMeasure === 'time' ? formatDuration(value) : String(value),
                    title: `${featureLabel(f.feature_key)}: ${f.unique_users} user(s), ${f.total_views} view(s), ${formatDuration(f.time_seconds)} spent, last used ${formatDateTime(f.last_used_at)}`,
                    onClick: () => setDrill(d!.feature(f.feature_key, featureMeasure)),
                  };
                })} />
              </Card>
              <Card title="Daily active users" subtitle="Distinct sellers who signed in or opened a feature, per UTC day.">
                <DailyColumns
                  points={data.daily_active_users.map(p => ({ date: p.date, value: p.active_users }))}
                  unit="active user(s)"
                  onPointClick={date => setDrill(d!.day(date))}
                />
                {data.top_accounts.length > 0 && (
                  <div className="mt-6">
                    <h3 className="text-[11px] font-bold uppercase tracking-wider text-gray-500 mb-2">Most viewed accounts</h3>
                    <table className="w-full text-xs">
                      <tbody className="divide-y divide-gray-100">
                        {data.top_accounts.map(a => (
                          <tr key={a.account_id}>
                            <td className="py-1.5 text-gray-800 font-semibold truncate">{a.account_name || <span className="text-gray-400">{a.account_id}</span>}</td>
                            <td className="py-1.5 text-right tabular-nums text-gray-900 font-bold">{a.views} views</td>
                            <td className="py-1.5 text-right tabular-nums w-20">
                              <button type="button" onClick={() => setDrill(d!.account(a.account_id))}
                                className="text-hp-blue hover:underline font-semibold" title="See who viewed this account">
                                {a.unique_users} user{a.unique_users === 1 ? '' : 's'}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>

            <Card
              title={cellMeasure === 'views' ? 'Views by user and feature' : 'Time by user and feature'}
              subtitle="In the selected range. A grey 0 is a feature this user did not use; the outlined cell is their top feature."
            >
              <div className="mb-3">
                <Toggle value={cellMeasure} onChange={setCellMeasure}
                  options={[{ key: 'views', label: 'Views' }, { key: 'time', label: 'Time' }]} />
              </div>
              {data.per_user.length === 0 ? (
                <p className="text-xs text-gray-500">No users yet. Add sellers on the Users page.</p>
              ) : (
                <UserFeatureTable data={data} measure={cellMeasure} />
              )}
            </Card>
          </div>
        )}
      </div>
      {drill && <UserListDialog title={drill.title} subtitle={drill.subtitle} rows={drill.rows} onClose={closeDrill} />}
    </ProtectedRoute>
  );
}

function UserFeatureTable({ data, measure }: { data: AnalyticsResponse; measure: CellMeasure }) {
  const cell = (u: AnalyticsResponse['per_user'][number], f: string) =>
    measure === 'views' ? (u.feature_views[f] ?? 0) : (u.feature_seconds?.[f] ?? 0);
  const max = Math.max(1, ...data.per_user.flatMap(u => data.features.map(f => cell(u, f))));
  return (
    <div className="overflow-x-auto -mx-6">
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="bg-gray-50 border-y border-gray-200 text-[10px] font-bold uppercase tracking-wider text-gray-600">
            <th className="py-3 px-4 sticky left-0 bg-gray-50 min-w-[12rem]">User</th>
            <th className="py-3 px-3 text-right">Logins</th>
            <th className="py-3 px-3">Last login</th>
            <th className="py-3 px-3 text-right">Features</th>
            <th className="py-3 px-3 text-right">Time</th>
            {data.features.map(f => (
              <th key={f} className="py-3 px-2 text-center min-w-[5.5rem] normal-case tracking-normal">{featureLabel(f)}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {data.per_user.map(u => (
            <tr key={u.user_id} className="hover:bg-slate-50/80">
              <td className="py-2.5 px-4 sticky left-0 bg-white">
                <div className="font-bold text-gray-900">{u.full_name || u.email}</div>
                <div className="text-[10px] text-gray-500">
                  {u.email}{!u.is_active && <span className="ml-1.5 text-gray-400">· deactivated</span>}
                </div>
              </td>
              <td className="py-2.5 px-3 text-right tabular-nums">{u.logins}</td>
              <td className="py-2.5 px-3 text-gray-500 whitespace-nowrap">{u.last_login_at ? formatDateTime(u.last_login_at) : 'Never'}</td>
              <td className="py-2.5 px-3 text-right tabular-nums font-bold">{u.features_used}</td>
              <td className="py-2.5 px-3 text-right tabular-nums whitespace-nowrap">{formatDuration(u.time_seconds ?? 0)}</td>
              {data.features.map(f => {
                const n = cell(u, f);
                const isTop = u.top_feature === f;
                return (
                  <td key={f} className="py-1 px-1 text-center">
                    <span
                      title={`${u.email} · ${featureLabel(f)}: ${u.feature_views[f] ?? 0} view(s), ${formatDuration(u.feature_seconds?.[f] ?? 0)}${isTop ? ' (top feature)' : ''}`}
                      className={`inline-block min-w-[2.5rem] rounded px-1.5 py-1 tabular-nums whitespace-nowrap ${
                        n ? 'text-gray-900 font-semibold' : 'text-gray-300'
                      } ${isTop ? 'ring-1 ring-hp-dark' : ''}`}
                      // One-hue sequential tint: darker = more. The value is
                      // always printed, so the tint is never the only signal.
                      style={n ? { backgroundColor: `rgba(0, 125, 184, ${0.12 + 0.38 * (n / max)})` } : undefined}
                    >
                      {measure === 'views' ? n : formatDuration(n)}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
