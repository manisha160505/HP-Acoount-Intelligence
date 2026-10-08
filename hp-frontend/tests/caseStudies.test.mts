// HP case-study links: retired ones hidden, the two the client sent opened
// from our own copy (7 Oct), everything else passed through.
//
// Run: npm test   (node --test; Node 23.6+ runs the TypeScript directly)

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';

import { caseStudyUrl } from '../src/lib/caseStudies.ts';

const STERNAUTO = 'https://h20195.www2.hp.com/v2/GetPDF.aspx/4AA8-4899ENW.pdf';
const NORM = 'https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA8-4051ENW';

test('a case study we hold opens our own copy, never the retired link', () => {
  assert.equal(caseStudyUrl(STERNAUTO), '/case-studies/STERNAUTO_4AA8-4899ENW.pdf');
  assert.equal(caseStudyUrl(`  ${NORM} `), '/case-studies/NORM_HOLDING_SUSTAINABILITY_REPORT_2024.pdf');
});

test('every own copy exists in public/, so the link never 404s', () => {
  for (const url of [STERNAUTO, NORM]) {
    const path = caseStudyUrl(url)!;
    assert.ok(existsSync(new URL(`../public${path}`, import.meta.url)), path);
  }
});

test('a retired link with no copy is hidden', () => {
  assert.equal(caseStudyUrl('https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-1694ENW'), null);
});

test('any other link, and an empty one, behave as before', () => {
  assert.equal(caseStudyUrl('https://reinvent.hp.com/us-en-3dprint-drones'),
    'https://reinvent.hp.com/us-en-3dprint-drones');
  assert.equal(caseStudyUrl(''), null);
  assert.equal(caseStudyUrl(undefined), null);
});
