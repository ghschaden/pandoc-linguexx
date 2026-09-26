// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * The Word task pane: Office.js glue, and nothing else.
 *
 * Everything that can be decided without Word is decided elsewhere and
 * tested there -- the parse and the plan in core/, the markup in
 * ooxml.js, the selection in selection.js, the numbers in numbering.js.
 * What is left is asking Word and telling Word, under the three rules
 * plan-addins.md took from S6:
 *
 *  - the inserted example's number is counted, not recalculated, and
 *    written into its cache (Word on the web recalculates nothing);
 *  - what goes stale behind an insertion is checked and reported, never
 *    claimed correct unchecked;
 *  - an insertion error is not trusted either way -- insertOoxml can
 *    insert and still throw, and after an error the page takes no further
 *    insertion until it is reloaded -- so the document is read back, the
 *    user is told what is there, and nothing more is inserted until reload.
 */

/* global Office, Word */

import { LAYOUT, NAMES } from "../core/constants.js";
import { advancesFor } from "../core/measure.js";
import { parseLines, strip } from "../core/parse.js";
import { planTable, prepareSelection, toExample } from "../core/plan.js";
import { OPT, checkSettings, readSettings, spacingPlan } from "../core/settings.js";
import { audit, freshBookmark, isExampleNumber, numberAt, refTarget, staleMessage } from "./numbering.js";
import { AFTER_EXAMPLE, exampleTable, flatPackage, sequenceRef } from "./ooxml.js";
import { readSelection } from "./selection.js";
import { untypesetPackage } from "./untypeset.js";
import { STYLE_IDS } from "./styles.js";

const POINTS_PER_CM = 72 / 2.54;
const LAYOUT_FIELDS = ["indentCm", "numberCm", "markerCm", "aboveCm", "belowCm"];

/** The document's indents: the Writer macro's user-defined properties. */
async function readProps(ctx) {
  const custom = ctx.document.properties.customProperties;
  custom.load("items/key,items/value");
  await ctx.sync();
  const props = {};
  for (const p of custom.items) if (Object.values(OPT).includes(p.key)) props[p.key] = p.value;
  return props;
}

/** The spacing styles' line heights, in cm; absent where there is no style. */
async function readSpacing(ctx) {
  const styles = ctx.document.getStyles();
  const get = (n) => styles.getByNameOrNullObject(n);
  const found = [NAMES.SPACE_PARA, NAMES.SPACE_ABOVE, NAMES.SPACE_BELOW].map(get);
  found.forEach((s) => s.load("isNullObject"));
  await ctx.sync();
  const fmts = found.map((s) => (s.isNullObject ? null : s.paragraphFormat));
  fmts.forEach((f) => f && f.load("lineSpacing"));
  await ctx.sync();
  const cm = (f) => (f && f.lineSpacing ? f.lineSpacing / POINTS_PER_CM : undefined);
  const parent = cm(fmts[0]);
  return { aboveCm: cm(fmts[1]) ?? parent, belowCm: cm(fmts[2]) ?? parent };
}

async function loadLayout() {
  await Word.run(async (ctx) => {
    const s = readSettings(await readProps(ctx), await readSpacing(ctx));
    for (const k of LAYOUT_FIELDS) $(k).value = String(Math.round(s[k] * 100) / 100);
  });
}

/**
 * Store the five lengths: the indents as the macro's properties, the
 * spacings in the styles (core/settings.spacingPlan).  A style change is
 * read back: changing a style's font through Office.js had no effect in
 * Word on the web, so the spacing may not take either, and the pane says
 * so rather than claiming it did.
 */
async function applyLayout() {
  const s = {};
  for (const k of LAYOUT_FIELDS) s[k] = parseFloat(String($(k).value).replace(",", "."));
  const refusal = checkSettings(s);
  if (refusal) return say(refusal, "error");
  let spacingNote = "";
  await Word.run(async (ctx) => {
    const custom = ctx.document.properties.customProperties;
    custom.add(OPT.indent, s.indentCm);
    custom.add(OPT.number, s.numberCm);
    custom.add(OPT.marker, s.markerCm);
    await ctx.sync();

    const styles = ctx.document.getStyles();
    const plan = spacingPlan(s.aboveCm, s.belowCm).filter((it) => !it.inherit);
    const targets = plan.map((it) => styles.getByNameOrNullObject(it.style));
    targets.forEach((t) => t.load("isNullObject"));
    await ctx.sync();
    if (targets.some((t) => t.isNullObject)) {
      spacingNote = "The spacing is a style an example brings: typeset one example first, then set it.";
      return;
    }
    plan.forEach((it, i) => { targets[i].paragraphFormat.lineSpacing = it.cm * POINTS_PER_CM; });
    await ctx.sync();
    targets.forEach((t) => t.paragraphFormat.load("lineSpacing"));
    await ctx.sync();
    const missed = plan.filter((it, i) => Math.abs(targets[i].paragraphFormat.lineSpacing - it.cm * POINTS_PER_CM) > 0.1);
    if (missed.length) {
      spacingNote = "Word did not change the spacing: set it in the Styles pane instead -- " +
        missed.map((it) => `${it.style}, line spacing Exactly ${(it.cm * POINTS_PER_CM).toFixed(1)} pt`).join("; ") + ".";
    }
  });
  say(spacingNote ? "The indents are set." : "Layout applied: the spacing now, the indents from the next example on.",
    spacingNote ? "error" : "ok");
  note([spacingNote]);
}

/** Set after Word reports an insertion error: see the module comment. */
let broken = false;

const $ = (id) => document.getElementById(id);

function say(message, kind = "info") {
  const box = $("status");
  box.className = kind;
  box.textContent = message;
}

/**
 * Run *work* with every button disabled and the status saying so.
 *
 * Word on the web takes a second or two per call, and the first live test
 * showed what happens when the pane gives no sign of having heard a click:
 * it was clicked again, and one reference went in five times.  A second
 * click while this runs now finds the button disabled.
 */
let working = false;
async function busy(message, work) {
  if (working) return;
  working = true;
  const buttons = [...document.querySelectorAll("button")];
  buttons.forEach((b) => { b.disabled = true; });
  say(message);
  try {
    await work();
  } catch (e) {
    say(e.message, "error");
  } finally {
    working = false;
    document.querySelectorAll("button").forEach((b) => { b.disabled = false; });
  }
}

function note(lines) {
  $("notes").textContent = lines.filter(Boolean).join("\n\n");
}

const RELOAD = "Word reported an error during an insertion. Reload this page " +
  "(F5, or close and reopen the add-in) before inserting anything else: until " +
  "then Word refuses every further insertion, even a correct one.";

/** Every field in the body, in order, as numbering.js wants them. */
async function allFields(ctx) {
  const fields = ctx.document.body.fields;
  fields.load("items/code,items/result/text");
  await ctx.sync();
  // One round trip for every field's bookmarks, not one per field.
  const marks = fields.items.map((f) => f.result.getBookmarks(true, true));
  await ctx.sync();
  return fields.items.map((f, i) => ({
    field: f, code: f.code, shown: f.result.text, bookmarks: marks[i].value,
  }));
}

/**
 * Bring the example numbers and our references up to date where the host
 * allows it, and say what is left.  Only SEQ NumEx fields and REF fields
 * pointing at one are touched: updating every field would also refresh a
 * user's dates and tables of contents, which is not ours to do.
 */
async function renumber(ctx) {
  let fields = await allFields(ctx);
  let { numbers, stale } = audit(fields);
  if (!stale.length) return "";
  // Word on the web accepts updateResult and does nothing (S6 fact 4):
  // asking, and reading every field back afterwards, only costs round trips.
  if (Office.context.platform === Office.PlatformType.OfficeOnline) return staleMessage(stale);
  try {
    for (const f of fields) {
      const target = refTarget(f.code);
      if (isExampleNumber(f.code) || (target && target in numbers)) f.field.updateResult();
    }
    await ctx.sync();
    fields = await allFields(ctx);
    ({ stale } = audit(fields));
  } catch (e) {
    // Word on the web: updateResult is accepted and does nothing, or refused.
  }
  return staleMessage(stale);
}

async function typeset() {
  if (broken) return say(RELOAD, "error");
  note([]);
  let name = "";
  let inserting = false;   // only an error from the insertion itself breaks the page
  let needAudit = true;
  let wanted = "";
  const notes = [];
  try {
    await Word.run(async (ctx) => {
      const sel = ctx.document.getSelection();
      const ooxml = sel.getOoxml();
      const ahead = ctx.document.body.getRange("Start").expandTo(sel.getRange("Start")).fields;
      ahead.load("items/code");
      const every = ctx.document.body.fields;
      every.load("items/code");
      const marks = ctx.document.body.getRange("Whole").getBookmarks(true, true);
      const styles = ctx.document.getStyles();
      styles.load("items/nameLocal");
      // The face the lines are typed in is the face the example is set in
      // and measured for -- Word reports it resolved ("Aptos", not a theme
      // slot).
      const typed = sel.paragraphs.getFirst().font;
      typed.load("name,size");
      await ctx.sync();

      const read = readSelection(ooxml.value);
      if (read.refusal) throw new Refusal(read.refusal);
      const parsed = parseLines(read.lines);
      if (parsed.error) throw new Refusal(parsed.error);

      const ex = toExample(parsed.items);
      const width = read.textWidthCm ?? LAYOUT.text_width_cm;
      if (read.textWidthCm === null) {
        notes.push(`Word did not say how wide the text block is; the example is laid out for ${width} cm.`);
      }
      const face = typed.name || LAYOUT.font_name;
      wanted = face;
      const size = typed.size || LAYOUT.font_pt;
      if (!advancesFor(face).known) {
        notes.push(`The columns are estimated from Times New Roman's metrics, and this text is in ` +
          `${face}, which has not been measured. Words may wrap in their columns.`);
      }
      const settings = readSettings(await readProps(ctx));
      const [layout, anyJudgment] = prepareSelection(ex,
        { ...LAYOUT, text_width_cm: width, font_name: face, font_pt: size }, { formats: read.formats, settings });
      const { plan, warnings } = planTable(ex, layout, { anyJudgment, formats: read.formats });
      notes.push(...warnings);

      // A number the selection leads with is taken over, not remade: an
      // example untypeset and typeset again keeps the field its references
      // point at.  Its old bookmark goes with the selection it is in.
      name = read.number ? read.number.bookmark : freshBookmark(marks.value);
      const id = 100000 + Math.floor(Math.random() * 800000);
      const n = numberAt(ahead.items.map((f) => f.code));
      // Nothing can be stale when no example follows this one -- inserting
      // at the end, the common case -- and a taken-over number kept its
      // value: then the audit, every field and every bookmark read back over
      // a slow connection, is skipped.
      const seq = (fs) => fs.filter((f) => isExampleNumber(f.code)).length;
      const later = seq(every.items) - seq(ahead.items) - (read.number ? 1 : 0);
      needAudit = later > 0 || (read.number && String(read.number.shown).trim() !== String(n));
      const table = exampleTable(ex, plan, { number: { id, name, cached: String(n) }, formats: read.formats });
      const have = new Set(styles.items.map((s) => s.nameLocal));
      const withStyles = STYLE_IDS.some((s) => !have.has(s));

      inserting = true;
      sel.insertOoxml(flatPackage(table + AFTER_EXAMPLE,
        { withStyles, defaults: { face, halfPoints: Math.round(size * 2) } }), "Replace");
      await ctx.sync();
    });
  } catch (e) {
    if (e instanceof Refusal) return say(e.message, "error");
    if (!inserting) return say(`Could not read the selection: ${e.message}`, "error");
    broken = true;
    // Not trusted either way: look.
    let there = false;
    try {
      await Word.run(async (ctx) => {
        const r = ctx.document.getBookmarkRangeOrNullObject(name);
        await ctx.sync();
        there = name && !r.isNullObject;
      });
    } catch (_) { /* reading failed too */ }
    return say((there ? "The example was inserted, but " : "The example may not have been inserted: ") +
      RELOAD + ` (Word said: ${e.message})`, "error");
  }

  // Check, don't trust: the face the example came out in.  A version of this
  // add-in inserted examples Word set in Times New Roman in an Aptos
  // document, twice, for two different reasons; this says so if it happens.
  try {
    await Word.run(async (ctx) => {
      const mark = ctx.document.getBookmarkRangeOrNullObject(name);
      mark.load("isNullObject");
      await ctx.sync();
      if (mark.isNullObject) return;
      const cell = mark.parentTableCellOrNullObject;
      cell.load("isNullObject");
      await ctx.sync();
      if (cell.isNullObject) return;
      const row = cell.parentRow;
      row.load("cellCount");
      await ctx.sync();
      const text = row.cells;
      text.load("items/body/font/name");
      await ctx.sync();
      const faces = [...new Set(text.items.map((c) => c.body.font.name).filter(Boolean))];
      if (faces.length && !faces.every((f) => f === wanted)) {
        notes.push(`Word set this example in ${faces.join(", ")}, not in ${wanted} as asked.`);
      }
    });
  } catch (e) { /* the check is a courtesy; the example is in */ }

  if (needAudit) {
    try {
      await Word.run(async (ctx) => {
        const left = await renumber(ctx);
        if (left) notes.push(left);
      });
    } catch (e) {
      notes.push(`The example is in, but its numbering could not be checked: ${e.message}`);
    }
  }
  say("Done.", "ok");
  note(notes);
}

class Refusal extends Error {}

/**
 * The example the cursor is in, back as the lines it was typed as, its
 * number -- the same field -- at the head of the first (plan-addins.md,
 * Phase 4; the Writer macro's Untypeset).
 */
async function untypeset() {
  if (broken) return say(RELOAD, "error");
  note([]);
  let inserting = false;
  try {
    await Word.run(async (ctx) => {
      const table = ctx.document.getSelection().parentTableOrNullObject;
      table.load("isNullObject");
      await ctx.sync();
      if (table.isNullObject) throw new Refusal("Put the cursor in the example you want back as text.");
      const range = table.getRange("Whole");
      const ooxml = range.getOoxml();
      await ctx.sync();
      const u = untypesetPackage(ooxml.value, 100000 + Math.floor(Math.random() * 800000));
      if (u.refusal) throw new Refusal(u.refusal);
      inserting = true;
      range.insertOoxml(u.pkg, "Replace");
      await ctx.sync();
    });
  } catch (e) {
    if (e instanceof Refusal) return say(e.message, "error");
    if (!inserting) return say(`Could not read the example: ${e.message}`, "error");
    broken = true;
    return say(RELOAD + ` (Word said: ${e.message})`, "error");
  }
  say("Back as text. Edit it, select the lines, and typeset them again: the number stays the same.", "ok");
}

/** The examples in the document, for the reference list. */
async function listExamples() {
  if (broken) return say(RELOAD, "error");
  const list = $("examples");
  list.textContent = "";
  await Word.run(async (ctx) => {
    const every = await allFields(ctx);
    const { numbers } = audit(every);
    const fields = every.filter((f) => isExampleNumber(f.code));
    // The preview is the row holding the number, not the table's first
    // row: Word joins adjacent tables (S6 fact 3), so a converted document's
    // consecutive examples are one table, and its first row previewed every
    // one of them the same.  A number outside any table previews its
    // paragraph.
    const cells = fields.map((f) => f.field.result.parentTableCellOrNullObject);
    const paras = fields.map((f) => f.field.result.paragraphs.getFirst());
    paras.forEach((p) => p.load("text"));
    cells.forEach((c) => c.load("isNullObject"));
    await ctx.sync();
    const rows = cells.map((c) => {
      if (c.isNullObject) return null;
      const r = c.parentRow;
      r.load("values");
      return r;
    });
    await ctx.sync();
    fields.forEach((f, i) => {
      const bookmark = f.bookmarks[0];
      if (!bookmark) return;
      const text = rows[i] ? rows[i].values[0].slice(1).join(" ")
        : paras[i].text.replace(/^\s*\(?\s*\d+\s*\)?/, "");
      const preview = text.replace(/\s+/g, " ").trim().slice(0, 60);
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.textContent = `(${numbers[bookmark]}) ${preview}`;
      button.onclick = () => busy("Inserting the reference…", () => insertReference(bookmark, numbers[bookmark]));
      li.appendChild(button);
      list.appendChild(li);
    });
    say(fields.length ? "Choose the example to refer to." : "There are no examples in this document yet.");
  });
}

async function insertReference(bookmark, number) {
  if (broken) return say(RELOAD, "error");
  const bare = $("bare").checked;
  try {
    await Word.run(async (ctx) => {
      const sel = ctx.document.getSelection();
      sel.insertOoxml(flatPackage(`<w:p>${sequenceRef(bookmark, String(number), { bare })}</w:p>`), "Replace");
      await ctx.sync();
    });
    say("Reference inserted.", "ok");
  } catch (e) {
    broken = true;
    say(RELOAD + ` (Word said: ${e.message})`, "error");
  }
}

Office.onReady(() => {
  if (!Office.context.requirements.isSetSupported("WordApi", "1.5")) {
    say("This version of Word lacks the field API the add-in needs (WordApi 1.5).", "error");
    return;
  }
  $("typeset").onclick = () => busy("Typesetting…", typeset);
  $("refs").onclick = () => busy("Reading the document's examples…", listExamples);
  $("untypeset").onclick = () => busy("Untypesetting…", untypeset);
  $("applyLayout").onclick = () => busy("Applying the layout…", applyLayout);
  loadLayout().catch(() => { /* a document Word cannot read yet keeps the defaults shown */ });
  say("Select the lines of an example, then Typeset.");
});

// for the console, when something needs looking at
globalThis.linguexx = { readSelection, parseLines, strip };
