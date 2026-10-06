'use client';

// The ⓘ beside a score: one click opens a short, plain-language card saying
// how the score is worked out (client request, 6 Oct). The wording lives in
// lib/scoreExplanations.ts so it can be reviewed in one place. Styled like the
// urgency driver popover it sits beside.

import { useEffect, useRef, useState } from 'react';
import { Info, X } from 'lucide-react';
import { SCORE_EXPLANATIONS, type ScoreTopic } from '@/lib/scoreExplanations';

interface ScoreInfoProps {
  topic: ScoreTopic;
  /** Which edge of the icon the card lines up with. Use 'right' near the right of the page. */
  align?: 'left' | 'right';
  className?: string;
}

export default function ScoreInfo({ topic, align = 'left', className = '' }: ScoreInfoProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const info = SCORE_EXPLANATIONS[topic];

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <span ref={ref} className={`relative inline-flex align-middle normal-case tracking-normal ${className}`}>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); e.preventDefault(); setOpen((v) => !v); }}
        title={info.title}
        aria-label={info.title}
        aria-expanded={open}
        className="text-slate-400 hover:text-slate-700 p-0.5 rounded transition"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
      {open && (
        <span
          role="dialog"
          aria-label={info.title}
          onClick={(e) => e.stopPropagation()}
          className={`absolute ${align === 'right' ? 'right-0' : 'left-0'} top-full mt-2 w-80 max-w-[calc(100vw-2rem)] bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 z-50 animate-fade-in text-xs text-left font-normal text-slate-700 cursor-default block`}
        >
          <span className="flex items-start justify-between gap-2 border-b border-slate-100 pb-2 mb-2">
            <span className="font-bold text-slate-900 text-[13px]">{info.title}</span>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close"
              className="text-slate-400 hover:text-slate-700 p-0.5 rounded">
              <X className="w-3.5 h-3.5" />
            </button>
          </span>
          <span className="block leading-relaxed">{info.intro}</span>
          <span className="block mt-2 space-y-1.5">
            {info.points.map((p) => (
              <span key={p} className="flex gap-2 leading-relaxed">
                <span className="text-hp-navy flex-shrink-0">•</span>
                <span>{p}</span>
              </span>
            ))}
          </span>
          {'note' in info && info.note && (
            <span className="block mt-2 pt-2 border-t border-slate-100 text-slate-500 leading-relaxed">{info.note}</span>
          )}
        </span>
      )}
    </span>
  );
}
