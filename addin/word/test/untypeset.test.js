// SPDX-License-Identifier: GPL-3.0-or-later
//
// Untypeset in Word, round trip, without Word: typed lines -> the add-in's
// own table -> untypeset -> those paragraphs read again as a selection ->
// the same example, taking over the same number.  The Writer macro's suite
// asks the same of the macro (check_untypeset, check_untypeset_references).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { LAYOUT } from "../../core/constants.js";
import { parseLines, strip, tagRun } from "../../core/parse.js";
import { planTable, prepareSelection, toExample } from "../../core/plan.js";
import { exampleTable, flatPackage } from "../ooxml.js";
import { readSelection } from "../selection.js";
import { untypesetPackage } from "../untypeset.js";

const FIXTURES = JSON.parse(readFileSync(fileURLToPath(new URL("../../../tests/fixtures/typed-examples.json", import.meta.url)), "utf-8"));

function builtPackage(lines, formats = [], number = { id: 11, name: "LxEx5", cached: "4" }) {
  const ex = toExample(parseLines(lines).items);
  const [lay, aj] = prepareSelection(ex, LAYOUT, { formats });
  const { plan } = planTable(ex, lay, { anyJudgment: aj, formats });
  return flatPackage(exampleTable(ex, plan, { number, formats }), { withStyles: true });
}

/**
 * The same example, as text: format marks stripped.  Read back from Word,
 * every run carries its format's mark -- plain text is format {} -- where a
 * typed fixture carries none; that is representation, and the formats are
 * compared on their own below.
 */
const plain = (parsed) => JSON.parse(JSON.stringify(parsed, (k, v) => (typeof v === "string" ? strip(v) : v)));
const same = (a, b) => assert.deepEqual(plain(a), plain(b));

for (const [name, c] of Object.entries(FIXTURES.UNTYPESET_CASES)) {
  test(`${name}: untypeset gives the typed lines, number first`, () => {
    const u = untypesetPackage(builtPackage(c.lines), 12);
    assert.equal(u.refusal, undefined);
    assert.deepEqual(u.lines.map(strip), c.back || c.lines);
    assert.deepEqual(u.number, { bookmark: "LxEx5", shown: "4" });
  });
}

for (const group of Object.keys(FIXTURES).filter((g) => !g.startsWith("_") && g !== "parsed" && g !== "REFUSE")) {
  for (const [name, c] of Object.entries(FIXTURES[group])) {
    test(`${group}/${name}: out and back in, the same example and the same number`, () => {
      const u = untypesetPackage(builtPackage(c.lines));
      const again = readSelection(u.pkg);
      assert.equal(again.refusal, "");
      assert.deepEqual(again.number, { bookmark: "LxEx5", shown: "4" }, "the number is taken over");
      same(parseLines(again.lines), parseLines(c.lines));
    });
  }
}

test("formats survive out and back", () => {
  const formats = [{}, { smallCaps: true }, { italic: true }];
  const lines = [tagRun("Der ", 0) + tagRun("Hund", 2), tagRun("the dog.", 0) + tagRun("nom", 1)];
  const again = readSelection(untypesetPackage(builtPackage(lines, formats)).pkg);
  const words = parseLines(again.lines).items[0].tiers.flat();
  const fmtOf = (w) => again.formats[w.charCodeAt(0) - 0xe000];
  assert.deepEqual(fmtOf(words.find((w) => strip(w) === "Hund")), { italic: true });
  assert.deepEqual(fmtOf(words.find((w) => strip(w) === "dog.nom")), {});
  // numbered in the order the re-read meets them, so looked up, not assumed
  const dogNom = words.find((w) => strip(w) === "dog.nom");
  const mark = dogNom[dogNom.indexOf("nom") - 1];
  assert.deepEqual(again.formats[mark.charCodeAt(0) - 0xe000], { smallCaps: true }, "small caps on nom alone");
});

test("a table that is not an example is left alone, saying why", () => {
  const W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"';
  const plain = `<w:document ${W}><w:body><w:tbl><w:tr><w:tc><w:p><w:r><w:t>a</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>`;
  assert.match(untypesetPackage(plain).refusal, /not an example/);
});

test("a table Word joined from several examples is refused, not taken apart as one", () => {
  const one = builtPackage(["Ich habe", "I have"]);
  const tbl = one.match(/<w:tbl>.*<\/w:tbl>/s)[0];
  const joined = one.replace(tbl, tbl.replace(/<\/w:tbl>$/, "") + tbl.replace(/^<w:tbl>.*?<\/w:tblGrid>/s, ""));
  assert.match(untypesetPackage(joined).refusal, /holds 2 examples/);
});
