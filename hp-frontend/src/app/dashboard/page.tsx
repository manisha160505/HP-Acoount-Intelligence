'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/providers/AuthProvider';
import api from '@/services/api';
import { CompanyAccount } from '@/types/account';
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
  ChevronUp,
  LayoutDashboard,
  Newspaper,
  Users,
  Lightbulb,
  Compass,
  Cpu,
  ShieldAlert,
  Shield,
  Clock,
  FileText,
  Package,
  MessageSquare,
  HelpCircle,
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
  Maximize2,
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
  ArrowRight,
  RotateCcw,
  Copy,
  Download,
  ShieldCheck,
  UserCheck,
  CheckCircle2,
  Minus,
  BarChart3
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

interface SidebarItem {
  key: string;
  label: string;
  subtitle: string;
  description: string;
  iconName: string;
}

interface SidebarGroup {
  sectionTitle: string;
  items: SidebarItem[];
}

const NORTHSTAR_SIDEBAR_GROUPS: SidebarGroup[] = [
  {
    sectionTitle: "INTELLIGENCE",
    items: [
      { key: 'executive_dashboard', label: 'Executive Dashboard', subtitle: 'Account profile & key metrics', description: 'Account profile & key metrics', iconName: 'LayoutDashboard' },
      { key: 'recent_news_signals', label: 'Live Signals', subtitle: 'Real-time news & triggers', description: 'Real-time news & triggers', iconName: 'Newspaper' },
      { key: 'intent_demand_signals', label: 'Intent & Demand Signals', subtitle: 'HP-category & topic-level research intent', description: 'HP-category & topic-level research intent', iconName: 'TrendingUp' },
      { key: 'stakeholder_map', label: 'Stakeholder Map', subtitle: 'Contacts & influence map', description: 'Contacts & influence map', iconName: 'Users' },
      { key: 'solution_narrative_opportunity_map', label: 'Opportunity Map', subtitle: 'HP plays: outcome, impact & evidence', description: 'HP plays: outcome, impact & evidence', iconName: 'Lightbulb' },
      { key: 'tech_landscape', label: 'Technographic Map', subtitle: 'Tech stack by category & HP fit', description: 'Tech stack by category & HP fit', iconName: 'Cpu' },
      { key: 'objection_playbook', label: 'Objection Playbook', subtitle: 'Reframes & proof points', description: 'Reframes & proof points', iconName: 'ShieldAlert' }
    ]
  },
  {
    sectionTitle: "ACTION",
    items: [
      { key: 'content_messaging', label: 'Content Messaging', subtitle: 'Campaign messaging pillars', description: 'Campaign messaging pillars', iconName: 'Megaphone' },
      { key: 'content_studio', label: 'Content Studio', subtitle: 'Generate tailored content', description: 'Generate tailored content', iconName: 'FileText' },
      { key: 'strategy_chat', label: 'Strategy Chat', subtitle: 'AI strategy assistant', description: 'AI strategy assistant', iconName: 'MessageSquare' }
    ]
  },
  {
    sectionTitle: "SIMULATION & PLANNING",
    items: [
      { key: 'message_evaluator', label: 'Message Evaluator', subtitle: 'Test messages against personas', description: 'Test messages against personas', iconName: 'CheckSquare' }
    ]
  }
];





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

// A widget that never generated stores the reason on its payload. Showing it
// turns an unexplained empty panel into something a reader can act on - most
// often a missing OPENAI_API_KEY, or source files absent from this machine.
function PendingNotice({ widget, title }: { widget: any; title: string }) {
  const notice = widget?.data?.notice;
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

// One HP recommendation, rendered to match the vendor cards it sits beneath.
// The product, the confidence and the approved facts are all decided in Python;
// this only lays them out.
function HpRecommendationCard({ rec }: { rec: any }) {
  const withheld: Record<string, number> = rec.withheld_summary || {};
  const withheldEntries = Object.entries(withheld);
  const conf = String(rec.confidence || '');
  const confClass =
    conf === 'Confirmed' ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : conf === 'Likely' ? 'bg-amber-50 text-amber-700 border-amber-200'
    : 'bg-slate-100 text-slate-600 border-slate-200';

  return (
    <div className="bg-indigo-50/40 border border-indigo-100 rounded-2xl p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2 border-b border-indigo-100 pb-2">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-indigo-600">
            HP Recommendation
          </span>
          <span className="text-xs font-black text-slate-900">HP {rec.hp_family}</span>
          {rec.device_type && (
            <span className="text-[10px] uppercase tracking-wider bg-white text-slate-600 px-1.5 py-0.5 rounded border border-slate-200">
              {rec.device_type}
            </span>
          )}
          <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded border ${confClass}`}>
            {conf}
          </span>
        </div>
        <span className="text-[10px] font-mono text-slate-400 whitespace-nowrap">
          Rule {rec.rule_id}
        </span>
      </div>

      {rec.rationale && (
        <p className="text-xs text-slate-700 leading-relaxed">{rec.rationale}</p>
      )}
      {rec.why_this_product && (
        <p className="text-xs text-slate-600 leading-relaxed">{rec.why_this_product}</p>
      )}

      {(rec.approved_facts || []).length > 0 && (
        <div className="bg-white border border-slate-100 rounded-xl p-3 space-y-1.5">
          <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-slate-500 block">
            HP facts approved for this account
          </span>
          {(rec.approved_facts || []).slice(0, 6).map((f: any, i: number) => (
            <div key={i} className="text-xs text-slate-700">
              <span>&bull; {f.text}</span>
              {(f.conditions || []).length > 0 && (
                <span className="block text-[10px] text-slate-500 ml-3 mt-0.5 leading-snug">
                  {f.conditions[0]}
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {withheldEntries.length > 0 && (
        <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          <span className="font-semibold">Withheld for this market or configuration: </span>
          {withheldEntries.map(([reason, count]) => `${reason} (${count})`).join(', ')}
        </p>
      )}

      {rec.discovery_question && (
        <p className="text-xs text-slate-600 italic border-l-2 border-indigo-200 pl-3">
          {rec.discovery_question}
        </p>
      )}
    </div>
  );
}

export default function UserDashboardPage() {
  const { user, logout } = useAuth();

  const [accounts, setAccounts] = useState<CompanyAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [selectedAccount, setSelectedAccount] = useState<CompanyAccount | null>(null);
  const [activeFeatureKey, setActiveFeatureKey] = useState<string>('executive_dashboard');
  
  const [widgets, setWidgets] = useState<WidgetResponse[]>([]);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(true);
  const [isLoadingWidgets, setIsLoadingLoadingWidgets] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // X-Ray Mode Toggle State (Northstar Debug / Provenance View)
  const [isXRayOn, setIsXRayOn] = useState(false);
  const [provenanceSearch, setProvenanceSearch] = useState('');
  const [provenanceSourceFilter, setProvenanceSourceFilter] = useState('ALL');

  // Urgency Score Driver Popover & Tooltip State
  const [activeDriverPopover, setActiveDriverPopover] = useState<string | null>(null);
  const [hoveredDriverTooltip, setHoveredDriverTooltip] = useState<string | null>(null);

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
  const [expandedObjectionId, setExpandedObjectionId] = useState<string | null>(null);

  // Intent Topics Filter State
  const [intentSearch, setIntentSearch] = useState('');
  const [intentScoreFilter, setIntentScoreFilter] = useState('ALL');
  const [isOtherTopicsExpanded, setIsOtherTopicsExpanded] = useState(false);
  const [hoveredBarTopic, setHoveredBarTopic] = useState<{ name: string; score: number } | null>(null);

  // Stakeholder Map Filter & View Sub-Tab State
  const [stakeholderSearch, setStakeholderSearch] = useState('');
  const [stakeholderDeptFilter, setStakeholderDeptFilter] = useState('ALL');
  const [stakeholderSubTab, setStakeholderSubTab] = useState<'grid' | 'entry_path'>('grid');
  const [isEntryPathInfoOpen, setIsEntryPathInfoOpen] = useState(false);
  const [stakeholderSeniorityFilter, setStakeholderSeniorityFilter] = useState('ALL');
  const [stakeholderInfluenceFilter, setStakeholderInfluenceFilter] = useState('ALL');
  const [stakeholderPriorityFilter, setStakeholderPriorityFilter] = useState('ALL');
  const [stakeholderRelevanceFilter, setStakeholderRelevanceFilter] = useState('ALL');
  const [expandedDepts, setExpandedDepts] = useState<Record<string, boolean>>({});
  const [stakeholderViewMode, setStakeholderViewMode] = useState<'departments' | 'top_contacts'>('departments');
  const [expandedContacts, setExpandedContacts] = useState<Record<string, boolean>>({});
  const [revealedContacts, setRevealedContacts] = useState<Record<string, boolean>>({});

  // Tech Landscape Filter & Sub-Tab State
  const [techSubTab, setTechSubTab] = useState<'map' | 'raw_matrix' | 'webstack' | 'detections'>('map');
  const [opportunitiesOnly, setOpportunitiesOnly] = useState(false);
  const [techSearch, setTechSearch] = useState('');
  const [techCategoryFilter, setTechCategoryFilter] = useState('ALL');

  // Content Studio State
  const [selectedPersona, setSelectedPersona] = useState<string>('cio_it');
  const [selectedContentType, setSelectedContentType] = useState<string>('email');
  const [selectedTopic, setSelectedTopic] = useState<string>('Z by HP Workstations');
  const [customTopic, setCustomTopic] = useState<string>('');
  const [additionalContext, setAdditionalContext] = useState<string>('');
  const [isGeneratingContent, setIsGeneratingContent] = useState<boolean>(false);
  const [hasGeneratedContent, setHasGeneratedContent] = useState<boolean>(false);
  const [generatedAsset, setGeneratedAsset] = useState<any>(null);
  // Co-creation step: the brief produces angles, the seller picks or edits one,
  // and only then is the asset written. `selectedAngle` carries the chosen text
  // (editable, so "selects OR ADJUSTS" is satisfied) into the generate call.
  const [angleOptions, setAngleOptions] = useState<any[]>([]);
  const [isSuggestingAngles, setIsSuggestingAngles] = useState<boolean>(false);
  const [selectedAngleId, setSelectedAngleId] = useState<string | null>(null);
  const [selectedAngle, setSelectedAngle] = useState<string>('');
  const [angleNotice, setAngleNotice] = useState<string | null>(null);
  // Which LinkedIn variant is on screen (1-based, matching variant_index).
  const [activeVariantIndex, setActiveVariantIndex] = useState<number>(1);
  const [generateError, setGenerateError] = useState<any>(null);
  const [copiedAssetId, setCopiedAssetId] = useState<string | null>(null);
  const [isGeneratingOppMap, setIsGeneratingOppMap] = useState<boolean>(false);
  const [expandedCalc, setExpandedCalc] = useState<Record<string, boolean>>({});

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
  const [chatMessages, setChatMessages] = useState<Array<{ id: string; sender: 'user' | 'assistant'; text: string; timestamp: string; citations?: any[]; available?: boolean; personaTitle?: string }>>([]);
  const [chatPending, setChatPending] = useState(false);
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
      if (response.data.length > 0) {
        setSelectedAccountId(response.data[0].id);
        setSelectedAccount(response.data[0]);
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load accessible account list.';
      setError(msg);
    } finally {
      setIsLoadingAccounts(false);
    }
  }, []);

  // Fetch Widget Contracts for Selected Account + Feature
  const fetchWidgetContracts = useCallback(async (accId: string, featureKey: string) => {
    if (!accId) return;
    setIsLoadingLoadingWidgets(true);
    try {
      const response = await api.get<WidgetResponse[]>(`/accounts/${accId}/widgets/${featureKey}`);
      setWidgets(response.data);
    } catch (err: any) {
      // Non-blocking
    } finally {
      setIsLoadingLoadingWidgets(false);
    }
  }, []);

  useEffect(() => {
    fetchUserAccounts();
  }, [fetchUserAccounts]);

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
  useEffect(() => {
    if (!selectedAccountId || activeFeatureKey !== 'strategy_chat') return;
    let cancelled = false;
    api.get(`/accounts/${selectedAccountId}/widgets/strategy_chat/personas`)
      .then(res => { if (!cancelled) setChatPersonas(res.data?.personas || []); })
      .catch(() => { if (!cancelled) setChatPersonas([]); });
    return () => { cancelled = true; };
  }, [selectedAccountId, activeFeatureKey]);

  const handleSelectAccount = (acc: CompanyAccount) => {
    setSelectedAccountId(acc.id);
    setSelectedAccount(acc);
    setIsDropdownOpen(false);
  };

  const getDownloadUrl = (datasetKey: string) => {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    const token = typeof window !== 'undefined' ? (localStorage.getItem('hp_token') || '') : '';
    return `${baseUrl}/api/v1/accounts/${selectedAccount?.id}/data/download/${datasetKey}?token=${encodeURIComponent(token)}`;
  };

  const allItems = NORTHSTAR_SIDEBAR_GROUPS.flatMap(g => g.items);
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
      { field_path: 'open_job_count', source: 'job_openings.csv (All postings seen, open and closed)', type: 'Job Openings', date: '2026-09-04', confidence: '85%', url: 'data/accounts/' + selectedAccount.id + '/job_openings/job_openings.csv' },
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
      <div className="flex h-screen bg-[#F8FAFC] overflow-hidden text-slate-800 font-sans">
        
        {/* ============================================================================== */}
        {/* LEFT FIXED SIDEBAR — NORTHSTAR EXACT LAYOUT                                    */}
        {/* ============================================================================== */}
        <aside 
          className={`bg-[#0B132B] text-white flex flex-col justify-between transition-all duration-300 z-50 flex-shrink-0 border-r border-slate-800/80 ${
            isSidebarCollapsed ? 'w-16' : 'w-64'
          }`}
        >
          <div className="flex flex-col h-full overflow-hidden">
            
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
                <span className="text-[9px] font-extrabold text-gray-400 uppercase tracking-widest block mb-1.5 px-1">
                  Target Account
                </span>

                <div className="relative">
                  <button
                    type="button"
                    disabled={isLoadingAccounts || accounts.length === 0}
                    onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                    className="w-full flex items-center justify-between p-2.5 bg-[#1C2541] hover:bg-slate-800 text-white rounded-xl border border-slate-700/80 transition text-left text-xs font-bold disabled:opacity-50 shadow-inner"
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
                    <div className="absolute left-0 mt-2 w-full bg-[#1C2541] border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
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
              {NORTHSTAR_SIDEBAR_GROUPS.map((group) => (
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
                * blocked by one unavailable driver still reports N/A honestly.
                */}
              {(() => {
                const urgencyWidget = widgets.find(w => w.widget_key === 'exec_urgency_score');
                const urgency = (urgencyWidget && urgencyWidget.data
                  && (urgencyWidget.status === 'available' || urgencyWidget.status === 'partial'))
                  ? (urgencyWidget.data as any) : null;

                if (!urgency) return null;

                // The score always computes now: a missing input costs its own
                // component 0 and nothing blocks the composite. The null branch
                // is kept for a payload written before that rule changed.
                const hasScore = urgency.score != null;
                const missing: string[] = urgency.missing_inputs ?? [];
                return (
                  <div
                    className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-full border text-xs font-bold ${
                      hasScore
                        ? 'bg-amber-50 text-amber-800 border-amber-200/80'
                        : 'bg-slate-50 text-slate-600 border-slate-200'
                    }`}
                    title={
                      hasScore
                        ? (missing.length
                            ? `Scored 0 for want of data: ${missing.join('; ')}`
                            : undefined)
                        : (urgency.unavailable_reason || undefined)
                    }
                  >
                    <span className="text-[11px]">Urgency Score</span>
                    <span className={`px-1.5 py-0.5 rounded font-mono text-[10px] ${
                      hasScore ? 'bg-amber-200 text-amber-900' : 'bg-slate-200 text-slate-700'
                    }`}>
                      {hasScore ? `${urgency.score}/${urgency.max_score ?? 100}` : 'N/A'}
                    </span>
                  </div>
                );
              })()}
            </div>

            {/* X-Ray Mode Toggle Button */}
            <div className="flex items-center space-x-3">
              <button
                type="button"
                onClick={() => setIsXRayOn(!isXRayOn)}
                className={`inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs ${
                  isXRayOn
                    ? 'bg-hp-navy text-white border-hp-navy shadow-sm'
                    : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
                }`}
              >
                <Maximize2 className="w-3.5 h-3.5" />
                <span>X-Ray: {isXRayOn ? 'ON' : 'OFF'}</span>
              </button>
            </div>
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
              <div className="space-y-6">
                
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
                          <option value="Bombora">Bombora (Intent)</option>
                          <option value="Google News">Google News RSS</option>
                          <option value="Job Openings">Job Openings (Source B)</option>
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
                  const hiringWidget = widgets.find(w => w.widget_key === 'exec_hiring_velocity');
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

                  // Quick Stats. All three come from exec_summary_card, which
                  // resolves them server-side - `widgets` here holds only the
                  // ACTIVE feature's widgets, so reading another feature's
                  // widget from this component returns nothing. Each is null
                  // when the owning feature has not run, and the card shows a
                  // dash. Previously "Solution Narratives" was the literal 5
                  // with no data binding at all (the account has 4), and
                  // "Active Urgent Signals" was wired to open_job_count - 100
                  // job postings shown as 100 urgent signals, against 8 real
                  // ones. A number with no source behind it is worse than a
                  // blank: it looks checked.
                  const narrativeCount = summaryData?.solution_narratives_count ?? null;
                  const stakeholderCount = summaryData?.stakeholders_mapped_count ?? null;
                  const signalCount = summaryData?.recent_signals_count ?? null;

                  // Figures the company actually filed, as opposed to the
                  // firmographic bands beside them. Each carries its own period,
                  // unit and page, so the card can say where it came from.
                  const reportedMetrics: any[] = (metricsData?.reported_metrics || prioritiesData?.reported_metrics || []) as any[];
                  const priorityList: any[] = (prioritiesData?.priorities || []) as any[];

                  const displayName = summaryData?.company_name || selectedAccount.name;
                  const displayDesc = summaryData?.business_description || `${selectedAccount.name} is an active target company account in the HP Account Intelligence platform. Upload firmographics.csv to view extracted company profile.`;
                  const domainVal = summaryData?.domain || null;
                  const locationVal = summaryData?.hq_location || null;
                  const industryVal = summaryData?.industry_classification || null;
                  const parentVal = summaryData?.ultimate_parent || null;

                  // Set when the backend suppressed a field rather than
                  // displaying a value it could not stand behind. Shown as an
                  // explicit "needs review" chip: a field that silently
                  // vanishes looks like missing data, when in fact a
                  // contradiction was detected and deliberately not resolved.
                  const parentFlag = ((summaryData?.review_flags || []) as any[])
                    .find((f: any) => f?.field === 'ultimate_parent') || null;

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
                              <span className="text-xs font-bold text-slate-500 bg-slate-100 px-2.5 py-0.5 rounded border border-slate-200 uppercase">
                                ACTIVE TARGET
                              </span>
                            </div>

                            {/* Single Clean Description Render */}
                            <p className="text-xs text-slate-600 leading-relaxed max-w-5xl">
                              {displayDesc}
                            </p>

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
                                <div className="flex items-center space-x-1.5 text-slate-700">
                                  <Building2 className="w-4 h-4 text-hp-navy" />
                                  <span className="truncate max-w-md">{industryVal}</span>
                                </div>
                              )}

                              {parentVal && (
                                <div className="flex items-center space-x-1.5 text-slate-700">
                                  <User className="w-4 h-4 text-hp-navy" />
                                  <span>Ultimate Parent: <strong className="font-bold text-slate-900">{parentVal}</strong></span>
                                </div>
                              )}

                              {!parentVal && parentFlag && (
                                <div
                                  className="flex items-center space-x-1.5 text-amber-800"
                                  title={parentFlag.reason || undefined}
                                >
                                  <User className="w-4 h-4 text-amber-600" />
                                  <span>
                                    Ultimate Parent:{' '}
                                    <strong className="font-bold text-amber-900">Unavailable</strong>
                                    <span className="ml-1.5 text-[10px] font-bold bg-amber-100 text-amber-900 px-1.5 py-0.5 rounded border border-amber-200 uppercase">
                                      Needs Review
                                    </span>
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Section 2: Executive Briefing Video Card */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex items-center space-x-6">
                        <div className="relative w-48 h-28 bg-slate-900 rounded-xl overflow-hidden flex items-center justify-center flex-shrink-0 shadow-md">
                          <div className="w-10 h-10 rounded-full bg-hp-navy text-white flex items-center justify-center shadow-lg">
                            <Play className="w-5 h-5 ml-0.5" />
                          </div>
                        </div>

                        <div className="space-y-1">
                          <span className="text-[10px] font-extrabold text-hp-blue uppercase tracking-wider block">
                            WATCH THE EXECUTIVE BRIEFING
                          </span>
                          <h3 className="text-base font-extrabold text-slate-900">
                            HP's Play for {displayName}
                          </h3>
                          <p className="text-xs text-slate-500 leading-relaxed">
                            A personal executive briefing covering the strategic rationale, key triggers, and recommended engagement approach for this account.
                          </p>
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
                            {reportedMetrics.length > 0 && `${reportedMetrics.length} from filings · `}2 firmographic bands
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">

                          {/* The firmographic bands. Kept first and labelled as
                              bands so the contrast with the filed figures is
                              immediate rather than buried in a tooltip. */}
                          <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                            <span className="text-[11px] text-slate-500 block">Total Employees</span>
                            <span className="text-lg font-semibold text-slate-900 leading-tight">
                              {metricsData ? metricsData.employee_count : 'N/A'}
                            </span>
                            <span className="text-[10px] text-slate-400">Band · Firmographics</span>
                          </div>

                          <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                            <span className="text-[11px] text-slate-500 block">Yearly Revenue Range</span>
                            <span className="text-lg font-semibold text-slate-900 leading-tight">
                              {metricsData ? metricsData.revenue : 'N/A'}
                            </span>
                            <span className="text-[10px] text-slate-400">Band · Firmographics</span>
                          </div>

                          {/* Open job postings - a count, not a band. */}
                          {hiringData?.open_job_count && (
                            <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
                              <span className="text-[11px] text-slate-500 block">Active Open Job Postings</span>
                              <span className="text-lg font-semibold text-slate-900 leading-tight">
                                {hiringData.open_job_count}
                              </span>
                              <span className="text-[10px] text-slate-400">Count · Job postings</span>
                            </div>
                          )}

                          {/* Every figure the account actually filed. */}
                          {reportedMetrics.map((m: any, i: number) => (
                            <div key={m.evidence_id || i} className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem]">
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
                                {m.value_text}
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
                                  {m.quote && (
                                    <p className="text-[10px] text-slate-500 mt-2 border-t border-slate-100 pt-2 break-words">
                                      <span className="font-bold text-slate-600">Row as printed: </span>{m.quote}
                                    </p>
                                  )}
                                </div>
                              )}
                            </div>
                          ))}

                          {reportedMetrics.length === 0 && (
                            <div className="bg-white p-4 rounded-2xl border border-dashed border-slate-200 shadow-xs flex flex-col justify-between min-h-[7rem] opacity-80 sm:col-span-2">
                              <span className="text-[11px] text-slate-500 block">Reported financial figures</span>
                              <span className="text-xs text-slate-400 italic leading-snug">
                                No filed figure is available yet
                              </span>
                              <span className="text-[10px] text-slate-400 leading-snug">
                                Upload the account&apos;s annual report or exchange filings under Compliance Filings.
                              </span>
                            </div>
                          )}

                        </div>

                        {reportedMetrics.length > 0 && (
                          <p className="text-[10px] text-slate-400 leading-relaxed">
                            Filed figures are what {displayName} reported, each with its reporting period, unit and page.
                            Band figures are buckets assigned by a data vendor, not reported values.
                            A period-on-period move is shown only where the earlier period was itself reported.
                          </p>
                        )}
                      </div>

                      {/* Section 4: URGENCY SCORE & QUICK STATS (Two-Column Layout) */}
                      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                        
                        {/* Urgency Score Breakdown Card */}
                        <div className="lg:col-span-2 bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                              <Flame className="w-4 h-4 text-amber-500" />
                              <span>URGENCY SCORE & DRIVER BREAKDOWN</span>
                            </h3>
                            <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                              urgencyData?.client_agreed
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                : 'bg-amber-50 text-amber-800 border-amber-200'
                            }`}>
                              {!urgencyData
                                ? 'Not yet computed'
                                : urgencyData.client_agreed
                                  ? 'Client-supplied formula'
                                  : 'Delivery-authored · not client-agreed'}
                            </span>
                          </div>

                          <div className="flex flex-col sm:flex-row items-center gap-6">
                            <div className={`w-24 h-24 rounded-full border-4 flex flex-col items-center justify-center flex-shrink-0 shadow-inner ${
                              urgencyData?.score != null
                                ? 'border-amber-400 bg-amber-50/50'
                                : 'border-slate-300 bg-slate-50'
                            }`}>
                              <span className={`font-extrabold ${
                                urgencyData?.score != null ? 'text-3xl text-slate-800' : 'text-base text-slate-400'
                              }`}>
                                {urgencyData?.score ?? 'N/A'}
                              </span>
                              <span className="text-[10px] font-bold text-slate-400">/100</span>
                            </div>

                            <div className="flex-1 w-full space-y-3 text-xs">
                              {(urgencyData?.drivers ?? []).map((d: any) => {
                                  // Components that scored 0 because nothing
                                  // was on file. Under the client's
                                  // missing-input rule they look identical to
                                  // a genuine 0, so the count is surfaced.
                                  const missing = (d.terms ?? []).filter((t: any) => t.missing_input);
                                  return {
                                  id: d.key,
                                  label: d.label,
                                  available: d.available,
                                  partial: missing.length > 0,
                                  scoreText: `${d.value}/100`,
                                  progressPct: `${d.value}%`,
                                  barColor: missing.length > 0 ? 'bg-amber-400' : 'bg-hp-navy',
                                  // The whole working, so a seller who
                                  // disagrees with the number can see which
                                  // term to disagree with.
                                  rationale: [
                                    `Weight ${Math.round(d.weight * 100)}% of the total.`,
                                    ...(d.terms ?? []).map((t: any) =>
                                      `${t.label}: ${t.points}/${t.max_points} — ${t.basis}${
                                        t.missing_input ? ' (no input on file — scores 0 by the missing-input rule)' : ''}.`),
                                    ...(d.notes ?? []),
                                    ...(d.caveats ?? []).map((c: string) => `⚠ ${c}`),
                                  ].join(' '),
                                };
                                }).map((driver: any) => (
                                <div key={driver.id} className="relative">
                                  <div className="flex justify-between items-center font-bold text-slate-700 text-[11px] mb-1">
                                    <div className="flex items-center space-x-1.5">
                                      <span className={driver.available ? '' : 'text-slate-400'}>{driver.label}</span>

                                      {/* At least one component scored 0 for
                                          want of data rather than for a weak
                                          signal. That changes how the driver's
                                          number should be read, so it belongs
                                          on the face of the card, not only
                                          inside the popover. */}
                                      {driver.partial && (
                                        <span className="text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                                          PARTIAL DATA
                                        </span>
                                      )}

                                      {/* Interactive Info Icon Button */}
                                      <div className="relative inline-block">
                                        <button
                                          type="button"
                                          onMouseEnter={() => setHoveredDriverTooltip(driver.id)}
                                          onMouseLeave={() => setHoveredDriverTooltip(null)}
                                          onClick={() => setActiveDriverPopover(activeDriverPopover === driver.id ? null : driver.id)}
                                          className="text-slate-400 hover:text-slate-700 p-0.5 rounded transition"
                                          title="Why this score"
                                        >
                                          <Info className="w-3.5 h-3.5" />
                                        </button>

                                        {/* Hover Tooltip Badge ("Why this score") */}
                                        {hoveredDriverTooltip === driver.id && activeDriverPopover !== driver.id && (
                                          <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 z-30 px-2 py-1 bg-slate-900 text-white text-[10px] font-bold rounded shadow-md whitespace-nowrap pointer-events-none">
                                            Why this score
                                            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900"></div>
                                          </div>
                                        )}
                                      </div>
                                    </div>

                                    <span className="font-mono text-slate-500 font-bold">{driver.scoreText}</span>
                                  </div>

                                  {/* Progress Bar */}
                                  <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                                    <div className={`${driver.barColor} h-2 rounded-full transition-all duration-500`} style={{ width: driver.progressPct }}></div>
                                  </div>

                                  {/* Popover Card Modal */}
                                  {activeDriverPopover === driver.id && (
                                    <div className="absolute left-0 top-full mt-2 w-80 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs font-medium">
                                      <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                                        <h4 className="font-extrabold text-slate-900 text-xs">{driver.label}</h4>
                                        <button
                                          type="button"
                                          onClick={() => setActiveDriverPopover(null)}
                                          className="text-slate-400 hover:text-slate-600 rounded p-0.5"
                                        >
                                          <X className="w-4 h-4" />
                                        </button>
                                      </div>
                                      <p className="text-slate-600 leading-relaxed text-[11px]">
                                        {driver.rationale}
                                      </p>
                                    </div>
                                  )}
                                </div>
                              ))}

                              {!urgencyData && (
                                <p className="text-[11px] text-slate-400 leading-relaxed">
                                  The urgency score has not been computed for this account yet.
                                </p>
                              )}
                            </div>
                          </div>

                          {/* Which components scored 0 for want of data. The
                              score always computes now - a missing input costs
                              only its own component - so a low number can mean
                              "little evidence" rather than "weak account", and
                              the card has to let a reader tell them apart. */}
                          {urgencyData && urgencyData.missing_inputs?.length > 0 && (
                            <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3 leading-relaxed">
                              <span className="font-semibold">
                                Scored 0 for want of data, not for a weak signal:
                              </span>{' '}
                              {urgencyData.missing_inputs.join('; ')}.
                            </div>
                          )}

                          {/* The arithmetic, shown adding up. The contributions
                              printed here are the same figures the API
                              publishes and they sum to the headline score, so a
                              reader checking the column by hand reaches the
                              number on the dial rather than a near miss. */}
                          {urgencyData && urgencyData.weighted_contributions && (
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

                          {urgencyData && (
                            <p className="text-[10px] text-slate-400 leading-relaxed border-t border-slate-100 pt-3">
                              {/* The authority sentence comes from the payload
                                  rather than being written here: the backend
                                  owns which document the formula is from, and
                                  a copy in the UI would drift from it. */}
                              {urgencyData.formula}{' '}{urgencyData.formula_authority}
                            </p>
                          )}
                        </div>

                        {/* Quick Stats Card */}
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm flex flex-col justify-between space-y-4">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 border-b border-slate-100 pb-3">
                            QUICK STATS
                          </h3>

                          <div className="space-y-3 text-xs font-bold text-slate-800">
                            <div className="flex items-center space-x-3 p-2.5 rounded-xl bg-slate-50">
                              <div className="p-2 bg-blue-100 text-hp-blue rounded-lg">
                                <Lightbulb className="w-4 h-4" />
                              </div>
                              <div>
                                <span className="text-base font-extrabold text-slate-900 block">
                                  {narrativeCount ?? <span className="text-slate-300">&mdash;</span>}
                                </span>
                                <span className="text-[10px] text-slate-500 font-medium">Solution Narratives</span>
                              </div>
                            </div>

                            <div className="flex items-center space-x-3 p-2.5 rounded-xl bg-slate-50">
                              <div className="p-2 bg-purple-100 text-purple-700 rounded-lg">
                                <Users className="w-4 h-4" />
                              </div>
                              <div>
                                 <span className="text-base font-extrabold text-slate-900 block">
                                   {stakeholderCount ?? <span className="text-slate-300">&mdash;</span>}
                                 </span>
                                <span className="text-[10px] text-slate-500 font-medium">Stakeholders Mapped</span>
                              </div>
                            </div>

                            <div className="flex items-center space-x-3 p-2.5 rounded-xl bg-slate-50">
                              <div className="p-2 bg-red-100 text-red-600 rounded-lg">
                                <Flame className="w-4 h-4" />
                              </div>
                              <div>
                                <span className="text-base font-extrabold text-slate-900 block">
                                  {signalCount ?? <span className="text-slate-300">&mdash;</span>}
                                </span>
                                {/* "Urgent" was never computed - nothing ranks
                                    these by urgency - so the label says what
                                    the number actually counts. */}
                                <span className="text-[10px] text-slate-500 font-medium">Recent Signals</span>
                              </div>
                            </div>
                          </div>
                        </div>

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
                          </h3>
                          {priorityList.length > 0 && (
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-hp-navy border border-blue-200 inline-flex items-center gap-1">
                              <FileText className="w-3 h-3" />
                              {priorityList.reduce((n: number, p: any) => n + (p.sources?.length || 0), 0)} primary sources
                            </span>
                          )}
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
                                      const m = p.measures || {};
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
                                              {p.from_news_fallback && (
                                                <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 inline-block" title={p.fallback_note}>
                                                  From recent events
                                                </span>
                                              )}
                                            </div>
                                            {/* The score on the face of the
                                                card, so catalysts can be
                                                compared without opening four
                                                drawers. The working stays in
                                                the drawer. */}
                                            {p.evidence_strength && (
                                              <span
                                                className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-blue-50 text-hp-navy border border-blue-200 flex-shrink-0 whitespace-nowrap cursor-help"
                                                title={p.evidence_strength.formula}
                                              >
                                                {p.evidence_strength.score}/{p.evidence_strength.max_score}
                                              </span>
                                            )}
                                          </div>

                                          {/* The card body is the description -
                                              what the account is doing and what
                                              it implies for HP. The raw source
                                              sentence is evidence, not prose,
                                              and now lives in the drawer where
                                              a reader goes to check a claim. */}
                                          {p.description?.text && (
                                            <p className="text-xs text-slate-600 leading-relaxed">
                                              {p.description.text}
                                            </p>
                                          )}

                                          {p.why_now && (
                                            <p className="text-[11px] text-slate-500 leading-relaxed">
                                              <span className="font-bold text-slate-600">Why now: </span>{p.why_now}
                                            </p>
                                          )}

                                          <p className="text-[10px] text-slate-500">
                                            <span className="font-bold text-slate-600">Evidence: </span>
                                            {m.support_count} source sentence{m.support_count === 1 ? '' : 's'}
                                            {' · '}{m.distinct_sections} document section{m.distinct_sections === 1 ? '' : 's'}
                                            {' · '}{m.independent_source_count} independent source{m.independent_source_count === 1 ? '' : 's'}
                                          </p>

                                          <div className="flex flex-wrap items-center gap-1.5">
                                            {(p.sources || []).slice(0, 4).map((s: any, si: number) => (
                                              s.source_url ? (
                                                <a
                                                  key={si}
                                                  href={s.source_url}
                                                  target="_blank"
                                                  rel="noopener noreferrer"
                                                  title={s.source_text}
                                                  className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-hp-navy border border-blue-200 hover:bg-blue-100 transition max-w-full"
                                                >
                                                  <FileText className="w-3 h-3 flex-shrink-0" />
                                                  <span className="truncate max-w-[11rem]">{s.label}</span>
                                                  <ExternalLink className="w-2.5 h-2.5 flex-shrink-0" />
                                                </a>
                                              ) : (
                                                <span
                                                  key={si}
                                                  title={s.source_text}
                                                  className="inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200 max-w-full"
                                                >
                                                  <FileText className="w-3 h-3 flex-shrink-0" />
                                                  <span className="truncate max-w-[11rem]">{s.label}</span>
                                                </span>
                                              )
                                            ))}
                                          </div>

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
                                              {/* Evidence strength: the score,
                                                  then one bar per term. Three
                                                  terms, three bars - the
                                                  formula has no fourth. Each
                                                  bar fills to its own share of
                                                  100, so their widths add up to
                                                  the score the way the terms
                                                  add up to the total, and the
                                                  basis line under each says
                                                  what it was counted from. */}
                                              <div className="space-y-2">
                                                <div className="flex items-center justify-between">
                                                  <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 inline-flex items-center gap-1">
                                                    <BarChart3 className="w-3 h-3" />
                                                    Evidence strength
                                                  </span>
                                                  <span
                                                    className="text-[11px] font-extrabold text-slate-700 cursor-help"
                                                    title={p.evidence_strength?.formula || prioritiesData?.evidence_strength_formula}
                                                  >
                                                    {p.evidence_strength?.score ?? 0}/{p.evidence_strength?.max_score ?? 100}
                                                  </span>
                                                </div>

                                                <div className="flex items-stretch gap-2">
                                                  {(p.evidence_strength?.terms || []).map((t: any, ti: number) => (
                                                    <div key={ti} className="flex-1 min-w-0 space-y-1" title={t.basis}>
                                                      <div className="h-1.5 rounded-full bg-slate-200 overflow-hidden">
                                                        <div
                                                          className="h-full rounded-full bg-hp-navy transition-all"
                                                          style={{ width: `${t.max_points ? Math.round((t.points / t.max_points) * 100) : 0}%` }}
                                                        />
                                                      </div>
                                                      <div className="flex items-baseline justify-between gap-1">
                                                        <span className="text-[9px] text-slate-500 truncate">{t.label}</span>
                                                        <span className="text-[9px] font-bold text-slate-600 flex-shrink-0">
                                                          {t.points}/{t.max_points}
                                                        </span>
                                                      </div>
                                                    </div>
                                                  ))}
                                                </div>

                                                <div className="space-y-0.5 pt-1">
                                                  {(p.evidence_strength?.terms || []).map((t: any, ti: number) => (
                                                    <p key={ti} className="text-[10px] text-slate-500 leading-relaxed">
                                                      <span className="text-slate-400">{t.label}:</span> {t.basis}
                                                    </p>
                                                  ))}
                                                </div>

                                                {/* Evidence that named no
                                                    category scored nothing for
                                                    diversity. Said plainly,
                                                    because a reader comparing
                                                    two cards needs to know the
                                                    difference between evidence
                                                    that is absent and evidence
                                                    that could not be placed. */}
                                                {(() => {
                                                  const div = (p.evidence_strength?.terms || []).find((t: any) => t.key === 'source_diversity');
                                                  const un = div?.uncategorised_sources || 0;
                                                  return un > 0 ? (
                                                    <p className="text-[10px] text-amber-700 leading-relaxed">
                                                      {un} supporting source{un === 1 ? '' : 's'} carried no category and scored nothing for diversity.
                                                    </p>
                                                  ) : null;
                                                })()}

                                                <p className="text-[10px] text-slate-400 leading-relaxed pt-1 border-t border-slate-200">
                                                  Scored on {p.evidence_strength?.scored_on || prioritiesData?.scored_on}. Age is measured to that date, so the score does not drift as this page ages.
                                                </p>
                                              </div>

                                              {/* ABX's own four measures, kept
                                                  beside the score rather than
                                                  replaced by it. They are what
                                                  the ordering rule uses, and
                                                  they say something the three
                                                  scored terms do not. */}
                                              <div className="space-y-1 pt-1 border-t border-slate-200">
                                                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">
                                                  Supporting counts
                                                </span>
                                                <p className="text-[10px] text-slate-500 leading-relaxed">
                                                  {m.support_count} source sentence{m.support_count === 1 ? '' : 's'}
                                                  {' · '}{m.distinct_sections} document section{m.distinct_sections === 1 ? '' : 's'}
                                                  {' · '}{m.independent_source_count} independent source{m.independent_source_count === 1 ? '' : 's'}
                                                  {m.most_recent_date ? ` · most recent ${m.most_recent_date}` : ''}
                                                </p>
                                              </div>

                                              <div className="space-y-1.5 pt-1 border-t border-slate-200">
                                                <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">
                                                  Supporting claims ({(p.sources || []).length})
                                                </span>
                                                {(p.sources || []).map((s: any, si: number) => (
                                                  <div key={si} className="text-[10px] text-slate-600 leading-relaxed">
                                                    &ldquo;{s.source_text}&rdquo;
                                                    <span className="text-slate-400"> — {s.label}</span>
                                                  </div>
                                                ))}
                                                {p.description?.written_by === 'python' && (
                                                  <p className="text-[10px] text-amber-700 pt-1">
                                                    The generated description was rejected ({p.description.rejected_reason}); a plain summary is shown instead.
                                                  </p>
                                                )}
                                              </div>
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
                          <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-8 text-center space-y-2">
                            <div className="w-10 h-10 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center mx-auto">
                              <Sparkles className="w-5 h-5" />
                            </div>
                            <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                              No evidenced priority yet
                            </h4>
                            <p className="text-[11px] text-slate-500 max-w-md mx-auto leading-relaxed">
                              Strategic priorities for <strong className="text-slate-800">{displayName}</strong> are read from its filed documents and signals. Upload the account&apos;s annual report or exchange filings under Compliance Filings, and they will be generated automatically.
                            </p>
                          </div>
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
                  const dimLabels: Record<string, string> = {
                    recency: 'Recency',
                    hp_relevance: 'HP Relevance',
                    strategic_impact: 'Strategic Impact',
                    actionability: 'Actionability',
                    source_reliability: 'Source Reliability',
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
                    if (!d) return 'Date N/A';
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

                      {!isScored && (
                        <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-800">
                          Relevance scoring has not run for this account, so signals are shown in date order and score filters are inactive. No scores are invented.
                        </div>
                      )}

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
                            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-2">Minimum Score</p>
                            <div className="flex flex-wrap gap-1.5">
                              {[0, 4, 6, 8].map(v => (
                                <button
                                  key={v}
                                  type="button"
                                  disabled={!isScored}
                                  onClick={() => setMinSignalScore(v)}
                                  title={!isScored ? 'Available once relevance scoring has run' : undefined}
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
                                        <>{s.confidence.toFixed(1)}<span className="text-slate-400 font-normal">/10</span></>
                                      ) : (
                                        <span className="text-slate-400 font-normal">unscored</span>
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

                                  {/* Source chip, directly below the implication block */}
                                  <div className="mt-2.5 flex flex-wrap items-center gap-2">
                                    {s.source_url ? (
                                      <a
                                        href={s.source_url}
                                        target="_blank"
                                        rel="noreferrer"
                                        className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-full hover:bg-emerald-100 transition"
                                      >
                                        <FileText className="w-3 h-3" />
                                        <span>{s.source_publisher || 'Source'}</span>
                                        <ExternalLink className="w-3 h-3" />
                                      </a>
                                    ) : (
                                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-500 bg-slate-50 border border-slate-200 px-2 py-0.5 rounded-full">
                                        <FileText className="w-3 h-3" />
                                        <span>Source link not available</span>
                                      </span>
                                    )}
                                    {s.supporting_source_count > 1 && (
                                      <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">
                                        {s.supporting_source_count} supporting sources
                                      </span>
                                    )}
                                  </div>

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
                                      <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider">Score breakdown</p>
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
                                                <div className="h-1.5 bg-hp-navy/60 rounded-full" style={{ width: `${val * 10}%` }}></div>
                                              </div>
                                              <span className="text-[10px] font-mono text-slate-400 w-9 text-right flex-shrink-0">{val}/10</span>
                                            </div>
                                            {sc.rationales?.[dim] && (
                                              <p className="text-[10px] text-slate-400 pl-[8.5rem] leading-relaxed">{sc.rationales[dim]}</p>
                                            )}
                                          </div>
                                        );
                                      })}
                                      <p className="text-[10px] text-slate-500 pt-1 border-t border-slate-200">
                                        Weighted total <span className="font-semibold text-slate-700">{s.confidence?.toFixed(2)}</span> /10 &middot; tier {s.tier}
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
                  const hiringWidget = widgets.find(w => w.widget_key === 'intent_hiring_demand');

                  const topicsData = (topicsWidget && topicsWidget.status === 'available' && topicsWidget.data) ? topicsWidget.data : null;
                  const summaryData = (summaryWidget && summaryWidget.status === 'available' && summaryWidget.data) ? summaryWidget.data : null;
                  const hiringData = (hiringWidget && hiringWidget.status === 'available' && hiringWidget.data) ? hiringWidget.data : null;

                  const topicsList: IntentTopic[] = topicsData?.topics || [];
                  const provider = topicsData?.provider || summaryData?.provider;
                  const accountMatch = topicsData?.account_match || summaryData?.account_match;
                  const observation = topicsData?.observation || summaryData?.observation;
                  const dictionaryVersion: string = topicsData?.dictionary_version || summaryData?.dictionary_version || '';
                  const categoryFile = summaryData?.category_file || summaryWidget?.data?.category_file;
                  const categoryFileMatched = categoryFile?.status === 'matched';
                  const categoryRun: string | null = categoryFile?.source?.run_date || null;
                  const themes: any[] = summaryData?.themes || [];
                  // The spec asks for the HP-category view across all supported categories,
                  // not for one of them to be ranked above the rest. Ordered by the
                  // category file's own score.
                  const hpCategories: any[] = [...(summaryData?.hp_categories || [])].sort(
                    (a: any, b: any) => (b.primary?.score ?? -1) - (a.primary?.score ?? -1)
                  );
                  const otherCats = hpCategories;
                  const chartCats = hpCategories.filter((c: any) => c.primary).sort((a: any, b: any) => (b.primary.score ?? -1) - (a.primary.score ?? -1));
                  const hiringLinked = summaryData?.hiring_linked;
                  const staffingTopics = topicsList.filter(t => t.included && t.hiring_linked);
                  const disclaimer: string = summaryData?.disclaimer || topicsData?.disclaimer || 'Intent indicates research activity, not confirmed purchase intent.';
                  // Source A that is missing or belongs to another domain is stated, never drawn as zero scores.
                  const sourceAMessage: string | null = topicsData ? null : (topicsWidget?.data?.message || 'Intent unavailable: no Bombora intent topics have been extracted for this account.');
                  const otherTheme = themes.find((t: any) => t.theme === 'Other / Unmapped');
                  const includedCount: number = topicsData?.included_topics_count || 0;
                  const unmappedPct = includedCount && otherTheme ? Math.round((otherTheme.topic_count / includedCount) * 100) : 0;

                  const filteredTopics = topicsList.filter((t: any) => {
                    if (intentSearch && !t.topic_name.toLowerCase().includes(intentSearch.toLowerCase().trim())) return false;
                    if (intentScoreFilter === '70+' && (t.composite_score ?? -1) < 70) return false;
                    if (intentScoreFilter === '85+' && (t.composite_score ?? -1) < 85) return false;
                    return true;
                  });
                  const topChartTopics = filteredTopics.filter((t: any) => t.included).slice(0, 10);
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
                    'Other / Unmapped': { chip: 'bg-slate-100 text-slate-700 border-slate-200', bar: 'bg-slate-500', border: 'border-slate-200' }
                  };
                  const INTENSITY_CHIP: Record<string, string> = {
                    'High': 'bg-red-50 text-red-700 border-red-200',
                    'Moderate': 'bg-amber-50 text-amber-800 border-amber-200',
                    'Low': 'bg-slate-50 text-slate-600 border-slate-200'
                  };
                  const categoryLabel = (name: string) => (name === 'Poly/Collaboration' ? 'Poly' : name);
                  const shortDate = (v?: string | null) => (v ? String(v).slice(0, 10) : null);
                  const hasSignal = (stage?: string | null) => !!stage && stage.toLowerCase() !== 'no signal';

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
                        <span className="text-[11px] text-slate-400 block">None reported</span>
                      )}
                      {p.keywords_matched?.length > 0 && (
                        <p className="text-[10px] text-slate-500"><span className="font-bold text-slate-400 uppercase mr-1">Keywords</span>{p.keywords_matched.join(' · ')}</p>
                      )}
                      {p.related_technologies?.length > 0 && (
                        <p className="text-[10px] text-slate-500"><span className="font-bold text-slate-400 uppercase mr-1">Technologies</span>{p.related_technologies.join(' · ')}</p>
                      )}
                      <p className="flex items-center gap-1.5 text-[11px] text-slate-500" title="Geo Source, as supplied by the HP Category Intent file for this category. Bombora topics carry no location.">
                        <Globe className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span className="font-bold text-slate-400 uppercase text-[10px]">Geo</span>
                        {p.geo?.length ? p.geo.join(', ') : 'Not reported for this category'}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {p.first_intent_date ? `Observed ${p.first_intent_date} → ${p.latest_intent_date || p.first_intent_date}` : 'No intent dates reported'}
                      </p>
                      {(p.quality_flags || []).map((q: any) => (
                        <p key={q.term} className="flex items-start gap-1 text-[10px] text-amber-800 font-semibold bg-amber-50 border border-amber-200 rounded-lg p-2">
                          <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                          <span>Noisy keyword &apos;{q.term}&apos; ({q.field}): {q.reason}. Read this category's score with care.</span>
                        </p>
                      ))}
                    </div>
                  );

                  // Steps 2-4: Bombora signals with exact scores, and the technologies that confirm them.
                  const renderSignals = (signals: any[], topicLimit: number) => {
                    if (!signals?.length) return <p className="text-[11px] text-slate-400">No supporting Bombora research.</p>;
                    return (
                      <div className="space-y-2">
                        {signals.map((sg: any) => (
                          <div key={sg.signal} className={`rounded-lg border p-2.5 ${sg.confirmed ? 'border-emerald-200 bg-emerald-50/40' : 'border-slate-200 bg-slate-50/50'}`}>
                            <div className="flex items-center justify-between gap-2">
                              <span className="flex items-center gap-1.5 text-[11px] font-bold text-slate-800">
                                {sg.confirmed ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> : <Minus className="w-3.5 h-3.5 text-slate-300" />}
                                {sg.signal}
                              </span>
                              <span className="font-mono text-xs font-extrabold text-slate-900">{sg.max != null ? `${sg.max}/100` : '—'}</span>
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
                                  {sg.topics.length === 0 && <span className="text-slate-400"> · no Bombora signal to score it</span>}
                                </>
                              ) : (
                                'No matching technology in Explorium sheets 4–5'
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
                          <div className={`${barClass} h-1.5 rounded-full`} style={{ width: `${Math.min(100, Math.max(0, item.composite_score ?? 0))}%` }}></div>
                        </div>
                        <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                        <span className="text-[10px] text-slate-400 font-medium w-12">{provider?.name || 'Bombora'}</span>
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
                          <p className="text-xs text-slate-500 mt-0.5">
                            {categoryFileMatched ? `${summaryData?.categories_with_signal ?? 0} of ${chartCats.length} HP categories with a signal in the category file • ` : ''}
                            {topicsList.length} Bombora intent topics for {selectedAccount?.name}
                          </p>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                          {categoryRun && (
                            <span className="px-3 py-1 bg-slate-100 text-slate-600 border border-slate-200 rounded-full text-[11px]">
                              Category file · run {shortDate(categoryRun)}
                            </span>
                          )}
                          {observation?.as_of && (
                            <span className="px-3 py-1 bg-slate-100 text-slate-600 border border-slate-200 rounded-full text-[11px]">
                              {provider ? `${provider.name} ${provider.product}` : 'Bombora'} · as of {observation.as_of}
                            </span>
                          )}
                          {accountMatch && (
                            <span className={`px-3 py-1 rounded-full text-[11px] border flex items-center gap-1 ${accountMatch.status === 'matched' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-amber-50 text-amber-800 border-amber-200'}`}>
                              {accountMatch.status === 'matched' ? <ShieldCheck className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
                              {accountMatch.status === 'matched' ? `${accountMatch.provider_domain} verified` : accountMatch.status === 'mismatch' ? 'Domain mismatch' : 'Domain not verified'}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Unavailable states: stated, never drawn as zeros */}
                      {sourceAMessage && (
                        <div className="bg-white rounded-2xl p-5 border border-amber-200 shadow-sm flex items-start gap-3">
                          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <h3 className="text-sm font-extrabold text-slate-900">
                              {topicsWidget?.data?.availability === 'no_matched_signal' ? 'No Matched Signal (Source A)' : 'Intent Unavailable (Source A)'}
                            </h3>
                            <p className="text-xs text-slate-600 leading-relaxed">{sourceAMessage}</p>
                          </div>
                        </div>
                      )}
                      {categoryFile && !categoryFileMatched && categoryFile.note && (
                        <div className="bg-white rounded-2xl p-5 border border-amber-200 shadow-sm flex items-start gap-3">
                          <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                          <div className="space-y-1">
                            <h3 className="text-sm font-extrabold text-slate-900">Category file not attached</h3>
                            <p className="text-xs text-slate-600 leading-relaxed">{categoryFile.note}</p>
                          </div>
                        </div>
                      )}

                      {summaryData && (
                        <>
                          {/* So What for HP */}
                          <div className="bg-blue-50/80 border border-blue-200/90 rounded-2xl p-6 text-xs text-blue-950 space-y-3 shadow-xs">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <h3 className="text-xs font-black uppercase tracking-wider text-hp-navy flex flex-wrap items-center gap-2">
                                <Lightbulb className="w-4 h-4 text-hp-navy" />
                                <span>SO WHAT FOR HP</span>
                                {includedCount > 0 && (
                                  <span className="normal-case tracking-normal font-medium text-[11px] text-blue-700/80">
                                    · {includedCount} Bombora topics categorized, {otherTheme?.topic_count ?? 0} ({unmappedPct}%) unmapped and kept out of the theme read below
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
                            <p className="text-[11px] leading-relaxed text-blue-950 font-bold flex items-start gap-2.5 pt-2 border-t border-blue-200/60">
                              <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
                              <span>{disclaimer}</span>
                            </p>
                          </div>

                          {/* Step 1 - HP Category Intent Scores, as received from the category file */}
                          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                              <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                                <Layers className="w-4 h-4 text-hp-navy" />
                                <span>HP CATEGORY INTENT SCORES</span>
                              </h3>
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200">
                                {categoryFileMatched ? `HP Category Intent file · run ${categoryRun}` : 'No category file for this account'}
                              </span>
                            </div>
                            {chartCats.length > 0 ? (
                              <div className="overflow-x-auto">
                                <div className="min-w-[480px] pl-8 pr-2 pt-3">
                                  <div className="relative h-52">
                                    {[0, 25, 50, 75, 100].map(v => (
                                      <div key={v} className={`absolute left-0 right-0 border-t ${v === 0 ? 'border-slate-300' : 'border-dashed border-slate-200'}`} style={{ bottom: `${v}%` }}>
                                        <span className="absolute -left-8 -translate-y-1/2 w-6 text-right text-[10px] font-mono text-slate-400">{v}</span>
                                      </div>
                                    ))}
                                    <div className="absolute inset-0 flex items-end justify-around">
                                      {chartCats.map((c: any) => {
                                        const pct = Math.min(100, Math.max(0, c.primary.score ?? 0));
                                        const noisy = (c.primary.quality_flags || []).length > 0;
                                        return (
                                          <div key={c.category} className="relative flex flex-col items-center justify-end h-full w-20">
                                            <div
                                              className={`w-14 rounded-t-md ${CATEGORY_STYLE[c.category]?.bar || 'bg-slate-400'} ${noisy ? 'opacity-40' : ''}`}
                                              style={{ height: `${pct}%` }}
                                            ></div>
                                            <span className="absolute text-[11px] font-bold text-slate-700" style={{ bottom: `calc(${pct}% + 6px)` }}>{c.primary.score ?? '—'}</span>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  </div>
                                  <div className="flex justify-around pt-2">
                                    {chartCats.map((c: any) => (
                                      <div key={c.category} className="w-20 text-center">
                                        <span className="text-xs block font-semibold text-slate-600">{categoryLabel(c.category)}</span>
                                        {(c.primary.quality_flags || []).length > 0 && <span className="text-[10px] font-semibold text-amber-700 block">Noisy keyword</span>}
                                        {!(c.primary.quality_flags || []).length && !c.primary.has_signal && c.primary.score != null && (
                                          <span className="text-[10px] font-semibold text-slate-400 block">No buying stage</span>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <p className="text-xs text-slate-500">{categoryFile?.note || 'Upload the HP Category Intent file to see category scores.'}</p>
                            )}
                            <p className="text-[11px] text-slate-500">
                              Scores as received from the HP Category Intent file, shown for every HP category, ordered by score. Bars are ordered by score alone: faded bars rest on a noisy keyword and are marked above. Supporting Bombora signals add context and never change these scores.
                              {categoryFile?.top_check && !categoryFile.top_check.consistent && (
                                <span className="text-amber-700 font-semibold"> The file&apos;s stated top category ({categoryFile.top_check.stated_category}) does not match its scores ({categoryFile.top_check.recomputed_category}).</span>
                              )}
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
                                <div key={cat.category} className={`bg-white p-5 rounded-2xl border shadow-xs flex flex-col gap-4 ${noisy ? 'border-amber-200' : 'border-slate-200'}`}>
                                  {/* Header: category chip, the file's own direction, buying stage */}
                                  <div className="flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2.5 min-w-0">
                                      <span className={`px-3 py-0.5 rounded-full text-sm font-extrabold border ${style.chip}`}>{categoryLabel(cat.category)}</span>
                                      {p?.trend_label && (
                                        <span
                                          className="flex items-center gap-1 text-[12px] font-semibold text-slate-400 truncate"
                                          title={p.trend_basis || "The category file states this direction but supplies no prior window to check it against."}
                                        >
                                          <Minus className="w-3.5 h-3.5 text-slate-300 flex-shrink-0" />
                                          {p.trend_label}
                                          <span className="text-[10px] text-slate-300">(unverified)</span>
                                        </span>
                                      )}
                                    </div>
                                    {p && (
                                      <span title="Buying Stage, as supplied by the category file" className={`text-[11px] font-bold px-2.5 py-1 rounded-md border flex-shrink-0 ${hasSignal(p.stage) ? 'bg-blue-50 text-hp-navy border-blue-200' : 'bg-slate-50 text-slate-500 border-slate-200'}`}>
                                        {p.stage || 'No stage'}
                                      </span>
                                    )}
                                  </div>

                                  {/* Score bar */}
                                  {p ? (
                                    <div className="flex items-center gap-3">
                                      <div className="flex-1 bg-slate-100 h-2.5 rounded-full overflow-hidden">
                                        <div className={`${style.bar} h-2.5 rounded-full ${noisy ? 'opacity-40' : ''}`} style={{ width: `${Math.min(100, Math.max(0, p.score ?? 0))}%` }}></div>
                                      </div>
                                      <span className="text-base font-extrabold text-slate-900 flex-shrink-0">{p.score ?? '—'}/100</span>
                                    </div>
                                  ) : (
                                    // No HP Category Intent file for this account. The card still
                                    // carries the Bombora research and the HP play, so it is shown
                                    // rather than collapsed to an empty box.
                                    <p className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5">
                                      No HP Category Intent file for this account, so there is no category score. The Bombora research below still applies.
                                    </p>
                                  )}

                                  {/* Signal topics as pills, then geo */}
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
                                        <p className="text-[11px] text-slate-400">None reported</p>
                                      )}
                                      <p className="flex items-center gap-2 text-[12px] text-slate-600" title="Geo Source, as supplied by the HP Category Intent file for this category. Bombora topics carry no location.">
                                        <Globe className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                        {p.geo?.length ? p.geo.join(',  ') : 'Not reported for this category'}
                                      </p>
                                      {(p.quality_flags || []).map((q: any) => (
                                        <p key={q.term} className="flex items-start gap-1.5 text-[10px] text-amber-800 font-semibold bg-amber-50 border border-amber-200 rounded-lg p-2">
                                          <AlertCircle className="w-3 h-3 flex-shrink-0 mt-0.5" />
                                          <span>Noisy keyword &apos;{q.term}&apos; ({q.field}): {q.reason}. Read this category&apos;s score with care.</span>
                                        </p>
                                      ))}
                                    </div>
                                  )}

                                  {/* Mapped HP play + research volume */}
                                  <div className="flex items-start justify-between gap-2 pt-3.5 border-t border-slate-100">
                                    <div className="flex items-start gap-2 min-w-0">
                                      <Target className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
                                      <div className="min-w-0">
                                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">Mapped HP Play</span>
                                        <span className="text-sm font-bold text-slate-900 leading-tight block">{cat.hp_play || 'No HP play mapped'}</span>
                                      </div>
                                    </div>
                                    {p?.research_volume && (
                                      <span title="Research Volume, as supplied by the category file" className="text-[11px] font-bold px-2.5 py-1 rounded-md border bg-slate-50 text-slate-600 border-slate-200 flex-shrink-0">
                                        {p.research_volume}
                                      </span>
                                    )}
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
                                      Supporting Intent Signals (Bombora)
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

                      {/* Broader intent topics (Source A raw view) */}
                      {topicsData && (
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
                          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                            <div>
                              <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                                <Database className="w-4 h-4 text-hp-navy" />
                                <span>BROADER INTENT TOPICS ({topicsList.length})</span>
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                As received from {provider ? `${provider.name} ${provider.product} (${provider.source})` : 'Bombora'} · {provider?.scoring_definition}
                              </p>
                            </div>

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
                            </div>
                          </div>

                          {/* Provenance for every row below */}
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 text-[11px] bg-slate-50/60 p-4 rounded-xl border border-slate-200/80">
                            {[
                              { label: 'Provider', value: provider ? `${provider.name} ${provider.product} (${provider.source})` : 'Not supplied' },
                              { label: 'Account / domain match', value: accountMatch?.status === 'matched' ? `${accountMatch.provider_domain} = account domain` : (accountMatch?.note || 'Not verified') },
                              { label: 'Observation date', value: observation?.as_of ? `${observation.as_of} (Date Stamp ${observation.date_stamp})` : (observation?.note || 'Not supplied'), title: observation?.note },
                              { label: 'Level of intent', value: topicsData.level_of_intent || 'Not supplied' },
                              { label: 'Refreshed', value: shortDate(observation?.refreshed_at) || 'Not recorded' },
                              { label: 'Mapping rules', value: dictionaryVersion || 'Not recorded' }
                            ].map((f) => (
                              <div key={f.label} className="space-y-0.5 min-w-0" title={f.title || ''}>
                                <span className="text-slate-400 font-bold uppercase text-[10px] block">{f.label}</span>
                                <span className="font-semibold text-slate-800 block break-words">{f.value}</span>
                              </div>
                            ))}
                          </div>

                          {topChartTopics.length > 0 && (
                            <div className="space-y-3 bg-slate-50/60 p-5 rounded-2xl border border-slate-200/80">
                              <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wider">
                                Top Signal Topics (Ranked by Composite Score)
                              </span>
                              <div className="space-y-2 pt-2">
                                {topChartTopics.map((item: any) => (
                                  <div key={item.topic_name} className="flex items-center space-x-3 text-xs relative group">
                                    <span className="w-64 text-right truncate font-bold text-slate-800 text-[11px] flex-shrink-0">{item.topic_name}</span>
                                    <div
                                      className="flex-1 bg-slate-200 h-5 rounded-md overflow-hidden relative cursor-pointer"
                                      onMouseEnter={() => setHoveredBarTopic({ name: item.topic_name, score: item.composite_score })}
                                      onMouseLeave={() => setHoveredBarTopic(null)}
                                    >
                                      <div
                                        className={`${THEME_STYLE[item.theme]?.bar || 'bg-hp-navy'} h-full rounded-md transition-all duration-300`}
                                        style={{ width: `${Math.min(100, Math.max(0, item.composite_score))}%` }}
                                      ></div>
                                    </div>
                                    {hoveredBarTopic?.name === item.topic_name && (
                                      <div className="absolute right-12 bottom-full mb-1 bg-white border border-slate-300 rounded-xl p-3 shadow-2xl z-50 text-xs font-medium w-64 animate-fade-in pointer-events-none">
                                        <span className="font-extrabold text-slate-900 block truncate">{item.topic_name}</span>
                                        <span className="text-[11px] text-hp-navy font-bold block mt-0.5">
                                          Composite score: {item.composite_score}/100 — {provider?.name || 'Bombora'}
                                        </span>
                                        <span className="text-[10px] text-slate-500 block mt-0.5">
                                          {item.theme}{item.hp_category ? ` · ${categoryLabel(item.hp_category)}` : ''}
                                        </span>
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                              <div className="flex justify-between text-[10px] font-mono text-slate-400 pl-64 pt-2 border-t border-slate-200">
                                <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                              </div>
                            </div>
                          )}

                          {/* Topics grouped by dictionary theme. Group numbers come from the backend summary, so a filter never changes them. */}
                          <div className="space-y-4 pt-2">
                            {themes.filter((t: any) => t.theme !== 'Other / Unmapped' && t.topic_count > 0).map((theme: any) => {
                              const style = THEME_STYLE[theme.theme] || THEME_STYLE['Other / Unmapped'];
                              const shown = filteredTopics.filter((x: any) => x.included && x.theme === theme.theme);
                              return (
                                <div key={theme.theme} className={`bg-white rounded-2xl p-5 border ${style.border} shadow-xs space-y-3`}>
                                  <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className={`px-2.5 py-0.5 rounded-full text-xs font-extrabold border ${style.chip}`}>{theme.theme}</span>
                                      <span className="text-xs font-semibold text-slate-500">
                                        {theme.topic_count} topics • max {theme.max} • avg {theme.average}
                                        {shown.length !== theme.topic_count ? ` • showing ${shown.length}` : ''}
                                      </span>
                                    </div>
                                  </div>
                                  <div className="space-y-2">
                                    {shown.map((item: any, idx: number) => renderTopicRow(item, idx, style.bar))}
                                  </div>
                                </div>
                              );
                            })}

                            {otherTheme && otherTheme.topic_count > 0 && (() => {
                              const shown = filteredTopics.filter((x: any) => x.included && x.theme === 'Other / Unmapped');
                              const flaggedShown = shown.filter((x: any) => x.mapping_status === 'flagged');
                              const rest = shown.filter((x: any) => x.mapping_status !== 'flagged');
                              return (
                                <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-3">
                                  <div className="flex items-center justify-between border-b border-slate-100 pb-2.5 gap-2">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-slate-100 text-slate-700 border border-slate-200">Other / Unmapped</span>
                                      <span className="text-xs font-semibold text-slate-500">
                                        {otherTheme.topic_count} topics not matched by {dictionaryVersion} • {otherTheme.flagged_count} flagged for review
                                      </span>
                                    </div>
                                    <button
                                      type="button"
                                      onClick={() => setIsOtherTopicsExpanded(!isOtherTopicsExpanded)}
                                      className="text-xs font-bold text-hp-navy hover:underline flex items-center gap-1 flex-shrink-0"
                                    >
                                      <span>{isOtherTopicsExpanded ? 'Collapse' : `Expand (${rest.length})`}</span>
                                      <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOtherTopicsExpanded ? 'rotate-180' : ''}`} />
                                    </button>
                                  </div>
                                  {flaggedShown.length > 0 && (
                                    <div className="space-y-2 bg-amber-50/60 border border-amber-200 rounded-xl p-3">
                                      <span className="text-[10px] font-bold uppercase tracking-wider text-amber-800 block">Flagged for review · near-misses the dictionary does not map</span>
                                      {flaggedShown.map((item: any) => (
                                        <div key={item.topic_name} className="flex items-start justify-between gap-3 text-xs">
                                          <div className="min-w-0">
                                            <span className="font-semibold text-slate-800 capitalize block truncate">{item.topic_name}</span>
                                            <span className="text-[10px] text-amber-800 block">{item.flag_reason}</span>
                                          </div>
                                          <span className="font-mono font-bold text-slate-900 flex-shrink-0">{item.composite_score}</span>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                  <div className="space-y-2">
                                    {(isOtherTopicsExpanded ? rest : rest.slice(0, 5)).map((item: any, idx: number) => renderTopicRow(item, idx, 'bg-slate-500'))}
                                  </div>
                                </div>
                              );
                            })()}

                            {(excludedTopics.length > 0 || duplicatesRemoved.length > 0) && (
                              <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 text-[11px] text-slate-600 space-y-1">
                                <span className="text-slate-500 font-bold uppercase text-[10px] block">Not in any summary</span>
                                {excludedTopics.map((t: any) => (
                                  <div key={`x-${t.topic_name}`}><span className="font-semibold capitalize">{t.topic_name}</span>: {t.exclusion_reason}</div>
                                ))}
                                {duplicatesRemoved.map((d: any, i: number) => (
                                  <div key={`d-${i}`}><span className="font-semibold capitalize">{d.topic_name}</span>: duplicate row (score {d.composite_score ?? 'n/a'}) removed; kept score {d.kept_score ?? 'n/a'}</div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Hiring-linked demand (Source B) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Users className="w-4 h-4 text-hp-navy" />
                            <span>HIRING-LINKED INTENT DEMAND</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-hp-navy border border-blue-200">
                            Source B job_openings + Source A staffing topics
                          </span>
                        </div>
                        {hiringData ? (
                          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-medium">
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-1">
                              <span className="text-slate-400 font-bold uppercase text-[10px] block">Postings Seen</span>
                              <span className="text-2xl font-extrabold text-slate-900 block">{hiringData.postings_seen ?? hiringData.open_job_count}</span>
                              <span className="text-[11px] text-slate-500">
                                Every posting in job_openings, open and closed
                                {hiringData.first_seen ? ` · first seen ${hiringData.first_seen}, last seen ${hiringData.last_seen}` : ''}
                              </span>
                            </div>
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-1">
                              <span className="text-slate-400 font-bold uppercase text-[10px] block">Open Postings</span>
                              <span className="text-2xl font-extrabold text-hp-navy block">{hiringData.open_postings ?? '—'}</span>
                              <span className="text-[11px] text-slate-500">
                                No closing status recorded
                                {hiringData.status_breakdown?.closed ? ` · ${hiringData.status_breakdown.closed} marked closed` : ''}
                              </span>
                            </div>
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                              <span className="text-slate-400 font-bold uppercase text-[10px] block">Seniority Mix (all postings seen)</span>
                              <div className="flex flex-wrap gap-2">
                                {Object.entries(hiringData.seniority_breakdown || {}).map(([k, v]) => (
                                  <span key={k} className="px-2.5 py-1 bg-white rounded-lg border border-slate-200 font-bold text-slate-800 text-[11px]">
                                    <span className="capitalize">{k.replace(/_/g, ' ')}</span>: <strong className="text-hp-navy">{String(v)}</strong>
                                  </span>
                                ))}
                              </div>
                            </div>
                          </div>
                        ) : (
                          <p className="text-xs text-slate-500">No job openings dataset on file for this account.</p>
                        )}
                        {staffingTopics.length > 0 && (
                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2 text-xs">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <span className="text-slate-400 font-bold uppercase text-[10px]">Staffing research (Source A · Bombora)</span>
                              <span className="text-[11px] text-slate-500 font-semibold">
                                {hiringLinked?.topic_count ?? staffingTopics.length} topics · max {hiringLinked?.max} · avg {hiringLinked?.average}
                              </span>
                            </div>
                            <div className="flex flex-wrap gap-1.5">
                              {staffingTopics.map(t => (
                                <span key={t.topic_name} className="px-2 py-0.5 rounded bg-white border border-slate-200 text-[11px] text-slate-700 font-medium capitalize">
                                  {t.topic_name} <strong className="text-hp-navy">{t.composite_score}</strong>
                                </span>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>

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
                          {/* Stated once here rather than repeated on every card. */}
                          <p className="text-[11px] text-slate-400 mt-1 max-w-3xl leading-relaxed">
                            HP proof points and case studies are not shown: no HP proof-point source is
                            connected to this system. The HP links on each play are product reference
                            pages, not evidence about this account.
                          </p>
                        </div>

                        <div className="flex items-center space-x-2 text-xs font-bold">
                          <span className="px-3 py-1 bg-white border border-slate-200 shadow-xs rounded-full text-slate-700">
                            {isAvailable ? generatedPlays.length : 0} HP Plays
                          </span>
                          {/* Nothing is badged while it is working. The
                              "Inferred TBD" state still shows, because that
                              tells a seller the plays are not ready yet. */}
                          {!isAvailable && (
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
                              const pKey = play.play_key || `play_${pIdx}`;
                              const isCalcExpanded = expandedCalc[pKey] || false;

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
                                    play.checks_met === 3 ? 'border-l-emerald-500'
                                      : play.checks_met === 2 ? 'border-l-amber-400'
                                      : 'border-l-slate-300'
                                  }`}>

                                    {/* Header: title left, evidence-checks pill right */}
                                    <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-2">
                                      <div className="flex items-center space-x-2 min-w-0">
                                        <Compass className="w-4 h-4 text-slate-400 flex-shrink-0" />
                                        <h4 className="text-base font-bold text-slate-900">{play.title || 'HP Opportunity Play'}</h4>
                                        <Info className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                      </div>

                                      <div className="flex flex-col items-start sm:items-end gap-0.5 flex-shrink-0">
                                        <span className={`text-[11px] font-semibold px-2 py-0.5 rounded border ${
                                          play.checks_met === 3 ? 'text-emerald-700 bg-emerald-50 border-emerald-200'
                                            : play.checks_met === 2 ? 'text-amber-700 bg-amber-50 border-amber-200'
                                            : 'text-slate-600 bg-slate-100 border-slate-200'
                                        }`}>
                                          {play.severity || `${play.checks_met ?? 0} of 3 checks`}
                                        </span>
                                        {play.missing_checks?.length > 0 && (
                                          <span className="text-[10px] text-amber-700">
                                            missing: {play.missing_checks.map((m: string) => m.replace(/_/g, ' ')).join(', ')}
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

                                      {play.hp_resource_url && (
                                        <div className="space-y-1">
                                          <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">
                                            HP RESOURCE
                                            <span className="normal-case font-normal text-slate-400"> &middot; HP product page</span>
                                          </span>
                                          <div className="flex flex-wrap items-center gap-2">
                                            <a
                                              href={play.hp_resource_url}
                                              target="_blank"
                                              rel="noreferrer"
                                              className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold text-[11px] hover:bg-emerald-100 transition"
                                            >
                                              <Globe className="w-3 h-3 text-emerald-600" />
                                              <span>HP &#8599;</span>
                                            </a>
                                            {/* An HP proof point, when one can ever be sourced. No HP
                                                proof corpus is connected, so this stays empty and the
                                                reason is stated once in the section header instead of
                                                repeated on every card. */}
                                            {play.hp_proof_point && (
                                              <span className="text-[11px] text-slate-600">{play.hp_proof_point}</span>
                                            )}
                                          </div>
                                        </div>
                                      )}
                                    </div>

                                    <div className="border-t border-slate-100"></div>

                                    {/* QUANTIFIED IMPACT - composed in Python from named
                                        source fields. No source field, no box. */}
                                    {(play.scale_statement || (play.quantified_impact && play.quantified_impact_state !== 'none')) && (
                                      <div className="bg-indigo-50/70 border border-indigo-100 rounded-lg p-3.5 space-y-1.5">
                                        <div className="flex flex-wrap items-center justify-between gap-2">
                                          <div className="flex items-center gap-1.5 text-indigo-600 font-semibold text-[10px] uppercase tracking-wider">
                                            <Target className="w-3.5 h-3.5 text-indigo-500" />
                                            {/* Only two states exist: 'sourced_signal' and
                                                'none'. There is no HP-modelled state - no
                                                projection formula is defined, and inventing
                                                one would be an unsourced number. */}
                                            <span>Quantified impact - derived from account data</span>
                                          </div>
                                          <span className="text-[9px] font-medium text-indigo-700 bg-indigo-100/80 px-1.5 py-0.5 rounded">
                                            Composed from named source fields - not an HP projection
                                          </span>
                                        </div>

                                        {play.scale_statement && (
                                          <p className="text-sm font-semibold text-slate-900 leading-snug">
                                            {play.scale_statement}
                                          </p>
                                        )}

                                        {play.quantified_impact && play.quantified_impact_state !== 'none' && (
                                          <p className="text-xs text-indigo-900">
                                            <span className="font-semibold">{play.quantified_impact}</span>
                                            {play.quantified_impact_source && (
                                              <span className="text-indigo-700/70"> &middot; {play.quantified_impact_source}</span>
                                            )}
                                          </p>
                                        )}

                                        {play.calculation_basis && (
                                          <div className="pt-0.5">
                                            <button
                                              type="button"
                                              onClick={() => setExpandedCalc(prev => ({ ...prev, [pKey]: !prev[pKey] }))}
                                              className="text-[10px] font-semibold text-indigo-600 hover:underline flex items-center gap-1"
                                            >
                                              {isCalcExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                              <span>How this was derived</span>
                                            </button>
                                            {isCalcExpanded && (
                                              <p className="text-xs text-slate-600 font-normal leading-relaxed bg-white p-2.5 rounded-md border border-indigo-100 mt-1.5">
                                                {play.calculation_basis}
                                              </p>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    )}

                                    {/* SUPPORTING SIGNAL - SOURCED. Every item quotes a cell of this
                                        account's own uploaded data, with the column it came from. */}
                                    {(play.account_evidence?.length > 0 || play.proof_point) && (
                                      <div className="bg-emerald-50/60 border border-emerald-200 rounded-lg p-3.5 space-y-2.5">
                                        <div className="flex items-center gap-1.5 text-emerald-700 font-semibold text-[10px] uppercase tracking-wider">
                                          <CheckCircle2 className="w-3.5 h-3.5" />
                                          <span>Supporting signal - sourced</span>
                                        </div>

                                        {play.account_evidence?.map((ev: any, i: number) => (
                                          <div key={i} className="space-y-1">
                                            <div className="flex flex-wrap items-center gap-1.5">
                                              <span className="inline-flex items-center gap-1 text-[10px] font-semibold text-emerald-800 bg-white border border-emerald-200 px-1.5 py-0.5 rounded">
                                                <FileText className="w-3 h-3" />
                                                {ev.dataset} &rarr; {ev.field}
                                              </span>
                                              {ev.kind && (
                                                <span className="text-[10px] text-emerald-700/70">{ev.kind}</span>
                                              )}
                                            </div>
                                            <p className="text-[11px] text-emerald-900/90 font-mono leading-relaxed break-words">
                                              &ldquo;{ev.quote}&rdquo;
                                            </p>
                                            {ev.statement && (
                                              <p className="text-xs text-emerald-800 italic leading-relaxed">{ev.statement}</p>
                                            )}
                                          </div>
                                        ))}

                                        {play.proof_point && (
                                          <p className="text-xs text-emerald-800 italic leading-relaxed">
                                            &quot;{play.proof_point}&quot;
                                          </p>
                                        )}
                                      </div>
                                    )}

                                    <div className="border-t border-slate-100"></div>

                                    {/* ENTRY PATH */}
                                    <div className="space-y-2.5">
                                      <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block">
                                        ENTRY PATH
                                      </span>

                                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                                        <div className="flex items-start gap-2">
                                          <Clock className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                                          <div>
                                            <span className="text-[10px] text-slate-400 font-semibold uppercase block">TIMELINE</span>
                                            <span className="font-semibold text-slate-800">{play.entry_path?.timeline || '0-90 days'}</span>
                                          </div>
                                        </div>

                                        <div className="flex items-start gap-2">
                                          <Users className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 mt-0.5" />
                                          <div className="min-w-0">
                                            <span className="text-[10px] text-slate-400 font-semibold uppercase block">TARGET BUYERS</span>
                                            {play.entry_path?.target_contacts?.length > 0 ? (
                                              <div className="space-y-0.5">
                                                {play.entry_path.target_contacts.map((c: any) => (
                                                  <div key={c.contact_id}>
                                                    <span className="font-semibold text-slate-800">{c.name}</span>
                                                    <span className="text-slate-500"> &mdash; {c.title}</span>
                                                  </div>
                                                ))}
                                              </div>
                                            ) : (
                                              <span className="text-slate-500 font-normal">
                                                {play.entry_path?.no_contact_note || 'No matching contact identified in supplied data.'}
                                              </span>
                                            )}
                                          </div>
                                        </div>
                                      </div>

                                      {play.entry_path?.recommended_cta && (
                                        <div className="bg-sky-50/60 border border-sky-100 rounded-lg p-2.5 space-y-0.5">
                                          <span className="text-[10px] font-semibold text-sky-800 uppercase tracking-wider block">
                                            RECOMMENDED CTA
                                          </span>
                                          <p className="text-xs font-semibold text-sky-900 leading-relaxed">
                                            {play.entry_path.recommended_cta}
                                          </p>
                                        </div>
                                      )}

                                      {play.checks && (
                                        <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
                                          {Object.entries(play.checks).map(([name, passed]: [string, any]) => (
                                            <span key={name} className={`text-[10px] ${passed ? 'text-emerald-700' : 'text-amber-700'}`}>
                                              {passed ? '\u2713' : '\u2717'} {name.replace(/_/g, ' ')}
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
                        ) : (
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
                                    AI-synthesized business outcomes, quantified impact projections, recommended product family matches, and target CTA entry paths for <strong className="text-amber-950">{play.name}</strong> will be generated automatically when account datasets are uploaded.
                                  </p>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* Discovery / evidence gaps - areas the data raises but does not
                          support as an HP opportunity. Deliberately reduced: no HP
                          capability, no products, no CTA. */}
                      {discoveryAreas.length > 0 && (
                        <div className="space-y-3 pt-2">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-600 flex items-center gap-2">
                            <Compass className="w-3.5 h-3.5 text-slate-400" />
                            <span>Discovery / evidence gaps</span>
                            <span className="text-slate-400">({discoveryAreas.length})</span>
                          </h3>
                          <p className="text-[11px] text-slate-400 max-w-3xl leading-relaxed">
                            The data raises these areas but does not support them as HP
                            opportunities. They carry no recommendation &mdash; only what the
                            evidence shows, what is missing, and what to confirm.
                          </p>

                          {discoveryAreas.map((area: any, i: number) => (
                            <div key={area.play_key || i} className="bg-slate-50 rounded-xl border border-dashed border-slate-300 p-4 space-y-2.5">
                              <div className="flex flex-wrap items-start justify-between gap-2">
                                <p className="text-sm font-semibold text-slate-700">{area.title}</p>
                                <span className="text-[11px] font-semibold text-slate-600 bg-white border border-slate-200 px-2 py-0.5 rounded flex-shrink-0">
                                  {area.severity}
                                </span>
                              </div>

                              {area.missing_checks?.length > 0 && (
                                <p className="text-[11px] text-amber-700">
                                  Failed checks: {area.missing_checks.map((m: string) => m.replace(/_/g, ' ')).join(', ')}
                                </p>
                              )}

                              {area.scale_statement && (
                                <div>
                                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">What the data shows</span>
                                  <p className="text-xs text-slate-600 leading-relaxed">{area.scale_statement}</p>
                                </div>
                              )}

                              {area.account_evidence?.length > 0 && (
                                <div className="space-y-1">
                                  {area.account_evidence.map((ev: any, j: number) => (
                                    <p key={j} className="text-[11px] text-slate-500 font-mono leading-relaxed break-words">
                                      [{ev.dataset} &rarr; {ev.field}] &ldquo;{ev.quote}&rdquo;
                                    </p>
                                  ))}
                                </div>
                              )}

                              {area.timing_note && (
                                <div>
                                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">What to confirm</span>
                                  <p className="text-xs text-slate-600 leading-relaxed">{area.timing_note}</p>
                                </div>
                              )}

                              {area.entry_path?.target_contacts?.length > 0 && (
                                <div>
                                  <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block">Who to ask</span>
                                  <p className="text-xs text-slate-600">
                                    {area.entry_path.target_contacts.map((c: any) => `${c.name} — ${c.title}`).join('; ')}
                                  </p>
                                </div>
                              )}
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
                  const sourceBreakdown: Record<string, any> = gridData?.source_breakdown || {};
                  const relevanceBreakdown: any = gridData?.relevance_breakdown || { high: 0, medium: 0, low: 0 };
                  const priorityCount: number = gridData?.priority_contacts_count ?? 0;
                  const departmentGroups: any[] = influenceData.department_groups || [];
                  const rankedEntryPath: any[] = influenceData.ranked_entry_path || [];

                  // Filter option lists are derived from the data, never hardcoded.
                  const uniq = (vals: any[]) => Array.from(new Set(vals.filter(Boolean))).sort() as string[];
                  const seniorityOptions = uniq(contactsList.map(c => c.seniority_band));
                  const influenceOptions = uniq(contactsList.map(c => c.influence_type));
                  const priorityOptions = uniq(contactsList.map(c => c.priority));
                  const departmentOptions = uniq(contactsList.map(c => c.normalized_department));

                  const matchesFilters = (c: any) => {
                    if (stakeholderSearch) {
                      const q = stakeholderSearch.toLowerCase().trim();
                      const hay = `${c.full_name || ''} ${c.title || ''} ${c.normalized_department || ''}`.toLowerCase();
                      if (!hay.includes(q)) return false;
                    }
                    if (stakeholderDeptFilter !== 'ALL' && c.normalized_department !== stakeholderDeptFilter) return false;
                    if (stakeholderSeniorityFilter !== 'ALL' && c.seniority_band !== stakeholderSeniorityFilter) return false;
                    if (stakeholderInfluenceFilter !== 'ALL' && c.influence_type !== stakeholderInfluenceFilter) return false;
                    if (stakeholderPriorityFilter !== 'ALL' && c.priority !== stakeholderPriorityFilter) return false;
                    if (stakeholderRelevanceFilter !== 'ALL' && c.hp_relevance_band !== stakeholderRelevanceFilter) return false;
                    return true;
                  };

                  const filteredContacts = contactsList.filter(matchesFilters);
                  const filteredIds = new Set(filteredContacts.map(c => c.contact_id));
                  const priorityContacts = filteredContacts.filter(c => c.is_priority_contact);
                  const topContacts = filteredContacts
                    .filter(c => c.is_priority_contact || c.hp_relevance_band === 'high')
                    .sort((a, b) => b.stakeholder_score - a.stakeholder_score);
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
                  const influenceBadge: Record<string, string> = {
                    'Decision Maker': 'bg-red-50 text-red-600 border border-red-200',
                    'Budget Holder': 'bg-orange-50 text-orange-600 border border-orange-200',
                    'Technical Evaluator': 'bg-purple-50 text-purple-600 border border-purple-200',
                    'Influencer': 'bg-blue-50 text-blue-600 border border-blue-200',
                  };
                  const priorityBadge: Record<string, string> = {
                    High: 'bg-red-100 text-red-700',
                    Medium: 'bg-yellow-100 text-yellow-700',
                    Low: 'bg-gray-100 text-gray-600',
                  };
                  const relevanceMeta: Record<string, { label: string; cls: string }> = {
                    high: { label: 'High HP fit', cls: 'bg-emerald-50 text-emerald-700 border border-emerald-200' },
                    medium: { label: 'Medium HP fit', cls: 'bg-blue-50 text-blue-600 border border-blue-200' },
                    low: { label: 'Lower HP fit', cls: 'bg-slate-100 text-slate-400 border border-slate-200' },
                  };

                  const handleExportCsv = () => {
                    const cols = ['full_name', 'title', 'normalized_department', 'seniority_band', 'influence_type',
                      'priority', 'hp_relevance_band', 'stakeholder_score', 'is_priority_contact',
                      'email', 'email_status', 'phone', 'linkedin_url', 'source'];
                    const esc = (v: any) => `"${String(v ?? '').replace(/"/g, '""')}"`;
                    const rows = filteredContacts.map((c: any) => {
                      const tp = talkingPoints[c.contact_id] || {};
                      return [...cols.map(k => esc(c[k])), esc(tp.how_to_open), esc(tp.hp_play_focus), esc(tp.decision_power)].join(',');
                    });
                    const csv = [[...cols, 'how_to_open', 'hp_play_focus', 'decision_power'].join(','), ...rows].join('\n');
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
                        <option key={o} value={o}>{relevanceMeta[o]?.label || o}</option>
                      ))}
                    </select>
                  );

                  const renderBadges = (c: any) => (
                    <>
                      <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${seniorityBadge[c.seniority_band] || 'bg-gray-100 text-gray-600'}`}>{c.seniority_band}</span>
                      <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${influenceBadge[c.influence_type] || 'bg-slate-50 text-slate-600 border border-slate-200'}`}>{c.influence_type}</span>
                      <span className={`text-[11px] font-medium px-2 py-0.5 rounded ${priorityBadge[c.priority] || 'bg-gray-100 text-gray-600'}`}>{c.priority}</span>
                    </>
                  );

                  // Email / phone block, shared by the expandable card once revealed.
                  const renderContactLines = (c: any) => (
                    <div className="space-y-1 text-xs">
                      <p className="text-slate-600 font-normal">
                        <span className="text-slate-500">Email: </span>
                        {c.email
                          ? <a href={`mailto:${c.email}`} className="text-hp-navy font-medium hover:underline">{c.email}</a>
                          : <span className="text-slate-400 italic">not available</span>}
                      </p>
                      <p className="text-slate-600 font-normal flex items-center gap-1.5 flex-wrap">
                        <span className="text-slate-500">Phone: </span>
                        {c.phone
                          ? <span>{c.phone}</span>
                          : <span className="text-slate-400 italic">not available</span>}
                        {c.contact_location && (
                          <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">{c.contact_location}</span>
                        )}
                        <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">{c.source}</span>
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
                              {c.is_priority_contact && <Star className="w-3.5 h-3.5 text-hp-navy fill-hp-navy flex-shrink-0" />}
                            </div>
                            <p className="text-xs text-slate-500 font-normal leading-snug">
                              {c.title || 'Title unspecified'} &middot; <span className="text-slate-400">{c.normalized_department}</span>
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
                              <p className="text-[11px] text-slate-400 italic">No talking points generated for this contact.</p>
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
                          <p className="text-xs text-slate-400 mt-0.5">
                            {priorityCount} Priority Contact{priorityCount === 1 ? '' : 's'} &middot; {relevanceBreakdown.high} High HP Fit &middot; {relevanceBreakdown.medium} Medium HP Fit &middot; {relevanceBreakdown.low} Lower HP Fit
                          </p>
                          {sourceBreakdown['Source A'] !== undefined && (
                            <p className="text-[11px] text-slate-400 mt-0.5">
                              Source A: {sourceBreakdown['Source A']} &middot; Apollo: {sourceBreakdown['Apollo']}
                            </p>
                          )}
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
                        {renderFilter('Influence', stakeholderInfluenceFilter, setStakeholderInfluenceFilter, influenceOptions)}
                        {renderFilter('Priority', stakeholderPriorityFilter, setStakeholderPriorityFilter, priorityOptions)}
                        {renderFilter('HP Relevance', stakeholderRelevanceFilter, setStakeholderRelevanceFilter, ['high', 'medium', 'low'])}
                        <button
                          type="button"
                          onClick={() => {
                            setStakeholderSearch(''); setStakeholderDeptFilter('ALL'); setStakeholderSeniorityFilter('ALL');
                            setStakeholderInfluenceFilter('ALL'); setStakeholderPriorityFilter('ALL'); setStakeholderRelevanceFilter('ALL');
                          }}
                          className="text-xs font-medium text-slate-500 hover:text-slate-800 px-2 py-1.5"
                        >
                          Clear
                        </button>
                      </div>

                      {/* Sub-tabs */}
                      <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1 w-fit">
                        <button
                          type="button"
                          onClick={() => setStakeholderSubTab('grid')}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                            stakeholderSubTab === 'grid' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                          }`}
                        >
                          <Users className="w-3.5 h-3.5" />
                          <span>Stakeholder Grid</span>
                        </button>
                        <button
                          type="button"
                          onClick={() => setStakeholderSubTab('entry_path')}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                            stakeholderSubTab === 'entry_path' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                          }`}
                        >
                          <ArrowRight className="w-3.5 h-3.5" />
                          <span>Entry Path</span>
                        </button>
                      </div>

                      {stakeholderSubTab === 'grid' && (
                        <div className="space-y-6">

                          {/* Priority Contacts - three across */}
                          <div className="space-y-3">
                            <div className="flex items-center gap-2 flex-wrap">
                              <Star className="w-4 h-4 text-hp-navy fill-hp-navy" />
                              <h4 className="text-base font-bold text-slate-900">Priority Contacts</h4>
                              <span className="text-[10px] font-semibold text-hp-navy bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-full">
                                {priorityContacts.length} HP-relevant
                              </span>
                              {getClassificationBadge('inferred')}
                            </div>
                            <p className="text-xs text-slate-500 font-normal">
                              The stakeholders scored most relevant to driving HP&apos;s case at {selectedAccount?.name} &mdash; each with their own contact details and an opening angle, not just role and department counts.
                            </p>

                            {priorityContacts.length === 0 ? (
                              <p className="text-xs text-slate-400 italic py-4">No priority contacts match the current filters.</p>
                            ) : (
                              <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
                                {priorityContacts.map((c: any) => {
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
                                          <p className="text-xs text-slate-500 font-normal leading-snug">{c.title || 'Title unspecified'}</p>
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
                                            : <span className="text-slate-400 italic">Email not available</span>}
                                        </div>
                                        <div className="flex items-center gap-2 flex-wrap">
                                          <Phone className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                                          {c.phone
                                            ? <span className="text-slate-700 font-normal">{c.phone}</span>
                                            : <span className="text-slate-400 italic">Phone not available</span>}
                                          {c.contact_location && (
                                            <span className="text-[10px] font-medium text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded">{c.contact_location}</span>
                                          )}
                                          <span className="text-[10px] font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded">
                                            {c.source}
                                          </span>
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
                                        <p className="text-[11px] text-slate-400 italic">No opening angle generated for this contact.</p>
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
                                })}
                              </div>
                            )}
                          </div>

                          {/* All Departments | Top Contacts */}
                          <div className="border-t border-slate-200 pt-5 space-y-4">
                            <div className="flex items-center gap-2 flex-wrap">
                              <div className="flex items-center gap-1 bg-slate-100 rounded-lg p-1 w-fit">
                                <button
                                  type="button"
                                  onClick={() => setStakeholderViewMode('departments')}
                                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                                    stakeholderViewMode === 'departments' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                                  }`}
                                >
                                  All Departments
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setStakeholderViewMode('top_contacts')}
                                  className={`px-3 py-1.5 rounded-md text-xs font-semibold transition ${
                                    stakeholderViewMode === 'top_contacts' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'
                                  }`}
                                >
                                  Top Contacts
                                </button>
                              </div>
                              {getClassificationBadge('derived')}
                            </div>

                            {stakeholderViewMode === 'departments' && (
                              <div className="space-y-2">
                                {departmentGroups.map((g: any) => {
                                  const surfaced = (g.surfaced_contact_ids || []).map((id: string) => byId[id]).filter((c: any) => c && filteredIds.has(c.contact_id));
                                  const lower = (g.lower_relevance_contact_ids || []).map((id: string) => byId[id]).filter((c: any) => c && filteredIds.has(c.contact_id));
                                  if (surfaced.length === 0 && lower.length === 0) return null;
                                  const isOpen = expandedDepts[g.department] || false;
                                  const showLow = expandedDepts[`${g.department}__low`] || false;
                                  return (
                                    <div key={g.department} className="space-y-2">
                                      <button
                                        type="button"
                                        onClick={() => setExpandedDepts(prev => ({ ...prev, [g.department]: !prev[g.department] }))}
                                        className="flex items-center gap-2 text-left group"
                                      >
                                        <h5 className="text-sm font-bold text-slate-800 group-hover:text-hp-navy transition">{g.department}</h5>
                                        <span className="text-[11px] font-normal text-slate-500 bg-slate-100 px-2 py-0.5 rounded"
                                              title="HP-relevant contacts (Priority Contacts plus High/Medium HP fit) vs. total roster in this department">
                                          {g.hp_relevant_count} HP-relevant &middot; {g.total_count} total
                                        </span>
                                        {isOpen
                                          ? <ChevronUp className="w-4 h-4 text-slate-400" />
                                          : <ChevronDown className="w-4 h-4 text-slate-400" />}
                                      </button>

                                      {isOpen && (
                                        <div className="space-y-2 pb-2">
                                          {surfaced.length === 0 ? (
                                            <p className="text-[11px] text-slate-400 italic">
                                              No high or medium HP-relevance contacts in this department &mdash; see lower-relevance contacts below.
                                            </p>
                                          ) : (
                                            surfaced.map((c: any) => renderExpandableCard(c))
                                          )}

                                          {lower.length > 0 && (
                                            <div className="pt-1">
                                              <button
                                                type="button"
                                                onClick={() => setExpandedDepts(prev => ({ ...prev, [`${g.department}__low`]: !prev[`${g.department}__low`] }))}
                                                className="text-[11px] font-semibold text-slate-500 hover:text-slate-800 flex items-center gap-1"
                                              >
                                                {showLow ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                                                <span>{showLow ? 'Hide' : 'Show'} {lower.length} lower-relevance contact{lower.length === 1 ? '' : 's'}</span>
                                                <span className="text-slate-400 font-normal">(limited fit for an HP hardware conversation)</span>
                                              </button>
                                              {showLow && (
                                                <div className="opacity-80 space-y-2 mt-2">
                                                  {lower.map((c: any) => renderExpandableCard(c))}
                                                </div>
                                              )}
                                            </div>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  );
                                })}
                              </div>
                            )}

                            {stakeholderViewMode === 'top_contacts' && (
                              <div className="space-y-2">
                                {topContacts.length === 0 ? (
                                  <p className="text-xs text-slate-400 italic py-4">No high HP-relevance contacts match the current filters.</p>
                                ) : (
                                  topContacts.map((c: any) => renderExpandableCard(c))
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {stakeholderSubTab === 'entry_path' && (
                        <div className="space-y-3">
                          <p className="text-xs text-slate-500 font-normal">
                            Ranked by seniority (25%), HP relevance (25%), influence (20%), data completeness (15%) and priority (15%).
                          </p>
                          <div className="bg-white rounded-xl border border-slate-200 shadow-xs divide-y divide-slate-100">
                            {rankedEntryPath.filter((s: any) => filteredIds.has(s.contact_id)).map((step: any) => (
                              <div key={step.contact_id} className="p-4">
                                <div className="flex items-start gap-3">
                                  <div className="w-6 h-6 rounded-full bg-hp-navy text-white flex items-center justify-center text-[11px] font-semibold flex-shrink-0">
                                    {step.order}
                                  </div>
                                  <div className="min-w-0 flex-1">
                                    <p className="text-sm font-semibold text-slate-900">{step.full_name}</p>
                                    <p className="text-xs text-slate-500 font-normal">{step.title} &middot; <span className="text-slate-400">{step.department}</span></p>
                                  </div>
                                  <span className="text-xs font-semibold text-slate-700 flex-shrink-0">
                                    {step.stakeholder_score}<span className="text-slate-400 font-normal">/100</span>
                                  </span>
                                </div>
                                <div className="mt-2.5 space-y-1.5 pl-9">
                                  {Object.entries(step.score_components || {}).map(([dim, val]: [string, any]) => (
                                    <div key={dim} className="flex items-center gap-2">
                                      <span className="text-[10px] text-slate-400 font-medium w-32 capitalize flex-shrink-0">{dim.replace(/_/g, ' ')}</span>
                                      <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                                        <div className="h-1.5 bg-hp-navy/60 rounded-full" style={{ width: `${val}%` }}></div>
                                      </div>
                                      <span className="text-[10px] font-mono text-slate-400 w-10 text-right flex-shrink-0">{val}/100</span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

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
                  const webstackWidget = widgets.find(w => w.widget_key === 'webstack_breakdown');
                  const detectionsWidget = widgets.find(w => w.widget_key === 'tech_detections_reference');
                  const hpRecWidget = widgets.find(w => w.widget_key === 'technographic_hp_recommendations');
                  const hpRecData: any = hpRecWidget?.data || {};
                  const hpRecs: any[] = hpRecData.recommendations || [];

                  const mapData = mapWidget?.data || {};
                  const matrixData = matrixWidget?.data || {};
                  const webstackData = webstackWidget?.data || {};
                  const detectionsData = detectionsWidget?.data || {};

                  const categoriesList: any[] = mapData.categories || [];
                  const displayedCategories = categoriesList.filter((cat: any) => {
                    if (opportunitiesOnly && !cat.is_opportunity) return false;
                    return true;
                  });

                  const totalTechCount = matrixData.total_tech_count ?? 0;
                  const categoryMatrix: Record<string, string[]> = matrixData.category_matrix || {};
                  const totalWebTechCount = webstackData.total_web_tech_count ?? 0;
                  const premiumTechCount = webstackData.premium_tech_count || '0';
                  const webSpendEst = webstackData.web_spend_estimate || 'N/A';
                  const webstackTechs: string[] = webstackData.technologies || [];
                  const totalDetectionsCount = detectionsData.total_detections_count ?? 0;
                  const detectionsList: any[] = detectionsData.detections || [];

                  const rawCategories = Object.keys(categoryMatrix);
                  const filteredRawCategories = rawCategories.filter(cat => {
                    if (techCategoryFilter !== 'ALL' && cat !== techCategoryFilter) return false;
                    if (!techSearch.trim()) return true;
                    const query = techSearch.toLowerCase();
                    const catMatches = cat.toLowerCase().includes(query);
                    const items = categoryMatrix[cat] || [];
                    const itemMatches = items.some(item => item.toLowerCase().includes(query));
                    return catMatches || itemMatches;
                  });

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
                            {mapData.total_detected_technologies ?? '--'} technologies detected in {selectedAccount?.name || 'Target Account'}&apos;s technographics export
                            {typeof mapData.mapped_signal_count === 'number' && (
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
                                <div className="text-xl font-black font-mono text-slate-900">{mapData.total_detected_technologies ?? '--'}</div>
                              </div>
                              <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                                <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">MAPPED TO HP CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-slate-900">
                                  {typeof mapData.mapped_signal_count === 'number' && typeof mapData.total_detected_technologies === 'number'
                                    ? `${mapData.mapped_signal_count}/${mapData.total_detected_technologies}`
                                    : '--'}
                                </div>
                              </div>
                              <div className="bg-blue-50/60 p-3.5 rounded-xl border border-blue-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-blue-800 uppercase tracking-wider block">HP-MAPPED CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-hp-navy">{mapData.hp_mapped_categories ?? '--'}</div>
                              </div>
                              <div className="bg-emerald-50/60 p-3.5 rounded-xl border border-emerald-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-emerald-800 uppercase tracking-wider block">WHITESPACE CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-emerald-700">{mapData.whitespace_categories ?? '--'}</div>
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
                                              <span className="text-[10px] font-extrabold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full border border-emerald-300">
                                                {vendor.risk_level}
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

                                          <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 border-t border-emerald-200/60 pt-2 flex items-center justify-between">
                                            <span className="truncate pr-2">{vendor.provenance}</span>
                                            <span className="font-bold text-slate-500">{vendor.confidence}</span>
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
                                                    title={vendor.hp_relationship || ''}
                                                    className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200"
                                                  >
                                                    {vendor.hp_relationship_label}
                                                  </span>
                                                )}
                                              </div>
                                            </div>
                                          </div>

                                          <p className="text-xs text-slate-500 font-medium">{vendor.description}</p>

                                          {vendor.hp_play && (
                                            <div className="mt-3 bg-blue-50/80 border border-blue-200/80 rounded-xl p-2.5 text-xs text-hp-navy font-semibold space-y-0.5">
                                              <span className="font-extrabold text-hp-navy flex items-center gap-1">
                                                <span>&rarr;</span>
                                                <span>{vendor.hp_play.product}</span>
                                              </span>
                                              <p className="text-[11px] text-slate-600 font-normal italic pl-4">
                                                {vendor.hp_play.play_text}
                                              </p>
                                            </div>
                                          )}
                                        </div>

                                        <div className="text-[9px] font-mono uppercase tracking-wider text-slate-400 border-t border-slate-100 pt-2 flex items-center justify-between">
                                          <span className="truncate pr-2">{vendor.provenance}</span>
                                          <span
                                            className="font-bold text-slate-500 whitespace-nowrap"
                                            title={vendor.evidence_basis || ''}
                                          >
                                            {vendor.confidence}
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
                                    <HpRecommendationCard key={rec.rule_id} rec={rec} />
                                  ))}

                               </div>
                             ))}
                          </div>
                      {/* Anything the category mapping could not place, plus the
                          rules that were evaluated and not used - surfaced so a
                          recommendation is never dropped without explanation. */}
                      {hpRecs.filter((r: any) => !r.category_key).map((rec: any) => (
                        <HpRecommendationCard key={rec.rule_id} rec={rec} />
                      ))}

                      {(hpRecData.rules_blocked || []).length > 0 && (
                        <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded px-3 py-2">
                          <span className="font-semibold text-slate-600">Rules evaluated but not used: </span>
                          {(hpRecData.rules_blocked || [])
                            .map((b: any) => `rule ${b.rule_id} (${b.blocked})`).join('; ')}
                        </div>
                      )}

                        </div>


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

                  // Score presentation, matching the reference app's bands.
                  const scoreColor = (n: number) =>
                    n >= 80 ? 'bg-green-500' : n >= 60 ? 'bg-teal-500'
                      : n >= 40 ? 'bg-amber-500' : n >= 20 ? 'bg-orange-500' : 'bg-rose-500';
                  const scoreLabel = (n: number) =>
                    n >= 80 ? 'Strong' : n >= 60 ? 'Good' : n >= 40 ? 'Fair'
                      : n >= 20 ? 'Weak' : 'Poor';
                  const scoreBadge = (n: number | null) =>
                    n == null ? 'border-slate-200 text-slate-400'
                      : n >= 80 ? 'border-green-300 text-green-700 bg-green-50'
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
                                  {!chosenPersona.is_named_person && (
                                    <li className="text-amber-700">&ndash; Role type, not a named person</li>
                                  )}
                                </ul>
                              </div>

                              <div>
                                <p className="text-sm font-semibold text-slate-700 mb-1.5">Pain Points</p>
                                {(chosenPersona.pain_points || []).length > 0 ? (
                                  <ul className="space-y-1 text-xs text-slate-600">
                                    {chosenPersona.pain_points.map((x: string, i: number) => (
                                      <li key={i}>&ndash; {x}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="text-xs text-slate-400">Not available for this contact</p>
                                )}
                              </div>

                              <div>
                                <p className="text-sm font-semibold text-slate-700 mb-1.5">Opening Angle</p>
                                {chosenPersona.opening_angle ? (
                                  <p className="text-xs text-slate-600">{chosenPersona.opening_angle}</p>
                                ) : (
                                  <p className="text-xs text-slate-400">Not available</p>
                                )}
                              </div>

                              <div>
                                <p className="text-sm font-semibold text-slate-700 mb-1.5">Account Signals</p>
                                {(evalOptions.account_context?.triggers || []).length > 0 ? (
                                  <ul className="space-y-1 text-xs text-slate-600">
                                    {evalOptions.account_context.triggers.slice(0, 4).map((x: string, i: number) => (
                                      <li key={i}>&ndash; {x}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <p className="text-xs text-slate-400">Not available</p>
                                )}
                              </div>
                            </div>

                            <div>
                              <p className="text-sm font-semibold text-slate-700 mb-1.5">HP Opportunity</p>
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
                                  No HP deck-usage rule matched this account&apos;s verified evidence.
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
                                        : src === 'hiring_role_proxy' ? 'Open job postings (role proxy)'
                                        : 'Not available'}
                                    </span>
                                  </p>
                                ))}
                                {Object.entries(evalOptions.context_sources || {})
                                  .filter(([f]: any) => ['hp_opportunity', 'competitive_vendors', 'triggers'].includes(f))
                                  .map(([field, src]: any) => (
                                    <p key={field} className="text-slate-700">
                                      <span className="font-medium capitalize">{field.replace(/_/g, ' ')}:</span>{' '}
                                      <span className={src === 'Not available' ? 'text-slate-400' : 'text-indigo-600'}>{src}</span>
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

                          {!evaluation.ai_available && (
                            <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                              AI scoring was unavailable. The coded checks below still ran. No
                              dimension scores or composite are shown, rather than estimated ones.
                            </div>
                          )}

                          {/* Step D - dimension scores */}
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
                            <h3 className="text-sm font-semibold text-slate-800">
                              Step D &mdash; Dimension Scores
                            </h3>

                            {Object.keys(evaluation.dimensions || {}).length > 0 ? (
                              <div className="space-y-2.5">
                                {Object.entries(evaluation.dimensions).map(([k, v]: any) => (
                                  <div key={k} className="flex items-center gap-3">
                                    <span className="text-xs font-medium text-slate-600 w-28 text-right capitalize">
                                      {k.replace(/_/g, ' ')}
                                    </span>
                                    <div className="flex-1 bg-slate-100 rounded-full h-4 overflow-hidden">
                                      <div
                                        className={`${scoreColor(v)} h-full rounded-full transition-all duration-500`}
                                        style={{ width: `${v}%` }}
                                      />
                                    </div>
                                    <span className="text-[11px] font-semibold text-slate-700 w-8 text-right">
                                      {v}
                                    </span>
                                    <span className="text-[10px] text-slate-400 w-16">
                                      {scoreLabel(v)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            ) : (
                              <p className="text-xs text-slate-500">
                                No dimension scores were published for this evaluation.
                              </p>
                            )}

                            <div className="border-t border-slate-100 pt-4 mt-4">
                              <div className="flex items-center gap-4 flex-wrap">
                                <div className={`inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border-2 ${scoreBadge(evaluation.composite)}`}>
                                  <span className="text-2xl font-bold">
                                    {evaluation.composite_available ? evaluation.composite : '—'}
                                  </span>
                                  <div>
                                    <span className="text-[10px] uppercase tracking-wide font-semibold">/ 100</span>
                                    <p className="text-xs font-medium">
                                      {evaluation.composite_available ? evaluation.score_band : 'Unavailable'}
                                    </p>
                                  </div>
                                </div>
                                <div className="text-xs text-slate-500">
                                  <p className="font-medium text-slate-600 mb-0.5">
                                    Composite ({evaluation.objective_label}) &middot; V{evaluation.version}
                                  </p>
                                  <p className="font-mono text-[10px]">{evaluation.formula_used}</p>
                                  <p className="text-[10px] text-slate-400">
                                    Formula source: {evaluation.formula_source}
                                  </p>
                                </div>
                              </div>
                              {(evaluation.dimension_problems || []).length > 0 && (
                                <p className="mt-3 text-xs font-semibold text-rose-600">
                                  Composite withheld &mdash; {evaluation.dimension_problems.join('; ')}
                                </p>
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
                          {(evaluation.reaction_withheld || []).length > 0 && (
                            <div className="bg-amber-50 rounded-xl border border-amber-200 p-5">
                              <h3 className="text-sm font-semibold text-amber-800 mb-1">
                                Persona Reaction withheld
                              </h3>
                              {evaluation.reaction_withheld.map((f: string, i: number) => (
                                <p key={i} className="text-xs text-amber-800">&bull; {f}</p>
                              ))}
                            </div>
                          )}

                          {/* Step E - phrase table, with the recommendation checkboxes inline. */}
                          <div className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
                            <h3 className="text-sm font-semibold text-slate-800">
                              Step E &mdash; Phrase-Level Analysis
                            </h3>
                            {evaluation.phrases_dropped > 0 && (
                              <p className="text-xs text-slate-500">
                                {evaluation.phrases_dropped} returned chunk(s) were dropped because they
                                could not be located in your message.
                              </p>
                            )}
                            {(evaluation.phrases || []).length === 0 ? (
                              <p className="text-xs text-slate-500">
                                No phrase-level feedback was produced for this message.
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
                            account&apos;s technographics evidence. These are not statements made by
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
                        <div className="bg-amber-50/60 border border-amber-200/80 rounded-2xl p-6 text-center space-y-3">
                          <div className="w-10 h-10 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto border border-amber-300">
                            <Sparkles className="w-5 h-5 text-amber-600" />
                          </div>
                          <h4 className="text-xs font-bold text-amber-900 uppercase tracking-wider">
                            No objections generated
                          </h4>
                          <p className="text-xs text-amber-800 max-w-xl mx-auto leading-relaxed">
                            {reframesData.notice || 'Objection generation has not run for this account. The incumbent evidence below is shown as extracted; no objections are invented.'}
                          </p>
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
                                      {card.not_in_technographics && (
                                        <p className="text-[11px] text-blue-700/80 mt-2 leading-relaxed">
                                          No vendor for this area appears in this account&apos;s technographics
                                          export. That is a limit of what this dataset reports &mdash; it is not
                                          evidence that no such vendor or process exists.
                                        </p>
                                      )}
                                    </div>

                                    <div className="bg-purple-50 border border-purple-200 rounded-lg p-4">
                                      <div className="flex items-center gap-2 mb-2">
                                        <HelpCircle className="w-4 h-4 text-purple-600" />
                                        <p className="text-xs font-semibold text-purple-700 uppercase tracking-wider">Counter Question</p>
                                      </div>
                                      <p className="text-sm text-purple-900 italic">&ldquo;{card.counter_question}&rdquo;</p>
                                    </div>

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
                                            : ' \u2014 no contact in this account\u2019s data clearly owns this area, so the area itself is named.'}
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

                  const techEvidence = contextData.technology_evidence || {};
                  const intentEvidence = contextData.intent_evidence || {};
                  const newsEvidence = contextData.news_evidence || {};
                  const fullTechStack: string[] = techEvidence.full_tech_stack || [];
                  const intentTopics: any[] = intentEvidence.topics || [];
                  const newsTriggers: any[] = newsEvidence.triggers || [];

                  const pillars: any[] = pillarsData.pillars || [];
                  const vectors: any[] = pillarsData.vectors || [];
                  const whyHpItems: any[] = pillarsData.why_hp_items || [];
                  const generation = pillarsData.generation || {};
                  const hasHouse = pillars.length > 0;

                  // The headline is generated; when it was withheld the flat
                  // umbrella sentence still stands in, so the hero is never empty.
                  const headline = pillarsData.umbrella_headline || pillarsData.umbrella_message || '';
                  const lead = pillarsData.umbrella_lead || '';

                  const cmIndex = (retrievalStatus?.indexes || [])
                    .find((i: any) => i.index === 'content_messaging');



                  // Two evidence rows from the same unlinked source are one chip.
                  // A row that links somewhere keeps its own, since the links
                  // genuinely go to different places. The count is shown so
                  // collapsing never hides how much evidence there was.
                  const dedupeSources = (sources: any[]) => {
                    const byKey = new Map<string, any>();
                    (sources || []).forEach((s: any) => {
                      const key = `${s.label}::${s.source_url || ''}`;
                      const seen = byKey.get(key);
                      if (seen) { seen.count = (seen.count || 1) + 1; }
                      else { byKey.set(key, { ...s, count: 1 }); }
                    });
                    return Array.from(byKey.values());
                  };

                  // The chip reads as provenance, never as a bare identifier; the
                  // exact evidence_id stays in the tooltip so a claim is still
                  // traceable to the registry row behind it.
                  const SourceChip = ({ s }: { s: any }) => {
                    // Much of this evidence is a cell in an uploaded CSV, which
                    // has no web page to open. Rather than render every chip as
                    // though it were clickable, an unlinkable one is flat and
                    // carries no external-link mark, so what can be opened is
                    // obvious before anyone clicks.
                    const linked = !!s.source_url;
                    const detail = s.quote
                      ? `${s.field ? s.field + ' — ' : ''}"${s.quote}"`
                      : String(s.source_text || '').slice(0, 180);
                    return (
                      <span
                        title={`${s.evidence_id}${detail ? ` — ${detail}` : ''}`}
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-[3px] text-[10px] font-semibold whitespace-nowrap align-middle ${
                          linked
                            ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                            : 'border-slate-200 bg-slate-50 text-slate-500'}`}
                      >
                        <FileText className="w-2.5 h-2.5" />
                        {linked ? (
                          <a href={s.source_url} target="_blank" rel="noopener noreferrer"
                             className="hover:underline">
                            {s.label}{s.count > 1 ? ' (' + s.count + ')' : ''}
                          </a>
                        ) : (
                          <>{s.label}{s.count > 1 ? ' (' + s.count + ')' : ''}</>
                        )}
                        {linked && <ExternalLink className="w-2.5 h-2.5" />}
                      </span>
                    );
                  };

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
                              {!pillarsData.umbrella_headline && (
                                <p className="text-[10px] text-amber-700 mt-2">
                                  Headline withheld — it introduced material the pillars do not support.
                                </p>
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
                                        <span
                                          title={sourced.dropped > 0
                                            ? `${sourced.dropped} proposed proof point(s) cited evidence that did not resolve and were discarded`
                                            : undefined}
                                          className={`rounded-full px-3 py-1 text-[11px] font-semibold whitespace-nowrap h-fit ${
                                            (sourced.proposed ?? sourced.total) > 0 && sourced.sourced === (sourced.proposed ?? sourced.total)
                                              ? 'bg-slate-100 text-slate-600 border border-slate-200'
                                              : 'bg-amber-50 text-amber-700 border border-amber-200'}`}>
                                          {sourced.sourced}/{sourced.proposed ?? sourced.total} sourced
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
                                            {p.hp_resource?.url && (
                                              <div className="flex items-center gap-2 mt-3">
                                                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-400">
                                                  HP resource
                                                </span>
                                                <a
                                                  href={p.hp_resource.url}
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
                                            Proof points ({sourced.total} shown, {sourced.sourced} sourced
                                            {sourced.dropped > 0 && ` · ${sourced.dropped} discarded as unverifiable`})
                                          </p>
                                          {sourced.total === 0 ? (
                                            <p className="text-xs text-slate-400">No proof point survived validation.</p>
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
                            const used = dedupeSources(
                              pillars.flatMap((p: any) => [
                                ...(p.proof_points || []).flatMap((pr: any) => pr.sources || []),
                                ...(p.challenge_evidence || []),
                              ])
                            );
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

                          {/* What was discarded, rather than a quietly shorter list. */}
                          <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-[11px] text-slate-500">
                            <p className="font-bold uppercase tracking-wider text-slate-400 mb-1.5">Generation audit</p>
                            <p>
                              {generation.candidates_returned ?? 0} candidate challenge(s) retrieved ·
                              {' '}{generation.challenges_kept ?? 0} kept after evidence validation ·
                              {' '}{pillars.length} pillar(s) published ·
                              {' '}{generation.invalid_evidence_count ?? 0} unresolvable evidence id(s) dropped
                            </p>
                            {(generation.framing_dropped || []).map((f: any, i: number) => (
                              <p key={i} className="text-amber-700">withheld {f.field}: {(f.reasons || []).join('; ')}</p>
                            ))}
                            {(generation.dropped_challenges || []).map((d: any, i: number) => (
                              <p key={i} className="text-slate-400">dropped: {d.challenge} — {d.reason}</p>
                            ))}
                            <p className="text-slate-400 mt-1">
                              Retrieved in {generation.retrieval_mode} mode · {fullTechStack.length} technologies,
                              {' '}{intentTopics.length} intent topics, {newsTriggers.length} news triggers indexed
                              {generation.restrictions?.superlatives_blocked && ' · superlatives blocked for this market'}
                              {generation.restrictions?.competitor_claims_blocked && ' · competitor claims blocked'}
                            </p>
                          </div>
                        </>
                      ) : (
                        <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center">
                          <p className="text-sm font-semibold text-slate-700">No message house yet</p>
                          <p className="text-xs text-slate-500 mt-1 max-w-lg mx-auto leading-relaxed">
                            It is built from this account&apos;s firmographics, technology, intent
                            and news evidence, and appears once that data has been indexed.
                            Uploading or replacing any of those files rebuilds it automatically.
                          </p>
                          {cmIndex && cmIndex.status !== 'READY' && (
                            <p className="text-xs text-slate-400 mt-2">
                              Retrieval index: {cmIndex.status}
                              {cmIndex.blocked_reason ? ` — ${cmIndex.blocked_reason}` : ''}
                            </p>
                          )}
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
                    { id: 'linkedin', title: 'LinkedIn Post', subtitle: 'Social selling content for LinkedIn' },
                    { id: 'one_pager', title: 'One-Pager', subtitle: 'Single-page solution overview for the account' },
                    { id: 'exec_brief', title: 'Executive Brief', subtitle: '2-page intelligence brief for leadership' },
                    { id: 'follow_up', title: 'Follow-up Note', subtitle: 'Post-meeting follow-up with next steps' },
                    { id: 'branded_emailer', title: 'Branded Emailer', subtitle: 'HP-branded email with visual preview and HTML download' },
                    { id: 'landing_page', title: 'Landing Page', subtitle: 'HP-branded landing page with visual preview and HTML download' }
                  ];

                  const sourcedTopics: string[] = contextData.sourced_topics || [
                    'Z by HP Workstations',
                    'Poly collaboration hardware',
                    'HP Elite & Pro PCs',
                    'HP Enterprise Printing & Managed Print Services'
                  ];

                  // Co-creation step 2: ask for angles instead of an asset. One
                  // cheap call; the expensive generate+retry loop runs later, on
                  // the one angle the seller actually picked.
                  const handleSuggestAngles = async () => {
                    if (!selectedAccountId) return;
                    const topicValue = (customTopic.trim() || selectedTopic || '').trim();
                    if (!topicValue) return;
                    const personaForRequest = targetPersonas.find(p => p.id === selectedPersona) || targetPersonas[0];
                    setIsSuggestingAngles(true);
                    setAngleNotice(null);
                    setGenerateError(null);
                    try {
                      const response = await api.post<WidgetResponse>(
                        `/accounts/${selectedAccountId}/widgets/content_studio/angles`,
                        {
                          persona_id: personaForRequest?.id,
                          content_type: selectedContentType,
                          topic: topicValue,
                          additional_context: additionalContext.trim(),
                        }
                      );
                      const opts = response.data?.data?.options || [];
                      setAngleOptions(opts);
                      setSelectedAngleId(null);
                      setSelectedAngle('');
                      if (!opts.length) {
                        setAngleNotice(response.data?.data?.last_error?.notice
                          || 'No angles were returned. You can generate directly instead.');
                      }
                    } catch (err: any) {
                      setAngleNotice(err?.response?.data?.detail || err?.message || 'Could not suggest angles.');
                    } finally {
                      setIsSuggestingAngles(false);
                    }
                  };

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
                          selected_angle: selectedAngle.trim(),
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
                    kind === 'named' ? 'Named contact' : kind === 'role_proxy' ? 'Hiring proxy' : kind === 'archetype' ? 'Archetype' : null;

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
                              rows={3}
                              value={additionalContext}
                              onChange={(e) => setAdditionalContext(e.target.value)}
                              placeholder="Add specific context, talking points, or recent developments to incorporate..."
                              className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy resize-none"
                            />
                          </div>

                          {/* 5. Suggested angles - the co-creation step.
                              The brief above produces options; the seller picks
                              one and may edit it before generating. Optional by
                              design: generating without choosing an angle still
                              works exactly as it did before. */}
                          <div className="space-y-2 pt-2 border-t border-slate-100">
                            <div className="flex items-center justify-between gap-2">
                              <span className="text-xs font-black text-slate-900 flex items-center gap-1.5 uppercase tracking-wider">
                                <Sparkles className="w-3.5 h-3.5 text-hp-navy" />
                                <span>Suggested Angles (Optional)</span>
                              </span>
                              <button
                                type="button"
                                onClick={handleSuggestAngles}
                                disabled={isSuggestingAngles || isGeneratingContent}
                                className="text-[11px] font-bold text-hp-navy hover:underline disabled:opacity-40 disabled:no-underline"
                              >
                                {isSuggestingAngles ? 'Suggesting...' : angleOptions.length ? 'Suggest again' : 'Suggest angles'}
                              </button>
                            </div>

                            {angleNotice && (
                              <p className="text-[11px] text-slate-500 leading-relaxed">{angleNotice}</p>
                            )}

                            {angleOptions.length > 0 && (
                              <div className="space-y-1.5">
                                {angleOptions.map((opt: any) => {
                                  const picked = selectedAngleId === opt.option_id;
                                  return (
                                    <button
                                      key={opt.option_id}
                                      type="button"
                                      onClick={() => {
                                        if (picked) {
                                          setSelectedAngleId(null);
                                          setSelectedAngle('');
                                        } else {
                                          setSelectedAngleId(opt.option_id);
                                          setSelectedAngle(
                                            [opt.summary, opt.opening_line].filter(Boolean).join(' ')
                                          );
                                        }
                                      }}
                                      className={`w-full text-left px-3 py-2 rounded-xl border transition ${
                                        picked
                                          ? 'bg-blue-50 border-hp-navy ring-1 ring-hp-navy'
                                          : 'bg-slate-50 border-slate-200 hover:border-slate-300'
                                      }`}
                                    >
                                      <span className="block text-[11px] font-bold text-slate-900">{opt.label}</span>
                                      <span className="block text-[11px] text-slate-600 leading-snug mt-0.5">{opt.summary}</span>
                                      {opt.evidence_used?.length > 0 && (
                                        <span className="block text-[10px] text-slate-400 mt-1">
                                          Based on {opt.evidence_used.join(', ')}
                                        </span>
                                      )}
                                    </button>
                                  );
                                })}

                                {/* "selects OR ADJUSTS the option" - the chosen
                                    angle stays editable before it is generated. */}
                                {selectedAngleId && (
                                  <textarea
                                    rows={3}
                                    value={selectedAngle}
                                    onChange={(e) => setSelectedAngle(e.target.value)}
                                    className="w-full px-3 py-2 bg-white border border-slate-300 rounded-xl text-[11px] text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy resize-none"
                                  />
                                )}
                              </div>
                            )}
                          </div>

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
                                <span>{selectedAngleId ? 'Generate from Selected Angle' : 'Generate Content'}</span>
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
                            const gr = generatedAsset.grounding_report || {};
                            const labels: [string, any][] = Object.entries(
                              (activeVariant?.evidence_labels) || generatedAsset.evidence_labels || {});
                            return (
                            <div className="w-full space-y-5 text-left animate-fade-in">

                              {/* Deterministic template, not generated copy. The spec
                                  requires the safe fallback be offered rather than
                                  nothing - and that it never read as model output. */}
                              {generatedAsset.is_fallback && (
                                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
                                  <p className="text-[11px] font-bold uppercase tracking-wider text-amber-900">
                                    Safe template - not AI-generated
                                  </p>
                                  <p className="text-xs text-amber-800 leading-relaxed mt-1">
                                    Live generation could not produce a grounded draft for this brief, so
                                    this is the deterministic template built from verified account fields
                                    only. Edit it before sending, or try generating again.
                                  </p>
                                </div>
                              )}

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

                              {/* Card header: type and persona, with Copy / Download HTML */}
                              <div className="flex items-center justify-between gap-3">
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
                              {generatedAsset.content_type === 'branded_emailer' ? (
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
                                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                                  <span className="font-mono font-extrabold text-[10px] text-slate-500 uppercase block">Evidence used</span>
                                  {labels.length === 0 && <div className="text-slate-500">None cited.</div>}
                                  {labels.map(([k, v]) => (
                                    <div key={k}>
                                      <span className="font-mono font-bold text-hp-navy">[{k}]</span>{' '}
                                      <span className="text-slate-700">{String(v).slice(0, 160)}{String(v).length > 160 ? '…' : ''}</span>
                                    </div>
                                  ))}
                                </div>
                                <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                                  <span className="font-mono font-extrabold text-[10px] text-slate-500 uppercase block">HP lines &amp; framing</span>
                                  {generatedAsset.topic && <div className="text-slate-500">Topic: {generatedAsset.topic}</div>}
                                  <div className="font-semibold text-slate-800">
                                    {(g.hp_products || []).length > 0 ? g.hp_products.join(', ') : 'No product named — discovery-led'}
                                  </div>
                                  {g.persona_framing && <div className="italic text-slate-600">{g.persona_framing}</div>}
                                  <div className="text-slate-500">
                                    Grounding: {gr.numbers_checked ?? 0} number(s) checked, {(gr.numbers_rejected || []).length} rejected &middot; {(gr.urls_rejected || []).length} URL(s) stripped
                                  </div>
                                  {generatedAsset.persona?.kind === 'role_proxy' && (
                                    <div className="text-amber-800">Role-type proxy from open hiring — no individual is known to hold this role.</div>
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
                  // Null when the account uploaded no contacts. These used to
                  // default to 23 stakeholders / 5 solutions, so an account with
                  // no data still rendered a confident "Grounded in" line built
                  // from another account's figures. A missing count is now shown
                  // as unavailable rather than invented; `solutions_count` is
                  // gone entirely because nothing ever computed it.
                  const stakeholdersCount: number | null =
                    typeof groundingMeta.stakeholders_count === 'number'
                      ? groundingMeta.stakeholders_count
                      : null;

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
                    const history = [...chatMessages, userMsg].map(m => ({
                      role: m.sender === 'user' ? 'user' : 'assistant',
                      content: m.text,
                    }));

                    setChatMessages(prev => [...prev, userMsg]);
                    setChatInput('');
                    setChatPending(true);

                    try {
                      const res = await api.post(
                        `/accounts/${selectedAccount.id}/widgets/strategy_chat/ask`,
                        chatPersonaId
                          ? { messages: history, mode: 'roleplay', persona_id: chatPersonaId }
                          : { messages: history, mode: 'advisor' }
                      );
                      setChatMessages(prev => [...prev, {
                        id: `asst_${Date.now()}`,
                        sender: 'assistant' as const,
                        text: res.data?.answer || 'No answer was returned.',
                        timestamp: stamp(),
                        citations: res.data?.citations || [],
                        available: res.data?.available !== false,
                        // From the response, not the current selection: a
                        // rejected rehearsal comes back out of character and
                        // must not be labelled as the role having said it.
                        personaTitle: res.data?.available === false
                          ? undefined
                          : res.data?.persona?.title,
                      }]);
                    } catch (err: any) {
                      setChatMessages(prev => [...prev, {
                        id: `asst_${Date.now()}`,
                        sender: 'assistant' as const,
                        text: err?.response?.data?.detail
                          || 'The strategy assistant could not be reached.',
                        timestamp: stamp(),
                        citations: [],
                        available: false,
                      }]);
                    } finally {
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
                        {/* The mode the chat actually runs in.

                            This was a four-option dropdown - Competitive
                            Defender, Executive Pitcher, ABM Campaign Planner -
                            but the selection was never sent: the request
                            hardcodes `mode: 'advisor'`, so three of the four
                            changed nothing when picked. Shown as a label rather
                            than a one-item select, because a chevron invites a
                            click that has nowhere to go.

                            The roleplay personas of Feature 18 are the reason
                            this stays a distinct element. `StrategyChatRequest`
                            already carries `mode`, so restoring a real selector
                            is a UI change and not a contract change. */}
                        <div className="flex items-center gap-2">
                          {/* Role first, name as provenance. "Chief Operating
                              Officer - from Irvan Nr's record" says the seller
                              is preparing for that person WITHOUT framing the
                              dialogue as that person speaking, which is the
                              distinction the whole feature rests on. */}
                          <select
                            value={chatPersonaId}
                            onChange={(e) => {
                              const next = e.target.value;
                              if (next === chatPersonaId) return;
                              // Switching ends the conversation, for the same
                              // reason switching account does: the backend
                              // rewrites a follow-up using the prior turns, so
                              // "and what about the cost of that?" would be
                              // resolved against a different role's answer.
                              if (chatMessages.length > 0 &&
                                  !window.confirm('Switching will clear this conversation. Continue?')) {
                                return;
                              }
                              setChatPersonaId(next);
                              setChatMessages([]);
                              setChatInput('');
                            }}
                            className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs font-extrabold text-slate-800 shadow-xs focus:outline-none focus:ring-2 focus:ring-hp-blue/30"
                          >
                            <option value="">🤖 Strategy Advisor</option>
                            {chatPersonas.length === 0 ? (
                              <option value="" disabled>No contacts on this account</option>
                            ) : chatPersonas.map((p: any) => (
                              <option key={p.persona_id} value={p.persona_id}>
                                🎭 {p.title}{p.name ? ` — from ${p.name}'s record` : ''}
                              </option>
                            ))}
                          </select>
                        </div>

                        <div className="flex items-center gap-1.5 text-slate-500 font-medium">
                          <Info className="w-3.5 h-3.5 text-hp-navy" />
                          <span>Grounded in: <strong className="text-slate-800">{companyName} Intelligence</strong>{stakeholdersCount !== null
                            ? <> &middot; <strong className="text-slate-800">{stakeholdersCount} Stakeholders</strong></>
                            : <> &middot; <span className="text-slate-500 italic">stakeholder count not available</span></>}</span>
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
                                      {msg.available === false && (
                                        <span className="text-[10px] font-bold text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                                          Not in the evidence
                                        </span>
                                      )}
                                    </div>

                                    {/* The answer is plain text with UPPERCASE
                                        headers and numbered lists, so it is
                                        rendered as written rather than parsed
                                        as markdown - except for the evidence
                                        tags, which become footnote markers. */}
                                    <AnswerWithCitations
                                      text={msg.text}
                                      citations={msg.citations || []}
                                      idPrefix={msg.id}
                                    />

                                    {(msg.citations?.length ?? 0) > 0 && (
                                      <div className="pt-2 border-t border-slate-200/80 space-y-1.5">
                                        <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-500 block">
                                          Sources ({msg.citations!.length})
                                        </span>
                                        {msg.citations!.map((c: any, ci: number) => (
                                          <div key={ci} id={`${msg.id}-src-${ci + 1}`}
                                               className="text-[10px] text-slate-600 leading-relaxed scroll-mt-24">
                                            <span className="font-bold text-slate-400 mr-1">{ci + 1}.</span>
                                            {c.source_url ? (
                                              <a href={c.source_url} target="_blank" rel="noopener noreferrer"
                                                 className="text-hp-navy hover:underline inline-flex items-center gap-1">
                                                <FileText className="w-3 h-3 flex-shrink-0" />
                                                <span>{c.publisher || c.filing_label || c.dataset || 'Source'}</span>
                                                <ExternalLink className="w-2.5 h-2.5" />
                                              </a>
                                            ) : (
                                              <span className="font-bold text-slate-500">
                                                {c.filing_label ? `${c.filing_label}${c.page ? ` p.${c.page}` : ''}` : (c.dataset || 'Account evidence')}
                                              </span>
                                            )}
                                            {c.source_text && <span> — {c.source_text}</span>}
                                          </div>
                                        ))}
                                      </div>
                                    )}

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
                                          navigator.clipboard?.writeText(msg.text);
                                          setCopiedMessageId(msg.id);
                                          setTimeout(() => setCopiedMessageId(null), 1500);
                                        }}
                                        className="text-[10px] font-bold text-slate-500 hover:text-hp-navy inline-flex items-center gap-1 transition"
                                      >
                                        <FileText className="w-3 h-3" />
                                        {copiedMessageId === msg.id ? 'Copied' : 'Copy'}
                                      </button>
                                      <a
                                        href={`mailto:?subject=${encodeURIComponent(`${companyName} — ABM strategy notes`)}&body=${encodeURIComponent(msg.text)}`}
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
                              <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                                {widget.data_classification === 'deterministic' ? 'Dataset Not Uploaded / Empty' : 'Derived / Inferred Placeholder'}
                              </h4>
                              <p className="text-[11px] text-slate-500 max-w-sm mx-auto leading-relaxed">
                                {widget.data_classification === 'deterministic'
                                  ? `No raw CSV data uploaded yet for source datasets (${widget.source_datasets.join(', ')}). Upload datasets in Admin Data tab.`
                                  : `Derived outputs for ${widget.widget_name} are not built yet.`}
                              </p>
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
    </ProtectedRoute>
  );
}
