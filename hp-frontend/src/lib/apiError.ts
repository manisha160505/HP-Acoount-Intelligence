/**
 * Reading an error off a failed API call.
 *
 * The backend returns one shape for every failure:
 *
 *   {
 *     "detail": "That account could not be found.",
 *     "error": { "code": "ACCOUNT_NOT_FOUND", "message": "...",
 *                "request_id": "3f9a...", "fields": { "email": "..." } }
 *   }
 *
 * `detail` is a plain string and stays one - existing screens read it directly
 * and render it, and that keeps working. This module is for code that wants
 * more: the stable `code` to branch on, the per-field messages for a form, or
 * the request id to show in a support message.
 *
 * Errors are read from the RAW envelope, not the unwrapped body: the axios
 * success interceptor never runs on a failed response, so `err.response.data`
 * is still the full { success, data, error, meta } object here.
 *
 * Nothing here assumes the `error` object is present. A response from a proxy,
 * a gateway timeout, or a network failure has no body at all, and those are
 * the cases where a helper is most likely to be called.
 */

/** Codes the frontend branches on. Others pass through as plain strings. */
export type ApiErrorCode =
  | 'VALIDATION_ERROR'
  | 'INVALID_ID_FORMAT'
  | 'INVALID_PARAMETER'
  | 'UNAUTHENTICATED'
  | 'INVALID_CREDENTIALS'
  | 'TOKEN_EXPIRED'
  | 'FORBIDDEN'
  | 'ACCOUNT_NOT_FOUND'
  | 'FILE_NOT_FOUND'
  | 'FEATURE_NOT_FOUND'
  | 'NO_SOURCE_DATA'
  | 'EXTRACTION_FAILED'
  | 'GENERATION_FAILED'
  | 'INDEX_NOT_READY'
  | 'LLM_UNAVAILABLE'
  | 'LLM_NOT_CONFIGURED'
  | 'INTERNAL_ERROR'
  | (string & {});   // keeps autocomplete while allowing any server code

export interface ApiError {
  /** Safe to render. Never empty. */
  message: string;
  code: ApiErrorCode | '';
  status: number;
  requestId: string;
  /** Per-field messages from a 422, for attaching to form inputs. */
  fields: Record<string, string>;
}

interface ErrorEnvelope {
  detail?: unknown;
  success?: boolean;
  error?: {
    code?: string;
    message?: string;
    fields?: Record<string, string>;
  };
  meta?: { request_id?: string; timestamp?: string };
}

/**
 * Normalise anything thrown by an API call into an ApiError.
 *
 * `fallback` is used when the server said nothing useful - a network failure,
 * or an error from outside the app. Pass the sentence the screen would have
 * shown anyway.
 */
export function parseApiError(err: unknown, fallback = 'Something went wrong.'): ApiError {
  const response = (err as {
    response?: { status?: number; data?: ErrorEnvelope; headers?: Record<string, string> };
  })?.response;
  const data = response?.data;
  const envelope = data?.error;

  // detail is a string by contract, but a proxy or a non-app 500 can put HTML
  // or an object there, so it is only trusted when it really is a string.
  const detail = typeof data?.detail === 'string' ? data.detail : '';

  let message = envelope?.message || detail;

  if (!message) {
    // No usable body. Distinguish "the server never answered" from "the server
    // answered with nothing", because the first is worth retrying.
    const noResponse = !response;
    message = noResponse
      ? 'Could not reach the server. Check your connection and try again.'
      : fallback;
  }

  return {
    message,
    code: envelope?.code ?? '',
    status: response?.status ?? 0,
    requestId: data?.meta?.request_id ?? response?.headers?.['x-request-id'] ?? '',
    fields: envelope?.fields ?? {},
  };
}

/** True when the failure is one retrying could plausibly fix. */
export function isRetryable(error: ApiError): boolean {
  if (error.status === 0) return true;              // never reached the server
  if (error.status >= 500) return true;             // server fault
  return error.code === 'INDEX_NOT_READY' || error.code === 'LLM_UNAVAILABLE';
}

/**
 * True when the failure means "upload the data first" rather than "this broke".
 * Worth separating: it is the one error class the user can actually resolve.
 */
export function isMissingData(error: ApiError): boolean {
  return error.code === 'NO_SOURCE_DATA';
}

/** The message plus a reference, for a screen that offers a support path. */
export function messageWithReference(error: ApiError): string {
  if (!error.requestId || error.message.includes(error.requestId)) return error.message;
  return `${error.message} (reference ${error.requestId})`;
}
