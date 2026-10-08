// HP case-study links that no longer open: HP retired these document ids and
// the address now redirects to its "page not found" (checked 6 Oct 2026, all
// 89 case-study links tested; refinements doc, point 6). The proof point is
// still shown - only the dead link is hidden. Kept here rather than edited in
// the case-study store, because changing that store marks every section built
// from it stale on every account.
const UNREACHABLE = new Set([
  'https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-1694ENW', // Invent Medical
]);

// Retired links whose document the client sent us (7 Oct), served from our
// own site (hp-frontend/public/case-studies) - so "View the HP case study"
// opens our copy, never an outside link. Same reason as above for keeping the
// mapping here instead of in the store.
const OWN_COPY: Record<string, string> = {
  // STERNAUTO: the case-study PDF itself.
  'https://h20195.www2.hp.com/v2/GetPDF.aspx/4AA8-4899ENW.pdf':
    '/case-studies/STERNAUTO_4AA8-4899ENW.pdf',
  // NORM ADDITIVE: the NORM Holding sustainability report 2024.
  'https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-4051ENW':
    '/case-studies/NORM_HOLDING_SUSTAINABILITY_REPORT_2024.pdf',
};

/** The case-study link to show - our own copy where we hold one - or null
 * when it does not open. */
export function caseStudyUrl(url?: string | null): string | null {
  const u = (url || '').trim();
  if (!u) return null;
  if (OWN_COPY[u]) return OWN_COPY[u];
  return UNREACHABLE.has(u) ? null : u;
}
