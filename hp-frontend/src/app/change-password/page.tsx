'use client';

import React, { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { ParallaxBand } from '@/components/common/motion';
import { AlertCircle, Loader2, KeyRound } from 'lucide-react';
import { PasswordInput } from '@/components/common/PasswordInput';
import HpLogo from '@/components/common/HpLogo';
import { RecoveryCodeNotice } from '@/components/common/RecoveryCodeNotice';
import { clearSession } from '@/lib/session';

// Mirrors MIN_PASSWORD_LENGTH in hp-backend/src/app/core/security.py; the
// server is the authority, this only saves a round trip.
const MIN_LENGTH = 8;

function PasswordField({ label, value, onChange, autoComplete }: {
  label: string; value: string; onChange: (v: string) => void; autoComplete: string;
}) {
  return (
    <div>
      <label className="block text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-1">
        {label}
      </label>
      <PasswordInput value={value} onChange={onChange} autoComplete={autoComplete} />
    </div>
  );
}

export default function ChangePasswordPage() {
  const { user, isAuthenticated, isLoading, changePassword, logout } = useAuth();
  const router = useRouter();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [recoveryCode, setRecoveryCode] = useState<string | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated && !recoveryCode) router.push('/login');
  }, [isLoading, isAuthenticated, recoveryCode, router]);

  const forced = !!user?.must_change_password;

  const handleSubmit = async (e: React.FormEvent) => {
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
    if (next === current) {
      setError('Your new password must be different from your old password.');
      return;
    }
    setIsSubmitting(true);
    const result = await changePassword(current, next);
    setIsSubmitting(false);
    if (result.success && result.recoveryCode) {
      // Every session has ended; show the recovery code once before sign-in.
      setRecoveryCode(result.recoveryCode);
    } else if (result.success) {
      clearSession();
      // Every session was ended, this one included.
      window.location.href = '/login?changed=1';
    } else {
      setError(result.error || 'Could not change the password.');
    }
  };

  if (recoveryCode) {
    return (
      <ParallaxBand fadeOnScroll={false} className="min-h-screen text-white flex flex-col justify-center py-12 sm:px-6 lg:px-8">
        <div className="as-rise sm:mx-auto sm:w-full sm:max-w-md text-center">
          <HpLogo size={64} onDark className="mx-auto" />
        </div>
        <div className="as-rise mt-8 sm:mx-auto sm:w-full sm:max-w-md">
          <div className="as-glass-dark py-8 px-4 rounded-2xl sm:px-10">
            <RecoveryCodeNotice code={recoveryCode} onDone={() => {
              clearSession();
              window.location.href = '/login?changed=1';
            }} />
          </div>
        </div>
      </ParallaxBand>
    );
  }

  if (isLoading || !isAuthenticated) return null;

  return (
    <ParallaxBand fadeOnScroll={false} className="min-h-screen text-white flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="as-rise sm:mx-auto sm:w-full sm:max-w-md text-center">
        <HpLogo size={64} onDark className="mx-auto" />
        <h2 className="mt-4 text-center text-2xl font-extrabold text-white tracking-tight">
          {forced ? 'Set your password' : 'Change your password'}
        </h2>
        <p className="mt-1 text-center text-xs text-gray-400 font-medium">
          {forced
            ? 'Replace the password you were given before you continue.'
            : `Signed in as ${user?.email}`}
        </p>
      </div>

      <div className="as-rise mt-8 sm:mx-auto sm:w-full sm:max-w-md" style={{ ['--as-delay' as string]: '90ms' }}>
        <div className="as-glass-dark py-8 px-4 rounded-2xl sm:px-10">
          {error && (
            <div className="mb-4 bg-red-950/80 as-fade border border-red-500/40 p-3.5 rounded-xl flex items-start space-x-3">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-200 font-medium">{error}</p>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <PasswordField label="Old password"
                           value={current} onChange={setCurrent} autoComplete="current-password" />
            <PasswordField label="New password" value={next} onChange={setNext}
                           autoComplete="new-password" />
            <PasswordField label="Confirm new password" value={confirm} onChange={setConfirm}
                           autoComplete="new-password" />
            <p className="text-[11px] text-gray-400">
              At least {MIN_LENGTH} characters, different from your old password.
              You will sign in again with the new one.
            </p>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition duration-150 disabled:opacity-50 mt-2"
            >
              {isSubmitting ? (
                <span className="flex items-center space-x-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Saving...</span>
                </span>
              ) : (
                <span className="flex items-center space-x-2">
                  <KeyRound className="w-4 h-4" />
                  <span>Save new password</span>
                </span>
              )}
            </button>
          </form>

          <div className="mt-5 text-center">
            {forced ? (
              <button type="button" onClick={() => { void logout(); }}
                      className="text-[11px] text-gray-400 hover:text-white underline">
                Sign out
              </button>
            ) : (
              <button type="button" onClick={() => router.back()}
                      className="text-[11px] text-gray-400 hover:text-white underline">
                Cancel
              </button>
            )}
          </div>
        </div>
      </div>
    </ParallaxBand>
  );
}
