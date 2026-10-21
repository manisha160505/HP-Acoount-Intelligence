'use client';

import React, { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { Loader2, Users } from 'lucide-react';
import api from '@/services/api';
import type { AccountUser } from '@/types/analytics';
import { TryAgain } from '@/components/common/TryAgain';

/** The sellers assigned to one account. Admins see every account and are not listed. */
export function AccountSellersPanel({ accountId }: { accountId: string }) {
  const [rows, setRows] = useState<AccountUser[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => { setFailed(false); setRows(null); setAttempt((n) => n + 1); }, []);

  useEffect(() => {
    let live = true;
    api.get<AccountUser[]>(`/admin/accounts/${accountId}/users`)
      .then((r) => { if (live) setRows(r.data); })
      .catch(() => { if (live) setFailed(true); });
    return () => { live = false; };
  }, [accountId, attempt]);

  return (
    <div data-tour="admin-account-sellers" className="mt-10 pt-6 border-t border-gray-200">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-base font-bold text-gray-900 flex items-center gap-2">
          <Users className="w-4 h-4 text-hp-navy" /> Sellers with access
        </h2>
        <Link href="/admin/users" className="text-xs font-bold text-hp-navy hover:underline">Manage on Users</Link>
      </div>
      <p className="text-xs text-gray-500 mb-3">Admins see every account and are not listed.</p>
      {failed ? (
        <TryAgain onRetry={retry} size="sm" align="start" />
      ) : rows === null ? (
        <Loader2 className="w-5 h-5 text-hp-navy animate-spin" />
      ) : rows.length === 0 ? (
        <p className="text-xs text-amber-700 font-semibold">No seller is assigned to this account yet.</p>
      ) : (
        <ul className="divide-y divide-gray-100 border border-gray-200 rounded-xl">
          {rows.map((u) => (
            <li key={u.id} className="flex items-center justify-between px-3.5 py-2.5 text-xs">
              <span className="font-medium text-gray-900 break-all">{u.email}</span>
              {!u.is_active && <span className="text-[11px] font-bold text-gray-500">Deactivated</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
