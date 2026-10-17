'use client';

// The product tour and each feature's help walkthrough.
//
// Client, 17 Oct: a new user is walked through every feature on their first
// sign-in. Each feature opens with an overview card: Skip goes to the next
// feature, Dive in goes through that feature's detail cards and then on to the
// next feature. The same cards replay for one feature from its ? button.
//
// A hook rather than a context provider: the dashboard page owns the active
// feature, and the tour needs to switch it, so the page calls the hook and
// renders `overlay` itself. The words live in lib/tourContent.ts.
//
// Each card points at a `data-tour` element. Switching feature renders that
// feature's widgets after their data arrives, so the target is waited for
// (up to TARGET_WAIT_MS); a section the account has no data for never appears
// and its card is shown in the middle of the page instead of hanging.

import React, { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import {
  FEATURE_TOURS,
  TOUR_FINISH,
  TOUR_WELCOME,
  type TourCard,
} from '@/lib/tourContent';
import { featureLabel } from '@/lib/features';

const TARGET_WAIT_MS = 4000;
const PAD = 6;          // spotlight padding around the target
const GAP = 12;         // between the spotlight and the card
const MARGIN = 16;      // kept clear of the window edges
const WIDTH = 380;

type Stage = 'welcome' | 'feature' | 'finish';

interface TourState {
  mode: 'tour' | 'help';
  features: string[];
  stage: Stage;
  /** Index into `features`. */
  fi: number;
  /** -1 = the feature's overview card, otherwise a detail card. */
  ci: number;
}

interface Box { top: number; left: number; width: number; height: number }

interface UseTourOptions {
  activeFeatureKey: string;
  setActiveFeatureKey: (key: string) => void;
  /** The full tour was finished or closed. */
  onTourDone: () => void;
}

export function useTour({ activeFeatureKey, setActiveFeatureKey, onTourDone }: UseTourOptions) {
  const [state, setState] = useState<TourState | null>(null);
  const stateRef = useRef<TourState | null>(null);
  stateRef.current = state;
  const returnTo = useRef<string | null>(null);

  const start = useCallback((featureKeys: string[]) => {
    const features = featureKeys.filter((k) => FEATURE_TOURS[k]);
    if (!features.length) return;
    returnTo.current = activeFeatureKey;
    setState({ mode: 'tour', features, stage: 'welcome', fi: 0, ci: -1 });
  }, [activeFeatureKey]);

  const help = useCallback((featureKey: string) => {
    if (!FEATURE_TOURS[featureKey]) return;
    returnTo.current = null;
    setState({ mode: 'help', features: [featureKey], stage: 'feature', fi: 0, ci: -1 });
  }, []);

  // Ends whatever is running. Ending the full tour - finished or closed early -
  // records it, so it does not start again, and goes back to where the user was.
  const close = useCallback(() => {
    const was = stateRef.current;
    setState(null);
    if (was?.mode === 'tour') {
      onTourDone();
      if (returnTo.current) setActiveFeatureKey(returnTo.current);
    }
  }, [onTourDone, setActiveFeatureKey]);

  // The feature a card belongs to is the one on screen.
  const feature = state?.stage === 'feature' ? state.features[state.fi] : null;
  useEffect(() => {
    if (feature && feature !== activeFeatureKey) setActiveFeatureKey(feature);
    // Only on a change of card: a user clicking the sidebar mid-tour is not
    // pulled back on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [feature]);

  const nextFeature = useCallback(() => {
    setState((s) => {
      if (!s) return s;
      if (s.fi + 1 < s.features.length) return { ...s, stage: 'feature', fi: s.fi + 1, ci: -1 };
      return s.mode === 'tour' ? { ...s, stage: 'finish' } : null;
    });
  }, []);

  const advance = useCallback(() => {
    setState((s) => {
      if (!s) return s;
      if (s.stage === 'welcome') return { ...s, stage: 'feature', fi: 0, ci: -1 };
      const details = FEATURE_TOURS[s.features[s.fi]].details;
      if (s.ci + 1 < details.length) return { ...s, ci: s.ci + 1 };
      if (s.fi + 1 < s.features.length) return { ...s, fi: s.fi + 1, ci: -1 };
      return s.mode === 'tour' ? { ...s, stage: 'finish' } : null;
    });
  }, []);

  const back = useCallback(() => {
    setState((s) => (s && s.ci >= 0 ? { ...s, ci: s.ci - 1 } : s));
  }, []);

  let card: TourCard | null = null;
  if (state?.stage === 'welcome') card = TOUR_WELCOME;
  else if (state?.stage === 'finish') card = TOUR_FINISH;
  else if (state && feature) {
    const t = FEATURE_TOURS[feature];
    card = state.ci < 0 ? t.overview : t.details[state.ci];
  }

  const overlay = state && card ? (
    <TourOverlay
      key={`${state.stage}-${state.fi}-${state.ci}`}
      card={card}
      state={state}
      onClose={close}
      onSkip={nextFeature}
      onAdvance={advance}
      onBack={back}
      onFinish={close}
    />
  ) : null;

  return { start, help, active: !!state, overlay };
}

// ---------------------------------------------------------------------------

interface OverlayProps {
  card: TourCard;
  state: TourState;
  onClose: () => void;
  onSkip: () => void;
  onAdvance: () => void;
  onBack: () => void;
  onFinish: () => void;
}

function findTarget(name?: string): HTMLElement | null {
  if (!name || typeof document === 'undefined') return null;
  const el = document.querySelector<HTMLElement>(`[data-tour="${name}"]`);
  // A collapsed or hidden section has no box to point at.
  return el && el.getClientRects().length ? el : null;
}

function TourOverlay({ card, state, onClose, onSkip, onAdvance, onBack, onFinish }: OverlayProps) {
  const [target, setTarget] = useState<HTMLElement | null>(() => findTarget(card.target));
  const [searching, setSearching] = useState(() => !!card.target && !findTarget(card.target));
  const [spot, setSpot] = useState<Box | null>(null);
  const [place, setPlace] = useState<{ top: number; left: number; width: number } | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const primaryRef = useRef<HTMLButtonElement>(null);

  // Wait for the target: a feature just switched to renders after its data.
  useEffect(() => {
    if (!searching) return;
    const found = () => {
      const el = findTarget(card.target);
      if (!el) return false;
      setTarget(el);
      setSearching(false);
      return true;
    };
    if (found()) return;
    const obs = new MutationObserver(() => { found(); });
    obs.observe(document.body, { childList: true, subtree: true, attributes: true });
    const giveUp = setTimeout(() => setSearching(false), TARGET_WAIT_MS);
    return () => { obs.disconnect(); clearTimeout(giveUp); };
  }, [searching, card.target]);

  useEffect(() => {
    if (!target) return;
    const r = target.getBoundingClientRect();
    if (r.top < MARGIN || r.bottom > window.innerHeight - MARGIN) {
      target.scrollIntoView({ block: r.height > window.innerHeight * 0.6 ? 'start' : 'center', behavior: 'smooth' });
    }
  }, [target]);

  const position = useCallback(() => {
    const vw = window.innerWidth, vh = window.innerHeight;
    const width = Math.min(WIDTH, vw - 2 * MARGIN);
    const h = cardRef.current?.offsetHeight ?? 220;
    if (!target) {
      setSpot(null);
      setPlace({ top: Math.max(MARGIN, (vh - h) / 2), left: (vw - width) / 2, width });
      return;
    }
    const r = target.getBoundingClientRect();
    // The spotlight is kept inside the window: a long feed is lit only where
    // it is on screen.
    const top = Math.max(r.top - PAD, MARGIN / 2);
    const bottom = Math.min(r.bottom + PAD, vh - MARGIN / 2);
    const box = { top, left: r.left - PAD, width: r.width + 2 * PAD, height: Math.max(0, bottom - top) };
    setSpot(box);

    let left = Math.max(MARGIN, Math.min(r.left, vw - width - MARGIN));
    let cardTop: number;
    if (vh - (box.top + box.height) - GAP - MARGIN >= h) cardTop = box.top + box.height + GAP;
    else if (box.top - GAP - MARGIN >= h) cardTop = box.top - GAP - h;
    else if (vw - (box.left + box.width) - GAP - MARGIN >= width) {
      // Beside it, when it fills the height (the sidebar, a tall section).
      left = box.left + box.width + GAP;
      cardTop = Math.max(MARGIN, Math.min(box.top, vh - h - MARGIN));
    } else {
      // No room around it: over its lower part, still on screen.
      cardTop = vh - h - MARGIN;
    }
    setPlace({ top: cardTop, left, width });
  }, [target]);

  useLayoutEffect(() => { position(); }, [position, searching]);

  useEffect(() => {
    const follow = () => position();
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('resize', follow);
    window.addEventListener('scroll', follow, true);
    document.addEventListener('keydown', onKey);
    // Content around the target can still be loading and move it.
    const settle = setInterval(follow, 400);
    return () => {
      window.removeEventListener('resize', follow);
      window.removeEventListener('scroll', follow, true);
      document.removeEventListener('keydown', onKey);
      clearInterval(settle);
    };
  }, [position, onClose]);

  useEffect(() => { primaryRef.current?.focus({ preventScroll: true }); }, []);

  if (typeof document === 'undefined') return null;

  const { mode, stage, features, fi, ci } = state;
  const featureKey = features[fi];
  const details = stage === 'feature' ? FEATURE_TOURS[featureKey].details : [];
  const isOverview = stage === 'feature' && ci < 0;
  const isLastDetail = stage === 'feature' && ci === details.length - 1;
  const isLastFeature = fi === features.length - 1;

  let progress = '';
  if (stage === 'feature') {
    progress = mode === 'tour'
      ? `Feature ${fi + 1} of ${features.length}`
      : featureLabel(featureKey);
    if (!isOverview) progress += ` · ${ci + 1} of ${details.length}`;
  }

  const btn = 'px-3.5 py-1.5 rounded-xl text-xs font-bold transition';
  const primary = `${btn} bg-hp-navy text-white hover:opacity-90 shadow-sm`;
  const secondary = `${btn} bg-white text-slate-700 border border-slate-300 hover:bg-slate-50`;

  let buttons: React.ReactNode;
  if (stage === 'welcome') {
    buttons = (<>
      <button type="button" className={secondary} onClick={onClose}>Not now</button>
      <button type="button" ref={primaryRef} className={primary} onClick={onAdvance}>Start the tour</button>
    </>);
  } else if (stage === 'finish') {
    buttons = <button type="button" ref={primaryRef} className={primary} onClick={onFinish}>Done</button>;
  } else if (isOverview) {
    buttons = (<>
      <button type="button" className={secondary} onClick={mode === 'help' ? onClose : onSkip}>
        {mode === 'help' ? 'Close' : 'Skip'}
      </button>
      {details.length > 0 && (
        <button type="button" ref={primaryRef} className={primary} onClick={onAdvance}>Dive in</button>
      )}
    </>);
  } else {
    const nextLabel = isLastDetail
      ? (mode === 'help' ? 'Done' : isLastFeature ? 'Finish' : 'Next feature')
      : 'Next';
    buttons = (<>
      <button type="button" className={secondary} onClick={onBack}>Back</button>
      <button type="button" ref={primaryRef} className={primary} onClick={onAdvance}>{nextLabel}</button>
    </>);
  }

  return createPortal(
    <div className="fixed inset-0 z-[1100]" aria-live="polite">
      {/* Catches clicks on the page while a card is open; the dimming is the
          spotlight's shadow, or this layer when there is nothing to light. */}
      <div
        className={`absolute inset-0 ${spot ? '' : 'bg-slate-900/55'}`}
        onClick={(e) => e.stopPropagation()}
      />
      {spot && (
        <div
          aria-hidden
          className="absolute rounded-xl ring-2 ring-white/90 pointer-events-none transition-all duration-200 motion-reduce:transition-none"
          style={{ ...spot, boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.55)' }}
        />
      )}
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-label={card.title}
        style={{
          position: 'absolute',
          top: place?.top ?? -9999,
          left: place?.left ?? -9999,
          width: place?.width ?? WIDTH,
          visibility: place && !searching ? 'visible' : 'hidden',
        }}
        className="bg-white border border-slate-200 rounded-2xl shadow-2xl p-5 text-left animate-fade-in motion-reduce:animate-none"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {progress && (
              <p className="text-[10px] font-extrabold uppercase tracking-wider text-hp-navy mb-1">{progress}</p>
            )}
            <h2 className="text-base font-extrabold text-slate-900 leading-snug">{card.title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={mode === 'tour' ? 'End the tour' : 'Close'}
            title={mode === 'tour' ? 'End the tour' : 'Close'}
            className="text-slate-400 hover:text-slate-700 p-1 rounded -mr-1 -mt-1"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <p className="mt-2 text-sm text-slate-700 leading-relaxed">{card.body}</p>
        {card.points && card.points.length > 0 && (
          <ul className="mt-2 space-y-1.5">
            {card.points.map((p) => (
              <li key={p} className="flex gap-2 text-sm text-slate-700 leading-relaxed">
                <span className="text-hp-navy flex-shrink-0">•</span>
                <span>{p}</span>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-4 flex items-center justify-end gap-2">{buttons}</div>
      </div>
    </div>,
    document.body,
  );
}
