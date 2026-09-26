// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * How wide a thing is, and which column it lands in -- src/linguexx2odt/
 * measure.py, ported.
 *
 * Arithmetic over centimetres and nothing about any markup, as there.  Not
 * a translation "in spirit": every sum runs in the order Python's does, so
 * the two agree to the last bit rather than to a tolerance, and the plan
 * test (test/plan.test.js) compares them exactly.  Floating-point addition
 * is not associative; reordering one of these loops is a change of result.
 *
 * And where the Python calls sum(), this calls pySum(): since 3.12, sum()
 * of floats is *compensated*, not a running total, and a plain loop comes
 * out a unit in the last place away.  Where the Python writes `x += w`, so
 * does this.
 */

import { ADVANCE, FACE_ADVANCE, FALLBACK_OTHER, FALLBACK_UPPER, GRID_TOL, TIMES_METRIC } from "./constants.js";

/**
 * Python's builtin sum() over floats, as CPython 3.12+ computes it: Neumaier's
 * improved Kahan-Babuska summation, compensation added once at the end
 * (Python/bltinmodule.c, builtin_sum_impl).  Starting from 0 is exact: the
 * int start plus the first float is that float.
 */
export function pySum(xs) {
  let f = 0;
  let c = 0;
  for (const x of xs) {
    const t = f + x;
    if (Math.abs(f) >= Math.abs(x)) c += (f - t) + x;
    else c += (x - t) + f;
    f = t;
  }
  if (c && Number.isFinite(c)) f += c;
  return f;
}

/** Python's str.isupper(), for the one-or-two-character strings used here. */
function isUpper(s) {
  return s.toUpperCase() === s && s.toLowerCase() !== s;
}

/** Python's str.islower(). */
function isLower(s) {
  return s.toLowerCase() === s && s.toUpperCase() !== s;
}

/**
 * Advance of one character, in em.  *ch* may be two characters long: the
 * capital of "ß" is "SS", which Python looks up (and misses) as one key too.
 */
export function advance(ch, advances = ADVANCE) {
  const width = advances[ch];
  if (width !== undefined) return width;
  return isUpper(ch) ? FALLBACK_UPPER : FALLBACK_OTHER;
}

/** measure.text_width_cm: the sum first, then the scale. */
export function textWidthCm(text, emCm, advances = ADVANCE) {
  return pySum(Array.from(text, (c) => advance(c, advances))) * emCm;
}

/** A small capital: the capital's advance at scRatio of the size. */
function scAdvance(ch, scRatio, advances) {
  if (isLower(ch)) return advance(ch.toUpperCase(), advances) * scRatio;
  return advance(ch, advances);
}

/**
 * measure.runs_width_cm.  *runs* is [[text, smallCaps], ...], as
 * InlineRenderer.runs() gives Python -- each measured as drawn.
 */
export function runsWidthCm(runs, emCm, scRatio, advances = ADVANCE) {
  return emCm * pySum(runs.map(([text, smallCaps]) => pySum(Array.from(text, (c) =>
    smallCaps ? scAdvance(c, scRatio, advances) : advance(c, advances)))));
}

/** Whether *name* is a face ADVANCE describes (measure.TIMES_METRIC). */
export function isTimesMetric(name) {
  const key = String(name).toLowerCase().replace(/ /g, "");
  return TIMES_METRIC.some((f) => f.replace(/ /g, "") === key);
}

/**
 * The advances to estimate *name* with -- measure.advances_for, less the
 * reading of font files a browser cannot do: Times metrics for a
 * Times-metric face, a measured face's own table (Aptos), and otherwise
 * Times metrics with {known: false}, so the caller can say the columns are
 * estimated for another face.
 */
export function advancesFor(name) {
  const key = String(name || "").toLowerCase().replace(/ /g, "");
  if (!key || isTimesMetric(name)) return { advances: ADVANCE, known: true };
  if (FACE_ADVANCE[key]) return { advances: FACE_ADVANCE[key], known: true };
  return { advances: ADVANCE, known: false };
}

/** The advances a layout's face is estimated with (Layout.advances). */
export function layoutAdvances(layout) {
  return advancesFor(layout.font_name).advances;
}

/** Layout.em_cm */
export function emCm(layout) {
  return (layout.font_pt / 72) * 2.54;
}

/**
 * The column grid of one example's table: the union of every word boundary
 * that every band of every body produces, each word spanning the columns
 * it covers.  measure.Grid, and its docstring is the explanation.
 *
 * *plans* is [[wordWidths, bands], ...], one per body; bands are
 * [start, stop) pairs of word indices.
 */
export class Grid {
  constructor(plans) {
    this.plans = plans;

    const edges = [];
    for (const [wordWidths, bands] of plans) {
      for (const [start, stop] of bands) {
        let x = 0;
        for (let j = start; j < stop; j++) {
          x += wordWidths[j];
          edges.push(x);
        }
      }
    }
    const merged = [];
    for (const x of [...edges].sort((a, b) => a - b)) {
      if (merged.length === 0 || x - merged[merged.length - 1] > GRID_TOL) merged.push(x);
    }
    this.edges = merged;

    // max((sum(w) for w, _ in plans), default=0.0)
    let widest = 0;
    plans.forEach(([w], i) => {
      const s = pySum(w);
      if (i === 0 || s > widest) widest = s;
    });
    const columns = [];
    let prev = 0;
    for (const b of merged) {
      columns.push(b - prev);
      prev = b;
    }
    this.columns = columns.length ? columns : [widest];
    this.total = merged.length ? merged[merged.length - 1] : widest;

    // "body,word" -> [first grid column, span]
    this._placement = new Map();
    plans.forEach(([wordWidths, bands], k) => {
      for (const [start, stop] of bands) {
        let x = 0;
        for (let j = start; j < stop; j++) {
          const lo = this._edgeIndex(x);
          x += wordWidths[j];
          const hi = this._edgeIndex(x);
          this._placement.set(`${k},${j}`, [lo, Math.max(1, hi - lo)]);
        }
      }
    });
  }

  /** Number of grid columns lying left of position x. */
  _edgeIndex(x) {
    for (let i = 0; i < this.edges.length; i++) {
      if (Math.abs(this.edges[i] - x) <= GRID_TOL) return i + 1;
    }
    let n = 0;
    for (const e of this.edges) if (e < x) n++;
    return n;
  }

  bandsOf(body) {
    return this.plans[body][1];
  }

  /** First grid column of word *word* of body *body*. */
  column(body, word) {
    return this._placement.get(`${body},${word}`)[0];
  }

  span(body, word) {
    return this._placement.get(`${body},${word}`)[1];
  }
}
