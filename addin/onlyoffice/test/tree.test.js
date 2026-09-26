// SPDX-License-Identifier: GPL-3.0-or-later
//
// Trees in OnlyOffice, the pure half: the core's shapes as the pieces the
// builder API can make, the jobs for a numbered and an unnumbered tree,
// and a tree read back.  The editor half is tools/run_onlyoffice_test.mjs.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { TREE_TITLE, drawTree } from "../../core/tree.js";
import { prepareBareJob, prepareJob, treePieces, untypesetJob } from "../job.js";

const run = (text) => ({ text, bold: false, italic: false, smallCaps: false, underline: false, vertAlign: "", style: "" });
const para = (text) => ({ inTable: false, runs: [run(text)] });
const read = (lines, extra = {}) => ({
  paragraphs: lines.map(para), bookmarks: [], widthTwips: 9638, font: "Aptos", sizeHalfPt: 22, error: "", ...extra,
});
const WH = ["[CP [DP,name=wh what] [C' [C did] [TP [DP you] [VP [V see] [DP,name=t __]]]]]", "move t -> wh"];

test("a tree's pieces: a line per branch, three per roof and per arrow, a head, a box per label", () => {
  const d = drawTree(["[S [NP {the big tree, roof}] [VP,name=v [V left] [DP,name=t __]]]", "move t -> v"]);
  const s = d.shapes;
  const { pieces } = treePieces(s);
  const count = (k) => pieces.filter((p) => p.kind === k).length;
  assert.equal(count("line"), s.lines.length + 3 * s.roofs.length + 3 * s.arrows.length);
  assert.equal(count("head"), 1);
  assert.equal(count("label"), s.labels.length);
  assert.deepEqual(pieces.slice(-s.labels.length).map((p) => p.kind), s.labels.map(() => "label"), "labels last, on top");
});

test("a line runs the way its branch does: flipped when it goes down to the left", () => {
  const { pieces } = treePieces(drawTree(["[DP [D the] [N tree]]"]).shapes);
  const [left, right] = pieces.filter((p) => p.kind === "line");
  assert.equal(left.flipH, true);
  assert.equal(right.flipH, false);
  // an arrow's vertical and horizontal runs are never flipped
  const arrow = treePieces(drawTree(WH).shapes).pieces.filter((p) => p.kind === "line").slice(-3);
  assert.ok(arrow.every((p) => !p.flipH) && arrow[1].h === 0 && arrow[0].w === 0, JSON.stringify(arrow));
});

test("pieces are in EMUs, inside the drawing's extent", () => {
  const d = drawTree(WH);
  const { pieces, width, height } = treePieces(d.shapes);
  assert.equal(width, Math.round(d.shapes.width * 360));
  for (const p of pieces) {
    assert.ok(p.x >= 0 && p.y >= 0 && p.x + p.w <= width + 1 && p.y + p.h <= height + 1, JSON.stringify(p));
  }
});

test("a paradigm of trees is one job: a drawing per item, labelled as ours", () => {
  const prep = prepareJob(read(["a. " + WH[0], WH[1], "b. *[S [NP him] [VP left]]", "'him left'"]), 1e12, { trees: true });
  assert.equal(prep.refusal, undefined);
  const cells = prep.job.rows.flat();
  const trees = cells.filter((c) => c.content.kind === "tree");
  assert.equal(trees.length, 2);
  assert.deepEqual(trees.map((c) => c.content.drawing.source), [WH.join("\n"), "*[S [NP him] [VP left]]"]);
  assert.ok(trees.every((c) => c.content.drawing.title === TREE_TITLE && c.content.drawing.face === "Aptos"));
  assert.equal(cells.filter((c) => c.content.kind === "number").length, 1);
});

test("typed as an example, the same brackets draw nothing", () => {
  const prep = prepareJob(read(["[TP [DP John] [VP left]]"]), 1e12);
  assert.equal(prep.job.rows.flat().filter((c) => c.content.kind === "tree").length, 0);
});

test("a tree with no number: the mark as text, the drawing, and no table", () => {
  const prep = prepareBareJob(read(["*[DP [D the] [N tree]]"]));
  assert.equal(prep.job.bare, true);
  assert.equal(prep.job.judgment, "*");
  assert.equal(prep.job.drawing.source, "*[DP [D the] [N tree]]");
  assert.equal(prep.job.rows, undefined);
});

test("a tree with no number refuses a paradigm and a number, in the macro's words", () => {
  assert.match(prepareBareJob(read(["a. [DP [D the] [N tree]]", "b. [DP [D a] [N cat]]"])).refusal, /looks like a paradigm/);
  assert.match(prepareBareJob(read(["[DP [D the] [N tree]]"], { numbers: [{ bookmark: "NumEx1", shown: "1", paragraph: 0 }] })).refusal,
    /carries an example number/);
});

test("a tree cell reads back as the lines it was drawn from, the letter in front", () => {
  const cell = (style, text, tree) => ({ style, runs: text ? [run(text)] : [], ...(tree ? { tree } : {}) });
  const rows = [
    [cell("LxExampleSpaceAbove", "")],
    [cell("LxExampleCell", "1"), cell("LxExampleCell", "a."), cell("LxJudgmentCell", ""), cell("LxExampleCell", "", WH.join("\n"))],
    [cell("LxExampleCell", ""), cell("LxExampleCell", "b."), cell("LxJudgmentCell", "*"), cell("LxExampleCell", "", "*[S [NP him] [VP left]]")],
    [cell("LxExampleCell", ""), cell("LxExampleCell", ""), cell("LxJudgmentCell", ""), cell("LxTranslation", "'him left'")],
    [cell("LxExampleSpaceBelow", "")],
  ];
  const u = untypesetJob({ rows, pos: 3, number: { bookmark: "NumEx1", shown: "1" } });
  assert.equal(u.refusal, undefined);
  assert.deepEqual(u.back.lines.map((l) => l.map((r) => r.text).join("")),
    ["a. " + WH[0], WH[1], "b. *[S [NP him] [VP left]]", "'him left'"]);
});

test("the editor half knows our drawings by the core's title", () => {
  // commands.js runs inside the editor and can import nothing, so the
  // title is written there as a literal: held to the core's here.
  const src = readFileSync(fileURLToPath(new URL("../commands.js", import.meta.url)), "utf-8");
  assert.ok(src.includes(`pr.title === "${TREE_TITLE}"`));
});
