// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * A laid-out tree (core/tree.js) as a Word drawing: one inline group of
 * shapes, as the Writer macro's LxTreeShapes groups them -- a text box per
 * label, a line per branch, a path per roof, arrow and head -- with the
 * bracket notation as its alt text.
 *
 * What T2 measured in Word on the web (plan-addins.md, "Trees -- drawing
 * spikes"): insertOoxml takes a wpg group inline and keeps its alt text;
 * a label box wraps its text by default, and set in a face wider than the
 * one it was sized for it hid the last letter ("tre").  So every label box
 * is set not to wrap and has no insets -- an estimate that is short spills
 * rather than hides -- as the macro's own label shapes are
 * (LxTPlainShape: TextWordWrap False, every distance 0).
 *
 * Coordinates come in 1/100 mm and leave as EMUs, 360 to the unit.
 */

import { TREE, TREE_TITLE } from "../core/tree.js";
import { tagIndex } from "../core/parse.js";
import { esc } from "./ooxml.js";

const NS = {
  mc: "http://schemas.openxmlformats.org/markup-compatibility/2006",
  wp: "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
  a: "http://schemas.openxmlformats.org/drawingml/2006/main",
  wpg: "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
  wps: "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
};
const GROUP_URI = NS.wpg;

/**
 * Text for an attribute value.  ooxml.esc is for element text and leaves
 * quotes as typed; here a quote would end the value, and a newline -- the
 * alt text keeps a tree's move lines on lines of their own -- would be
 * read back as a space (XML normalizes attribute whitespace).
 */
export function escAttr(text) {
  return esc(text).replace(/"/g, "&quot;").replace(/\n/g, "&#10;").replace(/\t/g, "&#9;").replace(/\r/g, "&#13;");
}

/**
 * The largest drawing id treeRun takes.  Its shapes are numbered from
 * id * 1000, and 2e6 * 1000 plus a tree's pieces stays under 2^31 - 1:
 * Word reads these ids as signed 32-bit integers, whatever the schema's
 * unsignedInt says (see plan-addins.md).
 */
export const MAX_DRAWING_ID = 2000000;

/** 1/100 mm -> EMU, whole. */
export const emu = (hmm) => Math.round(hmm * 360);

/**
 * A label run's properties, in CT_RPr's order (rStyle, rFonts, b, i,
 * smallCaps, color, sz, szCs, u, vertAlign): the host's format for the
 * run, and the face and size the tree is set in, which the macro applies
 * to every label afterwards (LxTShapeFont) because they are not part of
 * what a run carries.  Black is said: a shape's text colour comes from its
 * style otherwise, and T1's first live test drew white labels on white.
 */
function labelRPr(fmt, face, halfPoints) {
  const f = fmt || {};
  let out = "";
  if (f.rStyle) out += `<w:rStyle w:val="${escAttr(f.rStyle)}"/>`;
  if (face) {
    const n = escAttr(face);
    out += `<w:rFonts w:ascii="${n}" w:hAnsi="${n}" w:eastAsia="${n}" w:cs="${n}"/>`;
  }
  if (f.bold) out += "<w:b/>";
  if (f.italic) out += "<w:i/>";
  if (f.smallCaps && !f.rStyle) out += "<w:smallCaps/>";
  out += '<w:color w:val="000000"/>';
  if (halfPoints) out += `<w:sz w:val="${halfPoints}"/><w:szCs w:val="${halfPoints}"/>`;
  if (f.underline) out += `<w:u w:val="${esc(f.underline)}"/>`;
  if (f.vertAlign) out += `<w:vertAlign w:val="${esc(f.vertAlign)}"/>`;
  return `<w:rPr>${out}</w:rPr>`;
}

/** A tagged label as runs, each in its own format. */
function labelRuns(tagged, formats, face, halfPoints) {
  let out = "";
  let fmt = -1;
  let text = "";
  const flush = () => {
    if (text) out += `<w:r>${labelRPr(formats[fmt], face, halfPoints)}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;
    text = "";
  };
  for (const c of tagged) {
    const n = tagIndex(c);
    if (n >= 0) {
      flush();
      fmt = n;
    } else text += c;
  }
  flush();
  return out;
}

const xfrm = (x, y, w, h, flipH = false) =>
  `<a:xfrm${flipH ? ' flipH="1"' : ""}><a:off x="${emu(x)}" y="${emu(y)}"/><a:ext cx="${emu(w)}" cy="${emu(h)}"/></a:xfrm>`;

const stroke = `<a:ln w="${emu(TREE.BRANCH_WIDTH)}"><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln>`;
const black = '<a:solidFill><a:srgbClr val="000000"/></a:solidFill>';

/** The shape body every drawn piece shares: no text, no autofit. */
const noText = '<wps:bodyPr rot="0"><a:noAutofit/></wps:bodyPr>';

/**
 * A polygon or polyline through *pts*, as a custom geometry in its own
 * bounding box -- the macro's LxTPolyShape, which also puts the points in
 * the shape's own frame first.  *closed* shuts the path; *fill* fills it.
 */
function pathShape(id, pts, { closed, fill }) {
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x, y] = [Math.min(...xs), Math.min(...ys)];
  const [w, h] = [Math.max(...xs) - x, Math.max(...ys) - y];
  const pt = ([px, py]) => `<a:pt x="${emu(px - x)}" y="${emu(py - y)}"/>`;
  const path = `<a:moveTo>${pt(pts[0])}</a:moveTo>` + pts.slice(1).map((p) => `<a:lnTo>${pt(p)}</a:lnTo>`).join("") +
    (closed ? "<a:close/>" : "");
  return `<wps:wsp><wps:cNvPr id="${id}" name="Path ${id}"/><wps:cNvSpPr/><wps:spPr>${xfrm(x, y, w, h)}` +
    '<a:custGeom><a:avLst/><a:gdLst/><a:ahLst/><a:cxnLst/><a:rect l="0" t="0" r="r" b="b"/>' +
    `<a:pathLst><a:path w="${emu(w)}" h="${emu(h)}"${fill ? "" : ' fill="none"'}>${path}</a:path></a:pathLst></a:custGeom>` +
    `${fill ? black : "<a:noFill/>"}${stroke}</wps:spPr>${noText}</wps:wsp>`;
}

/** A branch: a straight line, flipped when it runs down to the left. */
function lineShape(id, [x0, y0, x1, y1]) {
  return `<wps:wsp><wps:cNvPr id="${id}" name="Line ${id}"/><wps:cNvSpPr/><wps:spPr>` +
    xfrm(Math.min(x0, x1), y0, Math.abs(x1 - x0), y1 - y0, x1 < x0) +
    `<a:prstGeom prst="line"><a:avLst/></a:prstGeom><a:noFill/>${stroke}</wps:spPr>${noText}</wps:wsp>`;
}

/** A label: a borderless, unfilled text box, the text centred, never wrapped. */
function labelShape(id, l, formats, face, halfPoints) {
  const para = '<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="240" w:lineRule="auto"/>' +
    '<w:ind w:left="0" w:right="0" w:firstLine="0"/><w:jc w:val="center"/></w:pPr>' +
    `${labelRuns(l.text, formats, face, halfPoints)}</w:p>`;
  return `<wps:wsp><wps:cNvPr id="${id}" name="Label ${id}"/><wps:cNvSpPr txBox="1"/><wps:spPr>` +
    `${xfrm(l.x, l.y, l.w, l.h)}<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln>` +
    `</wps:spPr><wps:txbx><w:txbxContent>${para}</w:txbxContent></wps:txbx>` +
    '<wps:bodyPr rot="0" vert="horz" wrap="none" lIns="0" tIns="0" rIns="0" bIns="0" anchor="ctr" anchorCtr="0">' +
    "<a:noAutofit/></wps:bodyPr></wps:wsp>";
}

/**
 * The run holding the drawing of *shapes* (core/tree.treeShapes), inline.
 * *id* is the drawing's document-wide id (wp:docPr), which Word wants
 * unique; the shapes inside are numbered from it.  *source* is the alt
 * text -- the lines the tree was typed as -- and TREE_TITLE its title,
 * which is what tells a tree of ours from a picture (LxShapeSource).
 */
export function treeRun(shapes, { id, source, formats = [], face = "", halfPoints = 0 }) {
  if (!(id >= 1 && id < MAX_DRAWING_ID)) throw new RangeError(`drawing id ${id} is out of range`);
  let n = id * 1000;
  const pieces = [
    ...shapes.lines.map((l) => lineShape(++n, l)),
    ...shapes.roofs.map((p) => pathShape(++n, p, { closed: true, fill: false })),
    ...shapes.arrows.map((p) => pathShape(++n, p, { closed: false, fill: false })),
    ...shapes.heads.map((p) => pathShape(++n, p, { closed: true, fill: true })),
    ...shapes.labels.map((l) => labelShape(++n, l, formats, face, halfPoints)),
  ].join("");
  const [cx, cy] = [emu(shapes.width), emu(shapes.height)];
  const group = `<wpg:wgp><wpg:cNvGrpSpPr/><wpg:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/>` +
    `<a:chOff x="0" y="0"/><a:chExt cx="${cx}" cy="${cy}"/></a:xfrm></wpg:grpSpPr>${pieces}</wpg:wgp>`;
  const title = escAttr(TREE_TITLE);
  const inline = `<wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="${cx}" cy="${cy}"/>` +
    '<wp:effectExtent l="0" t="0" r="0" b="0"/>' +
    `<wp:docPr id="${id}" name="${title} ${id}" title="${title}" descr="${escAttr(source)}"/><wp:cNvGraphicFramePr/>` +
    `<a:graphic><a:graphicData uri="${GROUP_URI}">${group}</a:graphicData></a:graphic></wp:inline>`;
  const decl = Object.entries(NS).map(([p, u]) => `xmlns:${p}="${u}"`).join(" ");
  return `<w:r><mc:AlternateContent ${decl}><mc:Choice Requires="wpg"><w:drawing>${inline}</w:drawing>` +
    "</mc:Choice></mc:AlternateContent></w:r>";
}
