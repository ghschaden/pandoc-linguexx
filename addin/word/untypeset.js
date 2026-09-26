// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * A built example back as typed lines, for Word -- LxUntypesetCommand's
 * work, the reading shared with every host (core/untypeset.js).
 *
 * The lines come back as paragraphs, the number at the head of the first:
 * the SAME field -- its bookmark's name, its shown value -- then a tab, as
 * the macro writes it (LxWriteLines).  Typesetting those lines again takes
 * that number over (selection.js), so an example can be changed without
 * breaking a single reference to it.
 */

import { NAMES } from "../core/constants.js";
import { isExampleTable, readTable } from "../core/untypeset.js";
import { flatPackage, run, runs, sequenceField } from "./ooxml.js";
import { readExampleTable } from "./selection.js";

/**
 * {pkg, lines, number} for the table in *tableOoxml*, or {refusal}.  *id*
 * is the bookmark id to write, which must be free in the document.
 */
export function untypesetPackage(tableOoxml, id = 1) {
  const t = readExampleTable(tableOoxml);
  if (t.refusal) return { refusal: t.refusal };
  if (!isExampleTable(t.rows)) {
    return {
      refusal: "That table is not an example.\n\nAn example is topped and tailed by the " +
        "spacer rows that carry the space around it, and this one is not -- so taking it " +
        "apart would be taking apart a table you built yourself.",
    };
  }
  // Word joins adjacent tables (S6 fact 3), so in a converted document one
  // table can hold several examples.  Reading it as one would give back all
  // of them as a single example -- and the Replace would take them all out.
  const examples = t.rows.filter((row) => row.some((c) => c.style === NAMES.SPACE_ABOVE)).length;
  if (examples > 1) {
    return {
      refusal: `This table holds ${examples} examples: Word joins tables that touch, and ` +
        "these were written one after another with nothing between them. Untypesetting " +
        "one of them is not something this version can do; putting an empty paragraph " +
        "between examples in the source document keeps them apart.",
    };
  }
  const got = readTable(t.rows);
  if (got.error) return { refusal: got.error };
  const paragraphs = got.lines.map((line, i) => {
    let head = "";
    if (i === 0 && t.number) {
      head = run("(") + sequenceField({ id, name: t.number.bookmark, cached: t.number.shown }) +
        run(")") + "<w:r><w:tab/></w:r>";
    }
    return `<w:p>${head}${runs(line, t.formats)}</w:p>`;
  });
  return { pkg: flatPackage(paragraphs.join("")), lines: got.lines, number: t.number, formats: t.formats };
}
