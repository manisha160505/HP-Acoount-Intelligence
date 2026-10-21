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
 * Screens never render the server's text (client rule, approved: no error
 * wording, no raw server detail). So this module gives back only what a
 * screen can branch on - the stable `code`, the HTTP `status`, the per-field
 * keys of a 422 - and the screen shows its own wording (lib/uiCopy.ts).
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
  code: ApiErrorCode | '';
  /** 0 when the server never answered. */
  status: number;
  requestId: string;
  /** Per-field messages from a 422: which inputs to mark. Not for display. */
  fields: Record<string, string>;
}

interface ErrorEnvelope {
  error?: {
    code?: string;
    fields?: Record<string, string>;
  };
  meta?: { request_id?: string; timestamp?: string };
}

/** Normalise anything thrown by an API call into an ApiError. */
export function parseApiError(err: unknown): ApiError {
  const response = (err as {
    response?: { status?: number; data?: ErrorEnvelope; headers?: Record<string, string> };
  })?.response;
  const data = response?.data;
  const envelope = data?.error;
  return {
    code: envelope?.code ?? '',
    status: response?.status ?? 0,
    requestId: data?.meta?.request_id ?? response?.headers?.['x-request-id'] ?? '',
    fields: envelope?.fields ?? {},
  };
}
