#!/usr/bin/env node
// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * The OnlyOffice plugin's editor half, run headless in Document Builder.
 *
 *     node tools/run_onlyoffice_test.mjs [OUTDIR]     (or: make onlyoffice-test)
 *
 * Document Builder runs the builder API a plugin's callCommand runs in the
 * editor (plan-addins.md, S9).  So this builds one document the way a user
 * would: for every typed-line fixture, it types the lines as paragraphs,
 * selects them, and runs the plugin's own commands on them --
 * readSelection, prepareJob, insertExample -- from the very linguexx.js the
 * plugin ships (tools/build_onlyoffice.py).  Then it reads the .docx back
 * and holds each table to the Word layer's markup for the same selection,
 * which test/ooxml.test.js holds to the converter: the same grid, the same
 * spans, the same widths to a twip (S8 fact 3's JSON rounding), the same
 * styles by name, the same text, a SEQ field with a bookmark round the
 * whole of it, and numbers 1..N once UpdateAllFields has run.
 *
 * A scenario follows: an example inserted ahead of the others, and a
 * reference completed from a placeholder, must renumber together.
 *
 * Needs Document Builder: $DOCBUILDER, or the archive unpacked under
 * ~/.local/opt/documentbuilder (see plan-addins.md).  The free build
 * watermarks the page header, which nothing here reads.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { LAYOUT } from "../addin/core/constants.js";
import { parseLines } from "../addin/core/parse.js";
import { planTable, prepareSelection, toExample } from "../addin/core/plan.js";
import { linesFromRead } from "../addin/onlyoffice/job.js";
import { exampleTable } from "../addin/word/ooxml.js";
import { child, findAll, parse, textOf } from "../addin/word/xml.js";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const GUID = "{D71895BD-806D-4964-ACA4-0A531FE92454}";
const BUNDLE = join(ROOT, "dist", "onlyoffice", GUID, "linguexx.js");
const OUT = resolve(process.argv[2] || "/tmp/lx-onlyoffice-test");
const TWIPS_PER_CM = 566.93;

function docbuilder() {
  const candidates = [process.env.DOCBUILDER,
    join(homedir(), ".local/opt/documentbuilder/opt/onlyoffice/documentbuilder/docbuilder"),
    "/opt/onlyoffice/documentbuilder/docbuilder"].filter(Boolean);
  const found = candidates.find((p) => existsSync(p));
  if (!found) {
    console.error("Document Builder not found; set DOCBUILDER=/path/to/docbuilder");
    process.exit(2);
  }
  return found;
}

function run(script, name) {
  const path = join(OUT, `${name}.docbuilder`);
  writeFileSync(path, script);
  const bin = docbuilder();
  execFileSync(bin, [path], {
    cwd: OUT, env: { ...process.env, LD_LIBRARY_PATH: dirname(bin) }, stdio: ["ignore", "ignore", "pipe"],
    timeout: 300000,
  });
}

function unzip(docx, part) {
  return execFileSync("unzip", ["-p", docx, part], { maxBuffer: 1 << 26 }).toString("utf-8");
}

// -- the document -----------------------------------------------------------

const FIXTURES = JSON.parse(readFileSync(join(ROOT, "tests/fixtures/typed-examples.json"), "utf-8"));
const cases = Object.entries(FIXTURES)
  .filter(([g]) => !g.startsWith("_") && g !== "parsed")
  .flatMap(([g, cs]) => Object.entries(cs).map(([n, c]) => ({ key: `${g}/${n}`, lines: c.lines })));

/** The script: the bundle, then one insertion per fixture, then the results. */
function script(docx) {
  const bundle = readFileSync(BUNDLE, "utf-8");
  if (/^\s*builder\./m.test(bundle)) throw new Error("a line of the bundle starts with builder.");
  return `builder.CreateFile("docx");
${bundle}
if (typeof Asc.scope !== "object" || !Asc.scope) Asc.scope = {};
var doc = Api.GetDocument();
var results = [];
try {
  doc.GetFinalSection().SetPageSize(11906, 16838);
  doc.GetFinalSection().SetPageMargins(1134, 1134, 1134, 1134);
  doc.GetElement(0).AddText("A document with every fixture in it.");
  var CASES = ${JSON.stringify(cases)};
  for (var c = 0; c < CASES.length; c++) {
    var start = doc.GetElementsCount();
    for (var l = 0; l < CASES[c].lines.length; l++) {
      var p = Api.CreateParagraph(); p.AddText(CASES[c].lines[l]); doc.Push(p);
    }
    var tail = Api.CreateParagraph(); tail.AddText("Prose after " + CASES[c].key + "."); doc.Push(tail);
    doc.GetElement(start).GetRange().ExpandTo(doc.GetElement(start + CASES[c].lines.length - 1).GetRange()).Select();
    var read = LinguExx.readSelection();
    var prep = LinguExx.prepareJob(read, 1e12 + c);
    var entry = { key: CASES[c].key, read: read };
    if (prep.refusal) entry.refusal = prep.refusal;
    else { Asc.scope.job = prep.job; entry.res = LinguExx.insertExample(); entry.bookmark = prep.job.bookmark; }
    results.push(entry);
  }
} catch (e) { results.push({ error: String(e && e.stack || e) }); }
var out = Api.CreateParagraph(); out.AddText("LXRESULT" + JSON.stringify(results)); doc.Push(out);
builder.SaveFile("docx", ${JSON.stringify(docx)});
builder.CloseFile();
`;
}

// -- reading it back ----------------------------------------------------------

function styleNames(stylesXml) {
  const names = {};
  for (const s of findAll(parse(stylesXml), "w:style")) {
    const n = child(s, "w:name");
    names[s.attrs["w:styleId"]] = n ? n.attrs["w:val"] : s.attrs["w:styleId"];
  }
  return names;
}

/** A w:tbl as {grid, rows: [[{span, width, style, text}]]}, styles by NAME. */
function describe(tbl, names) {
  const grid = findAll(child(tbl, "w:tblGrid"), "w:gridCol").map((g) => Number(g.attrs["w:w"]));
  const rows = findAll(tbl, "w:tr").map((tr) => tr.children
    .filter((c) => typeof c !== "string" && c.name === "w:tc")
    .map((tc) => {
      const pr = child(tc, "w:tcPr");
      const span = pr && child(pr, "w:gridSpan") ? Number(child(pr, "w:gridSpan").attrs["w:val"]) : 1;
      const width = pr && child(pr, "w:tcW") ? Number(child(pr, "w:tcW").attrs["w:w"]) : null;
      const p = child(tc, "w:p");
      const ps = p && child(p, "w:pPr") && child(child(p, "w:pPr"), "w:pStyle");
      const text = findAll(tc, "w:t").map(textOf).join("");
      return { span, width, style: ps ? (names[ps.attrs["w:val"]] || ps.attrs["w:val"]) : "", text };
    }));
  return { grid, rows };
}

function compare(key, got, want, problems) {
  const say = (m) => problems.push(`${key}: ${m}`);
  if (got.grid.length !== want.grid.length || got.grid.some((w, i) => Math.abs(w - want.grid[i]) > 1)) {
    say(`grid ${got.grid} against ${want.grid}`);
  }
  if (got.rows.length !== want.rows.length) return say(`${got.rows.length} rows against ${want.rows.length}`);
  got.rows.forEach((row, r) => {
    if (row.length !== want.rows[r].length) return say(`row ${r}: ${row.length} cells against ${want.rows[r].length}`);
    row.forEach((c, k) => {
      const w = want.rows[r][k];
      if (c.span !== w.span) say(`row ${r} cell ${k}: span ${c.span} against ${w.span}`);
      if (Math.abs(c.width - w.width) > c.span) say(`row ${r} cell ${k}: width ${c.width} against ${w.width}`);
      if (c.style !== w.style) say(`row ${r} cell ${k}: style ${c.style} against ${w.style}`);
      // the number cell's text is the counted number here, the Word
      // markup's placeholder there; compared on its own below
      if (!/^\(\d+\)$/.test(w.text) && c.text !== w.text) say(`row ${r} cell ${k}: text ${JSON.stringify(c.text)} against ${JSON.stringify(w.text)}`);
    });
  });
}

/** What the Word layer writes for the selection the editor reported. */
function expected(read) {
  const sel = linesFromRead(read);
  const ex = toExample(parseLines(sel.lines).items);
  const width = read.widthTwips / TWIPS_PER_CM;
  const [layout, anyJudgment] = prepareSelection(ex, { ...LAYOUT, text_width_cm: width }, { formats: sel.formats });
  const { plan } = planTable(ex, layout, { anyJudgment, formats: sel.formats });
  return exampleTable(ex, plan, { number: { id: 1, name: "x", cached: "1" }, formats: sel.formats });
}

// -- main -------------------------------------------------------------------------

mkdirSync(OUT, { recursive: true });
if (!existsSync(BUNDLE)) {
  console.error(`${BUNDLE} is missing: run python3 tools/build_onlyoffice.py first`);
  process.exit(1);
}
const docx = join(OUT, "fixtures.docx");
console.log(`--- building ${cases.length} fixtures in Document Builder (about 20 s)`);
run(script(docx), "fixtures");

const documentXml = unzip(docx, "word/document.xml");
const names = styleNames(unzip(docx, "word/styles.xml"));
const body = findAll(parse(documentXml), "w:body")[0];
const resultText = findAll(body, "w:t").map(textOf).join("");
const results = JSON.parse(resultText.slice(resultText.indexOf("LXRESULT") + 8));
const problems = [];
if (results.some((r) => r.error)) problems.push(`the script failed: ${results.find((r) => r.error).error}`);

const tables = body.children.filter((c) => typeof c !== "string" && c.name === "w:tbl");
const inserted = results.filter((r) => r.res && !r.res.error);
const refused = results.filter((r) => r.refusal);
console.log(`--- ${inserted.length} inserted, ${refused.length} refused, ${tables.length} tables in the document`);
if (tables.length !== inserted.length) problems.push(`${tables.length} tables for ${inserted.length} insertions`);
for (const r of results) if (r.res && r.res.error) problems.push(`${r.key}: ${r.res.error}`);
for (const r of refused) if (!r.key.startsWith("REFUSE/")) problems.push(`${r.key}: refused: ${r.refusal}`);
if (!refused.some((r) => r.key.startsWith("REFUSE/"))) problems.push("the REFUSE fixture was not refused");

// Every table against the Word markup for its own selection.
inserted.forEach((r, i) => {
  if (!tables[i]) return;
  const want = describe(parse(expected(r.read)).children[0], names);
  compare(r.key, describe(tables[i], names), want, problems);
});

// Numbers: UpdateAllFields ran after every insertion, so the caches count 1..N.
const numbers = [];
for (const tbl of tables) {
  const texts = [];
  let inResult = false;
  let code = "";
  (function walk(node) {
    for (const c of node.children) {
      if (typeof c === "string") continue;
      if (c.name === "w:fldChar") {
        const t = c.attrs["w:fldCharType"];
        if (t === "begin") { code = ""; inResult = false; }
        if (t === "separate") inResult = /SEQ\s+NumEx/.test(code);
        if (t === "end") inResult = false;
      } else if (c.name === "w:instrText") code += textOf(c);
      else if (c.name === "w:t" && inResult) texts.push(textOf(c));
      walk(c);
    }
  })(tbl);
  numbers.push(texts.join(""));
}
const want = numbers.map((_, i) => String(i + 1));
if (JSON.stringify(numbers) !== JSON.stringify(want)) problems.push(`numbers read ${numbers.join(",")}`);

// Every table: fixed layout, no insets, no borders -- what S8 had to fight
// for (the rebuild through JSON adds Table Grid's borders, fact 4).
tables.forEach((tbl, i) => {
  const pr = child(tbl, "w:tblPr");
  const key = inserted[i] ? inserted[i].key : `table ${i}`;
  const layout = child(pr, "w:tblLayout");
  if (!layout || layout.attrs["w:type"] !== "fixed") problems.push(`${key}: layout is not fixed`);
  const mar = child(pr, "w:tblCellMar");
  for (const side of ["w:top", "w:left", "w:bottom", "w:right"]) {
    const m = mar && child(mar, side);
    if (!m || Number(m.attrs["w:w"]) !== 0) problems.push(`${key}: cell margin ${side} is not 0`);
  }
  const borders = child(pr, "w:tblBorders");
  for (const side of ["w:top", "w:left", "w:bottom", "w:right", "w:insideH", "w:insideV"]) {
    const bd = borders && child(borders, side);
    if (!bd || bd.attrs["w:val"] !== "none") problems.push(`${key}: border ${side} is not none`);
  }
});

// Every Lx style as the converter defines it -- not only present by name.
// The properties STYLES_FRAGMENT sets, looked up in what OnlyOffice saved.
{
  const saved = {};
  for (const st of findAll(parse(unzip(docx, "word/styles.xml")), "w:style")) {
    const n = child(st, "w:name");
    if (n) saved[n.attrs["w:val"]] = st;
  }
  const facts = (st, byName) => {
    const out = {};
    const based = child(st, "w:basedOn");
    if (based) out.basedOn = byName(based.attrs["w:val"]);
    const ppr = child(st, "w:pPr");
    const sp = ppr && child(ppr, "w:spacing");
    if (sp) for (const k of ["w:before", "w:after", "w:line", "w:lineRule"]) if (sp.attrs[k] !== undefined) out[k] = sp.attrs[k];
    const ind = ppr && child(ppr, "w:ind");
    if (ind && ind.attrs["w:firstLine"] !== undefined) out.firstLine = ind.attrs["w:firstLine"];
    const jc = ppr && child(ppr, "w:jc");
    if (jc) out.jc = { start: "left", end: "right" }[jc.attrs["w:val"]] || jc.attrs["w:val"];
    const rpr = child(st, "w:rPr");
    const sz = rpr && child(rpr, "w:sz");
    if (sz) out.sz = sz.attrs["w:val"];
    if (rpr && child(rpr, "w:smallCaps")) out.smallCaps = true;
    return out;
  };
  const idToName = {};
  for (const [name, st] of Object.entries(saved)) idToName[st.attrs["w:styleId"]] = name;
  const { STYLES_FRAGMENT } = await import("../addin/word/styles.js");
  for (const def of findAll(parse(`<w:styles>${STYLES_FRAGMENT}</w:styles>`), "w:style")) {
    const name = def.attrs["w:styleId"];
    if (!saved[name]) { problems.push(`style ${name} is not in the document`); continue; }
    const want = facts(def, (v) => v);
    const got = facts(saved[name], (v) => idToName[v] || v);
    for (const [k, v] of Object.entries(want)) {
      // OnlyOffice may state a default the fragment leaves implicit; what the
      // fragment states must be there, as stated
      if (String(got[k]) !== String(v)) problems.push(`style ${name}: ${k} is ${got[k]}, the converter says ${v}`);
    }
  }
}

// Every bookmark wraps its whole field: its start is before the "begin".
for (const r of inserted) {
  const at = documentXml.indexOf(`w:name="${r.bookmark}"`);
  const next = documentXml.indexOf("w:fldChar", at);
  const begin = documentXml.slice(next, next + 40);
  if (at < 0 || !begin.includes('"begin"')) problems.push(`${r.key}: bookmark ${r.bookmark} does not open on the field`);
}

// No two example tables touch (S6 fact 3, S7 fact 8).
body.children.filter((c) => typeof c !== "string").forEach((el, i, all) => {
  if (el.name === "w:tbl" && all[i + 1] && all[i + 1].name === "w:tbl") problems.push(`two tables touch at element ${i}`);
});

console.log(`--- compared ${inserted.length} tables with the Word layer's markup; numbers ${numbers.join(" ")}`);

// -- the scenario ---------------------------------------------------------------
//
// In the fixture document every example is appended, with prose after it, so
// two of the plugin's duties cannot fail there: renumbering what an example
// inserted AHEAD of others moves, and keeping two example tables apart.  And
// the fixtures carry no formatting.  Each was shown by a mutation of
// commands.js that the fixture document let through.
//
// Here: A; then B typed DIRECTLY above A's table, nothing between them, and
// typeset -- right after which A must already read 2, before anything else
// can have renumbered it, and the two tables must not touch; then a reference
// to A completed from a placeholder, as the plugin pastes one; then C, typed
// with formatting -- italic, small caps, a Leipzig character style, a bold
// subscript -- which must arrive in its cells.

const scenarioDocx = join(OUT, "scenario.docx");
const bundle = readFileSync(BUNDLE, "utf-8");
run(`builder.CreateFile("docx");
${bundle}
if (typeof Asc.scope !== "object" || !Asc.scope) Asc.scope = {};
var doc = Api.GetDocument();
var log = {};
function typeset(at, lines, now) {
  for (var l = 0; l < lines.length; l++) { var p = Api.CreateParagraph(); p.AddText(lines[l]); doc.AddElement(at + l, p); }
  doc.GetElement(at).GetRange().ExpandTo(doc.GetElement(at + lines.length - 1).GetRange()).Select();
  var prep = LinguExx.prepareJob(LinguExx.readSelection(), now);
  Asc.scope.job = prep.job;
  var res = LinguExx.insertExample();
  return prep.job.bookmark;
}
try {
  doc.GetFinalSection().SetPageSize(11906, 16838);
  doc.GetFinalSection().SetPageMargins(1134, 1134, 1134, 1134);
  doc.GetElement(0).AddText("Before everything.");
  var tail = Api.CreateParagraph(); tail.AddText("Between."); doc.Push(tail);
  log.A = typeset(2, ["Ich habe geschlafen", "I have slept"], 1e12);
  var aTable = doc.GetBookmarkRange(log.A).GetParagraph(0).GetParentTable().GetPosInParent();
  log.B = typeset(aTable, ["Du hast geschlafen", "you have slept"], 1e12 + 1);
  log.afterB = { A: doc.GetBookmarkRange(log.A).GetText(), B: doc.GetBookmarkRange(log.B).GetText() };
  var ref = Api.CreateParagraph(); ref.AddText("See (LXREFtest) here."); doc.Push(ref);
  Asc.scope.ref = { placeholder: "LXREFtest", bookmark: log.A };
  log.ref = LinguExx.completeReference();
  var n = doc.GetElementsCount();
  // Typed run by run with fresh runs: AddText would give each new run the
  // previous one's formatting, and the test would type the leak it looks for.
  function typeRun(par, text, format) {
    var r = Api.CreateRun(); r.AddText(text); if (format) format(r); par.AddElement(r); return r;
  }
  var o = Api.CreateParagraph();
  typeRun(o, "der "); typeRun(o, "Hund", function (r) { r.SetItalic(true); }); typeRun(o, " schlief");
  var g = Api.CreateParagraph();
  typeRun(g, "the dog sleep-"); typeRun(g, "pst", function (r) { r.SetSmallCaps(true); });
  typeRun(g, ".3"); typeRun(g, "sg", function (r) { r.SetStyle(doc.GetStyle("LxLeipzig")); });
  typeRun(g, "x", function (r) { r.SetBold(true); r.SetVertAlign("subscript"); });
  doc.AddElement(n, o); doc.AddElement(n + 1, g);
  doc.GetElement(n).GetRange().ExpandTo(doc.GetElement(n + 1).GetRange()).Select();
  var prepC = LinguExx.prepareJob(LinguExx.readSelection(), 1e12 + 2);
  Asc.scope.job = prepC.job;
  LinguExx.insertExample();
  log.C = prepC.job.bookmark;
} catch (e) { log.error = String(e && e.stack || e); }
var out = Api.CreateParagraph(); out.AddText("LXRESULT" + JSON.stringify(log)); doc.AddElement(0, out);
builder.SaveFile("docx", ${JSON.stringify(scenarioDocx)});
builder.CloseFile();
`, "scenario");

const scenarioIds = {};
for (const st of findAll(parse(unzip(scenarioDocx, "word/styles.xml")), "w:style")) {
  const n = child(st, "w:name");
  if (n) scenarioIds[st.attrs["w:styleId"]] = n.attrs["w:val"];
}
const idToNameScenario = (id) => scenarioIds[id] || id;
{
  const xml = unzip(scenarioDocx, "word/document.xml");
  const b = findAll(parse(xml), "w:body")[0];
  // the result is the first paragraph, and all of it
  const first = b.children.find((c) => typeof c !== "string" && c.name === "w:p");
  const log = JSON.parse(findAll(first, "w:t").map(textOf).join("").replace(/^LXRESULT/, ""));
  if (log.error) problems.push(`scenario failed: ${log.error}`);
  // the cached result of the field a bookmark wraps, and of a REF to it
  const shown = (name) => {
    const at = xml.indexOf(`w:name="${name}"`);
    const sep = xml.indexOf('w:fldCharType="separate"', at);
    const m = /<w:t[^>]*>([^<]*)<\/w:t>/.exec(xml.slice(sep));
    return m ? m[1] : "?";
  };
  if (JSON.stringify(log.afterB) !== JSON.stringify({ A: "2", B: "1" })) {
    problems.push(`scenario: right after B went in, A read ${log.afterB.A} and B ${log.afterB.B}, not 2 and 1`);
  }
  const got = { B: shown(log.B), A: shown(log.A), C: shown(log.C) };
  if (JSON.stringify(got) !== JSON.stringify({ B: "1", A: "2", C: "3" })) {
    problems.push(`scenario: numbers B,A,C read ${got.B},${got.A},${got.C}, not 1,2,3`);
  }
  const refAt = xml.indexOf(`REF ${log.A}`);
  const refSep = xml.indexOf('w:fldCharType="separate"', refAt);
  const refShown = (/<w:t[^>]*>([^<]*)<\/w:t>/.exec(xml.slice(refSep)) || [])[1];
  if (refAt < 0) problems.push("scenario: the reference is not a REF field to A");
  else if (refShown !== "2") problems.push(`scenario: the reference to A reads ${refShown}, not 2`);
  const blocks = b.children.filter((c) => typeof c !== "string" && c.name !== "w:sectPr");
  if (blocks[blocks.length - 1].name !== "w:p") problems.push("scenario: the document ends in a table");
  blocks.forEach((el, i) => {
    if (el.name === "w:tbl" && blocks[i + 1] && blocks[i + 1].name === "w:tbl") problems.push("scenario: two tables touch");
  });
  // C's formatting, in C's cells: the run each word landed in
  const cTable = blocks.filter((el) => el.name === "w:tbl").pop();
  const runFmt = {};
  for (const r of findAll(cTable, "w:r")) {
    const t = findAll(r, "w:t").map(textOf).join("");
    const pr = child(r, "w:rPr");
    if (!t) continue;
    if (!pr) { runFmt[t] = ""; continue; }
    runFmt[t] = pr.children.filter((c) => typeof c !== "string").map((c) =>
      c.name === "w:rStyle" ? `style:${idToNameScenario(c.attrs["w:val"])}` :
      c.name === "w:vertAlign" ? `vertAlign:${c.attrs["w:val"]}` : c.name).sort().join(" ");
  }
  // Exactly: a format a word should not have is the leak this is for.
  // Only what a linguist marks is compared (OnlyOffice may add w:lang etc.).
  const MARKS = /^(w:i|w:b|w:smallCaps|w:u|style:.*|vertAlign:.*)$/;
  const wantFmt = { der: "", Hund: "w:i", schlief: "", the: "", dog: "", "sleep-": "",
                    pst: "w:smallCaps", ".3": "", sg: "style:LxLeipzig", x: "vertAlign:subscript w:b" };
  for (const [word, fmt] of Object.entries(wantFmt)) {
    const have = (runFmt[word] ?? "?").split(" ").filter((f) => MARKS.test(f)).sort().join(" ");
    if (runFmt[word] === undefined) problems.push(`scenario: "${word}" is not a run of C`);
    else if (have !== fmt.split(" ").sort().join(" ")) problems.push(`scenario: "${word}" has ${have || "no format"}, not ${fmt || "no format"}`);
  }
  console.log(`--- scenario: right after B, A read ${log.afterB.A}; B, A, C read ${got.B}, ${got.A}, ${got.C}; ` +
    `the reference to A reads ${refShown}; C's formats ${JSON.stringify(runFmt)}`);
}
if (problems.length) {
  console.log(problems.slice(0, 40).map((p) => `    FAIL: ${p}`).join("\n"));
  if (problems.length > 40) console.log(`    ... and ${problems.length - 40} more`);
  console.log(`\n${problems.length} FAILURE(S)`);
  process.exit(1);
}
console.log("\nOK");
