// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * Where everything goes in one example's table, before any markup --
 * emit_base.BaseEmitter.prepare/_bands/_lead_widths/_word_widths/plan_table,
 * ported.
 *
 * Every number here is a measurement or a count; nothing is spelled in
 * OOXML or in anybody's builder API, and test/markup.test.js keeps it so.
 * The Word and OnlyOffice layers render the same plan in their own
 * vocabularies, as emit_odt and emit_docx do the converter's.
 *
 * test/plan.test.js holds planTable to the converter's own plan_table(),
 * run on the same examples by tools/addin_oracle.py, exactly: same bands,
 * same spans, same widths to the last bit.  Keep the arithmetic in the
 * order the Python does it.
 */

import { LAYOUT } from "./constants.js";
import { Grid, emCm, layoutAdvances, pySum, runsWidthCm, textWidthCm } from "./measure.js";
import { strip, tagIndex } from "./parse.js";

/**
 * A cell's text as [[text, smallCaps], ...] -- what the widths are measured
 * from.  *formats* is the host's table of the formats the tag marks stand
 * for; a format counts as small caps when it says so.
 */
export function runsOf(cell, formats = []) {
  const out = [];
  let fmt = -1;
  let text = "";
  for (let i = 0; i < cell.length; i++) {
    const n = tagIndex(cell[i]);
    if (n >= 0) {
      if (text) out.push([text, Boolean(formats[fmt]?.smallCaps)]);
      text = "";
      fmt = n;
    } else {
      text += cell[i];
    }
  }
  if (text) out.push([text, Boolean(formats[fmt]?.smallCaps)]);
  return out;
}

/**
 * The parser's items as an example in the shape of ir.Example: one body
 * for a plain example, one item per letter for a paradigm.  One tier is
 * unglossed running text, its words joined as LxJoinWords joins them.
 */
export function toExample(items, index = 0) {
  const body = (it) => {
    const glossed = it.tiers.length > 1;
    return {
      judgment: it.judgment,
      text: glossed ? "" : (it.tiers[0] || []).join(" "),
      tiers: glossed ? it.tiers : [],
      translation: it.translation,
      source: "",
      annot: it.annot,
    };
  };
  if (items.length === 1 && !items[0].marker) {
    return { index, customLabel: "", body: body(items[0]), items: [] };
  }
  return {
    index, customLabel: "", body: null,
    items: items.map((it, k) => ({ level: 1, ordinal: k, marker: it.marker, body: body(it) })),
  };
}

function bodiesOf(ex) {
  return ex.body ? [["", ex.body]] : ex.items.map((i) => [i.marker, i.body]);
}

function widthOfBody(body) {
  let w = 0;
  for (const t of body.tiers) if (t.length > w) w = t.length;
  return w;
}

/**
 * A copy of *layout* with the number, letter and judgment columns sized
 * for the whole document -- BaseEmitter.prepare, the converter's rule.
 * Returns [layout, anyJudgment].
 */
export function prepareDocument(examples, layout = LAYOUT, options = {}) {
  const runs = options.runs || ((s) => runsOf(s, options.formats));
  const wrap = options.wrap || ((n) => `(${n})`);
  const em = emCm(layout);
  const adv = layoutAdvances(layout);

  const marks = examples.flatMap((ex) => bodiesOf(ex).map(([, b]) => b.judgment)).filter(Boolean);
  const anyJudgment = marks.length > 0;
  let judgment = 0;
  if (anyJudgment) {
    let widest = -Infinity;
    for (const m of marks) widest = Math.max(widest, runsWidthCm(runs(m), em, layout.sc_ratio, adv));
    judgment = layout.judgment_gap_cm + widest;
  }

  let numbers = examples.map((ex) => ex.customLabel || wrap(String(ex.index + 1)));
  if (numbers.length === 0) numbers = [wrap("1")];
  let number = -Infinity;
  for (const n of numbers) number = Math.max(number, runsWidthCm(runs(n), em, layout.sc_ratio, adv));

  let letters = examples.flatMap((ex) => ex.items.map((it) => strip(it.marker)));
  if (letters.length === 0) letters = ["a."];
  let letter = -Infinity;
  for (const m of letters) letter = Math.max(letter, textWidthCm(m, em, adv));

  return [{
    ...layout,
    judgment_cm: judgment,
    number_cm: Math.max(layout.number_cm, number + layout.pad_cm) + judgment,
    marker_cm: Math.max(layout.marker_cm, letter + layout.pad_cm) + judgment,
  }, anyJudgment];
}

/**
 * The same for one selection, by the Writer macro's rule rather than the
 * converter's (LxLayOut): an add-in, like the macro, sees one example and
 * not the document, so it cannot know whether some other example is
 * judged.  So the judgment column is reserved always -- at least a "*"
 * wide -- and the number column is sized for "(00)", so the first
 * ninety-nine examples all start their text at the same x.
 * Returns [layout, anyJudgment = true].
 */
export function prepareSelection(example, layout = LAYOUT, options = {}) {
  const runs = options.runs || ((s) => runsOf(s, options.formats));
  const em = emCm(layout);
  const adv = layoutAdvances(layout);
  const w = (s) => runsWidthCm(runs(s), em, layout.sc_ratio, adv);

  let judgment = w("*");
  for (const [, b] of bodiesOf(example)) if (b.judgment) judgment = Math.max(judgment, w(b.judgment));
  judgment = judgment + layout.judgment_gap_cm;

  const number = Math.max(layout.number_cm, w("(00)") + layout.pad_cm) + judgment;
  let marker = layout.marker_cm;
  if (example.items.length) {
    let letter = 0;
    for (const it of example.items) letter = Math.max(letter, w(it.marker));
    marker = Math.max(layout.marker_cm, letter + layout.pad_cm) + judgment;
  }
  return [{ ...layout, judgment_cm: judgment, number_cm: number, marker_cm: marker }, true];
}

/** Greedy band packing -- BaseEmitter._bands. */
export function bands(wordW, available, layout, split, warn) {
  if (!split) {
    const sum = pySum(wordW);
    if (sum > available) {
      warn(`glossed example is about ${sum.toFixed(1)}cm wide against a ` +
           `${available.toFixed(1)}cm text block, and --no-split was given; ` +
           "columns were squeezed and long words will wrap in their cells");
    }
    return [[0, wordW.length]];
  }
  const out = [];
  let start = 0;
  let acc = 0;
  wordW.forEach((w, j) => {
    if (acc + w > available && j > start) {
      out.push([start, j]);
      start = j;
      acc = 0;
    }
    acc += w;
  });
  out.push([start, wordW.length]);
  if (out.length > 1) {
    warn(`glossed example does not fit the ${layout.text_width_cm.toFixed(0)}cm ` +
         `text block; split into ${out.length} bands`);
  }
  const over = wordW.filter((w) => w > available).length;
  if (over) {
    warn(`${over} word(s) are individually wider than the text block ` +
         "and will wrap inside their cell");
  }
  return out;
}

/**
 * Number, letter, judgment -- in that order, the judgment carved out of
 * the column to its left so the mark hangs.  BaseEmitter._lead_widths.
 */
export function leadWidths(layout, hasMarker, hasJudgment) {
  const lead = [layout.number_cm];
  if (hasMarker) lead.push(layout.marker_cm);
  if (hasJudgment) {
    lead[lead.length - 1] -= layout.judgment_cm;
    lead.push(layout.judgment_cm);
  }
  return lead;
}

/** BaseEmitter._word_widths, for one body. */
export function wordWidths(body, layout, runs) {
  const em = emCm(layout);
  const adv = layoutAdvances(layout);
  const widest = new Array(widthOfBody(body)).fill(0);
  for (const tier of body.tiers) {
    tier.forEach((cell, i) => {
      widest[i] = Math.max(widest[i], runsWidthCm(runs(cell), em, layout.sc_ratio, adv));
    });
  }
  return widest.map((w) =>
    Math.min(layout.max_col_cm, Math.max(layout.min_col_cm, w * layout.width_safety + layout.pad_cm)));
}

const sum = pySum;   // every sum() in plan_table is Python's builtin

/**
 * BaseEmitter.plan_table.  *layout* is a prepared one (prepareDocument or
 * prepareSelection).  Returns the plan and the warnings it gave.
 */
export function planTable(ex, layout, options = {}) {
  const runs = options.runs || ((s) => runsOf(s, options.formats));
  const split = options.split ?? true;
  const anyJudgment = options.anyJudgment ?? false;
  const warnings = [];
  const warn = (m) => warnings.push(m);

  const bodies = bodiesOf(ex);
  const hasMarker = ex.body === null;
  const hasJudgment = anyJudgment;

  const lead = leadWidths(layout, hasMarker, hasJudgment);
  let available = layout.text_width_cm - sum(lead);

  // \exannot: a column at annot_column_ratio of the text block, from its
  // left edge; the body gets what is left before it, less \ExAnnotSep.
  const hasAnnot = bodies.some(([, b]) => b.annot);
  const annotX = layout.annot_column_ratio * layout.text_width_cm;
  if (hasAnnot) {
    available = Math.max(layout.min_col_cm,
      annotX - sum(lead) - layout.annot_sep_em * emCm(layout));
  }

  // One plan per body, each measured and banded on its own words.
  let plans = bodies.map(([, b]) => {
    if (b.tiers.length) {
      const w = wordWidths(b, layout, runs);
      return [w, bands(w, available, layout, split, warn)];
    }
    return [[], []];
  });
  if (!plans.some(([w]) => w.length)) plans = bodies.map(() => [[available], [[0, 1]]]);

  const grid = new Grid(plans);
  let columns = grid.columns;
  let total = grid.total;
  if (total > available) {
    const scale = available / total;
    columns = columns.map((c) => c * scale);
    total = available;
  }
  let filler = total <= available - layout.min_col_cm ? 1 : 0;
  let widths = [...lead, ...columns, ...(filler ? [available - total] : [])];
  if (hasAnnot) {
    widths = [...lead, ...columns];
    const gap = annotX - sum(lead) - total;
    // Emitted however narrow: the gap IS \ExAnnotSep.
    filler = gap > 0.01 ? 1 : 0;
    if (filler) widths = [...widths, gap];
    widths = [...widths, layout.text_width_cm - sum(widths)];
  }
  return {
    plan: { bodies, hasMarker, hasJudgment, hasAnnot, lead, columns, widths, grid, filler },
    warnings,
  };
}
