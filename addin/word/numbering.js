// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * Numbers for a host that never renumbers -- plan-addins.md, Phase 2,
 * "Numbering without recalculation".
 *
 * Word on the web does not recalculate a field and refuses to let an
 * add-in write one (S6 facts 4 and 5).  So the add-in computes: the number
 * an inserted example gets is the count of example numbers ahead of it,
 * plus one, written into its cache; a reference is cached at the number
 * of the example its bookmark wraps.  What goes stale behind an insertion
 * is found by comparing the numbers shown with the numbers computed, and
 * reported -- never claimed correct unchecked.
 *
 * Pure functions over what Office.js reports (field codes, shown results,
 * bookmark names), so all of it is tested without Word.
 */

import { NAMES } from "../core/constants.js";

const SEQ = new RegExp(`^\\s*SEQ\\s+${NAMES.SEQ_NAME}\\b`, "i");
const REF = /^\s*REF\s+(\S+)/i;

export function isExampleNumber(code) {
  return SEQ.test(code);
}

/** The bookmark a REF field points at, or null. */
export function refTarget(code) {
  const m = REF.exec(code);
  return m ? m[1] : null;
}

/** The number an example inserted after *codesBefore* (field codes, in order) gets. */
export function numberAt(codesBefore) {
  return codesBefore.filter(isExampleNumber).length + 1;
}

/**
 * A bookmark name nobody in the document uses yet.  Word's rules: a
 * letter first, then letters, digits and underscores, at most 40 long.
 * Not "_"-prefixed, which Word hides from its Bookmark dialog, because a
 * user inserting a cross-reference by hand should be able to find it.
 */
export function freshBookmark(existing, now = Date.now()) {
  const taken = new Set(existing);
  const stem = `LxEx${now.toString(36)}`;
  for (let n = 0; ; n++) {
    const name = n ? `${stem}_${n}` : stem;
    if (!taken.has(name)) return name.slice(0, 40);
  }
}

/**
 * The numbering as it should be.  *fields* is every field in document
 * order as {code, shown, bookmarks}, bookmarks being those round the field.
 * Returns {numbers: bookmark -> number, stale: [...]}, stale listing every
 * example number and every reference whose shown value is not what it
 * should be, with what it should be.
 */
export function audit(fields) {
  const numbers = {};
  const stale = [];
  let n = 0;
  for (const f of fields) {
    if (!isExampleNumber(f.code)) continue;
    n += 1;
    for (const b of f.bookmarks || []) numbers[b] = n;
    if (String(f.shown).trim() !== String(n)) stale.push({ kind: "number", shown: f.shown, want: n });
  }
  for (const f of fields) {
    const target = refTarget(f.code);
    if (target === null || !(target in numbers)) continue;
    if (String(f.shown).trim() !== String(numbers[target])) {
      stale.push({ kind: "reference", target, shown: f.shown, want: numbers[target] });
    }
  }
  return { numbers, stale };
}

/**
 * What to tell a user about *stale*, or "" when nothing is.  The pairs are
 * listed only while there are few: in a real document an insertion near
 * the top leaves dozens, and a paragraph of "1 should be 2, 1 should be 3,
 * ..." -- which is what the first live test showed -- says less than a
 * count does.
 */
export function staleMessage(stale, listUpTo = 3) {
  if (!stale.length) return "";
  const numbers = stale.filter((s) => s.kind === "number");
  const refs = stale.filter((s) => s.kind === "reference");
  const describe = (items, one, many) => {
    const head = `${items.length} ${items.length > 1 ? many : one}`;
    if (items.length > listUpTo) return head;
    return `${head} (${items.map((s) => `${s.shown} should be ${s.want}`).join(", ")})`;
  };
  const parts = [];
  if (numbers.length) parts.push(describe(numbers, "example number", "example numbers"));
  if (refs.length) parts.push(describe(refs, "cross-reference", "cross-references"));
  return `${parts.join(" and ")} still show their old value. ` +
    "They are live fields and renumber when fields are updated: " +
    "in Word for the desktop, Ctrl+A then F9; LibreOffice does it on opening. " +
    "Word on the web does not update fields.";
}
