'use client';

import ScoreInfo from '@/components/common/ScoreInfo';
import type { ScoreTopic } from '@/lib/scoreExplanations';
import { caseStudyUrl } from '@/lib/caseStudies';
import React, { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/providers/AuthProvider';
import api, { postStream } from '@/services/api';
import { CompanyAccount } from '@/types/account';
import { NORTHSTAR_SIDEBAR_GROUPS } from '@/lib/features';
import { activeAccountFrom, dashboardHref } from '@/lib/accountSelection';
import { NO_SIGNAL, NOT_DISCLOSED } from '@/lib/placeholders';
import { track, stopFeatureTime } from '@/lib/track';
import { MyActivityPanel } from '@/components/analytics/MyActivityPanel';
import { CountUpText, ScoreRing, growDelay, useParallax } from '@/components/common/motion';
import { Activity as ActivityIcon } from 'lucide-react';
import { 
  WidgetResponse, 
  WidgetClassification,
  IntentTopic
} from '@/types/widget';
import { 
  Building2, 
  Search, 
  Loader2, 
  AlertCircle, 
  Database, 
  Layers, 
  Info,
  ChevronDown,
  ArrowUpDown,
  ChevronUp,
  LayoutDashboard,
  Newspaper,
  Users,
  Lightbulb,
  Compass,
  Cpu,
  ShieldAlert,
  Shield,
  FileText,
  Package,
  MessageSquare,
  HelpCircle,
  Award,
  BookOpen,
  CheckSquare,
  Megaphone,
  TrendingUp,
  TrendingDown,
  Sparkles,
  PenTool,
  Star,
  Linkedin,
  Mail,
  Phone,
  Calculator,
  Binary,
  ChevronLeft,
  MapPin,
  Globe,
  User,
  Edit3,
  Play,
  Check,
  Filter,
  Flame,
  Zap,
  Target,
  FileSpreadsheet,
  ExternalLink,
  X,
  ChevronRight,
  RotateCcw,
  Copy,
  Download,
  ShieldCheck,
  UserCheck,
  CheckCircle2,
  Minus,
  BarChart3,
  Briefcase
} from 'lucide-react';

const ICON_MAP: Record<string, React.FC<{ className?: string }>> = {
  LayoutDashboard,
  Newspaper,
  Users,
  Lightbulb,
  Cpu,
  ShieldAlert,
  FileText,
  MessageSquare,
  CheckSquare,
  Megaphone,
  TrendingUp
};






interface ProvenanceEntry {
  field_path: string;
  source: string;
  type: string;
  date: string;
  confidence: string;
  url: string;
}

// Evidence tags, as the model writes them: [a6a997c3b_objection_x#c5], and
// several to a bracket when a sentence rests on more than one source.
//
// Matched as "a bracket containing at least one id", then the ids are pulled
// out of it - rather than as a comma-separated list of ids. The model varies
// the separator run to run: ", " one time, "; " the next, and a bare "c3"
// shorthand a third. Each variant that the pattern did not anticipate rendered
// the whole tag raw in the seller's face. Matching the bracket and extracting
// what is inside it is indifferent to what sits between the ids.
// A citation now names the SECTION of the account payload it came from -
// `[exec_urgency_score]`, `[stakeholder_contacts_grid, stakeholder_influence_map]`
// - rather than a chunk of a retrieval index (`a6a997c3b_objection_a8e9..#c5`).
// Strategy Chat reads the whole account in one pass, so there are no chunks left
// to address.
//
// These two must stay the mirror of `_CITATION_RE` and `_SECTION_KEY_RE` in
// services/strategy/chat.py. When they disagree the backend validates a tag the
// frontend then fails to match, and the answer renders the raw bracket
// mid-sentence - which is exactly what these markers exist to prevent.
//
// The underscore is required, not decorative: without it every bracketed aside
// the model writes - `[see below]`, `[estimated]` - would be read as a citation,
// match nothing, and be silently deleted from the sentence.
const CITATION_BRACKET_RE = /\[[^[\]]*?[a-z][a-z0-9]*(?:_[a-z0-9]+)+[^[\]]*\]/g;
const EVIDENCE_ID_RE = /[a-z][a-z0-9]*(?:_[a-z0-9]+)+/g;

// The source-reliability line on a Live Signal, composed here from the score
// the widget already stores rather than read from the text stored beside it.
//
// This must stay the mirror of `describe_source` in
// services/extractors/signal_scoring.py, and `test_signal_batching.py` pins
// every string below so a change there fails a test rather than showing two
// different lines for the same signal.
//
// Why derive it instead of reading `rationales.source_reliability`: that string
// is composed when the signal is scored and frozen inside the widget, so
// renaming a band would reach an account only when its Live Signals are
// regenerated - which re-runs the Executive Dashboard, its index, the
// opportunity triggers and Strategy Chat's snapshot along with it. The score
// itself never moved, so the name can be resolved at read time and every
// account shows it at once.
//
// The tiers are the client's own (27 Sep): T0 filings and press releases, T1
// established news channels, T2 paid licensed tools, T3 long tail. Unverifiable
// carries no tier - their list defines four - so it falls back to the scoring
// document's own word.
//
// Shown in plain words (client, 6 Oct: no internal terminology): the tier
// codes (T0-T3) and labels like "long tail" are dropped from the screen; the
// bands and scores are unchanged.
// "For this account" in the score ⓘ: the account's own sum, from the numbers
// the widget already carries, so a reader can see how the shown figure is
// reached. Plain labels only - the backend's term names are mapped here.
const fmtNum = (n: any): string =>
  typeof n === 'number' ? String(Math.round(n * 100) / 100) : String(n ?? '');

function urgencyWorked(u: any): string | null {
  const drivers = u?.drivers;
  if (!Array.isArray(drivers) || !drivers.length || u.score == null) return null;
  const exact = u.exact_score ?? u.score;
  const sum = drivers.map((d: any) => `${fmtNum(d.value)} × ${Math.round((d.weight ?? 0) * 100)}%`).join(' + ');
  return `${sum} = ${fmtNum(exact)}${exact !== u.score ? ` → ${u.score}` : ''}`;
}

const MESSAGE_LABELS: Record<string, string> = {
  relevance: 'Relevance', impact: 'Impact', brand_recall: 'Brand recall', clarity: 'Clarity',
  creativity: 'Creativity', emotional_connection: 'Emotional appeal', next_step_strength: 'Call to action',
};

function messageWorked(evaluation: any): string | null {
  const dims = evaluation?.dimensions, weights = evaluation?.dimension_weights;
  if (!dims || !weights || evaluation.composite == null) return null;
  const used = Object.keys(weights).filter((k) => weights[k] && dims[k] != null);
  if (!used.length) return null;
  const sum = used.map((k) => `${MESSAGE_LABELS[k] ?? k} ${fmtNum(dims[k])} × ${Math.round(weights[k] * 100)}%`).join(' + ');
  return `${sum} = ${fmtNum(evaluation.composite)}`;
}

// The ⓘ beside each urgency driver: what goes into it, in plain words.
const DRIVER_INFO: Record<string, ScoreTopic> = {
  workplace_os: 'urgencyWorkplace',
  ai_workstation: 'urgencyAi',
  growth_expansion: 'urgencyGrowth',
  hp_solution_intent: 'urgencyHpIntent',
};

const SOURCE_TIERS: Record<number, string> = {
  10: 'The company’s own announcement or filing',
  8: 'Established news outlet',
  6: 'Business data provider',
  3: 'Smaller or less established site',
  0: 'Source could not be verified',
};

function sourceReliabilityLine(points: unknown, publisher: unknown): string {
  const head = SOURCE_TIERS[Number(points)];
  if (!head) return '';
  const name = String(publisher ?? '').trim();
  return name ? `${head}: ${name}` : head;
}

/**
 * The chat answer with its evidence tags turned into footnote markers.
 *
 * Every factual sentence carries the address of the sentence it came from -
 * that traceability is the feature, and the validator rejects an answer whose
 * tags do not resolve. But a seller should not be reading database keys
 * mid-sentence: `[stakeholder_contacts_grid]` is a database key, not
 * and breaks the line.
 *
 * So the tag becomes a superscript number linking to its row in Sources below,
 * which is where the quoted source sentence already is. The tags stay in the
 * model's output untouched - they are what validation runs on.
 *
 * A tag naming evidence that is not in this answer's citation list is dropped
 * rather than shown: it would be a marker pointing at nothing. That should not
 * happen (validation resolves every tag first), so it is a display guard, not
 * a substitute for the check.
 */
function AnswerWithCitations({ text, citations, idPrefix }:
  { text: string; citations: any[]; idPrefix: string }) {
  const position = new Map<string, number>();
  (citations || []).forEach((c, i) => {
    if (c?.evidence_id) position.set(String(c.evidence_id), i + 1);
  });

  const parts: React.ReactNode[] = [];
  let cursor = 0;
  let key = 0;
  for (const match of Array.from(text.matchAll(CITATION_BRACKET_RE))) {
    const at = match.index ?? 0;
    if (at > cursor) parts.push(text.slice(cursor, at));
    const numbers = (match[0].match(EVIDENCE_ID_RE) || [])
      .map(id => position.get(id))
      .filter((n): n is number => typeof n === 'number');
    if (numbers.length > 0) {
      parts.push(
        <sup key={`c${key++}`} className="ml-0.5">
          {numbers.map((n, i) => (
            <span key={n}>
              {i > 0 && <span className="text-slate-400">,</span>}
              <a
                href={`#${idPrefix}-src-${n}`}
                title="Jump to this source"
                className="text-hp-navy no-underline hover:underline font-bold px-0.5"
              >
                {n}
              </a>
            </span>
          ))}
        </sup>
      );
    }
    cursor = at + match[0].length;
  }
  if (cursor < text.length) parts.push(text.slice(cursor));

  return <p className="text-xs leading-relaxed whitespace-pre-wrap">{parts}</p>;
}

// A case study attached to a recommendation that already stands on its own
// evidence. Added 24 Sep for the three places the client named: Live Signals'
// Implication for HP, Intent's So What for HP, and the Technographic Map's what
// it means for HP - "nowhere else". It strengthens a recommendation and never
// creates one, so it renders below the prose rather than inside it.
function ProofPoint({ proof }: { proof: any }) {
  const ctx = React.useContext(AccountIdContext);
  if (!proof?.text) return null;
  const href = openableUrl(proof.source_url, ctx);
  return (
    <div className="bg-amber-50/60 border border-amber-200 rounded-xl px-3 py-2 space-y-1 mt-2">
      <span className="text-[9px] font-mono font-extrabold uppercase tracking-widest text-amber-800 block">
        HP proof point
      </span>
      <p className="text-[11px] text-amber-900 leading-relaxed">{proof.text}</p>
      {(proof.customer || proof.source_url) && (
        <p className="text-[10px] text-amber-800">
          {proof.customer && <span className="font-semibold">{proof.customer}</span>}
          {proof.industry && <span className="text-amber-700"> &middot; {proof.industry}</span>}
          {href && (
            <>
              {' · '}
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-amber-950"
              >
                View the HP case study
              </a>
            </>
          )}
        </p>
      )}
    </div>
  );
}

// Client ruling, 24 Sep, on what to show when a dataset is missing: "leave it
// out, do not write anything as of now". They asked us to stay flexible because
// the decision is still with Sahaj, so this is one flag rather than deleted
// code - flip it back to true and every empty state returns exactly as it was.
const SHOW_EMPTY_STATE_NOTICES = false;

// A widget that never generated stores the reason on its payload. Showing it
// turns an unexplained empty panel into something a reader can act on - most
// often a missing OPENAI_API_KEY, or source files absent from this machine.
function PendingNotice({ widget, title }: { widget: any; title: string }) {
  const notice = widget?.data?.notice;
  if (!SHOW_EMPTY_STATE_NOTICES) return null;
  if (!widget || widget.status === 'available' || !notice) return null;
  return (
    <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
      <Sparkles className="w-4 h-4 text-amber-600 mt-0.5 shrink-0" />
      <div className="space-y-0.5">
        <p className="text-xs font-bold uppercase tracking-wider text-amber-900">{title}</p>
        <p className="text-xs leading-relaxed text-amber-800">{notice}</p>
      </div>
    </div>
  );
}

// Which account's files a source chip may open, and which of its filings can
// actually be opened. Supplied once around the dashboard rather than threaded
// through every evidence list, because the chip is rendered from six different
// places and none of them is near the account state.
//
// The default is empty on purpose: a chip rendered outside the provider, or
// before the manifest answers, is plain text rather than a link that might not
// work. It fails in the safe direction.
//
// `unreachable` is this account's links the link check found do not open
// (`scripts/check_evidence_links.py`). Empty until it answers, so a link shows
// until it is known to be dead - an unchecked link is far more often fine.
interface SourceLinkContext { accountId: string; filings: Set<string>; unreachable: Set<string> }
const NO_LINKS: SourceLinkContext =
  { accountId: '', filings: new Set<string>(), unreachable: new Set<string>() };
const AccountIdContext = React.createContext<SourceLinkContext>(NO_LINKS);

// A link worth showing: present, not known dead, and not one of HP's retired
// case studies. '' otherwise - and a source with no openable link is not
// shown at all (client, 7 Oct).
//
// A retired case study we hold our own copy of is swapped for that copy FIRST:
// its old address is recorded as dead by the link check, and testing that
// address would hide the copy we serve.
function openableUrl(url: unknown, ctx?: SourceLinkContext): string {
  const raw = String(url ?? '').trim();
  if (!raw) return '';
  const u = caseStudyUrl(raw) || '';
  if (!u || (ctx || NO_LINKS).unreachable.has(u)) return '';
  return u;
}

// Two evidence rows from the same unlinked source are one chip. A row that
// links somewhere keeps its own, since the links genuinely go to different
// places. The count is shown so collapsing never hides how much evidence
// there was.
//
// Keyed on what identifies the source rather than on the built link, so this
// needs no account id. Two pages of one filing have different labels
// ("…annual_report.pdf p.11" / "p.14") and stay separate chips, which is right:
// they open at different places.
function dedupeSources(sources: any[]) {
  const byKey = new Map<string, any>();
  (sources || []).forEach((s: any) => {
    const ident = s.filing_label || s.resolved_source_url || s.resolved_url
      || s.source_url || s.url || '';
    const key = `${s.label}::${ident}`;
    const seen = byKey.get(key);
    if (seen) { seen.count = (seen.count || 1) + 1; }
    else { byKey.set(key, { ...s, count: 1 }); }
  });
  return Array.from(byKey.values());
}

// Our own copy of a filing, opened at the page the evidence cites.
//
// `filing_label` is the registered upload filename, which is what the backend
// matches on - so a link built here needs nothing added to any stored widget.
// `#page=` is honoured by every browser's built-in PDF viewer.
function filingHref(ctx: SourceLinkContext, s: any): string {
  const name = String(s?.filing_label || '').trim();
  // Only a filing the backend confirms it can serve. `filing_label` was true of
  // the corpus when the widget was built, not necessarily now - a re-uploaded
  // filing leaves its old row replaced, and a filing can be registered on an
  // account whose PDF is not on this machine. Linking from the label alone
  // opened a tab containing a 404 in both cases.
  if (!ctx.accountId || !name || !ctx.filings.has(name)) return '';
  const accountId = ctx.accountId;
  const base = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const token = typeof window !== 'undefined'
    ? (localStorage.getItem('hp_token') || '') : '';
  const url = `${base}/api/v1/accounts/${accountId}/data/filing`
    + `?name=${encodeURIComponent(name)}&token=${encodeURIComponent(token)}`;
  const page = Number(s?.page);
  return Number.isFinite(page) && page > 0 ? `${url}#page=${page}` : url;
}

// The link for a source row, or '' when it has none.
//
// Order: our own copy of the filing, then the company's public URL, then plain
// text. Our copy wins because of the filing URLs the crawl attempted, 24% failed
// or returned something that was not a document, and a public URL cannot open at
// page 11. But when we have no openable copy, the public `source_url` part one
// put on these rows is still something we HAVE, so it is offered rather than
// dropped - and when there is neither, the source is not shown.
//
// For everything else, `resolved_source_url` is preferred where it exists - a
// Live Signal's raw `source_url` is often a news.google.com redirect. A link the
// link check found dead, or an HP case study HP has retired, counts as no link:
// a dead link is worse than none. The redirect is not tried in its place - it
// leads to the same retired article.
function sourceHref(s: any, ctx?: SourceLinkContext): string {
  const filing = filingHref(ctx || NO_LINKS, s);
  if (filing) return filing;
  return openableUrl(s?.resolved_source_url || s?.resolved_url
                     || s?.source_url || s?.url, ctx);
}

// What a chip reads when the row names no source of its own. The link's host is
// real - it is where the click goes - where the word "Source" was a placeholder
// standing in for information we actually hold.
function hostLabel(href: string): string {
  try {
    return new URL(href).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

// A source, as provenance rather than a bare identifier: the exact evidence_id
// stays in the tooltip so a claim is still traceable to the registry row
// behind it.
//
// Client, 6 Oct: wherever evidence is shown the source should be clickable, so
// a seller can verify the claim before sending it. Client, 7 Oct: a source with
// no link, or with a link that does not open, is not shown at all - much of this
// evidence is a cell in an uploaded CSV, and a grey name with nothing to open
// behind it read as a broken link.
function SourceChip({ s, tone = 'emerald' }: { s: any; tone?: 'emerald' | 'slate' }) {
  const ctx = React.useContext(AccountIdContext);
  const href = sourceHref(s, ctx);
  if (!href) return null;
  const detail = s.quote
    ? `${s.field ? s.field + ' — ' : ''}"${s.quote}"`
    : String(s.source_text || '').slice(0, 180);
  // Named by the source, else by where the link goes.
  const name = s.label || s.publisher || hostLabel(href);
  if (!name) return null;
  const label = `${name}${s.count > 1 ? ` (${s.count})` : ''}`;
  const linkedClass = tone === 'slate'
    ? 'border-blue-200 bg-blue-50 text-hp-navy hover:bg-blue-100'
    : 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:bg-emerald-100';
  return (
    <span
      title={[s.evidence_id, detail].filter(Boolean).join(' — ') || undefined}
      className={`inline-flex max-w-full items-center gap-1 rounded-full border px-2 py-[3px] text-[10px] font-semibold align-middle ${linkedClass}`}
    >
      <FileText className="w-2.5 h-2.5 flex-shrink-0" />
      <a href={href} target="_blank" rel="noopener noreferrer"
         className="truncate hover:underline">{label}</a>
      <ExternalLink className="w-2.5 h-2.5 flex-shrink-0" />
    </span>
  );
}

// The sources among `sources` that would render - for a caller that heads a
// list with a count, or that should vanish when nothing in it can be opened.
function linkedSources(sources: any[], ctx?: SourceLinkContext): any[] {
  return (sources || []).filter((s: any) => {
    const href = sourceHref(s, ctx);
    return href && (s.label || s.publisher || hostLabel(href));
  });
}

// One HP recommendation, rendered to match the vendor cards it sits beneath.
// The product, the confidence and the approved facts are all decided in Python;
// this only lays them out.
function HpRecommendationCard({ rec, xray }: { rec: any; xray?: boolean }) {
  return (
    <div className="bg-indigo-50/40 border border-indigo-100 rounded-2xl p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-indigo-100 pb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-indigo-600">
            HP Recommendation
          </span>
          {/* A Part B rule names its own HP line ("HP Wolf Security"); a Part A
              rule names a family that reads as "HP Elite". Prefixing the line
              would print "HP HP Wolf Security". */}
          <span className="text-xs font-black text-slate-900">
            {rec.hp_line || `HP ${rec.hp_family}`}
          </span>
          {rec.offering && rec.offering !== rec.hp_line && (
            <span className="text-[11px] font-semibold text-slate-600">{rec.offering}</span>
          )}
          {rec.device_type && (
            <span className="text-[10px] uppercase tracking-wider bg-white text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
              {rec.device_type}
            </span>
          )}
          {/* The fit band (Confirmed / Likely / Discovery) and evidence label
              (Opportunity / Conversation Starter / Context Only) were removed
              from the card at the client's request (6 Oct). */}
        </div>
        {/* Section 3: "Do not expose internal rule IDs ... Seller-facing
            output should contain the conclusion, not the backend logic." The
            id is how an engineer traces the card back to the rulebook, so it
            stays - behind X-Ray, with the rest of the machinery. */}
        {xray && (
          <span className="text-[10px] font-mono text-slate-400 whitespace-nowrap">
            Rule {rec.rule_id}
          </span>
        )}
      </div>

      {rec.rationale && (
        <p className="text-xs text-slate-700 leading-relaxed">{rec.rationale}</p>
      )}
      {rec.why_this_product && (
        <p className="text-xs text-slate-600 leading-relaxed">{rec.why_this_product}</p>
      )}

      {(rec.approved_facts || []).length > 0 && (() => {
        /* A deck fact carries its OWN footnote, so printing it under each one
           is right. A rulebook fact carries the RULE's conditions, which are
           the same for every fact of that rule - printed per fact they
           repeated the same sentence six times under one recommendation.
           Shared conditions are lifted out and shown once; anything specific
           to a single fact still sits under it. */
        /* All of them, not the first six. The cap upstream is eight
           (MAX_FACTS_PER_RECOMMENDATION), and truncating here meant the prose
           cited "up to 128GB DDR5" and "up to 11 native USB ports" - both
           approved, both facts 7 and 8 - while the reader could not see them. */
        const facts = rec.approved_facts || [];
        const conditionLists = facts.map((f: any) => (f.conditions || []));
        const shared = (conditionLists[0] || []).filter((c: string) =>
          conditionLists.length > 1 && conditionLists.every((list: string[]) => list.includes(c)));
        return (
          <div className="bg-white border border-slate-100 rounded-xl p-3 space-y-1.5">
            <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-slate-500 block">
              HP facts approved for this account
            </span>
            {facts.map((f: any, i: number) => {
              const own = (f.conditions || []).filter((c: string) => !shared.includes(c));
              return (
                <div key={i} className="text-xs text-slate-700">
                  <span>&bull; {f.text}</span>
                  {own.length > 0 && (
                    <span className="block text-[10px] text-slate-500 ml-3 mt-0.5 leading-snug">
                      {own[0]}
                    </span>
                  )}
                </div>
              );
            })}
            {shared.length > 0 && (
              <p className="text-[10px] text-slate-500 leading-snug pt-1.5 border-t border-slate-100">
                <span className="font-semibold">Applies to all of the above: </span>
                {shared.join(' ')}
              </p>
            )}
          </div>
        );
      })()}

      {/* Gap reason lives in the backend (data_gaps); the client sees neutral wording. */}

      {rec.discovery_question && (
        <p className="text-xs text-slate-600 italic border-l-2 border-indigo-200 pl-3">
          {rec.discovery_question}
        </p>
      )}

      {/* Which of the account's files earned this card.
          A recommendation in PC/Laptop Brands can be fired by a job ad - HP's
          own signal for rule 1 is "Enterprise AI / local AI ... AI hiring" -
          and a category header reading "0 detected signals" would otherwise
          make that card look unexplained, or worse, look like a detection.

          One line by default. The first version printed the raw cells, which
          on this account meant 300 characters of an Indonesian job posting
          under every card - true, and unreadable. The cells themselves are
          worth having when someone is checking the work, so they moved behind
          X-Ray with the rest of the provenance view. */}
      {(rec.fired_by_datasets || []).length > 0 && (
        <div className="border-t border-indigo-100 pt-2 space-y-1">
          <p className="text-[11px] text-slate-600 leading-snug">
            <span className="font-semibold">Earned by </span>
            {(rec.matched_tokens || []).join(', ') || 'this account’s evidence'}
            <span className="text-slate-400">
              {' '}&mdash; from {(rec.fired_by_datasets || []).join(', ')}
            </span>
          </p>

          {xray && (rec.account_evidence || []).length > 0 && (
            <div className="space-y-1 pt-1">
              {rec.account_evidence.map((e: any, i: number) => (
                <p key={i} className="text-[10px] text-slate-500 leading-snug">
                  <span className="font-mono text-slate-400">
                    {e.dataset}{e.field ? ` → ${e.field}` : ''}
                  </span>
                  <span className="block pl-1 line-clamp-2">{e.text}</span>
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function UserDashboardPage() {
  const { user, logout } = useAuth();
  const router = useRouter();
  // The sidebar's light layer drifts with the pointer, like the header bands.
  const sidebarRef = useRef<HTMLElement>(null);
  useParallax(sidebarRef);

  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [selectedAccount, setSelectedAccount] = useState<CompanyAccount | null>(null);
  const [activeFeatureKey, setActiveFeatureKey] = useState<string>('executive_dashboard');
  
  const [widgets, setWidgets] = useState<WidgetResponse[]>([]);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [isLoadingWidgets, setIsLoadingLoadingWidgets] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // X-Ray (provenance / debug view) is kept off: the client asked for the
  // toggle to be removed (issue list v3). The views it gates stay in the code.
  const isXRayOn = false;
  const [provenanceSearch, setProvenanceSearch] = useState('');
  const [provenanceSourceFilter, setProvenanceSourceFilter] = useState('ALL');

  // Urgency Score Driver Popover & Tooltip State

  // Key Metrics Source Citation Popover State
  const [activeMetricPopover, setActiveMetricPopover] = useState<string | null>(null);
  const [expandedPriority, setExpandedPriority] = useState<number | null>(null);

  // Live Signals Filter Drawer State
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);
  const [dateRangeFilter, setDateRangeFilter] = useState('All time');
  const [signalTypes, setSignalTypes] = useState<Set<string>>(new Set());
  const [minSignalScore, setMinSignalScore] = useState(0);
  const [expandedSignalId, setExpandedSignalId] = useState<string | null>(null);
  const [expandedSignalDetailId, setExpandedSignalDetailId] = useState<string | null>(null);
  // Which signal is listing the other articles it was merged from. Collapsed by
  // default: a signal merged from five reports should not print five chips
  // unprompted.
  const [expandedSignalSourcesId, setExpandedSignalSourcesId] = useState<string | null>(null);
  // The filings this account has an openable copy of, by registered filename.
  // Empty until the manifest answers, so a chip starts plain and becomes a link
  // rather than starting as a link that might not work.
  const [filingsAvailable, setFilingsAvailable] = useState<Set<string>>(new Set());
  // This account's evidence links known not to open; those sources are hidden.
  const [unreachableLinks, setUnreachableLinks] = useState<Set<string>>(new Set());
  // Memoised: a fresh object on every render would re-render every source chip
  // on the screen, and this component renders a lot.
  const sourceLinkCtx = useMemo(
    () => ({ accountId: selectedAccount?.id || '', filings: filingsAvailable,
             unreachable: unreachableLinks }),
    [selectedAccount?.id, filingsAvailable, unreachableLinks]);
  const [expandedObjectionId, setExpandedObjectionId] = useState<string | null>(null);

  // Intent Topics Filter State
  const [intentSearch, setIntentSearch] = useState('');
  const [intentScoreFilter, setIntentScoreFilter] = useState('ALL');
  const [intentSort, setIntentSort] = useState<'score' | 'name'>('score');
  const [isOtherTopicsExpanded, setIsOtherTopicsExpanded] = useState(false);
  const [hoveredBarTopic, setHoveredBarTopic] = useState<{ name: string; score: number } | null>(null);
  const [hoveredIntentCat, setHoveredIntentCat] = useState<string | null>(null);

  // Stakeholder Map Filter State. Influence, priority and HP relevance are no
  // longer filterable - the client dropped all three on 27 Sep as scoring we
  // cannot defend - and the Entry Path sub-tab went with them.
  const [stakeholderSearch, setStakeholderSearch] = useState('');
  const [stakeholderDeptFilter, setStakeholderDeptFilter] = useState('ALL');
  const [stakeholderSeniorityFilter, setStakeholderSeniorityFilter] = useState('ALL');
  const [expandedDepts, setExpandedDepts] = useState<Record<string, boolean>>({});
  const [expandedContacts, setExpandedContacts] = useState<Record<string, boolean>>({});
  const [revealedContacts, setRevealedContacts] = useState<Record<string, boolean>>({});

  // Tech Landscape Filter & Sub-Tab State
  // Intent theme groups start collapsed (Sahaj, 27 Sep).
  const [expandedIntentThemes, setExpandedIntentThemes] = useState<Record<string, boolean>>({});
  const [opportunitiesOnly, setOpportunitiesOnly] = useState(false);
  const [techSearch, setTechSearch] = useState('');
  const [techCategoryFilter, setTechCategoryFilter] = useState('ALL');
  // The two technology accordions keep no open/closed state here. They are
  // native <details>, so the browser owns it and a click on the row always
  // works - the React-state version did not respond at all on this panel,
  // and nothing in this file explained why. <details> removes the question:
  // there is no handler to miss and no state to lose.
  // Technographic Map stack view filters (Caterpillar-style layout, Sahaj 27 Sep).
  const [stackFamilyFilter, setStackFamilyFilter] = useState<string>('ALL');
  const [stackSourceFilter, setStackSourceFilter] = useState<string>('ALL');
  const [stackHpOnly, setStackHpOnly] = useState<boolean>(false);

  // Content Studio State
  const [selectedPersona, setSelectedPersona] = useState<string>('cio_it');
  const [selectedContentType, setSelectedContentType] = useState<string>('email');
  const [selectedTopic, setSelectedTopic] = useState<string>('Z by HP Workstations');
  const [customTopic, setCustomTopic] = useState<string>('');
  const [additionalContext, setAdditionalContext] = useState<string>('');
  const [isGeneratingContent, setIsGeneratingContent] = useState<boolean>(false);
  const [hasGeneratedContent, setHasGeneratedContent] = useState<boolean>(false);
  const [generatedAsset, setGeneratedAsset] = useState<any>(null);
  // Which LinkedIn variant is on screen (1-based, matching variant_index).
  const [activeVariantIndex, setActiveVariantIndex] = useState<number>(1);
  const [generateError, setGenerateError] = useState<any>(null);
  const [copiedAssetId, setCopiedAssetId] = useState<string | null>(null);
  const [isGeneratingOppMap, setIsGeneratingOppMap] = useState<boolean>(false);

  // Strategy Chat State
  //
  // `chatPersonaId` empty means the advisor. Anything else is a rehearsal
  // against that stakeholder's ROLE - the list is the account's own roster,
  // served live by the backend, and is empty for an account with no contacts.
  const [chatInput, setChatInput] = useState<string>('');
  const [chatPersonaId, setChatPersonaId] = useState<string>('');
  const [chatPersonas, setChatPersonas] = useState<any[]>([]);
  // `personaTitle` is stamped on each message rather than read from the current
  // selection, so a bubble keeps saying who said it after the selector moves.
  // `text` is what the seller reads - prose with [section] tags the footnote
  // renderer turns into markers. `clean` is the same prose without them, for
  // copying, emailing and the history posted back to the model. They are kept
  // apart deliberately: a tag is presentation, and nothing downstream of the
  // screen should ever see one.
  const [chatMessages, setChatMessages] = useState<Array<{ id: string; sender: 'user' | 'assistant'; text: string; clean?: string; timestamp: string; citations?: any[]; available?: boolean; personaTitle?: string; dropped?: number }>>([]);
  const [chatPending, setChatPending] = useState(false);
  // Which stage of the answer is running. An answer takes around fifteen
  // seconds and cannot be streamed - every fact is validated against the
  // evidence before any of it is shown, so text that appeared as it was
  // written could be retracted a paragraph later. What can be shown honestly
  // is which step is running, which is what this drives.
  const [chatStage, setChatStage] = useState<number>(0);
  // The validated answer so far, while it is still being written. Every value
  // this holds has already passed the same check the finished answer passes -
  // the server releases text only as far as its last resolved citation - so
  // rendering it does not show the seller anything unverified.
  const [chatStreamingText, setChatStreamingText] = useState<string>('');
  const [copiedMessageId, setCopiedMessageId] = useState<string | null>(null);

  // Message Evaluator State
  // Defaults are empty: the objective, format and persona vocabularies are
  // served by the backend, so hardcoding a starting value here would pin the UI
  // to a string the scoring formulas may not recognise.
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>('');
  const [selectedObjective, setSelectedObjective] = useState<string>('');
  const [selectedFormat, setSelectedFormat] = useState<string>('');
  const [evaluatorMode, setEvaluatorMode] = useState<string>('DEEP');
  const [evalOptions, setEvalOptions] = useState<any>(null);
  const [evalHistory, setEvalHistory] = useState<any[]>([]);
  const [evaluation, setEvaluation] = useState<any>(null);
  const [isEvaluating, setIsEvaluating] = useState<boolean>(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [selectedRecs, setSelectedRecs] = useState<string[]>([]);
  const [isRewriting, setIsRewriting] = useState<boolean>(false);
  const [rewriteError, setRewriteError] = useState<string | null>(null);
  const [stimulusText, setStimulusText] = useState<string>('');
  const [copiedRewrite, setCopiedRewrite] = useState<boolean>(false);
  const [evaluatorStep, setEvaluatorStep] = useState<string>('inputs');

  // Content Messaging
  const [expandedPillar, setExpandedPillar] = useState<string | null>(null);
  const [retrievalStatus, setRetrievalStatus] = useState<any>(null);

  // Whether an answer is current, stale, or unavailable mid-rebuild is a fact
  // about the index, not about the widget - so it is read from the retrieval
  // layer rather than inferred from the widget's own timestamp.
  useEffect(() => {
    if (!selectedAccountId) return;
    if (!['content_messaging'].includes(activeFeatureKey || '')) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<any>(`/accounts/${selectedAccountId}/retrieval/status`);
        if (!cancelled) setRetrievalStatus(res.data);
      } catch {
        if (!cancelled) setRetrievalStatus(null);
      }
    })();
    return () => { cancelled = true; };
  }, [activeFeatureKey, selectedAccountId]);

  // Which filings this account actually has an openable copy of.
  //
  // An evidence row's `filing_label` was true of the corpus when the widget was
  // built, not necessarily now: a re-uploaded filing leaves its old row
  // `replaced`, and a filing can be registered on an account whose PDF is not on
  // this machine. Linking optimistically from the label alone opened a tab
  // containing a 404 in both cases, and a dead link is worse than plain text.
  //
  // Fails soft to an empty set, like the two fetches above: no filings known
  // means no filing links, which degrades to the public URL or to plain text -
  // never to a broken one.
  useEffect(() => {
    if (!selectedAccountId) { setFilingsAvailable(new Set()); return; }
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<any>(`/accounts/${selectedAccountId}/data/filings`);
        if (cancelled) return;
        setFilingsAvailable(new Set<string>(
          (res.data?.filings || []).map((f: any) => String(f.filename))));
      } catch {
        if (!cancelled) setFilingsAvailable(new Set());
      }
    })();
    return () => { cancelled = true; };
  }, [selectedAccountId]);

  // Which of this account's links the link check found dead. Fails soft to an
  // empty set: the links then show as they did before the check existed.
  useEffect(() => {
    if (!selectedAccountId) { setUnreachableLinks(new Set()); return; }
    let cancelled = false;
    (async () => {
      try {
        const res = await api.get<any>(`/accounts/${selectedAccountId}/data/unreachable-links`);
        if (cancelled) return;
        setUnreachableLinks(new Set<string>(
          (res.data?.unreachable || []).map((u: any) => String(u))));
      } catch {
        if (!cancelled) setUnreachableLinks(new Set());
      }
    })();
    return () => { cancelled = true; };
  }, [selectedAccountId]);

  // Objectives, formats and personas come from the evaluator endpoints so the
  // dropdowns cannot drift from the scoring formulas that consume them.
  useEffect(() => {
    if (activeFeatureKey !== 'message_evaluator' || !selectedAccountId) return;
    let cancelled = false;
    (async () => {
      try {
        const [opts, hist] = await Promise.all([
          api.get<any>(`/accounts/${selectedAccountId}/widgets/message_evaluator/options`),
          api.get<any>(`/accounts/${selectedAccountId}/widgets/message_evaluator/history`),
        ]);
        if (cancelled) return;
        setEvalOptions(opts.data);
        setEvalHistory(hist.data?.evaluations || []);
      } catch {
        if (!cancelled) setEvalOptions({ objectives: [], formats: [], personas: [], modes: ['LITE', 'DEEP'] });
      }
    })();
    return () => { cancelled = true; };
  }, [activeFeatureKey, selectedAccountId]);

  const [isEvaluatorInfoOpen, setIsEvaluatorInfoOpen] = useState<boolean>(false);

  // Account search filter in dropdown
  const [accountSearch, setAccountSearch] = useState('');
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Fetch Active Accounts for User Account Switcher
  const fetchUserAccounts = useCallback(async () => {
    setIsLoadingAccounts(true);
    setError(null);
    try {
      const response = await api.get<CompanyAccount[]>('/accounts/user-list');
      setAccounts(response.data);
      // The active account is the one in the URL, put there by the Account
      // Selection screen or the dropdown below - which is what lets it survive
      // a refresh. Read from window.location rather than useSearchParams, which
      // would need a Suspense boundary for one parameter. With no account, or
      // one that is no longer active, send the seller to choose one rather
      // than opening whichever account sorts first.
      const match = activeAccountFrom(response.data, window.location.search);
      if (match) {
        setSelectedAccountId(match.id);
        setSelectedAccount(match);
      } else {
        router.replace('/accounts');
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load accessible account list.';
      setError(msg);
    } finally {
      setIsLoadingAccounts(false);
    }
  }, [router]);

  // Fetch Widget Contracts for Selected Account + Feature
  const fetchWidgetContracts = useCallback(async (accId: string, featureKey: string) => {
    if (!accId) return;
    setIsLoadingLoadingWidgets(true);
    try {
      const response = await api.get<WidgetResponse[]>(`/accounts/${accId}/widgets/${featureKey}`);
      setWidgets(response.data);
    } catch {
      // The api client logs the failure (method, path, status, request_id);
      // the client sees the panels' neutral wording, never a load error.
      setWidgets([]);
    } finally {
      setIsLoadingLoadingWidgets(false);
    }
  }, []);

  useEffect(() => {
    fetchUserAccounts();
  }, [fetchUserAccounts]);

  // Usage analytics: one feature_view each time the seller lands on a feature
  // (or on a new account within it), starting with the first feature shown
  // once the account list has loaded. track() only queues - it never blocks or
  // fails navigation. The ref drops the duplicate StrictMode's double effect
  // run would otherwise send.
  const lastTrackedView = useRef('');
  useEffect(() => {
    // No account means the page is on its way back to Account Selection; a
    // view recorded now would count a dashboard the seller never saw.
    if (isLoadingAccounts || !selectedAccountId) return;
    const key = `${activeFeatureKey}|${selectedAccountId}`;
    if (key === lastTrackedView.current) return;
    lastTrackedView.current = key;
    track({ event: 'feature_view', feature_key: activeFeatureKey, account_id: selectedAccountId || null });
  }, [activeFeatureKey, selectedAccountId, isLoadingAccounts]);
  // Time on a feature stops counting once the dashboard is gone.
  useEffect(() => () => stopFeatureTime(), []);

  const [isMyActivityOpen, setIsMyActivityOpen] = useState(false);
  const closeMyActivity = useCallback(() => setIsMyActivityOpen(false), []);

  useEffect(() => {
    if (selectedAccountId) {
      fetchWidgetContracts(selectedAccountId, activeFeatureKey);
    }
  }, [selectedAccountId, activeFeatureKey, fetchWidgetContracts]);

  // Changing account ends the conversation. ABX Feature 8: "Validate follow-up
  // questions against conversation account scope; changing accounts must
  // invalidate prior retrieved context." Carrying turns across would let a
  // follow-up resolve "that" against the previous account's answer.
  useEffect(() => {
    setChatMessages([]);
    setChatInput('');
    setChatPersonaId('');
  }, [selectedAccountId]);

  // Who this account's seller can rehearse against. Served live rather than
  // read from a widget: the strategy_chat extractor does not depend on
  // prospect_contacts, so a widget copy would go stale at exactly the moment a
  // new roster was uploaded. Empty list is a valid answer - an account with no
  // contacts gets no personas rather than a default set of roles.
  // The persona roster is no longer fetched: the chat is advisor-only, so
  // nothing reads it and the request was one more round trip every time the
  // tab opened. The endpoint is still there and still tested; restoring the
  // picker means restoring this effect with it.

  const handleSelectAccount = (acc: CompanyAccount) => {
    setSelectedAccountId(acc.id);
    setSelectedAccount(acc);
    setIsDropdownOpen(false);
    // Keep the URL on the active account so a refresh reopens this one.
    router.replace(dashboardHref(acc.id), { scroll: false });
  };

  const getDownloadUrl = (datasetKey: string) => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const token = typeof window !== 'undefined' ? (localStorage.getItem('hp_token') || '') : '';
    return `${baseUrl}/api/v1/accounts/${selectedAccount?.id}/data/download/${datasetKey}?token=${encodeURIComponent(token)}`;
  };

  // Features the client asked not to show for this account (backend
  // config/account_overrides.yaml, sent on the account as hidden_features).
  const hiddenFeatures = useMemo(
    () => new Set(selectedAccount?.hidden_features ?? []),
    [selectedAccount?.hidden_features]);
  const sidebarGroups = useMemo(
    () => NORTHSTAR_SIDEBAR_GROUPS
      .map(g => ({ ...g, items: g.items.filter(i => !hiddenFeatures.has(i.key)) }))
      .filter(g => g.items.length > 0),
    [hiddenFeatures]);
  // Switching to an account that hides the open feature lands on the dashboard.
  useEffect(() => {
    if (hiddenFeatures.has(activeFeatureKey)) setActiveFeatureKey('executive_dashboard');
  }, [hiddenFeatures, activeFeatureKey]);

  const allItems = sidebarGroups.flatMap(g => g.items);
  const activeFeatureDef = allItems.find(f => f.key === activeFeatureKey) || allItems[0];

  const getClassificationBadge = (cls: WidgetClassification) => {
    switch (cls) {
      case 'deterministic':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-100 text-hp-blue border border-blue-200">
            <Binary className="w-3 h-3 mr-1" />
            Deterministic
          </span>
        );
      case 'derived':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-100 text-amber-800 border border-amber-200">
            <Calculator className="w-3 h-3 mr-1" />
            Derived
          </span>
        );
      case 'inferred':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-100 text-purple-800 border border-purple-200">
            <Sparkles className="w-3 h-3 mr-1" />
            Inferred
          </span>
        );
    }
  };

  const filteredAccounts = accounts.filter(a => 
    a.name.toLowerCase().includes(accountSearch.toLowerCase().trim())
  );

  // Provenance map table data generator
  const getProvenanceEntries = (): ProvenanceEntry[] => {
    if (!selectedAccount) return [];
    return [
      { field_path: 'company_name', source: '1_firmographics.csv (Company Name)', type: 'Firmographics', date: '2026-09-04', confidence: '95%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'domain', source: '1_firmographics.csv (Company Domain)', type: 'Firmographics', date: '2026-09-04', confidence: '95%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'business_description', source: '1_firmographics.csv (Business Description)', type: 'Firmographics', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'industry_classification', source: '1_firmographics.csv (NAICS, SIC, LinkedIn)', type: 'Firmographics', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'hq_location', source: '1_firmographics.csv (City, Region, Country)', type: 'Firmographics', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'employee_count', source: '1_firmographics.csv (Number Of Employees Range)', type: 'Firmographics', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'revenue', source: '1_firmographics.csv (Yearly Revenue Range)', type: 'Firmographics', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/firmographics/firmographics.csv' },
      { field_path: 'company_hierarchy', source: '2_company_hierarchy.csv (Parent Company Name)', type: 'Hierarchy', date: '2026-09-04', confidence: '90%', url: 'data/accounts/' + selectedAccount.id + '/company_hierarchy/company_hierarchy.csv' },
      { field_path: 'job_postings', source: 'job_openings.csv (Last 12 months, account country only, open and closed)', type: 'Job Openings', date: '2026-09-04', confidence: '85%', url: 'data/accounts/' + selectedAccount.id + '/job_openings/job_openings.csv' },
      { field_path: 'liveSignals', source: 'google_news_rss_data.csv + news_events.csv', type: 'Google News', date: '2026-09-04', confidence: '80%', url: 'data/accounts/' + selectedAccount.id + '/google_news/google_news_rss_data.csv' },
      { field_path: 'technology_stack', source: '4_technographics.csv (Full Tech Stack)', type: 'Technographics', date: '2026-09-04', confidence: '85%', url: 'data/accounts/' + selectedAccount.id + '/technographics/technographics.csv' },
      { field_path: 'intentTopics', source: '11_intent_score.csv (Composite Score)', type: 'Bombora', date: '2026-09-04', confidence: '80%', url: 'data/accounts/' + selectedAccount.id + '/intent_score/intent_score.csv' }
    ];
  };

  const provenanceEntries = getProvenanceEntries();
  const filteredProvenanceEntries = provenanceEntries.filter(entry => {
    const matchesSearch = entry.field_path.toLowerCase().includes(provenanceSearch.toLowerCase().trim()) ||
                          entry.source.toLowerCase().includes(provenanceSearch.toLowerCase().trim());
    const matchesSource = provenanceSourceFilter === 'ALL' || entry.type.toLowerCase().includes(provenanceSourceFilter.toLowerCase());
    return matchesSearch && matchesSource;
  });

  return (
    <ProtectedRoute allowedRoles={['user', 'admin']}>
      {/* Which account's filings an evidence chip may open. Empty while no
          account is selected, which makes filingHref return '' and the chip
          render flat - the correct behaviour, not a broken link. */}
      <AccountIdContext.Provider value={sourceLinkCtx}>
      <div className="flex h-screen bg-[#F8FAFC] overflow-hidden text-slate-800 font-sans">
        
        {/* ============================================================================== */}
        {/* LEFT FIXED SIDEBAR — NORTHSTAR EXACT LAYOUT                                    */}
        {/* ============================================================================== */}
        <aside 
          ref={sidebarRef}
          className={`relative bg-[#0B132B] text-white flex flex-col justify-between transition-all duration-300 z-50 flex-shrink-0 border-r border-slate-800/80 ${
            isSidebarCollapsed ? 'w-16' : 'w-64'
          }`}
        >
          <div className="as-side-glow absolute -inset-6 pointer-events-none" aria-hidden />
          <div className="relative flex flex-col h-full overflow-hidden">
            
            {/* Top Brand Header */}
            <div className="p-4 flex items-center space-x-3 border-b border-slate-800/80">
              <div className="w-8 h-8 bg-hp-navy text-white rounded-lg flex items-center justify-center font-extrabold text-sm tracking-wider shadow-md flex-shrink-0">
                HP
              </div>
              {!isSidebarCollapsed && (
                <div>
                  <h1 className="text-sm font-bold text-white leading-tight tracking-tight">HP</h1>
                  <p className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                    Account Intelligence
                  </p>
                </div>
              )}
            </div>

            {/* Target Account Selector Section */}
            {!isSidebarCollapsed && (
              <div className="p-3 border-b border-slate-800/80">
                <div className="flex items-center justify-between mb-1.5 px-1">
                  <span className="text-[9px] font-extrabold text-gray-400 uppercase tracking-widest">
                    Target Account
                  </span>
                  <button
                    type="button"
                    onClick={() => router.push('/accounts')}
                    className="text-[10px] font-bold text-hp-accent hover:underline"
                  >
                    All accounts
                  </button>
                </div>

                <div className="relative">
                  <button
                    type="button"
                    disabled={isLoadingAccounts || accounts.length === 0}
                    onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                    className="as-glass-dark w-full flex items-center justify-between p-2.5 hover:bg-white/5 text-white rounded-xl transition text-left text-xs font-bold disabled:opacity-50"
                  >
                    <div className="flex items-center space-x-2.5 truncate">
                      <div className="p-1.5 bg-slate-800 text-hp-accent rounded-lg">
                        <Building2 className="w-4 h-4" />
                      </div>
                      <div className="truncate">
                        <span className="truncate block text-xs font-bold text-white">
                          {isLoadingAccounts 
                            ? 'Loading accounts...' 
                            : selectedAccount 
                            ? selectedAccount.name 
                            : 'No target accounts'}
                        </span>
                        <span className="text-[10px] font-normal text-gray-400 block font-mono">
                          {selectedAccount ? `ID: ${selectedAccount.id.substring(0, 8)}...` : 'N/A'}
                        </span>
                      </div>
                    </div>
                    <ChevronDown className="w-4 h-4 text-gray-400 flex-shrink-0 ml-1" />
                  </button>

                  {/* Dropdown Menu */}
                  {isDropdownOpen && (
                    <div className="animate-fade-in as-glass-dark absolute left-0 mt-2 w-full rounded-xl z-50 overflow-hidden">
                      <div className="p-2 border-b border-slate-800">
                        <div className="relative">
                          <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2.5" />
                          <input
                            type="text"
                            autoFocus
                            value={accountSearch}
                            onChange={(e) => setAccountSearch(e.target.value)}
                            placeholder="Search company..."
                            className="w-full pl-8 pr-2 py-1 bg-[#0B132B] text-xs text-white rounded-lg focus:outline-none focus:ring-1 focus:ring-hp-navy placeholder-gray-500"
                          />
                        </div>
                      </div>

                      <div className="max-h-52 overflow-y-auto divide-y divide-slate-800 text-xs">
                        {filteredAccounts.length === 0 ? (
                          <div className="p-3 text-center text-gray-400">No active accounts</div>
                        ) : (
                          filteredAccounts.map((acc) => (
                            <button
                              key={acc.id}
                              type="button"
                              onClick={() => handleSelectAccount(acc)}
                              className={`w-full text-left px-3 py-2.5 hover:bg-slate-800 transition flex items-center justify-between ${
                                acc.id === selectedAccountId ? 'bg-hp-navy/20 text-hp-accent font-bold' : 'text-gray-200 font-medium'
                              }`}
                            >
                              <span className="truncate">{acc.name}</span>
                              {acc.id === selectedAccountId && (
                                <span className="w-1.5 h-1.5 rounded-full bg-hp-accent ml-2"></span>
                              )}
                            </button>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Vertical Navigation Groups (INTELLIGENCE, ACTION, SIMULATION & PLANNING) */}
            <div className="flex-1 overflow-y-auto p-2 space-y-4 no-scrollbar">
              {sidebarGroups.map((group) => (
                <div key={group.sectionTitle} className="space-y-1">
                  {!isSidebarCollapsed && (
                    <span className="text-[9px] font-extrabold text-gray-400 uppercase tracking-widest px-2.5 pt-2 block">
                      {group.sectionTitle}
                    </span>
                  )}

                  {group.items.map((item) => {
                    const IconComp = ICON_MAP[item.iconName] || LayoutDashboard;
                    const isActive = item.key === activeFeatureKey;

                    return (
                      <button
                        key={item.key}
                        type="button"
                        onClick={() => setActiveFeatureKey(item.key)}
                        title={item.label}
                        className={`w-full flex items-center space-x-3 px-2.5 py-2 rounded-xl transition text-left ${
                          isActive
                            ? 'bg-[#1C2541] text-white border-l-4 border-hp-accent font-bold shadow-md'
                            : 'text-gray-300 hover:text-white hover:bg-slate-800/60 font-medium'
                        }`}
                      >
                        <IconComp className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-hp-accent' : 'text-gray-400'}`} />
                        {!isSidebarCollapsed && (
                          <div className="truncate">
                            <span className="text-xs block truncate leading-tight">{item.label}</span>
                            <span className="text-[10px] text-gray-400 font-normal block truncate leading-tight">
                              {item.subtitle}
                            </span>
                          </div>
                        )}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>

            {/* Bottom Footer User Info & Collapse Toggle */}
            <div className="p-3 border-t border-slate-800/80 bg-[#0B132B] flex items-center justify-between">
              {!isSidebarCollapsed && (
                <div className="flex items-center space-x-2 truncate">
                  <div className="w-7 h-7 bg-slate-800 text-hp-accent rounded-full flex items-center justify-center font-bold text-xs">
                    {user?.full_name?.substring(0, 1) || 'U'}
                  </div>
                  <div className="truncate text-xs">
                    <span className="font-bold text-gray-200 block truncate">{user?.full_name}</span>
                    <button onClick={logout} className="text-[10px] text-red-400 hover:underline">
                      Sign Out
                    </button>
                  </div>
                </div>
              )}

              <button
                onClick={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
                className="p-1.5 text-gray-400 hover:text-white rounded-lg bg-slate-800/60 hover:bg-slate-800 transition ml-auto"
                title={isSidebarCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar'}
              >
                <ChevronLeft className={`w-4 h-4 transition-transform ${isSidebarCollapsed ? 'rotate-180' : ''}`} />
              </button>
            </div>

          </div>
        </aside>

        {/* ============================================================================== */}
        {/* RIGHT MAIN CONTENT AREA                                                        */}
        {/* ============================================================================== */}
        <div className="flex-1 flex flex-col h-screen overflow-hidden">
          
          {/* Top Status Bar (Northstar Header) */}
          <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between flex-shrink-0 shadow-xs">
            <div className="flex items-center space-x-3">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <h2 className="text-base font-extrabold text-slate-900 tracking-tight">
                {selectedAccount ? selectedAccount.name : 'Select Target Account'}
              </h2>
              <span className="text-[10px] font-bold bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-mono uppercase border border-slate-200">
                ACTIVE
              </span>

              {/* Urgency Score Pill
                *
                * Bound to the same exec_urgency_score widget as the breakdown
                * card below, so the two can never disagree. This previously
                * read a hardcoded "Contract TBD" - a placeholder that outlived
                * the contract question and sat next to a card that was already
                * computing the real number.
                *
                * `widgets` holds only the active feature's widgets, so this
                * resolves on the executive dashboard and renders nothing
                * elsewhere rather than showing a stale or empty score. Read on
                * 'partial' too, matching the card: a payload whose composite is
                * blocked by one unavailable driver shows the neutral placeholder.
                */}
              {(() => {
                const urgencyWidget = widgets.find(w => w.widget_key === 'exec_urgency_score');
                const urgency = (urgencyWidget && urgencyWidget.data
                  && (urgencyWidget.status === 'available' || urgencyWidget.status === 'partial'))
                  ? (urgencyWidget.data as any) : null;

                if (!urgency) return null;

                // Withheld below the 60% coverage gate: no tag at all, rather
                // than a "No signal" one (client, 8 Oct).
                if (urgency.score == null) return null;
                return (
                  <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full border text-xs font-bold bg-amber-50 text-amber-800 border-amber-200/80">
                    <span className="text-[11px]">Urgency Score</span>
                    <span className="px-1.5 py-0.5 rounded font-mono text-[10px] bg-amber-200 text-amber-900">
                      <CountUpText text={urgency.score} />/{urgency.max_score ?? 100}
                    </span>
                    <ScoreInfo topic="urgency" align="right" worked={urgencyWorked(urgency)} />
                  </div>
                );
              })()}
            </div>

            {/* When the ACCOUNT DATA was loaded - not when this page was opened,
                and not when the widget was last generated. Recommendation
                Tuning Logic section E: a dashboard opened months after
                ingestion must still name the snapshot it is reasoning from.

                Executive Dashboard only (client, 6 Oct). This header is shared
                by every feature, so the tag used to sit beside each feature's
                own dating - next to Intent's "as of", which is Bombora's
                observation date, not an ingestion date - and the two read as a
                contradiction. One tag, in one place, measuring one thing.

                The value itself never varied by feature: the API attaches the
                same account-wide map to every widget. This changes where it is
                shown, not what it says. */}
            {activeFeatureKey === 'executive_dashboard' && (() => {
              // Client ruling, 24 Sep: show the retrieval date of the data
              // itself, not one rolled-up date for the account. Each dataset
              // is named with the day it was loaded; where every pipeline
              // arrived together this collapses back to a single date.
              const spread: Record<string, string> =
                widgets.find(w => w.data_as_of)?.data_as_of?.by_dataset || {};
              const days = Array.from(new Set(Object.values(spread))).sort();
              if (!days.length) return null;
              const byDay = days.map(day => ({
                day,
                sets: Object.keys(spread).filter(k => spread[k] === day).sort(),
              }));
              return (
                <span
                  className="text-[10px] font-mono text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 whitespace-nowrap"
                  title={byDay
                    .map(({ day, sets }) => `${day}: ${sets.join(', ')}`)
                    .join('\n')}
                >
                  {days.length === 1
                    ? `Data as of ${days[0]}`
                    : `Data as of ${days[0]} – ${days[days.length - 1]}`}
                  {days.length > 1 && (
                    <span className="text-slate-400"> &middot; {Object.keys(spread).length} sources</span>
                  )}
                </span>
              );
            })()}

            {/* My Activity: the seller's own usage. Admin activity is not
                tracked, so there is nothing to show an admin here. */}
            {user?.role !== 'admin' && (
              <button
                type="button"
                onClick={() => setIsMyActivityOpen(true)}
                className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs bg-white text-slate-700 border-slate-300 hover:bg-slate-50"
              >
                <ActivityIcon className="w-3.5 h-3.5 text-hp-navy" />
                <span>My Activity</span>
              </button>
            )}

          </header>

          {/* Main Dashboard Canvas Scroll Area */}
          <main className="flex-1 overflow-y-auto p-8 space-y-6">
            
            {error && (
              <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-r-lg flex items-center space-x-2 text-red-800 text-xs font-semibold">
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {!selectedAccount ? (
              <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm">
                <Building2 className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                <h3 className="text-base font-bold text-slate-800">No Target Account Selected</h3>
                <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                  Please select an active target company account from the left sidebar to view intelligence feature widgets.
                </p>
              </div>
            ) : (
              // Keyed on feature, account and load state, so each switch - and
              // the moment its data arrives - settles in rather than snapping.
              <div
                key={`${activeFeatureKey}|${selectedAccountId}|${isLoadingWidgets ? 'loading' : 'ready'}`}
                className="space-y-6 as-feature-in"
              >
                
                {/* Provenance Map Explorer Table when X-Ray ON */}
                {isXRayOn && selectedAccount && (
                  <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4 animate-fade-in">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                      <div>
                        <h3 className="text-base font-extrabold text-slate-900 flex items-center gap-2">
                          <Database className="w-5 h-5 text-hp-navy" />
                          <span>All Data Sources & Lineage</span>
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Provenance map for {selectedAccount.name} — Field paths, dataset sources, dates, and confidence ratings
                        </p>
                      </div>

                      <span className="text-xs font-bold text-hp-navy bg-blue-50 px-3 py-1 rounded-full border border-blue-200 self-start sm:self-auto">
                        X-Ray Mode Active
                      </span>
                    </div>

                    {/* Provenance Filters */}
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                      <div className="relative flex-1 max-w-md">
                        <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-2.5" />
                        <input
                          type="text"
                          value={provenanceSearch}
                          onChange={(e) => setProvenanceSearch(e.target.value)}
                          placeholder="Search field path or source..."
                          className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy"
                        />
                      </div>

                      <div className="flex flex-wrap items-center gap-2">
                        <Filter className="w-3.5 h-3.5 text-slate-400 mr-1" />
                        <select
                          value={provenanceSourceFilter}
                          onChange={(e) => setProvenanceSourceFilter(e.target.value)}
                          className="px-3 py-1.5 bg-slate-50 border border-slate-300 rounded-lg text-xs font-semibold text-slate-700 focus:outline-none"
                        >
                          <option value="ALL">All Source Types</option>
                          <option value="Firmographics">Firmographics (1_Firmographics)</option>
                          <option value="Hierarchy">Hierarchy (2_Company_Hierarchy)</option>
                          <option value="Technographics">Technographics (4_Technographics)</option>
                          <option value="Bombora">Intent</option>
                          <option value="Google News">Google News RSS</option>
                          <option value="Job Openings">Hiring</option>
                        </select>
                      </div>
                    </div>

                    {/* Lineage Table */}
                    <div className="overflow-x-auto rounded-xl border border-slate-200">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-slate-50 border-b border-slate-200 font-extrabold uppercase tracking-wider text-[10px] text-slate-600">
                            <th className="py-3 px-4">Field Path</th>
                            <th className="py-3 px-4">Source</th>
                            <th className="py-3 px-4">Type</th>
                            <th className="py-3 px-4">Date</th>
                            <th className="py-3 px-4">Confidence</th>
                            <th className="py-3 px-4">File Path / Reference</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-200 font-medium">
                          {filteredProvenanceEntries.map((entry, idx) => (
                            <tr key={idx} className="hover:bg-slate-50 transition">
                              <td className="py-3 px-4 font-mono font-bold text-slate-800">{entry.field_path}</td>
                              <td className="py-3 px-4 text-slate-600">{entry.source}</td>
                              <td className="py-3 px-4">
                                <span className="px-2 py-0.5 rounded font-bold text-[10px] bg-slate-100 text-slate-700 border border-slate-200">
                                  {entry.type}
                                </span>
                              </td>
                              <td className="py-3 px-4 text-slate-500 font-mono">{entry.date}</td>
                              <td className="py-3 px-4 font-bold text-emerald-700">{entry.confidence}</td>
                              <td className="py-3 px-4 font-mono text-hp-navy text-[11px] truncate max-w-xs">{entry.url}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}

                {/* ============================================================================== */}
                {/* EXECUTIVE DASHBOARD VIEW — EXACT NORTHSTAR 5 SECTIONS                          */}
                {/* ============================================================================== */}
                {activeFeatureKey === 'executive_dashboard' && (() => {
                  const summaryWidget = widgets.find(w => w.widget_key === 'exec_summary_card');
                  const metricsWidget = widgets.find(w => w.widget_key === 'exec_key_metrics');
                  const hiringWidget = widgets.find(w => w.widget_key === 'hiring_postings_summary');
                  const prioritiesWidget = widgets.find(w => w.widget_key === 'exec_strategic_priorities');
                  const urgencyWidget = widgets.find(w => w.widget_key === 'exec_urgency_score');

                  // Read on 'partial' too. A urgency payload whose composite is
                  // blocked by one unavailable driver still carries the four
                  // that computed, and the card's job in that state is to name
                  // the blocker - which needs the data, not an empty card.
                  const urgencyData = (urgencyWidget && urgencyWidget.data
                    && (urgencyWidget.status === 'available' || urgencyWidget.status === 'partial'))
                    ? urgencyWidget.data : null;

                  const summaryData = (summaryWidget && summaryWidget.status === 'available' && summaryWidget.data) ? summaryWidget.data : null;
                  const metricsData = (metricsWidget && metricsWidget.status === 'available' && metricsWidget.data) ? metricsWidget.data : null;
                  const hiringData = (hiringWidget && hiringWidget.status === 'available' && hiringWidget.data) ? hiringWidget.data : null;
                  const prioritiesData = (prioritiesWidget && prioritiesWidget.status === 'available' && prioritiesWidget.data) ? prioritiesWidget.data : null;

                  // The company write-up as bullets, reorganised from the
                  // same paragraph at extraction time. Empty when the
                  // paragraph was too short to break up or the bullets failed
                  // their figure check, and then the paragraph is shown.
                  const descPoints: string[] = (summaryData?.business_description_points || []) as string[];

                  // Figures the company actually filed, as opposed to the
                  // firmographic bands beside them. Each carries its own period,
                  // unit and page, so the card can say where it came from.
                  const reportedMetrics: any[] = (metricsData?.reported_metrics || prioritiesData?.reported_metrics || []) as any[];
                  // A band the vendor did not supply is a box with nothing in it (Sahaj 1.c).
                  const isBand = (v: any) => !!v && !['n/a', 'na', 'none', '-', ''].includes(String(v).trim().toLowerCase());
                  const hasEmployeeBand = isBand(metricsData?.employee_count);
                  const hasRevenueBand = isBand(metricsData?.revenue);
                  const bandCount = (hasEmployeeBand ? 1 : 0) + (hasRevenueBand ? 1 : 0);
                  const priorityList: any[] = (prioritiesData?.priorities || []) as any[];

                  const displayName = summaryData?.company_name || selectedAccount.name;
                  const displayDesc = summaryData?.business_description || NOT_DISCLOSED;
                  const domainVal = summaryData?.domain || null;
                  const locationVal = summaryData?.hq_location || null;
                  const industryVal = summaryData?.industry_classification || null;
                  // Client, 5 Oct: the parent is the hierarchy sheet's column E
                  // (column C where E is the account itself) and the
                  // subsidiaries are column A of the Subsidiaries sheet, both as
                  // supplied. Blank means hidden, not shown as missing.
                  // Client, 7 Oct: its corrected parent where it gave one, and
                  // a company can have two (direct and ultimate) - both shown.
                  const parentsVal: string[] = summaryData?.parent_companies
                    || (summaryData?.parent_company ? [summaryData.parent_company] : []);
                  const parentVal = parentsVal.length ? parentsVal.join(' · ') : null;
                  const subsidiariesVal: string[] = summaryData?.subsidiaries || [];
                  // Feature 1's header CEO, read from the newest filing naming one.
                  const ceoVal: any = metricsData?.ceo || null;

                  return (
                    <div className="space-y-6">
                      
                      {/* Section 1: Executive Summary Company Profile Card */}
                      <div className="bg-white rounded-2xl p-8 border border-slate-200 shadow-sm">
                        <div className="flex items-start space-x-5">
                          {/* Clean Building SVG Icon Box (Matching Northstar Image 1) */}
                          <div className="w-16 h-16 bg-slate-100 border border-slate-200 text-slate-600 rounded-2xl flex items-center justify-center flex-shrink-0">
                            <Building2 className="w-8 h-8 text-slate-600" />
                          </div>

                          <div className="flex-1 space-y-3">
                            <div className="flex items-center space-x-3">
                              <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                                {displayName}
                              </h2>
                            </div>

                            {/* The profile, as bullets where we have them. */}
                            {descPoints.length > 0 ? (
                              <ul className="space-y-1 max-w-5xl">
                                {descPoints.map((point, i) => (
                                  <li key={i} className="text-xs text-slate-600 leading-relaxed flex gap-2">
                                    <span className="text-hp-navy flex-shrink-0">&bull;</span>
                                    <span>{point}</span>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className={`text-xs leading-relaxed max-w-5xl ${summaryData?.business_description ? 'text-slate-600' : 'text-slate-400'}`}>
                                {displayDesc}
                              </p>
                            )}

                            <div className="flex flex-wrap items-center gap-4 text-xs font-medium text-slate-500 pt-3 border-t border-slate-100">
                              {domainVal && (
                                <a
                                  href={domainVal.startsWith('http') ? domainVal : `https://${domainVal}`}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="flex items-center space-x-1.5 text-hp-navy font-bold hover:underline"
                                >
                                  <Globe className="w-4 h-4 text-hp-navy" />
                                  <span>{domainVal}</span>
                                </a>
                              )}
                              
                              {locationVal && (
                                <div className="flex items-center space-x-1.5 text-slate-700">
                                  <MapPin className="w-4 h-4 text-hp-navy" />
                                  <span>{locationVal}</span>
                                </div>
                              )}

                              {industryVal && (
                                <div className="flex items-start space-x-1.5 text-slate-700">
                                  <Building2 className="w-4 h-4 text-hp-navy shrink-0 mt-0.5" />
                                  <span className="break-words">{industryVal}</span>
                                </div>
                              )}

                              {ceoVal?.name && (
                                <div className="flex items-center space-x-1.5 text-slate-700" title={`${ceoVal.title} · ${ceoVal.filing_label || ceoVal.source}`}>
                                  <User className="w-4 h-4 text-hp-navy" />
                                  <span>CEO: <strong className="font-bold text-slate-900">{ceoVal.name}</strong></span>
                                </div>
                              )}

                              {parentVal && (
                                <div className="flex items-center space-x-1.5 text-slate-700" title={summaryData?.parent_company_source || undefined}>
                                  <Building2 className="w-4 h-4 text-hp-navy" />
                                  <span>{parentsVal.length > 1 ? 'Parent Companies' : 'Parent Company'}: <strong className="font-bold text-slate-900 capitalize">{parentVal}</strong></span>
                                </div>
                              )}
                            </div>

                            {/* Subsidiaries: the first few inline, the rest one click away. */}
                            {subsidiariesVal.length > 0 && (
                              <details className="group text-xs text-slate-700">
                                <summary className="as-summary flex items-start gap-1.5 cursor-pointer list-none">
                                  <Layers className="w-4 h-4 text-hp-navy shrink-0 mt-0.5" />
                                  <span className="min-w-0">
                                    <span className="font-medium text-slate-500">Subsidiaries ({subsidiariesVal.length}): </span>
                                    <span className="capitalize text-slate-900 font-semibold">
                                      {subsidiariesVal.slice(0, 5).join(' · ')}
                                    </span>
                                    {subsidiariesVal.length > 5 && (
                                      <span className="text-hp-navy font-bold group-open:hidden"> +{subsidiariesVal.length - 5} more</span>
                                    )}
                                  </span>
                                </summary>
                                {subsidiariesVal.length > 5 && (
                                  <div className="mt-2 ml-5 flex flex-wrap gap-1.5">
                                    {subsidiariesVal.slice(5).map((s, i) => (
                                      <span key={`${s}-${i}`} className="capitalize px-2 py-0.5 rounded bg-slate-100 text-slate-700">{s}</span>
                                    ))}
                                  </div>
                                )}
                              </details>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Section 3: KEY METRICS GRID
                          Laid out as in the northstar dashboard: a dense grid of
                          small cards, each with its label, the figure, its
                          period-on-period move, a tier badge and a source chip.

                          Two kinds of card sit in this grid and the difference
                          is deliberate and visible. A FILED card is a number the
                          company reported, carrying its own reporting period,
                          unit and page. A BAND card is a bucket a data vendor
                          assigned. Presenting a band as though it were a filed
                          figure is exactly the confusion ABX's pre-display check
                          exists to prevent, so the badge names which it is. */}
                      <div className="space-y-3">
                        <div className="flex items-center space-x-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
                            KEY METRICS
                          </h3>
                          {/* Provenance is stated once, quietly, instead of a
                              coloured pill on every card. The figures are what
                              the eye should land on. */}
                          <span className="text-[10px] text-slate-400">
                            {[reportedMetrics.length > 0 ? `${reportedMetrics.length} from filings` : '',
                              bandCount > 0 ? `${bandCount} firmographic band${bandCount === 1 ? '' : 's'}` : '']
                              .filter(Boolean).join(' · ')}
                          </span>
                        </div>

                        <div className="as-stagger grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">

                          {/* The firmographic bands. Kept first and labelled as
                              bands so the contrast with the filed figures is
                              immediate rather than buried in a tooltip. */}
                          {/* Sahaj 1.c: a box with no data is dropped, not shown as N/A. */}
                          {hasEmployeeBand && (
                            <div className="as-lift relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                              <span className="text-[11px] text-slate-500 block">Total Employees</span>
                              <span className="text-lg font-semibold text-slate-900 leading-tight">
                                <CountUpText text={metricsData?.employee_count} />
                              </span>
                              <span className="text-[10px] text-slate-400">Band · Firmographics</span>
                            </div>
                          )}

                          {hasRevenueBand && (
                            <div className="as-lift relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                              <span className="text-[11px] text-slate-500 block">Yearly Revenue Range</span>
                              <span className="text-lg font-semibold text-slate-900 leading-tight">
                                <CountUpText text={metricsData?.revenue} />
                              </span>
                              <span className="text-[10px] text-slate-400">Band · Firmographics</span>
                            </div>
                          )}

                          {/* Job postings - a count, not a band. Read from the Hiring Signals
                              output (hiring_postings_summary): account country, last 12 months, open and closed. */}
                          {hiringData && hiringData.job_postings > 0 && (
                            <div className="as-lift relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                              <span className="text-[11px] text-slate-500 block">Job postings (last 12 months)</span>
                              <span className="text-lg font-semibold text-slate-900 leading-tight">
                                <CountUpText text={hiringData.job_postings} />
                              </span>
                              <span className="text-[10px] text-slate-400">Count · Job postings</span>
                            </div>
                          )}

                          {/* Every figure the account actually filed. */}
                          {reportedMetrics.map((m: any, i: number) => (
                            <div key={m.evidence_id || i} className="as-lift relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                              <div className="flex items-start justify-between gap-1">
                                <span className="text-[11px] text-slate-500 block leading-snug" title={`${m.metric} (${m.period})`}>
                                  {m.period} {m.metric}
                                </span>
                                {/* The arrow carries the direction in colour -
                                    it is the one place a glance should pick up
                                    a signal - while everything else on the card
                                    stays quiet. */}
                                {m.direction === 'up' && <TrendingUp className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />}
                                {m.direction === 'down' && <TrendingDown className="w-3.5 h-3.5 text-rose-600 flex-shrink-0" />}
                              </div>

                              <span className="text-lg font-semibold text-slate-900 leading-tight break-words">
                                <CountUpText text={m.value_text} />
                                {m.change_text && (
                                  <span className={`ml-1.5 text-[11px] font-normal ${m.direction === 'up' ? 'text-emerald-700' : m.direction === 'down' ? 'text-rose-700' : 'text-slate-500'}`}>
                                    {m.change_text}
                                  </span>
                                )}
                              </span>

                              <div className="flex items-center gap-1 text-[10px] text-slate-400">
                                <span>Filed ·</span>
                                <button
                                  type="button"
                                  onClick={() => setActiveMetricPopover(activeMetricPopover === `rep${i}` ? null : `rep${i}`)}
                                  className="inline-flex items-center gap-1 text-slate-500 hover:text-hp-navy hover:underline transition min-w-0"
                                >
                                  <span className="truncate max-w-[6rem]">p.{m.page}</span>
                                </button>
                              </div>

                              {activeMetricPopover === `rep${i}` && (
                                <div className="absolute left-0 bottom-full mb-2 w-80 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs">
                                  <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                      REPORTED FIGURE &middot; COMPANY FILING
                                    </span>
                                  </div>
                                  <p className="text-slate-700 leading-relaxed">
                                    <strong>{m.metric}</strong> for <strong>{m.period}</strong>: {m.value_text}
                                  </p>
                                  {m.change_text && (
                                    <p className="text-[10px] text-slate-600 mt-1.5">
                                      {m.change_text} against {m.previous_period} ({m.previous_value_text}). {m.change_basis}.
                                    </p>
                                  )}
                                  {m.series?.length > 1 && (
                                    <p className="text-[10px] text-slate-500 mt-1.5">
                                      {m.series.map((s: any) => `${s.period} ${s.value_text}`).join('  ·  ')}
                                    </p>
                                  )}
                                  <p className="text-[10px] text-slate-500 mt-2">
                                    {m.filing_label}{m.page ? `, page ${m.page}` : ''}
                                  </p>
                                  {/* fallback_note / entity_note are gap reasons; they live in
                                      the backend (data_gaps) and are not shown to the client. */}
                                  {m.quote && (
                                    <p className="text-[10px] text-slate-500 mt-2 border-t border-slate-100 pt-2 break-words">
                                      <span className="font-bold text-slate-600">Row as printed: </span>{m.quote}
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}


                        </div>

                        {reportedMetrics.length > 0 && (
                          <p className="text-[10px] text-slate-400 leading-relaxed">
                            Filed figures are what {displayName} reported, each with its reporting period, unit and page.
                            Band figures are buckets assigned by a data vendor, not reported values.
                            A period-on-period move is shown only where the earlier period was itself reported.
                          </p>
                        )}
                      </div>

                      {/* Section 4: URGENCY SCORE
                          Quick Stats sat beside this in a three-column grid
                          until the client dropped it on 27 Sep ("most figures
                          in the Quick Stats are empty - let's drop this all
                          together for all accounts"), so the card is now the
                          full width rather than two thirds of a row with a
                          hole in it. */}
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                              <Flame className="w-4 h-4 text-amber-500" />
                              <span>URGENCY SCORE & DRIVER BREAKDOWN</span>
                            </h3>
                            {/* The formula's provenance badge was removed at the
                                client's request (refinements, 6 Oct). */}
                          </div>

                          <div className="flex flex-col sm:flex-row items-center gap-6">
                            {/* The ring fills to the score on the same clock the
                                number counts on. Below the client's 60% coverage
                                gate there is no score, and no ring: the client
                                asked (8 Oct) for the "No signal" circle to go
                                rather than stand in for a number. */}
                            {urgencyData?.score != null && (
                              <div className="relative w-24 h-24 rounded-full flex flex-col items-center justify-center flex-shrink-0 shadow-inner bg-amber-50/50">
                                <ScoreRing value={urgencyData.score} max={urgencyData.max_score ?? 100}
                                  className="stroke-amber-400" trackClassName="stroke-amber-100" />
                                <span className="font-extrabold text-3xl text-slate-800">
                                  <CountUpText text={urgencyData.score} />
                                </span>
                                <span className="text-[10px] font-bold text-slate-400">/100</span>
                              </div>
                            )}

                            <div className="flex-1 w-full space-y-3 text-xs">
                              {(urgencyData?.drivers ?? [])
                                // Withheld score (below the 60% gate): a driver
                                // with nothing behind it shows an empty bar, so
                                // it is left out (client, 8 Oct).
                                .filter((d: any) => urgencyData?.score != null || Number(d.value) > 0)
                                .map((d: any) => {
                                  // A component with no input on file scores 0
                                  // under the client's missing-input rule and
                                  // is shown like any other 0: the client asked
                                  // (1 Oct) for no partial-data flag on the card.
                                  return {
                                  id: d.key,
                                  label: d.label,
                                  available: d.available,
                                  scoreText: `${d.value}/100`,
                                  value: d.value,
                                  terms: d.terms,
                                  progressPct: `${d.value}%`,
                                  barColor: 'bg-hp-navy',
                                };
                                }).map((driver: any, driverIdx: number) => (
                                <div key={driver.id} className="relative">
                                  <div className="flex justify-between items-center font-bold text-slate-700 text-[11px] mb-1">
                                    <div className="flex items-center space-x-1.5">
                                      <span className={driver.available ? '' : 'text-slate-400'}>{driver.label}</span>

                                      {DRIVER_INFO[driver.id] && <ScoreInfo topic={DRIVER_INFO[driver.id]} />}
                                    </div>

                                    <span className="font-mono text-slate-500 font-bold"><CountUpText text={driver.scoreText} first delay={growDelay(driverIdx)} /></span>
                                  </div>

                                  {/* Progress Bar */}
                                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                                    <div className={`as-grow ${driver.barColor} h-2 rounded-full transition-all duration-500`} style={{ width: driver.progressPct, ['--as-d' as string]: `${growDelay(driverIdx)}ms` }}></div>
                                  </div>

                                </div>
                              ))}

                              {!urgencyData && (
                                <p className="text-[11px] text-slate-400 leading-relaxed">
                                  The urgency score has not been computed for this account yet.
                                </p>
                              )}
                            </div>
                          </div>

                          {/* The arithmetic, shown adding up. The contributions
                              printed here are the same figures the API
                              publishes and they sum to the headline score, so a
                              reader checking the column by hand reaches the
                              number on the dial rather than a near miss. */}
                          {/* Not for a withheld score: the sum would print the
                              total the gate holds back. */}
                          {urgencyData && urgencyData.score != null && urgencyData.weighted_contributions && (
                            <p className="text-[10px] text-slate-500 font-mono leading-relaxed border-t border-slate-100 pt-3">
                              {(urgencyData.drivers ?? [])
                                .map((d: any) =>
                                  `${d.value} × ${Math.round(d.weight * 100)}% = ${
                                    urgencyData.weighted_contributions[d.key]}`)
                                .join('  +  ')}
                              {'  =  '}
                              <span className="font-bold text-slate-700">
                                {urgencyData.exact_score ?? urgencyData.score}
                              </span>
                              {urgencyData.exact_score != null
                                && urgencyData.exact_score !== urgencyData.score
                                && ` → ${urgencyData.score} rounded`}
                            </p>
                          )}

                          {/* The formula and its source document used to be
                              printed here. The ⓘ in the header explains the score
                              in plain language instead (client, 6 Oct). */}
                        </div>

                      {/* Section 5: STRATEGIC PRIORITIES
                          Catalyst cards grouped by theme, as in the northstar
                          dashboard: a numbered card per priority, its evidence
                          line, its source chips, and an expandable panel
                          carrying the underlying claims.

                          One deliberate difference. The northstar prints an
                          EVIDENCE STRENGTH out of 100 above those four bars.
                          ABX weights that score - 40% support frequency, 25%
                          supporting document sections, 20% recency, 15%
                          independent external sources - but never defines how
                          any of the four counts becomes a number on a scale.
                          Rendering 65/100 would mean inventing four
                          normalisations and attributing the result to the
                          specification. So the same four measures are shown as
                          the counts they actually are, and the composite says
                          it is undefined. */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-5">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Target className="w-4 h-4 text-hp-navy" />
                            <span>STRATEGIC PRIORITIES</span>
                            <ScoreInfo topic="catalysts" />
                          </h3>
{/* Guarded on the COUNT, not on the list: catalysts with no
                              sources rendered "0 primary sources", which is a
                              statement about something we do not have. */}
                          {(() => {
                            const n = priorityList.reduce(
                              (t: number, p: any) => t + (p.sources?.length || 0), 0);
                            if (!n) return null;
                            return (
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-hp-navy border border-blue-200 inline-flex items-center gap-1">
                                <FileText className="w-3 h-3" />
                                {n} primary source{n === 1 ? '' : 's'}
                              </span>
                            );
                          })()}
                        </div>

                        {/* The executive summary is no longer rendered here - it
                            restated what the cards below already say. It is
                            still assembled and stored on the widget, because ABX
                            Feature 1 lists it as required output and Strategy
                            Chat will read it; it simply has no place at the top
                            of a list it duplicates. */}

                        {priorityList.length > 0 ? (
                          <div className="space-y-6">
                            {Array.from(new Set(priorityList.map((p: any) => p.theme || 'other'))).map((theme: any) => {
                              const group = priorityList.filter((p: any) => (p.theme || 'other') === theme);
                              return (
                                <div key={theme} className="space-y-3">
                                  {/* Theme divider, as in the northstar layout */}
                                  <div className="flex items-center gap-3">
                                    <div className="h-px bg-slate-200 flex-1" />
                                    <span className="text-[10px] font-extrabold uppercase tracking-widest text-slate-400 whitespace-nowrap">
                                      {theme}
                                    </span>
                                    <div className="h-px bg-slate-200 flex-1" />
                                  </div>

                                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 items-start">
                                    {group.map((p: any) => {
                                      const idx = priorityList.indexOf(p);
                                      const open = expandedPriority === idx;
                                      return (
                                        <div key={idx} className="border border-slate-200 rounded-xl p-4 space-y-3 hover:border-slate-300 transition">
                                          <div className="flex items-start gap-3">
                                            <span className="w-6 h-6 rounded-full bg-blue-50 text-hp-navy border border-blue-200 text-[11px] font-extrabold flex items-center justify-center flex-shrink-0 mt-0.5">
                                              {idx + 1}
                                            </span>
                                            <div className="space-y-2 min-w-0 flex-1">
                                              <h4 className="text-sm font-extrabold text-slate-900 leading-snug">
                                                Catalyst {idx + 1} &ndash; {p.title}
                                              </h4>
                                            </div>
                                            {/* The score on the face of the
                                                card, so catalysts can be
                                                compared without opening four
                                                drawers. The working stays in
                                                the drawer. */}
                                            {p.evidence_strength && (
                                              p.evidence_strength.zero_reason ? (
                                                /* Gap reason lives in the backend (data_gaps); the client sees neutral wording. */
                                                <span className="text-[10px] font-medium text-slate-400 flex-shrink-0 whitespace-nowrap">
                                                  {NO_SIGNAL}
                                                </span>
                                              ) : (
                                                <span className="inline-flex items-center gap-0.5 flex-shrink-0">
                                                  <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full border whitespace-nowrap bg-blue-50 text-hp-navy border-blue-200">
                                                    {`${p.evidence_strength.score}/${p.evidence_strength.max_score}`}
                                                  </span>
                                                  <ScoreInfo topic="evidenceStrength" align="right" />
                                                </span>
                                              )
                                            )}
                                          </div>

                                          {/* The card body is the description -
                                              what the account is doing and what
                                              it implies for HP. The raw source
                                              sentence is evidence, not prose,
                                              and now lives in the drawer where
                                              a reader goes to check a claim. */}
                                          {(p.description?.points?.length ?? 0) > 0 ? (
                                            <ul className="space-y-1">
                                              {p.description.points.map((point: string, i: number) => (
                                                <li key={i} className="text-xs text-slate-600 leading-relaxed flex gap-2">
                                                  <span className="text-hp-navy flex-shrink-0">&bull;</span>
                                                  <span>{point}</span>
                                                </li>
                                              ))}
                                            </ul>
                                          ) : p.description?.text ? (
                                            <p className="text-xs text-slate-600 leading-relaxed">
                                              {p.description.text}
                                            </p>
                                          ) : null}

                                          {p.why_now && (
                                            <p className="text-[11px] text-slate-500 leading-relaxed">
                                              <span className="font-bold text-slate-600">Why now: </span>{p.why_now}
                                            </p>
                                          )}

                                          {/* A published HP case study supporting the HP
                                              offering this catalyst names. Attached in Python
                                              AFTER the paragraph is written, to whichever HP
                                              line the paragraph actually mentions - the
                                              tuning logic is explicit that proof "must not
                                              create the account need", so it can only follow
                                              a recommendation the evidence already earned.
                                              A catalyst naming no HP line carries none. */}
                                          {p.hp_proof_point && (
                                            <div className="bg-amber-50/60 border border-amber-200 rounded-xl px-3 py-2 space-y-1">
                                              <span className="text-[9px] font-mono font-extrabold uppercase tracking-widest text-amber-800 block">
                                                HP proof point
                                              </span>
                                              <p className="text-[11px] text-amber-900 leading-relaxed">{p.hp_proof_point}</p>
                                              {p.hp_proof_point_detail && (
                                                <p className="text-[10px] text-amber-800">
                                                  <span className="font-semibold">{p.hp_proof_point_detail.customer}</span>
                                                  {p.hp_proof_point_detail.industry && (
                                                    <span className="text-amber-700"> &middot; {p.hp_proof_point_detail.industry}</span>
                                                  )}
                                                  {openableUrl(p.hp_proof_point_detail.source_url, sourceLinkCtx) && (
                                                    <>
                                                      {' · '}
                                                      <a
                                                        href={openableUrl(p.hp_proof_point_detail.source_url, sourceLinkCtx)}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="underline hover:text-amber-950"
                                                      >
                                                        View the HP case study
                                                      </a>
                                                    </>
                                                  )}
                                                </p>
                                              )}
                                            </div>
                                          )}

                                          <button
                                            type="button"
                                            onClick={() => setExpandedPriority(open ? null : idx)}
                                            className="text-[11px] font-bold text-hp-navy hover:underline inline-flex items-center gap-1"
                                          >
                                            {open ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                            {open ? 'Hide evidence' : 'View evidence'}
                                          </button>

                                          {open && (
                                            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-3">
                                              {/* The score, and nothing about how it was reached.
                                                  The client, 30 Sep: the working does not belong on
                                                  screen. So the three term bars, the basis lines
                                                  ("2 relevant filings x 5 points"), the scored-on note
                                                  and the Supporting counts line are all gone from here.

                                                  The payload still carries every one of them, and must:
                                                  `measures` decides the ORDER these catalysts appear in
                                                  (priorities.py), feeds the executive summary and the
                                                  Strategy Chat corpus, and verify_executive_dashboard.py
                                                  asserts the whole evidence_strength structure. This is a
                                                  display change and only a display change. */}
                                              <div className="flex items-center justify-between">
                                                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 inline-flex items-center gap-1">
                                                  <BarChart3 className="w-3 h-3" />
                                                  Evidence strength
                                                </span>
                                                {p.evidence_strength?.zero_reason ? (
                                                  <span className="text-[11px] text-slate-400">{NO_SIGNAL}</span>
                                                ) : (
                                                  <span className="inline-flex items-center gap-0.5">
                                                    <span className="text-[11px] font-extrabold text-slate-700">
                                                      {`${p.evidence_strength?.score ?? 0}/${p.evidence_strength?.max_score ?? 100}`}
                                                    </span>
                                                    <ScoreInfo topic="evidenceStrength" align="right" />
                                                  </span>
                                                )}
                                              </div>

{/* The heading goes with its content: it used to stand over
                                                  an empty list reading "Supporting claims (0)". */}
                                              {(p.sources || []).length > 0 && (
                                              <div className="space-y-1.5 pt-1 border-t border-slate-200">
                                                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">
                                                  Supporting claims ({(p.sources || []).length})
                                                </span>
                                                {/* One short point per source, in the source's own
                                                    words (priorities.claim_point). The whole registered
                                                    text stays on hover. A payload built before
                                                    claim_point existed falls back to that text. */}
                                                <div className="space-y-2.5">
                                                  {(p.sources || []).map((s: any, si: number) => {
                                                    // One point for a short source, 3-6 for a long
                                                    // paragraph (priorities.claim_points).
                                                    const points: string[] = s.claim_points?.length
                                                      ? s.claim_points
                                                      : [s.claim_point || s.source_text];
                                                    return (
                                                      <div key={si} title={s.claim_points?.length || s.claim_point ? s.source_text : undefined}>
                                                        <ul className="space-y-1">
                                                          {points.map((point, pi) => (
                                                            <li key={pi} className="flex gap-2">
                                                              <span className="text-hp-navy flex-shrink-0 text-[11px] leading-snug">&bull;</span>
                                                              <span className="text-[11px] text-slate-700 leading-snug min-w-0">{point}</span>
                                                            </li>
                                                          ))}
                                                        </ul>
                                                        {/* The source, shown only when it has a
                                                            link that opens (client, 6-7 Oct). This
                                                            is the one place a catalyst's sources
                                                            appear: the card face no longer repeats
                                                            them. */}
                                                        <span className="block mt-1 pl-4">
                                                          <SourceChip s={s} tone="slate" />
                                                        </span>
                                                      </div>
                                                    );
                                                  })}
                                                </div>
                                              </div>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                </div>
                              );
                            })}

                            <p className="text-[10px] text-slate-500 leading-relaxed pt-1 border-t border-slate-100">
                              {prioritiesData?.ordering_basis}
                            </p>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                        )}
                      </div>

                    </div>
                  );
                })()}

                {/* Live Signals View (Feature Key: recent_news_signals) */}
                {activeFeatureKey === 'recent_news_signals' && (() => {
                  const feedWidget = widgets.find(w => w.widget_key === 'news_signals_feed');
                  const scoreWidget = widgets.find(w => w.widget_key === 'news_relevance_summary');

                  const feedData = (feedWidget && feedWidget.status === 'available' && feedWidget.data) ? feedWidget.data : null;
                  const scoreData: any = scoreWidget?.data || {};
                  const scores: Record<string, any> = scoreData.scores || {};
                  const scoreWeights: Record<string, number> = scoreData.score_weights || {};
                  const isScored = Object.keys(scores).length > 0;

                  const signals: any[] = feedData?.signals || [];

                  // Northstar thresholds: Critical 8+, High 6+, Medium 4+, else Low.
                  const urgencyOf = (score: number | null) => {
                    if (score === null || score === undefined) return null;
                    if (score >= 8.0) return { label: 'Critical', cls: 'bg-red-100 text-red-700 border-red-200', pulse: true };
                    if (score >= 6.0) return { label: 'High', cls: 'bg-orange-100 text-orange-700 border-orange-200', pulse: false };
                    if (score >= 4.0) return { label: 'Medium', cls: 'bg-yellow-100 text-yellow-700 border-yellow-200', pulse: false };
                    return { label: 'Low', cls: 'bg-gray-100 text-gray-600 border-gray-200', pulse: false };
                  };

                  // Has the event actually happened? A plant that "will be built"
                  // and one that "has opened" are different conversations, so the
                  // card must not read the same for both. 'unknown', a missing
                  // value and anything unrecognised all render nothing rather
                  // than asserting a status the evidence did not support.
                  const eventStatusBadge = (raw: any) => {
                    switch (String(raw ?? '').trim().toLowerCase()) {
                      case 'completed':
                        return { label: 'Completed', cls: 'bg-emerald-50 text-emerald-700 border-emerald-200', title: 'This event has already happened' };
                      case 'announced':
                        return { label: 'Announced', cls: 'bg-blue-50 text-blue-700 border-blue-200', title: 'Formally announced, not yet completed' };
                      case 'planned':
                        return { label: 'Planned', cls: 'bg-violet-50 text-violet-700 border-violet-200', title: 'Targeted or under consideration, not yet committed' };
                      case 'rumoured':
                        return { label: 'Rumoured', cls: 'bg-amber-50 text-amber-700 border-amber-200', title: 'Reported second-hand and unconfirmed' };
                      default:
                        return null;
                    }
                  };

                  // Source-confidence dot. google_news reports High/Medium/Low,
                  // news_events a 0-1 float; both map onto the same three states.
                  // No value in the row means no dot - nothing is assumed.
                  const confidenceDot = (raw: any) => {
                    if (raw === null || raw === undefined || raw === '') return null;
                    const text = String(raw).trim();
                    const num = Number(text);
                    let level: 'high' | 'medium' | 'low' | null = null;
                    if (!isNaN(num) && text !== '') {
                      level = num >= 0.8 ? 'high' : num >= 0.5 ? 'medium' : 'low';
                    } else {
                      const t = text.toLowerCase();
                      if (t.startsWith('high')) level = 'high';
                      else if (t.startsWith('med')) level = 'medium';
                      else if (t.startsWith('low')) level = 'low';
                    }
                    if (!level) return null;
                    return {
                      cls: level === 'high' ? 'bg-emerald-500' : level === 'medium' ? 'bg-amber-500' : 'bg-red-500',
                      title: `Source confidence: ${text}`,
                    };
                  };

                  // Display-only truncation. The full sentence stays in the DOM
                  // behind the toggle; the stored value is never altered.
                  const DETAIL_CLAMP = 160;

                  const typeColors: Record<string, string> = {
                    Financial: 'bg-green-100 text-green-700',
                    Technology: 'bg-blue-100 text-blue-700',
                    Security: 'bg-red-100 text-red-700',
                    Hiring: 'bg-purple-100 text-purple-700',
                    Strategic: 'bg-indigo-100 text-indigo-700',
                    Competitive: 'bg-orange-100 text-orange-700',
                  };
                  // Keyed by dimension name; the renderer skips any key absent
                  // from a signal's scores, so the three dimensions the scoring
                  // rewrite dropped stay listed here deliberately. A widget
                  // cached before the change still carries them, and removing
                  // the labels would render those breakdowns blank until the
                  // account is re-extracted.
                  const dimLabels: Record<string, string> = {
                    recency: 'Recency',
                    relevance_impact: 'Relevance & Impact',
                    source_reliability: 'Source Reliability',
                    // Superseded by relevance_impact - see above.
                    hp_relevance: 'HP Relevance',
                    strategic_impact: 'Strategic Impact',
                    actionability: 'Actionability',
                  };

                  // Categories present in the data, never a hardcoded list.
                  const categoryOptions = Array.from(new Set(signals.map(s => s.category).filter(Boolean))).sort() as string[];

                  const toggleType = (t: string) => {
                    setSignalTypes(prev => {
                      const next = new Set(prev);
                      if (next.has(t)) { next.delete(t); } else { next.add(t); }
                      return next;
                    });
                  };

                  // Date window is measured from the newest signal in the set, not
                  // from today - the uploaded exports lag real time, and anchoring
                  // on today would empty the view.
                  const times = signals
                    .map(s => new Date(s.event_date).getTime())
                    .filter(t => !isNaN(t) && t > 0);
                  const maxTime = times.length > 0 ? Math.max(...times) : Date.now();

                  const filteredSignals = signals.filter((s: any) => {
                    if (signalTypes.size > 0 && !signalTypes.has(s.category)) return false;
                    if (minSignalScore > 0) {
                      if (s.confidence === null || s.confidence === undefined) return false;
                      if (s.confidence < minSignalScore) return false;
                    }
                    if (dateRangeFilter !== 'All time') {
                      const t = new Date(s.event_date).getTime();
                      if (!isNaN(t) && t > 0) {
                        const diffDays = (maxTime - t) / (1000 * 60 * 60 * 24);
                        if (dateRangeFilter === 'Last 7 days' && diffDays > 7) return false;
                        if (dateRangeFilter === 'Last 30 days' && diffDays > 30) return false;
                        if (dateRangeFilter === 'Last 90 days' && diffDays > 90) return false;
                      }
                    }
                    return true;
                  });

                  const urgencyCounts = filteredSignals.reduce((acc: Record<string, number>, s: any) => {
                    const u = urgencyOf(s.confidence);
                    if (u) acc[u.label] = (acc[u.label] || 0) + 1;
                    return acc;
                  }, {});

                  const fmtDate = (d: string) => {
                    if (!d) return NOT_DISCLOSED;
                    const dt = new Date(d);
                    if (isNaN(dt.getTime())) return d;
                    return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
                  };

                  return (
                    <div className="space-y-5 animate-fade-in">
                      <PendingNotice widget={scoreWidget} title="Signal scoring unavailable" />

                      {/* Header */}
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3">
                        <div>
                          <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                            <Newspaper className="w-5 h-5 text-hp-navy" />
                            <span>Live Signals</span>
                          </h3>
                          <p className="text-sm text-slate-500 mt-0.5">
                            Real-time intelligence triggers for {selectedAccount?.name}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setIsFilterDrawerOpen(!isFilterDrawerOpen)}
                          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-semibold rounded-lg border transition ${
                            isFilterDrawerOpen
                              ? 'bg-blue-50 text-hp-navy border-blue-200'
                              : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50'
                          }`}
                        >
                          <Filter className="w-3.5 h-3.5" />
                          <span>Filters</span>
                        </button>
                      </div>

                      {/* Summary bar */}
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-semibold text-slate-700">{filteredSignals.length} Signals</span>
                        {['Critical', 'High', 'Medium', 'Low'].map(lvl => urgencyCounts[lvl] ? (
                          <span key={lvl} className={`px-2 py-0.5 rounded-full font-medium ${
                            lvl === 'Critical' ? 'bg-red-100 text-red-700'
                            : lvl === 'High' ? 'bg-orange-100 text-orange-700'
                            : lvl === 'Medium' ? 'bg-yellow-100 text-yellow-700'
                            : 'bg-gray-100 text-gray-600'}`}>
                            {urgencyCounts[lvl]} {lvl}
                          </span>
                        ) : null)}
                        {feedData?.raw_signal_count !== undefined && (
                          <span className="text-[11px] text-slate-400">
                            from {feedData.raw_signal_count} raw &middot;{' '}
                            {(() => {
                              // These are ordinary Gate 0 exclusions, not validation
                              // failures - name the actual reason.
                              const summary: Record<string, number> = feedData.gate_rejection_summary || {};
                              const reasons = Object.entries(summary);
                              if (reasons.length === 1 && reasons[0][0].startsWith('older than')) {
                                return `${reasons[0][1]} outside the 12-month window`;
                              }
                              if (reasons.length > 0) {
                                return reasons.map(([r, n]) => `${n} ${r}`).join(', ');
                              }
                              return `${feedData.gate_rejected_count} excluded`;
                            })()}
                          </span>
                        )}
                        {getClassificationBadge(isScored ? 'inferred' : 'deterministic')}
                      </div>

                      {/* Gap reason lives in the backend (data_gaps); the client sees neutral wording. */}

                      {/* Filter panel */}
                      {isFilterDrawerOpen && (
                        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-4 space-y-4">
                          <div>
                            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Signal Type</p>
                            <div className="flex flex-wrap gap-1.5">
                              {categoryOptions.map(t => (
                                <button
                                  key={t}
                                  type="button"
                                  onClick={() => toggleType(t)}
                                  className={`text-[11px] px-2.5 py-1 rounded-full font-medium border transition ${
                                    signalTypes.has(t)
                                      ? `${typeColors[t] || 'bg-slate-100 text-slate-700'} border-transparent`
                                      : 'bg-white text-slate-400 border-slate-200'
                                  }`}
                                >
                                  {t}
                                </button>
                              ))}
                            </div>
                          </div>

                          <div>
                            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2 flex items-center gap-1">Minimum Score <ScoreInfo topic="liveSignal" /></p>
                            <div className="flex flex-wrap gap-1.5">
                              {[0, 4, 6, 8].map(v => (
                                <button
                                  key={v}
                                  type="button"
                                  disabled={!isScored}
                                  onClick={() => setMinSignalScore(v)}
                                  className={`text-[11px] px-2.5 py-1 rounded-full font-medium border transition disabled:opacity-40 disabled:cursor-not-allowed ${
                                    minSignalScore === v
                                      ? 'bg-hp-navy text-white border-hp-navy'
                                      : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50'
                                  }`}
                                >
                                  {v === 0 ? 'All' : `${v}+`}
                                </button>
                              ))}
                            </div>
                          </div>

                          <div>
                            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Date Range</p>
                            <div className="flex flex-wrap gap-1.5">
                              {['All time', 'Last 7 days', 'Last 30 days', 'Last 90 days'].map(r => (
                                <button
                                  key={r}
                                  type="button"
                                  onClick={() => setDateRangeFilter(r)}
                                  className={`text-[11px] px-2.5 py-1 rounded-full font-medium border transition ${
                                    dateRangeFilter === r
                                      ? 'bg-hp-navy text-white border-hp-navy'
                                      : 'bg-white text-slate-500 border-slate-200 hover:bg-slate-50'
                                  }`}
                                >
                                  {r}
                                </button>
                              ))}
                            </div>
                            <p className="text-[10px] text-slate-400 mt-1.5">
                              Measured from the most recent signal in this account&apos;s data, not from today.
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={() => { setSignalTypes(new Set()); setMinSignalScore(0); setDateRangeFilter('All time'); }}
                            className="text-xs font-medium text-slate-500 hover:text-slate-800"
                          >
                            Clear filters
                          </button>
                        </div>
                      )}

                      {/* Signal cards */}
                      {filteredSignals.length === 0 ? (
                        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-8 text-center">
                          <p className="text-slate-400 text-sm">No signals match the current filters.</p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {filteredSignals.map((s: any) => {
                            const sc = scores[s.signal_id];
                            const urgency = urgencyOf(s.confidence);
                            const isOpen = expandedSignalId === s.signal_id;
                            return (
                              <div
                                key={s.signal_id}
                                className={`bg-white rounded-xl border shadow-xs overflow-hidden ${
                                  s.confidence !== null && s.confidence >= 8.0 ? 'border-red-200' : 'border-slate-200'
                                }`}
                              >
                                <div className="p-4">
                                  {/* badges + date + score */}
                                  <div className="flex flex-wrap items-center gap-2 mb-2">
                                    <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold ${typeColors[s.category] || 'bg-slate-100 text-slate-700'}`}>
                                      {s.category}
                                    </span>
                                    {urgency && (
                                      <span className={`text-[11px] px-2 py-0.5 rounded-full font-semibold border ${urgency.cls} ${urgency.pulse ? 'animate-pulse' : ''}`}>
                                        {urgency.label}
                                      </span>
                                    )}
                                    {(() => {
                                      // Whether the event has actually happened. "unknown" is
                                      // deliberately silent - no badge rather than a guess.
                                      const st = eventStatusBadge(s.event_status);
                                      return st ? (
                                        <span
                                          title={st.title}
                                          className={`text-[10px] px-1.5 py-0.5 rounded font-bold uppercase tracking-wider border ${st.cls}`}
                                        >
                                          {st.label}
                                        </span>
                                      ) : null;
                                    })()}
                                    <span className="text-xs text-slate-400">{fmtDate(s.event_date)}</span>
                                    {s.publication_date && s.publication_date !== s.event_date && (
                                      <span className="text-[10px] text-slate-400" title="Publication date, where it differs from the event date">
                                        published {fmtDate(s.publication_date)}
                                      </span>
                                    )}
                                    <span className="ml-auto flex items-center gap-2 text-xs font-semibold text-slate-600">
                                      {s.confidence !== null && s.confidence !== undefined ? (
                                        <>{s.confidence.toFixed(1)}<span className="text-slate-400 font-normal">/10</span><ScoreInfo topic="liveSignal" align="right" /></>
                                      ) : (
                                        <span className="text-slate-400 font-normal">{NO_SIGNAL}</span>
                                      )}
                                      {s.tier && (
                                        <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">{s.tier}</span>
                                      )}
                                      {(() => {
                                        const dot = confidenceDot(s.source_confidence);
                                        return dot ? (
                                          <span className={`inline-block w-2 h-2 rounded-full ${dot.cls}`} title={dot.title} />
                                        ) : null;
                                      })()}
                                    </span>
                                  </div>

                                  {/* WHAT'S NEW - a single clipped line, as the reference card */}
                                  <div className="flex items-baseline gap-2 min-w-0">
                                    <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 flex-shrink-0">
                                      What&apos;s new:
                                    </span>
                                    <span
                                      title={s.headline}
                                      className="text-sm font-semibold text-slate-900 truncate min-w-0"
                                    >
                                      {s.headline}
                                    </span>
                                  </div>

                                  {s.amount && (
                                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                                      <span className="text-[10px] font-medium text-slate-600 bg-slate-100 border border-slate-200 px-1.5 py-0.5 rounded">
                                        {s.amount}
                                      </span>
                                    </div>
                                  )}

                                  {/* Implication for HP */}
                                  {sc?.sales_angle && (
                                    <div className="mt-2 text-xs text-sky-800 bg-sky-50 border border-sky-200 rounded-lg px-2.5 py-1.5">
                                      {sc.hp_play && (
                                        <span className="inline-block mb-1 text-[10px] font-bold uppercase tracking-wider text-sky-700 bg-sky-100 border border-sky-200 px-1.5 py-0.5 rounded">
                                          {sc.hp_play}
                                        </span>
                                      )}
                                      <p>
                                        <span className="font-semibold">Implication for HP: </span>{sc.sales_angle}
                                      </p>
                                      <ProofPoint proof={s.hp_proof_point} />
                                    </div>
                                  )}

                                  {/* Detail paragraph, then its own toggle line. Absent when the
                                      export gave no text beyond the headline. */}
                                  {(() => {
                                    const detail: string = s.evidence_sentence || '';
                                    // Some exports repeat the headline in the body column; the
                                    // extractor blanks those, so there is simply nothing to add.
                                    if (!detail) return null;
                                    const needsClamp = detail.length > DETAIL_CLAMP;
                                    const detailOpen = expandedSignalDetailId === s.signal_id;
                                    const shown = (needsClamp && !detailOpen)
                                      ? detail.slice(0, DETAIL_CLAMP).trimEnd() + '…'
                                      : detail;
                                    return (
                                      <>
                                        <p className="mt-2 text-xs text-slate-500 leading-relaxed">{shown}</p>
                                        {needsClamp && (
                                          <button
                                            type="button"
                                            onClick={() => setExpandedSignalDetailId(detailOpen ? null : s.signal_id)}
                                            className="mt-1 flex items-center gap-1 text-[11px] font-medium text-hp-navy hover:underline"
                                          >
                                            {detailOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                            <span>{detailOpen ? 'Show less' : 'Read more'}</span>
                                          </button>
                                        )}
                                      </>
                                    );
                                  })()}

                                  {/* Source chip, directly below the implication block.
                                      The link prefers resolved_source_url: a google_news
                                      row's own URL is a news.google.com redirect, and the
                                      backend unwraps it to the publisher. A news_events
                                      signal carries no URL by design and stays unlinked. */}
                                  {(() => {
                                    const acctId = sourceLinkCtx;
                                    const primaryHref = sourceHref(s, acctId);
                                    // The merge keeps the primary's own entry in this list,
                                    // so the article already linked above is dropped rather
                                    // than shown twice.
                                    const others = (s.supporting_sources || []).filter(
                                      (x: any) => sourceHref(x, acctId)
                                        && sourceHref(x, acctId) !== primaryHref);
                                    const sourcesOpen = expandedSignalSourcesId === s.signal_id;
                                    return (
                                      <div className="mt-2.5 space-y-1.5">
                                        <div className="flex flex-wrap items-center gap-2">
                                          {primaryHref && (
                                            <a
                                              href={primaryHref}
                                              target="_blank"
                                              rel="noopener noreferrer"
                                              className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full hover:bg-emerald-100 transition"
                                            >
                                              <FileText className="w-3 h-3" />
                                              <span>{s.source_publisher || hostLabel(primaryHref) || 'Source'}</span>
                                              <ExternalLink className="w-3 h-3" />
                                            </a>
                                          )}
                                          {/* The count was the whole of this before: the
                                              payload has carried every merged article with
                                              its own URL all along, and none of them were
                                              reachable (client, 6 Oct).

                                              When none of them IS reachable, nothing is said.
                                              "2 supporting sources" appeared in exactly the
                                              case where there was nothing to open, which is
                                              the opposite of useful. */}
                                          {others.length > 0 && (
                                            <button
                                              type="button"
                                              onClick={() => setExpandedSignalSourcesId(sourcesOpen ? null : s.signal_id)}
                                              className="inline-flex items-center gap-1 text-[10px] font-medium text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded hover:bg-slate-200 transition"
                                            >
                                              {sourcesOpen ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
                                              {others.length} more source{others.length === 1 ? '' : 's'}
                                            </button>
                                          )}
                                        </div>
                                        {sourcesOpen && others.length > 0 && (
                                          <div className="flex flex-wrap items-center gap-1.5 pl-0.5">
                                            {others.map((x: any, xi: number) => (
                                              <SourceChip
                                                key={xi}
                                                s={{ ...x, label: x.publisher || x.dataset
                                                      || hostLabel(sourceHref(x, acctId)) }}
                                              />
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    );
                                  })()}

                                  {sc && (
                                    <div className="mt-2 flex justify-end">
                                      <button
                                        type="button"
                                        onClick={() => setExpandedSignalId(isOpen ? null : s.signal_id)}
                                        className="text-[11px] text-hp-navy hover:underline font-medium flex items-center gap-1"
                                      >
                                        {isOpen ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                        <span>{isOpen ? 'Hide' : 'Score'} breakdown</span>
                                      </button>
                                    </div>
                                  )}

                                  {/* expanded score breakdown */}
                                  {isOpen && sc && (
                                    <div className="mt-3 bg-slate-50 rounded-lg p-3 border border-slate-200 space-y-2">
                                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1">Score breakdown <ScoreInfo topic="liveSignal" /></p>
                                      {Object.entries(dimLabels).map(([dim, label]) => {
                                        const val = sc.scores?.[dim];
                                        if (val === undefined) return null;
                                        const weight = scoreWeights[dim];
                                        return (
                                          <div key={dim} className="space-y-0.5">
                                            <div className="flex items-center gap-2">
                                              <span className="text-[10px] text-slate-500 font-medium w-32 flex-shrink-0">
                                                {label}{weight ? ` (${Math.round(weight * 100)}%)` : ''}
                                              </span>
                                              <div className="flex-1 h-1.5 bg-slate-200 rounded-full overflow-hidden">
                                                <div className="as-grow h-1.5 bg-hp-navy/60 rounded-full" style={{ width: `${val * 10}%` }}></div>
                                              </div>
                                              <span className="text-[10px] font-mono text-slate-400 w-9 text-right flex-shrink-0"><CountUpText text={val} />/10</span>
                                            </div>
                                            {/* Recency has no line of its own: its
                                                basis is the event's date, and the
                                                card above already shows it. The
                                                score and its weight still read
                                                here.

                                                Source reliability is composed from
                                                the score rather than read from the
                                                stored text, so the band's name is
                                                current on every account without
                                                regenerating any of them - see
                                                `sourceReliabilityLine`. The stored
                                                line is the fallback, for a widget
                                                whose score is missing. */}
                                            {dim !== 'recency' && (() => {
                                              const line = dim === 'source_reliability'
                                                ? (sourceReliabilityLine(val, s.source_publisher)
                                                   || sc.rationales?.[dim])
                                                : sc.rationales?.[dim];
                                              return line ? (
                                                <p className="text-[10px] text-slate-400 pl-[8.5rem] leading-relaxed">{line}</p>
                                              ) : null;
                                            })()}
                                          </div>
                                        );
                                      })}
                                      <p className="text-[10px] text-slate-500 pt-1 border-t border-slate-200">
                                        Weighted total <span className="font-semibold text-slate-700">{s.confidence?.toFixed(2)}</span> /10
                                        {s.tier && <> &middot; tier {s.tier}</>}
                                      </p>
                                    </div>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  );
                })()}
                {activeFeatureKey === 'intent_demand_signals' && (() => {
                  const topicsWidget = widgets.find(w => w.widget_key === 'intent_topics_table');
                  const summaryWidget = widgets.find(w => w.widget_key === 'intent_category_summary');

                  const topicsData = (topicsWidget && topicsWidget.status === 'available' && topicsWidget.data) ? topicsWidget.data : null;
                  const summaryData = (summaryWidget && summaryWidget.status === 'available' && summaryWidget.data) ? summaryWidget.data : null;

                  const topicsList: IntentTopic[] = topicsData?.topics || [];
                  const provider = topicsData?.provider || summaryData?.provider;
                  const accountMatch = topicsData?.account_match || summaryData?.account_match;
                  // `observation` (Bombora's own Date Stamp) is no longer read:
                  // its only reader was the "Intent · as of" chip, removed on
                  // 6 Oct. It stays in the widget payload.
                  const dictionaryVersion: string = topicsData?.dictionary_version || summaryData?.dictionary_version || '';
                  const categoryFile = summaryData?.category_file || summaryWidget?.data?.category_file;
                  const categoryFileMatched = categoryFile?.status === 'matched';
                  const themes: any[] = summaryData?.themes || [];
                  // The spec asks for the HP-category view across all supported categories,
                  // not for one of them to be ranked above the rest. Ordered by the
                  // category file's own score.
                  const hpCategories: any[] = [...(summaryData?.hp_categories || [])].sort(
                    (a: any, b: any) => (b.primary?.score ?? -1) - (a.primary?.score ?? -1)
                  );
                  // Sahaj 3.6: where the account has Bombora research, lead with it -
                  // the cards order by their strongest Bombora topic, and each shows
                  // that research above the Predictleads category score.
                  const buUnits: any[] = summaryData?.bu_summary?.units || [];
                  const buByCat: Record<string, any> = Object.fromEntries(buUnits.map((u: any) => [u.category, u]));
                  const leadWithBombora = summaryData?.bu_summary?.lead_source === 'Bombora';
                  // Client email, 5 Oct: a Bombora account's topics are grouped by HP
                  // category in the summary, with the long tail in its dropdown. The
                  // dictionary's theme groups further down would be a second, different
                  // grouping of the same topics, so they are left out on these accounts.
                  const hpGrouped = leadWithBombora && Array.isArray(summaryData?.bu_summary?.long_tail);
                  const otherCats = leadWithBombora
                    ? [...hpCategories].sort((a: any, b: any) =>
                        (buByCat[b.category]?.bombora_max ?? -1) - (buByCat[a.category]?.bombora_max ?? -1))
                    : hpCategories;
                  const chartCats = hpCategories.filter((c: any) => c.primary).sort((a: any, b: any) => (b.primary.score ?? -1) - (a.primary.score ?? -1));
                  const disclaimer: string = summaryData?.disclaimer || topicsData?.disclaimer || 'Intent indicates research activity, not confirmed purchase intent.';
                  // Source A that is missing or belongs to another domain is stated, never drawn as zero scores.
                  // Client ruling, 24 Sep: when a dataset is missing, leave the section
                  // out and write nothing. Behind the same flag as the other empty
                  // states so the whole behaviour reverses in one place.
                  const sourceAMessage: string | null = (topicsData || !SHOW_EMPTY_STATE_NOTICES)
                    ? null
                    : (topicsWidget?.data?.message || 'Intent unavailable: no intent topics have been extracted for this account.');
                  const otherTheme = themes.find((t: any) => t.theme === 'Other / Low Relevance');
                  const includedCount: number = topicsData?.included_topics_count || 0;
                  const unmappedPct = includedCount && otherTheme ? Math.round((otherTheme.topic_count / includedCount) * 100) : 0;

                  const filteredTopics = topicsList.filter((t: any) => {
                    if (intentSearch && !t.topic_name.toLowerCase().includes(intentSearch.toLowerCase().trim())) return false;
                    if (intentScoreFilter === '70+' && (t.composite_score ?? -1) < 70) return false;
                    if (intentScoreFilter === '85+' && (t.composite_score ?? -1) < 85) return false;
                    return true;
                  }).sort((a: any, b: any) => (
                    intentSort === 'name'
                      ? a.topic_name.localeCompare(b.topic_name)
                      : (b.composite_score ?? -1) - (a.composite_score ?? -1)
                  ));
                  const excludedTopics = topicsList.filter((t: any) => !t.included);
                  const duplicatesRemoved: any[] = topicsData?.duplicates_removed || [];

                  const CATEGORY_STYLE: Record<string, { bar: string; chip: string }> = {
                    'PC': { bar: 'bg-[#0096D6]', chip: 'bg-blue-50 text-hp-navy border-blue-200' },
                    'Workstation': { bar: 'bg-indigo-500', chip: 'bg-indigo-50 text-indigo-800 border-indigo-200' },
                    'Poly/Collaboration': { bar: 'bg-emerald-600', chip: 'bg-emerald-50 text-emerald-800 border-emerald-200' },
                    'Print': { bar: 'bg-amber-500', chip: 'bg-amber-50 text-amber-800 border-amber-200' },
                    '3D': { bar: 'bg-pink-600', chip: 'bg-pink-50 text-pink-800 border-pink-200' }
                  };
                  const THEME_STYLE: Record<string, { chip: string; bar: string; border: string }> = {
                    'AI & Compute': { chip: 'bg-purple-100 text-purple-800 border-purple-200', bar: 'bg-purple-600', border: 'border-purple-200' },
                    'Devices & Endpoints': { chip: 'bg-blue-100 text-blue-800 border-blue-200', bar: 'bg-hp-navy', border: 'border-blue-200' },
                    'Collaboration & Workplace': { chip: 'bg-emerald-100 text-emerald-800 border-emerald-200', bar: 'bg-emerald-600', border: 'border-emerald-200' },
                    'Print': { chip: 'bg-amber-100 text-amber-800 border-amber-200', bar: 'bg-amber-500', border: 'border-amber-200' },
                    '3D': { chip: 'bg-pink-100 text-pink-800 border-pink-200', bar: 'bg-pink-500', border: 'border-pink-200' },
                    'Cloud & Infrastructure': { chip: 'bg-sky-100 text-sky-800 border-sky-200', bar: 'bg-sky-500', border: 'border-sky-200' },
                    'Security': { chip: 'bg-red-100 text-red-800 border-red-200', bar: 'bg-red-500', border: 'border-red-200' },
                    'Financial Services & Fintech': { chip: 'bg-green-100 text-green-800 border-green-200', bar: 'bg-green-500', border: 'border-green-200' },
                    'E-commerce & Logistics': { chip: 'bg-orange-100 text-orange-800 border-orange-200', bar: 'bg-orange-500', border: 'border-orange-200' },
                    'Other / Low Relevance': { chip: 'bg-slate-100 text-slate-700 border-slate-200', bar: 'bg-slate-400', border: 'border-slate-200' }
                  };
                  const categoryLabel = (name: string) => (name === 'Poly/Collaboration' ? 'Poly' : name);

                  const shortTopic = (name: string) => (name.includes(':') ? name.split(':').slice(1).join(':').trim() : name);

                  // The category file's own detail for one category, shown as received.
                  const renderFileDetails = (p: any) => (
                    <div className="space-y-2">
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Signal Topics (category file)</span>
                      {p.topics_researched?.length ? (
                        <div className="flex flex-wrap gap-1.5">
                          {p.topics_researched.map((t: string) => (
                            <span key={t} className="px-2 py-0.5 rounded-full border border-slate-200 text-[11px] text-slate-700 font-medium">{t}</span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-[11px] text-slate-400 block">{NO_SIGNAL}</span>
                      )}
                      {p.keywords_matched?.length > 0 && (
                        <p className="text-[10px] text-slate-500"><span className="font-bold text-slate-400 uppercase mr-1">Keywords</span>{p.keywords_matched.join(' · ')}</p>
                      )}
                      {p.related_technologies?.length > 0 && (
                        <p className="text-[10px] text-slate-500"><span className="font-bold text-slate-400 uppercase mr-1">Technologies</span>{p.related_technologies.join(' · ')}</p>
                      )}
                      <p className="text-[10px] text-slate-400">
                        {p.first_intent_date ? `Observed ${p.first_intent_date} → ${p.latest_intent_date || p.first_intent_date}` : NO_SIGNAL}
                      </p>
                      {/* quality_flags are review notes; they live in the backend, not on the client's screen. */}
                    </div>
                  );

                  // Steps 2-4: Bombora signals with exact scores, and the technologies that confirm them.
                  const renderSignals = (signals: any[], topicLimit: number) => {
                    if (!signals?.length) return <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>;
                    return (
                      <div className="space-y-2">
                        {signals.map((sg: any) => (
                          <div key={sg.signal} className={`rounded-lg border p-2.5 ${sg.confirmed ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200 bg-slate-50/50'}`}>
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-1.5 text-[11px] font-bold text-slate-800">
                                {sg.confirmed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <Minus className="w-3.5 h-3.5 text-slate-300" />}
                                {sg.signal}
                              </span>
                              {sg.max != null
                                ? <span className="font-mono text-xs font-extrabold text-slate-900"><CountUpText text={sg.max} />/100</span>
                                : <span className="text-[10px] font-medium text-slate-400">{NO_SIGNAL}</span>}
                            </div>
                            {sg.topics.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-1.5">
                                {sg.topics.slice(0, topicLimit).map((t: any) => (
                                  <span key={t.topic_name} title={t.topic_name} className="px-1.5 py-0.5 rounded bg-white border border-slate-200 text-[10px] text-slate-700 font-medium">
                                    {shortTopic(t.topic_name)} <strong className="text-hp-navy">{t.composite_score}</strong>
                                  </span>
                                ))}
                                {sg.topics.length > topicLimit && (
                                  <span className="text-[10px] text-slate-400 font-bold self-center">+{sg.topics.length - topicLimit} more</span>
                                )}
                              </div>
                            )}
                            <p className="text-[10px] mt-1.5 text-slate-500">
                              {sg.technologies.length > 0 ? (
                                <>
                                  <span className="font-bold text-slate-400 uppercase mr-1">Technologies</span>
                                  {sg.technologies.map((t: any) => t.name).join(', ')}
                                  <span className="text-slate-400"> ({Array.from(new Set(sg.technologies.map((t: any) => `${t.sheet} · ${t.column}`))).join('; ')})</span>
                                </>
                              ) : (
                                <span className="text-slate-400">{NO_SIGNAL}</span>
                              )}
                            </p>
                          </div>
                        ))}
                      </div>
                    );
                  };

                  const renderTopicRow = (item: any, idx: number, barClass: string) => (
                    <div key={item.topic_name} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-slate-50 transition">
                      <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2 min-w-0">
                        <span className="text-slate-400 font-mono text-[11px] w-5 text-right flex-shrink-0">{idx + 1}</span>
                        <span className="capitalize truncate">{item.topic_name}</span>
                        {item.hp_category && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-50 text-hp-navy border border-blue-200 flex-shrink-0">{categoryLabel(item.hp_category)}</span>
                        )}
                        {item.mapping_status === 'flagged' && (
                          <span title={item.flag_reason || ''} className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200 flex-shrink-0">Review</span>
                        )}
                      </div>
                      <div className="flex items-center space-x-3 flex-shrink-0">
                        <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                          <div className={`as-grow ${barClass} h-1.5 rounded-full`} style={{ width: `${Math.min(100, Math.max(0, item.composite_score ?? 0))}%`, ['--as-d' as string]: `${growDelay(idx)}ms` }}></div>
                        </div>
                        <span className="font-mono font-bold text-slate-900 w-8 text-right"><CountUpText text={item.composite_score} delay={growDelay(idx)} /></span>
                        <span className="text-[10px] text-slate-400 font-medium w-12">{'Intent'}</span>
                      </div>
                    </div>
                  );

                  return (
                    <div className="space-y-6">

                      {/* Header */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <TrendingUp className="w-5 h-5 text-hp-navy" />
                            <span>Intent & Demand Signals</span>
                          </h2>
                          {/* Sahaj, 27 Sep: replace the counts line with the source. */}
                          <p className="text-xs text-slate-500 mt-0.5">
                            Research activity across HP's business areas
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                          {/* The "Intent · as of" chip was removed (client, 6 Oct).
                              It carried Bombora's own Date Stamp - when Bombora
                              OBSERVED the research - while the account header
                              carries the ingestion date. Two different dates on
                              one screen read as a contradiction, so only the
                              header's remains. The observation date is still in
                              the payload; nothing renders it. */}
                          {/* Only a verified match is shown; a mismatch or an unverified
                              domain is a backend review item, not a client-facing chip. */}
                          {accountMatch?.status === 'matched' && (
                            <span className="px-3 py-1 rounded-full text-[11px] border flex items-center gap-1 bg-emerald-50 text-emerald-800 border-emerald-200">
                              <ShieldCheck className="w-3.5 h-3.5" />
                              {`${accountMatch.provider_domain} verified`}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* The read leads the tab (Sahaj, 28 Sep: "move this
                          box to the top in intent n demand"). It is the answer;
                          the unit summary and the topics below are the working. */}
                      {summaryData && (
                      <div className="bg-blue-50/80 border border-blue-200/90 rounded-2xl p-6 text-xs text-blue-950 space-y-3 shadow-xs">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <h3 className="text-xs font-black uppercase tracking-wider text-hp-navy flex flex-wrap items-center gap-2">
                            <Lightbulb className="w-4 h-4 text-hp-navy" />
                            <span>SO WHAT FOR HP</span>
                            {includedCount > 0 && (
                              <span className="normal-case tracking-normal font-medium text-[11px] text-blue-700/80">
                                · {includedCount} intent topics categorized, {otherTheme?.topic_count ?? 0} ({unmappedPct}%) low-relevance and kept out of the theme read below
                              </span>
                            )}
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                            Rule-based · {dictionaryVersion}
                          </span>
                        </div>
                        <div className="space-y-2.5">
                          {(summaryData.so_what || []).map((line: string, i: number) => (
                            <p key={i} className="text-[12px] leading-relaxed text-slate-700 font-medium flex items-start gap-2.5">
                              <Target className="w-4 h-4 text-hp-navy flex-shrink-0 mt-0.5" />
                              <span>{line}</span>
                            </p>
                          ))}
                        </div>

                        {/* Case-study proof for the categories this read
                            covers. Client direction, 24 Sep: proof may
                            strengthen the So What for HP, and it follows
                            the read rather than creating it. Each is
                            labelled with the category it supports, so a
                            seller can see which part of the read it backs. */}
                        <p className="text-[11px] leading-relaxed text-blue-950 font-bold flex items-start gap-2.5 pt-2 border-t border-blue-200/60">
                          <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
                          <span>{disclaimer}</span>
                        </p>
                      </div>
                      )}

                      {/* Intent across HP's five business units.
                          Sahaj, 27 Sep: "add a broad summary at the start that
                          mentions intent around HP's key business units".
                          Sahaj, 28 Sep: "on top we can show the summary from the
                          bombora data itself, llm can generate in cards".

                          Where the account has Bombora, this is the whole of the
                          HP-unit view - one card per unit, its own researched
                          topics, and the model's one-line read of them. The
                          category file's numbers are not shown beside them: that
                          file is the fallback for the accounts with no Bombora,
                          and those keep the list form and the sections below.
                          Every number here is Python's; the read carries none. */}
                      {(summaryData?.bu_summary?.units || []).length > 0 && (() => {
                        const bu: any = summaryData?.bu_summary;
                        const byBombora = bu.lead_source === 'Bombora';
                        // Client email, 5 Oct: on a Bombora account each HP category is
                        // scored by the average of the Bombora topics the model placed in
                        // it. Where no topic was HP-relevant, the category file's scores
                        // stand in (score_source 'PredictLeads'). `score` is whichever
                        // applies; older builds carried only bombora_max.
                        const unitScore = (u: any) => u.score ?? u.bombora_max ?? u.category_file_score ?? null;
                        const averaged = bu.score_source === 'Bombora';
                        const longTail: any[] = bu.long_tail || [];
                        const sourceNote = averaged
                          ? 'Average strength of the research topics matched to each HP area'
                          : byBombora
                            ? 'From buying-interest data · none of this account’s research topics relate to an HP area'
                            : 'From buying-interest data for each HP area';
                        return (
                          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                              <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
                                Intent across HP business units <ScoreInfo topic="intentHpCategory" />
                              </h3>
                              <span className="text-[10px] text-slate-400">{sourceNote}</span>
                            </div>

                            {byBombora && bu.overview && (
                              <p className="text-xs text-slate-700 leading-relaxed bg-slate-50 border border-slate-200 rounded-xl p-3">
                                {bu.overview}
                              </p>
                            )}

                            {byBombora && bu.units.some((u: any) => unitScore(u) != null) && (
                              <div className="overflow-x-auto">
                                <div className="min-w-[480px] pl-8 pr-2 pt-7">
                                  <div className="relative h-52">
                                    {[0, 25, 50, 75, 100].map(v => (
                                      <div key={v} className={`absolute left-0 right-0 border-t ${v === 0 ? 'border-slate-300' : 'border-dashed border-slate-200'}`} style={{ bottom: `${v}%` }}>
                                        <span className="absolute -left-8 -translate-y-1/2 w-6 text-right text-[10px] font-mono text-slate-400">{v}</span>
                                      </div>
                                    ))}
                                    <div className="absolute inset-0 flex items-end justify-around">
                                      {bu.units.map((u: any, colIdx: number) => {
                                        const s = unitScore(u);
                                        const pct = Math.min(100, Math.max(0, s ?? 0));
                                        return (
                                          <div
                                            key={u.category}
                                            className="relative flex flex-col items-center justify-end h-full w-20"
                                            onMouseEnter={() => setHoveredIntentCat(u.category)}
                                            onMouseLeave={() => setHoveredIntentCat(null)}
                                          >
                                            <div
                                              className={`as-grow-y w-14 rounded-t-md cursor-default ${CATEGORY_STYLE[u.category]?.bar || THEME_STYLE[u.category]?.bar || 'bg-slate-400'}`}
                                              style={{ height: `${pct}%`, ['--as-d' as string]: `${growDelay(colIdx, 120, 70)}ms` }}
                                            ></div>
                                            {s != null && (
                                              <span className="absolute text-[11px] font-bold text-slate-700" style={{ bottom: `calc(${pct}% + 6px)` }}>
                                                <CountUpText text={s} delay={growDelay(colIdx, 120, 70)} />
                                              </span>
                                            )}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                  <div className="flex justify-around pt-2">
                                    {bu.units.map((u: any) => (
                                      <div key={u.category} className="w-20 text-center">
                                        <span className="text-xs block font-semibold text-slate-600">{categoryLabel(u.category)}</span>
                                        {unitScore(u) == null ? (
                                          <span className="text-[10px] font-medium text-slate-400 block">{NO_SIGNAL}</span>
                                        ) : averaged && (
                                          <span className="text-[10px] font-medium text-slate-400 block">
                                            avg of {u.bombora_topic_count} topic{u.bombora_topic_count === 1 ? '' : 's'}
                                          </span>
                                        )}
                                      </div>
                                    ))}
                                  </div>

                                  {/* The hovered unit's detail, under the chart: the
                                      plot scrolls sideways on a narrow screen and
                                      would clip anything floating over a bar. */}
                                  {(() => {
                                    const hovered = bu.units.find((u: any) => u.category === hoveredIntentCat);
                                    if (!hovered) {
                                      return (
                                        <p className="mt-3 text-[11px] text-slate-400 border-t border-slate-100 pt-2">
                                          Hover a bar for the topics behind that category&apos;s score.
                                        </p>
                                      );
                                    }
                                    const listed: any[] = hovered.bombora_topics || hovered.bombora_top_topics || [];
                                    return (
                                      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 space-y-1">
                                        <p className="text-[11px] font-extrabold text-slate-900">
                                          {categoryLabel(hovered.category)}
                                          {hovered.score_basis === 'bombora_average' && (
                                            <span className="text-slate-500 font-semibold">
                                              {' '}&middot; {hovered.bombora_topic_count} topic{hovered.bombora_topic_count === 1 ? '' : 's'} &middot; {hovered.bombora_score_sum} / {hovered.bombora_topic_count} = {hovered.score}
                                            </span>
                                          )}
                                          {hovered.score_basis === 'category_file' && hovered.category_file_stage && (
                                            <span className="text-slate-500 font-semibold"> &middot; {hovered.category_file_stage}</span>
                                          )}
                                        </p>
                                        {listed.length > 0 ? (
                                          <p className="text-[10px] text-slate-500 leading-snug">
                                            {listed.map((t: any) => `${shortTopic(t.topic)} ${t.score}`).join(' · ')}
                                          </p>
                                        ) : hovered.score_basis !== 'category_file' && (
                                          <p className="text-[10px] text-slate-400">{NO_SIGNAL}</p>
                                        )}
                                        <p className="text-[9px] text-slate-400">
                                          {hovered.score_basis === 'category_file' ? 'Score as received from the research provider.' : 'Topic scores as received from the research provider.'}
                                        </p>
                                      </div>
                                    );
                                  })()}
                                </div>
                              </div>
                            )}

                            {byBombora ? (
                              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                                {bu.units.map((u: any) => {
                                  const s = unitScore(u);
                                  const scored = s != null;
                                  const style = CATEGORY_STYLE[u.category] || THEME_STYLE[u.category]
                                    || { bar: 'bg-slate-400', chip: 'bg-slate-50 text-slate-700 border-slate-200' };
                                  const listed: any[] = u.bombora_topics || u.bombora_top_topics || [];
                                  return (
                                    <div
                                      key={u.category}
                                      className={`rounded-xl border overflow-hidden ${scored
                                        ? 'bg-white border-slate-200 shadow-xs'
                                        : 'bg-slate-50/60 border-slate-200'}`}
                                    >
                                      <div className={`h-1 ${scored ? style.bar : 'bg-slate-200'}`}></div>
                                      <div className="p-3.5 space-y-2">
                                      <div className="flex items-center justify-between gap-2">
                                        <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${style.chip}`}>
                                          {categoryLabel(u.category)}
                                        </span>
                                        {scored && (
                                          <span className="text-sm font-extrabold text-slate-800">
                                            {s}<span className="text-[10px] text-slate-400 font-medium">/100</span>
                                          </span>
                                        )}
                                      </div>
                                      {u.hp_play && (
                                        <p className="text-[11px] text-slate-400 leading-snug">{u.hp_play}</p>
                                      )}

                                      <p className="text-[11px] font-semibold text-slate-600">
                                        {u.score_basis === 'bombora_average'
                                          ? <>Average of {u.bombora_topic_count} research topic{u.bombora_topic_count === 1 ? '' : 's'}</>
                                          : u.score_basis === 'category_file'
                                            ? <>Buying-interest data{u.category_file_stage ? ` · ${u.category_file_stage}` : ''}</>
                                            : scored
                                              ? <>{u.bombora_topic_count} researched topic{u.bombora_topic_count === 1 ? '' : 's'}</>
                                              : <span className="text-slate-400 font-normal">{NO_SIGNAL}</span>}
                                      </p>

                                      {listed.length > 0 && (
                                        <div className="flex flex-wrap gap-1">
                                          {listed.map((t: any) => (
                                            <span
                                              key={t.topic}
                                              title={t.reason || undefined}
                                              className="text-[10px] font-medium text-slate-600 bg-slate-50 border border-slate-200 px-1.5 py-0.5 rounded-full"
                                            >
                                              {shortTopic(t.topic)} <span className="text-slate-400">{t.score}</span>
                                            </span>
                                          ))}
                                        </div>
                                      )}

                                      {u.read && (
                                        <p className="text-[11px] text-slate-700 leading-relaxed pt-1 border-t border-slate-100">
                                          {u.read}
                                        </p>
                                      )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <ul className="space-y-1.5">
                                {bu.units.map((u: any) => (
                                  <li key={u.category} className="text-xs text-slate-700 leading-relaxed">
                                    <span className="font-semibold text-slate-900">{categoryLabel(u.category)}</span>
                                    <span className="text-slate-400"> &middot; {u.hp_play}</span>
                                    {u.category_file_score !== null && u.category_file_score !== undefined && (
                                      <span className="text-slate-500"> - category score {u.category_file_score}/100</span>
                                    )}
                                  </li>
                                ))}
                              </ul>
                            )}

                            {/* The long tail (client email, 5 Oct): every Bombora topic
                                not placed in an HP category, as received, behind a
                                dropdown so the HP view stays first. */}
                            {byBombora && longTail.length > 0 && (
                              <details className="group rounded-xl border border-slate-200 bg-slate-50/50">
                                <summary className="cursor-pointer list-none flex items-center justify-between px-3.5 py-2.5 text-xs font-bold text-slate-700">
                                  <span>Other researched topics ({longTail.length})</span>
                                  <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" />
                                </summary>
                                <div className="px-3.5 pb-3 space-y-1 max-h-96 overflow-y-auto">
                                  {longTail.map((t: any, idx: number) => (
                                    <div key={`${t.topic}-${idx}`} className="flex items-center justify-between gap-3 text-xs py-0.5">
                                      <span className="capitalize text-slate-700 truncate">{t.topic}</span>
                                      <span className="font-mono font-bold text-slate-900 flex-shrink-0">{t.score}</span>
                                    </div>
                                  ))}
                                </div>
                              </details>
                            )}
                          </div>
                        );
                      })()}

                      {/* Unavailable states: stated, never drawn as zeros */}
                      {sourceAMessage && (
                        <div className="bg-white rounded-2xl p-5 border border-amber-200 shadow-sm flex items-start gap-3">
                          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <h3 className="text-sm font-extrabold text-slate-900">
                              {topicsWidget?.data?.availability === 'no_matched_signal' ? 'No Matched Signal' : 'Intent Unavailable'}
                            </h3>
                            <p className="text-xs text-slate-600 leading-relaxed">{sourceAMessage}</p>
                          </div>
                        </div>
                      )}
                      {/* Gap reason lives in the backend (data_gaps); the client sees neutral wording. */}

                      {summaryData && (
                        <>
                          {/* The HP Category Intent Scores - the intent file's own
                              chart and its five category cards - are shown only where
                              the account has NO Bombora research. Sahaj, 28 Sep: for
                              the 173 accounts that have Bombora, the summary at the
                              top stands in their place; the other 47 keep this. */}
                          {!leadWithBombora && (
                          <>
                          {/* Step 1 - HP Category Intent Scores, as received from the category file */}
                          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                              <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                                <Layers className="w-4 h-4 text-hp-navy" />
                                <span>HP CATEGORY INTENT SCORES</span>
                              </h3>
                              {categoryFileMatched && (
                                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200">
                                  HP Category Intent file
                                </span>
                              )}
                            </div>
                            {chartCats.length > 0 ? (
                              <div className="overflow-x-auto">
                                <div className="min-w-[480px] pl-8 pr-2 pt-7">
                                  <div className="relative h-52">
                                    {[0, 25, 50, 75, 100].map(v => (
                                      <div key={v} className={`absolute left-0 right-0 border-t ${v === 0 ? 'border-slate-300' : 'border-dashed border-slate-200'}`} style={{ bottom: `${v}%` }}>
                                        <span className="absolute -left-8 -translate-y-1/2 w-6 text-right text-[10px] font-mono text-slate-400">{v}</span>
                                      </div>
                                    ))}
                                    <div className="absolute inset-0 flex items-end justify-around">
                                      {chartCats.map((c: any, colIdx: number) => {
                                        const pct = Math.min(100, Math.max(0, c.primary.score ?? 0));
                                        const noisy = (c.primary.quality_flags || []).length > 0;
                                        const p = c.primary || {};
                                        return (
                                          <div
                                            key={c.category}
                                            className="relative flex flex-col items-center justify-end h-full w-20"
                                            onMouseEnter={() => setHoveredIntentCat(c.category)}
                                            onMouseLeave={() => setHoveredIntentCat(null)}
                                          >
                                            <div
                                              className={`as-grow-y w-14 rounded-t-md cursor-default ${CATEGORY_STYLE[c.category]?.bar || 'bg-slate-400'} ${noisy ? 'opacity-40' : ''}`}
                                              style={{ height: `${pct}%`, ['--as-d' as string]: `${growDelay(colIdx, 120, 70)}ms` }}
                                            ></div>
                                            {c.primary.score != null
                                              ? <span className="absolute text-[11px] font-bold text-slate-700" style={{ bottom: `calc(${pct}% + 6px)` }}><CountUpText text={c.primary.score} delay={growDelay(colIdx, 120, 70)} /></span>
                                              : <span className="absolute text-[10px] font-medium text-slate-400 text-center leading-tight" style={{ bottom: `calc(${pct}% + 6px)` }}>{NO_SIGNAL}</span>}

                                            {/* Hover detail: the category file's own fields for this category,
                                                each attributed and taken as supplied. */}
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                  <div className="flex justify-around pt-2">
                                    {chartCats.map((c: any) => (
                                      <div key={c.category} className="w-20 text-center">
                                        <span className="text-xs block font-semibold text-slate-600">{categoryLabel(c.category)}</span>
                                        {!c.primary.has_signal && c.primary.score != null && (
                                          <span className="text-[10px] font-medium text-slate-400 block">{NO_SIGNAL}</span>
                                        )}
                                      </div>

                                    ))}
                                  </div>

                                  {/* The hovered category's detail, under the
                                      chart. It used to sit above the bar inside
                                      this horizontally scrolling box, and a box
                                      that leaves a scrolling container on any
                                      axis is clipped by it. */}
                                  {(() => {
                                    const c = chartCats.find((x: any) => x.category === hoveredIntentCat);
                                    if (!c) {
                                      return (
                                        <p className="mt-3 text-[11px] text-slate-400 border-t border-slate-100 pt-2">
                                          Hover a bar for that category&apos;s detail from the intent file.
                                        </p>
                                      );
                                    }
                                    const p = c.primary || {};
                                    return (
                                              <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-left space-y-1.5">
                                                <p className="text-[11px] font-extrabold text-slate-900">
                                                  {categoryLabel(c.category)} &middot; {p.score != null ? `${p.score}/100` : <span className="font-medium text-slate-400">{NO_SIGNAL}</span>}
                                                </p>
                                                <div className="space-y-1">
                                                  <p className="flex items-baseline justify-between gap-2 text-[10px]">
                                                    <span className="font-bold text-slate-400 uppercase tracking-wider">Buying Stage</span>
                                                    <span className={`text-right ${p.stage ? 'font-semibold text-slate-600' : 'text-slate-400'}`}>{p.stage || NO_SIGNAL}</span>
                                                  </p>
                                                </div>

                                                {/* The rest of this category's block in the intent file. */}
                                                {p.topics_researched?.length > 0 && (
                                                  <p className="text-[10px] text-slate-500 leading-snug">
                                                    <span className="font-bold text-slate-400 uppercase tracking-wider block">Topics Researched</span>
                                                    {p.topics_researched.join(' \u00b7 ')}
                                                  </p>
                                                )}
                                                {p.keywords_matched?.length > 0 && (
                                                  <p className="text-[10px] text-slate-500 leading-snug">
                                                    <span className="font-bold text-slate-400 uppercase tracking-wider block">Keywords Matched</span>
                                                    {p.keywords_matched.join(' \u00b7 ')}
                                                  </p>
                                                )}
                                                {p.related_technologies?.length > 0 && (
                                                  <p className="text-[10px] text-slate-500 leading-snug">
                                                    <span className="font-bold text-slate-400 uppercase tracking-wider block">Related Technologies</span>
                                                    {p.related_technologies.join(' \u00b7 ')}
                                                  </p>
                                                )}
                                                <p className="text-[10px] text-slate-500 leading-snug">
                                                  <span className="font-bold text-slate-400 uppercase tracking-wider block">Observed</span>
                                                  {p.first_intent_date
                                                    ? `${p.first_intent_date} \u2192 ${p.latest_intent_date || p.first_intent_date}`
                                                    : NO_SIGNAL}
                                                </p>
                                                <p className="text-[9px] text-slate-400 leading-snug pt-0.5 border-t border-slate-100">
                                                  All values as received from the research provider.
                                                </p>
                                              </div>
                                    );
                                  })()}
                                </div>
                              </div>
                            ) : (
                              <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                            )}
                            <p className="text-[11px] text-slate-500">
                              Buying interest in each HP area, highest first. Hover a bar for that area&apos;s buying stage and the topics and keywords behind it. Other research signals add context and never change these scores.
                            </p>
                          </div>


                          {/* Other HP categories */}
                          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
                            {otherCats.map((cat: any) => {
                              const p = cat.primary;
                              const style = CATEGORY_STYLE[cat.category] || { bar: 'bg-slate-400', chip: 'bg-slate-50 text-slate-700 border-slate-200' };
                              const noisy = (p?.quality_flags || []).length > 0;
                              const signalTopics: string[] = [
                                ...(p?.topics_researched || []),
                                ...(p?.keywords_matched || []),
                              ];
                              return (
                                <div key={cat.category} className="bg-white p-5 rounded-2xl border shadow-xs flex flex-col gap-4 border-slate-200">
                                  {/* Header: category chip, the file's own direction, buying stage */}
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2.5 min-w-0">
                                      <span className={`px-3 py-0.5 rounded-full text-sm font-extrabold border ${style.chip}`}>{categoryLabel(cat.category)}</span>
                                    </div>
                                    {/* The buying-stage badge was removed at the client's
                                        request (6 Oct): the cards show the score only. */}
                                  </div>

                                  {/* Bombora research for this unit, first (Sahaj 3.6) */}
                                  {leadWithBombora && (() => {
                                    const u = buByCat[cat.category];
                                    if (!u) return null;
                                    return u.bombora_topic_count > 0 ? (
                                      <div className="rounded-lg bg-blue-50/60 border border-blue-100 px-3 py-2 space-y-1">
                                        <p className="text-[11px] font-bold text-slate-800">
                                          Research activity &middot; {u.bombora_topic_count} topic{u.bombora_topic_count === 1 ? '' : 's'} &middot; max {u.bombora_max}
                                        </p>
                                        {u.bombora_top_topics?.length > 0 && (
                                          <p className="text-[11px] text-slate-600 leading-relaxed">
                                            {u.bombora_top_topics.map((t: any) => `${t.topic} ${t.score}`).join(' · ')}
                                          </p>
                                        )}
                                      </div>
                                    ) : (
                                      <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>
                                    );
                                  })()}

                                  {/* Score bar */}
                                  {p && (
                                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Buying-interest score</span>
                                  )}
                                  {p ? (
                                    <div className="flex items-center gap-3">
                                      <div className="flex-1 bg-slate-100 h-2.5 rounded-full overflow-hidden">
                                        <div className={`as-grow ${style.bar} h-2.5 rounded-full ${noisy ? 'opacity-40' : ''}`} style={{ width: `${Math.min(100, Math.max(0, p.score ?? 0))}%`, ['--as-d' as string]: '120ms' }}></div>
                                      </div>
                                      {p.score != null
                                        ? <span className="text-base font-extrabold text-slate-900 flex-shrink-0"><CountUpText text={p.score} delay={120} />/100</span>
                                        : <span className="text-[11px] text-slate-400 flex-shrink-0">{NO_SIGNAL}</span>}
                                    </div>
                                  ) : (
                                    // No category score for this account. The card still carries the
                                    // Bombora research and the HP play, so it is shown, not collapsed.
                                    <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>
                                  )}

                                  {/* Signal topics as pills */}
                                  {p && (
                                    <div className="space-y-2.5">
                                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Signal Topics</span>
                                      {signalTopics.length ? (
                                        <div className="flex flex-wrap gap-2">
                                          {signalTopics.map((t: string) => (
                                            <span key={t} className="px-3 py-1 rounded-full border border-slate-200 bg-white text-[12px] text-slate-700">{t}</span>
                                          ))}
                                        </div>
                                      ) : (
                                        <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>
                                      )}
                                    </div>
                                  )}

                                  {/* Mapped HP play + research volume */}
                                  <div className="flex items-start justify-between gap-2 pt-3.5 border-t border-slate-100">
                                    <div className="flex items-start gap-2 min-w-0">
                                      <Target className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                                      <div className="min-w-0">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Mapped HP Play</span>
                                        {cat.hp_play
                                          ? <span className="text-sm font-bold text-slate-900 leading-tight block">{cat.hp_play}</span>
                                          : <span className="text-sm text-slate-400 leading-tight block">{NO_SIGNAL}</span>}
                                      </div>
                                    </div>
                                  </div>

                                  {/* Observation window */}
                                  {p?.first_intent_date && (
                                    <p className="text-[11px] text-slate-400">
                                      Observed {p.first_intent_date} → {p.latest_intent_date || p.first_intent_date}
                                    </p>
                                  )}

                                  {/* Supporting Bombora signals, kept visibly apart from the file's own numbers */}
                                  <details open={!p} className="pt-3 border-t border-slate-100 group">
                                    <summary className="text-[10px] font-bold text-slate-400 uppercase tracking-wider cursor-pointer list-none flex items-center gap-1.5 hover:text-slate-600">
                                      <ChevronDown className="w-3.5 h-3.5 transition-transform group-open:rotate-180" />
                                      Supporting Intent Signals
                                    </summary>
                                    <div className="mt-2.5">{renderSignals(cat.supporting_signals, 3)}</div>
                                  </details>

                                  <p className="text-[11px] text-slate-600 leading-relaxed mt-auto">{cat.explanation}</p>
                                </div>
                              );
                            })}
                          </div>
                          </>
                          )}

                        </>
                      )}

                      {/* Broader intent topics, raw view */}
                      {topicsData && (
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                            <div>
                              <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                                <Database className="w-4 h-4 text-hp-navy" />
                                <span>{hpGrouped ? 'INTENT DATA' : `BROADER INTENT TOPICS (${topicsList.length})`}</span>
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                The topics people at this company have been researching, each scored 0-100, as received
                              </p>
                            </div>

                            {!hpGrouped && (
                            <div className="flex items-center space-x-2 text-xs">
                              <div className="relative">
                                <Search className="w-3.5 h-3.5 text-gray-400 absolute left-2.5 top-2.5" />
                                <input
                                  type="text"
                                  value={intentSearch}
                                  onChange={(e) => setIntentSearch(e.target.value)}
                                  placeholder="Filter topics..."
                                  className="pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-300 rounded-xl text-xs focus:outline-none focus:ring-1 focus:ring-hp-navy w-44"
                                />
                              </div>
                              <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl border border-slate-200">
                                {['ALL', '70+', '85+'].map((sc) => (
                                  <button
                                    key={sc}
                                    type="button"
                                    onClick={() => setIntentScoreFilter(sc)}
                                    className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition ${
                                      intentScoreFilter === sc ? 'bg-hp-navy text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
                                    }`}
                                  >
                                    {sc}
                                  </button>
                                ))}
                              </div>
                              <button
                                type="button"
                                onClick={() => setIntentSort(intentSort === 'score' ? 'name' : 'score')}
                                title={intentSort === 'score' ? 'Sorted by composite score — click to sort A-Z' : 'Sorted A-Z — click to sort by composite score'}
                                className="flex items-center gap-1 px-2.5 py-1.5 rounded-xl border border-slate-300 bg-slate-50 text-[11px] font-bold text-slate-600 hover:text-slate-900 transition"
                              >
                                <ArrowUpDown className="w-3.5 h-3.5" />
                                <span>{intentSort === 'score' ? 'Score' : 'A-Z'}</span>
                              </button>
                            </div>
                            )}
                          </div>

                          {/* The provenance strip (sources, domain match, observation
                              date, refresh, mapping rules) was removed at the client's
                              request (refinements, 6 Oct): it is backend detail. */}

                          {/* Topics grouped by dictionary theme. Group numbers come from the backend summary, so a filter never changes them. */}
                          <div className="space-y-4 pt-2">
                            {!hpGrouped && themes.filter((t: any) => t.theme !== 'Other / Low Relevance' && t.topic_count > 0).map((theme: any) => {
                              const style = THEME_STYLE[theme.theme] || THEME_STYLE['Other / Low Relevance'];
                              const shown = filteredTopics.filter((x: any) => x.included && x.theme === theme.theme);
                              // Collapsed by default; a search opens the groups it matched.
                              const themeOpen = !!expandedIntentThemes[theme.theme]
                                || (intentSearch.trim() !== '' && shown.length > 0);
                              return (
                                <div key={theme.theme} className={`bg-white rounded-2xl p-5 border ${style.border} shadow-xs space-y-3`}>
                                  {/* Collapsed by default (Sahaj, 27 Sep): the header carries
                                      the numbers, the rows open on demand. */}
                                  <button
                                    type="button"
                                    onClick={() => setExpandedIntentThemes((prev) => ({ ...prev, [theme.theme]: !prev[theme.theme] }))}
                                    className="w-full flex items-center justify-between gap-2 text-left"
                                    aria-expanded={themeOpen}
                                  >
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-extrabold border ${style.chip}`}>{theme.theme}</span>
                                      <span className="text-xs font-semibold text-slate-500">
                                        {/* The count alone. The average said
                                            little - every theme on a real
                                            export sits in the sixties - and
                                            the strongest score is already the
                                            bar above and the first row below. */}
                                        {theme.topic_count} topics
                                        {shown.length !== theme.topic_count ? ` • showing ${shown.length}` : ''}
                                      </span>
                                    </div>
                                    <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform ${themeOpen ? 'rotate-180' : ''}`} />
                                  </button>
                                  {themeOpen && (
                                    <div className="space-y-2 border-t border-slate-100 pt-2.5">
                                      {shown.map((item: any, idx: number) => renderTopicRow(item, idx, style.bar))}
                                    </div>
                                  )}
                                </div>
                              );
                            })}

                            {!hpGrouped && otherTheme && otherTheme.topic_count > 0 && (() => {
                              const shown = filteredTopics.filter((x: any) => x.included && x.theme === 'Other / Low Relevance');
                              // Open like every other theme group: a search opens
                              // it, otherwise the button decides. It used to toggle
                              // between the whole list and the first five rows,
                              // with the flagged list rendered either way - so on
                              // an account with flagged topics "Collapse" looked
                              // like it did nothing.
                              const otherOpen = isOtherTopicsExpanded
                                || (intentSearch.trim() !== '' && shown.length > 0);
                              return (
                                <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-3">
                                  <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-slate-100 text-slate-700 border border-slate-200">Other / Low Relevance</span>
                                      <span className="text-xs font-semibold text-slate-500">
                                        {/* The dictionary version and the
                                            flagged count were ours to act on,
                                            not the seller's to read. */}
                                        {otherTheme.topic_count} topics
                                      </span>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => setIsOtherTopicsExpanded(!isOtherTopicsExpanded)}
                                      className="text-xs font-bold text-hp-navy hover:underline flex items-center gap-1 flex-shrink-0"
                                    >
                                      <span>{otherOpen ? 'Collapse' : `Expand (${shown.length})`}</span>
                                      <ChevronDown className={`w-3.5 h-3.5 transition-transform ${otherOpen ? 'rotate-180' : ''}`} />
                                    </button>
                                  </div>
                                  {/* One list, in the same shape as every other
                                      theme: topic, score, source. The flagged
                                      rows used to sit above it on amber with the
                                      reason the dictionary did not place them -
                                      "Mentions 'financial' but no Financial
                                      Services & Fintech dictionary term". That is
                                      a note to whoever maintains the dictionary,
                                      not to a seller reading the account, and it
                                      made an unmapped topic look like a problem
                                      with the topic. `mapping_status` and
                                      `flag_reason` are still in the payload for
                                      that maintenance. */}
                                  {otherOpen && (
                                    <div className="space-y-2">
                                      {shown.map((item: any, idx: number) => renderTopicRow(item, idx, 'bg-slate-500'))}
                                    </div>
                                  )}
                                </div>
                              );
                            })()}

                            {(excludedTopics.length > 0 || duplicatesRemoved.length > 0) && (
                              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-[11px] text-slate-600 space-y-1">
                                <span className="text-slate-500 font-bold uppercase text-[10px] block">Not in any summary</span>
                                {/* exclusion_reason stays in the payload; the client sees the topic only. */}
                                {excludedTopics.map((t: any) => (
                                  <div key={`x-${t.topic_name}`}><span className="font-semibold capitalize">{t.topic_name}</span></div>
                                ))}
                                {duplicatesRemoved.map((d: any, i: number) => (
                                  <div key={`d-${i}`}><span className="font-semibold capitalize">{d.topic_name}</span>: duplicate row (score {d.composite_score ?? NO_SIGNAL}) removed; kept score {d.kept_score ?? NO_SIGNAL}</div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Hiring-linked demand: dropped for now (Sahaj, 27 Sep - BridgeAI will come back on it). */}

                      {/* Hiring Signals - Hiring_Signals_Rule_Set_Final.docx, laid out as the
                          Australia Post worked example. The jobs are the ones the Executive
                          Dashboard's job postings tile counts. */}
                      {(() => {
                        const pick = (key: string) => {
                          const w = widgets.find(x => x.widget_key === key);
                          return (w && w.status === 'available' && w.data) ? w.data : null;
                        };
                        const summary = pick('hiring_postings_summary');
                        const families = pick('hiring_family_breakdown');
                        const tags = pick('hiring_tech_tags');
                        const cards = pick('hiring_theme_cards');

                        // No jobs after the country check and the 12-month window: the
                        // section is left out, never "no data" (rule set).
                        if (!summary) return null;

                        const bars: any[] = families?.bars || [];
                        const maxBar = Math.max(1, ...bars.map((b: any) => b.count || 0));
                        const tagList: any[] = tags?.tags || [];
                        const cardList: any[] = cards?.cards || [];

                        return (
                          <div className="space-y-6 pt-6 border-t border-slate-200">

                            {/* Header */}
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                              <div>
                                <h2 className="text-lg font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                                  <Briefcase className="w-5 h-5 text-hp-navy" />
                                  <span>Hiring Signals</span>
                                  {summary.country_code && (
                                    <span className="px-1.5 py-0.5 rounded bg-blue-50 text-hp-navy border border-blue-200 text-[10px] font-bold">
                                      {summary.country_code}
                                    </span>
                                  )}
                                </h2>
                                <p className="text-xs text-slate-500 mt-0.5">
                                  Job openings{summary.domain ? ` · ${summary.domain}` : ''}
                                </p>
                              </div>
                            </div>

                            {/* Tiles */}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                                <span className="text-xs text-slate-500 block">Job postings</span>
                                <span className="text-3xl font-extrabold text-slate-900 block mt-1">{summary.job_postings}</span>
                                <span className="text-[11px] text-slate-500 block mt-1">{summary.window_label || 'Last 12 months'}</span>
                              </div>
                              {summary.hybrid_count > 0 && (
                                <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                                  <span className="text-xs text-slate-500 block">Hybrid roles</span>
                                  <span className="text-3xl font-extrabold text-slate-900 block mt-1">{summary.hybrid_pct}%</span>
                                  <span className="text-[11px] text-slate-500 block mt-1">
                                    {summary.hybrid_count} of {summary.job_postings} list hybrid, remote or work from home
                                  </span>
                                </div>
                              )}
                            </div>

                            {/* What they're hiring for + tech named in job ads */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                              {bars.length > 0 && (
                                <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                                  <h3 className="text-sm font-bold text-slate-900 mb-4">What they&apos;re hiring for</h3>
                                  <div className="space-y-2.5">
                                    {bars.map((b: any, barIdx: number) => (
                                      <div key={b.family} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_2rem] items-center gap-3">
                                        <span className="text-xs text-slate-700 truncate" title={b.family}>{b.family}</span>
                                        <div className="h-2.5 bg-slate-100 rounded-full overflow-hidden">
                                          <div className="as-grow h-full bg-hp-navy rounded-full" style={{ width: `${(b.count / maxBar) * 100}%`, ['--as-d' as string]: `${growDelay(barIdx)}ms` }} />
                                        </div>
                                        <span className="text-xs font-bold text-slate-900 text-right tabular-nums"><CountUpText text={b.count} delay={growDelay(barIdx)} /></span>
                                      </div>
                                    ))}
                                  </div>
                                  <div className="flex justify-between border-t border-slate-200 mt-4 pt-3 text-xs font-bold text-slate-900">
                                    <span>Total postings</span>
                                    <span className="tabular-nums"><CountUpText text={families?.total} /></span>
                                  </div>
                                </div>
                              )}
                              {tagList.length > 0 && (
                                <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs">
                                  <h3 className="text-sm font-bold text-slate-900 mb-4">Tech named in job ads</h3>
                                  <div className="flex flex-wrap gap-2">
                                    {tagList.map((t: any) => (
                                      <span key={t.tag} title={`${t.jobs} job${t.jobs === 1 ? '' : 's'}`}
                                        className="px-2.5 py-1 rounded-md border border-slate-200 text-[11px] text-slate-700 bg-white">
                                        {t.tag}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Hiring signals for HP - one card per theme with jobs */}
                            {cardList.length > 0 && (
                              <div className="space-y-4">
                                <h3 className="text-base font-extrabold text-slate-900">Hiring signals for HP</h3>
                                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 items-start">
                                  {cardList.map((c: any) => (
                                    <div key={c.theme_key} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-4">
                                      <div className="flex items-start justify-between gap-3">
                                        <h4 className="text-sm font-bold text-slate-900 leading-snug">{c.theme}</h4>
                                        <span className="text-xs font-bold text-hp-navy whitespace-nowrap">
                                          {c.job_count} job{c.job_count === 1 ? '' : 's'}
                                        </span>
                                      </div>
                                      <div className="bg-slate-50 rounded-xl p-3">
                                        <span className="text-[10px] font-extrabold uppercase tracking-wider text-hp-navy block mb-2">Jobs found</span>
                                        <ul className="space-y-1.5">
                                          {(c.titles || []).map((t: any) => (
                                            <li key={t.title} className="text-xs text-slate-700 flex gap-2">
                                              <span className="text-slate-400">•</span>
                                              <span>{t.title}{t.posted > 1 ? ` (posted ${t.posted}×)` : ''}</span>
                                            </li>
                                          ))}
                                        </ul>
                                        {/* The rest of the titles behind "+ N more jobs"
                                            (refinements, 6 Oct). A card built before
                                            more_titles existed keeps the plain count. */}
                                        {c.more_jobs > 0 && ((c.more_titles || []).length > 0 ? (
                                          <details className="group mt-1.5">
                                            <summary className="as-summary cursor-pointer list-none text-[11px] font-semibold text-hp-navy pl-4 flex items-center gap-1">
                                              + {c.more_jobs} more job{c.more_jobs === 1 ? '' : 's'}
                                              <ChevronDown className="as-chevron w-3 h-3" />
                                            </summary>
                                            <ul className="space-y-1.5 mt-1.5 max-h-64 overflow-y-auto">
                                              {c.more_titles.map((t: any) => (
                                                <li key={t.title} className="text-xs text-slate-700 flex gap-2">
                                                  <span className="text-slate-400">•</span>
                                                  <span>{t.title}{t.posted > 1 ? ` (posted ${t.posted}×)` : ''}</span>
                                                </li>
                                              ))}
                                            </ul>
                                          </details>
                                        ) : (
                                          <span className="text-[11px] text-slate-500 block mt-1.5 pl-4">+ {c.more_jobs} more job{c.more_jobs === 1 ? '' : 's'}</span>
                                        ))}
                                      </div>
                                      <div className="border-t border-slate-200 pt-3 space-y-3">
                                        {[['HP product', c.hp_product], ['HP service', c.hp_service], ['HP solution', c.hp_solution]]
                                          .filter(([, v]) => v)
                                          .map(([label, value]) => (
                                            <div key={label}>
                                              <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">{label}</span>
                                              <span className="text-xs text-slate-800 block mt-0.5">{value}</span>
                                            </div>
                                          ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  );
                })()}

                {/* Solution Narrative / Opportunity Map View (Feature Key: solution_narrative_opportunity_map) */}
                {activeFeatureKey === 'solution_narrative_opportunity_map' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'opportunity_context_card');
                  const triggerWidget = widgets.find(w => w.widget_key === 'opportunity_trigger_signals');

                  const contextData = (contextWidget && contextWidget.status === 'available' && contextWidget.data) ? contextWidget.data : null;
                  const triggerData = (triggerWidget && triggerWidget.status === 'available' && triggerWidget.data) ? triggerWidget.data : null;

                  const busDesc = contextData?.business_description || '';
                  const techStackList = contextData?.full_tech_stack_sample || [];
                  const intentTopics = contextData?.top_intent_topics || [];
                  const triggerSignals = triggerData?.triggers || [];

                  const playsWidget = widgets.find(w => w.widget_key === 'opportunity_narrative_plays');
                  const playsData = playsWidget?.data || {};
                  const generatedPlays: any[] = playsData.opportunity_plays || [];
                  // Plays failing the HP-fit check are not opportunities; they are
                  // retained separately as discovery gaps, with no sales narrative.
                  const discoveryAreas: any[] = playsData.discovery_areas || [];
                  const servicePlays: any[] = playsData.service_plays || [];
                  const isAvailable = playsWidget?.status === 'available' && generatedPlays.length > 0;

                  return (
                    <div className="space-y-6 animate-fade-in">
                      <PendingNotice widget={playsWidget} title="Opportunity plays unavailable" />
                      
                      {/* Header Banner */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Lightbulb className="w-6 h-6 text-hp-navy" />
                            <span>Opportunity Map</span>
                          </h2>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {isAvailable ? generatedPlays.length : 0} HP {isAvailable && generatedPlays.length === 1 ? 'opportunity' : 'opportunities'} mapped for {selectedAccount?.name} &mdash; business outcome, HP products, entry path, and evidence in one view.
                          </p>
                          {discoveryAreas.length > 0 && (
                            <p className="text-xs text-slate-500 mt-0.5">
                              {discoveryAreas.length} additional discovery {discoveryAreas.length === 1 ? 'area' : 'areas'} identified &mdash; listed separately below, not presented as HP opportunities.
                            </p>
                          )}
                          {/* Stated once here rather than repeated on every card.
                              The first sentence used to say no proof-point source was
                              connected; HP's published case studies now are. The second
                              is unchanged and still matters. */}
                          <p className="text-[11px] text-slate-400 mt-1 max-w-3xl leading-relaxed">
                            Proof points are published HP case studies about other customers, shown
                            only where one supports an HP product this play already names. The HP
                            links on each play are product reference pages, not evidence about this
                            account, and a play without a proof point simply has none in the corpus.
                          </p>
                        </div>

                        <div className="flex items-center space-x-2 text-xs font-bold">
                          <span className="px-3 py-1 bg-white border border-slate-200 shadow-xs rounded-full text-slate-700">
                            {isAvailable ? generatedPlays.length : 0} HP Plays
                          </span>
                          {/* Nothing is badged while it is working, and under
                              the client's "write nothing" ruling the not-ready
                              badge is suppressed too. */}
                          {!isAvailable && SHOW_EMPTY_STATE_NOTICES && (
                            <span className="px-3 py-1 rounded-full bg-purple-50 text-purple-800 border border-purple-200">
                              Inferred TBD
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Opportunity Plays List */}
                      <div className="space-y-5">
                        <div className="flex items-center justify-between">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <span>HP OPPORTUNITY PLAYS</span>
                            <span className="text-slate-400">({isAvailable ? generatedPlays.length : 0} PRODUCT LINES)</span>
                          </h3>
                          {getClassificationBadge('inferred')}
                        </div>

                        {isAvailable ? (
                          /* Render generated plays, matching the Northstar UI */
                          <div className="space-y-8">
                            {generatedPlays.map((play: any, pIdx: number) => {
                              return (
                                <div key={pIdx} className="space-y-3">
                                  {/* Category Divider Bar */}
                                  <div className="relative flex items-center justify-center my-4">
                                    <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200"></div></div>
                                    <span className="relative bg-slate-100 px-4 text-[10px] font-mono font-extrabold uppercase tracking-widest text-slate-500 rounded-full border border-slate-200">
                                      — {play.category_label || play.play_key || 'OPPORTUNITY PLAY'} —
                                    </span>
                                  </div>

                                  {/* Card Body - laid out to match the Northstar reference card */}
                                  <div className={`bg-white rounded-xl border border-slate-200 border-l-4 shadow-xs p-5 space-y-3.5 ${
                                    play.priority === 'Critical' ? 'border-l-rose-500'
                                      : play.priority === 'High' ? 'border-l-amber-500'
                                      : play.priority === 'Medium' ? 'border-l-sky-400'
                                      : 'border-l-slate-300'
                                  }`}>

                                    {/* Header: title left, evidence-checks pill right */}
                                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                                      <div className="flex items-center space-x-2 min-w-0">
                                        <Compass className="w-4 h-4 text-slate-400 flex-shrink-0" />
                                        <h4 className="text-base font-bold text-slate-900">{play.title || 'HP Opportunity Play'}</h4>
                                      </div>

                                      <div className="flex flex-col items-start sm:items-end gap-0.5 flex-shrink-0">
                                        {play.priority && (
                                          <span className="inline-flex items-center gap-0.5">
                                          <span className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${
                                            play.priority === 'Critical' ? 'text-rose-700 bg-rose-50 border-rose-200'
                                              : play.priority === 'High' ? 'text-amber-700 bg-amber-50 border-amber-200'
                                              : play.priority === 'Medium' ? 'text-sky-700 bg-sky-50 border-sky-200'
                                              : 'text-slate-600 bg-slate-100 border-slate-200'
                                          }`}>
                                            {play.priority}
                                          </span>
                                          <ScoreInfo topic="opportunityPriority" align="right" />
                                          </span>
                                        )}
                                      </div>
                                    </div>

                                    {/* Lead paragraph - the AI reading of the evidence below */}
                                    {play.inference && (
                                      <p className="text-sm text-slate-700 leading-relaxed">{play.inference}</p>
                                    )}

                                    {/* HOW HP ENABLES - general product capability, never an account fact */}
                                    {play.hp_capability && (
                                      <div className="space-y-1">
                                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                                          HOW HP ENABLES
                                          <span className="normal-case font-normal text-slate-400"> &middot; general HP capability</span>
                                        </span>
                                        <p className="text-sm text-slate-700 leading-relaxed">{play.hp_capability}</p>
                                      </div>
                                    )}

                                    {/* HP PRODUCTS + HP PROOF / RESOURCE */}
                                    <div className="flex flex-wrap items-start justify-between gap-3">
                                      {play.hp_products?.length > 0 && (
                                        <div className="space-y-1">
                                          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                                            HP PRODUCTS
                                          </span>
                                          <div className="flex flex-wrap gap-1.5">
                                            {play.hp_products.map((prod: string, idx: number) => (
                                              <span key={idx} className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full text-[11px] font-medium">
                                                {prod}
                                              </span>
                                            ))}
                                          </div>
                                        </div>
                                      )}

                                      {openableUrl(play.hp_resource_url, sourceLinkCtx) && (
                                        <div className="space-y-1">
                                          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                                            HP RESOURCE
                                            <span className="normal-case font-normal text-slate-400"> &middot; HP product page</span>
                                          </span>
                                          <div className="flex flex-wrap items-center gap-2">
                                            <a
                                              href={openableUrl(play.hp_resource_url, sourceLinkCtx)}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold text-[11px] hover:bg-emerald-100 transition"
                                            >
                                              <Globe className="w-3 h-3 text-emerald-600" />
                                              <span>HP &#8599;</span>
                                            </a>
                                          </div>
                                        </div>
                                      )}
                                    </div>

                                    {/* HP PROOF POINT. A published HP case study about another
                                        customer, chosen in Python from the HP products this play
                                        already names - never written by the model, and never
                                        evidence about this account. The customer and the link are
                                        the point: this is the one place a seller can cite a public
                                        HP source to a customer. Most plays carry none, which is the
                                        correct answer rather than a gap. */}
                                    {play.hp_proof_point && (
                                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                          <Award className="w-4 h-4 text-amber-600" />
                                          <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
                                            HP Proof Point
                                          </p>
                                        </div>
                                        <p className="text-sm text-amber-900 leading-relaxed">{play.hp_proof_point}</p>
                                        {play.hp_proof_point_detail && (
                                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-amber-700">
                                            <span className="font-semibold">{play.hp_proof_point_detail.customer}</span>
                                            {play.hp_proof_point_detail.industry && (
                                              <span>{play.hp_proof_point_detail.industry}</span>
                                            )}
                                            {/* `hp_product` is deliberately NOT shown - see the
                                                objection card for why the tag contradicts the text. */}
                                            {openableUrl(play.hp_proof_point_detail.source_url, sourceLinkCtx) && (
                                              <a
                                                href={openableUrl(play.hp_proof_point_detail.source_url, sourceLinkCtx)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="underline hover:text-amber-900"
                                              >
                                                View the HP case study
                                              </a>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {/* The entry-path box - timeline, target
                                        buyers and the recommended CTA - was
                                        deleted on the client's instruction,
                                        27 Sep, along with the quantified impact
                                        and supporting signal boxes above it.
                                        The checks row below is what remains. */}
                                    <div className="space-y-2.5">
                                      {play.checks && (
                                        <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
                                          {/* Failed checks stay in the payload (and data_gaps); only passed ones are shown. */}
                                          {Object.entries(play.checks).filter(([, passed]: [string, any]) => passed).map(([name]: [string, any]) => (
                                            <span key={name} className="text-[10px] text-emerald-700">
                                              {'\u2713'} {name.replace(/_/g, ' ')}
                                            </span>
                                          ))}
                                        </div>
                                      )}
                                    </div>


                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        ) : !SHOW_EMPTY_STATE_NOTICES ? null : (
                          /* Inferred TBD Placeholder State */
                          <div className="space-y-4">
                            {[
                              { key: 'workstation', name: 'Z by HP Workstations', group: 'WORKSTATION' },
                              { key: 'poly', name: 'Poly collaboration hardware', group: 'POLY' },
                              { key: 'pc', name: 'HP Elite & Pro PCs', group: 'PC' },
                              { key: 'print', name: 'HP Enterprise Printing & Managed Print Services', group: 'PRINT' },
                              { key: '3d', name: 'HP Multi Jet Fusion (3D)', group: '3D' }
                            ].map((play) => (
                              <div key={play.key} className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                                <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                                  <div className="flex items-center space-x-3">
                                    <h4 className="text-base font-extrabold text-slate-900">{play.name}</h4>
                                    <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-2 py-0.5 rounded uppercase">
                                      {play.group}
                                    </span>
                                  </div>
                                  <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200">
                                    Inferred TBD
                                  </span>
                                </div>

                                <div className="bg-amber-50/60 border border-amber-200/80 rounded-xl p-6 text-center space-y-2">
                                  <div className="w-8 h-8 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto border border-amber-300">
                                    <Sparkles className="w-4 h-4 text-amber-600" />
                                  </div>
                                  <h5 className="text-xs font-black text-amber-900 uppercase tracking-wider">
                                    Opportunity Narrative Play Generation — Inferred TBD
                                  </h5>
                                  <p className="text-[11px] text-amber-800 max-w-md mx-auto leading-relaxed">
                                    The business outcome and the recommended HP product family for <strong className="text-amber-950">{play.name}</strong> will be generated automatically when account datasets are uploaded.
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* HP services the account's evidence earns, from the HP 220
                          Account Rulebook. A different kind of thing from the plays
                          above: those are a model's reading of the account, these are
                          a rule the account matched, and every sentence in them is
                          HP's own approved wording rather than generated copy. */}
                      {servicePlays.length > 0 && (
                        <div className="space-y-3 pt-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-600 flex items-center gap-2">
                            <BookOpen className="w-3.5 h-3.5 text-hp-navy" />
                            <span>Recommended HP services</span>
                            {servicePlays.length > 0 && (
                              <span className="text-slate-400">({servicePlays.length})</span>
                            )}
                          </h3>
                          {/* The rulebook wording (what HP says, how HP requires it to
                              be put) moved to Admin -> Rules at the client's request
                              (refinements, 6 Oct). The services the account earns stay. */}

                          {servicePlays.map((play: any, i: number) => (
                            <div key={i} className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3">
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <div>
                                  <div className="flex items-center gap-2 flex-wrap">
                                    {/* Section 3: the rule id is backend logic.
                                        The opportunity type beside it is the
                                        capability, which is what the doc asks
                                        a seller to be shown instead. */}
                                    {isXRayOn && (
                                      <span className="text-[10px] font-mono font-bold text-hp-navy bg-blue-50 border border-blue-200 px-1.5 py-0.5 rounded">
                                        {play.rule_label}
                                      </span>
                                    )}
                                    <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                                      {play.opportunity_type}
                                    </span>
                                    {play.selection === 'secondary' && (
                                      <span className="text-[10px] font-semibold text-slate-500">
                                        second play &middot; separate evidence
                                      </span>
                                    )}
                                  </div>
                                  <h4 className="text-sm font-extrabold text-slate-900 mt-1">{play.title}</h4>
                                </div>
                              </div>

                              {/* C 07: "leave out the recommendation or label the missing
                                  condition clearly." This is the labelling branch. */}
                              {(play.unverified_conditions || []).length > 0 && (
                                <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
                                  <span className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider block">
                                    Points to confirm
                                  </span>
                                  {play.unverified_conditions.map((c: string, j: number) => (
                                    <p key={j} className="text-[12px] text-slate-700 leading-relaxed">{c}</p>
                                  ))}
                                </div>
                              )}

                              {/* The narrowing the rule itself asks for. WXP 07 ends
                                  "Mention only the integration that matches the account
                                  evidence", so listing all six routes when the account
                                  runs two of them leaves the seller doing HP's work. */}
                              {(play.named_in_rule || []).length > 0 && (
                                <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-3">
                                  <span className="text-[10px] font-semibold text-emerald-700 uppercase tracking-wider block mb-1">
                                    Integration routes this account runs
                                  </span>
                                  <p className="text-[13px] text-emerald-900 font-semibold leading-relaxed">
                                    {play.named_in_rule.join(', ')}
                                  </p>
                                </div>
                              )}

                              {/* The supporting-signal block that stood here, and the
                                  entry path below it, were deleted on the client's
                                  instruction, 27 Sep. `account_evidence` is still what
                                  admits the play - it is simply no longer read out. */}
                            </div>
                          ))}

                          {/* The "PRINT 04 withheld ... " / "HP IQ not offered ... "
                              notes were removed on the client's instruction, 28 Sep.
                              They are rulebook bookkeeping, not something a seller
                              acts on. Still recorded in `service_notes` on the
                              widget, so why a family is absent is still answerable. */}
                        </div>
                      )}

                      {/* Discovery / evidence gaps - areas the data raises but does not
                          support as an HP opportunity. Deliberately reduced: no HP
                          capability, no products, no CTA. */}
                      {discoveryAreas.length > 0 && (
                        <div className="space-y-3 pt-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-600 flex items-center gap-2">
                            <Compass className="w-3.5 h-3.5 text-slate-400" />
                            <span>Discovery areas</span>
                            <span className="text-slate-400">({discoveryAreas.length})</span>
                          </h3>
                          <p className="text-[11px] text-slate-400 max-w-3xl leading-relaxed">
                            Areas worth exploring with the account: what the evidence shows
                            and what to confirm.
                          </p>

                          {discoveryAreas.map((area: any, i: number) => (
                            <div key={area.play_key || i} className="bg-slate-50 rounded-xl border border-dashed border-slate-300 p-4 space-y-2.5">
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <p className="text-sm font-semibold text-slate-700">{area.title}</p>
                                {area.priority && (
                                  <span className="text-[11px] font-semibold text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded flex-shrink-0">
                                    {area.priority}
                                  </span>
                                )}
                              </div>

                              {area.scale_statement && (
                                <div>
                                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">What the data shows</span>
                                  <p className="text-xs text-slate-600 leading-relaxed">{area.scale_statement}</p>
                                </div>
                              )}

                              {area.timing_note && (
                                <div>
                                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">What to confirm</span>
                                  <p className="text-xs text-slate-600 leading-relaxed">{area.timing_note}</p>
                                </div>
                              )}

                              {/* No raw evidence quotes and no "who to ask" here either:
                                  the supporting-signal and target-buyer boxes were dropped
                                  from the Opportunity Map on 27 Sep (Sahaj 5.1). */}
                            </div>
                          ))}
                        </div>
                      )}

                    </div>
                  );
                })()}

                {/* Stakeholder Map View (Feature Key: stakeholder_map) */}
                {activeFeatureKey === 'stakeholder_map' && (() => {
                  const gridWidget = widgets.find(w => w.widget_key === 'stakeholder_contacts_grid');
                  const influenceWidget = widgets.find(w => w.widget_key === 'stakeholder_influence_map');
                  const talkingWidget = widgets.find(w => w.widget_key === 'stakeholder_talking_points');

                  const gridData = (gridWidget && gridWidget.status === 'available' && gridWidget.data) ? gridWidget.data : null;
                  const influenceData: any = influenceWidget?.data || {};
                  const talkingPoints: Record<string, any> = talkingWidget?.data?.talking_points || {};

                  const contactsList: any[] = gridData?.contacts || [];
                  const deptDist: Record<string, any> = gridData?.department_distribution || {};
                  const departmentGroups: any[] = influenceData.department_groups || [];

                  // Filter option lists are derived from the data, never hardcoded.
                  const uniq = (vals: any[]) => Array.from(new Set(vals.filter(Boolean))).sort() as string[];
                  const seniorityOptions = uniq(contactsList.map(c => c.seniority_band));
                  const departmentOptions = uniq(contactsList.map(c => c.normalized_department));

                  const matchesFilters = (c: any) => {
                    if (stakeholderSearch) {
                      const q = stakeholderSearch.toLowerCase().trim();
                      const hay = `${c.full_name || ''} ${c.title || ''} ${c.normalized_department || ''}`.toLowerCase();
                      if (!hay.includes(q)) return false;
                    }
                    if (stakeholderDeptFilter !== 'ALL' && c.normalized_department !== stakeholderDeptFilter) return false;
                    if (stakeholderSeniorityFilter !== 'ALL' && c.seniority_band !== stakeholderSeniorityFilter) return false;
                    return true;
                  };

                  const filteredContacts = contactsList.filter(matchesFilters);
                  const filteredIds = new Set(filteredContacts.map(c => c.contact_id));
                  // The detailed cards used to be the composite-score selection
                  // ("Priority Contacts"). They are now the C-Suite and VP rows:
                  // a seniority band read off the title in the uploaded file,
                  // which is an answer we can give when asked how it was picked.
                  // Python already returns the roster in seniority order.
                  const seniorContacts = filteredContacts.filter(
                    c => c.seniority_band === 'C-Suite' || c.seniority_band === 'VP');
                  // Everyone the senior rule leaves out. Python already returns
                  // the roster in seniority order, so this keeps that order.
                  const otherContacts = filteredContacts.filter(
                    c => c.seniority_band !== 'C-Suite' && c.seniority_band !== 'VP');
                  const byId: Record<string, any> = {};
                  contactsList.forEach(c => { byId[c.contact_id] = c; });

                  const initialsOf = (name: string) =>
                    (name || '?').split(' ').filter(Boolean).map(n => n[0]).join('').substring(0, 2).toUpperCase();

                  const linkedinHref = (url: string) => url.startsWith('http') ? url : `https://${url}`;

                  const seniorityBadge: Record<string, string> = {
                    'C-Suite': 'bg-purple-100 text-purple-700',
                    'VP': 'bg-blue-100 text-blue-700',
                    'Director': 'bg-green-100 text-green-700',
                    'Manager': 'bg-yellow-100 text-yellow-700',
                    'Individual Contributor': 'bg-gray-100 text-gray-600',
                  };

                  // One roster card. Defined once because it is rendered
                  // twice - the senior contacts first, then everybody else -
                  // and two copies of this much JSX drift the first time one
                  // of them is edited.
                  const renderContactCard = (c: any) => {
                                const tp = talkingPoints[c.contact_id] || {};
                                return (
                                  <div key={c.contact_id} className="bg-white rounded-xl border border-slate-200 shadow-xs p-4 space-y-3">

                                    {/* Identity */}
                                    <div className="flex items-start gap-3">
                                      <div className="w-10 h-10 rounded-full bg-sky-50 text-hp-navy flex items-center justify-center text-xs font-bold flex-shrink-0">
                                        {initialsOf(c.full_name)}
                                      </div>
                                      <div className="min-w-0 flex-1">
                                        <div className="flex items-center gap-1.5">
                                          <h5 className="text-sm font-bold text-slate-900 truncate">{c.full_name}</h5>
                                          {c.linkedin_url && (
                                            <a href={linkedinHref(c.linkedin_url)} target="_blank" rel="noreferrer"
                                               title="Open LinkedIn profile"
                                               className="text-slate-400 hover:text-hp-navy flex-shrink-0">
                                              <Linkedin className="w-3.5 h-3.5" />
                                            </a>
                                          )}
                                        </div>
                                        <p className="text-xs text-slate-500 font-normal leading-snug">{c.title || NOT_DISCLOSED}</p>
                                        <p className="text-[11px] text-slate-400 font-normal">{c.normalized_department}</p>
                                      </div>
                                    </div>

                                    {/* Badges */}
                                    <div className="flex flex-wrap gap-1.5">
                                      {renderBadges(c)}
                                    </div>

                                    {/* Contact details */}
                                    <div className="border-t border-slate-100 pt-3 space-y-1.5 text-xs">
                                      <div className="flex items-center gap-2">
                                        <Mail className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                        {c.email
                                          ? <a href={`mailto:${c.email}`} className="text-hp-navy font-medium truncate hover:underline">{c.email}</a>
                                          : <span className="text-slate-400">{NOT_DISCLOSED}</span>}
                                      </div>
                                      <div className="flex items-center gap-2 flex-wrap">
                                        <Phone className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                        {c.phone
                                          ? <span className="text-slate-700 font-normal">{c.phone}</span>
                                          : <span className="text-slate-400">{NOT_DISCLOSED}</span>}
                                        {c.contact_location && (
                                          <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">{c.contact_location}</span>
                                        )}
                                      </div>
                                      {c.email_status && (
                                        <p className="text-[10px] text-slate-400 italic">Email status: {c.email_status}</p>
                                      )}
                                    </div>

                                    {/* How to open */}
                                    {tp.how_to_open ? (
                                      <div className="bg-sky-50/70 border border-sky-100 rounded-lg p-3 space-y-1">
                                        <span className="text-[11px] font-semibold text-hp-navy uppercase tracking-wider block">How to open</span>
                                        <p className="text-xs text-slate-700 font-normal leading-relaxed">{tp.how_to_open}</p>
                                      </div>
                                    ) : (
                                      <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>
                                    )}

                                    {/* Label / value rows */}
                                    {(tp.hp_play_focus || tp.decision_power) && (
                                      <div className="space-y-1.5">
                                        {tp.hp_play_focus && (
                                          <div className="flex gap-2">
                                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider w-24 flex-shrink-0 pt-0.5">HP play focus:</span>
                                            <span className="text-xs text-slate-700 font-normal leading-relaxed">{tp.hp_play_focus}</span>
                                          </div>
                                        )}
                                        {tp.decision_power && (
                                          <div className="flex gap-2">
                                            <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider w-24 flex-shrink-0 pt-0.5">Decision power:</span>
                                            <span className="text-xs text-slate-700 font-normal leading-relaxed">{tp.decision_power}</span>
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {Array.isArray(tp.pain_points) && tp.pain_points.length > 0 && (
                                      <div className="space-y-1">
                                        <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Potential pain points <span className="normal-case font-normal">(inferred)</span></span>
                                        <ul className="space-y-0.5">
                                          {tp.pain_points.map((p: string, i: number) => (
                                            <li key={i} className="text-[11px] text-slate-600 font-normal flex gap-1.5">
                                              <span className="text-red-400 flex-shrink-0">&bull;</span>
                                              <span>{p}</span>
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                );
                  };


                  const handleExportCsv = () => {
                    // No influence, priority, HP relevance, composite score or
                    // priority flag: a sheet the client forwards must not carry
                    // the numbers we agreed on 27 Sep not to stand behind. Nor the
                    // data tool a contact came from (refinements, 6 Oct).
                    const cols = ['full_name', 'title', 'normalized_department', 'seniority_band',
                      'email', 'email_status', 'phone', 'linkedin_url'];
                    const esc = (v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`;
                    const rows = filteredContacts.map((c: any) => {
                      const tp = talkingPoints[c.contact_id] || {};
                      return [...cols.map(k => esc(c[k])), esc(tp.how_to_open), esc(tp.hp_play_focus), esc(tp.decision_power)].join(',');
                    });
                    const header = [...cols, 'how_to_open', 'hp_play_focus', 'decision_power'];
                    const csv = [header.join(','), ...rows].join('\n');
                    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `stakeholders_${selectedAccount?.name || 'account'}.csv`.replace(/\s+/g, '_');
                    a.click();
                    URL.revokeObjectURL(url);
                  };

                  const renderFilter = (label: string, value: string, onChange: (v: string) => void, options: string[]) => (
                    <select
                      value={value}
                      onChange={(e) => onChange(e.target.value)}
                      className="text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-hp-navy"
                    >
                      <option value="ALL">{label}</option>
                      {options.map(o => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  );

                  // Seniority only. The influence and priority chips that sat
                  // beside it are gone with their filters.
                  const renderBadges = (c: any) => (
                    <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${seniorityBadge[c.seniority_band] || 'bg-gray-100 text-gray-600'}`}>{c.seniority_band}</span>
                  );

                  // Email / phone block, shared by the expandable card once revealed.
                  const renderContactLines = (c: any) => (
                    <div className="space-y-1 text-xs">
                      <p className="text-slate-600 font-normal">
                        <span className="text-slate-500">Email: </span>
                        {c.email
                          ? <a href={`mailto:${c.email}`} className="text-hp-navy font-medium hover:underline">{c.email}</a>
                          : <span className="text-slate-400">{NOT_DISCLOSED}</span>}
                      </p>
                      <p className="text-slate-600 font-normal flex items-center gap-1.5 flex-wrap">
                        <span className="text-slate-500">Phone: </span>
                        {c.phone
                          ? <span>{c.phone}</span>
                          : <span className="text-slate-400">{NOT_DISCLOSED}</span>}
                        {c.contact_location && (
                          <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">{c.contact_location}</span>
                        )}
                      </p>
                    </div>
                  );

                  // One expandable card, used by both All Departments and Top Contacts.
                  const renderExpandableCard = (c: any) => {
                    const tp = talkingPoints[c.contact_id] || {};
                    const isOpen = expandedContacts[c.contact_id] || false;
                    const isRevealed = revealedContacts[c.contact_id] || false;
                    const bullets: string[] = [];
                    if (tp.how_to_open) bullets.push(tp.how_to_open);
                    if (tp.hp_play_focus) bullets.push(`HP play focus: ${tp.hp_play_focus}`);
                    if (tp.decision_power) bullets.push(`Decision power: ${tp.decision_power}`);

                    return (
                      <div key={c.contact_id} className="bg-white rounded-xl border border-slate-200 overflow-hidden">
                        <button
                          type="button"
                          onClick={() => setExpandedContacts(prev => ({ ...prev, [c.contact_id]: !prev[c.contact_id] }))}
                          className="w-full flex items-center gap-3 p-4 text-left hover:bg-slate-50/60 transition"
                        >
                          <div className="w-9 h-9 rounded-full bg-slate-100 text-slate-600 flex items-center justify-center text-[11px] font-semibold flex-shrink-0">
                            {initialsOf(c.full_name)}
                          </div>
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-1.5">
                              <span className="text-sm font-bold text-slate-900">{c.full_name}</span>
                            </div>
                            <p className="text-xs text-slate-500 font-normal leading-snug">
                              {c.title || NOT_DISCLOSED} &middot; <span className="text-slate-400">{c.normalized_department}</span>
                            </p>
                          </div>
                          <div className="hidden sm:flex items-center gap-1.5 flex-wrap justify-end flex-shrink-0">
                            {renderBadges(c)}
                          </div>
                          {c.linkedin_url && (
                            <a
                              href={linkedinHref(c.linkedin_url)}
                              target="_blank"
                              rel="noreferrer"
                              onClick={(e) => e.stopPropagation()}
                              className="text-slate-400 hover:text-hp-navy flex-shrink-0"
                              title="Open LinkedIn profile"
                            >
                              <Linkedin className="w-4 h-4" />
                            </a>
                          )}
                          {isOpen
                            ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0" />
                            : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />}
                        </button>

                        {isOpen && (
                          <div className="border-t border-slate-100 bg-slate-50/50 px-4 py-3 space-y-3">
                            {bullets.length > 0 ? (
                              <div className="space-y-1.5">
                                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Talking points</span>
                                <ul className="space-y-1">
                                  {bullets.map((b, i) => (
                                    <li key={i} className="text-xs text-slate-700 font-normal leading-relaxed flex gap-2">
                                      <span className="text-hp-navy flex-shrink-0">&bull;</span>
                                      <span>{b}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            ) : (
                              <p className="text-[11px] text-slate-400">{NO_SIGNAL}</p>
                            )}

                            {Array.isArray(tp.pain_points) && tp.pain_points.length > 0 && (
                              <div className="space-y-1">
                                <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Potential pain points <span className="normal-case font-normal text-slate-400">(inferred)</span></span>
                                <ul className="space-y-0.5">
                                  {tp.pain_points.map((p: string, i: number) => (
                                    <li key={i} className="text-xs text-slate-600 font-normal flex gap-2">
                                      <span className="text-red-400 flex-shrink-0">&bull;</span>
                                      <span>{p}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                            {isRevealed ? renderContactLines(c) : (
                              <button
                                type="button"
                                onClick={() => setRevealedContacts(prev => ({ ...prev, [c.contact_id]: true }))}
                                className="text-xs font-semibold text-hp-navy hover:underline"
                              >
                                Show Contact Info
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  };

                  return (
                    <div className="space-y-6 animate-fade-in">
                      <PendingNotice widget={talkingWidget} title="Talking points unavailable" />

                      {/* Header */}
                      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 border-b border-slate-200 pb-4">
                        <div>
                          <h3 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                            <Users className="w-5 h-5 text-hp-navy" />
                            <span>Stakeholder Map</span>
                          </h3>
                          <p className="text-sm text-slate-500 mt-0.5">
                            {contactsList.length} contact{contactsList.length === 1 ? '' : 's'} identified for {selectedAccount?.name}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={handleExportCsv}
                          disabled={filteredContacts.length === 0}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 bg-white text-xs font-semibold text-slate-700 hover:bg-slate-50 transition disabled:opacity-40"
                        >
                          <FileSpreadsheet className="w-3.5 h-3.5" />
                          <span>Export CSV</span>
                        </button>
                      </div>

                      {/* Filters */}
                      <div className="flex flex-wrap items-center gap-2">
                        <div className="relative flex-1 min-w-[220px]">
                          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                          <input
                            type="text"
                            value={stakeholderSearch}
                            onChange={(e) => setStakeholderSearch(e.target.value)}
                            placeholder="Search name, title, or department..."
                            className="w-full pl-9 pr-3 py-2 text-xs font-medium bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-hp-navy"
                          />
                        </div>
                        {renderFilter('Seniority', stakeholderSeniorityFilter, setStakeholderSeniorityFilter, seniorityOptions)}
                        {renderFilter('Department', stakeholderDeptFilter, setStakeholderDeptFilter, departmentOptions)}
                        <button
                          type="button"
                          onClick={() => {
                            setStakeholderSearch(''); setStakeholderDeptFilter('ALL'); setStakeholderSeniorityFilter('ALL');
                          }}
                          className="text-xs font-medium text-slate-500 hover:text-slate-800 px-2 py-1.5"
                        >
                          Clear
                        </button>
                      </div>

                      <div className="space-y-6">

                          {/* Senior contacts - three across */}
                          {seniorContacts.length > 0 && (
                          <div className="space-y-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="text-base font-bold text-slate-900">Senior contacts</h4>
                              <span className="text-[10px] font-semibold text-hp-navy bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                                {seniorContacts.length} C-Suite &amp; VP
                              </span>
                              {getClassificationBadge('inferred')}
                            </div>
                            <p className="text-xs text-slate-500 font-normal">
                              The C-Suite and VP contacts on the roster at {selectedAccount?.name} &mdash; each with their own contact details and an opening angle. Every other contact is in the departments below.
                            </p>

                            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                              {seniorContacts.map(renderContactCard)}
                            </div>
                          </div>
                          )}

                          {/* The rest of the roster. The senior block above is
                              the 28 Sep rule - C-Suite and VP, read off the
                              title. It is kept, and everyone else is shown here
                              rather than reduced to a count: at an account whose
                              senior people are titled "Head of ..." that rule
                              surfaces one card out of twenty-three. */}
                          {otherContacts.length > 0 && (
                          <div className="space-y-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="text-base font-bold text-slate-900">All other contacts</h4>
                              <span className="text-[10px] font-semibold text-slate-600 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
                                {otherContacts.length} on the roster
                              </span>
                              {getClassificationBadge('inferred')}
                            </div>
                            <p className="text-xs text-slate-500 font-normal">
                              Everyone else on the roster at {selectedAccount?.name}, most senior
                              first. A &ldquo;Head of&rdquo; title bands as Director rather than VP,
                              so the seniority badge is the title&rsquo;s wording, not a judgement
                              about influence.
                            </p>

                            <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                              {otherContacts.map(renderContactCard)}
                            </div>
                          </div>
                          )}
                          {/* Departments - the whole roster */}
                          <div className="border-t border-slate-200 pt-5 space-y-4">
                            <div className="flex items-center gap-2 flex-wrap">
                              <h4 className="text-base font-bold text-slate-900">All departments</h4>
                              <span className="text-[10px] font-semibold text-slate-500 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded-full">
                                {filteredContacts.length} contact{filteredContacts.length === 1 ? '' : 's'}
                              </span>
                              {getClassificationBadge('derived')}
                            </div>

                            <div className="space-y-2">
                              {departmentGroups.map((g: any) => {
                                // Python returns the department's roster most
                                // senior first. Members used to be split into
                                // "HP-relevant" and "lower relevance" here;
                                // that judgement left the product on 27 Sep.
                                const members = (g.contact_ids || [])
                                  .map((id: string) => byId[id])
                                  .filter((c: any) => c && filteredIds.has(c.contact_id));
                                if (members.length === 0) return null;
                                const isOpen = expandedDepts[g.department] || false;
                                return (
                                  <div key={g.department} className="space-y-2">
                                    <button
                                      type="button"
                                      onClick={() => setExpandedDepts(prev => ({ ...prev, [g.department]: !prev[g.department] }))}
                                      className="flex items-center gap-2 text-left group"
                                    >
                                      <h5 className="text-sm font-bold text-slate-800 group-hover:text-hp-navy transition">{g.department}</h5>
                                      <span className="text-[11px] font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                                        {members.length} contact{members.length === 1 ? '' : 's'}
                                      </span>
                                      {isOpen
                                        ? <ChevronUp className="w-4 h-4 text-slate-400" />
                                        : <ChevronDown className="w-4 h-4 text-slate-400" />}
                                    </button>

                                    {isOpen && (
                                      <div className="space-y-2 pb-2">
                                        {members.map((c: any) => renderExpandableCard(c))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        </div>

                      {/* Department distribution, straight from the uploaded file */}
                      <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-4 space-y-2">
                        <div className="flex items-center justify-between">
                          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                            Raw department distribution ({Object.keys(deptDist).length})
                          </h4>
                          {getClassificationBadge('deterministic')}
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {Object.entries(deptDist).map(([dept, count]: [string, any]) => (
                            <span key={dept} className="text-[11px] font-medium text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-full">
                              {dept} <span className="text-slate-400">{count}</span>
                            </span>
                          ))}
                        </div>
                      </div>

                    </div>
                  );
                })()}

                {activeFeatureKey === 'tech_landscape' && (() => {
                  const mapWidget = widgets.find(w => w.widget_key === 'technographic_map');
                  const matrixWidget = widgets.find(w => w.widget_key === 'tech_stack_matrix');
                  const detectionsWidget = widgets.find(w => w.widget_key === 'tech_detections_reference');
                  const hpRecWidget = widgets.find(w => w.widget_key === 'technographic_hp_recommendations');
                  const hpRecData: any = hpRecWidget?.data || {};
                  const hpRecs: any[] = hpRecData.recommendations || [];

                  const mapData = mapWidget?.data || {};
                  const matrixData = matrixWidget?.data || {};
                  const detectionsData = detectionsWidget?.data || {};

                  const categoriesList: any[] = mapData.categories || [];
                  const displayedCategories = categoriesList.filter((cat: any) => {
                    if (opportunitiesOnly && !cat.is_opportunity) return false;
                    return true;
                  });

                  const totalTechCount = matrixData.total_tech_count ?? 0;
                  const totalDetectionsCount = detectionsData.total_detections_count ?? 0;
                  const detectionsList: any[] = detectionsData.detections || [];

                  // The whole estate, clubbed into the export's own categories.
                  // Python settles the grouping and the order, including the
                  // group for everything the export left uncategorised.
                  const techGroups: any[] = matrixData.category_groups || [];
                  const techSources: Record<string, string> = matrixData.technology_sources || {};
                  const multiCategoryCount: number = matrixData.multi_category_technologies ?? 0;
                  const techQuery = techSearch.trim().toLowerCase();
                  const visibleTechGroups = techGroups
                    .map((g: any) => {
                      if (!techQuery) return g;
                      if (String(g.category).toLowerCase().includes(techQuery)) return g;
                      const hits = (g.technologies || [])
                        .filter((t: string) => t.toLowerCase().includes(techQuery));
                      return hits.length ? { ...g, technologies: hits, count: hits.length } : null;
                    })
                    .filter(Boolean);

                  return (
                    <div className="space-y-6 animate-fade-in">

                      {/* Top Header & Opportunities Toggle */}
                      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-200 pb-4">
                        <div>
                          <h3 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Cpu className="w-6 h-6 text-hp-navy" />
                            <span>Technographic Map</span>
                          </h3>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {/* Two different counts: the full technographics export, and the
                                subset a rule matched into the HP categories below. They are
                                not equal - saying so here stops a reader assuming the cards
                                account for the whole stack. */}
                            {mapData.total_detected_technologies == null ? NO_SIGNAL : <>{mapData.total_detected_technologies} technologies detected in {selectedAccount?.name || 'Target Account'}&apos;s technographics export</>}
                            {typeof mapData.mapped_signal_count === 'number' && mapData.total_detected_technologies != null && (
                              <> &middot; {mapData.mapped_signal_count} map to the {mapData.total_categories ?? 7} HP categories below</>
                            )}
                          </p>
                        </div>

                        {/* Top Action Toggle */}
                        <div className="flex items-center gap-2 self-start md:self-auto">
                          <button
                            onClick={() => setOpportunitiesOnly(!opportunitiesOnly)}
                            className={`px-3.5 py-1.5 rounded-xl text-xs font-extrabold transition flex items-center gap-1.5 shadow-sm ${
                              opportunitiesOnly
                                ? 'bg-hp-navy text-white ring-2 ring-hp-navy ring-offset-1'
                                : 'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50'
                            }`}
                          >
                            <Sparkles className={`w-3.5 h-3.5 ${opportunitiesOnly ? 'text-amber-300' : 'text-slate-400'}`} />
                            <span>Opportunities only</span>
                          </button>
                        </div>
                      </div>

                      {/* Technographic Map Content View */}
                      <div className="space-y-6">
                          {/* STRATEGIC READ Banner */}
                          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-slate-400">
                                STRATEGIC READ
                              </span>
                            </div>
                            {mapData.strategic_read ? (
                              <p className="text-xs text-slate-700 leading-relaxed font-medium">
                                {mapData.strategic_read}
                              </p>
                            ) : (
                              <p className="text-xs text-slate-500 leading-relaxed">
                                Detected technologies and their HP relationship are shown below.
                                The sales narrative and product recommendations are in
                                <span className="font-semibold"> HP Product Recommendations</span>,
                                where they are grounded in HP product sources and filtered for this
                                account&apos;s market.
                              </p>
                            )}

                            {/* Integration routes. Context only, by the
                                client's direction: a detected technology HP
                                names as an integration target shows
                                compatibility, never a need, so it sits outside
                                the recommendation and is styled as a note. */}
                            {(mapData.integration_routes || []).length > 0 && (
                              <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-4 py-3 space-y-1.5">
                                <p className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-slate-400">
                                  Integration routes &middot; context
                                </p>
                                {(mapData.integration_routes || []).map((r: any, i: number) => (
                                  <p key={i} className="text-xs text-slate-600 leading-relaxed">
                                    {r.text}
                                  </p>
                                ))}
                              </div>
                            )}


                            {/* 4 Stat Cards */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                              <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                                {/* Relabelled: this is the whole export, not the subset the
                                    category cards below count. The tile beside it carries
                                    that subset so the two can be read together.

                                    The `|| 21`, `|| '5/7'` and `|| '4/7'` fallbacks these
                                    tiles used to carry were one account's figures, and would
                                    render as another account's real numbers whenever the
                                    widget came back empty. The backend already refuses that
                                    (see tech_landscape.py: "No hardcoded fallback"); an
                                    absent value now reads as absent. */}
                                <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">TECHNOLOGIES IN EXPORT</span>
                                <div className="text-xl font-black font-mono text-slate-900">{mapData.total_detected_technologies ?? <span className="text-xs font-normal font-sans text-slate-400">{NO_SIGNAL}</span>}</div>
                              </div>
                              <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                                <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">MAPPED TO HP CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-slate-900">
                                  {typeof mapData.mapped_signal_count === 'number' && typeof mapData.total_detected_technologies === 'number'
                                    ? `${mapData.mapped_signal_count}/${mapData.total_detected_technologies}`
                                    : <span className="text-xs font-normal font-sans text-slate-400">{NO_SIGNAL}</span>}
                                </div>
                              </div>
                              <div className="bg-blue-50/60 p-3.5 rounded-xl border border-blue-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-blue-800 uppercase tracking-wider block">HP-MAPPED CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-hp-navy">{mapData.hp_mapped_categories ?? <span className="text-xs font-normal font-sans text-slate-400">{NO_SIGNAL}</span>}</div>
                              </div>
                              <div className="bg-emerald-50/60 p-3.5 rounded-xl border border-emerald-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-emerald-800 uppercase tracking-wider block">WHITESPACE CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-emerald-700">{mapData.whitespace_categories ?? <span className="text-xs font-normal font-sans text-slate-400">{NO_SIGNAL}</span>}</div>
                              </div>
                            </div>
                          </div>

                          {/* Category Blocks List */}
                          <div className="space-y-6">
                            {displayedCategories.map((cat: any) => (
                              <div key={cat.category_key} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4 hover:border-slate-300 transition">
                                
                                {/* Category Header */}
                                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-100 pb-3">
                                  <div>
                                    <h4 className="text-sm font-black text-slate-900 flex items-center gap-2">
                                      <Cpu className="w-4 h-4 text-hp-navy" />
                                      <span>{cat.category_name}</span>
                                    </h4>
                                    <p className="text-[11px] font-medium text-slate-500 mt-0.5">
                                      {cat.detected_signals_count} detected signals{cat.whitespace_count > 0 ? ` - ${cat.whitespace_count} whitespace` : ''}
                                    </p>
                                  </div>

                                  {/* Status Badge */}
                                  <div>
                                    {cat.badge_type === 'displacement' && (
                                      <span className="text-[11px] font-extrabold text-red-700 bg-red-50 border border-red-200 px-3 py-1 rounded-full flex items-center gap-1">
                                        <TrendingUp className="w-3 h-3 text-red-600" />
                                        <span>{cat.status_badge}</span>
                                      </span>
                                    )}
                                    {cat.badge_type === 'complementary' && (
                                      <span className="text-[11px] font-extrabold text-blue-700 bg-blue-50 border border-blue-200 px-3 py-1 rounded-full flex items-center gap-1">
                                        <Zap className="w-3 h-3 text-blue-600" />
                                        <span>{cat.status_badge}</span>
                                      </span>
                                    )}
                                    {cat.badge_type === 'contextual' && (
                                      <span className="text-[11px] font-semibold text-slate-600 bg-slate-100 border border-slate-200 px-3 py-1 rounded-full flex items-center gap-1">
                                        <Info className="w-3 h-3 text-slate-400" />
                                        <span>{cat.status_badge}</span>
                                      </span>
                                    )}
                                    {cat.badge_type === 'whitespace' && (
                                      <span className="text-[11px] font-extrabold text-emerald-800 bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full flex items-center gap-1">
                                        <Sparkles className="w-3 h-3 text-emerald-600" />
                                        <span>{cat.status_badge}</span>
                                      </span>
                                    )}
                                  </div>
                                </div>

                                {/* HP RELATIONSHIP - deterministic, from the ABX
                                    status rules. The narrative equivalent lives in
                                    the recommendations widget. */}
                                {(cat.what_it_means || cat.hp_relationship) && (
                                  <div className="bg-blue-50/50 border border-blue-100/80 rounded-xl p-4 space-y-1">
                                    <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-blue-600 block">
                                      {cat.what_it_means ? 'WHAT IT MEANS FOR HP' : 'HP RELATIONSHIP'}
                                    </span>
                                    <p className="text-xs text-slate-700 font-medium leading-relaxed">
                                      {cat.what_it_means || cat.hp_relationship}
                                    </p>
                                    <ProofPoint proof={cat.hp_proof_point} />
                                  </div>
                                )}

                                {/* Vendor Cards Grid */}
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                  {cat.vendors?.map((vendor: any, vIdx: number) => {
                                    if (vendor.is_whitespace) {
                                      return (
                                        <div key={vIdx} className="bg-emerald-50/40 border-2 border-emerald-300/80 rounded-2xl p-4 space-y-3 flex flex-col justify-between">
                                          <div>
                                            <div className="flex items-center justify-between gap-2 border-b border-emerald-200/60 pb-2 mb-2">
                                              <h5 className="text-xs font-black text-slate-900">{vendor.vendor_name}</h5>
                                              <span className="inline-flex items-center gap-0.5">
                                                <span className="text-[10px] font-extrabold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-300">
                                                  {vendor.risk_level}
                                                </span>
                                                <ScoreInfo topic="techRisk" align="right" />
                                              </span>
                                            </div>
                                            <p className="text-xs text-slate-600 font-medium">{vendor.description}</p>

                                            {vendor.hp_play && (
                                              <div className="mt-3 bg-white border border-emerald-200 rounded-xl p-2.5 text-xs text-emerald-900 font-semibold space-y-0.5 shadow-sm">
                                                <span className="font-extrabold text-emerald-800 flex items-center gap-1">
                                                  <Sparkles className="w-3 h-3 text-emerald-600" />
                                                  <span>{vendor.hp_play.product}</span>
                                                </span>
                                                <p className="text-[11px] text-slate-600 font-normal italic pl-4">
                                                  {vendor.hp_play.play_text}
                                                </p>
                                              </div>
                                            )}
                                          </div>

                                          {/* A whitespace card is HP's absence from the
                                              category, not a technology detection, so it
                                              carries no Tech Landscape confidence. Its
                                              detection status is the honest thing to show. */}
                                          <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 border-t border-emerald-200/60 pt-2 flex items-center justify-between">
                                            <span className="truncate pr-2">{vendor.provenance}</span>
                                            <span className="font-bold text-slate-500">{vendor.detection_status}</span>
                                          </div>
                                        </div>
                                      );
                                    }

                                     return (
                                      <div key={vIdx} className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3 flex flex-col justify-between hover:border-slate-300 transition shadow-xs">
                                        <div>
                                          <div className="flex items-center justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
                                            <h5 className="text-xs font-black text-slate-900">{vendor.vendor_name}</h5>
                                            <div>
                                              <div className="flex items-center gap-1.5">
                                                {vendor.risk_level && (
                                                  <span
                                                    className={`text-[10px] font-extrabold px-2 py-0.5 rounded-md border ${
                                                      vendor.risk_level === 'High risk'
                                                        ? 'text-red-700 bg-red-50 border-red-200'
                                                        : vendor.risk_level === 'Medium risk'
                                                        ? 'text-amber-700 bg-amber-50 border-amber-200'
                                                        : 'text-emerald-700 bg-emerald-50 border-emerald-200'
                                                    }`}
                                                  >
                                                    {vendor.risk_level}
                                                  </span>
                                                )}
                                                {vendor.hp_relationship_label && (
                                                  <span
                                                    className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200"
                                                  >
                                                    {vendor.hp_relationship_label}
                                                  </span>
                                                )}
                                                {(vendor.risk_level || vendor.hp_relationship_label) && (
                                                  <ScoreInfo topic="techRisk" align="right" />
                                                )}
                                              </div>
                                            </div>
                                          </div>

                                          <p className="text-xs text-slate-500 font-medium">{vendor.description}</p>

                                          {vendor.hp_play && (
                                            <div className="mt-3 bg-blue-50/80 border border-blue-200/80 rounded-xl p-2.5 text-xs text-hp-navy font-semibold space-y-0.5">
                                              <span className="font-extrabold text-hp-navy flex items-center gap-1 flex-wrap">
                                                <span>&rarr;</span>
                                                <span>{vendor.hp_play.product}</span>
                                                {/* What stands behind this line. A rulebook match
                                                    is an authorised answer; the alternative is the
                                                    model positioning a broad line against a
                                                    detected vendor - reasonable, but not a rule,
                                                    and a seller should be able to tell. */}
                                                {vendor.hp_play.product_source === 'positioning' && (
                                                  <span className="text-[9px] font-medium text-slate-400 normal-case">
                                                    general positioning
                                                  </span>
                                                )}
                                              </span>
                                              <p className="text-[11px] text-slate-600 font-normal italic pl-4">
                                                {vendor.hp_play.play_text}
                                              </p>
                                              {/* The rule used to be quoted in full here. It is
                                                  now a proper recommendation card in this
                                                  category, which carries the same wording plus
                                                  the approved facts and what was withheld - so
                                                  this stays as the pointer that ties THIS vendor
                                                  to that card, and the rule is stated once. */}
                                              {vendor.rulebook_offering && (
                                                <p className="mt-2 pt-2 border-t border-blue-200/70 text-[10px] font-mono text-hp-navy">
                                                  {/* Section 3: the offering is
                                                      the supported capability and
                                                      stays; the rule id that
                                                      selected it is backend logic. */}
                                                  {isXRayOn && (
                                                    <>{vendor.rulebook_offering.rule_label} &middot;{' '}</>
                                                  )}
                                                  {vendor.rulebook_offering.offering}
                                                  <span className="text-slate-400 normal-case font-sans">
                                                    {' '}&mdash; see the HP recommendation below
                                                  </span>
                                                </p>
                                              )}
                                            </div>
                                          )}
                                        </div>

                                        <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 border-t border-slate-100 pt-2 flex items-center justify-between">
                                          <span className="truncate pr-2">{vendor.provenance}</span>
                                          {/* Was the Tech Landscape confidence percentage.
                                              The client, 27 Sep: "I would stay away from
                                              this, hence, let's drop the confidence score."
                                              What is left is whether the export actually
                                              named this vendor, which is the whitespace
                                              card's footer too. The score is still computed
                                              - it decides which cards exist at all. */}
                                          <span
                                            className="font-bold text-slate-500 whitespace-nowrap"
                                            title={vendor.evidence_basis || undefined}
                                          >
                                            {vendor.detection_status}
                                          </span>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>

                                {/* HP recommendations for this category, from
                                    the deck-usage rules. category_key is
                                    assigned in Python from the rule's device
                                    type. */}
                                {hpRecs
                                  .filter((rec: any) => rec.category_key === cat.category_key)
                                  .map((rec: any) => (
                                    <HpRecommendationCard key={rec.rule_id} rec={rec} xray={isXRayOn} />
                                  ))}

                                {/* Rules that WOULD have produced a card in this
                                    category and were refused. Shown here rather
                                    than only at the foot of the page: a category
                                    reading "no HP client hardware detected" with
                                    nothing under it is exactly where a seller
                                    asks why, and the answer was three screens
                                    away under a heading about something else. */}
                                {isXRayOn && (hpRecData.rules_blocked || [])
                                  .filter((b: any) => b.category_key === cat.category_key)
                                  .map((b: any) => (
                                    <div key={`blocked-${b.rule_id}`}
                                         className="text-[11px] text-slate-600 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 mt-2">
                                      <span className="font-semibold">
                                        Rule {b.rule_id} was evaluated and not used.
                                      </span>{' '}
                                      {b.blocked}
                                    </div>
                                  ))}

                               </div>
                             ))}
                          </div>
                      {/* Anything the category mapping could not place, plus the
                          rules that were evaluated and not used - surfaced so a
                          recommendation is never dropped without explanation. */}
                      {hpRecs.filter((r: any) => !r.category_key).map((rec: any) => (
                        <HpRecommendationCard key={rec.rule_id} rec={rec} xray={isXRayOn} />
                      ))}

                      {/* Only the refusals with no category of their own; the
                          rest are shown beside the category they belong to. */}
                      {isXRayOn && (hpRecData.rules_blocked || [])
                        .filter((b: any) => !b.category_key).length > 0 && (
                        <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded px-3 py-2">
                          <span className="font-semibold text-slate-600">Rules evaluated but not used: </span>
                          {(hpRecData.rules_blocked || [])
                            .filter((b: any) => !b.category_key)
                            .map((b: any) => `rule ${b.rule_id} (${b.blocked})`).join('; ')}
                        </div>
                      )}

                      {/* The Website stack panel - the Explorium WebStack totals,
                          the estimated spend and the 298-name list - was removed on
                          the client's instruction, 28 Sep. The widget is still
                          produced: `detected_technologies` falls back to it when an
                          account has no technographics estate at all. */}

                        </div>

                      {/* ---------------------------------------------------------------
                          The whole technology stack, clubbed into the export's own
                          categories. The client, 27 Sep: "we mention about 281
                          technologies detected - we need to club those in relevant
                          categories and show here."

                          They asked for a download beside it in the same sentence, and
                          it shipped; it was removed on 30 Sep. The sheet carried one row
                          per technology with hp_play, hp_category, risk and reason blank
                          on every row HP has no line for - which is most of 281 - and
                          filling those with "No HP play" would have been 281 rows of
                          nothing. The stack on screen is the answer to the request.

                          It sits below the HP categories and changes nothing above it:
                          those cards are the HP-relevant reading of the estate, this is
                          the estate itself. Every group starts closed - the point of the
                          section is that 281 names are reachable, not that they are all
                          on screen. */}
                      {/* The whole stack as cards (Sahaj, 27 Sep: "club those in
                          relevant categories ... refer to the Caterpillar - Tech and
                          Risk Landscape example"). Families are the export's 20
                          columns folded into eight; HP plays, their approved risk
                          label and one-line reason are copied from the category
                          cards above. No score is shown. */}
                      {matrixData.stack_view && (() => {
                        const sv: any = matrixData.stack_view;
                        const q = techSearch.trim().toLowerCase();
                        const shownTechs: any[] = (sv.technologies || []).filter((t: any) =>
                          (stackFamilyFilter === 'ALL' || t.family === stackFamilyFilter)
                          && (stackSourceFilter === 'ALL' || t.source === stackSourceFilter)
                          && (!stackHpOnly || t.hp)
                          && (!q || t.name.toLowerCase().includes(q)
                              || String(t.hp?.hp_play || '').toLowerCase().includes(q)));
                        const filtering = !!q || stackFamilyFilter !== 'ALL' || stackSourceFilter !== 'ALL' || stackHpOnly;
                        const riskChip = (r: string) => {
                          const k = String(r || '').toLowerCase();
                          return k.startsWith('high') ? 'bg-rose-50 text-rose-700 border-rose-200'
                            : k.startsWith('medium') ? 'bg-amber-50 text-amber-700 border-amber-200'
                            : 'bg-emerald-50 text-emerald-700 border-emerald-200';
                        };
                        return (
                          <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-5">
                            <div>
                              <h4 className="text-sm font-extrabold text-slate-900">Combined technology view</h4>
                              <p className="text-[11px] text-slate-500 mt-0.5">
                                {sv.total} technologies for {selectedAccount?.name || 'this account'}, merged and de-duplicated
                                across sources &middot; {sv.hp_relevant_count} support an HP play
                              </p>
                            </div>

                            {/* Filters */}
                            <div className="flex flex-wrap items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl p-3">
                              <select value={stackFamilyFilter} onChange={(e) => setStackFamilyFilter(e.target.value)}
                                className="px-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg">
                                <option value="ALL">All categories</option>
                                {(sv.families || []).map((f: any) => (
                                  <option key={f.family} value={f.family}>{f.family} ({f.count})</option>
                                ))}
                              </select>
                              <select value={stackSourceFilter} onChange={(e) => setStackSourceFilter(e.target.value)}
                                className="px-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg">
                                <option value="ALL">All sources</option>
                                {(sv.sources || []).map((src: any) => (
                                  <option key={src.label} value={src.label}>{src.label} ({src.count})</option>
                                ))}
                              </select>
                              <button type="button" onClick={() => setStackHpOnly(!stackHpOnly)}
                                className={`px-3 py-1.5 text-xs rounded-lg border font-semibold transition ${stackHpOnly ? 'bg-hp-navy text-white border-hp-navy' : 'bg-white text-slate-700 border-slate-200'}`}>
                                HP-relevant only
                              </button>
                              <div className="relative flex-1 min-w-[10rem]">
                                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                                <input type="text" value={techSearch} onChange={(e) => setTechSearch(e.target.value)}
                                  placeholder="Search technologies..."
                                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-hp-navy" />
                              </div>
                            </div>

                            {/* HP opportunities roll-up */}
                            {(sv.opportunities || []).length > 0 && (
                              <div className="bg-blue-50/50 border border-blue-100 rounded-xl p-4 space-y-3">
                                <h5 className="text-xs font-extrabold text-slate-800 flex items-center gap-2">
                                  HP opportunities
                                  <span className="text-[10px] font-bold bg-white border border-blue-200 text-hp-navy px-1.5 rounded">{sv.opportunities.length}</span>
                                </h5>
                                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                  {/* Not clickable (refinements, 6 Oct): the filter it
                                      applied only showed technologies already on the
                                      category cards above. */}
                                  {sv.opportunities.map((o: any) => (
                                    <div key={o.hp_play}
                                      className="text-left bg-white border border-slate-200 rounded-lg px-3 py-2.5">
                                      <span className="block text-sm font-bold text-hp-navy">{o.hp_play}</span>
                                      <span className="block text-[11px] text-slate-500">
                                        {o.technology_count} technolog{o.technology_count === 1 ? 'y' : 'ies'} &rarr; {o.hp_category}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Families, each a grid of technology cards */}
                            {shownTechs.length === 0 ? (
                              <p className="text-xs text-slate-400 italic">No technology matches these filters.</p>
                            ) : (sv.families || []).map((f: any) => {
                              const items = shownTechs.filter((t: any) => t.family === f.family);
                              if (!items.length) return null;
                              // Every group starts closed and opens on a click, with no
                              // React state in the way. A filter opens what it matched by
                              // mounting the group open; the key carries the same flag, so
                              // clearing the filter remounts everything closed. Between
                              // those two moments the browser owns open/closed, which is
                              // the point - the row cannot stop responding.
                              const autoOpen = filtering;
                              return (
                                <details key={`${f.family}:${autoOpen}`} open={autoOpen}
                                  className="group space-y-2">
                                  <summary
                                    className="as-summary w-full flex items-center gap-2 text-left">
                                    <span className="text-xs font-extrabold uppercase tracking-wider text-slate-700">{f.family}</span>
                                    <span className="text-[10px] font-bold bg-slate-100 text-slate-500 px-1.5 rounded">{items.length}</span>
                                    <span className="flex-1" />
                                    <ChevronDown className="as-chevron w-4 h-4 text-slate-400" />
                                  </summary>
                                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2.5">
                                      {items.map((t: any) => (
                                        <div key={t.name}
                                          className={`rounded-lg border px-3 py-2.5 space-y-1.5 ${t.hp ? 'border-blue-200 bg-white' : 'border-slate-200 bg-white'}`}>
                                          <div className="flex items-start justify-between gap-2">
                                            <span className="text-sm font-semibold text-slate-900 leading-tight">{t.name}</span>
                                            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-50 text-slate-500 border border-slate-200 whitespace-nowrap">{t.source}</span>
                                          </div>
                                          {t.hp && (
                                            <>
                                              <div className="flex flex-wrap items-center gap-1.5 pt-1 border-t border-slate-100">
                                                {t.hp.risk_level && (
                                                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${riskChip(t.hp.risk_level)}`}>{t.hp.risk_level}</span>
                                                )}
                                                <span className="text-[11px] font-semibold text-hp-navy">{t.hp.hp_play}</span>
                                              </div>
                                              {t.hp.reason && (
                                                <p className="text-[11px] text-slate-500 leading-snug">{t.hp.reason}</p>
                                              )}
                                            </>
                                          )}
                                        </div>
                                      ))}
                                  </div>
                                </details>
                              );
                            })}
                          </div>
                        );
                      })()}

                      {!matrixData.stack_view && techGroups.length > 0 && (
                        <div className="bg-white rounded-xl border border-slate-200 shadow-xs p-4 space-y-3">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                            <div>
                              <h4 className="text-sm font-bold text-slate-900">
                                Full technology stack
                                <span className="text-slate-400 font-normal"> &middot; {totalTechCount}</span>
                              </h4>
                              <p className="text-[11px] text-slate-500 mt-0.5">
                                Every technology in {selectedAccount?.name || 'this account'}&apos;s
                                technographics export, grouped by the export&apos;s own categories.
                                {multiCategoryCount > 0 && (
                                  <> {multiCategoryCount} of them are filed under more than one
                                  category, so the group counts add up to more than {totalTechCount}.</>
                                )}
                              </p>
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="relative">
                                <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-2.5" />
                                <input
                                  type="text"
                                  value={techSearch}
                                  onChange={(e) => setTechSearch(e.target.value)}
                                  placeholder="Search technologies..."
                                  className="w-full sm:w-56 pl-9 pr-3 py-2 text-xs font-medium bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-hp-navy"
                                />
                              </div>
                            </div>
                          </div>

                          {visibleTechGroups.length === 0 ? (
                            <p className="text-xs text-slate-400 italic py-2">
                              No technology matches that search.
                            </p>
                          ) : (
                            <div className="divide-y divide-slate-100">
                              {visibleTechGroups.map((g: any) => {
                                // Same as the families above: a search opens what it
                                // matched, otherwise closed, and the row itself is a
                                // <summary> the browser toggles.
                                const autoOpen = !!techQuery;
                                return (
                                  <details key={`${g.category}:${autoOpen}`} open={autoOpen}
                                    className="group py-2">
                                    <summary
                                      className="as-summary group w-full flex items-center gap-2 text-left"
                                    >
                                      <span className="text-xs font-semibold text-slate-800 group-hover:text-hp-navy transition">
                                        {g.category}
                                      </span>
                                      <span className="text-[11px] font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                                        {g.count}
                                      </span>
                                      <span className="flex-1" />
                                      <ChevronDown className="as-chevron w-4 h-4 text-slate-400" />
                                    </summary>
                                    {g.note && (
                                      <p className="text-[11px] text-slate-400 mt-0.5">{g.note}</p>
                                    )}
                                    <div className="flex flex-wrap gap-1.5 mt-2">
                                        {(g.technologies || []).map((t: string) => (
                                          <span
                                            key={t}
                                            title={techSources[t] || undefined}
                                            className="text-[11px] font-medium text-slate-600 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-full"
                                          >
                                            {t}
                                          </span>
                                        ))}
                                    </div>
                                  </details>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      )}

                    </div>
                  );
                })()}

                {/* ============================================================================== */}
                {/* MESSAGE EVALUATOR — 7-STEP PIPELINE, ALL DATA FROM THE BACKEND               */}
                {/*                                                                              */}
                {/* Nothing here is hardcoded. Objectives, formats, personas, scores, phrases,   */}
                {/* the reaction and the rewrite all come from the evaluator endpoints. The      */}
                {/* previous version shipped 8 personas with invented phone numbers attached to  */}
                {/* real Astra people and a sample draft asserting a 23% saving that appears     */}
                {/* nowhere in the account's data.                                              */}
                {/* ============================================================================== */}
                {activeFeatureKey === 'message_evaluator' && (() => {
                  const stepsList = [
                    { key: 'inputs', label: 'Inputs' },
                    { key: 'persona', label: 'Persona' },
                    { key: 'confirm', label: 'Confirm' },
                    { key: 'scores', label: 'Scores' },
                    { key: 'phrases', label: 'Phrases' },
                    { key: 'summary', label: 'Summary' },
                    { key: 'rewrite', label: 'Rewrite' },
                  ];
                  const currentStepIdx = stepsList.findIndex(s => s.key === evaluatorStep);

                  const personas = evalOptions?.personas || [];
                  const objectives = evalOptions?.objectives || [];
                  const formats = evalOptions?.formats || [];
                  const chosenPersona = personas.find((p: any) => p.persona_id === selectedPersonaId) || null;
                  const chosenObjective = objectives.find((o: any) => o.id === selectedObjective) || null;
                  const chosenFormat = formats.find((f: any) => f.id === selectedFormat) || null;

                  const canEvaluate = !!selectedPersonaId && !!selectedObjective
                    && !!selectedFormat && stimulusText.trim().length > 0;

                  const runEvaluation = async () => {
                    if (!selectedAccountId || !canEvaluate) return;
                    setIsEvaluating(true);
                    setEvalError(null);
                    try {
                      const res = await api.post<any>(
                        `/accounts/${selectedAccountId}/widgets/message_evaluator/evaluate`,
                        {
                          persona_contact_id: selectedPersonaId,
                          objective: selectedObjective,
                          format: selectedFormat,
                          message: stimulusText,
                          mode: evaluatorMode,
                        }
                      );
                      setEvaluation(res.data);
                      setSelectedRecs([]);
                      setEvaluatorStep('scores');
                    } catch (err: any) {
                      setEvalError(err?.response?.data?.detail || err?.message || 'Evaluation failed.');
                    } finally {
                      setIsEvaluating(false);
                    }
                  };

                  const runRewrite = async () => {
                    if (!selectedAccountId || !evaluation?.fingerprint || selectedRecs.length === 0) return;
                    setIsRewriting(true);
                    setRewriteError(null);
                    try {
                      const res = await api.post<any>(
                        `/accounts/${selectedAccountId}/widgets/message_evaluator/rewrite`,
                        { fingerprint: evaluation.fingerprint, selected_recommendations: selectedRecs }
                      );
                      setEvaluation(res.data);
                    } catch (err: any) {
                      setRewriteError(err?.response?.data?.detail || err?.message || 'Rewrite failed.');
                    } finally {
                      setIsRewriting(false);
                    }
                  };

                  const loadPrevious = async (fingerprint: string) => {
                    if (!selectedAccountId) return;
                    try {
                      const res = await api.get<any>(
                        `/accounts/${selectedAccountId}/widgets/message_evaluator/evaluation/${fingerprint}`);
                      setStimulusText(res.data?.message_text || '');
                      setSelectedPersonaId(res.data?.persona_contact_id || '');
                      setSelectedObjective(res.data?.objective || '');
                      setSelectedFormat(res.data?.format || '');
                      setEvaluation(res.data);
                    } catch {
                      /* the list came from the server; a failure here is not worth a banner */
                    }
                  };

                  // Score presentation. The bands are the build specification's
                  // rubric (Section 4.5) and they are six, not five: the previous
                  // table started Strong at 80, so a 76 read as Good where the
                  // specification calls it Strong. `score_band` on the server uses
                  // the same table - these have to agree or the bar and the badge
                  // disagree on the same number.
                  const scoreColor = (n: number) =>
                    n >= 90 ? 'bg-emerald-600' : n >= 75 ? 'bg-green-500' : n >= 60 ? 'bg-teal-500'
                      : n >= 40 ? 'bg-amber-500' : n >= 20 ? 'bg-orange-500' : 'bg-rose-500';
                  const scoreLabel = (n: number) =>
                    n >= 90 ? 'Exceptional' : n >= 75 ? 'Strong' : n >= 60 ? 'Good'
                      : n >= 40 ? 'Average' : n >= 20 ? 'Weak' : 'Poor';
                  const scoreBadge = (n: number | null) =>
                    n == null ? 'border-slate-200 text-slate-400'
                      : n >= 90 ? 'border-emerald-300 text-emerald-700 bg-emerald-50'
                      : n >= 75 ? 'border-green-300 text-green-700 bg-green-50'
                      : n >= 60 ? 'border-teal-300 text-teal-700 bg-teal-50'
                      : n >= 40 ? 'border-amber-300 text-amber-700 bg-amber-50'
                      : 'border-rose-300 text-rose-700 bg-rose-50';

                  const resetEvaluator = () => {
                    setEvaluation(null);
                    setSelectedRecs([]);
                    setRewriteError(null);
                    setEvalError(null);
                    setStimulusText('');
                    setEvaluatorStep('inputs');
                  };

                  const verdictChip = (v: string) =>
                    v === 'Keep' ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                      : v === 'Improve' ? 'bg-amber-50 text-amber-700 border-amber-200'
                      : 'bg-rose-50 text-rose-700 border-rose-200';


                  return (
                    <div className="space-y-5">

                      {/* Header */}
                      <div className="space-y-2">
                        <div className="flex items-start space-x-3">
                          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center flex-shrink-0">
                            <MessageSquare className="w-5 h-5 text-indigo-600" />
                          </div>
                          <div>
                            <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">
                              Message Evaluator
                            </h2>
                            <p className="text-xs text-slate-500 font-medium">
                              Persona-aware message scoring for {evalOptions?.company_name || selectedAccount?.name || 'this account'}.
                            </p>
                          </div>
                        </div>
                        {evaluation && (
                          <div className="pl-12">
                            <span className={`inline-block rounded-full border px-3 py-1 text-xs font-semibold ${scoreBadge(evaluation.composite)}`}>
                              V{evaluation.version}: {evaluation.composite_available ? evaluation.composite : '—'}
                            </span>
                          </div>
                        )}
                      </div>

                      {/* Stepper */}
                      <div className="flex items-center flex-wrap gap-2 text-xs font-medium text-slate-400">
                        {stepsList.map((st, i) => {
                          const isActive = st.key === evaluatorStep;
                          const reachable = i <= currentStepIdx || (!!evaluation && i >= 3);
                          return (
                            <React.Fragment key={st.key}>
                              <button
                                type="button"
                                onClick={() => reachable && setEvaluatorStep(st.key)}
                                disabled={!reachable}
                                className={`transition ${isActive
                                  ? 'text-indigo-600 font-bold underline'
                                  : reachable
                                    ? 'text-slate-600 hover:text-indigo-600 font-semibold'
                                    : 'text-slate-300 cursor-not-allowed'}`}
                              >
                                {i + 1}. {st.label}
                              </button>
                              {i < stepsList.length - 1 && <span className="text-slate-300">›</span>}
                            </React.Fragment>
                          );
                        })}
                      </div>

                      {evalError && (
                        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700">
                          {evalError}
                        </div>
                      )}

                      {!evalOptions && (
                        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-6 text-center text-xs font-semibold text-slate-500">
                          Loading personas, objectives and formats…
                        </div>
                      )}

                      {/* ------------------------------------------------ STEP A — INPUTS */}
                      {evalOptions && evaluatorStep === 'inputs' && (
                        <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-5">
                          <h3 className="text-sm font-semibold text-slate-800">
                            Step A &mdash; Configure Evaluation
                          </h3>

                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1.5">Mode</label>
                            <div className="flex gap-2">
                              {(evalOptions.modes || ['LITE', 'DEEP']).map((m: string) => (
                                <button
                                  key={m}
                                  type="button"
                                  onClick={() => setEvaluatorMode(m)}
                                  className={`px-5 py-2 rounded-lg text-sm font-semibold transition-colors ${
                                    evaluatorMode === m
                                      ? 'bg-indigo-600 text-white'
                                      : 'bg-slate-100 text-slate-700 hover:bg-slate-200'}`}
                                >
                                  {m}
                                </button>
                              ))}
                            </div>
                            <p className="text-xs text-slate-500 mt-1.5">
                              {evaluatorMode === 'LITE'
                                ? `Quick evaluation: ${5} phrase chunks, skip behavioral state`
                                : 'Full evaluation: more phrase chunks, includes the simulated persona reaction'}
                            </p>
                          </div>

                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1.5">
                              Audience (Persona)
                            </label>
                            <select
                              value={selectedPersonaId}
                              onChange={(e) => setSelectedPersonaId(e.target.value)}
                              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-800"
                            >
                              <option value="">Select persona...</option>
                              {personas.map((p: any) => (
                                <option key={p.persona_id} value={p.persona_id}>
                                  {p.name ? `${p.name} — ${p.title}` : `${p.title} (role type)`}
                                </option>
                              ))}
                            </select>
                          </div>

                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1.5">
                              Objective (Funnel Stage)
                            </label>
                            <select
                              value={selectedObjective}
                              onChange={(e) => setSelectedObjective(e.target.value)}
                              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-800"
                            >
                              <option value="">Select objective...</option>
                              {objectives.map((o: any) => (
                                <option key={o.id} value={o.id}>{o.label}</option>
                              ))}
                            </select>
                            {chosenObjective && (
                              <p className="text-[10px] font-mono text-slate-400 mt-1">
                                {chosenObjective.formula}
                              </p>
                            )}
                          </div>

                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1.5">
                              Format (Content Type)
                            </label>
                            <select
                              value={selectedFormat}
                              onChange={(e) => setSelectedFormat(e.target.value)}
                              className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-800"
                            >
                              <option value="">Select format...</option>
                              {formats.map((f: any) => (
                                <option key={f.id} value={f.id}>{f.label}</option>
                              ))}
                            </select>
                            {chosenFormat && (
                              <p className="text-xs text-slate-500 mt-1">{chosenFormat.criteria}</p>
                            )}
                          </div>

                          <div>
                            <label className="block text-xs font-medium text-slate-600 mb-1.5">
                              Stimulus (Message Text)
                            </label>
                            <textarea
                              value={stimulusText}
                              onChange={(e) => setStimulusText(e.target.value)}
                              rows={10}
                              placeholder="Paste or type your sales email, LinkedIn message, campaign copy, or call script here..."
                              className="w-full rounded-lg border-2 border-indigo-300 px-4 py-3 text-sm text-slate-800 leading-relaxed focus:outline-none focus:border-indigo-500"
                            />
                            <p className="text-xs text-slate-500 mt-1">
                              {stimulusText.length} characters
                            </p>
                          </div>

                          {/* Previous real submissions. There is no sample generator: a
                              plausible-looking specimen draft would have to invent the
                              kind of claim this feature exists to catch. */}
                          {evalHistory.length > 0 && (
                            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                              <p className="text-xs font-medium text-slate-600 mb-2">
                                Load a previous submission
                              </p>
                              <div className="space-y-1">
                                {evalHistory.slice(0, 5).map((h: any) => (
                                  <button
                                    key={h.fingerprint}
                                    type="button"
                                    onClick={() => loadPrevious(h.fingerprint)}
                                    className="block w-full text-left text-xs text-slate-600 hover:text-indigo-600 truncate"
                                  >
                                    V{h.version} &middot; {h.objective_label} &middot; {h.format_label}
                                    {h.composite != null && ` · ${h.composite}/100`}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}

                          <button
                            type="button"
                            disabled={!selectedPersonaId || !selectedObjective || !selectedFormat || !stimulusText.trim()}
                            onClick={() => setEvaluatorStep('persona')}
                            className="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:bg-indigo-300 disabled:cursor-not-allowed transition-colors"
                          >
                            <User className="w-4 h-4" />
                            Build Persona
                          </button>
                        </div>
                      )}

                      {/* ----------------------------------------------- STEP B — PERSONA */}
                      {evalOptions && ['persona', 'confirm'].includes(evaluatorStep) && chosenPersona && (
                        <div className="space-y-4">
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-5">
                            <h3 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                              <User className="w-4 h-4 text-indigo-500" />
                              Persona: {chosenPersona.name || chosenPersona.title}
                              {evalOptions.company_name ? ` at ${evalOptions.company_name}` : ''}
                            </h3>

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                              <div>
                                <p className="text-sm font-semibold text-slate-700 mb-1.5">Role</p>
                                <ul className="space-y-1 text-xs text-slate-600">
                                  <li>&ndash; {chosenPersona.title}</li>
                                  {chosenPersona.department && <li>&ndash; Department: {chosenPersona.department}</li>}
                                  {chosenPersona.seniority_band && <li>&ndash; Seniority: {chosenPersona.seniority_band}</li>}
                                  {chosenPersona.influence_type && <li>&ndash; Influence: {chosenPersona.influence_type}</li>}
                                </ul>
                              </div>

                              {/* Step B, spec Section 4.3. Every list here is the hardcoded
                                  persona card - identical on all 220 accounts - and it is
                                  labelled as a persona reference rather than as intelligence
                                  about this buyer. The account-derived blocks below keep their
                                  own labels. */}
                              {(['goals', 'pain_points', 'value_drivers', 'decision_criteria'] as const).map((field) => {
                                const items: string[] = chosenPersona.card?.[field] || [];
                                if (items.length === 0) return null;
                                const heading = field === 'decision_criteria'
                                  ? 'They decide by asking'
                                  : field.replace(/_/g, ' ').replace(/^./, (c: string) => c.toUpperCase());
                                return (
                                  <div key={field}>
                                    <p className="text-sm font-semibold text-slate-700 mb-1.5">{heading}</p>
                                    <ul className="space-y-1 text-xs text-slate-600">
                                      {items.map((x, i) => <li key={i}>&ndash; {x}</li>)}
                                    </ul>
                                  </div>
                                );
                              })}

                              <div>
                                <p className="text-sm font-semibold text-slate-700 mb-1.5">Account Signals</p>
                                {(evalOptions.account_context?.triggers || []).length > 0 ? (
                                  <ul className="space-y-1 text-xs text-slate-600">
                                    {evalOptions.account_context.triggers.slice(0, 4).map((x: string, i: number) => (
                                      <li key={i}>&ndash; {x}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                                )}
                              </div>
                            </div>

                            {chosenPersona.card && (
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
                                <div>
                                  <p className="text-sm font-semibold text-slate-700 mb-1.5">
                                    What does not land
                                  </p>
                                  <ul className="space-y-1 text-xs text-slate-600">
                                    {(chosenPersona.card.does_not_resonate || []).map((x: string, i: number) => (
                                      <li key={i}>&ndash; {x}</li>
                                    ))}
                                  </ul>
                                </div>
                                <div>
                                  <p className="text-sm font-semibold text-slate-700 mb-1.5">
                                    Objections they raise
                                  </p>
                                  <ul className="space-y-1 text-xs text-slate-600">
                                    {(chosenPersona.card.typical_objections || []).map((x: string, i: number) => (
                                      <li key={i}>&ndash; {x}</li>
                                    ))}
                                  </ul>
                                </div>
                                <div className="md:col-span-2 text-xs text-slate-600 space-y-1">
                                  <p>
                                    <span className="font-semibold text-slate-700">Preferred tone:</span>{' '}
                                    {chosenPersona.card.content_preferences?.tone}
                                  </p>
                                  <p>
                                    <span className="font-semibold text-slate-700">Preferred format:</span>{' '}
                                    {chosenPersona.card.content_preferences?.format}
                                  </p>
                                  <p>
                                    <span className="font-semibold text-slate-700">Measured on:</span>{' '}
                                    {(chosenPersona.card.content_preferences?.key_metrics || []).join(', ')}
                                  </p>
                                  <p>
                                    <span className="font-semibold text-slate-700">
                                      What HP can and cannot address for this role:
                                    </span>{' '}
                                    {chosenPersona.card.hp_opportunity}
                                  </p>
                                </div>
                                <p className="md:col-span-2 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-[11px] text-slate-600">
                                  <span className="font-semibold">
                                    Evidence grade: {chosenPersona.card.evidence_grade}.
                                  </span>{' '}
                                  {chosenPersona.card.confidence_explanation}{' '}
                                  This card is a persona reference, identical on every account
                                  &mdash; not intelligence about this buyer. The account reaches
                                  the evaluation through the evidence below and through the
                                  scoring itself.
                                </p>
                              </div>
                            )}

                            <div>
                              <p className="text-sm font-semibold text-slate-700 mb-1.5">
                                HP Opportunity at this account
                              </p>
                              {(evalOptions.account_context?.hp_opportunity || []).length > 0 ? (
                                <p className="text-xs text-slate-600 leading-relaxed">
                                  {evalOptions.account_context.hp_opportunity.map((o: any, i: number) => (
                                    <span key={i}>
                                      {i > 0 && ' '}
                                      {o.hp_family}{o.category_name ? ` (${o.category_name})` : ''} &mdash;{' '}
                                      <span className={o.confidence === 'Confirmed' ? 'text-green-700 font-medium' : 'text-slate-500'}>
                                        {o.confidence}
                                      </span>
                                      , {o.fact_count} approved fact{o.fact_count === 1 ? '' : 's'}.
                                    </span>
                                  ))}
                                  {(evalOptions.account_context?.competitive_vendors || []).length > 0 && (
                                    <span> Vendors detected in this account&apos;s technology data:{' '}
                                      {evalOptions.account_context.competitive_vendors.join(', ')}.
                                    </span>
                                  )}
                                </p>
                              ) : (
                                <p className="text-xs text-slate-400">
                                  {NO_SIGNAL}
                                </p>
                              )}
                            </div>

                            {/* DATA SOURCES — the honesty panel. Each line is the real
                                provenance recorded when the persona was built. */}
                            <div className="border-t border-slate-100 pt-4">
                              <p className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-2">
                                Data Sources
                              </p>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-1.5 text-xs">
                                {Object.entries(chosenPersona.sources || {}).map(([field, src]: any) => (
                                  <p key={field} className="text-slate-700">
                                    <span className="font-medium capitalize">{field.replace(/_/g, ' ')}:</span>{' '}
                                    <span className={src === 'not_available' ? 'text-slate-400' : 'text-indigo-600'}>
                                      {src === 'account_contact' ? 'This account’s contact record'
                                        : src === 'account_evidence' ? 'Account evidence'
                                        : src === 'hiring_role_proxy' ? 'Open job postings'
                                        : src === 'company_personas' ? 'The client’s target buying committee'
                                        : src === 'not_available' ? NO_SIGNAL
                                        : String(src)}
                                    </span>
                                  </p>
                                ))}
                                {Object.entries(evalOptions.context_sources || {})
                                  .filter(([f]: any) => ['hp_opportunity', 'competitive_vendors', 'triggers'].includes(f))
                                  .map(([field, src]: any) => (
                                    <p key={field} className="text-slate-700">
                                      <span className="font-medium capitalize">{field.replace(/_/g, ' ')}:</span>{' '}
                                      <span className={src === 'Not available' ? 'text-slate-400' : 'text-indigo-600'}>{src === 'Not available' ? NO_SIGNAL : src}</span>
                                    </p>
                                  ))}
                              </div>
                            </div>
                          </div>

                          <div className="flex flex-wrap gap-3">
                            <button
                              type="button"
                              disabled={isEvaluating}
                              onClick={runEvaluation}
                              className="inline-flex items-center gap-2 px-5 py-2.5 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 disabled:opacity-50 transition-colors"
                            >
                              <Check className="w-4 h-4" />
                              {isEvaluating ? 'Evaluating…' : 'Confirm Persona & Evaluate'}
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('inputs')}
                              className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-200 transition-colors"
                            >
                              <Edit3 className="w-4 h-4" />
                              Edit Inputs
                            </button>
                          </div>
                        </div>
                      )}

                      {/* ------------------------------------- 4-6. RESULTS (Scores/Phrases/Summary)
                          The reference app shows these three on one screen, with steps D, E and F
                          highlighted together in the stepper. Paginating them hides the phrase
                          table behind a click when it is the part a seller acts on. */}
                      {evaluation && ['scores', 'phrases', 'summary'].includes(evaluatorStep) && (
                        <div className="space-y-5">

                          {/* ai_available, padded dimensions, withheld composite or
                              reaction and dropped chunks stay in the evaluation record;
                              the client sees neutral wording, never a placeholder 50. */}

                          {/* Step D - dimension scores */}
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
                            <h3 className="text-sm font-semibold text-slate-800">
                              Step D &mdash; Dimension Scores
                            </h3>

                            {Object.keys(evaluation.dimensions || {}).length > 0 ? (
                              <div className="space-y-2.5">
                                {Object.entries(evaluation.dimensions).map(([k, v]: any, dimIdx: number) => {
                                  const weight = evaluation.dimension_weights?.[k];
                                  const padded = (evaluation.dimensions_padded || []).includes(k);
                                  const floored = (evaluation.severe_failures || [])
                                    .find((f: any) => f.dimension === k);
                                  return (
                                    <div key={k} className="space-y-1">
                                      <div className="flex items-center gap-3">
                                      <span className="text-xs font-medium text-slate-600 w-28 text-right capitalize">
                                        {k.replace(/_/g, ' ')}
                                      </span>
                                      <div className="flex-1 bg-slate-100 rounded-full h-4 overflow-hidden">
                                        <div
                                          className={`as-grow ${padded ? 'bg-slate-300' : scoreColor(v)} h-full rounded-full transition-all duration-500`}
                                          style={{ width: `${padded ? 0 : v}%`, ['--as-d' as string]: `${growDelay(dimIdx)}ms` }}
                                        />
                                      </div>
                                      <span className="text-[11px] font-semibold text-slate-700 w-8 text-right">
                                        {padded ? null : <CountUpText text={v} delay={growDelay(dimIdx)} />}
                                      </span>
                                      <span className="text-[10px] text-slate-400 w-24">
                                        {padded ? NO_SIGNAL : scoreLabel(v)}
                                      </span>
                                      {/* A dimension outside this objective's formula is scored
                                          and shown and weighs nothing - say so, or a low bar
                                          reads as something that pulled the composite down. */}
                                      <span className="text-[10px] w-20">
                                        {weight === 0
                                          ? <span className="text-slate-400">no weight</span>
                                          : weight != null
                                            ? <span className="text-slate-500 font-mono">&times;{weight}</span>
                                            : null}
                                      </span>
                                      {floored && (
                                        <span
                                          className="text-[10px] font-semibold text-rose-600"
                                          title={floored.detail}
                                        >
                                          capped
                                        </span>
                                      )}
                                      </div>
                                      {/* Spec 4.10 asks for a rationale per
                                          dimension. Seven bars and no reasons is
                                          a score, not feedback. */}
                                      {evaluation.dimension_rationales?.[k] && !padded && (
                                        <p className="ml-[7.75rem] -mt-1 text-[11px] text-slate-500 leading-snug">
                                          {evaluation.dimension_rationales[k]}
                                        </p>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-500">
                                {NO_SIGNAL}
                              </p>
                            )}

                            <div className="border-t border-slate-100 pt-4 mt-4">
                              <div className="flex items-center gap-4 flex-wrap">
                                <div className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border-2 ${scoreBadge(evaluation.composite)}`}>
                                  <span className="text-2xl font-bold">
                                    {evaluation.composite_available ? evaluation.composite : <span className="text-sm font-medium">{NO_SIGNAL}</span>}
                                  </span>
                                  {evaluation.composite_available && (
                                    <div>
                                      <span className="text-[10px] uppercase tracking-wide font-semibold">/ 100</span>
                                      <p className="text-xs font-medium">{evaluation.score_band}</p>
                                    </div>
                                  )}
                                </div>
                                <div className="text-xs text-slate-500">
                                  <p className="font-medium text-slate-600 mb-0.5 flex items-center gap-1">
                                    Overall score ({evaluation.objective_label}) &middot; V{evaluation.version}
                                    <ScoreInfo topic="messageScore" worked={messageWorked(evaluation)} />
                                  </p>
                                </div>
                              </div>
                              {(evaluation.severe_failures || []).length > 0 && (
                                <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2.5 space-y-1">
                                  <p className="text-[10px] font-bold uppercase tracking-wider text-rose-700">
                                    Severe failure
                                  </p>
                                  {evaluation.severe_failures.map((f: any, i: number) => (
                                    <p key={i} className="text-xs text-rose-800">
                                      {f.detail}
                                      {f.model_score != null && (
                                        <span className="text-rose-600">
                                          {' '}(scored {f.model_score} before the cap)
                                        </span>
                                      )}
                                      {f.quote && (
                                        <span className="block text-[11px] italic text-rose-700 mt-0.5">
                                          &ldquo;{f.quote}&rdquo;
                                        </span>
                                      )}
                                    </p>
                                  ))}
                                </div>
                              )}
                              {(evaluation.hp_lines_named || []).length > 0 && (
                                <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs text-slate-700 space-y-1.5">
                                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                                    What Brand Recall and Impact were judged against
                                  </p>
                                  <p>
                                    <span className="font-semibold">HP lines named:</span>{' '}
                                    {evaluation.hp_lines_named.join(', ')}
                                  </p>
                                  {(evaluation.rulebook_positioning || []).length > 0 ? (
                                    <p>
                                      <span className="font-semibold">Rulebook positioning:</span>{' '}
                                      {evaluation.rulebook_positioning
                                        .map((r: any) => r.offering)
                                        .filter(Boolean).join(' · ')}
                                    </p>
                                  ) : (
                                    <p className="text-slate-500">
                                      The Rulebook carries no positioning for these lines.
                                    </p>
                                  )}
                                  {(evaluation.proof_available || []).length > 0 ? (
                                    <p>
                                      <span className="font-semibold">HP proof available:</span>{' '}
                                      {evaluation.proof_available.map((p: any) => p.text).join(' ')}
                                    </p>
                                  ) : (
                                    <p className="text-slate-500">
                                      No HP case study fits these lines, so an unproved claim
                                      should be cut rather than softened.
                                    </p>
                                  )}
                                </div>
                              )}
                              {evaluation.persona_card?.behavioural_state && (
                                <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2.5 text-xs text-indigo-900 space-y-1">
                                  <p className="text-[10px] font-bold uppercase tracking-wider text-indigo-700">
                                    Assumed entry state &mdash; {evaluation.persona_card.behavioural_state.name}
                                  </p>
                                  <p>
                                    Trust {evaluation.persona_card.behavioural_state.trust_level},{' '}
                                    {String(evaluation.persona_card.behavioural_state.response_bias).toLowerCase()} bias.{' '}
                                    {evaluation.persona_card.behavioural_state.messaging_approach}.
                                  </p>
                                  <p>
                                    <span className="font-semibold">Would move them forward:</span>{' '}
                                    {evaluation.persona_card.behavioural_state.fast_track_trigger}
                                  </p>
                                  <p>
                                    <span className="font-semibold">Holds them back:</span>{' '}
                                    {evaluation.persona_card.behavioural_state.key_blocker}
                                  </p>
                                  <p className="text-[10px] text-indigo-600">
                                    A default for this role, not something observed about this
                                    reader.
                                  </p>
                                </div>
                              )}
                            </div>

                            {/* Coded checks: the part that survives an AI failure. */}
                            <div className="border-t border-slate-100 pt-3 space-y-1.5">
                              <p className="text-xs font-semibold text-slate-600">
                                Coded checks ({evaluation.structure_checks?.checks_passed}/{evaluation.structure_checks?.checks_total})
                                <span className="font-normal text-slate-400"> — computed in code, independent of the AI</span>
                              </p>
                              {(evaluation.structure_checks?.checks || []).map((c: any) => (
                                <div key={c.check} className="flex items-start gap-2 text-xs">
                                  <span className={c.passed ? 'text-green-500' : 'text-rose-500'}>
                                    {c.passed ? '✓' : '✕'}
                                  </span>
                                  <span className="font-medium text-slate-700 capitalize w-36">
                                    {c.check.replace(/_/g, ' ')}
                                  </span>
                                  <span className="text-slate-500 flex-1">{c.detail}</span>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Simulated reaction - always labelled as a simulation. */}
                          {evaluation.reaction && (
                            <div className="bg-white rounded-xl border border-slate-200 p-5">
                              <h3 className="text-sm font-semibold text-slate-700 mb-2">
                                Persona Reaction
                              </h3>
                              <p className="text-sm text-slate-600 italic leading-relaxed">
                                &ldquo;{evaluation.reaction.text}&rdquo;
                              </p>
                              <p className="text-xs text-slate-400 mt-1.5">
                                &mdash; {evaluation.reaction.label}
                              </p>
                            </div>
                          )}
                          {!evaluation.reaction && (evaluation.reaction_withheld || []).length > 0 && (
                            <div className="bg-white rounded-xl border border-slate-200 p-5">
                              <h3 className="text-sm font-semibold text-slate-700 mb-1">
                                Persona Reaction
                              </h3>
                              <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                            </div>
                          )}

                          {/* Step E - phrase table, with the recommendation checkboxes inline. */}
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
                            <h3 className="text-sm font-semibold text-slate-800">
                              Step E &mdash; Phrase-Level Analysis
                            </h3>
                            {(evaluation.phrases || []).length === 0 ? (
                              <p className="text-xs text-slate-500">
                                {NO_SIGNAL}
                              </p>
                            ) : (
                              <div className="overflow-x-auto">
                                <table className="w-full text-xs">
                                  <thead>
                                    <tr className="border-b border-slate-200">
                                      <th className="text-center py-2 px-2 text-slate-500 font-medium w-10">
                                        <span className="sr-only">Select</span>
                                      </th>
                                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Chunk</th>
                                      <th className="text-center py-2 px-2 text-slate-500 font-medium w-20">Rating</th>
                                      <th className="text-center py-2 px-2 text-slate-500 font-medium w-24">Problem</th>
                                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Reason</th>
                                      <th className="text-left py-2 px-2 text-slate-500 font-medium">Recommendation</th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {(evaluation.phrases || []).map((p: any, i: number) => {
                                      const rec = p.suggestion || p.comment;
                                      const selectable = p.verdict !== 'Keep' && !!rec;
                                      return (
                                        <tr key={i} className="border-b border-slate-100 align-top">
                                          <td className="py-2 px-2 text-center">
                                            {selectable && (
                                              <input
                                                type="checkbox"
                                                checked={selectedRecs.includes(rec)}
                                                onChange={(e) => setSelectedRecs(
                                                  e.target.checked
                                                    ? [...selectedRecs, rec]
                                                    : selectedRecs.filter((x: string) => x !== rec))}
                                              />
                                            )}
                                          </td>
                                          <td className="py-2 px-2 text-slate-700 italic">
                                            &ldquo;{p.chunk}&rdquo;
                                            <span className="block text-[10px] text-slate-400 not-italic">
                                              chars {p.start}&ndash;{p.end}
                                            </span>
                                          </td>
                                          <td className="py-2 px-2 text-center">
                                            <span className={`inline-block rounded-full border px-2 py-0.5 text-[10px] font-semibold ${verdictChip(p.verdict)}`}>
                                              {p.verdict}
                                            </span>
                                          </td>
                                          <td className="py-2 px-2 text-center">
                                            <span className={`text-[10px] font-semibold ${p.problem_type === 'factual_grounding' ? 'text-rose-600' : 'text-slate-400'}`}>
                                              {p.problem_type === 'factual_grounding' ? 'Factual' : 'Style'}
                                            </span>
                                          </td>
                                          <td className="py-2 px-2 text-slate-600">
                                            {p.comment}
                                            {(p.grounding?.reasons || []).map((r: string, j: number) => (
                                              <span key={j} className="block text-[10px] font-semibold text-rose-600">{r}</span>
                                            ))}
                                          </td>
                                          <td className="py-2 px-2 text-slate-600">{p.suggestion}</td>
                                        </tr>
                                      );
                                    })}
                                  </tbody>
                                </table>
                              </div>
                            )}

                            {/* Coded checks that failed are also actionable changes. */}
                            {(evaluation.structure_checks?.checks || []).filter((c: any) => !c.passed).length > 0 && (
                              <div className="border-t border-slate-100 pt-3 space-y-1.5">
                                <p className="text-xs font-semibold text-slate-600">Also fixable</p>
                                {(evaluation.structure_checks?.checks || [])
                                  .filter((c: any) => !c.passed)
                                  .map((c: any) => {
                                    const rec = `Fix ${c.check.replace(/_/g, ' ')}: ${c.detail}`;
                                    return (
                                      <label key={c.check} className="flex items-start gap-2 text-xs text-slate-600">
                                        <input
                                          type="checkbox"
                                          checked={selectedRecs.includes(rec)}
                                          onChange={(e) => setSelectedRecs(
                                            e.target.checked
                                              ? [...selectedRecs, rec]
                                              : selectedRecs.filter((x: string) => x !== rec))}
                                          className="mt-0.5"
                                        />
                                        <span>{rec}</span>
                                      </label>
                                    );
                                  })}
                              </div>
                            )}
                          </div>

                          {/* Step F - summary */}
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
                            <h3 className="text-sm font-semibold text-slate-800">
                              Step F &mdash; Summary
                            </h3>
                            {evaluation.format_notes && (
                              <p className="text-sm text-slate-600 leading-relaxed">
                                <span className="font-semibold text-slate-700">
                                  As {evaluation.format_label ? `a ${evaluation.format_label}` : 'this format'}:
                                </span>{' '}
                                {evaluation.format_notes}
                              </p>
                            )}
                            {evaluation.summary && (
                              <p className="text-sm text-slate-600 leading-relaxed">{evaluation.summary}</p>
                            )}

                            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                              {(evaluation.strengths || []).length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-slate-600 mb-1">Strengths</p>
                                  <ul className="space-y-1">
                                    {evaluation.strengths.map((s: string, i: number) => (
                                      <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                                        <Check className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0" />{s}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                              {(evaluation.weaknesses || []).length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold text-slate-600 mb-1">Weaknesses</p>
                                  <ul className="space-y-1">
                                    {evaluation.weaknesses.map((s: string, i: number) => (
                                      <li key={i} className="text-xs text-slate-600 flex items-start gap-1.5">
                                        <span className="text-rose-500 mt-0.5">&bull;</span>{s}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-3 pt-2">
                              <button
                                type="button"
                                onClick={() => { setEvaluatorStep('rewrite'); runRewrite(); }}
                                disabled={selectedRecs.length === 0 || isRewriting}
                                className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                              >
                                <Sparkles className="w-4 h-4" />
                                Apply &amp; Rewrite ({selectedRecs.length})
                              </button>
                              <button
                                type="button"
                                onClick={resetEvaluator}
                                className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-200 transition-colors"
                              >
                                <RotateCcw className="w-4 h-4" />
                                Start Over
                              </button>
                            </div>
                          </div>

                          {/* Data Sources - which source may establish what. */}
                          {evaluation.data_sources && (
                            <div className="bg-slate-50 rounded-xl border border-slate-200 p-5">
                              <h3 className="text-sm font-semibold text-slate-800 mb-2">Data Sources</h3>
                              <div className="space-y-2">
                                {(evaluation.data_sources.sources || []).map((s: any) => (
                                  <div key={s.id} className="text-xs">
                                    <div className="flex items-center gap-2">
                                      <span className={s.available ? 'text-green-500' : 'text-slate-300'}>&#9679;</span>
                                      <span className="font-semibold text-slate-700">{s.label}</span>
                                      {s.detail && <span className="text-slate-400">&mdash; {s.detail}</span>}
                                    </div>
                                    <p className="pl-5 text-slate-500">
                                      Establishes: {(s.may_establish || []).join('; ')}
                                    </p>
                                    <p className="pl-5 text-slate-400">
                                      Never: {(s.never_establishes || []).join('; ')}
                                    </p>
                                  </div>
                                ))}
                              </div>
                              {(evaluation.data_sources.superlatives_blocked
                                || evaluation.data_sources.competitor_claims_blocked) && (
                                <p className="mt-2 text-[11px] font-semibold text-amber-700">
                                  Market restrictions apply in {evaluation.data_sources.country}:
                                  {evaluation.data_sources.superlatives_blocked && ' superlative claims'}
                                  {evaluation.data_sources.superlatives_blocked
                                    && evaluation.data_sources.competitor_claims_blocked && ' and'}
                                  {evaluation.data_sources.competitor_claims_blocked && ' competitor comparisons'}
                                  {' '}are not permitted.
                                </p>
                              )}
                            </div>
                          )}
                        </div>
                      )}

                      {/* ------------------------------------------------------- 7. REWRITE */}
                      {evaluation && evaluatorStep === 'rewrite' && (
                        <div className="space-y-5">
                          {isRewriting && (
                            <div className="flex flex-col items-center justify-center py-16 space-y-4">
                              <div className="w-16 h-16 rounded-full border-4 border-slate-200 border-t-indigo-500 animate-spin" />
                              <h3 className="text-lg font-semibold text-slate-800">Rewriting Message</h3>
                            </div>
                          )}

                          {rewriteError && !isRewriting && (
                            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
                              <p className="text-sm text-red-700">{rewriteError}</p>
                              <p className="text-xs text-red-500 mt-1">
                                Your original message is unchanged.
                              </p>
                            </div>
                          )}

                          {!isRewriting && evaluation.rewrite && (
                            <>
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
                                  <h3 className="text-sm font-semibold text-slate-800">Original</h3>
                                  <p className="text-sm text-slate-600 leading-relaxed whitespace-pre-wrap">
                                    {evaluation.message_text}
                                  </p>
                                </div>
                                <div className="bg-white rounded-xl border border-indigo-200 p-5 space-y-3">
                                  <h3 className="text-sm font-semibold text-indigo-800">
                                    Rewritten &mdash; {evaluation.rewrite.format_label}
                                  </h3>
                                  {/* Rendered by field so the format is visible, not a blob. */}
                                  {evaluation.rewrite.subject_line && (
                                    <div>
                                      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">Subject</p>
                                      <p className="text-sm font-semibold text-slate-900">{evaluation.rewrite.subject_line}</p>
                                    </div>
                                  )}
                                  {/* Composed in Python, so email and LinkedIn DM greet
                                      and the public formats never do. */}
                                  {evaluation.rewrite.greeting && (
                                    <p className="text-sm text-slate-800">{evaluation.rewrite.greeting}</p>
                                  )}
                                  {evaluation.rewrite.headline && (
                                    <p className="text-sm font-semibold text-slate-900">{evaluation.rewrite.headline}</p>
                                  )}
                                  {evaluation.rewrite.opening && (
                                    <p className="text-sm text-slate-700 leading-relaxed">{evaluation.rewrite.opening}</p>
                                  )}
                                  {(evaluation.rewrite.body_sections || []).map((s: any, i: number) => (
                                    <div key={i}>
                                      {s.heading && <p className="text-sm font-semibold text-slate-800">{s.heading}</p>}
                                      {/* pre-line keeps a social post's "• " bullet lines apart */}
                                      <p className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">{s.text}</p>
                                    </div>
                                  ))}
                                  {evaluation.rewrite.cta && (
                                    <p className="text-sm font-medium text-slate-800">{evaluation.rewrite.cta}</p>
                                  )}
                                  {evaluation.rewrite.signoff && (
                                    <p className="text-sm text-slate-700 whitespace-pre-line">{evaluation.rewrite.signoff}</p>
                                  )}
                                  {(evaluation.rewrite.hashtags || []).length > 0 && (
                                    <p className="text-sm font-medium text-indigo-600">
                                      {evaluation.rewrite.hashtags.join(' ')}
                                    </p>
                                  )}
                                </div>
                              </div>

                              {(evaluation.rewrite.diff?.applied_recommendations || []).length > 0 && (
                                <div className="bg-slate-50 rounded-xl border border-slate-200 p-5 space-y-3">
                                  <h3 className="text-sm font-semibold text-slate-800">Changes Applied</h3>
                                  <ul className="space-y-1.5">
                                    {evaluation.rewrite.diff.applied_recommendations.map((change: string, i: number) => (
                                      <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                                        <Check className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                                        {change}
                                      </li>
                                    ))}
                                  </ul>
                                  {(evaluation.rewrite.diff.facts_dropped || []).length > 0 && (
                                    <p className="text-xs text-slate-500">
                                      Figures removed: {evaluation.rewrite.diff.facts_dropped.join(', ')}
                                    </p>
                                  )}
                                  {(evaluation.rewrite.diff.facts_added || []).length > 0 && (
                                    <p className="text-xs text-slate-500">
                                      Figures added, each checked against the sources: {evaluation.rewrite.diff.facts_added.join(', ')}
                                    </p>
                                  )}
                                </div>
                              )}

                              <div className="flex flex-wrap gap-3">
                                <button
                                  type="button"
                                  onClick={() => {
                                    navigator.clipboard.writeText(evaluation.rewrite.plain_text || '');
                                    setCopiedRewrite(true);
                                    setTimeout(() => setCopiedRewrite(false), 2500);
                                  }}
                                  className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-200 transition-colors"
                                >
                                  <Copy className="w-4 h-4" />
                                  {copiedRewrite ? 'Copied' : 'Copy to Clipboard'}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setStimulusText(evaluation.rewrite.plain_text || '');
                                    setEvaluation(null);
                                    setSelectedRecs([]);
                                    setEvaluatorStep('confirm');
                                  }}
                                  className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                                >
                                  <Sparkles className="w-4 h-4" />
                                  Evaluate the rewrite
                                </button>
                                <button
                                  type="button"
                                  onClick={resetEvaluator}
                                  className="inline-flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg hover:bg-slate-200 transition-colors"
                                >
                                  <RotateCcw className="w-4 h-4" />
                                  Start Over
                                </button>
                              </div>
                            </>
                          )}

                          {!isRewriting && !evaluation.rewrite && !rewriteError && (
                            <div className="bg-white rounded-xl border border-slate-200 p-5">
                              <p className="text-sm text-slate-600">
                                Select at least one recommendation on the results screen, then choose
                                Apply &amp; Rewrite.
                              </p>
                              <button
                                type="button"
                                onClick={() => setEvaluatorStep('scores')}
                                className="mt-3 inline-flex items-center gap-2 px-4 py-2 bg-slate-100 text-slate-700 text-sm font-medium rounded-lg"
                              >
                                Back to results
                              </button>
                            </div>
                          )}
                        </div>
                      )}

                    </div>
                  );
                })()}

                {activeFeatureKey === 'objection_playbook' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'objection_incumbent_context');
                  const reframesWidget = widgets.find(w => w.widget_key === 'objection_reframe_cards');

                  const contextData = contextWidget?.data || {};
                  const reframesData = reframesWidget?.data || {};

                  const incumbentTechs: string[] = contextData.incumbent_technologies || [];
                  const relevantCategories: string[] = contextData.relevant_categories || [];
                  const businessContext = contextData.business_context || {};
                  const totalIncumbentsCount = contextData.total_incumbents_count ?? incumbentTechs.length;

                  const objectionCards: any[] = reframesData.cards || [];
                  const objectionsReady = reframesWidget?.status === 'available' && objectionCards.length > 0;

                  return (
                    <div className="space-y-6 animate-fade-in">
                      {/* Top Header */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-4">
                        <div>
                          <h3 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <ShieldAlert className="w-6 h-6 text-hp-navy" />
                            <span>Objection Playbook</span>
                          </h3>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {objectionCards.length} objection reframes for {selectedAccount?.name || 'Target Account'}
                          </p>
                          <p className="text-[11px] text-slate-400 mt-1 max-w-2xl leading-relaxed">
                            Anticipated push-back a seller should be ready for, generated from this
                            account&apos;s {(reframesData.technology_evidence_source ?? contextData.technology_evidence_source) === 'tech_breakdown'
                              ? 'website technology (no technographics data for this account)'
                              : 'technographics evidence'}. These are not statements made by
                            any contact.
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-hp-navy bg-blue-50 px-3 py-1.5 rounded-xl border border-blue-200">
                            {totalIncumbentsCount} Incumbents Detected
                          </span>
                        </div>
                      </div>

                      {/* Objection accordion */}
                      {!objectionsReady ? (
                        /* reframesData.notice keeps the reason; the client sees neutral wording. */
                        <div className="bg-slate-50 border border-slate-200 rounded-2xl p-6 text-center">
                          <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {objectionCards.map((card: any) => {
                            const isOpen = expandedObjectionId === card.card_id;
                            const raiserIsContact = card.likely_raiser_source === 'prospect_contacts';
                            return (
                              <div key={card.card_id} className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
                                <button
                                  type="button"
                                  className="w-full flex items-start gap-3 p-4 text-left hover:bg-slate-50 transition-colors"
                                  onClick={() => setExpandedObjectionId(isOpen ? null : card.card_id)}
                                >
                                  <MessageSquare className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                                  <div className="flex-1 min-w-0">
                                    <p className="text-sm font-semibold text-slate-900">
                                      &ldquo;{card.objection.replace(/^["“]|["”]$/g, '')}&rdquo;
                                    </p>
                                    <p className="text-xs text-slate-400 mt-0.5">
                                      Could be raised by: <span className="font-medium text-slate-600">{card.likely_raiser}</span>
                                      {!raiserIsContact && (
                                        <span className="text-slate-400"> (owning function)</span>
                                      )}
                                    </p>
                                  </div>
                                  <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded flex-shrink-0 mt-0.5">
                                    {card.area}
                                  </span>
                                  {isOpen
                                    ? <ChevronUp className="w-4 h-4 text-slate-400 flex-shrink-0 mt-1" />
                                    : <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0 mt-1" />}
                                </button>

                                {isOpen && (
                                  <div className="border-t border-slate-100 p-4 bg-slate-50 space-y-4">
                                    <div className="bg-green-50 border border-green-200 rounded-lg p-4">
                                      <div className="flex items-center gap-2 mb-2">
                                        <Shield className="w-4 h-4 text-green-600" />
                                        <p className="text-xs font-semibold text-green-700 uppercase tracking-wider">Reframe</p>
                                      </div>
                                      <p className="text-sm text-green-900 leading-relaxed">{card.reframe}</p>
                                    </div>

                                    <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
                                      <p className="text-xs font-semibold text-blue-700 uppercase tracking-wider mb-2">Evidence</p>
                                      <p className="text-xs text-blue-900 font-mono leading-relaxed break-words">{card.evidence}</p>
                                    </div>

                                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                                      <div className="flex items-center gap-2 mb-2">
                                        <HelpCircle className="w-4 h-4 text-purple-600" />
                                        <p className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Counter Question</p>
                                      </div>
                                      <p className="text-sm text-purple-900 italic">&ldquo;{card.counter_question}&rdquo;</p>
                                    </div>

                                    {/* An HP customer who already did this. Rendered only when the
                                        case-study corpus actually holds one for this area - the
                                        corpus has no Poly or collaboration study, so those cards
                                        correctly show nothing rather than a placeholder. The named
                                        customer and the link are the point: this is the one place a
                                        seller can cite a public HP source to a customer. */}
                                    {card.hp_proof_point && (
                                      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                                        <div className="flex items-center gap-2 mb-2">
                                          <Award className="w-4 h-4 text-amber-600" />
                                          <p className="text-xs font-semibold text-amber-700 uppercase tracking-wider">
                                            HP Proof Point
                                          </p>
                                        </div>
                                        <p className="text-sm text-amber-900 leading-relaxed">{card.hp_proof_point}</p>
                                        {card.hp_proof_point_detail && (
                                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-amber-700">
                                            <span className="font-semibold">{card.hp_proof_point_detail.customer}</span>
                                            {card.hp_proof_point_detail.industry && (
                                              <span>{card.hp_proof_point_detail.industry}</span>
                                            )}
                                            {/* `hp_product` is deliberately NOT shown. It is the
                                                tag HP filed the study under and it is how we found
                                                it, but it often disagrees with what the study is
                                                about - the Universidad Andrés Bello story is
                                                tagged "HP EliteBook" and is entirely about HP
                                                Managed Device Services. The headline above already
                                                names the offering, from the study's own text, so
                                                printing the tag beside it only contradicts it. */}
                                            {openableUrl(card.hp_proof_point_detail.source_url, sourceLinkCtx) && (
                                              <a
                                                href={openableUrl(card.hp_proof_point_detail.source_url, sourceLinkCtx)}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="underline hover:text-amber-900"
                                              >
                                                View the HP case study
                                              </a>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    <div className="bg-slate-100 border border-slate-200 rounded-lg p-3 flex items-start gap-2">
                                      <User className="w-4 h-4 text-slate-500 flex-shrink-0 mt-0.5" />
                                      <p className="text-xs text-slate-600 leading-relaxed">
                                        <span className="font-semibold">
                                          {raiserIsContact ? 'Topic owner: ' : 'Owning function: '}
                                        </span>
                                        {card.likely_raiser}
                                        <span className="text-slate-400">
                                          {raiserIsContact
                                            ? ' \u2014 a title in this account\u2019s contacts who would own this subject. They have not raised this objection.'
                                            : ''}
                                        </span>
                                      </p>
                                    </div>
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      )}

                    </div>
                  );
                })()}

                {activeFeatureKey === 'content_messaging' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'messaging_context_card');
                  const pillarsWidget = widgets.find(w => w.widget_key === 'messaging_pillars_output');

                  const contextData = contextWidget?.data || {};
                  const pillarsData: any = pillarsWidget?.data || {};

                  const pillars: any[] = pillarsData.pillars || [];
                  const vectors: any[] = pillarsData.vectors || [];
                  const whyHpItems: any[] = pillarsData.why_hp_items || [];
                  const hasHouse = pillars.length > 0;

                  // The headline is generated; when it was withheld the flat
                  // umbrella sentence still stands in, so the hero is never empty.
                  const headline = pillarsData.umbrella_headline || pillarsData.umbrella_message || '';
                  const lead = pillarsData.umbrella_lead || '';

                  const cmIndex = (retrievalStatus?.indexes || [])
                    .find((i: any) => i.index === 'content_messaging');


                  return (
                    <div className="space-y-6">

                      {/* No build button. The message house rebuilds itself when a
                          dataset it depends on is uploaded or replaced, the same
                          way every other feature does - the upload queues one
                          index job and that job regenerates this. */}
                      <div>
                        <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">
                          Content Messaging
                        </h2>
                        <p className="text-xs text-slate-500 font-medium mt-0.5">
                          Challenge &rarr; HP benefit &rarr; HP solutions &rarr; sourced proof.
                          Rebuilt automatically when this account&apos;s data changes.
                        </p>
                      </div>

                      {cmIndex && (
                        <div className={`rounded-xl border px-4 py-2.5 text-xs ${
                          cmIndex.status === 'READY' ? 'border-slate-200 bg-slate-50 text-slate-600'
                            : cmIndex.status === 'RETIRED' ? 'border-slate-300 bg-slate-100 text-slate-600'
                            : cmIndex.status === 'STALE' ? 'border-amber-200 bg-amber-50 text-amber-800'
                            : cmIndex.status === 'BUILDING' ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                            : 'border-rose-200 bg-rose-50 text-rose-700'}`}>
                          <span className="font-semibold">Retrieval index: {cmIndex.status}</span>
                          {cmIndex.documents > 0 && <span> · {cmIndex.documents} documents · v{cmIndex.version}</span>}
                          {cmIndex.status === 'BUILDING' && <span> — unavailable until the rebuild finishes.</span>}
                          {cmIndex.status === 'STALE' && <span> — answering from the last good build.</span>}
                          {cmIndex.status === 'FAILED' && <span> — {cmIndex.last_error}</span>}
                          {/* Retired is not a fault: the index was dropped on purpose
                              to free capacity. What is below is the last build, and it
                              is complete - it simply will not refresh until rebuilt. */}
                          {cmIndex.status === 'RETIRED' && (
                            <span> — retired to free capacity. What you see below is the
                              last published version and will not refresh until this index
                              is rebuilt.</span>
                          )}
                        </div>
                      )}

                      {/* The index built but the message house did not regenerate.
                          Reported separately from the index's own status, because
                          the index is fine and still answering. */}
                      {cmIndex?.generation_error && (
                        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-800">
                          <span className="font-semibold">The message house could not be rebuilt.</span>{' '}
                          {cmIndex.generation_error} The version below is the last one that built.
                        </div>
                      )}

                      {hasHouse ? (
                        <>
                          {/* ---------------------------------------- UMBRELLA */}
                          <section className="rounded-2xl border border-teal-200 bg-teal-50/40 overflow-hidden">
                            <div className="px-5 pt-4">
                              <span className="inline-flex items-center gap-1.5 rounded-md bg-teal-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                                <Star className="w-3 h-3" /> Umbrella message
                              </span>
                            </div>
                            <div className="px-5 pb-5 pt-3">
                              <h3 className="text-lg md:text-xl font-extrabold text-slate-900 leading-snug">
                                {headline}
                              </h3>
                              {lead && (
                                <p className="text-xs text-slate-600 mt-2 font-medium">{lead}</p>
                              )}
                              {vectors.length > 0 && (
                                <div className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2 mt-3">
                                  {vectors.map((v: any, i: number) => (
                                    <div key={i} className="flex items-start gap-2 rounded-lg bg-white/70 border border-teal-100 px-3 py-2">
                                      <span className="mt-1 w-1.5 h-1.5 rounded-full bg-teal-500 flex-shrink-0" />
                                      <span className="text-xs font-medium text-slate-700">{v.label}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </section>

                          {/* ---------------------------------------- PILLARS */}
                          <section>
                            <div className="flex items-center justify-between gap-3 mb-2">
                              <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                                Messaging pillars
                              </span>
                              <span className="text-[10px] text-slate-400 font-medium">
                                Click a row for challenge, benefit &amp; proof points
                              </span>
                            </div>

                            <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
                              {/* Column headers, as in the reference layout */}
                              <div className="hidden md:grid grid-cols-[1.5fr_1.6fr_1.9fr_auto] gap-5 px-5 py-2.5 border-b border-slate-200 bg-slate-50/70">
                                {['Pillar', 'Challenge', 'HP benefit', 'Proof'].map((h, i) => (
                                  <span key={i} className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                    {h}
                                  </span>
                                ))}
                              </div>

                              {pillars.map((p: any, i: number) => {
                                const open = expandedPillar === p.pillar_title;
                                const sourced = p.sourced || { sourced: 0, total: 0 };
                                return (
                                  <div key={i} className="border-b border-slate-100 last:border-b-0">
                                    <button
                                      type="button"
                                      onClick={() => setExpandedPillar(open ? null : p.pillar_title)}
                                      className={`w-full text-left grid grid-cols-1 md:grid-cols-[1.5fr_1.6fr_1.9fr_auto] gap-3 md:gap-5 px-5 py-4 transition-colors ${open ? 'bg-slate-50/60' : 'hover:bg-slate-50/60'}`}
                                    >
                                      {/* Pillar: chevron, number, title */}
                                      <div className="flex items-start gap-2.5">
                                        {open
                                          ? <ChevronUp className="w-4 h-4 text-slate-400 mt-1 flex-shrink-0" />
                                          : <ChevronDown className="w-4 h-4 text-slate-400 mt-1 flex-shrink-0" />}
                                        <span className="w-5 h-5 rounded-full bg-sky-100 text-sky-700 text-[10px] font-bold flex items-center justify-center flex-shrink-0 mt-0.5">
                                          {i + 1}
                                        </span>
                                        <span className="text-[15px] font-bold text-slate-900 leading-snug">
                                          {p.pillar_title}
                                        </span>
                                      </div>

                                      {/* Challenge summary — the reference sets these
                                          large and dark; they are the row's content,
                                          not a caption for it. */}
                                      <p className="text-[14px] font-semibold text-slate-800 leading-snug">
                                        {p.challenge_summary}
                                      </p>

                                      <div>
                                        <p className="text-[14px] font-semibold text-slate-800 leading-snug">
                                          {p.benefit_summary}
                                        </p>
                                        <div className="flex flex-wrap gap-1.5 mt-2">
                                          {(p.hp_solutions || []).map((sol: string, j: number) => (
                                            <span key={j} className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-[11px] font-semibold text-indigo-700">
                                              {sol}
                                            </span>
                                          ))}
                                        </div>
                                      </div>

                                      <div className="flex md:justify-end flex-shrink-0">
                                        {/* Denominator is what the model PROPOSED, so a pillar
                                            that had claims discarded reads 3/5, not 3/3. Amber
                                            whenever anything was dropped. */}
                                        {/* Discarded proof points stay in `sourced.dropped`; not shown. */}
                                        <span className="rounded-full px-3 py-1 text-[11px] font-semibold whitespace-nowrap h-fit bg-slate-100 text-slate-600 border border-slate-200">
                                          {sourced.sourced} sourced
                                        </span>
                                      </div>
                                    </button>

                                    {open && (
                                      <div className="px-5 pb-5 bg-slate-50/40 border-t border-slate-100">
                                        {/* Challenge and benefit sit side by side */}
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-5 pt-4">
                                          <div>
                                            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 mb-2">
                                              Challenge
                                            </p>
                                            <p className="text-[13px] text-slate-700 leading-[1.75]">{p.challenge}</p>
                                            <div className="flex flex-wrap gap-1.5 mt-2.5">
                                              {dedupeSources(p.challenge_evidence).map((e: any, j: number) => (
                                                <SourceChip key={j} s={e} />
                                              ))}
                                            </div>
                                          </div>

                                          <div>
                                            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 mb-2">
                                              HP benefit
                                            </p>
                                            <p className="text-[13px] text-slate-700 leading-[1.75]">{p.hp_benefit}</p>
                                            <span className="inline-block mt-2 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                                              {p.hp_benefit_label || 'HP account analysis'}
                                            </span>
                                            {/* The public HP page for what this pillar sells.
                                                Separate from the proof chips on purpose: the
                                                proof came from a deck slide, not this page. */}
                                            {openableUrl(p.hp_resource?.url, sourceLinkCtx) && (
                                              <div className="flex items-center gap-2 mt-3">
                                                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                                  HP resource
                                                </span>
                                                <a
                                                  href={openableUrl(p.hp_resource.url, sourceLinkCtx)}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-[3px] text-[10px] font-semibold text-emerald-800 hover:underline"
                                                >
                                                  <FileText className="w-2.5 h-2.5" />
                                                  {p.hp_resource.label}
                                                  <ExternalLink className="w-2.5 h-2.5" />
                                                </a>
                                              </div>
                                            )}
                                          </div>
                                        </div>

                                        <div className="border-t border-slate-200 mt-5 pt-4">
                                          <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400 mb-2.5">
                                            Proof points ({sourced.total} shown, {sourced.sourced} sourced)
                                          </p>
                                          {sourced.total === 0 ? (
                                            <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                                          ) : (
                                            <ul className="space-y-2">
                                              {(p.proof_points || []).map((pr: any, j: number) => (
                                                <li key={j} className="flex items-start gap-2.5">
                                                  <span className="mt-[7px] w-1.5 h-1.5 rounded-full bg-slate-300 flex-shrink-0" />
                                                  <p className="text-[13px] text-slate-700 leading-[1.7] flex-1">
                                                    {pr.proof}
                                                    {/* Collapsed by label+link: two rows from the
                                                        same unlinked source rendered as
                                                        "Account newsAccount news". A distinct
                                                        link still earns its own chip. */}
                                                    {dedupeSources(pr.sources).map((s: any, k: number) => (
                                                      <span key={k}>{' '}<SourceChip s={s} /></span>
                                                    ))}
                                                    {pr.shared && (
                                                      <span className="ml-1 text-[10px] font-semibold text-amber-700">
                                                        (also supports another pillar)
                                                      </span>
                                                    )}
                                                  </p>
                                                </li>
                                              ))}
                                            </ul>
                                          )}
                                        </div>

                                        {/* An HP customer story for the lines this pillar
                                            names. Separate from the proof points above, which
                                            are facts about THIS account resolved by evidence
                                            id - this one is about a different company, and
                                            says so by naming them. */}
                                        {p.hp_proof_point && (
                                          <div className="border-t border-slate-200 mt-4 pt-4">
                                            <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-700 mb-2 flex items-center gap-1.5">
                                              <Award className="w-3.5 h-3.5" />
                                              HP customer proof point
                                            </p>
                                            <p className="text-[13px] text-slate-700 leading-[1.7]">{p.hp_proof_point}</p>
                                            {p.hp_proof_point_detail && (
                                              <p className="mt-1.5 text-[11px] text-slate-500">
                                                {p.hp_proof_point_detail.customer}
                                                {p.hp_proof_point_detail.industry && ` · ${p.hp_proof_point_detail.industry}`}
                                                {openableUrl(p.hp_proof_point_detail.source_url, sourceLinkCtx) && (
                                                  <>
                                                    {' · '}
                                                    <a
                                                      href={openableUrl(p.hp_proof_point_detail.source_url, sourceLinkCtx)}
                                                      target="_blank"
                                                      rel="noopener noreferrer"
                                                      className="underline hover:text-hp-navy"
                                                    >
                                                      View the HP case study
                                                    </a>
                                                  </>
                                                )}
                                              </p>
                                            )}
                                          </div>
                                        )}

                                        {(p.target_role || p.next_step) && (
                                          <div className="border-t border-slate-200 mt-4 pt-3 text-[12px] text-slate-600 space-y-0.5">
                                            {p.target_role && <p><span className="font-semibold text-slate-700">Target role:</span> {p.target_role}</p>}
                                            {p.next_step && <p><span className="font-semibold text-slate-700">Next step:</span> {p.next_step}</p>}
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })}
                            </div>
                          </section>

                          {/* ---------------------------------------- WHY HP */}
                          {whyHpItems.length > 0 && (
                            <section className="rounded-2xl border border-teal-200 bg-teal-50/40 overflow-hidden">
                              <div className="px-5 pt-4">
                                <span className="inline-flex items-center gap-1.5 rounded-md bg-teal-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white">
                                  Why HP
                                </span>
                              </div>
                              <div className="px-5 pb-5 pt-3 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-4">
                                {whyHpItems.map((w: any, i: number) => (
                                  <div key={i} className="flex items-start gap-2">
                                    <Check className="w-4 h-4 text-teal-600 mt-0.5 flex-shrink-0" />
                                    <div>
                                      <p className="text-sm font-bold text-slate-900">{w.title}</p>
                                      <p className="text-xs text-slate-600 leading-relaxed mt-0.5">{w.description}</p>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </section>
                          )}

                          {/* SOURCES - every distinct citation actually used across the
                              pillars, so the document's evidence can be read without
                              expanding each row. Built from the same proof-point sources
                              the rows show, so it can never list something unused. */}
                          {(() => {
                            // Only the sources that can be opened - the ones the
                            // rows above actually show (client, 7 Oct).
                            const used = linkedSources(dedupeSources(
                              pillars.flatMap((p: any) => [
                                ...(p.proof_points || []).flatMap((pr: any) => pr.sources || []),
                                ...(p.challenge_evidence || []),
                              ])
                            ), sourceLinkCtx);
                            if (!used.length) return null;
                            return (
                              <section className="rounded-xl border border-slate-200 bg-white p-4">
                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                                  Sources ({used.length})
                                </p>
                                {/* The same chip the pillar rows use, so a source reads
                                    identically wherever it appears and keeps its
                                    linked/unlinked distinction and evidence-id tooltip. */}
                                <div className="flex flex-wrap gap-1.5">
                                  {used.map((s: any, i: number) => <SourceChip key={i} s={s} />)}
                                </div>
                              </section>
                            );
                          })()}
                        </>
                      ) : (
                        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
                          {/* Index status and blocked_reason are in the admin Pipeline tab. */}
                          <p className="text-sm text-slate-400">{NO_SIGNAL}</p>
                        </div>
                      )}
                    </div>
                  );
                })()}

                {activeFeatureKey === 'content_studio' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'content_persona_context');
                  const generatedWidget = widgets.find(w => w.widget_key === 'content_generated_assets');

                  const contextData = contextWidget?.data || {};
                  const generatedData = generatedWidget?.data || {};

                  const targetPersonas: any[] = contextData.target_personas || [
                    { id: 'cio_it', title: 'CIO / IT Leadership', subtitle: 'Chief Information Officer and IT decision makers' },
                    { id: 'infra_workplace', title: 'Infrastructure & Workplace IT', subtitle: 'Device fleet owners, infrastructure strategy & commercial teams' },
                    { id: 'engineering_ai', title: 'Engineering / AI & Compute Leadership', subtitle: 'AI, ML and data science leads, GPU/compute buyers' },
                    { id: 'security_wolf', title: 'Security Leadership (Wolf Security)', subtitle: 'Endpoint security and risk decision makers' },
                    { id: 'procurement_finance', title: 'Procurement / Finance', subtitle: 'IT procurement and budget holders' },
                    { id: 'operations', title: 'Operations & Facilities', subtitle: 'Site and office leads, print & workplace services' },
                    { id: 'hr_workforce', title: 'HR / Workforce Experience', subtitle: 'Device refresh, hybrid work and onboarding programs' }
                  ];

                  const contentTypes: any[] = contextData.content_types || [
                    { id: 'email', title: 'Email', subtitle: 'Personalized executive outreach email' },
                    { id: 'linkedin_message', title: 'LinkedIn Message', subtitle: 'Short direct message to one contact' },
                    { id: 'one_pager', title: 'One-Pager', subtitle: "How HP's portfolio can deliver value for this customer" }
                  ];

                  const sourcedTopics: string[] = contextData.sourced_topics || [
                    'HP Elite & Pro PCs',
                    'Z by HP Workstations',
                    'Poly collaboration hardware',
                    'HP Enterprise Printing & Managed Print Services',
                    'HP Multi Jet Fusion (3D)'
                  ];

                  const handleGenerateClick = async () => {
                    if (!selectedAccountId) return;
                    const topicValue = (customTopic.trim() || selectedTopic || '').trim();
                    if (!topicValue) return;
                    const personaForRequest = targetPersonas.find(p => p.id === selectedPersona) || targetPersonas[0];
                    setIsGeneratingContent(true);
                    setGenerateError(null);
                    try {
                      const response = await api.post<WidgetResponse>(
                        `/accounts/${selectedAccountId}/widgets/content_studio/generate`,
                        {
                          persona_id: personaForRequest?.id,
                          content_type: selectedContentType,
                          topic: topicValue,
                          additional_context: additionalContext.trim(),
                        }
                      );
                      const latest = response.data?.data?.latest || null;
                      const lastError = response.data?.data?.last_error || null;
                      setWidgets(prev => prev.map(w => (w.widget_key === 'content_generated_assets' ? response.data : w)));
                      if (latest) {
                        setGeneratedAsset(latest);
                        setActiveVariantIndex(1);
                        setHasGeneratedContent(true);
                      } else {
                        setGeneratedAsset(null);
                        setHasGeneratedContent(false);
                        setGenerateError(lastError || { notice: 'Generation did not return an asset.' });
                      }
                    } catch (err: any) {
                      setGenerateError({ notice: err?.response?.data?.detail || err?.message || 'Generation failed.' });
                    } finally {
                      setIsGeneratingContent(false);
                    }
                  };

                  const downloadHtml = (asset: any) => {
                    if (!asset?.rendered_html) return;
                    const blob = new Blob([asset.rendered_html], { type: 'text/html' });
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${asset.content_type}-${asset.asset_id}.html`;
                    a.click();
                    URL.revokeObjectURL(url);
                  };

                  const personaKindLabel = (kind?: string) =>
                    kind === 'named' ? 'Named contact' : kind === 'role_proxy' || kind === 'archetype' ? 'Target role' : null;

                  const activePersonaObj = targetPersonas.find(p => p.id === selectedPersona) || targetPersonas[0];
                  const activeFormatObj = contentTypes.find(c => c.id === selectedContentType) || contentTypes[0];

                  return (
                    <div className="space-y-6 animate-fade-in">
                      {/* Top Header */}
                      <div className="border-b border-slate-200 pb-4">
                        <h3 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                          <FileText className="w-6 h-6 text-hp-navy" />
                          <span>Content Studio</span>
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Generate persona-targeted ABM content for {selectedAccount?.name || 'Target Account'} - grounded in the account&apos;s own data
                        </p>
                      </div>

                      {/* 2-Column Grid Layout: Left Controls + Right Canvas */}
                      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                        
                        {/* Left Control Panel (5 Cols) */}
                        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200 shadow-sm p-5 space-y-6">
                          
                          {/* 1. Target Persona Section */}
                          <div className="space-y-2">
                            <span className="text-xs font-black text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                              <User className="w-3.5 h-3.5 text-hp-navy" />
                              <span>Target Persona</span>
                            </span>

                            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                              {targetPersonas.map((p) => {
                                const isSelected = selectedPersona === p.id;
                                return (
                                  <button
                                    key={p.id}
                                    onClick={() => setSelectedPersona(p.id)}
                                    className={`w-full text-left p-3 rounded-xl border transition flex flex-col justify-between ${
                                      isSelected
                                        ? 'bg-blue-50/90 border-hp-navy ring-1 ring-hp-navy shadow-xs'
                                        : 'bg-slate-50/60 border-slate-200 hover:bg-slate-100/80'
                                    }`}
                                  >
                                    <span className={`text-xs font-extrabold ${isSelected ? 'text-hp-navy' : 'text-slate-800'}`}>
                                      {p.title}
                                      {personaKindLabel(p.kind) && (
                                        <span className={`ml-1.5 align-middle text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded ${p.kind === 'named' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : p.kind === 'role_proxy' ? 'bg-amber-50 text-amber-800 border border-amber-200' : 'bg-slate-100 text-slate-500 border border-slate-200'}`}>
                                          {personaKindLabel(p.kind)}
                                        </span>
                                      )}
                                    </span>
                                    <span className="text-[11px] text-slate-500 font-medium mt-0.5">
                                      {p.subtitle}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>

                          {/* 2. Content Type Section */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <span className="text-xs font-black text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                              <FileText className="w-3.5 h-3.5 text-hp-navy" />
                              <span>Content Type</span>
                            </span>

                            <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                              {contentTypes.map((c) => {
                                const isSelected = selectedContentType === c.id;
                                return (
                                  <button
                                    key={c.id}
                                    onClick={() => setSelectedContentType(c.id)}
                                    className={`w-full text-left p-3 rounded-xl border transition flex flex-col justify-between ${
                                      isSelected
                                        ? 'bg-blue-50/90 border-hp-navy ring-1 ring-hp-navy shadow-xs'
                                        : 'bg-slate-50/60 border-slate-200 hover:bg-slate-100/80'
                                    }`}
                                  >
                                    <span className={`text-xs font-extrabold ${isSelected ? 'text-hp-navy' : 'text-slate-800'}`}>
                                      {c.title}
                                    </span>
                                    <span className="text-[11px] text-slate-500 font-medium mt-0.5">
                                      {c.subtitle}
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>

                          {/* 3. Topic Selection Section */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <span className="text-xs font-black text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                              <Lightbulb className="w-3.5 h-3.5 text-amber-500" />
                              <span>Topic</span>
                            </span>

                            <div className="flex flex-wrap gap-1.5 max-h-36 overflow-y-auto">
                              {sourcedTopics.map((top, idx) => {
                                const isSelected = selectedTopic === top && !customTopic.trim();
                                return (
                                  <button
                                    key={idx}
                                    onClick={() => {
                                      setSelectedTopic(top);
                                      setCustomTopic('');
                                    }}
                                    className={`text-[11px] font-semibold px-2.5 py-1 rounded-xl border transition text-left ${
                                      isSelected
                                        ? 'bg-hp-navy text-white border-hp-navy shadow-xs'
                                        : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                                    }`}
                                  >
                                    {top}
                                  </button>
                                );
                              })}
                            </div>

                            <input
                              type="text"
                              value={customTopic}
                              onChange={(e) => setCustomTopic(e.target.value)}
                              placeholder="Or type a custom topic..."
                              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy"
                            />
                          </div>

                          {/* 4. Additional Context Section */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <span className="text-xs font-black text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                              <MessageSquare className="w-3.5 h-3.5 text-hp-navy" />
                              <span>Additional Context (Optional)</span>
                            </span>

                            <textarea
                              rows={8}
                              value={additionalContext}
                              onChange={(e) => setAdditionalContext(e.target.value)}
                              placeholder="Add specific context, talking points, or recent developments to incorporate..."
                              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy resize-y min-h-[10rem]"
                            />
                          </div>

                          {/* Suggested angles: dropped (Sahaj, 27 Sep) - the context box above carries the seller's steer. */}
                          {/* 6. Generate Button */}
                          <button
                            onClick={handleGenerateClick}
                            disabled={isGeneratingContent}
                            className="w-full py-3 px-4 bg-hp-navy hover:bg-blue-900 text-white font-extrabold text-xs rounded-xl shadow-md transition flex items-center justify-center gap-2 disabled:opacity-50"
                          >
                            {isGeneratingContent ? (
                              <>
                                <Loader2 className="w-4 h-4 animate-spin text-white" />
                                <span>Generating ABM Content...</span>
                              </>
                            ) : (
                              <>
                                <Sparkles className="w-4 h-4 text-amber-300" />
                                <span>Generate Content</span>
                              </>
                            )}
                          </button>

                        </div>

                        {/* Right Output Canvas (7 Cols) */}
                        <div className={`lg:col-span-7 bg-white rounded-2xl border shadow-sm transition-colors ${
                          isGeneratingContent
                            ? 'border-sky-200 p-5 text-left'
                            : 'border-slate-200 p-8 min-h-[320px] flex flex-col justify-center items-center text-center'
                        }`}>

                          {isGeneratingContent ? (
                            <div className="w-full space-y-4 animate-fade-in" role="status" aria-live="polite">
                              <div className="flex items-center gap-2 text-sm font-medium text-blue-600">
                                <Loader2 className="w-4 h-4 animate-spin" />
                                <span>
                                  Crafting your {activeFormatObj?.id === 'linkedin' ? 'LinkedIn post' : (activeFormatObj?.title || 'content').toLowerCase()}...
                                </span>
                              </div>
                              <div className="space-y-3">
                                {['w-[82%]', 'w-[87%]', 'w-[62%]', 'w-[80%]', 'w-[68%]', 'w-[93%]', 'w-[74%]', 'w-[65%]'].map((w, i) => (
                                  <div
                                    key={i}
                                    className={`cs-skeleton-line h-3.5 ${w} rounded-md`}
                                    style={{ animationDelay: `${i * 90}ms` }}
                                  />
                                ))}
                              </div>
                            </div>
                          ) : generateError && !hasGeneratedContent ? (
                            <div className="max-w-md space-y-3 animate-fade-in">
                              <div className="w-14 h-14 rounded-2xl bg-rose-50 border border-rose-200 flex items-center justify-center mx-auto text-rose-500 shadow-xs">
                                <Sparkles className="w-7 h-7" />
                              </div>
                              <h4 className="text-base font-extrabold text-slate-800">
                                Draft not published{Array.isArray(generateError.attempts) && generateError.attempts.length > 0 ? ` after ${generateError.attempts.length} attempt${generateError.attempts.length === 1 ? '' : 's'}` : ''}
                              </h4>
                              <p className="text-xs text-slate-500 leading-relaxed font-medium">{generateError.notice}</p>
                              {Array.isArray(generateError.faults) && generateError.faults.length > 0 && (
                                <ul className="text-left text-[11px] text-rose-800 bg-rose-50 border border-rose-200 rounded-xl p-3 space-y-1">
                                  {generateError.faults.map((f: string, i: number) => (
                                    <li key={i}>&bull; {f}</li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          ) : !hasGeneratedContent || !generatedAsset ? (
                            <div className="w-full max-w-md animate-fade-in">
                              <PenTool className="w-10 h-10 text-slate-400 mx-auto mb-4" />
                              <h4 className="text-base font-bold text-slate-600 mb-2">
                                Ready to generate
                              </h4>
                              <p className="text-sm text-slate-400 leading-relaxed">
                                Select a target persona and content type, then click &quot;Generate Content&quot;. Personalized ABM content will be created using {selectedAccount?.name || 'Target Account'} account intelligence and HP Inc. product positioning.
                              </p>
                            </div>
                          ) : (() => {
                            // A LinkedIn post comes back as 2-3 variants (HP_ABX_v3_final);
                            // every other format is a single asset. The chosen variant
                            // replaces the generated body, so everything below reads one shape.
                            const variants: any[] = generatedAsset.variants || [];
                            const activeVariant = variants.length > 1
                              ? (variants.find(v => v.variant_index === activeVariantIndex) || variants[0])
                              : null;
                            const g = (activeVariant?.generated) || generatedAsset.generated || {};
                            // Spec 3.5's brand template needs the account and the date. Both are
                            // read off the asset where it carries them and off the page where it
                            // does not, so an asset generated before this existed still prints.
                            const onePagerAccount =
                              generatedAsset.company_name
                              || evalOptions?.company_name
                              || selectedAccount?.name
                              || 'this account';
                            const onePagerDate = generatedAsset.generated_at
                              ? new Date(generatedAsset.generated_at).toLocaleDateString(undefined,
                                  { year: 'numeric', month: 'long', day: 'numeric' })
                              : '';
                            // G12 is the overflow rule. 3.5 says an overflowing 1-Pager is out of
                            // budget rather than something to shrink, and 3.4 fixes the budget at
                            // 350-500 words because that is "what fits on one page at readable
                            // body size" - so the word-budget warning IS the overflow warning.
                            const onePagerOverBudget = (generatedAsset.style_warnings || [])
                              .find((w: string) => w.startsWith('G12'));
                            const gr = generatedAsset.grounding_report || {};
                            const labels: [string, any][] = Object.entries(
                              (activeVariant?.evidence_labels) || generatedAsset.evidence_labels || {});
                            return (
                            <div className="w-full space-y-5 text-left animate-fade-in">

                              {/* Deterministic template, not generated copy. The spec
                                  requires the safe fallback be offered rather than
                                  nothing - and that it never read as model output. */}
                              {/* is_fallback stays on the asset (and in data_gaps); not flagged on screen. */}

                              {/* Variant switcher */}
                              {variants.length > 1 && (
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                    {variants.length} variants
                                  </span>
                                  {variants.map((v: any) => (
                                    <button
                                      key={v.variant_index}
                                      type="button"
                                      onClick={() => setActiveVariantIndex(v.variant_index)}
                                      className={`px-2.5 py-1 rounded-lg text-[11px] font-bold border transition ${
                                        (activeVariant?.variant_index === v.variant_index)
                                          ? 'bg-hp-navy text-white border-hp-navy'
                                          : 'bg-white text-slate-600 border-slate-200 hover:border-slate-300'
                                      }`}
                                    >
                                      Variant {v.variant_index}
                                    </button>
                                  ))}
                                </div>
                              )}

                              {/* Spec 3.5: an overflowing 1-Pager "is out of budget - fail it
                                  back to regeneration rather than shrinking the type". The budget
                                  is G12's, because 3.4 sets 350-500 words as what fits on one
                                  page. Surfaced here rather than blocking: the seller asked for
                                  this asset, and a one-word overrun is theirs to judge. */}
                              {generatedAsset.content_type === 'one_pager' && onePagerOverBudget && (
                                <div className="no-print rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                                  {onePagerOverBudget}. The one-page budget is what fits on A4 and
                                  US Letter at readable size &mdash; regenerate rather than shrink
                                  the type.
                                </div>
                              )}

                              {/* Card header: type and persona, with Copy / Download HTML */}
                              <div className="no-print flex items-center justify-between gap-3">
                                <div className="flex items-center gap-2 min-w-0 text-sm font-semibold text-slate-900">
                                  <PenTool className="w-4 h-4 text-hp-navy shrink-0" />
                                  <span className="truncate">
                                    {generatedAsset.content_type_label} - {generatedAsset.persona?.title}
                                  </span>
                                </div>
                                <div className="flex items-center gap-4 shrink-0 text-xs">
                                  {generatedAsset.plain_text && (
                                    <button
                                      onClick={async () => {
                                        try {
                                          // Copy what is on screen, not always variant 1.
                                          await navigator.clipboard.writeText(
                                            activeVariant?.plain_text || generatedAsset.plain_text);
                                          setCopiedAssetId(generatedAsset.asset_id);
                                          setTimeout(() => setCopiedAssetId(null), 1500);
                                        } catch {
                                          /* clipboard unavailable */
                                        }
                                      }}
                                      className="flex items-center gap-1.5 text-slate-500 hover:text-slate-800 transition"
                                    >
                                      <Copy className="w-3.5 h-3.5" />
                                      {copiedAssetId === generatedAsset.asset_id ? 'Copied' : 'Copy'}
                                    </button>
                                  )}
                                  {generatedAsset.content_type === 'one_pager'
                                      && (g.pillars || []).length > 0 && (
                                      <button
                                        onClick={() => window.print()}
                                        title="Opens the print dialog. Choose Save as PDF for a one-page file."
                                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-200 text-xs font-medium text-slate-600 hover:border-slate-300"
                                      >
                                        <Download className="w-3.5 h-3.5" />
                                        Print / Save as PDF
                                      </button>
                                    )}
                                  {generatedAsset.rendered_html && (
                                    <button
                                      onClick={() => downloadHtml(generatedAsset)}
                                      className="flex items-center gap-1.5 text-blue-600 hover:text-blue-800 font-medium transition"
                                    >
                                      <Download className="w-3.5 h-3.5" />
                                      Download HTML
                                    </button>
                                  )}
                                </div>
                              </div>

                              {/* The asset */}
                              {generatedAsset.content_type === 'one_pager' && (g.pillars || []).length > 0 ? (
                                /* Spec 3.5. This block is both the on-screen document and the
                                   printed one - `onepager-print` is what the print stylesheet
                                   keeps and everything else on the page is hidden. Rendered from
                                   the structured fields, never from generated markup. */
                                <div className="onepager-print bg-white border border-slate-200 rounded-2xl p-8 space-y-5 text-sm text-slate-800 leading-relaxed">

                                  {/* HP brand template: on paper only. On screen the card already
                                      sits under an HP-branded page. */}
                                  <div className="print-only" style={{ marginBottom: '14px' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '2px solid #0096D6', paddingBottom: '8px' }}>
                                      <span style={{ fontWeight: 800, fontStyle: 'italic', fontSize: '15pt', color: '#0096D6', letterSpacing: '-0.5px' }}>hp</span>
                                      <span style={{ fontSize: '8.5pt', color: '#52606D' }}>
                                        {onePagerAccount} &middot; Prepared by HP
                                      </span>
                                    </div>
                                  </div>

                                  {/* Title and subtitle */}
                                  {g.headline && (
                                    <h4 className="text-xl font-extrabold text-slate-900 leading-snug">{g.headline}</h4>
                                  )}
                                  {g.subtitle && (
                                    <p className="-mt-3 text-[13px] text-slate-500">{g.subtitle}</p>
                                  )}

                                  {/* Why now */}
                                  {(g.why_now || g.opening) && (
                                    <div className="space-y-1">
                                      <h5 className="text-[10px] font-black uppercase tracking-wider text-hp-navy">Why now</h5>
                                      <p>{g.why_now || g.opening}</p>
                                    </div>
                                  )}

                                  {/* The pillars, as pillars. Challenge and HP response are
                                      separate claims and are shown as separate claims - merged
                                      into one paragraph there is no way to see that a pillar
                                      asserts something HP does without saying what prompted it. */}
                                  <div className="space-y-4">
                                    {(g.pillars || []).map((p: any, i: number) => (
                                      <div key={i} className="onepager-pillar space-y-1 border-l-2 border-slate-200 pl-3">
                                        <h5 className="text-[10px] font-black uppercase tracking-wider text-hp-navy">
                                          {p.heading}
                                        </h5>
                                        <p>{p.challenge}</p>
                                        {p.hp_response && (
                                          <p className="text-slate-700">{p.hp_response}</p>
                                        )}
                                        {(p.evidence_used || []).length > 0 && (
                                          <p className="text-[10px] font-mono text-slate-400">
                                            {p.evidence_used.map((label: string) => `[${label}]`).join(' ')}
                                          </p>
                                        )}
                                      </div>
                                    ))}
                                  </div>

                                  {/* The one HP play */}
                                  {g.hp_play && (
                                    <div className="space-y-1">
                                      <h5 className="text-[10px] font-black uppercase tracking-wider text-hp-navy">The HP play</h5>
                                      <p>{g.hp_play}</p>
                                    </div>
                                  )}

                                  {/* Proof. Python attaches this after the line is settled - the
                                      model is never shown a case study. */}
                                  {(g.proof_point || generatedAsset.hp_proof_point) && (
                                    <div className="space-y-1">
                                      <h5 className="text-[10px] font-black uppercase tracking-wider text-hp-navy">Proof point</h5>
                                      <p>{g.proof_point || generatedAsset.hp_proof_point}</p>
                                    </div>
                                  )}

                                  {/* The ask */}
                                  {g.cta && <p className="font-semibold text-slate-900">{g.cta}</p>}

                                  {/* Provenance, on paper only. A seller forwarding this
                                      internally needs to know where it came from. The contact's
                                      name appears only where the client named one for the role -
                                      on an UNFILLED persona the document is addressed to the
                                      role, and 3.5 says the footer follows that. */}
                                  <div className="print-only" style={{ marginTop: '18px', borderTop: '1px solid #CBD2D9', paddingTop: '6px', fontSize: '7.5pt', color: '#7B8794', lineHeight: 1.5 }}>
                                    <div>
                                      Prepared for {generatedAsset.persona?.title}
                                      {generatedAsset.persona?.full_name ? ` · ${generatedAsset.persona.full_name}` : ''}
                                    </div>
                                    <div>
                                      Generated from HP Account Intelligence &mdash; {onePagerAccount} &mdash; {onePagerDate}
                                    </div>
                                  </div>
                                </div>
                              ) : generatedAsset.content_type === 'branded_emailer' ? (
                                <div className="rounded-xl border border-slate-200 overflow-hidden bg-white">
                                  <div className="bg-slate-50 px-4 py-3 text-[13px] leading-relaxed">
                                    <p>
                                      <span className="font-semibold text-slate-800">From:</span>{' '}
                                      <span className="text-slate-500">Your HP Account Team</span>
                                    </p>
                                    <p>
                                      <span className="font-semibold text-slate-800">To:</span>{' '}
                                      <span className="text-slate-500">
                                        {generatedAsset.persona?.kind === 'named' && generatedAsset.persona?.full_name
                                          ? `${generatedAsset.persona.full_name}, ${generatedAsset.persona.title}`
                                          : generatedAsset.persona?.title}
                                      </span>
                                    </p>
                                    {g.subject_line && (
                                      <p>
                                        <span className="font-semibold text-slate-800">Subject:</span>{' '}
                                        <span className="text-slate-500">{g.subject_line}</span>
                                      </p>
                                    )}
                                  </div>
                                  <div className="h-1.5 bg-gradient-to-r from-[#0096D6] to-[#00629B]" />
                                  <div className="px-5 py-5 space-y-4 text-[15px] text-slate-700 leading-7">
                                    <div className="flex items-center gap-2">
                                      <span className="w-7 h-7 rounded-full bg-[#0096D6] text-white text-xs font-bold italic flex items-center justify-center">
                                        hp
                                      </span>
                                      <span className="text-[11px] font-black text-slate-900">HP</span>
                                    </div>
                                    {generatedAsset.greeting && <p>{generatedAsset.greeting}</p>}
                                    {g.opening && <p>{g.opening}</p>}
                                    {(g.body_sections || []).map((sec: any, i: number) => (
                                      <p key={i}>{sec.text}</p>
                                    ))}
                                    {g.cta && <p>{g.cta}</p>}
                                  </div>
                                </div>
                              ) : generatedAsset.rendered_html ? (
                                <iframe
                                  title="Branded preview"
                                  srcDoc={generatedAsset.rendered_html}
                                  sandbox=""
                                  className="w-full h-[640px] rounded-xl border border-slate-200 bg-white"
                                />
                              ) : generatedAsset.content_type === 'linkedin' ? (
                                <div className="bg-white border border-slate-200 rounded-2xl p-5 space-y-3 text-sm text-slate-800 leading-relaxed">
                                  <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
                                    <div className="w-10 h-10 rounded-full bg-hp-navy text-white text-xs font-black flex items-center justify-center">
                                      HP
                                    </div>
                                    <div>
                                      <p className="text-sm font-bold text-slate-900">HP Seller</p>
                                      <p className="text-[11px] text-slate-500">LinkedIn post preview</p>
                                    </div>
                                  </div>
                                  {g.headline && <p className="font-semibold text-slate-900">{g.headline}</p>}
                                  {g.opening && <p>{g.opening}</p>}
                                  {(g.body_sections || []).map((sec: any, i: number) => (
                                    <p key={i} className="whitespace-pre-line">{sec.text}</p>
                                  ))}
                                  {g.cta && <p>{String(g.cta).replace(/\s*#\w+/g, '').trim()}</p>}
                                  {(() => {
                                    const tags: string[] = (g.hashtags && g.hashtags.length > 0)
                                      ? g.hashtags
                                      : (String(g.cta || '').match(/#\w+/g) || []);
                                    return tags.length > 0 ? (
                                      <p className="text-hp-navy font-semibold">{tags.join(' ')}</p>
                                    ) : null;
                                  })()}
                                </div>
                              ) : generatedAsset.plain_text && (generatedAsset.content_type === 'email' || generatedAsset.content_type === 'follow_up') ? (
                                <pre className="bg-white border border-slate-200 rounded-2xl p-6 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap font-sans">
                                  {generatedAsset.plain_text}
                                </pre>
                              ) : (
                                <div className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4 text-sm text-slate-800 leading-relaxed">
                                  {g.subject_line && ['email', 'follow_up', 'branded_emailer'].includes(generatedAsset.content_type) && (
                                    <div className="border-b border-slate-100 pb-3">
                                      <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">Subject</span>
                                      <p className="font-extrabold text-slate-900">{g.subject_line}</p>
                                    </div>
                                  )}
                                  {g.headline && <h4 className="text-lg font-extrabold text-slate-900">{g.headline}</h4>}
                                  {/* The 1-Pager's subtitle: who the document is for and what it
                                      covers. Only the structured contract carries it. */}
                                  {g.subtitle && <p className="-mt-2 text-[13px] text-slate-500">{g.subtitle}</p>}
                                  <p>{g.opening}</p>
                                  {(g.body_sections || []).map((sec: any, i: number) => (
                                    <div key={i} className="space-y-1">
                                      {sec.heading && <h5 className="text-xs font-black uppercase tracking-wider text-hp-navy">{sec.heading}</h5>}
                                      <p>{sec.text}</p>
                                    </div>
                                  ))}
                                  <p className="font-semibold text-slate-900">{g.cta}</p>
                                </div>
                              )}

                              {/* Provenance */}
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px]">
{/* Heading and panel only when something was cited. This
                                    printed "None cited." under an "Evidence used"
                                    heading, which is a note about an absence. */}
                                {labels.length > 0 && (
                                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                                  <span className="font-mono font-extrabold text-[10px] text-slate-500 uppercase block">Evidence used</span>
                                  {labels.map(([k, v]) => (
                                    <div key={k}>
                                      <span className="font-mono font-bold text-hp-navy">[{k}]</span>{' '}
                                      <span className="text-slate-700">{String(v).slice(0, 160)}{String(v).length > 160 ? '…' : ''}</span>
                                    </div>
                                  ))}
                                </div>
                                )}
                                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                                  <span className="font-mono font-extrabold text-[10px] text-slate-500 uppercase block">HP lines &amp; framing</span>
                                  {generatedAsset.topic && <div className="text-slate-500">Topic: {generatedAsset.topic}</div>}
                                  <div className="font-semibold text-slate-800">
                                    {(g.hp_products || []).length > 0 ? g.hp_products.join(', ') : 'Discovery-led'}
                                  </div>
                                  {g.persona_framing && <div className="italic text-slate-600">{g.persona_framing}</div>}
                                  <div className="text-slate-500">
                                    Grounding: {gr.numbers_checked ?? 0} number(s) checked, {(gr.numbers_rejected || []).length} rejected &middot; {(gr.urls_rejected || []).length} URL(s) stripped
                                  </div>
                                  {/* Where the Proof Points section came from. The sentence
                                      itself is already in the copy above; what a seller needs
                                      here is the customer and the public HP page behind it,
                                      so the claim can be checked before it is sent. */}
                                  {g.hp_proof_point_detail && (
                                    <div className="text-slate-600">
                                      Proof point:{' '}
                                      <span className="font-semibold text-slate-800">{g.hp_proof_point_detail.customer}</span>
                                      {/* Guarded like every other proof-point link. This one
                                          rendered the raw URL, so the three case-study
                                          documents HP has retired were offered here as links
                                          while the rest of the app already suppressed them. */}
                                      {openableUrl(g.hp_proof_point_detail.source_url, sourceLinkCtx) && (
                                        <>
                                          {' · '}
                                          <a
                                            href={openableUrl(g.hp_proof_point_detail.source_url, sourceLinkCtx)}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="underline hover:text-hp-navy"
                                          >
                                            HP case study
                                          </a>
                                        </>
                                      )}
                                    </div>
                                  )}
                                  {Array.isArray(generatedAsset.style_warnings) && generatedAsset.style_warnings.length > 0 && (
                                    <div className="text-amber-800">
                                      <span className="font-bold">Style to fix before sending:</span>{' '}
                                      {generatedAsset.style_warnings.join('; ')}
                                      {generatedAsset.attempts ? ` (kept after ${generatedAsset.attempts} attempts)` : ''}
                                    </div>
                                  )}
                                </div>
                              </div>

                            </div>
                            );
                          })()}

                        </div>

                      </div>

                    </div>
                  );
                })()}

                {activeFeatureKey === 'strategy_chat' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'strategy_snapshot_context');
                  const interfaceWidget = widgets.find(w => w.widget_key === 'strategy_chat_interface');

                  const contextData = contextWidget?.data || {};
                  const groundingMeta = contextData.grounding_metadata || {};
                  // Who is being rehearsed with, if anyone. Looked up rather
                  // than stored so it cannot drift from the selector.
                  const activePersona = chatPersonaId
                    ? chatPersonas.find((p: any) => p.persona_id === chatPersonaId)
                    : null;
                  // A rehearsal needs openers a seller would SAY, not questions
                  // about the account. They are built per persona from that
                  // person's own evidence, by the backend, deterministically.
                  const suggestedPrompts: any[] = (
                    activePersona?.starter_prompts?.length
                      ? activePersona.starter_prompts
                      : contextData.suggested_prompts
                  ) || [
                    {
                      id: 'entry_point',
                      title: 'Best entry point',
                      prompt_text: `What's the strongest entry point for engaging ${selectedAccount?.name || 'Target Account'}? Consider their active IT projects.`
                    },
                    {
                      id: 'meeting_prep',
                      title: 'Meeting prep',
                      prompt_text: `Help me prepare for a meeting with ${selectedAccount?.name || 'Target Account'}'s security leadership. What below-the-OS value propositions resonate best?`
                    },
                    {
                      id: 'competitive_defense',
                      title: 'Competitive defense',
                      prompt_text: `What competitive risks should I prepare for in the deal at ${selectedAccount?.name || 'Target Account'}? Give me counter-strategies for Dell and Lenovo.`
                    },
                    {
                      id: 'abm_plan',
                      title: '90-day ABM plan',
                      prompt_text: `Draft a 90-day ABM campaign plan for ${selectedAccount?.name || 'Target Account'}. Include week-by-week stakeholder outreach cadence.`
                    },
                    {
                      id: 'objections',
                      title: 'Objections',
                      prompt_text: `What objections will ${selectedAccount?.name || 'Target Account'}'s leadership likely raise about adopting HP hardware subscriptions?`
                    },
                    {
                      id: 'device_security',
                      title: 'Device & security posture',
                      prompt_text: `Analyze ${selectedAccount?.name || 'Target Account'}'s current device fleet and endpoint security posture based on technographics signals.`
                    }
                  ];

                  const companyName = groundingMeta.company_name || selectedAccount?.name || 'Target Account';
                  const handleSendPrompt = async (promptText: string) => {
                    if (!promptText.trim() || chatPending) return;
                    const stamp = () => new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                    const userMsg = {
                      id: `user_${Date.now()}`,
                      sender: 'user' as const,
                      text: promptText,
                      timestamp: stamp(),
                    };

                    // The whole conversation goes with every question. The chat
                    // is stateless per account on the server, which is what lets
                    // ABX's rule hold: switching account clears these messages,
                    // and the old turns simply stop being sent.
                    // The clean form goes back to the model. Sending the
                    // rendered answer taught it that an assistant turn looks
                    // like prose with [section] tags glued on, which is the
                    // habit the segment contract exists to break.
                    const history = [...chatMessages, userMsg].map(m => ({
                      role: m.sender === 'user' ? 'user' : 'assistant',
                      content: m.sender === 'assistant' ? (m.clean || m.text) : m.text,
                    }));

                    setChatMessages(prev => [...prev, userMsg]);
                    setChatInput('');
                    setChatPending(true);

                    // The server reports its own stages now, so nothing here is
                    // on a timer. `delta` carries the whole validated answer so
                    // far rather than an increment, which means a dropped or
                    // late event costs nothing - the next one is still correct
                    // on its own, and `done` carries the finished answer.
                    setChatStage(0);
                    setChatStreamingText('');
                    const STAGES: Record<string, number> = {
                      reading: 0, writing: 1, rewriting: 1, checking: 2,
                    };

                    let settled = false;
                    const publish = (
                      text: string, citations: any[], available: boolean,
                      personaTitle?: string, clean?: string, dropped?: number,
                    ) => {
                      settled = true;
                      setChatMessages(prev => [...prev, {
                        id: `asst_${Date.now()}`,
                        sender: 'assistant' as const,
                        text, clean: clean || text,
                        timestamp: stamp(), citations, available,
                        personaTitle, dropped,
                      }]);
                    };

                    try {
                      await postStream(
                        `/accounts/${selectedAccount.id}/widgets/strategy_chat/ask/stream`,
                        { messages: history, mode: 'advisor' },
                        (event) => {
                          if (event.type === 'stage') {
                            setChatStage(STAGES[event.stage ?? ''] ?? 0);
                            // A rewrite is a second attempt over text the
                            // seller is already reading. Clearing it is the
                            // honest thing to do - the answer they were shown
                            // was rejected, and the replacement is not written
                            // yet.
                            if (event.stage === 'rewriting') setChatStreamingText('');
                          } else if (event.type === 'delta') {
                            setChatStreamingText(event.text ?? '');
                          } else if (event.type === 'done') {
                            publish(
                              (event.answer as string) || 'No answer was returned.',
                              (event.citations as any[]) || [],
                              event.available !== false,
                              // From the response, not the current selection:
                              // a rejected rehearsal comes back out of
                              // character and must not be labelled as the
                              // role having said it.
                              event.available === false
                                ? undefined
                                : (event.persona as any)?.title,
                              (event.answer_clean as string) || undefined,
                              // How much of the answer was thrown away for
                              // want of evidence. Shown, because a gutted
                              // answer that looks whole is worse than a short
                              // one that admits it.
                              ((event.generation as any)?.segments_dropped as number)
                                || undefined,
                            );
                          } else if (event.type === 'error') {
                            publish(
                              event.detail
                                || 'The strategy assistant could not be reached.',
                              [], false,
                            );
                          }
                        },
                      );
                      // A stream that ends without `done` - a dropped
                      // connection - must not leave the question unanswered in
                      // the thread.
                      if (!settled) {
                        publish('The strategy assistant could not complete that answer.',
                                [], false);
                      }
                    } catch {
                      if (!settled) {
                        publish('The strategy assistant could not be reached.',
                                [], false);
                      }
                    } finally {
                      setChatStage(0);
                      setChatStreamingText('');
                      setChatPending(false);
                    }
                  };

                  return (
                    <div className="space-y-6 animate-fade-in">
                      {/* Top Header */}
                      <div className="border-b border-slate-200 pb-4">
                        <h3 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                          <MessageSquare className="w-6 h-6 text-hp-navy" />
                          <span>AI Strategy Chat</span>
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Brainstorm GTM &amp; ABM strategy for {companyName} - grounded in account intelligence
                        </p>
                      </div>

                      {/* Grounding Bar */}
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs">
                        {/* The mode the chat runs in, and there is one.

                            It was a four-option dropdown that sent nothing,
                            then a real selector offering a rehearsal with each
                            stakeholder on the account. Both are gone: the
                            product is the advisor, and a picker whose other
                            options nobody wants is a way to land in a mode by
                            accident and wonder why the answers changed.

                            A label rather than a one-item select, because a
                            chevron invites a click that has nowhere to go.

                            Nothing was removed behind this. The backend still
                            has the roleplay path, its validator and its
                            persona endpoint, and `StrategyChatRequest` still
                            carries `mode` and `persona_id` - so putting the
                            picker back is this block and nothing else. */}
                        <div className="flex items-center gap-2">
                          {/* Role first, name as provenance. "Chief Operating
                              Officer - from Irvan Nr's record" says the seller
                              is preparing for that person WITHOUT framing the
                              dialogue as that person speaking, which is the
                              distinction the whole feature rests on. */}
                          <span className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs font-extrabold text-slate-800 shadow-xs">
                            🤖 Strategy Advisor
                          </span>
                        </div>

                        <div className="flex items-center gap-1.5 text-slate-500 font-medium">
                          <Info className="w-3.5 h-3.5 text-hp-navy" />
                          {/* No stakeholder count (Sahaj, 27 Sep: "this has nothing to do with chat"). */}
                          <span>Grounded in: <strong className="text-slate-800">{companyName} Intelligence</strong></span>
                        </div>
                      </div>

                      {/* Main Canvas: Welcome Cards OR Chat Thread */}
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 min-h-[500px] flex flex-col justify-between">
                        
                        {chatMessages.length === 0 ? (
                          /* Welcome / Suggested Prompts View */
                          <div className="space-y-8 my-auto animate-fade-in">
                            <div className="text-center max-w-2xl mx-auto space-y-3">
                              <div className="w-14 h-14 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center mx-auto text-hp-navy shadow-xs">
                                <MessageSquare className="w-7 h-7 text-hp-navy" />
                              </div>
                              <h4 className="text-lg font-black text-slate-900">
                                {activePersona ? `Rehearsal: ${activePersona.title}` : 'ABM Strategy Assistant'}
                              </h4>
                              {activePersona ? (
                                /* The disclaimer is the Objection Playbook's,
                                   verbatim, because it is the same claim about
                                   the same data - these are anticipated
                                   positions, not things anyone said. Naming the
                                   record it was built from keeps the provenance
                                   visible without framing the dialogue as that
                                   person speaking. */
                                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                                  You are practising against the <strong className="text-slate-800">{activePersona.title}</strong> role at {companyName}
                                  {activePersona.name ? <> , built from {activePersona.name}&apos;s record</> : null}.
                                  <span className="block mt-1.5 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2.5 py-1.5">
                                    A simulation of this role, built from the account&apos;s own evidence. Not statements made by any contact.
                                  </span>
                                </p>
                              ) : (
                                <p className="text-xs text-slate-600 leading-relaxed font-medium">
                                  Ask me anything about {companyName}, HP Inc. positioning, competitive strategy, or ABM campaign planning. I&apos;m grounded in {companyName}&apos;s actual data and strategic priorities.
                                </p>
                              )}
                            </div>

                            {/* 6 Suggested Prompt Cards Grid */}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-w-4xl mx-auto">
                              {suggestedPrompts.map((p) => (
                                <button
                                  key={p.id}
                                  onClick={() => handleSendPrompt(p.prompt_text)}
                                  className="text-left p-4 rounded-2xl border border-slate-200 bg-slate-50/60 hover:bg-blue-50/60 hover:border-hp-navy/40 transition space-y-1.5 group flex flex-col justify-between shadow-xs"
                                >
                                  <div>
                                    <span className="text-xs font-black text-hp-navy flex items-center gap-1.5 group-hover:text-blue-900">
                                      <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                                      <span>{p.title}</span>
                                    </span>
                                    <p className="text-[11px] text-slate-600 font-medium line-clamp-2 mt-1">
                                      {p.prompt_text}
                                    </p>
                                  </div>
                                </button>
                              ))}
                            </div>
                          </div>
                        ) : (
                          /* Interactive Chat Messages Thread */
                          <div className="space-y-4 max-h-[460px] overflow-y-auto pr-2 w-full animate-fade-in">
                            {chatMessages.map((msg) => (
                              <div
                                key={msg.id}
                                className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                              >
                                {msg.sender === 'user' ? (
                                  <div className="bg-hp-navy text-white rounded-2xl p-4 max-w-2xl space-y-1 shadow-xs">
                                    <p className="text-xs font-medium leading-relaxed">{msg.text}</p>
                                    <span className="text-[9px] font-mono opacity-60 block text-right">{msg.timestamp}</span>
                                  </div>
                                ) : (
                                  <div className="bg-slate-50 border border-slate-200 text-slate-800 rounded-2xl p-5 max-w-2xl space-y-3 shadow-xs">
                                    <div className="flex items-center justify-between gap-2 border-b border-slate-200/80 pb-2">
                                      <span className="text-xs font-black text-hp-navy flex items-center gap-1.5">
                                        <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                                        <span>{msg.personaTitle || 'ABM Strategy Assistant'}</span>
                                      </span>
                                    </div>

                                    {/* The answer is plain text with UPPERCASE
                                        headers and numbered lists, so it is
                                        rendered as written rather than parsed
                                        as markdown - except for the evidence
                                        tags, which become footnote markers. */}
                                    {/* Only citations with a link that opens are listed
                                        (client, 7 Oct), and only those get a footnote
                                        marker - AnswerWithCitations drops a tag whose
                                        citation is not in the list it is given, so the
                                        numbers and the list always agree. */}
                                    {(() => {
                                      const cites = (msg.citations || [])
                                        .map((c: any) => ({ c, href: sourceHref(c, sourceLinkCtx) }))
                                        .filter((x: any) => x.href);
                                      return (
                                        <>
                                          <AnswerWithCitations
                                            text={msg.text}
                                            citations={cites.map((x: any) => x.c)}
                                            idPrefix={msg.id}
                                          />
                                          {cites.length > 0 && (
                                            <div className="pt-2 border-t border-slate-200/80 space-y-1.5">
                                              <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">
                                                Sources ({cites.length})
                                              </span>
                                              {cites.map(({ c, href }: any, ci: number) => (
                                                <div key={ci} id={`${msg.id}-src-${ci + 1}`}
                                                     className="text-[10px] text-slate-600 leading-relaxed scroll-mt-24">
                                                  <span className="font-bold text-slate-400 mr-1">{ci + 1}.</span>
                                                  <a href={href} target="_blank" rel="noopener noreferrer"
                                                     className="text-hp-navy hover:underline inline-flex items-center gap-1">
                                                    <FileText className="w-3 h-3 flex-shrink-0" />
                                                    <span>{c.publisher
                                                      || (c.filing_label ? `${c.filing_label}${c.page ? ` p.${c.page}` : ''}` : '')
                                                      || hostLabel(href) || c.dataset}</span>
                                                    <ExternalLink className="w-2.5 h-2.5" />
                                                  </a>
                                                  {c.source_text && <span> — {c.source_text}</span>}
                                                </div>
                                              ))}
                                            </div>
                                          )}
                                        </>
                                      );
                                    })()}

                                    {/* Copy and Send as email, as the reference
                                        offers. The email is a mailto: so it
                                        opens the seller's own client with their
                                        own signature - nothing is sent from
                                        here, and no account data leaves the
                                        browser on our account. */}
                                    <div className="flex items-center gap-3 pt-1">
                                      <button
                                        type="button"
                                        onClick={() => {
                                          navigator.clipboard?.writeText(msg.clean || msg.text);
                                          setCopiedMessageId(msg.id);
                                          setTimeout(() => setCopiedMessageId(null), 1500);
                                        }}
                                        className="text-[10px] font-bold text-slate-500 hover:text-hp-navy inline-flex items-center gap-1 transition"
                                      >
                                        <FileText className="w-3 h-3" />
                                        {copiedMessageId === msg.id ? 'Copied' : 'Copy'}
                                      </button>
                                      <a
                                        href={`mailto:?subject=${encodeURIComponent(`${companyName} — ABM strategy notes`)}&body=${encodeURIComponent(msg.clean || msg.text)}`}
                                        className="text-[10px] font-bold text-slate-500 hover:text-hp-navy inline-flex items-center gap-1 transition"
                                      >
                                        <Mail className="w-3 h-3" />
                                        Send as email
                                      </a>
                                    </div>

                                    <span className="text-[9px] font-mono text-slate-400 block">{msg.timestamp}</span>
                                  </div>
                                )}
                              </div>
                            ))}

                            {/* What is happening during the wait.

                                The answer cannot be shown as it is written:
                                every claim is checked against the retrieved
                                evidence first, and an answer that fails is
                                rewritten rather than published. Streaming the
                                draft would put an unverified sentence in front
                                of a seller and then take it back, which is the
                                one thing this feature promises not to do.

                                So the wait is narrated instead of filled. The
                                steps are the real pipeline, named in the
                                seller's terms, and the checking step is listed
                                because it is the reason the wait exists. */}
                            {chatPending && (
                              <div className="flex justify-start">
                                <div className="bg-slate-50 border border-slate-200 rounded-2xl p-5 max-w-2xl w-full space-y-3 shadow-xs animate-fade-in">
                                  <div className="flex items-center gap-1.5 border-b border-slate-200/80 pb-2">
                                    <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                                    <span className="text-xs font-black text-hp-navy">ABM Strategy Assistant</span>
                                  </div>
                                  {/* The answer as it is written. Only text the
                                      server has already validated reaches here:
                                      it releases up to the last resolved
                                      citation and holds the sentence in flight
                                      back, so a figure the checker has not seen
                                      is never on screen. */}
                                  {chatStreamingText && (
                                    <div className="text-xs text-slate-800 leading-relaxed whitespace-pre-wrap border-b border-slate-200/80 pb-3">
                                      {chatStreamingText}
                                      <span className="inline-block w-1.5 h-3.5 ml-0.5 bg-hp-navy/60 align-text-bottom animate-pulse" />
                                    </div>
                                  )}

                                  <div className="space-y-2">
                                    {[
                                      { label: `Reading ${companyName}'s account intelligence` },
                                      { label: 'Writing your answer' },
                                      { label: 'Checking every fact against the evidence' },
                                    ].map((step, i) => {
                                      const done = i < chatStage;
                                      const active = i === chatStage;
                                      return (
                                        <div key={step.label} className="flex items-center gap-2.5">
                                          {done ? (
                                            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                                          ) : active ? (
                                            <Loader2 className="w-3.5 h-3.5 text-hp-navy animate-spin flex-shrink-0" />
                                          ) : (
                                            <div className="w-3.5 h-3.5 flex items-center justify-center flex-shrink-0">
                                              <div className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                                            </div>
                                          )}
                                          <span className={`text-xs ${done ? 'text-slate-400' : active ? 'font-bold text-slate-800' : 'text-slate-400'}`}>
                                            {step.label}
                                          </span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                  <p className="text-[10px] text-slate-400 leading-relaxed pt-1 border-t border-slate-200/80">
                                    Answers are shown only once every fact has been matched to account evidence.
                                  </p>
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Bottom Input Controls */}
                        <div className="pt-4 border-t border-slate-100 w-full mt-4">
                          <form
                            onSubmit={(e) => {
                              e.preventDefault();
                              handleSendPrompt(chatInput);
                            }}
                            className="flex items-center gap-2"
                          >
                            <input
                              type="text"
                              value={chatInput}
                              onChange={(e) => setChatInput(e.target.value)}
                              placeholder={`Ask about ${companyName} strategy, competitive positioning, campaign ideas...`}
                              className="flex-1 px-4 py-3 bg-slate-50 border border-slate-300 rounded-2xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy shadow-xs"
                            />
                            <button
                              type="submit"
                              disabled={!chatInput.trim() || chatPending}
                              className="p-3 bg-hp-navy hover:bg-blue-900 text-white rounded-2xl transition disabled:opacity-40 shadow-xs flex items-center justify-center flex-shrink-0"
                            >
                              {chatPending
                                ? <Loader2 className="w-4 h-4 animate-spin" />
                                : <Sparkles className="w-4 h-4 text-amber-300" />}
                            </button>
                          </form>
                        </div>

                      </div>

                    </div>
                  );
                })()}

                {/* For all other Features (if any future unhandled feature is added) */}
                {activeFeatureKey !== 'executive_dashboard' && activeFeatureKey !== 'recent_news_signals' && activeFeatureKey !== 'intent_demand_signals' && activeFeatureKey !== 'solution_narrative_opportunity_map' && activeFeatureKey !== 'stakeholder_map' && activeFeatureKey !== 'tech_landscape' && activeFeatureKey !== 'objection_playbook' && activeFeatureKey !== 'content_messaging' && activeFeatureKey !== 'content_studio' && activeFeatureKey !== 'strategy_chat' && activeFeatureKey !== 'message_evaluator' && (
                  <div className="space-y-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                          <span>{activeFeatureDef.label} Widgets</span>
                        </h3>
                        <p className="text-xs text-slate-500 mt-0.5">{activeFeatureDef.description}</p>
                      </div>

                      {isXRayOn && (
                        <div className="text-[11px] font-mono text-hp-navy bg-blue-50 px-2.5 py-1 rounded-lg border border-blue-200">
                          X-Ray Mode Active
                        </div>
                      )}
                    </div>

                    {isLoadingWidgets ? (
                      <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm flex flex-col items-center justify-center space-y-3">
                        <Loader2 className="w-8 h-8 text-hp-navy animate-spin" />
                        <p className="text-xs text-slate-500 font-medium">Loading feature widget contracts...</p>
                      </div>
                    ) : widgets.length === 0 ? (
                      <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm">
                        <Info className="w-10 h-10 text-slate-300 mx-auto mb-2" />
                        <h3 className="text-sm font-bold text-slate-800">No Widget Contracts Defined</h3>
                        <p className="text-xs text-slate-500 mt-1">
                          No widget contracts registered for feature "{activeFeatureDef.label}".
                        </p>
                      </div>
                    ) : (
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        {widgets.map((widget) => (
                          <div key={widget.widget_key} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                            
                            {/* Widget Card Header */}
                            <div className="flex items-start justify-between gap-3 border-b border-slate-100 pb-3">
                              <div>
                                <div className="flex items-center space-x-2">
                                  <h3 className="text-sm font-extrabold text-slate-900">{widget.widget_name}</h3>
                                  {isXRayOn && (
                                    <span className="text-[10px] font-mono text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">
                                      {widget.widget_type}
                                    </span>
                                  )}
                                </div>
                                <p className="text-xs text-slate-500 mt-0.5">{widget.description}</p>
                              </div>

                              {/* Classification Badge */}
                              <div className="flex-shrink-0">
                                {getClassificationBadge(widget.data_classification)}
                              </div>
                            </div>

                            {/* X-Ray Mode Debug Metadata Bar */}
                            {isXRayOn && (
                              <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80 space-y-1.5 text-[11px]">
                                <div className="flex flex-wrap items-center gap-1.5">
                                  <span className="text-slate-400 font-bold uppercase text-[10px]">Source Datasets:</span>
                                  {widget.source_datasets.map((ds) => (
                                    <span key={ds} className="inline-flex items-center px-2 py-0.5 rounded bg-white text-slate-700 font-mono text-[10px] border border-slate-200">
                                      <Database className="w-3 h-3 mr-1 text-hp-navy" />
                                      {ds}
                                    </span>
                                  ))}
                                </div>

                                <div className="flex flex-wrap items-center gap-1">
                                  <span className="text-slate-400 font-bold uppercase text-[10px]">Mapped Fields:</span>
                                  {widget.source_fields.map((field) => (
                                    <span key={field} className="text-slate-600 font-mono text-[10px] bg-slate-200/60 px-1.5 py-0.5 rounded">
                                      {field}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Widget Contract Empty Placeholder */}
                            <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-6 text-center space-y-2">
                              <div className="w-8 h-8 rounded-full bg-slate-200/70 text-slate-500 flex items-center justify-center mx-auto">
                                <Info className="w-4 h-4" />
                              </div>
                              <p className="text-xs text-slate-400">{NO_SIGNAL}</p>
                            </div>

                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

              </div>
            )}

          </main>
        </div>

      </div>
      <MyActivityPanel open={isMyActivityOpen} onClose={closeMyActivity} userName={user?.full_name} />
      </AccountIdContext.Provider>
    </ProtectedRoute>
  );
}
