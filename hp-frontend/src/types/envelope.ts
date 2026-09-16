/**
 * The response envelope, mirrored from the backend.
 *
 * Every JSON response is:
 *   { success, data, error, meta: { request_id, timestamp } }
 *
 * You normally never see this type. The axios interceptor in services/api.ts
 * unwraps `data` on success, so `api.get<Account>(...)` gives `response.data`
 * typed as `Account` - the payload, not the envelope. That is what keeps all
 * 33 existing call sites working unchanged.
 *
 * These types are here for the cases that do see the raw shape: reading an
 * error body (the success interceptor never runs on a rejection), or calling
 * the API with something other than this client.
 */

export interface ResponseMeta {
  /** Matches the X-Request-ID header and the backend log entry. */
  request_id: string;
  /** UTC, ISO-8601. */
  timestamp: string;
}

export interface ResponseError {
  /** Stable code, e.g. ACCOUNT_NOT_FOUND. Branch on this, not on the message. */
  code: string;
  /** Safe to show a user. */
  message: string;
  /** Present on a validation failure, keyed by field name. */
  fields?: Record<string, string>;
}

/**
 * The full envelope. `success` discriminates the union, so checking it
 * narrows `data` from `T | null` to `T`.
 */
export type ApiEnvelope<T> =
  | {
      success: true;
      data: T;
      error: null;
      meta: ResponseMeta;
      /** Alias of error.message. Absent on success. */
      detail?: string;
    }
  | {
      success: false;
      data: null;
      error: ResponseError;
      meta: ResponseMeta;
      /** Alias of error.message, kept so existing screens can render it. */
      detail: string;
    };

/** Narrow an unknown body to an envelope. */
export function isApiEnvelope<T = unknown>(body: unknown): body is ApiEnvelope<T> {
  return (
    typeof body === 'object' &&
    body !== null &&
    'success' in body &&
    'data' in body &&
    'meta' in body
  );
}
