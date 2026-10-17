'use client';

import React, { useEffect, useRef, useState } from 'react';
import { MoreHorizontal } from 'lucide-react';

export interface RowMenuItem {
  label: string;
  icon: React.ReactNode;
  onSelect: () => void;
  /** Shown last, after a divider, in red. */
  danger?: boolean;
}

const MENU_WIDTH = 208;

/** The bordered button that sits beside a RowMenu in a table row. */
export const ROW_BUTTON =
  'inline-flex items-center gap-1.5 h-8 px-3 rounded-lg border border-gray-200 bg-white text-[11px] '
  + 'font-bold text-gray-700 hover:bg-gray-50 hover:border-gray-300 transition disabled:opacity-50 whitespace-nowrap';
/** Its icon-only, destructive sibling (delete). */
export const ROW_ICON_BUTTON_DANGER =
  'inline-flex items-center justify-center w-8 h-8 rounded-lg border border-gray-200 bg-white text-gray-400 '
  + 'hover:text-red-600 hover:border-red-200 hover:bg-red-50 transition disabled:opacity-50';

/**
 * The "..." menu at the end of a table row (Users, Platform). Placed with fixed positioning
 * from the button's own rectangle, so the table's horizontal scroll area
 * cannot clip it; it opens upward when there is no room below. Closes on
 * Escape, an outside click, a scroll or a resize.
 */
export function RowMenu({ items, label }: { items: RowMenuItem[]; label: string }) {
  const [open, setOpen] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; up: boolean }>({ top: 0, left: 0, up: false });
  const button = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);

  const place = () => {
    const r = button.current?.getBoundingClientRect();
    if (!r) return;
    const height = items.length * 36 + 16;
    const up = r.bottom + height + 8 > window.innerHeight && r.top > height + 8;
    setPos({ top: up ? r.top - height - 6 : r.bottom + 6, left: Math.max(8, r.right - MENU_WIDTH), up });
  };

  useEffect(() => {
    if (!open) return;
    const close = (e: Event) => {
      if (e.type === 'keydown' && (e as KeyboardEvent).key !== 'Escape') return;
      if (e.type === 'mousedown' && (menu.current?.contains(e.target as Node)
          || button.current?.contains(e.target as Node))) return;
      setOpen(false);
    };
    window.addEventListener('mousedown', close);
    window.addEventListener('keydown', close);
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    menu.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {
      window.removeEventListener('mousedown', close);
      window.removeEventListener('keydown', close);
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [open]);

  const regular = items.filter((i) => !i.danger);
  const danger = items.filter((i) => i.danger);

  const item = (i: RowMenuItem) => (
    <button
      key={i.label}
      type="button"
      role="menuitem"
      onClick={() => { setOpen(false); i.onSelect(); }}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-xs font-semibold rounded-md text-left transition focus:outline-none ${
        i.danger
          ? 'text-red-600 hover:bg-red-50 focus:bg-red-50'
          : 'text-gray-700 hover:bg-slate-100 focus:bg-slate-100'
      }`}
    >
      <span className={i.danger ? 'text-red-500' : 'text-gray-400'}>{i.icon}</span>
      {i.label}
    </button>
  );

  return (
    <>
      <button
        ref={button}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        title="More actions"
        onClick={() => { if (!open) place(); setOpen((o) => !o); }}
        className={`inline-flex items-center justify-center w-8 h-8 rounded-lg border transition ${
          open
            ? 'border-hp-navy/30 bg-hp-navy/5 text-hp-navy'
            : 'border-gray-200 text-gray-500 hover:text-gray-800 hover:bg-gray-50'
        }`}
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {open && (
        <div
          ref={menu}
          role="menu"
          aria-label={label}
          style={{ top: pos.top, left: pos.left, width: MENU_WIDTH }}
          className="fixed z-50 bg-white rounded-xl border border-gray-200 shadow-xl p-1.5 as-fade"
        >
          {regular.map(item)}
          {danger.length > 0 && regular.length > 0 && <div className="my-1.5 border-t border-gray-100" />}
          {danger.map(item)}
        </div>
      )}
    </>
  );
}
