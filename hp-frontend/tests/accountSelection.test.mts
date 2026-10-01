// Account Selection: search, urgency filter, pagination and the routing that
// carries the chosen account into the dashboard.
//
// Run: npm test   (node --test; Node 23.6+ runs the TypeScript directly)

import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
  ACCOUNT_PAGE_SIZE,
  accountIdFromSearch,
  activeAccountFrom,
  dashboardHref,
  filterAccounts,
  homeRouteFor,
  matchesUrgency,
  pageNumbers,
  paginate,
} from '../src/lib/accountSelection.ts';

type Acc = { id: string; name: string; urgency_score: number | null };

// 220 accounts, like the live list, with scores spread over 0-100 and a few
// unscored. Names are unique so search results are countable.
const ALL: Acc[] = Array.from({ length: 220 }, (_, i) => ({
  id: `id${i}`,
  name: i < 4 ? `Jabil ${['Inc', 'Circuit', 'Mexico', 'Malaysia'][i]}` : `Company ${String(i).padStart(3, '0')}`,
  urgency_score: i % 11 === 0 ? null : i % 101,
}));

const SAMPLE: Acc[] = [
  { id: 'a', name: 'Account A', urgency_score: 85 },
  { id: 'b', name: 'Account B', urgency_score: 72 },
  { id: 'c', name: 'Account C', urgency_score: 45 },
  { id: 'd', name: 'Account D', urgency_score: 18 },
];

// ------------------------------------------------------------- routing

test('successful login lands a seller on Account Selection, an admin on the platform', () => {
  assert.equal(homeRouteFor('user'), '/accounts');
  assert.equal(homeRouteFor(undefined), '/accounts');
  assert.equal(homeRouteFor('admin'), '/admin/platform');
});

test('selecting an account opens the dashboard with that account active', () => {
  const href = dashboardHref('b');
  assert.equal(href, '/dashboard?account=b');
  const search = new URL(href, 'http://x').search;
  assert.equal(activeAccountFrom(SAMPLE, search)?.name, 'Account B');
});

test('the active account survives a refresh: it is read back from the URL', () => {
  // A dropdown switch rewrites the URL the same way, so reloading reopens it.
  const search = new URL(dashboardHref('c'), 'http://x').search;
  assert.equal(accountIdFromSearch(search), 'c');
  assert.equal(activeAccountFrom(SAMPLE, search)?.id, 'c');
});

test('no account, or one no longer in the list, resolves to none (sent back to choose)', () => {
  assert.equal(activeAccountFrom(SAMPLE, ''), null);
  assert.equal(activeAccountFrom(SAMPLE, '?account='), null);
  assert.equal(activeAccountFrom(SAMPLE, '?account=gone'), null);
  assert.equal(activeAccountFrom([], '?account=a'), null);
});

test('ids with URL-special characters round-trip', () => {
  const search = new URL(dashboardHref('a&b=c'), 'http://x').search;
  assert.equal(accountIdFromSearch(search), 'a&b=c');
});

// ------------------------------------------------------------- loading + paging

test('all accounts are available, none dropped by the default view', () => {
  assert.equal(filterAccounts(ALL, '', 'all').length, 220);
  const pages = paginate(ALL, 1).totalPages;
  const seen = new Set<string>();
  for (let p = 1; p <= pages; p++) paginate(ALL, p).items.forEach((a) => seen.add(a.id));
  assert.equal(seen.size, 220);
});

test('pagination: 20 per page, "Showing 1-20 of 220", last page partial', () => {
  const first = paginate(ALL, 1);
  assert.equal(ACCOUNT_PAGE_SIZE, 20);
  assert.deepEqual([first.start, first.end, first.total, first.totalPages], [1, 20, 220, 11]);
  assert.equal(first.items[0].id, 'id0');
  const second = paginate(ALL, 2);
  assert.deepEqual([second.start, second.end], [21, 40]);
  assert.equal(second.items[0].id, 'id20');
  const last = paginate(ALL.slice(0, 45), 3);
  assert.deepEqual([last.start, last.end, last.items.length], [41, 45, 5]);
});

test('pagination clamps a page past the end or below 1', () => {
  assert.equal(paginate(ALL, 99).page, 11);
  assert.equal(paginate(ALL, 0).page, 1);
  assert.equal(paginate(ALL, Number.NaN).page, 1);
});

test('page buttons show gaps on long lists', () => {
  assert.deepEqual(pageNumbers(1, 3), [1, 2, 3]);
  assert.deepEqual(pageNumbers(1, 11), [1, 2, null, 11]);
  assert.deepEqual(pageNumbers(6, 11), [1, null, 5, 6, 7, null, 11]);
  assert.deepEqual(pageNumbers(11, 11), [1, null, 10, 11]);
});

// ------------------------------------------------------------- search + filter

test('search matches company name, case-insensitively and trimmed', () => {
  const hits = filterAccounts(ALL, '  jabil ', 'all');
  assert.deepEqual(hits.map((a) => a.name), ['Jabil Inc', 'Jabil Circuit', 'Jabil Mexico', 'Jabil Malaysia']);
});

test('urgency filter: 61-80 on the example returns Account B only', () => {
  assert.deepEqual(filterAccounts(SAMPLE, '', '61-80').map((a) => a.name), ['Account B']);
  assert.deepEqual(filterAccounts(SAMPLE, '', '81-100').map((a) => a.name), ['Account A']);
  assert.deepEqual(filterAccounts(SAMPLE, '', '0-20').map((a) => a.name), ['Account D']);
});

test('range edges are inclusive and every score falls in exactly one range', () => {
  const ranges = ['0-20', '21-40', '41-60', '61-80', '81-100'] as const;
  for (let s = 0; s <= 100; s++) {
    assert.equal(ranges.filter((r) => matchesUrgency(s, r)).length, 1, `score ${s}`);
  }
  assert.ok(matchesUrgency(20, '0-20') && matchesUrgency(21, '21-40') && matchesUrgency(100, '81-100'));
});

test('unscored accounts appear under All and Not scored, never in a range', () => {
  assert.ok(matchesUrgency(null, 'all'));
  assert.ok(matchesUrgency(undefined, 'unscored'));
  assert.ok(!matchesUrgency(null, '0-20'));
  assert.ok(!matchesUrgency(0, 'unscored'));
  const unscored = filterAccounts(ALL, '', 'unscored');
  assert.equal(unscored.length, 20);
  assert.ok(unscored.every((a) => a.urgency_score === null));
});

test('search and urgency filter combine', () => {
  // Jabil scores: Inc 0 (i=0 -> unscored), Circuit 1, Mexico 2, Malaysia 3.
  assert.deepEqual(filterAccounts(ALL, 'jabil', '0-20').map((a) => a.name),
    ['Jabil Circuit', 'Jabil Mexico', 'Jabil Malaysia']);
  assert.deepEqual(filterAccounts(ALL, 'jabil', 'unscored').map((a) => a.name), ['Jabil Inc']);
  assert.deepEqual(filterAccounts(ALL, 'jabil', '61-80'), []);
});

test('pagination runs on the filtered result, not the full list', () => {
  const view = paginate(filterAccounts(ALL, 'jabil', 'all'), 1);
  assert.deepEqual([view.start, view.end, view.total, view.totalPages], [1, 4, 4, 1]);

  const ranged = filterAccounts(ALL, '', '41-60');
  const p1 = paginate(ranged, 1);
  assert.equal(p1.total, ranged.length);
  assert.ok(p1.items.every((a) => a.urgency_score! >= 41 && a.urgency_score! <= 60));
  const p2 = paginate(ranged, 2);
  assert.equal(p2.start, 21);
  assert.equal(new Set([...p1.items, ...p2.items].map((a) => a.id)).size, p1.items.length + p2.items.length);
});

test('empty results: no items, "0 of 0", one page and nothing to go to', () => {
  const view = paginate(filterAccounts(ALL, 'no such company', 'all'), 3);
  assert.deepEqual([view.items.length, view.start, view.end, view.total, view.totalPages, view.page],
    [0, 0, 0, 0, 1, 1]);
  assert.deepEqual(paginate([], 1).items, []);
});
