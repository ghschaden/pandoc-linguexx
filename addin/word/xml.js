// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright (C) 2026 Gerhard Schaden
//
// This file is part of pandoc-linguexx.

/**
 * Just enough XML to read what Word hands an add-in, with no dependency.
 *
 * The browser has DOMParser and Node does not, and the add-in's own logic
 * is tested under Node; a parser both can run keeps one code path.  It is
 * strict where that catches our own mistakes -- mismatched and unclosed
 * tags throw -- and makes no attempt at DTDs or namespaces beyond keeping
 * the prefixed name ("w:p") as written, which is how OOXML is always read.
 */

const ENTITIES = { lt: "<", gt: ">", amp: "&", quot: '"', apos: "'" };

export function decode(s) {
  return s.replace(/&(#x[0-9a-fA-F]+|#[0-9]+|[a-z]+);/g, (m, e) => {
    if (e[0] === "#") {
      const code = e[1] === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
      return String.fromCodePoint(code);
    }
    if (!(e in ENTITIES)) throw new Error(`unknown entity &${e};`);
    return ENTITIES[e];
  });
}

function attributes(src) {
  const attrs = {};
  const re = /([^\s=]+)\s*=\s*("([^"]*)"|'([^']*)')/g;
  let m;
  let rest = src;
  while ((m = re.exec(src))) {
    attrs[m[1]] = decode(m[3] !== undefined ? m[3] : m[4]);
    rest = rest.replace(m[0], "");
  }
  if (rest.trim()) throw new Error(`malformed attributes: ${src.trim().slice(0, 60)}`);
  return attrs;
}

/**
 * A tree of {name, attrs, children}, children being elements or strings.
 * Returns a synthetic root whose children are the document's top level.
 */
export function parse(xml) {
  const root = { name: "#root", attrs: {}, children: [] };
  const stack = [root];
  let i = 0;
  while (i < xml.length) {
    const lt = xml.indexOf("<", i);
    if (lt < 0) {
      const text = xml.slice(i);
      if (text.trim()) stack[stack.length - 1].children.push(decode(text));
      break;
    }
    if (lt > i) stack[stack.length - 1].children.push(decode(xml.slice(i, lt)));
    if (xml.startsWith("<?", lt)) {
      i = xml.indexOf("?>", lt) + 2;
    } else if (xml.startsWith("<!--", lt)) {
      i = xml.indexOf("-->", lt) + 3;
    } else if (xml.startsWith("<![CDATA[", lt)) {
      const end = xml.indexOf("]]>", lt);
      stack[stack.length - 1].children.push(xml.slice(lt + 9, end));
      i = end + 3;
    } else if (xml.startsWith("<!", lt)) {
      i = xml.indexOf(">", lt) + 1;
    } else {
      const gt = xml.indexOf(">", lt);
      if (gt < 0) throw new Error("unterminated tag");
      const inner = xml.slice(lt + 1, gt);
      if (inner[0] === "/") {
        const name = inner.slice(1).trim();
        const open = stack.pop();
        if (!open || open.name !== name) {
          throw new Error(`</${name}> closes <${open ? open.name : "nothing"}>`);
        }
      } else {
        const empty = inner.endsWith("/");
        const body = empty ? inner.slice(0, -1) : inner;
        const sp = body.search(/\s/);
        const name = sp < 0 ? body : body.slice(0, sp);
        const el = { name, attrs: sp < 0 ? {} : attributes(body.slice(sp)), children: [] };
        stack[stack.length - 1].children.push(el);
        if (!empty) stack.push(el);
      }
      i = gt + 1;
    }
    if (i <= 0) throw new Error("unterminated construct");
  }
  if (stack.length !== 1) throw new Error(`<${stack[stack.length - 1].name}> is never closed`);
  return root;
}

/** true, or throws saying what is wrong. */
export function wellFormed(xml) {
  const root = parse(xml);
  const top = root.children.filter((c) => typeof c !== "string");
  if (top.length !== 1) throw new Error(`${top.length} root elements`);
  return true;
}

/** Every descendant element named *name*, in document order. */
export function findAll(el, name, out = []) {
  for (const c of el.children) {
    if (typeof c === "string") continue;
    if (c.name === name) out.push(c);
    findAll(c, name, out);
  }
  return out;
}

/** The first child element named *name*, or undefined. */
export function child(el, name) {
  return el.children.find((c) => typeof c !== "string" && c.name === name);
}

/** The concatenated text of an element's string children, at any depth. */
export function textOf(el) {
  return el.children.map((c) => (typeof c === "string" ? c : textOf(c))).join("");
}
