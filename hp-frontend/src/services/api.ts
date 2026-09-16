import axios from 'axios';
import logger, { toErrorField } from '@/lib/logger';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

const api = axios.create({
  baseURL: `${API_URL}/api/v1`,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Interceptor to attach Authorization Bearer token from localStorage
api.interceptors.request.use((config) => {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('hp_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
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
// is handled once, here, rather than eleven times in the features.
//
// The two keys cleared are the ones AuthProvider.logout clears; leaving a stale
// token behind would re-send it on the next call and 401 again.
/** Milliseconds since the request interceptor stamped this config. */
function elapsed(config: unknown): number | undefined {
  const start = (config as { metadata?: { start: number } })?.metadata?.start;
  return typeof start === 'number' ? Math.round((performance.now() - start) * 100) / 100 : undefined;
}

api.interceptors.response.use(
  (response) => {
    // Debug, not info: one line per successful call is useful while working on
    // a feature and pure noise otherwise. MIN_LEVEL drops these in production.
    logger.debug(`${response.config.method?.toUpperCase()} ${response.config.url} ${response.status}`, {
      // Exposed by the backend's CORS config; this is what ties a line in the
      // browser console to the server-side log entry for the same call.
      request_id: response.headers['x-request-id'],
      method: response.config.method?.toUpperCase(),
      path: response.config.url,
      status_code: response.status,
      duration_ms: elapsed(response.config),
    });
    return response;
  },
  (error) => {
    const onLoginPage =
      typeof window !== 'undefined' && window.location.pathname.startsWith('/login');

    const status = error?.response?.status;
    const fields = {
      request_id: error?.response?.headers?.['x-request-id'],
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
    if (!status || status >= 500) {
      logger.error(`${fields.method} ${fields.path} failed`, fields);
    } else {
      logger.warn(`${fields.method} ${fields.path} ${status}`, fields);
    }

    // Not on the login page: a 401 there is a wrong password, which the form
    // already reports, and redirecting would loop.
    if (status === 401 && typeof window !== 'undefined' && !onLoginPage) {
      logger.info('Token rejected - clearing session and redirecting to login.', {
        request_id: fields.request_id,
      });
      localStorage.removeItem('hp_token');
      localStorage.removeItem('hp_user');
      window.location.href = '/login?expired=1';
    }
    return Promise.reject(error);
  }
);

export default api;
