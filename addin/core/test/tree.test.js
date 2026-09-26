// SPDX-License-Identifier: GPL-3.0-or-later
//
// The core's tree reader and layout against the Writer macro's, exactly.
//
// tests/fixtures/trees.json's "laid_out" is the macro's own reading of
// every tree fixture and its layout with the recorded label widths handed
// in (tools/run_macro_test.py, TreeLayoutQuiet).  Here the same lines go
// through the core with the same widths, and every position must be the
// same double.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { strip } from "../parse.js";
import { TREE, isMoveLine, layoutTree, parseTreeLines, readTree, treeShapes, treeWidth } from "../tree.js";

const TREES = JSON.parse(readFileSync(
  fileURLToPath(new URL("../../../tests/fixtures/trees.json", import.meta.url)), "utf-8"));
const LAID = TREES.laid_out;
const groups = (keep) => Object.entries(TREES).filter(([g]) => keep(g))
  .flatMap(([group, cs]) => Object.entries(cs).map(([name, c]) => [`${group}/${name}`, c.lines]));
const GOLDENS = ["laid_out", "items_parsed"];
// one tree's lines each; ITEM groups are whole selections for the tree command
const cases = groups((g) => !g.startsWith("_") && !g.startsWith("ITEM") && !GOLDENS.includes(g));
const selections = groups((g) => g.startsWith("ITEM"));

test("the tree golden covers every tree fixture", () => {
  assert.deepEqual(cases.map(([k]) => k).sort(), Object.keys(LAID).sort());
});

/** The core's answer in the golden's shape. */
function coreTree(lines, widths) {
  const tree = readTree(lines);
  if (tree.error) return { error: tree.error };
  const err = layoutTree(tree, (label) => widths[strip(label)]);
  if (err) return { error: err };
  return {
    judgment: tree.judgment,
    widths,
    nodes: tree.nodes.map((n) => ({
      label: strip(n.label), name: n.name, roof: n.roof, kid: n.kid, sib: n.sib, depth: n.depth, w: n.w, x: n.x,
    })),
    arrows: tree.arrows.map((a) => ({ from: a.from, to: a.to, lane: a.lane })),
  };
}

for (const [key, lines] of cases) {
  test(`reads and lays out ${key} as the macro does`, () => {
    assert.deepStrictEqual(coreTree(lines, LAID[key].widths || {}), LAID[key]);
  });
}

test("the item golden covers every tree selection", () => {
  assert.deepEqual(selections.map(([k]) => k).sort(), Object.keys(TREES.items_parsed).sort());
});

for (const [key, lines] of selections) {
  test(`parses ${key} as the tree command does`, () => {
    const got = parseTreeLines(lines);
    const want = TREES.items_parsed[key];
    if (got.error) return assert.deepStrictEqual({ error: got.error }, want);
    assert.deepStrictEqual({
      items: got.items.map((it) => ({
        marker: strip(it.marker), judgment: it.judgment, translation: strip(it.translation),
        annot: strip(it.annot), tiers: it.tiers, tree: it.tree.map(strip),
      })),
    }, want);
  });
}

// -- what the golden does not reach ----------------------------------------

const laid = (key) => {
  const tree = readTree(cases.find(([k]) => k === key)[1]);
  layoutTree(tree, (label) => LAID[key].widths[strip(label)]);
  return tree;
};
const LINE_H = 480; // any label height will do for the geometry

test("every branch runs from its parent's box to its child's", () => {
  for (const [key] of cases.filter(([k]) => !LAID[k].error)) {
    const tree = laid(key);
    const s = treeShapes(tree, LINE_H);
    const box = new Map(s.labels.map((l) => [l.node, l]));
    for (const [x0, y0, x1, y1] of s.lines) {
      const parent = s.labels.find((l) => l.y + l.h === y0 && x0 === l.x + l.w / 2);
      const child = s.labels.find((l) => l.y === y1 && x1 === l.x + l.w / 2);
      assert.ok(parent && child, `${key}: a branch (${x0}, ${y0})-(${x1}, ${y1}) joins no two boxes`);
    }
    assert.equal(s.lines.length + s.roofs.length, tree.nodes.length - 1, key);
    assert.equal(box.size, tree.nodes.filter((n) => strip(n.label)).length, key);
  }
});

test("no two boxes on one tier overlap, and a tier's gap is kept", () => {
  for (const [key] of cases.filter(([k]) => !LAID[k].error)) {
    const s = treeShapes(laid(key), LINE_H);
    const tiers = Map.groupBy(s.labels, (l) => l.y);
    for (const row of tiers.values()) {
      row.sort((a, b) => a.x - b.x);
      for (let i = 1; i < row.length; i++) {
        assert.ok(row[i].x - (row[i - 1].x + row[i - 1].w) >= TREE.NODE_GAP_CM * 1000 - 1e-9,
          `${key}: "${strip(row[i - 1].text)}" and "${strip(row[i].text)}" are too close`);
      }
    }
  }
});

test("an arrow runs below the tree and lands on the underside of its target", () => {
  const tree = laid("MOVES/wh");
  const s = treeShapes(tree, LINE_H);
  assert.equal(s.arrows.length, 1);
  const deepest = Math.max(...s.labels.map((l) => l.y + l.h));
  const [[x0], [, lane], , [x3, y3]] = s.arrows[0];
  assert.ok(lane > deepest, "the lane is under every label");
  assert.equal(x0, tree.nodes[tree.arrows[0].from].x);
  assert.equal(x3, tree.nodes[tree.arrows[0].to].x);
  assert.equal(y3 - TREE.HEAD_LEN_CM * 1000, s.heads[0][0][1], "the line ends where the head begins");
  // the run under the tree is not the drawing's bottom edge: in a table
  // that edge is the next row's top, which OnlyOffice painted over it
  assert.ok(s.height >= lane + TREE.GUTTER_GAP_CM * 1000, `${s.height} leaves no room under the lane at ${lane}`);
});

test("the tree starts at x = 0 and its width is its rightmost box", () => {
  const tree = laid("TREES/deep");
  const s = treeShapes(tree, LINE_H);
  assert.equal(Math.min(...s.labels.map((l) => l.x)), 0);
  assert.equal(s.width, treeWidth(tree.nodes));
});

test("a label keeps the formatting it began in, not the next one's", () => {
  // "sg" typed in small caps before a plain "]": the scanner sees the
  // plain mark after the label, which is the next label's, not this one's.
  const [plain, caps] = ["", ""];
  const tree = readTree([`${plain}[DP [N ${caps}sg${plain}] [D ${plain}the]]`]);
  assert.equal(tree.error, undefined);
  assert.deepEqual(tree.nodes.map((n) => n.label), [`${plain}DP`, `${plain}N`, `${caps}sg`, `${plain}D`, `${plain}the`]);
  assert.equal(tree.source, "[DP [N sg] [D the]]", "the alt text has no marks in it");
});

test("move lines are told apart as the macro tells them", () => {
  assert.ok(isMoveLine("move t -> wh"));
  assert.ok(isMoveLine("MOVE\tt -> wh"));
  assert.ok(!isMoveLine("mover t -> wh"));
  assert.ok(!isMoveLine("[S [NP move]]"));
});
