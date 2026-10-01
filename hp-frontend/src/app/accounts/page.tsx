'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { ParallaxBand, SlidingSegments } from '@/components/common/motion';
import api from '@/services/api';
import { CompanyAccount } from '@/types/account';
import {
  URGENCY_FILTERS,
  UrgencyFilter,
  dashboardHref,
  filterAccounts,
  pageNumbers,
  paginate,
} from '@/lib/accountSelection';
import { AlertCircle, ArrowRight, Building2, ChevronLeft, ChevronRight, Loader2, RefreshCw, Search, X } from 'lucide-react';

/**
 * Account Selection - the step between sign-in and the dashboard.
 *
 * Reads the same /accounts/user-list the dashboard's account dropdown reads,
 * and enters an account through the same route the dropdown keeps in sync
 * (/dashboard?account=<id>), so there is one way an account becomes active.
 * Search, filter and paging run over the loaded list, in that order.
 */
export default function AccountSelectionPage() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [urgency, setUrgency] = useState<UrgencyFilter>('all');
  const [page, setPage] = useState(1);
  const [openingId, setOpeningId] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await api.get<CompanyAccount[]>('/accounts/user-list');
      setAccounts(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load accessible account list.');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // A new search or filter starts from the first page of its own results.
  useEffect(() => {
    setPage(1);
  }, [search, urgency]);

  // "/" jumps to search, the convention in most list tools.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (e.key !== '/' || e.metaKey || e.ctrlKey || e.altKey) return;
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
      e.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  // The first arrival gets the full stagger; later page and filter changes
  // replay a quicker one. Switched after the arrival has finished so the
  // running animation is not retimed mid-flight.
  const [hasEntered, setHasEntered] = useState(false);
  useEffect(() => {
    if (isLoading || hasEntered) return;
    const t = window.setTimeout(() => setHasEntered(true), 800);
    return () => window.clearTimeout(t);
  }, [isLoading, hasEntered]);

  const filtered = useMemo(() => filterAccounts(accounts, search, urgency), [accounts, search, urgency]);
  const view = paginate(filtered, page);
  const isFiltering = search.trim() !== '' || urgency !== 'all';

  const open = (acc: CompanyAccount) => {
    if (openingId) return;
    setOpeningId(acc.id);
    router.push(dashboardHref(acc.id));
  };

  const goToPage = (p: number) => {
    setPage(p);
    // Keep the list in view when paging from the bottom controls.
    document.getElementById('as-list')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  };

  return (
    <ProtectedRoute allowedRoles={['user', 'admin']}>
      <div className="as-page min-h-[calc(100vh-4rem)] bg-[#F4F6F8]">
        {/* Header band: continues the navbar's ink, with parallax depth. */}
        <ParallaxBand>
          <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 pt-10 pb-20 sm:pt-14 sm:pb-24">
            <h1 className="as-rise text-2xl sm:text-3xl font-extrabold text-white tracking-tight [text-wrap:balance]">
              Select an account
            </h1>
            <p className="as-rise mt-2 text-sm text-slate-300/90 max-w-xl" style={{ ['--as-delay' as string]: '70ms' }}>
              Choose a target account to open its intelligence dashboard.
              {!isLoading && !error && accounts.length > 0 && (
                <span className="as-fade text-slate-400"> {accounts.length} available.</span>
              )}
            </p>
          </div>
        </ParallaxBand>

        <div className="relative max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 -mt-12 sm:-mt-14 pb-16">
          {/* Controls, floating over the band's edge */}
          <div
            className="as-rise relative z-10 bg-white rounded-2xl border border-slate-200/80 p-3 sm:p-4 shadow-[0_12px_32px_-12px_rgba(11,19,43,0.28),0_2px_6px_-2px_rgba(11,19,43,0.08)]"
            style={{ ['--as-delay' as string]: '120ms' }}
          >
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                ref={searchRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Escape') setSearch(''); }}
                placeholder="Search by company name"
                aria-label="Search accounts"
                className="w-full pl-10 pr-16 py-3 bg-slate-50 border border-slate-200 rounded-xl text-sm text-slate-800 placeholder-slate-500 transition-[background-color,box-shadow,border-color] duration-200 focus:bg-white focus:border-[#0096D6]/50 focus:outline-none focus:ring-4 focus:ring-[#0096D6]/15"
              />
              <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
                {search ? (
                  <button
                    type="button"
                    onClick={() => { setSearch(''); searchRef.current?.focus(); }}
                    aria-label="Clear search"
                    className="as-fade p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 bg-white border border-slate-200 rounded-md shadow-[0_1px_0_rgba(15,23,42,0.06)]">
                    /
                  </kbd>
                )}
              </div>
            </div>

            <div className="mt-3 flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3">
              <span id="as-urgency-label" className="text-xs font-bold text-slate-600 whitespace-nowrap">
                Urgency Score
              </span>
              <div className="as-scroll-x overflow-x-auto -mx-1 px-1 min-w-0">
                <SlidingSegments value={urgency} onChange={setUrgency} labelledBy="as-urgency-label" options={URGENCY_FILTERS} />
              </div>
            </div>
          </div>

          {/* List */}
          <div id="as-list" className="mt-5 bg-white rounded-2xl border border-slate-200/80 shadow-[0_1px_2px_rgba(11,19,43,0.05)] overflow-hidden scroll-mt-6">
            <div className="flex items-center justify-between px-4 sm:px-5 py-2.5 border-b border-slate-100 text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              <span>Account</span>
              <span className="pr-7">Urgency Score</span>
            </div>

            {isLoading ? (
              <SkeletonRows />
            ) : error ? (
              <div className="as-fade p-10 flex flex-col items-center text-center">
                <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center mb-3">
                  <AlertCircle className="w-5 h-5 text-red-600" />
                </div>
                <p className="text-sm font-semibold text-slate-800">{error}</p>
                <button
                  type="button"
                  onClick={load}
                  className="mt-4 inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-bold text-white bg-[#0B132B] hover:bg-[#1C2541] transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Try again
                </button>
              </div>
            ) : view.total === 0 ? (
              <div className="as-fade px-6 py-14 text-center">
                <div className="w-12 h-12 rounded-2xl bg-slate-100 flex items-center justify-center mx-auto mb-3">
                  <Building2 className="w-6 h-6 text-slate-400" />
                </div>
                <p className="text-sm font-bold text-slate-800">
                  {isFiltering ? 'No accounts found matching your search and filter.' : 'No accounts are available yet.'}
                </p>
                {isFiltering && (
                  <button
                    type="button"
                    onClick={() => { setSearch(''); setUrgency('all'); }}
                    className="mt-3 text-xs font-bold text-[#007DB8] hover:text-[#0B132B] underline underline-offset-4 decoration-[#0096D6]/40 transition-colors"
                  >
                    Clear search and filter
                  </button>
                )}
              </div>
            ) : (
              <ul
                key={`${view.page}|${urgency}`}
                className={`divide-y divide-slate-100 ${hasEntered ? 'as-list-swap' : ''}`}
              >
                {view.items.map((acc, i) => (
                  <AccountRow
                    key={acc.id}
                    account={acc}
                    index={Math.min(i, 8)}
                    opening={openingId === acc.id}
                    dimmed={openingId !== null && openingId !== acc.id}
                    onOpen={() => open(acc)}
                  />
                ))}
              </ul>
            )}
          </div>

          {/* Pagination */}
          {!isLoading && !error && view.total > 0 && (
            <div className="as-fade flex flex-col sm:flex-row items-center justify-between gap-3 mt-4 text-xs text-slate-600">
              <span className="tabular-nums" aria-live="polite">
                Showing <b className="text-slate-800">{view.start}–{view.end}</b> of <b className="text-slate-800">{view.total}</b>
              </span>
              <nav className="flex items-center gap-1" aria-label="Pagination">
                <PageButton disabled={view.page <= 1} onClick={() => goToPage(view.page - 1)}>
                  <ChevronLeft className="w-3.5 h-3.5" /> <span className="hidden sm:inline">Previous</span>
                </PageButton>
                {pageNumbers(view.page, view.totalPages).map((p, i) =>
                  p === null ? (
                    <span key={`gap-${i}`} className="px-1 text-slate-400">…</span>
                  ) : (
                    <PageButton key={p} current={p === view.page} onClick={() => goToPage(p)}>
                      {p}
                    </PageButton>
                  ),
                )}
                <PageButton disabled={view.page >= view.totalPages} onClick={() => goToPage(view.page + 1)}>
                  <span className="hidden sm:inline">Next</span> <ChevronRight className="w-3.5 h-3.5" />
                </PageButton>
              </nav>
            </div>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}

// ---------------------------------------------------------------- pieces

function AccountRow({ account, index, opening, dimmed, onOpen }: {
  account: CompanyAccount;
  index: number;
  opening: boolean;
  dimmed: boolean;
  onOpen: () => void;
}) {
  const score = typeof account.urgency_score === 'number' ? account.urgency_score : null;
  const max = account.urgency_max_score ?? 100;
  return (
    <li className="as-row" style={{ ['--as-i' as string]: index }}>
      <button
        type="button"
        onClick={onOpen}
        disabled={dimmed}
        aria-busy={opening}
        className={`as-row-btn group w-full flex items-center gap-4 px-4 sm:px-5 py-3.5 text-left focus:outline-none focus-visible:bg-sky-50/70 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#0096D6]/50 ${
          opening ? 'bg-sky-50/80' : 'hover:bg-slate-50/90'
        } ${dimmed ? 'opacity-45' : ''}`}
      >
        <span className="as-monogram w-9 h-9 rounded-xl bg-[#0B132B] text-[#7FD3FF] flex items-center justify-center text-[11px] font-extrabold tracking-wide flex-shrink-0">
          {monogram(account.name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-semibold text-slate-900 truncate">{account.name}</span>
          {opening && (
            <span className="as-fade flex items-center gap-1.5 text-[11px] font-semibold text-[#007DB8] mt-0.5">
              <Loader2 className="w-3 h-3 animate-spin" /> Opening dashboard…
            </span>
          )}
        </span>

        <span className="flex items-center gap-3 flex-shrink-0">
          {score !== null ? (
            <>
              <span className="hidden sm:block w-24 h-1.5 rounded-full bg-slate-100 overflow-hidden" aria-hidden>
                <span
                  className="as-meter-fill block h-full rounded-full bg-gradient-to-r from-[#007DB8] to-[#00B0FF]"
                  style={{ width: `${Math.max(2, Math.min(100, (score / max) * 100))}%` }}
                />
              </span>
              <span className="w-14 text-right text-sm font-bold text-slate-900 tabular-nums">
                {score}<span className="text-[11px] font-semibold text-slate-400">/{max}</span>
              </span>
            </>
          ) : (
            <span
              className="whitespace-nowrap sm:w-[10.25rem] text-right text-[11px] font-semibold text-slate-500"
              title="Not generated yet, or withheld because too little of the account is measured"
            >
              Not scored
            </span>
          )}
          <ArrowRight className="as-row-arrow w-4 h-4 text-[#0096D6]" aria-hidden />
        </span>
      </button>
    </li>
  );
}

function SkeletonRows() {
  return (
    <ul aria-busy="true" aria-label="Loading accounts" className="divide-y divide-slate-100">
      {Array.from({ length: 6 }, (_, i) => (
        <li key={i} className="flex items-center gap-4 px-4 sm:px-5 py-3.5">
          <span className="cs-skeleton-line w-9 h-9 rounded-xl" />
          <span className="cs-skeleton-line h-3 rounded flex-1 max-w-[16rem]" style={{ width: `${70 - i * 6}%` }} />
          <span className="cs-skeleton-line h-1.5 w-24 rounded-full ml-auto hidden sm:block" />
          <span className="cs-skeleton-line h-3 w-10 rounded" />
        </li>
      ))}
    </ul>
  );
}

function PageButton({ children, onClick, disabled, current }: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  current?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-current={current ? 'page' : undefined}
      className={`inline-flex items-center justify-center gap-1 min-w-[2.25rem] h-9 px-2.5 rounded-lg border font-bold tabular-nums transition-[background-color,border-color,color,transform] duration-150 active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0096D6]/50 disabled:opacity-40 disabled:active:scale-100 ${
        current
          ? 'bg-[#0B132B] text-white border-[#0B132B]'
          : 'bg-white text-slate-700 border-slate-200 hover:bg-slate-50 hover:border-slate-300'
      }`}
    >
      {children}
    </button>
  );
}

// The first two letters of the company's first word. Initials of the first
// two words read badly here: "Accenture Inc" became "AI".
function monogram(name: string): string {
  const word = name.replace(/[^A-Za-z0-9 ]+/g, ' ').trim().split(/\s+/)[0] ?? '';
  return word.slice(0, 2).toUpperCase() || '#';
}
