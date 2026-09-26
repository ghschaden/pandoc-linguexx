// SPDX-License-Identifier: GPL-3.0-or-later
//
// The layout settings: read as the macro reads them (LxOpt), refused as it
// refuses them (LxWriteLayout), and applied as LxLayOut applies them.

import { test } from "node:test";
import assert from "node:assert/strict";

import { LAYOUT, NAMES } from "../constants.js";
import { parseLines } from "../parse.js";
import { planTable, prepareSelection, toExample } from "../plan.js";
import { tableRows } from "../table.js";
import { DEFAULTS, OPT, checkSettings, effectiveIndent, readSettings, spacingPlan } from "../settings.js";
import { exampleTable } from "../../word/ooxml.js";

test("a document with no settings has the defaults", () => {
  assert.deepEqual(readSettings(), { ...DEFAULTS });
  assert.deepEqual(DEFAULTS, { indentCm: 0, numberCm: LAYOUT.number_cm, markerCm: LAYOUT.marker_cm,
    aboveCm: LAYOUT.space_cm, belowCm: LAYOUT.space_cm });
});

test("settings are read as LxOpt reads them: prose and out-of-range are ignored", () => {
  const s = readSettings({ [OPT.indent]: 0.9, [OPT.number]: "2", [OPT.marker]: "wide" }, { aboveCm: 0.3 });
  assert.deepEqual(s, { indentCm: 0.9, numberCm: 2, markerCm: DEFAULTS.markerCm, aboveCm: 0.3, belowCm: DEFAULTS.belowCm });
  assert.equal(readSettings({ [OPT.indent]: 11 }).indentCm, 0);
  assert.equal(readSettings({ [OPT.indent]: -1 }).indentCm, 0);
});

test("refused, not clamped, with the macro's words", () => {
  assert.equal(checkSettings(DEFAULTS), "");
  for (const bad of [-0.1, 10.5, NaN]) {
    assert.equal(checkSettings({ ...DEFAULTS, numberCm: bad }), "Every length has to be between 0 and 10 cm.");
  }
});

test("equal spacings live on the parent, unequal ones on each side", () => {
  assert.deepEqual(spacingPlan(0.3, 0.3), [
    { style: NAMES.SPACE_PARA, cm: 0.3 }, { style: NAMES.SPACE_ABOVE, inherit: true },
    { style: NAMES.SPACE_BELOW, inherit: true }]);
  assert.deepEqual(spacingPlan(0.3, 0.45), [
    { style: NAMES.SPACE_ABOVE, cm: 0.3 }, { style: NAMES.SPACE_BELOW, cm: 0.45 }]);
});

const glossed = () => toExample(parseLines(["Ich habe geschlafen", "I have slept"]).items);
const sum = (xs) => xs.reduce((a, b) => a + b, 0);

test("the indent comes off the text block, and sets the table in", () => {
  const ex = glossed();
  const [lay] = prepareSelection(ex, LAYOUT, { settings: { indentCm: 1.5 } });
  assert.equal(lay.indent_cm, 1.5);
  assert.equal(lay.text_width_cm, LAYOUT.text_width_cm - 1.5);
  const { plan } = planTable(ex, lay, { anyJudgment: true });
  assert.ok(Math.abs(sum(plan.widths) - (LAYOUT.text_width_cm - 1.5)) < 1e-9, "the table fills what is left");
  assert.equal(tableRows(ex, plan).indentCm, 1.5);
  const xml = exampleTable(ex, plan);
  assert.match(xml, /<w:tblW w:w="\d+" w:type="dxa"\/><w:tblInd w:w="850" w:type="dxa"\/><w:tblLayout/);
  // and none at all without an indent: the converter's markup, unchanged
  const [plain] = prepareSelection(ex, LAYOUT);
  assert.ok(!exampleTable(ex, planTable(ex, plain, { anyJudgment: true }).plan).includes("tblInd"));
});

test("an indent is at most half the text block", () => {
  assert.equal(effectiveIndent(12, 17), 8.5);
  assert.equal(prepareSelection(glossed(), LAYOUT, { settings: { indentCm: 12 } })[0].indent_cm, 8.5);
});

test("the number and letter settings are floors, not exact widths", () => {
  const ex = glossed();
  const [base] = prepareSelection(ex, LAYOUT);
  const [wide] = prepareSelection(ex, LAYOUT, { settings: { numberCm: 2.5 } });
  assert.ok(Math.abs(wide.number_cm - wide.judgment_cm - 2.5) < 1e-9);
  // a floor below what "(00)" needs does not squeeze the number
  const [narrow] = prepareSelection(ex, LAYOUT, { settings: { numberCm: 0 } });
  assert.ok(narrow.number_cm > 0.5 && narrow.number_cm <= base.number_cm);
  const para = toExample(parseLines(["a. Ich habe", "I have", "b. Du hast", "you have"]).items);
  const [m] = prepareSelection(para, LAYOUT, { settings: { markerCm: 1.4 } });
  assert.ok(Math.abs(m.marker_cm - m.judgment_cm - 1.4) < 1e-9);
});
