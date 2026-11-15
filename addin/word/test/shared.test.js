// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {LAYOUT} from '../../core/constants.js';
import {parseLines, strip, tagRun} from '../../core/parse.js';
import {planTable, prepareSelection, toExample} from '../../core/plan.js';
import {AFTER_EXAMPLE, exampleTable, flatPackage, runs} from '../ooxml.js';
import {readSelection, readExampleTable} from '../selection.js';
import {untypesetPackage} from '../untypeset.js';

const fixtures = JSON.parse(readFileSync(new URL('../../../tests/fixtures/linguexx15-untypeset.json', import.meta.url)));
const authoring = JSON.parse(readFileSync(new URL('../../../tests/fixtures/shared-authoring.json', import.meta.url)));
const command = String.fromCharCode(92) + 'CommonGloss';
function selected(lines, formats = []) {
  return flatPackage(lines.map(line => `<w:p>${runs(line, formats)}</w:p>`).join(''), {withStyles: true});
}
function build(read, width) {
  const parsed = parseLines(read.lines, undefined, {shared: true});
  assert.equal(parsed.error, undefined);
  const ex = toExample(parsed.items, 0, parsed.head, parsed.shared);
  const [layout, anyJudgment] = prepareSelection(ex, {...LAYOUT, text_width_cm: width}, {formats: read.formats});
  const {plan} = planTable(ex, layout, {anyJudgment, formats: read.formats});
  const number = {id: 29, name: read.number?.bookmark || 'LxShared29', cached: read.number?.shown || '7'};
  return flatPackage(exampleTable(ex, plan, {number, formats: read.formats}) + AFTER_EXAMPLE, {withStyles: true});
}
for (const [name, fixture] of Object.entries(fixtures).filter(([n]) => n.startsWith('shared'))) {
  test(`${name}: Word packages retain shared text and bookmark identity through repeated cycles`, () => {
    for (const width of [17, 6.5]) {
      for (const input of [selected(fixture.lines), untypesetPackage(fixture.xml).pkg]) {
        let selection = input;
        const expectedNumber = readSelection(input).number || {bookmark: 'LxShared29', shown: '7'};
        for (let cycle = 0; cycle < 3; cycle++) {
          const pkg = build(readSelection(selection), width);
          assert.equal((pkg.match(/SEQ NumEx/g) || []).length, 1);
          const back = untypesetPackage(pkg);
          assert.equal(back.refusal, undefined);
          assert.deepEqual(back.lines.map(strip), fixture.lines);
          assert.deepEqual(back.number, expectedNumber);
          assert.deepEqual(readSelection(back.pkg).number, expectedNumber);
          if (width < 7) assert.ok(pkg.includes('LxCommonGlossBand'));
          selection = back.pkg;
        }
      }
    }
  });
}

test('Word shared serialization retains rich runs, grouped phrases and leading gaps', () => {
  const formats = [{}, {bold: true}, {italic: true}, {smallCaps: true}];
  const lines = [tagRun('a. *', 0) + tagRun('Alpha', 1) + tagRun(' {} {two words}', 0),
    tagRun('b. {} ', 0) + tagRun('Beta', 2), tagRun(command + ' ', 0) + tagRun('ONE', 3) + tagRun(' TWO THREE', 0)];
  let read = readSelection(selected(lines, formats));
  for (let cycle = 0; cycle < 3; cycle++) {
    const back = untypesetPackage(build(read, 17));
    assert.deepEqual(back.lines.map(strip), ['a. *Alpha {} {two words}', 'b. {} Beta {}', command + ' ONE TWO THREE']);
    read = readSelection(back.pkg);
    for (const [word, property] of [['Alpha', 'bold'], ['Beta', 'italic'], ['ONE', 'smallCaps']]) {
      const line = read.lines.find(line => strip(line).includes(word));
      const before = line.slice(0, line.indexOf(word));
      const mark = [...before].filter(c => c.charCodeAt(0) >= 0xe000).at(-1);
      assert.equal(read.formats[mark.charCodeAt(0) - 0xe000][property], true, word);
    }
  }
});

// Run the actual task-pane command against a minimal Office.js boundary.
// This verifies opt-in and rejection before insertOoxml; it does not emulate Word's renderer.
async function pane() {
  const url = new URL('../taskpane.js', import.meta.url);
  let source = readFileSync(url, 'utf8');
  const scope = {};
  for (const match of source.matchAll(/^import \{([^}]+)\} from "([^"]+)";/gm)) {
    const module = await import(new URL(match[2], url));
    for (const name of match[1].split(',').map(s => s.trim())) scope[name] = module[name];
  }
  source = source.replace(/^import .*;$/gm, '');
  const status = {}, notes = {replaceChildren() {}, appendChild() {}};
  const context = vm.createContext({...scope, Office: {onReady() {}}, document: {
    getElementById: id => id === 'status' ? status : notes,
    createElement: () => ({}),
  }});
  vm.runInContext(source + '\nglobalThis.testTypeset = typeset;', context);
  return {context, status};
}
function wordContext(pkg, insertions) {
  const fields = {items: [], load() {}};
  const range = {getRange() {return this;}, expandTo() {return this;}, fields,
    getBookmarks() {return {value: []};}};
  const sel = {...range, getOoxml: () => ({value: pkg}),
    paragraphs: {getFirst: () => ({font: {name: 'Times New Roman', size: 12, load() {}}})},
    insertOoxml: (xml, where) => insertions.push({xml, where})};
  return {sync: async () => {}, document: {getSelection: () => sel,
    body: {...range, fields}, properties: {customProperties: {items: [], load() {}}},
    getBookmarkRangeOrNullObject: () => ({isNullObject: true, load() {}})}};
}
test('Word Typeset enables shared groups and refuses invalid selections before insertion', async () => {
  const {context, status} = await pane();
  const insertions = [];
  for (const [name, {lines, errorLine}] of Object.entries(authoring.invalid)) {
    const ctx = wordContext(selected(lines), insertions);
    context.Word = {run: work => work(ctx)};
    await context.testTypeset();
    assert.equal(insertions.length, 0);
    assert.match(status.textContent, new RegExp(`Line ${errorLine}:`), name);
  }
  const ctx = wordContext(selected(fixtures.shared.lines), insertions);
  context.Word = {run: work => work(ctx)};
  await context.testTypeset();
  assert.equal(status.textContent, 'Done.');
  assert.equal(insertions.length, 1);
  assert.equal(insertions[0].where, 'Replace');
  assert.deepEqual(untypesetPackage(insertions[0].xml).lines.map(strip), fixtures.shared.lines);
  const prior = untypesetPackage(fixtures.shared.xml);
  const takeover = wordContext(prior.pkg, insertions);
  context.Word = {run: work => work(takeover)};
  await context.testTypeset();
  assert.equal(insertions.length, 2);
  assert.deepEqual(readExampleTable(insertions[1].xml).number, prior.number);
  // The tree command must still refuse explicit shared tiers.
  await context.testTypeset(true);
  assert.equal(insertions.length, 2);
  assert.match(status.textContent, /shared gloss/);
  assert.ok(readExampleTable(insertions[0].xml).rows.length);
});
