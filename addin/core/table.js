// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * One example's table as rows of cells -- what goes where, before any
 * markup.  emit_docx's _table/_body_rows/_band_cells, with the markup
 * taken out: which cell spans which grid columns, how wide it is, which
 * paragraph style it carries, and whether it holds the number, some text
 * or nothing.
 *
 * Shared because two hosts write it.  The Word layer serializes it as
 * OOXML (word/ooxml.js, held string for string to the converter); the
 * OnlyOffice layer builds it with the builder API.  Kept once, the row
 * logic cannot come out one way in Word and another in OnlyOffice -- and
 * the Word comparison with the converter tests it for both.
 *
 * A cell is {widthCm, span, style, content}; content is one of
 *   {kind: "empty"}
 *   {kind: "number"}                  the example number, whatever carries it
 *   {kind: "text", text}              a tagged string (see parse.js)
 */

import { NAMES } from "./constants.js";
import { pySum } from "./measure.js";

// Every sum() in emit_docx is Python's builtin, compensated since 3.12 (see
// measure.js); a last-place difference can round to another twip.
const sum = pySum;

const empty = { kind: "empty" };
const text = (t) => (t ? { kind: "text", text: t } : empty);

/** The rows of *ex*'s table, from core/plan.js's planTable().plan. */
export function tableRows(ex, plan) {
  const p = plan;
  const widths = p.widths;
  const ncols = p.columns.length + p.filler;
  const fillerWidth = () => (p.filler ? widths[p.lead.length + p.columns.length] : 0);
  const cell = (widthCm, content, span = 1, style = NAMES.CELL_PARA) => ({ widthCm, span, style, content });

  function bodyRows(marker, body, first, k) {
    const rows = [];
    let headUsed = false;

    const leadCells = (active) => {
      const out = [cell(p.lead[0], active && first ? { kind: "number" } : empty)];
      let i = 1;
      if (p.hasMarker) {
        out.push(cell(p.lead[i], active ? text(marker) : empty));
        i += 1;
      }
      if (p.hasJudgment) {
        out.push(cell(p.lead[i], active ? text(body.judgment) : empty, 1, NAMES.JUDG_PARA));
      }
      return out;
    };
    const annotCell = (active) => (p.hasAnnot
      ? [cell(widths[widths.length - 1], active ? text(body.annot) : empty, 1, NAMES.ANNOT_PARA)]
      : []);
    const bodySpan = (content, style = NAMES.CELL_PARA) =>
      cell(sum(p.columns) + fillerWidth(), content, ncols, style);

    // One tier's cells for one band, padded to the grid by SPAN, each as
    // wide as the grid columns it covers (emit_docx._band_cells).
    const bandCells = (cells, [start, stop], style) => {
      const out = [];
      let covered = 0;
      for (let j = start; j < stop; j++) {
        const span = p.grid.span(k, j);
        out.push(cell(sum(p.columns.slice(covered, covered + span)),
          j < cells.length ? text(cells[j]) : empty, span, style));
        covered += span;
      }
      const remaining = p.columns.length + p.filler - covered;
      if (remaining > 0) out.push(cell(sum(p.columns.slice(covered)) + fillerWidth(), empty, remaining, style));
      return out;
    };

    if (body.tiers.length) {
      p.grid.bandsOf(k).forEach((band, b) => {
        body.tiers.forEach((tier, tr) => {
          // A continuation band's first row is marked: nothing else in the
          // finished table can say that a band, not a tier, begins here.
          const style = b && !tr ? NAMES.BAND_PARA : NAMES.CELL_PARA;
          rows.push([...leadCells(!headUsed), ...bandCells(tier, band, style), ...annotCell(!headUsed)]);
          headUsed = true;
        });
      });
    } else {
      rows.push([...leadCells(true), bodySpan(text(body.text)), ...annotCell(true)]);
      headUsed = true;
    }

    const trailer = [body.translation, body.source].filter(Boolean).join(" ");
    if (trailer) {
      rows.push([...leadCells(false), bodySpan(text(trailer), NAMES.TRANS_PARA), ...annotCell(false)]);
    }
    return rows;
  }

  let rows = [];
  p.bodies.forEach(([marker, body], k) => {
    rows = rows.concat(bodyRows(marker, body, k === 0, k));
  });
  // Spacer rows: the space around an example is a style's height, which a
  // user can change for the whole document from one place.
  const spacer = (style) => [cell(sum(widths), empty, widths.length, style)];
  return {
    widthCm: sum(widths),
    grid: widths,
    rows: [spacer(NAMES.SPACE_ABOVE), ...rows, spacer(NAMES.SPACE_BELOW)],
  };
}
