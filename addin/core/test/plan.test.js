// SPDX-License-Identifier: GPL-3.0-or-later
//
// The core's table plan against the converter's own plan_table(), exactly.
//
// tests/fixtures/typed-examples.plans.json is written by
// tools/addin_oracle.py from the converter's Python, on the Writer macro's
// parse of each fixture, at two text widths.  Here the same lines go
// through the core's parser and planner, and every width must be the same
// double -- deepStrictEqual, no tolerance: the arithmetic is ported in
// Python's order, so any difference is a difference in the port.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { LAYOUT } from "../constants.js";
import { parseLines } from "../parse.js";
import { planTable, prepareDocument, prepareSelection, runsOf, toExample } from "../plan.js";

const read = (rel) => JSON.parse(readFileSync(
  fileURLToPath(new URL(rel, import.meta.url)), "utf-8"));
const FIXTURES = read("../../../tests/fixtures/typed-examples.json");
const PLANS = read("../../../tests/fixtures/typed-examples.plans.json");

function corePlan(lines, textWidth, face = LAYOUT.font_name) {
  const parsed = parseLines(lines);
  const ex = toExample(parsed.items);
  const [layout, anyJudgment] = prepareDocument([ex], { ...LAYOUT, text_width_cm: textWidth, font_name: face });
  const { plan, warnings } = planTable(ex, layout, { anyJudgment });
  return {
    prepared: {
      number_cm: layout.number_cm, marker_cm: layout.marker_cm,
      judgment_cm: layout.judgment_cm, any_judgment: anyJudgment,
    },
    lead: plan.lead, columns: plan.columns, widths: plan.widths, filler: plan.filler,
    has_marker: plan.hasMarker, has_judgment: plan.hasJudgment, has_annot: plan.hasAnnot,
    bands: plan.bodies.map((_, k) => plan.grid.bandsOf(k)),
    placement: plan.grid.plans.map(([w], k) =>
      w.map((_, j) => [plan.grid.column(k, j), plan.grid.span(k, j)])),
    warnings,
  };
}

const keys = Object.keys(PLANS).filter((k) => !k.startsWith("_"));

test("the plan golden covers every fixture that parses", () => {
  const parsing = Object.entries(FIXTURES.parsed).filter(([, v]) => !v.error).map(([k]) => k);
  assert.deepEqual(keys.sort(), parsing.sort());
});

for (const key of keys) {
  const [group, name] = key.split("/");
  // keys are "17", "12", "7" -- Times -- or "17 Aptos": a width and a face
  for (const [variant, want] of Object.entries(PLANS[key])) {
    const [width, ...face] = variant.split(" ");
    test(`plans ${key} at ${variant} cm as the converter does`, () => {
      assert.deepStrictEqual(corePlan(FIXTURES[group][name].lines, Number(width), face.join(" ") || undefined), want);
    });
  }
}

// -- what the converter's golden cannot cover ------------------------------

test("small caps are measured as drawn: wider than the lowercase", () => {
  const formats = [{ smallCaps: true }];
  const plain = parseLines(["Ich schlafe", "I sleep.prs.1sg"]);
  const sc = parseLines(["Ich schlafe", "I sleep.prs.1sg"]);
  const widths = (p, f) => {
    const ex = toExample(p.items);
    const [lay, aj] = prepareDocument([ex], LAYOUT, { formats: f });
    return planTable(ex, lay, { anyJudgment: aj, formats: f }).plan.columns;
  };
  const [a, b] = [widths(plain, []), widths(sc, formats)];
  assert.equal(a[0], b[0]);
  assert.ok(b[1] > a[1], `small caps ${b[1]} should exceed lowercase ${a[1]}`);
});

test("runsOf splits a tagged cell into [text, smallCaps] runs", () => {
  const f = [{ smallCaps: false }, { smallCaps: true }];
  assert.deepEqual(runsOf("sleep-pst", f), [["sleep-", false], ["pst", true]]);
  assert.deepEqual(runsOf("plain"), [["plain", false]]);
});

test("a selection always reserves the judgment column, as the macro does", () => {
  // The add-in sees one example, never the document, so -- like the Writer
  // macro -- it cannot know that some other example is judged.  Reserving
  // the column always keeps every example's text at one x.
  const judged = toExample(parseLines(["*Das Kind", "the child"]).items);
  const plain = toExample(parseLines(["Das Kind", "the child"]).items);
  const [lj, aj] = prepareSelection(judged);
  const [lp, ap] = prepareSelection(plain);
  assert.equal(aj, true);
  assert.equal(ap, true);
  const x = (lay, ex) => {
    const { plan } = planTable(ex, lay, { anyJudgment: true });
    return plan.lead.reduce((s, w) => s + w, 0);
  };
  assert.equal(x(lj, judged), x(lp, plain), "text must start at the same x");
});

test("a selection's number column holds (00)", () => {
  const ex = toExample(parseLines(["Das Kind", "the child"]).items);
  const [lay] = prepareSelection(ex);
  assert.ok(lay.number_cm - lay.judgment_cm >= LAYOUT.number_cm);
});

test("a face is measured with its own metrics, or said to be unmeasured", async () => {
  const { advancesFor } = await import("../measure.js");
  const { ADVANCE, FACE_ADVANCE } = await import("../constants.js");
  assert.equal(advancesFor("Times New Roman").advances, ADVANCE);
  assert.equal(advancesFor("Liberation Serif").known, true);
  assert.equal(advancesFor("Aptos").advances, FACE_ADVANCE.aptos);
  assert.deepEqual([advancesFor("Arial").advances === ADVANCE, advancesFor("Arial").known], [true, false]);
  // Aptos is wider than Times, which is why it is measured at all
  const lines = ["Ich habe geschlafen", "I have slept"];
  assert.ok(corePlan(lines, 17, "Aptos").columns.every((c, i) => c >= corePlan(lines, 17).columns[i]));
});
