// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseLines, strip, splitSharedWords, tagRun} from '../../core/parse.js';
import {prepareJob, untypesetJob} from '../job.js';

import {LAYOUT} from '../../core/constants.js';
import {planTable, prepareDocument, toExample} from '../../core/plan.js';
import {tableRows} from '../../core/table.js';
import {dxa} from '../../word/ooxml.js';
import {parse, child, findAll, textOf} from '../../word/xml.js';

const command = String.fromCharCode(92) + 'CommonGloss';
const annotate = (text) => String.fromCharCode(92) + 'exannot{' + text + '}';
const read = (lines, width = 9638) => ({paragraphs: lines.map(text => ({inTable: false,
  runs: typeof text === 'string' ? [{text}] : text})), widthTwips: width,
  font: 'Times New Roman', bookmarks: []});
const plain = (back) => back.lines.map(runs => runs.map(r => r.text).join(''));
const tableRead = (job) => ({pos: 0, number: {bookmark: job.bookmark, shown: '1'},
  rows: job.rows.map(row => row.map(c => ({style: c.style,
    runs: c.content.kind === 'text' ? c.content.runs.map(r => ({text: r.text, ...r.fmt})) : []})))});

const fixtures = JSON.parse(readFileSync(new URL('../../../tests/fixtures/linguexx15-untypeset.json', import.meta.url)));
for (const [name, fixture] of Object.entries(fixtures).filter(([name]) => name.startsWith('shared'))) {
  test(`${name}: fresh authoring and repeated round trips, including narrow bands`, () => {
    for (const width of [9638, 3700]) {
      let input = read(fixture.lines, width);
      let number;
      for (let cycle = 0; cycle < 3; cycle++) {
        const {job, refusal} = prepareJob(input, 1e12);
        assert.equal(refusal, undefined);
        assert.equal(job.rows.flat().filter(c => c.content.kind === 'number').length, 1);
        if (number) assert.equal(job.bookmark, number.bookmark);
        const back = untypesetJob(tableRead(job));
        assert.equal(back.refusal, undefined);
        assert.deepEqual(plain(back.back), fixture.lines);
        number = back.back.number;
        input = {...read(plain(back.back), width), numbers: [{...number, paragraph: 0}]};
      }
    }
  });
}

for (const [name, fixture] of Object.entries(fixtures).filter(([name]) => name.startsWith('shared'))) {
  test(`${name}: grid, spans, structural styles and row text agree with the converter`, () => {
    const parsed = parseLines(fixture.lines, undefined, {shared: true});
    const ex = toExample(parsed.items, 0, parsed.head, parsed.shared);
    const [layout, anyJudgment] = prepareDocument([ex], {...LAYOUT, text_width_cm: fixture.width || 17});
    const {plan} = planTable(ex, layout, {anyJudgment});
    const got = tableRows(ex, plan);
    const xml = parse(fixture.xml), table = findAll(xml, 'w:tbl')[0];
    const expectedGrid = findAll(child(table, 'w:tblGrid'), 'w:gridCol').map(c => Number(c.attrs['w:w']));
    assert.deepEqual(got.grid.map(dxa), expectedGrid);
    const expectedRows = findAll(table, 'w:tr').map(row => row.children.filter(c => c.name === 'w:tc'));
    assert.equal(got.rows.length, expectedRows.length);
    got.rows.forEach((row, r) => {
      assert.equal(row.length, expectedRows[r].length, `row ${r}`);
      row.forEach((cell, c) => {
        const expected = expectedRows[r][c], pr = child(expected, 'w:tcPr');
        assert.equal(cell.span, Number(child(pr, 'w:gridSpan')?.attrs['w:val'] || 1));
        assert.equal(dxa(cell.widthCm), Number(child(pr, 'w:tcW').attrs['w:w']));
        const style = findAll(expected, 'w:pStyle')[0]?.attrs['w:val'];
        assert.equal(cell.style, style);
        if (cell.content.kind !== 'number') assert.equal(cell.content.text || '', findAll(expected, 'w:t').map(textOf).join(''));
      });
    });
  });
}

test('grouped words, leading/interior gaps and unequal lengths retain slots', () => {
  const lines = ['a. {} {two words} C', 'b. X', command + ' ONE TWO THREE'];
  const {job} = prepareJob(read(lines));
  assert.deepEqual(plain(untypesetJob(tableRead(job)).back),
    ['a. {} {two words} C', 'b. X {} {}', command + ' ONE TWO THREE']);
  assert.deepEqual(splitSharedWords(tagRun('{} {two words} {}', 0)).map(strip), ['', 'two words', '']);
});

test('shared rich text and annotated variants retain bold, italic and small caps', () => {
  const lines = [[{text: 'a. *'}, {text: 'Alpha', bold: true}, {text: ' {} C' + annotate('ANNA')}],
    [{text: 'b. Beta ', italic: true}, {text: 'Longer Delta'}],
    [{text: command + ' '}, {text: 'ONE', smallCaps: true}, {text: ' TWO THREE'}]];
  const {job} = prepareJob(read(lines));
  const {back} = untypesetJob(tableRead(job));
  for (const [word, format] of [['Alpha', 'bold'], ['Beta', 'italic'], ['ONE', 'smallCaps']]) {
    const run = back.lines.flat().find(r => r.text.includes(word));
    assert.equal(run.fmt[format], true, word);
  }
});

test('invalid shared groups are refused; a following valid operation succeeds', () => {
  const tier = command + ' ONE TWO';
  for (const lines of [[tier], ['a. A', command], ['a. A', 'a. B', tier],
    ['a. A', tier, 'b. B'], ['a. A', 'extra tier', tier], ['a. A', tier, 'T', tier],
    ['a. A', tier, 'T', 'extra translation'], ['a. {A', tier], ['a. A}', tier]]) {
    const input = read(lines), before = structuredClone(input);
    const result = prepareJob(input);
    assert.match(result.refusal, /Line/);
    assert.equal(result.job, undefined);
    assert.deepEqual(input, before);
    assert.ok(prepareJob(read(['a. A', tier])).job);
  }
  assert.ok(prepareJob(read([command + 'ary'])).job);
  assert.match(prepareJob(read(['a. A', tier]), 0, {trees: true}).refusal, /shared gloss/);
  assert.match(parseLines(['a. A', tier]).error, /shared gloss/, 'shared parsing requires explicit opt-in; tree parsing remains protected');
});
