'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, KeyRound, Loader2, Mail, ShieldCheck } from 'lucide-react';
import api from '@/services/api';
import { parseApiError } from '@/lib/apiError';
import { ACTION_FAILED, NEW_PASSWORD_REFUSED } from '@/lib/uiCopy';
import { ParallaxBand } from '@/components/common/motion';
import { PasswordInput } from '@/components/common/PasswordInput';
import { RecoveryCodeNotice } from '@/components/common/RecoveryCodeNotice';
import HpLogo from '@/components/common/HpLogo';

// Mirrors MIN_PASSWORD_LENGTH in hp-backend/src/app/core/security.py.
const MIN_LENGTH = 8;

const label = 'block text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-1';
const plainInput =
  'block w-full pl-10 pr-3 py-2.5 bg-[#0B132B] border border-slate-700 rounded-lg text-xs text-white '
  + 'placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent transition';

/**
 * Forgot password: set a new one with the recovery code saved the last time a
 * password was set. No sign-in and no admin needed. Without a code, an admin
 * can issue a temporary password from the Users page.
 */
export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [newCode, setNewCode] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    if (next.length < MIN_LENGTH) {
      setError(`Your new password must be at least ${MIN_LENGTH} characters.`);
      return;
    }
    if (next !== confirm) {
      setError('The two new passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      const res = await api.post<{ recovery_code: string }>('/auth/forgot-password', {
        email: email.trim(), recovery_code: code.trim(), new_password: next,
      });
      setNewCode(res.data.recovery_code);
    } catch (err) {
      // This page's own wording for what the user can fix; never the server's.
      const e = parseApiError(err);
      setError(e.code === 'INVALID_CREDENTIALS' ? 'That email and recovery code do not match.'
        : e.code === 'VALIDATION_ERROR' && e.fields?.new_password ? NEW_PASSWORD_REFUSED
          : ACTION_FAILED);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ParallaxBand fadeOnScroll={false} className="min-h-screen text-white flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="as-rise sm:mx-auto sm:w-full sm:max-w-md text-center">
        <HpLogo size={64} onDark className="mx-auto" />
        <h2 className="mt-4 text-center text-2xl font-extrabold text-white tracking-tight">
          {newCode ? 'New password set' : 'Forgot your password?'}
        </h2>
        {!newCode && (
          <p className="mt-1 text-center text-xs text-gray-400 font-medium">
            Use the recovery code you saved when you last set your password.
          </p>
        )}
      </div>

      <div className="as-rise mt-8 sm:mx-auto sm:w-full sm:max-w-md" style={{ ['--as-delay' as string]: '90ms' }}>
        <div className="as-glass-dark py-8 px-4 rounded-2xl sm:px-10">
          {newCode ? (
            <RecoveryCodeNotice code={newCode} onDone={() => { window.location.href = '/login?changed=1'; }} />
          ) : (
            <>
              {error && (
                <div className="mb-4 bg-red-950/80 as-fade border border-red-500/40 p-3.5 rounded-xl flex items-start space-x-3">
                  <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
                  <p className="text-xs text-red-200 font-medium">{error}</p>
                </div>
              )}

              <form className="space-y-4" onSubmit={submit}>
                <div>
                  <label className={label}>Email address</label>
                  <div className="relative rounded-md shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Mail className="h-4 w-4 text-gray-400" />
                    </div>
                    <input type="email" required autoComplete="username" value={email}
                           onChange={(e) => setEmail(e.target.value)} placeholder="name@hp.com" className={plainInput} />
                  </div>
                </div>
                <div>
                  <label className={label}>Recovery code</label>
                  <div className="relative rounded-md shadow-sm">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <ShieldCheck className="h-4 w-4 text-gray-400" />
                    </div>
                    <input type="text" required autoComplete="off" spellCheck={false} autoCapitalize="characters"
                           value={code} onChange={(e) => setCode(e.target.value)} placeholder="XXXX-XXXX-XXXX-XXXX"
                           className={`${plainInput} font-mono tracking-wider`} />
                  </div>
                </div>
                <div>
                  <label className={label}>New password</label>
                  <PasswordInput value={next} onChange={setNext} autoComplete="new-password" />
                </div>
                <div>
                  <label className={label}>Confirm new password</label>
                  <PasswordInput value={confirm} onChange={setConfirm} autoComplete="new-password" />
                </div>
                <p className="text-[11px] text-gray-400">
                  At least {MIN_LENGTH} characters, different from your old password.
                </p>

                <button type="submit" disabled={busy}
                        className="w-full flex justify-center items-center py-3 px-4 rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue transition disabled:opacity-50 mt-2">
                  {busy ? (
                    <span className="flex items-center space-x-2"><Loader2 className="w-4 h-4 animate-spin" /><span>Saving...</span></span>
                  ) : (
                    <span className="flex items-center space-x-2"><KeyRound className="w-4 h-4" /><span>Set new password</span></span>
                  )}
                </button>
              </form>

              <div className="mt-5 pt-4 border-t border-slate-800 text-[11px] text-gray-400 space-y-2 text-center">
                <p>No recovery code? Ask your admin to reset your password from the Users page.</p>
                <Link href="/login" className="font-semibold text-sky-300 hover:text-white">Back to sign in</Link>
              </div>
            </>
          )}
        </div>
      </div>
    </ParallaxBand>
  );
}
