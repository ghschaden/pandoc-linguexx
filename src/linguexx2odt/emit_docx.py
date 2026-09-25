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
r"""Stage 2 for .docx — IR -> one opaque ``openxml`` block per example.

The counterpart of emit_odt.py, not a variation on it: the geometry is
BaseEmitter's and shared, the markup is not.  plan-docx.md records the
measurements this is built on; the ones that shaped the code are:

* **The numbers are `SEQ` fields and the references are `REF`**, so
  inserting an example renumbers the rest.  That is the whole point of the
  tool and it works — measured, including that a pasted copy does not steal
  the original's bookmark.
* **Cached values are written CORRECT** (fact 12).  A field carries the
  text a reader shows when it does not recalculate, and readers differ:
  LibreOffice recalculates on open, OnlyOffice 9.4 does not.  So the cache
  is not a hint to be fixed later, it is what somebody sees.  The field
  stays live either way, which is what makes editing renumber.
* **Cell margins are zeroed** (fact 8).  OOXML insets a cell's content by
  108 twips a side, which the width estimate knows nothing about; leave it
  and every word wraps.
* **The table spans the text block, slack in a trailing filler column**
  (fact 9) — the rule the ODT emitter already follows.  A narrow table with
  declared widths rendered at 69% of them.
* **`w:tblLayout` must be `fixed`** (fact 4), or a reader re-fits the
  columns and the declared widths are a suggestion.

Phase 2 of the plan: plain examples, numbers and references.  A glossed
example, a judgment, a sub-example or a band is not emitted here yet and
says so rather than coming out wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .emit_base import BaseEmitter, register
from .inline import esc
from .ir import Example

#: twentieths of a point per centimetre, which is what OOXML measures in
DXA = 566.93


def dxa(cm: float) -> int:
    return int(round(cm * DXA))


def bookmark_name(index: int) -> str:
    """Word bookmark names are restricted; an example's index is safe."""
    return f"NumEx{index}"


def field_run(instr: str, cached: str) -> str:
    r"""A Word field: begin, instruction, cached result, end.

    *cached* is what a reader that does not recalculate will show, so it is
    the caller's job to make it right.  See fact 12.
    """
    return (
        '<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
        f'<w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
        '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        f"<w:r><w:t>{esc(cached)}</w:t></w:r>"
        '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
    )


def sequence_field(index: int, seq: str = "NumEx") -> str:
    """The example number: a live counter, cached at its correct value.

    Bookmarked around the field alone and not the line, which is what makes
    a reference give back "3" rather than "(3) the whole example" — fact 3,
    and the difference is not cosmetic.
    """
    name = bookmark_name(index)
    return (
        f'<w:bookmarkStart w:id="{index + 1}" w:name="{name}"/>'
        + field_run(f"SEQ {seq} \\* ARABIC", str(index + 1))
        + f'<w:bookmarkEnd w:id="{index + 1}"/>'
    )


def sequence_ref(index: int, letter: str = "", brackets=None,
                 bare: bool = False) -> str:
    """A reference to that bookmark, cached at the number it resolves to."""
    from .latexutil import Brackets

    br = brackets or Brackets()
    left, right = ("", "") if bare else (esc(br.ex_l), esc(br.ex_r))
    inner = field_run(f"REF {bookmark_name(index)} \\h", str(index + 1))
    tail = f"<w:r><w:t>{esc(letter)}</w:t></w:r>" if letter else ""
    return (
        (f"<w:r><w:t>{left}</w:t></w:r>" if left else "")
        + inner + tail
        + (f"<w:r><w:t>{right}</w:t></w:r>" if right else "")
    )


def run(text: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def cell(width_cm: float, content: str, span: int = 1) -> str:
    grid = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{dxa(width_cm)}" w:type="dxa"/>{grid}</w:tcPr>'
        f"<w:p>{content}</w:p></w:tc>"
    )


#: Zeroed insets and a fixed layout.  Facts 8 and 4: without the first every
#: word wraps, and without the second the declared widths are a suggestion.
TABLE_PR = (
    '<w:tblLayout w:type="fixed"/>'
    "<w:tblCellMar>"
    '<w:top w:w="0" w:type="dxa"/><w:left w:w="0" w:type="dxa"/>'
    '<w:bottom w:w="0" w:type="dxa"/><w:right w:w="0" w:type="dxa"/>'
    "</w:tblCellMar>"
)


@register("docx")
@dataclass
class DocxEmitter(BaseEmitter):
    """Office Open XML.  The geometry is BaseEmitter's; this writes w:tbl."""

    RAW_FORMAT: ClassVar[str] = "openxml"

    def reference(self, index: int, letter: str = "",
                  bare: bool = False) -> str:
        return sequence_ref(index, letter, self.brackets, bare=bare)

    def example(self, ex: Example) -> str:
        """One example as a table.  Phase 2: plain bodies only."""
        if ex.body is None or ex.body.tiers or ex.items:
            what = ("a gloss" if (ex.body and ex.body.tiers)
                    else "sub-examples" if ex.items else "this shape")
            self.warnings.append(
                f"line {ex.line}: the .docx target cannot lay out {what} yet "
                f"(Phase 3 of plan-docx.md); example {ex.index + 1} is "
                f"emitted as plain text, so its number is live but its "
                f"columns are not")
        return self._table(ex)

    # -- markup -----------------------------------------------------------
    def _number(self, ex: Example) -> str:
        if ex.custom_label:
            return run(ex.custom_label)
        br = self.brackets
        return (run(br.ex_l) if br.ex_l else "") + sequence_field(ex.index) + (
            run(br.ex_r) if br.ex_r else "")

    def _body_text(self, ex: Example) -> str:
        """Everything the example says, as running text.

        Phase 2 does not build a column grid, so a glossed example's tiers
        are joined rather than aligned.  That is wrong on the page and
        announced in example(); it is not wrong silently.
        """
        body = ex.body
        if body is None:
            return " ".join(
                f"{it.marker} {it.body.text}".strip() for it in ex.items)
        parts = [body.judgment + body.text if body.judgment else body.text]
        for tier in body.tiers:
            parts.append(" ".join(tier.cells))
        if body.translation:
            parts.append(body.translation)
        if body.annot:
            parts.append(body.annot)
        return " ".join(p for p in parts if p)

    def _table(self, ex: Example) -> str:
        lay = self.layout
        number_cm = lay.number_cm
        text_cm = lay.text_width_cm - number_cm
        widths = [number_cm, text_cm]
        grid = "".join(f'<w:gridCol w:w="{dxa(w)}"/>' for w in widths)
        row = (
            "<w:tr>"
            + cell(widths[0], self._number(ex))
            + cell(widths[1], run(self._body_text(ex)))
            + "</w:tr>"
        )
        return (
            f'<w:tbl><w:tblPr><w:tblW w:w="{dxa(lay.text_width_cm)}" w:type="dxa"/>'
            f"{TABLE_PR}</w:tblPr>"
            f"<w:tblGrid>{grid}</w:tblGrid>{row}</w:tbl>"
        )
