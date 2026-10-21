import React from 'react';

/**
 * The email and phone tags beside a contact's details (client, 19-21 Oct).
 *
 * Shown as the data provides them, with these rules: no email means no email
 * tag, no phone number means no phone tag, and a status that only says nothing
 * could be found or checked - unknown, unavailable, not found, could not
 * verify, unverified, N/A and the like - shows no tag at all, never a
 * placeholder such as "No Tag". The contact card itself always shows.
 * catch_all and CATCH_ALL are one tag.
 */

// Mirrors NO_INFO_TAG in scripts/upload_shipping_list_contacts.py, so data
// loaded before that rule existed is shown the same way.
const NO_INFO_TAG = new RegExp(
  '^$|unknown|unavailable|not[\\s_-]*(found|available|verified|provided|checked)'
  + '|could[\\s_-]*not|can[\\s_-]*not|cannot|unable|unverified|unverifiable|invalid'
  + '|pending|error|failed|^(n/?a|na|none|null|nil|-+)$',
  'i',
);

function hasInfo(tag: string): boolean {
  return !NO_INFO_TAG.test(tag);
}

export function emailTag(email?: string | null, status?: string | null): string | null {
  if (!email) return null;
  const tag = String(status ?? '').trim();
  if (!hasInfo(tag)) return null;
  return tag.toUpperCase() === 'CATCH_ALL' ? 'CATCH_ALL' : tag;
}

export function phoneTag(phone?: string | null, lineType?: string | null): string | null {
  if (!phone) return null;
  const tag = String(lineType ?? '').trim().toUpperCase();
  return hasInfo(tag) ? tag : null;
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
