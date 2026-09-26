// SPDX-License-Identifier: GPL-3.0-or-later
//
// The Word add-in's markup against the converter's own, string for string.
//
// tests/fixtures/typed-examples.docx.json is DocxEmitter.example() on the
// macro's parse of every fixture (tools/addin_oracle.py).  The same lines
// go through the core and ooxml.js here, and the w:tbl must be identical:
// an example the add-in inserts and one the converter wrote are then the
// same object.  The one substitution is the translation, which the
// converter draws through LaTeX (' becomes a curly quote) and the add-in
// leaves as typed -- the golden records the drawn text and it is used.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { LAYOUT } from "../../core/constants.js";
import { parseLines } from "../../core/parse.js";
import { planTable, prepareDocument, toExample } from "../../core/plan.js";
import {
  AFTER_EXAMPLE, dxa, exampleTable, flatPackage, pyRound, rPr, runs, sequenceRef,
} from "../ooxml.js";
import { STYLE_IDS } from "../styles.js";
import { wellFormed } from "../xml.js";

const read = (rel) => JSON.parse(readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf-8"));
const FIXTURES = read("../../../tests/fixtures/typed-examples.json");
const DOCX = read("../../../tests/fixtures/typed-examples.docx.json");

function table(lines, width, drawn) {
  const ex = toExample(parseLines(lines).items);
  const bodies = ex.body ? [ex.body] : ex.items.map((i) => i.body);
  bodies.forEach((b, k) => { b.translation = drawn[k]; });
  const [layout, anyJudgment] = prepareDocument([ex], { ...LAYOUT, text_width_cm: width });
  const { plan } = planTable(ex, layout, { anyJudgment });
  return exampleTable(ex, plan, { number: { id: 1, name: "NumEx0", cached: "1" } });
}

const keys = Object.keys(DOCX).filter((k) => !k.startsWith("_"));

test("the markup golden covers every fixture that parses", () => {
  const parsing = Object.entries(FIXTURES.parsed).filter(([, v]) => !v.error).map(([k]) => k);
  assert.deepEqual(keys.sort(), parsing.sort());
});

for (const key of keys) {
  const [group, name] = key.split("/");
  for (const [width, want] of Object.entries(DOCX[key])) {
    test(`writes ${key} at ${width} cm as the converter does`, () => {
      assert.equal(table(FIXTURES[group][name].lines, Number(width), want.translations_drawn), want.table);
    });
  }
}

test("pyRound rounds halves to even, as Python's round() does", () => {
  assert.deepEqual([0.5, 1.5, 2.5, 3.5, -0.5, 2.4999, 2.5001].map(pyRound), [0, 2, 2, 4, 0, 2, 3]);
  assert.equal(dxa(1), 567);
});

test("run properties are in schema order, and plain text has none", () => {
  assert.equal(rPr(undefined), "");
  assert.equal(rPr({}), "");
  assert.equal(
    rPr({ vertAlign: "subscript", underline: "single", smallCaps: true, italic: true, bold: true }),
    '<w:rPr><w:b/><w:i/><w:smallCaps/><w:u w:val="single"/><w:vertAlign w:val="subscript"/></w:rPr>');
  // a character style carries its own small caps; saying it twice is noise
  assert.equal(rPr({ rStyle: "LxLeipzig", smallCaps: true }), '<w:rPr><w:rStyle w:val="LxLeipzig"/></w:rPr>');
});

test("a tagged cell becomes one run per format", () => {
  const formats = [{ smallCaps: true }, undefined];
  assert.equal(runs("sleep-\ue000pst", formats),
    '<w:r><w:t xml:space="preserve">sleep-</w:t></w:r>' +
    '<w:r><w:rPr><w:smallCaps/></w:rPr><w:t xml:space="preserve">pst</w:t></w:r>');
  assert.equal(runs("a<b & c"), '<w:r><w:t xml:space="preserve">a&lt;b &amp; c</w:t></w:r>');
});

test("a reference is a REF field cached at its number, in brackets unless bare", () => {
  const r = sequenceRef("LxEx7", "4");
  assert.match(r, /REF LxEx7 \\h/);
  assert.match(r, /separate"\/><\/w:r><w:r><w:t xml:space="preserve">4<\/w:t>/);
  assert.ok(r.startsWith('<w:r><w:t xml:space="preserve">(</w:t></w:r>'));
  assert.ok(!sequenceRef("LxEx7", "4", { bare: true }).includes("(</w:t>"));
});

test("the package is well-formed, with and without its styles", () => {
  const t = table(["Ich habe geschlafen", "I have slept"], 17, [""]);
  for (const withStyles of [false, true]) {
    const pkg = flatPackage(t + AFTER_EXAMPLE, { withStyles });
    assert.equal(wellFormed(pkg), true);
    assert.equal(pkg.includes("/word/styles.xml"), withStyles);
  }
  const styled = flatPackage(t, { withStyles: true });
  for (const id of STYLE_IDS) assert.ok(styled.includes(`w:styleId="${id}"`), id);
});
