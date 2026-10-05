'use client';

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { PageHero } from '@/components/common/motion';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { NORTHSTAR_SIDEBAR_GROUPS, featureLabel } from '@/lib/features';
import type { FeatureRules, ReferenceSet, ReferenceSetSummary, Rule, RulesIndexResponse } from '@/types/rules';
import {
  FeatureNavItem, RuleBadges, RuleBody, RuleRow, RuleTreeNav, ancestors, featureIcon, indexRules,
} from '@/components/rules/RuleParts';
import { ReferenceView } from '@/components/rules/ReferenceParts';
import {
  AlertCircle, ArrowLeft, ArrowRight, BookMarked, BookOpen, ChevronRight, Loader2, Monitor, Search, Workflow, X,
} from 'lucide-react';

const SIDEBAR_ITEMS = NORTHSTAR_SIDEBAR_GROUPS.flatMap(g => g.items);
const iconFor = (key: string) => SIDEBAR_ITEMS.find(i => i.key === key)?.iconName;

// The selection lives in the URL (?feature=&rule=, or ?book=) so a rule can be linked to
// and Back steps through what was read. Read from window.location rather than
// useSearchParams, which would need a Suspense boundary - the same choice the
// dashboard makes.
function selectionFromUrl(): { feature: string | null; rule: string | null; book: string | null } {
  if (typeof window === 'undefined') return { feature: null, rule: null, book: null };
  const p = new URLSearchParams(window.location.search);
  return { feature: p.get('feature'), rule: p.get('rule'), book: p.get('book') };
}

export default function AdminRulesPage() {
  const [index, setIndex] = useState<RulesIndexResponse | null>(null);
  const [details, setDetails] = useState<Record<string, FeatureRules>>({});
  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feature, setFeature] = useState<string | null>(null);
  const [rule, setRule] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [openIds, setOpenIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState('');
  const [books, setBooks] = useState<ReferenceSetSummary[]>([]);
  const [bookData, setBookData] = useState<Record<string, ReferenceSet>>({});
  const [book, setBook] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  // Sidebar order and grouping, so the list reads the way sellers see the app.
  const groups = useMemo(() => {
    const keys = new Set(index?.features.map(f => f.feature_key));
    return NORTHSTAR_SIDEBAR_GROUPS
      .map(g => ({ title: g.sectionTitle, items: g.items.filter(i => keys.has(i.key)) }))
      .filter(g => g.items.length);
  }, [index]);
  const summaries = useMemo(() => new Map(index?.features.map(f => [f.feature_key, f])), [index]);
  const firstKey = groups[0]?.items[0]?.key ?? null;

  const load = useCallback(async (key: string) => {
    if (details[key]) return details[key];
    setLoading(key);
    try {
      const res = await api.get<FeatureRules>(`/admin/rules/${encodeURIComponent(key)}`);
      setDetails(prev => ({ ...prev, [key]: res.data }));
      return res.data;
    } catch (err) {
      setError(parseApiError(err, 'Failed to load this feature’s rules.').message);
      return null;
    } finally {
      setLoading(null);
    }
  }, [details]);

  useEffect(() => {
    api.get<RulesIndexResponse>('/admin/rules')
      .then(res => setIndex(res.data))
      .catch(err => setError(parseApiError(err, 'Failed to load the rules.').message));
    api.get<{ sets: ReferenceSetSummary[] }>('/admin/rules/reference')
      .then(res => setBooks(res.data.sets))
      .catch(err => setError(parseApiError(err, 'Failed to load the rule books.').message));
  }, []);

  const openBook = useCallback(async (key: string) => {
    setBook(key);
    setExpanded(null);
    if (bookData[key]) return;
    setLoading(`book:${key}`);
    try {
      const res = await api.get<ReferenceSet>(`/admin/rules/reference/${encodeURIComponent(key)}`);
      setBookData(prev => ({ ...prev, [key]: res.data }));
    } catch (err) {
      setError(parseApiError(err, 'Failed to load this rule book.').message);
    } finally {
      setLoading(null);
    }
  }, [bookData]);

  // Apply a selection: load the feature, open its tree and the rule's branch.
  const apply = useCallback(async (key: string, ruleId: string | null) => {
    setBook(null);
    setFeature(key);
    setRule(ruleId);
    setExpanded(key);
    const data = await load(key);
    if (data && ruleId) {
      const idx = indexRules(data.rules);
      setOpenIds(prev => {
        const next = new Set(prev);
        ancestors(idx, ruleId).forEach(a => next.add(a.id));
        return next;
      });
    }
  }, [load]);

  // First load and Back/Forward.
  useEffect(() => {
    if (!index) return;
    const sync = () => {
      const { feature: f, rule: r, book: b } = selectionFromUrl();
      if (b) { openBook(b); return; }
      const key = f && summaries.has(f) ? f : firstKey;
      if (key) apply(key, f === key ? r : null);
    };
    sync();
    window.addEventListener('popstate', sync);
    return () => window.removeEventListener('popstate', sync);
    // apply changes identity as details load; the URL is the source here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index]);

  const navigate = useCallback((key: string, ruleId: string | null) => {
    const params = new URLSearchParams({ feature: key, ...(ruleId ? { rule: ruleId } : {}) });
    window.history.pushState(null, '', `?${params}`);
    if (key !== feature) { setOpenIds(new Set()); setQuery(''); }
    apply(key, ruleId);
    // Bring the detail pane into view if it has scrolled off (always, on phones).
    requestAnimationFrame(() => {
      const top = detailRef.current?.getBoundingClientRect().top ?? 0;
      if (top < 0 || top > window.innerHeight * 0.6) {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }, [apply, feature]);

  const navigateBook = useCallback((key: string) => {
    window.history.pushState(null, '', `?${new URLSearchParams({ book: key })}`);
    openBook(key);
    requestAnimationFrame(() => {
      const top = detailRef.current?.getBoundingClientRect().top ?? 0;
      if (top < 0 || top > window.innerHeight * 0.6) {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }, [openBook]);

  const onFeatureClick = (key: string) => {
    if (key === feature && book) { navigate(key, rule); return; }
    if (key === feature) {
      // The open feature: its row toggles the tree and returns to the overview.
      if (rule) navigate(key, null);
      else setExpanded(expanded === key ? null : key);
      return;
    }
    navigate(key, null);
  };

  const toggleNode = useCallback((id: string) => setOpenIds(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  }), []);

  const data = feature ? details[feature] : undefined;
  const ruleIndex = useMemo(() => (data ? indexRules(data.rules) : null), [data]);
  const totalRules = index?.features.reduce((n, f) => n + f.rule_count, 0) ?? 0;

  return (
    <ProtectedRoute allowedRoles={['admin']}>
      <div className="as-page min-h-screen">
        <PageHero
          width="max-w-[88rem]"
          title="Rules"
          subtitle="How each feature decides what it shows. Choose a feature on the left, open its rule tree and select a rule to see what it calculates, how, and a worked example."
          actions={index && (
            <div className="as-glass-dark rounded-xl px-4 py-2.5 text-xs text-slate-200 flex items-center gap-4">
              <span><b className="text-white text-base tabular-nums">{index.features.length}</b> features</span>
              <span className="h-4 w-px bg-white/15" />
              <span><b className="text-white text-base tabular-nums">{totalRules}</b> rules</span>
              {books.length > 0 && <>
                <span className="h-4 w-px bg-white/15" />
                <span><b className="text-white text-base tabular-nums">{books.length}</b> rule books</span>
              </>}
            </div>
          )}
        />

        <div className="relative max-w-[88rem] mx-auto px-4 sm:px-6 lg:px-8 -mt-12 sm:-mt-14 pb-14">
          {error && (
            <div className="relative z-10 mb-4 bg-red-50 border border-red-200 p-4 rounded-xl flex items-center gap-2 text-red-800 text-xs font-semibold">
              <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />{error}
            </div>
          )}
          {!index && !error && (
            <div className="relative z-10 as-glass rounded-2xl p-16 flex flex-col items-center gap-3">
              <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
              <p className="text-xs text-gray-500 font-medium">Loading rules...</p>
            </div>
          )}

          {index && (
            <div className="relative z-10 grid grid-cols-1 lg:grid-cols-[20rem_minmax(0,1fr)] gap-6 items-start">
              {/* ------------------------------------------------ sidebar */}
              <aside className="as-rise as-glass-strong rounded-2xl lg:sticky lg:top-4 flex flex-col max-h-[60vh] lg:max-h-[calc(100vh-2rem)] overflow-hidden">
                <div className="px-4 pt-4 pb-3 border-b border-gray-100/80">
                  <div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-500">
                    <BookOpen className="w-3.5 h-3.5 text-hp-navy" />Features
                  </div>
                  {expanded && (
                    <label className="mt-3 flex items-center gap-2 rounded-lg bg-white ring-1 ring-gray-200 focus-within:ring-2 focus-within:ring-hp-navy px-2.5 py-1.5 transition-shadow">
                      <Search className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" />
                      <input value={query} onChange={e => setQuery(e.target.value)}
                        placeholder={`Search ${featureLabel(expanded)} rules`}
                        className="min-w-0 flex-1 bg-transparent text-xs text-gray-800 placeholder:text-gray-400 focus:outline-none" />
                      {query && (
                        <button type="button" onClick={() => setQuery('')} aria-label="Clear search" className="text-gray-400 hover:text-gray-700">
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </label>
                  )}
                </div>
                <nav className="min-h-0 flex-1 overflow-y-auto px-2 py-3 space-y-4" aria-label="Rules by feature">
                  {groups.map(g => (
                    <div key={g.title}>
                      <h2 className="px-2.5 mb-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-400">{g.title}</h2>
                      <ul className="space-y-1">
                        {g.items.map(item => {
                          const s = summaries.get(item.key)!;
                          const tree = details[item.key];
                          return (
                            <FeatureNavItem key={item.key} label={item.label} iconName={item.iconName}
                              ruleCount={s.rule_count}
                              active={feature === item.key && !book} expanded={expanded === item.key && !!tree}
                              loading={loading === item.key} onSelect={() => onFeatureClick(item.key)}>
                              {tree && (
                                <RuleTreeNav index={indexRules(tree.rules)} selectedId={feature === item.key ? rule : null}
                                  openIds={openIds} onToggle={toggleNode} query={query}
                                  onSelect={id => navigate(item.key, id)} />
                              )}
                            </FeatureNavItem>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                  {books.length > 0 && (
                    <div>
                      <h2 className="px-2.5 mb-1.5 text-[10px] font-bold uppercase tracking-[0.14em] text-gray-400">Rule books</h2>
                      <ul className="space-y-1">
                        {books.map(b => {
                          const active = book === b.key;
                          return (
                            <li key={b.key}>
                              <button type="button" onClick={() => navigateBook(b.key)} aria-current={active ? 'page' : undefined}
                                className={`group w-full flex items-center gap-2.5 rounded-xl px-2.5 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-hp-navy ${
                                  active ? 'bg-hp-dark text-white shadow-md' : 'text-gray-800 hover:bg-white/80'}`}>
                                <span className={`flex-shrink-0 rounded-lg p-1.5 transition-colors ${active ? 'bg-white/15 text-white' : 'bg-hp-dark/[0.06] text-hp-dark group-hover:bg-hp-blue group-hover:text-white'}`}>
                                  {loading === `book:${b.key}` ? <Loader2 className="w-4 h-4 animate-spin" /> : <BookMarked className="w-4 h-4" />}
                                </span>
                                <span className="min-w-0 flex-1">
                                  <span className="block truncate text-[13px] font-bold">{b.title}</span>
                                  <span className={`block text-[10px] font-semibold ${active ? 'text-sky-200' : 'text-gray-500'}`}>{b.count} entries</span>
                                </span>
                              </button>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  )}
                  {index.missing.length > 0 && (
                    <p className="mx-2 rounded-lg bg-amber-50 ring-1 ring-amber-200 p-2.5 text-[11px] text-amber-900">
                      No rule book yet for: {index.missing.map(featureLabel).join(', ')}.
                    </p>
                  )}
                </nav>
              </aside>

              {/* ------------------------------------------------- detail */}
              <div ref={detailRef} className="min-w-0 scroll-mt-4">
                {book ? (
                  bookData[book]
                    ? <ReferenceView key={book} data={bookData[book]} onOpenFeature={k => navigate(k, null)} />
                    : <div className="as-glass rounded-2xl p-16 flex justify-center"><Loader2 className="w-8 h-8 text-hp-navy animate-spin" /></div>
                ) : !data || !feature || !ruleIndex ? (
                  <div className="as-glass rounded-2xl p-16 flex justify-center"><Loader2 className="w-8 h-8 text-hp-navy animate-spin" /></div>
                ) : rule && ruleIndex.byId.get(rule) ? (
                  <RuleDetail key={`${feature}:${rule}`} featureKey={feature} index={ruleIndex}
                    rule={ruleIndex.byId.get(rule)!} onNavigate={navigate} books={books} onOpenBook={navigateBook} />
                ) : (
                  <FeatureOverview key={feature} featureKey={feature} data={data} index={ruleIndex} onNavigate={navigate}
                    books={books.filter(b => b.used_by.includes(feature))} onOpenBook={navigateBook} />
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </ProtectedRoute>
  );
}

// ------------------------------------------------------------- right-hand panes

type Navigate = (feature: string, rule: string | null) => void;

function FeatureHeader({ featureKey, children }: { featureKey: string; children?: React.ReactNode }) {
  const Icon = featureIcon(iconFor(featureKey));
  return (
    <div className="flex items-start gap-3.5">
      <span className="flex-shrink-0 rounded-xl bg-hp-dark text-white p-2.5 shadow-md"><Icon className="w-5 h-5" /></span>
      <div className="min-w-0">{children}</div>
    </div>
  );
}

function FeatureOverview({ featureKey, data, index, onNavigate, books, onOpenBook }: {
  books: ReferenceSetSummary[]; onOpenBook: (key: string) => void;
  featureKey: string; data: FeatureRules; index: ReturnType<typeof indexRules>; onNavigate: Navigate;
}) {
  return (
    <div className="space-y-5">
      <div className="as-rise as-glass-strong rounded-2xl p-5 sm:p-6">
        <FeatureHeader featureKey={featureKey}>
          <h2 className="text-xl font-extrabold text-gray-900 tracking-tight">{featureLabel(featureKey)}</h2>
          <p className="mt-1 text-[13px] leading-relaxed text-gray-600">{data.purpose}</p>
        </FeatureHeader>
      </div>

      <div className="as-rise grid grid-cols-1 xl:grid-cols-2 gap-5" style={{ ['--as-delay' as string]: '60ms' }}>
        <div className="as-glass rounded-2xl p-5">
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-gray-500"><Monitor className="w-3.5 h-3.5 text-hp-navy" />What the seller sees</h3>
          <p className="mt-2 text-[13px] leading-relaxed text-gray-800">{data.final_output}</p>
        </div>
        {data.how_it_combines && (
          <div className="as-glass rounded-2xl p-5">
            <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-gray-500"><Workflow className="w-3.5 h-3.5 text-hp-navy" />How the rules combine</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-gray-800 whitespace-pre-line">{data.how_it_combines}</p>
          </div>
        )}
      </div>

      {books.length > 0 && (
        <section className="as-rise as-glass rounded-2xl p-5" style={{ ['--as-delay' as string]: '90ms' }}>
          <h3 className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-wider text-gray-500">
            <BookMarked className="w-3.5 h-3.5 text-hp-navy" />Rule books this feature applies
          </h3>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
            {books.map(b => (
              <button key={b.key} type="button" onClick={() => onOpenBook(b.key)}
                className="group text-left rounded-xl bg-white/80 ring-1 ring-gray-200 px-4 py-3 hover:bg-white hover:shadow-md transition-[box-shadow,background-color]">
                <span className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-bold text-gray-900 group-hover:text-hp-blue transition-colors">{b.title}</span>
                  <span className="text-[10px] font-semibold text-gray-400 tabular-nums">{b.count} entries</span>
                </span>
                <span className="mt-0.5 block text-xs text-gray-600 leading-relaxed">{b.summary}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="as-rise as-glass-strong rounded-2xl p-5 sm:p-6" style={{ ['--as-delay' as string]: '110ms' }}>
        <h3 className="text-sm font-extrabold text-gray-900">Rules in this feature</h3>
        <p className="text-[11px] text-gray-500">{data.rules.length} rules, {index.roots.length} at the top level. Select one here or in the tree on the left.</p>
        <div className="mt-4 space-y-2">
          {index.roots.map((r, i) => (
            <RuleRow key={r.id} rule={r} index={i} partCount={index.children.get(r.id)?.length ?? 0}
              onSelect={() => onNavigate(featureKey, r.id)} />
          ))}
        </div>
      </section>
    </div>
  );
}

function RuleDetail({ featureKey, index, rule, onNavigate, books, onOpenBook }: {
  books: ReferenceSetSummary[]; onOpenBook: (key: string) => void;
  featureKey: string; index: ReturnType<typeof indexRules>; rule: Rule; onNavigate: Navigate;
}) {
  const trail = ancestors(index, rule.id);
  const parts = index.children.get(rule.id) ?? [];
  const at = index.order.findIndex(r => r.id === rule.id);
  const prev = index.order[at - 1];
  const next = index.order[at + 1];

  return (
    <div className="space-y-5">
      <div className="as-rise as-glass-strong rounded-2xl p-5 sm:p-6">
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-1 text-[11px] font-semibold text-gray-500">
          <button type="button" onClick={() => onNavigate(featureKey, null)} className="hover:text-hp-blue transition-colors">{featureLabel(featureKey)}</button>
          {trail.map(a => (
            <React.Fragment key={a.id}>
              <ChevronRight className="w-3 h-3 text-gray-300" />
              <button type="button" onClick={() => onNavigate(featureKey, a.id)} className="hover:text-hp-blue transition-colors max-w-[16rem] truncate">{a.name}</button>
            </React.Fragment>
          ))}
          <ChevronRight className="w-3 h-3 text-gray-300" />
          <span className="text-gray-800 max-w-[16rem] truncate">{rule.name}</span>
        </nav>
        <h2 className="mt-3 text-xl font-extrabold text-gray-900 tracking-tight [text-wrap:balance]">{rule.name}</h2>
        <div className="mt-2 flex flex-wrap items-center gap-2"><RuleBadges rule={rule} /></div>
        {!!rule.uses?.length && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <span className="text-[10px] font-bold uppercase tracking-wider text-gray-500 mr-1">Applies rules from</span>
            {rule.uses.map(k => (
              <button key={k} type="button" onClick={() => onOpenBook(k)}
                className="group inline-flex items-center gap-1.5 rounded-full bg-hp-dark text-white pl-2 pr-2.5 py-1 text-[11px] font-semibold shadow-sm hover:bg-hp-blue transition-colors">
                <BookMarked className="w-3.5 h-3.5" />{books.find(b => b.key === k)?.title ?? k}
                <ArrowRight className="w-3 h-3 transition-transform group-hover:translate-x-0.5" />
              </button>
            ))}
          </div>
        )}
        {/* The summary is usually the Purpose's first sentence; say it once. */}
        {rule.summary && !rule.purpose?.startsWith(rule.summary.replace(/\.\.\.$/, '')) && (
          <p className="mt-2 text-[13px] leading-relaxed text-gray-600">{rule.summary}</p>
        )}
      </div>

      <div className="as-rise as-glass-strong rounded-2xl px-5 sm:px-6 py-2" style={{ ['--as-delay' as string]: '60ms' }}>
        <RuleBody rule={rule} />
      </div>

      {parts.length > 0 && (
        <section className="as-rise as-glass rounded-2xl p-5 sm:p-6" style={{ ['--as-delay' as string]: '100ms' }}>
          <h3 className="text-sm font-extrabold text-gray-900">Built from</h3>
          <p className="text-[11px] text-gray-500">The {parts.length} part{parts.length === 1 ? '' : 's'} this rule combines. Select one to read it.</p>
          <div className="mt-4 space-y-2 border-l-2 border-sky-100 pl-3">
            {parts.map((p, i) => (
              <RuleRow key={p.id} rule={p} index={i} partCount={index.children.get(p.id)?.length ?? 0}
                onSelect={() => onNavigate(featureKey, p.id)} />
            ))}
          </div>
        </section>
      )}

      <div className="flex items-stretch justify-between gap-3">
        {prev ? (
          <button type="button" onClick={() => onNavigate(featureKey, prev.id)}
            className="group as-glass rounded-xl px-4 py-3 text-left max-w-[48%] hover:shadow-md transition-shadow">
            <span className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-gray-500"><ArrowLeft className="w-3 h-3" />Previous</span>
            <span className="mt-0.5 block text-[12px] font-semibold text-gray-800 group-hover:text-hp-blue truncate">{prev.name}</span>
          </button>
        ) : <span />}
        {next && (
          <button type="button" onClick={() => onNavigate(featureKey, next.id)}
            className="group as-glass rounded-xl px-4 py-3 text-right max-w-[48%] ml-auto hover:shadow-md transition-shadow">
            <span className="flex items-center justify-end gap-1 text-[10px] font-bold uppercase tracking-wider text-gray-500">Next<ArrowRight className="w-3 h-3" /></span>
            <span className="mt-0.5 block text-[12px] font-semibold text-gray-800 group-hover:text-hp-blue truncate">{next.name}</span>
          </button>
        )}
      </div>
    </div>
  );
}
