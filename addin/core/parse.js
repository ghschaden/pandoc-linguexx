// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * Typed lines -> items: the Writer macro's grammar (LinguExx.bas,
 * LxParseItems and the pieces under it), ported.
 *
 * The macro is the reference, not the inspiration.  Its own parse of every
 * case in tests/fixtures/typed-examples.json is recorded there as "parsed",
 * and test/parse.test.js holds this module to it.  Where a function here
 * looks odd, the Basic it mirrors looks the same; the comments say why the
 * Basic is that way, and the "why" of each fixture says what broke before.
 *
 * Formatting rides along as it does in the macro: a line is a *tagged*
 * string, with a private-use character (U+E000 + n) in front of every run
 * of like-formatted text and again after every space, so each word knows
 * its own format through splitting and banding.  The host reads the
 * selection into such strings (see tagRun) and keeps the formats
 * themselves, indexed by n, out of the string.
 */

/** U+E000, the private use area: nothing a linguist types collides. */
export const FMT_BASE = 0xe000;
export const FMT_MAX = 250;

/** Characters a judgment mark is made of. */
export const JUDG_CHARS = "*?#%!";

/** Characters a free translation may open with -- LxQuotes. */
export const QUOTES = "'\"`«‘’‚“„‹";

/** The format a mark stands for, or -1 for an ordinary character. */
export function tagIndex(c) {
  if (c === undefined || c.length !== 1) return -1;
  const n = c.charCodeAt(0) - FMT_BASE;
  return n >= 0 && n < FMT_MAX ? n : -1;
}

export function tag(n) {
  return n < 0 ? "" : String.fromCharCode(FMT_BASE + n);
}

/**
 * A space, for splitting words: not only the ASCII two.  Writer's French
 * autocorrect puts a (narrow) no-break space before ?!;: behind the
 * linguist's back, and "c. ?Probably" must still split -- LxIsSpace.
 */
export function isSpace(c) {
  if (c === " " || c === "\t") return true;
  if (c === undefined || c.length !== 1) return false;
  const n = c.charCodeAt(0);
  return n === 160 || (n >= 8192 && n <= 8202) || n === 8239 || n === 8287 || n === 12288;
}

/** Mark *s* with format n, again after every space -- LxTagged. */
export function tagRun(s, n) {
  const t = tag(n);
  if (!t) return s;
  let out = t;
  let space = false;
  for (const c of s) {
    if (isSpace(c)) {
      out += c;
      space = true;
    } else {
      if (space) out += t;
      out += c;
      space = false;
    }
  }
  return out;
}

/** The text without its marks -- LxStrip. */
export function strip(s) {
  let out = "";
  for (let i = 0; i < s.length; i++) if (tagIndex(s[i]) < 0) out += s[i];
  return out;
}

/** Trim, keeping the mark the first surviving character is under -- LxTrimTagged. */
export function trimTagged(s) {
  let n = s.length;
  while (n > 0 && isSpace(s[n - 1])) n--;
  let i = 0;
  let t = "";
  while (i < n) {
    const c = s[i];
    if (tagIndex(c) >= 0) t = c;
    else if (!isSpace(c)) break;
    i++;
  }
  return i >= n ? "" : t + s.slice(i, n);
}

function lastTag(s) {
  for (let i = s.length - 1; i >= 0; i--) if (tagIndex(s[i]) >= 0) return s[i];
  return "";
}

/** Give text cut from mid-line back the mark in force where it was cut -- LxCarryTag. */
export function carryTag(from, s) {
  if (s.length === 0) return s;
  if (tagIndex(s[0]) >= 0) return s;
  const t = lastTag(from);
  return t ? t + s : s;
}

/**
 * Is this token a sub-example marker -- "a.", "(b)", "iii."?  Narrow on
 * purpose: "Dr." and "no." are words -- LxIsMarker.
 */
export function isMarker(word) {
  let s = strip(word);
  if (s.length < 2 || s.length > 6) return false;
  const c = s[s.length - 1];
  if (c !== "." && c !== ")") return false;
  s = s.slice(0, -1);
  if (s[0] === "(") s = s.slice(1);
  if (s.length === 0) return false;
  if (s.length === 1) {
    const l = s.toLowerCase();
    return l >= "a" && l <= "z";
  }
  for (const ch of s) if (!"ivxlcdm".includes(ch.toLowerCase())) return false;
  return true;
}

/**
 * The marker this line opens with, as a literal prefix of it, or "".  The
 * head of the first word counts when a judgment mark follows at once --
 * "b.?Maybe" -- and nothing else may follow -- LxMarkerOf.
 */
export function markerOf(line) {
  const words = splitWords(line);
  if (words.length === 0) return "";
  const word = words[0];
  for (let i = 0; i < word.length; i++) {
    const c = word[i];
    if (c === "." || c === ")") {
      const head = word.slice(0, i + 1);
      const rest = word.slice(i + 1);
      if (rest.length > 0 && !JUDG_CHARS.includes(rest[0])) return "";
      return isMarker(head) ? head : "";
    }
  }
  return "";
}

export function looksLikeMarker(line) {
  return markerOf(line).length > 0;
}

/** Does this line open like a free translation?  The quote is the signal. */
export function isTranslation(s) {
  const c = strip(s).replace(/^ +| +$/g, "").slice(0, 1);
  return c.length > 0 && QUOTES.includes(c);
}

/** Drop marks dangling at the end of a word -- LxTrimTags. */
function trimTags(s) {
  let n = s.length;
  while (n > 0 && tagIndex(s[n - 1]) >= 0) n--;
  return s.slice(0, n);
}

/**
 * Whitespace splits words, except inside {braces}, which are not kept.  The
 * last mark seen opens the next word -- LxSplitWords.
 */
export function splitWords(line) {
  const out = [];
  let cur = "";
  let depth = 0;
  let t = "";
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (tagIndex(c) >= 0) {
      t = c;
      if (cur.length > 0) cur += c;
    } else if (c === "{") {
      depth++;
    } else if (c === "}") {
      if (depth > 0) depth--;
    } else if (isSpace(c) && depth === 0) {
      if (cur.length > 0) {
        out.push(trimTags(cur));
        cur = "";
      }
    } else {
      if (cur.length === 0) cur = t;
      cur += c;
    }
  }
  if (cur.length > 0) out.push(trimTags(cur));
  return out;
}

/** [rest of the word, the mark] -- LxPullJudgment. */
export function pullJudgment(word) {
  let mark = "";
  let t = "";
  let i = 0;
  while (i < word.length) {
    const c = word[i];
    if (tagIndex(c) >= 0) t = c;
    else if (!JUDG_CHARS.includes(c)) break;
    else mark += c;
    i++;
  }
  return [carryTag(t, word.slice(i)), mark];
}

/**
 * [line without it, label]: \exannot{...} taken off a line -- LxPullAnnot.
 * Like the Basic, a line that had one comes back without its marks.
 */
export function pullAnnot(line) {
  // Case-blind, as the Basic is: LibreOffice's InStr compares as text by
  // default, so the macro takes "\EXANNOT{..}" too.
  const found = /\\exannot/i.exec(line);
  if (!found) return [line, ""];
  const at = found.index;
  let i = at + "\\exannot".length;
  if (line[i] === "[") {
    while (i < line.length && line[i] !== "]") i++;
    i++;
  }
  if (line[i] !== "{") return [line, ""];
  const open = i;
  let depth = 0;
  while (i < line.length) {
    const c = line[i];
    if (c === "{") depth++;
    if (c === "}") {
      depth--;
      if (depth === 0) break;
    }
    i++;
  }
  if (depth !== 0) return [line, ""];
  return [strip(line.slice(0, at) + line.slice(i + 1)), line.slice(open + 1, i)];
}

/**
 * One item from its own lines -- LxMakeItem.  A quoted last line is the
 * translation whenever there is more than one line, which leaves a
 * one-line item unglossed.  Tiers are word arrays; one tier = unglossed.
 */
export function makeItem(marker, body) {
  let lines = body.slice();
  let translation = "";
  if (lines.length > 1 && isTranslation(lines[lines.length - 1])) {
    translation = lines[lines.length - 1];
    lines = lines.slice(0, -1);
  }

  let annot = "";
  if (lines.length > 0) [lines[0], annot] = pullAnnot(lines[0]);

  const tiers = lines.map(splitWords);

  // A judgment mark leads the object line and goes to its own column,
  // never glued to the first word, or a judged item no longer lines up.
  let judgment = "";
  if (tiers.length > 0 && tiers[0].length > 0) {
    const [first, mark] = pullJudgment(tiers[0][0]);
    judgment = mark;
    if (mark.length > 0) {
      if (first.length > 0) tiers[0] = [first, ...tiers[0].slice(1)];
      else tiers[0] = tiers[0].slice(1); // the mark stood alone
    }
  }
  return { marker, judgment, translation, annot, tiers };
}

/**
 * Split a selection's lines into items -- LxParseItems.  A line opening
 * with a marker starts an item; the marker may stand alone or lead the
 * object language.  Returns {items} or {error}, with the macro's words.
 *
 * *lines* get what LxSelectedLines gives a selection first: trimmed, and
 * blank ones dropped.
 */
export function parseLines(rawLines) {
  const lines = rawLines.map(trimTagged).filter((l) => l.length > 0);
  if (lines.length === 0) return { error: "no lines" };

  if (!lines.some(looksLikeMarker)) return { items: [makeItem("", lines)] };

  if (!looksLikeMarker(lines[0])) {
    return {
      error:
        "A sub-example letter appears part-way through the selection, " +
        "but the selection does not start with one.\n\n" +
        "Start at the first sub-example, or leave the letters out " +
        "and gloss one example at a time.",
    };
  }

  const items = [];
  let body = [];
  let marker = "";
  for (const raw of lines) {
    if (looksLikeMarker(raw)) {
      if (body.length > 0) items.push(makeItem(marker, body));
      const line = trimTagged(raw);
      marker = markerOf(line);
      const rest = carryTag(marker, trimTagged(line.slice(marker.length)));
      body = rest.length > 0 ? [rest] : [];
    } else {
      body.push(raw);
    }
  }
  if (body.length > 0) items.push(makeItem(marker, body));

  if (items.length === 0) {
    return { error: "Every selected line is a sub-example letter with nothing after it." };
  }
  return { items };
}
