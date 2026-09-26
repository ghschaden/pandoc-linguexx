// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * The OnlyOffice plugin's pure half: what the editor reported about a
 * selection, turned into a *job* -- the example as plain data that
 * commands.js builds with the builder API inside the editor.
 *
 * Everything decidable without the editor is decided here, where Node
 * tests it: the lines and their formats, the parse, the plan, which cell
 * spans what (core/table.js, the same rows the Word layer serializes), the
 * widths in twips, and the styles.  commands.js is then only calls.
 *
 * The styles come from word/styles.js's STYLES_FRAGMENT -- the OOXML the
 * converter injects into a .docx -- read and restated as builder
 * properties, so a document edited in OnlyOffice and one converted or
 * edited in Word answer to the same styles from one source.
 */

import { LAYOUT, NAMES } from "../core/constants.js";
import { advancesFor } from "../core/measure.js";
import { parseLines, strip, tagIndex, tagRun } from "../core/parse.js";
import { planTable, prepareSelection, toExample } from "../core/plan.js";
import { tableRows } from "../core/table.js";
import { isExampleTable, readTable } from "../core/untypeset.js";
import { freshBookmark } from "../word/numbering.js";
import { dxa } from "../word/ooxml.js";
import { STYLES_FRAGMENT } from "../word/styles.js";
import { child, findAll, parse } from "../word/xml.js";

const TWIPS_PER_CM = 566.93;

/**
 * The styles an example uses, as builder properties.  Lengths stay in the
 * fragment's twips; line is 240ths for "auto" and twips for "exact", as
 * both OOXML and ApiParaPr.SetSpacingLine read it.
 */
export function stylesJob(fragment = STYLES_FRAGMENT) {
  const root = parse(`<w:styles>${fragment}</w:styles>`);
  return findAll(root, "w:style").map((s) => {
    const type = s.attrs["w:type"];
    const based = child(s, "w:basedOn");
    const ppr = child(s, "w:pPr");
    const rpr = child(s, "w:rPr");
    const para = {};
    if (ppr) {
      const sp = child(ppr, "w:spacing");
      if (sp) {
        if (sp.attrs["w:before"] !== undefined) para.before = Number(sp.attrs["w:before"]);
        if (sp.attrs["w:after"] !== undefined) para.after = Number(sp.attrs["w:after"]);
        if (sp.attrs["w:line"] !== undefined) {
          para.line = Number(sp.attrs["w:line"]);
          para.lineRule = sp.attrs["w:lineRule"] || "auto";
        }
      }
      const ind = child(ppr, "w:ind");
      if (ind && ind.attrs["w:firstLine"] !== undefined) para.firstLine = Number(ind.attrs["w:firstLine"]);
      const jc = child(ppr, "w:jc");
      // OOXML's logical "start"/"end" are the builder's left/right here:
      // the examples are set left-to-right.
      if (jc) para.jc = { start: "left", end: "right" }[jc.attrs["w:val"]] || jc.attrs["w:val"];
    }
    const run = {};
    if (rpr) {
      const sz = child(rpr, "w:sz");
      if (sz) run.size = Number(sz.attrs["w:val"]);
      if (child(rpr, "w:smallCaps")) run.smallCaps = true;
    }
    return {
      name: s.attrs["w:styleId"], type: type === "character" ? "run" : "paragraph",
      basedOn: based ? based.attrs["w:val"] : "", para, run,
    };
  });
}

/**
 * What commands.readSelection reported, as the core's tagged lines --
 * selection.js's reading, for OnlyOffice's runs.  A "\r" run is a line
 * break; the paragraph is the line.  A format is what a linguist marks
 * within a line (never face or size), as in the Word layer and the macro.
 */
export function linesFromRead(read) {
  const out = { lines: [], formats: [], starts: [], refusal: read.error || "" };
  const keys = new Map();
  const index = (fmt) => {
    const key = JSON.stringify(fmt);
    if (!keys.has(key)) { keys.set(key, out.formats.length); out.formats.push(fmt); }
    return keys.get(key);
  };
  for (const p of read.paragraphs || []) {
    if (p.inTable) {
      out.refusal ||= "The selection is inside a table. Select the typed lines of a new " +
        "example; taking a built example apart is not something this version can do yet.";
    }
    let line = "";
    out.starts.push(out.lines.length);   // where this paragraph's first line lands
    for (const r of p.runs) {
      const fmt = {};
      if (r.style) fmt.rStyle = r.style;
      if (r.bold) fmt.bold = true;
      if (r.italic) fmt.italic = true;
      if (r.underline) fmt.underline = "single";
      if (r.vertAlign === "subscript" || r.vertAlign === "superscript") fmt.vertAlign = r.vertAlign;
      if (r.smallCaps) fmt.smallCaps = true;
      const n = index(fmt);
      const pieces = String(r.text).split(/\r\n|\r|\n/);
      pieces.forEach((piece, i) => {
        if (i > 0) { out.lines.push(line); line = ""; }
        if (piece) line += tagRun(piece, n);
      });
    }
    out.lines.push(line);
  }
  return out;
}

/**
 * *tagged* without a leading "(N)" and the space after it -- a taken-over
 * number's shown text, which the builder API reports as ordinary runs --
 * format marks kept where they are.
 */
export function dropNumber(tagged) {
  const plain = strip(tagged);
  const m = /^\s*\(\s*\d+\s*\)\s*/.exec(plain);
  if (!m) return tagged;
  let drop = m[0].length;
  let out = "";
  for (const c of tagged) {
    if (tagIndex(c) >= 0 || drop === 0) out += c;
    else drop -= 1;
  }
  return out;
}

/** A tagged cell as [{text, fmt}] runs. */
export function runsOf(tagged, formats) {
  const out = [];
  let fmt = -1;
  let text = "";
  for (let i = 0; i < tagged.length; i++) {
    const n = tagIndex(tagged[i]);
    if (n >= 0) {
      if (text) out.push({ text, fmt: formats[fmt] || {} });
      text = "";
      fmt = n;
    } else text += tagged[i];
  }
  if (text) out.push({ text, fmt: formats[fmt] || {} });
  return out;
}

/**
 * The job for one selection: {job, notes} or {refusal}.  *now* seeds the
 * bookmark name (numbering.freshBookmark), so tests can fix it.
 */
export function prepareJob(read, now = Date.now()) {
  const sel = linesFromRead(read);
  if (sel.refusal) return { refusal: sel.refusal };

  // A number the selection leads with is taken over: its bookmark's name is
  // the identity every reference points at (the macro's LxTakeNumber rules).
  const numbers = read.numbers || [];
  let takeOver = null;
  if (numbers.length > 1) {
    return { refusal: "The selection carries two example numbers.\n\nAn example has one. Typeset one example at a time." };
  }
  if (numbers.length === 1) {
    const at = sel.starts[numbers[0].paragraph];
    const before = sel.lines.slice(0, at).map(strip).join("").trim();
    if (before) {
      return { refusal: "An example number appears part-way through the selection.\n\n" +
        "The number an example takes over has to lead it. Start the selection at the number, " +
        "or leave the number out and a new one is made." };
    }
    sel.lines[at] = dropNumber(sel.lines[at]);
    takeOver = numbers[0];
  }
  const parsed = parseLines(sel.lines);
  if (parsed.error) return { refusal: parsed.error };

  const notes = [];
  const width = read.widthTwips ? read.widthTwips / TWIPS_PER_CM : LAYOUT.text_width_cm;
  if (!read.widthTwips) notes.push(`The editor did not say how wide the text block is; laid out for ${width} cm.`);
  // The example is set in the document's face (its styles name none), so
  // it is measured for that face: Aptos from its own metrics, and a face
  // not measured from Times's, with a note saying so.
  const face = read.font || LAYOUT.font_name;
  const size = read.sizeHalfPt ? read.sizeHalfPt / 2 : LAYOUT.font_pt;
  if (!advancesFor(face).known) {
    notes.push(`The columns are estimated from Times New Roman's metrics, and this document's ` +
      `face is ${face}, which has not been measured. Words may wrap in their columns.`);
  }

  const ex = toExample(parsed.items);
  const [layout, anyJudgment] = prepareSelection(ex,
    { ...LAYOUT, text_width_cm: width, font_name: face, font_pt: size }, { formats: sel.formats });
  const { plan, warnings } = planTable(ex, layout, { anyJudgment, formats: sel.formats });
  notes.push(...warnings);

  const t = tableRows(ex, plan);
  const rows = t.rows.map((row) => row.map((c) => ({
    span: c.span,
    widthTwips: dxa(c.widthCm),
    style: c.style,
    content: c.content.kind === "text"
      ? { kind: "text", runs: runsOf(c.content.text, sel.formats) }
      : { kind: c.content.kind },
  })));
  return {
    job: {
      widthTwips: dxa(t.widthCm),
      grid: t.grid.map(dxa),
      rows,
      styles: stylesJob(),
      bookmark: takeOver ? takeOver.bookmark : freshBookmark(read.bookmarks || [], now),
      takeOver: Boolean(takeOver),
      brackets: { left: "(", right: ")" },
    },
    notes,
  };
}

/**
 * What commands.readExampleTable read, as the lines to write back:
 * {back: {pos, number, lines: [[{text, fmt}]]}} or {refusal}.  The reading
 * is core/untypeset.js's, as in Word.
 */
export function untypesetJob(read) {
  if (!read || read.error) return { refusal: (read && read.error) || "The editor returned nothing." };
  const formats = [];
  const keys = new Map();
  const index = (fmt) => {
    const key = JSON.stringify(fmt);
    if (!keys.has(key)) { keys.set(key, formats.length); formats.push(fmt); }
    return keys.get(key);
  };
  const rows = read.rows.map((row) => row.map((c) => {
    let text = "";
    for (const r of c.runs) {
      const fmt = {};
      if (r.style) fmt.rStyle = r.style;
      if (r.bold) fmt.bold = true;
      if (r.italic) fmt.italic = true;
      if (r.underline) fmt.underline = "single";
      if (r.vertAlign === "subscript" || r.vertAlign === "superscript") fmt.vertAlign = r.vertAlign;
      if (r.smallCaps) fmt.smallCaps = true;
      // a line break in a cell is a space, as LxReadText has it
      const t = String(r.text).replace(/\r\n|\r|\n/g, " ");
      if (t) text += tagRun(t, index(fmt));
    }
    return { style: c.style, text };
  }));
  if (!isExampleTable(rows)) {
    return { refusal: "That table is not an example.\n\nAn example is topped and tailed by the " +
      "spacer rows that carry the space around it, and this one is not -- so taking it apart " +
      "would be taking apart a table you built yourself." };
  }
  const examples = rows.filter((row) => row.some((c) => c.style === NAMES.SPACE_ABOVE)).length;
  if (examples > 1) return { refusal: `This table holds ${examples} examples; untypeset them one at a time.` };
  const got = readTable(rows);
  if (got.error) return { refusal: got.error };
  return { back: { pos: read.pos, number: read.number, lines: got.lines.map((l) => runsOf(l, formats)) } };
}
