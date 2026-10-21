/**
 * Copy for failures, per the client rule (approved): users - sellers and HP
 * admins - never see gap or error wording, and never the server's own error
 * text. A failed load offers a neutral "Try again" (components/common/TryAgain);
 * a failed action says ACTION_FAILED. Validation the user must act on
 * ("Passwords do not match") is not a failure and keeps its own wording.
 *
 * hp-backend/tests/test_no_gap_wording_in_ui.py enforces this over every .tsx.
 */
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
