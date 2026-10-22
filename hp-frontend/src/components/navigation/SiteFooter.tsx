'use client';

import React from 'react';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/providers/AuthProvider';
import PoweredByBridgeAI from '@/components/common/PoweredByBridgeAI';

// "Powered by BridgeAI" at the foot of every page that has the Navbar, right
// aligned to the Navbar's own content width, as in the Zebra platform's app
// footer, on the light pages. Not shown signed out (the sign-in card carries
// its own), on /dashboard (its sidebar carries it), or on the full-screen navy
// password pages, where it would sit on a light strip below the navy band.
const NO_FOOTER = new Set(['/dashboard', '/login', '/forgot-password', '/change-password']);

export const SiteFooter: React.FC = () => {
  const { user, isAuthenticated } = useAuth();
  const pathname = usePathname();

  if (!isAuthenticated || !user || NO_FOOTER.has(pathname ?? '')) return null;

  // Full width in the pages' own base colour (#F4F6F8, `.as-page` in
  // globals.css), so it reads as the bottom edge of the page, not a band
  // below it; a hairline marks where the page's soft gradient stops. The logo
  // is right aligned to the Navbar's content width.
  return (
    <footer className="flex-shrink-0 bg-[#F4F6F8] border-t border-slate-200/70">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex justify-end">
        <PoweredByBridgeAI />
      </div>
    </footer>
  );
};
