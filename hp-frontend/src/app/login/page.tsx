'use client';

import React, { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { Shield, User as UserIcon, Lock, Mail, AlertCircle, Loader2 } from 'lucide-react';

export default function LoginPage() {
  const [activeTab, setActiveTab] = useState<'user' | 'admin'>('user');
  const [email, setEmail] = useState('user@hp.com');
  const [password, setPassword] = useState('UserPassword123!');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { login, isAuthenticated, user } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (isAuthenticated && user) {
      if (user.role === 'admin') {
        router.push('/admin/platform');
      } else {
        router.push('/dashboard');
      }
    }
  }, [isAuthenticated, user, router]);

  const handleTabSwitch = (tab: 'user' | 'admin') => {
    setActiveTab(tab);
    setError(null);
    if (tab === 'admin') {
      setEmail('admin@hp.com');
      setPassword('AdminPassword123!');
    } else {
      setEmail('user@hp.com');
      setPassword('UserPassword123!');
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsSubmitting(true);

    const result = await login(email, password);
    setIsSubmitting(false);

    if (result.success) {
      if (result.role === 'admin') {
        router.push('/admin/platform');
      } else {
        router.push('/dashboard');
      }
    } else {
      setError(result.error || 'Authentication failed. Please check credentials.');
    }
  };

  return (
    <div className="min-h-screen bg-[#0B132B] text-white flex flex-col justify-center py-12 sm:px-6 lg:px-8">
      <div className="sm:mx-auto sm:w-full sm:max-w-md text-center">
        <div className="inline-flex items-center justify-center bg-hp-navy text-white p-3 rounded-full text-3xl font-extrabold tracking-widest shadow-2xl border-2 border-white/20">
          HP
        </div>
        <h2 className="mt-4 text-center text-2xl font-extrabold text-white tracking-tight">
          Account Intelligence
        </h2>
        <p className="mt-1 text-center text-xs text-gray-400 font-medium">
          Target Account Sales & ABM Platform
        </p>
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-[#1C2541] py-8 px-4 shadow-2xl rounded-2xl sm:px-10 border border-slate-700/80">
          
          {/* Role Selector Tabs */}
          <div className="flex bg-[#0B132B] p-1 rounded-xl mb-6 border border-slate-800">
            <button
              type="button"
              onClick={() => handleTabSwitch('user')}
              className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-xs font-bold transition duration-200 ${
                activeTab === 'user'
                  ? 'bg-hp-navy text-white shadow-md'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <UserIcon className="w-4 h-4 text-hp-accent" />
              <span>Sales User</span>
            </button>
            <button
              type="button"
              onClick={() => handleTabSwitch('admin')}
              className={`flex-1 flex items-center justify-center space-x-2 py-2.5 rounded-lg text-xs font-bold transition duration-200 ${
                activeTab === 'admin'
                  ? 'bg-emerald-600 text-white shadow-md'
                  : 'text-gray-400 hover:text-white'
              }`}
            >
              <Shield className="w-4 h-4 text-emerald-400" />
              <span>Administrator</span>
            </button>
          </div>

          {/* Error Banner */}
          {error && (
            <div className="mb-4 bg-red-950/80 border-l-4 border-red-500 p-3.5 rounded-r-lg flex items-start space-x-3">
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
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 bg-[#0B132B] border border-slate-700 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent transition"
                  placeholder="name@hp.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-gray-300 uppercase tracking-wider mb-1">
                Password
              </label>
              <div className="relative rounded-md shadow-sm">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Lock className="h-4 w-4 text-gray-400" />
                </div>
                <input
                  type="password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="block w-full pl-10 pr-3 py-2.5 bg-[#0B132B] border border-slate-700 rounded-lg text-xs text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-hp-navy focus:border-transparent transition"
                  placeholder="••••••••••••"
                />
              </div>
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
                <span>Sign In as {activeTab === 'admin' ? 'Administrator' : 'Sales User'}</span>
              )}
            </button>
          </form>

          {/* Test Credentials Helper */}
          <div className="mt-6 pt-5 border-t border-slate-800 text-[11px] text-gray-400">
            <p className="font-semibold text-gray-300 mb-1.5">Test Credentials Quick Reference:</p>
            <div className="bg-[#0B132B] p-2.5 rounded-lg border border-slate-800 font-mono space-y-0.5 text-[10px]">
              <div><span className="font-bold text-gray-300">User:</span> user@hp.com / UserPassword123!</div>
              <div><span className="font-bold text-gray-300">Admin:</span> admin@hp.com / AdminPassword123!</div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
