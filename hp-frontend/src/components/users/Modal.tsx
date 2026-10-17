'use client';

import React, { useEffect } from 'react';
import { X } from 'lucide-react';

/** The dialog shell the Users screen's forms sit in. Escape closes it. */
export function Modal({ title, icon, onClose, children, wide = false }: {
  title: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  wide?: boolean;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-fade-in"
         onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div role="dialog" aria-modal="true" aria-label={title}
           className={`bg-white rounded-2xl shadow-2xl w-full ${wide ? 'max-w-2xl' : 'max-w-md'} max-h-[90vh] flex flex-col overflow-hidden border border-gray-200`}>
        <div className="flex justify-between items-center px-6 py-4 bg-gray-50 border-b border-gray-200 flex-shrink-0">
          <h3 className="text-base font-bold text-gray-900 flex items-center gap-2 min-w-0">
            {icon}
            <span className="truncate">{title}</span>
          </h3>
          <button type="button" onClick={onClose} aria-label="Close"
                  className="text-gray-400 hover:text-gray-600 rounded-lg p-1">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function ModalActions({ children }: { children: React.ReactNode }) {
  return <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">{children}</div>;
}

export const secondaryButton =
  'px-4 py-2 text-xs font-bold text-gray-600 hover:text-gray-800 bg-gray-100 hover:bg-gray-200 rounded-lg transition';
export const primaryButton =
  'inline-flex items-center justify-center px-4 py-2 rounded-lg shadow-sm text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue transition disabled:opacity-50';
export const dangerButton =
  'inline-flex items-center justify-center px-4 py-2 rounded-lg shadow-sm text-xs font-bold text-white bg-red-600 hover:bg-red-700 transition disabled:opacity-50';
