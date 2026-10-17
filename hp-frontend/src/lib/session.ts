/**
 * The signed-in session, held in memory only.
 *
 * The access token (15 minutes) lives in this module and nowhere else: not in
 * localStorage, where any script on the page could read it. What survives a
 * reload is the httpOnly refresh cookie the browser holds and scripts cannot
 * see; `refreshSession()` trades it for a new access token, which is how a
 * reloaded page learns who is signed in.
 *
 * One refresh at a time: every caller that finds the token missing or expired
 * awaits the same request, so a burst of 401s does not become a burst of
 * refreshes (each would swap the cookie out from under the others).
 */
import type { User } from '@/types/auth';

export const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/** Refresh this long before the access token expires. */
const REFRESH_EARLY_MS = 60_000;

let accessToken: string | null = null;
let expiresAt = 0;
let currentUser: User | null = null;
let refreshTimer: ReturnType<typeof setTimeout> | null = null;
let inFlight: Promise<User | null> | null = null;
const listeners = new Set<(user: User | null) => void>();

export interface TokenBody {
  access_token: string;
  expires_in: number;
  user: User;
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getSessionUser(): User | null {
  return currentUser;
}

/** Called with the user on every sign-in, refresh and sign-out (null). */
export function onSessionChange(fn: (user: User | null) => void): () => void {
  listeners.add(fn);
  return () => { listeners.delete(fn); };
}

function emit(): void {
  listeners.forEach((fn) => fn(currentUser));
}

export function setSession(body: TokenBody): void {
  accessToken = body.access_token;
  expiresAt = Date.now() + body.expires_in * 1000;
  currentUser = body.user;
  if (refreshTimer) clearTimeout(refreshTimer);
  const wait = Math.max(5_000, body.expires_in * 1000 - REFRESH_EARLY_MS);
  // Kept fresh while the tab is open, so the hp_access cookie a PDF link or a
  // download relies on has not lapsed when it is clicked.
  refreshTimer = setTimeout(() => { void refreshSession(); }, wait);
  emit();
}

/** A change to the signed-in user the server has already made. */
export function updateSessionUser(patch: Partial<User>): void {
  if (!currentUser) return;
  currentUser = { ...currentUser, ...patch };
  emit();
}

export function clearSession(): void {
  accessToken = null;
  expiresAt = 0;
  currentUser = null;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = null;
  emit();
}

/**
 * A new access token from the refresh cookie. Resolves to the user, or null
 * when there is no live session (never signed in, signed out, expired).
 */
export function refreshSession(): Promise<User | null> {
  if (inFlight) return inFlight;
  inFlight = (async () => {
    try {
      const res = await fetch(`${API_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!res.ok) {
        clearSession();
        return null;
      }
      const raw = await res.json();
      // The API wraps JSON bodies as { success, data, meta }.
      const body: TokenBody = raw && typeof raw === 'object' && 'data' in raw && 'success' in raw
        ? raw.data : raw;
      setSession(body);
      return body.user;
    } catch {
      // Network down: keep what we have; the next call will try again.
      return currentUser;
    } finally {
      inFlight = null;
    }
  })();
  return inFlight;
}

if (typeof document !== 'undefined') {
  // A laptop that slept past the token's expiry wakes with a stale token and a
  // timer that fired late or not at all.
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible' && currentUser
        && Date.now() > expiresAt - REFRESH_EARLY_MS) void refreshSession();
  });
}
