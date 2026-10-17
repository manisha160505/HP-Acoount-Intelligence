'use client';

import React, { useState } from 'react';
import { Eye, EyeOff, Lock } from 'lucide-react';

/**
 * The dark password field of the sign-in and set-password screens, with an
 * eye button to show what was typed before submitting. Each field reveals on
 * its own; nothing is remembered between page loads.
 */
export function PasswordInput({ value, onChange, autoComplete, placeholder, id }: {
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  placeholder?: string;
  id?: string;
}) {
  const [shown, setShown] = useState(false);
  return (
    <div className="relative rounded-md shadow-sm">
      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <Lock className="h-4 w-4 text-gray-400" />
      </div>
      <input
        id={id}
        type={shown ? 'text' : 'password'}
        required
        autoComplete={autoComplete}
        spellCheck={false}
        autoCapitalize="off"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="block w-full pl-10 pr-10 py-2.5 bg-[#0B132B] border border-slate-700 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent transition"
      />
      <button
        type="button"
        onClick={() => setShown((s) => !s)}
        aria-label={shown ? 'Hide password' : 'Show password'}
        aria-pressed={shown}
        title={shown ? 'Hide password' : 'Show password'}
        className="absolute inset-y-0 right-0 pr-3 pl-2 flex items-center text-gray-400 hover:text-white focus:outline-none focus-visible:text-white transition"
      >
        {shown ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
}
