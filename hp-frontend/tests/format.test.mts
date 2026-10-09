// Display casing for vendor text the source sent in lowercase.
//
// Run: npm test   (node --test; Node 23.6+ runs the TypeScript directly)

import { test } from 'node:test';
import assert from 'node:assert/strict';

import { displayCase, displayPlace, fmtDate } from '../src/lib/format.ts';

const NAME = { name: true };

test('places and industries read as proper nouns', () => {
  assert.equal(displayPlace('tokyo, japan'), 'Tokyo, Japan');
  assert.equal(displayPlace('hà nội, viet nam'), 'Hà Nội, Viet Nam');
  assert.equal(displayCase('semiconductor manufacturing'), 'Semiconductor Manufacturing');
  assert.equal(displayCase('it services and it consulting'), 'IT Services and IT Consulting');
  assert.equal(displayCase('transportation/trucking/railroad'), 'Transportation/Trucking/Railroad');
});

test('text the source already cased is left exactly as written', () => {
  assert.equal(displayCase('Semiconductor and Related Device Manufacturing'),
    'Semiconductor and Related Device Manufacturing');
  assert.equal(displayCase('jQuery'), 'jQuery');
});

test('company names keep their legal forms and short codes', () => {
  assert.equal(displayCase('verigy us', NAME), 'Verigy US');
  assert.equal(displayCase('crea srl', NAME), 'Crea SRL');
  assert.equal(displayCase('japan airlines co ltd', NAME), 'Japan Airlines Co Ltd');
  assert.equal(displayCase('elektrisola malaysia sdn bhd', NAME), 'Elektrisola Malaysia Sdn Bhd');
  assert.equal(displayCase('pt charoen pokphand indonesia tbk', NAME), 'PT Charoen Pokphand Indonesia Tbk');
  assert.equal(displayCase('bdo', NAME), 'BDO');
  assert.equal(displayCase('australian submarine corporation (asc)', NAME),
    'Australian Submarine Corporation (ASC)');
  assert.equal(displayCase('w2bi a member of the advantest group', NAME),
    'W2bi a Member of the Advantest Group');
  // An everyday word that is also a country code stays a word.
  assert.equal(displayCase('daikin czech republic in pilsen', NAME), 'Daikin Czech Republic in Pilsen');
});

test('a Bombora "category: topic" cases each side', () => {
  assert.equal(displayCase('business services: vinson & elkins llp'),
    'Business Services: Vinson & Elkins LLP');
});

test('empty and odd input never throws', () => {
  assert.equal(displayCase(null), '');
  assert.equal(displayCase('  '), '');
  assert.equal(displayPlace(''), '');
});

test('dates read as "Sep 17, 2026"; anything else passes through', () => {
  assert.equal(fmtDate('2026-09-17T12:00:00Z'), 'Sep 17, 2026');
  assert.equal(fmtDate('not a date'), 'not a date');
  assert.equal(fmtDate('', '—'), '—');
});
