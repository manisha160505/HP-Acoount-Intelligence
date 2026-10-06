// HP case-study links that no longer open: HP retired these document ids and
// the address now redirects to its "page not found" (checked 6 Oct 2026, all
// 89 case-study links tested; refinements doc, point 6). The proof point is
// still shown - only the dead link is hidden. Kept here rather than edited in
// the case-study store, because changing that store marks every section built
// from it stale on every account.
const UNREACHABLE = new Set([
  'https://h20195.www2.hp.com/v2/GetPDF.aspx/4AA8-4899ENW.pdf', // STERNAUTO
  'https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-1694ENW', // Invent Medical
  'https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-4051ENW', // NORM ADDITIVE
]);

/** The case-study link to show, or null when it does not open. */
export function caseStudyUrl(url?: string | null): string | null {
  const u = (url || '').trim();
  return u && !UNREACHABLE.has(u) ? u : null;
}
