/**
 * Copy for failures, per the client rule (approved): users - sellers and HP
 * admins - never see gap or error wording, and never the server's own error
 * text. A failed load offers a neutral "Try again" (components/common/TryAgain);
 * a failed action says ACTION_FAILED. Validation the user must act on
 * ("Passwords do not match") is not a failure and keeps its own wording.
 *
 * hp-backend/tests/test_no_gap_wording_in_ui.py enforces this over every .tsx.
 */
import { parseApiError } from './apiError';

export const ACTION_FAILED = 'Something went wrong. Please try again.';

/**
 * An admin's upload the server rejected as unreadable for its dataset (HTTP
 * 400/422 from POST /accounts/{id}/data: wrong file type, empty, no rows or
 * pages, a file that does not parse). The admin has to fix the file, so this
 * says what to do - never the server's own text.
 */
export const UPLOAD_FILE_REJECTED =
  "This file doesn't match the expected format for this dataset. Check its columns and upload it again.";
export const UPLOAD_PDF_REJECTED =
  "This file doesn't match the expected format for this dataset. Check that it opens as a PDF and upload it again.";

/**
 * Message Evaluator refusals the seller can act on, by the server's error code
 * (hp-backend errors/codes.py). Each says what to do; any other failure - the
 * AI not answering, a timeout - is ACTION_FAILED. Sent to the client 12 Nov:
 * every refusal used to read as "Something went wrong", which looked like a
 * broken system when the fix was to untick a change or shorten the message.
 */
export const EVALUATOR_REFUSALS: Record<string, string> = {
  REWRITE_TOO_LONG:
    'The rewrite came out longer than this format allows. Untick a change, or shorten your message, and try again.',
  REWRITE_UNSUPPORTED_FIGURE:
    "The rewrite added a figure we can't confirm from this account's data. Untick the change that adds it and try again.",
  REWRITE_CLAIM_NOT_PERMITTED:
    "The rewrite added a claim that isn't allowed in this market, such as a superlative or a competitor's name. Untick the change that adds it and try again.",
  REWRITE_PERSONA_BLOCKED:
    "The rewrite added something that can't be sent to this persona. Untick the change that adds it and try again.",
  EVALUATION_NOT_FOUND: 'Please evaluate the message again, then rewrite.',
  PERSONA_UNAVAILABLE: 'That persona has changed for this account. Pick one from the list and try again.',
};

/** The line for a failed evaluation or rewrite: the refusal's own, else ACTION_FAILED. */
export function evaluatorFailureText(err: unknown): string {
  return EVALUATOR_REFUSALS[parseApiError(err).code] ?? ACTION_FAILED;
}

/** HTTP status of a failed API call (0 when the server never answered). */
export function failureStatus(err: unknown): number {
  return (err as { response?: { status?: number } })?.response?.status ?? 0;
}

/**
 * True when the server's reason for refusing matches `pattern`. For telling a
 * validation refusal the user must act on (a duplicate name, a wrong recovery
 * code) from any other failure; the screen then shows its own wording for it,
 * never the server's text.
 */
export function serverSaid(err: unknown, pattern: RegExp): boolean {
  const data = (err as { response?: { data?: { detail?: unknown; error?: { message?: unknown } } } })?.response?.data;
  const text = [data?.error?.message, data?.detail].filter((v): v is string => typeof v === 'string').join(' ');
  return pattern.test(text);
}

/**
 * The server refused the new password. Length is checked on the page before
 * sending, with the server's minimum, so what is left is reusing the old one.
 */
export const NEW_PASSWORD_REFUSED = 'Your new password must be different from your old password.';
