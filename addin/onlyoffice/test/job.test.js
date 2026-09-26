// SPDX-License-Identifier: GPL-3.0-or-later
//
// The OnlyOffice plugin's pure half, and its bundle.  The editor half
// (commands.js) runs in Document Builder: tools/run_onlyoffice_test.mjs.

import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

import { LAYOUT } from "../../core/constants.js";
import { parseLines, strip } from "../../core/parse.js";
import { planTable, prepareSelection, toExample } from "../../core/plan.js";
import { tableRows } from "../../core/table.js";
import { dxa } from "../../word/ooxml.js";
import { STYLE_IDS } from "../../word/styles.js";
import { linesFromRead, prepareJob, runsOf, stylesJob } from "../job.js";

const run = (text, extra = {}) => ({ text, bold: false, italic: false, smallCaps: false,
  underline: false, vertAlign: "baseline", style: "", ...extra });
const read = (paragraphs, extra = {}) => ({ paragraphs, bookmarks: [], widthTwips: 9638, font: "Times New Roman", error: "", ...extra });

test("the styles are the converter's, restated for the builder", () => {
  const styles = stylesJob();
  assert.deepEqual(styles.map((s) => s.name), [...STYLE_IDS]);
  const by = Object.fromEntries(styles.map((s) => [s.name, s]));
  assert.deepEqual(by.LxExampleCell.para, { before: 0, after: 0, line: 240, lineRule: "auto", firstLine: 0 });
  assert.equal(by.LxTranslation.basedOn, "LxExampleCell");
  assert.equal(by.LxTranslation.para.before, 57);
  assert.equal(by.LxJudgmentCell.para.jc, "right");
  assert.equal(by.LxAnnot.para.jc, "left", "OOXML's start is the builder's left");
  assert.equal(by.LxExampleSpace.para.lineRule, "exact");
  assert.equal(by.LxExampleSpace.para.line, Math.round(LAYOUT.space_cm * 567));
  assert.equal(by.LxExampleSpace.run.size, 2);
  assert.deepEqual([by.LxLeipzig.type, by.LxLeipzig.run.smallCaps], ["run", true]);
  // parents before children, which is the order commands.js creates them in
  const seen = new Set();
  for (const s of styles) { if (s.basedOn) assert.ok(seen.has(s.basedOn), s.name); seen.add(s.name); }
});

test("runs become lines: a paragraph or a \\r run ends one; formats ride along", () => {
  const sel = linesFromRead(read([
    { inTable: false, runs: [run("Ich habe"), run("\r"), run("I "), run("have", { smallCaps: true })] },
    { inTable: false, runs: [run("‘I have.’")] },
  ]));
  assert.equal(sel.refusal, "");
  assert.deepEqual(sel.lines.map(strip), ["Ich habe", "I have", "‘I have.’"]);
  const fmts = sel.formats.map((f) => JSON.stringify(f));
  assert.ok(fmts.includes('{"smallCaps":true}'));
  assert.ok(fmts.includes("{}"));
});

test("only what a linguist marks is a format, and baseline is none", () => {
  const sel = linesFromRead(read([{ inTable: false, runs: [
    run("a", { style: "LxLeipzig", bold: true, italic: true, underline: true, vertAlign: "subscript" }),
  ] }]));
  assert.deepEqual(sel.formats, [{ rStyle: "LxLeipzig", bold: true, italic: true, underline: "single", vertAlign: "subscript" }]);
  assert.deepEqual(linesFromRead(read([{ inTable: false, runs: [run("b")] }])).formats, [{}]);
});

test("a selection inside a table is refused, as is nothing selected", () => {
  assert.match(prepareJob(read([{ inTable: true, runs: [run("x")] }])).refusal, /inside a table/);
  assert.match(prepareJob(read([], { error: "Select the lines of an example first." })).refusal, /Select/);
  assert.match(prepareJob(read([{ inTable: false, runs: [run("x y")] }, { inTable: false, runs: [run("b. z")] }])).refusal,
    /sub-example letter/);
});

test("the job is core/table.js's rows in twips, runs split by format", () => {
  const r = read([{ inTable: false, runs: [run("Ich habe")] }, { inTable: false, runs: [run("I "), run("have", { italic: true })] }]);
  const { job } = prepareJob(r, 1e12);
  const sel = linesFromRead(r);
  const ex = toExample(parseLines(sel.lines).items);
  const [lay, aj] = prepareSelection(ex, { ...LAYOUT, text_width_cm: 9638 / 566.93 }, { formats: sel.formats });
  const t = tableRows(ex, planTable(ex, lay, { anyJudgment: aj, formats: sel.formats }).plan);
  assert.deepEqual(job.grid, t.grid.map(dxa));
  assert.equal(job.widthTwips, dxa(t.widthCm));
  assert.deepEqual(job.rows.map((row) => row.map((c) => [c.span, c.widthTwips, c.style, c.content.kind])),
    t.rows.map((row) => row.map((c) => [c.span, dxa(c.widthCm), c.style, c.content.kind])));
  const cells = job.rows.flat().filter((c) => c.content.kind === "text").map((c) => c.content.runs);
  assert.ok(cells.some((runs) => runs.length === 1 && runs[0].text === "have" && runs[0].fmt.italic));
  assert.equal(job.rows.flat().filter((c) => c.content.kind === "number").length, 1);
  assert.match(job.bookmark, /^LxEx/);
});

test("a face the estimate does not describe is noted", () => {
  const { notes } = prepareJob(read([{ inTable: false, runs: [run("Ich habe")] }, { inTable: false, runs: [run("I have")] }],
    { font: "Arial" }));
  assert.ok(notes.some((n) => /Times New Roman.*Arial/.test(n)));
});

test("runsOf keeps a cell's formats apart", () => {
  assert.deepEqual(runsOf("sleep-pst", [{}, { smallCaps: true }]),
    [{ text: "sleep-", fmt: {} }, { text: "pst", fmt: { smallCaps: true } }]);
});

// -- the bundle ------------------------------------------------------------

const BUNDLE = fileURLToPath(new URL(
  "../../../dist/onlyoffice/{D71895BD-806D-4964-ACA4-0A531FE92454}/linguexx.js", import.meta.url));
const FIXTURES = JSON.parse(readFileSync(fileURLToPath(new URL("../../../tests/fixtures/typed-examples.json", import.meta.url)), "utf-8"));

test("the plugin's linguexx.js gives the modules' answers", { skip: !existsSync(BUNDLE) && "run make onlyoffice first" }, () => {
  const ctx = {};
  vm.createContext(ctx);
  vm.runInContext(readFileSync(BUNDLE, "utf-8") + ";this.LinguExx = LinguExx;", ctx);
  const L = ctx.LinguExx;
  for (const group of Object.keys(FIXTURES).filter((g) => !g.startsWith("_") && g !== "parsed")) {
    for (const [name, c] of Object.entries(FIXTURES[group])) {
      assert.deepEqual(JSON.parse(JSON.stringify(L.parseLines(c.lines))), parseLines(c.lines), `${group}/${name}`);
    }
  }
  const r = read([{ inTable: false, runs: [run("*Das Kind")] }, { inTable: false, runs: [run("the "), run("child", { smallCaps: true })] }]);
  assert.deepEqual(JSON.parse(JSON.stringify(L.prepareJob(r, 7))), prepareJob(r, 7));
});

test("measured for the document's face: Aptos by its own metrics, and without a note", () => {
  const r = (font) => read([{ inTable: false, runs: [run("Ich habe geschlafen")] }, { inTable: false, runs: [run("I have slept")] }],
    { font, sizeHalfPt: 24 });
  const aptos = prepareJob(r("Aptos"));
  const times = prepareJob(r("Times New Roman"));
  assert.deepEqual(aptos.notes, []);
  assert.ok(aptos.job.grid.slice(0, -1).reduce((a, b) => a + b) > times.job.grid.slice(0, -1).reduce((a, b) => a + b));
});
