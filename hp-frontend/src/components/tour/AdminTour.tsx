'use client';

// The admin pages' tour: Accounts, Platform, Users and Analytics (client,
// 17 Oct). The same cards and buttons as the dashboard tour
// (components/tour/useTour.tsx), but each stop is a page of its own, so the
// tour lives in the top bar - which stays mounted while the page changes - and
// moves between pages with the router. Its words are ADMIN_TOURS in
// lib/tourContent.ts.
//
// It starts once, on an admin's first visit to these pages, and is remembered
// apart from the dashboard tour (admin_tour_completed_at). A page's ? button
// replays that page; Take the tour in the top bar replays all four.

import { useCallback, useEffect, useRef } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { Compass, HelpCircle } from 'lucide-react';
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
const HELP_EVENT = 'hp-admin-tour-help';

function pageKeyFor(pathname: string | null): string {
  return ADMIN_TOUR_PAGES.find((p) => pathname === p.href || pathname?.startsWith(`${p.href}/`))?.key ?? '';
}

/** A page's ? button: replays that page's cards. The tour itself is in the
 *  top bar, so the request goes there as a window event. */
export function AdminHelpButton({ page }: { page: string }) {
  const { user } = useAuth();
  if (!isAdminRole(user?.role)) return null;
  return (
    <button
      type="button"
      onClick={() => window.dispatchEvent(new CustomEvent(HELP_EVENT, { detail: page }))}
      title="How this page works"
      aria-label="How this page works"
      className="inline-flex items-center align-middle ml-2 p-0.5 rounded text-slate-300 hover:text-white transition"
    >
      <HelpCircle className="w-5 h-5" />
    </button>
  );
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
    if (autoStarted.current || !isAdmin || !current || user?.admin_tour_completed_at) return;
    autoStarted.current = true;
    tour.start(PAGE_KEYS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAdmin, current, user?.admin_tour_completed_at]);

  // A page's ? button.
  const { help } = tour;
  useEffect(() => {
    const onHelp = (e: Event) => help((e as CustomEvent<string>).detail);
    window.addEventListener(HELP_EVENT, onHelp);
    return () => window.removeEventListener(HELP_EVENT, onHelp);
  }, [help]);

  if (!isAdmin) return null;
  return (
    <>
      <button
        type="button"
        data-tour="admin-tour-button"
        onClick={() => tour.start(PAGE_KEYS)}
        title="Take the tour of the admin pages"
        className="flex items-center space-x-1 text-gray-300 hover:text-white hover:bg-white/10 text-xs font-bold px-2 py-1.5 rounded-lg whitespace-nowrap transition duration-150"
      >
        <Compass className="w-3.5 h-3.5" />
        <span className="hidden xl:inline">Take the tour</span>
      </button>
      {tour.overlay}
    </>
  );
}
