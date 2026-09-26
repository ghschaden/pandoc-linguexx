// SPDX-License-Identifier: GPL-3.0-or-later
//
// Untypeset, in the core: a table built from typed lines, read back, must
// be the same example.  UNTYPESET_CASES say more -- the lines themselves,
// exactly as typed, which is what the Writer macro's suite requires of the
// macro (check_untypeset).

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { LAYOUT, NAMES } from "../constants.js";
import { parseLines, strip, tagRun } from "../parse.js";
import { planTable, prepareDocument, prepareSelection, toExample } from "../plan.js";
import { tableRows } from "../table.js";
import { isExampleTable, leadColumns, readTable } from "../untypeset.js";

const FIXTURES = JSON.parse(readFileSync(fileURLToPath(new URL("../../../tests/fixtures/typed-examples.json", import.meta.url)), "utf-8"));

/**
 * Built as a host builds it, then read as a host reads it: style names and
 * text.  *converter* builds it by the converter's rule instead, which gives
 * an example no judgment column when nothing is judged -- the case where
 * the text's first column is found from the translation, and the only one.
 */
function built(lines, width = 17, formats = [], converter = false) {
  const ex = toExample(parseLines(lines).items);
  const [lay, aj] = converter ? prepareDocument([ex], { ...LAYOUT, text_width_cm: width }, { formats })
    : prepareSelection(ex, { ...LAYOUT, text_width_cm: width }, { formats });
  const t = tableRows(ex, planTable(ex, lay, { anyJudgment: aj, formats }).plan);
  return t.rows.map((row) => row.map((c) => ({ style: c.style, text: c.content.kind === "text" ? c.content.text : "" })));
}

const same = (a, b) => assert.deepEqual(JSON.parse(JSON.stringify(a)), JSON.parse(JSON.stringify(b)));

for (const [name, c] of Object.entries(FIXTURES.UNTYPESET_CASES)) {
  test(`untypesets ${name} back to the lines it was typed as`, () => {
    const got = readTable(built(c.lines));
    assert.equal(got.error, undefined);
    assert.deepEqual(got.lines.map(strip), c.back || c.lines);
  });
}

for (const group of Object.keys(FIXTURES).filter((g) => !g.startsWith("_") && g !== "parsed" && g !== "REFUSE")) {
  for (const [name, c] of Object.entries(FIXTURES[group])) {
    for (const width of [17, 7]) {
      test(`${group}/${name} at ${width} cm: built and read back, the same example`, () => {
        const table = built(c.lines, width);
        assert.ok(isExampleTable(table));
        same(parseLines(readTable(table).lines), parseLines(c.lines));
      });
    }
    // Built by the converter's rule: no judgment column unless judged, so
    // an unjudged example with a translation is read by its translation's
    // first column, and one with neither must say it cannot be read.
    test(`${group}/${name}, converted: read back, or refused for want of a landmark`, () => {
      const table = built(c.lines, 17, [], true);
      const ex = parseLines(c.lines).items;
      const landmark = ex.some((it) => it.judgment) || ex.some((it) => it.translation);
      const got = readTable(table);
      if (landmark) same(parseLines(got.lines), parseLines(c.lines));
      else assert.match(got.error, /does not say where its text begins/);
    });
  }
}

test("formatting survives the round trip, mark for mark", () => {
  const formats = [{}, { smallCaps: true }, { italic: true }];
  const lines = [tagRun("Der ", 0) + tagRun("Hund", 2), tagRun("the dog.", 0) + tagRun("nom", 1)];
  const back = readTable(built(lines, 17, formats)).lines;
  same(parseLines(back), parseLines(lines));
});

test("a table somebody built is not an example", () => {
  assert.ok(!isExampleTable([[{ style: "Normal", text: "a" }], [{ style: "Normal", text: "b" }], [{ style: "Normal", text: "c" }]]));
  assert.ok(!isExampleTable([]));
});

test("no judgment column and no translation: it says so", () => {
  const rows = [[{ style: NAMES.SPACE_ABOVE, text: "" }], [{ style: NAMES.CELL_PARA, text: "x" }], [{ style: NAMES.SPACE_BELOW, text: "" }]];
  assert.equal(leadColumns(rows).lead, -1);
  assert.match(readTable(rows).error, /does not say where its text begins/);
});
