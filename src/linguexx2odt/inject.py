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

REF_CMD = re.compile(r"\\(p?ref)\s*\{([^}]*)\}")


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


class Injector:
    def __init__(
        self,
        blocks_by_index: dict[int, str],
        labels: dict[str, tuple[int, str]],
        warn: Callable[[str], None] | None = None,
        emitter=None,
    ) -> None:
        self.blocks = blocks_by_index
        self.labels = labels
        self.warn = warn or (lambda _m: None)
        # The emitter decides what a reference and a raw block ARE; this
        # pass only decides where they go.
        self.emitter = emitter
        self.fmt = getattr(emitter, "RAW_FORMAT", "opendocument")
        self.placeholders_replaced = 0
        self.refs_rewritten = 0

    def run(self, doc: dict) -> dict:
        doc = dict(doc)
        doc["blocks"] = [self._node(b) for b in doc.get("blocks", [])]
        return doc

    def _node(self, node):
        """One uniform recursion.  Placeholder Paras and \\ref nodes are
        the only things rewritten; everything else is copied through with
        its children transformed."""
        if isinstance(node, list):
            return [self._node(x) for x in node]
        if not isinstance(node, dict):
            return node

        idx = _placeholder_index(node)
        if idx is not None:
            if idx in self.blocks:
                self.placeholders_replaced += 1
                return {"t": "RawBlock", "c": [self.fmt, self.blocks[idx]]}
            self.warn(f"placeholder {idx} survived into the AST with no example to put back")

        replaced = self._reference(node)
        if replaced is not None:
            return replaced

        if node.get("c") is not None:
            node = dict(node)
            node["c"] = self._node(node["c"])
        return node

    # -- references --------------------------------------------------------
    def _reference(self, node: dict):
        if node.get("t") == "Link":
            label = _link_reference(node)
            if label and label in self.labels:
                index, letter = self.labels[label]
                self.refs_rewritten += 1
                return _raw_inline(self.fmt, self.emitter.reference(index, letter))
            return None
        if node.get("t") == "RawInline":
            fmt, text = (node.get("c") or ["", ""])[:2]
            if fmt in ("latex", "tex"):
                m = REF_CMD.fullmatch(str(text).strip())
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


def inject(doc: dict, blocks_by_index, labels, warn=None,
           emitter=None) -> tuple[dict, Injector]:
    inj = Injector(blocks_by_index, labels, warn, emitter=emitter)
    return inj.run(doc), inj
