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
from .styles import (
    ANNOT_PARA, BAND_PARA, CELL_PARA, JUDGMENT_PARA,
    SPACE_ABOVE_PARA, SPACE_BELOW_PARA, TRANSLATION_PARA,
)
from .styles_docx import LEIPZIG_CHAR
from .ir import Body, Example

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
        + f'<w:r><w:instrText xml:space="preserve"> {instr} </w:instrText></w:r>'
        + '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
        + run(cached)
        + '<w:r><w:fldChar w:fldCharType="end"/></w:r>'
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
    tail = run(letter) if letter else ""
    return (
        (run(left) if left else "")
        + inner + tail
        + (run(right) if right else "")
    )


def run(text: str, small_caps: bool = False) -> str:
    """One run of plain text, optionally in small capitals.

    The face and size are not here any more: they are on the CELL_PARA
    style every cell's paragraph uses, which is where a Word user can
    change them.  Phase 3 put them on every run because nothing declared
    the styles yet, and a column measured for one font and drawn in
    another wraps.
    """
    rpr = (f'<w:rPr><w:rStyle w:val="{LEIPZIG_CHAR}"/></w:rPr>'
           if small_caps else "")
    return f'<w:r>{rpr}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def cell(width_cm: float, content: str, span: int = 1,
         style: str = CELL_PARA) -> str:
    """One table cell, its paragraph carrying a named style.

    The style is what a Word user edits from the Styles pane, and it is
    also where the face and size the column widths were measured against
    live.  A `w:pStyle` naming a style the document does not define is not
    an error -- the reference survives and the paragraph renders with the
    default -- so a missing injection looks like nothing rather than like
    a failure.  See styles_docx.
    """
    grid = f'<w:gridSpan w:val="{span}"/>' if span > 1 else ""
    return (
        f'<w:tc><w:tcPr><w:tcW w:w="{dxa(width_cm)}" w:type="dxa"/>{grid}</w:tcPr>'
        f'<w:p><w:pPr><w:pStyle w:val="{style}"/></w:pPr>{content}</w:p></w:tc>'
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
        return self._table(ex)

    # -- markup -----------------------------------------------------------
    def _number(self, ex: Example) -> str:
        if ex.custom_label:
            return self._runs(ex.custom_label)
        br = self.brackets
        return ((run(br.ex_l) if br.ex_l else "")
                + sequence_field(ex.index)
                + (run(br.ex_r) if br.ex_r else ""))

    def _runs(self, latex: str) -> str:
        r"""LaTeX source as OOXML runs, with its markup interpreted.

        Not esc(): that leaves \lpzg{3sg} in the document as those eleven
        characters.  InlineRenderer.runs() is the converter's own reader and
        gives back (text, is_small_caps) pairs with the commands resolved
        and the quotes turned -- which is also what the width estimator
        measured, so anything else would make the columns the wrong size
        for what is drawn.

        Small capitals are direct formatting here.  A named character style
        a Word user can edit is Phase 4, with the rest of the styles.
        """
        return "".join(run(text, sc) for text, sc in self.inline.runs(latex))

    def _judgment(self, body: Body) -> str:
        return self._runs(body.judgment) if body.judgment else ""

    def _trailer(self, body: Body) -> str:
        parts = []
        if body.translation:
            parts.append(body.translation)
        if body.source:
            parts.append(body.source)
        return " ".join(parts)

    def _table(self, ex: Example) -> str:
        p = self.plan_table(ex)
        widths = p.widths
        grid_cols = "".join(f'<w:gridCol w:w="{dxa(w)}"/>' for w in widths)

        rows: list[str] = []
        for k, (marker, body) in enumerate(p.bodies):
            rows += self._body_rows(ex, marker, body, k == 0, p, k)

        # Spacer rows rather than w:spacing on the first and last
        # paragraphs, which the plan asked to weigh.  Both make the gap a
        # style a user can edit; the rows keep the two targets one shape,
        # so a document converted either way is the same object and one
        # vocabulary explains both.  w:spacing would also have to solve an
        # example whose first row is its last.
        rows = ([self._spacer_row(widths, SPACE_ABOVE_PARA)] + rows
                + [self._spacer_row(widths, SPACE_BELOW_PARA)])

        return (
            f'<w:tbl><w:tblPr><w:tblW w:w="{dxa(sum(widths))}" w:type="dxa"/>'
            f"{TABLE_PR}</w:tblPr>"
            f"<w:tblGrid>{grid_cols}</w:tblGrid>" + "".join(rows) + "</w:tbl>"
        )

    def _spacer_row(self, widths: list[float], style: str) -> str:
        """An empty full-width row whose only job is to be *style*'s height."""
        return ("<w:tr>" + cell(sum(widths), "", span=len(widths), style=style)
                + "</w:tr>")

    # -- rows --------------------------------------------------------------
    def _body_rows(self, ex, marker, body, first, p, body_index) -> list[str]:
        """The same row structure as the ODT target, in OOXML's idiom.

        Which is not the same idiom.  ODF spans a cell and then emits a
        `covered` placeholder for each column swallowed, so every row has
        one element per grid column.  OOXML spans with `w:gridSpan` and
        emits **nothing** for the columns taken: a row's cells must add up
        to the grid by their spans, not by their count.  Emit the
        placeholders here and Word reads a table one column too wide per
        span, which it will happily render as a mess.
        """
        rows: list[str] = []
        head_used = False
        ncols = len(p.columns) + p.filler

        def lead_cells(active: bool) -> str:
            out = [cell(p.lead[0], self._number(ex) if (active and first) else "")]
            i = 1
            if p.has_marker:
                out.append(cell(p.lead[i], self._runs(marker) if active else ""))
                i += 1
            if p.has_judgment:
                out.append(cell(p.lead[i],
                                self._judgment(body) if active else "",
                                style=JUDGMENT_PARA))
            return "".join(out)

        def annot_cell(active: bool) -> str:
            if not p.has_annot:
                return ""
            content = self._runs(body.annot) if (active and body.annot) else ""
            return cell(p.widths[-1], content, style=ANNOT_PARA)

        def body_span(content: str, style: str = CELL_PARA) -> str:
            """One cell across every body column, spans included."""
            return cell(sum(p.columns) + (p.widths[len(p.lead) + len(p.columns)]
                                          if p.filler else 0.0),
                        content, span=ncols, style=style)

        if body.tiers:
            for b, band in enumerate(p.grid.bands_of(body_index)):
                for tr, tier in enumerate(body.tiers):
                    # The first row of a continuation band is marked,
                    # because nothing else in the finished table can say
                    # so: a band's rows are built exactly like a tier's.
                    style = BAND_PARA if b and not tr else CELL_PARA
                    rows.append(
                        "<w:tr>" + lead_cells(not head_used)
                        + self._band_cells(tier.cells, band, p, body_index,
                                           style)
                        + annot_cell(not head_used) + "</w:tr>"
                    )
                    head_used = True
        else:
            rows.append(
                "<w:tr>" + lead_cells(True)
                + body_span(self._runs(body.text))
                + annot_cell(True) + "</w:tr>"
            )
            head_used = True

        trailer = self._trailer(body)
        if trailer:
            rows.append(
                "<w:tr>" + lead_cells(False)
                + body_span(self._runs(trailer), style=TRANSLATION_PARA)
                + annot_cell(False) + "</w:tr>"
            )
        return rows

    def _band_cells(self, cells, band, p, body_index: int,
                    style: str = CELL_PARA) -> str:
        """One tier's cells for one band, padded to the grid by SPAN.

        The padding counts columns, not cells, for the reason in
        _body_rows: a `w:gridSpan` of 3 is one cell that occupies three
        columns, and the row is complete when the spans total the grid.
        """
        start, stop = band
        out, covered = [], 0
        for j in range(start, stop):
            span = p.grid.span(body_index, j)
            content = self._runs(cells[j]) if j < len(cells) else ""
            # The cell's first column is how many this row has covered, not
            # the word's index: a continuation band starts back at column 0,
            # and a paradigm's words land where the grid union put them.
            # Word and LibreOffice lay out from w:tblGrid and never showed
            # the difference; OnlyOffice lays out from w:tcW and drew banded
            # examples as letters in slivers.
            width = sum(p.columns[covered:covered + span])
            out.append(cell(width, content, span=span, style=style))
            covered += span
        remaining = len(p.columns) + p.filler - covered
        if remaining > 0:
            tail = sum(p.columns[covered:]) + (
                p.widths[len(p.lead) + len(p.columns)] if p.filler else 0.0)
            out.append(cell(tail, "", span=remaining, style=style))
        return "".join(out)
