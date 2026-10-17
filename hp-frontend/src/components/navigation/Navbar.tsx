'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import { isAdminRole } from '@/types/auth';
import { LogOut, User as UserIcon, Shield, Building2, Users, BarChart3, BookOpen, KeyRound, LayoutGrid } from 'lucide-react';
import HpLogo from '@/components/common/HpLogo';
import { AdminTour } from '@/components/tour/AdminTour';

const ADMIN_LINKS = [
  // The seller view: every account, searchable, each opening its dashboard.
  // Admins see all 220 here; sellers reach the same page as their home.
  { href: '/accounts', label: 'Accounts', Icon: LayoutGrid },
  { href: '/admin/platform', label: 'Platform', Icon: Building2 },
  { href: '/admin/users', label: 'Users', Icon: Users },
  { href: '/admin/analytics', label: 'Analytics', Icon: BarChart3 },
  { href: '/admin/rules', label: 'Rules', Icon: BookOpen },
];

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
          <div className="flex items-center space-x-3 flex-shrink-0">
            <HpLogo size={40} onDark />
            <div className="whitespace-nowrap">
              <span className="text-lg font-bold tracking-tight text-white">
                Account Intelligence
              </span>
              {/* Dropped on narrower screens so the admin links never wrap. */}
              <span className="hidden 2xl:inline ml-2 text-[10px] bg-hp-blue text-white px-2 py-0.5 rounded font-bold uppercase">
                Enterprise
              </span>
            </div>
          </div>

          {isAdminRole(user.role) && (
            <div data-tour="admin-nav" className="hidden md:flex items-center space-x-1">
              {ADMIN_LINKS.map(({ href, label, Icon }) => {
                const active = pathname?.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold whitespace-nowrap transition ${
                      active ? 'bg-white/15 text-white' : 'text-gray-300 hover:text-white hover:bg-white/10'
                    }`}
                  >
                    <Icon className="w-3.5 h-3.5" />
                    <span>{label}</span>
                  </Link>
                );
              })}
            </div>
          )}

          <div className="flex items-center space-x-2 flex-shrink-0">
            <div className="flex items-center space-x-2 bg-slate-800 px-3 py-1.5 rounded-full border border-slate-700 min-w-0">
              {isAdminRole(user.role) ? (
                <Shield className="w-4 h-4 text-emerald-400" />
              ) : (
                <UserIcon className="w-4 h-4 text-hp-accent" />
              )}
              <div className="text-xs whitespace-nowrap flex items-center min-w-0">
                <span className="font-bold text-gray-200 truncate max-w-[200px]" title={user.email}>{user.full_name}</span>
                {isAdminRole(user.role) && (
                  <span className="hidden xl:inline ml-1 text-[10px] text-gray-400 capitalize">({user.role.replace('_', ' ')})</span>
                )}
              </div>
            </div>

            <AdminTour />

            <Link
              href="/change-password"
              title="Change password"
              aria-label="Change password"
              className="flex items-center space-x-1 text-gray-300 hover:text-white hover:bg-white/10 text-xs font-bold px-2 py-1.5 rounded-lg whitespace-nowrap transition duration-150"
            >
              <KeyRound className="w-3.5 h-3.5" />
              <span className="hidden xl:inline">Change password</span>
            </Link>

            <button
              onClick={logout}
              className="flex items-center space-x-1 bg-red-600 hover:bg-red-700 text-white text-xs font-bold px-3 py-1.5 rounded-lg whitespace-nowrap transition duration-150"
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
