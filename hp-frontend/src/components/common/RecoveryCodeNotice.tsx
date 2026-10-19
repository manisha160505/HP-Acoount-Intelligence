'use client';

import React, { useState } from 'react';
import { Check, Copy, ShieldCheck } from 'lucide-react';

/**
 * The recovery code a user gets each time they set a password, on the dark
 * sign-in screens. Shown once: it is stored only as a hash. With it, the user
 * can set a new password from "Forgot password?" without asking an admin.
 */
export function RecoveryCodeNotice({ code, onDone }: { code: string; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="space-y-5">
      <div className="flex items-start gap-3">
        <ShieldCheck className="w-5 h-5 text-emerald-400 flex-shrink-0 mt-0.5" />
        <div>
          <p className="text-sm font-bold text-white">Password saved. Keep your recovery code.</p>
          <p className="text-xs text-gray-300 mt-1 leading-relaxed">
            If you forget your password, use this code on the sign-in page under
            &ldquo;Forgot password?&rdquo; to set a new one yourself. It is shown only once and works once;
            you get a new code each time you set a password.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-700 bg-[#0B132B] px-4 py-3">
        <code className="font-mono text-lg tracking-[0.18em] text-white select-all">{code}</code>
        <button
          type="button"
          onClick={() => {
            void navigator.clipboard?.writeText(code).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
          aria-label="Copy recovery code"
          className="inline-flex items-center gap-1.5 text-xs font-bold text-gray-300 hover:text-white px-2 py-1.5 rounded-lg hover:bg-white/10 transition"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>

      <p className="text-[11px] text-gray-400">
        Save it somewhere safe, such as your password manager. Anyone with this code and your email can set
        your password.
      </p>

      <button
        type="button"
        onClick={onDone}
        className="w-full flex justify-center items-center py-3 px-4 rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue transition"
      >
        I&apos;ve saved it - continue to sign in
      </button>
    </div>
  );
}
