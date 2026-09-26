// SPDX-License-Identifier: GPL-3.0-or-later
//
// The core's parse against the Writer macro's own, case by case.  The
// "parsed" section of tests/fixtures/typed-examples.json is the macro's
// answer, recorded by tools/run_macro_test.py (LINGUEXX_UPDATE_GOLDEN=1),
// which also fails when the macro stops giving it.  So a change to either
// grammar fails one side until both agree again.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import {
  isMarker, isSpace, markerOf, parseLines, pullAnnot, splitWords, strip, tagRun,
} from "../parse.js";

const FIXTURES = JSON.parse(readFileSync(
  fileURLToPath(new URL("../../../tests/fixtures/typed-examples.json", import.meta.url)),
  "utf-8"));

/** The core's answer in the shape the macro's golden is recorded in. */
function asGolden(result) {
  if (result.error) return { error: result.error };
  return {
    items: result.items.map((it) => ({
      marker: strip(it.marker),
      judgment: it.judgment,
      translation: strip(it.translation),
      annot: strip(it.annot),
      tiers: it.tiers.map((words) => words.map(strip)),
    })),
  };
}

test("the golden covers every fixture", () => {
  const cases = Object.entries(FIXTURES)
    .filter(([g]) => !g.startsWith("_") && g !== "parsed")
    .flatMap(([g, cs]) => Object.keys(cs).map((n) => `${g}/${n}`));
  assert.deepEqual(Object.keys(FIXTURES.parsed).sort(), cases.sort());
});

for (const [key, want] of Object.entries(FIXTURES.parsed)) {
  const [group, name] = key.split("/");
  test(`parses ${key} as the macro does`, () => {
    const got = asGolden(parseLines(FIXTURES[group][name].lines));
    assert.deepEqual(got, want);
  });
}

// What the fixtures cannot show, because they carry no formatting.

test("a format mark follows a word through splitting", () => {
  // "the" plain, "cat" in format 3: the mark opens the word it belongs to.
  const line = "the " + tagRun("cat", 3);
  const words = splitWords(line);
  assert.equal(words.length, 2);
  assert.equal(words[1], "cat");
  assert.equal(strip(words[1]), "cat");
});

test("a mark in front of the marker does not hide it", () => {
  const line = tagRun("a. Esto es", 1);
  assert.equal(strip(markerOf(line)), "a.");
  const r = parseLines([line, tagRun("this is", 1)]);
  assert.equal(r.items[0].marker, "a.");
  assert.deepEqual(r.items[0].tiers.map((t) => t.map(strip)), [["Esto", "es"], ["this", "is"]]);
});

test("a judgment keeps the format of the word behind it", () => {
  const r = parseLines([tagRun("*Das Kind", 2), "the child"]);
  assert.equal(r.items[0].judgment, "*");
  assert.equal(r.items[0].tiers[0][0], "Das");
});

test("autocorrect's no-break spaces are spaces", () => {
  for (const c of [" ", " ", " ", "　"]) assert.ok(isSpace(c), c);
  assert.ok(!isSpace("x"));
});

test("markers: narrow on purpose", () => {
  for (const m of ["a.", "(b)", "iii.", "c)", "IV."]) assert.ok(isMarker(m), m);
  for (const w of ["Dr.", "no.", "a", "ab.", "é.", "(.)"]) assert.ok(!isMarker(w), w);
});

test("\\exannot comes off the object line, in any case, with its [spoken] form", () => {
  assert.deepEqual(pullAnnot("que Pierre \\exannot{[CP]}"), ["que Pierre ", "[CP]"]);
  assert.deepEqual(pullAnnot("x \\exannot[sp]{[TP]} y"), ["x  y", "[TP]"]);
  assert.deepEqual(pullAnnot("x \\EXANNOT{[TP]}"), ["x ", "[TP]"]);
  assert.deepEqual(pullAnnot("x \\exannot{unclosed"), ["x \\exannot{unclosed", ""]);
});
