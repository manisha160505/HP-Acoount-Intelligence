'use client';

import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { ProtectedRoute } from '@/components/common/ProtectedRoute';
import { useAuth } from '@/providers/AuthProvider';
import api from '@/services/api';
import { CompanyAccount } from '@/types/account';
import { 
  WidgetResponse, 
  WidgetClassification 
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
  TrendingUp,
  Sparkles,
  Calculator,
  Binary,
  Maximize2,
  ChevronLeft,
  MapPin,
  Globe,
  User,
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
  ShieldCheck,
  UserCheck,
  CheckCircle2
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
      { key: 'intent_demand_signals', label: 'Intent & Demand Signals', subtitle: 'HP-category & topic-level buying intent', description: 'HP-category & topic-level buying intent', iconName: 'TrendingUp' },
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

interface PersonaArchetype {
  id: string;
  label: string;
  short_title: string;
  department: string;
  seniority: string;
  buying_role: string;
  default_contact_match: string;
  matched_title: string;
  matched_dept: string;
  email: string;
  phone: string;
  linkedin: string;
  receptivity: string;
  primary_concern: string;
  objection_point: string;
}

const PERSONA_ARCHETYPES: PersonaArchetype[] = [
  {
    id: "ciso",
    label: "CISO — Chief Information Security Officer",
    short_title: "Chief Information Security Officer",
    department: "Information Security / Risk Advisory",
    seniority: "C-Level / Director",
    buying_role: "Security Decision Maker",
    default_contact_match: "Hesalonika Fransisca",
    matched_title: "Head of Governance & Strategy - Risk Advisory",
    matched_dept: "Risk Advisory & IT Audit",
    email: "hesalonika.fransisca@ai.astra.co.id",
    phone: "+62 21 5084 7777",
    linkedin: "linkedin.com/in/hesalonika-fransisca",
    receptivity: "High caution, technical defensibility required",
    primary_concern: "Enterprise threat surface, firmware vulnerability, data residency",
    objection_point: "Endpoint agent bloat, third-party supply chain risk"
  },
  {
    id: "cio",
    label: "CIO — Chief Information Officer",
    short_title: "Chief Information Officer",
    department: "Executive IT / CIO Office",
    seniority: "C-Level / Executive",
    buying_role: "Executive IT Decision Maker",
    default_contact_match: "Alwin Hadikusuma",
    matched_title: "CIO Office",
    matched_dept: "Executive Information Technology",
    email: "alwin.hadikusuma@ai.astra.co.id",
    phone: "+62 812 9398 6658",
    linkedin: "linkedin.com/in/alwin-hadikusuma",
    receptivity: "Strategic business outcome, modernization velocity",
    primary_concern: "Workforce productivity, hybrid enablement, fleet TCO",
    objection_point: "Disruption to ongoing enterprise digital transformation"
  },
  {
    id: "cto",
    label: "CTO — Chief Technology Officer",
    short_title: "Chief Technology Officer",
    department: "Technology Development & Engineering",
    seniority: "C-Level / Head",
    buying_role: "Technology Decision Maker",
    default_contact_match: "Mochamad (ivan) Triawan",
    matched_title: "Department Head - Technology Development and BI Insight",
    matched_dept: "Technology Development & Intelligence",
    email: "m.triawan@ai.astra.co.id",
    phone: "+62 21 6530 0000",
    linkedin: "linkedin.com/in/mochamad-triawan",
    receptivity: "AI compute capabilities, developer performance",
    primary_concern: "Compute bottlenecks for AI/ML workloads, architecture scale",
    objection_point: "Standardization on existing cloud/workstation vendors"
  },
  {
    id: "vp_infra",
    label: "VP Infrastructure — VP of Infrastructure & Infrastructure Security",
    short_title: "VP of Infrastructure & Operations",
    department: "IT Infrastructure / Cloud Operations",
    seniority: "Director / Head",
    buying_role: "Infrastructure Lead",
    default_contact_match: "Ronggo Wicaksono",
    matched_title: "Head of Development Operations",
    matched_dept: "Operations & Cloud Infrastructure",
    email: "ronggo.wicaksono@ai.astra.co.id",
    phone: "+62 21 6530 1111",
    linkedin: "linkedin.com/in/ronggo-wicaksono",
    receptivity: "Deployment automation, management simplicity, uptime",
    primary_concern: "Dual-OS manageability, fleet telemetry, configuration drift",
    objection_point: "Overhead of managing multi-vendor client fleet"
  },
  {
    id: "sec_architect",
    label: "Security Architect — Security Architect / Director of Security",
    short_title: "Security Architect",
    department: "Security Architecture / Risk Governance",
    seniority: "Director / Section Head",
    buying_role: "Security Evaluator",
    default_contact_match: "Hesalonika Fransisca",
    matched_title: "Head of Governance & Strategy Section - Risk Advisory",
    matched_dept: "Risk Advisory & IT Security",
    email: "hesalonika.fransisca@ai.astra.co.id",
    phone: "+62 21 5084 7777",
    linkedin: "linkedin.com/in/hesalonika-fransisca",
    receptivity: "Hardware-enforced isolation, zero-trust endpoint proof",
    primary_concern: "Protection against zero-day browser and email attachments",
    objection_point: "Claims of endpoint security without silicon-level telemetry"
  },
  {
    id: "net_architect",
    label: "Network Architect — Network Architect / Director of Network Engineering",
    short_title: "Network Architect",
    department: "Network Engineering & Cloud Systems",
    seniority: "Director / Section Head",
    buying_role: "Technical Evaluator",
    default_contact_match: "Gatot Sungkono",
    matched_title: "Cloud Operation Section Head",
    matched_dept: "Engineering & Cloud Network Operations",
    email: "gatot.sungkono@ai.astra.co.id",
    phone: "+62 896 3808 8305",
    linkedin: "linkedin.com/in/gatot-sungkono",
    receptivity: "Bandwidth efficiency, remote endpoint connectivity",
    primary_concern: "Video room packet jitter, unified communications latency",
    objection_point: "Complex room configuration and multi-platform SIP routing"
  },
  {
    id: "it_director",
    label: "IT Director — IT Director / Director of Applications",
    short_title: "IT Director / Director of Applications",
    department: "Applications Operations & Software QA",
    seniority: "Director / Department Head",
    buying_role: "Application & Quality Lead",
    default_contact_match: "Franky Wibisono",
    matched_title: "Department Head of Applications Operations & Software Quality Assurance",
    matched_dept: "Engineering & Operations",
    email: "franky.wibisono@ai.astra.co.id",
    phone: "+62 21 6530 2222",
    linkedin: "linkedin.com/in/franky-wibisono",
    receptivity: "End-user satisfaction, QA tooling performance",
    primary_concern: "Application compatibility during hardware transitions",
    objection_point: "Long validation cycles for corporate software builds"
  },
  {
    id: "procurement_finance",
    label: "Procurement/Finance — CFO / VP of Procurement / Finance Executive",
    short_title: "VP of Procurement / Finance Executive",
    department: "IT Project Procurement & Corporate Purchasing",
    seniority: "Director / Head",
    buying_role: "Economic Buyer",
    default_contact_match: "Stephen Dharma",
    matched_title: "Head of Information Technology Project Procurement",
    matched_dept: "IT Procurement",
    email: "stephen.dharma@ai.astra.co.id",
    phone: "+62 21 6530 3333",
    linkedin: "linkedin.com/in/stephen-dharma",
    receptivity: "Commercial terms, lifecycle financing, residual value",
    primary_concern: "Budget overruns, uncompetitive pricing, rigid lease terms",
    objection_point: "Strict procurement tenders and existing supplier SLA locks"
  }
];

const FUNNEL_OBJECTIVES = [
  "Initial Outreach / Cold Prospecting",
  "Follow-up / Re-engagement",
  "Discovery / Meeting Request",
  "Solution Presentation / Pitch",
  "Objection Handling",
  "Executive Briefing",
  "Proposal / Commercial Closing"
];

const CONTENT_FORMATS = [
  "Cold Email",
  "LinkedIn Message / InMail",
  "Sales Call Script / Phone Pitch",
  "Executive Briefing / One-Pager",
  "Follow-up Email"
];

interface ProvenanceEntry {
  field_path: string;
  source: string;
  type: string;
  date: string;
  confidence: string;
  url: string;
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

  // Live Signals Filter Drawer State
  const [isFilterDrawerOpen, setIsFilterDrawerOpen] = useState(false);
  const [signalTypeFilter, setSignalTypeFilter] = useState('ALL');
  const [dateRangeFilter, setDateRangeFilter] = useState('All time');

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

  // Strategy Chat State
  const [chatAdvisorMode, setChatAdvisorMode] = useState<string>('Strategy Advisor');
  const [chatInput, setChatInput] = useState<string>('');
  const [chatMessages, setChatMessages] = useState<Array<{ id: string; sender: 'user' | 'assistant'; text: string; timestamp: string }>>([]);

  // Message Evaluator State
  const [selectedPersonaId, setSelectedPersonaId] = useState<string>('procurement_finance');
  const [selectedObjective, setSelectedObjective] = useState<string>('Initial Outreach / Cold Prospecting');
  const [selectedFormat, setSelectedFormat] = useState<string>('Cold Email');
  const [stimulusText, setStimulusText] = useState<string>('');
  const [copiedRewrite, setCopiedRewrite] = useState<boolean>(false);
  const [evaluatorStep, setEvaluatorStep] = useState<string>('inputs');
  const [evaluatorMode, setEvaluatorMode] = useState<string>('LITE');
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
      { field_path: 'open_job_count', source: 'job_openings.csv (Active record count)', type: 'Job Openings', date: '2026-09-04', confidence: '85%', url: 'data/accounts/' + selectedAccount.id + '/job_openings/job_openings.csv' },
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

              {/* Urgency Score Pill */}
              <div className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-full bg-amber-50 text-amber-800 border border-amber-200/80 text-xs font-bold">
                <span className="text-[11px]">Urgency Score</span>
                <span className="bg-amber-200 text-amber-900 px-1.5 py-0.5 rounded font-mono text-[10px]">Contract TBD</span>
              </div>
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

                  const summaryData = (summaryWidget && summaryWidget.status === 'available' && summaryWidget.data) ? summaryWidget.data : null;
                  const metricsData = (metricsWidget && metricsWidget.status === 'available' && metricsWidget.data) ? metricsWidget.data : null;
                  const hiringData = (hiringWidget && hiringWidget.status === 'available' && hiringWidget.data) ? hiringWidget.data : null;
                  
                  const displayName = summaryData?.company_name || selectedAccount.name;
                  const displayDesc = summaryData?.business_description || `${selectedAccount.name} is an active target company account in the HP Account Intelligence platform. Upload firmographics.csv to view extracted company profile.`;
                  const domainVal = summaryData?.domain || null;
                  const locationVal = summaryData?.hq_location || null;
                  const industryVal = summaryData?.industry_classification || null;
                  const parentVal = summaryData?.ultimate_parent || null;

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

                      {/* Section 3: KEY METRICS GRID (Exact Northstar 5-Column Style with Citation Popovers) */}
                      <div className="space-y-3">
                        <div className="flex items-center space-x-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
                            KEY METRICS
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-blue-50 text-hp-navy border border-blue-200">
                            Verified Datasets Sourced
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                          
                          {/* Card 1: Total Employees */}
                          <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between h-28">
                            <span className="text-[11px] font-semibold text-slate-500 block">Total Employees</span>
                            <span className="text-xl font-extrabold text-slate-900">
                              {metricsData ? metricsData.employee_count : 'N/A'}
                            </span>
                            <div className="flex items-center space-x-1.5 text-[10px] font-bold">
                              <span className="px-1.5 py-0.5 bg-blue-50 text-hp-navy rounded font-bold border border-blue-200">T1</span>
                              <button
                                type="button"
                                onClick={() => setActiveMetricPopover(activeMetricPopover === 'emp' ? null : 'emp')}
                                className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-50/80 hover:bg-blue-100 text-hp-navy border border-blue-200/80 font-bold transition"
                              >
                                <FileText className="w-3 h-3 text-hp-navy" />
                                <span>Firmographics</span>
                                <ExternalLink className="w-2.5 h-2.5 ml-0.5" />
                              </button>
                            </div>

                            {/* Citation Popover Modal */}
                            {activeMetricPopover === 'emp' && (
                              <div className="absolute left-0 bottom-full mb-2 w-72 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs">
                                <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                    PRIMARY SOURCE · FIRMOGRAPHICS
                                  </span>
                                  <button onClick={() => setActiveMetricPopover(null)} className="text-slate-400 hover:text-slate-600">
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <p className="text-slate-700 italic font-serif leading-relaxed text-[11px] mb-2">
                                  “Number Of Employees Range: {metricsData ? metricsData.employee_count : '10001+'} extracted from 1_firmographics.csv for {displayName}.”
                                </p>
                                <a
                                  href={getDownloadUrl('firmographics')}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-hp-navy font-bold text-[10px] inline-flex items-center hover:underline"
                                >
                                  <ExternalLink className="w-3 h-3 mr-1" />
                                  <span>Open source file</span>
                                </a>
                              </div>
                            )}
                          </div>

                          {/* Card 2: Yearly Revenue Range */}
                          <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between h-28">
                            <span className="text-[11px] font-semibold text-slate-500 block">Yearly Revenue Range</span>
                            <span className="text-xl font-extrabold text-emerald-700">
                              {metricsData ? metricsData.revenue : 'N/A'}
                            </span>
                            <div className="flex items-center space-x-1.5 text-[10px] font-bold">
                              <span className="px-1.5 py-0.5 bg-blue-50 text-hp-navy rounded font-bold border border-blue-200">T1</span>
                              <button
                                type="button"
                                onClick={() => setActiveMetricPopover(activeMetricPopover === 'rev' ? null : 'rev')}
                                className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-50/80 hover:bg-blue-100 text-hp-navy border border-blue-200/80 font-bold transition"
                              >
                                <FileText className="w-3 h-3 text-hp-navy" />
                                <span>Firmographics</span>
                                <ExternalLink className="w-2.5 h-2.5 ml-0.5" />
                              </button>
                            </div>

                            {/* Citation Popover Modal */}
                            {activeMetricPopover === 'rev' && (
                              <div className="absolute left-0 bottom-full mb-2 w-72 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs">
                                <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                    PRIMARY SOURCE · FIRMOGRAPHICS
                                  </span>
                                  <button onClick={() => setActiveMetricPopover(null)} className="text-slate-400 hover:text-slate-600">
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <p className="text-slate-700 italic font-serif leading-relaxed text-[11px] mb-2">
                                  “Yearly Revenue Range: {metricsData ? metricsData.revenue : '10B-100B'} extracted from 1_firmographics.csv for {displayName}.”
                                </p>
                                <a
                                  href={getDownloadUrl('firmographics')}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-hp-navy font-bold text-[10px] inline-flex items-center hover:underline"
                                >
                                  <ExternalLink className="w-3 h-3 mr-1" />
                                  <span>Open source file</span>
                                </a>
                              </div>
                            )}
                          </div>

                          {/* Card 3: Active Open Job Postings */}
                          <div className="relative bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between h-28">
                            <span className="text-[11px] font-semibold text-slate-500 block">Active Open Job Postings</span>
                            <span className="text-xl font-extrabold text-hp-navy">
                              {hiringData ? `${hiringData.open_job_count} roles` : 'N/A'}
                            </span>
                            <div className="flex items-center space-x-1.5 text-[10px] font-bold">
                              <span className="px-1.5 py-0.5 bg-blue-50 text-hp-navy rounded font-bold border border-blue-200">T1</span>
                              <button
                                type="button"
                                onClick={() => setActiveMetricPopover(activeMetricPopover === 'jobs' ? null : 'jobs')}
                                className="inline-flex items-center space-x-1 px-2 py-0.5 rounded bg-blue-50/80 hover:bg-blue-100 text-hp-navy border border-blue-200/80 font-bold transition"
                              >
                                <FileText className="w-3 h-3 text-hp-navy" />
                                <span>Job Openings</span>
                                <ExternalLink className="w-2.5 h-2.5 ml-0.5" />
                              </button>
                            </div>

                            {/* Citation Popover Modal */}
                            {activeMetricPopover === 'jobs' && (
                              <div className="absolute left-0 bottom-full mb-2 w-72 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs">
                                <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                    PRIMARY SOURCE · JOB OPENINGS
                                  </span>
                                  <button onClick={() => setActiveMetricPopover(null)} className="text-slate-400 hover:text-slate-600">
                                    <X className="w-3.5 h-3.5" />
                                  </button>
                                </div>
                                <p className="text-slate-700 italic font-serif leading-relaxed text-[11px] mb-2">
                                  “{hiringData ? hiringData.open_job_count : '100'} active open job postings recorded in job_openings.csv for {displayName}.”
                                </p>
                                <a
                                  href={getDownloadUrl('job_openings')}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="text-hp-navy font-bold text-[10px] inline-flex items-center hover:underline"
                                >
                                  <ExternalLink className="w-3 h-3 mr-1" />
                                  <span>Open source file</span>
                                </a>
                              </div>
                            )}
                          </div>

                          {/* Card 4: Revenue Growth (Northstar Metric Placeholder) */}
                          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between h-28 opacity-80">
                            <span className="text-[11px] font-semibold text-slate-500 block">Revenue Growth (YoY)</span>
                            <span className="text-sm font-bold text-slate-400 italic">Derived TBD</span>
                            <div className="flex items-center space-x-1 text-[10px] font-bold text-slate-400">
                              <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-600 border border-slate-200">T1</span>
                              <span>Future Calc</span>
                            </div>
                          </div>

                          {/* Card 5: Annual ICT Spend (Northstar Metric Placeholder) */}
                          <div className="bg-white p-4 rounded-2xl border border-slate-200 shadow-xs flex flex-col justify-between h-28 opacity-80">
                            <span className="text-[11px] font-semibold text-slate-500 block">Est. Annual ICT Spend</span>
                            <span className="text-sm font-bold text-slate-400 italic">Derived TBD</span>
                            <div className="flex items-center space-x-1 text-[10px] font-bold text-slate-400">
                              <span className="px-1.5 py-0.5 bg-slate-100 rounded text-slate-600 border border-slate-200">T2</span>
                              <span>Future Calc</span>
                            </div>
                          </div>

                        </div>
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
                            <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                              Derived Contract TBD
                            </span>
                          </div>

                          <div className="flex flex-col sm:flex-row items-center gap-6">
                            <div className="w-24 h-24 rounded-full border-4 border-amber-400 flex flex-col items-center justify-center flex-shrink-0 bg-amber-50/50 shadow-inner">
                              <span className="text-xl font-extrabold text-slate-800">TBD</span>
                              <span className="text-[10px] font-bold text-slate-400">/100</span>
                            </div>

                            <div className="flex-1 w-full space-y-3 text-xs">
                              {[
                                {
                                  id: 'fleet_refresh',
                                  label: 'Fleet-Refresh & Dual-OS',
                                  scoreText: 'TBD',
                                  progressPct: '0%',
                                  barColor: 'bg-slate-300',
                                  rationale: `Fleet-refresh & dual-OS driver calculation: TBD for future runtime calculation. Current workforce size: ${metricsData ? metricsData.employee_count : 'Dataset not uploaded'}.`
                                },
                                {
                                  id: 'ai_catalysts',
                                  label: 'AI / Workstation Catalysts',
                                  scoreText: 'TBD',
                                  progressPct: '0%',
                                  barColor: 'bg-slate-300',
                                  rationale: `AI/workstation catalysts driver calculation: TBD for future runtime calculation.`
                                },
                                {
                                  id: 'hiring_velocity',
                                  label: 'Hiring Velocity',
                                  scoreText: hiringData ? `${hiringData.open_job_count} open roles` : 'TBD',
                                  progressPct: hiringData ? '80%' : '0%',
                                  barColor: hiringData ? 'bg-hp-navy' : 'bg-slate-300',
                                  rationale: `Hiring velocity signal: ${hiringData ? `${hiringData.open_job_count} active open job postings extracted from job_openings.csv.` : 'No job openings dataset uploaded yet.'}`
                                },
                                {
                                  id: 'expansion_triggers',
                                  label: 'Expansion / Print Triggers',
                                  scoreText: 'TBD',
                                  progressPct: '0%',
                                  barColor: 'bg-slate-300',
                                  rationale: `Expansion / print triggers driver calculation: TBD for future runtime calculation.`
                                },
                                {
                                  id: 'intent_intensity',
                                  label: 'Intent Intensity',
                                  scoreText: 'TBD',
                                  progressPct: '0%',
                                  barColor: 'bg-slate-300',
                                  rationale: `Intent intensity driver calculation: TBD for future runtime calculation.`
                                }
                              ].map((driver) => (
                                <div key={driver.id} className="relative">
                                  <div className="flex justify-between items-center font-bold text-slate-700 text-[11px] mb-1">
                                    <div className="flex items-center space-x-1.5">
                                      <span>{driver.label}</span>
                                      
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
                            </div>
                          </div>
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
                                <span className="text-base font-extrabold text-slate-900 block">5</span>
                                <span className="text-[10px] text-slate-500 font-medium">Solution Narratives</span>
                              </div>
                            </div>

                            <div className="flex items-center space-x-3 p-2.5 rounded-xl bg-slate-50">
                              <div className="p-2 bg-purple-100 text-purple-700 rounded-lg">
                                <Users className="w-4 h-4" />
                              </div>
                              <div>
                                 <span className="text-base font-extrabold text-slate-900 block">
                                   {summaryData?.stakeholders_mapped_count ?? 23}
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
                                  {hiringData ? hiringData.open_job_count : '0'}
                                </span>
                                <span className="text-[10px] text-slate-500 font-medium">Active Urgent Signals</span>
                              </div>
                            </div>
                          </div>
                        </div>

                      </div>

                      {/* Section 5: STRATEGIC PRIORITIES (Catalyst Cards Placeholder) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Target className="w-4 h-4 text-hp-navy" />
                            <span>STRATEGIC PRIORITIES & CATALYSTS</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-50 text-purple-800 border border-purple-200">
                            Inferred Contract TBD
                          </span>
                        </div>

                        <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-8 text-center space-y-2">
                          <div className="w-10 h-10 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center mx-auto">
                            <Sparkles className="w-5 h-5" />
                          </div>
                          <h4 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                            Strategic Priority Catalyst Generation Placeholder
                          </h4>
                          <p className="text-[11px] text-slate-500 max-w-md mx-auto leading-relaxed">
                            AI-synthesized strategic catalysts, evidence claims, and filing citations for <strong className="text-slate-800">{displayName}</strong> will be generated in Step 7.2+.
                          </p>
                        </div>
                      </div>

                    </div>
                  );
                })()}

                {/* Live Signals View (Feature Key: recent_news_signals) */}
                {activeFeatureKey === 'recent_news_signals' && (() => {
                  const feedWidget = widgets.find(w => w.widget_key === 'news_signals_feed');
                  const feedData = (feedWidget && feedWidget.status === 'available' && feedWidget.data) ? feedWidget.data : null;
                  const signals = feedData?.signals || [];

                  const getCleanCategoryBadge = (rawType: string) => {
                    const typeClean = (rawType || '').toLowerCase().trim();
                    if (['launch', 'launches', 'is_developing', 'product', 'technology'].includes(typeClean)) {
                      return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">Technology</span>;
                    }
                    if (['partners_with', 'leadership', 'attends_event', 'strategic'].includes(typeClean)) {
                      return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">Strategic</span>;
                    }
                    if (['has_earnings', 'financing_type', 'funding', 'invests_into', 'financial'].includes(typeClean)) {
                      return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">Financial</span>;
                    }
                    if (['identified_as_competitor_of', 'competitive'].includes(typeClean)) {
                      return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">Competitive</span>;
                    }
                    if (['acquires', 'sells_assets_to', 'm&a'].includes(typeClean)) {
                      return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-700 border border-red-200">Strategic M&A</span>;
                    }
                    return <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200 capitalize">{typeClean || 'Signal'}</span>;
                  };

                  const filteredSignals = signals.filter((sig: any) => {
                    // 1. Signal Type Filter
                    if (signalTypeFilter !== 'ALL') {
                      const rawT = (sig.event_type || '').toLowerCase();
                      if (signalTypeFilter === 'Technology' && !['launch', 'launches', 'is_developing', 'product', 'technology'].includes(rawT)) return false;
                      if (signalTypeFilter === 'Strategic' && !['partners_with', 'leadership', 'attends_event', 'strategic', 'acquires', 'sells_assets_to'].includes(rawT)) return false;
                      if (signalTypeFilter === 'Financial' && !['has_earnings', 'financing_type', 'funding', 'invests_into', 'financial'].includes(rawT)) return false;
                      if (signalTypeFilter === 'Competitive' && !['identified_as_competitor_of', 'competitive'].includes(rawT)) return false;
                    }

                    // 2. Date Range Filter
                    if (dateRangeFilter !== 'All time' && sig.event_date && sig.event_date !== 'N/A') {
                      try {
                        const sigTime = new Date(sig.event_date).getTime();
                        const validTimes = signals.map((s: any) => (s.event_date && s.event_date !== 'N/A') ? new Date(s.event_date).getTime() : 0).filter((t: number) => !isNaN(t) && t > 0);
                        const maxTime = validTimes.length > 0 ? Math.max(...validTimes) : Date.now();
                        
                        const diffDays = (maxTime - sigTime) / (1000 * 60 * 60 * 24);
                        if (dateRangeFilter === 'Last 7 days' && diffDays > 7) return false;
                        if (dateRangeFilter === 'Last 30 days' && diffDays > 30) return false;
                        if (dateRangeFilter === 'Last 90 days' && diffDays > 90) return false;
                      } catch (e) {
                        // Keep if date parse fails
                      }
                    }

                    return true;
                  });

                  return (
                    <div className="space-y-6">
                      
                      {/* Header Bar */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Newspaper className="w-5 h-5 text-hp-navy" />
                            <span>Live Signals</span>
                          </h2>
                          <p className="text-xs text-slate-500 mt-0.5">
                            Real-time intelligence triggers for {selectedAccount.name}
                          </p>
                        </div>

                        <div className="flex items-center space-x-3">
                          <span className="px-3 py-1 bg-white border border-slate-200 shadow-xs rounded-full text-slate-700 font-bold text-xs">
                            {filteredSignals.length} Signals
                          </span>

                          <button
                            type="button"
                            onClick={() => setIsFilterDrawerOpen(!isFilterDrawerOpen)}
                            className={`inline-flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl border text-xs font-bold transition shadow-xs ${
                              isFilterDrawerOpen
                                ? 'bg-hp-navy text-white border-hp-navy shadow-sm'
                                : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'
                            }`}
                          >
                            <Filter className="w-3.5 h-3.5" />
                            <span>Filters</span>
                            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isFilterDrawerOpen ? 'rotate-180' : ''}`} />
                          </button>
                        </div>
                      </div>

                      {/* Expanded Interactive Filter Drawer (Matching Image 1) */}
                      {isFilterDrawerOpen && (
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-5 animate-fade-in text-xs font-medium">
                          {/* SIGNAL TYPE */}
                          <div className="space-y-2">
                            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 block">
                              SIGNAL TYPE
                            </span>
                            <div className="flex flex-wrap items-center gap-2">
                              {['ALL', 'Financial', 'Technology', 'Strategic', 'Competitive'].map((st) => (
                                <button
                                  key={st}
                                  type="button"
                                  onClick={() => setSignalTypeFilter(st)}
                                  className={`px-3 py-1 rounded-full border font-bold text-xs transition ${
                                    signalTypeFilter === st
                                      ? 'bg-hp-navy text-white border-hp-navy shadow-xs'
                                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                                  }`}
                                >
                                  {st}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* MINIMUM SCORE */}
                          <div className="space-y-2">
                            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 block">
                              MINIMUM SCORE (Derived TBD)
                            </span>
                            <div className="flex flex-wrap items-center gap-2">
                              {['All', '4+', '6+', '8+'].map((score) => (
                                <button
                                  key={score}
                                  type="button"
                                  className="px-3 py-1 rounded-lg border font-bold text-xs bg-slate-50 text-slate-400 border-slate-200 cursor-not-allowed"
                                  title="Score filtering will be enabled when derived scoring runs in Step 8"
                                >
                                  {score}
                                </button>
                              ))}
                            </div>
                          </div>

                          {/* DATE RANGE */}
                          <div className="space-y-2">
                            <span className="text-[10px] font-extrabold uppercase tracking-wider text-slate-400 block">
                              DATE RANGE
                            </span>
                            <div className="flex flex-wrap items-center gap-2">
                              {['All time', 'Last 7 days', 'Last 30 days', 'Last 90 days'].map((range) => (
                                <button
                                  key={range}
                                  type="button"
                                  onClick={() => setDateRangeFilter(range)}
                                  className={`px-3 py-1 rounded-lg border font-bold text-xs transition ${
                                    dateRangeFilter === range
                                      ? 'bg-hp-navy text-white border-hp-navy shadow-xs'
                                      : 'bg-slate-50 text-slate-700 border-slate-200 hover:bg-slate-100'
                                  }`}
                                >
                                  {range}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Signals Stream (Full Width Cards) */}
                      {filteredSignals.length === 0 ? (
                        <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm">
                          <Newspaper className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                          <h3 className="text-base font-bold text-slate-800">No Live Signals Match Filter</h3>
                          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                            Try adjusting or resetting the signal type and date range filters above.
                          </p>
                        </div>
                      ) : (
                        <div className="space-y-4">
                          {filteredSignals.map((sig: any, idx: number) => (
                            <div key={idx} className="bg-white rounded-2xl p-6 border border-slate-200/90 shadow-sm space-y-3.5 hover:border-slate-300 transition">
                              
                              {/* Top Meta Row */}
                              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  {getCleanCategoryBadge(sig.event_type)}
                                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                    Impact: Derived TBD
                                  </span>
                                  <span className="text-xs font-mono text-slate-400">
                                    {sig.event_date || 'Date N/A'}
                                  </span>
                                </div>

                                <div className="flex items-center space-x-1.5">
                                  <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                                    Relevance: Derived TBD
                                  </span>
                                </div>
                              </div>

                              {/* Headline */}
                              <div>
                                <span className="text-[11px] font-extrabold text-slate-400 uppercase tracking-wider block mb-1">
                                  WHAT'S NEW:
                                </span>
                                <h3 className="text-sm font-extrabold text-slate-900 leading-snug">
                                  {sig.event_headline}
                                </h3>
                              </div>

                              {/* Implication for HP Box */}
                              <div className="bg-blue-50/70 border border-blue-200/80 rounded-xl p-3.5 text-xs text-blue-950 space-y-1">
                                <div className="flex items-center space-x-2">
                                  <span className="font-extrabold text-hp-navy text-[11px]">
                                    Implication for HP:
                                  </span>
                                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 border border-purple-200">
                                    Inferred TBD
                                  </span>
                                </div>
                                <p className="text-[11px] leading-relaxed text-slate-500 italic">
                                  AI-synthesized HP sales angle and portfolio implication TBD for future runtime generation.
                                </p>
                              </div>

                              {/* Article Excerpt Paragraph */}
                              {sig.article_detail && (
                                <p className="text-xs text-slate-600 leading-relaxed font-normal pt-1">
                                  {sig.article_detail}
                                </p>
                              )}

                              {/* Source Button */}
                              {sig.source_url ? (
                                <div className="pt-1">
                                  <a
                                    href={sig.source_url}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200 transition"
                                  >
                                    <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600" />
                                    <span className="truncate max-w-xs">{selectedAccount.name} Source Article</span>
                                    <ExternalLink className="w-3 h-3 ml-0.5" />
                                  </a>
                                </div>
                              ) : (
                                <div className="pt-1 text-[11px] text-slate-400 font-medium italic">
                                  Source: Source B News Events dataset (No external article URL provided)
                                </div>
                              )}

                            </div>
                          ))}
                        </div>
                      )}

                    </div>
                  );
                })()}

                {/* Intent & Demand Signals View (Feature Key: intent_demand_signals) */}
                {activeFeatureKey === 'intent_demand_signals' && (() => {
                  const topicsWidget = widgets.find(w => w.widget_key === 'intent_topics_table');
                  const hiringWidget = widgets.find(w => w.widget_key === 'intent_hiring_demand');

                  const topicsData = (topicsWidget && topicsWidget.status === 'available' && topicsWidget.data) ? topicsWidget.data : null;
                  const hiringData = (hiringWidget && hiringWidget.status === 'available' && hiringWidget.data) ? hiringWidget.data : null;

                  const topicsList = topicsData?.topics || [];
                  const openJobCount = hiringData?.open_job_count || 0;
                  const seniorityBreakdown = hiringData?.seniority_breakdown || {};

                  const filteredTopics = topicsList.filter((t: any) => {
                    if (intentSearch && !t.topic_name.toLowerCase().includes(intentSearch.toLowerCase().trim())) {
                      return false;
                    }
                    if (intentScoreFilter === '70+' && t.composite_score < 70) return false;
                    if (intentScoreFilter === '85+' && t.composite_score < 85) return false;
                    return true;
                  });

                  // Categorize topics into Northstar Domain Groups
                  const aiGroup = filteredTopics.filter((t: any) => 
                    ['ai', 'machine learning', 'data insights', 'analytics', 'chatgpt', 'openai'].some(k => t.topic_name.toLowerCase().includes(k))
                  );
                  const secGroup = filteredTopics.filter((t: any) => 
                    ['security', 'privacy', 'authentication', 'tokenization', 'protection', 'aml', 'risk'].some(k => t.topic_name.toLowerCase().includes(k))
                  );
                  const finGroup = filteredTopics.filter((t: any) => 
                    ['financial', 'visa', 'mastercard', 'mortgage', 'hedging', 'trading', 'investing', 'loan', 'credit', 'payment'].some(k => t.topic_name.toLowerCase().includes(k))
                  );
                  const collabGroup = filteredTopics.filter((t: any) => 
                    ['workplace', 'teams', 'collaboration', 'working', 'hr', 'recruitment', 'talent', 'staffing', 'leadership', 'training', 'employee'].some(k => t.topic_name.toLowerCase().includes(k))
                  );
                  const cloudGroup = filteredTopics.filter((t: any) => 
                    ['cloud', 'data center', 'server', 'postgres', 'aws', 'network', 'hardware', 'ai chips'].some(k => t.topic_name.toLowerCase().includes(k))
                  );

                  const categorizedKeys = new Set([...aiGroup, ...secGroup, ...finGroup, ...collabGroup, ...cloudGroup].map(t => t.topic_name));
                  const otherGroup = filteredTopics.filter((t: any) => !categorizedKeys.has(t.topic_name));

                  const topChartTopics = filteredTopics.slice(0, 10);

                  return (
                    <div className="space-y-6">
                      
                      {/* Header Banner (Matching Image 1) */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <TrendingUp className="w-5 h-5 text-hp-navy" />
                            <span>Intent & Demand Signals</span>
                          </h2>
                          <p className="text-xs text-slate-500 mt-0.5">
                            5 HP category signals • {topicsList.length} broader Bombora intent topics for {selectedAccount?.name}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                          <span className="px-3 py-1 bg-[#0096D6]/10 text-hp-navy border border-[#0096D6]/20 rounded-full">
                            Avg HP-category intent: Derived TBD
                          </span>
                          <span className="px-3 py-1 bg-slate-100 text-slate-600 border border-slate-200 rounded-full font-mono text-[11px]">
                            Powered by Bombora
                          </span>
                        </div>
                      </div>

                      {/* "So What for HP" Blue Insights Banner */}
                      <div className="bg-blue-50/80 border border-blue-200/90 rounded-2xl p-6 text-xs text-blue-950 space-y-2 shadow-xs">
                        <div className="flex items-center justify-between border-b border-blue-200/60 pb-2">
                          <h3 className="text-xs font-black uppercase tracking-wider text-hp-navy flex items-center gap-2">
                            <Sparkles className="w-4 h-4 text-hp-navy" />
                            <span>SO WHAT FOR HP</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-100 text-purple-800 border border-purple-200">
                            Inferred TBD
                          </span>
                        </div>
                        <p className="text-[11px] leading-relaxed text-slate-700 font-medium">
                          AI-synthesized intent topic categorization, low-relevance topic filtering, and HP play alignment TBD for future runtime generation in Step 8.
                        </p>
                      </div>

                      {/* Section 1: HP Category Intent Scores Vertical Bar Chart (Matching Image 1) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Layers className="w-4 h-4 text-hp-navy" />
                            <span>HP CATEGORY INTENT SCORES</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                            Derived Contract TBD
                          </span>
                        </div>

                        <div className="flex items-end space-x-8 h-48 pt-6 pb-2 px-8 border-b border-slate-200 relative">
                          <div className="absolute left-2 top-2 bottom-6 flex flex-col justify-between text-[10px] font-mono text-slate-400">
                            <span>100</span>
                            <span>75</span>
                            <span>50</span>
                            <span>25</span>
                            <span>0</span>
                          </div>

                          {[
                            { name: 'Print', color: 'bg-amber-500' },
                            { name: '3D', color: 'bg-pink-500' },
                            { name: 'PC', color: 'bg-hp-navy' },
                            { name: 'Workstation', color: 'bg-indigo-600' },
                            { name: 'Poly', color: 'bg-emerald-500' }
                          ].map((cat) => (
                            <div key={cat.name} className="flex-1 flex flex-col items-center h-full justify-end group">
                              <span className="text-[10px] font-bold text-slate-400 mb-1 opacity-0 group-hover:opacity-100 transition">TBD</span>
                              <div className="w-12 bg-slate-100 rounded-t-lg h-full flex items-end justify-center border border-dashed border-slate-200 relative">
                                <div className={`w-full ${cat.color} rounded-t-lg h-2 transition-all duration-300 opacity-60`}></div>
                              </div>
                              <span className="text-xs font-bold text-slate-700 mt-2">{cat.name}</span>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Section 2: 5 HP Category Play Cards Grid */}
                      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
                        {[
                          { 
                            name: 'Print', 
                            play: 'HP Enterprise Printing & Managed Print Services', 
                            keywords: ['launches', 'digitization initiative', 'cost reduction'] 
                          },
                          { 
                            name: '3D', 
                            play: 'HP Multi Jet Fusion (3D)', 
                            keywords: ['manufacturing innovation', 'is developing', 'supply chain'] 
                          },
                          { 
                            name: 'PC', 
                            play: 'HP Elite & Pro PCs', 
                            keywords: ['fleet management', 'remote work expansion', 'hardware refresh'] 
                          },
                          { 
                            name: 'Workstation', 
                            play: 'Z by HP Workstations', 
                            keywords: ['AI/ML expansion', 'data science growth', 'engineering'] 
                          },
                          { 
                            name: 'Poly', 
                            play: 'Poly Collaboration Hardware', 
                            keywords: ['UC/collaboration', 'Zoom Rooms deployment', 'conferencing'] 
                          }
                        ].map((cat) => (
                          <div key={cat.name} className="bg-white p-5 rounded-2xl border border-slate-200 shadow-xs space-y-3.5 flex flex-col justify-between hover:border-slate-300 transition">
                            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
                              <span className="text-sm font-extrabold text-slate-900">{cat.name}</span>
                              <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200">
                                Derived TBD
                              </span>
                            </div>

                            <div>
                              <span className="text-2xl font-black text-slate-400 block">TBD</span>
                              <span className="text-[10px] text-slate-400 font-bold block">/100 Intent Score</span>
                            </div>

                            <div className="space-y-1.5 pt-1 border-t border-slate-100 text-[10px]">
                              <span className="text-slate-400 font-bold uppercase block">SIGNAL TOPICS</span>
                              <div className="flex flex-wrap gap-1">
                                {cat.keywords.map((kw, i) => (
                                  <span key={i} className="px-1.5 py-0.5 bg-slate-100 text-slate-700 rounded font-medium">
                                    {kw}
                                  </span>
                                ))}
                              </div>
                            </div>

                            <div className="space-y-1 pt-1 border-t border-slate-100 text-[10px]">
                              <span className="text-slate-400 font-bold uppercase block">MAPPED HP PLAY</span>
                              <span className="font-bold text-hp-navy block leading-tight">{cat.play}</span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {/* Section 3: Broader Intent Topics Section (Horizontal Bar Chart + Accordions matching Images 1 & 2) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-6">
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-100 pb-4">
                          <div>
                            <h3 className="text-sm font-extrabold uppercase tracking-wider text-slate-800 flex items-center gap-2">
                              <Database className="w-4 h-4 text-hp-navy" />
                              <span>BROADER INTENT TOPICS ({topicsList.length})</span>
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Extracted directly from Bombora intent score export (11_intent_score.csv)
                            </p>
                          </div>

                          {/* Filter Bar */}
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
                                    intentScoreFilter === sc
                                      ? 'bg-hp-navy text-white shadow-xs'
                                      : 'text-slate-600 hover:text-slate-900'
                                  }`}
                                >
                                  {sc}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>

                        {/* Top Signal Topics Horizontal Bar Chart (Matching Image 1) */}
                        {topChartTopics.length > 0 && (
                          <div className="space-y-3 bg-slate-50/60 p-5 rounded-2xl border border-slate-200/80">
                            <span className="text-[11px] font-bold text-slate-500 block uppercase tracking-wider">
                              Top Signal Topics (Ranked by Composite Score)
                            </span>

                            <div className="space-y-2 pt-2">
                              {topChartTopics.map((item: any, i: number) => (
                                <div key={i} className="flex items-center space-x-3 text-xs relative group">
                                  <span className="w-64 text-right truncate font-bold text-slate-800 text-[11px] flex-shrink-0">
                                    {item.topic_name}
                                  </span>

                                  <div className="flex-1 bg-slate-200 h-5 rounded-md overflow-hidden relative cursor-pointer"
                                       onMouseEnter={() => setHoveredBarTopic({ name: item.topic_name, score: item.composite_score })}
                                       onMouseLeave={() => setHoveredBarTopic(null)}
                                  >
                                    <div 
                                      className="bg-hp-navy h-full rounded-md transition-all duration-300 hover:bg-hp-blue"
                                      style={{ width: `${Math.min(100, Math.max(0, item.composite_score))}%` }}
                                    ></div>
                                  </div>

                                  {/* Hover Tooltip Card (Matching Image 2) */}
                                  {hoveredBarTopic?.name === item.topic_name && (
                                    <div className="absolute right-12 bottom-full mb-1 bg-white border border-slate-300 rounded-xl p-3 shadow-2xl z-50 text-xs font-medium w-64 animate-fade-in pointer-events-none">
                                      <span className="font-extrabold text-slate-900 block truncate">{item.topic_name}</span>
                                      <span className="text-[11px] text-hp-navy font-bold block mt-0.5">
                                        Composite score: {item.composite_score}/100 — Bombora
                                      </span>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>

                            <div className="flex justify-between text-[10px] font-mono text-slate-400 pl-64 pt-2 border-t border-slate-200">
                              <span>0</span>
                              <span>25</span>
                              <span>50</span>
                              <span>75</span>
                              <span>100</span>
                            </div>
                          </div>
                        )}

                        {/* Grouped Intent Topics Category Cards (Matching Images 1 & 2) */}
                        <div className="space-y-4 pt-2">
                          
                          {/* 1. AI & Compute Group */}
                          {aiGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-purple-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-purple-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-purple-100 text-purple-800 border border-purple-200">
                                    AI & Compute
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {aiGroup.length} topics • up to {Math.max(...aiGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {aiGroup.map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-purple-50/50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-purple-600 h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 2. Security & Infrastructure Group */}
                          {secGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-red-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-red-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-red-100 text-red-800 border border-red-200">
                                    Security & Infrastructure
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {secGroup.length} topics • up to {Math.max(...secGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {secGroup.map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-red-50/50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-red-600 h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 3. Financial Services Group */}
                          {finGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-emerald-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-emerald-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200">
                                    Financial Services & Fintech
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {finGroup.length} topics • up to {Math.max(...finGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {finGroup.map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-emerald-50/50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-emerald-600 h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 4. Collaboration & Workplace Group */}
                          {collabGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-green-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-green-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-green-100 text-green-800 border border-green-200">
                                    Collaboration & Workplace
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {collabGroup.length} topics • up to {Math.max(...collabGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {collabGroup.map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-green-50/50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-green-600 h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 5. Cloud & Infrastructure Group */}
                          {cloudGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-blue-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-blue-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-blue-100 text-blue-800 border border-blue-200">
                                    Cloud & Infrastructure
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {cloudGroup.length} topics • up to {Math.max(...cloudGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>
                              </div>

                              <div className="space-y-2">
                                {cloudGroup.map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-blue-50/50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-hp-navy h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 6. Other / Low Relevance Group (With Expand / Collapse Toggle matching Image 2) */}
                          {otherGroup.length > 0 && (
                            <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-xs space-y-3">
                              <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
                                <div className="flex items-center space-x-2">
                                  <span className="px-2.5 py-0.5 rounded-full text-xs font-extrabold bg-slate-100 text-slate-700 border border-slate-200">
                                    Other / Low Relevance
                                  </span>
                                  <span className="text-xs font-semibold text-slate-500">
                                    {otherGroup.length} topics • up to {Math.max(...otherGroup.map((x: any) => x.composite_score))}/100
                                  </span>
                                </div>

                                <button
                                  type="button"
                                  onClick={() => setIsOtherTopicsExpanded(!isOtherTopicsExpanded)}
                                  className="text-xs font-bold text-hp-navy hover:underline flex items-center gap-1"
                                >
                                  <span>{isOtherTopicsExpanded ? 'Collapse' : 'Expand'}</span>
                                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isOtherTopicsExpanded ? 'rotate-180' : ''}`} />
                                </button>
                              </div>

                              <div className="space-y-2">
                                {(isOtherTopicsExpanded ? otherGroup : otherGroup.slice(0, 5)).map((item: any, idx: number) => (
                                  <div key={idx} className="flex items-center justify-between text-xs py-1 px-2 rounded-lg hover:bg-slate-50 transition">
                                    <div className="flex items-center space-x-3 font-semibold text-slate-800 truncate pr-2">
                                      <span className="text-slate-400 font-mono text-[11px] w-5 text-right">{idx + 1}</span>
                                      <span className="capitalize truncate">{item.topic_name}</span>
                                    </div>
                                    <div className="flex items-center space-x-3 flex-shrink-0">
                                      <div className="w-24 bg-slate-200 h-1.5 rounded-full overflow-hidden">
                                        <div className="bg-slate-500 h-1.5 rounded-full" style={{ width: `${item.composite_score}%` }}></div>
                                      </div>
                                      <span className="font-mono font-bold text-slate-900 w-8 text-right">{item.composite_score}</span>
                                      <span className="text-[10px] text-slate-400 font-medium">Bombora</span>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                        </div>
                      </div>

                      {/* Hiring-Linked Demand Signals Section (job_openings.csv Extracted Data) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Users className="w-4 h-4 text-hp-navy" />
                            <span>HIRING-LINKED INTENT DEMAND (job_openings.csv)</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-hp-navy border border-blue-200">
                            Source B job_openings
                          </span>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-medium">
                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-1">
                            <span className="text-slate-400 font-bold uppercase text-[10px] block">Active Job Posting Volume</span>
                            <span className="text-2xl font-extrabold text-slate-900 block">{openJobCount} open roles</span>
                            <span className="text-[11px] text-slate-500">Hiring velocity used as staffing demand signal</span>
                          </div>

                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 space-y-2">
                            <span className="text-slate-400 font-bold uppercase text-[10px] block">Seniority Mix Breakdown</span>
                            <div className="flex flex-wrap gap-2">
                              {Object.entries(seniorityBreakdown).map(([k, v]) => (
                                <span key={k} className="px-2.5 py-1 bg-white rounded-lg border border-slate-200 font-bold text-slate-800 text-[11px]">
                                  <span className="capitalize">{k}</span>: <strong className="text-hp-navy">{String(v)}</strong>
                                </span>
                              ))}
                            </div>
                          </div>
                        </div>
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

                  return (
                    <div className="space-y-6">
                      
                      {/* Header Banner */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Lightbulb className="w-5 h-5 text-hp-navy" />
                            <span>Opportunity Map</span>
                          </h2>
                          <p className="text-xs text-slate-500 mt-0.5">
                            5 HP opportunities mapped for {selectedAccount?.name} — business outcome, HP products, entry path, and evidence in one view.
                          </p>
                        </div>

                        <div className="flex items-center space-x-2 text-xs font-bold">
                          <span className="px-3 py-1 bg-white border border-slate-200 shadow-xs rounded-full text-slate-700">
                            5 HP Plays
                          </span>
                          <span className="px-3 py-1 bg-purple-50 text-purple-800 border border-purple-200 rounded-full">
                            Inferred TBD
                          </span>
                        </div>
                      </div>

                      {/* Section C: Inferred Opportunity Narrative Plays (Clean Inferred TBD Placeholders) */}
                      <div className="space-y-4">
                        <div className="flex items-center justify-between">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700">
                            HP OPPORTUNITY PLAYS (5 HP PRODUCT LINES)
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-50 text-purple-800 border border-purple-200">
                            Inferred Contract TBD
                          </span>
                        </div>

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
                                Priority: Derived TBD
                              </span>
                            </div>

                            <div className="bg-slate-50 border border-dashed border-slate-200 rounded-xl p-6 text-center space-y-2">
                              <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center mx-auto">
                                <Sparkles className="w-4 h-4" />
                              </div>
                              <h5 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                                Opportunity Narrative Play Generation Placeholder
                              </h5>
                              <p className="text-[11px] text-slate-500 max-w-md mx-auto leading-relaxed">
                                AI-synthesized business outcomes, quantified impact projections, recommended product family matches, and target CTA entry paths for <strong className="text-slate-800">{play.name}</strong> will be generated in Step 8.
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>

                    </div>
                  );
                })()}

                {/* Stakeholder Map View (Feature Key: stakeholder_map) */}
                {activeFeatureKey === 'stakeholder_map' && (() => {
                  const gridWidget = widgets.find(w => w.widget_key === 'stakeholder_contacts_grid');
                  const gridData = (gridWidget && gridWidget.status === 'available' && gridWidget.data) ? gridWidget.data : null;

                  const contactsList = gridData?.contacts || [];
                  const deptDist = gridData?.department_distribution || {};
                  const sourceBreakdown = gridData?.source_breakdown || {};

                  const filteredContacts = contactsList.filter((c: any) => {
                    if (stakeholderSearch) {
                      const q = stakeholderSearch.toLowerCase().trim();
                      const matchName = (c.full_name || '').toLowerCase().includes(q);
                      const matchTitle = (c.title || '').toLowerCase().includes(q);
                      const matchDept = (c.department || '').toLowerCase().includes(q);
                      if (!matchName && !matchTitle && !matchDept) return false;
                    }
                    if (stakeholderDeptFilter !== 'ALL') {
                      if ((c.department || 'Unassigned') !== stakeholderDeptFilter) return false;
                    }
                    return true;
                  });

                  return (
                    <div className="space-y-6">
                      
                      {/* Header Banner (Matching Images 1 & 2) */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div>
                          <h2 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Users className="w-5 h-5 text-hp-navy" />
                            <span>Stakeholder Map</span>
                          </h2>
                          <p className="text-xs text-slate-500 mt-0.5">
                            {contactsList.length} active contacts identified for {selectedAccount?.name}
                          </p>
                        </div>

                        <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                          <span className="px-3 py-1 bg-white border border-slate-200 shadow-xs rounded-full text-slate-700">
                            {contactsList.length} Contacts Mapped
                          </span>
                          {sourceBreakdown['Source A'] !== undefined && (
                            <span className="px-3 py-1 bg-blue-50 text-hp-navy border border-blue-200 rounded-full font-mono text-[11px]">
                              Source A: {sourceBreakdown['Source A']} • Apollo: {sourceBreakdown['Apollo']}
                            </span>
                          )}
                        </div>
                      </div>

                      {/* Sub-Tabs View Switcher Bar (Stakeholder Grid vs Entry Path) */}
                      <div className="flex items-center justify-between bg-white p-2.5 rounded-2xl border border-slate-200 shadow-xs text-xs font-bold">
                        <div className="flex items-center space-x-2">
                          <button
                            type="button"
                            onClick={() => setStakeholderSubTab('grid')}
                            className={`px-4 py-2 rounded-xl transition flex items-center space-x-2 ${
                              stakeholderSubTab === 'grid'
                                ? 'bg-hp-navy text-white shadow-xs'
                                : 'bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200'
                            }`}
                          >
                            <Users className="w-4 h-4" />
                            <span>Stakeholder Grid</span>
                          </button>

                          <div className="relative inline-flex items-center">
                            <button
                              type="button"
                              onClick={() => setStakeholderSubTab('entry_path')}
                              className={`px-4 py-2 rounded-xl transition flex items-center space-x-2 ${
                                stakeholderSubTab === 'entry_path'
                                  ? 'bg-hp-navy text-white shadow-xs'
                                  : 'bg-slate-50 text-slate-700 hover:bg-slate-100 border border-slate-200'
                              }`}
                            >
                              <Layers className="w-4 h-4" />
                              <span>Entry Path</span>
                            </button>

                            <button
                              type="button"
                              onClick={() => setIsEntryPathInfoOpen(!isEntryPathInfoOpen)}
                              className="ml-1 text-slate-400 hover:text-hp-navy p-1 rounded-lg"
                              title="Entry Path Information"
                            >
                              <Info className="w-4 h-4" />
                            </button>

                            {/* Entry Path Info Popover Modal (Matching Image 2) */}
                            {isEntryPathInfoOpen && (
                              <div className="absolute left-0 top-full mt-2 w-80 bg-white border border-slate-300 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs font-medium">
                                <div className="flex justify-between items-center border-b border-slate-100 pb-2 mb-2">
                                  <h4 className="font-extrabold text-slate-900 text-xs flex items-center gap-1.5">
                                    <Layers className="w-4 h-4 text-hp-navy" />
                                    <span>Entry Path</span>
                                  </h4>
                                  <button onClick={() => setIsEntryPathInfoOpen(false)} className="text-slate-400 hover:text-slate-600">
                                    <X className="w-4 h-4" />
                                  </button>
                                </div>
                                <p className="text-slate-600 leading-relaxed text-[11px]">
                                  The entry path ranks stakeholders by their receptivity to an initial conversation, their organizational influence over the buying decision, and their alignment with HP's value proposition. Starting with the wrong stakeholder can create political friction or trigger premature gatekeeping. Follow the recommended sequence for the highest probability of gaining access to decision makers.
                                </p>
                              </div>
                            )}
                          </div>
                        </div>

                        <span className="text-[11px] text-slate-400 font-medium hidden sm:inline">
                          Showing active employees only
                        </span>
                      </div>

                      {/* View 1: Stakeholder Grid (Contact Cards) */}
                      {stakeholderSubTab === 'grid' && (
                        <div className="space-y-6">
                          
                          {/* Filter Controls Bar */}
                          <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
                            <div className="relative flex-1 max-w-md">
                              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-2.5" />
                              <input
                                type="text"
                                value={stakeholderSearch}
                                onChange={(e) => setStakeholderSearch(e.target.value)}
                                placeholder="Search name, title, or department..."
                                className="w-full pl-9 pr-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs font-medium focus:outline-none focus:ring-2 focus:ring-hp-navy"
                              />
                            </div>

                            <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                              <Filter className="w-3.5 h-3.5 text-slate-400 mr-1" />
                              <select
                                value={stakeholderDeptFilter}
                                onChange={(e) => setStakeholderDeptFilter(e.target.value)}
                                className="px-3 py-1.5 bg-slate-50 border border-slate-300 rounded-xl text-xs font-bold text-slate-700 focus:outline-none"
                              >
                                <option value="ALL">All Departments ({contactsList.length})</option>
                                {Object.entries(deptDist).map(([dept, count]) => (
                                  <option key={dept} value={dept}>
                                    {dept} ({String(count)})
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>

                          {/* Contacts Cards Grid (Matching Images 1 & 2 Layout) */}
                          {filteredContacts.length === 0 ? (
                            <div className="bg-white rounded-2xl p-12 text-center border border-slate-200 shadow-sm">
                              <Users className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                              <h3 className="text-base font-bold text-slate-800">
                                {contactsList.length === 0 ? 'No Prospect Contacts Uploaded Yet' : 'No Contacts Match Filter'}
                              </h3>
                              <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
                                {contactsList.length === 0 
                                  ? 'Upload 14_prospect_contacts.csv in Admin Data tab to populate stakeholders.'
                                  : 'Try clearing the search query or selecting All Departments.'}
                              </p>
                            </div>
                          ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                              {filteredContacts.map((contact: any, idx: number) => {
                                const initials = contact.full_name
                                  ? contact.full_name.split(' ').map((n: string) => n[0]).join('').substring(0, 2).toUpperCase()
                                  : 'U';

                                return (
                                  <div key={idx} className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4 hover:border-slate-300 transition flex flex-col justify-between">
                                    
                                    <div className="space-y-3">
                                      {/* Top Contact Header */}
                                      <div className="flex items-start space-x-3">
                                        <div className="w-11 h-11 bg-blue-50 text-hp-navy font-black rounded-full flex items-center justify-center text-xs flex-shrink-0 border border-blue-200">
                                          {initials}
                                        </div>

                                        <div className="flex-1 truncate">
                                          <div className="flex items-center space-x-2">
                                            <h3 className="text-sm font-extrabold text-slate-900 truncate">{contact.full_name}</h3>
                                            {contact.linkedin_url && (
                                              <a
                                                href={contact.linkedin_url.startsWith('http') ? contact.linkedin_url : `https://${contact.linkedin_url}`}
                                                target="_blank"
                                                rel="noreferrer"
                                                className="text-hp-navy hover:text-hp-blue flex-shrink-0"
                                                title="LinkedIn Profile"
                                              >
                                                <Globe className="w-3.5 h-3.5" />
                                              </a>
                                            )}
                                          </div>
                                          <p className="text-xs text-slate-600 font-semibold leading-snug line-clamp-2 mt-0.5">{contact.title || 'Title Unspecified'}</p>
                                          <p className="text-[11px] text-slate-400 font-medium truncate mt-0.5">{contact.department || 'General'}</p>
                                        </div>
                                      </div>

                                      {/* Badges Row */}
                                      <div className="flex flex-wrap items-center gap-1.5 pt-1">
                                        {contact.seniority && (
                                          <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-slate-100 text-slate-700 border border-slate-200 uppercase">
                                            {contact.seniority}
                                          </span>
                                        )}

                                        {/* Persona Badge (Rendered ONLY when present in raw data; absent for Apollo contacts) */}
                                        {contact.buying_committee_persona && (
                                          <span className="px-2 py-0.5 rounded text-[10px] font-extrabold bg-red-50 text-red-700 border border-red-200">
                                            {contact.buying_committee_persona.replace(/[\[\]"]/g, '')}
                                          </span>
                                        )}

                                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                          Priority: Derived TBD
                                        </span>

                                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-gray-50 text-slate-500 border border-slate-200 font-mono">
                                          {contact.source}
                                        </span>
                                      </div>

                                      {/* Contact Methods */}
                                      <div className="bg-slate-50 p-3 rounded-xl border border-slate-200/80 space-y-1 text-xs text-slate-700 font-medium">
                                        {contact.email ? (
                                          <div className="flex items-center justify-between font-mono text-[11px]">
                                            <span className="truncate text-hp-navy font-bold">{contact.email}</span>
                                            {contact.email_status && (
                                              <span className="text-[9px] font-bold px-1.5 py-0.2 bg-emerald-100 text-emerald-800 rounded">
                                                {contact.email_status}
                                              </span>
                                            )}
                                          </div>
                                        ) : (
                                          <span className="text-[11px] text-slate-400 italic">Email: Not provided</span>
                                        )}

                                        {contact.phone && (
                                          <div className="text-[11px] font-mono text-slate-600">
                                            Phone: {contact.phone}
                                          </div>
                                        )}
                                      </div>

                                      {/* Entry Path / How to Open (Inferred TBD Placeholder) */}
                                      <div className="bg-blue-50/70 border border-blue-200/80 rounded-xl p-3.5 text-xs text-blue-950 space-y-2">
                                        <div>
                                          <span className="font-extrabold text-hp-navy text-[10px] uppercase block">
                                            HOW TO OPEN:
                                          </span>
                                          <p className="text-[11px] leading-relaxed text-slate-600 italic">
                                            AI-synthesized person-specific talking points TBD for future runtime generation in Step 8.
                                          </p>
                                        </div>

                                        <div className="pt-2 border-t border-blue-200/60 space-y-1 text-[11px]">
                                          <div className="flex justify-between text-slate-600 font-medium">
                                            <span className="font-bold text-slate-500 uppercase text-[9px]">HP PLAY FOCUS:</span>
                                            <span className="text-purple-700 font-bold bg-purple-50 px-1.5 py-0.5 rounded text-[10px]">Inferred TBD</span>
                                          </div>
                                          <div className="flex justify-between text-slate-600 font-medium">
                                            <span className="font-bold text-slate-500 uppercase text-[9px]">DECISION POWER:</span>
                                            <span className="text-purple-700 font-bold bg-purple-50 px-1.5 py-0.5 rounded text-[10px]">Inferred TBD</span>
                                          </div>
                                        </div>
                                      </div>

                                    </div>

                                  </div>
                                );
                              })}
                            </div>
                          )}

                        </div>
                      )}

                      {/* View 2: Entry Path Ranked List View (Matching Image 2) */}
                      {stakeholderSubTab === 'entry_path' && (
                        <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                          <div className="border-b border-slate-100 pb-3">
                            <h3 className="text-sm font-extrabold text-slate-900 flex items-center gap-2">
                              <Layers className="w-4 h-4 text-hp-navy" />
                              <span>Entry Path Stakeholder Sequence</span>
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Dynamically ranked by seniority (25%), sector (20%), persona (25%), pain points (15%), priority (15%) — <strong className="text-amber-700 font-bold">Derived TBD</strong>
                            </p>
                          </div>

                          <div className="divide-y divide-slate-100">
                            {filteredContacts.map((contact: any, idx: number) => (
                              <div key={idx} className="py-3.5 flex items-center justify-between hover:bg-slate-50/80 transition px-3 rounded-xl">
                                <div className="flex items-center space-x-3.5">
                                  <span className="w-7 h-7 rounded-full bg-blue-50 text-hp-navy font-extrabold text-xs flex items-center justify-center border border-blue-200">
                                    {idx + 1}
                                  </span>
                                  <div>
                                    <div className="flex items-center space-x-2">
                                      <span className="text-sm font-bold text-slate-900">{contact.full_name}</span>
                                      {contact.seniority && (
                                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200 uppercase">
                                          {contact.seniority}
                                        </span>
                                      )}
                                    </div>
                                    <p className="text-xs text-slate-500 font-medium">{contact.title || 'Title Unspecified'} • <span className="text-slate-400">{contact.department || 'General'}</span></p>
                                  </div>
                                </div>

                                <div className="flex items-center space-x-2">
                                  <span className="text-xs font-mono font-bold text-slate-400 bg-slate-100 px-2.5 py-1 rounded-lg border border-slate-200">
                                    Derived TBD / 100
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Dynamic Department Breakdown Cards Section (Bottom of Images 1 & 2) */}
                      <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <h3 className="text-xs font-extrabold uppercase tracking-wider text-slate-700 flex items-center gap-2">
                            <Building2 className="w-4 h-4 text-hp-navy" />
                            <span>DYNAMIC DEPARTMENT BREAKDOWN ({Object.keys(deptDist).length} Departments)</span>
                          </h3>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-blue-50 text-hp-navy border border-blue-200">
                            Calculated Runtime
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
                          {Object.entries(deptDist).map(([dept, count]) => (
                            <div key={dept} className="bg-slate-50 p-3.5 rounded-xl border border-slate-200/80 flex items-center justify-between text-xs">
                              <span className="font-bold text-slate-800 truncate pr-2">{dept}</span>
                              <span className="font-mono text-hp-navy font-black bg-white px-2 py-0.5 rounded border border-slate-200">
                                {String(count)}
                              </span>
                            </div>
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
                            {mapData.total_detected_technologies || 21} detected technologies across {mapData.total_categories || 7} categories in {selectedAccount?.name || 'Target Account'}&apos;s stack, mapped to what each one means for HP
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
                              <span className="text-[10px] font-mono font-extrabold text-amber-700 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                                [ Strategic Read: Inferred TBD ]
                              </span>
                            </div>
                            <p className="text-xs text-slate-700 leading-relaxed font-medium">
                              {mapData.strategic_read}
                            </p>

                            {/* 4 Stat Cards */}
                            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
                              <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                                <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">DETECTED TECHNOLOGIES</span>
                                <div className="text-xl font-black font-mono text-slate-900">{mapData.total_detected_technologies || 21}</div>
                              </div>
                              <div className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                                <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider block">CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-slate-900">{mapData.total_categories || 7}</div>
                              </div>
                              <div className="bg-blue-50/60 p-3.5 rounded-xl border border-blue-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-blue-800 uppercase tracking-wider block">HP-MAPPED CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-hp-navy">{mapData.hp_mapped_categories || '5/7'}</div>
                              </div>
                              <div className="bg-emerald-50/60 p-3.5 rounded-xl border border-emerald-200/80 space-y-1">
                                <span className="text-[10px] font-extrabold text-emerald-800 uppercase tracking-wider block">WHITESPACE CATEGORIES</span>
                                <div className="text-xl font-black font-mono text-emerald-700">{mapData.whitespace_categories || '4/7'}</div>
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

                                {/* WHAT IT MEANS FOR HP Callout */}
                                <div className="bg-blue-50/50 border border-blue-100/80 rounded-xl p-4 space-y-1">
                                  <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-blue-600 block">
                                    WHAT IT MEANS FOR HP
                                  </span>
                                  <p className="text-xs text-slate-700 font-medium leading-relaxed">
                                    {cat.what_it_means}
                                  </p>
                                </div>

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
                                              {vendor.risk_level === 'High risk' && (
                                                <span className="text-[10px] font-extrabold text-red-700 bg-red-50 px-2 py-0.5 rounded-md border border-red-200">
                                                  High risk
                                                </span>
                                              )}
                                              {vendor.risk_level === 'Medium risk' && (
                                                <span className="text-[10px] font-extrabold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-md border border-amber-200">
                                                  Medium risk
                                                </span>
                                              )}
                                              {vendor.risk_level === 'Low risk' && (
                                                <span className="text-[10px] font-extrabold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded-md border border-emerald-200">
                                                  Low risk
                                                </span>
                                              )}
                                              {vendor.risk_level === 'Contextual' && (
                                                <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200">
                                                  Contextual
                                                </span>
                                              )}
                                              {vendor.risk_level === 'Inferred TBD' && (
                                                <span className="text-[10px] font-mono font-extrabold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded-md border border-indigo-200">
                                                  Inferred TBD
                                                </span>
                                              )}
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
                                          <span className="font-bold text-slate-500">{vendor.confidence === 'TBD' ? 'Confidence: TBD' : vendor.confidence}</span>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>

                               </div>
                             ))}
                          </div>
                        </div>

                    </div>
                  );
                })()}

                {/* ============================================================================== */}
                {/* MESSAGE EVALUATOR VIEW — MATCHING IMAGE 1 & FULL 7-STEP PIPELINE               */}
                {/* ============================================================================== */}
                {activeFeatureKey === 'message_evaluator' && (() => {
                  const personaWidget = widgets.find(w => w.widget_key === 'evaluator_persona_context');
                  const personaData = personaWidget?.data || {};

                  // Find active persona model from archetypes or fallback to static list
                  const currentPersona = PERSONA_ARCHETYPES.find(p => p.id === selectedPersonaId) || null;

                  const handleLoadSampleMessage = () => {
                    const sampleText = `Hi ${currentPersona?.default_contact_match?.split(' ')[0] || 'Stephen'},\n\nI noticed ${selectedAccount?.name || 'PT Astra International Tbk'} is accelerating its enterprise IT modernization and digitization across its business units in Indonesia.\n\nWith over 100,000 employees and significant hybrid operations, managing multi-vendor client device fleets and procurement cycles can create unnecessary operational overhead. HP Enterprise provides unified DaaS fleet management, hardware-enforced Wolf Security, and commercial lifecycle financing designed to simplify IT procurement and reduce total cost of ownership by up to 23%.\n\nWould you be open to a brief 15-minute introductory conversation next Tuesday to explore how we can optimize Astra's device procurement?\n\nBest regards,\nHP Enterprise Sales Team`;
                    setStimulusText(sampleText);
                    if (!selectedObjective) setSelectedObjective("Initial Outreach / Cold Prospecting");
                    if (!selectedFormat) setSelectedFormat("Cold Email");
                    if (!selectedPersonaId) setSelectedPersonaId("procurement_finance");
                  };

                  const handleCopyRewrite = () => {
                    const rewriteSample = `Subject: Optimizing IT device lifecycle & security for ${selectedAccount?.name || 'Astra'}\n\nHi ${currentPersona?.default_contact_match?.split(' ')[0] || 'Stephen'},\n\nGiven Astra's ongoing infrastructure expansion and multi-sector workforce requirements, managing device procurement cycles across disparate vendor fleets often introduces configuration friction and budget overruns.\n\nHP's commercial device programs combine zero-touch fleet provisioning, silicon-level Wolf Security containment, and dedicated enterprise SLA pricing tailored for large conglomerates in Indonesia.\n\nAre you available for a brief 10-minute briefing next Thursday to review how peer organizations streamlined their fleet procurement?`;
                    navigator.clipboard.writeText(rewriteSample);
                    setCopiedRewrite(true);
                    setTimeout(() => setCopiedRewrite(false), 3000);
                  };

                  // Step sequence definition
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

                  return (
                    <div className="space-y-6 animate-fade-in max-w-5xl">
                      
                      {/* Top Header Row Matching Image 1 */}
                      <div className="space-y-2">
                        <div className="flex items-center space-x-3">
                          <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center flex-shrink-0">
                            <MessageSquare className="w-5 h-5 text-indigo-600" />
                          </div>
                          <div className="flex items-center space-x-2">
                            <h2 className="text-xl font-extrabold text-slate-900 tracking-tight">
                              Message Evaluator
                            </h2>
                            <div className="relative">
                              <button
                                type="button"
                                onClick={() => setIsEvaluatorInfoOpen(!isEvaluatorInfoOpen)}
                                className="text-slate-400 hover:text-indigo-600 p-0.5 rounded transition"
                                title="About Message Evaluator"
                              >
                                <Info className="w-4 h-4" />
                              </button>

                              {/* Info Tooltip Popover */}
                              {isEvaluatorInfoOpen && (
                                <div className="absolute left-0 top-full mt-2 w-80 bg-white border border-slate-300 rounded-2xl shadow-2xl p-4 z-50 text-xs font-medium animate-fade-in">
                                  <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-2">
                                    <span className="font-extrabold text-slate-900">Message Evaluator</span>
                                    <button onClick={() => setIsEvaluatorInfoOpen(false)} className="text-slate-400 hover:text-slate-600">
                                      <X className="w-3.5 h-3.5" />
                                    </button>
                                  </div>
                                  <p className="text-slate-600 leading-relaxed text-[11px]">
                                    Persona-aware message scoring with behavioral simulation for {selectedAccount?.name || 'Target Account'}. Evaluates outreach copy against verified decision maker titles, objection triggers, and account guardrails before sending.
                                  </p>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>

                        <p className="text-xs text-slate-500 font-medium pl-12">
                          Persona-aware message scoring with behavioral simulation for {selectedAccount?.name || 'PT Astra International Tbk'}.
                        </p>
                      </div>

                      {/* 7-Step Breadcrumb Stepper Matching Image 1 */}
                      <div className="flex items-center space-x-2 text-xs font-medium text-slate-400 pl-1 pt-1">
                        {stepsList.map((st, i) => {
                          const isActive = st.key === evaluatorStep;
                          const isPassed = i < currentStepIdx;

                          return (
                            <React.Fragment key={st.key}>
                              <button
                                type="button"
                                onClick={() => {
                                  if (isPassed || isActive) {
                                    setEvaluatorStep(st.key as any);
                                  }
                                }}
                                disabled={!isPassed && !isActive}
                                className={`transition ${
                                  isActive
                                    ? 'text-indigo-600 font-bold underline cursor-pointer'
                                    : isPassed
                                    ? 'text-slate-600 hover:text-indigo-600 cursor-pointer font-semibold'
                                    : 'text-slate-400 cursor-default'
                                }`}
                              >
                                {st.label}
                              </button>
                              {i < stepsList.length - 1 && (
                                <span className="text-slate-300 text-[11px]">&gt;</span>
                              )}
                            </React.Fragment>
                          );
                        })}
                      </div>

                      {/* STEP 1: Inputs — Matching Image 1 EXACTLY */}
                      {evaluatorStep === 'inputs' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          
                          <div className="border-b border-slate-100 pb-3">
                            <h3 className="text-sm font-extrabold text-slate-900">
                              Step A — Configure Evaluation
                            </h3>
                          </div>

                          {/* Mode Toggle */}
                          <div className="space-y-1.5">
                            <label className="block text-xs font-semibold text-slate-700">
                              Mode
                            </label>
                            <div className="flex items-center space-x-2">
                              <button
                                type="button"
                                onClick={() => setEvaluatorMode('LITE')}
                                className={`px-4 py-1.5 rounded-lg text-xs font-extrabold uppercase transition ${
                                  evaluatorMode === 'LITE'
                                    ? 'bg-indigo-600 text-white shadow-sm'
                                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                }`}
                              >
                                LITE
                              </button>
                              <button
                                type="button"
                                onClick={() => setEvaluatorMode('DEEP')}
                                className={`px-4 py-1.5 rounded-lg text-xs font-extrabold uppercase transition ${
                                  evaluatorMode === 'DEEP'
                                    ? 'bg-indigo-600 text-white shadow-sm'
                                    : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                                }`}
                              >
                                DEEP
                              </button>
                            </div>
                            <p className="text-[11px] text-slate-400 font-medium">
                              {evaluatorMode === 'LITE'
                                ? 'Quick evaluation: 5 phrase chunks, skip behavioral state'
                                : 'Full behavioral simulation: phrase-by-phrase sentiment, psychographic profiling, objection forecast'}
                            </p>
                          </div>

                          {/* Audience (Persona) Select Dropdown Matching Image 1 */}
                          <div className="space-y-1.5">
                            <label className="block text-xs font-semibold text-slate-700">
                              Audience (Persona)
                            </label>
                            <select
                              value={selectedPersonaId}
                              onChange={(e) => setSelectedPersonaId(e.target.value)}
                              className="w-full p-2.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition shadow-xs"
                            >
                              <option value="">Select persona...</option>
                              {PERSONA_ARCHETYPES.map((p) => (
                                <option key={p.id} value={p.id}>
                                  {p.label}
                                </option>
                              ))}
                            </select>
                            {currentPersona && (
                              <p className="text-[11px] text-emerald-700 font-medium pt-0.5">
                                Verified Astra Contact Match: <strong className="font-bold">{currentPersona.default_contact_match}</strong> ({currentPersona.matched_title})
                              </p>
                            )}
                          </div>

                          {/* Objective (Funnel Stage) Select Dropdown */}
                          <div className="space-y-1.5">
                            <label className="block text-xs font-semibold text-slate-700">
                              Objective (Funnel Stage)
                            </label>
                            <select
                              value={selectedObjective}
                              onChange={(e) => setSelectedObjective(e.target.value)}
                              className="w-full p-2.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition shadow-xs"
                            >
                              <option value="">Select objective...</option>
                              {FUNNEL_OBJECTIVES.map((obj) => (
                                <option key={obj} value={obj}>
                                  {obj}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Format (Content Type) Select Dropdown */}
                          <div className="space-y-1.5">
                            <label className="block text-xs font-semibold text-slate-700">
                              Format (Content Type)
                            </label>
                            <select
                              value={selectedFormat}
                              onChange={(e) => setSelectedFormat(e.target.value)}
                              className="w-full p-2.5 bg-white border border-slate-300 rounded-lg text-xs font-medium text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition shadow-xs"
                            >
                              <option value="">Select format...</option>
                              {CONTENT_FORMATS.map((fmt) => (
                                <option key={fmt} value={fmt}>
                                  {fmt}
                                </option>
                              ))}
                            </select>
                          </div>

                          {/* Stimulus (Message Text) Textarea */}
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between">
                              <label className="block text-xs font-semibold text-slate-700">
                                Stimulus (Message Text)
                              </label>
                              <button
                                type="button"
                                onClick={handleLoadSampleMessage}
                                className="text-[11px] text-indigo-600 hover:text-indigo-800 font-bold underline"
                              >
                                Load Sample Outreach
                              </button>
                            </div>
                            <textarea
                              rows={7}
                              value={stimulusText}
                              onChange={(e) => setStimulusText(e.target.value)}
                              placeholder="Paste or type your sales email, LinkedIn message, campaign copy, or call script here..."
                              className="w-full p-3.5 border border-slate-300 rounded-xl text-xs leading-relaxed font-mono focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 bg-white shadow-xs transition"
                            />
                            <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                              <span>{stimulusText.length} characters</span>
                              {stimulusText && (
                                <button
                                  type="button"
                                  onClick={() => setStimulusText('')}
                                  className="text-slate-400 hover:text-red-500 underline"
                                >
                                  Clear
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Action Button Matching Image 1 */}
                          <div className="pt-2">
                            <button
                              type="button"
                              onClick={() => {
                                if (!selectedPersonaId) {
                                  setSelectedPersonaId("procurement_finance");
                                }
                                setEvaluatorStep('persona');
                              }}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <User className="w-4 h-4" />
                              <span>Build Persona</span>
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 2: Persona Calibration & Baseline */}
                      {evaluatorStep === 'persona' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-sm font-extrabold text-slate-900">
                                Step B — Calibrated Persona Profile
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                Grounded in deterministic records for {selectedAccount?.name || 'PT Astra International Tbk'}
                              </p>
                            </div>
                            <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-blue-50 text-indigo-700 border border-indigo-200 font-mono">
                              14_prospect_contacts.csv
                            </span>
                          </div>

                          {/* Contact Profile Grid */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-medium">
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-2">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                                DETERMINISTIC CONTACT PROFILE
                              </span>
                              <div className="space-y-1">
                                <div className="text-sm font-extrabold text-slate-900">{currentPersona?.default_contact_match || 'Stephen Dharma'}</div>
                                <div className="text-slate-700 font-semibold">{currentPersona?.matched_title || 'Head of IT Project Procurement'}</div>
                                <div className="text-slate-500">{currentPersona?.matched_dept || 'IT Procurement'} • {currentPersona?.seniority || 'Director / Head'}</div>
                                <div className="pt-1 font-mono text-[11px] text-hp-navy">{currentPersona?.email || 'stephen.dharma@ai.astra.co.id'}</div>
                                <div className="font-mono text-[11px] text-slate-600">{currentPersona?.phone || '+62 21 6530 3333'}</div>
                              </div>
                            </div>

                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-2">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                                PSYCHOGRAPHIC BASELINE & CONCERNS
                              </span>
                              <div className="space-y-1.5 text-[11px]">
                                <div>
                                  <span className="font-bold text-slate-600">Receptivity Orientation: </span>
                                  <span className="text-slate-800">{currentPersona?.receptivity || 'Technical & economic defensibility'} <strong className="text-indigo-600">[ Inferred TBD ]</strong></span>
                                </div>
                                <div>
                                  <span className="font-bold text-slate-600">Core Concern: </span>
                                  <span className="text-slate-800">{currentPersona?.primary_concern || 'Budget overruns, uncompetitive pricing'} <strong className="text-indigo-600">[ Inferred TBD ]</strong></span>
                                </div>
                                <div>
                                  <span className="font-bold text-slate-600">Anticipated Objection: </span>
                                  <span className="text-slate-800">{currentPersona?.objection_point || 'Strict procurement tenders and existing supplier SLA locks'} <strong className="text-indigo-600">[ Inferred TBD ]</strong></span>
                                </div>
                              </div>
                            </div>
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('inputs')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back to Inputs
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('confirm')}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <span>Proceed to Confirm</span>
                              <ArrowRight className="w-4 h-4" />
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 3: Confirm & Guardrail Audit */}
                      {evaluatorStep === 'confirm' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="border-b border-slate-100 pb-3">
                            <h3 className="text-sm font-extrabold text-slate-900">
                              Step C — Pre-Evaluation Audit & Guardrail Check
                            </h3>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Verify inputs and compliance rules before running evaluation
                            </p>
                          </div>

                          <div className="space-y-4 text-xs font-medium">
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-2">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                                EVALUATION SCOPE
                              </span>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                                <div>
                                  <span className="text-slate-400 block text-[10px]">Target Persona:</span>
                                  <span className="font-bold text-slate-800">{currentPersona?.short_title || 'Procurement / Finance'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-400 block text-[10px]">Funnel Objective:</span>
                                  <span className="font-bold text-slate-800">{selectedObjective || 'Initial Outreach'}</span>
                                </div>
                                <div>
                                  <span className="text-slate-400 block text-[10px]">Evaluation Mode:</span>
                                  <span className="font-bold text-indigo-700">{evaluatorMode} Mode</span>
                                </div>
                              </div>
                            </div>

                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-2">
                              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400 block">
                                STIMULUS MESSAGE PREVIEW
                              </span>
                              <p className="font-mono text-[11px] text-slate-700 leading-relaxed bg-white p-3 rounded-lg border border-slate-200 whitespace-pre-wrap">
                                {stimulusText || 'No message text entered.'}
                              </p>
                            </div>

                            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-start space-x-3 text-emerald-900">
                              <ShieldCheck className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
                              <div className="space-y-0.5">
                                <span className="font-bold text-xs">Guardrail Compliance Audit: Verified Active</span>
                                <p className="text-[11px] text-emerald-800 leading-relaxed">
                                  Account guardrails for {selectedAccount?.name || 'PT Astra International Tbk'} active. Message will be verified against restricted superlative claims and proof point defensibility.
                                </p>
                              </div>
                            </div>
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('persona')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('scores')}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <Sparkles className="w-4 h-4" />
                              <span>Run Message Evaluation</span>
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 4: Scores Diagnostic Panel */}
                      {evaluatorStep === 'scores' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-sm font-extrabold text-slate-900">
                                Step D — Evaluation Diagnostic Scorecard
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                Scored against {currentPersona?.short_title || 'Target Persona'} at {selectedAccount?.name || 'Astra'}
                              </p>
                            </div>
                            <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-mono">
                              Inferred TBD
                            </span>
                          </div>

                          {/* Score Cards Grid */}
                          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs font-medium">
                            {[
                              { label: 'Resonance Score', score: 'Inferred TBD', max: '/100', desc: 'Alignment with persona pain points' },
                              { label: 'Clarity & Brevity', score: 'Inferred TBD', max: '/100', desc: 'Message conciseness and flow' },
                              { label: 'Value Relevance', score: 'Inferred TBD', max: '/100', desc: 'Quantified HP outcome framing' },
                              { label: 'Urgency & Hook', score: 'Inferred TBD', max: '/100', desc: 'Call-to-action effectiveness' }
                            ].map((item, idx) => (
                              <div key={idx} className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-1">
                                <span className="text-[11px] font-bold text-slate-500 block">{item.label}</span>
                                <div className="text-xl font-extrabold text-indigo-700">
                                  {item.score} <span className="text-xs text-slate-400 font-normal">{item.max}</span>
                                </div>
                                <span className="text-[10px] text-slate-400 block">{item.desc}</span>
                              </div>
                            ))}
                          </div>

                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-2 text-xs">
                            <span className="font-extrabold text-slate-800 uppercase text-[10px] block">
                              EVALUATOR SYNTHESIS STATUS
                            </span>
                            <p className="text-[11px] text-slate-600 leading-relaxed italic">
                              AI-synthesized behavioral simulation scoring and sentiment weights for {selectedAccount?.name || 'PT Astra International Tbk'} are TBD for future model execution.
                            </p>
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('confirm')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('phrases')}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <span>Inspect Phrase Breakdown</span>
                              <ArrowRight className="w-4 h-4" />
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 5: Phrases Breakdown */}
                      {evaluatorStep === 'phrases' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-sm font-extrabold text-slate-900">
                                Step E — Phrase-by-Phrase Behavioral Response
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                Cognitive friction and sentiment breakdown per phrase chunk
                              </p>
                            </div>
                            <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-mono">
                              Inferred TBD
                            </span>
                          </div>

                          <div className="space-y-3">
                            {[
                              { chunk: '1. Salutation & Opening', text: 'Noticing Astra\'s enterprise IT modernization programs...', reaction: 'Receptivity: Neutral [ Inferred TBD ]' },
                              { chunk: '2. Value Framing', text: 'With over 100,000 employees and significant hybrid operations...', reaction: 'Relevance: High [ Inferred TBD ]' },
                              { chunk: '3. HP Solution Offer', text: 'HP Enterprise provides unified DaaS and Wolf Security...', reaction: 'Objection Risk: Moderate [ Inferred TBD ]' },
                              { chunk: '4. Call to Action', text: 'Would you be open to a brief 15-minute introductory call...', reaction: 'Friction: Low [ Inferred TBD ]' },
                            ].map((pChunk, idx) => (
                              <div key={idx} className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-1.5 text-xs">
                                <div className="flex items-center justify-between">
                                  <span className="font-extrabold text-slate-800 text-[11px]">{pChunk.chunk}</span>
                                  <span className="text-[10px] font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                                    {pChunk.reaction}
                                  </span>
                                </div>
                                <p className="font-mono text-slate-700 text-[11px]">{pChunk.text}</p>
                              </div>
                            ))}
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('scores')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('summary')}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <span>View Executive Summary</span>
                              <ArrowRight className="w-4 h-4" />
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 6: Summary Findings */}
                      {evaluatorStep === 'summary' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-sm font-extrabold text-slate-900">
                                Step F — Executive Evaluation Summary
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                Overall findings, strengths, and recommended improvements
                              </p>
                            </div>
                            <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-mono">
                              Inferred TBD
                            </span>
                          </div>

                          <div className="space-y-4 text-xs font-medium">
                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-1.5">
                              <span className="font-extrabold text-emerald-800 text-[11px] block uppercase">
                                Message Strengths
                              </span>
                              <p className="text-slate-700 text-[11px] leading-relaxed">
                                • Sourced company scale (100,000+ employees) establishes authentic account context.<br/>
                                • Direct HP value proposition alignment (DaaS + Wolf Security). <strong className="text-indigo-600">[ Inferred TBD ]</strong>
                              </p>
                            </div>

                            <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/80 space-y-1.5">
                              <span className="font-extrabold text-amber-800 text-[11px] block uppercase">
                                Friction Points & Suggested Refinements
                              </span>
                              <p className="text-slate-700 text-[11px] leading-relaxed">
                                • Quantified 23% savings claim should cite specific lifecycle benchmark evidence.<br/>
                                • Soften initial meeting request to a peer case study review. <strong className="text-indigo-600">[ Inferred TBD ]</strong>
                              </p>
                            </div>
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('phrases')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back
                            </button>
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('rewrite')}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold shadow-md transition"
                            >
                              <Sparkles className="w-4 h-4" />
                              <span>Generate Optimized Rewrite</span>
                            </button>
                          </div>

                        </div>
                      )}

                      {/* STEP 7: AI Optimized Rewrite */}
                      {evaluatorStep === 'rewrite' && (
                        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8 space-y-6">
                          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                            <div>
                              <h3 className="text-sm font-extrabold text-slate-900">
                                Step G — AI-Optimized Message Rewrite
                              </h3>
                              <p className="text-xs text-slate-500 mt-0.5">
                                Tailored outreach tailored to {currentPersona?.short_title || 'Persona'}
                              </p>
                            </div>
                            <span className="text-[10px] font-bold px-2.5 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 font-mono">
                              Inferred TBD
                            </span>
                          </div>

                          <div className="bg-slate-50 p-5 rounded-xl border border-slate-200/80 space-y-3 text-xs">
                            <div className="flex items-center justify-between">
                              <span className="font-extrabold text-slate-800 text-[11px] uppercase">
                                Recommended Copy (High-Resonance Optimization)
                              </span>
                              <button
                                type="button"
                                onClick={handleCopyRewrite}
                                className="inline-flex items-center space-x-1 px-3 py-1 bg-white border border-slate-200 rounded-lg text-[11px] font-bold text-indigo-700 hover:bg-indigo-50 shadow-xs transition"
                              >
                                {copiedRewrite ? (
                                  <>
                                    <Check className="w-3.5 h-3.5 text-emerald-600" />
                                    <span>Copied!</span>
                                  </>
                                ) : (
                                  <>
                                    <Copy className="w-3.5 h-3.5" />
                                    <span>Copy Text</span>
                                  </>
                                )}
                              </button>
                            </div>

                            <div className="font-mono text-[11px] text-slate-800 leading-relaxed bg-white p-4 rounded-xl border border-slate-200/90 whitespace-pre-wrap">
{`Subject: Optimizing IT device lifecycle & security for ${selectedAccount?.name || 'Astra'}

Hi ${currentPersona?.default_contact_match?.split(' ')[0] || 'Stephen'},

Given Astra's ongoing infrastructure expansion and multi-sector workforce requirements, managing device procurement cycles across disparate vendor fleets often introduces configuration friction and budget overruns.

HP's commercial device programs combine zero-touch fleet provisioning, silicon-level Wolf Security containment, and dedicated enterprise SLA pricing tailored for large conglomerates in Indonesia.

Are you available for a brief 10-minute briefing next Thursday to review how peer organizations streamlined their fleet procurement?`}
                            </div>
                            <span className="text-[10px] text-slate-400 italic block">
                              AI-optimized rewrite for {selectedAccount?.name || 'PT Astra International Tbk'} is TBD for future model execution.
                            </span>
                          </div>

                          {/* Navigation Actions */}
                          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                            <button
                              type="button"
                              onClick={() => setEvaluatorStep('summary')}
                              className="px-4 py-2 text-xs font-bold text-slate-600 hover:text-slate-900 bg-slate-100 hover:bg-slate-200 rounded-xl transition"
                            >
                              Back
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setEvaluatorStep('inputs');
                                setStimulusText('');
                              }}
                              className="inline-flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-900 text-white text-xs font-bold shadow-md transition"
                            >
                              <RotateCcw className="w-4 h-4" />
                              <span>Start New Evaluation</span>
                            </button>
                          </div>

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
                            Incumbent technology evidence &amp; objection reframe contracts for {selectedAccount?.name || 'Target Account'}
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-hp-navy bg-blue-50 px-3 py-1.5 rounded-xl border border-blue-200">
                            {totalIncumbentsCount} Incumbents Detected
                          </span>
                        </div>
                      </div>

                      {/* Section 2: Competitor Reframes & Proof Points (Inferred - Left as TBD) */}
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <div>
                            <h4 className="text-sm font-black text-slate-900 flex items-center gap-2">
                              <Sparkles className="w-4 h-4 text-purple-600" />
                              <span>Competitor Reframes &amp; Proof Points</span>
                              {getClassificationBadge('inferred')}
                            </h4>
                            <p className="text-xs text-slate-500 mt-0.5">
                              AI-generated objection statements, competitive reframes, counter questions, and likely raisers
                            </p>
                          </div>

                          <span className="text-[11px] font-mono font-extrabold text-amber-800 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                            Inferred TBD
                          </span>
                        </div>

                        {/* Inferred TBD Banner Box */}
                        <div className="bg-amber-50/60 border border-amber-200/80 rounded-2xl p-6 text-center space-y-3">
                          <div className="w-10 h-10 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto border border-amber-300">
                            <Sparkles className="w-5 h-5 text-amber-600" />
                          </div>
                          <h4 className="text-xs font-black text-amber-900 uppercase tracking-wider">
                            Objection Reframe Generation — Inferred TBD
                          </h4>
                          <p className="text-xs text-amber-800 max-w-xl mx-auto leading-relaxed">
                            AI-synthesized objection statements, likely raisers, competitive reframes, and strategic counter-questions based on incumbent technology evidence will be generated in Step 8 (AI Generation Layer).
                          </p>
                        </div>
                      </div>

                    </div>
                  );
                })()}

                {activeFeatureKey === 'content_messaging' && (() => {
                  const contextWidget = widgets.find(w => w.widget_key === 'messaging_context_card');
                  const pillarsWidget = widgets.find(w => w.widget_key === 'messaging_pillars_output');

                  const contextData = contextWidget?.data || {};
                  const pillarsData = pillarsWidget?.data || {};

                  const businessCtx = contextData.business_context || {};
                  const techEvidence = contextData.technology_evidence || {};
                  const intentEvidence = contextData.intent_evidence || {};
                  const newsEvidence = contextData.news_evidence || {};

                  const totalSourcedSignals = contextData.total_sourced_signals ?? 0;
                  const fullTechStack: string[] = techEvidence.full_tech_stack || [];
                  const intentTopics: any[] = intentEvidence.topics || [];
                  const newsTriggers: any[] = newsEvidence.triggers || [];

                  return (
                    <div className="space-y-6 animate-fade-in">
                      {/* Top Header */}
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-200 pb-4">
                        <div>
                          <h3 className="text-xl font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                            <Megaphone className="w-6 h-6 text-hp-navy" />
                            <span>Content Messaging</span>
                          </h3>
                          <p className="text-xs text-slate-500 mt-0.5">
                            Campaign message house for {selectedAccount?.name || 'Target Account'} &middot; 4 pillars &middot; {totalSourcedSignals} sourced signals
                          </p>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-xs font-bold text-hp-navy bg-blue-50 px-3 py-1.5 rounded-xl border border-blue-200">
                            {totalSourcedSignals} Evidence Signals Sourced
                          </span>
                        </div>
                      </div>

                      {/* Layer 1: Umbrella Message Container (Inferred TBD) */}
                      <div className="bg-gradient-to-r from-blue-50/90 to-indigo-50/80 rounded-2xl border border-blue-200/80 p-6 space-y-3 shadow-xs">
                        <div className="flex items-center justify-between">
                          <span className="text-[10px] font-mono font-extrabold uppercase tracking-widest text-blue-700 flex items-center gap-1.5">
                            <Globe className="w-3.5 h-3.5 text-blue-600" />
                            <span>UMBRELLA MESSAGE</span>
                          </span>
                          <span className="text-[10px] font-mono font-extrabold text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                            Inferred TBD
                          </span>
                        </div>

                        <h4 className="text-base font-extrabold text-slate-900 leading-snug">
                          {selectedAccount?.name || 'Target Account'} Strategic Transformation Umbrella Message
                        </h4>

                        <div className="bg-white/80 border border-blue-200/60 rounded-xl p-4 text-xs text-slate-600 space-y-2">
                          <div className="flex items-center gap-2 text-amber-800 font-extrabold text-xs">
                            <Sparkles className="w-4 h-4 text-amber-600 flex-shrink-0" />
                            <span>AI Umbrella Message Headline Synthesis — Step 8 Execution</span>
                          </div>
                          <p className="text-slate-600 leading-relaxed font-medium">
                            The campaign umbrella headline and core transformation vectors for {selectedAccount?.name || 'Target Account'} will be synthesized in Step 8 (AI Generation Layer) based on the sourced evidence below.
                          </p>
                        </div>
                      </div>

                      {/* Layer 2: 4 Messaging Pillars Placeholders (Inferred TBD) */}
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <div>
                            <h4 className="text-sm font-black text-slate-900 flex items-center gap-2">
                              <Layers className="w-4 h-4 text-hp-navy" />
                              <span>Core Messaging Pillars (4 Pillars)</span>
                              {getClassificationBadge('inferred')}
                            </h4>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Pillar headlines, customer challenges, HP benefit claims, product plays, and proof selections
                            </p>
                          </div>

                          <span className="text-[11px] font-mono font-extrabold text-amber-800 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                            4 Pillars — Inferred TBD
                          </span>
                        </div>

                        <div className="space-y-3">
                          {[1, 2, 3, 4].map((num) => (
                            <div key={num} className="bg-slate-50/80 rounded-xl border border-slate-200 p-4 space-y-3">
                              <div className="flex items-center justify-between">
                                <span className="text-xs font-black text-slate-800 flex items-center gap-2">
                                  <span className="w-5 h-5 rounded-full bg-blue-100 text-hp-navy text-[11px] font-mono font-extrabold flex items-center justify-center border border-blue-200">
                                    {num}
                                  </span>
                                  <span>Messaging Pillar {num} — Inferred TBD</span>
                                </span>
                                <span className="text-[10px] font-mono font-bold text-slate-400 bg-white px-2 py-0.5 rounded border border-slate-200">
                                  Step 8 AI Synthesis
                                </span>
                              </div>

                              <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs pt-1">
                                <div className="bg-white p-3 rounded-lg border border-slate-200 space-y-1">
                                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">CHALLENGE</span>
                                  <p className="text-slate-500 italic text-[11px]">Customer pain point &amp; challenge narrative will be generated in Step 8.</p>
                                </div>
                                <div className="bg-white p-3 rounded-lg border border-slate-200 space-y-1">
                                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">HP BENEFIT</span>
                                  <p className="text-slate-500 italic text-[11px]">HP solution benefit &amp; product hardware mapping will be generated in Step 8.</p>
                                </div>
                                <div className="bg-white p-3 rounded-lg border border-slate-200 space-y-1">
                                  <span className="text-[10px] font-extrabold text-slate-400 uppercase tracking-wider block">PROOF POINTS</span>
                                  <p className="text-slate-500 italic text-[11px]">Sourced evidence signals will be selected and linked in Step 8.</p>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Layer 3: Why HP Section (Inferred TBD Placeholders) */}
                      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
                        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
                          <div>
                            <h4 className="text-sm font-black text-slate-900 flex items-center gap-2">
                              <Sparkles className="w-4 h-4 text-purple-600" />
                              <span>Why HP Positioning</span>
                              {getClassificationBadge('inferred')}
                            </h4>
                            <p className="text-xs text-slate-500 mt-0.5">
                              Strategic differentiators &amp; competitive positioning statements
                            </p>
                          </div>

                          <span className="text-[11px] font-mono font-extrabold text-amber-800 bg-amber-50 px-3 py-1 rounded-full border border-amber-200">
                            Inferred TBD
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                          {[
                            'Full Estate Unified Hardware Partnership',
                            'Silicon & BIOS Below-the-OS Security',
                            'Platform Certification & Eco-system Parity',
                            'AI-Scale High Performance Compute'
                          ].map((title, idx) => (
                            <div key={idx} className="bg-slate-50/80 p-3.5 rounded-xl border border-slate-200 space-y-1">
                              <span className="font-extrabold text-slate-800 flex items-center gap-1.5 text-xs">
                                <span className="text-blue-600 font-mono font-black">#</span>
                                <span>{title}</span>
                              </span>
                              <p className="text-slate-500 italic text-[11px] pl-3">
                                Positioning claim synthesis is TBD for Step 8 AI model execution.
                              </p>
                            </div>
                          ))}
                        </div>
                      </div>

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
                    { id: 'engineering_ai', title: 'Engineering / AI & Compute Leadership', subtitle: 'AI Centre of Excellence, ML and GPU/compute buyers' },
                    { id: 'security_wolf', title: 'Security Leadership (Wolf Security)', subtitle: 'Endpoint security and risk decision makers' },
                    { id: 'procurement_finance', title: 'Procurement / Finance', subtitle: 'Regional IT procurement and budget holders' },
                    { id: 'operations', title: 'Regional Operations', subtitle: 'New office / expansion leads, print & workplace services' },
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

                  const handleGenerateClick = () => {
                    setIsGeneratingContent(true);
                    setTimeout(() => {
                      setIsGeneratingContent(false);
                      setHasGeneratedContent(true);
                    }, 600);
                  };

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
                          Generate persona-targeted ABM content for {selectedAccount?.name || 'Target Account'} - powered by Gemini
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

                          {/* 5. Generate Button */}
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
                        <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200 shadow-sm p-8 min-h-[560px] flex flex-col justify-center items-center text-center">
                          
                          {!hasGeneratedContent ? (
                            <div className="max-w-md space-y-4 animate-fade-in">
                              <div className="w-14 h-14 rounded-2xl bg-slate-100 border border-slate-200 flex items-center justify-center mx-auto text-slate-400 shadow-xs">
                                <Sparkles className="w-7 h-7 text-slate-400" />
                              </div>
                              <h4 className="text-base font-extrabold text-slate-800">
                                Ready to generate
                              </h4>
                              <p className="text-xs text-slate-500 leading-relaxed font-medium">
                                Select a target persona and content type, then click &quot;Generate Content&quot;. Gemini will create personalized ABM content using {selectedAccount?.name || 'Target Account'} account intelligence and HP Inc. product positioning.
                              </p>
                            </div>
                          ) : (
                            <div className="w-full space-y-6 text-left animate-fade-in">
                              
                              {/* Generation Selection Summary Bar */}
                              <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
                                <div className="space-y-0.5">
                                  <span className="text-[10px] font-mono font-bold text-slate-400 uppercase">Target Persona &amp; Format:</span>
                                  <p className="font-extrabold text-slate-900">
                                    {activePersonaObj.title} &middot; <span className="text-hp-navy">{activeFormatObj.title}</span>
                                  </p>
                                </div>

                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-mono font-extrabold text-amber-800 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200">
                                    Inferred TBD
                                  </span>
                                  <button
                                    onClick={() => setHasGeneratedContent(false)}
                                    className="text-[10px] font-bold text-slate-500 underline hover:text-slate-800"
                                  >
                                    Reset
                                  </button>
                                </div>
                              </div>

                              {/* Inferred TBD Banner Box */}
                              <div className="bg-amber-50/70 border border-amber-200/80 rounded-2xl p-8 text-center space-y-4">
                                <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-800 flex items-center justify-center mx-auto border border-amber-300 shadow-xs">
                                  <Sparkles className="w-6 h-6 text-amber-600" />
                                </div>

                                <h4 className="text-sm font-black text-amber-900 uppercase tracking-wider">
                                  ABM Content Generation — Inferred TBD
                                </h4>

                                <p className="text-xs text-amber-800 max-w-lg mx-auto leading-relaxed font-medium">
                                  LLM prompt generation for <span className="font-bold text-amber-950">{activeFormatObj.title}</span> tailored to <span className="font-bold text-amber-950">{activePersonaObj.title}</span> for <span className="font-bold text-amber-950">{selectedAccount?.name || 'Target Account'}</span> will be executed in Step 8 (AI Generation Layer).
                                </p>

                                <div className="bg-white/80 border border-amber-200/60 rounded-xl p-4 text-left text-xs space-y-2 text-slate-700">
                                  <span className="font-mono font-extrabold text-[10px] text-amber-900 uppercase block tracking-wider">
                                    Selected Inputs Ready for Step 8 Prompt:
                                  </span>
                                  <div className="space-y-1 font-mono text-[11px] text-slate-600">
                                    <div>&bull; Persona: <span className="font-bold text-slate-900">{activePersonaObj.title}</span> ({activePersonaObj.subtitle})</div>
                                    <div>&bull; Format: <span className="font-bold text-slate-900">{activeFormatObj.title}</span> ({activeFormatObj.subtitle})</div>
                                    <div>&bull; Topic: <span className="font-bold text-slate-900">{customTopic.trim() || selectedTopic}</span></div>
                                    {additionalContext.trim() && (
                                      <div>&bull; Context: <span className="italic text-slate-800">&quot;{additionalContext}&quot;</span></div>
                                    )}
                                  </div>
                                </div>

                              </div>

                            </div>
                          )}

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
                  const suggestedPrompts: any[] = contextData.suggested_prompts || [
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
                  const stakeholdersCount = groundingMeta.stakeholders_count ?? 23;
                  const solutionsCount = groundingMeta.solutions_count ?? 5;

                  const handleSendPrompt = (promptText: string) => {
                    if (!promptText.trim()) return;
                    const userMsg = {
                      id: `user_${Date.now()}`,
                      sender: 'user' as const,
                      text: promptText,
                      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    };

                    const assistantMsg = {
                      id: `asst_${Date.now() + 1}`,
                      sender: 'assistant' as const,
                      text: `Conversational RAG response for prompt "${promptText}" on ${companyName} is TBD for Step 8 (AI Generation Layer).`,
                      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                    };

                    setChatMessages(prev => [...prev, userMsg, assistantMsg]);
                    setChatInput('');
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
                        <div className="flex items-center gap-2">
                          <div className="relative">
                            <select
                              value={chatAdvisorMode}
                              onChange={(e) => setChatAdvisorMode(e.target.value)}
                              className="px-3 py-2 bg-slate-50 border border-slate-300 rounded-xl text-xs font-extrabold text-slate-800 focus:outline-none focus:ring-2 focus:ring-hp-navy appearance-none pr-8 cursor-pointer shadow-xs"
                            >
                              <option value="Strategy Advisor">🤖 Strategy Advisor</option>
                              <option value="Competitive Defender">🛡️ Competitive Defender</option>
                              <option value="Executive Pitcher">🎯 Executive Pitcher</option>
                              <option value="ABM Campaign Planner">📅 ABM Campaign Planner</option>
                            </select>
                            <ChevronDown className="w-3.5 h-3.5 text-slate-400 absolute right-2.5 top-3 pointer-events-none" />
                          </div>
                        </div>

                        <div className="flex items-center gap-1.5 text-slate-500 font-medium">
                          <Info className="w-3.5 h-3.5 text-hp-navy" />
                          <span>Grounded in: <strong className="text-slate-800">{companyName} Intelligence</strong> &middot; <strong className="text-slate-800">{stakeholdersCount} Stakeholders</strong> &middot; <strong className="text-slate-800">{solutionsCount} Solutions</strong></span>
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
                                ABM Strategy Assistant
                              </h4>
                              <p className="text-xs text-slate-600 leading-relaxed font-medium">
                                Ask me anything about {companyName}, HP Inc. positioning, competitive strategy, or ABM campaign planning. I&apos;m grounded in {companyName}&apos;s actual data and strategic priorities.
                              </p>
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
                                        <span>ABM Strategy Assistant</span>
                                      </span>
                                      <span className="text-[10px] font-mono font-extrabold text-amber-800 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
                                        Inferred TBD
                                      </span>
                                    </div>

                                    <div className="bg-amber-50/70 border border-amber-200/80 rounded-xl p-3.5 text-xs text-amber-900 space-y-1.5">
                                      <span className="font-extrabold text-xs block">
                                        Strategy Assistant RAG Grounding — Inferred TBD
                                      </span>
                                      <p className="text-[11px] text-amber-800 leading-relaxed font-medium">
                                        Conversational RAG response generation using Gemini LLM prompts over {companyName}&apos;s grounded snapshot (23 stakeholders, 220 tech vendors, 10 news events) will be executed in Step 8 (AI Generation Layer).
                                      </p>
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
                              disabled={!chatInput.trim()}
                              className="p-3 bg-hp-navy hover:bg-blue-900 text-white rounded-2xl transition disabled:opacity-40 shadow-xs flex items-center justify-center flex-shrink-0"
                            >
                              <Sparkles className="w-4 h-4 text-amber-300" />
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
                                  : `Calculated or AI generated outputs for ${widget.widget_name} will be enabled in subsequent steps.`}
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
