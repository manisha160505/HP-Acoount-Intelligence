import axios from 'axios';
import logger, { toErrorField } from '@/lib/logger';
import { API_URL, clearSession, getAccessToken, refreshSession } from '@/lib/session';

export { API_URL };

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  // The sign-in cookies ride along; the access token itself goes in the header.
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
});

// The access token lives in memory (lib/session), never in localStorage.
api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Stamped here so the response interceptor can report how long the call
  // actually took. performance.now() rather than Date.now(): it is monotonic,
  // so a clock adjustment mid-call cannot produce a negative duration.
  (config as { metadata?: { start: number } }).metadata = { start: performance.now() };
  return config;
});

// An expired token used to fail silently. Every call 401'd, each caller showed
// its own empty state, and the dashboard simply went blank - indistinguishable
// from a broken feature, with nothing telling anyone to sign in again. So a 401
// is handled once, here, rather than eleven times in the features: refresh the
// session and retry once; only if that fails, send the user to sign in.
/** Milliseconds since the request interceptor stamped this config. */
function elapsed(config: unknown): number | undefined {
  const start = (config as { metadata?: { start: number } })?.metadata?.start;
  return typeof start === 'number' ? Math.round((performance.now() - start) * 100) / 100 : undefined;
}

/**
 * The backend wraps every JSON response as
 *   { success, data, error, meta: { request_id, timestamp } }
 *
 * Unwrapped here, once, so that `response.data` stays the payload itself at
 * all 33 call sites. Without this every one of them would need to become
 * `response.data.data`, and every future call would have to remember the extra
 * hop.
 *
 * Only an envelope is unwrapped. A response that is not one - a file download,
 * /health, or anything from outside this API - passes through untouched, so
 * this cannot corrupt a non-enveloped body.
 */
function isEnvelope(body: unknown): body is { success: boolean; data: unknown; meta?: unknown } {
  return (
    typeof body === 'object' &&
    body !== null &&
    'success' in body &&
    'data' in body &&
    'meta' in body
  );
}

api.interceptors.response.use(
  (response) => {
    // The request id is on every response, success included - so a call that
    // returned the wrong-looking number is as traceable as one that failed.
    const requestId =
      (isEnvelope(response.data) &&
        (response.data.meta as { request_id?: string } | undefined)?.request_id) ||
      response.headers['x-request-id'];

    if (isEnvelope(response.data)) {
      response.data = response.data.data;
    }

    // Debug, not info: one line per successful call is useful while working on
    // a feature and pure noise otherwise. MIN_LEVEL drops these in production.
    logger.debug(`${response.config.method?.toUpperCase()} ${response.config.url} ${response.status}`, {
      // Ties a line in the browser console to the server-side log entry for
      // the same call.
      request_id: requestId,
      method: response.config.method?.toUpperCase(),
      path: response.config.url,
      status_code: response.status,
      duration_ms: elapsed(response.config),
    });
    return response;
  },
  async (error) => {
    const onLoginPage =
      typeof window !== 'undefined' && window.location.pathname.startsWith('/login');

    const status = error?.response?.status;
    // The backend puts a stable code on every error body. Logging it makes the
    // console line say WHY the call failed, not just that it did.
    const errorCode = error?.response?.data?.error?.code;
    const fields = {
      error_code: errorCode,
      // Prefer the id from the body: a CORS-blocked or proxied response can
      // lose the header while the body survives.
      request_id: error?.response?.data?.error?.request_id
        ?? error?.response?.headers?.['x-request-id'],
      method: error?.config?.method?.toUpperCase(),
      path: error?.config?.url,
      status_code: status,
      duration_ms: elapsed(error?.config),
      error: toErrorField(error),
    };

    // A 5xx is a server fault and a 401/404 is an expected outcome of ordinary
    // use; logging both at error would make the console cry wolf on every
    // session expiry. No status at all means the request never completed -
    // network down, CORS, or the API not running - which is worth an error.
    const label = errorCode ? `${status ?? 'network'} ${errorCode}` : `${status ?? 'network'}`;
    if (!status || status >= 500) {
      logger.error(`${fields.method} ${fields.path} failed (${label})`, fields);
    } else {
      logger.warn(`${fields.method} ${fields.path} ${label}`, fields);
    }

    const config = error?.config as (Record<string, unknown> & { headers?: Record<string, string> }) | undefined;
    const url = String(config?.url || '');
    const isAuthCall = url.startsWith('/auth/login') || url.startsWith('/auth/refresh')
      || url.startsWith('/auth/logout');

    // Not on the login page: a 401 there is a wrong password, which the form
    // already reports, and redirecting would loop.
    if (status === 401 && typeof window !== 'undefined' && !onLoginPage && !isAuthCall) {
      if (config && !config._retried) {
        config._retried = true;
        const user = await refreshSession();
        const token = getAccessToken();
        if (user && token) {
          config.headers = { ...(config.headers || {}), Authorization: `Bearer ${token}` };
          return api.request(config);
        }
      }
      logger.info('Session ended - redirecting to login.', { request_id: fields.request_id });
      clearSession();
      window.location.href = '/login?expired=1';
    }

    // Access to the open account was removed (or the link was never theirs):
    // back to the accounts this user does have, rather than a dashboard of
    // empty panels.
    if (status === 404 && errorCode === 'ACCOUNT_NOT_FOUND' && typeof window !== 'undefined'
        && window.location.pathname.startsWith('/dashboard')) {
      window.location.href = '/accounts';
    }

    // A new account must set its own password before anything else works.
    if (status === 403 && errorCode === 'PASSWORD_CHANGE_REQUIRED' && typeof window !== 'undefined'
        && !window.location.pathname.startsWith('/change-password')) {
      window.location.href = '/change-password';
    }
    return Promise.reject(error);
  }
);

/** One event from a server-sent-event endpoint. */
export type StreamEvent = {
  type: 'stage' | 'delta' | 'done' | 'error';
  stage?: string;
  text?: string;
  detail?: string;
  [key: string]: unknown;
};

/**
 * POST to an SSE endpoint and call `onEvent` as each event arrives.
 *
 * axios buffers the whole body before resolving, so it cannot read a stream -
 * this uses `fetch` for the response body reader while keeping the same base
 * URL and the same bearer token as every other call.
 *
 * `signal` aborts the request; the caller passes one so that switching account
 * or asking a second question stops the first stream rather than leaving it
 * writing into a thread the seller has moved on from.
 */
export async function postStream(
  path: string,
  body: unknown,
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const send = () => {
    const token = getAccessToken();
    return fetch(`${API_URL}/api/v1${path}`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });
  };
  let res = await send();
  // Same one-retry rule as the axios client: an expired token is refreshed.
  if (res.status === 401 && await refreshSession()) {
    res = await send();
  }

  if (!res.ok || !res.body) {
    throw new Error(`stream request failed: ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // An event can be split across two network chunks, so the tail of a chunk is
  // carried forward rather than parsed. Splitting on the blank line SSE uses as
  // a record separator keeps a half-received event in the buffer until the rest
  // of it arrives.
  let buffer = '';

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const records = buffer.split('\n\n');
    buffer = records.pop() ?? '';

    for (const record of records) {
      const line = record.split('\n').find((l) => l.startsWith('data: '));
      if (!line) continue;
      try {
        onEvent(JSON.parse(line.slice(6)) as StreamEvent);
      } catch {
        // A malformed event is skipped rather than aborting the stream: the
        // answer still arrives on the `done` event, which is what the thread
        // ultimately renders.
        logger.warn('Discarded an unparseable stream event.');
      }
    }
  }
}

export default api;
