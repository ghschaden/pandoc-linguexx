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

import { strip, tagRun } from "../core/parse.js";
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
 * The run reader both a selection and a built table are read with.
 *
 * *sink* receives what a reader sees: text(s, fmtIndex) for shown text,
 * brk() for a line break, and number({bookmark, shown}) for an example
 * number -- a SEQ NumEx field, handed over whole and never as text, with
 * the name of the bookmark round it, which is the identity every
 * cross-reference points at.  Formats are collected into *formats*.
 */
function inlineReader(styles, formats) {
  const smallCapsOfStyle = charStyleSmallCaps(styles);
  const keys = new Map(formats.map((f, i) => [JSON.stringify(f), i]));
  const formatIndex = (fmt) => {
    const key = JSON.stringify(fmt);
    if (!keys.has(key)) {
      keys.set(key, formats.length);
      formats.push(fmt);
    }
    return keys.get(key);
  };

  // A complex field's state: codes are not text, its result is.  Text is
  // shown only when EVERY enclosing field is in its result part: a field
  // nested in another's code (IF { MERGEFIELD n } = ...) has a result of
  // its own, which the reader never sees.  Asking only the innermost field
  // read it as text -- "answer: 1yes".
  const inResult = [];
  const code = [];
  const shown = () => inResult.every(Boolean);
  // An example number's result is collected, not emitted.
  let number = null;
  // Bookmarks open at this point, by id: the one round a number is its name.
  const open = new Map();

  return function read(el, sink) {
    const numberStarts = () => {
      const names = [...open.values()];
      number = { bookmark: names.length ? names[names.length - 1] : "", shown: "" };
    };
    const emit = (s, fmt) => {
      if (number) number.shown += s;
      else if (shown()) sink.text(s, fmt);
    };
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
              if (/^\s*SEQ\s+NumEx\b/i.test(code[code.length - 1]) && inResult.length === 1) numberStarts();
            } else if (t === "end") {
              inResult.pop();
              code.pop();
              if (number && inResult.length === 0) { sink.number(number); number = null; }
            }
            break;
          }
          case "w:instrText":
            if (code.length) code[code.length - 1] += c.children.join("");
            break;
          case "w:t":
            emit(c.children.join(""), fmt);
            break;
          case "w:tab":
            emit("\t", fmt);
            break;
          case "w:noBreakHyphen":
            emit("‑", fmt);
            break;
          case "w:softHyphen":
            emit("­", fmt);
            break;
          case "w:br":
          case "w:cr":
            if (!c.attrs["w:type"] || c.attrs["w:type"] === "textWrapping") sink.brk();
            break;
          default:
            break;
        }
      }
    }
    // Runs, wherever inline containers put them; deleted text is not text.
    (function inline(node) {
      for (const c of node.children) {
        if (typeof c === "string") continue;
        if (c.name === "w:r") runText(c);
        else if (c.name === "w:bookmarkStart") open.set(c.attrs["w:id"], c.attrs["w:name"]);
        else if (c.name === "w:bookmarkEnd") open.delete(c.attrs["w:id"]);
        else if (c.name === "w:del" || c.name === "w:moveFrom") continue;
        else if (c.name === "w:fldSimple") {
          if (/^\s*SEQ\s+NumEx\b/i.test(c.attrs["w:instr"] || "") && inResult.length === 0) {
            numberStarts();
            inline(c);
            sink.number(number);
            number = null;
          } else inline(c);
        } else if (["w:hyperlink", "w:ins", "w:moveTo", "w:smartTag", "w:sdt", "w:sdtContent",
          "w:customXml", "w:dir", "w:bdo"].includes(c.name)) inline(c);
      }
    })(el);
  };
}

/** The document's default face, as selection and table readers report it. */
function defaultFonts(styles) {
  // LxExampleCell names no face, so the example is drawn in the document
  // default's.  A theme reference is reported as such, since the theme is
  // not in the package and its face cannot be named.
  const out = [];
  const defaults = styles && findAll(styles, "w:rPrDefault")[0];
  const fonts = defaults && findAll(defaults, "w:rFonts")[0];
  if (fonts) {
    if (fonts.attrs["w:ascii"]) out.push(fonts.attrs["w:ascii"]);
    else if (fonts.attrs["w:asciiTheme"]) out.push(`theme:${fonts.attrs["w:asciiTheme"]}`);
  }
  return out;
}

/**
 * Read a selection.  Returns
 *   {lines, formats, textWidthCm, fonts, number, refusal}
 * lines: tagged strings, one per line; formats: what the tags stand for;
 * textWidthCm: from the section, or null when the package has none;
 * fonts: the default face(s) named; number: {bookmark, shown} when the
 * selection leads with an example number to take over, else null;
 * refusal: a message, or "".
 *
 * A number is TAKEN OVER, not remade -- the Writer macro's rule
 * (LxTakeNumber): an example untypeset and typeset again keeps the field
 * every cross-reference to it points at.  So its bookmark is recorded and
 * its "(" and ")" dropped; it must lead the selection, and there may be
 * only one, or it would move silently from one example to another.
 */
export function readSelection(ooxml) {
  const root = parse(ooxml);
  const doc = partRoot(root, "/word/document.xml") || root;
  const styles = partRoot(root, "/word/styles.xml");
  const body = findAll(doc, "w:body")[0];
  const out = { lines: [], formats: [], textWidthCm: null, fonts: defaultFonts(styles), number: null, refusal: "" };
  if (!body) {
    out.refusal = "Word gave the add-in no text for this selection.";
    return out;
  }

  const read = inlineReader(styles, out.formats);
  let line = "";
  let closer = false;             // drop the ")" that closes a taken-over number
  const sink = {
    text(s, fmt) {
      if (closer && s.startsWith(")")) s = s.slice(1);
      if (s) closer = false;
      if (s) line += tagRun(s, fmt);
    },
    brk() { out.lines.push(line); line = ""; closer = false; },
    number(n) {
      if (out.number) {
        out.refusal ||= "The selection carries two example numbers.\n\nAn example has one. " +
          "Typeset one example at a time.";
        return;
      }
      const before = out.lines.map(strip).join("") + strip(line);
      if (before.replace(/[\s(]/g, "") !== "") {
        out.refusal ||= "An example number appears part-way through the selection.\n\n" +
          "The number an example takes over has to lead it. Start the selection at the " +
          "number, or leave the number out and a new one is made.";
        return;
      }
      out.number = n;
      // the "(" in front of it goes with it
      const at = line.lastIndexOf("(");
      if (at >= 0) line = line.slice(0, at) + line.slice(at + 1);
      closer = true;
    },
  };

  for (const block of body.children) {
    if (typeof block === "string") continue;
    if (block.name === "w:p") {
      read(block, sink);
      sink.brk();
    } else if (block.name === "w:tbl") {
      out.refusal ||= "The selection contains a table. Select the typed lines of an example, " +
        "without any table -- or put the cursor in a built example and untypeset it.";
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
      if (content) for (const p of findAll(content, "w:p")) { read(p, sink); sink.brk(); }
    }
  }
  return out;
}

/**
 * Read the first table in a package -- a built example, when the cursor is
 * in one -- as core/untypeset.js reads tables: rows of {style, text}, the
 * style by its NAME (a document OnlyOffice has saved names them "1_363"),
 * the text tagged, a cell's paragraphs and line breaks joined by a space
 * as LxReadText joins them.  The example number is not text: it comes
 * back as {bookmark, shown}.
 * Returns {rows, formats, number, fonts, textWidthCm, refusal}.
 */
export function readExampleTable(ooxml) {
  const root = parse(ooxml);
  const doc = partRoot(root, "/word/document.xml") || root;
  const styles = partRoot(root, "/word/styles.xml");
  const out = { rows: [], formats: [], number: null, fonts: defaultFonts(styles), textWidthCm: null, refusal: "" };
  const table = findAll(doc, "w:tbl")[0];
  if (!table) {
    out.refusal = "Put the cursor in the example you want back as text.";
    return out;
  }
  const names = new Map();
  if (styles) {
    for (const st of findAll(styles, "w:style")) {
      const n = child(st, "w:name");
      names.set(st.attrs["w:styleId"], n ? n.attrs["w:val"] : st.attrs["w:styleId"]);
    }
  }
  const read = inlineReader(styles, out.formats);
  for (const tr of table.children) {
    if (typeof tr === "string" || tr.name !== "w:tr") continue;
    const row = [];
    for (const tc of tr.children) {
      if (typeof tc === "string" || tc.name !== "w:tc") continue;
      let text = "";
      let style = "";
      const sink = {
        text(s, fmt) { text += tagRun(s, fmt); },
        brk() { text += " "; },
        number(n) { if (!out.number) out.number = n; },
      };
      for (const p of findAll(tc, "w:p")) {
        if (!style) {
          const ppr = child(p, "w:pPr");
          const ps = ppr && child(ppr, "w:pStyle");
          if (ps) style = names.get(ps.attrs["w:val"]) || ps.attrs["w:val"];
        }
        if (text) text += " ";
        read(p, sink);
      }
      row.push({ style, text });
    }
    out.rows.push(row);
  }
  const sect = findAll(doc, "w:sectPr").pop();
  if (sect) {
    const pg = child(sect, "w:pgSz");
    const mar = child(sect, "w:pgMar");
    if (pg && mar) {
      const tw = (el, a) => Number(el.attrs[a] || 0);
      const w = tw(pg, "w:w") - tw(mar, "w:left") - tw(mar, "w:right") - tw(mar, "w:gutter");
      if (w > 0) out.textWidthCm = w / TWIPS_PER_CM;
    }
  }
  return out;
}
