'use client';

// The ⓘ beside a score: one click opens a short, plain-language card saying
// what goes into the score, the rule, and (where the page has the numbers)
// this account's own sum. The wording lives in lib/scoreExplanations.ts.
//
// The card is rendered into document.body with fixed positioning, measured
// from the icon. Inside the page it was clipped by any parent with overflow
// hidden and painted over by the next card (6 Oct, Live Signals); a portal
// sits above all of that. It opens below the icon when there is room, above
// it when there is not, stays inside the window horizontally, and follows the
// icon on scroll and resize.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Info, X } from 'lucide-react';
import { SCORE_EXPLANATIONS, type ScoreTopic } from '@/lib/scoreExplanations';

interface ScoreInfoProps {
  topic: ScoreTopic;
  /** Which edge of the icon the card lines up with. Use 'right' near the right of the page. */
  align?: 'left' | 'right';
  /** This account's own sum, e.g. "95 × 20% + 70 × 25% + … = 69.35 → 69". */
  worked?: string | null;
  className?: string;
}

const GAP = 8;        // between icon and card
const MARGIN = 16;    // kept clear of the window edges
const WIDTH = 416;    // 26rem

interface Placement { top: number; left: number; width: number; maxHeight: number }

export default function ScoreInfo({ topic, align = 'left', worked, className = '' }: ScoreInfoProps) {
  const [open, setOpen] = useState(false);
  const [place, setPlace] = useState<Placement | null>(null);
  const anchorRef = useRef<HTMLButtonElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const info = SCORE_EXPLANATIONS[topic];

  const position = useCallback(() => {
    const btn = anchorRef.current;
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const vw = window.innerWidth, vh = window.innerHeight;
    const width = Math.min(WIDTH, vw - 2 * MARGIN);
    let left = align === 'right' ? r.right - width : r.left;
    left = Math.max(MARGIN, Math.min(left, vw - width - MARGIN));

    // The whole card is always shown: below the icon if it fits there, above
    // if it fits there, otherwise moved up just enough to fit in the window
    // (it may then cover the icon - its own close button is in reach). Only a
    // card taller than the whole window scrolls.
    const avail = vh - 2 * MARGIN;
    const h = Math.min(cardRef.current?.scrollHeight ?? 0, avail);
    let top: number;
    if (vh - r.bottom - GAP - MARGIN >= h) top = r.bottom + GAP;
    else if (r.top - GAP - MARGIN >= h) top = r.top - GAP - h;
    else top = Math.max(MARGIN, Math.min(r.bottom + GAP, vh - MARGIN - h));
    setPlace({ top, left, width, maxHeight: avail });
  }, [align]);

  // Measure once the card has rendered (its height decides up or down).
  useLayoutEffect(() => {
    if (open) position();
  }, [open, position, worked]);

  useEffect(() => {
    if (!open) return;
    const outside = (e: MouseEvent) => {
      const t = e.target as Node;
      if (anchorRef.current?.contains(t) || cardRef.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    const follow = () => position();
    document.addEventListener('mousedown', outside);
    document.addEventListener('keydown', onKey);
    window.addEventListener('resize', follow);
    window.addEventListener('scroll', follow, true);   // any scrolling container
    return () => {
      document.removeEventListener('mousedown', outside);
      document.removeEventListener('keydown', onKey);
      window.removeEventListener('resize', follow);
      window.removeEventListener('scroll', follow, true);
    };
  }, [open, position]);

  const card = open && typeof document !== 'undefined' ? createPortal(
    <div
      ref={cardRef}
      role="dialog"
      aria-label={info.title}
      // A portal still bubbles React events to the icon's parents (a card
      // that expands on click, say); the card's clicks stay its own.
      onClick={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      style={{
        position: 'fixed',
        top: place?.top ?? -9999,
        left: place?.left ?? -9999,
        width: place?.width ?? WIDTH,
        maxHeight: place?.maxHeight,
        visibility: place ? 'visible' : 'hidden',
      }}
      className="z-[1000] overflow-y-auto bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 animate-fade-in text-xs text-left font-normal normal-case tracking-normal text-slate-700 cursor-default"
    >
      <div className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
        <span className="font-bold text-slate-900 text-[13px]">{info.title}</span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close"
          className="text-slate-400 hover:text-slate-700 p-0.5 rounded">
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
      <p className="leading-relaxed">{info.intro}</p>
      <ul className="mt-2 space-y-1.5">
        {info.points.map((p) => (
          <li key={p} className="flex gap-2 leading-relaxed">
            <span className="text-hp-navy flex-shrink-0">•</span>
            <span>{p}</span>
          </li>
        ))}
      </ul>
      {'rules' in info && info.rules && info.rules.length > 0 && (
        <div className="mt-3 rounded-xl bg-slate-50 border border-slate-200 px-3 py-2">
          <p className="text-[10px] font-extrabold uppercase tracking-wider text-hp-navy mb-1">The rule</p>
          <div className="space-y-1">
            {info.rules.map((r) => (
              <p key={r} className="leading-relaxed text-slate-700">{r}</p>
            ))}
          </div>
        </div>
      )}
      {worked && (
        <div className="mt-2 rounded-xl bg-blue-50/70 border border-blue-100 px-3 py-2">
          <p className="text-[10px] font-extrabold uppercase tracking-wider text-hp-navy mb-1">For this account</p>
          <p className="font-mono text-[11px] text-slate-800 leading-relaxed break-words">{worked}</p>
        </div>
      )}
      {'note' in info && info.note && (
        <p className="mt-2 pt-2 border-t border-slate-100 text-slate-500 leading-relaxed">{info.note}</p>
      )}
    </div>,
    document.body,
  ) : null;

  return (
    <span className={`inline-flex align-middle normal-case tracking-normal ${className}`}>
      <button
        ref={anchorRef}
        type="button"
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); setPlace(null); setOpen((v) => !v); }}
        title={info.title}
        aria-label={info.title}
        aria-expanded={open}
        className="text-slate-400 hover:text-slate-700 p-0.5 rounded transition"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {card}
    </span>
  );
}
