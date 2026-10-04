# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Gerhard Schaden
#
# This file is part of pandoc-linguexx.
#
# pandoc-linguexx is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# pandoc-linguexx is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <https://www.gnu.org/licenses/>.
r"""The way back, stage 1: a .docx's example tables -> IR.

The counterpart of the emitters, for documents whose examples this project
made -- the converter, the Writer macro (through LibreOffice's .docx
export) or an add-in.  plan-reverse.md is the plan; its spikes decided the
shape:

* **The XML is read, not pandoc's AST.**  Pandoc keeps a cell's paragraph
  style but drops an EMPTY paragraph's, so the spacer rows that say "this
  is an example" arrive as bare cells; it keeps a field's cached text but
  not the field; and its ODT reader drops a reference's text altogether.
  None of that is pandoc's to fix, and all of it is in ``document.xml``.
* **Style names decide, never contents** -- the rule of the macro's
  ``LxReadTable`` and of ``addin/core/untypeset.js``.  A first word that
  reads like "a." does not make a sub-example.  The one place the reader
  has to fall back on what a cell says is named in ``_lead()``.
* **The prose stays pandoc's.**  Each example table is replaced by a
  paragraph holding a placeholder and each reference to an example by a
  placeholder word; pandoc converts the rest, and reverse.py fills the
  placeholders in afterwards.

A cell's text comes back as LaTeX source, which is what the IR holds: the
character styles the converter writes are the commands they came from
(``LxLeipzig`` -> ``\lpzg``), and direct formatting the nearest command.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .inline import WRAPPERS
from .ir import Body, Example, Item, Tier
from .latexutil import Brackets
from .styles import (
    ANNOT_PARA, BAND_PARA, CELL_PARA, JUDGMENT_PARA, SPACE_ABOVE_PARA,
    SPACE_BELOW_PARA, TRANSLATION_PARA,
)

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


#: What a drawn tree is titled, so that it can be told from a picture --
#: addin/core/tree.js's TREE_TITLE, which the macro writes too.
TREE_TITLE = "LinguExx tree"

#: A placeholder is letters and digits only, so pandoc passes it through
#: untouched and nothing in it is a LaTeX special.
EXAMPLE_TOKEN = "LXEXAMPLE{n}X"
REF_TOKEN = "LXREF{n}X"
EXAMPLE_TOKEN_RE = re.compile(r"LXEXAMPLE(\d+)X")

#: A character style -> the command it was written from.  The inverse of
#: inline.WRAPPERS, first spelling wins: \emph and \textit are both
#: LxItalic, and \textit is the one that reads the same in every context.
STYLE_COMMANDS: dict[str, str] = {}
for _cmd, _style in WRAPPERS.items():
    if _style:
        STYLE_COMMANDS.setdefault(_style, _cmd)

#: Direct formatting -> command.  The .docx target writes no italic or
#: bold into a cell (only small capitals), but a document edited in Word
#: may have them, and they are what a reader sees.
#:
#: Small capitals in an example are a Leipzig gloss: a document made in
#: Writer or Word with the macro or an add-in has no LxLeipzig style, only
#: the small capitals the linguist typed (the macro keeps Writer's case
#: map, the add-ins w:smallCaps), and \lpzg is what linguexx sets a gloss
#: label with.  The converter's own \textsc keeps its name, LxSmallCaps,
#: and comes back as \textsc.
DIRECT_COMMANDS = {
    "i": "textit", "b": "textbf", "smallCaps": "lpzg", "u": "underline",
    "superscript": "textsuperscript", "subscript": "textsubscript",
}

#: Small capitals that were typed, not converted: a pseudo-command riding
#: beside "lpzg", written as nothing.  Only these have their edges trimmed;
#: LxLeipzig marks exactly what an author put inside \lpzg, and linguexx's
#: own lpzgcheck.tex puts a "." there on purpose.
TYPED = "typed"

#: What a gloss label is made of; anything else at either end of a typed
#: small-capital run -- the "." of "acc.", the "-" of "-pst" -- was selected
#: with it, and stays outside \lpzg, which reads "." inside as a separator.
_LABEL_EDGES = re.compile(r"^([\W_]*)(.*?)([\W_]*)$", re.S)

#: Nesting order when a run carries several, outermost first.
COMMAND_ORDER = ("lpzg", "jdg", "textsc", "textbf", "textit", "underline",
                 "textsuperscript", "textsubscript")

LATEX_SPECIALS = {
    "\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "$": r"\$",
    "&": r"\&", "#": r"\#", "%": r"\%", "_": r"\_",
    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    "\u00a0": "~",
    # pdflatex has no glyph for the prime in text; this is what the
    # converter itself reads a ' in math as.
    "\u2032": "$'$", "\u2033": "$''$",
    # Quotes and dashes as TeX's ligatures, which is what the converter
    # read them from and what a LaTeX author types.  (A translation set
    # 1.4pt left of the original's was microtype's protrusion, which
    # pandoc's template loads, not the quote character.)
    "\u2018": "`", "\u2019": "'", "\u201c": "``", "\u201d": "''",
    "\u2013": "--", "\u2014": "---",
}


def latex_escape(text: str) -> str:
    # Hyphens the text really has stay hyphens: "--" typed is not a dash.
    text = re.sub(r"-(?=-)", "-{}", text)
    return "".join(LATEX_SPECIALS.get(ch, ch) for ch in text)


# -- styles --------------------------------------------------------------

@dataclass
class Styles:
    """styles.xml, as much of it as the reader needs: the display NAME of
    each style id (LibreOffice and Word may both rename an id, and the name
    is what the converter wrote), and the commands a character style's own
    run properties amount to."""

    names: dict[str, str] = field(default_factory=dict)
    commands: dict[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def read(cls, xml: bytes | None) -> Styles:
        out = cls()
        if not xml:
            return out
        root = ET.fromstring(xml)
        for st in root.iter(w("style")):
            sid = st.get(w("styleId")) or ""
            name_el = st.find(w("name"))
            name = name_el.get(w("val")) if name_el is not None else sid
            out.names[sid] = name or sid
            if st.get(w("type")) == "character":
                cmd = STYLE_COMMANDS.get(name) or STYLE_COMMANDS.get(sid)
                if cmd:
                    out.commands[sid] = frozenset({cmd})
                else:
                    out.commands[sid] = _direct(st.find(w("rPr")))
        return out

    def name(self, sid: str) -> str:
        return self.names.get(sid, sid)


def _on(el: ET.Element | None) -> bool:
    if el is None:
        return False
    return el.get(w("val"), "true") not in ("0", "false", "off", "none")


def _direct(rpr: ET.Element | None) -> frozenset[str]:
    if rpr is None:
        return frozenset()
    found = set()
    for tag in ("i", "b", "smallCaps", "u"):
        if _on(rpr.find(w(tag))):
            found.add(DIRECT_COMMANDS[tag])
    if "lpzg" in found:
        found.add(TYPED)
    va = rpr.find(w("vertAlign"))
    if va is not None and va.get(w("val")) in DIRECT_COMMANDS:
        found.add(DIRECT_COMMANDS[va.get(w("val"))])
    return frozenset(found)


def para_style(p: ET.Element, styles: Styles) -> str:
    ps = p.find(f"{w('pPr')}/{w('pStyle')}")
    return styles.name(ps.get(w("val"), "")) if ps is not None else ""


# -- paragraphs ----------------------------------------------------------

@dataclass
class Segment:
    kind: str                       # text | seq | ref | tree | note
    text: str = ""                  # text, or a field's cached result
    commands: frozenset[str] = frozenset()
    target: str = ""                # ref: the bookmark; note: the id


@dataclass
class Para:
    segments: list[Segment]
    bookmarks: list[str]

    @property
    def plain(self) -> str:
        return "".join(s.text for s in self.segments if s.kind != "tree")


#: Containers whose runs are part of the paragraph's text.  A deletion is
#: not, and neither is the old position of a move: pandoc's default is to
#: accept tracked changes, and the examples are read the same way.
_TRANSPARENT = {w(t) for t in ("hyperlink", "smartTag", "ins", "moveTo",
                               "customXml", "sdtContent", "dir", "bdo")}
_SKIPPED = {w(t) for t in ("del", "moveFrom", "pPr", "sdtPr", "sdtEndPr")}


def _events(node: ET.Element, styles: Styles, out: list) -> None:
    """A paragraph's content in document order, as flat events."""
    for child in node:
        tag = child.tag
        if tag in _SKIPPED:
            continue
        if tag == w("bookmarkStart"):
            out.append(("bookmark", child.get(w("name"), "")))
        elif tag == w("fldSimple"):
            out.append(("begin",))
            out.append(("instr", child.get(w("instr"), "")))
            out.append(("separate",))
            _events(child, styles, out)
            out.append(("end",))
        elif tag == w("r"):
            _run_events(child, styles, out)
        elif tag in _TRANSPARENT or tag == w("sdt"):
            _events(child, styles, out)


def _run_events(r: ET.Element, styles: Styles, out: list) -> None:
    rpr = r.find(w("rPr"))
    commands = _direct(rpr)
    if rpr is not None:
        rs = rpr.find(w("rStyle"))
        if rs is not None:
            commands |= styles.commands.get(rs.get(w("val"), ""), frozenset())
    for el in r:
        tag = el.tag
        if tag == w("t"):
            out.append(("text", el.text or "", commands))
        elif tag in (w("tab"), w("br"), w("cr")):
            out.append(("text", " ", commands))
        elif tag == w("noBreakHyphen"):
            out.append(("text", "-", commands))
        elif tag == w("fldChar"):
            kind = el.get(w("fldCharType"))
            out.append(({"begin": "begin", "separate": "separate",
                         "end": "end"}.get(kind, "noop"),))
        elif tag == w("instrText"):
            out.append(("instr", el.text or ""))
        elif tag in (w("footnoteReference"), w("endnoteReference")):
            out.append(("note", el.tag.split("}")[1].replace("Reference", ""),
                        el.get(w("id"), "")))
        elif tag == w("drawing") or tag.endswith("AlternateContent"):
            for pr in el.iter(f"{{{WP}}}docPr"):
                if pr.get("title") == TREE_TITLE:
                    out.append(("tree", pr.get("descr", "")))
                    break


def read_para(p: ET.Element, styles: Styles) -> Para:
    """A paragraph as segments: text with its commands, and the fields that
    matter -- an example number (SEQ) and a reference (REF) -- as
    themselves.  Any other field is its cached result, as a reader that
    does not recalculate shows it."""
    events: list = []
    _events(p, styles, events)
    segments: list[Segment] = []
    bookmarks: list[str] = []
    stack: list[dict] = []          # open fields: instr, result, phase

    def emit(seg: Segment) -> None:
        if stack:
            stack[-1]["result"].append(seg)
        else:
            segments.append(seg)

    for ev in events:
        kind = ev[0]
        if kind == "bookmark":
            bookmarks.append(ev[1])
        elif kind == "begin":
            stack.append({"instr": "", "result": [], "phase": "instr"})
        elif kind == "instr":
            if stack and stack[-1]["phase"] == "instr":
                stack[-1]["instr"] += ev[1]
        elif kind == "separate":
            if stack:
                stack[-1]["phase"] = "result"
        elif kind == "end":
            if not stack:
                continue
            f = stack.pop()
            words = f["instr"].split()
            name = words[0].upper() if words else ""
            cached = "".join(s.text for s in f["result"] if s.kind == "text")
            if name == "SEQ":
                emit(Segment("seq", cached))
            elif name == "REF" and len(words) > 1:
                emit(Segment("ref", cached, target=words[1]))
            else:
                for s in f["result"]:
                    emit(s)
        elif kind == "text":
            if stack and stack[-1]["phase"] == "instr":
                continue
            emit(Segment("text", ev[1], ev[2]))
        elif kind == "tree":
            emit(Segment("tree", ev[1]))
        elif kind == "note":
            emit(Segment("note", target=f"{ev[1]}:{ev[2]}"))
    while stack:                    # a field never closed: keep its text
        for s in stack.pop()["result"]:
            segments.append(s)
    return Para(segments, bookmarks)


# -- tables --------------------------------------------------------------

@dataclass
class Cell:
    style: str
    span: int
    paras: list[Para]

    @property
    def plain(self) -> str:
        return " ".join(p.plain for p in self.paras).strip()

    @property
    def segments(self) -> list[Segment]:
        out: list[Segment] = []
        for k, p in enumerate(self.paras):
            if k and p.segments:
                out.append(Segment("text", " "))
            out += p.segments
        return out

    @property
    def bookmarks(self) -> list[str]:
        return [b for p in self.paras for b in p.bookmarks]

    @property
    def has_seq(self) -> bool:
        return any(s.kind == "seq" for s in self.segments)

    @property
    def tree(self) -> str | None:
        for s in self.segments:
            if s.kind == "tree":
                return s.text
        return None


def read_rows(tbl: ET.Element, styles: Styles) -> list[list[Cell]]:
    rows = []
    for tr in tbl.findall(w("tr")):
        cells = []
        for tc in tr.findall(w("tc")):
            gs = tc.find(f"{w('tcPr')}/{w('gridSpan')}")
            span = int(gs.get(w("val"), "1")) if gs is not None else 1
            paras = tc.findall(w("p"))
            style = para_style(paras[0], styles) if paras else ""
            cells.append(Cell(style, span, [read_para(p, styles) for p in paras]))
        rows.append(cells)
    return rows


def is_example_table(rows: list[list[Cell]]) -> bool:
    """Topped and tailed by the rows that are only the space around it --
    nothing else makes a row like that (LxIsExampleTable)."""
    return (len(rows) >= 3
            and any(c.style == SPACE_ABOVE_PARA for c in rows[0])
            and any(c.style == SPACE_BELOW_PARA for c in rows[-1]))


# -- cells -> LaTeX ------------------------------------------------------

@dataclass
class Context:
    """What turning cells into LaTeX needs from the whole document."""

    styles: Styles
    notes: dict[str, ET.Element] = field(default_factory=dict)
    refs: list[str] = field(default_factory=list)
    """Every reference met, by its target bookmark; a REF_TOKEN's number
    indexes this."""

    warnings: list[str] = field(default_factory=list)

    def ref_token(self, target: str) -> str:
        self.refs.append(target)
        return REF_TOKEN.format(n=len(self.refs) - 1)


def segments_latex(segments: list[Segment], ctx: Context,
                   example_bookmarks: set[str]) -> str:
    """Segments as LaTeX source: runs of the same commands grouped and
    wrapped once, a reference to an example as a placeholder, a footnote
    as \\footnote."""
    out: list[str] = []
    buf: list[str] = []
    cur: frozenset[str] = frozenset()

    def wrap(text: str, commands) -> str:
        text = latex_escape(text)
        for cmd in reversed([c for c in COMMAND_ORDER if c in commands]):
            text = f"\\{cmd}{{{text}}}"
        return text

    def flush() -> None:
        if buf:
            raw = "".join(buf)
            if TYPED in cur:
                lead, core, trail = _LABEL_EDGES.match(raw).groups()
                rest = cur - {"lpzg", TYPED}
                out.append(wrap(lead, rest) if lead else "")
                out.append(wrap(core, cur) if core else "")
                out.append(wrap(trail, rest) if trail else "")
            else:
                out.append(wrap(raw, cur))
            buf.clear()

    for s in segments:
        if s.kind == "text":
            if s.commands != cur and s.text.strip():
                flush()
                cur = s.commands
            buf.append(s.text)
            continue
        flush()
        cur = frozenset()
        if s.kind == "ref":
            if s.target in example_bookmarks:
                out.append(ctx.ref_token(s.target))
            else:
                out.append(latex_escape(s.text))
        elif s.kind == "seq":
            out.append(latex_escape(s.text))
        elif s.kind == "note":
            out.append(_note_latex(s.target, ctx, example_bookmarks))
    flush()
    return "".join(out).strip()


def _note_latex(key: str, ctx: Context, example_bookmarks: set[str]) -> str:
    note = ctx.notes.get(key)
    if note is None:
        return ""
    paras = [segments_latex(read_para(p, ctx.styles).segments, ctx,
                            example_bookmarks)
             for p in note.findall(w("p"))]
    return "\\footnote{" + "\n\n".join(p for p in paras if p) + "}"


# -- rows -> IR ----------------------------------------------------------

_MARKER_CORE = re.compile(r"[a-z]+")


def _alph(n: int) -> str:
    return chr(ord("a") + (n - 1) % 26)


_ROMAN = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]


def marker_core(marker: str) -> str:
    m = _MARKER_CORE.search(marker.lower())
    return m.group(0) if m else ""


def _lead(rows: list[list[Cell]]) -> tuple[int, int | None]:
    """How many cells precede the example's own text, and which is the
    judgment column (or None) -- LxLeadColumns.

    The judgment column says it outright; failing that, a translation's
    wide cell starts where the text does.  An example with neither (a
    gloss with no translation and no mark, or sub-examples without
    either) says nothing.  If it is one row, its cells do; otherwise, and
    only there, a cell's content is read: column 1 is a marker column when
    it holds "a." on the first row and the next marker on a later one.  A
    glossed example of one sub-example with no translation and no mark is
    read as no sub-example at all.
    """
    for row in rows:
        for i, c in enumerate(row):
            if c.style == JUDGMENT_PARA:
                return i + 1, i
    for row in rows:
        for i, c in enumerate(row):
            if c.style == TRANSLATION_PARA:
                return i, None
    body = [r for r in rows if r and not is_spacer(r)]
    head = head_row(rows)
    if head is not None:
        body = [r for r in body if r is not head]
    if len(body) == 1:
        # One row is unglossed text (a gloss has two tiers at least), and
        # unglossed text is one cell across the body: whatever precedes it
        # leads.
        return len([c for c in body[0] if c.style != ANNOT_PARA]) - 1, None
    if body and len(body[0]) > 2 and marker_core(body[0][1].plain) == "a":
        if any(len(r) > 1 and marker_core(r[1].plain) in ("b", "i")
               for r in body[1:]):
            return 2, None
    return 1, None


def head_row(rows: list[list[Cell]]) -> list[Cell] | None:
    """The row of text before the first sub-example, if there is one: the
    number, then one cell across every other column, then more rows that
    are not a translation.  Unglossed text without sub-examples is the same
    first row with nothing but a translation after it; a marker cell spans
    one column."""
    body = [r for r in rows if r and not is_spacer(r)]
    if len(body) < 2:
        return None
    first = body[0]
    if (len(first) == 2 and first[1].span >= 2 and first[1].style == CELL_PARA
            and not any(c.style == TRANSLATION_PARA for c in body[1])):
        return first
    return None


def is_spacer(row: list[Cell]) -> bool:
    return any(c.style in (SPACE_ABOVE_PARA, SPACE_BELOW_PARA) for c in row)


def judgment_latex(plain: str) -> str:
    r"""A judgment cell's text as the source linguexx reads as a mark:
    the marks it detects on its own as they are, anything else as
    \jdg{...}."""
    plain = plain.strip()
    if not plain:
        return ""
    if all(ch in "*?#%" for ch in plain):
        return plain.replace("#", r"\#").replace("%", r"\%")
    return "\\jdg{" + latex_escape(plain) + "}"




@dataclass
class _Building:
    """One body (the example's, or one sub-example's) as its rows come."""

    marker: str = ""
    judgment: str = ""
    annot: str = ""
    bands: list[list[list[Cell]]] = field(default_factory=list)
    translation: list[str] = field(default_factory=list)
    tree: str | None = None


def read_example(rows: list[list[Cell]], index: int, ctx: Context,
                 example_bookmarks: set[str]
                 ) -> tuple[Example, Brackets | None, list[str]]:
    """One example table -> (Example, the brackets around its number, the
    bookmarks on its number).  The Example's labels are left empty: which
    examples need one is known only once every reference has been read."""
    lead, jcol = _lead(rows)
    has_marker = (lead - (1 if jcol is not None else 0)) >= 2

    def latex(c: Cell) -> str:
        return segments_latex(c.segments, ctx, example_bookmarks)

    bodies: list[_Building] = []
    number_cell: Cell | None = None
    head = head_row(rows)
    for row in rows:
        if not row or is_spacer(row) or row is head:
            if row is head:
                number_cell = row[0]
            continue
        if number_cell is None:
            number_cell = row[0]
        rest = [c for c in row[lead:] if c.style != ANNOT_PARA]
        if any(c.style == TRANSLATION_PARA for c in row):
            text = " ".join(t for t in (latex(c) for c in rest) if t)
            if bodies and text:
                bodies[-1].translation.append(text)
            continue
        marker = row[1].plain.strip() if has_marker and len(row) > 1 else ""
        if not bodies or marker:
            b = _Building(marker=marker)
            if jcol is not None and len(row) > jcol:
                b.judgment = judgment_latex(row[jcol].plain)
            annot = next((c for c in row if c.style == ANNOT_PARA), None)
            if annot is not None:
                b.annot = latex(annot)
            bodies.append(b)
        b = bodies[-1]
        tree = next((c.tree for c in rest if c.tree is not None), None)
        if tree is not None:
            b.tree = tree
            continue
        # A row marked as a band's first starts the tiers again.
        if not b.bands or (rest and rest[0].style == BAND_PARA):
            b.bands.append([])
        b.bands[-1].append(rest)

    built = [_body(b, latex, ctx, index) for b in bodies]
    custom, brackets, marks = "", None, []
    if number_cell is not None:
        marks = number_cell.bookmarks
        if number_cell.has_seq:
            brackets = _number_brackets(number_cell)
        elif number_cell.plain:
            custom = latex(number_cell)
    if has_marker:
        levels = _levels([b.marker for b in bodies], ctx, index)
        items = tuple(Item(level=lv, ordinal=o, marker=b.marker, body=body)
                      for b, body, (lv, o) in zip(bodies, built, levels))
        ex = Example(index=index, placeholder="", custom_label=custom,
                     items=items,
                     head=latex(head[1]) if head is not None else "")
    else:
        ex = Example(index=index, placeholder="", custom_label=custom,
                     body=built[0] if built else Body())
    return ex, brackets, marks


def _body(b: _Building, latex, ctx: Context, index: int) -> Body:
    translation = " ".join(b.translation)
    if b.tree is not None:
        ctx.warnings.append(
            f"example {index + 1} holds a drawn tree; its bracket notation is "
            f"kept as a comment in the example, to be set with forest by hand")
        lines = [ln.strip() for ln in b.tree.splitlines() if ln.strip()]
        text = "% LinguExx tree, as it was typed:\n" + "\n".join(
            f"% {ln}" for ln in lines) + "\n"
        return Body(judgment=b.judgment, text=text, translation=translation,
                    annot=b.annot)
    tiers: list[list[str]] = []
    for band in b.bands:
        # Every row of a band has the same cells, so the cell after the
        # last word -- the padding up to the grid -- is the last cell, and
        # it is empty on every row.  Only it is dropped here: an empty cell
        # INSIDE a tier is a word one line lacks, and keeps its place.
        texts = [[latex(c) for c in row] for row in band]
        plains = [[c.plain for c in row] for row in band]
        if len(band) > 1 and all(r and not t[-1] and not p[-1]
                                 for r, t, p in zip(band, texts, plains)):
            texts = [t[:-1] for t in texts]
        for t, cells in enumerate(texts):
            if t < len(tiers):
                tiers[t] += cells
            else:
                tiers.append(list(cells))
    if len(tiers) <= 1:
        text = " ".join(c for c in (tiers[0] if tiers else []) if c)
        return Body(judgment=b.judgment, text=text, translation=translation,
                    annot=b.annot)
    for cells in tiers:
        while cells and not cells[-1]:
            cells.pop()
    return Body(judgment=b.judgment,
                tiers=tuple(Tier(cells=tuple(c)) for c in tiers),
                translation=translation, annot=b.annot)


def _number_brackets(cell: Cell) -> Brackets:
    """What stands either side of the number field: \\ExLBr and \\ExRBr."""
    before, after, seen = [], [], False
    for s in cell.segments:
        if s.kind == "seq":
            seen = True
        elif s.kind == "text":
            (after if seen else before).append(s.text)
    return Brackets(ex_l="".join(before).strip(), ex_r="".join(after).strip())


def _levels(markers: list[str], ctx: Context, index: int) -> list[tuple[int, int]]:
    """(level, ordinal) of each sub-example, from its marker.

    The table does not say which level a sub-example is at -- both sit in
    one marker column -- so the letters and numerals do, read as linguexx
    writes them: a., b., ... at the first level, i., ii., ... below it.
    "i." after "h." is read as the ninth letter, not as a deeper level.
    """
    out: list[tuple[int, int]] = []
    level, counts = 0, {1: 0, 2: 0}
    for m in markers:
        core = marker_core(m)
        if level == 2 and counts[2] < len(_ROMAN) and core == _ROMAN[counts[2]]:
            counts[2] += 1
        elif core == _alph(counts[1] + 1):
            level = 1
            counts[1] += 1
            counts[2] = 0
        elif core == "i" and level >= 1:
            level, counts[2] = 2, 1
        else:
            ctx.warnings.append(
                f"example {index + 1}: sub-example marker {m!r} does not "
                f"follow the one before it; numbered as the next one")
            level = level or 1
            counts[level] += 1
        out.append((level, counts[level]))
    return out
