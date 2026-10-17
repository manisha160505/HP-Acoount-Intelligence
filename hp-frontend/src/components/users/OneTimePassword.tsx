'use client';

import React, { useState } from 'react';
import { Check, Copy, KeyRound } from 'lucide-react';

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      aria-label={`Copy ${label}`}
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        });
      }}
      className="p-1.5 rounded-md text-gray-500 hover:text-hp-navy hover:bg-white transition"
    >
      {done ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
    </button>
  );
}

/**
 * A temporary password the server just generated. It is shown here once and
 * stored nowhere but as a hash: closing this is the last chance to copy it.
 */
export function OneTimePassword({ email, password }: { email: string; password: string }) {
  return (
    <div className="space-y-3">
      <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-900">
        Copy this now and share it with the user privately. It will not be shown again.
        They must set their own password when they first sign in.
      </div>
      <div className="rounded-xl border border-gray-200 bg-gray-50 divide-y divide-gray-200 text-sm">
        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500 w-24">Email</span>
          <span className="flex-1 font-medium text-gray-900 break-all">{email}</span>
          <CopyButton text={email} label="email" />
        </div>
        <div className="flex items-center justify-between px-3 py-2.5">
          <span className="text-[11px] font-bold uppercase tracking-wider text-gray-500 w-24 inline-flex items-center gap-1">
            <KeyRound className="w-3 h-3" /> Password
          </span>
          <code className="flex-1 font-mono text-base tracking-wide text-gray-900">{password}</code>
          <CopyButton text={password} label="password" />
        </div>
      </div>
    </div>
  );
}
