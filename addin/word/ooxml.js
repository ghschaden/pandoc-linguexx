// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * A plan as OOXML -- src/linguexx2odt/emit_docx.py, ported, and the flat
 * package Office.js `insertOoxml` takes.
 *
 * The same markup the converter writes, not markup like it: the table, its
 * zeroed insets and fixed layout, the spacer rows, the `SEQ` field and its
 * whole-field bookmark, the `REF`.  test/ooxml.test.js holds it to the
 * converter's own output for every fixture, string for string, so an
 * example the add-in inserts and one the converter wrote are the same
 * object and answer to the same styles.
 *
 * What differs is only what the converter cannot know: the bookmark's name
 * and id (unique in somebody else's document, not "NumEx" + index) and the
 * cached number (counted from the document at insertion time, not from
 * the order of a LaTeX file).  Both are parameters.
 */

import { NAMES } from "../core/constants.js";
import { tagIndex } from "../core/parse.js";
import { tableRows } from "../core/table.js";
import { STYLES_FRAGMENT } from "./styles.js";

const W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main";
const PKG_NS = "http://schemas.microsoft.com/office/2006/xmlPackage";
const REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships";
const OFFDOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";

const CELL_PARA = NAMES.CELL_PARA;

/** twentieths of a point per centimetre, which is what OOXML measures in */
export const DXA = 566.93;

/**
 * Python's round() to an integer: halves go to the even neighbour.  The
 * converter writes int(round(cm * DXA)); Math.round sends halves up, which
 * is a different twip for some width sooner or later.
 */
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

export function dxa(cm) {
  return pyRound(cm * DXA);
}

/** inline.esc: what text needs, and no more -- quotes stay as typed. */
export function esc(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/**
 * Run properties for one of the host's formats, in the order CT_RPr
 * requires (rStyle, b, i, smallCaps, u, vertAlign) -- Word refuses a run
 * whose properties are out of schema order, which LibreOffice forgives.
 * A format may be absent: plain text carries no w:rPr at all, as the
 * converter's runs do.
 */
export function rPr(fmt) {
  if (!fmt) return "";
  let out = "";
  if (fmt.rStyle) out += `<w:rStyle w:val="${esc(fmt.rStyle)}"/>`;
  if (fmt.bold) out += "<w:b/>";
  if (fmt.italic) out += "<w:i/>";
  if (fmt.smallCaps && !fmt.rStyle) out += "<w:smallCaps/>";
  if (fmt.underline) out += `<w:u w:val="${esc(fmt.underline)}"/>`;
  if (fmt.vertAlign) out += `<w:vertAlign w:val="${esc(fmt.vertAlign)}"/>`;
  return out ? `<w:rPr>${out}</w:rPr>` : "";
}

/** emit_docx.run: one run of text. */
export function run(text, fmt) {
  return `<w:r>${rPr(fmt)}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;
}

/** A tagged string (see core/parse.js) as runs, each in its own format. */
export function runs(tagged, formats = []) {
  let out = "";
  let fmt = -1;
  let text = "";
  for (let i = 0; i < tagged.length; i++) {
    const n = tagIndex(tagged[i]);
    if (n >= 0) {
      if (text) out += run(text, formats[fmt]);
      text = "";
      fmt = n;
    } else {
      text += tagged[i];
    }
  }
  if (text) out += run(text, formats[fmt]);
  return out;
}

/** emit_docx.field_run: begin, instruction, cached result, end. */
export function fieldRun(instr, cached) {
  return (
    '<w:r><w:fldChar w:fldCharType="begin"/></w:r>' +
    `<w:r><w:instrText xml:space="preserve"> ${instr} </w:instrText></w:r>` +
    '<w:r><w:fldChar w:fldCharType="separate"/></w:r>' +
    run(cached) +
    '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
  );
}

/**
 * emit_docx.sequence_field: the example number, bookmarked round the field
 * alone so that a REF gives back "3" and not the whole line (plan-docx.md
 * fact 3; S7 fact 4 found the same from the other side).
 */
export function sequenceField({ id, name, cached }, seq = NAMES.SEQ_NAME) {
  return (
    `<w:bookmarkStart w:id="${id}" w:name="${esc(name)}"/>` +
    fieldRun(`SEQ ${seq} \\* ARABIC`, cached) +
    `<w:bookmarkEnd w:id="${id}"/>`
  );
}

/** emit_docx.sequence_ref: a reference, cached at what it resolves to. */
export function sequenceRef(name, cached, { left = "(", right = ")", bare = false, letter = "" } = {}) {
  const [l, r] = bare ? ["", ""] : [left, right];
  return (
    (l ? run(l) : "") + fieldRun(`REF ${name} \\h`, cached) +
    (letter ? run(letter) : "") + (r ? run(r) : "")
  );
}

/** emit_docx.cell */
export function cell(widthCm, content, span = 1, style = CELL_PARA) {
  const grid = span > 1 ? `<w:gridSpan w:val="${span}"/>` : "";
  return (
    `<w:tc><w:tcPr><w:tcW w:w="${dxa(widthCm)}" w:type="dxa"/>${grid}</w:tcPr>` +
    `<w:p><w:pPr><w:pStyle w:val="${style}"/></w:pPr>${content}</w:p></w:tc>`
  );
}

/** emit_docx.TABLE_PR: zeroed insets and a fixed layout (facts 8 and 4). */
export const TABLE_PR =
  '<w:tblLayout w:type="fixed"/>' +
  "<w:tblCellMar>" +
  '<w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>' +
  '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/>' +
  "</w:tblCellMar>";

/**
 * One example as a w:tbl -- DocxEmitter._table.  *plan* is core/plan.js's
 * planTable().plan for *ex*; which cell goes where is core/table.js's, and
 * this only writes it down.
 *
 * opts.number: {id, name, cached} for the SEQ field and its bookmark.
 * opts.formats: the host's formats the cells' tag marks stand for.
 * opts.brackets: {left, right} round the number, "(" and ")" by default.
 */
export function exampleTable(ex, plan, opts = {}) {
  const formats = opts.formats || [];
  const left = opts.brackets?.left ?? "(";
  const right = opts.brackets?.right ?? ")";
  const number = () =>
    (left ? run(left) : "") + sequenceField(opts.number || { id: 1, name: "NumEx0", cached: "1" }) +
    (right ? run(right) : "");
  const content = (c) => {
    if (c.kind === "number") return number();
    if (c.kind === "text") return runs(c.text, formats);
    return "";
  };
  const t = tableRows(ex, plan);
  const gridCols = t.grid.map((w) => `<w:gridCol w:w="${dxa(w)}"/>`).join("");
  const rows = t.rows.map((row) =>
    "<w:tr>" + row.map((c) => cell(c.widthCm, content(c.content), c.span, c.style)).join("") + "</w:tr>");
  // The document's indent (core/settings.js), in CT_TblPr's place: after
  // tblW, before the layout.  None at all when there is none, which keeps
  // the markup the converter's, string for string.
  const indent = t.indentCm > 0 ? `<w:tblInd w:w="${dxa(t.indentCm)}" w:type="dxa"/>` : "";
  return (
    `<w:tbl><w:tblPr><w:tblW w:w="${dxa(t.widthCm)}" w:type="dxa"/>${indent}${TABLE_PR}</w:tblPr>` +
    `<w:tblGrid>${gridCols}</w:tblGrid>` + rows.join("") + "</w:tbl>"
  );
}

/** The paragraph that follows every inserted example: Word joins adjacent tables (S6 fact 3). */
export const AFTER_EXAMPLE = "<w:p/>";

/**
 * The document defaults a styles part carries: the face and size the
 * document's own text is in.  Without them OOXML's implicit default is
 * Times New Roman, and Word resolved the imported styles against it and
 * wrote "Times New Roman, 12" into LxExampleCell -- examples in Times in an
 * Aptos document (the second live test showed it; the Styles pane said so).
 */
export function docDefaults(face, halfPoints) {
  if (!face) return "";
  const f = esc(face);
  const size = halfPoints ? `<w:sz w:val="${halfPoints}"/><w:szCs w:val="${halfPoints}"/>` : "";
  return "<w:docDefaults><w:rPrDefault><w:rPr>" +
    `<w:rFonts w:ascii="${f}" w:hAnsi="${f}" w:eastAsia="${f}" w:cs="${f}"/>${size}` +
    "</w:rPr></w:rPrDefault></w:docDefaults>";
}

/**
 * A flat OPC package for Body/Range.insertOoxml: *bodyXml* as the document
 * body, and -- when *withStyles* -- the Lx styles as its styles part.
 * *defaults* ({face, halfPoints}) go into a styles part whether or not the
 * Lx styles do: without them the inserted text resolves, inside the
 * package, to OOXML's implicit Times New Roman, and Word keeps that "source
 * formatting" as direct formatting on the text even when the document's
 * own style says otherwise -- which is what the live test after the first
 * fix still showed.
 * Styles travel only when the document lacks one (plan-addins.md,
 * Phase 2): re-sending a styles part the document has was never isolated
 * from the page-state failure of S6 fact 2.
 */
export function flatPackage(bodyXml, { withStyles = false, defaults = null } = {}) {
  const parts = [
    ["/_rels/.rels", "application/vnd.openxmlformats-package.relationships+xml",
      `<Relationships xmlns="${REL_NS}"><Relationship Id="rId1" ` +
      `Type="${OFFDOC}/officeDocument" Target="word/document.xml"/></Relationships>`],
    ["/word/_rels/document.xml.rels", "application/vnd.openxmlformats-package.relationships+xml",
      `<Relationships xmlns="${REL_NS}">` +
      (withStyles || defaults ? `<Relationship Id="rId1" Type="${OFFDOC}/styles" Target="styles.xml"/>` : "") +
      "</Relationships>"],
    ["/word/document.xml",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
      `<w:document xmlns:w="${W_NS}"><w:body>${bodyXml}</w:body></w:document>`],
  ];
  if (withStyles || defaults) {
    parts.push(["/word/styles.xml",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml",
      `<w:styles xmlns:w="${W_NS}">` +
      (defaults ? docDefaults(defaults.face, defaults.halfPoints) : "") +
      `${withStyles ? STYLES_FRAGMENT : ""}</w:styles>`]);
  }
  const inner = parts.map(([name, type, xml]) =>
    `<pkg:part pkg:name="${name}" pkg:contentType="${type}"><pkg:xmlData>${xml}</pkg:xmlData></pkg:part>`)
    .join("");
  return `<?xml version="1.0" standalone="yes"?><pkg:package xmlns:pkg="${PKG_NS}">${inner}</pkg:package>`;
}
