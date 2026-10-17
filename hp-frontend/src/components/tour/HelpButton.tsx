'use client';

// The ? beside a feature's title: replays that feature's walkthrough from the
// product tour (components/tour/useTour.tsx) whenever the user wants it.

import { HelpCircle } from 'lucide-react';

interface HelpButtonProps {
  onClick: () => void;
  className?: string;
}

export default function HelpButton({ onClick, className = '' }: HelpButtonProps) {
  return (
    <button
      type="button"
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title="How this feature works"
      aria-label="How this feature works"
      className={`inline-flex items-center text-slate-400 hover:text-hp-navy p-0.5 rounded transition align-middle ${className}`}
    >
      <HelpCircle className="w-4 h-4" />
    </button>
  );
}
