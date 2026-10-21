'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { History, Loader2 } from 'lucide-react';
import api from '@/services/api';
import { TryAgain } from '@/components/common/TryAgain';
import type { AuditEntry, ManagedUser } from '@/types/analytics';

const ACTION_LABEL: Record<string, string> = {
  'user.created': 'Created user',
  'user.activated': 'Activated',
  'user.deactivated': 'Deactivated',
  'user.renamed': 'Renamed',
  'user.role_changed': 'Changed role',
  'user.accounts_changed': 'Changed accounts',
  'user.password_reset': 'Reset password',
  'user.password_changed': 'Changed own password',
  'user.password_recovered': 'Set password with recovery code',
  'sessions.revoked_all': 'Signed out everyone',
};

function list(v: unknown): string[] {
  return Array.isArray(v) ? v.map(String) : [];
}

/** One line saying what changed, from the entry's details. */
function describe(e: AuditEntry): string {
  const d = e.details || {};
  switch (e.action) {
    case 'user.created': {
      const accts = list(d.accounts);
      return `Role ${String(d.role || 'user')}${accts.length ? `; accounts: ${accts.join(', ')}` : ''}`;
    }
    case 'user.role_changed':
      return `${String(d.from)} → ${String(d.to)}`;
    case 'user.accounts_changed': {
      const parts = [];
      if (list(d.added).length) parts.push(`added ${list(d.added).join(', ')}`);
      if (list(d.removed).length) parts.push(`removed ${list(d.removed).join(', ')}`);
      return parts.join('; ');
    }
    case 'user.password_changed':
      return d.first_sign_in ? 'At first sign-in' : '';
    case 'sessions.revoked_all':
      return `${String(d.sessions ?? 0)} session(s) ended`;
    default:
      return '';
  }
}

export function formatDateTime(value: string | null): string {
  if (!value) return '';
  // Timestamps are stored in UTC; a naive one from the API is UTC too.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  return isNaN(d.getTime()) ? '' : d.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

/** Every change to users and their access, newest first. */
export function AuditLog({ users }: { users: ManagedUser[] }) {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [userId, setUserId] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadFailed(false);
    try {
      const res = await api.get<AuditEntry[]>('/admin/audit', {
        params: { limit: 500, ...(userId ? { user_id: userId } : {}) },
      });
      setEntries(res.data);
    } catch {
      // No error text on screen (client rule): a neutral Try again instead.
      setLoadFailed(true);
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 px-5 py-3.5 border-b border-gray-200 bg-gray-50">
        <h2 className="text-sm font-bold text-gray-900 inline-flex items-center gap-2">
          <History className="w-4 h-4 text-hp-navy" /> Activity log
        </h2>
        <select
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          aria-label="Show changes for"
          className="text-xs border border-gray-300 rounded-lg px-2.5 py-1.5 bg-white focus:outline-none focus:ring-2 focus:ring-hp-navy"
        >
          <option value="">All users</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
        </select>
      </div>
      {isLoading ? (
        <div className="p-10 flex justify-center"><Loader2 className="w-6 h-6 text-hp-navy animate-spin" /></div>
      ) : loadFailed ? (
        <TryAgain onRetry={load} className="p-6" />
      ) : entries.length === 0 ? (
        <p className="p-10 text-center text-xs text-gray-500">No changes recorded yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-600">
                <th className="py-3 px-5">When</th>
                <th className="py-3 px-5">Who</th>
                <th className="py-3 px-5">What</th>
                <th className="py-3 px-5">User</th>
                <th className="py-3 px-5">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {entries.map((e) => (
                <tr key={e.id} className="align-top">
                  <td className="py-3 px-5 text-gray-500 whitespace-nowrap">{formatDateTime(e.ts)}</td>
                  <td className="py-3 px-5 text-gray-700">{e.actor_email}</td>
                  <td className="py-3 px-5 font-bold text-gray-900 whitespace-nowrap">{ACTION_LABEL[e.action] || e.action}</td>
                  <td className="py-3 px-5 text-gray-700">{e.target_email}</td>
                  <td className="py-3 px-5 text-gray-600">{describe(e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
