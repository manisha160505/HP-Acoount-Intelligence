'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { LogOut, User as UserIcon, Shield } from 'lucide-react';

export const Navbar: React.FC = () => {
  const { user, isAuthenticated, logout } = useAuth();
  const pathname = usePathname();

  if (!isAuthenticated || !user) return null;

  // On /dashboard, the Left Sidebar handles primary branding & navigation to match Northstar UI
  if (pathname === '/dashboard') {
    return null;
  }

  return (
    <nav className="bg-[#0B132B] text-white shadow-md border-b border-slate-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16 items-center">
          <div className="flex items-center space-x-3">
            <div className="bg-hp-navy text-white p-2 rounded-xl font-bold text-lg tracking-wider border border-white/20">
              HP
            </div>
            <div>
              <span className="text-lg font-bold tracking-tight text-white">
                Account Intelligence
              </span>
              <span className="ml-2 text-[10px] bg-hp-blue text-white px-2 py-0.5 rounded font-bold uppercase">
                Enterprise
              </span>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div className="flex items-center space-x-2 bg-slate-800 px-3 py-1.5 rounded-full border border-slate-700">
              {user.role === 'admin' ? (
                <Shield className="w-4 h-4 text-emerald-400" />
              ) : (
                <UserIcon className="w-4 h-4 text-hp-accent" />
              )}
              <div className="text-xs">
                <span className="font-bold text-gray-200">{user.full_name}</span>
                <span className="ml-1 text-[10px] text-gray-400 capitalize">({user.role})</span>
              </div>
            </div>

            <button
              onClick={logout}
              className="flex items-center space-x-1 bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg transition duration-150"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span>Sign Out</span>
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
};
