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
r"""The document's sections, as references to them see them.

A ``\ref`` to a section was deleted: pandoc, reading with ``raw_tex``, keeps
it as raw LaTeX, and the writer drops raw LaTeX.  It is a field now, like a
reference to an example (plan-crossrefs.md), and the field needs two things
from here: where the section is (pandoc bookmarks every heading with its
label, in both formats) and what the reference shows until a reader
recomputes it -- the number LaTeX prints.  A .docx reader may never
recompute (OnlyOffice does not), so that cached number must be right.

Format-agnostic: no markup here, as in measure and emit_base (a test holds
all three to it).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: LaTeX's article numbers \section, \subsection and \subsubsection
#: (secnumdepth 3); pandoc makes them header levels 1-3.
NUMBERED_LEVELS = 3

#: The prefix of the bookmark the converter puts in an unnumbered heading;
#: the postprocess keeps the outline numbering off that heading by it.
UNNUMBERED = "_Reflxnon"
#: The prefix of a numbered appendix heading's bookmark: the postprocess
#: letters those headings' numbers by it.
APPENDIX = "_Reflxapx"

#: A footnote's bookmarks: around its mark in the text, and where its
#: \label was inside it.  The postprocess pairs them by the serial after.
FOOTNOTE_MARK = "_Reflxfn"
FOOTNOTE_MARKER = "_Reflxfnl"


@dataclass(frozen=True)
class Section:
    ident: str
    """The label pandoc gave the heading: the document's \\label, or a slug."""
    level: int
    title: str
    number: str | None
    """Its own number, "1.1"; None for \\section* and below subsubsection."""
    shown: str
    r"""What \ref to it prints: its number, or for an unnumbered one the
    last number set before it, as LaTeX's \@currentlabel has it."""
    serial: int
    """Its place among the document's headings, from 0."""
    appendix: bool = False
    r"""After \appendix: lettered, "A", "A.1"."""
    numbers: tuple[int, ...] = ()
    r"""Its number's parts, (1, 1) for "A.1": what \cref sorts by."""

    @property
    def bookmark(self) -> str:
        """A bookmark name a .docx can hold (letters, digits, underscores):
        pandoc's own is the label, "sec:intro", which Word does not accept.
        It also says whether the heading is numbered (UNNUMBERED)."""
        if not self.number:
            return f"{UNNUMBERED}{self.serial}"
        return f"{APPENDIX if self.appendix else '_Reflxsec'}{self.serial}"


def _text(inlines: Any) -> str:
    out: list[str] = []
    for node in inlines or []:
        if not isinstance(node, dict):
            continue
        t, c = node.get("t"), node.get("c")
        if t == "Str":
            out.append(c)
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif t in ("Emph", "Strong", "SmallCaps", "Underline", "Strikeout",
                   "Superscript", "Subscript"):
            out.append(_text(c))
        elif t == "Quoted":
            left, right = ("\u201c", "\u201d") if c[0].get("t") == "DoubleQuote" \
                else ("\u2018", "\u2019")
            out.append(left + _text(c[1]) + right)
        elif t in ("Span", "Link", "Cite"):
            out.append(_text(c[1]))
        elif t in ("Code", "Math"):
            out.append(c[1])
    return "".join(out)


def is_appendix_mark(block: Any) -> bool:
    """The paragraph extract.APPENDIX_MARK became."""
    from .extract import APPENDIX_MARK

    return (isinstance(block, dict) and block.get("t") in ("Para", "Plain")
            and _text(block["c"]).strip() == APPENDIX_MARK)


def _headers(blocks: Any):
    """Every Header, in document order, also inside a Div -- and None where
    \\appendix was."""
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        if b.get("t") == "Header":
            yield b
        elif is_appendix_mark(b):
            yield None
        elif b.get("t") == "Div":
            yield from _headers(b["c"][1])


def _letter(n: int) -> str:
    """\\Alph: 1 -> "A"."""
    return chr(ord("A") + n - 1) if 1 <= n <= 26 else str(n)


def sections(blocks: Any) -> list[tuple[dict, Section]]:
    """Every heading with its Section, numbered as LaTeX numbers them."""
    counters = [0] * (NUMBERED_LEVELS + 1)
    last = ""
    appendix = False
    out: list[tuple[dict, Section]] = []
    n = 0
    for h in _headers(blocks):
        if h is None:
            # \appendix: the sections start again, lettered
            appendix = True
            counters = [0] * (NUMBERED_LEVELS + 1)
            continue
        level, (ident, classes, _kv), inlines = h["c"]
        number = None
        numbers: tuple[int, ...] = ()
        if level <= NUMBERED_LEVELS and "unnumbered" not in classes:
            counters[level] += 1
            for deeper in range(level + 1, NUMBERED_LEVELS + 1):
                counters[deeper] = 0
            numbers = tuple(counters[k] for k in range(1, level + 1))
            parts = [str(c) for c in numbers]
            if appendix:
                parts[0] = _letter(numbers[0])
            number = ".".join(parts)
            last = number
        out.append((h, Section(ident, level, _text(inlines).strip(),
                               number, number or last, n,
                               appendix and number is not None, numbers)))
        n += 1
    return out


def section_table(blocks: Any) -> dict[str, Section]:
    """label -> Section, for the headings that have a label."""
    return {s.ident: s for _h, s in sections(blocks) if s.ident}


# -- tables, figures and footnotes ------------------------------------------

#: The word processor's sequence a caption's number counts in.  Not what
#: the caption prints, which is the document's language's (names.py).
CAPTION_NAMES = {"table": "Table", "figure": "Figure"}


@dataclass(frozen=True)
class Float:
    """A captioned table or figure: LaTeX numbers each kind on its own."""
    ident: str
    kind: str
    number: int
    title: str
    r"""The caption, as \nameref prints it: without its final full stop."""
    serial: int

    @property
    def bookmark(self) -> str:
        """Around the number in the caption."""
        return f"_Reflxnum{self.serial}"

    @property
    def title_bookmark(self) -> str:
        """Around the caption's text, for \\nameref."""
        return f"_Reflxttl{self.serial}"


@dataclass(frozen=True)
class Footnote:
    ident: str
    number: int
    serial: int
    name: str = ""
    """The name of a footnote in an example, which the renderer gave it
    (inline.note_name); empty for one pandoc wrote."""

    @property
    def bookmark(self) -> str:
        """Around the note's mark in the text, which is what a reference to
        a note points at -- put there by the postprocess, which finds the
        mark by the note holding `marker`.  A note in an example has its
        name already, in both formats."""
        return self.name or f"{FOOTNOTE_MARK}{self.serial}"

    @property
    def marker(self) -> str:
        r"""Where the \label was, inside the note."""
        return f"{FOOTNOTE_MARKER}{self.serial}"


def _walk(node: Any):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        if node.get("t") not in ("RawInline", "RawBlock", "Str"):
            yield from _walk(node.get("c"))


def caption_inlines(node: dict) -> list | None:
    """The inlines of a Table's or Figure's caption, or None if it has none."""
    try:
        blocks = node["c"][1][1]
    except (KeyError, IndexError, TypeError):
        return None
    if not blocks or blocks[0].get("t") not in ("Plain", "Para"):
        return None
    return blocks[0]["c"] or None


def _label_in(note: dict) -> str | None:
    for n in _walk(note.get("c")):
        if n.get("t") == "RawInline" and n["c"][0] in ("latex", "tex"):
            m = re.fullmatch(r"\s*\\label\s*\{([^}]*)\}\s*", n["c"][1])
            if m:
                return m.group(1)
    return None


# -- list items ---------------------------------------------------------

#: article's enumerate, level by level: pandoc's list style and delimiter,
#: and what a word processor's field for the item's own number shows --
#: its label without a final full stop, "2", "(b)", "i", "A".
ENUM_LEVELS = [("Decimal", "Period"), ("LowerAlpha", "TwoParens"),
               ("LowerRoman", "Period"), ("UpperAlpha", "Period")]


def _roman(n: int) -> str:
    out = ""
    for value, digits in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                          (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                          (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while n >= value:
            out += digits
            n -= value
    return out


def _alpha(n: int) -> str:
    return chr(ord("a") + (n - 1) % 26) if n > 0 else str(n)


def list_style(depth: int, style: str, delim: str) -> tuple[str, str]:
    """The style and delimiter a list at enumerate *depth* is numbered in:
    its own, or article's for its depth if it is in pandoc's default."""
    if style == "DefaultStyle":
        return ENUM_LEVELS[min(depth, len(ENUM_LEVELS) - 1)]
    return style, delim


def item_label(style: str, delim: str, n: int) -> str:
    """What a field on item *n* of a list so numbered shows: its label, a
    final full stop dropped (measured, in both formats)."""
    number = {"LowerAlpha": _alpha(n), "UpperAlpha": _alpha(n).upper(),
              "LowerRoman": _roman(n), "UpperRoman": _roman(n).upper()
              }.get(style, str(n))
    if delim == "TwoParens":
        return f"({number})"
    if delim == "OneParen":
        return f"{number})"
    return number


@dataclass(frozen=True)
class Item:
    r"""An item of an enumerate with a \label in it.

    LaTeX's \ref prints its number with its parents', "2b", "2(b)i".  A
    reference is a field per level, each on that level's item: pandoc
    writes a nested list as a list of its own, so no word processor's
    "number in context" knows the parents.  The second level's field
    shows the label, "(b)", where LaTeX's \ref prints "b" -- there is no
    field that drops the parentheses.
    """
    ident: str
    path: tuple[tuple[str, str], ...]
    """(bookmark, what its field shows), outermost first."""
    section: Section | None
    r"""The heading before it: what \nameref to an item prints is that
    section's title (LaTeX's \@currenttitle)."""
    numbers: tuple[int, ...] = ()
    r"""Its number and its parents', outermost first: what \cref sorts by."""


def item_bookmark(serial: int) -> str:
    return f"_Reflxitm{serial}"


def _own_label(blocks: Any) -> str | None:
    """The \\label in an item, not in a list nested in it."""
    for node in blocks or []:
        if not isinstance(node, dict):
            continue
        if node.get("t") == "OrderedList":
            continue
        if node.get("t") == "RawInline" and node["c"][0] in ("latex", "tex"):
            m = re.fullmatch(r"\s*\\label\s*\{([^}]*)\}\s*", node["c"][1])
            if m:
                return m.group(1)
        c = node.get("c")
        if isinstance(c, list):
            found = _own_label(_flatten(c))
            if found:
                return found
    return None


def _flatten(c: list) -> list:
    out: list = []
    for x in c:
        if isinstance(x, list):
            out.extend(_flatten(x))
        elif isinstance(x, dict):
            out.append(x)
    return out


@dataclass
class ListTargets:
    items: list[Item]
    marks: dict[int, tuple[str, int]]
    """id(item's block list) -> (bookmark, serial), for every item a
    reference needs: a labelled one and its ancestors."""
    depths: dict[int, int]
    """id(OrderedList) -> its enumerate depth, from 0."""


def list_targets(blocks: Any, heads: dict[int, Section], serial: int) -> ListTargets:
    items: list[Item] = []
    marks: dict[int, tuple[str, int]] = {}
    depths: dict[int, int] = {}
    section: list[Section | None] = [None]
    counter = [serial]

    def mark(item_blocks: list) -> str:
        if id(item_blocks) not in marks:
            marks[id(item_blocks)] = (item_bookmark(counter[0]), counter[0])
            counter[0] += 1
        return marks[id(item_blocks)][0]

    def walk(node: Any, ancestors: list) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x, ancestors)
            return
        if not isinstance(node, dict):
            return
        t = node.get("t")
        if t == "Header" and id(node) in heads:
            section[0] = heads[id(node)]
        if t == "OrderedList":
            depth = len(ancestors)
            depths[id(node)] = depth
            (start, style, delim), entries = node["c"]
            style, delim = list_style(depth, style["t"], delim["t"])
            for k, entry in enumerate(entries):
                here = ancestors + [(entry, item_label(style, delim, start + k),
                                     start + k)]
                label = _own_label(entry)
                if label:
                    items.append(Item(label, tuple((mark(b), shown) for b, shown, _n in here),
                                      section[0], tuple(n for _b, _s, n in here)))
                walk(entry, here)
            return
        if t in ("RawInline", "RawBlock", "Str"):
            return
        walk(node.get("c"), ancestors)

    walk(blocks, [])
    return ListTargets(items, marks, depths)


@dataclass
class Targets:
    """Everything a reference can point at that is not an example."""
    headings: list[tuple[dict, Section]]
    floats: list[tuple[dict, Float]]
    footnotes: list[Footnote]
    lists: ListTargets
    equations: Any = None
    """equations.EquationTargets"""

    def by_label(self) -> dict[str, Any]:
        table: dict[str, Any] = {s.ident: s for _h, s in self.headings if s.ident}
        table.update({f.ident: f for _n, f in self.floats if f.ident})
        table.update({n.ident: n for n in self.footnotes})
        table.update({i.ident: i for i in self.lists.items})
        if self.equations is not None:
            table.update({e.ident: e for e in self.equations.equations})
        return table


def targets(blocks: Any, example_notes: Any = None,
            note_labels: dict[str, int] | None = None,
            equations_within: int | None = None,
            display_sources: list[str] | None = None,
            warn=lambda _m: None) -> Targets:
    """*example_notes*(node) -> the numbers of the footnotes in the example
    a placeholder stands for (the renderer's, inline.notes), which LaTeX
    counts with the rest; *note_labels* their labels."""
    heads = sections(blocks)
    serial = len(heads)
    counts = {"table": 0, "figure": 0}
    floats: list[tuple[dict, Float]] = []
    notes: list[Footnote] = []
    note_number = 0
    # pandoc 3.6 puts a table's \label on a Div around it, 3.10 on the table
    wrapped = {id(d["c"][1][0]): d["c"][0][0] for d in _walk(blocks)
               if d.get("t") == "Div" and d["c"][0][0] and len(d["c"][1]) == 1
               and isinstance(d["c"][1][0], dict) and d["c"][1][0].get("t") == "Table"}
    for node in _walk(blocks):
        t = node.get("t")
        if t in ("Table", "Figure"):
            inlines = caption_inlines(node)
            if inlines is None:
                continue
            kind = t.lower()
            counts[kind] += 1
            title = _text(inlines).strip()
            floats.append((node, Float(node["c"][0][0] or wrapped.get(id(node), ""),
                                       kind, counts[kind],
                                       title[:-1] if title.endswith(".") else title,
                                       serial)))
            serial += 1
        elif example_notes is not None and example_notes(node):
            from .inline import note_name

            by_note = {k: lab for lab, k in (note_labels or {}).items()}
            for k in example_notes(node):
                note_number += 1
                if k in by_note:
                    notes.append(Footnote(by_note[k], note_number, serial,
                                          note_name(k)))
                    serial += 1
        elif t == "Note":
            note_number += 1
            label = _label_in(node)
            if label:
                notes.append(Footnote(label, note_number, serial))
                serial += 1
    from .equations import equation_targets

    by_node = {id(h): s for h, s in heads}
    return Targets(heads, floats, notes, list_targets(blocks, by_node, serial),
                   equation_targets(blocks, by_node, equations_within,
                                    display_sources, warn))
