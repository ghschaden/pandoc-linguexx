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
from .latexutil import Brackets
from .sections import AUTOREF_NAMES, sections

REF_CMD = re.compile(r"\\(p?ref)\s*\{([^}]*)\}")
#: Every reference command a section label can be given to, and \pageref,
#: which an example's can.
ANY_REF = re.compile(
    r"\\(ref|pref|cref|Cref|autoref|nameref|pageref|cpageref|Cpageref)"
    r"\s*\{([^}]*)\}")
#: What each prints before the field: cleveref's and hyperref's names, as
#: LaTeX sets them (measured, plan-crossrefs.md), with their unbreakable
#: space.  None is \autoref's, whose name depends on the heading's level.
_SECTION_FORMS = {
    "ref": ("", "number"), "pref": ("", "number"),
    "cref": ("section", "number"), "Cref": ("Section", "number"),
    "autoref": (None, "number"), "nameref": ("", "title"),
    "pageref": ("", "page"), "cpageref": ("page", "page"),
    "Cpageref": ("Page", "page"),
}


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
    ) -> None:
        self.blocks = blocks_by_index
        self.labels = labels
        # A reference to an example written \ex.[(7)] prints its label
        # (linguexx 1.4): plain text, the same in every format, and no field,
        # since a custom label is not a counter and nothing renumbers it.
        self.custom_labels = custom_labels or {}
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
        # headings, by identity and by label; filled by run()
        self._headings: dict[int, Any] = {}
        self.sections: dict[str, Any] = {}

    def run(self, doc: dict) -> dict:
        doc = dict(doc)
        blocks = _free_trapped_placeholders(doc.get("blocks", []), self.warn)
        if self.emitter is not None:
            found = sections(blocks)
            self._headings = {id(h): sec for h, sec in found}
            self.sections = {sec.ident: sec for _h, sec in found if sec.ident}
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
            return self._separate([self._node(x) for x in node])
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

        replaced = self._reference(node)
        if replaced is not None:
            return replaced

        sec = self._headings.get(id(node))
        if sec is not None:
            # A bookmark of the converter's own around the title: the one a
            # reference points at, and in an unnumbered heading the sign the
            # postprocess keeps the outline number off it by.
            level, attr, inlines = node["c"]
            start, end = self.emitter.heading_marks(sec)
            return {"t": "Header", "c": [level, attr,
                    [_raw_inline(self.fmt, start)] + self._node(inlines)
                    + [_raw_inline(self.fmt, end)]]}

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
                m = REF_CMD.fullmatch(str(text).strip())
                if m and m.group(2) in self.custom_labels:
                    return self._custom_reference(m.group(2), bare=m.group(1) == "pref")
                any_ref = ANY_REF.fullmatch(str(text).strip())
                if any_ref and any_ref.group(2) in self.sections:
                    return self._section_reference(*any_ref.groups())
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

    def _section_reference(self, cmd: str, label: str) -> dict:
        sec = self.sections[label]
        word, form = _SECTION_FORMS[cmd]
        if word is None:
            word = AUTOREF_NAMES.get(sec.level, "section")
        self.refs_rewritten += 1
        return _with_word(word, _raw_inline(
            self.fmt, self.emitter.section_reference(sec, form)))

    def _page_reference(self, cmd: str, label: str) -> dict:
        index, _letter = self.labels[label]
        self.refs_rewritten += 1
        return _with_word(_SECTION_FORMS[cmd][0], _raw_inline(
            self.fmt, self.emitter.page_reference(index)))

    def _custom_reference(self, label: str, bare: bool) -> dict:
        custom, letter = self.custom_labels[label]
        br = getattr(self.emitter, "brackets", None) or Brackets()
        self.refs_rewritten += 1
        return {"t": "Str", "c": br.custom_reference(custom, letter, bare)}


def inject(doc: dict, blocks_by_index, labels, warn=None,
           emitter=None, custom_labels=None) -> tuple[dict, Injector]:
    inj = Injector(blocks_by_index, labels, warn, emitter=emitter,
                   custom_labels=custom_labels)
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

