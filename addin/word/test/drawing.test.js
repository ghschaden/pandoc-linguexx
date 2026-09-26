// SPDX-License-Identifier: GPL-3.0-or-later
//
// A tree as a Word drawing: the markup T2 showed Word on the web takes,
// and the settings it showed a label needs.

import { test } from "node:test";
import assert from "node:assert/strict";

import { TREE_TITLE, drawTree } from "../../core/tree.js";
import { escAttr, treeRun } from "../drawing.js";
import { child, findAll, parse, textOf, wellFormed } from "../xml.js";

const WH = ["[CP [DP,name=wh what] [C' [C did] [TP [DP John] [VP [V see] [DP,name=t __]]]]]", "move t -> wh"];

function drawn(lines, opts = {}) {
  const d = drawTree(lines, { face: "Aptos", pt: 11, ...opts });
  assert.equal(d.error, undefined);
  const xml = treeRun(d.shapes, { id: 7, source: d.source, face: "Aptos", halfPoints: 22, ...opts });
  return { d, xml, doc: parse(`<w:body xmlns:w="w">${xml}</w:body>`) };
}

test("the drawing is well-formed and one inline group", () => {
  const { xml, doc } = drawn(WH);
  assert.ok(wellFormed(`<w:body xmlns:w="w">${xml}</w:body>`));
  assert.equal(findAll(doc, "wp:inline").length, 1);
  assert.equal(findAll(doc, "wp:anchor").length, 0, "inline, never floating");
  assert.equal(findAll(doc, "wpg:wgp").length, 1);
});

test("every piece the core drew is a shape in the group", () => {
  const { d, doc } = drawn(WH);
  const s = d.shapes;
  const want = s.labels.length + s.lines.length + s.roofs.length + s.arrows.length + s.heads.length;
  assert.equal(findAll(doc, "wps:wsp").length, want);
  assert.equal(findAll(doc, "wps:txbx").length, s.labels.length);
  assert.equal(s.arrows.length, 1);
  const ids = findAll(doc, "wps:cNvPr").map((e) => e.attrs.id);
  assert.equal(new Set(ids).size, ids.length, "shape ids are unique");
});

test("a label box never wraps and has no insets, so a short estimate spills", () => {
  // T2: sized for one face and set in a wider one, a wrapping box showed "tre".
  const { doc } = drawn(WH);
  for (const wsp of findAll(doc, "wps:wsp").filter((w) => child(w, "wps:txbx"))) {
    const b = child(wsp, "wps:bodyPr").attrs;
    assert.deepEqual([b.wrap, b.lIns, b.rIns, b.tIns, b.bIns], ["none", "0", "0", "0", "0"]);
  }
});

test("labels are black, in the face and size asked for, centred", () => {
  // T1's first live test: a shape's text took its style's colour, white.
  const { doc } = drawn(WH);
  const labels = findAll(doc, "wps:txbx");
  for (const t of labels) {
    for (const r of findAll(t, "w:r")) {
      const rpr = child(r, "w:rPr");
      assert.equal(child(rpr, "w:color").attrs["w:val"], "000000");
      assert.equal(child(rpr, "w:rFonts").attrs["w:ascii"], "Aptos");
      assert.equal(child(rpr, "w:sz").attrs["w:val"], "22");
    }
    assert.equal(child(child(findAll(t, "w:p")[0], "w:pPr"), "w:jc").attrs["w:val"], "center");
  }
  assert.deepEqual(labels.map(textOf).slice(0, 3), ["CP", "DP", "what"]);
});

test("the alt text is the typed lines, move line included, and says it is a tree", () => {
  const { doc, xml } = drawn(WH);
  // Read off the markup itself: a real XML parser turns a raw newline in an
  // attribute into a space, and this module's small parser does not.
  const raw = /descr="([^"]*)"/.exec(xml)[1];
  assert.ok(!raw.includes("\n") && raw.includes("&#10;"), `the newline is escaped: ${raw}`);
  const pr = findAll(doc, "wp:docPr")[0].attrs;
  assert.equal(pr.descr, WH.join("\n"), "the newline survives the attribute");
  assert.equal(pr.title, TREE_TITLE);
  assert.equal(pr.id, "7");
});

test("a quote in a label does not end the alt text", () => {
  const lines = ['[S [N {say "hi"}]]'];
  const { doc } = drawn(lines);
  assert.equal(findAll(doc, "wp:docPr")[0].attrs.descr, lines[0]);
});

test("two trees in one document share no id", () => {
  // Word wants a drawing's ids unique in the document; the shapes are
  // numbered from the drawing's own id, so two drawings never collide.
  const ids = (id) => {
    const d = drawTree(WH);
    const doc = parse(`<w:body xmlns:w="w">${treeRun(d.shapes, { id, source: d.source })}</w:body>`);
    return [...findAll(doc, "wp:docPr"), ...findAll(doc, "wps:cNvPr")].map((e) => e.attrs.id);
  };
  const [a, b] = [ids(7), ids(8)];
  assert.equal(new Set([...a, ...b]).size, a.length + b.length);
});

test("an attribute escape keeps quotes and newlines", () => {
  const src = 'a "b" <c> & d\nmove x -> y';
  assert.equal(parse(`<e v="${escAttr(src)}"/>`).children[0].attrs.v, src);
});

test("the group's extent is the tree's size, in EMUs", () => {
  const { d, doc } = drawn(WH);
  const ext = findAll(doc, "wp:extent")[0].attrs;
  assert.equal(Number(ext.cx), Math.round(d.shapes.width * 360));
  assert.equal(Number(ext.cy), Math.round(d.shapes.height * 360));
});

test("a small-caps label is measured wider than the same label plain", () => {
  const plain = drawTree(["[N sg]"], { face: "Aptos", pt: 11 });
  const caps = drawTree(["[N sg]"], { face: "Aptos", pt: 11, formats: [{}, { smallCaps: true }] });
  const w = (d) => d.tree.nodes[1].w;
  assert.ok(w(caps) > w(plain), `${w(caps)} should exceed ${w(plain)}`);
});

test("a face nobody measured is said to be estimated", () => {
  assert.equal(drawTree(["[N x]"], { face: "Comic Sans MS" }).known, false);
  assert.equal(drawTree(["[N x]"], { face: "Aptos" }).known, true);
});

test("a paradigm of trees is one table: a letter each, a drawing each, one number", async () => {
  const { parseTreeLines } = await import("../../core/tree.js");
  const { LAYOUT } = await import("../../core/constants.js");
  const { planTable, prepareSelection, toExample } = await import("../../core/plan.js");
  const { exampleTable } = await import("../ooxml.js");
  const lines = ["a. *[S [NP him] [VP [V left]]]", "b. [DP [D a] [NP [N cat]]]", "'a cat'"];
  const ex = toExample(parseTreeLines(lines).items);
  const [layout, anyJudgment] = prepareSelection(ex, LAYOUT);
  const { plan } = planTable(ex, layout, { anyJudgment });
  const widths = [];
  let id = 10;
  const tree = (ls, cellCm) => {
    widths.push(cellCm);
    const d = drawTree(ls);
    return treeRun(d.shapes, { id: ++id, source: d.source });
  };
  const doc = parse(exampleTable(ex, plan, { number: { id: 1, name: "NumEx9", cached: "4" }, tree }));
  assert.equal(findAll(doc, "w:tbl").length, 1);
  assert.equal(findAll(doc, "wpg:wgp").length, 2);
  assert.deepEqual(findAll(doc, "wp:docPr").map((e) => e.attrs.descr), ["*[S [NP him] [VP [V left]]]", "[DP [D a] [NP [N cat]]]"]);
  assert.equal(findAll(doc, "w:instrText").filter((e) => textOf(e).includes("SEQ")).length, 1);
  const cells = findAll(doc, "w:tc").map((tc) => findAll(tc, "w:t").map(textOf).join(""));
  assert.ok(cells.includes("a.") && cells.includes("b.") && cells.includes("*"), cells.join("|"));
  assert.ok(cells.includes("'a cat'"), "the translation keeps its own row");
  assert.ok(widths.every((w) => w > 10), `each tree gets the wide cell: ${widths}`);
});

test("an example typeset as an example draws nothing, whatever its brackets", async () => {
  const { parseLines } = await import("../../core/parse.js");
  const { LAYOUT } = await import("../../core/constants.js");
  const { planTable, prepareSelection, toExample } = await import("../../core/plan.js");
  const { exampleTable } = await import("../ooxml.js");
  const ex = toExample(parseLines(["[TP [DP John] [VP left]]"]).items);
  const [layout, anyJudgment] = prepareSelection(ex, LAYOUT);
  const { plan } = planTable(ex, layout, { anyJudgment });
  const xml = exampleTable(ex, plan, { tree: () => { throw new Error("drew a tree"); } });
  assert.ok(xml.includes("[TP [DP John] [VP left]]"));
});

test("every id stays a signed 32-bit integer, which Word insists on", async () => {
  // Measured in Word on the web: the same tree with shape ids up to
  // 3000001009 was refused ("GeneralException unknown"), and with ids up to
  // 1999999009 went in -- and the pane had drawn ids up to 4e6 * 1000.
  const { MAX_DRAWING_ID } = await import("../drawing.js");
  const d = drawTree(WH);
  const xml = treeRun(d.shapes, { id: MAX_DRAWING_ID - 1, source: d.source });
  const ids = [...xml.matchAll(/ id="(\d+)"/g)].map((m) => Number(m[1]));
  assert.ok(Math.max(...ids) < 2 ** 31, `largest id ${Math.max(...ids)}`);
  assert.throws(() => treeRun(d.shapes, { id: MAX_DRAWING_ID, source: d.source }), RangeError);
  assert.throws(() => treeRun(d.shapes, { id: 0, source: d.source }), RangeError);
});

test("a paradigm of trees untypesets to the lines it was typed as", async () => {
  const { parseTreeLines } = await import("../../core/tree.js");
  const { LAYOUT } = await import("../../core/constants.js");
  const { planTable, prepareSelection, toExample } = await import("../../core/plan.js");
  const { exampleTable, flatPackage } = await import("../ooxml.js");
  const { readExampleTable } = await import("../selection.js");
  const { readTable } = await import("../../core/untypeset.js");
  const lines = ["a. [CP [DP,name=wh what] [C' [C did] [TP [DP you] [VP [V see] [DP,name=t __]]]]]", "move t -> wh",
    'b. *[CP [C that] [TP [DP him] [VP [V {left "early"}]]]]', "'that he left'"];
  const ex = toExample(parseTreeLines(lines).items);
  const [layout, anyJudgment] = prepareSelection(ex, LAYOUT);
  const { plan } = planTable(ex, layout, { anyJudgment });
  let id = 40;
  const tree = (ls) => { const d = drawTree(ls); return treeRun(d.shapes, { id: ++id, source: d.source }); };
  const xml = exampleTable(ex, plan, { number: { id: 1, name: "NumEx3", cached: "1" }, tree });
  const read = readExampleTable(flatPackage(xml, { withStyles: true }));
  assert.equal(read.refusal, "");
  // the labels are text boxes' paragraphs, not the cell's text
  const treeCells = read.rows.flat().filter((c) => c.tree);
  assert.equal(treeCells.length, 2);
  assert.ok(treeCells.every((c) => !c.text.includes("CP")), treeCells.map((c) => c.text).join("|"));
  // compared without format marks: the reader tags every run it reads
  const { strip } = await import("../../core/parse.js");
  assert.deepEqual(readTable(read.rows).lines.map(strip), lines);
});

test("a picture with alt text in an example is not read as a tree", async () => {
  const { readExampleTable } = await import("../selection.js");
  const { flatPackage } = await import("../ooxml.js");
  const d = drawTree(["[N x]"]);
  const run = treeRun(d.shapes, { id: 5, source: "[N x]" }).replace(/title="[^"]*"/, 'title="A photo"');
  const xml = `<w:tbl><w:tr><w:tc><w:p>${run}</w:p></w:tc></w:tr></w:tbl>`;
  assert.equal(readExampleTable(flatPackage(xml)).rows[0][0].tree, undefined);
});
