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

"""Stage 3 — rewrite the pandoc AST.

Two substitutions:

* a ``Para`` that is nothing but a placeholder becomes the example's
  ``RawBlock "opendocument"``;
* a ``\\ref``/``\\pref`` to an example label becomes a
  ``RawInline "opendocument"`` carrying a ``text:sequence-ref``.

S4 established that on pandoc 3.6.1 ``\\ref{x}`` arrives as a ``Link``
whose attributes carry ``reference``; ``RawInline "latex"`` is handled too,
because older pandocs and ``+raw_tex`` produce that instead.
"""

from __future__ import annotations

import re
from typing import Any
from collections.abc import Callable

from .extract import PLACEHOLDER_RE
from .cleveref import Entry, phrase
from .equations import Equation
from .latexutil import Brackets
from .styles import EQUATION_PARA
from .names import ENGLISH, Names
from .sections import Float, Footnote, Item, is_appendix_mark, \
    caption_inlines, list_style, targets

REF_CMD = re.compile(r"\\(p?ref)\s*\{([^}]*)\}")
#: Every reference command a section's, a table's, a figure's or a
#: footnote's label can be given to, and \pageref, which an example's can.
ANY_REF = re.compile(
    r"\\(ref|pref|eqref|cref|Cref|autoref|nameref|pageref|cpageref|Cpageref)"
    r"\s*\{([^}]*)\}")
#: What each prints before the field: nothing (""), or a name (None) --
#: cleveref's and hyperref's, in the document's language (names.py), with
#: their unbreakable space.
_FORMS = {
    "ref": ("", "number"), "pref": ("", "number"), "eqref": ("", "number"),
    "cref": (None, "number"), "Cref": (None, "number"),
    "autoref": (None, "number"), "nameref": ("", "title"),
    "pageref": ("", "page"), "cpageref": (None, "page"),
    "Cpageref": (None, "page"),
}
_LABEL = re.compile(r"\s*\\label\s*\{([^}]*)\}\s*")
#: cleveref's commands that take a list, or a range: what cleveref.phrase
#: sets.  \cref to an example is here too, alone -- it was deleted.
_CLEVEREF = re.compile(
    r"\\(cref|Cref|cpageref|Cpageref|crefrange|Crefrange)\s*\{([^}]*)\}"
    r"(?:\s*\{([^}]*)\})?")
#: A footnote in an example, by its name (inline.note_name): the text:id
#: of an ODF note, the bookmark around an OOXML one's mark.
_EXAMPLE_NOTE = re.compile(r'"lxftn(\d+)"')


#: hyperref's \autoref names a heading by its level; an unnumbered one --
#: \section*, \paragraph -- is "section" (measured: "section 1.1.1").
_HEADING_LEVELS = {1: "section", 2: "subsection", 3: "subsubsection"}


def _word(names: Names, target, cmd: str) -> str:
    """The name \\cref, \\Cref, \\autoref or \\cpageref prints before *target*."""
    if cmd.lower() == "cpageref":
        return names.cref("page", capital=cmd[0] == "C")
    if isinstance(target, (Float, Footnote, Item, Equation)):
        kind = (target.kind if isinstance(target, Float)
                else "footnote" if isinstance(target, Footnote)
                else "equation" if isinstance(target, Equation) else "item")
    elif cmd == "autoref":
        if target.appendix and target.level == 1:
            return names.autoref("appendix")     # "Appendix A"
        return names.autoref(_HEADING_LEVELS.get(target.level, "section")
                             if target.number else "section")
    else:
        kind = "section"
    if cmd == "autoref":
        return names.autoref(kind)
    return names.cref(kind, capital=cmd == "Cref")


def _text_of(inlines: Any) -> str:
    out: list[str] = []
    stack = list(inlines) if isinstance(inlines, list) else [inlines]
    while stack:
        node = stack.pop(0)
        if not isinstance(node, dict):
            continue
        t, c = node.get("t"), node.get("c")
        if t == "Str":
            out.append(c)
        elif t in ("Space", "SoftBreak", "LineBreak"):
            out.append(" ")
        elif isinstance(c, list):
            stack = [x for x in c if isinstance(x, dict)] + stack
    return "".join(out)


ENV_NAME = re.compile(r"\\begin\s*\{([^}]*)\}")


def _free_trapped_placeholders(node: Any, warn: Callable[[str], None]) -> Any:
    r"""Lift placeholders out of raw LaTeX pandoc could not parse.

    An environment pandoc does not know -- ``multicols`` is the one a real
    paper hit -- arrives whole, as one ``RawBlock "latex"`` holding its own
    ``\begin``, its content and its ``\end``.  The ODT and docx writers drop
    a raw LaTeX block, so a placeholder inside one is not a placeholder at
    all: it never becomes a Para, the injector never sees it, and the
    example is simply gone from the output.  The count at the end of a run
    catches it, which is how this was found, but catching is not keeping.

    Splitting the raw block at each placeholder gives the injector the Para
    it needs and leaves the LaTeX either side as raw, exactly as unhandled
    as it already was.  No general list of environments to maintain: this
    works for any construct that comes back raw.

    The expansion happens in place in whatever list the raw block sits in.
    That is safe without knowing which lists hold blocks, because a
    ``RawBlock`` can only ever BE an element of a block list -- so a list
    containing one is a block list.
    """
    if isinstance(node, list):
        out = []
        for item in node:
            item = _free_trapped_placeholders(item, warn)
            if isinstance(item, dict) and item.get("t") == "RawBlock":
                fmt, text = (item.get("c") or ["", ""])[:2]
                if fmt in ("latex", "tex") and PLACEHOLDER_RE.search(text):
                    out.extend(_split_raw(text, warn))
                    continue
            out.append(item)
        return out
    if isinstance(node, dict):
        if node.get("c") is not None:
            node = dict(node)
            node["c"] = _free_trapped_placeholders(node["c"], warn)
        return node
    return node


def _split_raw(text: str, warn: Callable[[str], None]) -> list[dict]:
    """One raw LaTeX block as raw/placeholder/raw/... in source order."""
    env = ENV_NAME.search(text)
    where = f" inside \\begin{{{env.group(1)}}}" if env else ""
    out: list[dict] = []
    pos = 0
    for m in PLACEHOLDER_RE.finditer(text):
        before = text[pos : m.start()]
        if before.strip():
            out.append({"t": "RawBlock", "c": ["latex", before]})
        out.append({"t": "Para", "c": [{"t": "Str", "c": m.group(0)}]})
        pos = m.end()
        warn(
            f"example{where} was inside LaTeX pandoc kept raw; the example is "
            f"recovered but the surrounding markup is not carried over"
        )
    rest = text[pos:]
    if rest.strip():
        out.append({"t": "RawBlock", "c": ["latex", rest]})
    return out


def _placeholder_index(block: dict) -> int | None:
    if block.get("t") not in ("Para", "Plain"):
        return None
    text = _text_of(block.get("c", [])).strip()
    m = PLACEHOLDER_RE.fullmatch(text)
    return int(m.group(1)) if m else None


def _raw_inline(fmt: str, xml: str) -> dict:
    return {"t": "RawInline", "c": [fmt, xml]}


def _link_reference(node: dict) -> str | None:
    """The label a Link stands for, if pandoc made it from \\ref."""
    try:
        attrs = node["c"][0][2]
    except (KeyError, IndexError, TypeError):
        return None
    kv = dict(attrs)
    if kv.get("reference-type") not in ("ref", "eqref", None):
        return None
    return kv.get("reference")


def _with_word(word: str, field: dict) -> dict:
    """*field* after *word* and an unbreakable space, as cleveref's ~."""
    if not word:
        return field
    return {"t": "Span", "c": [["", [], []],
                               [{"t": "Str", "c": word + "\u00a0"}, field]]}


class Injector:
    def __init__(
        self,
        blocks_by_index: dict[int, str],
        labels: dict[str, tuple[int, str]],
        warn: Callable[[str], None] | None = None,
        emitter=None,
        custom_labels: dict[str, tuple[str, str]] | None = None,
        names: Names | None = None,
        equations_within: int | None = None,
    ) -> None:
        self.blocks = blocks_by_index
        self.labels = labels
        # A reference to an example written \ex.[(7)] prints its label
        # (linguexx 1.4): plain text, the same in every format, and no field,
        # since a custom label is not a counter and nothing renumbers it.
        self.custom_labels = custom_labels or {}
        # the names a reference prints, in the document's language
        self.names = names or ENGLISH
        # \numberwithin{equation}{...}: the heading level, or None
        self.equations_within = equations_within
        self.warn = warn or (lambda _m: None)
        # The emitter decides what a reference and a raw block ARE; this
        # pass only decides where they go.
        self.emitter = emitter
        self.fmt = getattr(emitter, "RAW_FORMAT", "opendocument")
        self.placeholders_replaced = 0
        self.refs_rewritten = 0
        # the example blocks this pass made, by identity: a separator goes
        # between two of THESE, never between an example and raw markup the
        # document itself carried
        self._examples: set[int] = set()
        # what a reference can point at besides an example: headings and
        # captioned floats by identity, footnotes by the \label in them,
        # all of them by label (self.targets); filled by run()
        self._headings: dict[int, Any] = {}
        self._floats: dict[int, Float] = {}
        self._notes: dict[str, Footnote] = {}
        self._item_marks: dict[int, tuple[str, int]] = {}
        self._list_depths: dict[int, int] = {}
        self._equations = None
        self.targets: dict[str, Any] = {}

    def run(self, doc: dict) -> dict:
        doc = dict(doc)
        blocks = _free_trapped_placeholders(doc.get("blocks", []), self.warn)
        if self.emitter is not None:
            inline = getattr(self.emitter, "inline", None)

            def example_notes(node: dict) -> list[int]:
                idx = _placeholder_index(node)
                if idx is None or idx not in self.blocks:
                    return []
                return [int(k) for k in _EXAMPLE_NOTE.findall(self.blocks[idx])]

            found = targets(blocks, example_notes,
                            getattr(inline, "note_labels", None),
                            self.equations_within)
            self._headings = {id(h): sec for h, sec in found.headings}
            self._floats = {id(n): f for n, f in found.floats}
            self._notes = {n.ident: n for n in found.footnotes}
            self._item_marks = found.lists.marks
            self._list_depths = found.lists.depths
            self._equations = found.equations
            self.targets = found.by_label()
        # the body is a block list like any other: through _node, so that
        # _separate sees it -- mapping it item by item here skipped exactly
        # the list consecutive examples almost always sit in
        doc["blocks"] = self._node(blocks)
        return doc

    def _node(self, node):
        """One uniform recursion.  Placeholder Paras and \\ref nodes are
        the only things rewritten; everything else is copied through with
        its children transformed."""
        if isinstance(node, list):
            out: list = []
            for x in node:
                done = self._node(x)
                # a block that became several (_numbered_equations)
                if isinstance(x, dict) and isinstance(done, list):
                    out.extend(done)
                else:
                    out.append(done)
            return self._separate(out)
        if not isinstance(node, dict):
            return node

        idx = _placeholder_index(node)
        if idx is not None:
            if idx in self.blocks:
                self.placeholders_replaced += 1
                block = {"t": "RawBlock", "c": [self.fmt, self.blocks[idx]]}
                self._examples.add(id(block))
                return block
            self.warn(f"placeholder {idx} survived into the AST with no example to put back")

        if is_appendix_mark(node):
            # read by targets(), and nothing on the page
            return []

        replaced = self._reference(node)
        if replaced is not None:
            return replaced

        sec = self._headings.get(id(node))
        if sec is not None:
            # A bookmark of the converter's own around the title: the one a
            # reference points at, and in an unnumbered heading the sign the
            # postprocess keeps the outline number off it by.
            level, attr, inlines = node["c"]
            start, end = self.emitter.marks(sec.bookmark, sec.serial)
            return {"t": "Header", "c": [level, attr,
                    [_raw_inline(self.fmt, start)] + self._node(inlines)
                    + [_raw_inline(self.fmt, end)]]}

        flt = self._floats.get(id(node))
        if flt is not None:
            return self._numbered_caption(node, flt)

        if id(node) in self._list_depths:
            return self._enumerate(node)

        if (self._equations is not None and node.get("t") in ("Para", "Plain")
                and any(isinstance(x, dict) and id(x) in self._equations.rows
                        for x in node["c"])):
            return self._numbered_equations(node)

        if node.get("c") is not None:
            node = dict(node)
            node["c"] = self._node(node["c"])
        return node

    def _separate(self, items: list) -> list:
        """Put the emitter's separator between two examples that touch.

        Word joins adjacent tables, so a run of examples written one after
        another became a single table there; the emitter says what keeps
        them apart (BaseEmitter.between_examples), this only says where.
        """
        sep = self.emitter.between_examples() if self.emitter else ""
        if not sep:
            return items
        out: list = []
        for item in items:
            if out and self._is_example(out[-1]) and self._is_example(item):
                out.append({"t": "RawBlock", "c": [self.fmt, sep]})
            out.append(item)
        return out

    def _is_example(self, node) -> bool:
        return (isinstance(node, dict) and node.get("t") == "RawBlock"
                and node.get("c", [None])[0] == self.fmt
                and id(node) in self._examples)

    # -- references --------------------------------------------------------
    def _reference(self, node: dict):
        if node.get("t") == "Link":
            label = _link_reference(node)
            if label and label in self.custom_labels:
                return self._custom_reference(label, bare=False)
            if label and label in self.labels:
                index, letter = self.labels[label]
                self.refs_rewritten += 1
                return _raw_inline(self.fmt, self.emitter.reference(index, letter))
            return None
        if node.get("t") == "RawInline":
            fmt, text = (node.get("c") or ["", ""])[:2]
            if fmt in ("latex", "tex"):
                label = _LABEL.fullmatch(str(text))
                if label and label.group(1) in self._notes:
                    # in a footnote: the place the note is found by
                    note = self._notes[label.group(1)]
                    return _raw_inline(self.fmt, self.emitter.point_mark(
                        note.marker, note.serial))
                m = REF_CMD.fullmatch(str(text).strip())
                if m and m.group(2) in self.custom_labels:
                    return self._custom_reference(m.group(2), bare=m.group(1) == "pref")
                many = _CLEVEREF.fullmatch(str(text).strip())
                if many and (many.group(3) is not None or "," in many.group(2)
                             or many.group(2).strip() in self.labels
                             or many.group(2).strip() in self.custom_labels):
                    return self._cleveref(*many.groups())
                any_ref = ANY_REF.fullmatch(str(text).strip())
                if any_ref and any_ref.group(2) in self.targets:
                    return self._target_reference(*any_ref.groups())
                if (any_ref and any_ref.group(1).lower().endswith("pageref")
                        and any_ref.group(2) in self.labels):
                    return self._page_reference(*any_ref.groups())
                if m and m.group(2) in self.labels:
                    index, letter = self.labels[m.group(2)]
                    self.refs_rewritten += 1
                    # \pref prints the bare number.  Built without the
                    # brackets rather than sliced off the finished XML: a
                    # slice is right only while they are one character each.
                    xml = self.emitter.reference(
                        index, letter, bare=m.group(1) == "pref")
                    return _raw_inline(self.fmt, xml)
        return None

    def _target_reference(self, cmd: str, label: str) -> dict:
        target = self.targets[label]
        word, form = _FORMS[cmd]
        if word is None:
            word = _word(self.names, target, cmd)
        self.refs_rewritten += 1
        if isinstance(target, Footnote):
            if form == "title":
                # \nameref to a footnote: LaTeX prints nothing (measured)
                return {"t": "Str", "c": ""}
            xml = self.emitter.note_reference(target, form)
        elif isinstance(target, Float):
            xml = self.emitter.float_reference(target, form)
        elif isinstance(target, Item):
            return self._item_reference(target, form, word)
        elif isinstance(target, Equation):
            return self._equation_reference(target, cmd, form, word)
        else:
            xml = self.emitter.section_reference(target, form)
        return _with_word(word, _raw_inline(self.fmt, xml))

    def _equation_reference(self, eq: Equation, cmd: str, form: str,
                            word: str) -> dict:
        r"""Text, as decided: "1", "(1)" for \eqref, "eq. (1)", "Equation
        (1)", "Equation 1" -- what LaTeX prints (measured).  The page is a
        field: no text could know it."""
        if form == "title":
            if eq.section is None:
                return {"t": "Str", "c": ""}
            return _raw_inline(self.fmt, self.emitter.section_reference(
                eq.section, "title"))
        if form == "page":
            return _with_word(word, _raw_inline(
                self.fmt, self.emitter.bookmark_page(eq.bookmark)))
        shown = f"({eq.number})" if cmd in ("eqref", "cref", "Cref") else eq.number
        return {"t": "Str", "c": f"{word}\u00a0{shown}" if word else shown}

    def _numbered_equations(self, node: dict) -> list | dict:
        """A paragraph with a numbered display equation in it, as one
        paragraph per row of each, its number flush right (EQUATION_PARA),
        and the prose before and after as paragraphs of their own.  Pandoc
        writes the equation with no number, which is all this is for.  An
        equation without one stays as pandoc writes it."""
        out: list = []
        prose: list = []

        def flush() -> None:
            while prose and prose[0].get("t") in ("Space", "SoftBreak"):
                prose.pop(0)
            while prose and prose[-1].get("t") in ("Space", "SoftBreak"):
                prose.pop()
            if prose:
                out.append({"t": node["t"], "c": self._node(list(prose))})
            prose.clear()

        for x in node["c"]:
            rows = self._equations.rows.get(id(x)) if isinstance(x, dict) else None
            if rows is None:
                prose.append(x)
                continue
            flush()
            for row in rows:
                tab = _raw_inline(self.fmt, self.emitter.tab())
                inl = [tab, {"t": "Math", "c": [{"t": "InlineMath"},
                                                "\\displaystyle " + row.math]}]
                if row.number is not None:
                    serial = self._equations.row_serials[id(row)]
                    start, end = self.emitter.marks(f"_Reflxeq{serial}", serial)
                    inl += [_raw_inline(self.fmt, self.emitter.tab()),
                            _raw_inline(self.fmt, start),
                            {"t": "Str", "c": f"({row.number})"},
                            _raw_inline(self.fmt, end)]
                out.append({"t": "Div", "c": [
                    ["", [], [["custom-style", EQUATION_PARA]]],
                    [{"t": "Para", "c": inl}]]})
        flush()
        return out

    def _item_reference(self, item: Item, form: str, word: str) -> dict:
        if form == "title":
            # \nameref to an item prints the section's title it is in
            if item.section is None:
                return {"t": "Str", "c": ""}
            return _raw_inline(self.fmt, self.emitter.section_reference(
                item.section, "title"))
        if form == "page":
            return _with_word(word, _raw_inline(
                self.fmt, self.emitter.bookmark_page(item.path[-1][0])))
        fields = "".join(self.emitter.item_reference(name, shown)
                         for name, shown in item.path)
        return _with_word(word, _raw_inline(self.fmt, fields))

    def _enumerate(self, node: dict) -> dict:
        """An ordered list numbered as article's enumerate numbers it, 1. /
        (a) / i. / A., and its items bookmarked where a reference needs them.

        Only a list in pandoc's DefaultStyle is restyled: one that names its
        own style got it from the document."""
        depth = self._list_depths[id(node)]
        (start, style, delim), entries = node["c"]
        name, punct = list_style(depth, style["t"], delim["t"])
        style, delim = {"t": name}, {"t": punct}
        out = []
        for entry in entries:
            mark = self._item_marks.get(id(entry))
            entry = self._node(entry)
            if mark is not None:
                entry = self._bookmark_item(entry, *mark)
            out.append(entry)
        return {"t": "OrderedList", "c": [[start, style, delim], out]}

    def _bookmark_item(self, blocks: list, name: str, serial: int) -> list:
        """The bookmark around the text of the item's first paragraph, which
        is the paragraph that carries its number."""
        if not blocks or blocks[0].get("t") not in ("Plain", "Para"):
            return [{"t": "Plain", "c": [_raw_inline(
                self.fmt, self.emitter.point_mark(name, serial))]}] + blocks
        start, end = self.emitter.marks(name, serial)
        first = dict(blocks[0])
        first["c"] = ([_raw_inline(self.fmt, start)] + first["c"]
                      + [_raw_inline(self.fmt, end)])
        return [first] + blocks[1:]

    def _cleveref(self, cmd: str, first: str, second: str | None) -> dict:
        r"""\cref and its kin with a list of labels, or a range, as cleveref
        prints them (cleveref.py): "sections 1 to 3 and 5", "(1) and (2)",
        "section 1, table 1, and eq. (1)" -- each number its own field."""
        pages = cmd.lower().endswith("pageref")
        labels = [first] if second is not None else first.split(",")
        entries = [self._entry(label.strip(), pages) for label in labels if label.strip()]
        if second is not None:
            entries.append(self._entry(second.strip(), pages))
        self.refs_rewritten += 1
        capital = cmd[0] == "C"
        if second is not None:
            kind = entries[0].kind
            word = "" if kind == "example" else self.names.cref(kind, True, capital)
            before, between = self.names.range
            parts = (([word + "\u00a0"] if word else []) + ([before] if before else [])
                     + [entries[0], between, entries[1]])
        else:
            parts = phrase(entries, capital, self.names)
        out = [{"t": "Str", "c": p} if isinstance(p, str) else p.target for p in parts]
        return {"t": "Span", "c": [["", [], []], out]}

    def _entry(self, label: str, page: bool) -> Entry:
        r"""One label of a \cref list: its kind, its number to sort by, and
        the field that shows it -- or its page, for \cpageref."""
        raw = lambda xml: _raw_inline(self.fmt, xml)  # noqa: E731
        if label in self.custom_labels:
            custom, letter = self.custom_labels[label]
            br = getattr(self.emitter, "brackets", None) or Brackets()
            return Entry("example", None,
                         {"t": "Str", "c": br.custom_reference(custom, letter, False)})
        if label in self.labels:
            index, letter = self.labels[label]
            if page:
                return Entry("page", None, raw(self.emitter.page_reference(index)))
            return Entry("example", (index, letter) if letter else (index,),
                         raw(self.emitter.reference(index, letter)))
        target = self.targets.get(label)
        if target is None:
            # as LaTeX prints a label it does not know
            self.warn(f"\\cref to {label!r}, which nothing carries: printed as ??")
            return Entry("example", None, {"t": "Str", "c": "??"})
        if page:
            if isinstance(target, Item):
                xml = self.emitter.bookmark_page(target.path[-1][0])
            elif isinstance(target, Equation):
                xml = self.emitter.bookmark_page(target.bookmark)
            elif isinstance(target, Footnote):
                xml = self.emitter.note_reference(target, "page")
            elif isinstance(target, Float):
                xml = self.emitter.float_reference(target, "page")
            else:
                xml = self.emitter.section_reference(target, "page")
            return Entry("page", None, raw(xml))
        if isinstance(target, Item):
            return Entry("item", target.numbers, raw("".join(
                self.emitter.item_reference(name, shown) for name, shown in target.path)))
        if isinstance(target, Equation):
            return Entry("equation", target.key, {"t": "Str", "c": f"({target.number})"})
        if isinstance(target, Footnote):
            return Entry("footnote", (target.number,),
                         raw(self.emitter.note_reference(target, "number")))
        if isinstance(target, Float):
            return Entry(target.kind, (target.number,),
                         raw(self.emitter.float_reference(target, "number")))
        # the appendix's after the rest: "sections 1 and A"
        key = ((int(target.appendix),) + target.numbers) if target.number else None
        return Entry("section", key, raw(self.emitter.section_reference(target, "number")))

    def _numbered_caption(self, node: dict, flt: Float) -> dict:
        r"""The float, its caption numbered as LaTeX numbers it -- "Table 1:
        A table." -- by a live sequence, its title bookmarked for \nameref.
        Pandoc writes the caption without a number."""
        node = dict(node)
        node["c"] = self._node(node["c"])
        inlines = caption_inlines(node)
        if inlines is None:     # pragma: no cover - targets() checked
            return node
        stop: list = []
        last = inlines[-1] if inlines else None
        if last and last.get("t") == "Str" and last["c"].endswith("."):
            inlines = inlines[:-1] + ([{"t": "Str", "c": last["c"][:-1]}]
                                      if last["c"] != "." else [])
            stop = [{"t": "Str", "c": "."}]
        start, end = self.emitter.marks(flt.title_bookmark, flt.serial, slot=1)
        name, sep = self.names.caption(flt.kind)
        numbered = ([{"t": "Str", "c": name}, {"t": "Space"},
                     _raw_inline(self.fmt, self.emitter.caption_number(flt)),
                     {"t": "Str", "c": sep}] + ([] if sep.endswith(" ") else [{"t": "Space"}]) + [
                     _raw_inline(self.fmt, start)] + inlines
                    + [_raw_inline(self.fmt, end)] + stop)
        caption = node["c"][1]
        first = dict(caption[1][0])
        first["c"] = numbered
        node["c"] = list(node["c"])
        node["c"][1] = [caption[0], [first] + list(caption[1][1:])]
        return node

    def _page_reference(self, cmd: str, label: str) -> dict:
        index, _letter = self.labels[label]
        self.refs_rewritten += 1
        word = _FORMS[cmd][0]
        return _with_word(_word(self.names, None, cmd) if word is None else word,
                          _raw_inline(self.fmt, self.emitter.page_reference(index)))

    def _custom_reference(self, label: str, bare: bool) -> dict:
        custom, letter = self.custom_labels[label]
        br = getattr(self.emitter, "brackets", None) or Brackets()
        self.refs_rewritten += 1
        return {"t": "Str", "c": br.custom_reference(custom, letter, bare)}


def inject(doc: dict, blocks_by_index, labels, warn=None,
           emitter=None, custom_labels=None, names=None,
           equations_within=None) -> tuple[dict, Injector]:
    inj = Injector(blocks_by_index, labels, warn, emitter=emitter,
                   custom_labels=custom_labels, names=names,
                   equations_within=equations_within)
    return inj.run(doc), inj


# -- what the writer will delete -----------------------------------------

#: Commands pandoc 3.10 keeps as raw LaTeX that set no text: spacing, page
#: breaks, sizes, document structure.  Each was measured to arrive raw; all
#: are deleted by the writer, and none of the deletions loses a word.  Kept
#: short on purpose -- a name missing here costs a line of warning, a name
#: wrongly here costs a silent loss.
LAYOUT_ONLY = frozenset("""
    noindent indent vspace hspace hfill vfill bigskip medskip smallskip
    newpage clearpage cleardoublepage pagebreak nopagebreak linebreak
    nolinebreak enlargethispage FloatBarrier centering raggedleft
    setlength addtolength pagestyle thispagestyle
    onehalfspacing doublespacing singlespacing sloppy fussy protect
    normalsize small footnotesize large phantom
    maketitle printbibliography bibliographystyle
    appendix frontmatter mainmatter backmatter label selectlanguage
""".split())

_FIRST_CMD = re.compile(r"\s*\\(?:begin\s*\{([^}]*)\}|([a-zA-Z@]+|.))")
#: What freeing an example from an unknown environment leaves behind: the
#: bare opening or closing line, which that rescue already warns about.
_BARE_DELIMITER = re.compile(
    r"\s*(?:\\begin\{[^}]*\}(?:\s*(?:\[[^\]]*\]|\{[^}]*\}))*"
    r"|\\end\{[^}]*\})\s*")
#: A command's star and bracketed or braced arguments, to skip past it.
_ARGUMENTS = re.compile(r"^\*?(?:\s*(?:\[[^\]]*\]|\{[^}]*\}))*")


def report_dropped_latex(doc: dict, warn: Callable[[str], None]) -> None:
    r"""Name the raw LaTeX left in the finished AST, which both writers
    delete.  ``\Next``, an unresolved ``Cite`` and ``\input`` were each
    lost this way, silently, before being fixed one at a time; this is the
    net for the next one.  Citations are skipped: citeproc renders them,
    or ``_degrade_citations`` replaces their fallback and says so."""
    found: dict[str, int] = {}

    def walk(node) -> None:
        if isinstance(node, list):
            for x in node:
                walk(x)
            return
        if not isinstance(node, dict) or node.get("t") == "Cite":
            return
        if node.get("t") in ("RawBlock", "RawInline"):
            fmt, text = (node.get("c") or ["", ""])[:2]
            if fmt in ("latex", "tex"):
                key = _dropped_key(str(text))
                if key:
                    found[key] = found.get(key, 0) + 1
            return
        walk(node.get("c"))

    walk(doc.get("blocks", []))
    if found:
        named = ", ".join(k if n == 1 else f"{k} ({n})"
                          for k, n in found.items())
        warn(f"LaTeX pandoc does not convert, deleted from the output "
             f"(an environment with everything in it): {named}")


def _dropped_key(text: str) -> str | None:
    """What to call a raw fragment in the warning, or None if it holds no
    text.  Layout commands are skipped rather than trusted to speak for
    the fragment: ``\\centering`` before a tree is still a tree."""
    while True:
        if not text.strip() or _BARE_DELIMITER.fullmatch(text):
            return None
        m = _FIRST_CMD.match(text)
        if m is None:
            return text.strip()[:30]
        if m.group(1) is not None:
            return f"\\begin{{{m.group(1)}}}"
        if m.group(2) not in LAYOUT_ONLY:
            return f"\\{m.group(2)}"
        text = _ARGUMENTS.sub("", text[m.end():], count=1)

