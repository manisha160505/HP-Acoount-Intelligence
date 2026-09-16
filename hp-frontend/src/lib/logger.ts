/**
 * Frontend structured logging.
 *
 * There was no client-side logging of any kind: a failed API call left nothing
 * in the console, so a user reporting "the dashboard is blank" gave no way to
 * tell a 401 from a 500 from a render bug.
 *
 * The fields mirror the backend's JSON log shape, and `request_id` is read off
 * the response's X-Request-ID header - so an error seen in the browser can be
 * pasted straight into a Cloud Logging query and matched to the server-side
 * line for the same call.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogFields {
  request_id?: string;
  method?: string;
  path?: string;
  status_code?: number;
  duration_ms?: number;
  error?: { type: string; message: string; stack?: string };
  [key: string]: unknown;
}

const SERVICE = 'hp-frontend';

// Next.js inlines NEXT_PUBLIC_* at build time, so this is a constant in the
// bundle and the minifier can drop the debug branch entirely in production.
const IS_DEV = process.env.NODE_ENV !== 'production';

const LEVEL_ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 };

// Debug is noise in a deployed build; below warn there is nothing a user's
// console should be carrying in production.
const MIN_LEVEL: LogLevel =
  (process.env.NEXT_PUBLIC_LOG_LEVEL as LogLevel) || (IS_DEV ? 'debug' : 'warn');

// console.debug/info/warn/error rather than console.log throughout: the
// browser's own level filter keys off the method, so using log for everything
// makes the devtools filter useless.
const CONSOLE_METHOD: Record<LogLevel, 'debug' | 'info' | 'warn' | 'error'> = {
  debug: 'debug',
  info: 'info',
  warn: 'warn',
  error: 'error',
};

const STYLE: Record<LogLevel, string> = {
  debug: 'color:#6b7280',
  info: 'color:#2563eb',
  warn: 'color:#d97706',
  error: 'color:#dc2626;font-weight:bold',
};

function enabled(level: LogLevel): boolean {
  return LEVEL_ORDER[level] >= LEVEL_ORDER[MIN_LEVEL];
}

function emit(level: LogLevel, message: string, fields: LogFields = {}): void {
  if (!enabled(level)) return;

  // Guard rather than assume: this module is imported by client components
  // that Next.js also renders on the server, where `window` does not exist.
  if (typeof window === 'undefined') return;

  const entry = {
    timestamp: new Date().toISOString(),
    level: level.toUpperCase(),
    service: SERVICE,
    message,
    ...fields,
  };

  const method = CONSOLE_METHOD[level];

  if (IS_DEV) {
    // Readable in a terminal-like console: one styled line, with the object
    // collapsed after it rather than stringified into the message.
    const rid = fields.request_id ? ` (${String(fields.request_id).slice(0, 8)})` : '';
    console[method](`%c[${SERVICE}]${rid} ${message}`, STYLE[level], fields);
    return;
  }

  // Production: one JSON line, so that anything scraping the console - a
  // session-replay tool, or a future /api/client-logs forwarder - gets the
  // same shape the backend emits.
  console[method](JSON.stringify(entry));
}

export const logger = {
  debug: (message: string, fields?: LogFields) => emit('debug', message, fields),
  info: (message: string, fields?: LogFields) => emit('info', message, fields),
  warn: (message: string, fields?: LogFields) => emit('warn', message, fields),
  error: (message: string, fields?: LogFields) => emit('error', message, fields),
};

/** Normalise a thrown value into the `error` field shape. */
export function toErrorField(err: unknown): LogFields['error'] {
  if (err instanceof Error) {
    return { type: err.name, message: err.message, stack: err.stack };
  }
  return { type: 'UnknownError', message: String(err) };
}

export default logger;
