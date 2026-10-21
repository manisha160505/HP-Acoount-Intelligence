import React from 'react';

/**
 * The email and phone tags beside a contact's details (client, 19 Oct).
 *
 * Shown as the data provides them, with three rules: no email means no email
 * tag, no phone number means no phone tag, and a blank or "unknown" status is
 * left blank - never a placeholder such as "No Tag". The same goes for
 * "unavailable", "not found" and the like. catch_all and CATCH_ALL are one tag.
 */

// Statuses that say nothing about the mailbox: "unknown", "unavailable",
// "not found" and the like (client, 21 Oct). Compared with spaces and hyphens
// as underscores.
const EMAIL_BLANK = new Set(['', 'UNKNOWN', 'UNAVAILABLE', 'INVALID', 'NONE', 'NULL',
  'NOT_FOUND', 'NOT_AVAILABLE', 'N/A', 'NA']);

export function emailTag(email?: string | null, status?: string | null): string | null {
  if (!email) return null;
  const tag = String(status ?? '').trim();
  if (EMAIL_BLANK.has(tag.toUpperCase().replace(/[\s-]+/g, '_'))) return null;
  return tag.toUpperCase() === 'CATCH_ALL' ? 'CATCH_ALL' : tag;
}

export function phoneTag(phone?: string | null, lineType?: string | null): string | null {
  if (!phone) return null;
  const tag = String(lineType ?? '').trim().toUpperCase();
  return tag || null;
}

const EMAIL_STYLE: Record<string, string> = {
  VERIFIED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  VALID: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  CATCH_ALL: 'bg-amber-50 text-amber-700 border-amber-200',
  VALID_RISKY: 'bg-orange-50 text-orange-700 border-orange-200',
};

const BASE = 'inline-flex items-center text-[10px] font-semibold tracking-wide px-1.5 py-0.5 rounded border';

export function EmailTag({ email, status }: { email?: string | null; status?: string | null }) {
  const tag = emailTag(email, status);
  if (!tag) return null;
  return (
    <span className={`${BASE} ${EMAIL_STYLE[tag.toUpperCase()] || 'bg-slate-50 text-slate-600 border-slate-200'}`}>
      {tag}
    </span>
  );
}

export function PhoneTag({ phone, lineType }: { phone?: string | null; lineType?: string | null }) {
  const tag = phoneTag(phone, lineType);
  if (!tag) return null;
  return <span className={`${BASE} bg-sky-50 text-sky-700 border-sky-200`}>{tag}</span>;
}
