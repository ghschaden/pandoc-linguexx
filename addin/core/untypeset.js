// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * A built example back as the lines it was typed as -- the Writer
 * macro's LxReadTable, ported (trees aside: the add-ins draw none).
 *
 * It reads a table as rows of cells, each {style, text}: the paragraph
 * style's NAME and the cell's text as a tagged string (parse.js), the
 * example number's shown digits left out -- the number is carried by its
 * field's identity, not read as a word.  Each host reads its own table
 * into that shape; the reading of it is here, once.
 *
 * Nothing is inferred from what a cell happens to contain: which columns
 * lead is said by the judgment column or, failing that, by where the
 * translation's wide cell starts; where a band begins is said by the band
 * style; the space rows by theirs.  A first word that reads like "a."
 * would otherwise turn an example into a paradigm.
 */

import { NAMES } from "./constants.js";
import { strip, trimTagged } from "./parse.js";

const has = (row, style) => row.some((c) => c.style === style);

/**
 * An example, or a table somebody built?  Both the converter and every
 * add-in top and tail an example with a row that is only the space around
 * it, and nothing else makes a row like that -- LxIsExampleTable.
 */
export function isExampleTable(rows) {
  return rows.length >= 3 && has(rows[0], NAMES.SPACE_ABOVE) && has(rows[rows.length - 1], NAMES.SPACE_BELOW);
}

/**
 * How many cells come before the example's own text, and which are what --
 * LxLeadColumns.  Returns {lead, judgment, marker}; lead < 1 is unknown.
 */
export function leadColumns(rows) {
  let lead = -1;
  let judgment = false;
  for (const row of rows) {
    for (let i = 0; i < row.length; i++) {
      if (row[i].style === NAMES.JUDG_PARA) {
        judgment = true;
        lead = i + 1;
        break;
      } else if (row[i].style === NAMES.TRANS_PARA && lead < 0) {
        lead = i;
      }
    }
    if (judgment) break;
  }
  let marker = false;
  if (lead >= 1) marker = (judgment ? lead - 1 : lead) >= 2;
  return { lead, judgment, marker };
}

/**
 * One row's text: the cells from *lead* on, the annotation column aside.
 * A cell of several words in a row of many was a {braced group} and says
 * so again; the one wide cell of running text is not braced -- LxRowText.
 */
function rowText(row, lead, brace) {
  const cells = row.slice(lead).filter((c) => c.style !== NAMES.ANNOT_PARA);
  const out = [];
  for (const c of cells) {
    let text = trimTagged(c.text);
    const plain = strip(text);
    if (!plain) continue;
    if (brace && cells.length > 1 && plain.includes(" ")) text = `{${text}}`;
    out.push(text);
  }
  return out.join(" ");
}

/**
 * The lines of the example in *rows*: one per tier and per translation,
 * letter and judgment mark back at the head of their item's first line,
 * bands joined back onto the tiers they were split off, an annotation as
 * \exannot{...} at the end of its object line.  {lines} or {error}.
 */
export function readTable(rows) {
  const { lead, judgment, marker } = leadColumns(rows);
  if (lead < 1) {
    return {
      error: "That example does not say where its text begins.\n\n" +
        "It has neither a judgment column nor a translation, which are the two " +
        "things that give it away.  A converted document whose examples are never " +
        "judged can look like this; typeset one example by hand and this will read it.",
    };
  }

  const out = [];
  let base = 0;
  let tier = 0;
  let band0 = true;
  for (const row of rows) {
    if (!row.length) continue;
    if (has(row, NAMES.SPACE_ABOVE) || has(row, NAMES.SPACE_BELOW)) continue;
    if (has(row, NAMES.TRANS_PARA)) {
      const line = rowText(row, lead, false);
      if (strip(line)) out.push(line);
      continue;
    }
    const mark = marker ? strip(row[1]?.text || "").trim() : "";
    const judg = judgment ? strip(row[lead - 1]?.text || "").trim() : "";
    const start = out.length === 0 || mark.length > 0;
    if (start) {
      base = out.length;
      tier = 0;
      band0 = true;
    } else if (has(row, NAMES.BAND_PARA)) {
      tier = 0;
      band0 = false;            // a band, not another tier
    }

    let line = rowText(row, lead, true);
    if (start) line = (mark ? `${mark} ` : "") + judg + line;
    const annot = row.find((c) => c.style === NAMES.ANNOT_PARA);
    if (annot && strip(annot.text).trim()) line = `${strip(line)}\\exannot{${strip(annot.text).trim()}}`;

    if (band0) {
      out.push(line);
    } else if (strip(line)) {
      // this band's share of a tier already written goes on the end of it
      const n = base + tier;
      if (n < out.length) out[n] = `${out[n]} ${line}`;
      else out.push(line);      // more tiers than the first band had: keep it
    }
    tier += 1;
  }
  const lines = out.map(trimTagged).filter((l) => strip(l).length > 0);
  if (!lines.length) return { error: "There is nothing in that example to give back." };
  return { lines };
}
