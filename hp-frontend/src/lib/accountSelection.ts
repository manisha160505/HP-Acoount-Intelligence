/**
 * Search, urgency filter and pagination for the account picker.
 *
 * Pure functions over the list `/accounts/user-list` already returns - the same
 * list the dashboard's account dropdown uses. Filtering happens before paging,
 * so "Showing 1-4 of 4" means four matches, not four of the full list.
 *
 * No imports, so `node --test` can run the tests without a bundler.
 */

export interface PickableAccount {
  id: string;
  name: string;
  urgency_score?: number | null;
}

export const ACCOUNT_PAGE_SIZE = 20;

/** The dashboard route for an account. The `account` query parameter is what
 *  makes the selection survive a refresh. */
export function dashboardHref(accountId: string): string {
  return `/dashboard?account=${encodeURIComponent(accountId)}`;
}

/** Where a signed-in user lands: sellers choose an account first. */
export function homeRouteFor(role: string | undefined): string {
  return role === 'admin' ? '/admin/platform' : '/accounts';
}

/** The account id in a `?account=` query string, or null. */
export function accountIdFromSearch(search: string): string | null {
  const id = new URLSearchParams(search).get('account');
  return id && id.trim() ? id.trim() : null;
}

/** The account the dashboard should open for this query string, or null when
 *  none is named or the named one is not in the seller's list. */
export function activeAccountFrom<T extends { id: string }>(accounts: T[], search: string): T | null {
  const wanted = accountIdFromSearch(search);
  return (wanted && accounts.find((a) => a.id === wanted)) || null;
}

// No band definitions exist for the composite urgency score, so these are
// plain ranges over its 0-100 scale. "Not scored" covers accounts whose score
// has not been generated or was withheld for low coverage.
export type UrgencyFilter = 'all' | '0-20' | '21-40' | '41-60' | '61-80' | '81-100' | 'unscored';

export const URGENCY_FILTERS: { value: UrgencyFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: '81-100', label: '81–100' },
  { value: '61-80', label: '61–80' },
  { value: '41-60', label: '41–60' },
  { value: '21-40', label: '21–40' },
  { value: '0-20', label: '0–20' },
  { value: 'unscored', label: 'Not scored' },
];

export function matchesUrgency(score: number | null | undefined, filter: UrgencyFilter): boolean {
  if (filter === 'all') return true;
  const scored = typeof score === 'number' && Number.isFinite(score);
  if (filter === 'unscored') return !scored;
  if (!scored) return false;
  const [lo, hi] = filter.split('-').map(Number);
  return score >= lo && score <= hi;
}

export function filterAccounts<T extends PickableAccount>(
  accounts: T[],
  search: string,
  urgency: UrgencyFilter,
): T[] {
  const q = search.trim().toLowerCase();
  return accounts.filter(
    (a) => (!q || a.name.toLowerCase().includes(q)) && matchesUrgency(a.urgency_score, urgency),
  );
}

export interface Page<T> {
  items: T[];
  page: number;        // 1-based, clamped to the pages that exist
  totalPages: number;  // at least 1, so "page 1 of 1" holds for an empty list
  total: number;
  start: number;       // 1-based index of the first item shown, 0 when empty
  end: number;
}

export function paginate<T>(items: T[], page: number, pageSize = ACCOUNT_PAGE_SIZE): Page<T> {
  const total = items.length;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(Math.max(1, Math.floor(page) || 1), totalPages);
  const offset = (current - 1) * pageSize;
  const slice = items.slice(offset, offset + pageSize);
  return {
    items: slice,
    page: current,
    totalPages,
    total,
    start: total ? offset + 1 : 0,
    end: offset + slice.length,
  };
}

/** Page buttons with gaps: 1 … 4 5 6 … 11. `null` is a gap. */
export function pageNumbers(current: number, totalPages: number): (number | null)[] {
  if (totalPages <= 7) return Array.from({ length: totalPages }, (_, i) => i + 1);
  const keep = new Set([1, totalPages, current - 1, current, current + 1]);
  const out: (number | null)[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (keep.has(p)) out.push(p);
    else if (out[out.length - 1] !== null) out.push(null);
  }
  return out;
}
