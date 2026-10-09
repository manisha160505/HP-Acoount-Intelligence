'use client';

/**
 * The account's regeneration pipeline, for admins.
 *
 * Uploads only store files (29 Sep): nothing regenerates until someone submits
 * the account here. The panel shows every section of the account grouped by
 * status - running, queued, failed, stale, never run, current - with why each
 * one is in that state (data file, upstream, code, prompt, rules, model,
 * instructions), live progress for what is running, and the account's recent
 * runs with what each cost. Preview and Submit call the same planner, so what
 * the preview says is what the run does.
 *
 * Refreshing is cheap: the backend works staleness out from fingerprints and
 * makes no model calls. While anything is queued or running the panel
 * refreshes itself every few seconds.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
import api from '@/services/api';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Eye,
  Loader2,
  PauseCircle,
  PlayCircle,
  RefreshCw,
  Send,
  XCircle,
} from 'lucide-react';

type Status = 'RUNNING' | 'QUEUED' | 'FILES_MISSING' | 'NO_DATA' | 'FAILED' | 'STALE' | 'DEGRADED' | 'BLOCKED' | 'NEVER_RUN' | 'CURRENT';

interface Reason {
  category: string;
  category_label: string;
  label: string;
  detail?: string;
  old?: unknown;
  new?: unknown;
}

interface JobView {
  id: string;
  status: string;
  started_at?: string | null;
  requested_at?: string | null;
  progress?: { done: number; total: number; label?: string } | null;
  run_ids?: string[];
}

interface Section {
  node_id: string;
  label: string;
  feature_label: string;
  kind: string;
  llm: boolean;
  status: Status;
  reasons: Reason[];
  categories: string[];
  generated_at?: string | null;
  last_error?: { code?: string; message?: string; at?: string } | null;
  job?: JobView | null;
  has_data: boolean;
  missing_files?: { dataset?: string; label?: string; file?: string; path?: string }[];
  datasets_not_provided?: { dataset: string; label: string }[];
  // Unprovided datasets another source fills for the same card - not gaps.
  datasets_covered?: { dataset: string; label: string; covered_by: string }[];
}

// A dataset some section reads that this account has no file for.
interface DataGap {
  dataset: string;
  label: string;
  sections: string[];
  blocks: string[];   // sections left with nothing at all to build from
}

// A dataset with no file that another source fills (regen/coverage.py).
interface DataCovered {
  dataset: string;
  label: string;
  covered_by: string;
  sections: string[];
}

interface RunRow {
  _id: string;
  status: string;
  created_at: string;
  finished_at?: string;
  actor?: string;
  reason?: string;
  request?: { force?: boolean; features?: unknown; nodes?: unknown };
  totals?: Record<string, number>;
}

interface PipelineResponse {
  groups: Record<Status, Section[]>;
  counts: Record<Status, number>;
  needs_run: number;
  data_gaps?: DataGap[];
  data_covered?: DataCovered[];
  queue: { paused: boolean; reason?: string | null; paused_at?: string | null;
           resume_after?: string | null };
  runs: RunRow[];
}

interface PlanItem {
  node_id: string;
  label: string;
  action: 'run' | 'skip_current' | 'in_progress' | 'cannot_run';
  forced: boolean;
  needed_by: string[];
  status: Status;
  llm: boolean;
  kind: string;
  missing_files?: { file?: string }[];
}

interface PlanResponse {
  accounts: { items: PlanItem[]; counts: Record<string, number>; downstream_left_stale: string[] }[];
  totals: Record<string, number>;
}

interface RunDetail {
  _id: string;
  status: string;
  progress: { done: number; total: number };
  usage: { model_calls: number; tokens: number; embedding_calls: number; embedded_texts: number };
  jobs: {
    job_id: string;
    node_id: string;
    status: string;
    outcome?: string;
    duration_ms?: number;
    error?: { code?: string; message?: string } | null;
    changed_inputs?: string[];
    progress?: { done: number; total: number; label?: string } | null;
    usage: { model_calls: number; tokens: number };
  }[];
}

const GROUPS: { key: Status; title: string; tone: string; open: boolean }[] = [
  { key: 'RUNNING', title: 'Running', tone: 'text-blue-700 bg-blue-50 border-blue-200', open: true },
  { key: 'QUEUED', title: 'Queued', tone: 'text-indigo-700 bg-indigo-50 border-indigo-200', open: true },
  { key: 'NO_DATA', title: 'Data not provided - upload a dataset before this can run', tone: 'text-stone-800 bg-stone-50 border-stone-300', open: true },
  { key: 'FAILED', title: 'Failed', tone: 'text-red-700 bg-red-50 border-red-200', open: true },
  { key: 'STALE', title: 'Stale', tone: 'text-amber-800 bg-amber-50 border-amber-200', open: true },
  { key: 'DEGRADED', title: 'Degraded (fallback output)', tone: 'text-orange-800 bg-orange-50 border-orange-200', open: true },
  { key: 'BLOCKED', title: 'Blocked (preconditions not met)', tone: 'text-gray-700 bg-gray-50 border-gray-200', open: false },
  { key: 'NEVER_RUN', title: 'Never run', tone: 'text-slate-700 bg-slate-50 border-slate-200', open: true },
  { key: 'CURRENT', title: 'Current', tone: 'text-emerald-800 bg-emerald-50 border-emerald-200', open: false },
];

const NEEDS_RUN: Status[] = ['FAILED', 'STALE', 'NEVER_RUN', 'DEGRADED'];

const CATEGORY_TONE: Record<string, string> = {
  data_file: 'bg-sky-100 text-sky-800',
  upstream: 'bg-violet-100 text-violet-800',
  code: 'bg-fuchsia-100 text-fuchsia-800',
  prompt: 'bg-pink-100 text-pink-800',
  rules: 'bg-teal-100 text-teal-800',
  model: 'bg-orange-100 text-orange-800',
  instructions: 'bg-lime-100 text-lime-800',
  account_details: 'bg-lime-100 text-lime-800',
  legacy: 'bg-gray-200 text-gray-700',
  never_run: 'bg-slate-200 text-slate-700',
  failed: 'bg-red-100 text-red-800',
  files_missing: 'bg-rose-200 text-rose-900',
  no_data: 'bg-stone-200 text-stone-800',
};

// Every dataset this account is missing, once, with the sections that read
// it - the list to take to whoever supplies the data.
// Files uploaded once but not on this server's disk, by dataset - these
// sections have no card of their own; the gaps box is the one place to look.
interface MissingOnServer {
  dataset: string;
  label: string;
  files: string[];
  sections: string[];
}

function missingOnServer(sections: Section[]): MissingOnServer[] {
  const by: Record<string, MissingOnServer> = {};
  for (const s of sections) {
    for (const f of s.missing_files || []) {
      const key = f.dataset || '?';
      const entry = by[key] || (by[key] = { dataset: key, label: f.label || key, files: [], sections: [] });
      const name = f.file || f.path || '?';
      if (!entry.files.includes(name)) entry.files.push(name);
      if (!entry.sections.includes(s.label)) entry.sections.push(s.label);
    }
  }
  return Object.values(by).sort((a, b) => a.label.localeCompare(b.label));
}

function DataGapsBox({ gaps, missing, covered }:
  { gaps: DataGap[]; missing: MissingOnServer[]; covered: DataCovered[] }) {
  const blocking = gaps.filter(g => g.blocks.length > 0).length;
  return (
    <div className="rounded-xl border border-stone-300 bg-stone-50 px-4 py-3">
      <div className="text-xs font-bold uppercase tracking-wider text-stone-800">
        Data gaps ({gaps.length} dataset{gaps.length === 1 ? '' : 's'} not provided
        {blocking > 0 ? `; ${blocking} read by a section that has no data at all` : ''}
        {missing.length > 0 ? `; ${missing.length} with files missing on this server` : ''})
      </div>
      <ul className="mt-2 space-y-1">
        {missing.map(m => (
          <li key={`missing-${m.dataset}`} className="text-[11px] text-stone-800">
            <span className="font-bold">{m.label}</span>
            <span className="ml-1.5 px-1.5 py-0.5 rounded bg-rose-200 text-rose-900 font-bold"
              title={`Uploaded before, but not on this server's disk - upload again before running:\n${m.files.join('\n')}`}>
              {m.files.length} FILE{m.files.length === 1 ? '' : 'S'} MISSING ON SERVER
            </span>
            <span className="text-stone-500"> - read by {m.sections.join(', ')}</span>
          </li>
        ))}
        {gaps.map(g => (
          <li key={g.dataset} className="text-[11px] text-stone-800">
            <span className="font-bold">{g.label}</span>
            {g.blocks.length > 0 && (
              <span className="ml-1.5 px-1.5 py-0.5 rounded bg-stone-300 text-stone-900 font-bold"
                title={`${g.blocks.join(', ')} ha${g.blocks.length === 1 ? 's' : 've'} no data at all. Uploading this, or any other dataset listed on ${g.blocks.length === 1 ? 'that section' : 'those sections'}, lets ${g.blocks.length === 1 ? 'it' : 'them'} run.`}>
                {g.blocks.length} SECTION{g.blocks.length === 1 ? '' : 'S'} CAN&apos;T RUN WITHOUT DATA
              </span>
            )}
            <span className="text-stone-500"> - read by {g.sections.join(', ')}</span>
          </li>
        ))}
      </ul>
      {covered.length > 0 && (
        <div className="mt-2.5 border-t border-stone-200 pt-2">
          <div className="text-[10px] font-bold uppercase tracking-wider text-stone-500">
            Covered by another source ({covered.length}) - not gaps
          </div>
          <ul className="mt-1 space-y-0.5">
            {covered.map(c => (
              <li key={`covered-${c.dataset}`} className="text-[11px] text-stone-500"
                title={`Read by ${c.sections.join(', ')}`}>
                {c.label}: covered by {c.covered_by}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function fmt(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? String(value) : d.toLocaleString();
}

function errorText(err: unknown): string {
  const e = err as { response?: { data?: { detail?: string; error?: { message?: string } } }; message?: string };
  return e?.response?.data?.detail || e?.response?.data?.error?.message || e?.message || 'Request failed';
}

function ProgressBar({ done, total, label }: { done: number; total: number; label?: string }) {
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  return (
    <div className="mt-2">
      <div className="h-2 w-full rounded-full bg-blue-100 overflow-hidden">
        <div className="h-2 bg-blue-600 transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-1 text-[11px] text-blue-800 font-medium">
        {label ? `${label} · ` : ''}{done}/{total} ({pct}%)
      </div>
    </div>
  );
}

export default function PipelinePanel({ accountId }: { accountId: string }) {
  const [data, setData] = useState<PipelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [open, setOpen] = useState<Record<string, boolean>>(
    Object.fromEntries(GROUPS.map(g => [g.key, g.open])),
  );
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planForce, setPlanForce] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [runDetail, setRunDetail] = useState<RunDetail | null>(null);
  const [runOpenId, setRunOpenId] = useState<string | null>(null);

  const load = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true);
    try {
      const res = await api.get<PipelineResponse>(`/accounts/${accountId}/pipeline`);
      setData(res.data);
      setError(null);
    } catch (err) {
      setError(errorText(err));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [accountId]);

  const loadRun = useCallback(async (runId: string) => {
    try {
      const res = await api.get<RunDetail>(`/regeneration/${runId}`);
      setRunDetail(res.data);
    } catch (err) {
      setError(errorText(err));
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const active = useMemo(
    () => !!data && ((data.counts.RUNNING || 0) + (data.counts.QUEUED || 0) > 0),
    [data],
  );

  // Poll fast while something is queued or running and keep an open run's
  // detail fresh; slower when idle, so a run started from another tab or the
  // platform page still shows up without a reload. Paused while the tab is hidden.
  useEffect(() => {
    const t = setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      load(true);
      if (runOpenId) loadRun(runOpenId);
    }, active ? 5000 : 15000);
    return () => clearInterval(t);
  }, [active, load, loadRun, runOpenId]);

  const request = (force: boolean) => {
    const body: Record<string, unknown> = { accounts: [accountId], force };
    if (selected.size) body.nodes = Array.from(selected);
    return body;
  };

  const preview = async (force = false) => {
    setBusy('preview');
    setNotice(null);
    try {
      const res = await api.post<PlanResponse>('/regeneration/preview', request(force));
      setPlan(res.data);
      setPlanForce(force);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const submit = async (force = false) => {
    if (force && !window.confirm(
      'Force re-run regenerates the selected sections even if they are current, using model quota. Continue?')) {
      return;
    }
    setBusy('submit');
    try {
      const res = await api.post<{ _id: string; totals: Record<string, number>; status: string }>(
        '/regeneration', request(force));
      const t = res.data.totals || {};
      setNotice(res.data.status === 'NOTHING_TO_DO'
        ? 'Nothing to run - every requested section is already current.'
        : `Submitted: ${t.queued || 0} section(s) queued, ${t.skip_current || 0} already current, `
          + `${t.cannot_run || 0} without data.`);
      setPlan(null);
      setSelected(new Set());
      setRunOpenId(res.data._id);
      await Promise.all([load(true), loadRun(res.data._id)]);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const resume = async () => {
    setBusy('resume');
    try {
      await api.post('/regeneration/queue/resume');
      await load(true);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const cancelRun = async (runId: string) => {
    if (!window.confirm('Cancel the sections this run has not started yet?')) return;
    try {
      await api.post(`/regeneration/${runId}/cancel`);
      await Promise.all([load(true), loadRun(runId)]);
    } catch (err) {
      setError(errorText(err));
    }
  };

  const toggle = (nodeId: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId); else next.add(nodeId);
      return next;
    });
  };

  const lastRun = data?.runs?.[0];

  return (
    <div className="space-y-5">
      {/* Header: what needs a run, queue state, actions */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-bold text-gray-900">Regeneration pipeline</h2>
          <p className="text-xs text-gray-500 mt-1 max-w-2xl">
            Uploading files only stores them. Nothing regenerates until you submit.
            Submit runs every section that is stale, failed, degraded or never run - each once,
            in dependency order. Select sections to run just those.
          </p>
          {lastRun && (
            <p className="text-xs text-gray-600 mt-2">
              Last run: <span className="font-semibold">{lastRun.status}</span> · {fmt(lastRun.created_at)}
              {lastRun.actor ? ` · ${lastRun.actor}` : ''}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={() => load()} disabled={loading}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-gray-300 bg-white hover:bg-gray-50">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
          </button>
          <button type="button" onClick={() => preview(false)} disabled={!!busy}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-hp-navy text-hp-navy bg-white hover:bg-blue-50">
            {busy === 'preview' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Eye className="w-3.5 h-3.5" />}
            Preview{selected.size ? ` (${selected.size})` : ''}
          </button>
          <button type="button" onClick={() => submit(false)} disabled={!!busy || (!selected.size && !data?.needs_run)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-hp-navy text-white hover:opacity-90 disabled:opacity-40">
            {busy === 'submit' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            {selected.size ? `Submit ${selected.size} selected` : `Submit & start pipeline (${data?.needs_run ?? 0})`}
          </button>
          {selected.size > 0 && (
            <button type="button" onClick={() => submit(true)} disabled={!!busy}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg border border-red-300 text-red-700 bg-white hover:bg-red-50">
              Force re-run selected
            </button>
          )}
        </div>
      </div>

      {data?.queue?.paused && (
        <div className="flex items-center justify-between gap-3 p-3 rounded-xl border border-amber-300 bg-amber-50">
          <div className="flex items-start gap-2 text-xs text-amber-900">
            <PauseCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <div className="font-bold">Queue paused</div>
              <div>{data.queue.reason || 'Paused by an admin'} · {fmt(data.queue.paused_at)}</div>
              {/* A quota pause lifts itself once its window passes; an admin's
                  waits for an admin. Saying which is the difference between
                  waiting and going to look for someone. */}
              <div className="mt-0.5">
                {data.queue.resume_after
                  ? <>Nothing runs for any account until {fmt(data.queue.resume_after)}, when it resumes by itself. Resume now to start sooner.</>
                  : <>Nothing runs for any account until it is resumed.</>}
              </div>
            </div>
          </div>
          <button type="button" onClick={resume} disabled={busy === 'resume'}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-amber-600 text-white hover:bg-amber-700">
            <PlayCircle className="w-3.5 h-3.5" /> Resume
          </button>
        </div>
      )}

      {error && (
        <div className="flex items-start gap-2 p-3 rounded-xl border border-red-200 bg-red-50 text-xs text-red-800">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" /> <span>{error}</span>
        </div>
      )}
      {notice && (
        <div className="flex items-start gap-2 p-3 rounded-xl border border-emerald-200 bg-emerald-50 text-xs text-emerald-900">
          <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" /> <span>{notice}</span>
        </div>
      )}

      {/* Preview */}
      {plan && plan.accounts[0] && (
        <div className="p-4 rounded-xl border border-blue-200 bg-blue-50/60">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-blue-900">
              Preview{planForce ? ' (forced)' : ''} - no model calls made
            </h3>
            <button type="button" onClick={() => setPlan(null)} className="text-blue-700 hover:text-blue-900">
              <XCircle className="w-4 h-4" />
            </button>
          </div>
          <div className="mt-2 grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs">
            {[
              ['Will run', plan.totals.run],
              ['Model-backed', plan.totals.llm_sections],
              ['Index builds', plan.totals.index_builds],
              ['Already current', plan.totals.skip_current],
              ['Cannot run', plan.totals.cannot_run],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded-lg bg-white border border-blue-100 p-2">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-bold">{k}</div>
                <div className="text-lg font-bold text-gray-900">{v ?? 0}</div>
              </div>
            ))}
          </div>
          <ul className="mt-3 space-y-1 text-xs">
            {plan.accounts[0].items.map(item => (
              <li key={item.node_id} className="flex items-center gap-2">
                <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                  item.action === 'run' ? 'bg-hp-navy text-white'
                    : item.action === 'cannot_run' ? 'bg-gray-300 text-gray-800'
                      : 'bg-gray-100 text-gray-600'}`}>
                  {item.action.replace('_', ' ')}
                </span>
                <span className="font-semibold text-gray-800">{item.label}</span>
                {item.forced && <span className="text-red-700 font-bold">forced</span>}
                {item.action === 'cannot_run' && (item.missing_files?.length ?? 0) > 0 && (
                  <span className="text-rose-800">{item.missing_files!.length} file(s) missing on server - upload again</span>
                )}
                {item.needed_by.length > 0 && (
                  <span className="text-gray-500">needed by {item.needed_by.join(', ')}</span>
                )}
              </li>
            ))}
          </ul>
          {plan.accounts[0].downstream_left_stale.length > 0 && (
            <p className="mt-2 text-[11px] text-gray-600">
              Will stay stale afterwards (not requested): {plan.accounts[0].downstream_left_stale.join(', ')}
            </p>
          )}
          <div className="mt-3 flex gap-2">
            <button type="button" onClick={() => submit(planForce)} disabled={!!busy || !plan.totals.run}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-bold rounded-lg bg-hp-navy text-white disabled:opacity-40">
              <Send className="w-3.5 h-3.5" /> Submit this plan
            </button>
          </div>
        </div>
      )}

      {/* Sections by status */}
      {!data && loading && (
        <div className="flex items-center gap-2 text-sm text-gray-500"><Loader2 className="w-4 h-4 animate-spin" /> Loading pipeline…</div>
      )}
      {data && (() => {
        const missing = missingOnServer(data.groups.FILES_MISSING || []);
        return ((data.data_gaps?.length ?? 0) > 0 || missing.length > 0
                || (data.data_covered?.length ?? 0) > 0)
          ? <DataGapsBox gaps={data.data_gaps || []} missing={missing} covered={data.data_covered || []} />
          : null;
      })()}
      {data && GROUPS.filter(g => (data.groups[g.key] || []).length > 0).map(g => {
        const rows = data.groups[g.key];
        const selectable = NEEDS_RUN.includes(g.key) || g.key === 'CURRENT';
        return (
          <div key={g.key} className={`rounded-xl border ${g.tone}`}>
            <button type="button"
              onClick={() => setOpen(prev => ({ ...prev, [g.key]: !prev[g.key] }))}
              className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-bold uppercase tracking-wider">
              <span className="flex items-center gap-2">
                {open[g.key] ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                {g.title} ({rows.length})
              </span>
            </button>
            {open[g.key] && (
              <ul className="bg-white divide-y divide-gray-100 rounded-b-xl">
                {rows.map(s => (
                  <li key={s.node_id} className="px-4 py-3">
                    <div className="flex items-start gap-3">
                      {selectable && (
                        <input type="checkbox" className="mt-1" checked={selected.has(s.node_id)}
                          onChange={() => toggle(s.node_id)} aria-label={`select ${s.label}`} />
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold text-gray-900">{s.label}</span>
                          {s.kind === 'index' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 font-bold">INDEX</span>}
                          {s.llm && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-100 text-gray-600 font-bold">MODEL</span>}
                          {!s.has_data && s.status !== 'NO_DATA' && <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-200 text-gray-700 font-bold">NO DATA UPLOADED</span>}
                          {(s.missing_files?.length ?? 0) > 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-200 text-rose-900 font-bold">
                              {s.missing_files!.length} FILE(S) MISSING ON SERVER
                            </span>
                          )}
                          <span className="text-[11px] text-gray-500 ml-auto flex items-center gap-1">
                            <Clock className="w-3 h-3" /> {s.generated_at ? `built ${fmt(s.generated_at)}` : 'never built'}
                          </span>
                        </div>
                        {s.status === 'RUNNING' && s.job && (
                          s.job.progress
                            ? <ProgressBar done={s.job.progress.done} total={s.job.progress.total} label={s.job.progress.label} />
                            : <div className="mt-2 flex items-center gap-2 text-[11px] text-blue-800"><Loader2 className="w-3 h-3 animate-spin" /> running since {fmt(s.job.started_at)}</div>
                        )}
                        {s.status === 'QUEUED' && s.job && (
                          <div className="mt-1 text-[11px] text-indigo-800">queued {fmt(s.job.requested_at)}</div>
                        )}
                        {(s.datasets_not_provided?.length ?? 0) > 0 && s.status !== 'NO_DATA' && (
                          <div className="mt-1.5 text-[11px] text-stone-700">
                            <span className="font-bold">Not provided:</span>{' '}
                            {s.datasets_not_provided!.map(d => d.label).join(', ')}
                          </div>
                        )}
                        {(s.datasets_covered?.length ?? 0) > 0 && (
                          <div className="mt-1 text-[11px] text-stone-500">
                            <span className="font-bold">Covered:</span>{' '}
                            {s.datasets_covered!.map(d => `${d.label} (by ${d.covered_by})`).join(', ')}
                          </div>
                        )}
                        {s.reasons.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {s.reasons.map((r, i) => (
                              <li key={i} className="flex flex-wrap items-center gap-2 text-[11px]">
                                <span className={`px-1.5 py-0.5 rounded font-bold ${CATEGORY_TONE[r.category] || 'bg-gray-100 text-gray-700'}`}>
                                  {r.category_label}
                                </span>
                                <span className="text-gray-800 font-medium">{r.label}</span>
                                {r.detail && <span className="text-gray-500 break-all">{r.detail}</span>}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        );
      })}

      {/* Run history */}
      {data && data.runs.length > 0 && (
        <div className="rounded-xl border border-gray-200">
          <div className="px-4 py-2.5 text-xs font-bold uppercase tracking-wider text-gray-700 bg-gray-50 rounded-t-xl">Recent runs</div>
          <ul className="divide-y divide-gray-100">
            {data.runs.map(r => (
              <li key={r._id} className="px-4 py-2.5 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  <button type="button" className="font-semibold text-hp-navy hover:underline"
                    onClick={() => {
                      if (runOpenId === r._id) { setRunOpenId(null); setRunDetail(null); return; }
                      setRunOpenId(r._id); loadRun(r._id);
                    }}>
                    {fmt(r.created_at)}
                  </button>
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 font-bold">{r.status}</span>
                  <span className="text-gray-600">{r.actor}</span>
                  {r.request?.force && <span className="text-red-700 font-bold">forced</span>}
                  <span className="text-gray-500">
                    {r.totals?.queued ?? 0} queued · {r.totals?.skip_current ?? 0} current · {r.totals?.cannot_run ?? 0} no data
                  </span>
                  {r.status === 'RUNNING' && (
                    <button type="button" onClick={() => cancelRun(r._id)}
                      className="ml-auto text-red-700 font-bold hover:underline">Cancel</button>
                  )}
                </div>
                {runOpenId === r._id && runDetail && runDetail._id === r._id && (
                  <div className="mt-2 rounded-lg border border-gray-200 bg-gray-50 p-3">
                    <ProgressBar done={runDetail.progress.done} total={runDetail.progress.total} label="sections finished" />
                    <div className="mt-2 text-[11px] text-gray-700">
                      Model calls <b>{runDetail.usage.model_calls}</b> · tokens <b>{runDetail.usage.tokens.toLocaleString()}</b> ·
                      embedding calls <b>{runDetail.usage.embedding_calls}</b>
                    </div>
                    <table className="mt-2 w-full text-[11px]">
                      <thead>
                        <tr className="text-left text-gray-500">
                          <th className="py-1 pr-2">Section</th><th className="py-1 pr-2">Status</th>
                          <th className="py-1 pr-2">Why it ran</th><th className="py-1 pr-2">Time</th>
                          <th className="py-1 pr-2">Calls / tokens</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runDetail.jobs.map(j => (
                          <tr key={j.job_id} className="border-t border-gray-200 align-top">
                            <td className="py-1 pr-2 font-semibold">{j.node_id}</td>
                            <td className="py-1 pr-2">
                              {j.status}{j.outcome && j.outcome !== 'committed' ? ` (${j.outcome})` : ''}
                              {j.progress && j.status === 'RUNNING' && ` ${j.progress.done}/${j.progress.total}`}
                              {j.error?.message && <div className="text-red-700 break-all">{j.error.code}: {j.error.message}</div>}
                            </td>
                            <td className="py-1 pr-2 text-gray-600 break-all">{(j.changed_inputs || []).slice(0, 4).join(', ') || '—'}</td>
                            <td className="py-1 pr-2">{j.duration_ms != null ? `${(j.duration_ms / 1000).toFixed(1)}s` : '—'}</td>
                            <td className="py-1 pr-2">{j.usage.model_calls} / {j.usage.tokens.toLocaleString()}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
