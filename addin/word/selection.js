// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * What Word hands an add-in for a selection -- the flat package
 * Range.getOoxml() returns -- as the tagged lines the core parses.
 *
 * The Writer macro's LxSelectedLines, for Word: a paragraph or a line break
 * ends a line, and every run is marked with its format (core/parse.js,
 * tagRun) so the format rides along through splitting and banding.  As in
 * the macro, a format is what a linguist marks *within* a line -- bold,
 * italic, small caps, underline, raised or lowered, a character style --
 * and never the face or the size: carried as direct formatting those would
 * freeze every cell, and restyling LxExampleCell would stop changing the
 * example.  Text is read as the reader sees it: a field contributes its
 * shown result and not its code, deleted revisions nothing.
 *
 * It also reads, from the same package, what the layout needs and the
 * document will not otherwise say: the text block's width (the section's
 * page size less its margins) and the document's default face, so the
 * add-in can say when that is not one core/constants.js's advances
 * describe.
 */

import { tagRun } from "../core/parse.js";
import { child, findAll, parse } from "./xml.js";
import { LEIPZIG_CHAR } from "./styles.js";

/** twips per centimetre */
const TWIPS_PER_CM = 566.93;

function on(el) {
  // <w:b/> and <w:b w:val="1"/> are on; w:val="0"/"false"/"off" is off.
  if (!el) return false;
  const v = el.attrs["w:val"];
  return v === undefined || !["0", "false", "off"].includes(v);
}

/** The document part of a flat package (or the XML itself, if it is one). */
function partRoot(root, name) {
  for (const part of findAll(root, "pkg:part")) {
    if (part.attrs["pkg:name"] === name) {
      const data = child(part, "pkg:xmlData");
      return data ? data.children.find((c) => typeof c !== "string") : undefined;
    }
  }
  return undefined;
}

/**
 * Character styles' own small caps, following w:basedOn -- so that a word
 * in some user style that sets small caps is measured as drawn.
 */
function charStyleSmallCaps(styles) {
  const byId = new Map();
  if (styles) {
    for (const s of findAll(styles, "w:style")) byId.set(s.attrs["w:styleId"], s);
  }
  const memo = new Map();
  const sc = (id, depth = 0) => {
    if (!id || depth > 20) return false;
    if (memo.has(id)) return memo.get(id);
    const s = byId.get(id);
    let value = id === LEIPZIG_CHAR;
    if (s) {
      const rpr = child(s, "w:rPr");
      const own = rpr && child(rpr, "w:smallCaps");
      if (own) value = on(own);
      else {
        const base = child(s, "w:basedOn");
        if (base) value = sc(base.attrs["w:val"], depth + 1);
      }
    }
    memo.set(id, value);
    return value;
  };
  return sc;
}

/** A run's format, as the few things carried -- see the module comment. */
function formatOf(rpr, smallCapsOfStyle) {
  if (!rpr) return {};
  const fmt = {};
  const style = child(rpr, "w:rStyle");
  if (style) fmt.rStyle = style.attrs["w:val"];
  if (on(child(rpr, "w:b"))) fmt.bold = true;
  if (on(child(rpr, "w:i"))) fmt.italic = true;
  const u = child(rpr, "w:u");
  if (u && u.attrs["w:val"] && u.attrs["w:val"] !== "none") fmt.underline = u.attrs["w:val"];
  const va = child(rpr, "w:vertAlign");
  if (va && ["superscript", "subscript"].includes(va.attrs["w:val"])) fmt.vertAlign = va.attrs["w:val"];
  const sc = child(rpr, "w:smallCaps");
  if (sc ? on(sc) : smallCapsOfStyle(fmt.rStyle)) fmt.smallCaps = true;
  return fmt;
}

/**
 * Read a selection.  Returns
 *   {lines, formats, textWidthCm, fonts, refusal}
 * lines: tagged strings, one per line; formats: what the tags stand for;
 * textWidthCm: from the section, or null when the package has none;
 * fonts: the default face(s) named; refusal: a message, or "".
 */
export function readSelection(ooxml) {
  const root = parse(ooxml);
  const doc = partRoot(root, "/word/document.xml") || root;
  const styles = partRoot(root, "/word/styles.xml");
  const body = findAll(doc, "w:body")[0];
  const out = { lines: [], formats: [], textWidthCm: null, fonts: [], refusal: "" };
  if (!body) {
    out.refusal = "Word gave the add-in no text for this selection.";
    return out;
  }

  const smallCapsOfStyle = charStyleSmallCaps(styles);
  const keys = new Map();
  const formatIndex = (fmt) => {
    const key = JSON.stringify(fmt);
    if (!keys.has(key)) {
      keys.set(key, out.formats.length);
      out.formats.push(fmt);
    }
    return keys.get(key);
  };

  let line = "";
  const flush = () => {
    out.lines.push(line);
    line = "";
  };

  // A complex field's state: codes are not text, its result is.
  let inResult = [];
  let code = [];

  // Text is shown only when EVERY enclosing field is in its result part: a
  // field nested in another's code (IF { MERGEFIELD n } = ...) has a result
  // of its own, which the reader never sees.  Asking only the innermost
  // field read it as text -- "answer: 1yes".
  const shown = () => inResult.every(Boolean);

  function runText(r) {
    const fmt = formatIndex(formatOf(child(r, "w:rPr"), smallCapsOfStyle));
    for (const c of r.children) {
      if (typeof c === "string") continue;
      switch (c.name) {
        case "w:fldChar": {
          const t = c.attrs["w:fldCharType"];
          if (t === "begin") { inResult.push(false); code.push(""); }
          else if (t === "separate") {
            inResult[inResult.length - 1] = true;
            if (/^\s*SEQ\s+NumEx\b/i.test(code[code.length - 1])) refuseNumber();
          } else if (t === "end") { inResult.pop(); code.pop(); }
          break;
        }
        case "w:instrText":
          if (code.length) code[code.length - 1] += c.children.join("");
          break;
        case "w:t":
          if (shown()) line += tagRun(c.children.join(""), fmt);
          break;
        case "w:tab":
          if (shown()) line += tagRun("\t", fmt);
          break;
        case "w:noBreakHyphen":
          line += tagRun("‑", fmt);
          break;
        case "w:softHyphen":
          line += tagRun("­", fmt);
          break;
        case "w:br":
        case "w:cr":
          if (!c.attrs["w:type"] || c.attrs["w:type"] === "textWrapping") flush();
          break;
        default:
          break;
      }
    }
  }

  function refuseNumber() {
    out.refusal ||= "The selection already holds an example number. " +
      "Select only the lines of a new example; taking a built example apart " +
      "is not something this version can do yet.";
  }

  // Runs, wherever inline containers put them; deleted text is not text.
  function inline(el) {
    for (const c of el.children) {
      if (typeof c === "string") continue;
      if (c.name === "w:r") runText(c);
      else if (c.name === "w:del" || c.name === "w:moveFrom") continue;
      else if (c.name === "w:fldSimple") {
        if (/^\s*SEQ\s+NumEx\b/i.test(c.attrs["w:instr"] || "")) refuseNumber();
        inline(c);
      } else if (["w:hyperlink", "w:ins", "w:moveTo", "w:smartTag", "w:sdt", "w:sdtContent",
        "w:customXml", "w:dir", "w:bdo"].includes(c.name)) inline(c);
    }
  }

  for (const block of body.children) {
    if (typeof block === "string") continue;
    if (block.name === "w:p") {
      inline(block);
      flush();
    } else if (block.name === "w:tbl") {
      out.refusal ||= "The selection contains a table. Select the typed lines of " +
        "an example, without any table.";
    } else if (block.name === "w:sectPr") {
      const pg = child(block, "w:pgSz");
      const mar = child(block, "w:pgMar");
      if (pg && mar) {
        const tw = (el, a) => Number(el.attrs[a] || 0);
        const text = tw(pg, "w:w") - tw(mar, "w:left") - tw(mar, "w:right") - tw(mar, "w:gutter");
        if (text > 0) out.textWidthCm = text / TWIPS_PER_CM;
      }
    } else if (block.name === "w:sdt") {
      const content = child(block, "w:sdtContent");
      if (content) for (const p of findAll(content, "w:p")) { inline(p); flush(); }
    }
  }

  // The face the example will be drawn in: LxExampleCell names none, so
  // it is the document default's.  A theme reference is reported as such,
  // since the theme is not in the package and its face cannot be named.
  const defaults = styles && findAll(styles, "w:rPrDefault")[0];
  const fonts = defaults && findAll(defaults, "w:rFonts")[0];
  if (fonts) {
    if (fonts.attrs["w:ascii"]) out.fonts.push(fonts.attrs["w:ascii"]);
    else if (fonts.attrs["w:asciiTheme"]) out.fonts.push(`theme:${fonts.attrs["w:asciiTheme"]}`);
  }
  return out;
}
