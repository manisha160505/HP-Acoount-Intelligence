/**
 * Display formatting for vendor data shown to sellers.
 *
 * Explorium and Bombora send most text in lowercase - country on 220 of 220
 * accounts, city on 195, LinkedIn industry on 217, subsidiary names on 2,141 of
 * 2,142, every Bombora topic - so the dashboard read "tokyo, japan" and
 * "verigy us". CSS `capitalize` was the old fix and made it "Verigy Us" and
 * "Crea Srl", and left the copied text lowercase.
 *
 * No imports, so `node --test` can run the tests without a bundler.
 */

// Lowercase in the middle of a phrase ("Bank of Tokyo", "Research and
// Development"); always capitalised as the first word.
const SMALL_WORDS = new Set(['a', 'an', 'and', 'as', 'at', 'by', 'for', 'in', 'of', 'on', 'or', 'the', 'to', 'via', '&']);

// Written in capitals whatever the source did: legal forms, countries and
// common business acronyms that appear in company names and places. Codes that
// are also everyday words ("in", "my", "as", "id") are left out on purpose:
// "Daikin Czech Republic in Pilsen" must not read "IN Pilsen". "it" is kept: in
// an industry or a topic it is IT ("IT Services and IT Consulting").
const ACRONYMS = new Set([
  'usa', 'uk', 'uae', 'eu', 'it', 'hr', 'ai', 'hp', 'ibm', 'ict',
  'llc', 'llp', 'lp', 'srl', 'sa', 'sas', 'ag', 'nv', 'bv', 'plc', 'pt',
  'kk', 'jsc', 'pte', 'oy',
  'nz', 'au', 'jp', 'kr', 'vn', 'th', 'ph', 'sg', 'hk', 'cn', 'tw',
]);
// "us" is the United States in a company name ("Verigy US") and a word anywhere
// else, so it is capitalised in names only.
const NAME_ONLY_ACRONYMS = new Set(['us']);
// Legal forms written in their usual mixed case rather than all capitals.
const MIXED = new Map([
  ['gmbh', 'GmbH'], ['spa', 'SpA'], ['tbk', 'Tbk'], ['ltd', 'Ltd'], ['sdn', 'Sdn'], ['bhd', 'Bhd'],
  ['pty', 'Pty'], ['pvt', 'Pvt'], ['mfg', 'Mfg'], ['bros', 'Bros'],
]);

const hasVowel = (w: string) => /[aeiouy]/.test(w);

// a-z, digits, Latin-1 and Latin Extended (ß-ɏ), and Latin Extended Additional
// (Ḁ-ỿ), which is where Vietnamese lives.
const L = 'a-z0-9\u00DF-\u00FF\u0100-\u024F\u1E00-\u1EFF';
const WORD = new RegExp(`^([^${L}]*)([${L}./'-]*)([^${L}]*)$`);
const INITIAL = new RegExp(`(^|[-'])([a-z\u00DF-\u00FF\u0100-\u024F\u1E00-\u1EFF])`, 'g');

export interface DisplayCaseOptions {
  /** A company name: short codes ("bdo", "psc") and legal forms are capitals. */
  name?: boolean;
}

function caseWord(word: string, first: boolean, opts: DisplayCaseOptions, single: boolean): string {
  // Keep punctuation around the word: "(asc)", "group,". Letters include the
  // accented Latin and Vietnamese ranges ("hà nội"); spelled out rather than
  // \p{L} because the project targets ES5, which has no `u` flag.
  const m = word.match(WORD);
  if (!m || !m[2]) return word;
  const [, pre, core, post] = m;
  // "transportation/trucking/railroad": each part is a word.
  if (core.includes('/')) {
    return pre + core.split('/').map((part, i) => caseWord(part, first && i === 0, opts, false)).join('/') + post;
  }
  const bare = core.replace(/[.']/g, '');
  let out: string;
  if (MIXED.has(bare)) out = MIXED.get(bare)!;
  else if (ACRONYMS.has(bare) || (opts.name && NAME_ONLY_ACRONYMS.has(bare))) out = core.toUpperCase();
  else if (opts.name && /^[a-z]{2,4}$/.test(bare) && (!hasVowel(bare) || single)) out = core.toUpperCase();
  // "australian submarine corporation (asc)": a short code in brackets.
  else if (opts.name && pre.endsWith('(') && post.startsWith(')') && /^[a-z]{2,5}$/.test(bare)) out = core.toUpperCase();
  else if (!first && SMALL_WORDS.has(core)) out = core;
  else out = core.replace(INITIAL, (_s, sep: string, c: string) => sep + c.toUpperCase());
  return pre + out + post;
}

function casePhrase(phrase: string, opts: DisplayCaseOptions): string {
  const words = phrase.split(' ');
  const single = words.filter(Boolean).length === 1;
  return words.map((w, i) => caseWord(w, i === 0, opts, single)).join(' ');
}

/**
 * Title case for text the source sent in lowercase. Text with any capital in it
 * is returned exactly as written - the source cased it on purpose ("jQuery",
 * "Semiconductor and Related Device Manufacturing").
 *
 *   displayCase('tokyo')                                   -> 'Tokyo'
 *   displayCase('verigy us', { name: true })               -> 'Verigy US'
 *   displayCase('business services: vinson & elkins llp')  -> 'Business Services: Vinson & Elkins LLP'
 */
export function displayCase(value: string | null | undefined, opts: DisplayCaseOptions = {}): string {
  const text = String(value ?? '').replace(/\s+/g, ' ').trim();
  if (!text || text !== text.toLowerCase()) return text;
  // "category: topic" (Bombora) - each side is its own phrase.
  return text.split(': ').map(part => casePhrase(part, opts)).join(': ');
}

/** "City, Region, Country", each part cased. */
export function displayPlace(value: string | null | undefined): string {
  return String(value ?? '').split(',').map(p => displayCase(p)).filter(Boolean).join(', ');
}

/** "Sep 17, 2026"; the input unchanged when it is not a date. */
export function fmtDate(value: string | null | undefined, empty = ''): string {
  if (!value) return empty;
  const dt = new Date(value);
  if (isNaN(dt.getTime())) return String(value);
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
