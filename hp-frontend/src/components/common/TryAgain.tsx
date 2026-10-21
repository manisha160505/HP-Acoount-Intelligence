'use client';

import React from 'react';
import { RefreshCw } from 'lucide-react';

/**
 * What a page or panel shows when its data did not load: a neutral button
 * that runs the fetch again - no error message (client rule, approved).
 */
export function TryAgain({ onRetry, className = '', size = 'md', align = 'center' }: {
  onRetry: () => void;
  className?: string;
  size?: 'sm' | 'md';
  align?: 'center' | 'start';
}) {
  const pad = size === 'sm' ? 'px-2.5 py-1 text-[11px]' : 'px-3.5 py-2 text-xs';
  return (
    <div className={`flex ${align === 'start' ? 'justify-start' : 'justify-center'} ${className}`}>
      <button
        type="button"
        onClick={onRetry}
        className={`inline-flex items-center gap-1.5 rounded-lg font-bold text-white bg-[#0B132B] hover:bg-[#1C2541] transition-colors ${pad}`}
      >
        <RefreshCw className={size === 'sm' ? 'w-3 h-3' : 'w-3.5 h-3.5'} /> Try again
      </button>
    </div>
  );
}

export default TryAgain;
