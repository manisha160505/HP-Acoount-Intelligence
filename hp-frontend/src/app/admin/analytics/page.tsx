'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { featureLabel } from '@/lib/features';
import { AnalyticsResponse } from '@/types/analytics';
import { BarChart3, Loader2, AlertCircle, RefreshCw, Users, Activity, LogIn, Eye } from 'lucide-react';

// Dates are UTC calendar days, inclusive at both ends - the API's contract.
function utcDay(offsetDays = 0): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const PRESETS = [
  { label: '7 days', days: 7 },
  { label: '30 days', days: 30 },
  { label: '90 days', days: 90 },
];

function formatDateTime(value: string | null): string {
  if (!value) return '—';
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return isNaN(d.getTime()) ? '—' : d.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function StatTile({ label, value, hint, Icon }: { label: string; value: number; hint: string; Icon: React.FC<{ className?: string }> }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-gray-500">
        <Icon className="w-4 h-4 text-hp-navy" />
        <span>{label}</span>
      </div>
      <div className="mt-2 text-3xl font-extrabold text-gray-900 tabular-nums">{value.toLocaleString()}</div>
      <div className="mt-1 text-[11px] text-gray-500">{hint}</div>
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-6">
      <h2 className="text-sm font-bold text-gray-900">{title}</h2>
      {subtitle && <p className="text-[11px] text-gray-500 mt-0.5">{subtitle}</p>}
      <div className="mt-4">{children}</div>
    </div>
  );
}

/** Horizontal bars, one per feature, every feature shown - zero included. */
function FeatureBars({ data }: { data: AnalyticsResponse }) {
  const max = Math.max(1, ...data.per_feature.map(f => f.unique_users));
  return (
    <div className="space-y-2" role="list">
      {data.per_feature.map(f => (
        <div
          key={f.feature_key}
          role="listitem"
          className="group grid grid-cols-[minmax(0,11rem)_1fr_2.5rem] items-center gap-3 rounded-md px-1 py-0.5 hover:bg-gray-50"
          title={`${featureLabel(f.feature_key)}: ${f.unique_users} user(s), ${f.total_views} view(s), last used ${formatDateTime(f.last_used_at)}`}
        >
          <span className="text-xs font-semibold text-gray-700 truncate">{featureLabel(f.feature_key)}</span>
          <div className="h-3.5 bg-gray-100 rounded-sm">
            {f.unique_users > 0 && (
              <div
                className="h-full bg-hp-blue rounded-r group-hover:bg-hp-dark transition-colors"
                style={{ width: `${(f.unique_users / max) * 100}%` }}
              />
            )}
          </div>
          <span className={`text-xs tabular-nums text-right ${f.unique_users ? 'font-bold text-gray-900' : 'text-gray-400'}`}>
            {f.unique_users}
          </span>
        </div>
      ))}
    </div>
  );
}

/** One column per day. Single series, so no legend; hover gives the number. */
function DailyColumns({ data }: { data: AnalyticsResponse }) {
  const days = data.daily_active_users;
  const max = Math.max(1, ...days.map(d => d.active_users));
  const peak = days.reduce((a, d) => (d.active_users > a.active_users ? d : a), days[0]);
  return (
    <div>
      <div className="flex items-end gap-[2px] h-32 border-b border-gray-200">
        {days.map(d => (
          <div
            key={d.date}
            className="group relative flex-1 h-full flex items-end"
            title={`${d.date}: ${d.active_users} active user(s)`}
          >
            <div
              className="w-full bg-hp-blue group-hover:bg-hp-dark rounded-t transition-colors"
              style={{ height: d.active_users ? `${Math.max(3, (d.active_users / max) * 100)}%` : '0' }}
            />
          </div>
        ))}
      </div>
      <div className="flex justify-between mt-1.5 text-[10px] text-gray-500 tabular-nums">
        <span>{days[0]?.date}</span>
        {peak && peak.active_users > 0 && <span>Peak {peak.active_users} on {peak.date}</span>}
        <span>{days[days.length - 1]?.date}</span>
      </div>
    </div>
  );
}

export default function AdminAnalyticsPage() {
  const [from, setFrom] = useState(utcDay(-29));
  const [to, setTo] = useState(utcDay(0));
  const [data, setData] = useState<AnalyticsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
  const activePreset = to === utcDay(0) ? PRESETS.find(p => from === utcDay(-(p.days - 1)))?.days : undefined;
  const hasActivity = !!data && (data.totals.feature_views > 0 || data.totals.logins > 0);

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
            {PRESETS.map(p => (
              <button
                key={p.days}
                type="button"
                onClick={() => { setFrom(utcDay(-(p.days - 1))); setTo(utcDay(0)); }}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                  activePreset === p.days ? 'bg-hp-navy text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {p.label}
              </button>
            ))}
            <span className="w-px h-6 bg-gray-200 mx-1" />
            <label className="text-[11px] font-bold text-gray-500 uppercase">From</label>
            <input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded-lg text-xs bg-gray-50 focus:outline-none focus:ring-2 focus:ring-hp-navy" />
            <label className="text-[11px] font-bold text-gray-500 uppercase">To</label>
            <input type="date" value={to} min={from} onChange={e => setTo(e.target.value)}
              className="px-2 py-1.5 border border-gray-300 rounded-lg text-xs bg-gray-50 focus:outline-none focus:ring-2 focus:ring-hp-navy" />
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
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatTile label="Total users" value={data.totals.total_users} hint="Non-admin users, active or not" Icon={Users} />
              <StatTile label="Active, last 7 days" value={data.totals.active_users_7d} hint="Signed in or opened a feature" Icon={Activity} />
              <StatTile label="Logins" value={data.totals.logins} hint={`${data.date_from} to ${data.date_to}`} Icon={LogIn} />
              <StatTile label="Feature views" value={data.totals.feature_views} hint={`${data.date_from} to ${data.date_to}`} Icon={Eye} />
            </div>

            {!hasActivity && (
              <div className="bg-white rounded-2xl border border-dashed border-gray-300 p-6 text-center text-xs text-gray-500">
                No seller activity between {data.date_from} and {data.date_to}. Every feature is listed below at zero.
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <Card title="Unique users per feature" subtitle="Every feature is listed; grey zero means nobody opened it in this range.">
                <FeatureBars data={data} />
              </Card>
              <Card title="Daily active users" subtitle="Distinct sellers who signed in or opened a feature, per UTC day.">
                <DailyColumns data={data} />
                {data.top_accounts.length > 0 && (
                  <div className="mt-6">
                    <h3 className="text-[11px] font-bold uppercase tracking-wider text-gray-500 mb-2">Most viewed accounts</h3>
                    <table className="w-full text-xs">
                      <tbody className="divide-y divide-gray-100">
                        {data.top_accounts.map(a => (
                          <tr key={a.account_id}>
                            <td className="py-1.5 text-gray-800 font-semibold truncate">{a.account_name || <span className="text-gray-400">{a.account_id}</span>}</td>
                            <td className="py-1.5 text-right tabular-nums text-gray-900 font-bold">{a.views} views</td>
                            <td className="py-1.5 text-right tabular-nums text-gray-500 w-20">{a.unique_users} user{a.unique_users === 1 ? '' : 's'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>

            <Card title="Views by user and feature" subtitle="Feature views in the selected range. A grey 0 is a feature this user did not open.">
              {data.per_user.length === 0 ? (
                <p className="text-xs text-gray-500">No users yet. Add sellers on the Users page.</p>
              ) : (
                <UserFeatureTable data={data} />
              )}
            </Card>
          </div>
        )}
      </div>
    </ProtectedRoute>
  );
}

function UserFeatureTable({ data }: { data: AnalyticsResponse }) {
  const max = Math.max(1, ...data.per_user.flatMap(u => Object.values(u.feature_views)));
  return (
    <div className="overflow-x-auto -mx-6">
      <table className="w-full text-left border-collapse text-xs">
        <thead>
          <tr className="bg-gray-50 border-y border-gray-200 text-[10px] font-bold uppercase tracking-wider text-gray-600">
            <th className="py-3 px-4 sticky left-0 bg-gray-50 min-w-[12rem]">User</th>
            <th className="py-3 px-3 text-right">Logins</th>
            <th className="py-3 px-3">Last login</th>
            <th className="py-3 px-3 text-right">Features</th>
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
              {data.features.map(f => {
                const n = u.feature_views[f] ?? 0;
                const isTop = u.top_feature === f;
                return (
                  <td key={f} className="py-1 px-1 text-center">
                    <span
                      title={`${u.email} · ${featureLabel(f)}: ${n} view(s)${isTop ? ' (top feature)' : ''}`}
                      className={`inline-block min-w-[2.5rem] rounded px-1.5 py-1 tabular-nums ${
                        n ? 'text-gray-900 font-semibold' : 'text-gray-300'
                      } ${isTop ? 'ring-1 ring-hp-dark' : ''}`}
                      // One-hue sequential tint: darker = more views. The number
                      // is always printed, so the tint is never the only signal.
                      style={n ? { backgroundColor: `rgba(0, 125, 184, ${0.12 + 0.38 * (n / max)})` } : undefined}
                    >
                      {n}
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
