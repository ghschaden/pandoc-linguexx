// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * Bracket notation -> a laid-out tree: the Writer macro's tree reader,
 * movement lines, layout and arrow lanes (LinguExx.bas, LxTreeParse and
 * everything under it), ported -- and the shapes it draws, as geometry
 * with no host in it.
 *
 * The macro is the reference, as it is for the parse.  Its own reading
 * and layout of every case in tests/fixtures/trees.json is recorded there
 * as "laid_out" (TreeLayoutQuiet, with the label widths handed in), and
 * test/tree.test.js holds this module to it with no tolerance: the
 * arithmetic is the Basic's, in the Basic's order.
 *
 * Lengths are in 1/100 mm, the unit the macro lays out in.  A host
 * converts once, at the end (Word and OnlyOffice both want EMUs: 360 to
 * the unit).
 *
 * A node is {label, name, roof, kid, sib, depth, w, x}: first child and
 * next sibling by index, -1 for none, as the Basic keeps them.  Labels are
 * tagged strings, as lines are in parse.js; a label's formatting rides in
 * front of it.
 */

import { LAYOUT } from "./constants.js";
import { advancesFor, runsWidthCm } from "./measure.js";
import { carryTag, isSpace, isTranslation, lastTag, parseLines, pullJudgment, strip, tagIndex, trimTagged, trimTags } from "./parse.js";
import { runsOf } from "./plan.js";

/** The macro's Const declarations; tests/test_addin_core.py holds them to it. */
export const TREE = Object.freeze({
  TREE_MAX: 300, //       nodes in one tree
  TREE_DEPTH: 40, //      tiers in one tree
  NODE_PAD_CM: 0.06, //   slack each side of a label
  NODE_GAP_CM: 0.22, //   least space between subtrees
  TIER_FACTOR: 2.0, //    tier spacing / line height
  BRANCH_WIDTH: 8, //     branch thickness, 1/100 mm
  ARROW_MAX: 40,
  GUTTER_GAP_CM: 0.30, // from the deepest node to lane 0
  LANE_STEP_CM: 0.34, //  from one lane to the next
  HEAD_LEN_CM: 0.18,
  HEAD_HALF_CM: 0.07,
});

/** What a tree drawing is called, so that it can be told from a picture -- TREE_TITLE. */
export const TREE_TITLE = "LinguExx tree";

// Basic's Trim takes spaces only, not tabs or the wider set isSpace knows.
const trim = (s) => s.replace(/^ +| +$/g, "");

// ------------------------------------------------------------- movement ---

/** Is this a "move a -> b" line -- LxIsMoveLine. */
export function isMoveLine(line) {
  const s = trim(strip(line)).toLowerCase();
  return s.startsWith("move ") || s.startsWith("move\t");
}

/**
 * [source, move lines, error]: the tree's lines joined, the move lines set
 * aside -- LxSplitMoves.  A tree is one expression however many lines it
 * was typed over.
 */
export function splitMoves(lines) {
  const moves = [];
  let s = "";
  for (const line of lines) {
    if (isMoveLine(line)) {
      if (moves.length > TREE.ARROW_MAX) return ["", moves, "That is more movement arrows than this can draw."];
      moves.push(strip(line));
    } else {
      if (s.length > 0) s += " ";
      s += line;
    }
  }
  const error = trim(s).length === 0 && moves.length > 0 ? "There are movement lines but no tree above them." : "";
  return [s, moves, error];
}

// -------------------------------------------------------------- parsing ---

class Reader {
  constructor(src) {
    this.src = src;
    this.pos = 0;
    this.err = "";
    this.tag = ""; // the format mark in force
    this.nodes = [];
  }

  newNode() {
    if (this.nodes.length > TREE.TREE_MAX) {
      this.err = "That tree has more nodes than this can draw.";
      return -1;
    }
    this.nodes.push({ label: "", name: "", roof: false, kid: -1, sib: -1, depth: 0, w: 0, x: 0 });
    return this.nodes.length - 1;
  }

  // Whitespace, and the marks in front of the next label, which are
  // remembered: they are what that label is written in -- LxTSkip.
  skip() {
    while (this.pos < this.src.length) {
      const c = this.src[this.pos];
      if (tagIndex(c) >= 0) this.tag = c;
      else if (!isSpace(c)) break;
      this.pos++;
    }
  }

  // The label wears the mark in force where it began; the one it ends on
  // is kept for the next label and trimmed off this one -- LxTCarry.
  carry(s) {
    const was = this.tag;
    const last = lastTag(s);
    if (last) this.tag = last;
    return carryTag(was, trimTags(s));
  }

  // A label: bare, or {braced} so that it may hold spaces -- LxTToken.
  token() {
    if (this.pos >= this.src.length) return "";
    if (this.src[this.pos] === "{") {
      let depth = 0;
      const start = this.pos + 1;
      while (this.pos < this.src.length) {
        const c = this.src[this.pos];
        if (c === "{") depth++;
        else if (c === "}") {
          depth--;
          if (depth === 0) {
            const s = this.src.slice(start, this.pos);
            this.pos++;
            return this.carry(s);
          }
        }
        this.pos++;
      }
      this.err = "A { is never closed.";
      return "";
    }
    const start = this.pos;
    while (this.pos < this.src.length) {
      const c = this.src[this.pos];
      if ("[]{}".includes(c) || isSpace(c)) break;
      this.pos++;
    }
    return this.carry(this.src.slice(start, this.pos));
  }

  // forest's node options, after a comma: only roof and name= -- LxTOptions.
  options(n) {
    const label = this.nodes[n].label;
    const p = label.indexOf(",");
    if (p < 0) return;
    const head = label.slice(0, p);
    let rest = label.slice(p + 1);
    do {
      let opt;
      const q = rest.indexOf(",");
      if (q >= 0) {
        opt = rest.slice(0, q);
        rest = rest.slice(q + 1);
      } else {
        opt = rest;
        rest = "";
      }
      opt = trim(strip(opt));
      const key = opt.toLowerCase();
      if (key === "roof") this.nodes[n].roof = true;
      else if (key.startsWith("name=")) this.nodes[n].name = trim(opt.slice(5)); // keeps its case
      else if (opt.length > 0) {
        this.err = `This does not know the node option "${opt}".  Only "roof" and "name=..." are supported.`;
        return;
      }
    } while (rest.length > 0);
    this.nodes[n].label = trimTagged(head);
  }

  // One bracketed node and everything in it -- LxTNode.
  node() {
    const n = this.newNode();
    if (n < 0) return -1;
    this.pos++; // the '['
    this.skip();
    this.nodes[n].label = this.token();

    let prev = -1;
    for (;;) {
      this.skip();
      if (this.pos >= this.src.length) {
        this.err = "A bracket is never closed.";
        return -1;
      }
      const c = this.src[this.pos];
      if (c === "]") {
        this.pos++;
        break;
      }
      let kid;
      if (c === "[") kid = this.node();
      else { // a bare word is a leaf
        kid = this.newNode();
        if (kid >= 0) {
          this.nodes[kid].label = this.token();
          this.options(kid); // ", roof" lives on leaves too
        }
      }
      if (kid < 0 || this.err.length > 0) return -1;
      if (prev < 0) this.nodes[n].kid = kid;
      else this.nodes[prev].sib = kid;
      prev = kid;
    }
    this.options(n);
    return this.err.length > 0 ? -1 : n;
  }
}

/**
 * The tree in *src*, one expression -- LxTreeParse.  {nodes, root} or
 * {error}, with the macro's words.  Root is node 0.
 */
export function parseTree(src) {
  // Refused by name, not dropped in silence: a tree that quietly lost its
  // movement arrows looks finished and is not.
  if (strip(src).includes("\\")) {
    return {
      error: "This does not read LaTeX (anything with a backslash).\n\n" +
        "For movement, name the two nodes and put a move line under the tree:\n" +
        "    [CP [DP,name=wh what] [TP [V saw] [DP,name=t __]]]\n    move t -> wh",
    };
  }
  const r = new Reader(src);
  r.skip();
  if (r.pos >= src.length || src[r.pos] !== "[") {
    return { error: "A tree has to start with a bracket, like [DP [D the] [NP [N tree]]]." };
  }
  const root = r.node();
  if (r.err.length > 0) return { error: r.err };
  r.skip();
  if (r.pos < src.length) {
    return { error: `The tree ends before the selection does; there is still "${strip(src.slice(r.pos))}" after it.` };
  }
  return { nodes: r.nodes, root };
}

/** The node named *name*, or -1 -- LxNodeNamed. */
function nodeNamed(nodes, name) {
  if (name.length === 0) return -1;
  return nodes.findIndex((n) => n.name === name);
}

/** The move lines as node pairs, now that the nodes exist -- LxResolveMoves. */
export function resolveMoves(nodes, moves) {
  const arrows = [];
  for (const line of moves) {
    // trimTagged, not the spaces-only trim: after "move<TAB>" a name is
    // still a name.  The line has no marks left, so this trims whitespace.
    let s = trimTagged(trimTagged(line).slice(4)); // drop the leading "move"
    const p = s.indexOf("->");
    if (p < 0) {
      return { error: `A movement line reads "move <from> -> <to>"; this one has no arrow:\n\n    ${trim(line)}` };
    }
    const from = trimTagged(s.slice(0, p));
    const to = trimTagged(s.slice(p + 2));
    const a = { from: nodeNamed(nodes, from), to: nodeNamed(nodes, to), lane: -1 };
    if (a.from < 0 || a.to < 0) {
      s = a.from < 0 ? from : to;
      return {
        error: `No node is named "${s}".\n\nName one by adding ", name=${s}" inside its ` +
          `brackets, as in [DP,name=${s} what].`,
      };
    }
    if (a.from === a.to) return { error: `A movement line points "${from}" at itself.` };
    arrows.push(a);
  }
  return { arrows };
}

/**
 * One tree's lines -> {judgment, nodes, arrows, source} or {error}: what the
 * macro's tree commands do before anything is drawn (LxBareTreeCommand,
 * TreeLayoutQuiet).  *source* is what the drawing keeps as its alt text.
 */
export function readTree(lines) {
  const [joined, moves, splitError] = splitMoves(lines);
  if (splitError) return { error: splitError };
  const [src, judgment] = pullJudgment(joined);
  const parsed = parseTree(src);
  if (parsed.error) return { error: parsed.error };
  const resolved = resolveMoves(parsed.nodes, moves);
  if (resolved.error) return { error: resolved.error };
  return { judgment, nodes: parsed.nodes, arrows: resolved.arrows, source: treeSource(lines) };
}

/**
 * The alt text a drawing carries: the lines as typed, without their
 * formatting -- LxTreeSource.  Untypeset gives the tree back from it.
 */
export function treeSource(lines) {
  return lines.map(strip).join("\n");
}

/**
 * One item of a numbered tree -- LxMakeItem under LxTreeOnly.  A tree is
 * an item like any other: its own letter, judgment mark and translation,
 * one row, one merged cell; only what goes in the cell differs.  The item
 * keeps the lines it was made from (*tree*): the tree is read again when
 * it is drawn, as the macro reads it again in LxWideCellTree.
 *
 * Where the move lines go wrong, the Basic's LxTreeParse clears the
 * message LxSplitMoves left, so here the tree reader has the last word --
 * kept, being what the macro says.
 */
export function makeTreeItem(marker, body) {
  let lines = body.slice();
  let translation = "";
  if (lines.length > 1 && isTranslation(lines[lines.length - 1])) {
    translation = lines[lines.length - 1];
    lines = lines.slice(0, -1);
  }
  const [joined, moves] = splitMoves(lines);
  const [src, judgment] = pullJudgment(joined);
  const parsed = parseTree(src);
  if (parsed.error) {
    if (marker.length === 0) return { error: parsed.error };
    // Say which item: in a paradigm "a tree has to start with a bracket"
    // on its own leaves the reader counting brackets.
    return {
      error: `Sub-example ${strip(marker)} is not a tree.\n\n${parsed.error}\n\n` +
        "Every item of a numbered tree is a tree.  To put a tree beside a glossed example, make them two examples.",
    };
  }
  const resolved = resolveMoves(parsed.nodes, moves);
  if (resolved.error) return { error: resolved.error };
  return { marker, judgment, translation, annot: "", tiers: [], tree: lines };
}

/** A selection's lines as a numbered tree's items -- the tree command's parse. */
export function parseTreeLines(rawLines) {
  return parseLines(rawLines, makeTreeItem);
}

// --------------------------------------------------------------- layout ---

/**
 * Every parent centred over its children and no two subtrees overlapping
 * -- LxTreeLayout.  *measure(label)* is a label's width in 1/100 mm (never
 * asked of an empty one).  Sets each node's w and x and each arrow's
 * lane; returns "" or the macro's refusal.
 *
 * Not Reingold-Tilford: one leftmost-free x per tier, bottom-up placement,
 * and a whole subtree shifted right when its parent would collide.
 */
export function layoutTree(tree, measure) {
  const { nodes, arrows } = tree;
  const pad = TREE.NODE_PAD_CM * 1000;
  const gap = TREE.NODE_GAP_CM * 1000;
  const free = new Array(TREE.TREE_DEPTH + 1).fill(0);
  const kids = function* (n) {
    for (let k = nodes[n].kid; k >= 0; k = nodes[k].sib) yield k;
  };

  const depth = (n, d) => {
    if (d > TREE.TREE_DEPTH) return false;
    nodes[n].depth = d;
    for (const k of kids(n)) if (!depth(k, d + 1)) return false;
    return true;
  };
  const shift = (n, dx) => {
    nodes[n].x = nodes[n].x + dx;
    for (const k of kids(n)) shift(k, dx);
  };
  const claim = (n) => {
    const d = nodes[n].x + nodes[n].w / 2 + gap;
    if (d > free[nodes[n].depth]) free[nodes[n].depth] = d;
    for (const k of kids(n)) claim(k);
  };
  const place = (n) => {
    const node = nodes[n];
    node.w = (strip(node.label).length === 0 ? 0 : measure(node.label)) + pad;
    if (node.kid < 0) {
      node.x = free[node.depth] + node.w / 2;
    } else {
      let last = -1;
      for (const k of kids(n)) {
        place(k);
        last = k;
      }
      let want = (nodes[node.kid].x + nodes[last].x) / 2;
      const floor = free[node.depth] + node.w / 2;
      if (want < floor) { // the parent will not fit there
        shift(n, floor - want);
        want = floor;
      }
      node.x = want;
    }
    claim(n);
  };
  const minLeft = (n) => {
    let d = nodes[n].x - nodes[n].w / 2;
    for (const k of kids(n)) d = Math.min(d, minLeft(k));
    return d;
  };

  if (!depth(0, 0)) return "That tree is nested deeper than this can draw.";
  place(0);
  // Start the tree at x = 0.  Kept because the Basic has it, but it never
  // moves anything: a node only ever moves right, as far as its tier's free
  // edge, and the first node on a tier finds that edge at 0 -- so some
  // node always ends with its left edge there.  (Mutation testing found it:
  // deleting these two lines fails nothing, and no fixture can make it.)
  const left = minLeft(0);
  if (left !== 0) shift(0, -left);
  arrowLanes(nodes, arrows);
  return "";
}

/**
 * Which lane each arrow runs in -- LxArrowLanes.  Greedy colouring of an
 * interval graph, narrowest span first, so that a movement nested inside
 * another sits above it, as it is drawn by hand.
 */
function arrowLanes(nodes, arrows) {
  const lo = (a) => Math.min(nodes[a.from].x, nodes[a.to].x);
  const hi = (a) => Math.max(nodes[a.from].x, nodes[a.to].x);
  const span = (a) => hi(a) - lo(a);
  const overlap = (a, b) => lo(a) <= hi(b) && lo(b) <= hi(a);

  const order = arrows.map((_, i) => i);
  for (let i = 1; i < order.length; i++) { // insertion sort by span
    const t = order[i];
    let j = i - 1;
    while (j >= 0 && !(span(arrows[order[j]]) <= span(arrows[t]))) {
      order[j + 1] = order[j];
      j--;
    }
    order[j + 1] = t;
  }
  for (const a of arrows) a.lane = -1;
  for (let i = 0; i < order.length; i++) {
    let k = 0;
    while (order.slice(0, i).some((m) => arrows[m].lane === k && overlap(arrows[order[i]], arrows[m]))) k++;
    arrows[order[i]].lane = k;
  }
}

/** The tree's width, 1/100 mm -- LxTreeWidth from the root. */
export function treeWidth(nodes) {
  return nodes.reduce((d, n) => Math.max(d, n.x + n.w / 2), 0);
}

// --------------------------------------------------------------- shapes ---

/**
 * What the macro draws for a laid-out tree, as geometry (LxTreeShapes,
 * LxTEmitNode, LxTRoof, LxTEmitArrows, LxTArrow), in 1/100 mm from the
 * tree's top left, y downwards.  *lineH* is a label's height; tiers are
 * TIER_FACTOR of it apart.
 *
 *   labels  [{node, text, x, y, w, h}]   a box per non-empty label, the
 *                                        text centred in it (tagged)
 *   lines   [[x0, y0, x1, y1]]           a branch per parent and child
 *   roofs   [[[x, y] x3]]                a triangle over a roofed child
 *   arrows  [[[x, y] x4]]                a movement's routed polyline
 *   heads   [[[x, y] x3]]                its filled head, apex up
 *
 * plus the bounding {width, height}.
 */
export function treeShapes(tree, lineH) {
  const { nodes, arrows } = tree;
  const tier = lineH * TREE.TIER_FACTOR;
  const out = { labels: [], lines: [], roofs: [], arrows: [], heads: [] };

  nodes.forEach((n, i) => {
    const y = n.depth * tier;
    if (strip(n.label).length > 0) out.labels.push({ node: i, text: n.label, x: n.x - n.w / 2, y, w: n.w, h: lineH });
    const bottom = y + lineH;
    for (let k = n.kid; k >= 0; k = nodes[k].sib) {
      const kid = nodes[k];
      const top = kid.depth * tier;
      if (kid.roof) {
        out.roofs.push([[n.x, bottom], [kid.x - kid.w / 2, top], [kid.x + kid.w / 2, top]]);
      } else {
        out.lines.push([n.x, bottom, kid.x, top]);
      }
    }
  });

  if (arrows.length > 0) {
    // The underside of everything a node dominates: an arrow leaves and
    // arrives there, where nothing is in its way -- LxSubtreeBottom.
    const under = (i) => {
      let d = nodes[i].depth * tier + lineH;
      for (let k = nodes[i].kid; k >= 0; k = nodes[k].sib) d = Math.max(d, under(k));
      return d;
    };
    const deep = nodes.reduce((d, n) => Math.max(d, n.depth * tier + lineH), 0);
    const head = TREE.HEAD_LEN_CM * 1000;
    const half = TREE.HEAD_HALF_CM * 1000;
    for (const a of arrows) {
      const lane = deep + TREE.GUTTER_GAP_CM * 1000 + a.lane * TREE.LANE_STEP_CM * 1000;
      const [x0, y0, x1, y1] = [nodes[a.from].x, under(a.from), nodes[a.to].x, under(a.to)];
      out.arrows.push([[x0, y0], [x0, lane], [x1, lane], [x1, y1 + head]]);
      out.heads.push([[x1, y1], [x1 - half, y1 + head], [x1 + half, y1 + head]]);
    }
  }

  const xs = [...out.labels.flatMap((l) => [l.x, l.x + l.w]), ...out.roofs.flat().map((p) => p[0]),
    ...out.heads.flat().map((p) => p[0])];
  const ys = [...out.labels.map((l) => l.y + l.h), ...out.arrows.flat().map((p) => p[1])];
  out.width = Math.max(0, ...xs);
  out.height = Math.max(0, ...ys);
  // Room under the lowest arrow, as much as the gutter leaves above it.
  // Without it the arrow's run under the tree is the drawing's bottom edge,
  // which in a table is the next row's top: OnlyOffice Desktop painted the
  // row below over it and the arrow lost its bottom (seen live, 2026-09-26).
  // The Writer macro's group ends at the lane; Writer does not clip it.
  if (out.arrows.length) out.height += TREE.GUTTER_GAP_CM * 1000;
  return out;
}

// -------------------------------------------------------------- drawing ---

/**
 * A label's height, in ems.  The macro measures it off a probe shape; the
 * add-ins cannot, so it is the tallest single line among the faces the
 * core knows, read off the font files (2026-09-26): Aptos 1.285 (OS/2 win
 * metrics, which Word sets a line by), Calibri 1.221, Cambria 1.172,
 * Liberation Serif, Times and Arial 1.150, Georgia 1.136.  Too short and
 * a box clips its label; too tall only spaces the tiers a little wider.
 */
export const LABEL_LINE_EM = 1.3;

/**
 * One tree's lines, ready to draw in *face* at *pt*: read, each label
 * measured as drawn (small caps included, with the host's *formats*), laid
 * out and turned into shapes.  {error} or {judgment, source, tree, shapes,
 * known, widthCm}; *known* is false when the face was estimated with Times
 * metrics because nobody measured it, which the host says.
 */
export function drawTree(lines, { face = LAYOUT.font_name, pt = LAYOUT.font_pt, formats = [] } = {}) {
  const tree = readTree(lines);
  if (tree.error) return tree;
  const { advances, known } = advancesFor(face);
  const em = (pt / 72) * 2.54;
  const err = layoutTree(tree, (label) => runsWidthCm(runsOf(label, formats), em, LAYOUT.sc_ratio, advances) * 1000);
  if (err) return { error: err };
  const shapes = treeShapes(tree, em * LABEL_LINE_EM * 1000);
  return { judgment: tree.judgment, source: tree.source, tree, shapes, known, widthCm: shapes.width / 1000 };
}
