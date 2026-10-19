'use client';

// The admin pages' tour: Accounts, Platform, Users and Analytics (client,
// 17 Oct). The same cards and buttons as the dashboard tour
// (components/tour/useTour.tsx), but each stop is a page of its own, so the
// tour lives in the top bar - which stays mounted while the page changes - and
// moves between pages with the router. Its words are ADMIN_TOURS in
// lib/tourContent.ts.
//
// It starts once, on an admin's first visit to these pages, and is remembered
// apart from the dashboard tour (admin_tour_completed_at). After that, Take the
// tour in the top bar shows the tour of the page on screen.

import { useCallback, useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Compass } from 'lucide-react';
import { useAuth } from '@/providers/AuthProvider';
import { isAdminRole } from '@/types/auth';
import { ADMIN_TOUR_FINISH, ADMIN_TOUR_WELCOME, ADMIN_TOURS } from '@/lib/tourContent';
import { useTour } from './useTour';

export const ADMIN_TOUR_PAGES: { key: string; href: string }[] = [
  { key: 'accounts', href: '/accounts' },
  { key: 'platform', href: '/admin/platform' },
  { key: 'users', href: '/admin/users' },
  { key: 'analytics', href: '/admin/analytics' },
];
const PAGE_KEYS = ADMIN_TOUR_PAGES.map((p) => p.key);

// Pages with a Take the tour but no place in the first-visit tour: their
// address names one account, which the tour cannot choose for the admin.
const ADMIN_HELP_PAGES: { key: string; prefix: string }[] = [
  { key: 'account', prefix: '/admin/accounts/' },
];

function pageKeyFor(pathname: string | null): string {
  return ADMIN_TOUR_PAGES.find((p) => pathname === p.href || pathname?.startsWith(`${p.href}/`))?.key
    ?? ADMIN_HELP_PAGES.find((p) => pathname?.startsWith(p.prefix))?.key
    ?? '';
}

/** Take the tour, for the top bar, and the tour's cards. Admins only. */
export function AdminTour() {
  const { user, markTourCompleted } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const current = pageKeyFor(pathname);

  const goTo = useCallback((key: string) => {
    const page = ADMIN_TOUR_PAGES.find((p) => p.key === key);
    if (page) router.push(page.href);
  }, [router]);

  const tour = useTour({
    activeFeatureKey: current,
    setActiveFeatureKey: goTo,
    onTourDone: () => { void markTourCompleted('admin'); },
    tours: ADMIN_TOURS,
    welcome: ADMIN_TOUR_WELCOME,
    finish: ADMIN_TOUR_FINISH,
    unit: 'Page',
  });

  const isAdmin = isAdminRole(user?.role);

  // First visit to the admin pages.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (autoStarted.current || !isAdmin || !PAGE_KEYS.includes(current) || user?.admin_tour_completed_at) return;
    autoStarted.current = true;
    tour.start(PAGE_KEYS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, current, user?.admin_tour_completed_at]);

  if (!isAdmin) return null;
  return (
    <>
      {/* Only on a page that has a tour (not Rules). */}
      {current && (
      <button
        type="button"
        data-tour="admin-tour-button"
        onClick={() => tour.help(current)}
        title="How this page works"
        className="flex items-center space-x-1 text-gray-300 hover:text-white hover:bg-white/10 text-xs font-bold px-2 py-1.5 rounded-lg whitespace-nowrap transition duration-150"
      >
        <Compass className="w-3.5 h-3.5" />
        <span className="hidden xl:inline">Take the tour</span>
      </button>
      )}
      {tour.overlay}
    </>
  );
}
