/**
 * Usage tracking: which features sellers open, and for how long.
 *
 *   track({ event: 'feature_view', feature_key, account_id })
 *
 * Time spent: after a feature_view, a `feature_heartbeat` for that feature is
 * queued every HEARTBEAT_MS - but only while the tab is visible and the seller
 * has touched the page (mouse, key, scroll, touch) within IDLE_AFTER_MS. A tab
 * left open over lunch stops counting. The server decides what a heartbeat is
 * worth and counts each 30s window once, so duplicates add nothing.
 * `stopFeatureTime()` ends it when the dashboard unmounts.
 *
 * Events are queued in memory and sent to POST /events in one batch every
 * FLUSH_INTERVAL_MS, and once more when the page is hidden or closed (via
 * navigator.sendBeacon, which survives the unload).
 *
 * Tracking is a side channel. Nothing here throws, nothing is awaited by the
 * caller, and a failed send never redirects or surfaces an error - so a broken
 * analytics endpoint cannot break navigation. That is also why this uses fetch
 * directly rather than the shared axios client, whose 401 handler logs the
 * user out.
 *
 * Admins are not tracked (the backend drops their events as well). The user's
 * identity is never sent: the server takes it from the token.
 */

import { API_URL } from '@/services/api';
import logger from '@/lib/logger';

export interface TrackEvent {
  event: 'feature_view' | 'feature_heartbeat';
  feature_key: string;
  account_id?: string | null;
}

interface QueuedEvent extends TrackEvent {
  session_id: string;
}

export const FLUSH_INTERVAL_MS = 10_000;
// Must match HEARTBEAT_SECONDS on the backend (services/usage.py).
export const HEARTBEAT_MS = 30_000;
export const IDLE_AFTER_MS = 5 * 60_000;
// The backend accepts at most 100 per request; anything beyond waits for the
// next flush. Also the cap on what is held while the server is unreachable.
export const MAX_BATCH = 100;

const EVENTS_URL = `${API_URL}/api/v1/events`;
const SESSION_KEY = 'hp_session_id';

let queue: QueuedEvent[] = [];
let timer: ReturnType<typeof setInterval> | null = null;
let exitHandlersInstalled = false;

// The feature on screen, for heartbeats. Set by every feature_view.
let current: { feature_key: string; account_id: string | null } | null = null;
let heartbeatTimer: ReturnType<typeof setInterval> | null = null;
let lastInteraction = Date.now();
let interactionHandlersInstalled = false;

function readToken(): string | null {
  try {
    return localStorage.getItem('hp_token');
  } catch {
    return null;
  }
}

function isTrackedUser(): boolean {
  try {
    const raw = localStorage.getItem('hp_user');
    if (!raw || !readToken()) return false;
    return JSON.parse(raw)?.role !== 'admin';
  } catch {
    return false;
  }
}

/** One id per browser tab, kept for the life of the tab. */
export function sessionId(): string {
  try {
    let id = sessionStorage.getItem(SESSION_KEY);
    if (!id) {
      id = typeof crypto !== 'undefined' && 'randomUUID' in crypto
        ? crypto.randomUUID()
        : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(SESSION_KEY, id);
    }
    return id;
  } catch {
    return 'no-session';
  }
}

/** Queue an event. Returns immediately; never throws. */
export function track(event: TrackEvent): void {
  if (typeof window === 'undefined' || !isTrackedUser()) return;
  queue.push({ ...event, account_id: event.account_id || null, session_id: sessionId() });
  // Bounded: a tab left open with the API down must not grow without limit.
  if (queue.length > MAX_BATCH * 5) queue = queue.slice(-MAX_BATCH * 5);
  if (event.event === 'feature_view') {
    current = { feature_key: event.feature_key, account_id: event.account_id || null };
    startHeartbeat();
  }
  start();
}

function markInteraction(): void {
  lastInteraction = Date.now();
}

function startHeartbeat(): void {
  if (!interactionHandlersInstalled) {
    interactionHandlersInstalled = true;
    for (const name of ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart', 'wheel']) {
      window.addEventListener(name, markInteraction, { passive: true, capture: true });
    }
  }
  // Opening a feature is itself activity.
  markInteraction();
  if (heartbeatTimer) return;
  heartbeatTimer = setInterval(() => {
    if (!current || document.visibilityState !== 'visible') return;
    if (Date.now() - lastInteraction > IDLE_AFTER_MS) return;
    track({ event: 'feature_heartbeat', ...current });
  }, HEARTBEAT_MS);
}

/** Stop counting time, e.g. when the dashboard unmounts. Never throws. */
export function stopFeatureTime(): void {
  current = null;
  if (heartbeatTimer) clearInterval(heartbeatTimer);
  heartbeatTimer = null;
}

/** Send what is queued. Resolves when done; never rejects. */
export async function flush(): Promise<void> {
  const token = readToken();
  if (!queue.length || !token) return;
  const batch = queue.splice(0, MAX_BATCH);
  try {
    const res = await fetch(EVENTS_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ events: batch }),
      keepalive: true,
    });
    if (res.status >= 500) requeue(batch);
    else if (!res.ok) logger.debug(`usage events rejected (${res.status})`);
  } catch {
    // Network failure: keep them for the next attempt.
    requeue(batch);
  }
}

function requeue(batch: QueuedEvent[]): void {
  queue = [...batch, ...queue].slice(0, MAX_BATCH * 5);
}

/**
 * Last-chance send while the page is going away. sendBeacon cannot set an
 * Authorization header, so the token goes in the query string (the endpoint
 * accepts either, as the file-download endpoint already does), and the body
 * goes as text/plain so the beacon needs no CORS preflight.
 */
export function flushOnExit(): void {
  const token = readToken();
  if (!queue.length || !token) return;
  const batch = queue.splice(0, MAX_BATCH);
  const url = `${EVENTS_URL}?token=${encodeURIComponent(token)}`;
  const body = JSON.stringify({ events: batch });
  try {
    if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function'
        && navigator.sendBeacon(url, new Blob([body], { type: 'text/plain;charset=UTF-8' }))) {
      return;
    }
    fetch(url, { method: 'POST', body, keepalive: true,
                 headers: { 'Content-Type': 'text/plain;charset=UTF-8' } }).catch(() => {});
  } catch {
    // Unloading; nothing more can be done.
  }
}

function start(): void {
  if (!timer) {
    timer = setInterval(() => { void flush(); }, FLUSH_INTERVAL_MS);
  }
  if (!exitHandlersInstalled) {
    exitHandlersInstalled = true;
    // pagehide rather than unload/beforeunload: it fires on mobile and on
    // bfcache navigations, where unload does not. visibilitychange catches a
    // tab that is backgrounded and then killed without ever firing pagehide.
    window.addEventListener('pagehide', flushOnExit);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') flushOnExit();
    });
  }
}

/** For tests: the queue as it stands, and a way to reset module state. */
export const __testing = {
  pending: (): readonly QueuedEvent[] => queue,
  reset: (): void => {
    queue = [];
    if (timer) clearInterval(timer);
    timer = null;
    stopFeatureTime();
  },
};
