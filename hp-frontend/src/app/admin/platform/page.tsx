'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { PageHero } from '@/components/common/motion';
import api from '@/services/api';
import { CompanyAccount, AccountStatus } from '@/types/account';
import { 
  Building2, 
  Plus, 
  Search, 
  Eye, 
  EyeOff, 
  Settings2, 
  Loader2, 
  AlertCircle, 
  CheckCircle2, 
  X,
  RefreshCw
} from 'lucide-react';

// Per-account pipeline counts from GET /regeneration/accounts-summary. Worked
// out from fingerprints on the server - no model calls - so Refresh is cheap.
interface PipelineSummaryRow {
  account_id: string;
  counts: Record<string, number>;
  total: number;
  needs_run: number;
  running?: { label: string; progress?: { done: number; total: number } | null } | null;
  // Datasets some section reads that this account has no file for; `blocks`
  // counts the sections left with no data at all.
  data_gaps?: { dataset: string; label: string; blocks: number }[];
}

// Per-account running/queued jobs from GET /regeneration/live: one query on the
// job queue, so the table polls it every few seconds. The summary above needs
// fingerprints and takes longer; it is re-fetched when this changes.
interface LiveRow {
  running: number;
  queued: number;
  running_job: { node_id: string; label: string; progress?: { done: number; total: number } | null } | null;
}

const LIVE_POLL_MS = 4000;
const SUMMARY_POLL_MS = 60000;

function PipelineCell({ row, live, liveLoaded }: { row?: PipelineSummaryRow; live?: LiveRow; liveLoaded: boolean }) {
  if (!row && !live) return <span className="text-gray-400">—</span>;
  // Running and queued come from the live poll once it has answered; the
  // summary may be a minute old.
  const c = { ...(row?.counts || {}) };
  const running = liveLoaded ? (live?.running_job ?? null) : (row?.running ?? null);
  if (liveLoaded) {
    c.RUNNING = live?.running || 0;
    c.QUEUED = live?.queued || 0;
  }
  const chips: [string, number, string][] = [
    ['running', c.RUNNING || 0, 'bg-blue-100 text-blue-800'],
    ['queued', c.QUEUED || 0, 'bg-indigo-100 text-indigo-800'],
    ['files missing', c.FILES_MISSING || 0, 'bg-rose-200 text-rose-900'],
    ['no data', c.NO_DATA || 0, 'bg-stone-200 text-stone-800'],
    ['failed', c.FAILED || 0, 'bg-red-100 text-red-800'],
    ['stale', (c.STALE || 0) + (c.DEGRADED || 0), 'bg-amber-100 text-amber-800'],
    ['never run', c.NEVER_RUN || 0, 'bg-slate-200 text-slate-700'],
  ];
  const shown = chips.filter(([, n]) => n > 0);
  const gaps = row?.data_gaps || [];
  if (!shown.length && !row) return <span className="text-gray-400">—</span>;
  const p = running?.progress;
  return (
    <div className="flex flex-wrap gap-1">
      {!shown.length && (
        <span className="inline-flex px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">all current</span>
      )}
      {shown.map(([label, n, tone]) => (
        <span key={label} className={`inline-flex px-2 py-0.5 rounded-full text-[11px] font-bold ${tone}`}
          title={label === 'no data' ? 'Sections with no uploaded file for anything they are built from' : undefined}>
          {n} {label}
        </span>
      ))}
      {gaps.length > 0 && (
        <span className="text-[11px] text-stone-700 w-full"
          title={gaps.map(g => g.label + (g.blocks ? ` (${g.blocks} section(s) have no data at all)` : '')).join('\n')}>
          Not provided: {gaps.slice(0, 3).map(g => g.label).join(', ')}{gaps.length > 3 ? ` +${gaps.length - 3} more` : ''}
        </span>
      )}
      {running && (
        <span className="text-[11px] text-blue-800 w-full">
          {running.label}{p ? ` ${Math.round((p.done / Math.max(1, p.total)) * 100)}%` : ''}
        </span>
      )}
    </div>
  );
}

export default function ManagePlatformPage() {
  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [pipeline, setPipeline] = useState<Record<string, PipelineSummaryRow>>({});
  const [live, setLive] = useState<Record<string, LiveRow>>({});
  const [liveLoaded, setLiveLoaded] = useState(false);
  const [pipelineLoading, setPipelineLoading] = useState(false);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [pipelineUpdatedAt, setPipelineUpdatedAt] = useState<Date | null>(null);
  const summaryInFlight = useRef(false);
  const liveSignature = useRef<string | null>(null);
  const [queuePaused, setQueuePaused] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newAccountName, setNewAccountName] = useState('');
  const [modalError, setModalError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Toggle Loading State per account ID
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const router = useRouter();

  const fetchPipeline = useCallback(async () => {
    // One summary at a time: polls and clicks while one is in flight would
    // only queue more of the same slow request.
    if (summaryInFlight.current) return;
    summaryInFlight.current = true;
    setPipelineLoading(true);
    try {
      const res = await api.get<{ accounts: PipelineSummaryRow[]; queue: { paused: boolean; reason?: string } }>(
        '/regeneration/accounts-summary');
      setPipeline(Object.fromEntries(res.data.accounts.map(r => [r.account_id, r])));
      setQueuePaused(res.data.queue?.paused ? (res.data.queue.reason || 'paused') : null);
      setPipelineError(null);
      setPipelineUpdatedAt(new Date());
    } catch (err: any) {
      // The table still works without the column, but say so.
      setPipelineError(err.response?.data?.detail || err.message || 'Could not load pipeline status.');
    } finally {
      summaryInFlight.current = false;
      setPipelineLoading(false);
    }
  }, []);

  const fetchLive = useCallback(async () => {
    try {
      const res = await api.get<{ accounts: Record<string, LiveRow>; queue: { paused: boolean; reason?: string } }>(
        '/regeneration/live');
      const rows = res.data.accounts || {};
      setLive(rows);
      setLiveLoaded(true);
      setQueuePaused(res.data.queue?.paused ? (res.data.queue.reason || 'paused') : null);
      // A job started or finished: the stale / failed / current counts moved
      // too, and only the summary knows them.
      const signature = Object.entries(rows)
        .map(([id, r]) => `${id}:${r.running}:${r.queued}:${r.running_job?.node_id ?? ''}`)
        .sort().join('|');
      if (liveSignature.current !== null && liveSignature.current !== signature) fetchPipeline();
      liveSignature.current = signature;
    } catch {
      // The next poll tries again; the summary still shows its own counts.
    }
  }, [fetchPipeline]);

  const refreshPipeline = useCallback(() => {
    fetchLive();
    fetchPipeline();
  }, [fetchLive, fetchPipeline]);

  const fetchAccounts = useCallback(async (search = '') => {
    setIsLoading(true);
    setError(null);
    try {
      const url = search.trim() ? `/accounts?search=${encodeURIComponent(search.trim())}` : '/accounts';
      const response = await api.get<CompanyAccount[]>(url);
      setAccounts(response.data);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to fetch account list.';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAccounts(searchQuery);
  }, [searchQuery, fetchAccounts]);

  // Live while the tab is visible: running/queued every few seconds, the full
  // summary every minute (and whenever the live poll sees a change). Coming
  // back to the tab refreshes both at once.
  useEffect(() => {
    refreshPipeline();
    const liveTimer = setInterval(() => {
      if (document.visibilityState === 'visible') fetchLive();
    }, LIVE_POLL_MS);
    const summaryTimer = setInterval(() => {
      if (document.visibilityState === 'visible') fetchPipeline();
    }, SUMMARY_POLL_MS);
    const onVisible = () => {
      if (document.visibilityState === 'visible') refreshPipeline();
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      clearInterval(liveTimer);
      clearInterval(summaryTimer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [refreshPipeline, fetchLive, fetchPipeline]);

  const handleCreateAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalError(null);

    const trimmed = newAccountName.trim();
    if (!trimmed) {
      setModalError('Account name is required.');
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await api.post<CompanyAccount>('/accounts', { name: trimmed });
      setSuccessMsg(`Account "${response.data.name}" created successfully.`);
      setNewAccountName('');
      setIsModalOpen(false);
      fetchAccounts(searchQuery);
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to create account.';
      setModalError(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleStatusToggle = async (account: CompanyAccount) => {
    const newStatus: AccountStatus = account.status === 'active' ? 'hidden' : 'active';
    setTogglingId(account.id);
    try {
      await api.patch(`/accounts/${account.id}/status`, { status: newStatus });
      setSuccessMsg(`Account "${account.name}" is now ${newStatus}.`);
      setAccounts(prev =>
        prev.map(a => (a.id === account.id ? { ...a, status: newStatus } : a))
      );
      setTimeout(() => setSuccessMsg(null), 3000);
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to update account status.';
      setError(msg);
    } finally {
      setTogglingId(null);
    }
  };

  const formatDate = (isoString: string) => {
    if (!isoString) return 'N/A';
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString('en-US', {
        month: 'short',
        day: '2-digit',
        year: 'numeric'
      });
    } catch {
      return isoString;
    }
  };

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="as-page">
      <PageHero
        title="Manage Platform"
        subtitle="Enterprise account portfolio management & entity status control"
        actions={
          <button
            type="button"
            onClick={() => {
              setIsModalOpen(true);
              setModalError(null);
              setNewAccountName('');
            }}
            className="inline-flex items-center justify-center px-4 py-2.5 border border-transparent rounded-lg shadow-md text-sm font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-hp-navy transition duration-150"
          >
            <Plus className="w-4 h-4 mr-2 stroke-[3]" />
            <span>Create New Account</span>
          </button>
        }
      />
      <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 -mt-12 sm:-mt-14 pb-12">

        {/* Global Feedback Notifications */}
        {successMsg && (
          <div className="mb-6 bg-emerald-50 as-fade border border-emerald-200 p-4 rounded-xl flex items-center justify-between text-emerald-800 text-xs font-semibold shadow-sm">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="w-5 h-5 text-emerald-600 flex-shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg(null)}>
              <X className="w-4 h-4 text-emerald-600" />
            </button>
          </div>
        )}

        {error && (
          <div className="mb-6 bg-red-50 as-fade border border-red-200 p-4 rounded-xl flex items-center justify-between text-red-800 text-xs font-semibold shadow-sm">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
              <span>{error}</span>
            </div>
            <button onClick={() => setError(null)}>
              <X className="w-4 h-4 text-red-600" />
            </button>
          </div>
        )}

        {/* Search Bar */}
        <div className="as-glass as-rise relative z-10 p-4 rounded-2xl mb-6 flex items-center gap-3" style={{ ['--as-delay' as string]: '120ms' }}>
          <div className="relative flex-1">
            <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none">
              <Search className="h-4 w-4 text-gray-400" />
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search company accounts by name (e.g. Astra, Sea Limited)..."
              className="block w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent text-xs bg-gray-50 focus:bg-white transition"
            />
          </div>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="text-xs text-gray-500 hover:text-gray-800 font-medium px-2 py-1 rounded bg-gray-100"
            >
              Clear
            </button>
          )}
          <button
            onClick={() => fetchAccounts(searchQuery)}
            className="p-2 text-gray-500 hover:text-hp-navy rounded-lg hover:bg-gray-100 transition"
            title="Refresh Account List"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Account Table */}
        <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
          {isLoading ? (
            <div className="p-12 flex flex-col items-center justify-center space-y-3">
              <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500 font-medium">Loading target enterprise accounts...</p>
            </div>
          ) : accounts.length === 0 ? (
            <div className="p-12 text-center">
              <Building2 className="w-12 h-12 text-gray-300 mx-auto mb-3" />
              <h3 className="text-sm font-bold text-gray-800">No accounts found</h3>
              <p className="text-xs text-gray-500 mt-1">
                {searchQuery
                  ? `No account matches the query "${searchQuery}".`
                  : 'Get started by creating your first enterprise company account.'}
              </p>
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="mt-4 text-xs font-semibold text-hp-navy hover:underline"
                >
                  Clear search filter
                </button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-[11px] font-bold uppercase tracking-wider text-gray-600">
                    <th className="py-3.5 px-6">Account Name</th>
                    <th className="py-3.5 px-6">Status</th>
                    <th className="py-3.5 px-6">
                      <span className="inline-flex items-center gap-1.5">
                        Pipeline
                        <button type="button" onClick={refreshPipeline} disabled={pipelineLoading}
                          title={pipelineUpdatedAt ? `Refresh pipeline status (updated ${pipelineUpdatedAt.toLocaleTimeString()})` : 'Refresh pipeline status'}
                          className="text-gray-500 hover:text-hp-navy disabled:cursor-wait">
                          <RefreshCw className={`w-3 h-3 ${pipelineLoading ? 'animate-spin' : ''}`} />
                        </button>
                        {liveLoaded && <span className="normal-case font-semibold text-emerald-700" title={`Running and queued update every ${LIVE_POLL_MS / 1000}s`}>· live</span>}
                        {queuePaused && <span className="normal-case text-amber-700" title={queuePaused}>· queue paused</span>}
                        {pipelineError && <span className="normal-case text-red-700" title={pipelineError}>· status failed to load</span>}
                      </span>
                    </th>
                    <th className="py-3.5 px-6">Last Updated</th>
                    <th className="py-3.5 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 text-xs font-medium">
                  {accounts.map((account) => (
                    <tr key={account.id} className="hover:bg-slate-50/80 transition duration-150">
                      <td className="py-4 px-6 font-semibold text-gray-900">
                        <div className="flex items-center space-x-2.5">
                          <div className="w-8 h-8 rounded-lg bg-hp-navy/10 text-hp-navy flex items-center justify-center font-bold text-xs uppercase">
                            {account.name.substring(0, 2)}
                          </div>
                          <span className="text-sm text-gray-900 font-bold">{account.name}</span>
                        </div>
                      </td>

                      <td className="py-4 px-6">
                        {account.status === 'active' ? (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-1.5"></span>
                            Active
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mr-1.5"></span>
                            Hidden
                          </span>
                        )}
                      </td>

                      <td className="py-4 px-6">
                        <PipelineCell row={pipeline[account.id]} live={live[account.id]} liveLoaded={liveLoaded} />
                      </td>

                      <td className="py-4 px-6 text-gray-500">
                        {formatDate(account.updated_at)}
                      </td>

                      <td className="py-4 px-6 text-right space-x-2">
                        <button
                          type="button"
                          onClick={() => router.push(`/admin/accounts/${account.id}`)}
                          className="inline-flex items-center space-x-1 px-3 py-1.5 bg-gray-100 hover:bg-hp-navy hover:text-white text-gray-700 rounded-lg transition text-xs font-bold"
                        >
                          <Settings2 className="w-3.5 h-3.5" />
                          <span>Manage</span>
                        </button>

                        <button
                          type="button"
                          disabled={togglingId === account.id}
                          onClick={() => handleStatusToggle(account)}
                          className={`inline-flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-bold transition ${
                            account.status === 'active'
                              ? 'bg-amber-50 text-amber-700 hover:bg-amber-600 hover:text-white border border-amber-200'
                              : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-600 hover:text-white border border-emerald-200'
                          }`}
                        >
                          {togglingId === account.id ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : account.status === 'active' ? (
                            <>
                              <EyeOff className="w-3.5 h-3.5" />
                              <span>Hide</span>
                            </>
                          ) : (
                            <>
                              <Eye className="w-3.5 h-3.5" />
                              <span>Show</span>
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>

      {/* Create Account Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border border-gray-200">
            
            <div className="flex justify-between items-center px-6 py-4 bg-gray-50 border-b border-gray-200">
              <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                <Building2 className="w-5 h-5 text-hp-navy" />
                <span>Create New Account</span>
              </h3>
              <button
                type="button"
                onClick={() => setIsModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 rounded-lg p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateAccount} className="p-6 space-y-4">
              {modalError && (
                <div className="bg-red-50 as-fade border border-red-200 p-3 rounded-xl flex items-center space-x-2 text-xs font-medium text-red-700">
                  <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0" />
                  <span>{modalError}</span>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider mb-1">
                  Account Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  autoFocus
                  value={newAccountName}
                  onChange={(e) => setNewAccountName(e.target.value)}
                  placeholder="e.g. Astra, Sea Limited, HP Inc"
                  className="block w-full px-3.5 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-hp-navy text-sm font-medium bg-gray-50 focus:bg-white transition"
                />
                <p className="text-[11px] text-gray-500 mt-1">
                  Unique company/entity name being analyzed. Default status will be Active.
                </p>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-gray-100">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-gray-600 hover:text-gray-800 bg-gray-100 hover:bg-gray-200 rounded-lg transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="inline-flex items-center justify-center px-4 py-2 border border-transparent rounded-lg shadow-sm text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition disabled:opacity-50"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin mr-1.5" />
                      <span>Creating...</span>
                    </>
                  ) : (
                    <span>Create Account</span>
                  )}
                </button>
              </div>
            </form>

          </div>
        </div>
      )}
      </div>
    </ProtectedRoute>
  );
}
