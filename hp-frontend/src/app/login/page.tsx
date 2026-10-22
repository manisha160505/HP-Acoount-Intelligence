'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { landingRouteFor } from '@/lib/accountSelection';
import { ParallaxBand } from '@/components/common/motion';
import { Mail, AlertCircle, Loader2 } from 'lucide-react';
import { PasswordInput } from '@/components/common/PasswordInput';
import HpLogo from '@/components/common/HpLogo';
import PoweredByBridgeAI from '@/components/common/PoweredByBridgeAI';
import { ACTION_FAILED } from '@/lib/uiCopy';

export default function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, isAuthenticated, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated && user) {
      router.push(landingRouteFor(user));
    }
  }, [isAuthenticated, user, router]);

  // Say why you are back here. The API client sends an expired session to
  // /login?expired=1; without this the screen looks like an ordinary sign-out
  // and the timeout stays invisible. Read from window.location rather than
  // useSearchParams, which would need a Suspense boundary for one flag.
  useEffect(() => {
    if (typeof window !== 'undefined'
        && new URLSearchParams(window.location.search).get('expired') === '1') {
      setError('Your session expired. Please sign in again.');
    }
    if (typeof window !== 'undefined'
        && new URLSearchParams(window.location.search).get('changed') === '1') {
      setNotice('Password changed. Sign in with your new password.');
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await login(email, password);
    setIsSubmitting(false);

    if (result.success) {
      router.push(landingRouteFor(result.user));
    } else {
      setError(result.error || ACTION_FAILED);
    }
  };

  return (
    <ParallaxBand fadeOnScroll={false} className="min-h-screen text-white flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="as-rise sm:mx-auto sm:w-full sm:max-w-md text-center">
        <HpLogo size={64} onDark className="mx-auto" />
        <h2 className="mt-4 text-center text-2xl font-extrabold text-white tracking-tight">
          Account Intelligence
        </h2>
        <p className="mt-1 text-center text-xs text-gray-400 font-medium">
          Target Account Sales & ABM Platform
        </p>
      </div>

      <div className="as-rise mt-8 sm:mx-auto sm:w-full sm:max-w-md" style={{ ['--as-delay' as string]: '90ms' }}>
        <div className="as-glass-dark py-8 px-4 rounded-2xl sm:px-10">
          
          {notice && !error && (
            <div className="mb-4 bg-emerald-950/70 as-fade border border-emerald-500/40 p-3.5 rounded-xl">
              <p className="text-xs text-emerald-200 font-medium">{notice}</p>
            </div>
          )}

          {/* Error Banner */}
          {error && (
            <div className="mb-4 bg-red-950/80 as-fade border border-red-500/40 p-3.5 rounded-xl flex items-start space-x-3">
              <AlertCircle className="w-4 h-4 text-red-400 flex-shrink-0 mt-0.5" />
              <p className="text-xs text-red-200 font-medium">{error}</p>
            </div>
          )}

          <form className="space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="block text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-1">
                Email Address
              </label>
              <div className="relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Mail className="h-4 w-4 text-gray-400" />
                </div>
                <input
                  type="email"
                  required
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 bg-[#0B132B] border border-slate-700 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent transition"
                  placeholder="name@hp.com"
                />
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-[10px] font-bold text-gray-300 uppercase tracking-wider">
                  Password
                </label>
                <Link href="/forgot-password" className="text-[11px] font-semibold text-sky-300 hover:text-white transition">
                  Forgot password?
                </Link>
              </div>
              <PasswordInput value={password} onChange={setPassword}
                             autoComplete="current-password" placeholder="••••••••••••" />
            </div>

            <button
              type="submit"
              disabled={isSubmitting}
              className="w-full flex justify-center items-center py-3 px-4 border border-transparent rounded-lg shadow-md text-xs font-bold text-white bg-hp-navy hover:bg-hp-blue focus:outline-none transition duration-150 disabled:opacity-50 mt-2"
            >
              {isSubmitting ? (
                <div className="flex items-center space-x-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Authenticating...</span>
                </div>
              ) : (
                <span>Sign In</span>
              )}
            </button>
          </form>

          <div className="mt-6 pt-5 border-t border-slate-700/60">
            <PoweredByBridgeAI tone="light" center />
          </div>
        </div>
      </div>
    </ParallaxBand>
  );
}
